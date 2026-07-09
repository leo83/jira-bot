"""Tests for CryptoService Fernet encryption/decryption."""

from app.config import Config
from app.crypto_service import CryptoService


def test_generate_key_is_valid_fernet_key():
    key = CryptoService.generate_key()
    # Fernet keys are 44-char url-safe base64 strings
    assert isinstance(key, str)
    assert len(key) == 44


def test_encrypt_decrypt_round_trip(monkeypatch):
    monkeypatch.setattr(Config, "TOKEN_ENCRYPTION_KEY", CryptoService.generate_key())
    svc = CryptoService()

    plaintext = "ATATT3xFfGF0-super-secret-token"
    encrypted = svc.encrypt_token(plaintext)

    assert encrypted is not None
    assert encrypted != plaintext
    assert svc.decrypt_token(encrypted) == plaintext


def test_decrypt_garbage_returns_none(monkeypatch):
    monkeypatch.setattr(Config, "TOKEN_ENCRYPTION_KEY", CryptoService.generate_key())
    svc = CryptoService()
    assert svc.decrypt_token("not-a-valid-token") is None


def test_decrypt_with_wrong_key_returns_none(monkeypatch):
    monkeypatch.setattr(Config, "TOKEN_ENCRYPTION_KEY", CryptoService.generate_key())
    svc_a = CryptoService()
    encrypted = svc_a.encrypt_token("secret")

    # A service initialised with a different key must fail to decrypt
    monkeypatch.setattr(Config, "TOKEN_ENCRYPTION_KEY", CryptoService.generate_key())
    svc_b = CryptoService()
    assert svc_b.decrypt_token(encrypted) is None


def test_no_key_disables_encryption(monkeypatch):
    monkeypatch.setattr(Config, "TOKEN_ENCRYPTION_KEY", None)
    svc = CryptoService()
    assert svc.encrypt_token("secret") is None
    assert svc.decrypt_token("whatever") is None
