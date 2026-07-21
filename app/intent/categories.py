"""意图类别定义 + 检索策略映射。"""

from __future__ import annotations


from app.core.models import IntentCategory


# 规则模式关键词映射
INTENT_KEYWORD_RULES: dict[IntentCategory, list[str]] = {
    IntentCategory.DEFINITION: ["是什么", "定义", "含义", "什么是", "解释", "概念"],
    IntentCategory.COMPARISON: ["对比", "区别", "差异", "比较", "不同", "哪个好", "vs"],
    IntentCategory.PROCESS: ["流程", "步骤", "操作", "怎么做", "方法", "程序", "如何"],
    IntentCategory.NEGATION: ["是否", "能不能", "可否", "是否可以", "有没有", "能不能不"],
}
