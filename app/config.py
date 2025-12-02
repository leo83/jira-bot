import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration class for the Jira Telegram bot."""

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    # Jira Configuration
    JIRA_URL = os.getenv("JIRA_URL", "https://jira.example.com")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

    # Project Configuration
    JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "PROJ")
    JIRA_COMPONENT_NAME = os.getenv("JIRA_COMPONENT_NAME", "default")

    # Database Configuration
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "jira_bot")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")

    @classmethod
    def validate(cls):
        """Validate that all required configuration is present."""
        required_vars = ["TELEGRAM_BOT_TOKEN", "JIRA_USERNAME", "JIRA_API_TOKEN", "DB_USER", "DB_PASSWORD"]

        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        return True
