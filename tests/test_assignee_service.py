"""Tests for AssigneeService (fuzzy-first resolution + LLM fallback)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.assignee_service import AssigneeService

# (username, displayName, email)
ROSTER = [
    ("aleksei.dolzhenkov", "Алексей Долженков", "aleksei.dolzhenkov@aeroclub.ru"),
    ("danila.redikultsev", "Данила Редикульцев", "danila.redikultsev@aeroclub.ru"),
    ("ivan.petrov", "Иван Петров", "ivan.petrov@aeroclub.ru"),
]


def make_jira_service(roster):
    users = [
        SimpleNamespace(name=n, displayName=d, emailAddress=e) for n, d, e in roster
    ]
    jira = MagicMock()
    jira.search_assignable_users_for_projects.return_value = users
    return SimpleNamespace(jira=jira, project_key="AAI")


def service(roster=ROSTER, llm=None):
    return AssigneeService(make_jira_service(roster), llm)


# ------------------------------------------------------------ exact match ---


def test_exact_username():
    name, msg = service().find_assignee("aleksei.dolzhenkov", "AAI")
    assert name == "aleksei.dolzhenkov"
    assert msg is None


def test_exact_email():
    name, msg = service().find_assignee("ivan.petrov@aeroclub.ru", "AAI")
    assert name == "ivan.petrov"
    assert msg is None


def test_exact_display_name_case_insensitive():
    name, msg = service().find_assignee("алексей долженков", "AAI")
    assert name == "aleksei.dolzhenkov"
    assert msg is None


# ------------------------------------------------------------------ fuzzy ---


def test_fuzzy_first_name():
    name, msg = service().find_assignee("Алексей", "AAI")
    assert name == "aleksei.dolzhenkov"
    assert msg is None


def test_fuzzy_surname():
    name, msg = service().find_assignee("Долженков", "AAI")
    assert name == "aleksei.dolzhenkov"
    assert msg is None


def test_ambiguous_first_name_asks_user():
    roster = ROSTER + [
        ("aleksei.smirnov", "Алексей Смирнов", "aleksei.smirnov@aeroclub.ru")
    ]
    name, msg = service(roster).find_assignee("Алексей", "AAI")
    assert name is None
    assert "Multiple users match" in msg
    assert "aleksei.dolzhenkov" in msg and "aleksei.smirnov" in msg


def test_not_found_without_llm():
    name, msg = service().find_assignee("qwertyzzz", "AAI")
    assert name is None
    assert "No assignee found" in msg


# -------------------------------------------------------------- LLM booster ---


def test_llm_fallback_when_fuzzy_misses():
    llm = MagicMock()
    llm.is_configured.return_value = True
    llm.pick_username.return_value = "danila.redikultsev"
    name, msg = service(llm=llm).find_assignee("qwertyzzz", "AAI")
    assert name == "danila.redikultsev"
    assert msg is None
    llm.pick_username.assert_called_once()


def test_llm_returns_none_falls_through_to_not_found():
    llm = MagicMock()
    llm.is_configured.return_value = True
    llm.pick_username.return_value = None
    name, msg = service(llm=llm).find_assignee("qwertyzzz", "AAI")
    assert name is None
    assert "No assignee found" in msg


def test_llm_not_consulted_when_fuzzy_succeeds():
    llm = MagicMock()
    llm.is_configured.return_value = True
    service(llm=llm).find_assignee("Алексей", "AAI")
    llm.pick_username.assert_not_called()


def test_llm_skipped_when_not_configured():
    llm = MagicMock()
    llm.is_configured.return_value = False
    name, msg = service(llm=llm).find_assignee("qwertyzzz", "AAI")
    assert name is None
    llm.pick_username.assert_not_called()


# ------------------------------------------------------- edge cases + cache ---


def test_empty_query():
    name, msg = service().find_assignee("   ", "AAI")
    assert name is None
    assert msg


def test_no_assignable_users():
    svc = service(roster=[])
    name, msg = svc.find_assignee("Алексей", "AAI")
    assert name is None
    assert "Could not fetch assignable users" in msg


def test_users_are_cached_per_project():
    svc = service()
    svc.find_assignee("Алексей", "AAI")
    svc.find_assignee("Иван", "AAI")
    # search called only once thanks to per-project cache
    assert svc.jira_service.jira.search_assignable_users_for_projects.call_count == 1
