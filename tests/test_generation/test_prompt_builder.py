"""Prompt 构建测试。"""

from app.generation.prompt_builder import build_prompt, MEDICAL_SYSTEM_PROMPT, INTENT_PROMPTS
from app.core.models import DocumentChunk, SearchResult, IntentCategory


def test_build_prompt_contains_system_prompt():
    """build_prompt 返回包含医疗系统提示词。"""

    chunks = [
        SearchResult(
            chunk=DocumentChunk(id="a:1", source="药品说明书.md", content="适应症包括解热镇痛"),
            score=0.85,
        )
    ]
    system, user = build_prompt("阿司匹林适应症", chunks)
    assert system == MEDICAL_SYSTEM_PROMPT
    assert "免责声明" in system


def test_build_prompt_contains_sources():
    """build_prompt 用户提示词包含检索片段。"""

    chunks = [
        SearchResult(
            chunk=DocumentChunk(id="a:1", source="药品说明书.md", content="适应症包括解热镇痛"),
            score=0.85,
        ),
    ]
    system, user = build_prompt("阿司匹林适应症", chunks)
    assert "药品说明书.md" in user
    assert "适应症包括解热镇痛" in user


def test_build_prompt_with_intent():
    """build_prompt 根据意图选择不同引导语。"""

    chunks = [
        SearchResult(
            chunk=DocumentChunk(id="a:1", source="test.md", content="内容"),
            score=0.8,
        )
    ]
    # 对比意图
    _, user = build_prompt("阿司匹林和布洛芬对比", chunks, intent=IntentCategory.COMPARISON)
    assert "对比表格" in user

    # 定义意图
    _, user = build_prompt("阿司匹林是什么", chunks, intent=IntentCategory.DEFINITION)
    assert "精确的定义" in user


def test_medical_system_prompt_contains_key_rules():
    """医疗系统提示词包含关键规则。"""

    assert "标注来源" in MEDICAL_SYSTEM_PROMPT
    assert "不要给出诊断建议" in MEDICAL_SYSTEM_PROMPT
    assert "免责声明" in MEDICAL_SYSTEM_PROMPT


def test_intent_prompts_cover_all_categories():
    """意图引导语覆盖所有 5 种意图。"""

    assert IntentCategory.QUERY in INTENT_PROMPTS
    assert IntentCategory.DEFINITION in INTENT_PROMPTS
    assert IntentCategory.COMPARISON in INTENT_PROMPTS
    assert IntentCategory.PROCESS in INTENT_PROMPTS
    assert IntentCategory.NEGATION in INTENT_PROMPTS
