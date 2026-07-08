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
