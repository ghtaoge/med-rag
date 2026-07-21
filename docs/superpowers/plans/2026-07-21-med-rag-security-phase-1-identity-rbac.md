# Med-Rag Security Phase 1 Identity and RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the temporary management key with local user authentication, PostgreSQL-backed department roles, reviewed document versions, and authorization enforced before every retrieval.

**Architecture:** Use SQLAlchemy repositories as the persistent authorization source, short-lived JWT access tokens, rotating opaque refresh tokens, and department-scoped fixed roles. Store document identity and approval state in PostgreSQL, copy exact ACL metadata into both retrieval indexes, and assert authorization again before context reaches the LLM.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, SQLite for tests, argon2-cffi, PyJWT, Redis, Milvus, Whoosh, Vue 3, Pinia, Axios

---

**Prerequisite:** Complete `2026-07-21-med-rag-security-phase-0-emergency-hardening.md`.

## File Structure

- Create `app/security/database.py`: engine, session factory, declarative base.
- Create `app/security/models.py`: users, departments, memberships, refresh-token families.
- Create `app/security/repository.py`: identity and membership persistence.
- Create `app/security/passwords.py`: Argon2id operations.
- Create `app/security/tokens.py`: JWT and opaque refresh-token primitives.
- Create `app/security/auth_service.py`: login, refresh, logout, reauthentication.
- Create `app/security/identity_provider.py`: OIDC-compatible identity provider contract and local implementation.
- Create `app/security/principal.py`: authenticated principal and request dependencies.
- Create `app/security/permissions.py`: fixed roles and permission checks.
- Create `app/security/routes.py`: authentication API.
- Create `app/security/audit.py`: immutable operational audit records and query service.
- Create `app/security/admin_routes.py`: user, department, and membership administration.
- Create `app/documents/models.py`: document, version, visibility, review actions.
- Create `app/documents/repository.py`: document workflow persistence.
- Create `app/documents/service.py`: upload, submit, approve, revoke, sync orchestration.
- Create `app/retrieval/access.py`: immutable retrieval access scope.
- Create `alembic.ini` and `migrations/`: schema migrations.
- Create `scripts/create_admin.py`: one-time local administrator creation.
- Modify API routes, retrieval stores, chunk models, chat sessions, config, deployment, and frontend authentication.

### Task 1: Establish the Relational Database Layer

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Create: `app/security/database.py`
- Create: `tests/test_security/test_database.py`
- Create: `tests/test_security/__init__.py`

- [ ] **Step 1: Write the failing database test**

```python
from sqlalchemy import text

from app.security.database import build_engine, build_session_factory


def test_sqlite_session_factory_executes_query(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'security.db'}")
    sessions = build_session_factory(engine)
    with sessions() as session:
        assert session.execute(text("select 1")).scalar_one() == 1
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest tests/test_security/test_database.py -v`

Expected: FAIL because `app.security.database` does not exist.

- [ ] **Step 3: Add dependencies and database configuration**

Add to `pyproject.toml` dependencies:

```toml
"sqlalchemy>=2.0,<3.0",
"alembic>=1.13,<2.0",
"psycopg[binary]>=3.2,<4.0",
"argon2-cffi>=23.1,<26.0",
"PyJWT>=2.9,<3.0",
```

Add defaults and environment mappings in `app/core/config.py`:

```python
    "database": {"url": "sqlite:///./data/med_rag.db"},
    "auth": {
        "jwt_secret": "",
        "access_ttl_seconds": 900,
        "refresh_ttl_seconds": 604800,
        "issuer": "med-rag",
    },
```

```python
ENV_MAPPINGS.update({
    "RAG_DATABASE_URL": ("database", "url"),
    "RAG_JWT_SECRET": ("auth", "jwt_secret"),
})
INT_FIELDS.extend([
    ("auth", "access_ttl_seconds"),
    ("auth", "refresh_ttl_seconds"),
])
```

Create `app/security/database.py`:

```python
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(url: str) -> Engine:
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=options)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
```

- [ ] **Step 4: Install and run the test**

Run: `pip install -e ".[dev]" && pytest tests/test_security/test_database.py -v`

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml app/core/config.py app/security/database.py tests/test_security
git commit -m "feat: add security database foundation"
```

### Task 2: Model Users, Departments, Roles, and Token Families

**Files:**
- Create: `app/security/models.py`
- Create: `tests/test_security/test_models.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/20260721_01_identity.py`

- [ ] **Step 1: Write failing model tests**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.security.database import Base
from app.security.models import Department, DepartmentMembership, Role, User


def test_user_can_hold_department_scoped_role():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        department = Department(name="药学部")
        user = User(username="reviewer", password_hash="hash", is_active=True)
        session.add_all([department, user])
        session.flush()
        session.add(DepartmentMembership(user_id=user.id, department_id=department.id, role=Role.KNOWLEDGE_REVIEWER))
        session.commit()
        membership = session.query(DepartmentMembership).one()
        assert membership.role == Role.KNOWLEDGE_REVIEWER
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_security/test_models.py -v`

Expected: FAIL because the ORM models do not exist.

- [ ] **Step 3: Implement identity models**

Create `app/security/models.py` with these complete model boundaries:

