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
from .database_service import DatabaseService
from .issue_type_service import IssueTypeService
from .jira_service import JiraService
from .sprint_service import SprintService
from .users import UserConfig

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for creating Jira stories."""

    def __init__(self):
        """Initialize the Telegram bot."""
        self.jira_service = JiraService()
        self.component_service = ComponentService(self.jira_service)
        self.sprint_service = SprintService(self.jira_service.jira)
        self.database_service = DatabaseService()
        self.application = None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        if not update.message:
            return
        await update.message.reply_text(
            f"Hello! I'm the Jira Bot. Use /task to create a new Jira task or /desc to view existing tasks.\n\n"
            f"Type /help for more commands."
        )

    async def _parse_task_parameters(self, task_description: str, update: Update):
        """
        Parse task parameters from task_description. Parameters can appear in any order.
        Supported parameters: type:, component:, sprint:, desc:/description:, link:, project:
        Returns: (summary, description, component_name, issue_type, sprint_id, link_issue, project_key, should_stop)
        """
        import re

        # Initialize defaults
        issue_type = "Story"
        component_name = Config.JIRA_COMPONENT_NAME
        jira_description = None
        sprint_id = None
        link_issue = None
        project_key = Config.JIRA_PROJECT_KEY

        # Pattern to find all parameters: type:, component:, sprint:, desc:, description:, link:, project:
        # This captures the parameter name and value up to the next parameter keyword
        # re.DOTALL allows . to match newlines so desc: can contain multi-line text
        # The lookahead stops at word boundary before next parameter keyword (no space required)
        param_pattern = r"(type:|component:|sprint:|desc:|description:|link:|project:)\s*(.+?)(?=\s*\b(?:type:|component:|sprint:|desc:|description:|link:|project:)|$)"

        matches = list(
            re.finditer(param_pattern, task_description, re.IGNORECASE | re.DOTALL)
        )

        if matches:
            # Extract parameters
            params = {}
            for match in matches:
                param_name = match.group(1).lower().rstrip(":")
                param_value = match.group(2).strip()

                # Handle desc/description as the same parameter
                if param_name in ["desc", "description"]:
                    param_name = "description"

                params[param_name] = param_value

            # Remove all parameter definitions from the task description to get the summary
            summary = task_description
            for match in reversed(
                matches
            ):  # Remove in reverse order to maintain positions
                summary = summary[: match.start()] + summary[match.end() :]
            summary = summary.strip()

            # Process project parameter first (before component and link parameters need it)
            if "project" in params:
                project_key = params["project"].strip().upper()
                logger.info(f"Using custom project: '{project_key}'")

            # Process type parameter
            if "type" in params:
                issue_type_label = params["type"]
                issue_type, issue_type_message = IssueTypeService.find_issue_type(
                    issue_type_label
                )
                logger.info(
                    f"Selected issue type '{issue_type}' for label '{issue_type_label}'"
                )

                if issue_type_message:
                    await update.message.reply_text(issue_type_message)
                    return None, None, None, None, None, None, None, True

            # Process component parameter (needs project_key)
            if "component" in params:
                component_label = params["component"]
                component_name, component_message = (
                    self.component_service.find_component(component_label, project_key)
                )
                logger.info(
                    f"Selected component '{component_name}' for label '{component_label}' in project '{project_key}'"
                )

                if component_message:
                    await update.message.reply_text(component_message)
                    return None, None, None, None, None, None, None, True

            # Process sprint parameter
            if "sprint" in params:
                sprint_query = params["sprint"]
                sprint_id, sprint_message = self.sprint_service.find_sprint(
                    sprint_query
                )

                if sprint_message:
                    # Error or ambiguity - notify user
                    await update.message.reply_text(sprint_message)
                    return None, None, None, None, None, None, None, True

                logger.info(
                    f"Selected sprint ID: {sprint_id} for query '{sprint_query}'"
                )

            # Process description parameter
            if "description" in params:
                jira_description = params["description"]
                logger.info(f"Extracted Jira description: '{jira_description}'")

            # Process link parameter
            if "link" in params:
                link_issue = params["link"].strip()
                # If only digits, prepend project key
                if link_issue.isdigit():
                    link_issue = f"{project_key}-{link_issue}"
                logger.info(f"Extracted link issue: '{link_issue}'")

            # Use summary from what's left after removing parameters
            task_description = summary
            logger.info(f"Task summary: '{task_description}'")

            # If summary is empty but description exists, use description as summary
            if not task_description and jira_description:
                task_description = jira_description
                jira_description = None
                logger.info(
                    f"Summary was empty, using description as summary: '{task_description}'"
                )

            # Clean summary: remove newlines and extra whitespace (Jira doesn't allow newlines in summary)
            if task_description:
                task_description = " ".join(task_description.split())
                logger.info(f"Cleaned summary (removed newlines): '{task_description}'")

            # Truncate summary to 255 characters (Jira limit)
            if task_description and len(task_description) > 255:
                logger.warning(
                    f"Summary too long ({len(task_description)} chars), truncating to 255 chars"
                )
                task_description = task_description[:252] + "..."

        return (
            task_description,
            jira_description,
            component_name,
            issue_type,
            sprint_id,
            link_issue,
            project_key,
            False,
        )

    async def _process_bug_or_story(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, task_description: str
    ):
        """Common processing logic for /bug and /story commands."""
        try:
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

            # Check for photo attachments
            photo_attachments = []
            if update.message.photo:
                photo_attachments = update.message.photo
                logger.info(f"Found {len(photo_attachments)} photo attachments")

            # Parse task parameters using the helper method
            (
                task_description,
                jira_description,
                component_name,
                issue_type,
                sprint_id,
                link_issue,
                project_key,
                should_stop,
            ) = await self._parse_task_parameters(task_description, update)
            if should_stop:
                return

            # Prepare labels for Jira issue
            labels = []
            chat = update.effective_chat

            # Add chat/channel name as label
            if chat:
                if chat.type in ["group", "supergroup", "channel"]:
                    # For groups and channels, use the chat title
                    if chat.title:
                        # Clean label: replace spaces and special chars
                        chat_label = chat.title.replace(" ", "_").replace("-", "_")
                        labels.append(f"tg_chat:{chat_label}")
                elif chat.type == "private":
                    # For private chats, use "private"
                    labels.append("tg_chat:private")

            # Add username as label
            if user:
                if user.username:
                    labels.append(f"tg_user:{user.username}")
                elif user.first_name:
                    # If no username, use first name
                    user_label = user.first_name.replace(" ", "_").replace("-", "_")
                    labels.append(f"tg_user:{user_label}")

            logger.info(f"Adding labels to Jira issue: {labels}")

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

            issue_key, error_message = self.jira_service.create_story(
                summary=task_description,
                description=final_description,
                component_name=component_name,
                issue_type=issue_type,
                attachments=attachment_files,
                sprint_id=sprint_id,
                labels=labels,
                project_key=project_key,
            )

            if error_message:
                # If there's an error message, send it to the user
                await update.message.reply_text(error_message)
                return

            if issue_key:
                issue_url = self.jira_service.get_issue_url(issue_key)

                # Link to another issue if specified
                if link_issue:
                    link_success = self.jira_service.link_issues(
                        inward_issue=issue_key, outward_issue=link_issue
                    )
                    if link_success:
                        logger.info(f"Successfully linked {issue_key} to {link_issue}")
                    else:
                        await update.message.reply_text(
                            f"⚠️ Created task but failed to link to {link_issue}. Please check the issue key."
                        )

                await update.message.reply_text(
                    f"✅ Jira {issue_type.lower()} created successfully!\n\n"
                    f"📋 Task Key: {issue_key}\n"
                    f"🔗 URL: {issue_url}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to create Jira {issue_type.lower()}. Please check the bot configuration and try again."
                )

        except Exception as e:
            logger.error(f"Error in _process_bug_or_story: {e}")
            await update.message.reply_text(
                "❌ An error occurred while creating the Jira task. Please try again later."
            )

    async def bug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /bug command as a shortcut for creating a bug."""
        logger.info("DEBUG: bug_command triggered")
        # Get the task description and force type to Bug
        if update.message and update.message.text:
            # Get everything after /bug
            parts = update.message.text.split(maxsplit=1)
            if len(parts) > 1:
                task_description = parts[1]
                # Remove type: parameter if it exists (it will be ignored)
                import re

                task_description = re.sub(
                    r"\btype:\s*\w+", "", task_description, flags=re.IGNORECASE
                ).strip()
                # Add type: Bug to the description
                task_description = f"{task_description} type: Bug".strip()
            else:
                task_description = "type: Bug"

            # Process as task command with modified description
            await self._process_bug_or_story(update, context, task_description)
        else:
            await update.message.reply_text(
                "❌ Please provide a bug description.\n\n"
                "📝 Usage: `/bug <description>`\n"
                "Example: `/bug Login fails on mobile`"
            )

    async def story_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /story command as a shortcut for creating a story."""
        logger.info("DEBUG: story_command triggered")
        # Get the task description and force type to Story
        if update.message and update.message.text:
            # Get everything after /story
            parts = update.message.text.split(maxsplit=1)
            if len(parts) > 1:
                task_description = parts[1]
                # Remove type: parameter if it exists (it will be ignored)
                import re

                task_description = re.sub(
                    r"\btype:\s*\w+", "", task_description, flags=re.IGNORECASE
                ).strip()
                # Add type: Story to the description
                task_description = f"{task_description} type: Story".strip()
            else:
                task_description = "type: Story"

            # Process as task command with modified description
            await self._process_bug_or_story(update, context, task_description)
        else:
            await update.message.reply_text(
                "❌ Please provide a story description.\n\n"
                "📝 Usage: `/story <description>`\n"
                "Example: `/story Add new dashboard feature`"
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

            # Parse task parameters using the helper method
            (
                task_description,
                jira_description,
                component_name,
                issue_type,
                sprint_id,
                link_issue,
                project_key,
                should_stop,
            ) = await self._parse_task_parameters(task_description, update)
            if should_stop:
                return

            # Prepare labels for Jira issue
            labels = []
            chat = update.effective_chat

            # Add chat/channel name as label
            if chat:
                if chat.type in ["group", "supergroup", "channel"]:
                    # For groups and channels, use the chat title
                    if chat.title:
                        # Clean label: replace spaces and special chars
                        chat_label = chat.title.replace(" ", "_").replace("-", "_")
                        labels.append(f"tg_chat:{chat_label}")
                elif chat.type == "private":
                    # For private chats, use "private"
                    labels.append("tg_chat:private")

            # Add username as label
            if user:
                if user.username:
                    labels.append(f"tg_user:{user.username}")
                elif user.first_name:
                    # If no username, use first name
                    user_label = user.first_name.replace(" ", "_").replace("-", "_")
                    labels.append(f"tg_user:{user_label}")

            logger.info(f"Adding labels to Jira issue: {labels}")

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

            issue_key, error_message = self.jira_service.create_story(
                summary=task_description,
                description=final_description,
                component_name=component_name,
                issue_type=issue_type,
                attachments=attachment_files,
                sprint_id=sprint_id,
                labels=labels,
                project_key=project_key,
            )

            if error_message:
                # If there's an error message, send it to the user
                await update.message.reply_text(error_message)
                return

            if issue_key:
                issue_url = self.jira_service.get_issue_url(issue_key)

                # Link to another issue if specified
                if link_issue:
                    link_success = self.jira_service.link_issues(
                        inward_issue=issue_key, outward_issue=link_issue
                    )
                    if link_success:
                        logger.info(f"Successfully linked {issue_key} to {link_issue}")
                    else:
                        await update.message.reply_text(
                            f"⚠️ Created task but failed to link to {link_issue}. Please check the issue key."
                        )

                await update.message.reply_text(
                    f"✅ Jira {issue_type.lower()} created successfully!\n\n"
                    f"📋 Task Key: {issue_key}\n"
                    f"🔗 URL: {issue_url}"
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
        help_text = f"""
