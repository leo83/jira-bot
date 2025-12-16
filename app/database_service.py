"""Database service for ClickHouse operations."""

import logging
from typing import Optional

from clickhouse_driver import Client

from app.config import Config

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for ClickHouse database operations."""

    def __init__(self):
        """Initialize database service."""
        self.client = None
        self._connect()

    def _connect(self):
        """Establish ClickHouse connection."""
        try:
            self.client = Client(
                host=Config.CH_HOST,
                port=int(Config.CH_PORT),
                user=Config.CH_USER,
                password=Config.CH_PASSWORD,
                database=Config.CH_DATABASE,
            )
            # Test connection
            self.client.execute("SELECT 1")
            logger.info("Successfully connected to ClickHouse database")
        except Exception as e:
            logger.error(f"Failed to connect to ClickHouse: {e}")
            raise

    def _ensure_connection(self):
        """Ensure ClickHouse connection is active."""
        try:
            self.client.execute("SELECT 1")
        except Exception:
            logger.info("Reconnecting to ClickHouse...")
            self._connect()

    def link_exists(self, message_ref: str, jira_key: str) -> bool:
        """
        Check if a link between message_ref and jira_key already exists.

        Args:
            message_ref: UUID of the message reference
            jira_key: Jira issue key (e.g., AAI-1020)

        Returns:
            bool: True if link exists, False otherwise
        """
        try:
            self._ensure_connection()

            query = """
                SELECT count() FROM jira_issues
                WHERE message_ref = %(message_ref)s AND jira_key = %(jira_key)s
            """
            result = self.client.execute(
                query, {"message_ref": message_ref, "jira_key": jira_key}
            )

            return result[0][0] > 0

        except Exception as e:
            logger.error(f"Error checking link existence: {e}")
            return False

    def insert_jira_issue_link(
        self, message_ref: str, jira_key: str
    ) -> tuple[bool, str]:
        """
        Insert a link between a message reference and a Jira issue.

        Args:
            message_ref: UUID of the message reference
            jira_key: Jira issue key (e.g., AAI-1020)

        Returns:
            tuple[bool, str]: (success, error_message) - success is True if inserted,
                             error_message contains reason if failed
        """
        try:
            self._ensure_connection()

            # Check for duplicate
            if self.link_exists(message_ref, jira_key):
                logger.warning(
                    f"Duplicate link rejected: message_ref={message_ref}, jira_key={jira_key}"
                )
                return False, "duplicate"

            query = """
                INSERT INTO jira_issues (message_ref, jira_key, created_at)
                VALUES (%(message_ref)s, %(jira_key)s, now())
            """

            self.client.execute(
                query, {"message_ref": message_ref, "jira_key": jira_key}
            )

            logger.info(
                f"Successfully inserted link: message_ref={message_ref}, jira_key={jira_key}"
            )
            return True, ""

        except Exception as e:
            logger.error(f"Error inserting jira_issue link: {e}")
            return False, "error"

    def delete_jira_issue_link(
        self, message_ref: str, jira_key: str
    ) -> tuple[bool, str]:
        """
        Delete a link between a message reference and a Jira issue.

        Args:
            message_ref: UUID of the message reference
            jira_key: Jira issue key (e.g., AAI-1020)

        Returns:
            tuple[bool, str]: (success, error_message) - success is True if deleted,
                             error_message contains reason if failed
        """
        try:
            self._ensure_connection()

            # Check if link exists
            if not self.link_exists(message_ref, jira_key):
                logger.warning(
                    f"Link not found for deletion: message_ref={message_ref}, jira_key={jira_key}"
                )
                return False, "not_found"

            query = """
                ALTER TABLE jira_issues DELETE
                WHERE message_ref = %(message_ref)s AND jira_key = %(jira_key)s
            """

            self.client.execute(
                query, {"message_ref": message_ref, "jira_key": jira_key}
            )

            logger.info(
                f"Successfully deleted link: message_ref={message_ref}, jira_key={jira_key}"
            )
            return True, ""

        except Exception as e:
            logger.error(f"Error deleting jira_issue link: {e}")
            return False, "error"

    def get_jira_keys_by_message_ref(self, message_ref: str) -> list[str]:
        """
        Get all Jira keys linked to a message reference.

        Args:
            message_ref: UUID of the message reference

        Returns:
            list[str]: List of Jira keys
        """
        try:
            self._ensure_connection()

            query = (
                "SELECT jira_key FROM jira_issues WHERE message_ref = %(message_ref)s"
            )
            results = self.client.execute(query, {"message_ref": message_ref})

            return [row[0] for row in results]

        except Exception as e:
            logger.error(f"Error fetching jira keys: {e}")
            return []

    # ==================== User Token Methods ====================

    def save_user_token(
        self, telegram_id: int, encrypted_token: str, username: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Save or update an encrypted Jira token for a Telegram user.

        Args:
            telegram_id: Telegram user ID
            encrypted_token: Fernet-encrypted Jira API token
            username: Optional Telegram username

        Returns:
            tuple[bool, str]: (success, error_message)
        """
        try:
            self._ensure_connection()

            # Insert new token (ReplacingMergeTree will handle updates)
            query = """
                INSERT INTO user_tokens (telegram_id, jira_token_encrypted, telegram_username, created_at, updated_at)
                VALUES (%(telegram_id)s, %(token)s, %(username)s, now(), now())
            """

            self.client.execute(
                query,
                {
                    "telegram_id": telegram_id,
                    "token": encrypted_token,
                    "username": username,
                },
            )

            logger.info(f"Successfully saved token for telegram_id={telegram_id}")
            return True, ""

        except Exception as e:
            logger.error(f"Error saving user token: {e}")
            return False, "error"

    def get_user_token(self, telegram_id: int) -> Optional[str]:
        """
        Get the encrypted Jira token for a Telegram user.

        Args:
            telegram_id: Telegram user ID

        Returns:
            The encrypted token string, or None if not found
        """
        try:
            self._ensure_connection()

            # Use FINAL to get the latest version from ReplacingMergeTree
            query = """
                SELECT jira_token_encrypted FROM user_tokens FINAL
                WHERE telegram_id = %(telegram_id)s
            """
            result = self.client.execute(query, {"telegram_id": telegram_id})

            if result:
                return result[0][0]
            return None

        except Exception as e:
            logger.error(f"Error getting user token: {e}")
            return None

    def delete_user_token(self, telegram_id: int) -> tuple[bool, str]:
        """
        Delete the Jira token for a Telegram user.

        Args:
            telegram_id: Telegram user ID

        Returns:
            tuple[bool, str]: (success, error_message)
        """
        try:
            self._ensure_connection()

            # Check if token exists
            existing = self.get_user_token(telegram_id)
            if not existing:
                logger.warning(f"Token not found for deletion: telegram_id={telegram_id}")
                return False, "not_found"

            query = """
                ALTER TABLE user_tokens DELETE
                WHERE telegram_id = %(telegram_id)s
            """

            self.client.execute(query, {"telegram_id": telegram_id})

            logger.info(f"Successfully deleted token for telegram_id={telegram_id}")
            return True, ""

        except Exception as e:
            logger.error(f"Error deleting user token: {e}")
            return False, "error"

    def user_is_registered(self, telegram_id: int) -> bool:
        """
        Check if a user has a registered Jira token.

        Args:
            telegram_id: Telegram user ID

        Returns:
            bool: True if user has a token, False otherwise
        """
        return self.get_user_token(telegram_id) is not None

    def close(self):
        """Close ClickHouse connection."""
        if self.client:
            self.client.disconnect()
            logger.info("ClickHouse connection closed")

    def __del__(self):
        """Cleanup ClickHouse connection."""
        self.close()
