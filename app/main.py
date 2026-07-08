"""Med-Rag FastAPI 入口。

组装所有模块和路由。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_config
from app.core.logging import setup_logging
from app.core.exceptions import MedRagError
from app.api.middleware import (
    RequestLoggingMiddleware,
    RateLimitMiddleware,
    med_rag_exception_handler,
    unhandled_exception_handler,
)
from app.api.chat_routes import router as chat_router
from app.api.documents import router as documents_router
from app.api.evaluation import router as evaluation_router
from app.api.health import router as health_router

config = get_config()
setup_logging(config.get("log_level", "INFO"))

app = FastAPI(
    title=config["app"]["name"],
    description="企业级医疗行业 RAG 知识助手",
    version=config["app"]["version"],
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 中间件 ──
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)

# ── 异常处理器 ──
app.add_exception_handler(MedRagError, med_rag_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── 路由注册 ──
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(evaluation_router)
