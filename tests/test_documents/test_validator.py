"""文档校验测试。"""

import tempfile
from pathlib import Path

from app.documents.validator import DocumentValidator


def test_validate_txt_file():
    """TXT 文件校验通过。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "药品说明书.txt"
        test_file.write_text("阿司匹林适应症", encoding="utf-8")

        result = DocumentValidator().validate(test_file)
        assert result.is_valid
        assert len(result.errors) == 0


def test_validate_unsupported_format():
    """不支持格式校验失败。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.xyz"
        test_file.write_text("content", encoding="utf-8")

        result = DocumentValidator().validate(test_file)
        assert not result.is_valid
        assert "不支持" in result.errors[0]


def test_validate_empty_file():
    """空文件校验失败。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "empty.txt"
        test_file.write_text("", encoding="utf-8")

        result = DocumentValidator().validate(test_file)
        assert not result.is_valid
        assert "为空" in result.errors[0]


def test_validate_non_medical_filename_warning():
    """非医疗文件名产生警告。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "notes.txt"
        test_file.write_text("some content that is long enough", encoding="utf-8")

        result = DocumentValidator().validate(test_file)
        assert result.is_valid
        assert any("医疗" in w for w in result.warnings)
