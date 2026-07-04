"""Optional second-stage reranker for dynamic memory recall."""

from __future__ import annotations

import time
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover - deployment normally has requests
    requests = None

from config import (
    DYNAMIC_MEMORY_RERANK_ALLOW_CUSTOM_URL,
    DYNAMIC_MEMORY_RERANK_API_URL,
    DYNAMIC_MEMORY_RERANK_BLEND,
    DYNAMIC_MEMORY_RERANK_DOCUMENT_MAX_CHARS,
    DYNAMIC_MEMORY_RERANK_ENABLED,
    DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES,
    DYNAMIC_MEMORY_RERANK_MODEL,
    DYNAMIC_MEMORY_RERANK_PROVIDER,
    DYNAMIC_MEMORY_RERANK_QUERY_MAX_CHARS,
    DYNAMIC_MEMORY_RERANK_TIMEOUT_SECONDS,
    DYNAMIC_MEMORY_RERANK_TOP_N,
    is_siliconflow_url,
    resolve_siliconflow_api_key,
)
from utils.log import get_logger

logger = get_logger(__name__)

_QWEN_RERANK_PREFIX = "Qwen/Qwen3-Reranker-"


def dynamic_memory_rerank_enabled() -> bool:
    return bool(DYNAMIC_MEMORY_RERANK_ENABLED and DYNAMIC_MEMORY_RERANK_PROVIDER == "siliconflow")


def _clip_text(text: str, max_chars: int) -> str:
    t = str(text or "").strip()
    if max_chars > 0 and len(t) > max_chars:
        return t[:max_chars]
    return t


def _safe_score(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        return 0.0
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def rerank_dynamic_memory_documents(query: str, documents: list[dict]) -> dict:
    """
    documents: [{"memory_id": str, "text": str, "hybrid_score": float}]
    Returns a debug-friendly dict and never raises for caller fallback.
    """
    if not dynamic_memory_rerank_enabled():
        return {"enabled": False, "ok": False, "reason": "disabled"}
    if not documents:
        return {"enabled": True, "ok": False, "reason": "empty_documents"}
    if not str(query or "").strip():
        return {"enabled": True, "ok": False, "reason": "empty_query", "model": DYNAMIC_MEMORY_RERANK_MODEL}
    if not DYNAMIC_MEMORY_RERANK_ALLOW_CUSTOM_URL and not is_siliconflow_url(DYNAMIC_MEMORY_RERANK_API_URL):
        return {"enabled": True, "ok": False, "reason": "unsafe_api_url", "model": DYNAMIC_MEMORY_RERANK_MODEL}

    api_key = resolve_siliconflow_api_key()
    if not api_key:
        return {"enabled": True, "ok": False, "reason": "missing_api_key", "model": DYNAMIC_MEMORY_RERANK_MODEL}
    if requests is None:
        return {"enabled": True, "ok": False, "reason": "missing_requests", "model": DYNAMIC_MEMORY_RERANK_MODEL}

    candidates = [doc for doc in documents[: max(1, int(DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES or 30))] if doc]
    texts = [_clip_text(str(doc.get("text") or ""), int(DYNAMIC_MEMORY_RERANK_DOCUMENT_MAX_CHARS or 900)) for doc in candidates]
    id_by_index = [str(doc.get("memory_id") or "") for doc in candidates]
    texts = [text if text else "(empty)" for text in texts]
    top_n = min(len(texts), max(1, int(DYNAMIC_MEMORY_RERANK_TOP_N or 12)))
    payload = {
        "model": DYNAMIC_MEMORY_RERANK_MODEL,
        "query": _clip_text(query, int(DYNAMIC_MEMORY_RERANK_QUERY_MAX_CHARS or 1200)),
        "documents": texts,
        "top_n": top_n,
        "return_documents": False,
    }
    if str(DYNAMIC_MEMORY_RERANK_MODEL or "").startswith(_QWEN_RERANK_PREFIX):
        payload["instruction"] = "根据当前对话语境，优先选择最能帮助回复小玥的动态记忆。"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    started = time.time()
    try:
        resp = requests.post(
            DYNAMIC_MEMORY_RERANK_API_URL,
            headers=headers,
            json=payload,
            timeout=max(0.3, float(DYNAMIC_MEMORY_RERANK_TIMEOUT_SECONDS or 2.5)),
            allow_redirects=False,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        if resp.status_code >= 300:
            trace_id = (
                resp.headers.get("x-siliconcloud-trace-id")
                or resp.headers.get("x-request-id")
                or resp.headers.get("cf-ray")
                or ""
            )
            logger.warning(
                "dynamic memory rerank failed status=%s model=%s docs=%s trace_id=%s",
                resp.status_code,
                DYNAMIC_MEMORY_RERANK_MODEL,
                len(texts),
                trace_id,
            )
            return {
                "enabled": True,
                "ok": False,
                "reason": "http_error",
                "status": resp.status_code,
                "model": DYNAMIC_MEMORY_RERANK_MODEL,
                "elapsed_ms": elapsed_ms,
                "trace_id": str(trace_id or "")[:80],
            }
        data = resp.json()
        if not isinstance(data, dict):
            return {
                "enabled": True,
                "ok": False,
                "reason": "invalid_json_shape",
                "model": DYNAMIC_MEMORY_RERANK_MODEL,
                "elapsed_ms": elapsed_ms,
            }
    except Exception as e:
        elapsed_ms = int((time.time() - started) * 1000)
        logger.warning("dynamic memory rerank exception model=%s docs=%s error=%s", DYNAMIC_MEMORY_RERANK_MODEL, len(texts), e)
        return {
            "enabled": True,
            "ok": False,
            "reason": "exception",
            "error": str(e)[:160],
            "model": DYNAMIC_MEMORY_RERANK_MODEL,
            "elapsed_ms": elapsed_ms,
        }

    ranked: list[dict] = []
    for rank, item in enumerate(data.get("results") or []):
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except Exception:
            continue
        if idx < 0 or idx >= len(id_by_index):
            continue
        ranked.append(
            {
                "rank": rank,
                "index": idx,
                "memory_id": id_by_index[idx],
                "score": _safe_score(item.get("relevance_score")),
                "raw_score": item.get("relevance_score"),
            }
        )

    if not ranked:
        return {
            "enabled": True,
            "ok": False,
            "reason": "empty_results",
            "model": DYNAMIC_MEMORY_RERANK_MODEL,
            "elapsed_ms": int((time.time() - started) * 1000),
            "candidate_count": len(texts),
        }

    return {
        "enabled": True,
        "ok": True,
        "provider": DYNAMIC_MEMORY_RERANK_PROVIDER,
        "model": DYNAMIC_MEMORY_RERANK_MODEL,
        "blend": float(DYNAMIC_MEMORY_RERANK_BLEND or 0.78),
        "elapsed_ms": int((time.time() - started) * 1000),
        "candidate_count": len(texts),
        "returned_count": len(ranked),
        "ranked": ranked,
        "meta": data.get("meta") if isinstance(data.get("meta"), dict) else {},
    }
