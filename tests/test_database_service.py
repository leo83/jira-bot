"""Tests for DatabaseService with a mocked ClickHouse client."""

from unittest.mock import MagicMock, patch

import pytest

from app.database_service import DatabaseService


@pytest.fixture
def db():
    """A DatabaseService whose ClickHouse Client is fully mocked."""
    with patch("app.database_service.Client") as mock_client_cls:
        client = mock_client_cls.return_value
        client.execute.return_value = [[0]]  # default: SELECT 1 / counts
        svc = DatabaseService()
        svc.client = client
        yield svc


# --------------------------------------------------------------- link CRUD ---


def test_link_exists_true(db):
    db.client.execute.return_value = [[1]]
    assert db.link_exists("ref", "AAI-1") is True


def test_link_exists_false(db):
    db.client.execute.return_value = [[0]]
    assert db.link_exists("ref", "AAI-1") is False


def test_insert_rejects_duplicate(db):
    db.client.execute.return_value = [[1]]  # link_exists -> True
    ok, reason = db.insert_jira_issue_link("ref", "AAI-1")
    assert ok is False
    assert reason == "duplicate"


def test_insert_success(db):
    db.client.execute.return_value = [[0]]  # link_exists -> False
    ok, reason = db.insert_jira_issue_link("ref", "AAI-1")
    assert ok is True
    assert reason == ""


def test_delete_not_found(db):
    db.client.execute.return_value = [[0]]  # link_exists -> False
    ok, reason = db.delete_jira_issue_link("ref", "AAI-1")
    assert ok is False
    assert reason == "not_found"


def test_delete_success(db):
    db.client.execute.return_value = [[1]]  # link_exists -> True
    ok, reason = db.delete_jira_issue_link("ref", "AAI-1")
    assert ok is True
    assert reason == ""


def test_get_jira_keys_by_message_ref(db):
    db.client.execute.return_value = [["AAI-1"], ["AAI-2"]]
    assert db.get_jira_keys_by_message_ref("ref") == ["AAI-1", "AAI-2"]


# --------------------------------------------------------------- user tokens ---


def test_save_user_token(db):
    ok, reason = db.save_user_token(123, "enc-token", "alice")
    assert ok is True
    assert reason == ""
    db.client.execute.assert_called()


def test_get_user_token_found(db):
    db.client.execute.return_value = [["enc-token"]]
    assert db.get_user_token(123) == "enc-token"


def test_get_user_token_missing(db):
    db.client.execute.return_value = []
    assert db.get_user_token(123) is None


def test_user_is_registered(db):
    db.client.execute.return_value = [["enc-token"]]
    assert db.user_is_registered(123) is True
    db.client.execute.return_value = []
    assert db.user_is_registered(123) is False


def test_delete_user_token_not_found(db):
    db.client.execute.return_value = []  # get_user_token -> None
    ok, reason = db.delete_user_token(123)
    assert ok is False
    assert reason == "not_found"


def test_error_paths_return_false(db):
    # Let the health-check ("SELECT 1") succeed but fail the real query, so
    # _ensure_connection does not mask the error by reconnecting.
    def exec_side(query, *args, **kwargs):
        if "SELECT 1" in query:
            return [[1]]
        raise RuntimeError("db down")

    db.client.execute.side_effect = exec_side
    ok, reason = db.save_user_token(1, "t")
    assert ok is False
    assert reason == "error"
