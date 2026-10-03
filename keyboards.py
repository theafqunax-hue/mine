from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="SELL CRYPTO ⚡", callback_data="sell")],
        [InlineKeyboardButton(text="Saved Payment Methods", callback_data="saved")],
        [InlineKeyboardButton(text="Support ↗", url="https://t.me/cryptoXgoon"")],
        [InlineKeyboardButton(text="↩️ BACK", callback_data="back")],
    ])


def methods(enabled_codes=None):
    enabled_codes = set(enabled_codes or [])
    rows = []
    labels = {
        "UPI": "UPI💳 🟢 Available",
        "IMPS": "IMPS⚪ 🟢 Available",
        "CDM": "CDM🏧 🟢 Available",
    }
    for code in ("UPI", "IMPS", "CDM"):
        if code in enabled_codes:
            rows.append([InlineKeyboardButton(text=labels[code], callback_data=f"method:{code}")])
    rows.append([InlineKeyboardButton(text="↩️ BACK", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Continue", callback_data="continue")],
        [InlineKeyboardButton(text="↩️ BACK", callback_data="back")],
    ])


def assets():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="USDT", callback_data="asset:USDT"),
         InlineKeyboardButton(text="SOL", callback_data="asset:SOL")],
        [InlineKeyboardButton(text="USDC", callback_data="asset:USDC")],
        [InlineKeyboardButton(text="↩️ BACK", callback_data="back")],
    ])


def networks(codes):
    rows = [[InlineKeyboardButton(text=code, callback_data=f"network:{code}")] for code in codes]
    rows.append([InlineKeyboardButton(text="↩️ BACK", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_proof():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="CHECK PAYMENT ✅", callback_data="confirm_payment")],
        [InlineKeyboardButton(text="↩️ BACK", callback_data="back")],
    ])


def payout_choices(method, has_saved):
    rows = []
    if has_saved:
        rows.append([InlineKeyboardButton(text=f"Use Saved {method}", callback_data="payout:saved")])
    rows.append([InlineKeyboardButton(text=f"＋ Add New {method}", callback_data="payout:new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def cdm_banks():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="AXIS", callback_data="cdm_bank:AXIS"),
         InlineKeyboardButton(text="SBI", callback_data="cdm_bank:SBI")],
        [InlineKeyboardButton(text="KOTAK", callback_data="cdm_bank:KOTAK"),
         InlineKeyboardButton(text="HDFC", callback_data="cdm_bank:HDFC")],
    ])


def operator_actions(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Accept Order", callback_data=f"op:accept:{order_id}")],
        [InlineKeyboardButton(text="Reject Order", callback_data=f"op:reject:{order_id}"),
         InlineKeyboardButton(text="View Details", callback_data=f"op:view:{order_id}")],
    ])


def operator_paid(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Payment Sent", callback_data=f"op:paid:{order_id}")]
    ])