```python
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.security.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    READER = "reader"
    KNOWLEDGE_EDITOR = "knowledge_editor"
    KNOWLEDGE_REVIEWER = "knowledge_reviewer"
    DEPARTMENT_ADMIN = "department_admin"
    SECURITY_AUDITOR = "security_auditor"
    PLATFORM_ADMIN = "platform_admin"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True)


class DepartmentMembership(Base):
    __tablename__ = "department_memberships"
    __table_args__ = (UniqueConstraint("user_id", "department_id", name="uq_membership_user_department"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))


class RefreshTokenFamily(Base):
    __tablename__ = "refresh_token_families"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

Configure Alembic `target_metadata = Base.metadata`, import `app.security.models`, and create a migration containing these four tables, indexes, foreign keys, and unique constraints.

- [ ] **Step 4: Run model and migration tests**

Run: `pytest tests/test_security/test_models.py -v && alembic upgrade head`

Expected: test passes and migration exits 0 against the configured local SQLite database.

- [ ] **Step 5: Commit**

```bash
git add app/security/models.py tests/test_security/test_models.py alembic.ini migrations
git commit -m "feat: model users departments and roles"
```

### Task 3: Implement Password and Token Primitives

**Files:**
- Create: `app/security/passwords.py`
- Create: `app/security/tokens.py`
- Create: `tests/test_security/test_credentials.py`

- [ ] **Step 1: Write failing credential tests**

```python
from app.security.passwords import hash_password, verify_password
from app.security.tokens import (
    decode_access_token,
    decode_reauthentication_token,
    hash_opaque_token,
    issue_access_token,
    issue_reauthentication_token,
    new_opaque_token,
)


def test_argon2_password_round_trip():
    encoded = hash_password("Correct Horse Battery Staple 2026")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "Correct Horse Battery Staple 2026") is True
    assert verify_password(encoded, "wrong") is False


def test_access_token_contains_required_claims():
    token = issue_access_token("user-1", "session-1", "secret" * 8, 900, "med-rag")
    claims = decode_access_token(token, "secret" * 8, "med-rag")
    assert claims["sub"] == "user-1"
    assert claims["sid"] == "session-1"
    assert claims["type"] == "access"


def test_opaque_tokens_are_hashed_before_storage():
    value = new_opaque_token()
    assert value not in hash_opaque_token(value)
    assert len(hash_opaque_token(value)) == 64


def test_reauthentication_token_expires_in_five_minutes():
    token = issue_reauthentication_token("user-1", "session-1", "secret" * 8, "med-rag")
    claims = decode_reauthentication_token(token, "secret" * 8, "med-rag")
    assert claims["type"] == "reauthentication"
    assert claims["exp"] - claims["iat"] == 300
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_security/test_credentials.py -v`

Expected: FAIL because credential modules do not exist.

- [ ] **Step 3: Implement credential primitives**

Create `app/security/passwords.py`:

```python
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("密码至少需要 12 个字符")
    return _hasher.hash(password)


def verify_password(encoded: str, candidate: str) -> bool:
    try:
        return _hasher.verify(encoded, candidate)
    except (VerifyMismatchError, InvalidHashError):
        return False
```

Create `app/security/tokens.py`:

```python
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def issue_access_token(user_id: str, session_id: str, secret: str, ttl: int, issuer: str) -> str:
    if len(secret) < 32:
        raise RuntimeError("RAG_JWT_SECRET 必须至少 32 个字符")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "type": "access",
        "iss": issuer,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str, issuer: str) -> dict:
    claims = jwt.decode(token, secret, algorithms=["HS256"], issuer=issuer)
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return claims


