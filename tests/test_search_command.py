"""Tests for the /search command handler."""

from unittest.mock import MagicMock

import pytest

from app import telegram_bot as tb
from app.config import Config
from app.telegram_bot import TelegramBot


@pytest.fixture(autouse=True)
def allow_all(monkeypatch):
    # Make authorization + default project deterministic regardless of the .env
    monkeypatch.setattr(
        tb.UserConfig, "is_user_allowed", lambda username, user_id: True
    )
    monkeypatch.setattr(Config, "JIRA_PROJECT_KEY", "AAI")


@pytest.fixture
def mock_jira():
    jira = MagicMock()
    jira.get_issue_url.side_effect = lambda key: f"https://jira/browse/{key}"
    return jira


@pytest.fixture
def bot(mock_jira):
    b = object.__new__(TelegramBot)
    b._get_user_jira_service = lambda user_id: mock_jira
    return b


async def test_search_happy_path(bot, mock_jira, update_factory):
    mock_jira.search_issues.return_value = (
        [
            {
                "key": "AAI-1",
                "summary": "Login timeout",
                "status": "Open",
                "issue_type": "Bug",
            },
            {
                "key": "AAI-2",
                "summary": "Slow dashboard",
                "status": "Done",
                "issue_type": "Story",
            },
        ],
        None,
    )
    upd = update_factory(text="/search login timeout")

    await bot.search_command(upd, None)

    # Defaults to the configured project (AAI) when no project: is given
    mock_jira.search_issues.assert_called_once_with("login timeout", project_key="AAI")
    # Last reply contains the formatted results
    final = upd.message.reply_text.call_args_list[-1]
    body = final.args[0]
    assert "AAI-1" in body and "AAI-2" in body
    assert "Login timeout" in body
    assert final.kwargs.get("parse_mode") == "HTML"


async def test_search_with_project_param(bot, mock_jira, update_factory):
    mock_jira.search_issues.return_value = ([], None)
    upd = update_factory(text="/search dashboard project: sv")

    await bot.search_command(upd, None)

    mock_jira.search_issues.assert_called_once_with("dashboard", project_key="SV")


async def test_search_all_projects(bot, mock_jira, update_factory):
    mock_jira.search_issues.return_value = ([], None)
    upd = update_factory(text="/search dashboard project: all")

    await bot.search_command(upd, None)

    # "project: all" clears the project filter -> search everywhere
    mock_jira.search_issues.assert_called_once_with("dashboard", project_key=None)


async def test_search_no_results(bot, mock_jira, update_factory):
    mock_jira.search_issues.return_value = ([], None)
    upd = update_factory(text="/search nothingmatches")

    await bot.search_command(upd, None)

    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "No issues found" in body


async def test_search_error_message_relayed(bot, mock_jira, update_factory):
    mock_jira.search_issues.return_value = (None, "❌ search failed")
    upd = update_factory(text="/search boom")

    await bot.search_command(upd, None)

    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "search failed" in body


async def test_search_missing_query_shows_usage(bot, mock_jira, update_factory):
    upd = update_factory(text="/search")
    await bot.search_command(upd, None)
    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "provide search words" in body
    mock_jira.search_issues.assert_not_called()


async def test_search_only_project_no_words(bot, mock_jira, update_factory):
    upd = update_factory(text="/search project: SV")
    await bot.search_command(upd, None)
    mock_jira.search_issues.assert_not_called()
    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "search words" in body


async def test_search_requires_registration(mock_jira, update_factory):
    b = object.__new__(TelegramBot)
    b._get_user_jira_service = lambda user_id: None
    upd = update_factory(text="/search anything")

    await b.search_command(upd, None)

    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "не зарегистрированы" in body


async def test_search_denied_for_unauthorized(mock_jira, update_factory, monkeypatch):
    monkeypatch.setattr(
        tb.UserConfig, "is_user_allowed", lambda username, user_id: False
    )
    b = object.__new__(TelegramBot)
    b._get_user_jira_service = lambda user_id: mock_jira
    upd = update_factory(text="/search anything")

    await b.search_command(upd, None)

    body = upd.message.reply_text.call_args_list[-1].args[0]
    assert "Access denied" in body
    mock_jira.search_issues.assert_not_called()
