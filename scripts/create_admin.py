"""从环境变量创建或复用初始平台管理员。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.dependencies import get_security_session_factory  # noqa: E402
from app.security.audit import AuditAction, AuditService  # noqa: E402
from app.security.models import Role  # noqa: E402
from app.security.repository import SecurityRepository  # noqa: E402


def create_admin(
    session,
    username: str,
    password: str,
    department_name: str,
    role: Role | str = Role.PLATFORM_ADMIN,
):
    selected_role = role if isinstance(role, Role) else Role(role)
    repository = SecurityRepository(session)
    user = repository.get_user_by_username(username)
    if user is None:
        user = repository.create_user(username, password)
        user.must_change_password = True
    department = repository.create_department(department_name)
    repository.set_membership(user.id, department.id, selected_role)
    AuditService(session).record(
        user.id,
        AuditAction.USER_CREATED,
        "user",
        user.id,
        "success",
        "initial administrator bootstrap",
        "bootstrap",
        after_state={"role": selected_role.value},
    )
    session.commit()
    return user


def main() -> None:
    password = os.environ.get("RAG_INITIAL_ADMIN_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("RAG_INITIAL_ADMIN_PASSWORD must contain at least 12 characters")
    username = os.environ.get("RAG_INITIAL_ADMIN_USERNAME", "admin")
    department = os.environ.get("RAG_INITIAL_ADMIN_DEPARTMENT", "平台管理")
    with get_security_session_factory()() as session:
        user = create_admin(session, username, password, department)
    print(f"Administrator ready: {user.username}")


if __name__ == "__main__":
    main()
