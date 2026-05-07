import time
import os
import math
import logging
import json
import re
import base64
import threading
from uuid import uuid4
from collections import Counter
from pathlib import Path
from datetime import datetime, timedelta

import requests
from flask import Blueprint, Response, current_app, jsonify, request
from urllib.parse import quote

from config import (
    DATA_DIR,
    R2_PUBLIC_URL,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    TELEGRAM_WENYOU_OWNER_USER_ID,
    WENYOU_GROUP_CHAT_ID,
    VOICE_CALL_MAX_BYTES,
    VOICE_CALL_WINDOW_ID,
    DEEPSEEK_API_URL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_CHAT_MODEL,
)
from storage import r2_store, whitelist_store, blacklist_store
from storage import silence_mode_store
from utils.ip_allowlist import enforce_ip_allowlist
from utils.miniapp_panel_auth import (
    enforce_panel_token,
)
from utils.telegram_webapp import enforce_telegram_initdata
from utils.time_aware import today_beijing, now_beijing_iso, parse_iso_to_beijing
from routes.miniapp.device_actions import register_routes as register_device_actions_routes
from routes.miniapp.device_state import register_routes as register_device_state_routes
from routes.miniapp.diagnostics import register_routes as register_diagnostics_routes
from routes.miniapp.logs import register_routes as register_logs_routes
from routes.miniapp.panel_auth import register_routes as register_panel_auth_routes
from routes.miniapp.sumitalk_history import register_routes as register_sumitalk_history_routes
from routes.miniapp.upstreams import register_routes as register_upstreams_routes


bp = Blueprint("miniapp_api", __name__, url_prefix="/miniapp-api")
register_device_actions_routes(bp)
register_device_state_routes(bp)
register_diagnostics_routes(bp)
register_logs_routes(bp)
register_panel_auth_routes(bp)
register_sumitalk_history_routes(bp)
register_upstreams_routes(bp)
logger = logging.getLogger(__name__)
sumitalk_logger = logging.getLogger("sumitalk")
_MEMORY_MAINTENANCE_LOCK = threading.Lock()
_MEMORY_MAINTENANCE_RUNNING = False
_MEMORY_MAINTENANCE_LAST_STARTED = ""
_MEMORY_MAINTENANCE_LAST_FINISHED = ""
_MEMORY_MAINTENANCE_LAST_ERROR = ""
_SUMITALK_CHAT_JOB_DIR = DATA_DIR / "sumitalk_chat_jobs"
_SUMITALK_CHAT_JOB_LOCK = threading.Lock()
_SUMITALK_CHAT_JOB_EVENTS: dict[str, threading.Event] = {}
_SUMITALK_CHAT_JOB_TTL_SECONDS = 30 * 60
_SUMITALK_CHAT_DIRECT_WAIT_MS = 2500


def _wenyou_session_id() -> int:
    return int(WENYOU_GROUP_CHAT_ID or TELEGRAM_WENYOU_OWNER_USER_ID or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)


def _resolve_primary_chat_window_id() -> str:
    recent = whitelist_store.list_recent_windows(limit=200) or []
    for w in recent:
        wid = str((w or {}).get("id") or "").strip()
        if wid.startswith("tg_"):
            return wid
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid > 0:
        return f"tg_{uid}"
    if recent:
        return str((recent[0] or {}).get("id") or "").strip()
    return ""


def _sumitalk_chat_job_path(job_id: str) -> Path:
    return _SUMITALK_CHAT_JOB_DIR / f"{job_id}.json"


