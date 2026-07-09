"""Tests for Config.validate required-variable checking."""

import pytest

from app.config import Config

REQUIRED = ["TELEGRAM_BOT_TOKEN", "CH_USER", "CH_PASSWORD", "TOKEN_ENCRYPTION_KEY"]


def _set_all(monkeypatch, value="present"):
    for var in REQUIRED:
        monkeypatch.setattr(Config, var, value)


def test_validate_passes_when_all_present(monkeypatch):
    _set_all(monkeypatch)
    assert Config.validate() is True


@pytest.mark.parametrize("missing", REQUIRED)
def test_validate_raises_on_missing(monkeypatch, missing):
    _set_all(monkeypatch)
    monkeypatch.setattr(Config, missing, None)
    with pytest.raises(ValueError) as exc:
        Config.validate()
    assert missing in str(exc.value)


def test_validate_reports_all_missing(monkeypatch):
    for var in REQUIRED:
        monkeypatch.setattr(Config, var, None)
    with pytest.raises(ValueError) as exc:
        Config.validate()
    for var in REQUIRED:
        assert var in str(exc.value)