🤖 Jira Bot Commands:

/task <description> - Create a new Jira task
/bug <description> - Create a bug (shortcut for /task with type: Bug)
/story <description> - Create a story (shortcut for /task with type: Story)
/task <description> component: <label> - Create task with specific component
/task <description> type: <type> - Create task with specific type (Story, Bug)
/task <description> sprint: <query> - Add task to a specific sprint
/task <description> link: <issue-key> - Link to another Jira issue
/task <description> project: <key> - Create task in a specific project (default: AAI)
/task desc: <description> - Use description after "desc:" as task description
/desc <issue-key> - Get details of a Jira issue (e.g., /desc 123 or /desc PROJ-123)
/link message_ref: <uuid> jira: <key> - Store message reference and Jira issue link
/help - Show this help message
/start - Start the bot
/userinfo - Show your user information
/admin - Show admin information (requires authorization)

📝 Examples:
/task Fix login bug
/bug Critical authentication error
/story Add new dashboard component: авиа-параметры
/desc 123
/desc PROJ-456
/link message_ref: 550e8400-e29b-41d4-a716-446655440000 jira: AAI-1020
/task Fix critical bug type: Bug
/bug Login issue component: авиа-параметры sprint: active
/story desc: Implement user authentication system
/task Update schema component: devops type: Bug sprint: s3 agent
/bug Fix related issue link: 2825
/task Create new feature project: PROJ component: frontend
/bug Database error project: SV component: backend sprint: active
/story New UI feature project: DESIGN component: frontend

