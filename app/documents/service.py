"""文档草稿、审核、发布和撤回状态机。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import (
    AuthorizationError,
    DocumentNotParsed,
    NotFoundError,
    ValidationError,
)
from app.documents.job_repository import ParseJobRepository
from app.documents.jobs import is_releaseable
from app.documents.models import (
    DocumentVisibility,
    DocumentVisibleDepartment,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    ReviewAction,
    ReviewStatus,
)
from app.documents.repository import DocumentRepository
from app.security.audit import AuditAction, AuditService
from app.security.permissions import Permission, ensure_permission
from app.security.principal import Principal


class DocumentWorkflowService:
    ALLOWED_TRANSITIONS = {
        ReviewStatus.DRAFT: {ReviewStatus.IN_REVIEW},
        ReviewStatus.IN_REVIEW: {ReviewStatus.APPROVED, ReviewStatus.DRAFT},
        ReviewStatus.APPROVED: {ReviewStatus.REVOKED, ReviewStatus.EXPIRED},
        ReviewStatus.REVOKED: set(),
        ReviewStatus.EXPIRED: set(),
    }

    def __init__(self, session: Session):
        self.session = session
        self.repository = DocumentRepository(session)
        self.audit = AuditService(session)

    def create_draft(
        self,
        principal: Principal,
        document_id: str,
        version_id: str,
        owner_department_id: str,
        visibility: DocumentVisibility,
        visible_department_ids: tuple[str, ...],
        display_name: str,
        storage_key: str,
        file_hash: str,
        extension: str,
        size: int,
        expires_at: datetime | None,
        request_id: str,
        commit: bool = True,
    ) -> tuple[KnowledgeDocument, KnowledgeDocumentVersion]:
        ensure_permission(principal, Permission.DOCUMENT_EDIT, owner_department_id)
        document = KnowledgeDocument(
            id=document_id,
            owner_department_id=owner_department_id,
            visibility=visibility,
            created_by=principal.user_id,
        )
        version = KnowledgeDocumentVersion(
            id=version_id,
            document_id=document.id,
            version_number=1,
            display_name=display_name,
            storage_key=storage_key,
            file_hash=file_hash,
            extension=extension,
            size=size,
            status=ReviewStatus.DRAFT,
            created_by=principal.user_id,
            last_edited_by=principal.user_id,
            expires_at=expires_at,
        )
        self.session.add_all([document, version])
        departments = {owner_department_id}
        if visibility == DocumentVisibility.SHARED_DEPARTMENTS:
            departments.update(visible_department_ids)
        for department_id in departments:
            self.session.add(
                DocumentVisibleDepartment(
                    document_id=document.id,
                    department_id=department_id,
                )
            )
        self.audit.record(
            principal.user_id,
            AuditAction.DOCUMENT_CREATED,
            "document",
            document.id,
            "success",
            "document uploaded as draft",
            request_id,
            after_state={"status": ReviewStatus.DRAFT.value},
        )
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return document, version

    def submit_review(
        self,
        principal: Principal,
        document_id: str,
        reason: str,
        request_id: str,
    ) -> KnowledgeDocumentVersion:
        document = self._visible_document(principal, document_id)
        ensure_permission(principal, Permission.DOCUMENT_EDIT, document.owner_department_id)
        version = self._current_version(document_id)
        parse_job = ParseJobRepository(self.session).for_version(version.id)
        if not is_releaseable(parse_job):
            raise DocumentNotParsed()
        self._transition(version, ReviewStatus.IN_REVIEW)
        self._review(version, principal, "submit", reason)
        self.audit.record(
            principal.user_id,
            AuditAction.DOCUMENT_SUBMITTED,
            "document_version",
            version.id,
            "success",
            reason,
            request_id,
            {"status": ReviewStatus.DRAFT.value},
            {"status": ReviewStatus.IN_REVIEW.value},
        )
        self.session.commit()
        return version

    def approve(
        self,
        principal: Principal,
        document_id: str,
        reason: str,
        request_id: str,
    ) -> KnowledgeDocumentVersion:
        document = self._visible_document(principal, document_id)
        ensure_permission(principal, Permission.DOCUMENT_APPROVE, document.owner_department_id)
        version = self._current_version(document_id)
        if not is_releaseable(
            ParseJobRepository(self.session).for_version(version.id)
        ):
            raise DocumentNotParsed()
        if version.status != ReviewStatus.IN_REVIEW:
            raise ValidationError("文档尚未进入审核状态")
        if version.last_edited_by == principal.user_id:
            raise AuthorizationError("审核人不能批准自己编辑的版本")
        self._transition(version, ReviewStatus.APPROVED)
        version.reviewed_by = principal.user_id
        version.published_at = datetime.now(timezone.utc)
        self._review(version, principal, "approve", reason)
        self.audit.record(
            principal.user_id,
            AuditAction.DOCUMENT_APPROVED,
            "document_version",
            version.id,
            "success",
            reason,
            request_id,
            {"status": ReviewStatus.IN_REVIEW.value},
            {"status": ReviewStatus.APPROVED.value},
        )
        self.session.commit()
        return version

    def revoke(
        self,
        principal: Principal,
        document_id: str,
        reason: str,
        request_id: str,
    ) -> KnowledgeDocumentVersion:
        document = self._visible_document(principal, document_id)
        ensure_permission(principal, Permission.DOCUMENT_APPROVE, document.owner_department_id)
        version = self._current_version(document_id)
        self._transition(version, ReviewStatus.REVOKED)
        self._review(version, principal, "revoke", reason)
        self.audit.record(
            principal.user_id,
            AuditAction.DOCUMENT_REVOKED,
            "document_version",
            version.id,
            "success",
            reason,
            request_id,
            {"status": ReviewStatus.APPROVED.value},
            {"status": ReviewStatus.REVOKED.value},
        )
        self.session.commit()
        return version

    def _visible_document(self, principal: Principal, document_id: str) -> KnowledgeDocument:
        document = self.repository.get_document(document_id)
        if document is None or not self.repository.is_visible(
            document, principal.department_ids
        ):
            raise NotFoundError("文档不存在")
        return document

    def _current_version(self, document_id: str) -> KnowledgeDocumentVersion:
        version = self.repository.current_version(document_id)
        if version is None:
            raise NotFoundError("文档不存在")
        return version

    def _transition(
        self,
        version: KnowledgeDocumentVersion,
        target: ReviewStatus,
    ) -> None:
        if target not in self.ALLOWED_TRANSITIONS[version.status]:
            raise ValidationError(
                f"非法文档状态转换: {version.status.value} -> {target.value}"
            )
        version.status = target

    def _review(
        self,
        version: KnowledgeDocumentVersion,
        principal: Principal,
        action: str,
        reason: str,
    ) -> None:
        if not reason.strip():
            raise ValidationError("操作原因不能为空")
        self.session.add(
            ReviewAction(
                document_version_id=version.id,
                actor_user_id=principal.user_id,
                action=action,
                reason=reason.strip(),
            )
        )
