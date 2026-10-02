from decimal import Decimal
from sqlalchemy import select, update
from models import PaymentMethod, Asset, Network, AssetNetwork, RateTier, WalletAddress, Setting

# ============================================================
# EDIT THESE RATES HERE.
# Each payment method has its OWN independent tier table.
# You can change UPI/CDM/IMPS without affecting the others.
# Amounts are in USD; rate is INR per USD.
# ============================================================
RATE_TIERS = {
    "UPI": [
        (Decimal("10"), Decimal("600"), Decimal("95.0")),
        (Decimal("601"), Decimal("2000"), Decimal("96.0")),
        (Decimal("2001"), Decimal("5000"), Decimal("97.0")),
        (Decimal("5001"), None, Decimal("98.0")),
    ],
    "CDM": [
        (Decimal("150"), Decimal("600"), Decimal("98.0")),
        (Decimal("601"), Decimal("2500"), Decimal("98.5")),
        (Decimal("2501"), None, Decimal("90.0")),
    ],
    "IMPS": [
        (Decimal("150"), Decimal("600"), Decimal("98.0")),
        (Decimal("601"), Decimal("2500"), Decimal("98.5")),
        (Decimal("2501"), None, Decimal("90.0")),
    ],
}

# ============================================================
# PASTE YOUR PUBLIC RECEIVING ADDRESSES HERE.
# These are the ONLY token/network combinations shown to users.
# Leave an address blank if you do not want that pair available.
# Never put private keys or seed phrases here.
# ============================================================
WALLET_ADDRESSES = {
    ("USDT", "BEP20"): "0x57C12a9F327B7f4a4Be52f9157f8667085494436",
    ("USDT", "SOL"): "EtkMDUS9JnY5G2PzMz1XzXr3Nt6tjZeSC1s5TwxcJBPN",
    ("USDT", "ERC20"): "0x57C12a9F327B7f4a4Be52f9157f8667085494436",
    ("SOL", "SOL"): "EtkMDUS9JnY5G2PzMz1XzXr3Nt6tjZeSC1s5TwxcJBPN",
    ("SOL", "BEP20"): "0x57C12a9F327B7f4a4Be52f9157f8667085494436",
    ("USDC", "BEP20"): "0x57C12a9F327B7f4a4Be52f9157f8667085494436",
    ("USDC", "SOL"): "EtkMDUS9JnY5G2PzMz1XzXr3Nt6tjZeSC1s5TwxcJBPN",
    ("USDC", "ERC20"): "0x57C12a9F327B7f4a4Be52f9157f8667085494436",
}

# Exact coin/network followups requested by the owner.
SUPPORTED_PAIRS = tuple(WALLET_ADDRESSES.keys())
SUPPORTED_ASSETS = tuple(dict.fromkeys(asset for asset, _ in SUPPORTED_PAIRS))
SUPPORTED_NETWORKS = tuple(dict.fromkeys(network for _, network in SUPPORTED_PAIRS))

async def seed_defaults(session):
    # Payment methods are controlled only through the owner commands:
    # /upi_enable, /cdm_enable, /imps_enable
    for code in ("UPI", "CDM", "IMPS"):
        obj = await session.scalar(select(PaymentMethod).where(PaymentMethod.code == code))
        if not obj:
            session.add(PaymentMethod(code=code, enabled=False))

    # Keep only the requested coin choices active.
    all_assets = (await session.execute(select(Asset))).scalars().all()
    for asset in all_assets:
        asset.enabled = asset.code in SUPPORTED_ASSETS
    for code in SUPPORTED_ASSETS:
        if not await session.scalar(select(Asset).where(Asset.code == code)):
            session.add(Asset(code=code, enabled=True))

    # Keep the requested networks active. Old networks can remain in DB but
    # are disabled, so they cannot appear in the user flow.
    all_networks = (await session.execute(select(Network))).scalars().all()
    for network in all_networks:
        network.enabled = network.code in SUPPORTED_NETWORKS
    for code in SUPPORTED_NETWORKS:
        if not await session.scalar(select(Network).where(Network.code == code)):
            session.add(Network(code=code, enabled=True))

    await session.flush()

    # Keep the database rates exactly in sync with the per-method tables above.
    existing_rates = (await session.execute(select(RateTier))).scalars().all()
    for row in existing_rates:
        await session.delete(row)
    session.add_all([
        RateTier(payment_method=method, min_amount=lo, max_amount=hi, rate=rate)
        for method, tiers in RATE_TIERS.items()
        for lo, hi, rate in tiers
    ])

    # Disable every existing asset/network pair first. Then enable only the
    # eight requested combinations that have a public wallet address.
    all_pairs = (await session.execute(select(AssetNetwork))).scalars().all()
    for pair in all_pairs:
        pair.enabled = False

    # Disable old wallet records first so stale addresses cannot be selected.
    all_wallets = (await session.execute(select(WalletAddress))).scalars().all()
    for wallet in all_wallets:
        wallet.enabled = False

    for (asset_code, network_code), address in WALLET_ADDRESSES.items():
        asset = await session.scalar(select(Asset).where(Asset.code == asset_code))
        network = await session.scalar(select(Network).where(Network.code == network_code))
        if not asset or not network:
            continue

        pair = await session.scalar(select(AssetNetwork).where(
            AssetNetwork.asset_id == asset.id,
            AssetNetwork.network_id == network.id,
        ))
        if pair:
            pair.enabled = bool(address.strip())
        else:
            session.add(AssetNetwork(
                asset_id=asset.id,
                network_id=network.id,
                enabled=bool(address.strip()),
            ))

        if address.strip():
            wallet = await session.scalar(select(WalletAddress).where(
                WalletAddress.asset_id == asset.id,
                WalletAddress.network_id == network.id,
            ))
            if wallet:
                wallet.address = address.strip()
                wallet.enabled = True
            else:
                session.add(WalletAddress(
                    asset_id=asset.id,
                    network_id=network.id,
                    address=address.strip(),
                    enabled=True,
                ))

    if not await session.scalar(select(Setting).where(Setting.key == "MIN_AMOUNT")):
        session.add(Setting(key="MIN_AMOUNT", value="10"))
    if not await session.scalar(select(Setting).where(Setting.key == "MAX_AMOUNT")):
        session.add(Setting(key="MAX_AMOUNT", value="1000000"))

    await session.commit()
