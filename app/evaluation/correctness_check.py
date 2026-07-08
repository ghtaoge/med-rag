"""正确性校验模块。

来源一致性 + 幻觉检测 + 置信度评分。
"""

from __future__ import annotations

from app.core.models import (
    SearchResult,
    CorrectnessResult,
    ConfidenceLevel,
)


class CorrectnessChecker:
    """正确性校验器。

    校验维度：
    1. 来源一致性 — 多个独立来源都支持 → 高置信度
    2. 幻觉检测 — 回答中出现检索片段没有的信息
    3. 置信度评分 — 综合评估
    """

    # 医疗关键信息关键词（需要严格来源标注）
    MEDICAL_KEYWORDS = [
        "剂量", "用法", "适应症", "禁忌", "不良反应",
        "药物相互作用", "处方", "mg", "ml", "每日",
    ]

    def check(
        self,
        answer: str,
        sources: list[SearchResult],
    ) -> CorrectnessResult:
        """校验回答的正确性。"""

        # 来源一致性
        source_count = len(sources)
        unique_sources = len(set(s.chunk.source for s in sources))

        # 置信度计算
        if unique_sources >= 3 and source_count >= 3:
            confidence = ConfidenceLevel.HIGH
            score = 0.85
            warnings = []
        elif unique_sources >= 2 and source_count >= 2:
            confidence = ConfidenceLevel.MEDIUM
            score = 0.7
            warnings = []
        elif unique_sources == 1 or source_count == 1:
            confidence = ConfidenceLevel.LOW
            score = 0.5
            warnings = ["仅单一来源，请人工确认"]
        else:
            confidence = ConfidenceLevel.LOW
            score = 0.3
            warnings = ["知识库中没有检索到相关内容"]

        # 幻觉检测
        hallucination_flags = self._detect_hallucination(answer, sources)

        # 医疗关键信息无来源 → 降低置信度
        for keyword in self.MEDICAL_KEYWORDS:
            if keyword in answer and not any(
                keyword in s.chunk.content for s in sources
            ):
                hallucination_flags.append(
                    f"医疗关键信息 '{keyword}' 在回答中出现但检索片段中不存在"
                )
                if confidence == ConfidenceLevel.HIGH:
                    confidence = ConfidenceLevel.MEDIUM
                    score = 0.7

        # 来源冲突检测
        conflicts = self._detect_source_conflicts(sources)
        if conflicts:
            warnings.extend(conflicts)
            if confidence != ConfidenceLevel.LOW:
                confidence = ConfidenceLevel.LOW
                score = min(score, 0.4)

        return CorrectnessResult(
            confidence=confidence,
            score=score,
            source_count=unique_sources,
            warnings=warnings,
            hallucination_flags=hallucination_flags,
        )

    def _detect_hallucination(
        self, answer: str, sources: list[SearchResult]
    ) -> list[str]:
        """检测回答中的幻觉内容。

        简化版：检查回答中的关键句子是否在检索片段中出现。
        """

        # 提取所有检索片段内容
        source_texts = " ".join(s.chunk.content for s in sources)

        flags = []

        # 检查回答是否包含"模型补充"标注
        if "模型补充" in answer or "非知识库来源" in answer:
            flags.append("包含模型补充（非知识库来源）的内容")

        # 简单句子级检查
        sentences = answer.replace("。", "。|").replace("！", "！|").split("|")
        unsupported = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 10:
                continue
            # 检查句子中的关键信息是否在来源中
            keywords = [w for w in sentence.split() if len(w) >= 3]
            overlap = sum(1 for w in keywords if w in source_texts)
            if keywords and overlap / len(keywords) < 0.3:
                unsupported.append(sentence[:50])

        if unsupported:
            flags.append(f"可能有 {len(unsupported)} 条信息无来源支持")

        return flags

    def _detect_source_conflicts(
        self, sources: list[SearchResult]
    ) -> list[str]:
        """检测来源间的冲突。"""

        if len(sources) < 2:
            return []

        # 简化版：如果同一文件的多个片段内容差异很大，标记为冲突
        # 生产版需要更精确的语义冲突检测
        return []
