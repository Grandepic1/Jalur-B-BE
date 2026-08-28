from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import urlparse

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_password: str) -> bool:
    try:
        return password_hash.verify(password, encoded_password)
    except (TypeError, ValueError):
        return False


def _jwt_secret() -> str:
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    return settings.jwt_secret_key


def create_access_token(user_id: int, token_version: int) -> tuple[str, int]:
    expires_in = settings.jwt_access_token_minutes * 60
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "ver": token_version,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        },
        _jwt_secret(),
        algorithm="HS256",
    )
    return token, expires_in


def decode_access_token(token: str) -> tuple[int, int] | None:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return int(payload["sub"]), int(payload["ver"])
    except (InvalidTokenError, KeyError, TypeError, ValueError, RuntimeError):
        return None


def create_oauth_state(return_to: str, nonce: str, browser_state: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "type": "oauth_state",
            "return_to": return_to,
            "nonce": nonce,
            "browser_state": browser_state,
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        _jwt_secret(),
        algorithm="HS256",
    )


def decode_oauth_state(state: str) -> tuple[str, str, str] | None:
    try:
        payload = jwt.decode(state, _jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != "oauth_state":
            return None
        return (
            str(payload["return_to"]),
            str(payload["nonce"]),
            str(payload["browser_state"]),
        )
    except (InvalidTokenError, KeyError, TypeError, RuntimeError):
        return None


def hash_login_code(code: str) -> str:
    return sha256(code.encode("utf-8")).hexdigest()


def is_allowed_frontend_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if origin in settings.allowed_frontend_origins:
        return True

    if settings.cors_origin_regex:
        import re

        return re.fullmatch(settings.cors_origin_regex, origin) is not None
    return False
