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

    def close(self):
        """Close ClickHouse connection."""
        if self.client:
            self.client.disconnect()
            logger.info("ClickHouse connection closed")

    def __del__(self):
        """Cleanup ClickHouse connection."""
        self.close()
