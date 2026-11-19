"""The bot token is part of every Telegram API URL; httpx must not log request lines."""

import logging

import main  # noqa: F401  (configures logging on import)


def test_httpx_request_logging_is_silenced():
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert not logging.getLogger("httpcore").isEnabledFor(logging.INFO)
