from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.security.database import Base
from app.security.models import new_id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParseJobStatus(str, enum.Enum):
    QUARANTINED = "quarantined"
    SCANNING = "scanning"
    PARSING = "parsing"
    READY_FOR_REVIEW = "ready_for_review"
    INFECTED = "infected"
    FAILED = "failed"


ALLOWED_JOB_TRANSITIONS = {
    ParseJobStatus.QUARANTINED: {
        ParseJobStatus.SCANNING,
        ParseJobStatus.FAILED,
    },
    ParseJobStatus.SCANNING: {
        ParseJobStatus.PARSING,
        ParseJobStatus.INFECTED,
        ParseJobStatus.FAILED,
    },
    ParseJobStatus.PARSING: {
        ParseJobStatus.READY_FOR_REVIEW,
        ParseJobStatus.FAILED,
    },
    ParseJobStatus.READY_FOR_REVIEW: set(),
    ParseJobStatus.INFECTED: set(),
    ParseJobStatus.FAILED: set(),
}


def transition_job(current: ParseJobStatus, target: ParseJobStatus) -> None:
    if target not in ALLOWED_JOB_TRANSITIONS[current]:
        raise ValueError(
            f"invalid parse job transition: {current.value} -> {target.value}"
        )


class ParseJob(Base):
    __tablename__ = "parse_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_document_versions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    quarantine_storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    parsed_storage_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[ParseJobStatus] = mapped_column(
        Enum(ParseJobStatus, native_enum=False), index=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    parser_name: Mapped[str | None] = mapped_column(String(128))
    parser_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


def is_releaseable(job: ParseJob | None) -> bool:
    return bool(
        job
        and job.status == ParseJobStatus.READY_FOR_REVIEW
        and job.parsed_storage_key
    )
