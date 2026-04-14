from __future__ import annotations

from typing import Optional

from storage import r2_store
from utils.time_aware import now_beijing_iso

_HIGH_SIGNAL_SCENES = {
    "heart_to_heart",
    "conflict",
    "affection",
    "emotional_venting",
}


def _is_transaction_like(mem: dict) -> bool:
    scene = str((mem or {}).get("scene_type") or "").strip()
    mention_count = max(0, int((mem or {}).get("mention_count") or 0))
    emotion = str((mem or {}).get("emotion_label") or "").strip().lower()
    return scene == "casual_chat" and mention_count <= 0 and emotion in ("", "neutral")


def _bucket_for_memory(mem: dict) -> str:
    target_type = str((mem or {}).get("target_type") or "").strip()
    if target_type == "self_state":
        return "xinyue"
    if target_type == "about_me":
        return "du"
    return ""


def _candidate_from_memory(mem: dict) -> Optional[dict]:
    if not isinstance(mem, dict):
        return None
    mem_id = str(mem.get("id") or "").strip()
    content = str(mem.get("content") or "").strip()
    if not mem_id or not content:
        return None
    if str(mem.get("tag") or "").strip() == "卧室":
        return None
    if int(mem.get("importance") or 0) < 3:
        return None
    if _is_transaction_like(mem):
        return None
    bucket = _bucket_for_memory(mem)
    if not bucket:
        return None
    scene = str(mem.get("scene_type") or "").strip()
    mention_count = max(0, int(mem.get("mention_count") or 0))
    if scene and scene not in _HIGH_SIGNAL_SCENES and mention_count <= 0:
        return None
    now = now_beijing_iso()
    return {
        "id": str(mem.get("id") or "").strip(),
        "summary": content,
        "source_memory_id": mem_id,
        "created_at": str(mem.get("created_at") or now),
        "updated_at": now,
        "bucket": bucket,
    }


def _upsert_candidate(items: list[dict], candidate: dict) -> list[dict]:
    source_memory_id = str(candidate.get("source_memory_id") or "").strip()
    out: list[dict] = []
    found = False
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("source_memory_id") or "").strip() == source_memory_id:
            merged = dict(item)
            merged.update(candidate)
            merged["id"] = str(item.get("id") or candidate.get("id") or source_memory_id).strip()
            merged["created_at"] = str(item.get("created_at") or candidate.get("created_at") or now_beijing_iso())
            out.append(merged)
            found = True
        else:
            out.append(item)
    if not found:
        out.append(candidate)
    return out


def _remove_candidate_by_memory_id(items: list[dict], source_memory_id: str) -> list[dict]:
    sid = str(source_memory_id or "").strip()
    return [
        item
        for item in (items or [])
        if isinstance(item, dict) and str(item.get("source_memory_id") or "").strip() != sid
    ]


def sync_portrait_candidate_from_memory(mem: dict) -> None:
    """
    按现有动态记忆同步画像候选：
    - 命中规则时，写入对应候选池
    - 不命中时，从两个候选池里都清掉同 source_memory_id 的旧候选
    """
    if not isinstance(mem, dict):
        return
    source_memory_id = str(mem.get("id") or "").strip()
    if not source_memory_id:
        return
    candidate = _candidate_from_memory(mem)

    xinyue_items = _remove_candidate_by_memory_id(r2_store.get_xinyue_portrait_candidates(), source_memory_id)
    du_items = _remove_candidate_by_memory_id(r2_store.get_du_portrait_candidates(), source_memory_id)

    if candidate:
        bucket = str(candidate.pop("bucket") or "").strip()
        if bucket == "xinyue":
            xinyue_items = _upsert_candidate(xinyue_items, candidate)
        elif bucket == "du":
            du_items = _upsert_candidate(du_items, candidate)

    r2_store.save_xinyue_portrait_candidates(xinyue_items)
    r2_store.save_du_portrait_candidates(du_items)
