from decimal import Decimal, InvalidOperation
from aiogram import Router, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from models import PaymentMethod, Asset, Network, AssetNetwork, WalletAddress, Order, User, SavedPayout, OrderStatus
from keyboards import methods, confirm, assets, networks, payment_proof, payout_choices, main_menu, cdm_banks
from services.pricing import get_rate, get_rate_tiers
from config import Config

router = Router()

class SellFlow(StatesGroup):
    method = State()
    amount = State()
    summary = State()
    asset = State()
    network = State()
    payment = State()
    proof = State()
    payout = State()

async def get_user(session, tg_id):
    return await session.scalar(select(User).where(User.telegram_id == tg_id))


def display_amount(value: Decimal) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


async def replace_message_with_text(message: Message, text: str, reply_markup=None):
    """Edit text messages; replace media messages with a clean text message.

    The welcome screen is an image, so Telegram cannot use edit_text() on it.
    Replacing the media message also keeps the rest of the sell flow as a
    normal editable text message.
    """
    if message.text is not None:
        return await message.edit_text(text, reply_markup=reply_markup)
    await message.delete()
    return await message.answer(text, reply_markup=reply_markup)

async def begin_sell(message: Message, state: FSMContext, session):
    await state.clear()
    enabled = (await session.execute(
        select(PaymentMethod.code).where(PaymentMethod.enabled == True)
    )).scalars().all()
    await state.set_state(SellFlow.method)
    await message.answer(
        "Sell your crypto in multiple methods 👇",
        reply_markup=methods(enabled),
    )


@router.callback_query(lambda c: c.data == "sell")
async def sell_start(callback: CallbackQuery, state: FSMContext, session):
    await state.clear()
    enabled = (await session.execute(
        select(PaymentMethod.code).where(PaymentMethod.enabled == True)
    )).scalars().all()
    await state.set_state(SellFlow.method)
    await replace_message_with_text(
        callback.message,
        "Sell your crypto in multiple methods 👇",
        methods(enabled),
    )
    await callback.answer()

@router.callback_query(SellFlow.method, F.data.startswith("method:"))
async def choose_method(callback: CallbackQuery, state: FSMContext, session):
    method = callback.data.split(":", 1)[1]
    enabled = await session.scalar(select(PaymentMethod).where(
        PaymentMethod.code == method, PaymentMethod.enabled == True
    ))
    if not enabled:
        await callback.answer("This payment method is unavailable.", show_alert=True)
        return
    await state.update_data(payment_method=method)
    tiers = await get_rate_tiers(session, method)
    rate_lines = []
    for tier in tiers:
        lo = display_amount(Decimal(tier.min_amount))
        if tier.max_amount is None:
            amount_range = f"${lo}+"
        else:
            hi = display_amount(Decimal(tier.max_amount))
            amount_range = f"${lo}-${hi}"
        rate_lines.append(f"▪️ {amount_range} : {Decimal(tier.rate):.2f}₹")

    await state.set_state(SellFlow.amount)
    await replace_message_with_text(
        callback.message,
        "Important - You may get funds in multiple shots, if the order is bigger than 25K⚡\n"
        "(100% Safe)\n\n"
        f"EXCHANGE RATES FOR {method} 👇\n\n"
        + "\n".join(rate_lines)
        + "\n\nEnter Amount in $ you want to sell : 🪙"
    )
    await callback.answer()

