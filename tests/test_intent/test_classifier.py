"""意图识别测试。"""

from app.intent.classifier import IntentClassifier
from app.core.models import IntentCategory


def test_rule_classifier_comparison():
    """关键词"对比"识别为 COMPARISON。"""

    classifier = IntentClassifier()
    result = classifier.classify("阿司匹林和布洛芬对比")
    assert result.category == IntentCategory.COMPARISON
    assert result.confidence >= 0.8
    assert result.method == "rule"


def test_rule_classifier_definition():
    """关键词"是什么"识别为 DEFINITION。"""

    result = IntentClassifier().classify("阿司匹林是什么药")
    assert result.category == IntentCategory.DEFINITION
    assert result.confidence >= 0.8


def test_rule_classifier_process():
    """关键词"流程"识别为 PROCESS。"""

    result = IntentClassifier().classify("药品使用流程步骤")
    assert result.category == IntentCategory.PROCESS


def test_rule_classifier_negation():
    """关键词"是否"识别为 NEGATION。"""

    result = IntentClassifier().classify("阿司匹林是否能与布洛芬合用")
    assert result.category == IntentCategory.NEGATION


def test_rule_classifier_default_query():
    """无匹配关键词默认为 QUERY。"""

    result = IntentClassifier().classify("阿司匹林适应症")
    assert result.category == IntentCategory.QUERY
    assert result.confidence == 0.5  # 低置信度


def test_rule_classifier_multiple_keywords():
    """多个关键词命中时取最匹配的。"""

    result = IntentClassifier().classify("什么是阿司匹林的用法流程")
    # "什么是" → DEFINITION, "流程" → PROCESS
    # 第一个命中的优先
    assert result.category in [IntentCategory.DEFINITION, IntentCategory.PROCESS]
    assert result.confidence >= 0.8
