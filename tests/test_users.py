"""Tests for UserConfig authorization logic."""

from app.users import UserConfig


def test_no_users_configured_allows_everyone(monkeypatch):
    monkeypatch.setattr(UserConfig, "ALLOWED_USERS_STR", "")
    assert UserConfig.get_allowed_users() == []
    assert UserConfig.is_user_allowed("anyone", 999) is True
    assert UserConfig.is_user_allowed(None, None) is True


def test_parses_and_strips_list(monkeypatch):
    monkeypatch.setattr(UserConfig, "ALLOWED_USERS_STR", " alice , 123 ,bob, ")
    assert UserConfig.get_allowed_users() == ["alice", "123", "bob"]


def test_allowed_by_username(monkeypatch):
    monkeypatch.setattr(UserConfig, "ALLOWED_USERS_STR", "alice,bob")
    assert UserConfig.is_user_allowed("alice", 999) is True


def test_allowed_by_user_id(monkeypatch):
    monkeypatch.setattr(UserConfig, "ALLOWED_USERS_STR", "alice,123")
    assert UserConfig.is_user_allowed(None, 123) is True


def test_denied_when_not_in_list(monkeypatch):
    monkeypatch.setattr(UserConfig, "ALLOWED_USERS_STR", "alice,123")
    assert UserConfig.is_user_allowed("carol", 999) is False


def test_display_no_restrictions(monkeypatch):
    monkeypatch.setattr(UserConfig, "ALLOWED_USERS_STR", "")
    assert "No restrictions" in UserConfig.get_allowed_users_display()


def test_display_lists_users(monkeypatch):
    monkeypatch.setattr(UserConfig, "ALLOWED_USERS_STR", "alice,bob")
    assert UserConfig.get_allowed_users_display() == "alice, bob"
