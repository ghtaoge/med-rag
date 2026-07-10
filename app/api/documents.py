"""文档管理路由 — 上传/同步/校验/列表。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Query

from app.core.dependencies import (
    get_config_dep,
    get_document_sync,
    get_document_validator,
)
from app.core.exceptions import DocumentError, ValidationError
from app.documents.sync import DocumentSync
from app.documents.validator import DocumentValidator
from app.documents.index_state import load_index_state, remove_index_state

router = APIRouter(prefix="/api/v1/documents", tags=["文档管理"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(..., description="上传文件"),
    config: dict = Depends(get_config_dep),
    validator: DocumentValidator = Depends(get_document_validator),
    sync: DocumentSync = Depends(get_document_sync),
):
    """上传文档 → 校验 → 保存 → 自动同步索引。"""

    # 保存文件到知识库目录
    knowledge_dir = Path(config["knowledge_dir"])
    dest_path = knowledge_dir / file.filename

    # 检查文件名冲突
    if dest_path.exists():
        raise ValidationError(f"文件已存在: {file.filename}")

    # 保存上传文件
    try:
        with open(dest_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise DocumentError(f"保存文件失败: {e}")

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
        chunk_count = sync.sync_file(file.filename, force=True)
    except Exception as e:
        raise DocumentError(f"文件已保存，但同步索引失败: {e}")

    return {
        "status": "accepted",
        "filename": file.filename,
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

    try:
        chunk_count = sync.sync_file(filename)
    except Exception as e:
        raise DocumentError(f"同步文件 {filename} 失败: {e}")

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

    # 临时保存文件
    knowledge_dir = Path(config["knowledge_dir"])
    temp_path = knowledge_dir / f"_temp_{file.filename}"

    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        result = validator.validate(temp_path)

        return {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
        }
    finally:
        temp_path.unlink(missing_ok=True)


@router.get("/list")
async def list_documents(
    config: dict = Depends(get_config_dep),
):
    """列出知识库中的所有文档及其 chunk 状态。"""

    knowledge_dir = Path(config["knowledge_dir"])

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
    file_path = knowledge_dir / filename

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