def issue_reauthentication_token(user_id: str, session_id: str, secret: str, issuer: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "type": "reauthentication",
        "iss": issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_reauthentication_token(token: str, secret: str, issuer: str) -> dict:
    claims = jwt.decode(token, secret, algorithms=["HS256"], issuer=issuer)
    if claims.get("type") != "reauthentication":
        raise jwt.InvalidTokenError("wrong token type")
    return claims
```

- [ ] **Step 4: Run and verify pass**

Run: `pytest tests/test_security/test_credentials.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/security/passwords.py app/security/tokens.py tests/test_security/test_credentials.py
git commit -m "feat: add password and token primitives"
```

### Task 4: Build Authentication Service and API

**Files:**
- Create: `app/security/repository.py`
- Create: `app/security/auth_service.py`
- Create: `app/security/identity_provider.py`
- Create: `app/security/routes.py`
- Modify: `app/core/dependencies.py`
- Modify: `app/main.py`
- Create: `tests/conftest.py`
- Create: `tests/test_api/test_auth.py`

- [ ] **Step 1: Write failing login and rotation tests**

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_returns_access_and_refresh_cookie(seed_user):
    response = client.post("/api/v1/auth/login", json={"username": "reader", "password": "Reader Password 2026"})
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.cookies.get("med_rag_refresh")
    assert response.json()["csrf_token"]


def test_refresh_rotates_cookie(seed_user):
    login = client.post("/api/v1/auth/login", json={"username": "reader", "password": "Reader Password 2026"})
    first_cookie = login.cookies["med_rag_refresh"]
    response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": login.json()["csrf_token"]})
    assert response.status_code == 200
    assert response.cookies["med_rag_refresh"] != first_cookie
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_api/test_auth.py -v`

Expected: FAIL with 404 for authentication routes.

- [ ] **Step 3: Implement repository and authentication service**

`SecurityRepository` must expose complete transaction-scoped methods:

```python
from sqlalchemy import select

from app.security.models import DepartmentMembership, RefreshTokenFamily, User


class SecurityRepository:
    def __init__(self, session):
        self.session = session

    def get_user_by_username(self, username: str):
        return self.session.scalar(select(User).where(User.username == username))

    def get_user(self, user_id: str):
        return self.session.get(User, user_id)

    def memberships(self, user_id: str):
        statement = select(DepartmentMembership).where(DepartmentMembership.user_id == user_id)
        return list(self.session.scalars(statement))

    def save_refresh_family(self, family: RefreshTokenFamily) -> None:
        self.session.add(family)
        self.session.flush()

    def find_refresh_family(self, token_hash: str):
        statement = select(RefreshTokenFamily).where(RefreshTokenFamily.token_hash == token_hash)
        return self.session.scalar(statement)
```

`LocalIdentityProvider.authenticate()` verifies lockout and password, increments `failed_login_count` on failure, sets `locked_until` to UTC now plus 15 minutes on the fifth consecutive failure, and raises the same public rejection for unknown, locked, and wrong-password users. Success resets both lock fields and returns `AuthenticatedIdentity`. `AuthService.login()` delegates credential verification to the provider, creates opaque refresh and CSRF values, stores only hashes, and issues a 15-minute access token. `AuthService.refresh()` requires matching token and CSRF hashes, rejects expired or revoked families, rotates both values in the same transaction, and revokes the family on replay. `logout()` sets `revoked_at`.

Define the provider boundary in `app/security/identity_provider.py`:

```python
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
```

`AuthService` depends on `IdentityProvider`, not directly on route or database types. A future OIDC implementation must return the same `AuthenticatedIdentity`; authorization still loads departments and roles from PostgreSQL.

Create request and response Pydantic models in `app/security/routes.py` and expose:

```python
router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post("/login")
def login(payload: LoginRequest, response: Response, service: AuthService = Depends(get_auth_service)):
    result = service.login(payload.username, payload.password)
    response.set_cookie(
        "med_rag_refresh",
        result.refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=604800,
    )
    return {"access_token": result.access_token, "csrf_token": result.csrf_token, "token_type": "bearer"}
```

Implement `/refresh`, `/logout`, `/change-password`, `/reauthenticate`, and `/me` with the same explicit cookie and CSRF rules. `/reauthenticate` requires the current Access Token and password, verifies both refer to the same active user, and returns a five-minute JWT from `issue_reauthentication_token`; it never extends the login session. Register the router in `app/main.py`.

Add `/api/v1/auth/login` to `RateLimitMiddleware.RATE_LIMITS` at 10 attempts per IP per 60 seconds. Account lockout remains authoritative when attempts come through different IP addresses.

When `must_change_password` is true, authentication succeeds but the principal dependency rejects every protected business route with `403 PASSWORD_CHANGE_REQUIRED`; only `/auth/me`, `/auth/change-password`, and `/auth/logout` remain available. A successful password change revokes all other refresh-token families and clears the flag in the same transaction.

Add a request-scoped database dependency in `app/core/dependencies.py`:

```python
@lru_cache
def get_security_session_factory():
    engine = build_engine(get_config()["database"]["url"])
    return build_session_factory(engine)


def get_db_session():
    factory = get_security_session_factory()
    with factory() as session:
        yield session
```

Create shared test persistence in `tests/conftest.py`; later role-specific fixtures must build on this factory rather than creating global production users:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.security.database import Base
from app.security.models import Department, DepartmentMembership, Role, User
from app.security.passwords import hash_password


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as value:
        yield value
    Base.metadata.drop_all(engine)


@pytest.fixture
def seed_user(session):
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
    session.add(DepartmentMembership(user_id=user.id, department_id=department.id, role=Role.READER))
    session.commit()
    return user
```

In `test_auth.py`, override `get_db_session` with the yielded `session` and clear the override in fixture teardown.

- [ ] **Step 4: Run authentication tests**

Run: `pytest tests/test_api/test_auth.py -v`

Expected: login, rotation, logout, replay rejection, lockout, and password-change tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/security/repository.py app/security/auth_service.py app/security/identity_provider.py app/security/routes.py app/core/dependencies.py app/api/middleware.py app/main.py tests/conftest.py tests/test_api/test_auth.py
git commit -m "feat: add local authentication api"
```

### Task 5: Enforce Fixed Department Permissions

**Files:**
- Create: `app/security/principal.py`
- Create: `app/security/permissions.py`
- Create: `tests/test_security/test_permissions.py`
- Modify: `app/api/documents.py`
- Modify: `app/api/evaluation.py`
- Modify: `app/api/health.py`

- [ ] **Step 1: Write failing permission matrix tests**

```python
import pytest

from app.security.permissions import Permission, require_permission
from app.security.principal import Principal, PrincipalMembership


def principal(role):
    return Principal("user-1", "reader", (PrincipalMembership("dept-1", role),), "session-1")


def test_reader_can_chat_but_cannot_upload():
    assert require_permission(principal("reader"), Permission.CHAT, "dept-1") is None
    with pytest.raises(PermissionError):
        require_permission(principal("reader"), Permission.DOCUMENT_EDIT, "dept-1")


def test_editor_cannot_approve():
    with pytest.raises(PermissionError):
        require_permission(principal("knowledge_editor"), Permission.DOCUMENT_APPROVE, "dept-1")


def test_reviewer_can_approve_in_own_department_only():
    assert require_permission(principal("knowledge_reviewer"), Permission.DOCUMENT_APPROVE, "dept-1") is None
    with pytest.raises(PermissionError):
        require_permission(principal("knowledge_reviewer"), Permission.DOCUMENT_APPROVE, "dept-2")
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_security/test_permissions.py -v`

Expected: FAIL because principal and permission modules do not exist.

- [ ] **Step 3: Implement principals and permission matrix**

Create immutable principal types and exact role mapping:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PrincipalMembership:
    department_id: str
    role: str


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    memberships: tuple[PrincipalMembership, ...]
    session_id: str

    @property
    def department_ids(self) -> tuple[str, ...]:
        return tuple(item.department_id for item in self.memberships)
```

```python
class Permission(str, Enum):
    CHAT = "chat"
    DOCUMENT_READ = "document_read"
    DOCUMENT_EDIT = "document_edit"
    DOCUMENT_APPROVE = "document_approve"
    DEPARTMENT_ADMIN = "department_admin"
    SECURITY_AUDIT = "security_audit"
    PLATFORM_CONFIG = "platform_config"


ROLE_PERMISSIONS = {
    "reader": {Permission.CHAT, Permission.DOCUMENT_READ},
    "knowledge_editor": {Permission.CHAT, Permission.DOCUMENT_READ, Permission.DOCUMENT_EDIT},
    "knowledge_reviewer": {Permission.CHAT, Permission.DOCUMENT_READ, Permission.DOCUMENT_APPROVE},
    "department_admin": {Permission.CHAT, Permission.DOCUMENT_READ, Permission.DEPARTMENT_ADMIN},
    "security_auditor": {Permission.SECURITY_AUDIT},
    "platform_admin": {Permission.PLATFORM_CONFIG},
}
```

`get_current_principal` decodes the bearer token, loads the active user and memberships from PostgreSQL on every request, and returns `503 AUTHORIZATION_SERVICE_UNAVAILABLE` if the database query fails. Replace the Phase 0 bootstrap dependency on protected routers with principal and permission dependencies.

- [ ] **Step 4: Run permission and API tests**

Run: `pytest tests/test_security/test_permissions.py tests/test_api -v`

Expected: permission matrix passes; unauthenticated protected routes return 401; wrong-role requests return 403.

- [ ] **Step 5: Commit**

```bash
git add app/security/principal.py app/security/permissions.py app/api tests/test_security/test_permissions.py tests/test_api
git commit -m "feat: enforce department scoped permissions"
```

### Task 6: Add Operational Audit Records

**Files:**
- Create: `app/security/audit.py`
- Create: `migrations/versions/20260721_02_audit.py`
- Create: `tests/test_security/test_audit.py`
- Modify: `app/security/auth_service.py`
- Modify: `app/security/routes.py`

- [ ] **Step 1: Write failing audit tests**

```python
import pytest

from app.security.audit import AuditAction, AuditService


def test_audit_event_excludes_credentials(session, user):
    service = AuditService(session)
    event = service.record(
        actor_user_id=user.id,
        action=AuditAction.LOGIN_SUCCEEDED,
        resource_type="user",
        resource_id=user.id,
        result="success",
        reason="interactive login",
        request_id="request-1",
        before_state=None,
        after_state={"is_active": True},
    )
    serialized = repr(event.__dict__)
    assert "password" not in serialized.lower()
    assert "token" not in serialized.lower()


def test_required_audit_failure_rolls_back_operation(session, user, monkeypatch):
    service = AuditService(session)
    monkeypatch.setattr(session, "flush", lambda: (_ for _ in ()).throw(RuntimeError("db error")))
    with pytest.raises(RuntimeError):
        service.record(user.id, AuditAction.ROLE_CHANGED, "membership", "member-1", "success", "approved", "request-2", None, {"role": "reader"})
    session.rollback()
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_security/test_audit.py -v`

Expected: FAIL because the audit module does not exist.

- [ ] **Step 3: Implement the generic audit model and service**

Define `AuditEvent` with UUID ID, actor user ID, actor department IDs JSON, action enum, resource type and ID, result, non-empty reason, request ID, before-state hash, after-state hash, and UTC timestamp. The schema must not contain request bodies, passwords, tokens, cookies, full questions, full answers, document contents, or exception text.

Hash canonical state summaries without retaining the state:

```python
def state_hash(value: dict | None) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

`AuditService.record()` adds and flushes the event inside the caller's transaction. Required state changes commit only after audit flush succeeds. Add actions for login success/failure, logout, password change, token-family revocation, user creation/disable, membership change, document create/submit/approve/revoke/sync, and configuration change.

Instrument authentication service paths without storing usernames for failed unknown-user attempts; store a normalized username hash as `resource_id` instead.

- [ ] **Step 4: Run audit and authentication tests**

Run: `alembic upgrade head && pytest tests/test_security/test_audit.py tests/test_api/test_auth.py -v`

Expected: migration and all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/security/audit.py app/security/auth_service.py app/security/routes.py migrations/versions/20260721_02_audit.py tests/test_security/test_audit.py tests/test_api/test_auth.py
git commit -m "feat: audit security state changes"
```

### Task 7: Add User and Department Membership Administration

**Files:**
- Create: `app/security/admin_routes.py`
- Modify: `app/security/repository.py`
- Modify: `app/security/permissions.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_identity_admin.py`

- [ ] **Step 1: Write failing administration tests**

```python
def test_platform_admin_can_create_user(platform_admin_client):
    response = platform_admin_client.post(
        "/api/v1/admin/users",
        json={"username": "new-reader", "temporary_password": "Temporary Password 2026"},
    )
    assert response.status_code == 201
    assert response.json()["must_change_password"] is True


def test_department_admin_can_grant_reader_in_own_department(department_admin_client, new_user_id):
    response = department_admin_client.put(
        f"/api/v1/departments/dept-a/members/{new_user_id}",
        json={"role": "reader", "reason": "joined department"},
    )
    assert response.status_code == 200


def test_department_admin_cannot_manage_other_department(department_admin_client, new_user_id):
    response = department_admin_client.put(
        f"/api/v1/departments/dept-b/members/{new_user_id}",
        json={"role": "reader", "reason": "unauthorized"},
    )
    assert response.status_code == 403


def test_role_change_requires_recent_reauthentication(department_admin_client, new_user_id):
    response = department_admin_client.put(
        f"/api/v1/departments/dept-a/members/{new_user_id}",
        json={"role": "knowledge_editor", "reason": "new responsibility"},
        headers={"X-Reauthentication-Token": "expired-token"},
    )
    assert response.status_code == 401
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_api/test_identity_admin.py -v`

Expected: FAIL with 404 because administration routes do not exist.

- [ ] **Step 3: Implement explicit administration endpoints**

Expose:

- `POST /api/v1/admin/users` for `platform_admin`.
- `PATCH /api/v1/admin/users/{user_id}` for activation or disablement by `platform_admin`.
- `POST /api/v1/admin/departments` for `platform_admin`.
- `GET /api/v1/departments/{department_id}/members` for that department's `department_admin`.
- `PUT /api/v1/departments/{department_id}/members/{user_id}` for grant/change.
- `DELETE /api/v1/departments/{department_id}/members/{user_id}` for revoke.
- `GET /api/v1/audit/events` for `security_auditor`, with cursor, action, actor, resource, result, and date filters.

All mutations require a non-empty reason, an `X-Reauthentication-Token` issued less than five minutes earlier, and an audit event in the same transaction. A department administrator can grant only `reader`, `knowledge_editor`, `knowledge_reviewer`, and `department_admin` inside a department they administer. Only a platform administrator can grant `security_auditor` or `platform_admin`, and those roles still do not grant document access.

On user disablement, revoke every refresh-token family in the same transaction. Because principals load memberships per request, the next protected request reflects role revocation without waiting for JWT expiry.

Every successful or denied `GET /api/v1/audit/events` request creates an `AUDIT_EVENTS_QUERIED` operational event containing a canonical hash of its filters, never returned event bodies.

- [ ] **Step 4: Run administration and permission tests**

Run: `pytest tests/test_api/test_identity_admin.py tests/test_security/test_permissions.py tests/test_security/test_audit.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/security/admin_routes.py app/security/repository.py app/security/permissions.py app/main.py tests/test_api/test_identity_admin.py
git commit -m "feat: manage department memberships securely"
```

### Task 8: Add Reviewed Document Version Persistence

**Files:**
- Create: `app/documents/models.py`
- Create: `app/documents/repository.py`
- Create: `app/documents/service.py`
- Create: `migrations/versions/20260721_03_documents.py`
- Create: `tests/test_documents/test_workflow.py`

- [ ] **Step 1: Write failing workflow tests**

```python
import pytest

from app.documents.service import DocumentWorkflowService


def test_uploaded_document_starts_as_draft(document_service, editor):
    document = document_service.create_draft(editor, "dept-a", "manual.pdf", "storage-key", "hash")
    assert document.current_status == "draft"


def test_editor_cannot_approve_own_version(document_service, editor):
    document = document_service.create_draft(editor, "dept-a", "manual.pdf", "storage-key", "hash")
    document_service.submit_review(editor, document.id)
    with pytest.raises(PermissionError):
        document_service.approve(editor, document.id, "self approval")


def test_reviewer_can_approve_then_revoke(document_service, editor, reviewer):
    document = document_service.create_draft(editor, "dept-a", "manual.pdf", "storage-key", "hash")
    document_service.submit_review(editor, document.id)
    approved = document_service.approve(reviewer, document.id, "verified")
    assert approved.current_status == "approved"
    revoked = document_service.revoke(reviewer, document.id, "superseded")
    assert revoked.current_status == "revoked"
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_documents/test_workflow.py -v`

Expected: FAIL because the document workflow service does not exist.

- [ ] **Step 3: Implement document workflow entities**

Create ORM models for `KnowledgeDocument`, `KnowledgeDocumentVersion`, `DocumentVisibleDepartment`, and `ReviewAction`. Use UUID string primary keys. The document stores `owner_department_id` and `visibility` (`department_only` or `shared_departments`). A version stores `display_name`, `storage_key`, `file_hash`, `status`, `created_by`, `last_edited_by`, `reviewed_by`, `published_at`, and `expires_at`. `DocumentVisibleDepartment` contains exact document and department foreign keys and is populated only for `shared_departments`; the owner department is always included by the service. Add a unique constraint on `(document_id, version_number)` and on `(document_id, department_id)`.

The service state machine must be explicit:

```python
ALLOWED_TRANSITIONS = {
    "draft": {"in_review"},
    "in_review": {"approved", "draft"},
    "approved": {"revoked", "expired"},
    "revoked": set(),
    "expired": set(),
}


def transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"invalid document transition: {current} -> {target}")
```

`approve()` must verify reviewer permission in the owner department, require a non-empty reason, reject `version.created_by == reviewer.user_id`, set approval fields, and call the indexing port only after the database transaction commits. `revoke()` sets the status and calls the index removal port; it never deletes the version row or original file.

Create the migration and repository methods used by the service. Keep SQLAlchemy statements inside the repository, not API routes.

- [ ] **Step 4: Run workflow tests**

Run: `pytest tests/test_documents/test_workflow.py -v`

Expected: all transition, separation-of-duty, and revoke tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/documents/models.py app/documents/repository.py app/documents/service.py migrations/versions/20260721_03_documents.py tests/test_documents/test_workflow.py
git commit -m "feat: add reviewed document workflow"
```

