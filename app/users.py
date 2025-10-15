"""
User authorization configuration for the Jira Telegram bot.
"""

import os
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


class UserConfig:
    """Configuration class for user authorization."""

    # Get allowed users from environment variable
    # Format: "username1,username2,user_id1,user_id2"
    ALLOWED_USERS_STR = os.getenv("ALLOWED_USERS", "")

    @classmethod
    def get_allowed_users(cls) -> List[str]:
        """
        Get list of allowed users.

        Returns:
            List[str]: List of allowed usernames and user IDs
        """
        if not cls.ALLOWED_USERS_STR:
            return []

        # Split by comma and strip whitespace
        users = [user.strip() for user in cls.ALLOWED_USERS_STR.split(",")]
        # Filter out empty strings
        return [user for user in users if user]

    @classmethod
    def is_user_allowed(cls, username: Optional[str], user_id: Optional[int]) -> bool:
        """
        Check if a user is allowed to create tasks.

        Args:
            username (Optional[str]): Telegram username
            user_id (Optional[int]): Telegram user ID

        Returns:
            bool: True if user is allowed, False otherwise
        """
        allowed_users = cls.get_allowed_users()

        # If no users configured, allow everyone (backward compatibility)
        if not allowed_users:
            return True

        # Check by username
        if username and username in allowed_users:
            return True

        # Check by user ID
        if user_id and str(user_id) in allowed_users:
            return True

        return False

    @classmethod
    def get_allowed_users_display(cls) -> str:
        """
        Get a formatted string of allowed users for display.

        Returns:
            str: Formatted list of allowed users
        """
        users = cls.get_allowed_users()
        if not users:
            return "No restrictions (all users allowed)"
        return ", ".join(users)
