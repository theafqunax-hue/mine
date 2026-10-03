from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import Config

class Base(DeclarativeBase):
    pass

def make_db(config: Config):
    engine = create_async_engine(config.database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory

async def init_db(engine):
    from models import Base as ModelsBase
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)

        if engine.dialect.name == "sqlite":
            order_columns = await conn.run_sync(
                lambda c: [x[1] for x in c.exec_driver_sql(
                    "PRAGMA table_info(orders)"
                ).fetchall()]
            )
            if "payout_proof_file_id" not in order_columns:
                await conn.execute(
                    text("ALTER TABLE orders ADD COLUMN payout_proof_file_id TEXT")
                )

            rate_columns = await conn.run_sync(
                lambda c: [x[1] for x in c.exec_driver_sql(
                    "PRAGMA table_info(rate_tiers)"
                ).fetchall()]
            )
            if "payment_method" not in rate_columns:
                await conn.execute(
                    text("ALTER TABLE rate_tiers ADD COLUMN payment_method VARCHAR(32)")
                )
                await conn.execute(
                    text("UPDATE rate_tiers SET payment_method='UPI' "
                         "WHERE payment_method IS NULL")
                )

            user_columns = await conn.run_sync(
                lambda c: [x[1] for x in c.exec_driver_sql(
                    "PRAGMA table_info(users)"
                ).fetchall()]
            )
            if "referrer_id" not in user_columns:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
                )

        elif engine.dialect.name == "postgresql":
            await conn.execute(
                text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payout_proof_file_id TEXT")
            )
            await conn.execute(
                text("ALTER TABLE rate_tiers ADD COLUMN IF NOT EXISTS payment_method VARCHAR(32)")
            )
            await conn.execute(
                text("UPDATE rate_tiers SET payment_method='UPI' "
                     "WHERE payment_method IS NULL")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_id INTEGER")
            )
