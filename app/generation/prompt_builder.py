"""医疗场景 Prompt 构建。

引用强制 + 免责声明 + 来源标注 + 意图策略映射。
"""

from __future__ import annotations

from app.core.models import IntentCategory, SearchResult

MEDICAL_SYSTEM_PROMPT = """你是一个医疗行业知识助手。请严格基于检索到的知识片段回答问题。

规则：
1. 只使用提供的知识片段作为回答依据，不要使用自身知识补充
2. 每个关键论点必须标注来源（[来源：文件名]）
3. 如果知识片段中没有相关信息，明确说明"当前知识库中没有相关内容"
4. 不要给出诊断建议或处方建议 — 这是信息检索工具，不是诊断工具
5. 对于药品信息，必须包含完整的适应症、用法用量、注意事项
6. 如有多个来源，优先引用最新版本的内容

免责声明：本工具提供的信息仅供参考，不构成医疗建议。请以专业医护人员意见为准。
"""

LLM_FALLBACK_NOTICE = "知识库中未检索到相关内容，以下为模型基于通用知识的回答。"

# 兜底提示与普通 RAG 提示分开维护：
# 普通提示要求“只能基于知识库片段”，兜底提示则明确允许模型通用知识。
# 同时严格禁止伪造知识库来源，保证用户能区分答案来源。
LLM_FALLBACK_SYSTEM_PROMPT = """你是一个医疗知识助手。当前知识库没有检索到足够相关的内容，允许基于模型通用知识回答。
规则：
1. 必须保持谨慎，明确说明内容仅供参考，不构成医疗建议。
2. 不要声称答案来自知识库、指南原文或具体文档。
3. 不要编造引用来源、文件名、页码或数据库证据。
4. 涉及诊断、处方、剂量、禁忌、特殊人群用药时，应建议咨询专业医护人员或查看药品说明书。
"""

INTENT_PROMPTS: dict[IntentCategory, str] = {
    IntentCategory.QUERY: "请给出相关信息摘要，优先最新来源。",
    IntentCategory.DEFINITION: "请给出精确的定义，并标注来源文件和版本。",
    IntentCategory.COMPARISON: "请列出对比表格，包含各选项的关键差异。",
    IntentCategory.PROCESS: "请按步骤描述流程，标注每一步的来源依据。",
    IntentCategory.NEGATION: "请在知识库中搜索反面证据，说明为什么某些说法可能不正确。",
}


def build_prompt(
    question: str,
    results: list[SearchResult],
    intent: IntentCategory | None = None,
) -> tuple[str, str]:
    """构建完整 Prompt（系统提示词 + 用户提示词）。

    Returns: (system_prompt, user_prompt)
    """

    # 系统提示词
    system_prompt = MEDICAL_SYSTEM_PROMPT

    # 意图引导语
    intent_guidance = INTENT_PROMPTS.get(intent or IntentCategory.QUERY, INTENT_PROMPTS[IntentCategory.QUERY])

    # 检索片段拼接
    context_parts = []
    for result in results:
        context_parts.append(
            f"[来源：{result.chunk.source}，相关度：{result.score:.3f}]\n{result.chunk.content}"
        )

    context = "\n\n".join(context_parts)

    # 用户提示词
    user_prompt = f"""问题：{question}

{intent_guidance}

以下是从知识库中检索到的相关片段：

{context}

请基于以上片段回答问题，每个论点标注来源。"""

    return system_prompt, user_prompt


def build_llm_fallback_prompt(question: str) -> tuple[str, str]:
    """Build a prompt for clearly marked model-knowledge fallback answers."""

    # user_prompt 再次强调“无知识库命中”，用于抵消模型在医疗问答中编造引用的倾向。
    # 最终对用户展示的显式标识由 ChatOrchestrator._mark_llm_fallback_answer 统一添加。
    user_prompt = f"""问题：{question}

知识库没有检索到足够相关的内容。请基于通用医学知识给出谨慎、简洁的参考回答。
不要添加知识库来源标注，不要编造引用。
"""

    return LLM_FALLBACK_SYSTEM_PROMPT, user_prompt
