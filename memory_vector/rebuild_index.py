"""
离线/后台：从动态层 current.json 全量或分批重建向量索引（写回 R2）。

用法：
python -m memory_vector.rebuild_index
python -m memory_vector.rebuild_index --batch-size 100 --start 0 --max-items 500
"""

import argparse
import json
import time
from pathlib import Path

from memory_vector.embedding_client import embed_text, content_hash, normalize_text
from memory_vector.vector_index_store import upsert_records
from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)
_FAILED_IDS_PATH = Path(__file__).resolve().parent.parent / "data" / "rebuild_index_failed_ids.json"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="分批重建动态层向量索引")
    p.add_argument("--start", type=int, default=0, help="从第几条动态记忆开始")
    p.add_argument("--max-items", type=int, default=0, help="最多处理多少条，0 表示全部")
    p.add_argument("--batch-size", type=int, default=100, help="每批最多处理多少条")
    p.add_argument("--sleep-seconds", type=float, default=0.2, help="每批之间休眠秒数")
    p.add_argument("--failed-only", action="store_true", help="只重试上次失败的 memory_id")
    p.add_argument("--core-pending", action="store_true", help="只重建核心缓存 pending 向量索引")
    return p.parse_args()


def _flush_records(batch_by_tag: dict[str, list[dict]]) -> int:
    written = 0
    for tag, records in batch_by_tag.items():
        if not records:
            continue
        ok = upsert_records(tag, records)
        logger.info("rebuild_index: tag=%s records=%s ok=%s", tag, len(records), ok)
        if ok:
            written += len(records)
    return written


def _load_failed_ids() -> set[str]:
    try:
        if not _FAILED_IDS_PATH.exists():
            return set()
        data = json.loads(_FAILED_IDS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("failed_ids"), list):
            return set()
        return {str(x).strip() for x in data.get("failed_ids") if str(x).strip()}
    except Exception:
        return set()


def _save_failed_ids(ids: set[str]) -> None:
    try:
        payload = {"failed_ids": sorted(ids)}
        _FAILED_IDS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("rebuild_index: 保存失败列表失败 error=%s", e)


def rebuild(
    start: int = 0,
    max_items: int = 0,
    batch_size: int = 100,
    sleep_seconds: float = 0.2,
    failed_only: bool = False,
) -> None:
    memories = r2_store.get_dynamic_memory_list() or []
    if not memories:
        logger.info("rebuild_index: 无动态记忆，跳过")
        return

    failed_filter = _load_failed_ids() if failed_only else set()
    if failed_only:
        memories = [m for m in memories if str((m or {}).get("id") or "").strip() in failed_filter]

    start = max(0, int(start or 0))
    batch_size = max(1, int(batch_size or 100))
    if max_items and max_items > 0:
        memories = memories[start : start + int(max_items)]
    else:
        memories = memories[start:]
    total = len(memories)
    if not total:
        logger.info("rebuild_index: start=%s 后无可处理动态记忆，跳过", start)
        return

    batch_by_tag: dict[str, list[dict]] = {}
    batch_count = 0
    written_total = 0
    failed_ids: set[str] = set()
    for i, m in enumerate(memories, start=1):
        mid = (m or {}).get("id")
        retrieval_text = str((m or {}).get("retrieval_text") or "").strip()
        content_text = str((m or {}).get("content") or "").strip()
        text = retrieval_text if retrieval_text else content_text
        if retrieval_text and content_text and retrieval_text not in content_text:
            text = f"{retrieval_text}\n{content_text}"
        tag = ((m or {}).get("tag") or "").strip() or "ALL"
        if not mid or not str(text).strip():
            continue
        t = normalize_text(str(text))
        try:
            emb = embed_text(t)
        except Exception as e:
            logger.error("rebuild_index: embed 失败 memory_id=%s error=%s", mid, e)
            failed_ids.add(str(mid))
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
                "emotion_label": str((m or {}).get("emotion_label") or "").strip(),
                "scene_type": str((m or {}).get("scene_type") or "").strip(),
                "target_type": str((m or {}).get("target_type") or "").strip(),
                "created_at": (m or {}).get("created_at") or "",
                "last_mentioned": (m or {}).get("last_mentioned") or "",
            },
        }
        batch_by_tag.setdefault(tag, []).append(rec)
        batch_count += 1

        if batch_count >= batch_size:
            written_total += _flush_records(batch_by_tag)
            logger.info("rebuild_index: progress=%s/%s written=%s", i, total, written_total)
            batch_by_tag = {}
            batch_count = 0
            if sleep_seconds > 0:
                time.sleep(float(sleep_seconds))

    if batch_by_tag:
        written_total += _flush_records(batch_by_tag)
    _save_failed_ids(failed_ids)
    logger.info("rebuild_index: done total=%s written=%s start=%s batch_size=%s", total, written_total, start, batch_size)


if __name__ == "__main__":
    args = _parse_args()
    if args.core_pending:
        from memory_vector.core_pending_index import sync_core_pending_index

        pending = r2_store.get_core_cache_pending() or []
        ok = sync_core_pending_index(pending)
        logger.info("rebuild_index: core_pending done total=%s ok=%s", len(pending), ok)
        raise SystemExit(0 if ok else 1)
    rebuild(
        start=args.start,
        max_items=args.max_items,
        batch_size=args.batch_size,
        sleep_seconds=args.sleep_seconds,
        failed_only=args.failed_only,
    )