def _valid_sumitalk_chat_job_id(job_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{32}", str(job_id or "").strip()))


def _safe_sumitalk_client_request_id(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^a-zA-Z0-9_.:-]", "", text)[:120]


def _find_sumitalk_chat_job_by_client_request_id(client_request_id: str, window_id: str, reply_target: str) -> dict | None:
    cid = _safe_sumitalk_client_request_id(client_request_id)
    if not cid or not _SUMITALK_CHAT_JOB_DIR.exists():
        return None
    best: dict | None = None
    best_ts = 0.0
    for path in _SUMITALK_CHAT_JOB_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            if not isinstance(data, dict):
                continue
            if _safe_sumitalk_client_request_id(data.get("client_request_id")) != cid:
                continue
            if str(data.get("window_id") or "").strip() != str(window_id or "").strip():
                continue
            if str(data.get("reply_target") or "").strip() != str(reply_target or "").strip():
                continue
            job_id = str(data.get("id") or "").strip()
            if not _valid_sumitalk_chat_job_id(job_id):
                continue
            ts = float(data.get("created_ts") or 0)
            if best is None or ts >= best_ts:
                best = data
                best_ts = ts
        except Exception:
            continue
    return best


def _write_sumitalk_chat_job_state(state: dict) -> None:
    job_id = str((state or {}).get("id") or "").strip()
    if not _valid_sumitalk_chat_job_id(job_id):
        raise ValueError("invalid job id")
    _SUMITALK_CHAT_JOB_DIR.mkdir(parents=True, exist_ok=True)
    path = _sumitalk_chat_job_path(job_id)
    tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(state or {}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_sumitalk_chat_job_state(job_id: str) -> dict | None:
    job_id = str(job_id or "").strip()
    if not _valid_sumitalk_chat_job_id(job_id):
        return None
    path = _sumitalk_chat_job_path(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _patch_sumitalk_chat_job_state(job_id: str, patch: dict) -> None:
    with _SUMITALK_CHAT_JOB_LOCK:
        current = _read_sumitalk_chat_job_state(job_id) or {"id": job_id, "created_ts": time.time(), "created_at": now_beijing_iso()}
        current.update(patch or {})
        current["updated_ts"] = time.time()
        current["updated_at"] = now_beijing_iso()
        _write_sumitalk_chat_job_state(current)


def _signal_sumitalk_chat_job(job_id: str) -> None:
    with _SUMITALK_CHAT_JOB_LOCK:
        event = _SUMITALK_CHAT_JOB_EVENTS.pop(str(job_id or "").strip(), None)
    if event is not None:
        event.set()


def _cleanup_sumitalk_chat_jobs() -> None:
    try:
        if not _SUMITALK_CHAT_JOB_DIR.exists():
            return
        cutoff = time.time() - max(60, int(_SUMITALK_CHAT_JOB_TTL_SECONDS))
        for path in _SUMITALK_CHAT_JOB_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
                updated_ts = float(data.get("updated_ts") or data.get("created_ts") or 0)
                if updated_ts and updated_ts < cutoff:
                    path.unlink(missing_ok=True)
            except Exception:
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink(missing_ok=True)
                except Exception:
                    pass
        with _SUMITALK_CHAT_JOB_LOCK:
            for job_id in list(_SUMITALK_CHAT_JOB_EVENTS.keys()):
                if not _sumitalk_chat_job_path(job_id).exists():
                    _SUMITALK_CHAT_JOB_EVENTS.pop(job_id, None)
    except Exception:
        pass


def _extract_chat_completion_result(result) -> tuple[int, dict]:
    response = result
    status = 200
    if isinstance(result, tuple):
        response = result[0] if result else None
        for item in result[1:]:
            if isinstance(item, int):
                status = item
                break
    if hasattr(response, "status_code"):
        try:
            status = int(response.status_code)
        except Exception:
            pass
    data = None
    if hasattr(response, "get_json"):
        try:
            data = response.get_json(silent=True)
        except Exception:
            data = None
    if data is None and hasattr(response, "get_data"):
        try:
            text = response.get_data(as_text=True)
            data = json.loads(text) if text else {}
        except Exception:
            data = {"raw": response.get_data(as_text=True) if hasattr(response, "get_data") else ""}
    if not isinstance(data, dict):
        data = {"content": data}
    return status, data


def _run_sumitalk_chat_job(app, job_id: str, chat_body: dict, headers: dict, remote_addr: str) -> None:
    _patch_sumitalk_chat_job_state(job_id, {"status": "running"})
    try:
        from routes.chat import chat_completions

        environ_base = {"REMOTE_ADDR": remote_addr or "127.0.0.1"}
        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=chat_body,
            headers=headers,
            environ_base=environ_base,
        ):
            result = chat_completions()
            status_code, data = _extract_chat_completion_result(result)
        if status_code >= 400:
            err = data.get("error") or data.get("message") or f"HTTP {status_code}"
            _patch_sumitalk_chat_job_state(
                job_id,
                {
                    "status": "error",
                    "status_code": status_code,
                    "error": str(err),
                    "response": data,
                },
            )
            return
        _patch_sumitalk_chat_job_state(
            job_id,
            {
                "status": "done",
                "status_code": status_code,
                "response": data,
            },
        )
    except Exception as e:
        sumitalk_logger.exception("chat_job_failed job_id=%s", job_id)
        _patch_sumitalk_chat_job_state(
            job_id,
            {
                "status": "error",
                "status_code": 500,
                "error": str(e),
            },
        )
    finally:
        _signal_sumitalk_chat_job(job_id)


def _start_sumitalk_chat_job_from_request(body: dict, waitable: bool = False):
    model = str(body.get("model") or "").strip()
    messages = body.get("messages") or []
    window_id = str(body.get("window_id") or "").strip()
    reply_target = str(body.get("reply_target") or request.headers.get("X-Reply-Target") or _get_panel_device_id()).strip()
    client_request_id = _safe_sumitalk_client_request_id(body.get("client_request_id"))
    if not model:
        return "", None, (jsonify({"ok": False, "error": "缺少 model"}), 400)
    if not isinstance(messages, list) or not messages:
        return "", None, (jsonify({"ok": False, "error": "缺少 messages"}), 400)
    if not window_id:
        return "", None, (jsonify({"ok": False, "error": "缺少 window_id"}), 400)
    _cleanup_sumitalk_chat_jobs()
    with _SUMITALK_CHAT_JOB_LOCK:
        existing = _find_sumitalk_chat_job_by_client_request_id(client_request_id, window_id, reply_target)
        if existing:
            existing_job_id = str(existing.get("id") or "").strip()
            event = _SUMITALK_CHAT_JOB_EVENTS.get(existing_job_id) if waitable else None
            sumitalk_logger.info(
                "chat_job_reused job_id=%s client_request_id=%s window_id=%s target=%s status=%s",
                existing_job_id,
                client_request_id,
                window_id,
                reply_target,
                str(existing.get("status") or ""),
            )
            return existing_job_id, event, None
        job_id = uuid4().hex
    chat_body = dict(body)
    chat_body["model"] = model
    chat_body["messages"] = messages
    chat_body["window_id"] = window_id
    chat_body["stream"] = False
    chat_body.pop("reply_target", None)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": request.headers.get("User-Agent") or "SumiTalk MiniApp",
        "X-Force-Last4": str(request.headers.get("X-Force-Last4") or body.get("force_last4") or "1"),
        "X-Reply-Channel": "sumitalk",
        "X-Reply-Target": reply_target,
        "X-Window-Id": window_id,
    }
    state = {
        "id": job_id,
        "ok": True,
        "status": "running",
        "created_ts": time.time(),
        "updated_ts": time.time(),
        "created_at": now_beijing_iso(),
        "updated_at": now_beijing_iso(),
        "client_request_id": client_request_id,
        "window_id": window_id,
        "reply_target": reply_target,
    }
    event = threading.Event() if waitable else None
    with _SUMITALK_CHAT_JOB_LOCK:
        existing = _find_sumitalk_chat_job_by_client_request_id(client_request_id, window_id, reply_target)
        if existing:
            existing_job_id = str(existing.get("id") or "").strip()
            existing_event = _SUMITALK_CHAT_JOB_EVENTS.get(existing_job_id) if waitable else None
            sumitalk_logger.info(
                "chat_job_reused_after_race job_id=%s client_request_id=%s window_id=%s target=%s status=%s",
                existing_job_id,
                client_request_id,
                window_id,
                reply_target,
                str(existing.get("status") or ""),
            )
            return existing_job_id, existing_event, None
        if event is not None:
            _SUMITALK_CHAT_JOB_EVENTS[job_id] = event
        _write_sumitalk_chat_job_state(state)
    app = current_app._get_current_object()
    remote_addr = request.remote_addr or ""
    threading.Thread(
        target=_run_sumitalk_chat_job,
        args=(app, job_id, chat_body, headers, remote_addr),
        daemon=True,
    ).start()
    sumitalk_logger.info("chat_job_created job_id=%s window_id=%s target=%s messages=%s", job_id, window_id, reply_target, len(messages))
    return job_id, event, None


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _notify_schedule_runtime_changed():
    """日历变更后通知网关内置调度线程立即重算。"""
    try:
        from services.schedule_runtime import notify_schedule_changed

        notify_schedule_changed()
    except Exception:
        pass


def _season_label(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"


def _default_cyber_tree_start_date(today: str) -> str:
    """
    默认从“今年”的纪念日 03-04 开始（不按每年回溯）。
    """
    try:
        y = int(str(today).split("-", 2)[0])
    except Exception:
        return "2026-03-04"
    return f"{y:04d}-03-04"


_DAILY_KW_STOPWORDS = {
    "今天",
    "现在",
    "这个",
    "那个",
    "然后",
    "就是",
    "还是",
    "感觉",
    "我们",
    "你们",
    "他们",
    "自己",
    "已经",
    "一下",
    "可能",
    "因为",
    "所以",
    "如果",
    "但是",
    "而且",
    "以及",
    "其实",
    "真的",
    "不会",
    "可以",
    "不要",
    "还有",
    "一个",
    "这个时候",
    "然后呢",
    "知道了",
}


def _extract_daily_keywords(texts: list[str], limit: int = 3) -> list[str]:
    """
    从文本中提取高频关键词（中英文），避免固定词表导致“每天都一样”。
    """
    tokens: list[str] = []
    for raw in texts or []:
        s = str(raw or "").strip()
        if not s:
            continue
        for t in re.findall(r"[\u4e00-\u9fff]{2,6}", s):
            t = t.strip()
            if t and t not in _DAILY_KW_STOPWORDS:
                tokens.append(t)
        for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,24}", s):
            lo = t.lower().strip()
            if lo and lo not in _DAILY_KW_STOPWORDS:
                tokens.append(lo)
    if not tokens:
        return []
    cnt = Counter(tokens)
    ranked = sorted(cnt.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [k for k, _ in ranked[: max(1, int(limit or 3))]]


def _generate_daily_report(today: str) -> dict:
    """按北京日期统计「今日」对话轮次与关键词（从最近存档中筛当日）。"""
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    window_id = f"tg_{uid}" if uid > 0 else ""
    # 拉取足够多的最近轮次，再按日期过滤（单日上限通常远小于此）
    all_rounds = r2_store.get_conversation_rounds(window_id, last_n=500) if window_id else []
    day_rounds: list[dict] = []
    user_text: list[str] = []
    all_text: list[str] = []
    for r in all_rounds or []:
        dt = _parse_beijing_dt(r.get("timestamp"))
        if not dt:
            continue
        if dt.strftime("%Y-%m-%d") != today:
            continue
        day_rounds.append(r)
        for m in (r.get("messages") or []):
            if not isinstance(m, dict):
                continue
            tx = _message_text(m.get("content"))
            if not tx:
                continue
            all_text.append(tx)
            role = str(m.get("role") or "").strip().lower()
            if role == "user":
                user_text.append(tx)
    rounds_count = len(day_rounds)
    # 优先用户消息关键词，避免被助手高频措辞“刷屏”成固定词。
    hot = _extract_daily_keywords(user_text, limit=3)
    if not hot:
        hot = _extract_daily_keywords(all_text, limit=3)
    if not hot:
        hot = ["陪伴", "日常", "关心"]
    report = {
        "report_date": today,
        "window_id": window_id,
        "rounds": rounds_count,
        "keywords": hot[:3],
        "done_count": 0,
        "summary_text": f"今天我们聊了 {rounds_count} 轮，关键词是 {' / '.join(hot[:3])}。",
        "generated_at": now_beijing_iso(),
    }
    return report


def _parse_beijing_dt(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(tz=None).astimezone()


def _mood_day_wave(seed_text: str) -> int:
    seed = sum(ord(ch) for ch in (seed_text or ""))
    return (seed % 5) - 2


def _extract_last_user_message_text(msgs: list[dict]) -> str:
    for m in reversed(msgs or []):
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip().lower() != "user":
            continue
        text = _message_text(m.get("content"))
        if text:
            return text
    return ""


def _extract_alarm_title_from_prompt(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "提醒"
    m = re.search(r"「([^」]+)」", raw)
    if m:
        return str(m.group(1) or "").strip() or "提醒"
    return "提醒"


def _tool_call_name(tc: dict) -> str:
    if not isinstance(tc, dict):
        return ""
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    return str(fn.get("name") or "").strip()


def _summarize_alarm_actions(msgs: list[dict]) -> list[str]:
    labels: list[str] = []
    for m in msgs or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip().lower() != "assistant":
            continue
        tcs = m.get("tool_calls") or []
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            name = _tool_call_name(tc)
            if not name:
                continue
            label = ""
            if name == "notion_diary_create":
                label = "写了日记"
            elif name == "daily_whisper_write":
                label = "写了气泡"
            elif name in {"forum_read_feed", "forum_open_thread"}:
                label = "看了论坛"
            elif name == "note_write":
                label = "写了便签"
            elif name in {"schedule_list", "get_time_info", "search_memory", "notion_diary_list"}:
                label = ""
            if label and label not in labels:
                labels.append(label)
    return labels


def _build_du_day_events(today: str) -> list[dict]:
    out: list[dict] = []

    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    window_id = f"tg_{uid}" if uid > 0 else ""
    rounds = r2_store.get_conversation_rounds(window_id, last_n=240) if window_id else []
    for r in rounds or []:
        dt = _parse_beijing_dt(r.get("timestamp"))
        if not dt or dt.strftime("%Y-%m-%d") != today:
            continue
        msgs = r.get("messages") or []
        user_text = _extract_last_user_message_text(msgs)
        if not user_text.startswith("你给自己定的「"):
            continue
        actions = _summarize_alarm_actions(msgs)
        out.append(
            {
                "kind": "routine",
                "timestamp": dt.isoformat(),
                "time": dt.strftime("%H:%M"),
                "title": "Morning Alarm",
                "subtitle": "醒来第一件事" if "醒来第一件事" in user_text else "",
                "actions": actions,
            }
        )

    for item in r2_store.get_proactive_decision_memory_items() or []:
        at = str(item.get("at") or "").strip()
        dt = _parse_beijing_dt(at)
        if not dt or dt.strftime("%Y-%m-%d") != today:
            continue
        action = str(item.get("action") or "").strip() or "unknown"
        reason = str(item.get("reason") or "").strip() or "—"
        if action == "error":
            continue
        lowered_reason = reason.lower()
        if "gateway_status=" in lowered_reason or "http 403" in lowered_reason or "403" in lowered_reason:
            continue
        out.append(
            {
                "kind": "decision",
                "timestamp": dt.isoformat(),
                "time": dt.strftime("%H:%M"),
                "title": "Active Reach",
                "decision_label": f"渡选择了 {action}",
                "reason": reason,
            }
        )

    out.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    return out


def _voice_call_default_config() -> dict:
    return {
        "displayName": "渡",
        "subtitle": "语音通话中",
        "avatarVersion": 0,
        "useAvatarImage": False,
        "theme": "night",
    }


def _miniapp_voice_avatar_url(avatar_version: int) -> str:
    v = max(0, int(avatar_version or 0))
    if v > 0:
        return f"/miniapp-api/voice-avatar/{v}"
    return "/miniapp-api/voice-avatar"


def _resolve_voice_call_window_id(explicit_window_id: str = "") -> str:
    wid = str(explicit_window_id or "").strip()
    if wid:
        return wid
    tg_uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if tg_uid > 0:
        return f"tg_{tg_uid}"
    return (VOICE_CALL_WINDOW_ID or "miniapp_voice_call").strip() or "miniapp_voice_call"


def _sort_call_records(items: list[dict]) -> list[dict]:
    return sorted(items or [], key=lambda x: str(x.get("updated_at") or x.get("started_at") or ""), reverse=True)


def _call_record_summary(item: dict) -> dict:
    turns = item.get("turns") or []
    started_at = str(item.get("started_at") or "").strip()
    title = str(item.get("title") or "").strip()
    if not title:
        title = "语音通话"
    preview = ""
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("text") or "").strip()
        if text:
            preview = text[:48]
            break
    return {
        "id": str(item.get("id") or "").strip(),
        "mode": str(item.get("mode") or "voice"),
        "started_at": started_at,
        "updated_at": str(item.get("updated_at") or started_at).strip() or started_at,
        "title": title,
        "preview": preview,
        "turn_count": len(turns),
    }


def _append_call_record_turns(call_id: str, started_at: str, turns: list[dict], mode: str = "voice") -> bool:
    cid = str(call_id or "").strip()
    if not cid or not turns:
        return False
    items = r2_store.get_miniapp_call_records() or []
    now_ts = now_beijing_iso()
    found = None
    for item in items:
        if str(item.get("id") or "").strip() == cid:
            found = item
            break
    if found is None:
        found = {
            "id": cid,
            "mode": mode or "voice",
            "started_at": started_at or now_ts,
            "updated_at": now_ts,
            "title": "语音通话",
            "turns": [],
        }
        items.append(found)
    found["updated_at"] = now_ts
    found.setdefault("turns", [])
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("text") or "").strip()
        role = str(turn.get("role") or "").strip().lower()
        if not text or role not in ("user", "assistant"):
            continue
        found["turns"].append(
            {
                "id": str(uuid4()),
                "role": role,
                "text": text,
                "kind": str(turn.get("kind") or "voice").strip() or "voice",
                "timestamp": str(turn.get("timestamp") or now_ts).strip() or now_ts,
            }
        )
    if found.get("turns"):
        first_text = str((found.get("turns") or [{}])[0].get("text") or "").strip()
        found["title"] = first_text[:24] if first_text else "语音通话"
    items = _sort_call_records(items)
    return r2_store.save_miniapp_call_records(items)

def _message_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or "").strip())
        return " ".join(x for x in parts if x).strip()
    return ""


def _mood_keyword_adjustment(text: str) -> tuple[int, list[str]]:
    raw = str(text or "").strip()
    if not raw:
        return 0, []
    negative = {
        "吵架": -12,
        "生气": -10,
        "冷战": -12,
        "委屈": -8,
        "难过": -8,
        "烦": -4,
        "哭": -7,
        "崩溃": -10,
        "失望": -7,
    }
    positive = {
        "爱你": 8,
        "想你": 5,
        "抱抱": 6,
        "晚安": 3,
        "开心": 6,
        "高兴": 5,
        "谢谢": 2,
        "散步": 3,
        "吃饭": 2,
        "陪你": 5,
    }
    score = 0
    hits: list[str] = []
    for word, delta in negative.items():
        if word in raw:
            score += delta
            hits.append(word)
    for word, delta in positive.items():
        if word in raw:
            score += delta
            hits.append(word)
    return max(-22, min(18, score)), hits[:6]


