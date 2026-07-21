"""身份与部门关系的持久化操作。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.security.models import (
    Department,
    DepartmentMembership,
    RefreshTokenFamily,
    Role,
    User,
)
from app.security.passwords import hash_password, verify_password

_DUMMY_HASH = hash_password("Invalid Password Padding 2026")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SecurityRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_user_by_username(self, username: str) -> User | None:
        normalized = username.strip().lower()
        return self.session.scalar(select(User).where(User.username == normalized))

    def get_user(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def authenticate_local_user(self, username: str, password: str) -> User:
        user = self.get_user_by_username(username)
        now = datetime.now(timezone.utc)
        if user is None:
            verify_password(_DUMMY_HASH, password)
            raise AuthenticationError()
        if not user.is_active:
            verify_password(_DUMMY_HASH, password)
            raise AuthenticationError()
        locked_until = _as_utc(user.locked_until)
        if locked_until and locked_until > now:
            verify_password(_DUMMY_HASH, password)
            raise AuthenticationError()
        if not verify_password(user.password_hash, password):
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
            self.session.commit()
            raise AuthenticationError()
        user.failed_login_count = 0
        user.locked_until = None
        self.session.flush()
        return user

    def memberships(self, user_id: str) -> list[DepartmentMembership]:
        statement = select(DepartmentMembership).where(
            DepartmentMembership.user_id == user_id
        )
        return list(self.session.scalars(statement))

    def get_refresh_family(self, family_id: str) -> RefreshTokenFamily | None:
        return self.session.get(RefreshTokenFamily, family_id)

    def revoke_user_tokens(self, user_id: str) -> None:
        now = datetime.now(timezone.utc)
        statement = select(RefreshTokenFamily).where(
            RefreshTokenFamily.user_id == user_id,
            RefreshTokenFamily.revoked_at.is_(None),
        )
        for family in self.session.scalars(statement):
            family.revoked_at = now

    def create_user(self, username: str, password: str) -> User:
        normalized = username.strip().lower()
        if not normalized:
            raise ValueError("用户名不能为空")
        if self.get_user_by_username(normalized):
            raise ValueError("用户名已存在")
        user = User(
            username=normalized,
            password_hash=hash_password(password),
            is_active=True,
            must_change_password=True,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def create_department(self, name: str) -> Department:
        normalized = name.strip()
        if not normalized:
            raise ValueError("部门名称不能为空")
        existing = self.session.scalar(select(Department).where(Department.name == normalized))
        if existing:
            return existing
        department = Department(name=normalized)
        self.session.add(department)
        self.session.flush()
        return department

    def set_membership(self, user_id: str, department_id: str, role: Role) -> DepartmentMembership:
        statement = select(DepartmentMembership).where(
            DepartmentMembership.user_id == user_id,
            DepartmentMembership.department_id == department_id,
        )
        membership = self.session.scalar(statement)
        if membership is None:
            membership = DepartmentMembership(
                user_id=user_id,
                department_id=department_id,
                role=role,
            )
            self.session.add(membership)
        else:
            membership.role = role
        self.session.flush()
        return membership

    @staticmethod
    def username_fingerprint(username: str) -> str:
        return hashlib.sha256(username.strip().lower().encode("utf-8")).hexdigest()
