import logging
import tempfile
from typing import List

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .component_service import ComponentService
from .config import Config
from .issue_type_service import IssueTypeService
from .jira_service import JiraService
from .users import UserConfig

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for creating Jira stories."""

    def __init__(self):
        """Initialize the Telegram bot."""
        self.jira_service = JiraService()
        self.component_service = ComponentService(self.jira_service)
        self.application = None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        if not update.message:
            return
        await update.message.reply_text(
            "Hello! I'm the Jira Bot. Use /task to create a new Jira story in the AAI project."
        )

    async def task_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /task command to create a Jira story."""
        logger.info("DEBUG: task_command triggered")
        logger.info(f"DEBUG: Message text: '{update.message.text}'")
        logger.info(f"DEBUG: Message caption: '{update.message.caption}'")
        logger.info(f"DEBUG: Has photos: {bool(update.message.photo)}")
        try:
            # Check if message exists
            if not update.message:
                logger.warning("Received update without message")
                return

            # Check user permissions
            user = update.effective_user
            if not UserConfig.is_user_allowed(user.username, user.id):
                await update.message.reply_text(
                    "❌ Access denied. You are not authorized to create Jira tasks.\n"
                    f"Contact administrator to get access."
                )
                logger.warning(
                    f"Unauthorized access attempt by user: {user.username} (ID: {user.id})"
                )
                return

            # Get the user's message text
            message_text = update.message.text or ""

            # Check for photo attachments
            photo_attachments = []
            if update.message.photo:
                photo_attachments = update.message.photo
                logger.info(f"Found {len(photo_attachments)} photo attachments")

            # Extract the task description (everything after /task)
            if message_text and len(message_text.split()) > 1:
                task_description = " ".join(message_text.split()[1:])
                logger.info(f"DEBUG: Task description from text: '{task_description}'")
            elif photo_attachments and not message_text:
                # If there are photos but no text, use a default description
                task_description = "Task with image attachment"
                logger.info("DEBUG: Using default description for photo-only task")
            else:
                await update.message.reply_text(
                    "❌ Please provide a task description.\n\n"
                    "📝 Usage examples:\n"
                    "• `/task Fix login bug`\n"
                    "• `/task Add new feature component: авиа-параметры`\n"
                    "• `/task Fix critical bug type: Bug`\n"
                    "• `/task desc: Implement user authentication system`\n"
                    "• `/task Update database component: devops type: Bug`\n\n"
                    "💡 Available issue types: Story, Bug\n"
                    "💡 Components are matched using transliteration and fuzzy matching\n"
                    "💡 Use `/help` for more detailed information"
                )
                return

            # Check for description specification
            jira_description = None
            if (
                "desc:" in task_description.lower()
                or "description:" in task_description.lower()
            ):
                # Extract description after "desc:" or "description:"
                desc_parts = None
                if "desc:" in task_description.lower():
                    desc_parts = task_description.split("desc:", 1)
                elif "description:" in task_description.lower():
                    desc_parts = task_description.split("description:", 1)

                if desc_parts and len(desc_parts) > 1:
                    jira_description = desc_parts[1].strip()
                    # Remove description part from task_description (summary)
                    task_description = desc_parts[0].strip()
                    logger.info(f"Extracted Jira description: '{jira_description}'")
                    logger.info(f"Task summary: '{task_description}'")

            # Check for component specification
            component_name = Config.JIRA_COMPONENT_NAME  # Default to 'org'
            if "component:" in task_description.lower():
                # Extract component label after "component:"
                parts = task_description.split("component:", 1)
                if len(parts) > 1:
                    component_label = parts[1].strip()
                    # Remove component specification from task description
                    task_description = parts[0].strip()

                    # Find the closest component using transliteration and fuzzy matching
                    component_name, component_message = (
                        self.component_service.find_component(component_label)
                    )
                    logger.info(
                        f"Selected component '{component_name}' for label '{component_label}'"
                    )

                    # If there's a message about available components, send it to the user and stop
                    if component_message:
                        await update.message.reply_text(component_message)
                        return

            # Check for issue type specification
            issue_type = "Story"  # Default to 'Story'
            if "type:" in task_description.lower():
                # Extract issue type label after "type:"
                parts = task_description.split("type:", 1)
                if len(parts) > 1:
                    issue_type_label = parts[1].strip()
                    # Remove issue type specification from task description
                    task_description = parts[0].strip()

                    # Find the closest issue type using fuzzy matching
                    issue_type, issue_type_message = IssueTypeService.find_issue_type(
                        issue_type_label
                    )
                    logger.info(
                        f"Selected issue type '{issue_type}' for label '{issue_type_label}'"
                    )

                    # If there's a message about available issue types, send it to the user and stop
                    if issue_type_message:
                        await update.message.reply_text(issue_type_message)
                        return

            # Create the Jira issue
            await update.message.reply_text(f"Creating Jira {issue_type.lower()}...")

            # Prepare description for Jira
            if jira_description:
                final_description = jira_description
            else:
                final_description = f"Created via Telegram bot by user {user.username or user.first_name}"

            # Download photo attachments if any
            attachment_files = []
            if photo_attachments:
                try:
                    attachment_files = await self._download_photos(photo_attachments)
                    logger.info(f"Downloaded {len(attachment_files)} photo attachments")
                except Exception as e:
                    logger.error(f"Failed to download photo attachments: {e}")
                    await update.message.reply_text(
                        "⚠️ Warning: Failed to download some photo attachments. Creating task without them."
                    )

            issue_key = self.jira_service.create_story(
                summary=task_description,
                description=final_description,
                component_name=component_name,
                issue_type=issue_type,
                attachments=attachment_files,
            )

            if issue_key:
                issue_url = self.jira_service.get_issue_url(issue_key)
                attachment_text = ""
                if photo_attachments:
                    attachment_text = (
                        f"\n📎 Attachments: {len(photo_attachments)} photo(s) attached"
                    )

                await update.message.reply_text(
                    f"✅ Jira {issue_type.lower()} created successfully!\n\n"
                    f"📋 Task Key: {issue_key}\n"
                    f"🔗 URL: {issue_url}{attachment_text}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to create Jira {issue_type.lower()}. Please check the bot configuration and try again."
                )

        except Exception as e:
            logger.error(f"Error in task_command: {e}")
            await update.message.reply_text(
                "❌ An error occurred while creating the Jira story. Please try again later."
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command."""
        if not update.message:
            return
        help_text = """
🤖 Jira Bot Commands:

/task <description> - Create a new Jira story in the AAI project
/task <description> component: <component_label> - Create story with specific component
/task <description> type: <issue_type> - Create issue with specific type (Story, Bug)
/task desc: <description> - Use description after "desc:" as task description
/task description: <description> - Use description after "description:" as task description
/help - Show this help message
/start - Start the bot
/userinfo - Show your user information
/admin - Show admin information (requires authorization)

📝 Examples:
/task Fix login bug
/task Add new feature component: авиа-параметры
/task Fix critical bug type: Bug
/task desc: Implement user authentication system
/task description: Update database schema component: devops type: Bug

💡 Features:
• Component matching uses transliteration and fuzzy matching for Russian labels
• Components are fetched dynamically from Jira (DEPRECATED components are filtered out)
• Available issue types: Story, Bug
• If no close component match is found, you'll see available components list
• Image attachments are automatically added to Jira tasks
        """
        await update.message.reply_text(help_text)

    async def _download_photos(self, photo_attachments: List) -> List[str]:
        """
        Download photo attachments from Telegram and return file paths.
        Only downloads the highest quality version of each photo.

        Args:
            photo_attachments: List of photo objects from Telegram

        Returns:
            List[str]: List of downloaded file paths
        """
        downloaded_files = []

        # Since Telegram sends multiple photo objects for the same image (different sizes),
        # we should only download the highest quality one
        if not photo_attachments:
            return downloaded_files

        # Find the highest quality photo (largest file_size)
        best_photo = max(photo_attachments, key=lambda p: p.file_size or 0)
        logger.info(
            f"DEBUG: Selected best photo - file_size: {best_photo.file_size}, width: {best_photo.width}, height: {best_photo.height}"
        )

        # Only process the best photo
        unique_photos = {best_photo.file_id: best_photo}

        logger.info(
            f"Processing 1 unique photo from {len(photo_attachments)} total photo objects"
        )

        for i, photo in enumerate(unique_photos.values()):
            try:
                # Get the highest resolution photo
                file = await self.application.bot.get_file(photo.file_id)

                # Create temporary file
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_{i}.jpg"
                ) as temp_file:
                    temp_path = temp_file.name

                logger.info(f"DEBUG: Creating temp file for photo {i + 1}: {temp_path}")
                logger.info(
                    f"DEBUG: Photo details - file_id: {photo.file_id}, size: {photo.file_size}"
                )

                # Download the file
                await file.download_to_drive(temp_path)
                downloaded_files.append(temp_path)
                logger.info(f"DEBUG: Downloaded unique photo {i + 1} to {temp_path}")

            except Exception as e:
                logger.error(f"Failed to download photo {i + 1}: {e}")
                continue

        return downloaded_files

    async def userinfo_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle the /userinfo command to show user information."""
        if not update.message:
            return
        user = update.effective_user
        is_allowed = UserConfig.is_user_allowed(user.username, user.id)

        user_info = f"""
👤 User Information:

🆔 User ID: {user.id}
👤 Username: @{user.username or "Not set"}
📛 Name: {user.first_name} {user.last_name or ""}
✅ Access: {"Authorized" if is_allowed else "Not authorized"}
        """

        await update.message.reply_text(user_info)

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /admin command to show admin information."""
        if not update.message:
            return
        user = update.effective_user

        # Check if user is authorized (basic admin check)
        if not UserConfig.is_user_allowed(user.username, user.id):
            await update.message.reply_text("❌ Access denied.")
            return

        admin_info = f"""
🔧 Admin Information:

👥 Allowed Users: {UserConfig.get_allowed_users_display()}
📊 Total Allowed: {len(UserConfig.get_allowed_users())}
        """

        await update.message.reply_text(admin_info)

    async def photo_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle photo-only messages (no text, just photos)."""
        logger.info("DEBUG: photo_message_handler triggered")
        logger.info(f"DEBUG: Message text: '{update.message.text}'")
        logger.info(f"DEBUG: Message caption: '{update.message.caption}'")
        logger.info(f"DEBUG: Has photos: {bool(update.message.photo)}")
        try:
            # Check if message exists
            if not update.message:
                logger.warning("Received update without message")
                return

            # Check if there's a command in the caption - if so, process it directly
            caption = update.message.caption or ""
            if caption.startswith("/task"):
                logger.info(
                    "DEBUG: Found /task command in caption, processing directly"
                )

                # Extract task description from caption (everything after /task)
                task_description = (
                    " ".join(caption.split()[1:]) if len(caption.split()) > 1 else ""
                )
                logger.info(
                    f"DEBUG: Task description from caption: '{task_description}'"
                )

                # Process the task with the caption text
                await self._process_task(update, task_description, update.message.photo)
                return

            # Check user permissions
            user = update.effective_user
            if not UserConfig.is_user_allowed(user.username, user.id):
                await update.message.reply_text(
                    "❌ Access denied. You are not authorized to create Jira tasks.\n"
                    f"Contact administrator to get access."
                )
                logger.warning(
                    f"Unauthorized access attempt by user: {user.username} (ID: {user.id})"
                )
                return

            # This handler only processes photo-only messages (no text at all)
            # Get photo attachments
            photo_attachments = []
            if update.message.photo:
                photo_attachments = update.message.photo
                logger.info(
                    f"Found {len(photo_attachments)} photo attachments in photo-only message"
                )

            # Use default description for photo-only tasks
            task_description = "Task with image attachment"
            logger.info("DEBUG: Using default description for photo-only task")

            # Process the task
            await self._process_task(update, task_description, photo_attachments)

        except Exception as e:
            logger.error(f"Error in photo_message_handler: {e}")
            await update.message.reply_text(
                "❌ An error occurred while processing the photo message. Please try again later."
            )

    async def _process_task(
        self, update: Update, task_description: str, photo_attachments: List
    ):
        """Common task processing logic for both text and photo messages."""
        try:
            user = update.effective_user

            # Check for description specification
            jira_description = None
            if (
                "desc:" in task_description.lower()
                or "description:" in task_description.lower()
            ):
                # Extract description after "desc:" or "description:"
                desc_parts = None
                if "desc:" in task_description.lower():
                    desc_parts = task_description.split("desc:", 1)
                elif "description:" in task_description.lower():
                    desc_parts = task_description.split("description:", 1)

                if desc_parts and len(desc_parts) > 1:
                    jira_description = desc_parts[1].strip()
                    # Remove description part from task_description (summary)
                    task_description = desc_parts[0].strip()
                    logger.info(f"Extracted Jira description: '{jira_description}'")
                    logger.info(f"Task summary: '{task_description}'")

            # Check for component specification
            component_name = Config.JIRA_COMPONENT_NAME  # Default to 'org'
            if "component:" in task_description.lower():
                # Extract component label after "component:"
                parts = task_description.split("component:", 1)
                if len(parts) > 1:
                    component_label = parts[1].strip()
                    # Remove component specification from task description
                    task_description = parts[0].strip()

                    # Find the closest component using transliteration and fuzzy matching
                    component_name, component_message = (
                        self.component_service.find_component(component_label)
                    )
                    logger.info(
                        f"Selected component '{component_name}' for label '{component_label}'"
                    )

                    # If there's a message about available components, send it to the user and stop
                    if component_message:
                        await update.message.reply_text(component_message)
                        return

            # Check for issue type specification
            issue_type = "Story"  # Default to 'Story'
            if "type:" in task_description.lower():
                # Extract issue type label after "type:"
                parts = task_description.split("type:", 1)
                if len(parts) > 1:
                    issue_type_label = parts[1].strip()
                    # Remove issue type specification from task description
                    task_description = parts[0].strip()

                    # Find the closest issue type using fuzzy matching
                    issue_type, issue_type_message = IssueTypeService.find_issue_type(
                        issue_type_label
                    )
                    logger.info(
                        f"Selected issue type '{issue_type}' for label '{issue_type_label}'"
                    )

                    # If there's a message about available issue types, send it to the user and stop
                    if issue_type_message:
                        await update.message.reply_text(issue_type_message)
                        return

            # Create the Jira issue
            await update.message.reply_text(f"Creating Jira {issue_type.lower()}...")

            # Prepare description for Jira
            if jira_description:
                final_description = jira_description
            else:
                final_description = f"Created via Telegram bot by user {user.username or user.first_name}"

            # Download photo attachments if any
            attachment_files = []
            if photo_attachments:
                try:
                    attachment_files = await self._download_photos(photo_attachments)
                    logger.info(f"Downloaded {len(attachment_files)} photo attachments")
                except Exception as e:
                    logger.error(f"Failed to download photo attachments: {e}")
                    await update.message.reply_text(
                        "⚠️ Warning: Failed to download some photo attachments. Creating task without them."
                    )

            issue_key = self.jira_service.create_story(
                summary=task_description,
                description=final_description,
                component_name=component_name,
                issue_type=issue_type,
                attachments=attachment_files,
            )

            if issue_key:
                issue_url = self.jira_service.get_issue_url(issue_key)
                attachment_text = ""
                if photo_attachments:
                    attachment_text = (
                        f"\n📎 Attachments: {len(photo_attachments)} photo(s) attached"
                    )

                await update.message.reply_text(
                    f"✅ Jira {issue_type.lower()} created successfully!\n\n"
                    f"📋 Task Key: {issue_key}\n"
                    f"🔗 URL: {issue_url}{attachment_text}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to create Jira {issue_type.lower()}. Please check the bot configuration and try again."
                )

        except Exception as e:
            logger.error(f"Error in _process_task: {e}")
            await update.message.reply_text(
                "❌ An error occurred while creating the Jira story. Please try again later."
            )

    def setup_handlers(self):
        """Set up command handlers for the bot."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("task", self.task_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("userinfo", self.userinfo_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        # Handle photo-only messages (no text, just photos, and not commands)
        # This should only trigger for messages that have photos but NO text at all
        self.application.add_handler(
            MessageHandler(
                filters.PHOTO & ~filters.TEXT,
                self.photo_message_handler,
            )
        )

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