def _generate_mood_meter(today: str) -> dict:
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    window_id = f"tg_{uid}" if uid > 0 else ""
    rounds = r2_store.get_conversation_rounds(window_id, last_n=24) if window_id else []
    total_recent = len(rounds or [])
    today_count = 0
    latest_dt = None
    today_text_parts: list[str] = []
    for r in rounds or []:
        dt = _parse_beijing_dt(r.get("timestamp"))
        if not dt:
            continue
        if dt.strftime("%Y-%m-%d") == today:
            today_count += 1
            for msg in (r.get("messages") or []):
                if not isinstance(msg, dict):
                    continue
                text = _message_text(msg.get("content"))
                if text:
                    today_text_parts.append(text)
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt

    recency_bonus = 0
    if latest_dt is not None:
        age_hours = max(0.0, (datetime.now(latest_dt.tzinfo) - latest_dt).total_seconds() / 3600.0)
        if age_hours <= 6:
            recency_bonus = 8
        elif age_hours <= 24:
            recency_bonus = 5
        elif age_hours <= 48:
            recency_bonus = 2
        else:
            recency_bonus = -2

    activity_bonus = min(18, today_count * 4) + min(10, max(0, total_recent - 4))
    keyword_bonus, keyword_hits = _mood_keyword_adjustment(" ".join(today_text_parts))
    day_wave = _mood_day_wave(f"{window_id}:{today}")
    score = max(35, min(95, 48 + activity_bonus + recency_bonus + keyword_bonus + day_wave))
    return {
        "date": today,
        "score": score,
        "today_rounds": today_count,
        "recent_rounds": total_recent,
        "keyword_hits": keyword_hits,
        "updated_at": now_beijing_iso(),
    }


def _latest_user_text_from_rounds(rounds: list[dict]) -> str:
    for r in reversed(rounds or []):
        for msg in reversed(r.get("messages") or []):
            if not isinstance(msg, dict):
                continue
            if str(msg.get("role") or "").strip().lower() != "user":
                continue
            text = _message_text(msg.get("content"))
            if text:
                return text
    return ""


def _extract_dynamic_memory_lines(system_text: str) -> list[str]:
    raw = str(system_text or "")
    start = raw.find("【动态记忆】")
    end = raw.find("【以上为动态记忆】")
    if start < 0 or end <= start:
        return []
    chunk = raw[start + len("【动态记忆】"):end].strip()
    return [line.strip() for line in chunk.splitlines() if line.strip()]


def _build_live_dynamic_recall_preview(window_id: str) -> dict | None:
    wid = str(window_id or "").strip()
    if not wid:
        return None
    rounds = r2_store.get_conversation_rounds(wid, last_n=6) or []
    query = _latest_user_text_from_rounds(rounds)
    if not query:
        return None
    try:
        from pipeline.pipeline import step_inject_dynamic_memory

        body = {
            "messages": [
                {"role": "system", "content": "debug"},
                {"role": "user", "content": query},
            ]
        }
        out = step_inject_dynamic_memory(body, wid)
        messages = out.get("messages") or []
        system_text = ""
        for msg in messages:
            if str(msg.get("role") or "").strip().lower() == "system":
                system_text = str(msg.get("content") or "")
                break
        lines = _extract_dynamic_memory_lines(system_text)
        refreshed = r2_store.get_dynamic_recall_debug_events(limit=1) or []
        if refreshed:
            return refreshed[0]
        return {
            "timestamp": now_beijing_iso(),
            "window_id": wid,
            "query": query,
            "keywords": [],
            "keyword_debug": [],
            "retrieval_query": "",
            "source": "live_preview",
            "recalled_lines": lines,
            "recalled_count": len(lines),
            "reason": "live_preview_fallback",
        }
    except Exception as e:
        return {
            "timestamp": now_beijing_iso(),
            "window_id": wid,
            "query": query,
            "keywords": [],
            "keyword_debug": [],
            "retrieval_query": "",
            "source": "live_preview",
            "recalled_lines": [],
            "recalled_count": 0,
            "reason": "live_preview_error",
            "vector_error": str(e),
        }


@bp.before_request
def _miniapp_auth():
    # 双保险：先 IP，再 Telegram initData（更快拒绝无效来源）
    if (
        request.path.rstrip("/").endswith("/panel-auth/meta")
        or request.path.rstrip("/").endswith("/panel-auth/check-password")
        or request.path.rstrip("/").endswith("/panel-auth/verify")
        or request.path.rstrip("/").endswith("/client-error")
        or request.path.rstrip("/").endswith("/tts-preview")
        or request.path.rstrip("/").endswith("/stickers/tags-public")
        or request.path.rstrip("/").endswith("/stickers/resolve")
        or request.path.rstrip("/").endswith("/stickers/raw-public")
        or request.path.rstrip("/").endswith("/device-screenshots/raw-public")
    ):
        enforce_ip_allowlist()
        return None
    enforce_ip_allowlist()
    panel_block = enforce_panel_token()
    if panel_block is not None:
        return panel_block
    if request.environ.get("miniapp_panel_payload"):
        return None
    enforce_telegram_initdata()


@bp.route("/chat-window", methods=["GET"])
def miniapp_chat_window():
    return jsonify({"ok": True, "window_id": _resolve_primary_chat_window_id()})


@bp.route("/co-read/session", methods=["POST"])
def miniapp_co_read_session():
    from routes.co_read_api import handle_co_read_session

    return handle_co_read_session()


@bp.route("/co-read/books", methods=["GET", "POST"])
def miniapp_co_read_books():
    from routes.co_read_api import handle_co_read_books

    return handle_co_read_books()


@bp.route("/co-read/uploads", methods=["POST"])
def miniapp_co_read_upload_start():
    from routes.co_read_api import handle_co_read_upload_start

    return handle_co_read_upload_start()


@bp.route("/co-read/uploads/<upload_id>/chunks", methods=["POST"])
def miniapp_co_read_upload_chunk(upload_id: str):
    from routes.co_read_api import handle_co_read_upload_chunk

    return handle_co_read_upload_chunk(upload_id)


@bp.route("/co-read/uploads/<upload_id>/finish", methods=["POST"])
def miniapp_co_read_upload_finish(upload_id: str):
    from routes.co_read_api import handle_co_read_upload_finish

    return handle_co_read_upload_finish(upload_id)


@bp.route("/co-read/books/<book_key>", methods=["GET", "DELETE"])
def miniapp_co_read_book_detail(book_key: str):
    from routes.co_read_api import handle_co_read_book_delete, handle_co_read_book_detail

    if request.method == "DELETE":
        return handle_co_read_book_delete(book_key)
    return handle_co_read_book_detail(book_key)


@bp.route("/co-read/books/<book_key>/sections/<section_id>", methods=["PUT"])
def miniapp_co_read_section_update(book_key: str, section_id: str):
    from routes.co_read_api import handle_co_read_section_update

    return handle_co_read_section_update(book_key, section_id)


@bp.route("/co-read/books/<book_key>/sections/<section_id>/complete", methods=["POST"])
def miniapp_co_read_section_complete(book_key: str, section_id: str):
    from routes.co_read_api import handle_co_read_section_complete

    return handle_co_read_section_complete(book_key, section_id)


@bp.route("/sumitalk-chat", methods=["POST"])
def miniapp_sumitalk_chat_adaptive():
    body = request.get_json(silent=True) or {}
    job_id, event, error_response = _start_sumitalk_chat_job_from_request(body, waitable=True)
    if error_response is not None:
        return error_response
    try:
        wait_ms = int(body.get("wait_ms") or request.args.get("wait_ms") or _SUMITALK_CHAT_DIRECT_WAIT_MS)
    except Exception:
        wait_ms = _SUMITALK_CHAT_DIRECT_WAIT_MS
    wait_s = max(0.0, min(8.0, wait_ms / 1000.0))
    job = _read_sumitalk_chat_job_state(job_id) or {}
    status = str(job.get("status") or "").strip()
    if status == "done":
        return jsonify({
            "ok": True,
            "status": "done",
            "mode": "direct",
            "job_id": job_id,
            "status_code": int(job.get("status_code") or 200),
            "response": job.get("response") or {},
        })
    if status == "error":
        return jsonify({
            "ok": False,
            "status": "error",
            "mode": "direct",
            "job_id": job_id,
            "status_code": int(job.get("status_code") or 500),
            "error": str(job.get("error") or "渡回复失败"),
            "response": job.get("response") or {},
        })
    if event is not None and event.wait(wait_s):
        job = _read_sumitalk_chat_job_state(job_id) or {}
        status = str(job.get("status") or "").strip()
        if status == "done":
            return jsonify({
                "ok": True,
                "status": "done",
                "mode": "direct",
                "job_id": job_id,
                "status_code": int(job.get("status_code") or 200),
                "response": job.get("response") or {},
            })
        if status == "error":
            return jsonify({
                "ok": False,
                "status": "error",
                "mode": "direct",
                "job_id": job_id,
                "status_code": int(job.get("status_code") or 500),
                "error": str(job.get("error") or "渡回复失败"),
                "response": job.get("response") or {},
            })
    return jsonify({"ok": True, "status": "running", "mode": "job", "job_id": job_id}), 202


@bp.route("/sumitalk-chat-jobs", methods=["POST"])
def miniapp_sumitalk_chat_job_create():
    body = request.get_json(silent=True) or {}
    job_id, _event, error_response = _start_sumitalk_chat_job_from_request(body, waitable=False)
    if error_response is not None:
        return error_response
    return jsonify({"ok": True, "job_id": job_id, "status": "running"})


@bp.route("/sumitalk-chat-jobs/<job_id>", methods=["GET"])
def miniapp_sumitalk_chat_job_get(job_id: str):
    job = _read_sumitalk_chat_job_state(job_id)
    if not job:
        return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
    public_job = {k: v for k, v in job.items() if k not in {"created_ts", "updated_ts"}}
    public_job["ok"] = public_job.get("status") != "error"
    return jsonify(public_job)


@bp.route("/wenyou/last-archive", methods=["GET"])
def miniapp_wenyou_last_archive():
    """
    文游：最近一次 /end 后的归档快照（R2 wenyou/last_archive/{user_id}.json）。
    前端可在结局页拉一次展示框架与历史。
    """
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    arch = r2_store.get_wenyou_last_archive(uid)
    return jsonify({"ok": True, "archive": arch})


@bp.route("/wenyou/archives", methods=["GET"])
def miniapp_wenyou_archives():
    """文游：已通关副本历史列表（按 endedAt 倒序）。"""
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    limit = request.args.get("limit", type=int, default=20)
    items = r2_store.list_wenyou_archives(uid, limit=limit)
    return jsonify({"ok": True, "items": items, "count": len(items)})


@bp.route("/wenyou/archive/<game_id>", methods=["GET"])
def miniapp_wenyou_archive_detail(game_id: str):
    """文游：单个已通关副本详情。"""
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    gid = (game_id or "").strip()
    if not gid:
        return jsonify({"ok": False, "error": "game_id 不能为空"}), 400
    data = r2_store.get_wenyou_archive_by_game_id(uid, gid)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "未找到该归档"}), 404
    fw = data.get("framework") if isinstance(data.get("framework"), dict) else {}
    return jsonify(
        {
            "ok": True,
            "archive": {
                "gameId": str(data.get("gameId") or ""),
                "endedAt": str(data.get("endedAt") or ""),
                "framework": {
                    "instance_code": str(fw.get("instance_code") or ""),
                    "instance_name": str(fw.get("instance_name") or ""),
                    "instance_genre": str(fw.get("instance_genre") or ""),
                    "difficulty": str(fw.get("difficulty") or ""),
                    "world": str(fw.get("world") or ""),
                    "conflict": str(fw.get("conflict") or ""),
                    "failure_hint": str(fw.get("failure_hint") or ""),
                    "reward_hint": str(fw.get("reward_hint") or ""),
                },
                "history_count": len(data.get("history") or []) if isinstance(data.get("history"), list) else 0,
            },
        }
    )


@bp.route("/wenyou/status", methods=["GET"])
def miniapp_wenyou_status():
    """文游：进行中状态（系统空间用于开局前提示）。"""
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return jsonify({"ok": True, "active": False, "session": None})
    fw = (session.get("framework") or {}) if isinstance(session.get("framework"), dict) else {}
    return jsonify(
        {
            "ok": True,
            "active": True,
            "session": {
                "gameId": str(session.get("gameId") or ""),
                "startedAt": str(session.get("startedAt") or ""),
                "instance_code": str(fw.get("instance_code") or ""),
                "instance_name": str(fw.get("instance_name") or ""),
                "instance_genre": str(fw.get("instance_genre") or ""),
                "difficulty": str(fw.get("difficulty") or ""),
            },
        }
    )


