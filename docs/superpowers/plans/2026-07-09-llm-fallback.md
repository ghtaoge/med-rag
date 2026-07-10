# Med-RAG LLM 兜底机制 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当 RAG 检索结果为空或相似度过低时，默认启用 LLM 兜底回答，并明确标注来源为模型通用知识、仅供参考。

**Architecture:** `ChatOrchestrator` 判断检索质量 → 低质量时切换到 `build_llm_fallback_prompt` → LLM 生成后用 `_mark_llm_fallback_answer` 加前缀标识 → `QaSession` 新增 `source_type` 字段追踪来源 → SSE 新增 `llm_fallback` 事件通知前端 → 前端显示黄色提示条。

**Tech Stack:** Python 3.13 / FastAPI / SSE / Vue 3 + Pinia / MarkdownIt

## Global Constraints

- 配置项 `retrieval.llm_fallback_enabled` 默认 `True`，可通过环境变量 `RAG_LLM_FALLBACK_ENABLED` 覆盖
- 相似度阈值沿用现有 `retrieval.min_relevance_score`（默认 0.05）
- 兜底回答前缀使用 `LLM_FALLBACK_NOTICE`（`prompt_builder.py:23` 中已有定义）
- `source_type` 取值：`"knowledge_base"` | `"llm_fallback"` | `"no_result"`
- 所有新增代码需有 XML 注释或 docstring
- 前端样式使用项目已有 CSS 变量（`--amber`、`--bg-*`、`--text-*` 等）

---

### Task 1: 配置 + 模型层 — config.yaml 补齐 + QaSession 扩展

**Files:**
- Modify: `med-rag/config.yaml` (补齐 retrieval 配置)
- Modify: `med-rag/app/core/models.py:94-105` (QaSession dataclass)
- Modify: `med-rag/tests/test_core/test_config.py` (验证新配置项)
- Modify: `med-rag/tests/test_api/test_routes.py:60-116` (验证 QaSession source_type 序列化)

**Interfaces:**
- Consumes: `config.py` DEFAULTS 中已有的 `retrieval.llm_fallback_enabled` 和 `retrieval.min_relevance_score` 定义
- Produces: `QaSession.source_type: str` 字段（默认 `"knowledge_base"`）；`config.yaml` 中 `retrieval.min_relevance_score: 0.05` 和 `retrieval.llm_fallback_enabled: true`

- [ ] **Step 1: 补齐 config.yaml retrieval 字段**

在 `med-rag/config.yaml` 的 `retrieval:` 部分末尾添加两个缺失字段：

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

- [ ] **Step 2: 扩展 QaSession 模型**

在 `med-rag/app/core/models.py` 的 `QaSession` dataclass 中添加 `source_type` 字段，放在 `correctness` 之后、`created_at` 之前：

```python
@dataclass
class QaSession:
    """问答会话。"""

    session_id: str
    question: str
    answer: str = ""
    sources: list[SearchResult] = field(default_factory=list)
    intent: IntentResult | None = None
    correctness: CorrectnessResult | None = None
    source_type: str = "knowledge_base"  # "knowledge_base" | "llm_fallback" | "no_result"
    created_at: datetime = field(default_factory=datetime.now)
```

- [ ] **Step 3: 添加配置项测试**

在 `med-rag/tests/test_core/test_config.py` 末尾追加：

```python
def test_llm_fallback_enabled_is_bool():
    """llm_fallback_enabled 应为布尔类型。"""

    config = load_config()
    assert isinstance(config["retrieval"]["llm_fallback_enabled"], bool)
    assert config["retrieval"]["llm_fallback_enabled"] is True


def test_min_relevance_score_is_float():
    """min_relevance_score 应为浮点数。"""

    config = load_config()
    assert isinstance(config["retrieval"]["min_relevance_score"], float)
    assert config["retrieval"]["min_relevance_score"] == 0.05


def test_env_var_overrides_llm_fallback_enabled():
    """环境变量可以关闭 LLM 兜底。"""

    os.environ["RAG_LLM_FALLBACK_ENABLED"] = "false"
    config = load_config()
    assert config["retrieval"]["llm_fallback_enabled"] is False
    del os.environ["RAG_LLM_FALLBACK_ENABLED"]
```

