import zipfile

import pytest

from app.core.exceptions import FileSecurityError
from app.documents.file_safety import inspect_file, resolve_child, validate_client_filename


@pytest.mark.parametrize(
    "name",
    [
        "../secret.txt",
        "..\\secret.txt",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "a/b.txt",
        "a\\b.txt",
    ],
)
def test_rejects_path_like_filenames(name):
    with pytest.raises(FileSecurityError):
        validate_client_filename(name)


def test_accepts_plain_unicode_filename():
    assert validate_client_filename("阿司匹林说明书.pdf") == "阿司匹林说明书.pdf"


def test_resolve_child_cannot_escape_root(tmp_path):
    with pytest.raises(FileSecurityError):
        resolve_child(tmp_path, "../outside.txt")


def _write_zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_rejects_extension_signature_mismatch(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(FileSecurityError):
        inspect_file(path, "application/pdf")


def test_accepts_real_docx_structure(tmp_path):
    path = tmp_path / "manual.docx"
    _write_zip(
        path,
        {"[Content_Types].xml": "<Types/>", "word/document.xml": "<document/>"},
    )
    assert (
        inspect_file(
            path,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        == "docx"
    )


def test_rejects_office_external_relationship(tmp_path):
    path = tmp_path / "manual.docx"
    _write_zip(
        path,
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "<document/>",
            "word/_rels/document.xml.rels": (
                '<Relationship TargetMode="External" Target="https://internal.example"/>'
            ),
        },
    )
    with pytest.raises(FileSecurityError, match="外部关系"):
        inspect_file(path)


def test_rejects_office_embedded_object(tmp_path):
    path = tmp_path / "manual.docx"
    _write_zip(
        path,
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "<document/>",
            "word/embeddings/oleObject1.bin": b"payload",
        },
    )
    with pytest.raises(FileSecurityError, match="嵌入对象"):
        inspect_file(path)


def test_rejects_pdf_active_content(tmp_path):
    path = tmp_path / "active.pdf"
    path.write_bytes(b"%PDF-1.7\n1 0 obj << /JavaScript (alert) >> endobj\n%%EOF")
    with pytest.raises(FileSecurityError, match="活动内容"):
        inspect_file(path)


def test_rejects_declared_mime_mismatch(tmp_path):
    path = tmp_path / "manual.txt"
    path.write_text("medical content", encoding="utf-8")
    with pytest.raises(FileSecurityError, match="MIME"):
        inspect_file(path, "application/pdf")
