"""元数据过滤测试。"""

from app.retrieval.metadata_filter import build_filter


def test_build_filter_single_source():
    """单个 source 过滤。"""

    result = build_filter({"source": "药品说明书.md"})
    assert result == 'source == "药品说明书.md"'


def test_build_filter_multiple_sources():
    """多个 source 过滤。"""

    result = build_filter({"source": ["a.md", "b.md"]})
    assert 'source == "a.md"' in result
    assert 'source == "b.md"' in result
    assert "||" in result


def test_build_filter_doc_type():
    """doc_type 过滤使用 like。"""

    result = build_filter({"doc_type": "药品说明书"})
    assert result == 'metadata_json like "%药品说明书%"'


def test_build_filter_none_input():
    """None 输入返回 None。"""

    result = build_filter(None)
    assert result is None


def test_build_filter_empty_dict():
    """空字典返回 None。"""

    result = build_filter({})
    assert result is None


def test_build_filter_combined():
    """组合多个过滤条件。"""

    result = build_filter({"source": "a.md", "doc_type": "药品说明书"})
    assert result is not None
    assert "&&" in result
