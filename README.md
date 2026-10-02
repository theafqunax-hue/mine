# ExpressP2P Telegram Bot

Python + aiogram 3 + SQLAlchemy async + SQLite.

This version follows the supplied reference video for the visible sell flow and keeps the later requirement that payout details are collected only after an operator accepts the crypto payment.

## 1. Install on Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`:

```env
BOT_TOKEN=your_bot_token
OWNER_ADMIN_ID=123456789
REVIEW_GROUP_ID=-100...
VOUCH_CHANNEL_ID=@your_vouch_channel
SUPPORT_USERNAME=your_support
DATABASE_URL=sqlite+aiosqlite:///./p2p_bot.db
PLATFORM_NAME=ExpressP2P Bot
```

`OWNER_ADMIN_ID` is the single owner/admin Telegram ID. Only this ID can run the admin commands.

Run:

```powershell
python bot.py
```

## 2. Enable UPI / CDM / IMPS

Only these payment-method enable commands are exposed:

```text
/upi_enable
/cdm_enable
/imps_enable
```

They are owner-admin only.

The bot will show only the methods that are enabled.

## 3. Where to put the rates

**Do not use a `/set_rate` command.**

Edit this file:

```text
services/seed.py
```

Find `RATE_TIERS`. Each payment method has a completely separate rate table, so changing UPI does **not** change CDM or IMPS.

```python
RATE_TIERS = {
    "UPI": [
        (Decimal("10"), Decimal("600"), Decimal("95.0")),
        (Decimal("600.01"), Decimal("2000"), Decimal("96.0")),
        (Decimal("2000.01"), Decimal("5000"), Decimal("97.0")),
        (Decimal("5000.01"), None, Decimal("98.0")),
    ],

    "CDM": [
        (Decimal("10"), Decimal("600"), Decimal("95.0")),
        (Decimal("600.01"), Decimal("2000"), Decimal("96.0")),
        (Decimal("2000.01"), Decimal("5000"), Decimal("97.0")),
        (Decimal("5000.01"), None, Decimal("98.0")),
    ],

    "IMPS": [
        (Decimal("10"), Decimal("600"), Decimal("95.0")),
        (Decimal("600.01"), Decimal("2000"), Decimal("96.0")),
        (Decimal("2000.01"), Decimal("5000"), Decimal("97.0")),
        (Decimal("5000.01"), None, Decimal("98.0")),
    ],
}
```

For example, if you want different rates, change only that method:

```python
"UPI": [
    (Decimal("10"), Decimal("600"), Decimal("95.0")),
    (Decimal("600.01"), Decimal("2000"), Decimal("96.0")),
    (Decimal("2000.01"), Decimal("5000"), Decimal("97.0")),
    (Decimal("5000.01"), None, Decimal("98.0")),
],

"CDM": [
    (Decimal("10"), Decimal("600"), Decimal("93.0")),
    (Decimal("600.01"), Decimal("2000"), Decimal("94.0")),
    (Decimal("2000.01"), Decimal("5000"), Decimal("95.0")),
    (Decimal("5000.01"), None, Decimal("96.0")),
],

"IMPS": [
    (Decimal("10"), Decimal("600"), Decimal("94.0")),
    (Decimal("600.01"), Decimal("2000"), Decimal("95.0")),
    (Decimal("2000.01"), Decimal("5000"), Decimal("96.0")),
    (Decimal("5000.01"), None, Decimal("97.0")),
],
```

Those CDM/IMPS values are only an example of how to configure separate rates. Replace them with your actual rates.

The selected payment method's own rate table is displayed to the user before they enter the amount, and the calculation uses that same method-specific table.

The default UPI/CDM/IMPS values in this project are:

| USD amount | Default rate |
|---|---:|
| $10-$600 | ₹95.0 |
| $600.01-$2000 | ₹96.0 |
| $2000.01-$5000 | ₹97.0 |
| $5000.01+ | ₹98.0 |

Important: `README.md` is documentation. The actual values used by the bot are in `services/seed.py`.

## 4. Where to paste every public crypto address

Edit the same file:

```text
services/seed.py
```

The bot supports exactly these token/network followups:

```text
USDT - BEP20
USDT - SOL
USDT - ERC20
SOL  - SOL
SOL  - BEP20
USDC - BEP20
USDC - SOL
USDC - ERC20
```

Find:

```python
WALLET_ADDRESSES = {
    ("USDT", "BEP20"): "",
    ("USDT", "SOL"): "",
    ("USDT", "ERC20"): "",
    ("SOL", "SOL"): "",
    ("SOL", "BEP20"): "",
    ("USDC", "BEP20"): "",
    ("USDC", "SOL"): "",
    ("USDC", "ERC20"): "",
}
```

Paste your **public receiving address** between the quotes for each matching token/network. Example:

```python
WALLET_ADDRESSES = {
    ("USDT", "BEP20"): "0xYOUR_USDT_BEP20_ADDRESS",
    ("USDT", "SOL"): "YOUR_USDT_SOL_ADDRESS",
    ("USDT", "ERC20"): "0xYOUR_USDT_ERC20_ADDRESS",
    ("SOL", "SOL"): "YOUR_SOL_ADDRESS",
    ("SOL", "BEP20"): "0xYOUR_SOL_BEP20_ADDRESS",
    ("USDC", "BEP20"): "0xYOUR_USDC_BEP20_ADDRESS",
    ("USDC", "SOL"): "YOUR_USDC_SOL_ADDRESS",
    ("USDC", "ERC20"): "0xYOUR_USDC_ERC20_ADDRESS",
}
```