- [ ] **Step 4: 运行配置测试确认通过**

```bash
cd med-rag && python -m pytest tests/test_core/test_config.py -v
```

预期：3 个新测试 + 5 个原有测试全部 PASS。

- [ ] **Step 5: 更新现有 test_routes.py 中 QaSession 构造**

在 `med-rag/tests/test_api/test_routes.py` 的 `test_sessions_persist_without_redis` 函数中，`QaSession` 构造处添加 `source_type="knowledge_base"` 以匹配新字段（虽然默认值已覆盖，但显式写明更清晰）：

```python
    session = QaSession(
        session_id="local-session-1",
        question="历史记录测试",
        answer="可以保存",
        intent=IntentResult(
            category=IntentCategory.QUERY,
            confidence=0.9,
            method="rule",
        ),
        correctness=CorrectnessResult(
            confidence=ConfidenceLevel.HIGH,
            score=0.8,
            source_count=0,
        ),
        source_type="knowledge_base",
        created_at=datetime(2026, 7, 9, 10, 0, 0),
    )
```

- [ ] **Step 6: 运行全量测试确认无破坏**

```bash
cd med-rag && python -m pytest tests/ -v --timeout=30
```

预期：所有测试 PASS。

- [ ] **Step 7: 提交**

```bash
cd med-rag && git add config.yaml app/core/models.py tests/test_core/test_config.py tests/test_api/test_routes.py && git commit -m "feat: config.yaml 补齐 + QaSession source_type 字段 — Task 1"
```

---

### Task 2: 后端核心 — _should_use_llm_fallback + _mark_llm_fallback_answer + chat/chat_stream 改造

**Files:**
- Modify: `med-rag/app/api/chat.py:38-181` (ChatOrchestrator: 新增 2 个方法 + 改造 chat/chat_stream)
- Create: `med-rag/tests/test_api/test_llm_fallback.py` (兜底逻辑测试)

**Interfaces:**
- Consumes: `QaSession.source_type`（Task 1 产出）；`LLM_FALLBACK_NOTICE`（`prompt_builder.py:23`）；`build_llm_fallback_prompt`（`prompt_builder.py:81`）；`get_config()["retrieval"]["llm_fallback_enabled"]` 和 `get_config()["retrieval"]["min_relevance_score"]`（Task 1 产出）
- Produces: `_should_use_llm_fallback(results) -> bool`；`_mark_llm_fallback_answer(answer) -> str`；`chat()` 和 `chat_stream()` 中的兜底分支逻辑；`QaSession` 构造时传入 `source_type`

- [ ] **Step 1: 编写 _should_use_llm_fallback 测试**

创建 `med-rag/tests/test_api/test_llm_fallback.py`：

```python
"""LLM 兜底逻辑测试。"""

from app.api.chat import ChatOrchestrator
from app.core.models import DocumentChunk, SearchResult, ChunkMetadata


def _make_result(score: float) -> SearchResult:
    """构造一个指定分数的 SearchResult。"""

    return SearchResult(
        chunk=DocumentChunk(
            id="test-chunk",
            source="test.pdf",
            content="测试内容",
        ),
        score=score,
    )


def test_should_use_llm_fallback_empty_results():
    """检索结果为空 → 应兜底。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    assert orchestrator._should_use_llm_fallback([]) is True


def test_should_use_llm_fallback_low_score():
    """所有 score < min_relevance_score → 应兜底。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    results = [_make_result(0.03), _make_result(0.02)]
    assert orchestrator._should_use_llm_fallback(results) is True


def test_should_use_llm_fallback_high_score():
    """最高 score >= min_relevance_score → 不兜底。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    results = [_make_result(0.08), _make_result(0.06)]
    assert orchestrator._should_use_llm_fallback(results) is False


def test_should_use_llm_fallback_disabled_config(monkeypatch):
    """llm_fallback_enabled=False → 不兜底（即使空结果）。"""

    from app.core import config as cfg_module

    original_cache = getattr(cfg_module.get_config, "_cache", None)
    try:
        if hasattr(cfg_module.get_config, "_cache"):
            del cfg_module.get_config._cache

        monkeypatch.setenv("RAG_LLM_FALLBACK_ENABLED", "false")

        orchestrator = ChatOrchestrator(None, None, None, None)
        assert orchestrator._should_use_llm_fallback([]) is False
    finally:
        monkeypatch.delenv("RAG_LLM_FALLBACK_ENABLED", raising=False)
        if original_cache is not None:
            cfg_module.get_config._cache = original_cache


def test_mark_llm_fallback_answer():
    """兜底回答应带 LLM_FALLBACK_NOTICE 前缀。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    raw = "阿司匹林是一种解热镇痛药。"
    marked = orchestrator._mark_llm_fallback_answer(raw)
    from app.generation.prompt_builder import LLM_FALLBACK_NOTICE
    assert LLM_FALLBACK_NOTICE in marked
    assert raw in marked


def test_mark_llm_fallback_answer_format():
    """兜底回答应包含 blockquote 格式和 ⚠️ 标记。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    raw = "阿司匹林是一种解热镇痛药。"
    marked = orchestrator._mark_llm_fallback_answer(raw)
    assert "⚠️" in marked
    assert marked.startswith("> ")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd med-rag && python -m pytest tests/test_api/test_llm_fallback.py -v
```

