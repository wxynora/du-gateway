from __future__ import annotations

from typing import Any

from memory_vector.embedding_client import content_hash, embed_text, normalize_text
from memory_vector.vector_index_store import load_index, save_index
from utils.log import get_logger

logger = get_logger(__name__)

CORE_PENDING_INDEX_TAG = "__core_pending__"
CORE_PENDING_MEMORY_ID_PREFIX = "core::"


def core_pending_memory_id(entry_id: str) -> str:
    entry_id = str(entry_id or "").strip()
    return f"{CORE_PENDING_MEMORY_ID_PREFIX}{entry_id}" if entry_id else ""


def _core_pending_text(item: dict[str, Any]) -> str:
    retrieval_text = str((item or {}).get("retrieval_text") or "").strip()
    content = str((item or {}).get("content") or "").strip()
    if retrieval_text and content and retrieval_text not in content:
        return f"{retrieval_text}\n{content}"
    return retrieval_text or content


def _metadata_for_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "core_pending",
        "entry_id": str((item or {}).get("id") or "").strip(),
        "source_memory_id": str((item or {}).get("source_memory_id") or "").strip(),
        "promoted_by": str((item or {}).get("promoted_by") or "").strip(),
        "importance": int((item or {}).get("importance") or 0),
        "mention_count": int((item or {}).get("mention_count") or 0),
        "tag": str((item or {}).get("tag") or "").strip(),
        "emotion_label": str((item or {}).get("emotion_label") or "").strip(),
        "scene_type": str((item or {}).get("scene_type") or "").strip(),
        "target_type": str((item or {}).get("target_type") or "").strip(),
        "promoted_at": (item or {}).get("promoted_at") or "",
        "created_at": (item or {}).get("created_at") or "",
        "updated_at": (item or {}).get("updated_at") or "",
        "last_mentioned": (item or {}).get("last_mentioned") or "",
    }


def _old_records_by_id() -> dict[str, dict[str, Any]]:
    idx = load_index(CORE_PENDING_INDEX_TAG)
    old_by_id: dict[str, dict[str, Any]] = {}
    for record in idx.get("records") or []:
        mid = str((record or {}).get("memory_id") or "").strip()
        if mid:
            old_by_id[mid] = record
    return old_by_id


def _records_for_items(
    pending: list[dict[str, Any]] | list[Any],
    old_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, int, int]:
    records: list[dict[str, Any]] = []
    embedded = 0
    reused = 0
    skipped = 0
    failed = 0

    for item in pending or []:
        if not isinstance(item, dict):
            skipped += 1
            continue
        entry_id = str(item.get("id") or "").strip()
        mid = core_pending_memory_id(entry_id)
        text = normalize_text(_core_pending_text(item))
        if not mid or not text:
            skipped += 1
            continue

        h = content_hash(text)
        old = old_by_id.get(mid) or {}
        old_embedding = old.get("embedding")
        if old.get("content_hash") == h and isinstance(old_embedding, list) and old_embedding:
            embedding = old_embedding
            reused += 1
        else:
            try:
                embedding = embed_text(text)
            except Exception as e:
                failed += 1
                logger.warning("core_pending_index embed failed memory_id=%s error=%s", mid, e)
                continue
            embedded += 1

        records.append(
            {
                "memory_id": mid,
                "text": text,
                "embedding": embedding,
                "content_hash": h,
                "metadata": _metadata_for_item(item),
            }
        )

    return records, reused, embedded, skipped, failed


def sync_core_pending_index(pending: list[dict[str, Any]] | list[Any]) -> bool:
    """
    Make the core pending vector index exactly match core_cache/pending.json.

    Existing records with the same content_hash reuse their embedding, so routine
    saves/deletes do not re-embed unchanged entries.
    """
    records, reused, embedded, skipped, failed = _records_for_items(pending, _old_records_by_id())
    ok = save_index(CORE_PENDING_INDEX_TAG, {"schema_version": 1, "records": records})
    logger.info(
        "core_pending_index sync ok=%s records=%s reused=%s embedded=%s skipped=%s failed=%s",
        ok,
        len(records),
        reused,
        embedded,
        skipped,
        failed,
    )
    return bool(ok and failed == 0)


def upsert_core_pending_items(items: list[dict[str, Any]] | list[Any]) -> bool:
    """Upsert only changed/new core pending entries into the shared pending index."""
    if not items:
        return True
    old_by_id = _old_records_by_id()
    records, reused, embedded, skipped, failed = _records_for_items(items, old_by_id)
    for record in records:
        mid = str((record or {}).get("memory_id") or "").strip()
        if mid:
            old_by_id[mid] = record
    ok = save_index(CORE_PENDING_INDEX_TAG, {"schema_version": 1, "records": list(old_by_id.values())})
    logger.info(
        "core_pending_index upsert ok=%s upserted=%s total=%s reused=%s embedded=%s skipped=%s failed=%s",
        ok,
        len(records),
        len(old_by_id),
        reused,
        embedded,
        skipped,
        failed,
    )
    return bool(ok and failed == 0)


def remove_core_pending_ids(entry_ids: set[str] | list[str] | tuple[str, ...]) -> bool:
    ids = {core_pending_memory_id(x) for x in (entry_ids or [])}
    ids = {x for x in ids if x}
    if not ids:
        return True
    old_by_id = _old_records_by_id()
    for mid in ids:
        old_by_id.pop(mid, None)
    ok = save_index(CORE_PENDING_INDEX_TAG, {"schema_version": 1, "records": list(old_by_id.values())})
    logger.info("core_pending_index remove ok=%s ids=%s total=%s", ok, len(ids), len(old_by_id))
    return bool(ok)


def clear_core_pending_index() -> bool:
    ok = save_index(CORE_PENDING_INDEX_TAG, {"schema_version": 1, "records": []})
    logger.info("core_pending_index clear ok=%s", ok)
    return bool(ok)
