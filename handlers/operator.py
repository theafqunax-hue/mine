from decimal import Decimal
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from models import Order, OrderStatus, User, SavedPayout, Operator
from services.orders import atomic_assign
from keyboards import operator_paid
from config import Config

router = Router()
logger = logging.getLogger(__name__)


async def _is_operator_or_owner(session, telegram_id: int, config: Config) -> bool:
    if telegram_id == config.owner_admin_id:
        return True
    operator = await session.scalar(select(Operator).where(
        Operator.telegram_id == telegram_id,
        Operator.enabled == True,
    ))
    return operator is not None


@router.callback_query(lambda c: c.data.startswith("op:"))
async def operator_action(callback: CallbackQuery, session, config: Config, bot):
    if not await _is_operator_or_owner(session, callback.from_user.id, config):
        await callback.answer("You are not authorized for operator actions.", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[1]
    order_id = int(parts[2])
    order = await session.get(Order, order_id)
    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return

    if action == "view":
        await callback.answer(
            f"#{order.id} {order.asset} {order.crypto_amount} {order.payment_method}",
            show_alert=True,
        )
        return

    if action == "reject":
        if order.status != OrderStatus.PENDING_REVIEW.value:
            await callback.answer("Order is no longer pending.", show_alert=True)
            return
        order.status = OrderStatus.REJECTED.value
        await session.commit()

        user = await session.get(User, order.user_id)
        if user:
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"Order #{order.id} Rejected ❌\n\n"
                    "Your payment proof could not be approved, so this order has been marked as rejected.\n\n"
                    "If you believe this is a mistake, please contact Support.",
                )
            except Exception:
                logger.exception("Could not notify user %s about rejection", user.telegram_id)

        # Never edit old work-group messages. Post a fresh status message.
        if config.review_group_id:
            await bot.send_message(
                config.review_group_id,
                f"❌ ORDER REJECTED\n\nOrder: #{order.id}\nRejected by: {callback.from_user.id}",
            )
        await callback.answer("Order rejected.")
        return

    if action == "accept":
        ok, assigned = await atomic_assign(
            session,
            order.id,
            callback.from_user.id,
            order.payment_method,
            Decimal(order.crypto_amount),
            owner_admin_id=config.owner_admin_id,
        )
        if not ok:
            await session.rollback()
            await callback.answer("You are not eligible, or this order was already taken.", show_alert=True)
            return
        await session.commit()

        user = await session.get(User, order.user_id)
        if user:
            await bot.send_message(
                user.telegram_id,
                "✅ Payment Verified!\n\n"
                f"Your order #{order.id} has been accepted and is now being processed.\n"
                f"Amount: {order.crypto_amount} {order.asset}\n"
                f"Expected INR: ₹{order.inr_amount:.2f}\n\n"
                "Please add your payment method below to receive your funds.",
            )
            saved = await session.scalar(select(SavedPayout).where(
                SavedPayout.user_id == user.id,
                SavedPayout.payment_method == order.payment_method,
            ))
            from keyboards import payout_choices
            await bot.send_message(
                user.telegram_id,
                "Payout details are required now.",
                reply_markup=payout_choices(order.payment_method, bool(saved)),
            )

        # Never edit the original order/proof message. Post a fresh status message.
        if config.review_group_id:
            await bot.send_message(
                config.review_group_id,
                f"✅ ORDER ACCEPTED\n\nOrder: #{order.id}\nAccepted by: {callback.from_user.id}\n"
                "Waiting for payout details from the user.",
            )
        await callback.answer("Order assigned.")
        return

    if action == "paid":
        if order.status != OrderStatus.PROCESSING.value:
            await callback.answer("Payout details are not ready yet.", show_alert=True)
            return
        if not order.payout_proof_file_id:
            await callback.answer("Send the payment screenshot in this work group first.", show_alert=True)
            return
        if order.assigned_operator_id:
            op = await session.get(Operator, order.assigned_operator_id)
            if not op or (op.telegram_id != callback.from_user.id and callback.from_user.id != config.owner_admin_id):
                await callback.answer("Only the assigned operator can complete this order.", show_alert=True)
                return
        else:
            await callback.answer("No operator is assigned to this order.", show_alert=True)
            return

        order.status = OrderStatus.COMPLETED.value
        await session.commit()
        user = await session.get(User, order.user_id)
        if user:
            await bot.send_message(
                user.telegram_id,
                "Payment has been made❤️ Account unfrozen.\n"
                "Chat Mode is now OFF."
            )
            bot_info = await bot.get_me()
            bot_username = bot_info.username or "PW_P2PBot"
            vouch_text = (
                f"vouched @{bot_username} for {Decimal(order.crypto_amount):.2f}$\n"
                "safe exchange."
            )
            from aiogram.enums import ParseMode
            from html import escape
            await bot.send_message(
                user.telegram_id,
                "Copy-paste to vouch:\n\n"
                f"<pre>{escape(vouch_text)}</pre>",
                parse_mode=ParseMode.HTML,
            )

        # Never edit the payout-details message. Post a fresh completion message.
        if config.review_group_id:
            await bot.send_message(
                config.review_group_id,
                f"💰 PAYMENT SENT\n\nOrder: #{order.id}\nStatus: COMPLETED\n"
                f"Paid by: {callback.from_user.id}",
            )
        await callback.answer("Payment marked as sent.")
        return


async def _latest_processing_order_for_operator(session, telegram_id: int, config: Config):
    if telegram_id == config.owner_admin_id:
        return await session.scalar(select(Order).where(
            Order.status == OrderStatus.PROCESSING.value,
        ).order_by(Order.id.desc()))

    op = await session.scalar(select(Operator).where(
        Operator.telegram_id == telegram_id,
        Operator.enabled == True,
    ))
    if not op:
        return None
    return await session.scalar(select(Order).where(
        Order.status == OrderStatus.PROCESSING.value,
        Order.assigned_operator_id == op.id,
    ).order_by(Order.id.desc()))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.photo)
async def operator_payment_photo(message: Message, session, config: Config, bot):
    if not config.review_group_id or message.chat.id != config.review_group_id:
        return
    if not await _is_operator_or_owner(session, message.from_user.id, config):
        return

    order = await _latest_processing_order_for_operator(session, message.from_user.id, config)
    if not order:
        return
    order.payout_proof_file_id = message.photo[-1].file_id
    await session.commit()
    await message.answer(
        f"📸 Payment screenshot received for Order #{order.id}.\n\n"
        "Now press Payment Sent.",
        reply_markup=operator_paid(order.id),
    )


@router.message(F.chat.type.in_({"group", "supergroup"}), F.document)
async def operator_payment_document(message: Message, session, config: Config, bot):
    if not config.review_group_id or message.chat.id != config.review_group_id:
        return
    if not await _is_operator_or_owner(session, message.from_user.id, config):
        return
    if not (message.document.mime_type or "").startswith("image/"):
        return

    order = await _latest_processing_order_for_operator(session, message.from_user.id, config)
    if not order:
        return
    order.payout_proof_file_id = message.document.file_id
    await session.commit()
    await message.answer(
        f"📸 Payment screenshot received for Order #{order.id}.\n\n"
        "Now press Payment Sent.",
        reply_markup=operator_paid(order.id),
    )