@bp.route("/wenyou/story", methods=["POST"])
def miniapp_wenyou_story():
    """文游开局：系统空间可选随机或自定义长描述（keywords）。"""
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode") or "random").strip().lower()
    keywords = str(data.get("keywords") or "").strip()
    if mode not in ("random", "custom"):
        return jsonify({"ok": False, "error": "mode 须为 random 或 custom"}), 400
    if mode == "custom" and not keywords:
        return jsonify({"ok": False, "error": "自定义任务请输入描述"}), 400
    from services.wenyou_service import cmd_story

    text = cmd_story(uid, keywords if mode == "custom" else None)
    need_confirm = ("若确定要开新局" in (text or "")) and ("再发一次" in (text or ""))
    return jsonify({"ok": True, "text": text, "need_confirm_new_game": bool(need_confirm)})


@bp.route("/status", methods=["GET"])
def miniapp_status():
    """概览页用：复用 admin/status 逻辑（但走 miniapp 的鉴权）。"""
    out = {}
    # 总结记忆
    try:
        s = r2_store.get_summary("")
        out["summary"] = {
            "ok": True,
            "has_summary": bool(s and s.strip()),
            "length": len((s or "").strip()),
        }
    except Exception as e:
        out["summary"] = {"ok": False, "error": str(e)}

    # R2（用总结读作为连通性检测）
    try:
        r2_store.get_summary("")
        out["r2"] = {"ok": True, "message": "可读"}
    except Exception as e:
        out["r2"] = {"ok": False, "error": str(e)}

    # 动态层
    try:
        lst = r2_store.get_dynamic_memory_list() or []
        out["dynamic_memory"] = {"ok": True, "count": len(lst)}
    except Exception as e:
        out["dynamic_memory"] = {"ok": False, "error": str(e)}

    # 核心缓存待审
    try:
        pending = r2_store.get_core_cache_pending() or []
        out["core_cache"] = {"ok": True, "pending_count": len(pending)}
    except Exception as e:
        out["core_cache"] = {"ok": False, "error": str(e)}

    # 小本本
    try:
        entries = r2_store.get_notebook_entries() or []
        out["notebook"] = {"ok": True, "count": len(entries)}
    except Exception as e:
        out["notebook"] = {"ok": False, "error": str(e)}

    # 白/黑名单/最近窗口
    try:
        out["whitelist"] = {"ok": True, "count": len(whitelist_store.list_whitelist())}
    except Exception as e:
        out["whitelist"] = {"ok": False, "error": str(e)}
    try:
        out["blacklist"] = {"ok": True, "count": len(blacklist_store.list_blacklist())}
    except Exception as e:
        out["blacklist"] = {"ok": False, "error": str(e)}
    try:
        out["recent_windows"] = {"ok": True, "count": len(whitelist_store.list_recent_windows(limit=500))}
    except Exception as e:
        out["recent_windows"] = {"ok": False, "error": str(e)}

    return jsonify(out)


@bp.route("/daily-whisper", methods=["GET"])
def miniapp_daily_whisper():
    today = today_beijing()
    force_refresh = request.args.get("refresh", type=int, default=0) == 1
    data = r2_store.get_miniapp_daily_whisper() or {}
    cached_text = str(data.get("text") or "").strip()
    cached_date = str(data.get("date") or "").strip()
    if (not force_refresh) and cached_date == today and cached_text:
        return jsonify({"ok": True, "date": today, "text": cached_text, "cached": True})

    default_text = "今天也想抱抱你，慢慢来，我们一起把今天过好。"
    generated_text = ""
    try:
        from services.deepseek_summary import fetch_daily_whisper_from_summary

        generated_text = (
            fetch_daily_whisper_from_summary(
                r2_store.get_summary("") or "",
                r2_store.get_latest_4_rounds_global() or [],
            )
        ).strip()
    except Exception:
        generated_text = ""
    if generated_text:
        payload = {"date": today, "text": generated_text, "updatedAt": now_beijing_iso()}
        r2_store.save_miniapp_daily_whisper(payload)
        return jsonify({"ok": True, "date": today, "text": generated_text, "cached": False})
    if cached_text and not force_refresh:
        return jsonify({
            "ok": True,
            "date": cached_date or today,
            "text": cached_text,
            "cached": True,
            "stale": cached_date != today,
        })
    if cached_text:
        return jsonify({
            "ok": False,
            "date": cached_date or today,
            "text": cached_text,
            "cached": True,
            "error": "Today note 刷新失败，已保留原文",
        })
    text = default_text
    payload = {"date": today, "text": text, "updatedAt": now_beijing_iso()}
    r2_store.save_miniapp_daily_whisper(payload)
    return jsonify({"ok": True, "date": today, "text": text, "cached": False, "fallback": True})


@bp.route("/cyber-tree", methods=["GET"])
def miniapp_cyber_tree():
    today = today_beijing()
    meta = r2_store.get_cyber_tree_meta() or {}
    start_date = str(meta.get("startDate") or "").strip() or _default_cyber_tree_start_date(today)
    if not (meta.get("startDate")):
        r2_store.save_cyber_tree_meta({"startDate": start_date, "createdAt": now_beijing_iso()})

    try:
        from datetime import datetime as _dt

        d0 = _dt.strptime(start_date, "%Y-%m-%d").date()
        d1 = _dt.strptime(today, "%Y-%m-%d").date()
        days = max(1, (d1 - d0).days + 1)
    except Exception:
        days = 1
    tg_uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    rounds = 0
    if tg_uid > 0:
        rounds = r2_store.get_window_conversation_rounds(f"tg_{tg_uid}")
    if rounds <= 0:
        rounds = r2_store.get_total_conversation_rounds()
    growth = float(days) * (1.0 + math.log(max(1, rounds)) / 10.0)
    # 阶段阈值调高：按当前纪念日起点，默认应先处于树苗期。
    if growth < 50:
        stage = "seedling"
    elif growth < 140:
        stage = "young"
    elif growth < 320:
        stage = "big"
    else:
        stage = "lush"
    month = int(today.split("-", 2)[1]) if "-" in today else 1
    season = _season_label(month)
    if season == "winter":
        weather_fx = "snowy"
    elif season == "summer":
        weather_fx = "sunny"
    else:
        weather_fx = "rainy"
    milestones = {
        "days": [30, 100, 365],
        "rounds": [300, 1000, 3000],
        "reachedDays": [x for x in (30, 100, 365) if days >= x],
        "reachedRounds": [x for x in (300, 1000, 3000) if rounds >= x],
    }
    mood = r2_store.get_miniapp_mood_meter() or _generate_mood_meter(today)
    if not (r2_store.get_miniapp_mood_meter() or {}).get("date"):
        r2_store.save_miniapp_mood_meter(mood)
    return jsonify(
        {
            "ok": True,
            "startDate": start_date,
            "today": today,
            "daysTogether": days,
            "totalRounds": rounds,
            "growth": round(growth, 2),
            "stage": stage,
            "season": season,
            "weatherFx": weather_fx,
            "milestones": milestones,
            "mood": mood,
        }
    )


@bp.route("/daily-report", methods=["GET"])
def miniapp_daily_report():
    today = today_beijing()
    data = r2_store.get_miniapp_daily_report() or {}
    if str(data.get("report_date") or "") != today:
        data = _generate_daily_report(today)
        r2_store.save_miniapp_daily_report(data)
    return jsonify({"ok": True, "report": data})


@bp.route("/daily-report/refresh", methods=["POST"])
def miniapp_daily_report_refresh():
    today = today_beijing()
    data = _generate_daily_report(today)
    ok = r2_store.save_miniapp_daily_report(data)
    return jsonify({"ok": bool(ok), "report": data})


@bp.route("/du-day", methods=["GET"])
def miniapp_du_day():
    today = today_beijing()
    items = _build_du_day_events(today)
    return jsonify({"ok": True, "date": today, "items": items, "count": len(items)})


# 兼容旧前端路径：与 daily-report 行为一致
@bp.route("/weekly-report", methods=["GET"])
def miniapp_weekly_report():
    return miniapp_daily_report()


@bp.route("/weekly-report/refresh", methods=["POST"])
def miniapp_weekly_report_refresh():
    return miniapp_daily_report_refresh()


@bp.route("/mood-meter", methods=["GET"])
def miniapp_mood_meter():
    today = today_beijing()
    data = _generate_mood_meter(today)
    r2_store.save_miniapp_mood_meter(data)
    return jsonify({"ok": True, "mood": data})


@bp.route("/mood-meter/refresh", methods=["POST"])
def miniapp_mood_meter_refresh():
    today = today_beijing()
    data = _generate_mood_meter(today)
    ok = r2_store.save_miniapp_mood_meter(data)
    return jsonify({"ok": bool(ok), "mood": data})


@bp.route("/cyber-tree/start-date", methods=["PUT"])
def miniapp_set_cyber_tree_start_date():
    data = request.get_json(silent=True) or {}
    start_date = str(data.get("startDate") or "").strip()
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except Exception:
        return jsonify({"ok": False, "error": "startDate 格式需为 YYYY-MM-DD"}), 400
    meta = r2_store.get_cyber_tree_meta() or {}
    meta["startDate"] = start_date
    meta["updatedAt"] = now_beijing_iso()
    ok = r2_store.save_cyber_tree_meta(meta)
    return jsonify({"ok": bool(ok), "startDate": start_date})


@bp.route("/windows", methods=["GET"])
def miniapp_windows():
    limit = request.args.get("limit", type=int, default=50)
    if limit > 200:
        limit = 200
    items = whitelist_store.list_recent_windows(limit=limit)
    whitelist = set(whitelist_store.list_whitelist())
    blacklist = set(blacklist_store.list_blacklist())
    for w in items:
        w["whitelisted"] = w.get("id") in whitelist
        w["blacklisted"] = w.get("id") in blacklist
    return jsonify({"windows": items})


@bp.route("/windows/<window_id>/rounds", methods=["GET"])
def miniapp_rounds(window_id: str):
    preview_chars = request.args.get("preview_chars", type=int, default=60)
    if preview_chars < 0:
        preview_chars = 0
    if preview_chars > 200:
        preview_chars = 200
    rounds = r2_store.list_conversation_rounds_preview(window_id or "", preview_chars=preview_chars)
    return jsonify({"window_id": window_id or "", "rounds": rounds, "count": len(rounds)})


@bp.route("/windows/<window_id>/conversation", methods=["GET"])
def miniapp_conversation(window_id: str):
    last_n = request.args.get("last_n", type=int, default=20)
    if last_n < 1:
        last_n = 1
    if last_n > 200:
        last_n = 200
    rounds = r2_store.get_conversation_rounds(window_id or "", last_n=last_n)
    return jsonify({"window_id": window_id or "", "rounds": rounds, "count": len(rounds)})


@bp.route("/windows/<window_id>/rounds/<int:round_index>", methods=["GET"])
def miniapp_round_detail(window_id: str, round_index: int):
    if round_index < 1:
        return jsonify({"error": "round_index 无效"}), 400
    r = r2_store.get_conversation_round_by_index(window_id or "", round_index)
    if not r:
        return jsonify({"ok": False, "error": "未找到该轮"}), 404
    return jsonify({"ok": True, "window_id": window_id or "", "round": r})


@bp.route("/windows/<window_id>/rounds/<int:round_index>", methods=["DELETE"])
def miniapp_delete_round(window_id: str, round_index: int):
    if round_index < 1:
        return jsonify({"error": "round_index 无效"}), 400
    ok = r2_store.delete_conversation_round(window_id or "", round_index)
    return jsonify({"ok": ok, "window_id": window_id or "", "round_index": round_index})


