import time
from hashlib import sha256

import requests

from memory_vector.config import (
    CF_ACCOUNT_ID,
    CF_API_TOKEN,
    CF_EMBEDDING_MODEL,
    CF_EMBEDDING_POOLING,
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_MAX_CHARS,
    EMBED_CACHE_TTL_SECONDS,
    EMBED_CACHE_MAX_ITEMS,
    EMBED_REQUEST_TIMEOUT_SECONDS,
    EMBED_MAX_RETRIES,
    EMBED_RETRY_BACKOFF_SECONDS,
    current_embedding_backend,
)
from utils.log import get_logger

logger = get_logger(__name__)

_embed_cache: dict[str, tuple[float, list[float]]] = {}


def normalize_text(text: str) -> str:
    t = (text or "").replace("\n", " ").strip()
    if EMBEDDING_MAX_CHARS and len(t) > EMBEDDING_MAX_CHARS:
        t = t[:EMBEDDING_MAX_CHARS]
    return t


def content_hash(text: str) -> str:
    t = normalize_text(text)
    h = sha256(t.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


def _cache_get(key: str) -> list[float] | None:
    if not key:
        return None
    v = _embed_cache.get(key)
    if not v:
        return None
    ts, emb = v
    if EMBED_CACHE_TTL_SECONDS and (time.time() - ts) > EMBED_CACHE_TTL_SECONDS:
        _embed_cache.pop(key, None)
        return None
    return emb


def _cache_set(key: str, emb: list[float]) -> None:
    if not key or not emb:
        return
    _embed_cache[key] = (time.time(), emb)
    if EMBED_CACHE_MAX_ITEMS and len(_embed_cache) > EMBED_CACHE_MAX_ITEMS:
        # 简单淘汰：删除最旧的一批
        items = sorted(_embed_cache.items(), key=lambda kv: kv[1][0])
        drop = max(1, len(_embed_cache) - EMBED_CACHE_MAX_ITEMS)
        for i in range(drop):
            _embed_cache.pop(items[i][0], None)


def _timeout_seconds() -> int:
    try:
        return max(5, int(EMBED_REQUEST_TIMEOUT_SECONDS or 45))
    except Exception:
        return 45


def _backend_model_desc() -> str:
    backend = current_embedding_backend()
    model = CF_EMBEDDING_MODEL if backend == "cloudflare_bge" else EMBEDDING_MODEL
    return f"{backend}/{model or '(empty)'}"


def _embed_via_cloudflare(text: str) -> list[float]:
    if not (CF_ACCOUNT_ID and CF_API_TOKEN):
        raise RuntimeError("CF_ACCOUNT_ID / CLOUDFLARE_API_TOKEN 未配置")
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_EMBEDDING_MODEL}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {"text": text, "truncate_inputs": True}
    if CF_EMBEDDING_POOLING in ("mean", "cls"):
        payload["pooling"] = CF_EMBEDDING_POOLING

    started = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=_timeout_seconds())
    elapsed_ms = int((time.time() - started) * 1000)
    if resp.status_code >= 400:
        body_preview = (resp.text or "")[:400]
        logger.warning(
            "Cloudflare embeddings 异常 status=%s elapsed_ms=%s model=%s body=%s",
            resp.status_code,
            elapsed_ms,
            CF_EMBEDDING_MODEL,
            body_preview,
        )
        raise RuntimeError(f"Cloudflare AI embeddings HTTP {resp.status_code}: {body_preview}")
    data = resp.json()
    # 兼容两种结构：直接返回 {data:[...]} 或 CF v4 包裹 {result:{data:[...]}}
    result = data.get("result") if isinstance(data, dict) else None
    obj = result if isinstance(result, dict) else (data if isinstance(data, dict) else {})
    emb_list = obj.get("data")
    if not isinstance(emb_list, list) or not emb_list:
        raise RuntimeError("Cloudflare AI embeddings 返回缺少 data")
    emb = emb_list[0]
    if not isinstance(emb, list):
        raise RuntimeError("Cloudflare AI embeddings data[0] 非向量")
    logger.info("Cloudflare embeddings 成功 elapsed_ms=%s model=%s dim=%s", elapsed_ms, CF_EMBEDDING_MODEL, len(emb))
    return [float(x) for x in emb]


def _embed_via_openai(text: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 未配置")
    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": EMBEDDING_MODEL, "input": text}
    started = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=_timeout_seconds())
    elapsed_ms = int((time.time() - started) * 1000)
    if resp.status_code >= 400:
        body_preview = (resp.text or "")[:400]
        logger.warning(
            "OpenAI embeddings 异常 status=%s elapsed_ms=%s model=%s body=%s",
            resp.status_code,
            elapsed_ms,
            EMBEDDING_MODEL,
            body_preview,
        )
        raise RuntimeError(f"OpenAI embeddings HTTP {resp.status_code}: {body_preview}")
    data = resp.json()
    emb = (((data.get("data") or [{}])[0]) or {}).get("embedding")
    if not isinstance(emb, list):
        raise RuntimeError("OpenAI embeddings 返回格式异常")
    logger.info("OpenAI embeddings 成功 elapsed_ms=%s model=%s dim=%s", elapsed_ms, EMBEDDING_MODEL, len(emb))
    return [float(x) for x in emb]


def embed_text(text: str) -> list[float]:
    """
    生成 embedding 向量。
    优先 Cloudflare Workers AI（中文优先推荐：@cf/baai/bge-m3），其次可回退 OpenAI。
    无 key 直接抛错让上层降级。
    """
    t = normalize_text(text)
    if not t:
        return []

    ck = content_hash(t)
    cached = _cache_get(ck)
    if cached:
        return cached

    backend_desc = _backend_model_desc()
    last_err = None
    max_retries = max(1, int(EMBED_MAX_RETRIES or 3))
    logger.info(
        "embed_text 开始 backend=%s text_len=%s timeout_s=%s max_retries=%s",
        backend_desc,
        len(t),
        _timeout_seconds(),
        max_retries,
    )
    for attempt in range(max_retries):
        started = time.time()
        try:
            if CF_ACCOUNT_ID and CF_API_TOKEN:
                emb = _embed_via_cloudflare(t)
            else:
                emb = _embed_via_openai(t)
            _cache_set(ck, emb)
            return emb
        except Exception as e:
            last_err = e
            elapsed_ms = int((time.time() - started) * 1000)
            logger.warning(
                "embed_text 失败 backend=%s attempt=%s/%s elapsed_ms=%s error=%s",
                backend_desc,
                attempt + 1,
                max_retries,
                elapsed_ms,
                e,
            )
            if attempt != max_retries - 1:
                backoff_s = max(0.2, float(EMBED_RETRY_BACKOFF_SECONDS or 1.0) * (attempt + 1))
                time.sleep(backoff_s)
    logger.error("embed_text 最终失败 backend=%s error=%s", backend_desc, last_err)
    raise last_err

