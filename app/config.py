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

    # ClickHouse Configuration
    CH_HOST = os.getenv("CH_HOST", "localhost")
    CH_PORT = os.getenv("CH_PORT", "9000")
    CH_DATABASE = os.getenv("CH_DATABASE", "default")
    CH_USER = os.getenv("CH_USER")
    CH_PASSWORD = os.getenv("CH_PASSWORD")

    # Grafana Configuration (for message reference links)
    GRAFANA_MESSAGE_URL = os.getenv(
        "GRAFANA_MESSAGE_URL",
        "http://grafana-ai.aeroclub.int/d/fenfa2ht8b668a/message-events-details?var-message_ref=",
    )

    # Token Encryption Configuration
    # Key must be 32 url-safe base64-encoded bytes (use Fernet.generate_key() to create one)
    TOKEN_ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")

    @classmethod
    def validate(cls):
        """Validate that all required configuration is present."""
        required_vars = [
            "TELEGRAM_BOT_TOKEN",
            "CH_USER",
            "CH_PASSWORD",
            "TOKEN_ENCRYPTION_KEY",
        ]

        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        return True
