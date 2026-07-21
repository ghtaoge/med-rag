"""Phase 0 临时管理鉴权。

Phase 1 的用户身份与部门 RBAC 上线后删除该模块。
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException

from app.core.dependencies import get_config_dep


def verify_bootstrap_admin(
    x_med_rag_admin_key: str | None = Header(default=None),
    config: dict = Depends(get_config_dep),
) -> None:
    expected = config["security"]["bootstrap_admin_key"]
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="管理认证尚未配置")
    if x_med_rag_admin_key is None or not hmac.compare_digest(
        x_med_rag_admin_key, expected
    ):
        raise HTTPException(status_code=401, detail="管理认证失败")
