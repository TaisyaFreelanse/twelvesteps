"""Entry point for the Sekto Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import sys

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

# Suppress TelegramConflictError from aiogram dispatcher logs
# These are expected when multiple instances run during deployment
# Only one instance will successfully handle updates, others will get conflicts
class ConflictErrorFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # Filter out conflict errors - they're expected during deployment
        if "TelegramConflictError" in msg and "Conflict: terminated by other getUpdates" in msg:
            return False
        return True

# Apply filter to aiogram.dispatcher logger to reduce noise
logging.getLogger("aiogram.dispatcher").addFilter(ConflictErrorFilter())


async def main() -> None:
    """Create the bot, wire handlers, and start polling."""
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp)
    
    logger.info("Starting bot with polling...")
    
    try:
        await dp.start_polling(
            bot, 
            allowed_updates=dp.resolve_used_update_types(),
            handle_as_tasks=False  # Process updates sequentially to avoid conflicts
        )
    except TelegramConflictError as e:
        # This is expected during deployment when old and new instances run simultaneously
        # One instance will win and continue working
        logger.info(
            f"Telegram conflict detected (this is normal during deployment): {e}. "
            "Another instance is handling updates. This instance will exit gracefully."
        )
        # Exit gracefully - another instance is handling updates
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