预期：`_should_use_llm_fallback` 方法不存在导致 `AttributeError` FAIL。

- [ ] **Step 3: 实现 _should_use_llm_fallback 和 _mark_llm_fallback_answer**

在 `med-rag/app/api/chat.py` 的 `ChatOrchestrator` 类中，在 `_retrieve` 方法之后（约 line 207）、`_generate` 方法之前（约 line 209）添加两个方法：

```python
    def _should_use_llm_fallback(self, results: list[SearchResult]) -> bool:
        """判断是否应使用 LLM 兜底回答。

        条件：
        1. llm_fallback_enabled 配置为 False → 不兜底
        2. 检索结果为空 → 兜底
        3. 最高 score < min_relevance_score → 兜底
        4. 否则 → 正常 RAG 回答
        """

        from app.core.config import get_config

        cfg = get_config()
        if not cfg["retrieval"]["llm_fallback_enabled"]:
            return False

        if not results:
            return True

        max_score = max(r.score for r in results)
        min_threshold = cfg["retrieval"]["min_relevance_score"]

        return max_score < min_threshold

    def _mark_llm_fallback_answer(self, answer: str) -> str:
        """在回答前插入 LLM 兜底标识。"""

        return f"> ⚠️ {LLM_FALLBACK_NOTICE}仅供参考。\n\n{answer}"
```

- [ ] **Step 4: 改造 chat() 方法 — 补充 source_type**

在 `med-rag/app/api/chat.py` 的 `chat()` 方法中，修改 `QaSession` 构造（约 line 93-101），加入 `source_type`：

```python
        # 5. 组装会话
        session = QaSession(
            session_id=session_id,
            question=question,
            answer=answer,
            sources=search_results,
            intent=intent_result,
            correctness=correctness,
            source_type="llm_fallback" if use_llm_fallback else "knowledge_base",
            created_at=datetime.now(),
        )
```

- [ ] **Step 5: 改造 chat_stream() 方法 — 加入兜底逻辑**

将 `med-rag/app/api/chat.py` 的 `chat_stream()` 方法（约 line 116-181）替换为包含兜底逻辑的版本：

