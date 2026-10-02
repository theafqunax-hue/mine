from decimal import Decimal
from sqlalchemy import select
from models import RateTier

async def get_rate(session, payment_method: str, amount: Decimal):
    result = await session.execute(
        select(RateTier)
        .where(
            RateTier.enabled == True,
            RateTier.payment_method == payment_method,
        )
        .order_by(RateTier.min_amount)
    )
    for tier in result.scalars():
        if amount >= tier.min_amount and (tier.max_amount is None or amount <= tier.max_amount):
            return Decimal(tier.rate)
    return None

async def get_rate_tiers(session, payment_method: str):
    result = await session.execute(
        select(RateTier)
        .where(
            RateTier.enabled == True,
            RateTier.payment_method == payment_method,
        )
        .order_by(RateTier.min_amount)
    )
    return list(result.scalars())
