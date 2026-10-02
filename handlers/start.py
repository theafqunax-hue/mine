from pathlib import Path
from decimal import Decimal

from aiogram import Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, FSInputFile
from sqlalchemy import select

from models import User, SavedPayout, Order, OrderStatus
from keyboards import main_menu
from config import Config

router = Router()
WELCOME_IMAGE = Path(__file__).resolve().parent.parent / "welcome_image.png"


async def ensure_user(session, tg_user):
    user = await session.scalar(select(User).where(User.telegram_id == tg_user.id))
    if not user:
        user = User(telegram_id=tg_user.id, username=tg_user.username)
        session.add(user)
        await session.flush()
    else:
        user.username = tg_user.username
    return user


WELCOME_TEXT = (
    "⭐ Welcome to ExpressP2P Bot, where you can Sell & Buy Crypto Easily 💧\n\n"
    "What is your objective?\n\n"
    "Vouches :- @exp_vouches"
)


async def send_welcome(message: Message, session):
    await ensure_user(session, message.from_user)
    await session.commit()
    if WELCOME_IMAGE.is_file():
        await message.answer_photo(
            FSInputFile(WELCOME_IMAGE),
            caption=WELCOME_TEXT,
            reply_markup=main_menu(),
        )
    else:
        await message.answer(WELCOME_TEXT, reply_markup=main_menu())


@router.message(CommandStart())
async def start(message: Message, session, config: Config):
    await send_welcome(message, session)


@router.message(Command("safe_sell"))
async def safe_sell(message: Message, state, session):
    # The actual sell-flow entry handler lives in selling.py. This command
    # is registered here as a small bridge so /safe_sell behaves like the
    # SELL CRYPTO button without duplicating the flow.
    from handlers.selling import begin_sell
    await begin_sell(message, state, session)


@router.message(Command("support"))
async def support_command(message: Message, config: Config):
    text = "Support ↗"
    if config.support_username:
        text += f"\n\nContact: @{config.support_username.lstrip('@')}"
    else:
        text += "\n\nSupport is not configured yet."
    await message.answer(text, reply_markup=main_menu())


@router.callback_query(lambda c: c.data == "saved")
async def saved(callback: CallbackQuery, session):
    user = await ensure_user(session, callback.from_user)
    rows = (await session.execute(
        select(SavedPayout).where(SavedPayout.user_id == user.id)
    )).scalars().all()
    if not rows:
        text = "Saved Payment Methods\n\nNo saved payment details yet."
    else:
        text = "Saved Payment Methods\n\n" + "\n".join(
            f"{r.payment_method}: {r.details[:80]}" for r in rows
        )
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()


@router.callback_query(lambda c: c.data == "support")
async def support(callback: CallbackQuery, config: Config):
    text = "Support ↗"
    if config.support_username:
        text += f"\n\nContact: @{config.support_username.lstrip('@')}"
    else:
        text += "\n\nSupport is not configured yet."
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()


def _normalize_vouch(text: str) -> str:
    return " ".join(text.strip().split())


@router.message(StateFilter(None), lambda m: m.chat.type == "private", lambda m: bool(m.text))
async def vouch_paste(message: Message, session, config: Config, bot):
    """Silently copy a valid completed-order vouch into the configured channel."""
    text = (message.text or "").strip()
    if not text.startswith("vouched @") or "safe exchange." not in text:
        return
    if not config.vouch_channel_id:
        return

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "PW_P2PBot"
    user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
    if not user:
        return

    completed = (await session.execute(
        select(Order).where(
            Order.status == OrderStatus.COMPLETED.value,
            Order.user_id == user.id,
        ).order_by(Order.id.desc())
    )).scalars().all()

    expected = {
        _normalize_vouch(
            f"vouched @{bot_username} for {Decimal(order.crypto_amount):.2f}$\nsafe exchange."
        )
        for order in completed
    }
    if _normalize_vouch(text) not in expected:
        return

    try:
        # Intentionally use Telegram's real forward operation here.
        # The channel should show the native "Forwarded from <user>" header
        # just like a manually forwarded Telegram message.
        await bot.forward_message(
            chat_id=config.vouch_channel_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Failed to copy vouch to VOUCH_CHANNEL_ID=%s", config.vouch_channel_id
        )
    # Deliberately no bot reply. The user's only visible action is the vouch
    # being copied into the channel.