```python
    async def chat_stream(self, question: str) -> AsyncIterator[str]:
        """流式问答完整流程。逐步生成 SSE 事件。"""

        session_id = str(uuid.uuid4())

        # 1. 意图识别
        intent_result = self._classify_intent(question)
        yield self.sse_streamer.stream_intent(intent_result)

        # 2. 混合检索
        yield self.sse_streamer.stream_search_start(
            strategy=intent_result.category,
            sources=["milvus", "whoosh"],
        )

        search_results = self._retrieve(question, intent_result.category)

        yield self.sse_streamer.stream_search_result(
            chunks=len(search_results),
            top_score=search_results[0].score if search_results else 0.0,
        )

        # 3. 判断是否兜底
        use_llm_fallback = self._should_use_llm_fallback(search_results)

        if use_llm_fallback:
            # 兜底模式：发送 llm_fallback 事件 + 使用 fallback prompt
            yield self.sse_streamer.stream_llm_fallback()
            system_prompt, user_prompt = build_llm_fallback_prompt(question)
        else:
            # 正常 RAG 模式
            system_prompt, user_prompt = build_prompt(
                question, search_results, intent_result.category
            )

        yield self.sse_streamer.stream_generation_start(self.llm_engine.model_name)

        full_answer = ""
        try:
            token_stream = self.llm_engine.generate_stream(user_prompt, system_prompt)
            async for token in token_stream:
                full_answer += token
                yield self.sse_streamer.stream_token(token)
        except Exception as e:
            logger.error("llm_stream_error", error=str(e))
            raise GenerationError(f"LLM 流式生成失败: {e}")

        # 兜底回答加前缀标识
        if use_llm_fallback:
            full_answer = self._mark_llm_fallback_answer(full_answer)

        yield self.sse_streamer.stream_generation_end(full_answer, search_results)

        # 4. 正确性校验
        correctness = self.correctness_checker.check(full_answer, search_results)
        yield self.sse_streamer.stream_correctness(correctness)

        # 5. 存入 Redis
        session = QaSession(
            session_id=session_id,
            question=question,
            answer=full_answer,
            sources=search_results,
            intent=intent_result,
            correctness=correctness,
            source_type="llm_fallback" if use_llm_fallback else "knowledge_base",
            created_at=datetime.now(),
        )
        self._save_session(session)

        # 6. 完成
        yield self.sse_streamer.stream_done(session_id)

        logger.info(
            "chat_stream_completed",
            session_id=session_id,
            intent=intent_result.category,
            confidence=correctness.confidence,
            source_type=session.source_type,
        )
```

- [ ] **Step 6: 处理 llm_fallback_enabled=False 且检索为空的场景**

在 `_should_use_llm_fallback` 返回 `False` 且检索为空时，`chat()` 和 `chat_stream()` 仍使用 `build_prompt`（但 results 为空），LLM 会按系统提示说"当前知识库中没有相关内容"。这符合设计：`source_type="knowledge_base"`，LLM 回答本身会说明无内容。

额外处理：当 `llm_fallback_enabled=False` 且检索为空，在 `chat()` 中用固定提示语替代。在 `chat()` 方法中，`use_llm_fallback` 判断后增加一个分支：

```python
        # 3. Prompt 构建 + LLM 生成
        use_llm_fallback = self._should_use_llm_fallback(search_results)
        if use_llm_fallback:
            system_prompt, user_prompt = build_llm_fallback_prompt(question)
        elif not search_results:
            # 兜底关闭且检索为空 → 返回固定提示语
            answer = "当前知识库中没有检索到相关内容，请尝试其他问题或联系管理员。"
            source_type = "no_result"
        else:
            system_prompt, user_prompt = build_prompt(
                question, search_results, intent_result.category
            )

        if search_results or use_llm_fallback:
            answer = await self._generate(user_prompt, system_prompt)
            if use_llm_fallback:
                answer = self._mark_llm_fallback_answer(answer)

        if not use_llm_fallback and search_results:
            source_type = "knowledge_base"
        elif use_llm_fallback:
            source_type = "llm_fallback"
        else:
            source_type = "no_result"
```

同样在 `chat_stream()` 中处理：

```python
        if use_llm_fallback:
            yield self.sse_streamer.stream_llm_fallback()
            system_prompt, user_prompt = build_llm_fallback_prompt(question)
        elif not search_results:
            # 兜底关闭且检索为空 → 固定提示语
            full_answer = "当前知识库中没有检索到相关内容，请尝试其他问题或联系管理员。"
            source_type = "no_result"
            yield self.sse_streamer.stream_token(full_answer)
            yield self.sse_streamer.stream_generation_end(full_answer, search_results)
            correctness = self.correctness_checker.check(full_answer, search_results)
            yield self.sse_streamer.stream_correctness(correctness)
            session = QaSession(
                session_id=session_id,
                question=question,
                answer=full_answer,
                sources=search_results,
                intent=intent_result,
                correctness=correctness,
                source_type=source_type,
                created_at=datetime.now(),
            )
            self._save_session(session)
            yield self.sse_streamer.stream_done(session_id)
            return
        else:
            system_prompt, user_prompt = build_prompt(
                question, search_results, intent_result.category
            )
```

