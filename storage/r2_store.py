# R2 存储（S3 兼容 API）
# 与需求文档十一「R2 存储结构」对齐：global/、conversations/、dynamic_memory/、core_cache/
import hashlib
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from utils.time_aware import now_beijing_iso, BEIJING_TZ

from botocore.exceptions import ClientError

from config import R2_BUCKET_NAME
from storage.co_read_store import (
    assemble_co_read_upload,
    create_co_read_upload,
    delete_co_read_book,
    delete_co_read_upload,
    get_co_read_book,
    get_co_read_book_card,
    get_co_read_book_index_payload,
    get_co_read_cards_payload,
    get_co_read_upload,
    list_co_read_book_cards,
    list_co_read_books,
    normalize_co_read_book_card,
    normalize_co_read_book_mark,
    normalize_co_read_book_payload,
    normalize_co_read_section,
    save_co_read_book,
    save_co_read_book_card,
    save_co_read_upload_chunk,
    update_co_read_book_card,
)
from storage.pc_command_store import (
    append_pc_command,
    get_pc_command_queue,
    mark_pc_commands_done,
)
from storage.app_action_store import (
    append_app_action,
    poll_app_actions,
    report_app_actions,
)
from storage import conversation_followup_store
from storage.r2_client import _read_json, _s3_client, _write_json
from storage.r2_conversation_store import (
    CONVERSATION_COMPACT_SCHEMA_VERSION,
    CONVERSATION_GUARD_BACKUP_DAYS,
    CONVERSATION_RECENT_MAX_ROUNDS,
    LEGACY_EMPTY_CONVERSATION_KEY,
    WINDOW_ID_DEFAULT,
    _content_to_text_for_preview,
    _conversation_guard_dates,
    _conversation_meta_key,
    _conversation_recent_key,
    _conversation_round_key,
    _conversations_key_for_date,
    _empty_conversation_meta,
    _ensure_compact_conversation_state,
    _image_desc_recent_key,
    _latest_rounds,
    _merge_rounds_by_index,
    _prefix,
    _read_conversation_backup_rounds_for_dates,
    _read_conversation_data_with_legacy_migrate,
    _read_conversation_meta,
    _read_conversation_meta_status,
    _read_recent_rounds,
    _repair_compact_conversation_state_from_recent_sources,
    _round_index_value,
    _sort_rounds,
    _write_compact_conversation_state_from_rounds,
    append_conversation_round,
    delete_conversation_round,
    get_conversation_round_by_index,
    get_conversation_rounds,
    get_next_round_index,
    list_conversation_rounds_preview,
    normalize_window_id,
    overwrite_conversation_rounds,
)
from storage.r2_context_store import (
    IMAGE_DESC_RECENT_LIMIT,
    R2_KEY_GLOBAL_SUMMARY,
    R2_KEY_GLOBAL_SUMMARY_CHUNKS,
    R2_KEY_IMAGE_DESC_RECENT,
    R2_KEY_LATEST_4_ROUNDS,
    _image_desc_items,
    _upsert_recent_image_description_locked,
    get_latest_4_rounds_global,
    get_recent_image_description_map,
    get_summary,
    get_summary_chunks,
    has_window_history,
    save_recent_image_description,
    save_summary,
    save_summary_chunks,
    update_latest_4_rounds_global,
)
from storage.r2_device_reporting_store import (
    DEFAULT_DEVICE_REPORTING_CONFIG,
    DEVICE_REPORTING_BUCKETS,
    R2_KEY_DEVICE_REPORTING_CONFIG,
    _device_reporting_config_doc,
    _ensure_device_reporting_config_bootstrapped,
    _normalize_device_reporting_config,
    get_device_reporting_config,
    is_device_reporting_bucket_enabled,
    save_device_reporting_config,
    update_device_reporting_bucket_config,
)
from storage.r2_media_store import (
    R2_KEY_SUMITALK_CHAT_MEDIA_PREFIX,
    _sumitalk_chat_media_ext,
    get_device_screenshot,
    get_object_bytes,
    get_sumitalk_chat_media_file,
    save_device_screenshot,
    upload_sumitalk_chat_media_file,
    upload_sumitalk_chat_media_thumbnail_file,
)
from storage.r2_miniapp_store import (
    R2_KEY_DU_NOTEBOOK,
    R2_KEY_MINIAPP_BG_CONFIG,
    R2_KEY_MINIAPP_BG_IMAGE,
    R2_KEY_MINIAPP_BG_IMAGE_PREFIX,
    R2_KEY_MINIAPP_CALL_RECORDS,
    R2_KEY_MINIAPP_DAILY_REPORT,
    R2_KEY_MINIAPP_DAILY_WHISPER,
    R2_KEY_MINIAPP_MOOD_METER,
    R2_KEY_MINIAPP_VOICE_AVATAR,
    R2_KEY_MINIAPP_VOICE_AVATAR_PREFIX,
    R2_KEY_MINIAPP_VOICE_CONFIG,
    _miniapp_bg_image_versioned_key,
    _miniapp_voice_avatar_versioned_key,
    add_du_notebook_entry,
    delete_du_notebook_entry,
    delete_miniapp_call_record,
    get_du_notebook_entries,
    get_miniapp_bg_config,
    get_miniapp_bg_image,
    get_miniapp_call_records,
    get_miniapp_daily_report,
    get_miniapp_daily_whisper,
    get_miniapp_mood_meter,
    get_miniapp_voice_avatar,
    get_miniapp_voice_config,
    save_du_notebook_entries,
    save_miniapp_bg_config,
    save_miniapp_bg_image,
    save_miniapp_call_records,
    save_miniapp_daily_report,
    save_miniapp_daily_whisper,
    save_miniapp_mood_meter,
    save_miniapp_voice_avatar,
    save_miniapp_voice_config,
    update_du_notebook_entry,
)
from storage.r2_sticker_store import (
    R2_KEY_STICKERS_MAPPING,
    R2_KEY_STICKERS_META,
    _merge_default_sticker_meta,
    _sticker_reserved_keys,
    add_sticker_category,
    delete_sticker_object,
    get_sticker_tag_keys,
    get_stickers_mapping,
    get_stickers_meta,
    rebuild_stickers_mapping_from_r2,
    save_stickers_mapping,
    save_stickers_meta,
    upload_sticker_file,
)
from storage.r2_studyroom_store import (
    R2_KEY_STUDYROOM,
    _STUDYROOM_MODULE_IDS,
    _STUDYROOM_MODULE_KEYWORDS,
    _STUDYROOM_MODULES,
    _STUDYROOM_SOURCE_TYPES,
    _STUDYROOM_STATUSES,
    _normalize_studyroom_item,
    _normalize_studyroom_log,
    _trim_study_text,
    add_studyroom_item,
    add_studyroom_log,
    delete_studyroom_item,
    get_studyroom_data,
    guess_studyroom_module_id,
    normalize_studyroom_data,
    save_studyroom_data,
    update_studyroom_item,
)
from storage.r2_wenyou_store import (
    delete_wenyou_active_session,
    get_wenyou_archive_by_game_id,
    get_wenyou_candidates,
    get_wenyou_card,
    get_wenyou_last_archive,
    get_wenyou_session,
    get_wenyou_wallet,
    list_wenyou_archives,
    save_wenyou_archive_copy,
    save_wenyou_candidates,
    save_wenyou_card,
    save_wenyou_last_archive,
    save_wenyou_session,
    save_wenyou_wallet,
    wenyou_active_session_key,
    wenyou_candidates_key,
    wenyou_card_key,
    wenyou_last_archive_key,
    wenyou_wallet_key,
)
from storage.du_state_store import (
    append_du_vitals_history,
    append_interaction_candidate,
    delete_du_portrait_candidate,
    delete_interaction_candidate,
    delete_xinyue_portrait_candidate,
    get_du_daily_state,
    get_du_portrait_candidates,
    get_du_thought_latest,
    get_du_vitals_history,
    get_du_vitals_latest,
    get_interaction_candidates,
    get_xinyue_portrait_candidates,
    save_du_daily_state,
    save_du_portrait_candidates,
    save_du_thought_latest,
    save_du_vitals_latest,
    save_interaction_candidates,
    save_xinyue_portrait_candidates,
)
from storage.sense_store import (
    close_app_session_for_device,
    get_sense_history_for_date,
    get_sense_latest,
    merge_and_save_sense_bucket,
    update_app_sessions_from_foreground,
)
from storage.schedule_store import (
    add_schedule_fired_key,
    create_schedule_item,
    delete_schedule_item,
    disable_schedule_item,
    enable_schedule_item,
    get_schedule_fired_keys,
    get_schedule_items,
    patch_schedule_items,
    save_schedule_items,
)
from storage.stay_with_du_store import (
    add_stay_with_du_entry,
    delete_stay_with_du_entry,
    get_stay_with_du_data,
    normalize_stay_with_du_data,
    save_stay_with_du_data,
)