If an address is blank, that exact token/network pair stays unavailable and will not be shown to users.

**Never put a private key, seed phrase, or recovery phrase in this file.**

## 5. Reference-video sell flow

The visible flow is:

`SELL CRYPTO ⚡`

→ `Sell your crypto in multiple methods 👇`

→ UPI / IMPS / CDM buttons, showing `🟢 Available` when enabled

→ exchange-rate message

→ amount in `$`

→ `You will receive approx: ₹...`

→ USDT / SOL / USDC

→ compatible network buttons

→ token + network + public receiving address

→ `CHECK PAYMENT ✅`

→ screenshot or transaction hash

→ operator review

The bot keeps the payout-detail step after operator acceptance as requested separately.

## 6. Number formatting

User-facing crypto amounts are limited to **2 decimal places maximum**. INR calculations are shown with exactly **2 decimal places**, e.g. `₹8455.00`, matching the reference video style. Values such as `100.000000` are not shown.

## 7. Text editing

The visible bot messages are written directly in the handlers, not stored in `.env` and not hidden behind a message dictionary. The main sell-flow text is in:

```text
handlers/start.py
handlers/selling.py
handlers/operator.py
handlers/admin.py
keyboards.py
```

So you can open those files and edit the exact text/buttons directly.

## 8. Owner admin commands and operator permissions

`OWNER_ADMIN_ID` is the single owner. Admin commands are accepted **only in that owner's private DM**. They are not accepted in the review/working group.

Owner command menu:

```text
/admin
/add_operator <telegram_id> <method> <min> <max>
/remove_operator <telegram_id>
/operators
/upi_enable
/cdm_enable
/imps_enable
```

Example:

```text
/add_operator 123456789 UPI 10 600
/add_operator 123456789 CDM 100 2000
/add_operator 123456789 IMPS 500 5000
```

An operator can have a separate permission and limit for each payment method. Running `/add_operator` again for the same operator and method updates that method's limits.

`/remove_operator <telegram_id>` disables the operator and removes their method permissions. `/operators` shows every operator and their method limits.

The review/working group is for operator order actions such as **Accept**, **Reject**, and **View Details**. The bot checks the operator's method permission and amount range before allowing an order to be accepted.

Normal users do not get the owner admin commands in their Telegram command menu.

## 9. Important

This is development software for a P2P financial workflow. Before using real funds, add proper blockchain transaction verification, fraud controls, audit logging, secure deployment, access controls, and appropriate legal/compliance review.

## 10. Telegram command menu

The normal Telegram command menu contains:

```text
/start
/safe_sell
/support
```

The owner admin's Telegram command menu additionally contains:

```text
/admin
/add_operator <telegram_id> <method> <min> <max>
/remove_operator <telegram_id>
/operators
/upi_enable
/cdm_enable
/imps_enable
```

These admin commands are restricted in the handler to `OWNER_ADMIN_ID` **and private chat**.

## 11. Welcome image

Put the welcome image at the project root with this exact filename:

```text
welcome_image.png
```

The `/start` command automatically sends that image with the welcome caption. If the file is missing, the bot falls back to the text welcome message instead of crashing.

## 12. Balance / Add Funds

The old Balance button has been removed temporarily. The Add Funds/deposit UI should be implemented from the reference screenshot rather than guessed. This avoids inventing a deposit flow before the exact UI is provided.

## Screenshot / payment-proof quality

The bot accepts both:

- Telegram **Photo**: convenient, but Telegram may compress it.
- Telegram **Document/File** with an image: preferred when you need the original screenshot quality.

The bot forwards image documents to the review group as documents, preserving the uploaded file instead of converting it into a Telegram photo.

## Welcome image

Put your welcome image at the project root as:

```text
telegram_p2p_bot/welcome_image.png
```

`/start` sends that image with the welcome caption and main menu.

## CDM payout details

For a CDM payout, the user is asked for these three details:

1. Bank (button): **AXIS, SBI, KOTAK, or HDFC**
2. Account number
3. Account holder name

The selected bank is saved together with the account number and holder name. Only the last-used CDM detail is saved for that user.

## Payout details and work group

After an operator accepts an order, the user is asked for payout details. **Every payout method's submitted details are sent to the configured `REVIEW_GROUP_ID` work group.** The group message includes the order, payment method, payable INR amount, payout details, and a **Payment Sent** button.

The assigned operator (or the owner) presses **Payment Sent** in the work group after actually paying the user. The button is not sent only to a private operator DM. The bot checks the assigned operator before completing the order.


## Vouch posting

After the operator marks an order as paid, the bot sends the user a vouch text in a monospace block. The user can copy that exact text and paste it back into the bot in DM. The bot verifies that the text matches a completed order belonging to that user, then **copies the message into `VOUCH_CHANNEL_ID`** so the channel does not show a forwarded-message header.

Set `VOUCH_CHANNEL_ID` to either the private/public channel numeric ID (for example `-1001234567890`) or the channel username (for example `@your_vouch_channel`). The bot must be an administrator in the channel with permission to post messages.

The bot no longer posts the vouch automatically when Payment Sent is pressed. The channel post happens when the user pastes the generated vouch text back to the bot.
