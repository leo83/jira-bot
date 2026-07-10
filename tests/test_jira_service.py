"""Tests for JiraService, focused on search, JQL escaping, and key handling."""

from unittest.mock import MagicMock, patch

import pytest
from jira.exceptions import JIRAError

from app.config import Config
from app.jira_service import JiraService


@pytest.fixture
def jira_service():
    """A JiraService with the underlying JIRA client mocked out (no network)."""
    with patch("app.jira_service.JIRA") as mock_jira_cls:
        svc = JiraService.with_token("dummy-token")
        # svc.jira is the instance returned by JIRA(...)
        svc.jira = mock_jira_cls.return_value
        yield svc


def _make_issue(key, summary, status, issue_type):
    issue = MagicMock()
    issue.key = key
    issue.fields.summary = summary
    issue.fields.status.name = status
    issue.fields.issuetype.name = issue_type
    return issue


# ---------------------------------------------------------------- escaping ---


def test_escape_backslash_then_quote():
    assert JiraService._escape_jql_text('a"b') == 'a\\"b'
    assert JiraService._escape_jql_text("a\\b") == "a\\\\b"
    # Order matters: backslash escaped first, then quote
    assert JiraService._escape_jql_text('a\\"b') == 'a\\\\\\"b'


# ------------------------------------------------------------------ search ---


def test_search_builds_jql_without_project(jira_service):
    jira_service.jira.search_issues.return_value = [
        _make_issue("AAI-1", "Login timeout", "Open", "Bug"),
    ]

    results, error = jira_service.search_issues("login timeout")

    assert error is None
    assert results == [
        {
            "key": "AAI-1",
            "summary": "Login timeout",
            "status": "Open",
            "issue_type": "Bug",
        }
    ]

    jql = jira_service.jira.search_issues.call_args[0][0]
    # Each word matched by prefix wildcard against summary OR description...
    assert 'summary ~ "login*"' in jql
    assert 'description ~ "login*"' in jql
    assert 'summary ~ "timeout*"' in jql
    assert 'description ~ "timeout*"' in jql
    # ...and both words required (AND), in any order.
    assert ") AND (" in jql
    assert "ORDER BY updated DESC" in jql
    assert "project =" not in jql


def test_search_is_case_insensitive(jira_service):
    jira_service.jira.search_issues.return_value = []
    jira_service.search_issues("LogIn TimeOut")
    jql = jira_service.jira.search_issues.call_args[0][0]
    # Words are lowercased so wildcard queries match the lowercased index.
    assert 'summary ~ "login*"' in jql
    assert 'summary ~ "timeout*"' in jql
    assert "LogIn" not in jql
    assert "TimeOut" not in jql


def test_search_single_word_has_no_and(jira_service):
    jira_service.jira.search_issues.return_value = []
    jira_service.search_issues("dashboard")
    jql = jira_service.jira.search_issues.call_args[0][0]
    assert 'summary ~ "dashboard*"' in jql
    assert ") AND (" not in jql


def test_search_builds_jql_with_project(jira_service):
    jira_service.jira.search_issues.return_value = []

    results, error = jira_service.search_issues("dashboard", project_key="SV")

    assert error is None
    assert results == []
    jql = jira_service.jira.search_issues.call_args[0][0]
    assert 'project = "SV" AND' in jql
    assert 'summary ~ "dashboard*"' in jql


def test_search_passes_max_results(jira_service):
    jira_service.jira.search_issues.return_value = []
    jira_service.search_issues("x", max_results=5)
    kwargs = jira_service.jira.search_issues.call_args[1]
    assert kwargs["maxResults"] == 5


def test_search_escapes_quotes_in_query(jira_service):
    jira_service.jira.search_issues.return_value = []
    jira_service.search_issues('say "hi"')
    jql = jira_service.jira.search_issues.call_args[0][0]
    # Each word is escaped and wildcarded independently.
    assert 'summary ~ "say*"' in jql
    assert 'summary ~ "\\"hi\\"*"' in jql


def test_search_handles_jira_error(jira_service):
    jira_service.jira.search_issues.side_effect = JIRAError(
        status_code=400, text="bad jql"
    )
    results, error = jira_service.search_issues("C++")
    assert results is None
    assert error is not None
    assert "C++" in error


def test_search_handles_unexpected_error(jira_service):
    jira_service.jira.search_issues.side_effect = RuntimeError("boom")
    results, error = jira_service.search_issues("anything")
    assert results is None
    assert error is not None


# ------------------------------------------------------------- misc helpers ---


def test_get_issue_url(jira_service, monkeypatch):
    monkeypatch.setattr(Config, "JIRA_URL", "https://jira.example.com")
    assert (
        jira_service.get_issue_url("AAI-123")
        == "https://jira.example.com/browse/AAI-123"
    )


def test_link_issues_normalizes_digit_keys(jira_service):
    jira_service.project_key = "AAI"
    ok = jira_service.link_issues(inward_issue="100", outward_issue="200")
    assert ok is True
    _, kwargs = jira_service.jira.create_issue_link.call_args
    assert kwargs["inwardIssue"] == "AAI-100"
    assert kwargs["outwardIssue"] == "AAI-200"


def test_link_issues_returns_false_on_error(jira_service):
    jira_service.jira.create_issue_link.side_effect = RuntimeError("nope")
    assert jira_service.link_issues("A-1", "A-2") is False