### Task 9: Replace Filename APIs With Document IDs

**Files:**
- Modify: `app/api/documents.py`
- Modify: `app/documents/file_safety.py`
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/stores/document.js`
- Modify: `frontend/src/views/DocumentsView.vue`
- Create: `tests/test_api/test_document_workflow.py`

- [ ] **Step 1: Write failing UUID route tests**

```python
def test_upload_returns_document_id(editor_client, sample_pdf):
    response = editor_client.post(
        "/api/v1/documents",
        data={"owner_department_id": "dept-a", "visibility": "department_only"},
        files={"file": ("manual.pdf", sample_pdf, "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["document_id"]
    assert response.json()["status"] == "draft"


def test_reader_cannot_upload(reader_client, sample_pdf):
    response = reader_client.post(
        "/api/v1/documents",
        data={"owner_department_id": "dept-a", "visibility": "department_only"},
        files={"file": ("manual.pdf", sample_pdf, "application/pdf")},
    )
    assert response.status_code == 403


def test_unknown_or_unauthorized_document_returns_404(reader_client):
    response = reader_client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_api/test_document_workflow.py -v`

Expected: FAIL with 404 for `POST /api/v1/documents`.

- [ ] **Step 3: Implement the UUID document API**

Expose the exact endpoints from the design spec. `POST /api/v1/documents` stores the original as `<document_id>/<version_id><validated_suffix>` and creates a draft without indexing. `approve` and `revoke` require a JSON body containing a non-empty `reason` and a recent-reauthentication claim.

Update frontend API signatures:

```javascript
export function uploadDocument(file, ownerDepartmentId, visibility = 'department_only') {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('owner_department_id', ownerDepartmentId)
  formData.append('visibility', visibility)
  return api.post('/api/v1/documents', formData)
}

export function approveDocument(documentId, reason) {
  return api.post(`/api/v1/documents/${documentId}/approve`, { reason })
}

export function revokeDocument(documentId, reason) {
  return api.post(`/api/v1/documents/${documentId}/revoke`, { reason })
}
```

Render status, owner department, version, editor, reviewer, and expiry fields in `DocumentsView.vue`. Hide editing actions the current principal lacks, while keeping server enforcement authoritative.

Keep old filename routes for one release. They must require `platform_admin`, emit `Deprecation: true` and `Sunset` headers, use Phase 0 path safety, and never appear in the frontend.

- [ ] **Step 4: Run API and frontend checks**

Run: `pytest tests/test_api/test_document_workflow.py -v && cd frontend && npm run build`

Expected: tests pass and Vite build exits 0.

- [ ] **Step 5: Commit**

```bash
git add app/api/documents.py app/documents/file_safety.py frontend/src/services/api.js frontend/src/stores/document.js frontend/src/views/DocumentsView.vue tests/test_api/test_document_workflow.py
git commit -m "feat: move document management to uuid workflow"
```

### Task 10: Add ACL Metadata to Chunks and Both Indexes

**Files:**
- Modify: `app/core/models.py`
- Create: `app/retrieval/access.py`
- Modify: `app/retrieval/milvus_store.py`
- Modify: `app/retrieval/keyword_store.py`
- Modify: `app/retrieval/hybrid_engine.py`
- Modify: `app/documents/sync.py`
- Create: `tests/test_retrieval/test_access_control.py`

- [ ] **Step 1: Write failing cross-department retrieval tests**

```python
from app.retrieval.access import RetrievalAccess


def test_department_a_never_receives_department_b_chunk(retrieval_engine, indexed_acl_chunks):
    results = retrieval_engine.search(
        "阿司匹林剂量",
        access=RetrievalAccess(user_id="user-a", department_ids=("dept-a",)),
    )
    assert results
    assert all("dept-a" in result.chunk.metadata.visible_department_ids for result in results)
    assert all(result.chunk.metadata.review_status == "approved" for result in results)


def test_unapproved_chunks_are_excluded(retrieval_engine, indexed_acl_chunks):
    results = retrieval_engine.search(
        "仅草稿中存在的词",
        access=RetrievalAccess(user_id="user-a", department_ids=("dept-a",)),
    )
    assert results == []
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_retrieval/test_access_control.py -v`

Expected: FAIL because retrieval has no access parameter or ACL metadata.

- [ ] **Step 3: Define access and chunk metadata**

Add fields to `ChunkMetadata`:

```python
    document_id: str = ""
    document_version_id: str = ""
    owner_department_id: str = ""
    visible_department_ids: tuple[str, ...] = field(default_factory=tuple)
    review_status: str = "draft"
    expires_at_epoch: int = 0
```

Create `app/retrieval/access.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalAccess:
    user_id: str
    department_ids: tuple[str, ...]

    def require_departments(self) -> tuple[str, ...]:
        if not self.department_ids:
            raise PermissionError("principal has no document scope")
        return self.department_ids
```

Store `document_version_id`, `review_status`, `expires_at_epoch`, and an `acl_departments` string formatted as `|uuid-1|uuid-2|` in Milvus. Build filter expressions only from validated UUID department IDs and the current UTC epoch:

```python
import uuid
from datetime import datetime, timezone


def build_access_filter(access: RetrievalAccess) -> str:
    values = [str(uuid.UUID(value)) for value in access.require_departments()]
    acl = " || ".join(f'acl_departments like "%|{value}|%"' for value in values)
    now = int(datetime.now(timezone.utc).timestamp())
    return f'review_status == "approved" && (expires_at_epoch == 0 || expires_at_epoch > {now}) && ({acl})'
```

Add `document_version_id`, `review_status`, `expires_at_epoch=NUMERIC(stored=True)`, and `department_ids=KEYWORD(commas=True, lowercase=True)` to Whoosh. Rebuild an incompatible existing index instead of opening it. Apply an OR of exact department terms, an exact approved-status term, and a numeric expiry range that includes zero and values later than the current epoch.

Pass the same `RetrievalAccess` into both stores. After RRF, assert every result is approved and intersects the allowed department set; raise `AuthorizationError` rather than silently returning an invalid result.

- [ ] **Step 4: Run retrieval tests**

Run: `pytest tests/test_retrieval -v`

Expected: all existing retrieval tests and new cross-department tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/core/models.py app/retrieval app/documents/sync.py tests/test_retrieval
git commit -m "feat: enforce acl in hybrid retrieval"
```

### Task 11: Scope Chat and Session History to the Principal

**Files:**
- Modify: `app/api/chat.py`
- Modify: `app/api/chat_routes.py`
- Modify: `app/core/models.py`
- Modify: `app/core/config.py`
- Create: `tests/test_api/test_chat_authorization.py`

- [ ] **Step 1: Write failing session ownership tests**

```python
def test_chat_requires_authentication(client):
    response = client.post("/api/v1/chat/complete?question=测试")
    assert response.status_code == 401


def test_user_cannot_read_another_users_session(user_a_client, user_b_session_id):
    response = user_a_client.get(f"/api/v1/chat/sessions/{user_b_session_id}")
    assert response.status_code == 404


def test_session_keys_are_user_scoped(orchestrator, principal_a, principal_b):
    first = orchestrator._session_key(principal_a, "session-1")
    second = orchestrator._session_key(principal_b, "session-1")
    assert first != second
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_api/test_chat_authorization.py -v`

Expected: public chat and cross-user sessions are still accessible.

- [ ] **Step 3: Thread principal and access through chat**

Add `user_id` and `department_ids` to `QaSession`. Change orchestrator entry points to:

```python
async def chat(self, question: str, principal: Principal) -> QaSession:
    access = RetrievalAccess(principal.user_id, principal.department_ids)
    search_results = self._retrieve(question, intent_result.category, access)
```

```python
async def chat_stream(self, question: str, principal: Principal) -> AsyncIterator[str]:
    access = RetrievalAccess(principal.user_id, principal.department_ids)
```

Use Redis keys `med_rag:session:<user_id>:<session_id>`. `list_sessions`, `get_session`, and `delete_session` require the principal and never scan another user's prefix. Remove local JSON session fallback in production; allow it only when `app.environment == "test"`.

Require `get_current_principal` on all chat routes and pass it into the orchestrator. Return 404 for a missing or foreign session.

- [ ] **Step 4: Run chat authorization tests**

Run: `pytest tests/test_api/test_chat_authorization.py tests/test_api/test_routes.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/chat.py app/api/chat_routes.py app/core/models.py app/core/config.py tests/test_api/test_chat_authorization.py tests/test_api/test_routes.py
git commit -m "feat: scope chat and history to users"
```

### Task 12: Add the Authenticated Frontend Flow

**Files:**
- Create: `frontend/src/stores/auth.js`
- Create: `frontend/src/views/LoginView.vue`
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/stores/auth.spec.js`
- Modify: `frontend/package.json`

- [ ] **Step 1: Add frontend test tooling and a failing auth store test**

Add `"test": "vitest run"` to scripts and `"vitest": "^2.1.0"` to dev dependencies.

```javascript
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth'

describe('auth store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('clears access state on logout', () => {
    const store = useAuthStore()
    store.accessToken = 'token'
    store.user = { username: 'reader' }
    store.clear()
    expect(store.accessToken).toBe('')
    expect(store.user).toBeNull()
  })
})
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend && npm install && npm test`

Expected: FAIL because `stores/auth.js` does not exist.

- [ ] **Step 3: Implement auth storage, interceptors, and route guard**

The auth store keeps the access token in memory only, calls `/auth/refresh` on application startup, and stores the CSRF token in `sessionStorage`. Axios adds the bearer token and performs exactly one refresh attempt after a 401.

Replace browser `EventSource`, which cannot attach an Authorization header, with a POST `fetch` stream:

```javascript
export async function chatStream(question, callbacks, signal) {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${useAuthStore().accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question }),
    signal,
  })
  if (!response.ok) throw new Error(`chat stream failed: ${response.status}`)
  await consumeSseStream(response.body, callbacks)
}
```

Implement `consumeSseStream` as a line-buffered parser that dispatches complete `event` and `data` pairs and never uses `eval`.

Add `/login` with `meta: { public: true }`; all other routes require an initialized authenticated store. Filter navigation items using permissions returned by `/auth/me`, and add an account menu with logout.

- [ ] **Step 4: Run frontend tests and build**

Run: `cd frontend && npm test && npm run build`

Expected: Vitest and Vite both exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src
git commit -m "feat: add authenticated frontend flow"
```