@router.message(SellFlow.amount)
async def enter_amount(message: Message, state: FSMContext, session):
    try:
        amount = Decimal(message.text.strip())
    except (InvalidOperation, AttributeError):
        await message.answer("Enter a valid amount in $.")
        return

    if amount <= 0:
        await message.answer("Amount must be greater than 0.")
        return

    if amount.as_tuple().exponent < -2:
        await message.answer("Maximum 2 decimal places are allowed.")
        return

    data = await state.get_data()
    rate = await get_rate(session, data["payment_method"], amount)
    if rate is None:
        await message.answer("Minimum sell amount is $10.")
        return

    inr = amount * rate
    await state.update_data(amount=str(amount), rate=str(rate), inr=str(inr))
    # The token buttons are the next step. The previous build left the FSM
    # in `summary`, so clicking USDT/SOL/USDC had no matching handler.
    await state.set_state(SellFlow.asset)
    await message.answer(
        f"You will receive approx: ₹{inr:.2f}🪙\n\n"
        "Select Your Crypto Token 👇",
        reply_markup=assets(),
    )

@router.callback_query(SellFlow.summary, F.data == "continue")
async def continue_to_asset(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellFlow.asset)
    await callback.message.edit_text("Select Your Crypto Token 👇", reply_markup=assets())
    await callback.answer()

@router.callback_query(SellFlow.asset, F.data.startswith("asset:"))
async def choose_asset(callback: CallbackQuery, state: FSMContext, session):
    asset = callback.data.split(":", 1)[1]
    obj = await session.scalar(select(Asset).where(Asset.code == asset, Asset.enabled == True))
    if not obj:
        await callback.answer("Asset unavailable.", show_alert=True)
        return
    await state.update_data(asset=asset)
    rows = (await session.execute(
        select(Network.code)
        .join(AssetNetwork, AssetNetwork.network_id == Network.id)
        .where(AssetNetwork.asset_id == obj.id, AssetNetwork.enabled == True, Network.enabled == True)
        .order_by(Network.id)
    )).scalars().all()
    if not rows:
        await callback.answer("No public wallet address is configured for this token yet.", show_alert=True)
        return
    await state.set_state(SellFlow.network)
    await replace_message_with_text(
        callback.message,
        f"🔗 Select Network Chain for {asset} 👇",
        networks(rows),
    )
    await callback.answer()

@router.callback_query(SellFlow.network, F.data.startswith("network:"))
async def choose_network(callback: CallbackQuery, state: FSMContext, session):
    network = callback.data.split(":", 1)[1]
    data = await state.get_data()
    asset = await session.scalar(select(Asset).where(Asset.code == data["asset"]))
    net = await session.scalar(select(Network).where(Network.code == network))
    if not asset or not net:
        await callback.answer("Invalid token/network.", show_alert=True)
        return

    compatible = await session.scalar(select(AssetNetwork).where(
        AssetNetwork.asset_id == asset.id,
        AssetNetwork.network_id == net.id,
        AssetNetwork.enabled == True,
    ))
    wallet = await session.scalar(select(WalletAddress).where(
        WalletAddress.asset_id == asset.id,
        WalletAddress.network_id == net.id,
        WalletAddress.enabled == True,
    ))
    if not compatible or not wallet or not wallet.address.strip():
        await callback.answer("Public receiving address is not configured for this network.", show_alert=True)
        return

    await state.update_data(network=network, wallet=wallet.address)
    await state.set_state(SellFlow.payment)
    await replace_message_with_text(
        callback.message,
        f"💎 Token: {data['asset']}\n"
        f"🔗 Network: {network}\n\n"
        "Pay on the address below 👇:\n"
        f"{wallet.address}\n\n"
        "⚠️ Note: Send exact amount or more.\n"
        "Any extra will be added to your wallet balance.\n\n"
        "After payment, click 'CHECK PAYMENT'\n"
        "below to send proof.",
        reply_markup=payment_proof(),
    )
    await callback.answer()

@router.callback_query(SellFlow.payment, F.data == "confirm_payment")
async def confirm_payment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellFlow.proof)
    await replace_message_with_text(
        callback.message,
        "Send payment screenshot/photo below.\n\n"
        "You can also send the transaction hash as text."
    )
    await callback.answer()

