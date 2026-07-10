"""Tests for EpicService (fuzzy-first epic resolution + LLM fallback)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.epic_service import EpicService

# (key, summary/name)
EPICS = [
    ("AAI-100", "Мобильное приложение"),
    ("AAI-200", "Payments Q4"),
    ("AAI-300", "Онбординг пользователей"),
]


def make_jira_service(epics):
    issues = [
        SimpleNamespace(key=k, fields=SimpleNamespace(summary=name))
        for k, name in epics
    ]
    jira = MagicMock()
    jira.search_issues.return_value = issues
    return SimpleNamespace(jira=jira, project_key="AAI")


def service(epics=EPICS, llm=None):
    return EpicService(make_jira_service(epics), llm)


# ------------------------------------------------------------- exact match ---


def test_exact_key():
    key, msg = service().find_epic("AAI-200", "AAI")
    assert key == "AAI-200"
    assert msg is None


def test_bare_number_key():
    key, msg = service().find_epic("300", "AAI")
    assert key == "AAI-300"
    assert msg is None


def test_exact_name_case_insensitive():
    key, msg = service().find_epic("payments q4", "AAI")
    assert key == "AAI-200"
    assert msg is None


# ------------------------------------------------------------------ fuzzy ---


def test_fuzzy_partial_russian_name():
    key, msg = service().find_epic("мобильное приложение", "AAI")
    assert key == "AAI-100"
    assert msg is None


def test_fuzzy_single_word():
    key, msg = service().find_epic("онбординг", "AAI")
    assert key == "AAI-300"
    assert msg is None


def test_ambiguous_asks_user():
    epics = [
        ("AAI-1", "Мобильное приложение iOS"),
        ("AAI-2", "Мобильное приложение Android"),
    ]
    key, msg = service(epics).find_epic("мобильное приложение", "AAI")
    assert key is None
    assert "Multiple epics match" in msg
    assert "AAI-1" in msg and "AAI-2" in msg


def test_not_found_without_llm():
    key, msg = service().find_epic("qwertyzzz", "AAI")
    assert key is None
    assert "No epic found" in msg


# -------------------------------------------------------------- LLM booster ---


def test_llm_fallback_when_fuzzy_misses():
    llm = MagicMock()
    llm.is_configured.return_value = True
    llm.pick_option.return_value = "AAI-200"
    key, msg = service(llm=llm).find_epic("qwertyzzz", "AAI")
    assert key == "AAI-200"
    assert msg is None
    llm.pick_option.assert_called_once()


def test_llm_not_consulted_when_fuzzy_succeeds():
    llm = MagicMock()
    llm.is_configured.return_value = True
    service(llm=llm).find_epic("онбординг", "AAI")
    llm.pick_option.assert_not_called()


def test_llm_skipped_when_not_configured():
    llm = MagicMock()
    llm.is_configured.return_value = False
    key, msg = service(llm=llm).find_epic("qwertyzzz", "AAI")
    assert key is None
    llm.pick_option.assert_not_called()


# ------------------------------------------------------- edge cases + cache ---


def test_empty_query():
    key, msg = service().find_epic("  ", "AAI")
    assert key is None
    assert msg


def test_no_epics():
    key, msg = service(epics=[]).find_epic("anything", "AAI")
    assert key is None
    assert "No epics found" in msg


def test_epics_are_cached_per_project():
    svc = service()
    svc.find_epic("онбординг", "AAI")
    svc.find_epic("payments", "AAI")
    assert svc.jira_service.jira.search_issues.call_count == 1


def test_search_jql_targets_epics():
    svc = service()
    svc.find_epic("онбординг", "AAI")
    jql = svc.jira_service.jira.search_issues.call_args[0][0]
    assert "issuetype = Epic" in jql
    assert 'project = "AAI"' in jql