### Task 13: Add PostgreSQL Deployment and Bootstrap Administration

**Files:**
- Create: `scripts/create_admin.py`
- Modify: `docker-compose.yml`
- Modify: `Dockerfile`
- Modify: `deploy/start.sh`
- Modify: `.env.example`
- Modify: `README.md`
- Create: `tests/test_security/test_create_admin.py`

- [ ] **Step 1: Write a failing idempotent bootstrap test**

```python
from scripts.create_admin import create_admin


def test_create_admin_is_idempotent(session):
    first = create_admin(session, "admin", "Administrator Password 2026", "平台管理", "platform_admin")
    second = create_admin(session, "admin", "Administrator Password 2026", "平台管理", "platform_admin")
    assert first.id == second.id
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_security/test_create_admin.py -v`

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Implement bootstrap and deployment**

`create_admin()` creates or reuses the department and user, grants exactly one requested fixed role, hashes the password, and never prints the password. The CLI accepts the password only from `RAG_INITIAL_ADMIN_PASSWORD` and exits nonzero if it is shorter than 12 characters.

Add PostgreSQL 16 to Compose with a health check and persistent volume. Set:

```yaml
RAG_DATABASE_URL: postgresql+psycopg://med_rag:${POSTGRES_PASSWORD}@postgres:5432/med_rag
RAG_JWT_SECRET: ${RAG_JWT_SECRET}
```

