import uuid

import pytest

from app.core.models import ChunkMetadata, DocumentChunk, SearchResult
from app.safety.output import (
    OutputBlocked,
    SafeStreamBuffer,
    sanitize_complete_output,
    validate_output_sources,
)
from app.security.models import Role
from app.security.principal import Principal, PrincipalMembership

DEPARTMENT_ID = str(uuid.uuid4())


def _principal():
    return Principal(
        "user-a",
        "user-a",
        (PrincipalMembership(DEPARTMENT_ID, Role.READER),),
        "session-a",
    )


def _source(departments=(DEPARTMENT_ID,), status="approved"):
    return SearchResult(
        DocumentChunk(
            "chunk-1",
            "version.txt",
            "安全医学说明",
            metadata=ChunkMetadata(
                document_id=str(uuid.uuid4()),
                document_version_id=str(uuid.uuid4()),
                visible_department_ids=departments,
                review_status=status,
            ),
        ),
        0.9,
    )


def test_stream_never_releases_split_secret():
    buffer = SafeStreamBuffer(buffer_chars=512)
    assert buffer.feed("Authorization: Bearer abcdefghijk") == ""
    with pytest.raises(OutputBlocked):
        buffer.feed("lmnopqrstuvwxyz123456")


def test_safe_stream_releases_text_after_holdback():
    buffer = SafeStreamBuffer(buffer_chars=512)
    released = buffer.feed("安全医学说明" * 100)
    assert released
    assert buffer.finalize()


def test_source_authorization_is_rechecked():
    with pytest.raises(OutputBlocked):
        validate_output_sources(_principal(), [_source((str(uuid.uuid4()),))])
    with pytest.raises(OutputBlocked):
        validate_output_sources(_principal(), [_source(status="draft")])


def test_complete_output_redacts_pii_and_blocks_secret():
    answer, _ = sanitize_complete_output(
        "联系电话 13812345678", [_source()], _principal()
    )
    assert "13812345678" not in answer
    with pytest.raises(OutputBlocked):
        sanitize_complete_output(
            "Bearer abcdefghijklmnopqrstuvwxyz123456",
            [_source()],
            _principal(),
        )
