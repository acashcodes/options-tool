"""Fernet encryption for raw email content at rest."""

from __future__ import annotations

from cryptography.fernet import Fernet


class EmailCrypto:
    """Encrypt / decrypt raw email data using a Fernet key."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, data: bytes | str) -> bytes:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return self._fernet.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        return self._fernet.decrypt(token)

    def decrypt_text(self, token: bytes) -> str:
        return self.decrypt(token).decode("utf-8")