# 动态层：重要记忆，7 天有效，权重机制，融合/褪色/保鲜
R2_KEY_DYNAMIC_MEMORY = "dynamic_memory/current.json"
# 核心记忆层：动态层里「更重要」的长期记忆卡片
R2_KEY_CORE_CACHE = "core_cache/pending.json"
# 动态层与核心层共用的记忆回收站；回收站内容不参与任何召回。
R2_KEY_MEMORY_TRASH = "memory/trash.json"
# 小本本：网关拎出后按时间先后排序存储
R2_KEY_NOTEBOOK = "notebook/entries.json"
# MiniApp 可编辑核心 Prompt（全局注入）
R2_KEY_CORE_PROMPT = "global/core_prompt_316.txt"
R2_KEY_CORE_PROMPT_CONFIG = "global/core_prompt_config.json"
# MiniApp Prompt 管理（多提示词 + 自动备份）
R2_KEY_PROMPT_MANAGER_CONFIG = "global/prompt_manager_config.json"
R2_KEY_PROMPT_MANAGER_BACKUP_PREFIX = "global/prompt_manager_backups/"
PROMPT_MANAGER_BACKUP_KEEP = 3
# 小渡的记忆文档：固定文本，供以后版本读取（不参与检索/注入逻辑）
R2_KEY_DU_MEMORY_DOC = "docs/du_memory_doc_v1.txt"
# 主动发消息：上一次成功主动联系的时间（北京时间 ISO）
R2_KEY_LAST_PROACTIVE_CONTACT_AT = "global/last_proactive_contact_at.txt"
# 主动发消息：目标用户最近一次真实活动时间（北京时间 ISO），用于「正在聊天时不主动发」
R2_KEY_LAST_USER_ACTIVITY_AT = "global/last_user_activity_at.txt"
R2_KEY_LAST_USER_ACTIVITY_AUDIT = "global/last_user_activity_audit.json"
R2_KEY_LAST_USER_ACTIVITY_AT_LEGACY = "global/last_telegram_user_activity_at.txt"
R2_KEY_LAST_USER_ACTIVITY_AUDIT_LEGACY = "global/last_telegram_user_activity_audit.json"
# 最近一次真实对话入口：给手机弹窗回执这类后端事件决定回发通道
R2_KEY_LAST_REPLY_CHANNEL = "global/last_reply_channel.json"
# 主动联络「抽中后问渡」的决策记忆，新在前，最多 5 条（闹钟不参与）
R2_KEY_PROACTIVE_DECISION_MEMORY = "global/proactive_decision_memory.json"
R2_KEY_DU_PENDING_THOUGHTS = "global/du_pending_thoughts.json"
R2_KEY_CONVERSATION_FOLLOWUPS = "global/conversation_followups.json"
# Telegram：TodoList（每个 tg 窗口一份 JSON）
R2_KEY_TG_TODOS = "tg/todos.json"
# 动态记忆召回调试记录（用于 MiniApp 可视化排查）
R2_KEY_DYNAMIC_RECALL_DEBUG = "dynamic_memory/recall_debug.json"
# 动态记忆 DS 写入决策审计（用于确认 new/merge/skip 与重试）
R2_KEY_DYNAMIC_DS_AUDIT = "dynamic_memory/ds_audit.json"
# 动态记忆离线慢整理最近一次结果
R2_KEY_DYNAMIC_MAINTENANCE_REPORT = "dynamic_memory/maintenance_report.json"
R2_KEY_TRIP_PLANS_PREFIX = "travel_plans"

# 多窗口同时写全局 key 时用进程内锁，避免 last-write-wins 覆盖（多进程部署需外部锁）
_global_write_lock = threading.Lock()
_notebook_write_lock = threading.Lock()
_trip_plan_write_lock = threading.Lock()
_conversation_followups_bootstrap_lock = threading.Lock()
_CONVERSATION_FOLLOWUPS_BOOTSTRAPPED = False

# 日志
from utils.log import get_logger
logger = get_logger(__name__)

LAST_USER_ACTIVITY_AUDIT_TTL_HOURS = 24
LAST_USER_ACTIVITY_AUDIT_MAX_ITEMS = 500
MEMORY_TRASH_TTL_DAYS = 7
LAST_USER_ACTIVITY_ALLOWED_SOURCES = frozenset(
    {
        "telegram_text",
        "telegram_image",
        "telegram_voice",
        "telegram_audio",
        "telegram_document",
        "cross_platform_tg_window_user_input",
        "private_board_sync_du",
        "captivity_simulator_user_interaction",
        "shared_game_user_interaction",
    }
)


def _get_key(prefix: str, key: str) -> str:
    return f"{prefix}/{key}" if prefix else key


# ---------- 小本本（按时间先后排序，滚动保留） ----------


def get_notebook_entries() -> list:
    """读取小本本条目列表，按 timestamp 升序。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_NOTEBOOK)
    if not data or not data.get("entries"):
        return []
    return sorted(data.get("entries", []), key=lambda e: e.get("timestamp", ""))


def notebook_append_entry(content: str) -> bool:
    """
    追加一条小本本（原文不动），打时间戳，按时间先后排序写回 R2。
    content: 原文，不删改。
    """
    if not (content or str(content).strip()):
        return False
    client = _s3_client()
    if not client:
        logger.warning("R2 client 未配置，跳过 notebook_append_entry")
        return False
    with _notebook_write_lock:
        try:
            data = _read_json(client, R2_KEY_NOTEBOOK)
            if data is None:
                data = {"entries": []}
            entries = data.get("entries") or []
            ts = now_beijing_iso()
            entries.append({"timestamp": ts, "content": str(content).strip()})
            entries.sort(key=lambda e: e.get("timestamp", ""))
            data["entries"] = entries
            _write_json(client, R2_KEY_NOTEBOOK, data)
            logger.info("notebook_append_entry 已写入 R2 条数=%s", len(entries))
            return True
        except Exception as e:
            logger.error("notebook_append_entry 失败 error=%s", e, exc_info=True)
            return False


def notebook_delete_entry_by_timestamp(timestamp: str) -> bool:
    """按 timestamp 删除一条小本本记录（用于手机端管理）。"""
    ts = (timestamp or "").strip()
    if not ts:
        return False
    client = _s3_client()
    if not client:
        return False
    with _notebook_write_lock:
        try:
            data = _read_json(client, R2_KEY_NOTEBOOK)
            if data is None:
                return False
            entries = data.get("entries") or []
            before = len(entries)
            entries = [e for e in entries if (e.get("timestamp") or "").strip() != ts]
            if len(entries) == before:
                return False
            entries.sort(key=lambda e: e.get("timestamp", ""))
            data["entries"] = entries
            _write_json(client, R2_KEY_NOTEBOOK, data)
            logger.info("notebook_delete_entry_by_timestamp 已删除 ts=%s 剩余=%s", ts, len(entries))
            return True
        except Exception as e:
            logger.error("notebook_delete_entry_by_timestamp 失败 ts=%s error=%s", ts, e, exc_info=True)
            return False


def _trip_plan_key(plan_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(plan_id or "").strip())
    return f"{R2_KEY_TRIP_PLANS_PREFIX}/{safe}.json" if safe else ""


def get_trip_plan(plan_id: str) -> dict:
    """读取一次出行计划。不存在、未配置 R2 或格式异常时返回 {}。"""
    key = _trip_plan_key(plan_id)
    if not key:
        return {}
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, key)
    return data if isinstance(data, dict) else {}


def save_trip_plan(plan: dict) -> bool:
    """保存一次出行计划，key 取 plan_meta.plan_id。"""
    if not isinstance(plan, dict):
        return False
    meta = plan.get("plan_meta") if isinstance(plan.get("plan_meta"), dict) else {}
    plan_id = str(meta.get("plan_id") or plan.get("plan_id") or "").strip()
    key = _trip_plan_key(plan_id)
    if not key:
        return False
    client = _s3_client()
    if not client:
        logger.warning("R2 client 未配置，跳过 save_trip_plan plan_id=%s", plan_id)
        return False
    with _trip_plan_write_lock:
        try:
            _write_json(client, key, plan)
            return True
        except Exception as e:
            logger.error("save_trip_plan 失败 plan_id=%s error=%s", plan_id, e, exc_info=True)
            return False


def update_trip_plan(plan_id: str, patch: dict) -> dict:
    """
    浅合并更新一次出行计划，返回更新后的计划。
    仅用于小范围状态/事实写回；复杂合并在调用方完成后用 save_trip_plan。
    """
    if not isinstance(patch, dict):
        return {}
    existing = get_trip_plan(plan_id)
    if not existing:
        existing = {}
    for key, value in patch.items():
        if isinstance(existing.get(key), dict) and isinstance(value, dict):
            merged = dict(existing.get(key) or {})
            merged.update(value)
            existing[key] = merged
        else:
            existing[key] = value
    save_trip_plan(existing)
    return existing


def get_last_proactive_contact_at() -> Optional[str]:
    """读取上次主动联系时间（北京时间 ISO）。未配置 R2 或不存在则返回 None。"""
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_LAST_PROACTIVE_CONTACT_AT)
        v = resp["Body"].read().decode("utf-8").strip()
        return v or None
    except Exception:
        return None


def save_last_proactive_contact_at(iso_str: str) -> bool:
    """保存上次主动联系时间（覆盖）。多窗口写同一 key 时加锁。"""
    client = _s3_client()
    if not client:
        return False
    s = (iso_str or "").strip()
    if not s:
        return False
    with _global_write_lock:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=R2_KEY_LAST_PROACTIVE_CONTACT_AT,
                Body=s.encode("utf-8"),
                ContentType="text/plain",
            )
            return True
        except Exception:
            return False


def get_proactive_decision_memory_items() -> list:
    """读取主动决策记忆（新在前），最多 5 条；失败返回 []。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_PROACTIVE_DECISION_MEMORY)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)][:5]


