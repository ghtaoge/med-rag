"""可替换的身份提供者边界。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.security.repository import SecurityRepository


@dataclass(frozen=True)
class AuthenticatedIdentity:
    subject: str
    username: str
    provider: str


class IdentityProvider(Protocol):
    def authenticate(self, username: str, password: str) -> AuthenticatedIdentity:
        raise NotImplementedError


class LocalIdentityProvider:
    provider_name = "local"

    def __init__(self, repository: SecurityRepository):
        self.repository = repository

    def authenticate(self, username: str, password: str) -> AuthenticatedIdentity:
        user = self.repository.authenticate_local_user(username, password)
        return AuthenticatedIdentity(user.id, user.username, self.provider_name)