注意：`chat_stream()` 是 generator，不能用 `return` 终止 — 需要改写为逻辑分支而非 early return。改为将 LLM 流式生成部分包在条件内：

```python
        # 3. 判断是否兜底
        use_llm_fallback = self._should_use_llm_fallback(search_results)

        # 兜底关闭且无结果 → 固定提示语，跳过 LLM 生成
        skip_llm_generation = not use_llm_fallback and not search_results

        if use_llm_fallback:
            yield self.sse_streamer.stream_llm_fallback()
            system_prompt, user_prompt = build_llm_fallback_prompt(question)
        elif skip_llm_generation:
            full_answer = "当前知识库中没有检索到相关内容，请尝试其他问题或联系管理员。"
        else:
            system_prompt, user_prompt = build_prompt(
                question, search_results, intent_result.category
            )

        # LLM 流式生成（仅在非 skip 时执行）
        if not skip_llm_generation:
            yield self.sse_streamer.stream_generation_start(self.llm_engine.model_name)

            full_answer = ""
            try:
                token_stream = self.llm_engine.generate_stream(user_prompt, system_prompt)
                async for token in token_stream:
                    full_answer += token
                    yield self.sse_streamer.stream_token(token)
            except Exception as e:
                logger.error("llm_stream_error", error=str(e))
                raise GenerationError(f"LLM 流式生成失败: {e}")

            if use_llm_fallback:
                full_answer = self._mark_llm_fallback_answer(full_answer)

        yield self.sse_streamer.stream_generation_end(full_answer, search_results)

        # 确定 source_type
        source_type = "llm_fallback" if use_llm_fallback else ("no_result" if skip_llm_generation else "knowledge_base")

        # 4. 正确性校验
        correctness = self.correctness_checker.check(full_answer, search_results)
        yield self.sse_streamer.stream_correctness(correctness)

        # 5. 存入 Redis
        session = QaSession(
            session_id=session_id,
            question=question,
            answer=full_answer,
            sources=search_results,
            intent=intent_result,
            correctness=correctness,
            source_type=source_type,
            created_at=datetime.now(),
        )
        self._save_session(session)

        # 6. 完成
        yield self.sse_streamer.stream_done(session_id)

        logger.info(
            "chat_stream_completed",
            session_id=session_id,
            intent=intent_result.category,
            confidence=correctness.confidence,
            source_type=source_type,
        )
```

- [ ] **Step 7: 运行兜底逻辑测试确认通过**

```bash
cd med-rag && python -m pytest tests/test_api/test_llm_fallback.py -v
```

预期：6 个测试全部 PASS。

- [ ] **Step 8: 运行全量测试确认无破坏**

```bash
cd med-rag && python -m pytest tests/ -v --timeout=30
```

预期：所有测试 PASS。

- [ ] **Step 9: 提交**

```bash
cd med-rag && git add app/api/chat.py tests/test_api/test_llm_fallback.py && git commit -m "feat: _should_use_llm_fallback + _mark_llm_fallback_answer + chat/chat_stream 兜底逻辑 — Task 2"
```

---

### Task 3: SSE + 序列化 — stream_llm_fallback 事件 + _serialize_session source_type

**Files:**
- Modify: `med-rag/app/generation/stream.py:19-99` (SSEStreamer: 新增 stream_llm_fallback 方法)
- Modify: `med-rag/app/api/chat.py:241-281` (_serialize_session: 输出 source_type)
- Modify: `med-rag/tests/test_generation/test_stream.py` (新增 stream_llm_fallback 测试)

**Interfaces:**
- Consumes: `LLM_FALLBACK_NOTICE`（`prompt_builder.py:23`）
- Produces: `SSEStreamer.stream_llm_fallback()` 方法；`_serialize_session` 输出中的 `"source_type"` 字段

- [ ] **Step 1: 编写 stream_llm_fallback 测试**

在 `med-rag/tests/test_generation/test_stream.py` 末尾追加：

