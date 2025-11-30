"""Entry point for the Sekto Telegram bot."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramConflictError

from bot.config import BOT_TOKEN
from bot.handlers import register_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Create the bot, wire handlers, and start polling."""
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp)
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except TelegramConflictError as e:
        logger.warning(
            f"Telegram conflict detected: {e}. "
            "This usually happens when multiple bot instances are running. "
            "The bot will retry automatically."
        )
        # Aiogram will automatically retry, but we can add a delay here if needed
        await asyncio.sleep(5)
        # Retry once more
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        except Exception as retry_error:
            logger.error(f"Failed to start polling after conflict: {retry_error}")
            raise
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
