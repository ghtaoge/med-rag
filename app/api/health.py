"""健康检查 + 引擎信息路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_config_dep
from app.security.bootstrap_auth import verify_bootstrap_admin

router = APIRouter(tags=["系统"])


@router.get("/health")
async def health(config: dict = Depends(get_config_dep)):
    """健康检查。"""

    return {"status": "ok", "version": config["app"]["version"]}


@router.get("/api/v1/engines", dependencies=[Depends(verify_bootstrap_admin)])
async def engines(config: dict = Depends(get_config_dep)):
    """查看当前引擎信息。"""

    return {
        "llm_provider": config["llm"]["provider"],
        "llm_model": config["llm"][config["llm"]["provider"]]["model"],
        "embedding_model": "bge-large-zh-v1.5",
        "embedding_dim": config["milvus"]["embedding_dim"],
        "vector_store": "Milvus",
        "keyword_store": "Whoosh BM25",
        "reranker": "bge-reranker-v2-m3",
        "hybrid_method": "RRF (Reciprocal Rank Fusion)",
    }
