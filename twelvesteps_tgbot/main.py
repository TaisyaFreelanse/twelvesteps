"""Entry point for the Sekto Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiohttp import web
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


async def health_check(request):
    """Health check endpoint for Render."""
    return web.json_response({"status": "ok", "service": "telegram-bot"})


async def start_bot_polling(bot: Bot, dp: Dispatcher) -> None:
    """Start bot polling in background task."""
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
            "Another instance is handling updates. This instance will continue running HTTP server."
        )
        # Don't exit - keep HTTP server running for health checks
    except KeyboardInterrupt:
        logger.info("Bot polling stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot polling: {e}", exc_info=True)
        # Don't raise - keep HTTP server running


async def main() -> None:
    """Create the bot, wire handlers, start HTTP server and bot polling."""
    # Get port from environment (Render sets PORT automatically)
    port = int(os.environ.get("PORT", 10000))
    
    # Create bot and dispatcher
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp)
    
    # Create HTTP server for health checks (required by Render)
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    # Start bot polling in background
    bot_task = asyncio.create_task(start_bot_polling(bot, dp))
    
    # Start HTTP server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"HTTP server started on port {port} for health checks")
    logger.info("Bot polling started in background")
    
    try:
        # Keep the server running
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        bot_task.cancel()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
