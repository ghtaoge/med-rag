"""跨测试模块共享的安全依赖覆盖。"""

import pytest

from app.main import app
from app.security.bootstrap_auth import verify_bootstrap_admin


@pytest.fixture(autouse=True)
def allow_test_management_access():
    """旧测试关注业务行为，Bootstrap 本身由独立测试覆盖。"""

    app.dependency_overrides[verify_bootstrap_admin] = lambda: None
    yield
    app.dependency_overrides.pop(verify_bootstrap_admin, None)
