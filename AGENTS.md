# Repository Guidelines

## 项目结构与模块组织

本仓库是医疗行业 RAG 知识助手。后端源码位于 `app/`，入口为 `app/main.py`。核心模块按职责拆分：`app/core/` 放配置、日志、异常和通用模型；`app/documents/` 负责文档加载、切块、校验和增量同步；`app/retrieval/` 包含 Milvus、Whoosh BM25、RRF 融合、重排和元数据过滤；`app/generation/` 管理 LLM Provider、Prompt 构建和 SSE 流式生成；`app/intent/` 处理意图识别和策略路由；`app/evaluation/` 放正确性与召回评估；`app/api/` 放 FastAPI 路由。前端在 `frontend/`，测试在 `tests/`，示例资料在 `data/`，部署文件在 `deploy/`。

## 构建、测试与本地开发命令

- `pip install -e ".[dev]"`：安装后端开发依赖，包括 pytest 与 ruff。
- `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`：启动后端开发服务。
- `pytest tests/ -v`：运行全部后端测试。
- `pytest tests/test_retrieval/ -v`：按模块运行测试，便于定位检索相关问题。
- `cd frontend && npm install`：安装前端依赖。
- `cd frontend && npm run dev`：启动 Vite 开发服务。
- `cd frontend && npm run build`：构建前端产物。
- `docker-compose up -d`：启动 Milvus、Redis 和应用服务。

## 编码风格与命名约定

Python 目标版本为 3.10，使用 4 空格缩进。Ruff 配置行宽为 100，提交前建议运行 `ruff check app tests`。模块、文件和函数使用 `snake_case`，类使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。前端使用 Vue 3 单文件组件，视图组件命名为 `*View.vue`，Pinia store 使用小写领域名，例如 `chat.js`、`document.js`。

## 测试指南

测试框架为 pytest，配置见 `pyproject.toml`。测试文件遵循 `test_*.py` 命名，并按业务模块组织在 `tests/test_api/`、`tests/test_documents/`、`tests/test_generation/` 等目录中。新增后端功能时，应补充对应模块测试；涉及异步逻辑时使用已配置的 `pytest-asyncio`。

## 提交与 Pull Request 规范

当前提交历史采用简洁的 Conventional Commits 风格，例如 `feat: Med-Rag 企业级医疗知识助手`、`chore: gitignore 增加 package-lock.json 排除`。建议继续使用 `feat:`、`fix:`、`chore:`、`test:`、`docs:` 前缀。PR 应说明变更目的、影响范围、验证命令；涉及前端界面时附截图；涉及配置或部署时说明 `.env`、`config.yaml` 或 `docker-compose.yml` 的变更点。

## 安全与配置提示

不要提交 API Key、真实医疗数据或本地 `.env` 文件。API Key 应通过环境变量传入，生产环境必须修改 `docker-compose.yml` 中 MinIO 等默认凭据。测试数据应使用匿名化样例，避免把敏感文档放入 `data/` 后直接提交。
