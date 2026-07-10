"""Tests for TelegramBot._parse_task_parameters (the parameter-parsing regex)."""

from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.telegram_bot import TelegramBot

# Names for the positional return tuple of _parse_task_parameters, so tests read
# by field and survive future additions to the tuple.
FIELDS = [
    "summary",
    "description",
    "component",
    "issue_type",
    "sprint_id",
    "link",
    "project",
    "assignee",
    "epic",
    "stop",
]


def parsed(result) -> dict:
    assert len(result) == len(FIELDS), f"tuple arity changed: {len(result)}"
    return dict(zip(FIELDS, result))


@pytest.fixture(autouse=True)
def stable_config(monkeypatch):
    monkeypatch.setattr(Config, "JIRA_PROJECT_KEY", "AAI")
    monkeypatch.setattr(Config, "JIRA_COMPONENT_NAME", "org")


@pytest.fixture
def bot():
    b = object.__new__(TelegramBot)
    b.component_service = None
    b.sprint_service = None
    b.assignee_service = None
    b.epic_service = None
    return b


async def test_plain_summary(bot, update_factory):
    upd = update_factory()
    r = parsed(await bot._parse_task_parameters("Fix login bug", upd))
    assert r["summary"] == "Fix login bug"
    assert r["description"] is None
    assert r["component"] == "org"
    assert r["issue_type"] == "Story"
    assert r["sprint_id"] is None
    assert r["link"] is None
    assert r["project"] == "AAI"
    assert r["assignee"] is None
    assert r["stop"] is False


async def test_type_parameter(bot, update_factory):
    upd = update_factory()
    r = parsed(await bot._parse_task_parameters("Fix crash type: Bug", upd))
    assert r["summary"] == "Fix crash"
    assert r["issue_type"] == "Bug"
    assert r["stop"] is False


async def test_description_parameter(bot, update_factory):
    upd = update_factory()
    r = parsed(
        await bot._parse_task_parameters(
            "Add feature desc: Detailed description here", upd
        )
    )
    assert r["summary"] == "Add feature"
    assert r["description"] == "Detailed description here"


async def test_empty_summary_uses_description(bot, update_factory):
    upd = update_factory()
    r = parsed(await bot._parse_task_parameters("desc: Only a description", upd))
    assert r["summary"] == "Only a description"
    assert r["description"] is None


async def test_link_digits_get_project_prefix(bot, update_factory):
    upd = update_factory()
    r = parsed(await bot._parse_task_parameters("Fix bug link: 123", upd))
    assert r["summary"] == "Fix bug"
    assert r["link"] == "AAI-123"
    assert r["project"] == "AAI"


async def test_link_explicit_key_preserved(bot, update_factory):
    upd = update_factory()
    r = parsed(await bot._parse_task_parameters("Fix bug link: SV-99", upd))
    assert r["link"] == "SV-99"


async def test_project_parameter_uppercased(bot, update_factory):
    upd = update_factory()
    r = parsed(await bot._parse_task_parameters("New feature project: sv link: 5", upd))
    assert r["project"] == "SV"
    assert r["link"] == "SV-5"  # link digits use the overridden project key


async def test_newlines_collapsed_in_summary(bot, update_factory):
    upd = update_factory()
    r = parsed(await bot._parse_task_parameters("line one\nline two type: Bug", upd))
    assert r["summary"] == "line one line two"


async def test_component_match_success(bot, update_factory):
    upd = update_factory()
    component_service = MagicMock()
    component_service.find_component.return_value = ("frontend", "")
    r = parsed(
        await bot._parse_task_parameters(
            "Task component: фронт", upd, component_service=component_service
        )
    )
    assert r["summary"] == "Task"
    assert r["component"] == "frontend"
    assert r["stop"] is False
    component_service.find_component.assert_called_once()


async def test_component_ambiguity_stops(bot, update_factory):
    upd = update_factory()
    component_service = MagicMock()
    component_service.find_component.return_value = ("default", "❌ No close match ...")
    r = parsed(
        await bot._parse_task_parameters(
            "Task component: xyz", upd, component_service=component_service
        )
    )
    assert r["stop"] is True
    upd.message.reply_text.assert_awaited_once()


async def test_sprint_match_success(bot, update_factory):
    upd = update_factory()
    sprint_service = MagicMock()
    sprint_service.find_sprint.return_value = (42, None)
    r = parsed(
        await bot._parse_task_parameters(
            "Task sprint: active", upd, sprint_service=sprint_service
        )
    )
    assert r["sprint_id"] == 42
    assert r["stop"] is False


async def test_sprint_error_stops(bot, update_factory):
    upd = update_factory()
    sprint_service = MagicMock()
    sprint_service.find_sprint.return_value = (None, "❌ Multiple active sprints ...")
    r = parsed(
        await bot._parse_task_parameters(
            "Task sprint: q4", upd, sprint_service=sprint_service
        )
    )
    assert r["stop"] is True
    upd.message.reply_text.assert_awaited_once()


