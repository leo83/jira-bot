"""Tests for the /linkmany command handler."""

from unittest.mock import MagicMock

import pytest

from app import telegram_bot as tb
from app.config import Config
from app.telegram_bot import TelegramBot


@pytest.fixture(autouse=True)
def allow_all(monkeypatch):
    monkeypatch.setattr(
        tb.UserConfig, "is_user_allowed", lambda username, user_id: True
    )
    monkeypatch.setattr(Config, "JIRA_PROJECT_KEY", "AAI")
    monkeypatch.setattr(Config, "GRAFANA_MESSAGE_URL", "https://grafana/msg/")


@pytest.fixture
def mock_jira():
    jira = MagicMock()
    jira.add_comment.return_value = True
    return jira


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.insert_jira_issue_link.return_value = (True, "")
    return db


@pytest.fixture
def bot(mock_jira, mock_db):
    b = object.__new__(TelegramBot)
    b._get_user_jira_service = lambda user_id: mock_jira
    b.database_service = mock_db
    return b


UUID_1 = "550e8400-e29b-41d4-a716-446655440000"
UUID_2 = "123e4567-e89b-12d3-a456-426614174000"


async def test_linkmany_single_key_per_line(bot, mock_jira, mock_db, update_factory):
    text = (
        "/linkmany\n"
        f"message_ref: {UUID_1} jira: AAI-1020\n"
        f"message_ref: {UUID_2} jira: SV-4403"
    )
    upd = update_factory(text=text)

    await bot.linkmany_command(upd, None)

    assert mock_db.insert_jira_issue_link.call_count == 2
    mock_db.insert_jira_issue_link.assert_any_call(UUID_1, "AAI-1020")
    mock_db.insert_jira_issue_link.assert_any_call(UUID_2, "SV-4403")
    assert mock_jira.add_comment.call_count == 2

    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "Linked: 2" in body


async def test_linkmany_multiple_keys_one_line(bot, mock_db, update_factory):
    text = f"/linkmany\nmessage_ref: {UUID_1} jira: AAI-1020,AAI-1021"
    upd = update_factory(text=text)

    await bot.linkmany_command(upd, None)

    assert mock_db.insert_jira_issue_link.call_count == 2
    mock_db.insert_jira_issue_link.assert_any_call(UUID_1, "AAI-1020")
    mock_db.insert_jira_issue_link.assert_any_call(UUID_1, "AAI-1021")


async def test_linkmany_digit_only_key_uses_default_project(bot, mock_db, update_factory):
    text = f"/linkmany\nmessage_ref: {UUID_1} jira: 4403"
    upd = update_factory(text=text)

    await bot.linkmany_command(upd, None)

    mock_db.insert_jira_issue_link.assert_called_once_with(UUID_1, "AAI-4403")


async def test_linkmany_invalid_uuid_reported_but_others_processed(bot, mock_db, update_factory):
    # "deadbeef-...-short" is valid hex/dash but too short to match the UUID shape.
    text = (
        "/linkmany\n"
        "message_ref: deadbeef-dead-beef-dead-beef jira: AAI-1\n"
        f"message_ref: {UUID_1} jira: AAI-2"
    )
    upd = update_factory(text=text)

    await bot.linkmany_command(upd, None)

    mock_db.insert_jira_issue_link.assert_called_once_with(UUID_1, "AAI-2")
    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "Invalid UUID" in body
    assert "Linked: 1, Failed/Skipped: 1" in body


async def test_linkmany_duplicate_reported(bot, mock_db, update_factory):
    mock_db.insert_jira_issue_link.return_value = (False, "duplicate")
    text = f"/linkmany\nmessage_ref: {UUID_1} jira: AAI-1020"
    upd = update_factory(text=text)

    await bot.linkmany_command(upd, None)

    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "already linked" in body


async def test_linkmany_missing_params_shows_usage(bot, mock_db, update_factory):
    upd = update_factory(text="/linkmany")

    await bot.linkmany_command(upd, None)

    mock_db.insert_jira_issue_link.assert_not_called()
    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "Usage" in body


async def test_linkmany_requires_registration(mock_db, update_factory):
    b = object.__new__(TelegramBot)
    b._get_user_jira_service = lambda user_id: None
    b.database_service = mock_db
    upd = update_factory(text=f"/linkmany\nmessage_ref: {UUID_1} jira: AAI-1")

    await b.linkmany_command(upd, None)

    mock_db.insert_jira_issue_link.assert_not_called()
    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "не зарегистрированы" in body


async def test_linkmany_denied_for_unauthorized(mock_db, update_factory, monkeypatch):
    monkeypatch.setattr(
        tb.UserConfig, "is_user_allowed", lambda username, user_id: False
    )
    b = object.__new__(TelegramBot)
    b._get_user_jira_service = lambda user_id: MagicMock()
    b.database_service = mock_db
    upd = update_factory(text=f"/linkmany\nmessage_ref: {UUID_1} jira: AAI-1")

    await b.linkmany_command(upd, None)

    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "Access denied" in body
    mock_db.insert_jira_issue_link.assert_not_called()
