from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=64)
    return f"{base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(derived).decode()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        salt_b64, hash_b64 = encoded.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(hash_b64.encode())
    except Exception:  # noqa: BLE001
        return False
    actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=64)
    return hmac.compare_digest(actual, expected)


def issue_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry(seconds: int) -> str:
    return (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
