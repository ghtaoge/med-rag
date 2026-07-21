"""跨测试模块共享的安全依赖覆盖。"""

import pytest

from app.main import app
from app.security.models import Role
from app.security.principal import Principal, PrincipalMembership, get_current_principal


@pytest.fixture(autouse=True)
def allow_test_management_access():
    """旧测试关注业务行为，Bootstrap 本身由独立测试覆盖。"""

    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id="test-user",
        username="test-user",
        memberships=tuple(
            PrincipalMembership("4b413c1d-625e-4ef5-956d-95900f7e4674", role)
            for role in Role
        ),
        session_id="test-session",
    )
    yield
    app.dependency_overrides.pop(get_current_principal, None)