def append_proactive_decision_memory(entry: dict) -> bool:
    """在列表头部插入一条决策记录，整体最多保留 5 条。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(entry, dict):
        return False
    with _global_write_lock:
        try:
            data = _read_json(client, R2_KEY_PROACTIVE_DECISION_MEMORY)
            if not isinstance(data, dict):
                data = {}
            items = data.get("items")
            if not isinstance(items, list):
                items = []
            items.insert(0, dict(entry))
            data["items"] = items[:5]
            _write_json(client, R2_KEY_PROACTIVE_DECISION_MEMORY, data)
            return True
        except Exception as e:
            logger.error("append_proactive_decision_memory 失败 error=%s", e, exc_info=True)
            return False


def _normalize_du_pending_thought_item(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or "").strip()
    if not text:
        return None
    status = str(item.get("status") or "pending").strip().lower() or "pending"
    if status not in {"pending", "done", "dismissed"}:
        status = "pending"
    out = {
        "id": str(item.get("id") or uuid4()).strip(),
        "text": text[:160],
        "status": status,
        "created_at": str(item.get("created_at") or now_beijing_iso()).strip(),
        "updated_at": str(item.get("updated_at") or item.get("created_at") or now_beijing_iso()).strip(),
    }
    for key in ("done_at", "dismissed_at"):
        value = str(item.get(key) or "").strip()
        if value:
            out[key] = value
    return out


def get_du_pending_thoughts(include_inactive: bool = False) -> list[dict]:
    """读取渡自己的待续念头；默认只返回 pending 项。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DU_PENDING_THOUGHTS)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    out = []
    for raw in items:
        item = _normalize_du_pending_thought_item(raw)
        if not item:
            continue
        if include_inactive or item.get("status") == "pending":
            out.append(item)
    return out


def save_du_pending_thoughts(items: list[dict]) -> bool:
    """保存渡自己的待续念头小列表；活跃项在前，已处理项只保留少量审计尾巴。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(items, list):
        return False
    normalized = []
    seen: set[str] = set()
    for raw in items:
        item = _normalize_du_pending_thought_item(raw)
        if not item:
            continue
        item_id = str(item.get("id") or "").strip()
        if item_id in seen:
            continue
        seen.add(item_id)
        normalized.append(item)
    pending = [x for x in normalized if x.get("status") == "pending"][:20]
    inactive = [x for x in normalized if x.get("status") != "pending"][-30:]
    payload = {
        "updated_at": now_beijing_iso(),
        "items": pending + inactive,
    }
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_DU_PENDING_THOUGHTS, payload)
            return True
        except Exception as e:
            logger.error("save_du_pending_thoughts 失败 error=%s", e, exc_info=True)
            return False


def _read_conversation_followups_from_r2() -> list[dict]:
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_CONVERSATION_FOLLOWUPS)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [dict(x) for x in items if isinstance(x, dict)]


def _ensure_conversation_followups_bootstrapped() -> None:
    global _CONVERSATION_FOLLOWUPS_BOOTSTRAPPED
    if _CONVERSATION_FOLLOWUPS_BOOTSTRAPPED:
        return
    with _conversation_followups_bootstrap_lock:
        if _CONVERSATION_FOLLOWUPS_BOOTSTRAPPED:
            return
        try:
            if conversation_followup_store.has_items():
                _CONVERSATION_FOLLOWUPS_BOOTSTRAPPED = True
                return
            conversation_followup_store.replace_items(_read_conversation_followups_from_r2())
        except Exception as e:
            logger.warning("conversation followups sqlite bootstrap 失败 error=%s", e)
        _CONVERSATION_FOLLOWUPS_BOOTSTRAPPED = True


def get_conversation_followups() -> list[dict]:
    """读取会话级延迟续话任务。"""
    _ensure_conversation_followups_bootstrapped()
    items = conversation_followup_store.get_items()
    if items or conversation_followup_store.has_items():
        return items
    return _read_conversation_followups_from_r2()


def save_conversation_followups(items: list[dict]) -> bool:
    """保存会话级延迟续话任务（覆盖）。"""
    client = _s3_client()
    if not client:
        return False
    payload = {"items": [dict(x) for x in (items or []) if isinstance(x, dict)]}
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_CONVERSATION_FOLLOWUPS, payload)
            conversation_followup_store.replace_items(payload["items"])
            return True
        except Exception as e:
            logger.error("save_conversation_followups 失败 error=%s", e, exc_info=True)
            return False


def append_conversation_followup(item: dict) -> bool:
    """追加一条会话级延迟续话任务。"""
    if not isinstance(item, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            data = _read_json(client, R2_KEY_CONVERSATION_FOLLOWUPS)
            if not isinstance(data, dict):
                data = {}
            items = data.get("items")
            if not isinstance(items, list):
                items = []
            items.insert(0, dict(item))
            if len(items) > 200:
                items = items[:200]
            data["items"] = items
            _write_json(client, R2_KEY_CONVERSATION_FOLLOWUPS, data)
            conversation_followup_store.replace_items([dict(x) for x in items if isinstance(x, dict)])
            return True
        except Exception as e:
            logger.error("append_conversation_followup 失败 error=%s", e, exc_info=True)
            return False


def get_last_user_activity_at() -> Optional[str]:
    """读取目标用户最近一次真实活动时间（北京时间 ISO）。未配置 R2 或不存在则返回 None。"""
    client = _s3_client()
    if not client:
        return None
    for key in (R2_KEY_LAST_USER_ACTIVITY_AT, R2_KEY_LAST_USER_ACTIVITY_AT_LEGACY):
        try:
            resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            v = resp["Body"].read().decode("utf-8").strip()
            if v:
                return v
        except Exception:
            continue
    return None


def _parse_last_user_activity_audit_dt(value: str) -> Optional[datetime]:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BEIJING_TZ)
        return dt.astimezone(BEIJING_TZ)
    except Exception:
        return None


def _prune_last_user_activity_audit_items(items: list, now_dt: datetime) -> list[dict]:
    cutoff = now_dt - timedelta(hours=LAST_USER_ACTIVITY_AUDIT_TTL_HOURS)
    kept: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_dt = _parse_last_user_activity_audit_dt(str(item.get("logged_at") or item.get("activity_at") or ""))
        if item_dt and item_dt < cutoff:
            continue
        kept.append(item)
        if len(kept) >= LAST_USER_ACTIVITY_AUDIT_MAX_ITEMS:
            break
    return kept


def get_last_user_activity_audit(limit: int = 100) -> dict:
    """读取 last_user_activity 最近 24h 写入审计，用于排查是谁更新了全局时间。"""
    client = _s3_client()
    if not client:
        return {"items": [], "updated_at": "", "ttl_hours": LAST_USER_ACTIVITY_AUDIT_TTL_HOURS}
    data = _read_json(client, R2_KEY_LAST_USER_ACTIVITY_AUDIT)
    if not isinstance(data, dict):
        data = _read_json(client, R2_KEY_LAST_USER_ACTIVITY_AUDIT_LEGACY)
    if not isinstance(data, dict):
        return {"items": [], "updated_at": "", "ttl_hours": LAST_USER_ACTIVITY_AUDIT_TTL_HOURS}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    try:
        n = max(1, min(int(limit or 100), LAST_USER_ACTIVITY_AUDIT_MAX_ITEMS))
    except Exception:
        n = 100
    return {
        "items": _prune_last_user_activity_audit_items(items, datetime.now(BEIJING_TZ))[:n],
        "updated_at": str(data.get("updated_at") or ""),
        "ttl_hours": LAST_USER_ACTIVITY_AUDIT_TTL_HOURS,
    }


def _clean_last_user_activity_source(source: str) -> str:
    return str(source or "").strip()


def _clean_last_user_activity_detail(detail: Optional[dict]) -> dict:
    if not isinstance(detail, dict):
        return {}
    try:
        return json.loads(json.dumps(detail, ensure_ascii=False, default=str))
    except Exception:
        return {"_detail_error": "unserializable"}


def _append_last_user_activity_audit(client, entry: dict) -> None:
    now = str(entry.get("logged_at") or now_beijing_iso())
    data = _read_json(client, R2_KEY_LAST_USER_ACTIVITY_AUDIT)
    if not isinstance(data, dict):
        data = {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    pruned = _prune_last_user_activity_audit_items([entry] + items, datetime.now(BEIJING_TZ))
    _write_json(
        client,
        R2_KEY_LAST_USER_ACTIVITY_AUDIT,
        {
            "items": pruned,
            "updated_at": now,
            "ttl_hours": LAST_USER_ACTIVITY_AUDIT_TTL_HOURS,
            "allowed_sources": sorted(LAST_USER_ACTIVITY_ALLOWED_SOURCES),
        },
    )


def save_last_user_activity_at(
    iso_str: str,
    *,
    source: str = "",
    detail: Optional[dict] = None,
) -> bool:
    """保存目标用户最近一次活动时间。只有明确白名单来源可以覆盖这个全局 key。"""
    client = _s3_client()
    if not client:
        return False
    s = (iso_str or "").strip()
    if not s:
        return False
    clean_source = _clean_last_user_activity_source(source)
    clean_detail = _clean_last_user_activity_detail(detail)
    if clean_source not in LAST_USER_ACTIVITY_ALLOWED_SOURCES:
        try:
            _append_last_user_activity_audit(
                client,
                {
                    "id": uuid4().hex,
                    "logged_at": now_beijing_iso(),
                    "activity_at": s,
                    "source": clean_source or "missing",
                    "accepted": False,
                    "denied_reason": "source_not_allowed",
                    "detail": clean_detail,
                },
            )
        except Exception as e:
            logger.warning("last_user activity reject audit failed source=%s error=%s", clean_source or "missing", e)
        logger.warning(
            "last_user activity rejected source=%s activity_at=%s",
            clean_source or "missing",
            s,
        )
        return False
    with _global_write_lock:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=R2_KEY_LAST_USER_ACTIVITY_AT,
                Body=s.encode("utf-8"),
                ContentType="text/plain",
            )
            try:
                now = now_beijing_iso()
                _append_last_user_activity_audit(
                    client,
                    {
                        "id": uuid4().hex,
                        "logged_at": now,
                        "activity_at": s,
                        "source": clean_source,
                        "accepted": True,
                        "detail": clean_detail,
                    },
                )
                logger.info("last_user activity saved source=%s activity_at=%s", clean_source, s)
            except Exception as e:
                logger.warning("last_user activity audit write failed source=%s error=%s", clean_source, e)
            return True
        except Exception:
            return False


def get_last_reply_channel() -> Optional[dict]:
    """读取最近一次真实对话入口。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_LAST_REPLY_CHANNEL)
    return data if isinstance(data, dict) else None


