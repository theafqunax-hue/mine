import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from aiogram.fsm.storage.memory import MemoryStorage
from config import load_config
from database import make_db, init_db
from services.seed import seed_defaults
from handlers import start, selling, operator, admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

class SessionMiddleware:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def __call__(self, handler, event, data):
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)

async def main():
    config = load_config()
    engine, session_factory = make_db(config)
    await init_db(engine)
    async with session_factory() as session:
        await seed_defaults(session)

    bot = Bot(config.bot_token)

    # Validate configured destinations early so channel/group configuration
    # errors are visible in the console instead of only appearing after an
    # order is completed. Telegram requires the bot to be an administrator
    # with posting permission in a channel.
    me = await bot.get_me()
    for destination_name, destination_id in (
        ("REVIEW_GROUP_ID", config.review_group_id),
        ("VOUCH_CHANNEL_ID", config.vouch_channel_id),
    ):
        if not destination_id:
            continue
        try:
            chat = await bot.get_chat(destination_id)
            member = await bot.get_chat_member(destination_id, me.id)
            logging.info(
                "%s configured: id=%s title=%r type=%s bot_status=%s",
                destination_name,
                destination_id,
                chat.title,
                chat.type,
                member.status,
            )
            if chat.type == "channel" and member.status not in {"administrator", "creator"}:
                logging.error(
                    "%s: bot is not an administrator in this channel. Add the bot as admin with permission to post messages.",
                    destination_name,
                )
            elif chat.type == "channel" and getattr(member, "can_post_messages", True) is False:
                logging.error(
                    "%s: bot is an administrator but cannot post messages. Enable 'Post Messages' for the bot.",
                    destination_name,
                )
        except Exception:
            logging.exception(
                "Could not validate %s=%s. Check the chat ID and make sure the bot is a member/admin.",
                destination_name,
                destination_id,
            )

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open the main menu"),
            BotCommand(command="safe_sell", description="Start a safe crypto sell"),
            BotCommand(command="support", description="Contact support"),
        ],
        scope=BotCommandScopeDefault(),
    )
    # Owner-only admin commands are visible only in the owner's Telegram menu.
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open the main menu"),
            BotCommand(command="safe_sell", description="Start a safe crypto sell"),
            BotCommand(command="support", description="Contact support"),
            BotCommand(command="admin", description="Owner admin panel"),
            BotCommand(command="add_operator", description="Add/update operator permission"),
            BotCommand(command="remove_operator", description="Disable an operator"),
            BotCommand(command="operators", description="List operators and limits"),
            BotCommand(command="upi_enable", description="Enable UPI"),
            BotCommand(command="cdm_enable", description="Enable CDM"),
            BotCommand(command="imps_enable", description="Enable IMPS"),
        ],
        scope=BotCommandScopeChat(chat_id=config.owner_admin_id),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(SessionMiddleware(session_factory))
    dp.callback_query.middleware(SessionMiddleware(session_factory))

    dp.include_router(start.router)
    dp.include_router(selling.router)
    dp.include_router(operator.router)
    dp.include_router(admin.router)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot, config=config)
    finally:
        await bot.session.close()
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
