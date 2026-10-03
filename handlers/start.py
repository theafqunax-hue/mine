from pathlib import Path
from decimal import Decimal
import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.deep_linking import create_start_link
from sqlalchemy import select, func

from models import User, SavedPayout, Order, OrderStatus
from keyboards import main_menu
from config import Config

router = Router()
logger = logging.getLogger(__name__)
WELCOME_IMAGE = Path(__file__).resolve().parent.parent / "welcome_image.png"

WELCOME_TEXT = (
    "⭐ Welcome to ExpressP2P Bot, where you can Sell & Buy Crypto Easily 💧\n\n"
    "What is your objective?\n\n"
    "Vouches :- @exp_vouches"
)

async def ensure_user(session, tg_user):
    user = await session.scalar(select(User).where(User.telegram_id == tg_user.id))
    if not user:
        user = User(telegram_id=tg_user.id, username=tg_user.username)
        session.add(user)
        await session.flush()
    else:
        user.username = tg_user.username
    return user

async def safe_edit_or_replace(message: Message, text: str, reply_markup=None):
    """Edit text/caption when possible; replace a photo message with text otherwise."""
    try:
        if message.text is not None:
            return await message.edit_text(text, reply_markup=reply_markup)
        if message.caption is not None:
            return await message.edit_caption(caption=text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return None
        if "there is no text in the message" not in str(exc).lower():
            raise

    try:
        await message.delete()
    except Exception:
        pass
    return await message.answer(text, reply_markup=reply_markup)

async def send_welcome(message: Message, session, config: Config):
    await ensure_user(session, message.from_user)
    await session.commit()
    markup = main_menu(config.support_username)
    if WELCOME_IMAGE.is_file():
        await message.answer_photo(
            FSInputFile(WELCOME_IMAGE),
            caption=WELCOME_TEXT,
            reply_markup=markup,
        )
    else:
        await message.answer(WELCOME_TEXT, reply_markup=markup)

async def record_referral(session, user: User, referrer_tg_id: int | None):
    if not referrer_tg_id or user.referrer_id is not None:
        return
    if referrer_tg_id == user.telegram_id:
        return
    referrer = await session.scalar(
        select(User).where(User.telegram_id == referrer_tg_id)
    )
    if referrer:
        user.referrer_id = referrer.id

@router.message(CommandStart())
async def start(message: Message, command, session, config: Config):
    # CommandObject is injected by aiogram's CommandStart filter.
    referrer_tg_id = None
    args = getattr(command, "args", None)
    if args and args.startswith("ref_"):
        try:
            referrer_tg_id = int(args[4:])
        except ValueError:
            referrer_tg_id = None

    user = await ensure_user(session, message.from_user)
    await record_referral(session, user, referrer_tg_id)
    await session.commit()
    await send_welcome(message, session, config)

@router.message(Command("safe_sell"))
async def safe_sell(message: Message, state, session):
    from handlers.selling import begin_sell
    await begin_sell(message, state, session)

@router.message(Command("support"))
async def support_command(message: Message, config: Config):
    username = config.support_username.lstrip("@").strip()
    if username:
        await message.answer(
            f"Support: @{username}\n\nTap the button below to contact support.",
            reply_markup=main_menu(config.support_username),
        )
    else:
        await message.answer(
            "Support is not configured yet.",
            reply_markup=main_menu(config.support_username),
        )

@router.callback_query(lambda c: c.data == "saved")
async def saved(callback: CallbackQuery, session, config: Config):
    user = await ensure_user(session, callback.from_user)
    rows = (
        await session.execute(
            select(SavedPayout).where(SavedPayout.user_id == user.id)
        )
    ).scalars().all()
    if not rows:
        text = "Saved Payment Methods\n\nNo saved payment details yet."
    else:
        text = "Saved Payment Methods\n\n" + "\n".join(
            f"{r.payment_method}: {r.details[:80]}" for r in rows
        )
    await safe_edit_or_replace(callback.message, text, main_menu(config.support_username))
    await callback.answer()

@router.callback_query(lambda c: c.data == "support")
async def support(callback: CallbackQuery, config: Config):
    username = config.support_username.lstrip("@").strip()
    text = (
        f"Support: @{username}\n\nTap Support ↗ below to contact support."
        if username
        else "Support is not configured yet."
    )
    await safe_edit_or_replace(callback.message, text, main_menu(config.support_username))
    await callback.answer()

@router.callback_query(lambda c: c.data == "referral")
async def referral(callback: CallbackQuery, session, bot, config: Config):
    user = await ensure_user(session, callback.from_user)
    await session.commit()
    link = await create_start_link(bot, f"ref_{user.telegram_id}")
    count = await session.scalar(
        select(func.count(User.id)).where(User.referrer_id == user.id)
    )
    text = (
        "👥 Referral Program\n\n"
        "Invite your friends using your personal referral link.\n\n"
        f"🔗 Your referral link:\n{link}\n\n"
        f"👥 Total referrals: {count or 0}"
    )
    await safe_edit_or_replace(
        callback.message,
        text,
        main_menu(config.support_username),
    )
    await callback.answer()

def _normalize_vouch(text: str) -> str:
    return " ".join(text.strip().split())

# IMPORTANT: exclude slash commands here. Previously this catch-all handler
# consumed /admin, /upi_enable, /add_operator, etc. before admin.py saw them.
@router.message(
    StateFilter(None),
    lambda m: m.chat.type == "private" and bool(m.text) and not m.text.startswith("/")
)
async def vouch_paste(message: Message, session, config: Config, bot):
    """Silently forward a valid completed-order vouch to the configured channel."""
    text = (message.text or "").strip()
    if not text.startswith("vouched @") or "safe exchange." not in text:
        return
    if not config.vouch_channel_id:
        return

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "PW_P2PBot"
    user = await session.scalar(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    if not user:
        return

    completed = (
        await session.execute(
            select(Order).where(
                Order.status == OrderStatus.COMPLETED.value,
                Order.user_id == user.id,
            ).order_by(Order.id.desc())
        )
    ).scalars().all()

    expected = {
        _normalize_vouch(
            f"vouched @{bot_username} for {Decimal(order.crypto_amount):.2f}$\nsafe exchange."
        )
        for order in completed
    }
    if _normalize_vouch(text) not in expected:
        return

    try:
        await bot.forward_message(
            chat_id=config.vouch_channel_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception:
        logger.exception(
            "Failed to forward vouch to VOUCH_CHANNEL_ID=%s",
            config.vouch_channel_id,
        )
    # Intentionally no response to the user.
