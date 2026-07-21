from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.security.database import Base
from app.security.models import DepartmentMembership, Role
from scripts.create_admin import create_admin


def test_create_admin_is_idempotent():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        first = create_admin(
            session,
            "admin",
            "Administrator Password 2026",
            "平台管理",
            "platform_admin",
        )
        second = create_admin(
            session,
            "admin",
            "Administrator Password 2026",
            "平台管理",
            Role.PLATFORM_ADMIN,
        )
        assert first.id == second.id
        memberships = session.query(DepartmentMembership).all()
        assert len(memberships) == 1
        assert memberships[0].role == Role.PLATFORM_ADMIN
