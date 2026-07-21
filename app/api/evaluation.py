"""效果评估路由 — 上线检查清单 + 评估测试。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from app.security.bootstrap_auth import verify_bootstrap_admin

from app.core.dependencies import (
    get_config_dep,
    get_milvus_store,
    get_keyword_store,
    get_llm_engine,
    get_redis_client,
)

router = APIRouter(
    prefix="/api/v1/evaluation",
    tags=["评估"],
    dependencies=[Depends(verify_bootstrap_admin)],
)


@router.get("/checklist")
async def launch_checklist(
    config: dict = Depends(get_config_dep),
    milvus_store=Depends(get_milvus_store),
    keyword_store=Depends(get_keyword_store),
    llm_engine=Depends(get_llm_engine),
    redis_client=Depends(get_redis_client),
):
    """上线检查清单 — 检查所有核心组件是否就绪。"""

    checks = []

    # Milvus 连通性
    milvus_ok = False
    try:
        milvus_ok = milvus_store.ping()
        chunk_count = milvus_store.get_chunk_count()
    except Exception:
        chunk_count = 0
    checks.append({
        "item": "Milvus 向量库",
        "status": "ok" if milvus_ok else "error",
        "detail": f"连通: {milvus_ok}, chunk数: {chunk_count}",
    })

    # Whoosh 关键词库
    keyword_ok = False
    try:
        kw_count = keyword_store.get_chunk_count()
        keyword_ok = kw_count > 0
    except Exception:
        kw_count = 0
    checks.append({
        "item": "Whoosh 关键词库",
        "status": "ok" if keyword_ok else "warning",
        "detail": f"chunk数: {kw_count}",
    })

    # LLM 连通性
    llm_ok = False
    llm_detail = ""
    try:
        # 简单连通测试 — 发送极短 prompt
        test_answer = await llm_engine.generate("测试", "请回复OK")
        llm_ok = len(test_answer) > 0
        llm_detail = f"模型: {llm_engine.model_name}, 响应长度: {len(test_answer)}"
    except Exception as e:
        llm_detail = f"连接失败: {str(e)[:100]}"
    checks.append({
        "item": "LLM 引擎",
        "status": "ok" if llm_ok else "error",
        "detail": llm_detail,
    })

    # Redis 连通性
    redis_ok = False
    if redis_client is not None:
        try:
            redis_client.ping()
            redis_ok = True
        except Exception:
            pass
    checks.append({
        "item": "Redis 缓存",
        "status": "ok" if redis_ok else "error",
        "detail": f"连通: {redis_ok}",
    })

    # 知识库目录
    from pathlib import Path
    knowledge_dir = Path(config["knowledge_dir"])
    files = [
        f
        for f in knowledge_dir.glob("*")
        if f.is_file() and f.suffix.lower() in {
            ".txt", ".md", ".pdf", ".docx", ".png", ".jpg",
            ".jpeg", ".tiff", ".xlsx", ".csv", ".pptx", ".bmp",
        }
    ]
    checks.append({
        "item": "知识库文件",
        "status": "ok" if len(files) > 0 else "warning",
        "detail": f"文件数: {len(files)}",
    })

    # 配置完整性
    required_keys = ["app", "milvus", "redis", "llm", "chunker", "retrieval"]
    missing_keys = [k for k in required_keys if k not in config]
    checks.append({
        "item": "配置完整性",
        "status": "ok" if not missing_keys else "error",
        "detail": f"缺失: {missing_keys}" if missing_keys else "配置完整",
    })

    # 总体评估
    all_ok = all(c["status"] == "ok" for c in checks)
    has_warning = any(c["status"] == "warning" for c in checks)
    has_error = any(c["status"] == "error" for c in checks)

    overall = "ready"
    if has_error:
        overall = "not_ready"
    elif has_warning:
        overall = "partial_ready"

    return {
        "overall_status": overall,
        "checks": checks,
        "ready_for_production": all_ok and not has_warning,
    }


@router.get("/stats")
async def evaluation_stats(
    config: dict = Depends(get_config_dep),
    milvus_store=Depends(get_milvus_store),
    keyword_store=Depends(get_keyword_store),
    redis_client=Depends(get_redis_client),
):
    """获取系统运行统计。"""

    # 向量库统计
    milvus_count = 0
    try:
        milvus_count = milvus_store.get_chunk_count()
    except Exception:
        pass

    # 关键词库统计
    keyword_count = 0
    try:
        keyword_count = keyword_store.get_chunk_count()
    except Exception:
        pass

    # 会话统计
    session_count = 0
    if redis_client is not None:
        from app.core.config import get_config
        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        try:
            session_keys = redis_client.keys(f"{prefix}*")
            session_count = len(session_keys)
        except Exception:
            pass

    # 知识库文件数
    from pathlib import Path
    knowledge_dir = Path(config["knowledge_dir"])
    file_count = len([
        f for f in knowledge_dir.glob("*")
        if f.is_file() and f.suffix.lower() in {
            ".txt", ".md", ".pdf", ".docx", ".png", ".jpg",
            ".jpeg", ".tiff", ".xlsx", ".csv", ".pptx", ".bmp",
        }
    ])

    return {
        "milvus_chunks": milvus_count,
        "keyword_chunks": keyword_count,
        "knowledge_files": file_count,
        "qa_sessions": session_count,
        "llm_provider": config["llm"]["provider"],
        "embedding_model": "bge-large-zh-v1.5",
        "reranker": "bge-reranker-v2-m3",
    }
