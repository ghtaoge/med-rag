"""Immutable authorization scope used by every retrieval backend."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.exceptions import AuthorizationError
from app.core.models import SearchResult


@dataclass(frozen=True)
class RetrievalAccess:
    user_id: str
    department_ids: tuple[str, ...]

    def validated_department_ids(self) -> tuple[str, ...]:
        if not self.department_ids:
            raise AuthorizationError("当前账号没有可检索的部门范围")
        try:
            return tuple(str(uuid.UUID(value)) for value in self.department_ids)
        except (ValueError, AttributeError) as exc:
            raise AuthorizationError("检索权限范围无效") from exc


def build_milvus_access_filter(access: RetrievalAccess) -> str:
    values = access.validated_department_ids()
    acl = " || ".join(
        f'acl_departments like "%|{department_id}|%"'
        for department_id in values
    )
    now = int(datetime.now(timezone.utc).timestamp())
    return (
        'review_status == "approved" && '
        f"(expires_at_epoch == 0 || expires_at_epoch > {now}) && ({acl})"
    )


def assert_authorized_results(
    results: list[SearchResult],
    access: RetrievalAccess,
) -> list[SearchResult]:
    allowed = set(access.validated_department_ids())
    now = int(datetime.now(timezone.utc).timestamp())
    for result in results:
        metadata = result.chunk.metadata
        visible = set(metadata.visible_department_ids)
        if (
            metadata.review_status != "approved"
            or not visible.intersection(allowed)
            or (metadata.expires_at_epoch != 0 and metadata.expires_at_epoch <= now)
        ):
            raise AuthorizationError("检索结果未通过授权校验")
    return results
