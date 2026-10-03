# api/security.py
"""Primitif kriptografi autentikasi (INTERFACE.md §6, DATABASE.md §8.6).

Tidak menyentuh basis data. Pemakaiannya ada di api/deps.py (sesi per
request) dan api/routes/auth.py.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import string
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

BCRYPT_ROUNDS = 12
PASSWORD_MIN_LENGTH = 10
SESSION_HOURS = 8
SESSION_COOKIE = "orbit_u_session"
JWT_ALGORITHM = "HS256"

TOKEN_PREFIX = "trn_"
TOKEN_RANDOM_BYTES = 32
TOKEN_MAX_DAYS = 180
TOKEN_RATE_LIMIT = 120          # request per jendela
TOKEN_RATE_WINDOW_S = 60.0

_BASE62 = string.digits + string.ascii_letters


# --- kata sandi ---------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:  # hash rusak/bukan bcrypt
        return False


# Dipakai saat username tidak dikenal, supaya waktu respons tidak membocorkan
# apakah akun itu ada.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def password_policy_error(password: str) -> str | None:
    """Pesan error (Inggris, M21) bila sandi melanggar kebijakan, None bila lolos."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
    if len(password.encode("utf-8")) > 72:
        # bcrypt hanya memakai 72 byte pertama.
        return "Password must be at most 72 bytes"
    return None


# --- JWT sesi -----------------------------------------------------------------

def jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be set to at least 32 characters")
    return secret


def create_session_jwt(user_id: int, role_code: str) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=SESSION_HOURS)
    payload = {"sub": str(user_id), "role": role_code, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM), exp


def decode_session_jwt(token: str) -> int | None:
    """user_id dari JWT yang sah dan belum kedaluwarsa; None bila tidak."""
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM],
                             options={"require": ["sub", "exp", "iat"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def cookie_secure() -> bool:
    return os.getenv("COOKIE_SECURE", "true").strip().lower() not in ("0", "false", "no")


# --- token API ----------------------------------------------------------------

def generate_api_token() -> tuple[str, str, str]:
    """(token utuh, prefix 8 karakter, SHA-256 hex). Token = trn_ + base62
    dari 32 byte acak; hanya prefix dan hash yang disimpan."""
    n = int.from_bytes(secrets.token_bytes(TOKEN_RANDOM_BYTES), "big")
    chars = []
    while n:
        n, r = divmod(n, 62)
        chars.append(_BASE62[r])
    body = "".join(reversed(chars)).rjust(43, "0")
    token = TOKEN_PREFIX + body
    return token, token[:8], hash_api_token(token)


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def api_token_matches(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_token(token), stored_hash.strip())


class RateLimiter:
    """Sliding window per kunci, in-process (INTERFACE.md §4: cukup
    sederhana; tidak dibagi antar worker)."""

    def __init__(self, limit: int = TOKEN_RATE_LIMIT, window_s: float = TOKEN_RATE_WINDOW_S) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[object, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: object) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


token_rate_limiter = RateLimiter()
