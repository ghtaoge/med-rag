"""受控知识文档、版本、可见部门与审核动作。"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.security.database import Base
from app.security.models import new_id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentVisibility(str, enum.Enum):
    DEPARTMENT_ONLY = "department_only"
    SHARED_DEPARTMENTS = "shared_departments"


class ReviewStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    EXPIRED = "expired"
    REVOKED = "revoked"


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_department_id: Mapped[str] = mapped_column(
        ForeignKey("departments.id"), index=True
    )
    visibility: Mapped[DocumentVisibility] = mapped_column(
        Enum(DocumentVisibility, native_enum=False)
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeDocumentVersion(Base):
    __tablename__ = "knowledge_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    display_name: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    file_hash: Mapped[str] = mapped_column(String(64))
    extension: Mapped[str] = mapped_column(String(32))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False), index=True
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    last_edited_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVisibleDepartment(Base):
    __tablename__ = "document_visible_departments"
    __table_args__ = (
        UniqueConstraint("document_id", "department_id", name="uq_document_department"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    department_id: Mapped[str] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), index=True
    )


class ReviewAction(Base):
    __tablename__ = "review_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_document_versions.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