@router.message(SellFlow.proof, F.photo)
async def proof_photo(message: Message, state: FSMContext, session, config: Config, bot):
    data = await state.get_data()
    user = await get_user(session, message.from_user.id)
    order = Order(
        user_id=user.id,
        payment_method=data["payment_method"],
        asset=data["asset"],
        network=data["network"],
        crypto_amount=Decimal(data["amount"]),
        rate=Decimal(data["rate"]),
        inr_amount=Decimal(data["inr"]),
        wallet_address=data["wallet"],
        proof_file_id=message.photo[-1].file_id,
        status=OrderStatus.PENDING_REVIEW.value,
    )
    session.add(order)
    await session.flush()
    await session.commit()
    await state.update_data(order_id=order.id)
    await message.answer(
        "✅ Screenshot Submitted!\n\n"
        "Please wait for admin verification."
    )
    if config.review_group_id:
        from keyboards import operator_actions
        await bot.send_photo(
            config.review_group_id,
            message.photo[-1].file_id,
            caption=(
                f"NEW SELL ORDER\n\nOrder: #{order.id}\n"
                f"User ID: {message.from_user.id}\n"
                f"Token: {order.asset}\nNetwork: {order.network}\n"
                f"Amount: {display_amount(order.crypto_amount)}\n"
                f"Payment Method: {order.payment_method}\n"
                f"Expected INR: ₹{order.inr_amount:.2f}\n"
                "Status: Pending Review"
            ),
            reply_markup=operator_actions(order.id),
        )

@router.message(SellFlow.proof, F.document)
async def proof_document(message: Message, state: FSMContext, session, config: Config, bot):
    """Accept an image sent as a Telegram document to preserve original quality."""
    document = message.document
    if not document or not (document.mime_type or "").startswith("image/"):
        await message.answer("Please send an image screenshot or transaction hash.")
        return

    data = await state.get_data()
    user = await get_user(session, message.from_user.id)
    order = Order(
        user_id=user.id,
        payment_method=data["payment_method"],
        asset=data["asset"],
        network=data["network"],
        crypto_amount=Decimal(data["amount"]),
        rate=Decimal(data["rate"]),
        inr_amount=Decimal(data["inr"]),
        wallet_address=data["wallet"],
        proof_file_id=document.file_id,
        status=OrderStatus.PENDING_REVIEW.value,
    )
    session.add(order)
    await session.flush()
    await session.commit()
    await state.update_data(order_id=order.id)
    await message.answer(
        "✅ Screenshot Submitted!\n\n"
        "Please wait for admin verification."
    )
    if config.review_group_id:
        from keyboards import operator_actions
        await bot.send_document(
            config.review_group_id,
            document.file_id,
            caption=(
                f"NEW SELL ORDER\n\nOrder: #{order.id}\n"
                f"User ID: {message.from_user.id}\n"
                f"Token: {order.asset}\nNetwork: {order.network}\n"
                f"Amount: {display_amount(order.crypto_amount)}\n"
                f"Payment Method: {order.payment_method}\n"
                f"Expected INR: ₹{order.inr_amount:.2f}\n"
                "Proof: Original document\n"
                "Status: Pending Review"
            ),
            reply_markup=operator_actions(order.id),
        )

@router.message(SellFlow.proof)
async def proof_text(message: Message, state: FSMContext, session, config: Config, bot):
    data = await state.get_data()
    tx_hash = (message.text or "").strip()
    if not tx_hash:
        await message.answer("Please send a screenshot/photo or transaction hash.")
        return

    user = await get_user(session, message.from_user.id)
    order = Order(
        user_id=user.id,
        payment_method=data["payment_method"],
        asset=data["asset"],
        network=data["network"],
        crypto_amount=Decimal(data["amount"]),
        rate=Decimal(data["rate"]),
        inr_amount=Decimal(data["inr"]),
        wallet_address=data["wallet"],
        tx_hash=tx_hash,
        status=OrderStatus.PENDING_REVIEW.value,
    )
    session.add(order)
    await session.flush()
    await session.commit()
    await state.update_data(order_id=order.id)
    await message.answer(
        f"Payment proof received for order #{order.id} ✅\n\n"
        "Please wait for verification."
    )
    if config.review_group_id:
        from keyboards import operator_actions
        await bot.send_message(
            config.review_group_id,
            (
                f"NEW SELL ORDER\n\nOrder: #{order.id}\n"
                f"User ID: {message.from_user.id}\n"
                f"Token: {order.asset}\nNetwork: {order.network}\n"
                f"Amount: {display_amount(order.crypto_amount)}\n"
                f"Payment Method: {order.payment_method}\n"
                f"Expected INR: ₹{order.inr_amount:.2f}\n"
                f"TX Hash: {tx_hash}\n"
                "Status: Pending Review"
            ),
            reply_markup=operator_actions(order.id),
        )

