"""知识文档持久化查询。"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.documents.models import (
    DocumentVisibleDepartment,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    ReviewStatus,
)


class DocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        return self.session.get(KnowledgeDocument, document_id)

    def get_version(self, version_id: str) -> KnowledgeDocumentVersion | None:
        return self.session.get(KnowledgeDocumentVersion, version_id)

    def current_version(self, document_id: str) -> KnowledgeDocumentVersion | None:
        statement = (
            select(KnowledgeDocumentVersion)
            .where(KnowledgeDocumentVersion.document_id == document_id)
            .order_by(KnowledgeDocumentVersion.version_number.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def next_version_number(self, document_id: str) -> int:
        value = self.session.scalar(
            select(func.max(KnowledgeDocumentVersion.version_number)).where(
                KnowledgeDocumentVersion.document_id == document_id
            )
        )
        return int(value or 0) + 1

    def visible_department_ids(self, document_id: str) -> tuple[str, ...]:
        statement = select(DocumentVisibleDepartment.department_id).where(
            DocumentVisibleDepartment.document_id == document_id
        )
        return tuple(self.session.scalars(statement))

    def is_visible(self, document: KnowledgeDocument, department_ids: tuple[str, ...]) -> bool:
        if document.owner_department_id in department_ids:
            return True
        if not department_ids:
            return False
        statement = select(DocumentVisibleDepartment.id).where(
            DocumentVisibleDepartment.document_id == document.id,
            DocumentVisibleDepartment.department_id.in_(department_ids),
        )
        return self.session.scalar(statement) is not None

    def list_visible(self, department_ids: tuple[str, ...]) -> list[tuple[KnowledgeDocument, KnowledgeDocumentVersion]]:
        if not department_ids:
            return []
        shared_documents = select(DocumentVisibleDepartment.document_id).where(
            DocumentVisibleDepartment.department_id.in_(department_ids)
        )
        statement = (
            select(KnowledgeDocument, KnowledgeDocumentVersion)
            .join(
                KnowledgeDocumentVersion,
                KnowledgeDocumentVersion.document_id == KnowledgeDocument.id,
            )
            .where(
                KnowledgeDocumentVersion.version_number
                == select(func.max(KnowledgeDocumentVersion.version_number))
                .where(KnowledgeDocumentVersion.document_id == KnowledgeDocument.id)
                .correlate(KnowledgeDocument)
                .scalar_subquery(),
                or_(
                    KnowledgeDocument.owner_department_id.in_(department_ids),
                    KnowledgeDocument.id.in_(shared_documents),
                ),
            )
            .order_by(KnowledgeDocumentVersion.created_at.desc())
        )
        return list(self.session.execute(statement).tuples())

    def active_versions(self) -> list[KnowledgeDocumentVersion]:
        statement = select(KnowledgeDocumentVersion).where(
            KnowledgeDocumentVersion.status == ReviewStatus.APPROVED
        )
        return list(self.session.scalars(statement))