def _normalize_cache_debug_items(value) -> list[dict]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    elif isinstance(value, dict):
        return [value]
    return []


@bp.route("/reasoning/latest", methods=["GET"])
def miniapp_reasoning_latest():
    """
    返回最新思维链（默认 10 条）：
    - 优先最近窗口里最新的 tg_*
    - 回退最近窗口第一条
    - 返回 reasoning + 工具调用/结果（用于 MiniApp COT 日志展示）
    """
    limit = request.args.get("limit", type=int, default=10)
    if limit < 1:
        limit = 1
    if limit > 30:
        limit = 30

    recent = whitelist_store.list_recent_windows(limit=200) or []
    targets: list[str] = []
    for w in recent:
        wid = (w.get("id") or "").strip()
        if not wid:
            continue
        if wid.startswith("tg_") or wid.startswith("wechat_") or wid.startswith("wx_"):
            if wid not in targets:
                targets.append(wid)
    if not targets and recent:
        wid0 = (recent[0].get("id") or "").strip()
        if wid0:
            targets = [wid0]

    primary_wid = _resolve_primary_chat_window_id()
    if primary_wid and primary_wid not in targets:
        if primary_wid.startswith("tg_") or primary_wid.startswith("wechat_") or primary_wid.startswith("wx_"):
            targets.insert(0, primary_wid)

    if not targets:
        return jsonify({"ok": True, "window_id": "", "items": [], "count": 0})

    out = []
    for target in targets:
        rounds = r2_store.get_conversation_rounds(target, last_n=160) or []
        for r in reversed(rounds):
            idx = int(r.get("index") or 0)
            ts = (r.get("timestamp") or "").strip()
            msgs = r.get("messages") or []
            reasoning_text = ""
            cache_debug_items: list[dict] = []
            tool_calls_out = []
            tool_results_map: dict[str, str] = {}
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                role = (m.get("role") or "").strip().lower()
                if role != "tool":
                    continue
                tid = (m.get("tool_call_id") or "").strip()
                if not tid:
                    continue
                content = m.get("content")
                if content is None:
                    val = ""
                elif isinstance(content, str):
                    val = content
                else:
                    try:
                        val = json.dumps(content, ensure_ascii=False)
                    except Exception:
                        val = str(content)
                tool_results_map[tid] = val
            for m in reversed(msgs):
                role = (m.get("role") or "").strip().lower() if isinstance(m, dict) else ""
                if role != "assistant":
                    continue
                if not isinstance(m, dict):
                    continue
                if not tool_calls_out:
                    tcs = m.get("tool_calls") or []
                    if isinstance(tcs, list):
                        for tc in tcs:
                            if not isinstance(tc, dict):
                                continue
                            tid = (tc.get("id") or "").strip()
                            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                            name = (fn.get("name") or "").strip()
                            args = fn.get("arguments")
                            if args is None:
                                args_text = ""
                            elif isinstance(args, str):
                                args_text = args
                            else:
                                try:
                                    args_text = json.dumps(args, ensure_ascii=False)
                                except Exception:
                                    args_text = str(args)
                            tool_calls_out.append(
                                {
                                    "id": tid,
                                    "name": name,
                                    "arguments": args_text,
                                    "result": tool_results_map.get(tid, str(tc.get("result") or "")),
                                }
                            )
                if not reasoning_text:
                    val = (m.get("reasoning") or m.get("reasoning_content") or m.get("thinking") or "").strip()
                    if val:
                        reasoning_text = val
                    elif m.get("reasoning_omitted") or m.get("reasoning_details"):
                        reasoning_text = "（模型已进行 adaptive thinking，但当前上游未返回可展示的思维链正文）"
                if not cache_debug_items:
                    cache_debug_items = _normalize_cache_debug_items(m.get("cache_debug"))
                if (reasoning_text or cache_debug_items) and tool_calls_out:
                    break
            if reasoning_text or cache_debug_items or tool_calls_out:
                out.append(
                    {
                        "window_id": target,
                        "index": idx,
                        "timestamp": ts,
                        "reasoning": reasoning_text,
                        "cache_debug": cache_debug_items,
                        "tool_calls": tool_calls_out,
                    }
                )

    out.sort(key=lambda x: (_parse_beijing_dt(x.get("timestamp") or "") is not None, _parse_beijing_dt(x.get("timestamp") or "")), reverse=True)
    out = out[:limit]
    resp = jsonify({"ok": True, "window_id": targets[0] if targets else "", "window_ids": targets, "items": out, "count": len(out)})
    # 思维链刷新希望“按一下就见效”，这里显式禁缓存，避免移动端/代理命中旧响应。
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp.route("/schedule/items", methods=["GET"])
def miniapp_schedule_items():
    items = r2_store.get_schedule_items() or []
    enabled_count = len([x for x in items if bool(x.get("enabled", True))])
    return jsonify({"ok": True, "items": items, "count": len(items), "enabled_count": enabled_count})


@bp.route("/schedule/items", methods=["POST"])
def miniapp_create_schedule_item():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    datetime_str = (data.get("datetime") or "").strip()
    repeat = (data.get("repeat") or "once").strip().lower()
    note = (data.get("note") or "").strip()
    enabled = bool(data.get("enabled", True))
    weekly_weekday = data.get("weekly_weekday", None)
    weekly_weekdays = data.get("weekly_weekdays", None)
    weekly_time = (data.get("weekly_time") or "").strip()
    daily_time = (data.get("daily_time") or "").strip()
    created_by = (data.get("created_by") or "wife").strip().lower()
    if created_by not in ("wife", "du"):
        created_by = "wife"
    target_role = (data.get("target_role") or "wife").strip().lower()
    if target_role not in ("wife", "du"):
        target_role = "wife"

    if not title:
        return jsonify({"ok": False, "error": "title 不能为空"}), 400
    if repeat not in ("once", "daily", "weekly"):
        repeat = "once"
    if repeat == "weekly":
        weekday_list: list[int] = []
        if isinstance(weekly_weekdays, list):
            for x in weekly_weekdays:
                try:
                    w = int(x)
                except Exception:
                    continue
                if 0 <= w <= 6:
                    weekday_list.append(w)
        elif weekly_weekday is not None:
            try:
                w = int(weekly_weekday)
                if 0 <= w <= 6:
                    weekday_list.append(w)
            except Exception:
                pass
        weekday_list = sorted(set(weekday_list))
        if not weekday_list:
            return jsonify({"ok": False, "error": "weekly_weekdays 无效"}), 400
        try:
            hh, mm = (weekly_time.split(":", 1) + ["0"])[:2]
            hhi = int(hh)
            mmi = int(mm)
            if hhi < 0 or hhi > 23 or mmi < 0 or mmi > 59:
                raise ValueError("invalid")
        except Exception:
            return jsonify({"ok": False, "error": "weekly_time 格式无效"}), 400
        created_items = []
        for w in weekday_list:
            item = r2_store.create_schedule_item(
                title=title,
                datetime_str="",
                repeat=repeat,
                note=note,
                enabled=enabled,
                weekly_weekday=w,
                weekly_time=weekly_time,
                daily_time=daily_time,
                created_by=created_by,
                target_role=target_role,
            )
            if item:
                created_items.append(item)
        if not created_items:
            return jsonify({"ok": False, "error": "创建失败"}), 500
        _notify_schedule_runtime_changed()
        return jsonify({"ok": True, "items": created_items, "count": len(created_items)})
    elif repeat == "daily":
        try:
            hh, mm = (daily_time.split(":", 1) + ["0"])[:2]
            hhi = int(hh)
            mmi = int(mm)
            if hhi < 0 or hhi > 23 or mmi < 0 or mmi > 59:
                raise ValueError("invalid")
        except Exception:
            return jsonify({"ok": False, "error": "daily_time 格式无效"}), 400
    else:
        if not datetime_str:
            return jsonify({"ok": False, "error": "datetime 不能为空"}), 400
        # 允许 ISO（2026-03-20T09:30[:ss][+08:00]）及 datetime-local（2026-03-20T09:30）
        try:
            datetime.fromisoformat(datetime_str)
        except Exception:
            return jsonify({"ok": False, "error": "datetime 格式无效"}), 400

    item = r2_store.create_schedule_item(
        title=title,
        datetime_str=datetime_str,
        repeat=repeat,
        note=note,
        enabled=enabled,
        weekly_weekday=weekly_weekday,
        weekly_time=weekly_time,
        daily_time=daily_time,
        created_by=created_by,
        target_role=target_role,
    )
    if not item:
        return jsonify({"ok": False, "error": "创建失败"}), 500
    _notify_schedule_runtime_changed()
    return jsonify({"ok": True, "item": item})


