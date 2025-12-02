"""Database service for PostgreSQL operations."""
import logging
import psycopg2
from psycopg2 import sql, extras
from typing import Optional
from app.config import Config

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for database operations."""

    def __init__(self):
        """Initialize database service."""
        self.connection = None
        self._connect()

    def _connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                database=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD
            )
            logger.info("Successfully connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def _ensure_connection(self):
        """Ensure database connection is active."""
        if self.connection is None or self.connection.closed:
            logger.info("Reconnecting to database...")
            self._connect()

    def insert_jira_issue_link(self, message_ref: str, jira_key: str) -> bool:
        """
        Insert a link between a message reference and a Jira issue.

        Args:
            message_ref: UUID of the message reference
            jira_key: Jira issue key (e.g., AAI-1020)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self._ensure_connection()

            with self.connection.cursor() as cursor:
                query = sql.SQL(
                    "INSERT INTO jira_issues (message_ref, jira_key) VALUES (%s, %s)"
                )
                cursor.execute(query, (message_ref, jira_key))
                self.connection.commit()

            logger.info(f"Successfully inserted link: message_ref={message_ref}, jira_key={jira_key}")
            return True

        except psycopg2.IntegrityError as e:
            logger.error(f"Integrity error inserting jira_issue link: {e}")
            self.connection.rollback()
            return False
        except Exception as e:
            logger.error(f"Error inserting jira_issue link: {e}")
            if self.connection:
                self.connection.rollback()
            return False

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

            with self.connection.cursor() as cursor:
                query = sql.SQL("SELECT jira_key FROM jira_issues WHERE message_ref = %s")
                cursor.execute(query, (message_ref,))
                results = cursor.fetchall()

            return [row[0] for row in results]

        except Exception as e:
            logger.error(f"Error fetching jira keys: {e}")
            return []

    def close(self):
        """Close database connection."""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.info("Database connection closed")

    def __del__(self):
        """Cleanup database connection."""
        self.close()

