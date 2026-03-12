"""
离线/后台：从动态层 current.json 全量重建向量索引（写回 R2）。

用法（PowerShell）：
python -m memory_vector.rebuild_index
"""

from memory_vector.embedding_client import embed_text, content_hash, normalize_text
from memory_vector.vector_index_store import upsert_records
from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)


def rebuild() -> None:
    memories = r2_store.get_dynamic_memory_list() or []
    if not memories:
        logger.info("rebuild_index: 无动态记忆，跳过")
        return

    by_tag: dict[str, list[dict]] = {}
    for m in memories:
        mid = (m or {}).get("id")
        text = (m or {}).get("content") or ""
        tag = ((m or {}).get("tag") or "").strip() or "ALL"
        if not mid or not str(text).strip():
            continue
        t = normalize_text(str(text))
        try:
            emb = embed_text(t)
        except Exception as e:
            logger.error("rebuild_index: embed 失败 memory_id=%s error=%s", mid, e)
            continue
        rec = {
            "memory_id": str(mid),
            "text": t,
            "embedding": emb,
            "content_hash": content_hash(t),
            "metadata": {
                "importance": int((m or {}).get("importance") or 0),
                "mention_count": int((m or {}).get("mention_count") or 0),
                "tag": tag,
                "created_at": (m or {}).get("created_at") or "",
                "last_mentioned": (m or {}).get("last_mentioned") or "",
            },
        }
        by_tag.setdefault(tag, []).append(rec)

    for tag, records in by_tag.items():
        ok = upsert_records(tag, records)
        logger.info("rebuild_index: tag=%s records=%s ok=%s", tag, len(records), ok)


if __name__ == "__main__":
    rebuild()