@router.callback_query(lambda c: c.data == "payout:saved")
async def use_saved(callback: CallbackQuery, state: FSMContext, session, config: Config, bot):
    data = await state.get_data()
    user = await get_user(session, callback.from_user.id)
    saved = await session.scalar(select(SavedPayout).where(
        SavedPayout.user_id == user.id,
        SavedPayout.payment_method == data["payment_method"],
    ))
    if not saved:
        await callback.answer("No saved detail exists.", show_alert=True)
        return
    await finish_payout(callback, state, session, config, bot, saved.details)

@router.callback_query(lambda c: c.data == "payout:new")
async def new_payout(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    method = data.get("payment_method")
    if method == "CDM":
        await state.update_data(payout_step="bank")
        await replace_message_with_text(
            callback.message,
            "Select your bank for CDM 👇",
            cdm_banks(),
        )
    else:
        await state.set_state(SellFlow.payout)
        prompt = {
            "UPI": "Send your UPI ID below.\n\nExample: name@upi",
            "IMPS": "Send your IMPS payment details below.\n\nPlease include account number, bank name, IFSC and account holder name.",
        }.get(method, "Send your payment details below.")
        await replace_message_with_text(callback.message, prompt)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("cdm_bank:"))
async def choose_cdm_bank(callback: CallbackQuery, state: FSMContext):
    bank = callback.data.split(":", 1)[1]
    if bank not in {"AXIS", "SBI", "KOTAK", "HDFC"}:
        await callback.answer("Unsupported CDM bank.", show_alert=True)
        return
    await state.set_state(SellFlow.payout)
    await state.update_data(payout_step="account", payout_bank=bank)
    await replace_message_with_text(
        callback.message,
        f"Bank selected: {bank}\n\nSend your account number below:",
    )
    await callback.answer()

async def finish_payout(callback, state, session, config, bot, details):
    data = await state.get_data()
    user = await get_user(session, callback.from_user.id)
    order = await session.get(Order, int(data["order_id"]))
    if not order or order.status not in {OrderStatus.ASSIGNED.value, OrderStatus.AWAITING_PAYOUT_DETAILS.value}:
        # Allow PROCESSING only for a duplicate saved-detail click from the same flow.
        if not order or order.status == OrderStatus.COMPLETED.value:
            await callback.answer("Order is no longer active.", show_alert=True)
            return
    order.payout_details = details
    order.status = OrderStatus.PROCESSING.value
    saved = await session.scalar(select(SavedPayout).where(
        SavedPayout.user_id == user.id,
        SavedPayout.payment_method == order.payment_method,
    ))
    if saved:
        saved.details = details
    else:
        session.add(SavedPayout(user_id=user.id, payment_method=order.payment_method, details=details))
    await session.commit()
    await replace_message_with_text(
        callback.message,
        "Details have been received!\n\n"
        "You will receive your funds on the above details within 10 to 60 minutes ⚡\n\n"
        "TEXT MODE IS ON. You are now in direct contact with an admin for this trade."
    )
    await notify_work_group(bot, config, order, details)
    await state.clear()
    await callback.answer("Details submitted.")

