# Med-RAG LLM 兜底机制设计

## 背景

当 RAG 检索结果为空或所有结果相似度低于阈值时，目前系统无法给出有效回答。需要引入 LLM 兜底机制：允许 LLM 基于自身通用知识回答，但必须明确标注来源，让用户知道仅为参考。

## 需求

1. 检索结果为空或所有 score < `min_relevance_score`（0.05）时，默认启用 LLM 兜底
2. 兜底回答必须标注："知识库中未检索到相关内容，以下为模型基于通用知识的回答"
3. 通过配置文件 `retrieval.llm_fallback_enabled`（默认 `True`）控制是否启用兜底
4. 前端醒目标识兜底回答，告知用户仅供参考
5. 非流式 `chat()` 和流式 `chat_stream()` 均需支持

## 涉及改动

| 层 | 文件 | 改动内容 |
|---|---|---|
| 配置 | `config.yaml` | 补齐 `retrieval.min_relevance_score` 和 `retrieval.llm_fallback_enabled` |
| 模型 | `app/core/models.py` | `QaSession` 增加 `source_type: str = "knowledge_base"` 字段 |
| 编排器 | `app/api/chat.py` | 实现 `_should_use_llm_fallback` + `_mark_llm_fallback_answer`；`chat_stream()` 加入兜底逻辑；`_serialize_session` 输出 `source_type` |
| SSE | `app/generation/stream.py` | 新增 `stream_llm_fallback` 事件 |
| 前端 Store | `frontend/src/stores/chat.js` | 增加 `isLlmFallback` 状态 |
| 前端 View | `frontend/src/views/ChatView.vue` | 接收 SSE 事件，显示顶部提示条 |

## 核心逻辑

### `_should_use_llm_fallback(results: list[SearchResult]) -> bool`

1. 读取 `retrieval.llm_fallback_enabled` 配置，若 `False` → 不兜底
2. 检索结果为空列表 → 兜底
3. 最高 score < `min_relevance_score` → 兜底
4. 否则 → 正常 RAG 回答

### `_mark_llm_fallback_answer(answer: str) -> str`

在回答文本前插入 `LLM_FALLBACK_NOTICE`：

```
> ⚠️ 知识库中未检索到相关内容，以下为模型基于通用知识的回答，仅供参考。

{原始回答}
```

### `chat()` 方法流程（已有框架，补充实现）

```
意图识别 → 混合检索 → _should_use_llm_fallback?
  ├─ True:  build_llm_fallback_prompt → 生成 → _mark_llm_fallback_answer → source_type="llm_fallback"
  └─ False: build_prompt → 生成 → source_type="knowledge_base"
→ 正确性校验 → 组装 QaSession → 存储
```

### `chat_stream()` 方法流程（新增兜底逻辑）

```
意图识别 → 混合检索 → _should_use_llm_fallback?
  ├─ True:  yield stream_llm_fallback → build_llm_fallback_prompt → 流式生成 → _mark_llm_fallback_answer → source_type="llm_fallback"
  └─ False: build_prompt → 流式生成 → source_type="knowledge_base"
→ stream_generation_end → 正确性校验 → 存储 → done
```

## SSE 新事件

```
event: llm_fallback
data: {"notice": "知识库中未检索到相关内容，以下为模型基于通用知识的回答，仅供参考"}
```

在 `stream_search_result` 之后、`stream_generation_start` 之前发送。

## QaSession 模型扩展

```python
@dataclass
class QaSession:
    session_id: str
    question: str
    answer: str = ""
    sources: list[SearchResult] = field(default_factory=list)
    intent: IntentResult | None = None
    correctness: CorrectnessResult | None = None
    source_type: str = "knowledge_base"  # "knowledge_base" | "llm_fallback"
    created_at: datetime = field(default_factory=datetime.now)
```

`_serialize_session` 输出新增 `"source_type"` 字段。

## config.yaml 补齐

```yaml
retrieval:
  default_top_k: 5
  vector_top_k: 20
  keyword_top_k: 20
  rrf_k: 60
  rerank_top_k: 5
  min_relevance_score: 0.05
  llm_fallback_enabled: true
```

## 非兜底时行为（`llm_fallback_enabled=False`）

当检索为空/低相似度且兜底关闭时：

- `chat()` 返回固定提示语回答："当前知识库中没有检索到相关内容，请尝试其他问题或联系管理员。"
- `chat_stream()` 生成结束后替换为提示语
- `source_type="no_result"`

## 前端展示

ChatView 中在回答区域上方显示提示条：

- 黄色/橙色背景，醒目但不打断阅读
- 文字："⚠️ 知识库中未检索到相关内容，以下为模型基于通用知识的回答，仅供参考"
- 仅在 `isLlmFallback=true` 时显示

Store 中新增：
```javascript
isLlmFallback: false  // SSE llm_fallback 事件触发时设为 true
```

## 测试要点

1. `_should_use_llm_fallback`：空列表 → True；score 全低于阈值 → True；score 超阈值 → False；配置关闭 → False
2. `_mark_llm_fallback_answer`：回答前缀包含 LLM_FALLBACK_NOTICE
3. `chat_stream()` 兜底流程：SSE 事件序列包含 `llm_fallback` 事件
4. `llm_fallback_enabled=False` 时：返回固定提示语，`source_type="no_result"`
5. 前端：提示条仅在兜底时显示，非兜底时隐藏
