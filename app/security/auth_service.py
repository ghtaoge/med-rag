"""登录、刷新、注销、密码修改与再认证。"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.security.audit import AuditAction, AuditService
from app.security.identity_provider import IdentityProvider
from app.security.models import RefreshTokenFamily
from app.security.passwords import hash_password, verify_password
from app.security.repository import SecurityRepository
from app.security.tokens import (
    hash_opaque_token,
    issue_access_token,
    issue_reauthentication_token,
    new_opaque_token,
    refresh_family_id,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    csrf_token: str
    expires_in: int


class AuthService:
    def __init__(
        self,
        session: Session,
        repository: SecurityRepository,
        identity_provider: IdentityProvider,
        config: dict,
    ):
        self.session = session
        self.repository = repository
        self.identity_provider = identity_provider
        self.config = config
        self.audit = AuditService(session)

    @property
    def _auth_config(self) -> dict:
        return self.config["auth"]

    def _access_token(self, user_id: str, session_id: str) -> str:
        cfg = self._auth_config
        return issue_access_token(
            user_id,
            session_id,
            cfg["jwt_secret"],
            cfg["access_ttl_seconds"],
            cfg["issuer"],
        )

    def login(self, username: str, password: str, request_id: str) -> AuthTokens:
        try:
            identity = self.identity_provider.authenticate(username, password)
        except AuthenticationError:
            self.audit.record(
                None,
                AuditAction.LOGIN_FAILED,
                "username_hash",
                self.repository.username_fingerprint(username),
                "denied",
                "invalid credentials",
                request_id,
            )
            self.session.commit()
            raise

        family_id, refresh_token = new_opaque_token()
        csrf_token = secrets.token_urlsafe(32)
        cfg = self._auth_config
        family = RefreshTokenFamily(
            id=family_id,
            user_id=identity.subject,
            token_hash=hash_opaque_token(refresh_token),
            csrf_hash=hash_opaque_token(csrf_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=cfg["refresh_ttl_seconds"]),
        )
        self.session.add(family)
        self.audit.record(
            identity.subject,
            AuditAction.LOGIN_SUCCEEDED,
            "user",
            identity.subject,
            "success",
            "interactive login",
            request_id,
        )
        self.session.commit()
        return AuthTokens(
            self._access_token(identity.subject, family_id),
            refresh_token,
            csrf_token,
            cfg["access_ttl_seconds"],
        )

    def refresh(
        self,
        refresh_token: str,
        csrf_token: str,
        request_id: str,
    ) -> AuthTokens:
        try:
            family_id = refresh_family_id(refresh_token)
        except (ValueError, TypeError) as exc:
            raise AuthenticationError("刷新令牌无效") from exc
        family = self.repository.get_refresh_family(family_id)
        if family is None:
            raise AuthenticationError("刷新令牌无效")

        token_matches = hmac.compare_digest(
            family.token_hash,
            hash_opaque_token(refresh_token),
        )
        csrf_matches = hmac.compare_digest(
            family.csrf_hash,
            hash_opaque_token(csrf_token),
        )
        now = datetime.now(timezone.utc)
        if not token_matches:
            family.revoked_at = now
            self.session.commit()
            raise AuthenticationError("检测到刷新令牌重放")
        if (
            not csrf_matches
            or family.revoked_at is not None
            or _as_utc(family.expires_at) <= now
        ):
            raise AuthenticationError("刷新令牌无效")

        user = self.repository.get_user(family.user_id)
        if user is None or not user.is_active:
            family.revoked_at = now
            self.session.commit()
            raise AuthenticationError("刷新令牌无效")

        _, rotated_token = new_opaque_token(family.id)
        rotated_csrf = secrets.token_urlsafe(32)
        family.token_hash = hash_opaque_token(rotated_token)
        family.csrf_hash = hash_opaque_token(rotated_csrf)
        family.last_rotated_at = now
        self.session.commit()
        return AuthTokens(
            self._access_token(user.id, family.id),
            rotated_token,
            rotated_csrf,
            self._auth_config["access_ttl_seconds"],
        )

    def logout(self, refresh_token: str, csrf_token: str, request_id: str) -> None:
        try:
            family = self.repository.get_refresh_family(refresh_family_id(refresh_token))
        except (ValueError, TypeError):
            family = None
        if family is None:
            return
        if not hmac.compare_digest(family.csrf_hash, hash_opaque_token(csrf_token)):
            raise AuthenticationError("CSRF 校验失败")
        family.revoked_at = datetime.now(timezone.utc)
        self.audit.record(
            family.user_id,
            AuditAction.LOGOUT,
            "refresh_token_family",
            family.id,
            "success",
            "user logout",
            request_id,
        )
        self.session.commit()

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
        current_session_id: str,
        request_id: str,
    ) -> None:
        user = self.repository.get_user(user_id)
        if user is None or not verify_password(user.password_hash, current_password):
            raise AuthenticationError()
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        self.repository.revoke_user_tokens(user.id)
        current_family = self.repository.get_refresh_family(current_session_id)
        if current_family is not None:
            current_family.revoked_at = None
        self.audit.record(
            user.id,
            AuditAction.PASSWORD_CHANGED,
            "user",
            user.id,
            "success",
            "password changed",
            request_id,
        )
        self.session.commit()

    def reauthenticate(
        self,
        user_id: str,
        session_id: str,
        password: str,
    ) -> str:
        user = self.repository.get_user(user_id)
        if user is None or not user.is_active or not verify_password(
            user.password_hash, password
        ):
            raise AuthenticationError()
        cfg = self._auth_config
        return issue_reauthentication_token(
            user_id,
            session_id,
            cfg["jwt_secret"],
            cfg["issuer"],
        )
