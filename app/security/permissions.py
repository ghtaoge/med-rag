"""固定角色的权限矩阵。"""

from __future__ import annotations

from enum import Enum

from fastapi import Depends

from app.core.exceptions import AuthorizationError
from app.security.models import Role
from app.security.principal import Principal, get_current_principal


class Permission(str, Enum):
    CHAT = "chat"
    DOCUMENT_READ = "document_read"
    DOCUMENT_EDIT = "document_edit"
    DOCUMENT_APPROVE = "document_approve"
    DEPARTMENT_ADMIN = "department_admin"
    SECURITY_AUDIT = "security_audit"
    PLATFORM_CONFIG = "platform_config"


ROLE_PERMISSIONS = {
    Role.READER: {Permission.CHAT, Permission.DOCUMENT_READ},
    Role.KNOWLEDGE_EDITOR: {
        Permission.CHAT,
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_EDIT,
    },
    Role.KNOWLEDGE_REVIEWER: {
        Permission.CHAT,
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_APPROVE,
    },
    Role.DEPARTMENT_ADMIN: {
        Permission.CHAT,
        Permission.DOCUMENT_READ,
        Permission.DEPARTMENT_ADMIN,
    },
    Role.SECURITY_AUDITOR: {Permission.SECURITY_AUDIT},
    Role.PLATFORM_ADMIN: {Permission.PLATFORM_CONFIG},
}


def ensure_permission(
    principal: Principal,
    permission: Permission,
    department_id: str | None = None,
) -> None:
    for membership in principal.memberships:
        if department_id is not None and membership.department_id != department_id:
            continue
        if permission in ROLE_PERMISSIONS[membership.role]:
            return
    raise AuthorizationError()


def permission_dependency(permission: Permission):
    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        ensure_permission(principal, permission)
        return principal

    return dependency
