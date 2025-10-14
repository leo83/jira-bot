import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import Config
from .jira_service import JiraService

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for creating Jira stories."""

    def __init__(self):
        """Initialize the Telegram bot."""
        self.jira_service = JiraService()
        self.application = None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        await update.message.reply_text(
            "Hello! I'm the Jira Bot. Use /task to create a new Jira story in the AAI project."
        )

    async def task_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /task command to create a Jira story."""
        try:
            # Get the user's message text
            message_text = update.message.text

            # Extract the task description (everything after /task)
            if len(message_text.split()) > 1:
                task_description = " ".join(message_text.split()[1:])
            else:
                await update.message.reply_text(
                    "Please provide a task description. Usage: /task Your task description here"
                )
                return

            # Create the Jira story
            await update.message.reply_text("Creating Jira story...")

            issue_key = self.jira_service.create_story(
                summary=task_description,
                description=f"Created via Telegram bot by user {update.effective_user.username or update.effective_user.first_name}",
            )

            if issue_key:
                issue_url = self.jira_service.get_issue_url(issue_key)
                await update.message.reply_text(
                    f"✅ Jira story created successfully!\n\n"
                    f"📋 Task Key: {issue_key}\n"
                    f"🔗 URL: {issue_url}"
                )
            else:
                await update.message.reply_text(
                    "❌ Failed to create Jira story. Please check the bot configuration and try again."
                )

        except Exception as e:
            logger.error(f"Error in task_command: {e}")
            await update.message.reply_text(
                "❌ An error occurred while creating the Jira story. Please try again later."
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command."""
        help_text = """
🤖 Jira Bot Commands:

/task <description> - Create a new Jira story in the AAI project
/help - Show this help message
/start - Start the bot

Example:
/task Implement user authentication system
        """
        await update.message.reply_text(help_text)

    def setup_handlers(self):
        """Set up command handlers for the bot."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("task", self.task_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

    async def run(self):
        """Run the Telegram bot."""
        try:
            # Validate configuration
            Config.validate()

            # Create application
            self.application = (
                Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
            )

            # Setup handlers
            self.setup_handlers()

            # Start the bot
            logger.info("Starting Telegram bot...")
            await self.application.run_polling()

        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