@bp.route("/schedule/items/<item_id>/disable", methods=["PUT"])
def miniapp_disable_schedule_item(item_id: str):
    iid = (item_id or "").strip()
    if not iid:
        return jsonify({"ok": False, "error": "缺少 item_id"}), 400
    ok = r2_store.disable_schedule_item(iid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到条目或已是禁用状态"}), 404
    _notify_schedule_runtime_changed()
    return jsonify({"ok": True, "id": iid, "action": "disable_future"})


@bp.route("/schedule/items/<item_id>/enable", methods=["PUT"])
def miniapp_enable_schedule_item(item_id: str):
    iid = (item_id or "").strip()
    if not iid:
        return jsonify({"ok": False, "error": "缺少 item_id"}), 400
    ok = r2_store.enable_schedule_item(iid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到条目或已是启用状态"}), 404
    _notify_schedule_runtime_changed()
    return jsonify({"ok": True, "id": iid, "action": "enable"})


@bp.route("/schedule/items/<item_id>", methods=["DELETE"])
def miniapp_delete_schedule_item(item_id: str):
    iid = (item_id or "").strip()
    if not iid:
        return jsonify({"ok": False, "error": "缺少 item_id"}), 400
    ok = r2_store.delete_schedule_item(iid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到该条目"}), 404
    _notify_schedule_runtime_changed()
    return jsonify({"ok": True, "id": iid, "action": "delete"})


@bp.route("/dynamic-memory", methods=["GET"])
def miniapp_dynamic_memory():
    try:
        lst = r2_store.get_dynamic_memory_list() or []
        return jsonify({"ok": True, "count": len(lst), "memories": lst})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "memories": []}), 500


@bp.route("/memory-debug", methods=["GET"])
def miniapp_memory_debug():
    """
    记忆调试视图：
    - 当前窗口记忆总结（summary）
    - 最近动态记忆召回明细（每次注入时记录）
    """
    try:
        limit = request.args.get("limit", type=int, default=10)
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100
        target = ""
        recent = whitelist_store.list_recent_windows(limit=200) or []
        for w in recent:
            wid = (w.get("id") or "").strip()
            if wid.startswith("tg_"):
                target = wid
                break
        if not target and recent:
            target = (recent[0].get("id") or "").strip()
        summary = (r2_store.get_summary(target) or "").strip()
        all_events = r2_store.get_dynamic_recall_debug_events(limit=limit * 3) or []
        if not all_events:
            live_preview = _build_live_dynamic_recall_preview(target)
            if live_preview:
                all_events = [live_preview]
        scope = str(request.args.get("scope") or "all").strip().lower()
        if scope not in ("all", "target"):
            scope = "all"
        if scope == "target" and target:
            events = [e for e in all_events if str((e or {}).get("window_id") or "").strip() in (target, "__default__", "__search_memory__")]
        else:
            events = all_events
        recall_events = [e for e in events if str((e or {}).get("source") or "").strip() != "search_memory"]
        search_events = [e for e in events if str((e or {}).get("source") or "").strip() == "search_memory"]
        maintenance_report = r2_store.get_dynamic_memory_maintenance_report() or {}
        dynamic_stats = {"maintenance_report": maintenance_report}
        try:
            from memory_vector.config import (
                VECTOR_MIN_SIM,
                VECTOR_TOPK,
                VECTOR_TOPN,
                CF_ACCOUNT_ID,
                CF_API_TOKEN,
                CF_EMBEDDING_MODEL,
                EMBEDDING_MODEL,
                EMBED_REQUEST_TIMEOUT_SECONDS,
                EMBED_MAX_RETRIES,
                EMBED_RETRY_BACKOFF_SECONDS,
                current_embedding_model,
                current_embedding_backend,
            )
            from memory_vector.vector_index_store import list_existing_tags
            mems = r2_store.get_dynamic_memory_list() or []
            mem_tags = sorted({str((m or {}).get("tag") or "").strip() for m in mems if str((m or {}).get("tag") or "").strip()})
            label_complete_count = 0
            label_missing_count = 0
            recent_vector_error = ""
            for m in mems:
                emotion_label = str((m or {}).get("emotion_label") or "").strip()
                scene_type = str((m or {}).get("scene_type") or "").strip()
                target_type = str((m or {}).get("target_type") or "").strip()
                if emotion_label and scene_type and target_type:
                    label_complete_count += 1
                else:
                    label_missing_count += 1
            for e in all_events:
                msg = str((e or {}).get("vector_error") or "").strip()
                if msg:
                    recent_vector_error = msg
                    break
            failed_ids_count = 0
            failed_ids_preview: list[str] = []
            try:
                failed_path = Path(__file__).resolve().parent.parent / "data" / "rebuild_index_failed_ids.json"
                if failed_path.exists():
                    failed_payload = json.loads(failed_path.read_text(encoding="utf-8"))
                    failed_ids = failed_payload.get("failed_ids") if isinstance(failed_payload, dict) else []
                    if isinstance(failed_ids, list):
                        failed_ids_preview = [str(x).strip() for x in failed_ids if str(x).strip()][:10]
                        failed_ids_count = len([x for x in failed_ids if str(x).strip()])
            except Exception:
                failed_ids_count = 0
                failed_ids_preview = []
            dynamic_stats.update({
                "memory_count": len(mems),
                "memory_tags": mem_tags[:30],
                "label_complete_count": label_complete_count,
                "label_missing_count": label_missing_count,
                "index_tags": (list_existing_tags() or [])[:50],
                "vector_min_sim": float(VECTOR_MIN_SIM),
                "vector_topk": int(VECTOR_TOPK),
                "vector_topn": int(VECTOR_TOPN),
                "embedding_backend": current_embedding_backend(),
                "embedding_model": current_embedding_model() or (CF_EMBEDDING_MODEL if (CF_ACCOUNT_ID and CF_API_TOKEN) else EMBEDDING_MODEL),
                "embed_timeout_seconds": int(EMBED_REQUEST_TIMEOUT_SECONDS),
                "embed_max_retries": int(EMBED_MAX_RETRIES),
                "embed_retry_backoff_seconds": float(EMBED_RETRY_BACKOFF_SECONDS),
                "recent_vector_error": recent_vector_error,
                "failed_ids_count": failed_ids_count,
                "failed_ids_preview": failed_ids_preview,
            })
        except Exception:
            dynamic_stats = {"maintenance_report": maintenance_report}
        return jsonify(
            {
                "ok": True,
                "window_id": target,
                "scope": scope,
                "summary": summary,
                "summary_exists": bool(summary),
                "recalls": recall_events[:limit],
                "count": len(recall_events[:limit]),
                "total_count": len(recall_events),
                "search_memory_events": search_events[:limit],
                "search_count": len(search_events[:limit]),
                "search_total_count": len(search_events),
                "dynamic_stats": dynamic_stats,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "summary": "", "recalls": [], "count": 0}), 500


@bp.route("/memory-maintenance", methods=["POST"])
def miniapp_memory_maintenance():
    """手动触发一次动态记忆离线慢整理。"""
    global _MEMORY_MAINTENANCE_RUNNING
    global _MEMORY_MAINTENANCE_LAST_STARTED
    global _MEMORY_MAINTENANCE_LAST_FINISHED
    global _MEMORY_MAINTENANCE_LAST_ERROR
    try:
        body = request.get_json(silent=True) or {}
        dry_run = bool(body.get("dry_run"))
        limit_candidates = int(body.get("limit_candidates") or 20)
        if limit_candidates < 1:
            limit_candidates = 1
        if limit_candidates > 50:
            limit_candidates = 50

        with _MEMORY_MAINTENANCE_LOCK:
            if _MEMORY_MAINTENANCE_RUNNING:
                return jsonify(
                    {
                        "ok": True,
                        "started": False,
                        "running": True,
                        "last_started": _MEMORY_MAINTENANCE_LAST_STARTED,
                        "last_finished": _MEMORY_MAINTENANCE_LAST_FINISHED,
                        "last_error": _MEMORY_MAINTENANCE_LAST_ERROR,
                    }
                )
            _MEMORY_MAINTENANCE_RUNNING = True
            _MEMORY_MAINTENANCE_LAST_STARTED = now_beijing_iso()
            _MEMORY_MAINTENANCE_LAST_ERROR = ""

        def _run_job():
            global _MEMORY_MAINTENANCE_RUNNING
            global _MEMORY_MAINTENANCE_LAST_FINISHED
            global _MEMORY_MAINTENANCE_LAST_ERROR
            try:
                from services.memory_maintenance import run_memory_maintenance

                run_memory_maintenance(limit_candidates=limit_candidates, dry_run=dry_run)
            except Exception as e:
                _MEMORY_MAINTENANCE_LAST_ERROR = str(e)
                logger.warning("miniapp memory maintenance background job failed: %s", e, exc_info=True)
            finally:
                _MEMORY_MAINTENANCE_LAST_FINISHED = now_beijing_iso()
                with _MEMORY_MAINTENANCE_LOCK:
                    _MEMORY_MAINTENANCE_RUNNING = False

        th = threading.Thread(target=_run_job, daemon=True)
        th.start()
        return jsonify(
            {
                "ok": True,
                "started": True,
                "running": True,
                "last_started": _MEMORY_MAINTENANCE_LAST_STARTED,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/core_cache", methods=["GET"])
def miniapp_core_cache():
    pending = r2_store.get_core_cache_pending() or []
    return jsonify({"pending": pending, "count": len(pending)})


@bp.route("/core_cache/<entry_id>", methods=["DELETE"])
def miniapp_delete_core_cache(entry_id: str):
    if not entry_id:
        return jsonify({"error": "缺少 entry_id"}), 400
    ok = r2_store.delete_core_cache_by_id(entry_id)
    return jsonify({"ok": ok, "id": entry_id})


@bp.route("/notebook", methods=["GET"])
def miniapp_notebook_list():
    entries = r2_store.get_notebook_entries() or []
    return jsonify({"entries": entries, "count": len(entries)})


@bp.route("/notebook", methods=["POST"])
def miniapp_notebook_add():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "缺少 content"}), 400
    ok = r2_store.notebook_append_entry(content)
    return jsonify({"ok": ok})


@bp.route("/notebook/<ts>", methods=["DELETE"])
def miniapp_notebook_delete(ts: str):
    ts = (ts or "").strip()
    if not ts:
        return jsonify({"error": "缺少 timestamp"}), 400
    ok = r2_store.notebook_delete_entry_by_timestamp(ts)
    return jsonify({"ok": ok, "timestamp": ts})


@bp.route("/du-notebook", methods=["GET"])
def miniapp_du_notebook_list():
    items = r2_store.get_du_notebook_entries() or []
    return jsonify({"ok": True, "items": items, "count": len(items)})


@bp.route("/du-notebook", methods=["POST"])
def miniapp_du_notebook_add():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    entry = r2_store.add_du_notebook_entry(content)
    if not entry:
        return jsonify({"ok": False, "error": "新增失败"}), 500
    return jsonify({"ok": True, "entry": entry})


@bp.route("/du-notebook/<entry_id>", methods=["PUT"])
def miniapp_du_notebook_update(entry_id: str):
    eid = (entry_id or "").strip()
    if not eid:
        return jsonify({"ok": False, "error": "缺少 entry_id"}), 400
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    ok = r2_store.update_du_notebook_entry(eid, content)
    if not ok:
        return jsonify({"ok": False, "error": "未找到条目或更新失败"}), 404
    return jsonify({"ok": True, "id": eid})


@bp.route("/du-notebook/<entry_id>", methods=["DELETE"])
def miniapp_du_notebook_delete(entry_id: str):
    eid = (entry_id or "").strip()
    if not eid:
        return jsonify({"ok": False, "error": "缺少 entry_id"}), 400
    ok = r2_store.delete_du_notebook_entry(eid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到该条目"}), 404
    return jsonify({"ok": True, "id": eid})


@bp.route("/stay-with-du", methods=["GET"])
def miniapp_stay_with_du_get():
    data = r2_store.get_stay_with_du_data()
    return jsonify({"ok": True, "data": data})


@bp.route("/stay-with-du", methods=["PUT", "POST"])
def miniapp_stay_with_du_save():
    body = request.get_json(silent=True) or {}
    raw = body.get("data") if isinstance(body.get("data"), dict) else body
    data = r2_store.normalize_stay_with_du_data(raw)
    ok = r2_store.save_stay_with_du_data(data)
    if not ok:
        return jsonify({"ok": False, "error": "保存失败"}), 500
    return jsonify({"ok": True, "data": r2_store.get_stay_with_du_data()})


@bp.route("/core-prompt", methods=["GET"])
def miniapp_get_core_prompt():
    """
    读取“核心 Prompt（3.16）”：
    - 若 R2 已有自定义内容，返回该内容
    - 否则回退读取本地 prompts/du_core_prompt.txt（只读展示）
    """
    cfg = r2_store.get_core_prompt_config()
    text = r2_store.get_core_prompt_text()
    source = "r2"
    if text is None and cfg is None:
        source = "file"
        try:
            p = Path(__file__).resolve().parent.parent / "prompts" / "du_core_prompt.txt"
            text = p.read_text(encoding="utf-8") if p.exists() else ""
        except Exception:
            text = ""
        cfg = {"active_key": "a", "prompts": {"a": (text or ""), "b": ""}}
    return jsonify(
        {
            "ok": True,
            "source": source,
            "content": (text or ""),
            "active_key": str((cfg or {}).get("active_key") or "a"),
            "prompts": ((cfg or {}).get("prompts") or {"a": (text or ""), "b": ""}),
        }
    )


@bp.route("/portrait-memory", methods=["GET"])
def miniapp_get_portrait_memory():
    xinyue = r2_store.get_xinyue_portrait_candidates() or []
    du = r2_store.get_du_portrait_candidates() or []
    interaction = r2_store.get_interaction_candidates() or []
    return jsonify(
        {
            "ok": True,
            "xinyue_candidates": xinyue,
            "du_candidates": du,
            "interaction_candidates": interaction,
            "counts": {
                "xinyue": len(xinyue),
                "du": len(du),
                "interaction": len(interaction),
            },
        }
    )


@bp.route("/portrait-memory/<bucket>/<entry_id>", methods=["DELETE"])
def miniapp_delete_portrait_memory(bucket: str, entry_id: str):
    b = str(bucket or "").strip().lower()
    eid = str(entry_id or "").strip()
    if b not in ("xinyue", "du", "interaction"):
        return jsonify({"ok": False, "error": "bucket 无效"}), 400
    if not eid:
        return jsonify({"ok": False, "error": "缺少 entry_id"}), 400
    if b == "xinyue":
        ok = r2_store.delete_xinyue_portrait_candidate(eid)
    elif b == "du":
        ok = r2_store.delete_du_portrait_candidate(eid)
    else:
        ok = r2_store.delete_interaction_candidate(eid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到该候选"}), 404
    return jsonify({"ok": True, "bucket": b, "id": eid})


@bp.route("/core-prompt", methods=["PUT"])
def miniapp_put_core_prompt():
    data = request.get_json(silent=True) or {}
    prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else None
    active_key = str(data.get("active_key") or "a").strip() or "a"
    if prompts is not None:
        pa = str(prompts.get("a") or "").strip()
        pb = str(prompts.get("b") or "").strip()
        if not pa and not pb:
            return jsonify({"ok": False, "error": "至少保留一套 prompt"}), 400
        if active_key == "a" and not pa:
            return jsonify({"ok": False, "error": "当前选中的 prompt A 不能为空"}), 400
        if active_key == "b" and not pb:
            return jsonify({"ok": False, "error": "当前选中的 prompt B 不能为空"}), 400
        ok = r2_store.save_core_prompt_config({"active_key": active_key, "prompts": {"a": pa, "b": pb}})
        return jsonify({"ok": ok})

    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    ok = r2_store.save_core_prompt_text(content)
    return jsonify({"ok": ok})


@bp.route("/silence-mode", methods=["GET"])
def miniapp_get_silence_mode():
    state = silence_mode_store.get_state()
    return jsonify({"ok": True, **state})


@bp.route("/silence-mode", methods=["PUT"])
def miniapp_put_silence_mode():
    data = request.get_json(silent=True) or {}
    raw = data.get("enabled")
    if isinstance(raw, str):
        enabled = raw.strip().lower() in ("1", "true", "yes", "on")
    else:
        enabled = bool(raw)
    state = silence_mode_store.set_enabled(enabled, updated_at=now_beijing_iso())
    return jsonify({"ok": True, **state})


@bp.route("/background-config", methods=["GET"])
def miniapp_get_background_config():
    data = r2_store.get_miniapp_bg_config() or {}
    return jsonify(
        {
            "ok": True,
            "config": {
                "preset": (data.get("preset") or "cream"),
                "useImage": bool(data.get("useImage")),
                "imageVersion": int(data.get("imageVersion") or 0),
                "dim": int(data.get("dim") or 20),
            },
        }
    )


@bp.route("/background-config", methods=["PUT"])
def miniapp_put_background_config():
    data = request.get_json(silent=True) or {}
    preset = (data.get("preset") or "cream").strip()
    if preset not in ("cream", "grid", "soft"):
        preset = "cream"
    dim = int(data.get("dim") or 20)
    dim = max(0, min(70, dim))
    use_image = bool(data.get("useImage"))
    image_version = int(data.get("imageVersion") or 0)
    # 防止客户端携带旧 draft 覆盖新图版本号：配置保存时版本号只允许前进不回退。
    current = r2_store.get_miniapp_bg_config() or {}
    current_ver = int(current.get("imageVersion") or 0)
    payload = {
        "preset": preset,
        "useImage": use_image,
        "imageVersion": max(current_ver, max(0, image_version)),
        "dim": dim,
    }
    ok = r2_store.save_miniapp_bg_config(payload)
    return jsonify({"ok": ok, "config": payload})


@bp.route("/background-image", methods=["POST"])
def miniapp_upload_background_image():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "缺少 file"}), 400
    ctype = (f.mimetype or "").strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        return jsonify({"ok": False, "error": "仅支持 jpg/png/webp/gif"}), 400
    content = f.read()
    if not content:
        return jsonify({"ok": False, "error": "文件为空"}), 400
    if len(content) > 8 * 1024 * 1024:
        return jsonify({"ok": False, "error": "图片过大（最大 8MB）"}), 400
    conf = r2_store.get_miniapp_bg_config() or {}
    # 用毫秒时间戳，且保证严格递增，避免同一秒内二次上传命中同一个版本号导致前端继续读旧缓存。
    old_ver = int(conf.get("imageVersion") or 0)
    new_ver = int(time.time() * 1000)
    if new_ver <= old_ver:
        new_ver = old_ver + 1

    # 同时写“最新别名键 + 版本化键”，规避顽固缓存回旧图问题
    ok = r2_store.save_miniapp_bg_image(content, ctype, image_version=new_ver)
    if not ok:
        return jsonify({"ok": False, "error": "保存失败"}), 500
    conf["imageVersion"] = new_ver
    conf["useImage"] = True
    conf["dim"] = max(0, min(70, int(conf.get("dim") or 20)))
    conf["preset"] = conf.get("preset") or "cream"
    r2_store.save_miniapp_bg_config(conf)
    return jsonify({"ok": True, "imageVersion": int(conf["imageVersion"])})


@bp.route("/background-image", methods=["GET"])
def miniapp_get_background_image():
    data, ctype = r2_store.get_miniapp_bg_image()
    if not data:
        return jsonify({"ok": False, "error": "暂无背景图"}), 404
    # 背景图支持频繁替换：这里禁用强缓存，实际刷新仍由 imageVersion 控制兜底。
    return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})