def save_last_reply_channel(channel: str, window_id: str = "", target: str = "", at_iso: str = "") -> bool:
    """保存最近一次真实对话入口，供后端事件按同入口回发。"""
    ch = str(channel or "").strip().lower()
    if ch not in {"tg", "wechat", "qq", "sumitalk"}:
        return False
    payload = {
        "channel": ch,
        "window_id": str(window_id or "").strip(),
        "target": str(target or "").strip(),
        "at": str(at_iso or "").strip() or now_beijing_iso(),
    }
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_LAST_REPLY_CHANNEL, payload)
            return True
        except Exception as e:
            logger.error("save_last_reply_channel 失败 channel=%s error=%s", ch, e, exc_info=True)
            return False


def get_tg_todos(window_id: str) -> list[dict]:
    """读取 Telegram 窗口的 TodoList。window_id 应为 tg_{user_id}。"""
    if not (window_id and window_id.strip()):
        return []
    client = _s3_client()
    if not client:
        return []
    prefix = _prefix(window_id)
    key = _get_key(prefix, R2_KEY_TG_TODOS)
    data = _read_json(client, key)
    if not data:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def save_tg_todos(window_id: str, items: list[dict]) -> bool:
    """保存 Telegram 窗口的 TodoList（覆盖）。"""
    if not (window_id and window_id.strip()):
        return False
    client = _s3_client()
    if not client:
        return False
    prefix = _prefix(window_id)
    key = _get_key(prefix, R2_KEY_TG_TODOS)
    payload = {"items": items or []}
    with _global_write_lock:
        try:
            _write_json(client, key, payload)
            return True
        except Exception:
            return False


# ---------- 动态层 current.json ----------


def get_dynamic_memory_list() -> list:
    """读取动态层记忆列表。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DYNAMIC_MEMORY)
    if not data or not data.get("memories"):
        return []
    return data.get("memories", [])


def ensure_dynamic_memory_ids(memories: list) -> tuple[list, bool]:
    """
    确保动态层每条记忆都有稳定 id；如缺失则补 uuid4。
    返回 (memories_new, changed)。
    """
    if not memories:
        return [], False
    changed = False
    out = []
    for m in memories:
        if not isinstance(m, dict):
            continue
        mm = dict(m)
        if not mm.get("id"):
            mm["id"] = str(uuid4())
            changed = True
        if mm.get("mention_count") is None:
            mm["mention_count"] = 0
            changed = True
        for key in ("emotion_label", "scene_type", "target_type"):
            if key not in mm:
                mm[key] = ""
                changed = True
        out.append(mm)
    return out, changed


def save_dynamic_memory_list(memories: list) -> bool:
    """写回动态层记忆列表。多窗口同时写时加锁。"""
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_DYNAMIC_MEMORY, {"memories": memories})
            return True
        except Exception as e:
            logger.error("save_dynamic_memory_list 失败 error=%s", e, exc_info=True)
            return False


def touch_dynamic_memory_mentions(memory_ids: list[str]) -> int:
    """按 memory_id 给动态记忆 mention_count +1，并刷新 last_mentioned。"""
    ids: list[str] = []
    seen = set()
    for raw in memory_ids or []:
        mid = str(raw or "").strip()
        if not mid or mid.startswith("core::") or mid in seen:
            continue
        seen.add(mid)
        ids.append(mid)
    if not ids:
        return 0

    memories = get_dynamic_memory_list()
    memories, id_changed = ensure_dynamic_memory_ids(memories)
    if not memories:
        return 0

    id_set = set(ids)
    now = now_beijing_iso()
    touched = 0
    for mem in memories:
        if str((mem or {}).get("id") or "").strip() not in id_set:
            continue
        try:
            mention_count = int((mem or {}).get("mention_count") or 0)
        except Exception:
            mention_count = 0
        mem["mention_count"] = mention_count + 1
        mem["last_mentioned"] = now
        touched += 1

    if not touched:
        if id_changed:
            save_dynamic_memory_list(memories)
        return 0
    if not save_dynamic_memory_list(memories):
        return 0
    logger.info("动态记忆引用回写完成 touched=%s ids=%s", touched, ids[:10])
    return touched


def retain_dynamic_memory_by_id(memory_id: str) -> dict:
    """保留单条动态记忆，并返回可区分未命中与写入失败的结果。"""
    clean_id = str(memory_id or "").strip()
    if not clean_id:
        return {"status": "not_found", "id": ""}

    client = _s3_client()
    if not client:
        logger.error("动态记忆保留失败：R2 未配置 memory_id=%s", clean_id)
        return {"status": "write_failed", "id": clean_id}

    updated_memory = None
    try:
        with _global_write_lock:
            data = _read_json(client, R2_KEY_DYNAMIC_MEMORY)
            memories = data.get("memories") if isinstance(data, dict) else None
            if not isinstance(memories, list):
                return {"status": "not_found", "id": clean_id}

            updated_memories = list(memories)
            for index, raw_memory in enumerate(memories):
                if not isinstance(raw_memory, dict):
                    continue
                if str(raw_memory.get("id") or "").strip() != clean_id:
                    continue
                updated_memory = dict(raw_memory)
                try:
                    mention_count = int(updated_memory.get("mention_count") or 0)
                except (TypeError, ValueError):
                    mention_count = 0
                updated_memory["mention_count"] = mention_count + 1
                updated_memory["last_mentioned"] = now_beijing_iso()
                updated_memories[index] = updated_memory
                break

            if updated_memory is None:
                return {"status": "not_found", "id": clean_id}

            _write_json(client, R2_KEY_DYNAMIC_MEMORY, {"memories": updated_memories})
    except Exception as e:
        logger.error("动态记忆保留写入失败 memory_id=%s error=%s", clean_id, e, exc_info=True)
        return {"status": "write_failed", "id": clean_id}

    _invalidate_memory_recall_cache_safe()
    logger.info(
        "动态记忆保留完成 memory_id=%s mention_count=%s last_mentioned=%s",
        clean_id,
        updated_memory.get("mention_count"),
        updated_memory.get("last_mentioned"),
    )
    return {
        "status": "ok",
        "id": clean_id,
        "memory": updated_memory,
    }


def get_dynamic_recall_debug_events(limit: int = 30) -> list[dict]:
    """读取动态记忆召回调试事件（按时间倒序取最近 N 条）。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DYNAMIC_RECALL_DEBUG)
    if not isinstance(data, dict):
        return []
    events = data.get("events")
    if not isinstance(events, list):
        return []
    out = [x for x in events if isinstance(x, dict)]
    out.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    try:
        n = int(limit or 30)
    except Exception:
        n = 30
    if n < 1:
        n = 1
    if n > 200:
        n = 200
    return out[:n]


