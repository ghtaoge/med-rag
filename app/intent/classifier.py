"""意图分类器。规则 + LLM 双模式。"""

from __future__ import annotations

from app.core.models import IntentCategory, IntentResult
from app.intent.categories import INTENT_KEYWORD_RULES


class IntentClassifier:
    """意图分类器。

    规则模式：关键词匹配 → 快速、零成本。
    LLM 模式：发送给 LLM 分类 → 更准确、有成本。
    仅在规则模式置信度低时启用 LLM 模式。
    """

    def __init__(self, llm_engine=None, rule_threshold: float = 0.7):
        self.llm_engine = llm_engine
        self.rule_threshold = rule_threshold

    def classify(self, question: str) -> IntentResult:
        """分类意图。先尝试规则模式，置信度低时启用 LLM。"""

        # 规则模式
        rule_result = self._rule_classify(question)

        if rule_result.confidence >= self.rule_threshold:
            return rule_result

        # LLM 模式（如果可用）
        if self.llm_engine is not None:
            try:
                # classify() is called from both sync and async request paths.
                # Avoid blocking or leaking an un-awaited coroutine inside an active event loop.
                import asyncio

                asyncio.get_running_loop()
                return rule_result
            except RuntimeError:
                pass

            try:
                llm_result = self._llm_classify(question)
                return llm_result
            except Exception:
                return rule_result

        return rule_result

    def _rule_classify(self, question: str) -> IntentResult:
        """规则模式：关键词匹配。"""

        best_category = IntentCategory.QUERY
        best_score = 0.0

        for category, keywords in INTENT_KEYWORD_RULES.items():
            for keyword in keywords:
                if keyword in question:
                    score = 0.9  # 命中关键词 → 高置信度
                    if score > best_score:
                        best_score = score
                        best_category = category
                    break

        # 未命中关键词 → 低置信度
        if best_score == 0.0:
            best_score = 0.5

        return IntentResult(
            category=best_category,
            confidence=best_score,
            method="rule",
        )

    def _llm_classify(self, question: str) -> IntentResult:
        """LLM 模式：发送给 LLM 分类。"""

        categories = [c for c in IntentCategory]
        prompt = f"""请判断以下问题的意图类别，只返回类别名称。

可选类别：{', '.join(categories)}

问题：{question}

类别："""

        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            self.llm_engine.generate(prompt)
        )

        # 解析 LLM 返回
        response = response.strip().lower()
        for category in categories:
            if category in response:
                return IntentResult(
                    category=category,
                    confidence=0.85,
                    method="llm",
                )

        # LLM 返回无法解析 → 回退到规则结果
        return self._rule_classify(question)