```python
def test_stream_llm_fallback():
    """llm_fallback 事件格式正确。"""

    streamer = SSEStreamer()
    event = streamer.stream_llm_fallback()
    assert event.startswith("event: llm_fallback\n")
    data = json.loads(event.split("data: ")[1].strip())
    assert "notice" in data
    assert "知识库" in data["notice"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd med-rag && python -m pytest tests/test_generation/test_stream.py::test_stream_llm_fallback -v
```

预期：`AttributeError: 'SSEStreamer' object has no attribute 'stream_llm_fallback'` FAIL。

- [ ] **Step 3: 在 SSEStreamer 中实现 stream_llm_fallback**

在 `med-rag/app/generation/stream.py` 的 `SSEStreamer` 类中，在 `stream_generation_start` 方法之前（约 line 54）添加：

```python
    def stream_llm_fallback(self) -> str:
        """生成 llm_fallback SSE 事件 — 标识回答来自模型通用知识。"""

        from app.generation.prompt_builder import LLM_FALLBACK_NOTICE

        data = {"notice": f"⚠️ {LLM_FALLBACK_NOTICE}仅供参考"}
        return f"event: llm_fallback\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd med-rag && python -m pytest tests/test_generation/test_stream.py::test_stream_llm_fallback -v
```

预期：PASS。

- [ ] **Step 5: 更新 _serialize_session 输出 source_type**

在 `med-rag/app/api/chat.py` 的 `_serialize_session` 方法中，在 `"created_at"` 字段之前（约 line 280）添加 `"source_type"` 字段：

```python
            "source_type": session.source_type,
            "created_at": session.created_at.isoformat(),
```

- [ ] **Step 6: 运行全量测试确认无破坏**

```bash
cd med-rag && python -m pytest tests/ -v --timeout=30
```

预期：所有测试 PASS。

- [ ] **Step 7: 提交**

```bash
cd med-rag && git add app/generation/stream.py app/api/chat.py tests/test_generation/test_stream.py && git commit -m "feat: SSE stream_llm_fallback 事件 + _serialize_session source_type — Task 3"
```

---

### Task 4: 前端 — SSE llm_fallback 事件接收 + 提示条 UI

**Files:**
- Modify: `med-rag/frontend/src/services/api.js:14-66` (chatStream: 新增 llm_fallback 事件监听)
- Modify: `med-rag/frontend/src/stores/chat.js` (state 新增 isLlmFallback + action 处理)
- Modify: `med-rag/frontend/src/views/ChatView.vue` (模板新增提示条 + 样式)

**Interfaces:**
- Consumes: SSE `llm_fallback` 事件（Task 3 产出）
- Produces: 前端提示条 UI，仅在 `isLlmFallback=true` 时可见

- [ ] **Step 1: 更新 api.js — 新增 llm_fallback 事件监听**

在 `med-rag/frontend/src/services/api.js` 的 `chatStream` 函数中，在 `search_result` 监听之后（约 line 28）、`generation_start` 监听之前（约 line 31）添加：

```javascript
  eventSource.addEventListener('llm_fallback', (e) => {
    callbacks.onLlmFallback?.(JSON.parse(e.data))
  })
```

- [ ] **Step 2: 更新 chat.js store — 新增 isLlmFallback 状态**

在 `med-rag/frontend/src/stores/chat.js` 中：

1. `state` 新增 `isLlmFallback: false`
2. `startStream` action 中在重置状态时加上 `this.isLlmFallback = false`
3. `startStream` 的回调中新增 `onLlmFallback`：
```javascript
        onLlmFallback: (data) => {
          this.isLlmFallback = true
        },
```
4. `clearChat` action 中加上 `this.isLlmFallback = false`

完整改动后的 state 和 actions：

