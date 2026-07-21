# Med-Rag — 企业级医疗行业 RAG 知识助手

> 基于知识库的智能问答系统，回答标注来源，自动检测幻觉，支持多格式文档、增量同步、混合检索。

## 架构概览

```
用户提问 → 意图识别 → 检索策略 → 混合检索 → Prompt构建 → LLM生成 → 正确性校验 → SSE流式输出
                        │              │
                  规则+LLM双模式    Milvus + Whoosh BM25 → RRF融合 → Reranker重排序
```

## 核心特性

| 特性 | 说明 |
|---|---|
| **混合检索** | Milvus 向量 + Whoosh BM25 + RRF 融合 + bge-reranker 重排序 |
| **多模型 LLM** | DeepSeek / 通义千问 / 智谱 GLM，OpenAI 兼容格式统一适配 |
| **意图识别** | 规则关键词 + LLM 双模式，5 种意图类别自动路由检索策略 |
| **正确性校验** | 来源一致性 + 幻觉检测 + 医疗关键词验证 + 置信度评分 |
| **8 格式文档** | TXT/MD/PDF/DOCX/PNG/JPG/XLSX/CSV/PPTX + PaddleOCR 扫描件 |
| **增量同步** | SHA-256 文件指纹 + 双缓冲切换，单文件更新不影响线上服务 |
| **SSE 流式** | 逐 token 实时输出，完整事件序列（意图→检索→生成→校验→完成） |
| **评估系统** | Recall/Precision/F1/MRR + 相关性分析 + 上线检查清单 + 建议报告 |

## 项目结构

```
med-rag/
├── app/
│   ├── core/           # 配置、异常、日志、模型、依赖注入
│   ├── documents/      # 文档加载(8格式)、智能切块、增量同步、校验
│   ├── retrieval/      # Milvus、Whoosh BM25、RRF融合、Reranker、元数据过滤
│   ├── generation/     # LLM引擎(ABC)、3 Provider、医疗Prompt、SSE流式
│   ├── intent/         # 意图分类(规则+LLM)、检索策略路由
│   ├── evaluation/     # 正确性校验、召回评估、相关性评估、报告生成
│   ├── api/            # FastAPI路由、对话编排、限速、异常处理
│   └── main.py         # FastAPI 入口
├── frontend/           # Vue 3 + Vite + Element Plus SPA
├── tests/              # 103 个测试（pytest）
├── config.yaml         # 配置文件
├── Dockerfile          # 多阶段构建
├── docker-compose.yml  # Milvus + Redis + Med-Rag
└── deploy/             # nginx.conf + start.sh
```

## 快速开始

### 1. 环境准备

```bash
# Python 依赖
pip install -e ".[dev]"

# 前端依赖
cd frontend && npm install && npm run build
```

### 2. 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 在 .env 中填入 API Key（勿硬编码到 config.yaml）
# DEEPSEEK_API_KEY=your-key-here
```

### 3. 运行后端

```bash
# 开发模式
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### 4. 运行前端

```bash
cd frontend
npm run dev    # 开发模式 → http://localhost:3000
npm run build  # 构建 → dist/
```

### 5. Docker 部署

```bash
# 启动全部服务（Milvus + Redis + Med-Rag）
docker-compose up -d

# ⚠️ 生产部署前请修改 docker-compose.yml 中的默认密码和 API Key
```

## API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 健康检查 |
| `/api/v1/engines` | GET | 引擎信息 |
| `/api/v1/chat/stream` | POST | SSE 流式问答 |
| `/api/v1/chat/complete` | POST | 非流式问答 |
| `/api/v1/chat/sessions` | GET | 会话列表 |
| `/api/v1/chat/sessions/{id}` | GET/DELETE | 会话详情/删除 |
| `/api/v1/documents/list` | GET | 文档列表 |
| `/api/v1/documents/upload` | POST | 上传文档 |
| `/api/v1/documents/sync` | POST | 全量同步 |
| `/api/v1/documents/sync/{filename}` | POST | 单文件同步 |
| `/api/v1/documents/{filename}` | DELETE | 删除文档 |
| `/api/v1/evaluation/checklist` | GET | 上线检查清单 |
| `/api/v1/evaluation/stats` | GET | 运行统计 |

