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


def _embed_via_cloudflare(text: str) -> list[float]:
    if not (CF_ACCOUNT_ID and CF_API_TOKEN):
        raise RuntimeError("CF_ACCOUNT_ID / CLOUDFLARE_API_TOKEN 未配置")
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_EMBEDDING_MODEL}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {"text": text, "truncate_inputs": True}
    if CF_EMBEDDING_POOLING in ("mean", "cls"):
        payload["pooling"] = CF_EMBEDDING_POOLING

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Cloudflare AI embeddings HTTP {resp.status_code}: {resp.text[:2000]}")
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
    return [float(x) for x in emb]


def _embed_via_openai(text: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 未配置")
    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": EMBEDDING_MODEL, "input": text}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI embeddings HTTP {resp.status_code}: {resp.text[:2000]}")
    data = resp.json()
    emb = (((data.get("data") or [{}])[0]) or {}).get("embedding")
    if not isinstance(emb, list):
        raise RuntimeError("OpenAI embeddings 返回格式异常")
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

    last_err = None
    for attempt in range(2):  # 重试 1 次
        try:
            if CF_ACCOUNT_ID and CF_API_TOKEN:
                emb = _embed_via_cloudflare(t)
            else:
                emb = _embed_via_openai(t)
            _cache_set(ck, emb)
            return emb
        except Exception as e:
            last_err = e
            logger.warning("embed_text 失败 attempt=%s error=%s", attempt + 1, e)
            time.sleep(0.6 * (attempt + 1))
    raise last_err

