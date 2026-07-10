"""API 中间件 — 请求日志 + 限速 + 全局异常处理。"""

from __future__ import annotations

import time
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import MedRagError
from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware:
    """请求日志中间件。记录每个请求的路径、方法、耗时。"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        path = scope.get("path", "")
        method = scope.get("method", "")
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "api_request",
                method=method,
                path=path,
                status=status_code,
                duration_ms=round(duration_ms, 2),
            )

            if duration_ms > 5000:
                logger.warning(
                    "slow_request",
                    method=method,
                    path=path,
                    duration_ms=round(duration_ms, 2),
                )


class RateLimitMiddleware:
    """简单限速中间件。

    基于 IP + 路径的滑动窗口限速。
    生产环境应使用 Redis + slowapi。
    """

    # 限速配置：路径 → (最大请求数, 窗口秒数)
    RATE_LIMITS = {
        "/api/v1/chat/stream": (30, 60),    # 流式问答：30次/分钟
        "/api/v1/chat/complete": (20, 60),   # 完整问答：20次/分钟
        "/api/v1/documents/upload": (10, 60), # 文件上传：10次/分钟
    }

    # 默认限速
    DEFAULT_LIMIT = (60, 60)  # 60次/分钟

    def __init__(self, app, redis_client=None):
        self.app = app
        self.redis_client = redis_client
        # 无 Redis 时使用内存限速（单进程有效）
        self._in_memory_counts: dict[str, list[float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # 非限速路径直接放行
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        # 获取限速配置
        max_requests, window = self.RATE_LIMITS.get(path, self.DEFAULT_LIMIT)

        # 限速键
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        rate_key = f"{client_ip}:{path}"

        # Redis 限速
        if self.redis_client is not None:
            from app.core.config import get_config
            cfg = get_config()
            prefix = cfg["redis"].get("rate_limit_prefix", "med_rag:rate:")
            redis_key = f"{prefix}{rate_key}"

            current = self.redis_client.get(redis_key)
            if current and int(current) >= max_requests:
                response = JSONResponse(
                    status_code=429,
                    content={
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"请求过于频繁，{path} 限制 {max_requests}次/{window}秒",
                    },
                )
                await response(scope, receive, send)
                return

            # 使用 Redis INCR + EXPIRE
            pipe = self.redis_client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window)
            pipe.execute()

        else:
            # 内存限速
            now = time.time()
            counts = self._in_memory_counts.get(rate_key, [])
            # 清除过期记录
            counts = [t for t in counts if now - t < window]
            if len(counts) >= max_requests:
                response = JSONResponse(
                    status_code=429,
                    content={
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"请求过于频繁，{path} 限制 {max_requests}次/{window}秒",
                    },
                )
                await response(scope, receive, send)
                return
            counts.append(now)
            self._in_memory_counts[rate_key] = counts

        await self.app(scope, receive, send)


async def med_rag_exception_handler(request: Request, exc: MedRagError) -> JSONResponse:
    """Med-Rag 业务异常全局处理器。"""

    # 映射异常 code → HTTP status code
    status_map = {
        "VALIDATION_ERROR": 400,
        "RETRIEVAL_ERROR": 503,
        "GENERATION_ERROR": 503,
        "DOCUMENT_ERROR": 400,
        "INTENT_ERROR": 503,
        "EVALUATION_ERROR": 500,
        "CONFIGURATION_ERROR": 500,
    }

    status_code = status_map.get(exc.code, 500)

    logger.warning(
        "business_exception",
        code=exc.code,
        message=exc.message,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "code": exc.code,
            "message": exc.message,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常全局处理器。"""

    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=request.url.path,
        traceback=traceback.format_exc(),
    )

    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "内部服务异常，请稍后重试",
        },
    )
