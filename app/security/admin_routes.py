"""本地用户、部门、成员角色和审计管理 API。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_db_session
from app.core.exceptions import AuthorizationError, ValidationError
from app.security.audit import AuditAction, AuditService
from app.security.models import AuditEvent, DepartmentMembership, Role
from app.security.permissions import Permission, ensure_permission, permission_dependency
from app.security.principal import (
    Principal,
    get_reauthenticated_principal,
)
from app.security.repository import SecurityRepository

router = APIRouter(prefix="/api/v1", tags=["身份管理"])


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    temporary_password: str = Field(min_length=12, max_length=512)
    reason: str = Field(min_length=1, max_length=500)


class UserStatusRequest(BaseModel):
    is_active: bool
    reason: str = Field(min_length=1, max_length=500)


class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)


class MembershipRequest(BaseModel):
    role: Role
    reason: str = Field(min_length=1, max_length=500)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())


def _require_platform(principal: Principal) -> None:
    ensure_permission(principal, Permission.PLATFORM_CONFIG)


def _can_grant(principal: Principal, department_id: str, role: Role) -> None:
    if Role.PLATFORM_ADMIN in principal.roles:
        return
    ensure_permission(principal, Permission.DEPARTMENT_ADMIN, department_id)
    if role in {Role.PLATFORM_ADMIN, Role.SECURITY_AUDITOR}:
        raise AuthorizationError("部门管理员不能授予全局角色")


@router.post("/admin/users", status_code=201)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    principal: Principal = Depends(get_reauthenticated_principal),
    session: Session = Depends(get_db_session),
):
    _require_platform(principal)
    repository = SecurityRepository(session)
    try:
        user = repository.create_user(payload.username, payload.temporary_password)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    AuditService(session).record(
        principal.user_id,
        AuditAction.USER_CREATED,
        "user",
        user.id,
        "success",
        payload.reason,
        _request_id(request),
        after_state={"is_active": True, "must_change_password": True},
    )
    session.commit()
    return {
        "user_id": user.id,
        "username": user.username,
        "must_change_password": user.must_change_password,
    }


@router.patch("/admin/users/{user_id}")
def change_user_status(
    user_id: str,
    payload: UserStatusRequest,
    request: Request,
    principal: Principal = Depends(get_reauthenticated_principal),
    session: Session = Depends(get_db_session),
):
    _require_platform(principal)
    repository = SecurityRepository(session)
    user = repository.get_user(user_id)
    if user is None:
        raise ValidationError("用户不存在")
    before = {"is_active": user.is_active}
    user.is_active = payload.is_active
    if not payload.is_active:
        repository.revoke_user_tokens(user.id)
    AuditService(session).record(
        principal.user_id,
        AuditAction.USER_STATUS_CHANGED,
        "user",
        user.id,
        "success",
        payload.reason,
        _request_id(request),
        before,
        {"is_active": user.is_active},
    )
    session.commit()
    return {"user_id": user.id, "is_active": user.is_active}


@router.post("/admin/departments", status_code=201)
def create_department(
    payload: DepartmentCreateRequest,
    request: Request,
    principal: Principal = Depends(get_reauthenticated_principal),
    session: Session = Depends(get_db_session),
):
    _require_platform(principal)
    department = SecurityRepository(session).create_department(payload.name)
    AuditService(session).record(
        principal.user_id,
        AuditAction.DEPARTMENT_CREATED,
        "department",
        department.id,
        "success",
        payload.reason,
        _request_id(request),
        after_state={"name_hash": hashlib.sha256(department.name.encode()).hexdigest()},
    )
    session.commit()
    return {"department_id": department.id, "name": department.name}


@router.get("/departments/{department_id}/members")
def list_members(
    department_id: str,
    principal: Principal = Depends(permission_dependency(Permission.DEPARTMENT_ADMIN)),
    session: Session = Depends(get_db_session),
):
    ensure_permission(principal, Permission.DEPARTMENT_ADMIN, department_id)
    statement = select(DepartmentMembership).where(
        DepartmentMembership.department_id == department_id
    )
    return {
        "members": [
            {"user_id": item.user_id, "role": item.role.value}
            for item in session.scalars(statement)
        ]
    }


@router.put("/departments/{department_id}/members/{user_id}")
def set_membership(
    department_id: str,
    user_id: str,
    payload: MembershipRequest,
    request: Request,
    principal: Principal = Depends(get_reauthenticated_principal),
    session: Session = Depends(get_db_session),
):
    _can_grant(principal, department_id, payload.role)
    repository = SecurityRepository(session)
    if repository.get_user(user_id) is None:
        raise ValidationError("用户不存在")
    membership = repository.set_membership(user_id, department_id, payload.role)
    AuditService(session).record(
        principal.user_id,
        AuditAction.MEMBERSHIP_CHANGED,
        "membership",
        membership.id,
        "success",
        payload.reason,
        _request_id(request),
        after_state={"department_id": department_id, "role": payload.role.value},
    )
    session.commit()
    return {"user_id": user_id, "department_id": department_id, "role": payload.role}


@router.delete("/departments/{department_id}/members/{user_id}", status_code=204)
def revoke_membership(
    department_id: str,
    user_id: str,
    request: Request,
    reason: str = Query(min_length=1, max_length=500),
    principal: Principal = Depends(get_reauthenticated_principal),
    session: Session = Depends(get_db_session),
):
    _can_grant(principal, department_id, Role.READER)
    statement = select(DepartmentMembership).where(
        DepartmentMembership.user_id == user_id,
        DepartmentMembership.department_id == department_id,
    )
    membership = session.scalar(statement)
    if membership is None:
        return
    membership_id = membership.id
    session.delete(membership)
    AuditService(session).record(
        principal.user_id,
        AuditAction.MEMBERSHIP_REVOKED,
        "membership",
        membership_id,
        "success",
        reason,
        _request_id(request),
        before_state={"department_id": department_id, "role": membership.role.value},
    )
    session.commit()


@router.get("/audit/events")
def list_audit_events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    action: str | None = None,
    result: str | None = None,
    created_after: datetime | None = None,
    principal: Principal = Depends(permission_dependency(Permission.SECURITY_AUDIT)),
    session: Session = Depends(get_db_session),
):
    statement = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    filters = {"limit": limit, "action": action, "result": result}
    if action:
        statement = statement.where(AuditEvent.action == action)
    if result:
        statement = statement.where(AuditEvent.result == result)
    if created_after:
        statement = statement.where(AuditEvent.created_at >= created_after)
        filters["created_after"] = created_after.isoformat()
    events = list(session.scalars(statement))
    filter_hash = hashlib.sha256(
        json.dumps(filters, sort_keys=True).encode("utf-8")
    ).hexdigest()
    AuditService(session).record(
        principal.user_id,
        AuditAction.AUDIT_EVENTS_QUERIED,
        "audit_query",
        filter_hash,
        "success",
        "auditor query",
        _request_id(request),
    )
    session.commit()
    return {
        "events": [
            {
                "id": event.id,
                "actor_user_id": event.actor_user_id,
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "result": event.result,
                "reason": event.reason,
                "request_id": event.request_id,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]
    }