async def notify_work_group(bot, config, order, details):
    if not config.review_group_id:
        return
    from keyboards import operator_paid
    await bot.send_message(
        config.review_group_id,
        f"💳 PAYOUT DETAILS RECEIVED\n\n"
        f"Order: #{order.id}\n"
        f"User ID: {order.user_id}\n"
        f"Payment Method: {order.payment_method}\n"
        f"Amount: ${display_amount(Decimal(order.crypto_amount))}\n"
        f"Payable: ₹{Decimal(order.inr_amount):.2f}\n\n"
        f"Payout Details:\n{details}\n\n"
        "Operator: pay the user and press Payment Sent.",
        reply_markup=operator_paid(order.id),
    )

@router.message(SellFlow.payout)
async def payout_details(message: Message, state: FSMContext, session, config: Config, bot):
    data = await state.get_data()
    user = await get_user(session, message.from_user.id)
    order = await session.get(Order, int(data["order_id"]))
    if not order:
        await message.answer("Order not found.")
        await state.clear()
        return

    details = (message.text or "").strip()
    if not details:
        await message.answer("Please send your payout details.")
        return

    method = order.payment_method
    if method == "CDM":
        step = data.get("payout_step")
        bank = data.get("payout_bank")
        if step == "account":
            if not details.isdigit() or not (8 <= len(details) <= 20):
                await message.answer("Enter a valid bank account number.")
                return
            await state.update_data(payout_step="holder", payout_account=details)
            await message.answer("Now send the bank account holder name:")
            return
        if step == "holder":
            holder = details
            if len(holder) < 2:
                await message.answer("Enter the bank account holder name.")
                return
            details = f"Bank: {bank}\nAccount Number: {data['payout_account']}\nAccount Holder Name: {holder}"
        else:
            await message.answer("Please select your CDM bank first.", reply_markup=cdm_banks())
            return

    elif method == "UPI":
        if len(details) < 3 or "@" not in details:
            await message.answer("Please send a valid UPI ID, for example name@upi.")
            return
        details = f"UPI ID: {details}"

    elif method == "IMPS":
        if len(details) < 10:
            await message.answer("Please send your IMPS account number, bank name, IFSC and account holder name.")
            return
        details = details

    await finish_payout_from_message(message, state, session, config, bot, details)

async def finish_payout_from_message(message, state, session, config, bot, details):
    data = await state.get_data()
    user = await get_user(session, message.from_user.id)
    order = await session.get(Order, int(data["order_id"]))
    if not order:
        await message.answer("Order not found.")
        await state.clear()
        return
    order.payout_details = details
    order.status = OrderStatus.PROCESSING.value
    saved = await session.scalar(select(SavedPayout).where(
        SavedPayout.user_id == user.id,
        SavedPayout.payment_method == order.payment_method,
    ))
    if saved:
        saved.details = details
    else:
        session.add(SavedPayout(user_id=user.id, payment_method=order.payment_method, details=details))
    await session.commit()
    await message.answer(
        "Details have been received!\n\n"
        "You will receive your funds on the above details within 10 to 60 minutes ⚡\n\n"
        "TEXT MODE IS ON. You are now in direct contact with an admin for this trade."
    )
    await notify_work_group(bot, config, order, details)
    await state.clear()

@router.callback_query(lambda c: c.data == "back")
async def back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await replace_message_with_text(
        callback.message,
        "⭐ Welcome to ExpressP2P Bot, where you can Sell & Buy Crypto Easily 💧\n\n"
        "What is your objective? \n\n"
        "Vouches :- @exp_vouches",
        reply_markup=main_menu(),
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await replace_message_with_text(
        callback.message,
        "⭐ Welcome to ExpressP2P Bot, where you can Sell & Buy Crypto Easily 💧\n\n"
        "What is your objective?\n\n"
        "Vouches :- @exp_vouches",
        reply_markup=main_menu(),
    )
    await callback.answer()
