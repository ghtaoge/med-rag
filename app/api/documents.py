"""文档管理路由 — 上传/同步/校验/列表。"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_config_dep,
    get_document_sync,
    get_document_validator,
    get_db_session,
    get_document_storage,
    get_parse_queue,
)
from app.core.exceptions import (
    DocumentError,
    FileSecurityError,
    MedRagError,
    NotFoundError,
    LegacyEndpointRetired,
    ParseQueueUnavailable,
    ValidationError,
)
from app.core.models import ChunkMetadata
from app.documents.models import DocumentVisibility, KnowledgeDocumentVersion, ReviewStatus
from app.documents.repository import DocumentRepository
from app.documents.service import DocumentWorkflowService
from app.documents.job_repository import ParseJobRepository
from app.documents.jobs import ParseJob, ParseJobStatus, is_releaseable
from app.documents.queue import ParseQueue
from app.documents.storage import DocumentStorage
from app.documents.file_safety import (
    inspect_upload_envelope,
    resolve_child,
    validate_client_filename,
)
from app.documents.sync import DocumentSync
from app.documents.validator import DocumentValidator
from app.documents.index_state import load_index_state, remove_index_state
from app.security.permissions import Permission, ensure_permission, permission_dependency
from app.security.principal import (
    Principal,
    get_current_principal,
    get_reauthenticated_principal,
)

router = APIRouter(prefix="/api/v1/documents", tags=["文档管理"])


class ReviewRequest(BaseModel):
    reason: str


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID", uuid.uuid4().hex)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _version_payload(
    document,
    version,
    visible_department_ids: tuple[str, ...],
    parse_job: ParseJob | None = None,
) -> dict:
    return {
        "document_id": document.id,
        "version_id": version.id,
        "version_number": version.version_number,
        "display_name": version.display_name,
        "owner_department_id": document.owner_department_id,
        "visibility": document.visibility.value,
        "visible_department_ids": visible_department_ids,
        "status": version.status.value,
        "created_by": version.created_by,
        "last_edited_by": version.last_edited_by,
        "reviewed_by": version.reviewed_by,
        "size": version.size,
        "extension": version.extension,
        "created_at": version.created_at,
        "published_at": version.published_at,
        "expires_at": version.expires_at,
        "parse_job_id": parse_job.id if parse_job else None,
        "processing_status": parse_job.status.value if parse_job else None,
        "processing_error_code": parse_job.error_code if parse_job else None,
    }


def _parse_visible_departments(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return ()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = [item.strip() for item in raw.split(",") if item.strip()]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValidationError("visible_department_ids 必须是部门 ID 数组")
    return tuple(dict.fromkeys(value))


def _index_approved_version(
    sync: DocumentSync,
    config: dict,
    repository: DocumentRepository,
    document,
    version: KnowledgeDocumentVersion,
) -> int:
    parse_job = ParseJobRepository(repository.session).for_version(version.id)
    if not is_releaseable(parse_job):
        from app.core.exceptions import DocumentNotParsed

        raise DocumentNotParsed()
    storage = DocumentStorage(Path(config["storage"]["root"]))
    visible_departments = repository.visible_department_ids(document.id)
    expires_at_epoch = int(version.expires_at.timestamp()) if version.expires_at else 0
    return sync.sync_managed_version(
        storage.resolve(parse_job.parsed_storage_key),
        version.storage_key,
        ChunkMetadata(
            source=version.storage_key,
            document_id=document.id,
            document_version_id=version.id,
            owner_department_id=document.owner_department_id,
            visible_department_ids=visible_departments,
            review_status=ReviewStatus.APPROVED.value,
            expires_at_epoch=expires_at_epoch,
        ),
    )


@router.post("", status_code=202)
async def create_document(
    request: Request,
    file: UploadFile = File(..., description="上传文件"),
    owner_department_id: str = Form(...),
    visibility: DocumentVisibility = Form(DocumentVisibility.DEPARTMENT_ONLY),
    visible_department_ids: str = Form(""),
    expires_at: datetime | None = Form(None),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    config: dict = Depends(get_config_dep),
    storage: DocumentStorage = Depends(get_document_storage),
    queue: ParseQueue = Depends(get_parse_queue),
):
    """Store an opaque quarantine object and enqueue isolated parsing."""

    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    filename = validate_client_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    storage_key = storage.allocate_quarantine_key(
        document_id, version_id, suffix
    )
    destination = storage.resolve(storage_key)
    job_id = str(uuid.uuid4())
    try:
        _, stored_path = await _save_bounded_upload(
            file,
            destination.parent,
            config.get("security", {}).get("max_upload_bytes", 50 * 1024 * 1024),
            destination_name=destination.name,
        )
        file_hash = _file_sha256(stored_path)
        workflow = DocumentWorkflowService(session)
        document, version = workflow.create_draft(
            principal=principal,
            document_id=document_id,
            version_id=version_id,
            owner_department_id=owner_department_id,
            visibility=visibility,
            visible_department_ids=_parse_visible_departments(visible_department_ids),
            display_name=filename,
            storage_key=storage_key,
            file_hash=file_hash,
            extension=suffix,
            size=stored_path.stat().st_size,
            expires_at=expires_at,
            request_id=_request_id(request),
            commit=False,
        )
        parse_job = ParseJob(
            id=job_id,
            document_id=document_id,
            document_version_id=version_id,
            quarantine_storage_key=storage_key,
            status=ParseJobStatus.QUARANTINED,
        )
        ParseJobRepository(session).create(parse_job)
        session.commit()
        try:
            queue.submit(job_id)
        except Exception as exc:
            ParseJobRepository(session).transition(
                job_id,
                ParseJobStatus.FAILED,
                error_code="PARSE_QUEUE_UNAVAILABLE",
            )
            raise ParseQueueUnavailable() from exc
    except MedRagError:
        if session.get(ParseJob, job_id) is None:
            destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if session.get(ParseJob, job_id) is None:
            destination.unlink(missing_ok=True)
        raise DocumentError("创建文档草稿失败") from exc
    repository = DocumentRepository(session)
    return _version_payload(
        document,
        version,
        repository.visible_department_ids(document.id),
        ParseJobRepository(session).for_version(version.id),
    )


@router.get("")
def list_managed_documents(
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    repository = DocumentRepository(session)
    rows = repository.list_visible(principal.department_ids)
    return {
        "documents": [
            _version_payload(
                document,
                version,
                repository.visible_department_ids(document.id),
                ParseJobRepository(session).for_version(version.id),
            )
            for document, version in rows
        ]
    }


async def _save_bounded_upload(
    file: UploadFile,
    directory: Path,
    max_bytes: int,
    *,
    destination_name: str | None = None,
) -> tuple[str, Path]:
    """将上传流写入同目录临时文件，检查后再原子替换。"""

    filename = validate_client_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    directory.mkdir(parents=True, exist_ok=True)
    final_name = destination_name or filename
    destination = resolve_child(directory, final_name)
    temporary = resolve_child(directory, f".upload-{uuid.uuid4().hex}{suffix}")
    written = 0
    try:
        with temporary.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise FileSecurityError("文件大小超过限制")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        inspect_upload_envelope(temporary, file.content_type)
        os.replace(temporary, destination)
        return filename, destination
    finally:
        temporary.unlink(missing_ok=True)


@router.post(
    "/upload",
    dependencies=[Depends(permission_dependency(Permission.PLATFORM_CONFIG))],
)
async def upload_document(
    response: Response,
    file: UploadFile = File(..., description="上传文件"),
    config: dict = Depends(get_config_dep),
    validator: DocumentValidator = Depends(get_document_validator),
    sync: DocumentSync = Depends(get_document_sync),
):
    """上传文档 → 校验 → 保存 → 自动同步索引。"""

    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    raise LegacyEndpointRetired()

    knowledge_dir = Path(config["knowledge_dir"])
    filename = validate_client_filename(file.filename)
    dest_path = resolve_child(knowledge_dir, filename)

    # 检查文件名冲突
    if dest_path.exists():
        raise ValidationError(f"文件已存在: {file.filename}")

    try:
        _, dest_path = await _save_bounded_upload(
            file,
            knowledge_dir,
            config.get("security", {}).get("max_upload_bytes", 50 * 1024 * 1024),
        )
    except FileSecurityError:
        raise
    except Exception as e:
        raise DocumentError("保存文件失败") from e

    # 校验
    result = validator.validate(dest_path)
    if not result.is_valid:
        # 校验失败 → 删除文件
        dest_path.unlink(missing_ok=True)
        return {
            "status": "rejected",
            "errors": result.errors,
            "warnings": result.warnings,
        }

    try:
        # 上传成功后立即同步当前文件，前端无需再手动点击“同步”。
        # force=True 用于覆盖旧索引状态，保证 Excel 等同名内容更新后能马上进入索引。
        chunk_count = sync.sync_file(filename, force=True)
    except Exception as e:
        # 文件已保存但索引失败时保留原文件，方便用户修正索引服务后再次单文件同步。
        raise DocumentError("文件已保存，但同步索引失败") from e

    return {
        "status": "accepted",
        "filename": filename,
        "chunk_count": chunk_count,
        "in_index": chunk_count > 0,
        "errors": result.errors,
        "warnings": result.warnings,
    }


@router.post(
    "/sync",
    dependencies=[Depends(permission_dependency(Permission.PLATFORM_CONFIG))],
)
async def sync_all_documents(
    response: Response,
    sync: DocumentSync = Depends(get_document_sync),
):
    """全量同步所有变更文件。"""

    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    raise LegacyEndpointRetired()

    # 先把变更列表返回给前端展示，再执行实际同步。
    # sync_all 内部仍会按当前文件状态重新计算，保证返回的 chunk 数以最终索引为准。
    changes = sync.detect_changes()
    total = sync.sync_all()

    return {
        "total_chunks": total,
        "changes": [
            {
                "filename": c.filename,
                "change_type": c.change_type,
            }
            for c in changes
        ],
    }


@router.post(
    "/sync/{filename}",
    dependencies=[Depends(permission_dependency(Permission.PLATFORM_CONFIG))],
)
async def sync_single_document(
    filename: str,
    response: Response,
    sync: DocumentSync = Depends(get_document_sync),
):
    """同步单个文件。"""

    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    raise LegacyEndpointRetired()

    filename = validate_client_filename(filename)
    try:
        chunk_count = sync.sync_file(filename)
    except Exception as e:
        raise DocumentError("同步文件失败") from e

    return {
        "filename": filename,
        "chunk_count": chunk_count,
    }


@router.post(
    "/validate",
    dependencies=[Depends(permission_dependency(Permission.PLATFORM_CONFIG))],
)
async def validate_document(
    response: Response,
    file: UploadFile = File(..., description="待校验文件"),
    config: dict = Depends(get_config_dep),
    validator: DocumentValidator = Depends(get_document_validator),
):
    """校验文档（不入库，只检查）。"""

    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    raise LegacyEndpointRetired()

    knowledge_dir = Path(config["knowledge_dir"])
    filename = validate_client_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    temp_name = f".validate-{uuid.uuid4().hex}{suffix}"

    try:
        _, temp_path = await _save_bounded_upload(
            file,
            knowledge_dir,
            config.get("security", {}).get("max_upload_bytes", 50 * 1024 * 1024),
            destination_name=temp_name,
        )

        result = validator.validate(temp_path)

        return {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
        }
    finally:
        resolve_child(knowledge_dir, temp_name).unlink(missing_ok=True)


@router.get("/jobs/{job_id}")
def get_parse_job(
    job_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    job = ParseJobRepository(session).get(job_id)
    if job is None:
        raise NotFoundError("处理任务不存在")
    document_repository = DocumentRepository(session)
    document = document_repository.get_document(job.document_id)
    if document is None or not document_repository.is_visible(
        document, principal.department_ids
    ):
        raise NotFoundError("处理任务不存在")
    return {
        "id": job.id,
        "document_id": job.document_id,
        "version_id": job.document_version_id,
        "status": job.status.value,
        "error_code": job.error_code,
        "parser_name": job.parser_name,
        "parser_version": job.parser_version,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


@router.get(
    "/list",
    dependencies=[Depends(permission_dependency(Permission.PLATFORM_CONFIG))],
)
async def list_documents(
    response: Response,
    config: dict = Depends(get_config_dep),
):
    """列出知识库中的所有文档及其 chunk 状态。"""

    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"

    knowledge_dir = Path(config["knowledge_dir"])

    # 索引状态文件记录每个文件最近一次同步得到的 chunk 数。
    # 列表页直接读取这个状态，避免每次刷新都去扫 Milvus 或重新解析大文件。
    index_state = load_index_state(knowledge_dir)
    documents = []
    for file_path in sorted(knowledge_dir.glob("*")):
        if not file_path.is_file():
            continue

        from app.documents.loader import supported_extensions
        if file_path.suffix.lower() not in supported_extensions():
            continue

        state = index_state.get(file_path.name, {})
        chunk_count = int(state.get("chunk_count") or 0)
        documents.append({
            "filename": file_path.name,
            "size": file_path.stat().st_size,
            "extension": file_path.suffix.lower(),
            "chunk_count": chunk_count,
            "in_index": chunk_count > 0,
        })

    return {
        "total_files": len(documents),
        "total_chunks": sum(doc["chunk_count"] for doc in documents),
        "documents": documents,
    }


@router.delete(
    "/{filename}",
    dependencies=[Depends(permission_dependency(Permission.PLATFORM_CONFIG))],
)
async def delete_document(
    filename: str,
    response: Response,
    config: dict = Depends(get_config_dep),
):
    """从知识库删除文档（文件 + 索引）。"""

    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"

    knowledge_dir = Path(config["knowledge_dir"])
    filename = validate_client_filename(filename)
    file_path = resolve_child(knowledge_dir, filename)

    # 删除文件
    if file_path.exists():
        file_path.unlink()
        remove_index_state(knowledge_dir, filename)
    else:
        raise ValidationError(f"文件不存在: {filename}")


    return {
        "deleted": True,
        "filename": filename,
    }


@router.get("/{document_id}")
def get_managed_document(
    document_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    repository = DocumentRepository(session)
    document = repository.get_document(document_id)
    if document is None or not repository.is_visible(document, principal.department_ids):
        raise NotFoundError("文档不存在")
    version = repository.current_version(document_id)
    if version is None:
        raise NotFoundError("文档不存在")
    return _version_payload(
        document,
        version,
        repository.visible_department_ids(document.id),
        ParseJobRepository(session).for_version(version.id),
    )


@router.post("/{document_id}/submit-review")
def submit_document_review(
    document_id: str,
    payload: ReviewRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    version = DocumentWorkflowService(session).submit_review(
        principal, document_id, payload.reason, _request_id(request)
    )
    document = DocumentRepository(session).get_document(document_id)
    return _version_payload(
        document,
        version,
        DocumentRepository(session).visible_department_ids(document_id),
        ParseJobRepository(session).for_version(version.id),
    )


@router.post("/{document_id}/approve")
def approve_document(
    document_id: str,
    payload: ReviewRequest,
    request: Request,
    principal: Principal = Depends(get_reauthenticated_principal),
    session: Session = Depends(get_db_session),
    config: dict = Depends(get_config_dep),
    sync: DocumentSync = Depends(get_document_sync),
):
    workflow = DocumentWorkflowService(session)
    version = workflow.approve(
        principal, document_id, payload.reason, _request_id(request)
    )
    repository = DocumentRepository(session)
    document = repository.get_document(document_id)
    chunk_count = _index_approved_version(
        sync, config, repository, document, version
    )
    response = _version_payload(
        document,
        version,
        repository.visible_department_ids(document_id),
        ParseJobRepository(session).for_version(version.id),
    )
    response["chunk_count"] = chunk_count
    return response


@router.post("/{document_id}/revoke")
def revoke_document(
    document_id: str,
    payload: ReviewRequest,
    request: Request,
    principal: Principal = Depends(get_reauthenticated_principal),
    session: Session = Depends(get_db_session),
    sync: DocumentSync = Depends(get_document_sync),
):
    repository = DocumentRepository(session)
    current = repository.current_version(document_id)
    if current is None:
        raise NotFoundError("文档不存在")
    source = current.storage_key
    version = DocumentWorkflowService(session).revoke(
        principal, document_id, payload.reason, _request_id(request)
    )
    sync.remove_source(source)
    document = repository.get_document(document_id)
    return _version_payload(
        document,
        version,
        repository.visible_department_ids(document_id),
        ParseJobRepository(session).for_version(version.id),
    )


@router.post("/{document_id}/sync")
def sync_managed_document(
    document_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    config: dict = Depends(get_config_dep),
    sync: DocumentSync = Depends(get_document_sync),
):
    repository = DocumentRepository(session)
    document = repository.get_document(document_id)
    if document is None or not repository.is_visible(document, principal.department_ids):
        raise NotFoundError("文档不存在")
    ensure_permission(principal, Permission.DOCUMENT_EDIT, document.owner_department_id)
    version = repository.current_version(document_id)
    if version is None or version.status != ReviewStatus.APPROVED:
        raise ValidationError("只有已批准文档可以同步索引")
    return {
        "document_id": document_id,
        "version_id": version.id,
        "chunk_count": _index_approved_version(
            sync, config, repository, document, version
        ),
    }
