"""Cryptographic service for encrypting and decrypting sensitive data."""

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from .config import Config

logger = logging.getLogger(__name__)


class CryptoService:
    """Service for encrypting and decrypting tokens using Fernet symmetric encryption."""

    def __init__(self):
        """Initialize the crypto service with encryption key from config."""
        self._fernet = None
        self._initialize_fernet()

    def _initialize_fernet(self):
        """Initialize Fernet cipher with the encryption key."""
        try:
            key = Config.TOKEN_ENCRYPTION_KEY
            if not key:
                logger.warning(
                    "TOKEN_ENCRYPTION_KEY not set. Token encryption will not work."
                )
                return

            # Fernet key must be 32 url-safe base64-encoded bytes
            self._fernet = Fernet(key.encode())
            logger.info("Crypto service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize crypto service: {e}")
            raise

    def encrypt_token(self, token: str) -> Optional[str]:
        """
        Encrypt a token using Fernet symmetric encryption.

        Args:
            token: The plaintext token to encrypt

        Returns:
            The encrypted token as a string, or None if encryption fails
        """
        if not self._fernet:
            logger.error("Fernet not initialized. Cannot encrypt token.")
            return None

        try:
            encrypted = self._fernet.encrypt(token.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Failed to encrypt token: {e}")
            return None

    def decrypt_token(self, encrypted_token: str) -> Optional[str]:
        """
        Decrypt a token using Fernet symmetric encryption.

        Args:
            encrypted_token: The encrypted token string

        Returns:
            The decrypted plaintext token, or None if decryption fails
        """
        if not self._fernet:
            logger.error("Fernet not initialized. Cannot decrypt token.")
            return None

        try:
            decrypted = self._fernet.decrypt(encrypted_token.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("Invalid token or wrong encryption key")
            return None
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            return None

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.

        This is a utility method for generating keys during setup.

        Returns:
            A new Fernet key as a string
        """
        return Fernet.generate_key().decode()

