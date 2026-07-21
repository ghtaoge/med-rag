from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.security.audit import AuditAction, AuditService
from app.security.database import Base, build_engine, build_session_factory
from app.security.models import Department, DepartmentMembership, Role, User
from app.security.passwords import hash_password, verify_password
from app.security.permissions import Permission, ensure_permission
from app.security.principal import Principal, PrincipalMembership
from app.security.tokens import decode_token, issue_access_token, new_opaque_token


def test_sqlite_session_factory_executes_query(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'security.db'}")
    factory = build_session_factory(engine)
    with factory() as session:
        assert session.connection().exec_driver_sql("select 1").scalar_one() == 1


def test_argon2_password_round_trip():
    encoded = hash_password("Correct Horse Battery Staple 2026")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "Correct Horse Battery Staple 2026")
    assert not verify_password(encoded, "wrong")


def test_access_token_claims():
    secret = "s" * 32
    token = issue_access_token("user-1", "session-1", secret, 900, "med-rag")
    claims = decode_token(token, secret, "med-rag", "access")
    assert claims["sub"] == "user-1"
    assert claims["sid"] == "session-1"


def test_refresh_token_contains_family_id():
    family_id, token = new_opaque_token()
    assert token.startswith(f"{family_id}.")


def test_permission_is_department_scoped():
    principal = Principal(
        "user-1",
        "reader",
        (PrincipalMembership("dept-a", Role.READER),),
        "session-1",
    )
    ensure_permission(principal, Permission.CHAT, "dept-a")
    try:
        ensure_permission(principal, Permission.DOCUMENT_EDIT, "dept-a")
    except Exception as exc:
        assert exc.code == "AUTHORIZATION_ERROR"
    else:
        raise AssertionError("reader received edit permission")


def test_audit_event_excludes_credentials():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        event = AuditService(session).record(
            None,
            AuditAction.LOGIN_FAILED,
            "username_hash",
            "f" * 64,
            "denied",
            "invalid credentials",
            "request-1",
        )
        assert "password" not in repr(event.__dict__).lower()
        assert "token" not in repr(event.__dict__).lower()


def test_membership_model_round_trip():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        department = Department(name="药学部")
        user = User(username="reviewer", password_hash="hash", is_active=True)
        session.add_all([department, user])
        session.flush()
        session.add(
            DepartmentMembership(
                user_id=user.id,
                department_id=department.id,
                role=Role.KNOWLEDGE_REVIEWER,
            )
        )
        session.commit()
        membership = session.query(DepartmentMembership).one()
        assert membership.role == Role.KNOWLEDGE_REVIEWER
