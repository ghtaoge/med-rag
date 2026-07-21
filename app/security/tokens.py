"""短期 JWT 与轮换刷新令牌。"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt


def new_opaque_token(family_id: str | None = None) -> tuple[str, str]:
    family = family_id or str(uuid.uuid4())
    return family, f"{family}.{secrets.token_urlsafe(48)}"


def refresh_family_id(token: str) -> str:
    family_id, separator, _ = token.partition(".")
    if not separator:
        raise ValueError("invalid refresh token")
    return str(uuid.UUID(family_id))


def hash_opaque_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_secret(secret: str) -> None:
    if len(secret) < 32:
        raise RuntimeError("RAG_JWT_SECRET 必须至少 32 个字符")


def issue_access_token(
    user_id: str,
    session_id: str,
    secret: str,
    ttl: int,
    issuer: str,
) -> str:
    _validate_secret(secret)
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "sid": session_id,
            "type": "access",
            "iss": issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        },
        secret,
        algorithm="HS256",
    )


def issue_reauthentication_token(
    user_id: str,
    session_id: str,
    secret: str,
    issuer: str,
) -> str:
    _validate_secret(secret)
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "sid": session_id,
            "type": "reauthentication",
            "iss": issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        secret,
        algorithm="HS256",
    )


def decode_token(token: str, secret: str, issuer: str, expected_type: str) -> dict:
    _validate_secret(secret)
    claims = jwt.decode(token, secret, algorithms=["HS256"], issuer=issuer)
    if claims.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return claims
