"""Tests for TelegramBot._parse_task_parameters (the parameter-parsing regex)."""

from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.telegram_bot import TelegramBot


@pytest.fixture(autouse=True)
def stable_config(monkeypatch):
    monkeypatch.setattr(Config, "JIRA_PROJECT_KEY", "AAI")
    monkeypatch.setattr(Config, "JIRA_COMPONENT_NAME", "org")


@pytest.fixture
def bot():
    b = object.__new__(TelegramBot)
    b.component_service = None
    b.sprint_service = None
    return b


async def test_plain_summary(bot, update_factory):
    upd = update_factory()
    (summary, desc, component, itype, sprint_id, link, project, stop) = (
        await bot._parse_task_parameters("Fix login bug", upd)
    )
    assert summary == "Fix login bug"
    assert desc is None
    assert component == "org"
    assert itype == "Story"
    assert sprint_id is None
    assert link is None
    assert project == "AAI"
    assert stop is False


async def test_type_parameter(bot, update_factory):
    upd = update_factory()
    result = await bot._parse_task_parameters("Fix crash type: Bug", upd)
    summary, _, _, itype, _, _, _, stop = result
    assert summary == "Fix crash"
    assert itype == "Bug"
    assert stop is False


async def test_description_parameter(bot, update_factory):
    upd = update_factory()
    result = await bot._parse_task_parameters(
        "Add feature desc: Detailed description here", upd
    )
    summary, desc, *_ = result
    assert summary == "Add feature"
    assert desc == "Detailed description here"


async def test_empty_summary_uses_description(bot, update_factory):
    upd = update_factory()
    result = await bot._parse_task_parameters("desc: Only a description", upd)
    summary, desc, *_ = result
    assert summary == "Only a description"
    assert desc is None


async def test_link_digits_get_project_prefix(bot, update_factory):
    upd = update_factory()
    result = await bot._parse_task_parameters("Fix bug link: 123", upd)
    summary, _, _, _, _, link, project, _ = result
    assert summary == "Fix bug"
    assert link == "AAI-123"
    assert project == "AAI"


async def test_link_explicit_key_preserved(bot, update_factory):
    upd = update_factory()
    result = await bot._parse_task_parameters("Fix bug link: SV-99", upd)
    _, _, _, _, _, link, _, _ = result
    assert link == "SV-99"


async def test_project_parameter_uppercased(bot, update_factory):
    upd = update_factory()
    result = await bot._parse_task_parameters("New feature project: sv link: 5", upd)
    summary, _, _, _, _, link, project, _ = result
    assert project == "SV"
    assert link == "SV-5"  # link digits use the overridden project key


async def test_newlines_collapsed_in_summary(bot, update_factory):
    upd = update_factory()
    result = await bot._parse_task_parameters("line one\nline two type: Bug", upd)
    summary, *_ = result
    assert summary == "line one line two"


async def test_component_match_success(bot, update_factory):
    upd = update_factory()
    component_service = MagicMock()
    component_service.find_component.return_value = ("frontend", "")
    result = await bot._parse_task_parameters(
        "Task component: фронт", upd, component_service=component_service
    )
    summary, _, component, _, _, _, _, stop = result
    assert summary == "Task"
    assert component == "frontend"
    assert stop is False
    component_service.find_component.assert_called_once()


async def test_component_ambiguity_stops(bot, update_factory):
    upd = update_factory()
    component_service = MagicMock()
    component_service.find_component.return_value = ("default", "❌ No close match ...")
    result = await bot._parse_task_parameters(
        "Task component: xyz", upd, component_service=component_service
    )
    assert result[-1] is True  # should_stop
    upd.message.reply_text.assert_awaited_once()


async def test_sprint_match_success(bot, update_factory):
    upd = update_factory()
    sprint_service = MagicMock()
    sprint_service.find_sprint.return_value = (42, None)
    result = await bot._parse_task_parameters(
        "Task sprint: active", upd, sprint_service=sprint_service
    )
    _, _, _, _, sprint_id, _, _, stop = result
    assert sprint_id == 42
    assert stop is False


async def test_sprint_error_stops(bot, update_factory):
    upd = update_factory()
    sprint_service = MagicMock()
    sprint_service.find_sprint.return_value = (None, "❌ Multiple active sprints ...")
    result = await bot._parse_task_parameters(
        "Task sprint: q4", upd, sprint_service=sprint_service
    )
    assert result[-1] is True
    upd.message.reply_text.assert_awaited_once()


async def test_unknown_type_stops(bot, update_factory):
    upd = update_factory()
    result = await bot._parse_task_parameters("Task type: superepic", upd)
    assert result[-1] is True
    upd.message.reply_text.assert_awaited_once()
