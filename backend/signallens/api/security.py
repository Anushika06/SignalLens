"""Password hashing (scrypt, stdlib) and signed session tokens (JWT, HS256)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from datetime import timedelta

import jwt

from signallens.db.base import utcnow

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
COOKIE_NAME = "sl_session"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    """False for a wrong password, and always False for accounts without one (single sign-on only)."""
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p),
                                dklen=32)
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def issue_token(user_id: uuid.UUID, org_id: uuid.UUID, *, secret: str, days: int) -> str:
    now = utcnow()
    payload = {"sub": str(user_id), "org": str(org_id), "iat": int(now.timestamp()),
               "exp": int((now + timedelta(days=days)).timestamp())}
    return jwt.encode(payload, secret, algorithm="HS256")


def read_token(token: str, *, secret: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return uuid.UUID(payload["sub"]), uuid.UUID(payload["org"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