💡 Features:
• Component matching uses transliteration and fuzzy matching for Russian labels
• Components are fetched dynamically from Jira (DEPRECATED components are filtered out)
• Sprint matching uses fuzzy matching (e.g., "s3 agent" matches "2025Q4-S3_агент")
• Link parameter creates "Relates" link to specified issue (e.g., link: 123 or link: PROJ-123)
• Project parameter allows creating tasks in any Jira project (default: AAI)
• Available issue types: Story, Bug
• /bug and /story commands ignore any type: parameter but support all other parameters (component, sprint, link, project, desc)
• If no close component match is found, you'll see available components list
• Image attachments are automatically added to Jira tasks (works with /task, /bug, and /story)
• All parameters (type, component, sprint, link, project, desc) can appear in any order
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

        # Handle photo attachments - they may already be filtered (from media groups) or need filtering
        if not photo_attachments:
            return downloaded_files

        # If we have already-filtered photos (from media group collection), use them all
        # Otherwise, take only the last photo (highest quality) from a single message
        if len(photo_attachments) > 1 and all(
            hasattr(p, "file_unique_id") for p in photo_attachments
        ):
            # Check if these are different photos (different file_unique_id prefixes)
            # For media groups, we already collected only the best version of each
            unique_photos = {p.file_id: p for p in photo_attachments}
            logger.info(
                f"Processing {len(unique_photos)} photos from media group or attachment list"
            )
        else:
            # Single message with multiple sizes of one photo - take the last (highest quality)
            best_photo = photo_attachments[-1]
            logger.info(
                f"DEBUG: Selected last photo as best - file_size: {best_photo.file_size}, width: {best_photo.width}, height: {best_photo.height}"
            )
            logger.info(
                f"Processing 1 photo (selecting last/highest quality) from {len(photo_attachments)} total photo objects"
            )
            unique_photos = {best_photo.file_id: best_photo}

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

    async def link_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /link command to store message reference and Jira key in database."""
        if not update.message:
            return

        user = update.effective_user

        # Check user permissions
        if not UserConfig.is_user_allowed(user.username, user.id):
            await update.message.reply_text(
                "❌ Access denied. You are not authorized to use this command."
            )
            logger.warning(
                f"Unauthorized access attempt by user: {user.username} (ID: {user.id})"
            )
            return

        # Parse command arguments
        message_text = update.message.text or ""
        parts = message_text.split(maxsplit=1)

        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Please provide parameters.\n\n"
                "Usage: `/link message_ref: <uuid> jira: <issue-key>`\n"
                "Examples:\n"
                "  • `/link message_ref: 550e8400-e29b-41d4-a716-446655440000 jira: AAI-1020`\n"
                "  • `/link message_ref: 123e4567-e89b-12d3-a456-426614174000 jira: SV-4403`"
            )
            return

        # Extract parameters using regex
        import re

        param_text = parts[1]
        message_ref = None
        jira_key = None

        # Pattern to extract message_ref and jira parameters
        message_ref_match = re.search(
            r"message_ref:\s*([a-fA-F0-9\-]+)", param_text, re.IGNORECASE
        )
        jira_match = re.search(r"jira:\s*([A-Z]+-\d+|\d+)", param_text, re.IGNORECASE)

        if message_ref_match:
            message_ref = message_ref_match.group(1).strip()

        if jira_match:
            jira_key = jira_match.group(1).strip().upper()
            # If only digits, prepend default project key
            if jira_key.isdigit():
                jira_key = f"{Config.JIRA_PROJECT_KEY}-{jira_key}"

        # Validate parameters
        if not message_ref or not jira_key:
            await update.message.reply_text(
                "❌ Both message_ref and jira parameters are required.\n\n"
                "Usage: `/link message_ref: <uuid> jira: <issue-key>`\n"
                "Examples:\n"
                "  • `/link message_ref: 550e8400-e29b-41d4-a716-446655440000 jira: AAI-1020`\n"
                "  • `/link message_ref: 123e4567-e89b-12d3-a456-426614174000 jira: 4403`"
            )
            return

        # Validate UUID format
        uuid_pattern = re.compile(
            r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
        )
        if not uuid_pattern.match(message_ref):
            await update.message.reply_text(
                f"❌ Invalid UUID format for message_ref: {message_ref}\n\n"
                "Expected format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            )
            return

        # Insert into database and add comment to Jira
        try:
            success, error_reason = self.database_service.insert_jira_issue_link(
                message_ref, jira_key
            )

            if success:
                # Add comment to Jira issue with link to message reference
                grafana_url = f"{Config.GRAFANA_MESSAGE_URL}{message_ref}"
                comment = f"Message reference linked: {grafana_url}"
                comment_added = self.jira_service.add_comment(jira_key, comment)

                if comment_added:
                    await update.message.reply_text(
                        f"✅ Successfully linked:\n"
                        f"• Message Ref: {message_ref}\n"
                        f"• Jira Issue: {jira_key}\n\n"
                        f"📊 Grafana: {grafana_url}\n"
                        f"🔗 Jira: {self.jira_service.get_issue_url(jira_key)}",
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ Link stored but failed to add comment to Jira:\n"
                        f"• Message Ref: {message_ref}\n"
                        f"• Jira Issue: {jira_key}\n\n"
                        f"📊 Grafana: {grafana_url}\n"
                        f"🔗 Jira: {self.jira_service.get_issue_url(jira_key)}",
                    )

                logger.info(
                    f"User {user.username} linked message_ref {message_ref} to Jira issue {jira_key}"
                )
            elif error_reason == "duplicate":
                await update.message.reply_text(
                    f"⚠️ This link already exists:\n"
                    f"• Message Ref: {message_ref}\n"
                    f"• Jira Issue: {jira_key}"
                )
                logger.warning(
                    f"Duplicate link attempt by {user.username}: message_ref={message_ref}, jira_key={jira_key}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to store the link. Database error occurred."
                )
                logger.error(
                    f"Failed to insert link: message_ref={message_ref}, jira_key={jira_key}"
                )

        except Exception as e:
            await update.message.reply_text(
                f"❌ An error occurred while storing the link: {str(e)}"
            )
            logger.error(f"Error in link_command: {e}", exc_info=True)

    async def desc_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /desc command to fetch and display Jira issue details."""
        if not update.message:
            return

        user = update.effective_user

        # Check user permissions
        if not UserConfig.is_user_allowed(user.username, user.id):
            await update.message.reply_text(
                "❌ Access denied. You are not authorized to view Jira tasks."
            )
            logger.warning(
                f"Unauthorized access attempt by user: {user.username} (ID: {user.id})"
            )
            return

        # Get the issue key from the command
        message_text = update.message.text or ""
        parts = message_text.split(maxsplit=1)

        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Please provide an issue key.\n\n"
                "Usage: `/desc <issue-key>`\n"
                "Examples:\n"
                "  • `/desc 123` - Gets PROJ-123 (uses default project)\n"
                "  • `/desc PROJ-123` - Gets PROJ-123\n"
                "  • `/desc OTHER-456` - Gets OTHER-456"
            )
            return

        issue_key = parts[1].strip()

        # Send "fetching" message
        await update.message.reply_text(f"🔍 Fetching issue {issue_key}...")

        try:
            # Get issue details from Jira
            issue_data = self.jira_service.get_issue(issue_key)

            if not issue_data:
                await update.message.reply_text(
                    f"❌ Could not find issue {issue_key} or you don't have permission to view it."
                )
                return

            # Format issue information
            issue_text = f"""
📋 **{issue_data["key"]}** - {issue_data["issue_type"]}

**Summary:** {issue_data["summary"]}

**Status:** {issue_data["status"]}
**Assignee:** {issue_data["assignee"]}
**Reporter:** {issue_data["reporter"]}

**Description:**
{issue_data["description"]}

🔗 {self.jira_service.get_issue_url(issue_data["key"])}
"""

            # Check if there are image attachments
            image_attachments = []
            other_attachments = []

            if issue_data["attachments"]:
                for attachment in issue_data["attachments"]:
                    if attachment["mimeType"].startswith("image/"):
                        image_attachments.append(attachment)
                    else:
                        other_attachments.append(attachment)

            # If there's at least one image, send the first image with the issue text as caption
            if image_attachments:
                first_image = image_attachments[0]
                try:
                    file_path = self.jira_service.download_attachment(
                        first_image["content_url"], first_image["filename"]
                    )

                    if file_path:
                        with open(file_path, "rb") as f:
                            await update.message.reply_photo(
                                photo=f, caption=issue_text, parse_mode="Markdown"
                            )

                        # Clean up
                        import os

                        try:
                            os.unlink(file_path)
                        except:
                            pass

                        # Remove the first image from the list
                        image_attachments = image_attachments[1:]
                except Exception as e:
                    logger.error(f"Failed to send first image: {e}")
                    # Fallback to text-only message
                    await update.message.reply_text(issue_text, parse_mode="Markdown")
            else:
                # No images, send text only
                await update.message.reply_text(issue_text, parse_mode="Markdown")

            # Send remaining image attachments
            if image_attachments:
                for attachment in image_attachments:
                    try:
                        file_path = self.jira_service.download_attachment(
                            attachment["content_url"], attachment["filename"]
                        )

                        if file_path:
                            with open(file_path, "rb") as f:
                                await update.message.reply_photo(
                                    photo=f, caption=f"📎 {attachment['filename']}"
                                )

                            # Clean up
                            import os

                            try:
                                os.unlink(file_path)
                            except:
                                pass
                    except Exception as e:
                        logger.error(
                            f"Failed to send attachment {attachment['filename']}: {e}"
                        )
                        await update.message.reply_text(
                            f"⚠️ Failed to download attachment: {attachment['filename']}"
                        )

            # Send non-image attachments
            if other_attachments:
                for attachment in other_attachments:
                    try:
                        file_path = self.jira_service.download_attachment(
                            attachment["content_url"], attachment["filename"]
                        )

                        if file_path:
                            with open(file_path, "rb") as f:
                                await update.message.reply_document(
                                    document=f,
                                    filename=attachment["filename"],
                                    caption=f"📎 {attachment['filename']}",
                                )

                            # Clean up
                            import os

                            try:
                                os.unlink(file_path)
                            except:
                                pass
                    except Exception as e:
                        logger.error(
                            f"Failed to send attachment {attachment['filename']}: {e}"
                        )
                        await update.message.reply_text(
                            f"⚠️ Failed to download attachment: {attachment['filename']}"
                        )

        except Exception as e:
            logger.error(f"Error in desc_command: {e}")
            await update.message.reply_text(
                "❌ An error occurred while fetching the issue. Please try again later."
            )

    async def photo_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle photo-only messages (no text, just photos)."""
        logger.info("DEBUG: photo_message_handler triggered")
        logger.info(f"DEBUG: Message text: '{update.message.text}'")
        logger.info(f"DEBUG: Message caption: '{update.message.caption}'")
        logger.info(f"DEBUG: Has photos: {bool(update.message.photo)}")
        logger.info(f"DEBUG: Media group ID: '{update.message.media_group_id}'")
        try:
            # Check if message exists
            if not update.message:
                logger.warning("Received update without message")
                return

            # Check if this is part of a media group (multiple photos sent together)
            if update.message.media_group_id:
                logger.info(
                    f"DEBUG: Part of media group {update.message.media_group_id}"
                )

                # Keys for tracking media groups
                media_group_id = update.message.media_group_id
                task_key = f"task_{media_group_id}"
                photo_count_key = f"photo_count_{media_group_id}"

                # Check if we already created a task for this media group
                existing_task_key = context.bot_data.get(task_key)

                if existing_task_key:
                    # Task already exists, add this photo to it
                    logger.info(
                        f"DEBUG: Task already exists for media group {media_group_id}, adding photo"
                    )

                    if update.message.photo:
                        best_photo = update.message.photo[-1]

                        # Download and attach the photo
                        try:
                            photo_file = await context.bot.get_file(best_photo.file_id)
                            photo_count = context.bot_data.get(photo_count_key, 1) + 1

                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix=f"_{photo_count - 1}.jpg"
                            ) as temp_file:
                                temp_path = temp_file.name
                                logger.info(
                                    f"DEBUG: Downloading additional photo {photo_count} to {temp_path}"
                                )
                                await photo_file.download_to_drive(temp_path)

                                # Add attachment to existing Jira task
                                self.jira_service.add_attachment(
                                    existing_task_key, temp_path
                                )
                                logger.info(
                                    f"DEBUG: Added photo {photo_count} to task {existing_task_key}"
                                )

                                # Update photo count
                                context.bot_data[photo_count_key] = photo_count

                                # Clean up temp file
                                import os

                                try:
                                    os.unlink(temp_path)
                                except:
                                    pass
                        except Exception as e:
                            logger.error(f"Error adding additional photo to task: {e}")

                    return

                # This is the first photo in the media group
                logger.info(f"DEBUG: First photo in media group {media_group_id}")

                # Process the caption to extract task details
                caption = update.message.caption or ""

                # Only create task if there's a /task, /bug, or /story command
                if (
                    caption.startswith("/task")
                    or caption.startswith("/bug")
                    or caption.startswith("/story")
                ):
                    command = caption.split()[0]
                    logger.info(
                        f"DEBUG: Found {command} command in first photo caption"
                    )

                    # Extract description after command
                    task_description = (
                        " ".join(caption.split()[1:])
                        if len(caption.split()) > 1
                        else ""
                    )

                    # Add type parameter for /bug and /story
                    import re

                    if command == "/bug":
                        task_description = re.sub(
                            r"\btype:\s*\w+", "", task_description, flags=re.IGNORECASE
                        ).strip()
                        task_description = f"{task_description} type: Bug".strip()
                    elif command == "/story":
                        task_description = re.sub(
                            r"\btype:\s*\w+", "", task_description, flags=re.IGNORECASE
                        ).strip()
                        task_description = f"{task_description} type: Story".strip()

                    # Process and create the task with the first photo
                    if update.message.photo:
                        # Only use the highest quality version (last one in the list)
                        best_photo = update.message.photo[-1]
                        photos_to_process = [best_photo]

                        # Create the task and get the task key
                        created_task_key = await self._process_task(
                            update, task_description, photos_to_process
                        )

                        # Store the task key for this media group
                        if created_task_key:
                            context.bot_data[task_key] = created_task_key
                            context.bot_data[photo_count_key] = 1
                            logger.info(
                                f"DEBUG: Stored task {created_task_key} for media group {media_group_id}"
                            )
                else:
                    # No command, just ignore the photo
                    logger.info("DEBUG: Media group photo without command - ignoring")

                return

            # Check if there's a command in the caption - if so, process it directly
            caption = update.message.caption or ""
            if (
                caption.startswith("/task")
                or caption.startswith("/bug")
                or caption.startswith("/story")
            ):
                command = caption.split()[0]
                logger.info(
                    f"DEBUG: Found {command} command in caption, processing directly"
                )

                # Extract task description from caption (everything after command)
                task_description = (
                    " ".join(caption.split()[1:]) if len(caption.split()) > 1 else ""
                )

                # Add type parameter for /bug and /story
                import re

                if command == "/bug":
                    task_description = re.sub(
                        r"\btype:\s*\w+", "", task_description, flags=re.IGNORECASE
                    ).strip()
                    task_description = f"{task_description} type: Bug".strip()
                elif command == "/story":
                    task_description = re.sub(
                        r"\btype:\s*\w+", "", task_description, flags=re.IGNORECASE
                    ).strip()
                    task_description = f"{task_description} type: Story".strip()

                logger.info(
                    f"DEBUG: Task description from caption: '{task_description}'"
                )

                # Process the task with the caption text
                # Pass only the highest quality photo (last one in the list)
                best_photo = [update.message.photo[-1]] if update.message.photo else []
                await self._process_task(update, task_description, best_photo)
                return

            # If photo doesn't have /task, /bug, or /story command, ignore it (just a regular photo message)
            logger.info("DEBUG: Photo without command - ignoring")
            return

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
            chat = update.effective_chat

            # Parse task parameters using the helper method
            (
                task_description,
                jira_description,
                component_name,
                issue_type,
                sprint_id,
                link_issue,
                project_key,
                should_stop,
            ) = await self._parse_task_parameters(task_description, update)
            if should_stop:
                return

            # Prepare labels for Jira issue
            labels = []

            # Add chat/channel name as label
            if chat:
                if chat.type in ["group", "supergroup", "channel"]:
                    # For groups and channels, use the chat title
                    if chat.title:
                        # Clean label: replace spaces and special chars
                        chat_label = chat.title.replace(" ", "_").replace("-", "_")
                        labels.append(f"tg_chat:{chat_label}")
                elif chat.type == "private":
                    # For private chats, use "private"
                    labels.append("tg_chat:private")

            # Add username as label
            if user:
                if user.username:
                    labels.append(f"tg_user:{user.username}")
                elif user.first_name:
                    # If no username, use first name
                    user_label = user.first_name.replace(" ", "_").replace("-", "_")
                    labels.append(f"tg_user:{user_label}")

            logger.info(f"Adding labels to Jira issue: {labels}")

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

            issue_key, error_message = self.jira_service.create_story(
                summary=task_description,
                description=final_description,
                component_name=component_name,
                issue_type=issue_type,
                attachments=attachment_files,
                sprint_id=sprint_id,
                labels=labels,
                project_key=project_key,
            )

            if error_message:
                # If there's an error message, send it to the user
                await update.message.reply_text(error_message)
                return

            if issue_key:
                issue_url = self.jira_service.get_issue_url(issue_key)

                # Link to another issue if specified
                if link_issue:
                    link_success = self.jira_service.link_issues(
                        inward_issue=issue_key, outward_issue=link_issue
                    )
                    if link_success:
                        logger.info(f"Successfully linked {issue_key} to {link_issue}")
                    else:
                        await update.message.reply_text(
                            f"⚠️ Created task but failed to link to {link_issue}. Please check the issue key."
                        )

                await update.message.reply_text(
                    f"✅ Jira {issue_type.lower()} created successfully!\n\n"
                    f"📋 Task Key: {issue_key}\n"
                    f"🔗 URL: {issue_url}"
                )
                return issue_key
            else:
                await update.message.reply_text(
                    f"❌ Failed to create Jira {issue_type.lower()}. Please check the bot configuration and try again."
                )
                return None

        except Exception as e:
            logger.error(f"Error in _process_task: {e}")
            await update.message.reply_text(
                "❌ An error occurred while creating the Jira story. Please try again later."
            )
            return None

    def setup_handlers(self):
        """Set up command handlers for the bot."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("task", self.task_command))
        self.application.add_handler(CommandHandler("bug", self.bug_command))
        self.application.add_handler(CommandHandler("story", self.story_command))
        self.application.add_handler(CommandHandler("link", self.link_command))
        self.application.add_handler(CommandHandler("desc", self.desc_command))
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
