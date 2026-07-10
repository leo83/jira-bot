"""Tests for LLMService.pick_username (validation + graceful degradation)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.llm_service import LLMService

CANDIDATES = [
    {"name": "aleksei.dolzhenkov", "displayName": "Алексей Долженков"},
    {"name": "danila.redikultsev", "displayName": "Данила Редикульцев"},
]


def _make_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.fixture
def configured_service(monkeypatch):
    monkeypatch.setattr(Config, "OPENAI_API_BASE", "https://llm.example/v1")
    monkeypatch.setattr(Config, "OPENAI_API_KEY", "test-key")
    svc = LLMService()
    # Replace the real OpenAI client with a mock (no network).
    svc._client = MagicMock()
    return svc


def test_not_configured(monkeypatch):
    monkeypatch.setattr(Config, "OPENAI_API_BASE", None)
    monkeypatch.setattr(Config, "OPENAI_API_KEY", None)
    svc = LLMService()
    assert svc.is_configured() is False
    assert svc.pick_username("Алексей", CANDIDATES) is None


def test_valid_pick(configured_service):
    configured_service._client.chat.completions.create.return_value = _make_response(
        "danila.redikultsev"
    )
    assert (
        configured_service.pick_username("редикюльцев", CANDIDATES)
        == "danila.redikultsev"
    )


def test_pick_takes_last_token(configured_service):
    # Model may wrap the answer in prose; we take the last token.
    configured_service._client.chat.completions.create.return_value = _make_response(
        "The best match is aleksei.dolzhenkov"
    )
    assert (
        configured_service.pick_username("Алексей", CANDIDATES) == "aleksei.dolzhenkov"
    )


def test_none_answer_returns_none(configured_service):
    configured_service._client.chat.completions.create.return_value = _make_response(
        "NONE"
    )
    assert configured_service.pick_username("nobody", CANDIDATES) is None


def test_unknown_username_returns_none(configured_service):
    configured_service._client.chat.completions.create.return_value = _make_response(
        "someone.else"
    )
    assert configured_service.pick_username("whoever", CANDIDATES) is None


def test_exception_returns_none(configured_service):
    configured_service._client.chat.completions.create.side_effect = RuntimeError(
        "timeout"
    )
    assert configured_service.pick_username("Алексей", CANDIDATES) is None


def test_empty_candidates_returns_none(configured_service):
    assert configured_service.pick_username("Алексей", []) is None


# ---------------------------------------------------------- generic pick ---

OPTIONS = [
    {"value": "AAI-100", "label": "Мобильное приложение"},
    {"value": "AAI-200", "label": "Payments Q4"},
]


def test_pick_option_valid(configured_service):
    configured_service._client.chat.completions.create.return_value = _make_response(
        "AAI-100"
    )
    assert (
        configured_service.pick_option("мобильное", OPTIONS, kind="Jira epic")
        == "AAI-100"
    )


def test_pick_option_unknown_returns_none(configured_service):
    configured_service._client.chat.completions.create.return_value = _make_response(
        "AAI-999"
    )
    assert configured_service.pick_option("whatever", OPTIONS) is None


def test_pick_option_empty_returns_none(configured_service):
    assert configured_service.pick_option("x", []) is None
