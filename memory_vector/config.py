import os


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
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002").strip()
EMBEDDING_MAX_CHARS = _env_int("EMBEDDING_MAX_CHARS", 8000)

# 向量召回阈值（默认适中）：过高会导致“几乎不触发”，过低会导致噪声注入
# 可通过环境变量 VECTOR_MIN_SIM 覆盖。
VECTOR_MIN_SIM = _env_float("VECTOR_MIN_SIM", 0.38)
VECTOR_TOPK = _env_int("VECTOR_TOPK", 30)
VECTOR_TOPN = _env_int("VECTOR_TOPN", 3)

# 是否把额外来源也并入向量召回（默认关闭，避免误注入）
INCLUDE_DU_MEMORY_DOC_IN_VECTOR = os.getenv("INCLUDE_DU_MEMORY_DOC_IN_VECTOR", "0").strip().lower() in ("1", "true", "yes")
# 核心缓存 pending 默认参与：你后续拆分后的“核心缓存层”会在这里发挥作用
INCLUDE_CORE_PENDING_IN_VECTOR = os.getenv("INCLUDE_CORE_PENDING_IN_VECTOR", "1").strip().lower() in ("1", "true", "yes")

# 是否按 tag 分片存储 embeddings/{tag}.embeddings.json
SHARD_BY_TAG = os.getenv("SHARD_BY_TAG", "true").strip().lower() in ("1", "true", "yes")

# embedding 结果缓存（内存，单进程）
EMBED_CACHE_TTL_SECONDS = _env_int("EMBED_CACHE_TTL_SECONDS", 3600)
EMBED_CACHE_MAX_ITEMS = _env_int("EMBED_CACHE_MAX_ITEMS", 1024)

