"""Tests for IssueTypeService fuzzy issue-type matching."""

from app.issue_type_service import IssueTypeService


def test_exact_match_bug():
    issue_type, message = IssueTypeService.find_issue_type("Bug")
    assert issue_type == "Bug"
    assert message == ""


def test_exact_match_story():
    issue_type, message = IssueTypeService.find_issue_type("Story")
    assert issue_type == "Story"
    assert message == ""


def test_case_insensitive_match():
    issue_type, message = IssueTypeService.find_issue_type("bUg")
    assert issue_type == "Bug"
    assert message == ""


def test_fuzzy_typo_match():
    # "stroy" is a close typo of "story"
    issue_type, message = IssueTypeService.find_issue_type("stroy")
    assert issue_type == "Story"
    assert message == ""


def test_unknown_returns_default_and_message():
    issue_type, message = IssueTypeService.find_issue_type("epic-supertask")
    assert issue_type == "Story"  # default fallback
    assert "No close match" in message
    assert "Story" in message and "Bug" in message


def test_get_available_issue_types_returns_copy():
    types = IssueTypeService.get_available_issue_types()
    assert types == ["Story", "Bug"]
    types.append("Task")
    # Mutating the returned list must not affect subsequent calls
    assert IssueTypeService.get_available_issue_types() == ["Story", "Bug"]
