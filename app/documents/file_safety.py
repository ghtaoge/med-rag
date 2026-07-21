"""不可信文档的文件名、路径和文件结构检查。"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from pathlib import Path, PurePath

from app.core.config import get_config
from app.core.exceptions import FileSecurityError

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_IMAGE_SIGNATURES: dict[str, bytes | tuple[bytes, ...]] = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".bmp": b"BM",
}
_OFFICE_MARKERS = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}
_ALLOWED_MIMES = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    },
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "tiff": {"image/tiff"},
    "bmp": {"image/bmp"},
    "txt": {"text/plain", "application/octet-stream"},
    "md": {"text/markdown", "text/plain", "application/octet-stream"},
    "csv": {"text/csv", "text/plain", "application/vnd.ms-excel"},
}


def validate_client_filename(value: str | None) -> str:
    """规范化显示文件名，并拒绝任何路径语义。"""

    if not value:
        raise FileSecurityError("文件名不能为空")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized or normalized in {".", ".."}:
        raise FileSecurityError("文件名无效")
    if "/" in normalized or "\\" in normalized or _DRIVE_PREFIX.match(normalized):
        raise FileSecurityError("文件名不能包含路径")
    if PurePath(normalized).name != normalized:
        raise FileSecurityError("文件名不能包含路径")
    if any(ord(char) < 32 for char in normalized):
        raise FileSecurityError("文件名包含控制字符")
    return normalized


def resolve_child(root: Path, filename: str) -> Path:
    """将普通文件名解析为 root 的直接子文件。"""

    safe_name = validate_client_filename(filename)
    resolved_root = root.resolve()
    candidate = (resolved_root / safe_name).resolve()
    if candidate.parent != resolved_root:
        raise FileSecurityError("文件路径越界")
    return candidate


def _inspect_archive(path: Path, marker: str) -> None:
    cfg = get_config()["security"]
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > cfg["max_archive_members"]:
                raise FileSecurityError("压缩成员数量超限")
            total = sum(item.file_size for item in infos)
            compressed = max(1, sum(item.compress_size for item in infos))
            if total > cfg["max_archive_uncompressed_bytes"]:
                raise FileSecurityError("解压后文件过大")
            if total / compressed > cfg["max_archive_ratio"]:
                raise FileSecurityError("压缩比异常")

            names = {item.filename for item in infos}
            if marker not in names or "[Content_Types].xml" not in names:
                raise FileSecurityError("Office 文件结构无效")

            for item in infos:
                lowered_name = item.filename.lower()
                if "/embeddings/" in lowered_name or "oleobject" in lowered_name:
                    raise FileSecurityError("Office 文件包含嵌入对象")
                if lowered_name.endswith("vbaproject.bin"):
                    raise FileSecurityError("Office 文件包含宏")
                if lowered_name.endswith(".rels"):
                    content = archive.read(item).decode("utf-8", errors="ignore")
                    if 'TargetMode="External"' in content:
                        raise FileSecurityError("Office 文件包含外部关系")
    except zipfile.BadZipFile as exc:
        raise FileSecurityError("Office 文件结构无效") from exc


def inspect_file(path: Path, declared_mime: str | None = None) -> str:
    """检查真实文件结构，并返回规范格式名。"""

    size = path.stat().st_size
    if size <= 0:
        raise FileSecurityError("文件为空")
    if size > get_config()["security"]["max_upload_bytes"]:
        raise FileSecurityError("文件大小超过限制")

    suffix = path.suffix.lower()
    with path.open("rb") as source:
        prefix = source.read(16)

    if suffix == ".pdf":
        if not prefix.startswith(b"%PDF-"):
            raise FileSecurityError("文件扩展名与内容不一致")
        with path.open("rb") as source:
            sample = source.read(2 * 1024 * 1024)
        active_markers = (
            b"/JavaScript",
            b"/JS",
            b"/OpenAction",
            b"/Launch",
            b"/EmbeddedFiles",
            b"/Filespec",
        )
        if any(marker in sample for marker in active_markers):
            raise FileSecurityError("PDF 包含活动内容或附件")
        detected = "pdf"
    elif suffix in _OFFICE_MARKERS:
        _inspect_archive(path, _OFFICE_MARKERS[suffix])
        detected = suffix[1:]
    elif suffix in _IMAGE_SIGNATURES:
        expected = _IMAGE_SIGNATURES[suffix]
        signatures = expected if isinstance(expected, tuple) else (expected,)
        if not any(prefix.startswith(signature) for signature in signatures):
            raise FileSecurityError("文件扩展名与内容不一致")
        detected = suffix[1:]
    elif suffix in {".txt", ".md", ".csv"}:
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise FileSecurityError("文本文件必须使用 UTF-8 编码") from exc
        detected = suffix[1:]
    else:
        raise FileSecurityError("不支持的文件格式")

    if declared_mime:
        normalized_mime = declared_mime.split(";", 1)[0].strip().lower()
        if normalized_mime not in _ALLOWED_MIMES[detected]:
            raise FileSecurityError("声明 MIME 与文件内容不一致")
    return detected


def inspect_upload_envelope(path: Path, declared_mime: str | None = None) -> str:
    """Check only size, extension, MIME, and a small magic prefix in the API."""

    size = path.stat().st_size
    if size <= 0:
        raise FileSecurityError("文件为空")
    if size > get_config()["security"]["max_upload_bytes"]:
        raise FileSecurityError("文件大小超过限制")
    suffix = path.suffix.lower()
    with path.open("rb") as source:
        prefix = source.read(16)
    if suffix == ".pdf":
        valid = prefix.startswith(b"%PDF-")
    elif suffix in _OFFICE_MARKERS:
        valid = prefix.startswith(b"PK\x03\x04")
    elif suffix in _IMAGE_SIGNATURES:
        expected = _IMAGE_SIGNATURES[suffix]
        signatures = expected if isinstance(expected, tuple) else (expected,)
        valid = any(prefix.startswith(signature) for signature in signatures)
    elif suffix in {".txt", ".md", ".csv"}:
        valid = True
    else:
        raise FileSecurityError("不支持的文件格式")
    if not valid:
        raise FileSecurityError("文件扩展名与内容不一致")
    detected = suffix[1:]
    if declared_mime:
        normalized_mime = declared_mime.split(";", 1)[0].strip().lower()
        if normalized_mime not in _ALLOWED_MIMES[detected]:
            raise FileSecurityError("声明 MIME 与文件内容不一致")
    return detected
