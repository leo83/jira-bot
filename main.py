import asyncio
import logging

from app.config import Config
from app.telegram_bot import TelegramBot

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def main():
    """Main entry point for the Jira Telegram bot."""
    try:
        # Validate configuration
        Config.validate()

        # Create and run the bot
        bot = TelegramBot()
        await bot.run()

    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please check your environment variables.")
    except Exception as e:
        print(f"Failed to start bot: {e}")


if __name__ == "__main__":
    asyncio.run(main())