def append_dynamic_recall_debug_event(event: dict, max_keep: int = 200) -> bool:
    """追加一条动态记忆召回调试事件。"""
    if not isinstance(event, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    try:
        keep = int(max_keep or 200)
    except Exception:
        keep = 200
    if keep < 20:
        keep = 20
    if keep > 1000:
        keep = 1000
    with _global_write_lock:
        try:
            data = _read_json(client, R2_KEY_DYNAMIC_RECALL_DEBUG)
            events = []
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                events = [x for x in data.get("events") if isinstance(x, dict)]
            events.append(event)
            if len(events) > keep:
                events = events[-keep:]
            _write_json(
                client,
                R2_KEY_DYNAMIC_RECALL_DEBUG,
                {"events": events, "updated_at": now_beijing_iso()},
            )
            return True
        except Exception as e:
            logger.error("append_dynamic_recall_debug_event 失败 error=%s", e, exc_info=True)
            return False


def get_dynamic_ds_audit_events(limit: int = 30) -> list[dict]:
    """读取动态记忆 DS 写入决策审计事件（按时间倒序取最近 N 条）。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DYNAMIC_DS_AUDIT)
    if not isinstance(data, dict):
        return []
    events = data.get("events")
    if not isinstance(events, list):
        return []
    out = [x for x in events if isinstance(x, dict)]
    out.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    try:
        n = int(limit or 30)
    except Exception:
        n = 30
    if n < 1:
        n = 1
    if n > 300:
        n = 300
    return out[:n]


def append_dynamic_ds_audit_event(event: dict, max_keep: int = 300) -> bool:
    """追加一条动态记忆 DS 写入决策审计事件。"""
    if not isinstance(event, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    try:
        keep = int(max_keep or 300)
    except Exception:
        keep = 300
    if keep < 30:
        keep = 30
    if keep > 1000:
        keep = 1000
    with _global_write_lock:
        try:
            data = _read_json(client, R2_KEY_DYNAMIC_DS_AUDIT)
            events = []
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                events = [x for x in data.get("events") if isinstance(x, dict)]
            events.append(event)
            if len(events) > keep:
                events = events[-keep:]
            _write_json(
                client,
                R2_KEY_DYNAMIC_DS_AUDIT,
                {"events": events, "updated_at": now_beijing_iso()},
            )
            return True
        except Exception as e:
            logger.error("append_dynamic_ds_audit_event 失败 error=%s", e, exc_info=True)
            return False


def get_dynamic_memory_maintenance_report() -> dict:
    """读取最近一次动态记忆离线慢整理结果。"""
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, R2_KEY_DYNAMIC_MAINTENANCE_REPORT)
    return data if isinstance(data, dict) else {}


def save_dynamic_memory_maintenance_report(report: dict) -> bool:
    """写入最近一次动态记忆离线慢整理结果。"""
    if not isinstance(report, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_DYNAMIC_MAINTENANCE_REPORT, report)
            return True
        except Exception as e:
            logger.error("save_dynamic_memory_maintenance_report 失败 error=%s", e, exc_info=True)
            return False


# ---------- 核心记忆层 pending.json（兼容旧 key；importance>=4 存当轮原文，mention_count>=5 存融合版） ----------


def get_core_cache_pending() -> list:
    """读取核心记忆列表。每项含 id, promoted_by, content, importance, mention_count, promoted_at。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_CORE_CACHE)
    if not data or not data.get("pending"):
        return []
    return data.get("pending", [])


def save_core_cache_pending(pending: list) -> bool:
    """写回核心记忆列表。多窗口写时加锁。"""
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_CORE_CACHE, {"pending": pending})
            return True
        except Exception as e:
            logger.error("save_core_cache_pending 失败 error=%s", e, exc_info=True)
            return False


def _normalize_memory_layer(layer: str) -> str:
    normalized = str(layer or "").strip().lower()
    return normalized if normalized in {"dynamic", "core"} else ""


def _memory_trash_entry_id(entry: dict) -> str:
    memory = entry.get("memory") if isinstance(entry, dict) else None
    return str((memory or {}).get("id") or "").strip()


def _prune_memory_trash_items(items: list) -> list:
    from utils.time_aware import _now_beijing, parse_iso_to_beijing

    cutoff = _now_beijing() - timedelta(days=MEMORY_TRASH_TTL_DAYS)
    kept = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if not _normalize_memory_layer(item.get("layer")) or not _memory_trash_entry_id(item):
            continue
        deleted_at = parse_iso_to_beijing(str(item.get("deleted_at") or ""))
        if deleted_at is not None and deleted_at >= cutoff:
            kept.append(item)
    return kept