@bp.route("/background-image/<int:image_version>", methods=["GET"])
def miniapp_get_background_image_versioned(image_version: int):
    """
    版本化路径读取背景图：
    - 目的：避免 WebView/代理对同一路径缓存过于激进导致“明明上传了仍显示旧图”。
    - 实际图片仍取当前存储，版本号用于强制路径变化。
    """
    data, ctype = r2_store.get_miniapp_bg_image(image_version=image_version)
    if not data:
        return jsonify({"ok": False, "error": "暂无背景图"}), 404
    return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})


@bp.route("/voice-config", methods=["GET"])
def miniapp_get_voice_config():
    raw = r2_store.get_miniapp_voice_config() or {}
    merged = _voice_call_default_config()
    merged.update({k: v for k, v in raw.items() if v is not None})
    avatar_version = int(merged.get("avatarVersion") or 0)
    merged["avatarVersion"] = avatar_version
    merged["useAvatarImage"] = bool(merged.get("useAvatarImage"))
    if not merged["useAvatarImage"]:
        data, _ = r2_store.get_miniapp_voice_avatar()
        if data:
            merged["useAvatarImage"] = True
    merged["avatarUrl"] = _miniapp_voice_avatar_url(avatar_version) if avatar_version > 0 and merged["useAvatarImage"] else ""
    if merged["useAvatarImage"] and not merged["avatarUrl"]:
        merged["avatarUrl"] = "/miniapp-api/voice-avatar"
    return jsonify({"ok": True, "config": merged})


@bp.route("/voice-config", methods=["PUT"])
def miniapp_put_voice_config():
    data = request.get_json(silent=True) or {}
    current = r2_store.get_miniapp_voice_config() or {}
    payload = _voice_call_default_config()
    payload.update({k: v for k, v in current.items() if v is not None})
    display_name = str(data.get("displayName") or payload.get("displayName") or "渡").strip()[:24] or "渡"
    subtitle = str(data.get("subtitle") or payload.get("subtitle") or "语音通话中").strip()[:40] or "语音通话中"
    theme = str(data.get("theme") or payload.get("theme") or "night").strip()[:16] or "night"
    # 防止客户端携带旧 draft 覆盖新头像版本号：版本号只允许前进不回退。
    current_ver = int(payload.get("avatarVersion") or 0)
    avatar_version = max(current_ver, max(0, int(data.get("avatarVersion") or 0)))
    payload.update(
        {
            "displayName": display_name,
            "subtitle": subtitle,
            "theme": theme,
            "avatarVersion": avatar_version,
            "useAvatarImage": bool(data.get("useAvatarImage", payload.get("useAvatarImage"))),
        }
    )
    ok = r2_store.save_miniapp_voice_config(payload)
    payload["avatarUrl"] = _miniapp_voice_avatar_url(avatar_version) if avatar_version > 0 and payload["useAvatarImage"] else ""
    return jsonify({"ok": ok, "config": payload})


@bp.route("/voice-avatar", methods=["POST"])
def miniapp_upload_voice_avatar():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "缺少 file"}), 400
    ctype = (f.mimetype or "").strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        return jsonify({"ok": False, "error": "仅支持 jpg/png/webp/gif"}), 400
    content = f.read()
    if not content:
        return jsonify({"ok": False, "error": "文件为空"}), 400
    if len(content) > 8 * 1024 * 1024:
        return jsonify({"ok": False, "error": "头像过大（最大 8MB）"}), 400
    conf = r2_store.get_miniapp_voice_config() or _voice_call_default_config()
    old_ver = int(conf.get("avatarVersion") or 0)
    new_ver = int(time.time() * 1000)
    if new_ver <= old_ver:
        new_ver = old_ver + 1
    ok = r2_store.save_miniapp_voice_avatar(content, ctype, image_version=new_ver)
    if not ok:
        return jsonify({"ok": False, "error": "头像保存失败"}), 500
    conf["avatarVersion"] = new_ver
    conf["useAvatarImage"] = True
    conf_ok = r2_store.save_miniapp_voice_config(conf)
    if not conf_ok:
        return jsonify({"ok": False, "error": "头像配置保存失败"}), 500
    return jsonify({"ok": True, "avatarVersion": new_ver, "avatarUrl": _miniapp_voice_avatar_url(new_ver)})


@bp.route("/voice-avatar", methods=["GET"])
def miniapp_get_voice_avatar():
    data, ctype = r2_store.get_miniapp_voice_avatar()
    if not data:
        return jsonify({"ok": False, "error": "暂无头像"}), 404
    return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})


@bp.route("/voice-avatar/<int:image_version>", methods=["GET"])
def miniapp_get_voice_avatar_versioned(image_version: int):
    data, ctype = r2_store.get_miniapp_voice_avatar(image_version=image_version)
    if not data:
        return jsonify({"ok": False, "error": "暂无头像"}), 404
    return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})


