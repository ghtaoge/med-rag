"""文档加载器测试。"""

import tempfile
from pathlib import Path

from app.documents.loader.registry import load_document, supported_extensions
from app.documents.loader.txt_loader import TxtLoader
from app.documents.loader.md_loader import MdLoader


def test_supported_extensions_contains_all_formats():
    """支持格式包含所有扩展名。"""

    exts = supported_extensions()
    assert ".txt" in exts
    assert ".md" in exts
    assert ".pdf" in exts
    assert ".docx" in exts
    assert ".png" in exts
    assert ".xlsx" in exts
    assert ".csv" in exts
    assert ".pptx" in exts
    assert ".jpg" in exts
    assert ".jpeg" in exts
    assert ".tiff" in exts


def test_txt_loader_reads_utf8():
    """TxtLoader 读取 UTF-8 文本。"""

    with tempfile.NamedTemporaryFile(
        suffix=".txt", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write("测试文本内容")
        f.flush()
        result = TxtLoader().load(Path(f.name))
    assert result == "测试文本内容"


def test_md_loader_reads_utf8():
    """MdLoader 读取 Markdown 文本。"""

    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write("# 标题\n\n内容段落")
        f.flush()
        result = MdLoader().load(Path(f.name))
    assert "# 标题" in result
    assert "内容段落" in result


def test_load_document_dispatches_by_extension():
    """load_document 按扩展名分发到对应加载器。"""

    with tempfile.NamedTemporaryFile(
        suffix=".txt", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write("hello world")
        f.flush()
        result = load_document(Path(f.name))
    assert result == "hello world"


def test_load_document_raises_for_unsupported_format():
    """不支持格式抛 ValueError。"""

    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        pass
    try:
        load_document(Path(f.name))
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "不支持的文件格式" in str(e)


def test_load_document_from_data_dir():
    """从 data 目录加载 sample_medical.md。"""

    from app.core.config import get_config

    config = get_config()
    data_dir = Path(__file__).resolve().parent.parent.parent / config["knowledge_dir"]
    md_file = data_dir / "sample_medical.md"
    if md_file.exists():
        result = load_document(md_file)
        assert "阿司匹林" in result
        assert "适应症" in result