```javascript
export const useChatStore = defineStore('chat', {
  state: () => ({
    question: '',
    answer: '',
    isStreaming: false,
    isLlmFallback: false,
    sources: [],
    intent: null,
    correctness: null,
    sessions: [],
    eventSource: null,
  }),

  actions: {
    // SSE 流式问答
    startStream(question) {
      this.question = question
      this.answer = ''
      this.isStreaming = false
      this.isLlmFallback = false
      this.sources = []
      this.intent = null
      this.correctness = null
      this.isStreaming = true

      this.eventSource = chatStream(question, {
        onIntent: (data) => {
          this.intent = data
        },
        onSearchStart: (data) => {
          // 检索开始
        },
        onSearchResult: (data) => {
          // 检索完成
        },
        onLlmFallback: (data) => {
          this.isLlmFallback = true
        },
        onGenerationStart: (data) => {
          // LLM 生成开始
        },
        onToken: (data) => {
          this.answer += data.content
        },
        onGenerationEnd: (data) => {
          this.sources = (data.sources || []).map(source => ({
            ...source,
            content_preview: source.content_preview || source.content || '',
          }))
        },
        onCorrectness: (data) => {
          this.correctness = data
        },
        onDone: (data) => {
          this.isStreaming = false
        },
        onError: (data) => {
          this.isStreaming = false
          this.answer += `\n\n❌ 错误: ${data.message || '未知错误'}`
        },
      })
    },

    // 停止流式
    stopStream() {
      if (this.eventSource) {
        this.eventSource.close()
        this.eventSource = null
      }
      this.isStreaming = false
    },

    // 加载历史会话
    async loadSessions() {
      try {
        const res = await listSessions()
        this.sessions = res.data.sessions || []
      } catch (e) {
        this.sessions = []
      }
    },

    // 删除会话
    async removeSession(sessionId) {
      await deleteSession(sessionId)
      this.sessions = this.sessions.filter(s => s.session_id !== sessionId)
    },

    // 清空当前问答
    clearChat() {
      this.question = ''
      this.answer = ''
      this.isLlmFallback = false
      this.sources = []
      this.intent = null
      this.correctness = null
    },
  },
})
```

- [ ] **Step 3: 更新 ChatView.vue — 添加提示条模板**

在 `med-rag/frontend/src/views/ChatView.vue` 的模板中，在 `<div class="messages">` 内、`<article v-if="chatStore.intent"` 之前（约 line 41），插入提示条：

```html
          <div v-if="chatStore.isLlmFallback" class="llm-fallback-notice">
            ⚠️ 知识库中未检索到相关内容，以下为模型基于通用知识的回答，仅供参考
          </div>
```

- [ ] **Step 4: 更新 ChatView.vue — 添加提示条样式**

在 `med-rag/frontend/src/views/ChatView.vue` 的 `<style scoped>` 中，在 `.messages` 样式之前（约 line 408）添加：

```css
.llm-fallback-notice {
  margin: 0 20px 12px;
  padding: 10px 14px;
  border: 1px solid var(--amber);
  border-radius: 8px;
  background: rgba(245, 158, 11, 0.12);
  color: var(--amber);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.6;
}
```

- [ ] **Step 5: 验证前端无构建错误**

```bash
cd med-rag/frontend && npm run build
```

预期：构建成功，无编译错误。

- [ ] **Step 6: 提交**

```bash
cd med-rag && git add frontend/src/services/api.js frontend/src/stores/chat.js frontend/src/views/ChatView.vue && git commit -m "feat: 前端 LLM 兜底提示条 — SSE llm_fallback 事件 + isLlmFallback 状态 + 提示条 UI — Task 4"
```

---

### Task 5: 集成验证 — 端到端手动测试 + 修复遗漏

**Files:**
- No new files — 手动验证 + 修复任何遗漏

**Interfaces:**
- Consumes: Tasks 1-4 所有产出
- Produces: 确认功能端到端可用

- [ ] **Step 1: 运行全量后端测试**

```bash
cd med-rag && python -m pytest tests/ -v --timeout=30
```

预期：所有测试 PASS。

- [ ] **Step 2: 验证前端构建**

```bash
cd med-rag/frontend && npm run build
```

预期：构建成功。

- [ ] **Step 3: 手动检查 — 验证 SSE 事件格式**

用 curl 模拟 SSE 流式请求，观察 `llm_fallback` 事件是否正确出现（需要服务运行）：

```bash
# 如果服务运行中：
curl -N "http://localhost:8000/api/v1/chat/stream?question=完全无关的问题"
```

预期：在 `search_result` 之后出现 `event: llm_fallback` 事件。

- [ ] **Step 4: 最终提交（如有修复）**

```bash
cd med-rag && git add -A && git commit -m "fix: 集成验证修复 — Task 5"
```

如果没有修复则跳过此步。
