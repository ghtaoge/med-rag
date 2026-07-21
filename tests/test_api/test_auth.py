from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_config_dep, get_db_session
from app.main import app
from app.security.database import Base
from app.security.models import Department, DepartmentMembership, Role, User
from app.security.passwords import hash_password
from app.security.principal import get_current_principal

AUTH_CONFIG = {
    "auth": {
        "jwt_secret": "s" * 32,
        "access_ttl_seconds": 900,
        "refresh_ttl_seconds": 604800,
        "issuer": "med-rag",
        "secure_cookies": True,
    }
}


def _auth_client():
    app.dependency_overrides.pop(get_current_principal, None)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    department = Department(id="dept-a", name="药学部")
    user = User(
        id="user-reader",
        username="reader",
        password_hash=hash_password("Reader Password 2026"),
        is_active=True,
        must_change_password=False,
    )
    session.add_all([department, user])
    session.flush()
    session.add(
        DepartmentMembership(
            user_id=user.id,
            department_id=department.id,
            role=Role.READER,
        )
    )
    session.commit()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_config_dep] = lambda: AUTH_CONFIG
    return TestClient(app, base_url="https://testserver"), session


def _cleanup(session):
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_config_dep, None)
    session.close()


def test_login_refresh_logout_flow():
    client, session = _auth_client()
    try:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "reader", "password": "Reader Password 2026"},
        )
        assert login.status_code == 200
        first_cookie = login.cookies["med_rag_refresh"]
        csrf = login.json()["csrf_token"]
        refreshed = client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": csrf},
        )
        assert refreshed.status_code == 200
        assert refreshed.cookies["med_rag_refresh"] != first_cookie
        logout = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": refreshed.json()["csrf_token"]},
        )
        assert logout.status_code == 204
    finally:
        _cleanup(session)


def test_wrong_password_returns_same_safe_error():
    client, session = _auth_client()
    try:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "reader", "password": "wrong password"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "AUTHENTICATION_ERROR"
        assert "reader" not in response.text
    finally:
        _cleanup(session)


def test_me_requires_bearer_token():
    client, session = _auth_client()
    try:
        assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        _cleanup(session)
