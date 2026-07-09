"""Shared pytest fixtures and helpers for the jira-bot test suite."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def make_update(
    text: str = "",
    username: str = "tester",
    user_id: int = 1,
    first_name: str = "Test",
    chat_type: str = "private",
    chat_title: str = None,
):
    """Build a lightweight fake telegram Update with an async reply_text mock.

    Only the attributes actually touched by the handlers are populated.
    """
    message = SimpleNamespace(
        text=text,
        caption=None,
        photo=[],
        media_group_id=None,
        reply_text=AsyncMock(),
        reply_photo=AsyncMock(),
        reply_document=AsyncMock(),
    )
    user = SimpleNamespace(
        id=user_id,
        username=username,
        first_name=first_name,
        last_name=None,
    )
    chat = SimpleNamespace(type=chat_type, title=chat_title)
    return SimpleNamespace(
        message=message,
        effective_user=user,
        effective_chat=chat,
    )


@pytest.fixture
def update_factory():
    """Return the make_update helper so tests can build fake updates."""
    return make_update
