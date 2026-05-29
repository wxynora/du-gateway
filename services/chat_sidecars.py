from typing import Optional

from pipeline.failed_response import get_assistant_content_text
from services.du_daily import (
    looks_like_plain_maintenance_daily,
    save_hidden_block as save_du_daily_hidden_block,
    split_assistant_for_daily,
)
from services.du_thought import split_assistant_for_thought
from services.du_vitals import normalize_vitals_payload, split_assistant_for_vitals
from services.dynamic_memory_citation import strip_assistant_memory_citations
from services.interaction_memory import split_assistant_for_interaction
from services.pc_command_handler import process_pcmd_in_assistant_text
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)


def _memory_source_label(memory_id: str) -> str:
    mid = str(memory_id or "").strip()
    return "core_cache" if mid.startswith("core::") else "dynamic_memory"


def lookup_referenced_memory_details(memory_ids: list[str]) -> list[dict]:
    ids: list[str] = []
    seen: set[str] = set()
    for raw in memory_ids or []:
        mid = str(raw or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        ids.append(mid)
    if not ids:
        return []

    details_by_id: dict[str, dict] = {}
    try:
        for mem in r2_store.get_dynamic_memory_list() or []:
            if not isinstance(mem, dict):
                continue
            mid = str(mem.get("id") or "").strip()
            if not mid or mid not in seen:
                continue
            details_by_id[mid] = {
                "id": mid,
                "source": "dynamic_memory",
                "content": str(mem.get("content") or "").strip(),
                "tag": str(mem.get("tag") or "").strip(),
                "importance": int(mem.get("importance") or 0),
                "mention_count": int(mem.get("mention_count") or 0),
                "last_mentioned": str(mem.get("last_mentioned") or mem.get("created_at") or "").strip(),
                "emotion_label": str(mem.get("emotion_label") or "").strip(),
                "scene_type": str(mem.get("scene_type") or "").strip(),
                "target_type": str(mem.get("target_type") or "").strip(),
            }
    except Exception as e:
        logger.debug("lookup dynamic referenced memories failed: %s", e)
    try:
        for item in r2_store.get_core_cache_pending() or []:
            if not isinstance(item, dict):
                continue
            entry_id = str(item.get("id") or "").strip()
            mid = f"core::{entry_id}" if entry_id else ""
            if not mid or mid not in seen:
                continue
            details_by_id[mid] = {
                "id": mid,
                "entry_id": entry_id,
                "source": "core_cache",
                "content": str(item.get("content") or "").strip(),
                "tag": str(item.get("tag") or "").strip(),
                "importance": int(item.get("importance") or 0),
                "mention_count": int(item.get("mention_count") or 0),
                "promoted_by": str(item.get("promoted_by") or "").strip(),
                "promoted_at": str(item.get("promoted_at") or "").strip(),
                "emotion_label": str(item.get("emotion_label") or "").strip(),
                "scene_type": str(item.get("scene_type") or "").strip(),
                "target_type": str(item.get("target_type") or "").strip(),
            }
    except Exception as e:
        logger.debug("lookup core referenced memories failed: %s", e)

    out: list[dict] = []
    for mid in ids:
        out.append(details_by_id.get(mid) or {"id": mid, "source": _memory_source_label(mid)})
    return out


def append_memory_citation_debug_event(window_id: str, memory_ids: list[str], full_text: str) -> None:
    if not memory_ids:
        return
    try:
        details = lookup_referenced_memory_details(memory_ids)
        r2_store.append_dynamic_recall_debug_event(
            {
                "timestamp": now_beijing_iso(),
                "window_id": (window_id or "").strip() or "__default__",
                "source": "memory_citation",
                "query": "",
                "recalled_count": len(details),
                "referenced_memory_ids": memory_ids,
                "referenced_memories": details,
                "assistant_preview": str(full_text or "").strip()[:240],
            }
        )
    except Exception as e:
        logger.warning("记忆引用调试事件写入失败 ids=%s error=%s", memory_ids[:10], e)


def extract_and_store_hidden_sidecars(
    full_text: str,
    window_id: str = "",
    du_daily_trigger: Optional[dict] = None,
    dynamic_memory_citation_map: Optional[dict] = None,
) -> str:
    visible_after_pcmd, _ = process_pcmd_in_assistant_text(full_text or "")
    visible, thought = split_assistant_for_thought(visible_after_pcmd)
    visible, vitals = split_assistant_for_vitals(visible)
    visible, interaction = split_assistant_for_interaction(visible)
    visible, du_daily = split_assistant_for_daily(visible)
    visible, referenced_memory_ids = strip_assistant_memory_citations(visible, dynamic_memory_citation_map)
    if thought:
        try:
            r2_store.save_du_thought_latest(now_beijing_iso(), thought)
        except Exception as e:
            logger.warning("save_du_thought_latest 失败 error=%s", e)
    if vitals:
        try:
            payload = normalize_vitals_payload(vitals, previous=r2_store.get_du_vitals_latest())
            if payload:
                r2_store.save_du_vitals_latest(payload)
                r2_store.append_du_vitals_history(payload, limit=10)
        except Exception as e:
            logger.warning("save_du_vitals_latest 失败 error=%s", e)
    if interaction:
        try:
            r2_store.append_interaction_candidate(interaction)
        except Exception as e:
            logger.warning("append_interaction_candidate 失败 error=%s", e)
    if du_daily:
        try:
            save_du_daily_hidden_block(du_daily, trigger=du_daily_trigger)
        except Exception as e:
            logger.warning("save_du_daily_hidden_block 失败 error=%s", e)
    elif looks_like_plain_maintenance_daily(visible, du_daily_trigger):
        try:
            save_du_daily_hidden_block(visible, trigger=du_daily_trigger)
            visible = ""
        except Exception as e:
            logger.warning("save_du_daily_hidden_block plain 失败 error=%s", e)
    if referenced_memory_ids:
        append_memory_citation_debug_event(window_id, referenced_memory_ids, visible)
        try:
            touched = r2_store.touch_dynamic_memory_mentions(referenced_memory_ids)
            logger.info("动态记忆引用命中 ids=%s touched=%s", referenced_memory_ids[:10], touched)
        except Exception as e:
            logger.warning("动态记忆引用回写失败 ids=%s error=%s", referenced_memory_ids[:10], e)
    return visible


def apply_hidden_sidecars_to_assistant_response(
    resp_json: dict,
    window_id: str = "",
    du_daily_trigger: Optional[dict] = None,
    dynamic_memory_citation_map: Optional[dict] = None,
) -> dict:
    """
    剥离助手回复中的隐藏块（老婆侧不可见）；若存在闭合块则写入 R2。
    就地修改 choices[0].message.content。
    """
    if not resp_json or not isinstance(resp_json, dict):
        return resp_json
    choices = resp_json.get("choices") or []
    if not choices:
        return resp_json
    msg = choices[0].get("message")
    if not isinstance(msg, dict):
        return resp_json
    content_text = get_assistant_content_text(msg)
    if not content_text:
        return resp_json
    visible = extract_and_store_hidden_sidecars(
        content_text,
        window_id=window_id,
        du_daily_trigger=du_daily_trigger,
        dynamic_memory_citation_map=dynamic_memory_citation_map,
    )
    if visible != content_text:
        msg["content"] = visible
    return resp_json
