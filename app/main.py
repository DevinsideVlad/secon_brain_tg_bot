import asyncio
import logging
import sys

from aiogram.types import BotCommandScopeDefault

from .bot import BOT_COMMANDS, create_bot, dp
from .config import settings
from .handlers import router
from .wiki import WikiStructureError, check_structure

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def main() -> None:
    setup_logging()
    if not settings.wiki_root:
        logger.error("WIKI_ROOT не задан. Заполните .env (см. .env.example).")
        sys.exit(1)
    try:
        check_structure(settings.wiki_root)
    except WikiStructureError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    bot = create_bot()
    dp.include_router(router)
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
    logger.info("karpaty-bot стартует (long polling)")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())