Run `alembic upgrade head` before uvicorn in `deploy/start.sh`. Remove the Phase 0 bootstrap key after all clients use JWT. Document key generation, initial administrator creation, migration, backup, and restore commands in `README.md`.

- [ ] **Step 4: Run deployment verification**

Run: `pytest tests/test_security/test_create_admin.py -v && docker compose config`

Expected: test passes and Compose renders with PostgreSQL health dependencies.

- [ ] **Step 5: Commit**

```bash
git add scripts/create_admin.py docker-compose.yml Dockerfile deploy/start.sh .env.example README.md tests/test_security/test_create_admin.py
git commit -m "feat: deploy postgres backed identity service"
```

### Task 14: Run the Identity and Isolation Release Gate

**Files:**
- Modify: `tests/test_smoke.py`
- Create: `tests/test_api/test_department_isolation.py`

- [ ] **Step 1: Add a complete department isolation scenario**

Create two departments, one reader per department, one approved document per department, and one shared approved document. Assert through HTTP that each reader sees its own and shared documents, cannot infer the other private document through list, chat, source preview, session history, 404 differences, or result counts.

The final assertions must include:

```python
assert "dept-b-private" not in response.text
assert "dept-b-private.pdf" not in response.text
assert all(source["document_id"] in allowed_document_ids for source in response.json()["sources"])
```