### SSE 事件序列

```
intent → search_start → search_result → generation_start → token* → generation_end → correctness → done
```

## 测试

```bash
# 全量测试（103 tests）
pytest tests/ -v

# 冒烟测试
pytest tests/test_smoke.py -v

# 各模块测试
pytest tests/test_documents/ -v
pytest tests/test_retrieval/ -v
pytest tests/test_generation/ -v
```

## 技术栈

| 层级 | 技术 |
|---|---|
| 向量库 | Milvus (HNSW + COSINE) |
| Embedding | bge-large-zh-v1.5 (1024d) |
| 关键词 | Whoosh BM25 + jieba 中文分词 + 医疗词典 |
| Reranker | bge-reranker-v2-m3 (CrossEncoder) |
| 混合融合 | RRF (Reciprocal Rank Fusion, k=60) |
| LLM | DeepSeek / Qwen / Zhipu (OpenAI 兼容格式) |
| OCR | PaddleOCR（扫描件） |
| 后端 | FastAPI + uvicorn + structlog |
| 前端 | Vue 3 + Vite + Element Plus + Pinia |
| 缓存 | Redis（文件指纹 + 会话存储 + 限速） |
| 部署 | Docker + Nginx + docker-compose |

## 安全提醒

- ⚠️ **API Key** 请通过 `.env` 环境变量传入，**勿硬编码到任何文件中**
- ⚠️ **docker-compose.yml** 中 Milvus/MinIO 的默认密码仅适用于开发环境，**生产部署前必须修改**
- ⚠️ `.env` 文件已被 `.gitignore` 排除，不会被提交到 Git

### 身份与数据库运维

生产环境必须配置 PostgreSQL 和至少 32 字符的随机 JWT 密钥。临时管理 Key 已停用，管理接口统一使用短期 Access Token、旋转 Refresh Token 和部门角色授权。

```bash
# 生成密钥并写入部署环境，不要提交实际值
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 启动基础设施和应用，容器启动时会先执行 Alembic 迁移
docker compose up -d --build

# 创建或复用初始平台管理员，密码只从环境变量读取
docker compose exec \
  -e RAG_INITIAL_ADMIN_PASSWORD='replace-with-a-strong-password' \
  med-rag python scripts/create_admin.py
```

数据库迁移、备份和恢复：

```bash
docker compose exec med-rag alembic upgrade head
docker compose exec postgres pg_dump -U med_rag -Fc med_rag > med_rag.dump
docker compose exec -T postgres pg_restore -U med_rag -d med_rag --clean < med_rag.dump
```

备份范围还应包含 `knowledge_data`、`whoosh_data` 和 Milvus 数据卷。恢复后，对已批准文档执行索引重建，确保数据库 ACL 与两个检索索引一致。

### 输入与输出安全网关

安全网关在意图识别和检索之前运行。它先做 Unicode 归一化与确定性 DLP，再将脱敏文本发送给内网 Qwen3Guard。分类器不可用时，普通请求降为受限检索，超过 500 字或命中高风险规则的请求直接阻断。

```bash
# 启动应用与内网 GPU 安全模型，模型端口不会发布到宿主机
docker compose --profile safety-gpu up -d --build

# 执行固定 200 条案例的离线、确定性发布门禁
python scripts/evaluate_safety.py

# 连同本地 Qwen3Guard 执行语义评估
RAG_SAFETY_EVAL_USE_CLASSIFIER=true python scripts/evaluate_safety.py
```

策略变更必须同步提升 `RAG_SAFETY_POLICY_VERSION`，重新评审 `data/evaluation/safety_cases.jsonl` 并通过门禁。安全事件只保留输入哈希、脱敏摘要、类别和决策；保留周期应按公司安全审计制度配置，导出时不得包含原始请求正文。

## License

MIT
