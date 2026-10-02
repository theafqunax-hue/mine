import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    bot_token: str
    owner_admin_id: int
    review_group_id: int | None
    vouch_channel_id: str | None
    support_username: str
    database_url: str
    platform_name: str

def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing from .env")
    owner = os.getenv("OWNER_ADMIN_ID", "").strip()
    if not owner:
        raise RuntimeError("OWNER_ADMIN_ID is missing from .env")
    review = os.getenv("REVIEW_GROUP_ID", "").strip()
    vouch = os.getenv("VOUCH_CHANNEL_ID", "").strip()
    return Config(
        bot_token=token,
        owner_admin_id=int(owner),
        review_group_id=int(review) if review else None,
        vouch_channel_id=vouch or None,
        support_username=os.getenv("SUPPORT_USERNAME", ""),
        database_url=os.getenv(
            "DATABASE_URL", "sqlite+aiosqlite:///./p2p_bot.db"
        ),
        platform_name=os.getenv("PLATFORM_NAME", "ExpressP2P Bot"),
    )