- [ ] **Step 2: Run migration and backend checks**

Run: `alembic upgrade head && ruff check app tests scripts && pytest tests/ -v`

Expected: all commands exit 0.

- [ ] **Step 3: Run frontend checks**

Run: `cd frontend && npm test && npm run build`

Expected: all commands exit 0.

- [ ] **Step 4: Verify authorization fail-closed behavior**

Stop PostgreSQL in the integration environment and request `/api/v1/chat/sessions` with a previously valid Access Token.

Expected: `503` with code `AUTHORIZATION_SERVICE_UNAVAILABLE`; no session or document metadata appears in the body.

- [ ] **Step 5: Commit the release gate**

```bash
git add tests/test_smoke.py tests/test_api/test_department_isolation.py
git commit -m "test: gate department data isolation"
```

## Completion Criteria

- All protected APIs require a valid user identity.
- Fixed roles are scoped to department memberships and are reloaded from PostgreSQL per request.
- Documents are UUID-addressed, versioned, reviewed, and indexed only after approval.
- Milvus and Whoosh exclude unauthorized and unapproved chunks before fusion.
- A post-fusion authorization assertion prevents invalid context from reaching the LLM.
- Session history is user-scoped.
- PostgreSQL failure produces 503 and no protected data.
- Authentication, backend, frontend, migration, and department isolation suites pass.
