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

### 临时管理鉴权

正式身份与部门权限上线前，文档、评估和引擎信息接口要求请求头
`X-Med-Rag-Admin-Key`。请将 `RAG_BOOTSTRAP_ADMIN_KEY` 设置为至少 32 位随机值；
未配置时这些接口会返回 503，不会以匿名方式降级开放。该临时密钥会在本地账户与 RBAC
上线后移除。

## License

MIT
