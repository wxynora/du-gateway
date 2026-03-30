import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

_BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(_BASE_DIR / ".env", override=False)


def _env_float(name: str, default: float) -> float:
    try:
        v = os.getenv(name)
        return float(v) if v is not None and str(v).strip() else float(default)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    try:
        v = os.getenv(name)
        return int(v) if v is not None and str(v).strip() else int(default)
    except Exception:
        return int(default)


CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "").strip()
# Cloudflare 官方示例常用名是 CLOUDFLARE_API_TOKEN / CLOUDFLARE_AUTH_TOKEN，这里两者都兼容
CF_API_TOKEN = (os.getenv("CLOUDFLARE_API_TOKEN") or os.getenv("CLOUDFLARE_AUTH_TOKEN") or os.getenv("CF_API_TOKEN") or "").strip()

# 优先中文效果 + 成本低：bge-m3（多语言 embedding，Cloudflare Workers AI）
CF_EMBEDDING_MODEL = os.getenv("CF_EMBEDDING_MODEL", "@cf/baai/bge-m3").strip()
CF_EMBEDDING_POOLING = os.getenv("CF_EMBEDDING_POOLING", "cls").strip().lower()  # cls 更准，但与 mean 不兼容

# 可选：OpenAI 兼容（未配置 CF 时可回退）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "").strip()
EMBEDDING_MAX_CHARS = _env_int("EMBEDDING_MAX_CHARS", 8000)
EMBED_REQUEST_TIMEOUT_SECONDS = _env_int("EMBED_REQUEST_TIMEOUT_SECONDS", 45)
EMBED_MAX_RETRIES = _env_int("EMBED_MAX_RETRIES", 3)
EMBED_RETRY_BACKOFF_SECONDS = _env_float("EMBED_RETRY_BACKOFF_SECONDS", 1.0)


def current_embedding_model() -> str:
    """返回当前实际使用的 embedding 模型名。"""
    if CF_ACCOUNT_ID and CF_API_TOKEN:
        return CF_EMBEDDING_MODEL
    return EMBEDDING_MODEL


def current_embedding_backend() -> str:
    """返回当前 embedding 后端：cloudflare_bge / openai_compatible / disabled。"""
    if CF_ACCOUNT_ID and CF_API_TOKEN:
        return "cloudflare_bge"
    if OPENAI_API_KEY and EMBEDDING_MODEL:
        return "openai_compatible"
    return "disabled"

# 向量召回阈值（默认适中）：过高会导致“几乎不触发”，过低会导致噪声注入
# 可通过环境变量 VECTOR_MIN_SIM 覆盖。
VECTOR_MIN_SIM = _env_float("VECTOR_MIN_SIM", 0.38)
VECTOR_TOPK = _env_int("VECTOR_TOPK", 30)
VECTOR_TOPN = _env_int("VECTOR_TOPN", 3)
# 重排后综合分最低门槛：低于此分的记忆不注入，宁可空也不塞噪声
# score = sem_user*0.50 + sem_ctx*0.20 + weight*0.22 + src*0.08
RERANK_MIN_SCORE = _env_float("RERANK_MIN_SCORE", 0.35)

# 是否把额外来源也并入向量召回（默认关闭，避免误注入）
INCLUDE_DU_MEMORY_DOC_IN_VECTOR = os.getenv("INCLUDE_DU_MEMORY_DOC_IN_VECTOR", "0").strip().lower() in ("1", "true", "yes")
# 核心缓存 pending 默认参与：你后续拆分后的“核心缓存层”会在这里发挥作用
INCLUDE_CORE_PENDING_IN_VECTOR = os.getenv("INCLUDE_CORE_PENDING_IN_VECTOR", "1").strip().lower() in ("1", "true", "yes")

# 是否按 tag 分片存储 embeddings/{tag}.embeddings.json
SHARD_BY_TAG = os.getenv("SHARD_BY_TAG", "true").strip().lower() in ("1", "true", "yes")

# embedding 结果缓存（内存，单进程）
EMBED_CACHE_TTL_SECONDS = _env_int("EMBED_CACHE_TTL_SECONDS", 3600)
EMBED_CACHE_MAX_ITEMS = _env_int("EMBED_CACHE_MAX_ITEMS", 1024)

