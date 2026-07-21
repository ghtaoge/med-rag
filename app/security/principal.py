"""从 Bearer Token 构建当前授权主体。"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.dependencies import get_config_dep, get_db_session
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationServiceUnavailable,
    PasswordChangeRequired,
)
from app.security.models import Role
from app.security.repository import SecurityRepository
from app.security.tokens import decode_token

_bearer = HTTPBearer(auto_error=False)
_PASSWORD_ALLOWED_PATHS = {
    "/api/v1/auth/me",
    "/api/v1/auth/change-password",
    "/api/v1/auth/logout",
}


@dataclass(frozen=True)
class PrincipalMembership:
    department_id: str
    role: Role


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    memberships: tuple[PrincipalMembership, ...]
    session_id: str

    @property
    def department_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.department_id for item in self.memberships))

    @property
    def roles(self) -> frozenset[Role]:
        return frozenset(item.role for item in self.memberships)


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_db_session),
    config: dict = Depends(get_config_dep),
) -> Principal:
    if credentials is None:
        raise AuthenticationError("需要登录")
    try:
        claims = decode_token(
            credentials.credentials,
            config["auth"]["jwt_secret"],
            config["auth"]["issuer"],
            "access",
        )
        repository = SecurityRepository(session)
        user = repository.get_user(claims["sub"])
        if user is None or not user.is_active:
            raise AuthenticationError("身份已失效")
        memberships = tuple(
            PrincipalMembership(item.department_id, item.role)
            for item in repository.memberships(user.id)
        )
    except AuthenticationError:
        raise
    except jwt.PyJWTError as exc:
        raise AuthenticationError("访问令牌无效") from exc
    except Exception as exc:
        raise AuthorizationServiceUnavailable() from exc

    if user.must_change_password and request.url.path not in _PASSWORD_ALLOWED_PATHS:
        raise PasswordChangeRequired()
    return Principal(user.id, user.username, memberships, claims["sid"])


def get_reauthenticated_principal(
    principal: Principal = Depends(get_current_principal),
    token: str | None = Header(default=None, alias="X-Reauthentication-Token"),
    config: dict = Depends(get_config_dep),
) -> Principal:
    if token is None:
        raise AuthenticationError("需要再次验证密码")
    try:
        claims = decode_token(
            token,
            config["auth"]["jwt_secret"],
            config["auth"]["issuer"],
            "reauthentication",
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("再认证令牌无效") from exc
    if claims["sub"] != principal.user_id or claims["sid"] != principal.session_id:
        raise AuthenticationError("再认证令牌无效")
    return principal
