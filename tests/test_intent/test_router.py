"""意图路由测试。"""

from app.intent.router import IntentRouter
from app.core.models import IntentCategory


def test_get_retrieval_strategy_default():
    """默认策略使用混合检索。"""

    strategy = IntentRouter.get_retrieval_strategy(None)
    assert strategy["use_vector"] is True
    assert strategy["use_keyword"] is True


def test_get_retrieval_strategy_comparison():
    """对比意图扩大召回范围。"""

    strategy = IntentRouter.get_retrieval_strategy(IntentCategory.COMPARISON)
    assert strategy["vector_top_k"] == 30
    assert strategy["keyword_top_k"] == 30


def test_get_prompt_suffix_definition():
    """定义意图的 Prompt 引导语。"""

    suffix = IntentRouter.get_prompt_suffix(IntentCategory.DEFINITION)
    assert "精确的定义" in suffix


def test_get_prompt_suffix_comparison():
    """对比意图的 Prompt 引导语。"""

    suffix = IntentRouter.get_prompt_suffix(IntentCategory.COMPARISON)
    assert "对比表格" in suffix