async def test_unknown_type_stops(bot, update_factory):
    upd = update_factory()
    r = parsed(await bot._parse_task_parameters("Task type: superepic", upd))
    assert r["stop"] is True
    upd.message.reply_text.assert_awaited_once()


# --------------------------------------------------------------- assignee ---


async def test_assignee_match_success(bot, update_factory):
    upd = update_factory()
    assignee_service = MagicMock()
    assignee_service.find_assignee.return_value = ("aleksei.dolzhenkov", None)
    r = parsed(
        await bot._parse_task_parameters(
            "Login broken assignee: Алексей", upd, assignee_service=assignee_service
        )
    )
    assert r["summary"] == "Login broken"
    assert r["assignee"] == "aleksei.dolzhenkov"
    assert r["stop"] is False
    assignee_service.find_assignee.assert_called_once_with("Алексей", "AAI")


async def test_who_is_alias_for_assignee(bot, update_factory):
    upd = update_factory()
    assignee_service = MagicMock()
    assignee_service.find_assignee.return_value = ("danila.redikultsev", None)
    r = parsed(
        await bot._parse_task_parameters(
            "New report who: редикульцев", upd, assignee_service=assignee_service
        )
    )
    assert r["summary"] == "New report"
    assert r["assignee"] == "danila.redikultsev"
    assignee_service.find_assignee.assert_called_once_with("редикульцев", "AAI")


async def test_assignee_uses_overridden_project(bot, update_factory):
    upd = update_factory()
    assignee_service = MagicMock()
    assignee_service.find_assignee.return_value = ("ivan.petrov", None)
    await bot._parse_task_parameters(
        "Task project: sv assignee: Иван", upd, assignee_service=assignee_service
    )
    assignee_service.find_assignee.assert_called_once_with("Иван", "SV")


async def test_assignee_not_found_stops(bot, update_factory):
    upd = update_factory()
    assignee_service = MagicMock()
    assignee_service.find_assignee.return_value = (None, "❌ No assignee found ...")
    r = parsed(
        await bot._parse_task_parameters(
            "Task assignee: zzz", upd, assignee_service=assignee_service
        )
    )
    assert r["stop"] is True
    upd.message.reply_text.assert_awaited_once()


async def test_assignee_with_other_params_any_order(bot, update_factory):
    upd = update_factory()
    assignee_service = MagicMock()
    assignee_service.find_assignee.return_value = ("aleksei.dolzhenkov", None)
    r = parsed(
        await bot._parse_task_parameters(
            "Fix it assignee: Алексей type: Bug",
            upd,
            assignee_service=assignee_service,
        )
    )
    assert r["summary"] == "Fix it"
    assert r["issue_type"] == "Bug"
    assert r["assignee"] == "aleksei.dolzhenkov"


# ------------------------------------------------------------------- epic ---


async def test_epic_match_success(bot, update_factory):
    upd = update_factory()
    epic_service = MagicMock()
    epic_service.find_epic.return_value = ("AAI-100", None)
    r = parsed(
        await bot._parse_task_parameters(
            "Add filter epic: мобильное приложение", upd, epic_service=epic_service
        )
    )
    assert r["summary"] == "Add filter"
    assert r["epic"] == "AAI-100"
    assert r["stop"] is False
    epic_service.find_epic.assert_called_once_with("мобильное приложение", "AAI")


async def test_epic_uses_overridden_project(bot, update_factory):
    upd = update_factory()
    epic_service = MagicMock()
    epic_service.find_epic.return_value = ("SV-5", None)
    await bot._parse_task_parameters(
        "Task project: sv epic: payments", upd, epic_service=epic_service
    )
    epic_service.find_epic.assert_called_once_with("payments", "SV")


async def test_epic_not_found_stops(bot, update_factory):
    upd = update_factory()
    epic_service = MagicMock()
    epic_service.find_epic.return_value = (None, "❌ No epic found ...")
    r = parsed(
        await bot._parse_task_parameters(
            "Task epic: zzz", upd, epic_service=epic_service
        )
    )
    assert r["stop"] is True
    upd.message.reply_text.assert_awaited_once()


async def test_epic_and_assignee_together(bot, update_factory):
    upd = update_factory()
    assignee_service = MagicMock()
    assignee_service.find_assignee.return_value = ("ivan.petrov", None)
    epic_service = MagicMock()
    epic_service.find_epic.return_value = ("AAI-100", None)
    r = parsed(
        await bot._parse_task_parameters(
            "New report who: Иван epic: AAI-100",
            upd,
            assignee_service=assignee_service,
            epic_service=epic_service,
        )
    )
    assert r["summary"] == "New report"
    assert r["assignee"] == "ivan.petrov"
    assert r["epic"] == "AAI-100"
    assert r["stop"] is False