def test_get_issue_returns_dict(jira_service):
    jira_service.project_key = "AAI"
    issue = MagicMock()
    issue.key = "AAI-5"
    issue.fields.summary = "Summary"
    issue.fields.description = "Desc"
    issue.fields.status.name = "Open"
    issue.fields.issuetype.name = "Story"
    issue.fields.assignee.displayName = "Alice"
    issue.fields.reporter.displayName = "Bob"
    issue.fields.created = "2026-01-01"
    issue.fields.updated = "2026-01-02"
    issue.fields.attachment = []
    jira_service.jira.issue.return_value = issue

    data = jira_service.get_issue("5")
    assert data["key"] == "AAI-5"
    assert data["summary"] == "Summary"
    assert data["assignee"] == "Alice"
    assert data["attachments"] == []
    # Digit-only key should be prefixed with the project key before lookup
    assert jira_service.jira.issue.call_args[0][0] == "AAI-5"


def test_get_issue_not_found_returns_none(jira_service):
    jira_service.jira.issue.side_effect = JIRAError(status_code=404, text="nope")
    assert jira_service.get_issue("AAI-999") is None


# ------------------------------------------------------------- create_story ---


def _component(name):
    comp = MagicMock()
    comp.name = name
    return comp


def test_create_story_success(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [_component("org")]
    created = MagicMock()
    created.key = "AAI-10"
    jira_service.jira.create_issue.return_value = created

    key, error = jira_service.create_story(
        summary="Fix it",
        description="details",
        component_name="org",
        issue_type="Bug",
        project_key="AAI",
        labels=["tg_user:alice"],
    )

    assert key == "AAI-10"
    assert error is None
    fields = jira_service.jira.create_issue.call_args[1]["fields"]
    assert fields["project"] == {"key": "AAI"}
    assert fields["summary"] == "Fix it"
    assert fields["issuetype"] == {"name": "Bug"}
    assert fields["components"] == [{"name": "org"}]
    assert fields["labels"] == ["tg_user:alice"]


def test_create_story_component_not_found(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [
        _component("backend"),
        _component("frontend"),
    ]

    key, error = jira_service.create_story(
        summary="Fix it", component_name="nonexistent", project_key="AAI"
    )

    assert key is None
    assert "not found" in error
    assert "backend" in error and "frontend" in error
    jira_service.jira.create_issue.assert_not_called()


def test_create_story_adds_to_sprint(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [_component("org")]
    created = MagicMock()
    created.key = "AAI-11"
    jira_service.jira.create_issue.return_value = created

    key, error = jira_service.create_story(
        summary="S", component_name="org", project_key="AAI", sprint_id=99
    )

    assert key == "AAI-11"
    assert error is None
    jira_service.jira.add_issues_to_sprint.assert_called_once_with(99, ["AAI-11"])


def test_create_story_jira_error(jira_service):
    jira_service.jira.project.side_effect = JIRAError(status_code=500, text="boom")

    key, error = jira_service.create_story(
        summary="S", component_name="org", project_key="AAI"
    )

    assert key is None
    assert error.startswith("❌ Failed to create Jira issue")


def test_create_story_assigns_issue(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [_component("org")]
    created = MagicMock()
    created.key = "AAI-12"
    jira_service.jira.create_issue.return_value = created

    key, error = jira_service.create_story(
        summary="S",
        component_name="org",
        project_key="AAI",
        assignee="aleksei.dolzhenkov",
    )

    assert key == "AAI-12"
    assert error is None
    jira_service.jira.assign_issue.assert_called_once_with(
        "AAI-12", "aleksei.dolzhenkov"
    )


def test_create_story_assignment_failure_is_nonfatal(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [_component("org")]
    created = MagicMock()
    created.key = "AAI-13"
    jira_service.jira.create_issue.return_value = created
    jira_service.jira.assign_issue.side_effect = JIRAError(
        status_code=400, text="not on screen"
    )

    key, error = jira_service.create_story(
        summary="S", component_name="org", project_key="AAI", assignee="bad.user"
    )

    # Issue is still created even though assignment failed.
    assert key == "AAI-13"
    assert error is None


def test_create_story_no_assignee_skips_assign(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [_component("org")]
    created = MagicMock()
    created.key = "AAI-14"
    jira_service.jira.create_issue.return_value = created

    jira_service.create_story(summary="S", component_name="org", project_key="AAI")

    jira_service.jira.assign_issue.assert_not_called()


def test_create_story_links_epic(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [_component("org")]
    created = MagicMock()
    created.key = "AAI-20"
    jira_service.jira.create_issue.return_value = created

    key, error = jira_service.create_story(
        summary="S", component_name="org", project_key="AAI", epic_key="AAI-100"
    )

    assert key == "AAI-20"
    assert error is None
    jira_service.jira.add_issues_to_epic.assert_called_once_with("AAI-100", ["AAI-20"])


def test_create_story_epic_failure_is_nonfatal(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [_component("org")]
    created = MagicMock()
    created.key = "AAI-21"
    jira_service.jira.create_issue.return_value = created
    jira_service.jira.add_issues_to_epic.side_effect = JIRAError(
        status_code=400, text="bad epic"
    )

    key, error = jira_service.create_story(
        summary="S", component_name="org", project_key="AAI", epic_key="AAI-999"
    )

    # Issue is still created even though epic linking failed.
    assert key == "AAI-21"
    assert error is None


def test_create_story_no_epic_skips_link(jira_service):
    jira_service.jira.project.return_value = MagicMock(name="proj")
    jira_service.jira.project_components.return_value = [_component("org")]
    created = MagicMock()
    created.key = "AAI-22"
    jira_service.jira.create_issue.return_value = created

    jira_service.create_story(summary="S", component_name="org", project_key="AAI")

    jira_service.jira.add_issues_to_epic.assert_not_called()
