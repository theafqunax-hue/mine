from pathlib import Path
from decimal import Decimal

from aiogram import Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters.command import CommandObject
from sqlalchemy import select, func

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


async def apply_referral(session, user: User, referrer_tg_id: int | None):
    """Attach the first valid referrer only. Self-referrals are ignored."""
    if not referrer_tg_id or user.referrer_id is not None:
        return False
    if referrer_tg_id == user.telegram_id:
        return False

    referrer = await session.scalar(
        select(User).where(User.telegram_id == referrer_tg_id)
    )
    if not referrer or referrer.id == user.id:
        return False

    user.referrer_id = referrer.id
    return True


WELCOME_TEXT = (
    "⭐ Welcome to ExpressP2P Bot, where you can Sell & Buy Crypto Easily 💧\n\n"
    "What is your objective?\n\n"
    "Vouches :- @exp_vouches"
)


async def send_welcome(message: Message, session, config: Config):
    await ensure_user(session, message.from_user)
    await session.commit()
    if WELCOME_IMAGE.is_file():
        await message.answer_photo(
            FSInputFile(WELCOME_IMAGE),
            caption=WELCOME_TEXT,
            reply_markup=main_menu(config.support_username),
        )
    else:
        await message.answer(
            WELCOME_TEXT,
            reply_markup=main_menu(config.support_username),
        )


@router.message(CommandStart())
async def start(
    message: Message,
    command: CommandObject,
    session,
    config: Config,
):
    user = await ensure_user(session, message.from_user)

    # Referral links look like: https://t.me/YourBot?start=ref_123456789
    referrer_tg_id = None
    if command.args and command.args.startswith("ref_"):
        raw_id = command.args[4:].strip()
        try:
            referrer_tg_id = int(raw_id)
        except ValueError:
            referrer_tg_id = None

    if await apply_referral(session, user, referrer_tg_id):
        await session.commit()
    else:
        await session.commit()

    await send_welcome(message, session, config)


@router.message(Command("safe_sell"))
async def safe_sell(message: Message, state, session):
    # The actual sell-flow entry handler lives in selling.py. This command
    # is registered here as a small bridge so /safe_sell behaves like the
    # SELL CRYPTO button without duplicating the flow.
    from handlers.selling import begin_sell
    await begin_sell(message, state, session)


@router.message(Command("support"))
async def support_command(message: Message, config: Config):
    if config.support_username:
        username = config.support_username.lstrip("@")
        await message.answer(
            "Support ↗",
            reply_markup=main_menu(config.support_username),
        )
        # The actual Support button is the direct t.me URL in the menu.
        return
    await message.answer(
        "Support is not configured yet.",
        reply_markup=main_menu(config.support_username),
    )


@router.callback_query(lambda c: c.data == "saved")
async def saved(callback: CallbackQuery, session, config: Config):
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
    # This callback normally comes from a text message or a welcome photo.
    # Avoid Telegram's 'there is no text in the message to edit' on photos.
    if callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=main_menu(config.support_username))
    else:
        await callback.message.edit_text(text, reply_markup=main_menu(config.support_username))
    await callback.answer()


@router.callback_query(lambda c: c.data == "support")
async def support(callback: CallbackQuery, config: Config):
    # Kept as a fallback only when SUPPORT_USERNAME is not configured.
    text = "Support ↗"
    if config.support_username:
        text += f"\n\nContact: @{config.support_username.lstrip('@')}"
    else:
        text += "\n\nSupport is not configured yet."
    if callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=main_menu(config.support_username))
    else:
        await callback.message.edit_text(text, reply_markup=main_menu(config.support_username))
    await callback.answer()


@router.callback_query(lambda c: c.data == "referral")
async def referral(callback: CallbackQuery, session, config: Config, bot):
    user = await ensure_user(session, callback.from_user)
    await session.commit()

    # Avoid importing bot-specific username/config values into the database.
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    if not bot_username:
        await callback.answer("Referral link is unavailable right now.", show_alert=True)
        return

    referral_link = f"https://t.me/{bot_username}?start=ref_{user.telegram_id}"
    referral_count = await session.scalar(
        select(func.count(User.id)).where(User.referrer_id == user.id)
    )

    text = (
        "👥 Referral Program\n\n"
        "Invite your friends using your personal referral link.\n\n"
        f"🔗 Your referral link:\n{referral_link}\n\n"
        f"👥 Total referrals: {referral_count or 0}"
    )

    if callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            text,
            reply_markup=main_menu(config.support_username),
        )
    else:
        await callback.message.edit_text(
            text,
            reply_markup=main_menu(config.support_username),
        )
    await callback.answer()


def _normalize_vouch(text: str) -> str:
    return " ".join(text.strip().split())


@router.message(StateFilter(None), lambda m: m.chat.type == "private", lambda m: bool(m.text))
async def vouch_paste(message: Message, session, config: Config, bot):
    """Silently forward a valid completed-order vouch into the configured channel."""
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
        await bot.forward_message(
            chat_id=config.vouch_channel_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Failed to forward vouch to VOUCH_CHANNEL_ID=%s",
            config.vouch_channel_id,
        )
    # Deliberately no bot reply. The user's only visible action is the vouch
    # being forwarded into the channel.