@bp.route("/voice-call", methods=["POST"])
def miniapp_voice_call():
    f = request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "error": "缺少 audio"}), 400
    mime_type = (f.mimetype or request.form.get("mime_type") or "application/octet-stream").strip().lower()
    if mime_type not in ("audio/webm", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg"):
        return jsonify({"ok": False, "error": f"暂不支持的音频格式：{mime_type or 'unknown'}"}), 400
    audio_bytes = f.read()
    if not audio_bytes:
        return jsonify({"ok": False, "error": "音频为空"}), 400
    if len(audio_bytes) > max(1024, int(VOICE_CALL_MAX_BYTES or 0)):
        return jsonify({"ok": False, "error": "音频太大了，缩短一点再试"}), 400

    filename = (f.filename or "voice.webm").strip() or "voice.webm"
    window_id = _resolve_voice_call_window_id(request.form.get("window_id") or "")
    call_id = (request.form.get("call_id") or "").strip() or str(uuid4())
    call_started_at = (request.form.get("call_started_at") or "").strip() or now_beijing_iso()
    user_text_override = (request.form.get("user_text_override") or "").strip()
    try:
        from services.voice_call_pipeline import run_voice_call
    except Exception as e:
        logger.warning("voice-call 依赖加载失败 err=%s", e)
        return jsonify({"ok": False, "error": "语音服务初始化失败"}), 500

    payload, status = run_voice_call(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        filename=filename,
        window_id=window_id,
        user_text_override=user_text_override,
    )
    if status >= 400:
        return jsonify(payload), status
    _append_call_record_turns(
        call_id=call_id,
        started_at=call_started_at,
        turns=[
            {"role": "user", "text": payload.get("user_text"), "kind": "voice", "timestamp": now_beijing_iso()},
            {"role": "assistant", "text": payload.get("reply_text"), "kind": "voice", "timestamp": now_beijing_iso()},
        ],
        mode="voice",
    )
    payload["call_id"] = call_id
    payload["call_started_at"] = call_started_at
    return jsonify(payload), status


@bp.route("/voice-call-preview", methods=["POST"])
def miniapp_voice_call_preview():
    f = request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "error": "缺少 audio"}), 400
    mime_type = (f.mimetype or request.form.get("mime_type") or "application/octet-stream").strip().lower()
    if mime_type not in ("audio/webm", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg"):
        return jsonify({"ok": False, "error": f"暂不支持的音频格式：{mime_type or 'unknown'}"}), 400
    audio_bytes = f.read()
    if not audio_bytes:
        return jsonify({"ok": False, "error": "音频为空"}), 400
    filename = (f.filename or "voice.webm").strip() or "voice.webm"
    try:
        from services.stt import speech_to_text
    except Exception as e:
        logger.warning("voice-call-preview 依赖加载失败 err=%s", e)
        return jsonify({"ok": False, "error": "语音服务初始化失败"}), 500
    text = speech_to_text(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename) or ""
    return jsonify({"ok": True, "text": text})


@bp.route("/tts-preview", methods=["POST"])
def miniapp_tts_preview():
    body = request.get_json(silent=True) or {}
    text = str(body.get("text") or "").strip()
    audio_format = str(body.get("audio_format") or "mp3").strip().lower() or "mp3"
    if not text:
        return jsonify({"ok": False, "error": "缺少 text"}), 400
    if audio_format not in ("mp3", "wav"):
        return jsonify({"ok": False, "error": f"暂不支持的 audio_format：{audio_format}"}), 400
    try:
        from services.minimax_tts import tts_to_audio_bytes
    except Exception as e:
        logger.warning("tts-preview 依赖加载失败 err=%s", e)
        return jsonify({"ok": False, "error": "语音服务初始化失败"}), 500
    audio_bytes = tts_to_audio_bytes(text, audio_format=audio_format)
    if not audio_bytes:
        return jsonify({"ok": False, "error": "语音生成失败"}), 502
    return jsonify(
        {
            "ok": True,
            "audio_b64": base64.b64encode(audio_bytes).decode("ascii"),
            "audio_format": audio_format,
        }
    )


@bp.route("/call-records", methods=["GET"])
def miniapp_get_call_records():
    items = _sort_call_records(r2_store.get_miniapp_call_records() or [])
    rows = [_call_record_summary(item) for item in items]
    return jsonify({"ok": True, "items": rows})


@bp.route("/call-records/<string:call_id>", methods=["GET"])
def miniapp_get_call_record_detail(call_id: str):
    cid = str(call_id or "").strip()
    if not cid:
        return jsonify({"ok": False, "error": "缺少通话 id"}), 400
    items = r2_store.get_miniapp_call_records() or []
    for item in items:
        if str(item.get("id") or "").strip() != cid:
            continue
        return jsonify(
            {
                "ok": True,
                "item": {
                    **_call_record_summary(item),
                    "turns": item.get("turns") or [],
                },
            }
        )
    return jsonify({"ok": False, "error": "找不到这条通话记录"}), 404


@bp.route("/call-records/<string:call_id>", methods=["DELETE"])
def miniapp_delete_call_record(call_id: str):
    cid = str(call_id or "").strip()
    if not cid:
        return jsonify({"ok": False, "error": "缺少通话 id"}), 400
    ok = r2_store.delete_miniapp_call_record(cid)
    if not ok:
        return jsonify({"ok": False, "error": "删除失败或记录不存在"}), 404
    return jsonify({"ok": True, "id": cid})


# ---------- 表情包 stickers/（MiniApp 管理 + 无公网时读图代理） ----------


@bp.route("/stickers/tags", methods=["GET"])
def miniapp_stickers_tags():
    """返回 [{ key, label_zh }]，网关目录与 [tag] 均为英文 key。"""
    from services.sticker_tags import validate_sticker_tag_key

    meta = r2_store.get_stickers_meta()
    rows: list[dict] = []
    for it in meta.get("tags") or []:
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "").strip().lower()
        if not validate_sticker_tag_key(k):
            continue
        lab = str(it.get("label_zh") or k).strip() or k
        rows.append({"key": k, "label_zh": lab})
    return jsonify({"ok": True, "tags": rows})


@bp.route("/stickers/category", methods=["POST"])
def miniapp_stickers_category_add():
    """新增分类：body { key: 英文代号, label_zh?: 展示名 }。"""
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    label_zh = (data.get("label_zh") or "").strip()
    ok, err = r2_store.add_sticker_category(key, label_zh)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True})


@bp.route("/stickers/mapping", methods=["GET"])
def miniapp_stickers_mapping_get():
    m = r2_store.get_stickers_mapping() or {}
    return jsonify(
        {
            "ok": True,
            "mapping": m,
            "public_base": (R2_PUBLIC_URL or "").strip().rstrip("/"),
        }
    )


@bp.route("/stickers/tags-public", methods=["GET"])
def miniapp_stickers_tags_public():
    """给服务端入口用：仅返回可用英文 tag 列表，不走 panel 鉴权。"""
    meta = r2_store.get_stickers_meta()
    keys: list[str] = []
    for it in meta.get("tags") or []:
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "").strip().lower()
        if k:
            keys.append(k)
    if not keys:
        keys = sorted(r2_store.get_sticker_tag_keys())
    return jsonify({"ok": True, "tags": sorted(set(keys))})


@bp.route("/stickers/resolve", methods=["GET"])
def miniapp_stickers_resolve():
    """给服务端入口用：按 tag 随机解析一张图。"""
    tag = (request.args.get("tag") or "").strip().lower()
    if not tag:
        return jsonify({"ok": False, "error": "缺少 tag"}), 400
    mapping = r2_store.get_stickers_mapping() or {}
    keys = [str(k or "").strip() for k in (mapping.get(tag) or []) if str(k or "").strip()]
    if not keys:
        return jsonify({"ok": False, "tag": tag, "error": "tag 未找到图片", "count": 0}), 404
    import random

    key = random.choice(keys)
    public_base = (R2_PUBLIC_URL or "").strip().rstrip("/")
    if public_base:
        url = f"{public_base}/{key.lstrip('/')}"
    else:
        url = f"/miniapp-api/stickers/raw-public?key={quote(key, safe='/')}"
    return jsonify({"ok": True, "tag": tag, "key": key, "url": url, "count": len(keys)})


@bp.route("/stickers/rebuild", methods=["POST"])
def miniapp_stickers_rebuild():
    data = r2_store.rebuild_stickers_mapping_from_r2()
    ok = r2_store.save_stickers_mapping(data)
    return jsonify({"ok": bool(ok), "mapping": data})


@bp.route("/stickers/upload", methods=["POST"])
def miniapp_stickers_upload():
    tag = (request.form.get("tag") or "").strip().lower()
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "缺少 file"}), 400
    content = f.read()
    if not content:
        return jsonify({"ok": False, "error": "文件为空"}), 400
    if len(content) > 8 * 1024 * 1024:
        return jsonify({"ok": False, "error": "单张不超过 8MB"}), 400
    ctype = (f.mimetype or "").strip().lower() or "image/jpeg"
    key = r2_store.upload_sticker_file(tag, f.filename or "sticker.jpg", content, ctype)
    if not key:
        return jsonify({"ok": False, "error": "上传失败（检查标签名与格式 jpg/png/webp/gif）"}), 400
    return jsonify({"ok": True, "key": key})


@bp.route("/stickers/item", methods=["DELETE"])
def miniapp_stickers_delete():
    body = request.get_json(silent=True) or {}
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "缺少 key"}), 400
    ok = r2_store.delete_sticker_object(key)
    if not ok:
        return jsonify({"ok": False, "error": "删除失败或 key 无效"}), 400
    return jsonify({"ok": True, "key": key})


@bp.route("/stickers/raw", methods=["GET"])
def miniapp_stickers_raw():
    """无 R2 公网域名时，前端用此 URL 预览图片（需 MiniApp 鉴权）。"""
    key = (request.args.get("key") or "").strip()
    if not key.startswith("stickers/") or ".." in key:
        return jsonify({"ok": False, "error": "key 无效"}), 400
    data, ctype = r2_store.get_object_bytes(key)
    if not data:
        return jsonify({"ok": False, "error": "未找到"}), 404
    mt = ctype if ctype and ctype.startswith("image/") else "image/jpeg"
    return Response(data, mimetype=mt, headers={"Cache-Control": "public, max-age=300"})


@bp.route("/stickers/raw-public", methods=["GET"])
def miniapp_stickers_raw_public():
    """给服务端入口用：无公网 R2 时通过网关直接取图，不走 panel 鉴权。"""
    key = (request.args.get("key") or "").strip()
    if not key.startswith("stickers/") or ".." in key:
        return jsonify({"ok": False, "error": "key 无效"}), 400
    data, ctype = r2_store.get_object_bytes(key)
    if not data:
        return jsonify({"ok": False, "error": "未找到"}), 404
    mt = ctype if ctype and ctype.startswith("image/") else "image/jpeg"
    return Response(data, mimetype=mt, headers={"Cache-Control": "public, max-age=300"})


_REASONING_TRANSLATE_CHUNK_CHARS = 6000


def _split_reasoning_translate_chunks(src: str, max_chars: int = _REASONING_TRANSLATE_CHUNK_CHARS) -> list[str]:
    text = str(src or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if len(line) > max_chars:
            if current:
                chunks.append("".join(current).strip())
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                part = line[i : i + max_chars].strip()
                if part:
                    chunks.append(part)
            continue
        if current and current_len + len(line) > max_chars:
            chunks.append("".join(current).strip())
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current).strip())
    return [c for c in chunks if c]


def _extract_chat_completion_text(data: dict) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    msg = (choices or [{}])[0].get("message", {}) if isinstance(choices, list) else {}
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts).strip()
    return str(content or "").strip()


def _translate_reasoning_chunk(src: str, url: str, api_key: str, model: str, index: int, total: int) -> str:
    system_prompt = (
        "你是一个高保真翻译器。请把用户提供的 reasoning 或 thinking 全文翻译成简体中文。"
        "必须完整保留原意、顺序与细节，不要总结，不要省略，不要扩写。"
        "代码、函数名、变量名、接口名、JSON 字段名、报错原文、英文专有名词可保留原文。"
        "输出只允许是译文正文，不要加任何前言、标题、注释或解释。"
    )
    if total > 1:
        user_prompt = f"请翻译下面 reasoning 的第 {index}/{total} 段，只输出这一段的译文：\n\n{src}"
    else:
        user_prompt = f"请把下面内容全文翻译成简体中文：\n\n{src}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": max(1024, min(8192, len(src) * 3)),
    }
    try:
        rc = requests.post(url, headers=headers, json=body, timeout=90)
        rc.raise_for_status()
        data = rc.json() if rc.content else {}
        out = _extract_chat_completion_text(data)
        if not out:
            raise RuntimeError("上游未返回翻译内容")
        return out
    except requests.HTTPError as e:
        detail = ""
        try:
            detail = (e.response.text or "").strip()
        except Exception:
            detail = ""
        raise RuntimeError(f"翻译请求失败：{detail[:240] or e}")
    except Exception as e:
        raise RuntimeError(f"翻译失败：{e}")


def _translate_reasoning_text(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return ""

    url = str(DEEPSEEK_API_URL or "").strip()
    api_key = str(DEEPSEEK_API_KEY or "").strip()
    model = str(DEEPSEEK_CHAT_MODEL or "").strip()
    if not url or not api_key or not model:
        raise RuntimeError("DeepSeek 翻译未配置完整，无法翻译")

    chunks = _split_reasoning_translate_chunks(src)
    if not chunks:
        return ""
    total = len(chunks)
    translated: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        translated.append(_translate_reasoning_chunk(chunk, url, api_key, model, idx, total))
    return "\n\n".join(part for part in translated if part).strip()


@bp.route("/reasoning/translate", methods=["POST"])
def miniapp_translate_reasoning():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text 不能为空"}), 400
    if len(text) > 120000:
        return jsonify({"ok": False, "error": "text 过长，暂不支持翻译"}), 400
    try:
        translated = _translate_reasoning_text(text)
    except Exception as e:
        logger.warning("reasoning_translate_failed length=%s error=%s", len(text), str(e)[:500])
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, "translated": translated})
