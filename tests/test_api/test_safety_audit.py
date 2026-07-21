from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_db_session
from app.main import app
from app.security.database import Base
from app.security.models import Role
from app.security.principal import Principal, PrincipalMembership, get_current_principal


def _principal(role):
    return Principal(
        f"user-{role.value}",
        role.value,
        (PrincipalMembership("dept-a", role),),
        "session-a",
    )


def test_only_security_auditor_can_list_events():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    app.dependency_overrides[get_db_session] = lambda: session
    client = TestClient(app)
    try:
        app.dependency_overrides[get_current_principal] = lambda: _principal(Role.READER)
        assert client.get("/api/v1/safety/events").status_code == 403
        app.dependency_overrides[get_current_principal] = lambda: _principal(
            Role.SECURITY_AUDITOR
        )
        response = client.get("/api/v1/safety/events")
        assert response.status_code == 200
        assert response.json()["events"] == []
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_principal, None)
        session.close()
