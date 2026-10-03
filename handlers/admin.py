from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import delete, select

from models import Operator, OperatorPermission, PaymentMethod
from config import Config

router = Router()
VALID_METHODS = {"UPI", "CDM", "IMPS"}


def is_owner_dm(message: Message, config: Config) -> bool:
    """Owner admin commands are allowed only from the configured owner's DM."""
    return (
        message.from_user is not None
        and message.chat is not None
        and message.from_user.id == config.owner_admin_id
        and message.chat.type == "private"
    )


def parse_amount(value: str) -> Decimal:
    amount = Decimal(value)
    if amount <= 0 or amount.as_tuple().exponent < -2:
        raise ValueError
    return amount


async def owner_guard(message: Message, config: Config) -> bool:
    """Return True when this is the owner DM. Give useful diagnostics otherwise."""
    if message.from_user is None:
        return False
    if message.from_user.id != config.owner_admin_id:
        return False
    if message.chat.type != "private":
        await message.answer("Owner admin commands work only in your private DM with the bot.")
        return False
    return True


@router.message(Command("admin"))
async def admin_help(message: Message, config: Config):
    if not await owner_guard(message, config):
        return
    await message.answer(
        "👑 Owner Admin Panel\n\n"
        "Payment methods:\n"
        "/upi_enable\n"
        "/cdm_enable\n"
        "/imps_enable\n\n"
        "Operators:\n"
        "/add_operator <telegram_id> <method> <min> <max>\n"
        "/remove_operator <telegram_id>\n"
        "/operators\n\n"
        "Example:\n"
        "/add_operator 123456789 UPI 10 600\n\n"
        "Rates: edit services/seed.py\n"
        "Wallets: paste public addresses in services/seed.py"
    )


async def enable_method(message: Message, session, config: Config, code: str):
    if not await owner_guard(message, config):
        return
    method = await session.scalar(
        select(PaymentMethod).where(PaymentMethod.code == code)
    )
    if not method:
        method = PaymentMethod(code=code, enabled=True)
        session.add(method)
    else:
        method.enabled = True
    await session.commit()
    await message.answer(f"{code} 🟢 Available")


@router.message(Command("upi_enable"))
async def upi_enable(message: Message, session, config: Config):
    await enable_method(message, session, config, "UPI")


@router.message(Command("cdm_enable"))
async def cdm_enable(message: Message, session, config: Config):
    await enable_method(message, session, config, "CDM")


@router.message(Command("imps_enable"))
async def imps_enable(message: Message, session, config: Config):
    await enable_method(message, session, config, "IMPS")


@router.message(Command("add_operator"))
async def add_operator(message: Message, session, config: Config):
    if not await owner_guard(message, config):
        return

    parts = (message.text or "").split()
    if len(parts) != 5:
        await message.answer(
            "Usage:\n"
            "/add_operator <telegram_id> <method> <min> <max>\n\n"
            "Example:\n"
            "/add_operator 123456789 UPI 10 600"
        )
        return

    try:
        telegram_id = int(parts[1])
        method = parts[2].upper()
        min_amount = parse_amount(parts[3])
        max_amount = parse_amount(parts[4])
    except (ValueError, InvalidOperation):
        await message.answer(
            "Invalid values. Use:\n"
            "/add_operator <telegram_id> <method> <min> <max>\n\n"
            "Example:\n"
            "/add_operator 123456789 UPI 10 600"
        )
        return

    if method not in VALID_METHODS:
        await message.answer("Method must be UPI, CDM, or IMPS.")
        return
    if min_amount > max_amount:
        await message.answer("Minimum amount cannot be greater than maximum amount.")
        return
    if telegram_id == config.owner_admin_id:
        await message.answer(
            "That ID is the owner. The owner is automatically allowed to handle every method and amount."
        )
        return

    operator = await session.scalar(
        select(Operator).where(Operator.telegram_id == telegram_id)
    )
    if not operator:
        operator = Operator(telegram_id=telegram_id, enabled=True)
        session.add(operator)
        await session.flush()
    else:
        operator.enabled = True

    permission = await session.scalar(
        select(OperatorPermission).where(
            OperatorPermission.operator_id == operator.id,
            OperatorPermission.payment_method == method,
        )
    )
    if permission:
        permission.min_amount = min_amount
        permission.max_amount = max_amount
    else:
        session.add(
            OperatorPermission(
                operator_id=operator.id,
                payment_method=method,
                min_amount=min_amount,
                max_amount=max_amount,
            )
        )

    await session.commit()
    await message.answer(
        "Operator saved ✅\n\n"
        f"Telegram ID: {telegram_id}\n"
        f"Method: {method}\n"
        f"Limit: ${min_amount:g} - ${max_amount:g}"
    )


@router.message(Command("remove_operator"))
async def remove_operator(message: Message, session, config: Config):
    if not await owner_guard(message, config):
        return

    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Usage:\n/remove_operator <telegram_id>")
        return

    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.answer("Telegram ID must be a number.")
        return

    if telegram_id == config.owner_admin_id:
        await message.answer("The owner cannot be removed.")
        return

    operator = await session.scalar(
        select(Operator).where(Operator.telegram_id == telegram_id)
    )
    if not operator:
        await message.answer("Operator not found.")
        return

    operator.enabled = False
    await session.execute(
        delete(OperatorPermission).where(
            OperatorPermission.operator_id == operator.id
        )
    )
    await session.commit()
    await message.answer(
        f"Operator {telegram_id} disabled and permissions removed ✅"
    )


@router.message(Command("operators"))
async def list_operators(message: Message, session, config: Config):
    if not await owner_guard(message, config):
        return

    operators = (
        await session.execute(
            select(Operator).order_by(Operator.telegram_id)
        )
    ).scalars().all()

    lines = [
        "👤 Operators\n",
        f"👑 Owner: {config.owner_admin_id} — Super operator\n",
    ]

    visible = [op for op in operators if op.telegram_id != config.owner_admin_id]
    if not visible:
        lines.append("\nNo additional operators configured.")
    else:
        for operator in visible:
            status = "🟢 Enabled" if operator.enabled else "🔴 Disabled"
            lines.append(f"\n{operator.telegram_id} — {status}")
            permissions = (
                await session.execute(
                    select(OperatorPermission).where(
                        OperatorPermission.operator_id == operator.id
                    ).order_by(OperatorPermission.payment_method)
                )
            ).scalars().all()
            if permissions:
                for permission in permissions:
                    lines.append(
                        f"  • {permission.payment_method}: "
                        f"${permission.min_amount:g} - ${permission.max_amount:g}"
                    )
            else:
                lines.append("  • No permissions")

    await message.answer("\n".join(lines))