def get_memory_trash(layer: str = "") -> list:
    """读取统一记忆回收站；超过 7 天的条目不再可恢复并从 R2 清除。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_MEMORY_TRASH)
    raw_items = data.get("items") if isinstance(data, dict) else []
    items = [dict(x) for x in (raw_items or []) if isinstance(x, dict)]
    kept = _prune_memory_trash_items(items)
    if len(kept) != len(items):
        save_memory_trash(kept)
    normalized_layer = _normalize_memory_layer(layer)
    if normalized_layer:
        return [item for item in kept if item.get("layer") == normalized_layer]
    return kept


def save_memory_trash(items: list) -> bool:
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MEMORY_TRASH, {"items": items or []})
            return True
        except Exception as e:
            logger.error("save_memory_trash 失败 error=%s", e, exc_info=True)
            return False


def _upsert_core_cache_pending_index_safe(items: list) -> None:
    try:
        from memory_vector.core_pending_index import upsert_core_pending_items

        upsert_core_pending_items(items)
    except Exception as e:
        logger.warning("core_cache pending 索引 upsert 失败 error=%s", e, exc_info=True)


def _remove_core_cache_pending_index_safe(entry_ids: set[str]) -> None:
    try:
        from memory_vector.core_pending_index import remove_core_pending_ids

        remove_core_pending_ids(entry_ids)
    except Exception as e:
        logger.warning("core_cache pending 索引删除失败 error=%s", e, exc_info=True)


def _remove_dynamic_memory_index_safe(entry_ids: set[str]) -> None:
    try:
        from memory_vector.vector_index_store import remove_memory_ids_from_all_indices

        remove_memory_ids_from_all_indices(entry_ids)
    except Exception as e:
        logger.warning("动态记忆索引删除失败 ids=%s error=%s", sorted(entry_ids), e, exc_info=True)


def _upsert_dynamic_memory_index_safe(item: dict) -> None:
    try:
        from pipeline.pipeline import _upsert_dynamic_memory_index

        _upsert_dynamic_memory_index(item)
    except Exception as e:
        logger.warning("动态记忆索引恢复失败 memory_id=%s error=%s", item.get("id"), e, exc_info=True)


def _invalidate_memory_recall_cache_safe() -> None:
    try:
        from pipeline.pipeline import _invalidate_recall_cache

        _invalidate_recall_cache()
    except Exception as e:
        logger.warning("记忆召回缓存清理失败 error=%s", e, exc_info=True)


def promote_to_core_cache(
    window_id: str,
    round_index: int,
    round_messages_text: str,
    current_memories: list,
    touched_mem_id: Optional[str] = None,
) -> set[str]:
    """
    动态层写入/更新后调用：满足条件则加入核心记忆列表。
    返回已经可靠存在于核心层、应从动态层移走的源 memory id 集合。

    晋升是移动，不是复制：调用方只有拿到返回值后，才可以删除对应动态记忆。
    核心写入失败时返回空集合，确保动态层原件不会丢失。

    只存“动态层总结后的记忆内容”，不存 user/assistant 原始对话。
    - 条件A：本轮触及的记忆 importance>=4 → 存该记忆的 summary content，id=imp_{window_id}_{round_index}，promoted_by=importance
    - 条件B：任一条记忆 mention_count>=5 → 存该条融合版 content，id=记忆 id，promoted_by=mention_count
    """
    client = _s3_client()
    if not client:
        return set()
    pending = get_core_cache_pending()
    existing_ids = {p.get("id") for p in pending if p.get("id")}
    existing_source_ids = {
        str(p.get("source_memory_id") or "").strip()
        for p in pending
        if str(p.get("source_memory_id") or "").strip()
    }
    # 旧 mention_count 核心项直接沿用了动态 id；兼容识别为同一源记忆。
    existing_source_ids.update(
        str(p.get("id") or "").strip()
        for p in pending
        if p.get("promoted_by") == "mention_count" and str(p.get("id") or "").strip()
    )
    promoted_at = now_beijing_iso()
    added = False
    added_items = []
    promoted_source_ids: set[str] = set()

    # 条件A：本轮触及记忆 importance>=4，存动态层 summary（不是原始对话）
    if touched_mem_id:
        for m in current_memories:
            if m.get("id") != touched_mem_id:
                continue
            if int(m.get("importance") or 0) >= 4:
                source_memory_id = str(m.get("id") or "").strip()
                if source_memory_id in existing_source_ids:
                    promoted_source_ids.add(source_memory_id)
                    break
                imp_id = f"imp_{window_id}_{round_index}"
                summary_content = str(m.get("content") or "").strip()
                if imp_id not in existing_ids and summary_content:
                    item = {
                        "id": imp_id,
                        "source_memory_id": source_memory_id,
                        "promoted_by": "importance",
                        "content": summary_content,
                        "importance": int(m.get("importance") or 0),
                        "mention_count": int(m.get("mention_count") or 0),
                        "promoted_at": promoted_at,
                        "created_at": str(m.get("created_at") or ""),
                        "updated_at": str(m.get("updated_at") or m.get("created_at") or ""),
                        "last_mentioned": str(m.get("last_mentioned") or ""),
                        "tag": (m.get("tag") or "").strip(),
                        "emotion_label": (m.get("emotion_label") or "").strip(),
                        "scene_type": (m.get("scene_type") or "").strip(),
                        "target_type": (m.get("target_type") or "").strip(),
                    }
                    pending.append(item)
                    added_items.append(item)
                    existing_ids.add(imp_id)
                    existing_source_ids.add(source_memory_id)
                    promoted_source_ids.add(source_memory_id)
                    added = True
            break

    # 条件B：mention_count>=5 的存融合版，用记忆 id 去重
    for m in current_memories:
        mid = m.get("id")
        if not mid or int(m.get("mention_count") or 0) < 5:
            continue
        mid = str(mid).strip()
        if mid in existing_source_ids or mid in existing_ids:
            promoted_source_ids.add(mid)
            continue
        item = {
            "id": mid,
            "source_memory_id": mid,
            "promoted_by": "mention_count",
            "content": (m.get("content") or "").strip(),
            "importance": int(m.get("importance") or 0),
            "mention_count": int(m.get("mention_count") or 0),
            "promoted_at": promoted_at,
            "created_at": str(m.get("created_at") or ""),
            "updated_at": str(m.get("updated_at") or m.get("created_at") or ""),
            "last_mentioned": str(m.get("last_mentioned") or ""),
            "tag": (m.get("tag") or "").strip(),
            "emotion_label": (m.get("emotion_label") or "").strip(),
            "scene_type": (m.get("scene_type") or "").strip(),
            "target_type": (m.get("target_type") or "").strip(),
        }
        pending.append(item)
        added_items.append(item)
        existing_ids.add(mid)
        existing_source_ids.add(mid)
        promoted_source_ids.add(mid)
        added = True

    if added:
        if not save_core_cache_pending(pending):
            return set()
        _upsert_core_cache_pending_index_safe(added_items)
        logger.info("core_cache 提拔 条数=%s", len(pending))
    return promoted_source_ids


def stage_core_memory_merge(
    entry_id: str,
    *,
    original_content: str,
    rewritten_content: str,
    proposed_at: str,
    window_id: str,
    round_index: int,
    field_updates: dict,
) -> bool:
    """暂存核心记忆 merge 候选；不修改当前生效正文，等待人工审核。"""
    clean_id = str(entry_id or "").strip()
    original = str(original_content or "").strip()
    rewritten = str(rewritten_content or "").strip()
    if not clean_id or not original or not rewritten or original == rewritten:
        return False
    pending = get_core_cache_pending()
    for index, item in enumerate(pending):
        if not isinstance(item, dict) or str(item.get("id") or "").strip() != clean_id:
            continue
        if str(item.get("content") or "").strip() != original:
            return False
        updated = dict(item)
        updated["pending_merge"] = {
            "original_content": original,
            "rewritten_content": rewritten,
            "reason": "本轮召回核心记忆后生成的 merge 候选",
            "proposed_at": str(proposed_at or "").strip() or now_beijing_iso(),
            "window_id": str(window_id or "").strip(),
            "round_index": int(round_index or 0),
            "field_updates": dict(field_updates or {}),
        }
        pending[index] = updated
        return save_core_cache_pending(pending)
    return False


def delete_memory_by_id(layer: str, entry_id: str) -> bool:
    """把动态/核心记忆移入统一回收站，并立即退出 active 层与召回索引。"""
    normalized_layer = _normalize_memory_layer(layer)
    clean_id = str(entry_id or "").strip()
    if not normalized_layer or not clean_id:
        return False

    active_items = get_dynamic_memory_list() if normalized_layer == "dynamic" else get_core_cache_pending()
    deleted = next(
        (
            item
            for item in active_items
            if isinstance(item, dict) and str(item.get("id") or "").strip() == clean_id
        ),
        None,
    )
    if not isinstance(deleted, dict):
        return False
    remaining_active = [item for item in active_items if item is not deleted]

    trash_before = get_memory_trash()
    trash = [
        item
        for item in trash_before
        if not (
            item.get("layer") == normalized_layer
            and _memory_trash_entry_id(item) == clean_id
        )
    ]
    trash.insert(
        0,
        {
            "layer": normalized_layer,
            "deleted_at": now_beijing_iso(),
            "memory": dict(deleted),
        },
    )
    if not save_memory_trash(trash):
        return False

    save_active = save_dynamic_memory_list if normalized_layer == "dynamic" else save_core_cache_pending
    if not save_active(remaining_active):
        if not save_memory_trash(trash_before):
            logger.error("记忆删除失败且回收站回滚失败 layer=%s entry_id=%s", normalized_layer, clean_id)
        return False

    if normalized_layer == "dynamic":
        _remove_dynamic_memory_index_safe({clean_id})
    else:
        _remove_core_cache_pending_index_safe({clean_id})
    _invalidate_memory_recall_cache_safe()
    return True


def restore_memory_by_id(layer: str, entry_id: str) -> bool:
    """从统一回收站恢复到原层，并重建该层召回索引。"""
    normalized_layer = _normalize_memory_layer(layer)
    clean_id = str(entry_id or "").strip()
    if not normalized_layer or not clean_id:
        return False

    trash = get_memory_trash()
    trash_entry = next(
        (
            item
            for item in trash
            if item.get("layer") == normalized_layer and _memory_trash_entry_id(item) == clean_id
        ),
        None,
    )
    if not isinstance(trash_entry, dict) or not isinstance(trash_entry.get("memory"), dict):
        return False

    active_items = get_dynamic_memory_list() if normalized_layer == "dynamic" else get_core_cache_pending()
    if any(
        isinstance(item, dict) and str(item.get("id") or "").strip() == clean_id
        for item in active_items
    ):
        return False
    restored = dict(trash_entry["memory"])
    save_active = save_dynamic_memory_list if normalized_layer == "dynamic" else save_core_cache_pending
    if not save_active(active_items + [restored]):
        return False

    if normalized_layer == "dynamic":
        _upsert_dynamic_memory_index_safe(restored)
    else:
        _upsert_core_cache_pending_index_safe([restored])
    _invalidate_memory_recall_cache_safe()

    remaining_trash = [item for item in trash if item is not trash_entry]
    if not save_memory_trash(remaining_trash):
        logger.warning("记忆已恢复但回收站清理失败 layer=%s entry_id=%s", normalized_layer, clean_id)
    return True


def delete_core_cache_by_id(entry_id: str) -> bool:
    return delete_memory_by_id("core", entry_id)


def delete_dynamic_memory_by_id(entry_id: str) -> bool:
    return delete_memory_by_id("dynamic", entry_id)


# ---------- 图片描述存档 ----------


def save_image_description(window_id: str, message_id: str, description: str) -> bool:
    """将某条消息中图片的文字描述存到 R2。"""
    client = _s3_client()
    if not client:
        return False
    prefix = _prefix(window_id)
    key = _get_key(prefix, f"images/{message_id}.txt")
    client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=key,
        Body=description.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )
    return True


# ---------- 小渡的记忆文档（固定文本） ----------


def get_du_memory_doc() -> Optional[str]:
    """读取小渡的记忆文档 1.0；不存在时返回 None。"""
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_DU_MEMORY_DOC)
        return resp["Body"].read().decode("utf-8")
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None
        logger.error("get_du_memory_doc 失败 error=%s", e, exc_info=True)
        return None
    except Exception as e:
        logger.error("get_du_memory_doc 失败 error=%s", e, exc_info=True)
        return None


def save_du_memory_doc(text: str) -> bool:
    """
    保存/覆盖小渡的记忆文档。
    仅用于固定文档（不加锁；调用频率极低）。
    """
    client = _s3_client()
    if not client:
        return False
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_KEY_DU_MEMORY_DOC,
            Body=(text or "").encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        return True
    except Exception as e:
        logger.error("save_du_memory_doc 失败 error=%s", e, exc_info=True)
        return False


def get_core_prompt_text() -> Optional[str]:
    """读取全局核心 Prompt（MiniApp 可编辑）；不存在时返回 None。"""
    cfg = get_core_prompt_config()
    if isinstance(cfg, dict):
        prompts = cfg.get("prompts") if isinstance(cfg.get("prompts"), dict) else {}
        active_key = str(cfg.get("active_key") or "a").strip().lower()
        active_key = "b" if active_key == "b" else "a"
        active_text = str((prompts or {}).get(active_key) or "").strip()
        if active_text:
            return active_text
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_CORE_PROMPT)
        return resp["Body"].read().decode("utf-8")
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None
        logger.error("get_core_prompt_text 失败 error=%s", e, exc_info=True)
        return None
    except Exception as e:
        logger.error("get_core_prompt_text 失败 error=%s", e, exc_info=True)
        return None


def save_core_prompt_text(text: str) -> bool:
    """保存/覆盖全局核心 Prompt（MiniApp 编辑后实时生效）。"""
    cfg = get_core_prompt_config()
    if isinstance(cfg, dict):
        prompts = cfg.get("prompts") if isinstance(cfg.get("prompts"), dict) else {}
        active_key = str(cfg.get("active_key") or "a").strip().lower()
        active_key = "b" if active_key == "b" else "a"
        prompts = {
            "a": str(prompts.get("a") or ""),
            "b": str(prompts.get("b") or ""),
        }
        prompts[active_key] = str(text or "")
        return save_core_prompt_config({"active_key": active_key, "prompts": prompts})
    client = _s3_client()
    if not client:
        return False
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_KEY_CORE_PROMPT,
            Body=(text or "").encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        return True
    except Exception as e:
        logger.error("save_core_prompt_text 失败 error=%s", e, exc_info=True)
        return False


def get_core_prompt_config() -> Optional[dict]:
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_CORE_PROMPT_CONFIG)
    if isinstance(data, dict):
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else {}
        active_key = str(data.get("active_key") or "a").strip().lower()
        active_key = "b" if active_key == "b" else "a"
        return {
            "active_key": active_key,
            "prompts": {
                "a": str(prompts.get("a") or ""),
                "b": str(prompts.get("b") or ""),
            },
        }
    legacy_text = None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_CORE_PROMPT)
        legacy_text = resp["Body"].read().decode("utf-8")
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code != "NoSuchKey":
            logger.error("get_core_prompt_config fallback 失败 error=%s", e, exc_info=True)
    except Exception as e:
        logger.error("get_core_prompt_config fallback 失败 error=%s", e, exc_info=True)
    if legacy_text is None:
        return None
    return {
        "active_key": "a",
        "prompts": {
            "a": str(legacy_text or ""),
            "b": "",
        },
    }


def save_core_prompt_config(data: dict) -> bool:
    client = _s3_client()
    if not client:
        return False
    prompts = data.get("prompts") if isinstance(data, dict) and isinstance(data.get("prompts"), dict) else {}
    active_key = str((data or {}).get("active_key") or "a").strip().lower()
    active_key = "b" if active_key == "b" else "a"
    payload = {
        "active_key": active_key,
        "prompts": {
            "a": str(prompts.get("a") or ""),
            "b": str(prompts.get("b") or ""),
        },
    }
    try:
        with _global_write_lock:
            _write_json(client, R2_KEY_CORE_PROMPT_CONFIG, payload)
            active_text = payload["prompts"].get(active_key) or ""
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=R2_KEY_CORE_PROMPT,
                Body=active_text.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
        return True
    except Exception as e:
        logger.error("save_core_prompt_config 失败 error=%s", e, exc_info=True)
        return False


def _prompt_manager_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _normalize_prompt_manager_config(data: Any) -> dict:
    if not isinstance(data, dict):
        data = {}
    sections_raw = data.get("sections") if isinstance(data.get("sections"), dict) else {}
    sections: dict[str, dict] = {}
    for section_id, raw in (sections_raw or {}).items():
        sid = str(section_id or "").strip()
        if not sid or not isinstance(raw, dict):
            continue
        content = str(raw.get("content") or "")
        try:
            revision = int(raw.get("revision") or 0)
        except Exception:
            revision = 0
        sections[sid] = {
            "section_id": sid,
            "content": content,
            "revision": revision,
            "content_sha256": str(raw.get("content_sha256") or _prompt_manager_hash(content)),
            "updated_at": str(raw.get("updated_at") or ""),
            "updated_by_device": str(raw.get("updated_by_device") or ""),
            "source": str(raw.get("source") or "r2"),
        }
    return {"schema_version": 1, "sections": sections}


def get_prompt_manager_config() -> dict:
    client = _s3_client()
    if not client:
        return _normalize_prompt_manager_config({})
    try:
        data = _read_json(client, R2_KEY_PROMPT_MANAGER_CONFIG)
        return _normalize_prompt_manager_config(data)
    except Exception as e:
        logger.error("get_prompt_manager_config 失败 error=%s", e, exc_info=True)
        return _normalize_prompt_manager_config({})


def get_prompt_manager_section(section_id: str) -> Optional[dict]:
    sid = str(section_id or "").strip()
    if not sid:
        return None
    cfg = get_prompt_manager_config()
    section = (cfg.get("sections") or {}).get(sid)
    return dict(section) if isinstance(section, dict) else None


def get_prompt_manager_section_text(section_id: str) -> Optional[str]:
    section = get_prompt_manager_section(section_id)
    if not section:
        return None
    return str(section.get("content") or "")


def _backup_prompt_manager_section(
    client,
    *,
    section_id: str,
    content: str,
    revision: int,
    updated_at: str = "",
    updated_by_device: str = "",
    reason: str = "save",
) -> dict:
    now = now_beijing_iso()
    backup_id = f"{datetime.now(BEIJING_TZ).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:10]}"
    payload = {
        "backup_id": backup_id,
        "section_id": section_id,
        "content": str(content or ""),
        "revision": int(revision or 0),
        "content_sha256": _prompt_manager_hash(str(content or "")),
        "content_length": len(str(content or "")),
        "created_at": now,
        "updated_at": str(updated_at or ""),
        "updated_by_device": str(updated_by_device or ""),
        "reason": str(reason or "save"),
        "schema_version": 1,
    }
    key = f"{R2_KEY_PROMPT_MANAGER_BACKUP_PREFIX}{section_id}/{backup_id}.json"
    _write_json(client, key, payload)
    return {k: v for k, v in payload.items() if k != "content"}


def _list_prompt_manager_backups_with_client(client, section_id: str) -> list[dict]:
    prefix = f"{R2_KEY_PROMPT_MANAGER_BACKUP_PREFIX}{section_id}/"
    rows: list[dict] = []
    kwargs: dict[str, Any] = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix}
    while True:
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = str(obj.get("Key") or "")
            if not key.endswith(".json"):
                continue
            data = _read_json(client, key)
            if not isinstance(data, dict):
                continue
            item = {k: v for k, v in data.items() if k != "content"}
            item["key"] = key
            rows.append(item)
        token = resp.get("NextContinuationToken")
        if not token:
            break
        kwargs["ContinuationToken"] = token
    rows.sort(
        key=lambda x: (str(x.get("created_at") or ""), str(x.get("backup_id") or "")),
        reverse=True,
    )
    return rows


def _prune_prompt_manager_backups_with_client(
    client,
    section_id: str,
    *,
    keep: int = PROMPT_MANAGER_BACKUP_KEEP,
) -> dict:
    sid = str(section_id or "").strip()
    if not sid:
        return {"ok": False, "deleted": 0, "error": "section_id 不能为空"}
    prefix = f"{R2_KEY_PROMPT_MANAGER_BACKUP_PREFIX}{sid}/"
    try:
        rows = _list_prompt_manager_backups_with_client(client, sid)
        stale_rows = rows[max(0, int(keep)) :]
        deleted = 0
        for item in stale_rows:
            key = str(item.get("key") or "")
            if not key.startswith(prefix) or not key.endswith(".json"):
                logger.warning("跳过异常 Prompt Manager 备份 key section_id=%s key=%s", sid, key)
                continue
            client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
            deleted += 1
        return {"ok": True, "deleted": deleted, "remaining": len(rows) - deleted}
    except Exception as e:
        logger.error("清理 Prompt Manager 备份失败 section_id=%s error=%s", sid, e, exc_info=True)
        return {"ok": False, "deleted": 0, "error": str(e)}


def prune_prompt_manager_backups(
    section_id: str,
    *,
    keep: int = PROMPT_MANAGER_BACKUP_KEEP,
) -> dict:
    client = _s3_client()
    if not client:
        return {"ok": False, "deleted": 0, "error": "R2 未配置"}
    return _prune_prompt_manager_backups_with_client(client, section_id, keep=keep)


def save_prompt_manager_section(
    section_id: str,
    content: str,
    *,
    base_revision: Optional[int] = None,
    updated_by_device: str = "",
    backup_content: Optional[str] = None,
    backup_revision: Optional[int] = None,
    reason: str = "save",
) -> dict:
    client = _s3_client()
    if not client:
        return {"ok": False, "error": "R2 未配置"}
    sid = str(section_id or "").strip()
    if not sid:
        return {"ok": False, "error": "section_id 不能为空"}
    text = str(content or "")
    with _global_write_lock:
        try:
            cfg = get_prompt_manager_config()
            sections = cfg.get("sections") if isinstance(cfg.get("sections"), dict) else {}
            current = sections.get(sid) if isinstance(sections.get(sid), dict) else None
            current_revision = int((current or {}).get("revision") or 0)
            if base_revision is not None and int(base_revision) != current_revision:
                return {
                    "ok": False,
                    "error": "版本已变化，请重新加载后再保存",
                    "code": "revision_conflict",
                    "current_revision": current_revision,
                }

            previous_content = str((current or {}).get("content") or "")
            previous_revision = current_revision
            previous_updated_at = str((current or {}).get("updated_at") or "")
            previous_updated_by = str((current or {}).get("updated_by_device") or "")
            if backup_content is not None and not current:
                previous_content = str(backup_content or "")
                previous_revision = int(backup_revision or 0)
                previous_updated_at = ""
                previous_updated_by = ""

            backup = None
            if previous_content:
                backup = _backup_prompt_manager_section(
                    client,
                    section_id=sid,
                    content=previous_content,
                    revision=previous_revision,
                    updated_at=previous_updated_at,
                    updated_by_device=previous_updated_by,
                    reason=reason,
                )

            next_revision = max(current_revision, int(time.time() * 1000)) + 1
            now = now_beijing_iso()
            section = {
                "section_id": sid,
                "content": text,
                "revision": next_revision,
                "content_sha256": _prompt_manager_hash(text),
                "updated_at": now,
                "updated_by_device": str(updated_by_device or ""),
                "source": "r2",
            }
            sections[sid] = section
            payload = {"schema_version": 1, "sections": sections}
            _write_json(client, R2_KEY_PROMPT_MANAGER_CONFIG, payload)
            cleanup = _prune_prompt_manager_backups_with_client(client, sid)
            if not cleanup.get("ok"):
                logger.warning("Prompt Manager 配置已保存，但备份清理失败 section_id=%s", sid)
            return {"ok": True, "section": section, "backup": backup}
        except Exception as e:
            logger.error("save_prompt_manager_section 失败 section_id=%s error=%s", sid, e, exc_info=True)
            return {"ok": False, "error": str(e)}


def list_prompt_manager_backups(section_id: str, limit: int = 30) -> list[dict]:
    client = _s3_client()
    if not client:
        return []
    sid = str(section_id or "").strip()
    if not sid:
        return []
    try:
        rows = _list_prompt_manager_backups_with_client(client, sid)
    except Exception as e:
        logger.error("list_prompt_manager_backups 失败 section_id=%s error=%s", sid, e, exc_info=True)
        return []
    return rows[: max(1, int(limit or 30))]


def get_prompt_manager_backup(section_id: str, backup_id: str) -> Optional[dict]:
    client = _s3_client()
    if not client:
        return None
    sid = str(section_id or "").strip()
    bid = str(backup_id or "").strip()
    if not sid or not bid or "/" in bid or ".." in bid:
        return None
    key = f"{R2_KEY_PROMPT_MANAGER_BACKUP_PREFIX}{sid}/{bid}.json"
    try:
        data = _read_json(client, key)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.error("get_prompt_manager_backup 失败 section_id=%s backup_id=%s error=%s", sid, bid, e, exc_info=True)
        return None


# ---------- 一键清空（测试/重置用） ----------


_R2_WIPE_PREFIXES = (
    "windows/",
    "conversations/",
    "global/",
    "dynamic_memory/",
    "core_cache/",
    "memory/",
    "notebook/",
    "docs/",
    "wenyou/",
    "sense/",
    "stickers/",
    "device_screenshots/",
    "sumitalk/chat_media/",
)


def delete_all_gateway_data() -> tuple[bool, int, Optional[str]]:
    """
    一键删除当前网关在 R2 中存的所有记录（对话、总结、动态层、核心缓存、小本本、图片描述等）。
    返回 (是否成功, 删除的 key 数量, 错误信息)。
    """
    client = _s3_client()
    if not client:
        return False, 0, "R2 未配置"
    keys_to_delete = []
    try:
        for prefix in _R2_WIPE_PREFIXES:
            token = None
            while True:
                kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix}
                if token:
                    kwargs["ContinuationToken"] = token
                resp = client.list_objects_v2(**kwargs)
                for obj in (resp.get("Contents") or []):
                    k = obj.get("Key")
                    if k:
                        keys_to_delete.append(k)
                if resp.get("IsTruncated"):
                    token = resp.get("NextContinuationToken")
                else:
                    break
        if not keys_to_delete:
            logger.info("delete_all_gateway_data 无数据可删")
            return True, 0, None
        deleted = 0
        for i in range(0, len(keys_to_delete), 1000):
            chunk = keys_to_delete[i : i + 1000]
            client.delete_objects(
                Bucket=R2_BUCKET_NAME,
                Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
            )
            deleted += len(chunk)
        logger.info("delete_all_gateway_data 已删除 %s 个 key", deleted)
        return True, deleted, None
    except Exception as e:
        logger.error("delete_all_gateway_data 失败 error=%s", e, exc_info=True)
        return False, 0, str(e)
