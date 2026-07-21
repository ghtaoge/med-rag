"""文档管理路由 — 上传/同步/校验/列表。"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File

from app.core.dependencies import (
    get_config_dep,
    get_document_sync,
    get_document_validator,
)
from app.core.exceptions import DocumentError, FileSecurityError, ValidationError
from app.documents.file_safety import inspect_file, resolve_child, validate_client_filename
from app.documents.sync import DocumentSync
from app.documents.validator import DocumentValidator
from app.documents.index_state import load_index_state, remove_index_state
from app.security.bootstrap_auth import verify_bootstrap_admin

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["文档管理"],
    dependencies=[Depends(verify_bootstrap_admin)],
)


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
        inspect_file(temporary, file.content_type)
        os.replace(temporary, destination)
        return filename, destination
    finally:
        temporary.unlink(missing_ok=True)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(..., description="上传文件"),
    config: dict = Depends(get_config_dep),
    validator: DocumentValidator = Depends(get_document_validator),
    sync: DocumentSync = Depends(get_document_sync),
):
    """上传文档 → 校验 → 保存 → 自动同步索引。"""

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


@router.post("/sync")
async def sync_all_documents(
    sync: DocumentSync = Depends(get_document_sync),
):
    """全量同步所有变更文件。"""

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


@router.post("/sync/{filename}")
async def sync_single_document(
    filename: str,
    sync: DocumentSync = Depends(get_document_sync),
):
    """同步单个文件。"""

    filename = validate_client_filename(filename)
    try:
        chunk_count = sync.sync_file(filename)
    except Exception as e:
        raise DocumentError("同步文件失败") from e

    return {
        "filename": filename,
        "chunk_count": chunk_count,
    }


@router.post("/validate")
async def validate_document(
    file: UploadFile = File(..., description="待校验文件"),
    config: dict = Depends(get_config_dep),
    validator: DocumentValidator = Depends(get_document_validator),
):
    """校验文档（不入库，只检查）。"""

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


@router.get("/list")
async def list_documents(
    config: dict = Depends(get_config_dep),
):
    """列出知识库中的所有文档及其 chunk 状态。"""

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


@router.delete("/{filename}")
async def delete_document(
    filename: str,
    config: dict = Depends(get_config_dep),
):
    """从知识库删除文档（文件 + 索引）。"""

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
