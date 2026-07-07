"""SQLite storage helpers for SumiTalk native app actions."""
import re
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import uuid4

from storage import runtime_sqlite
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ

R2_KEY_APP_ACTION_QUEUE = "sumitalk/app_actions.json"

_APP_ACTION_ALLOWLIST = {
    "create_system_alarm",
    "create_calendar_event",
    "show_choice_dialog",
    "show_system_notification",
    "request_screen_check",
    "voice_call_invite",
    "recall_message",
}
_APP_ACTION_HISTORY_MAX = 100
_APP_ACTION_EXPIRES_DEFAULT = 900
_APP_ACTION_EXPIRES_MIN = 30
_APP_ACTION_EXPIRES_MAX = 3600
_APP_ACTION_LEASE_SECONDS = 90
_APP_ACTION_MAX_RETRY = 3
_APP_ACTION_VOICE_TAG_RE = re.compile(r"</?voice>", flags=re.IGNORECASE)

_app_action_write_lock = threading.Lock()
_app_action_bootstrap_lock = threading.Lock()
_APP_ACTION_BOOTSTRAPPED = False

logger = get_logger(__name__)


def _payload_log_summary(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {}
    summary: dict[str, Any] = {}
    title = str(payload.get("title") or "").strip()
    message = str(payload.get("message") or payload.get("content") or "").strip()
    if title:
        summary["title"] = title[:60]
    if message:
        summary["message_len"] = len(message)
    if "timeoutSeconds" in payload:
        summary["timeoutSeconds"] = payload.get("timeoutSeconds")
    if "choices" in payload and isinstance(payload.get("choices"), list):
        summary["choices"] = len(payload.get("choices") or [])
    reply_text = str(payload.get("replyText") or payload.get("reply_text") or "").strip()
    if reply_text:
        summary["reply_text_len"] = len(reply_text)
    surface = str(payload.get("surface") or "").strip()
    if surface:
        summary["surface"] = surface
    window_id = str(payload.get("windowId") or payload.get("window_id") or "").strip()
    if window_id:
        summary["windowId"] = window_id[:80]
    message_ids = payload.get("messageIds") or payload.get("message_ids")
    if isinstance(message_ids, list):
        summary["message_count"] = len(message_ids)
    return summary


def _result_log_summary(result: Any) -> dict:
    if not isinstance(result, dict):
        return {}
    detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
    return {
        "status": str(result.get("status") or "").strip(),
        "error": str(result.get("error") or "").strip()[:120],
        "stage": str(detail.get("stage") or "").strip(),
        "approved": detail.get("approved") if "approved" in detail else "",
        "choice_id": str(detail.get("choice_id") or "").strip(),
        "choiceId": str(detail.get("choiceId") or "").strip(),
        "timeout": detail.get("timeout") if "timeout" in detail else "",
        "autoSelected": detail.get("autoSelected") if "autoSelected" in detail else "",
        "message_count": len(detail.get("recalledMessages") or []) if isinstance(detail.get("recalledMessages"), list) else "",
        "detail_error": str(detail.get("error") or "").strip()[:120],
    }


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Optional[Any]:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_iso(value: str) -> Optional[datetime]:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _parse_any_iso_to_utc(value: str) -> Optional[datetime]:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BEIJING_TZ)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _app_action_queue_raw(client) -> dict:
    data = _read_json(client, R2_KEY_APP_ACTION_QUEUE)
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("pending"), list):
        data["pending"] = []
    if not isinstance(data.get("history"), list):
        data["history"] = []
    if not isinstance(data.get("idempotencyKeys"), dict):
        data["idempotencyKeys"] = {}
    return data


def _trim_app_action_history(history: list) -> list:
    rows = [x for x in (history or []) if isinstance(x, dict)]
    rows.sort(key=lambda x: str(x.get("finishedAt") or x.get("createdAt") or ""), reverse=True)
    return rows[:_APP_ACTION_HISTORY_MAX]


def _json_dict(raw: str | None) -> dict:
    data = runtime_sqlite.json_loads(raw, {})
    return data if isinstance(data, dict) else {}


def _row_to_app_action(row) -> dict:
    status = str(row["status"] or "pending").strip() or "pending"
    item = {
        "id": str(row["id"] or ""),
        "type": str(row["type"] or ""),
        "payload": _json_dict(row["payload_json"]),
        "deviceId": str(row["device_id"] or ""),
        "source": str(row["source"] or "tool"),
        "createdAt": str(row["created_at"] or ""),
        "expiresAt": str(row["expires_at"] or ""),
        "leasedUntil": str(row["leased_until"] or ""),
        "leasedAt": str(row["leased_at"] or ""),
        "leasedByDeviceId": str(row["leased_by_device_id"] or ""),
        "retryCount": int(row["retry_count"] or 0),
    }
    if status != "pending":
        item["status"] = status
        item["finishedAt"] = str(row["finished_at"] or "")
        item["result"] = _json_dict(row["result_json"])
        item["error"] = str(row["error"] or "")
    return item


def _insert_app_action_row(conn, item: dict, status: str = "pending", *, ignore: bool = False) -> None:
    verb = "INSERT OR IGNORE" if ignore else "INSERT"
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    conn.execute(
        f"""
        {verb} INTO app_actions (
            id, type, payload_json, device_id, source, created_at, expires_at,
            leased_until, leased_at, leased_by_device_id, retry_count,
            status, finished_at, result_json, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(item.get("id") or ""),
            str(item.get("type") or ""),
            runtime_sqlite.json_dumps(payload),
            str(item.get("deviceId") or ""),
            str(item.get("source") or "tool").strip()[:40] or "tool",
            str(item.get("createdAt") or ""),
            str(item.get("expiresAt") or ""),
            str(item.get("leasedUntil") or ""),
            str(item.get("leasedAt") or ""),
            str(item.get("leasedByDeviceId") or ""),
            int(item.get("retryCount") or 0),
            str(status or "pending").strip() or "pending",
            str(item.get("finishedAt") or ""),
            runtime_sqlite.json_dumps(result),
            str(item.get("error") or ""),
        ),
    )


def _prune_app_action_state(conn, now_iso: str) -> None:
    conn.execute("DELETE FROM app_action_idempotency WHERE expires_at <= ?", (now_iso,))
    conn.execute(
        """
        DELETE FROM app_actions
        WHERE status <> 'pending'
          AND id NOT IN (
            SELECT id
            FROM app_actions
            WHERE status <> 'pending'
            ORDER BY COALESCE(NULLIF(finished_at, ''), created_at) DESC
            LIMIT ?
          )
        """,
        (_APP_ACTION_HISTORY_MAX,),
    )


def _import_r2_app_action_queue(data: dict) -> None:
    if not isinstance(data, dict):
        return
    now_iso = _utc_now_iso()
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for item in data.get("pending") or []:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                action_type = str(item.get("type") or "").strip()
                if not item_id or not action_type:
                    continue
                _insert_app_action_row(conn, item, "pending", ignore=True)
            for item in _trim_app_action_history(data.get("history") or []):
                item_id = str(item.get("id") or "").strip()
                action_type = str(item.get("type") or "").strip()
                if not item_id or not action_type:
                    continue
                status = str(item.get("status") or "done").strip() or "done"
                if status == "pending":
                    status = "done"
                _insert_app_action_row(conn, item, status, ignore=True)
            idem_keys = data.get("idempotencyKeys") if isinstance(data.get("idempotencyKeys"), dict) else {}
            for key, value in idem_keys.items():
                if not isinstance(value, dict):
                    continue
                idem = str(key or "").strip()
                action_id = str(value.get("id") or "").strip()
                expires_at = str(value.get("expiresAt") or "").strip()
                exp = _parse_utc_iso(expires_at)
                if not idem or not action_id or not exp or exp <= datetime.now(timezone.utc):
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO app_action_idempotency
                        (idem_key, action_id, expires_at)
                    VALUES (?, ?, ?)
                    """,
                    (idem, action_id, expires_at),
                )
            _prune_app_action_state(conn, now_iso)
            conn.execute("COMMIT")
            logger.info("app_action_sqlite_bootstrap imported_from_r2=True")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _ensure_app_actions_bootstrapped() -> None:
    global _APP_ACTION_BOOTSTRAPPED
    if _APP_ACTION_BOOTSTRAPPED:
        return
    with _app_action_bootstrap_lock:
        if _APP_ACTION_BOOTSTRAPPED:
            return
        try:
            with runtime_sqlite.connect() as conn:
                row = conn.execute("SELECT 1 FROM app_actions LIMIT 1").fetchone()
                idem = conn.execute("SELECT 1 FROM app_action_idempotency LIMIT 1").fetchone()
                if row is not None or idem is not None:
                    _APP_ACTION_BOOTSTRAPPED = True
                    return
        except Exception as e:
            logger.warning("app_action_sqlite_bootstrap check failed error=%s", e)
            return

        client = _s3_client()
        if client:
            try:
                _import_r2_app_action_queue(_app_action_queue_raw(client))
            except Exception as e:
                logger.warning("app_action_sqlite_bootstrap import r2 failed error=%s", e)
        _APP_ACTION_BOOTSTRAPPED = True


def _parse_app_action_datetime(value) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    return dt


def _normalize_calendar_event_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or src.get("summary") or "渡的行程").strip() or "渡的行程"
    if len(title) > 120:
        title = title[:120]
    all_day = bool(src.get("allDay") if "allDay" in src else src.get("all_day", False))
    start = _parse_app_action_datetime(src.get("startAt") or src.get("start_at") or src.get("start_datetime") or src.get("datetime"))
    if not start:
        return None, "start_datetime/startAt 必须是 ISO 时间"

    end = _parse_app_action_datetime(src.get("endAt") or src.get("end_at") or src.get("end_datetime"))
    if not end:
        try:
            duration_minutes = int(src.get("durationMinutes") if "durationMinutes" in src else src.get("duration_minutes", 1440 if all_day else 60))
        except Exception:
            duration_minutes = 1440 if all_day else 60
        if duration_minutes <= 0:
            return None, "duration_minutes 必须大于 0"
        end = start + timedelta(minutes=duration_minutes)
    if end <= start:
        return None, "end_datetime 必须晚于 start_datetime"

    description = str(src.get("description") or src.get("note") or "").strip()
    if len(description) > 1000:
        description = description[:1000]
    location = str(src.get("location") or "").strip()
    if len(location) > 200:
        location = location[:200]
    try:
        reminder_minutes = int(src.get("reminderMinutes") if "reminderMinutes" in src else src.get("reminder_minutes", 10))
    except Exception:
        reminder_minutes = 10
    reminder_minutes = max(-1, min(10080, reminder_minutes))
    notify = bool(src.get("notify", True))

    start_bj = start.astimezone(BEIJING_TZ)
    end_bj = end.astimezone(BEIJING_TZ)
    return {
        "title": title,
        "startAt": start_bj.isoformat(),
        "endAt": end_bj.isoformat(),
        "startMillis": int(start.timestamp() * 1000),
        "endMillis": int(end.timestamp() * 1000),
        "allDay": all_day,
        "description": description,
        "location": location,
        "reminderMinutes": reminder_minutes,
        "notify": notify,
    }, None


def _normalize_app_action_payload(action_type: str, payload: dict) -> tuple[Optional[dict], Optional[str]]:
    if action_type == "create_calendar_event":
        return _normalize_calendar_event_payload(payload)
    if action_type == "show_choice_dialog":
        return _normalize_choice_dialog_payload(payload)
    if action_type == "show_system_notification":
        return _normalize_system_notification_payload(payload)
    if action_type == "request_screen_check":
        return _normalize_screen_check_payload(payload)
    if action_type == "voice_call_invite":
        return _normalize_voice_call_invite_payload(payload)
    if action_type == "recall_message":
        return _normalize_recall_message_payload(payload)
    if action_type != "create_system_alarm":
        return None, f"不支持的 app action: {action_type}"
    src = payload if isinstance(payload, dict) else {}
    try:
        hour = int(src.get("hour"))
    except Exception:
        return None, "hour 必须是 0-23"
    try:
        minute = int(src.get("minute"))
    except Exception:
        return None, "minute 必须是 0-59"
    if hour < 0 or hour > 23:
        return None, "hour 必须是 0-23"
    if minute < 0 or minute > 59:
        return None, "minute 必须是 0-59"
    title = str(src.get("title") or "渡的提醒").strip() or "渡的提醒"
    if len(title) > 80:
        title = title[:80]
    skip_ui = bool(src.get("skipUi") if "skipUi" in src else src.get("skip_ui", False))
    notify = bool(src.get("notify", True))
    return {
        "hour": hour,
        "minute": minute,
        "title": title,
        "skipUi": skip_ui,
        "notify": notify,
    }, None


def _normalize_choice_label(value, fallback: str) -> str:
    label = str(value or "").strip() or fallback
    if len(label) > 8:
        label = label[:8]
    return label


def _normalize_choice_dialog_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "渡").strip() or "渡"
    if len(title) > 60:
        title = title[:60]
    message = str(src.get("message") or src.get("content") or "").strip()
    if not message:
        return None, "message 不能为空"
    if len(message) > 500:
        message = message[:500]

    choice_a = src.get("choice_a") or src.get("choiceA") or src.get("positive")
    choice_b = src.get("choice_b") or src.get("choiceB") or src.get("negative")
    raw_choices = src.get("choices")
    if isinstance(raw_choices, list):
        if len(raw_choices) > 0:
            first = raw_choices[0]
            choice_a = first.get("label") if isinstance(first, dict) else first
        if len(raw_choices) > 1:
            second = raw_choices[1]
            choice_b = second.get("label") if isinstance(second, dict) else second
    label_a = _normalize_choice_label(choice_a, "好的")
    label_b = _normalize_choice_label(choice_b, "知道了")

    level = str(src.get("level") or "info").strip().lower()
    if level not in {"info", "warning", "strict"}:
        level = "info"
    dismissible = bool(src.get("dismissible", level != "strict"))
    try:
        timeout_seconds = int(src.get("timeout_seconds") if "timeout_seconds" in src else src.get("timeoutSeconds", 600))
    except Exception:
        timeout_seconds = 600
    timeout_seconds = max(30, min(1800, timeout_seconds))
    notify_du = bool(src.get("notifyDu") if "notifyDu" in src else src.get("notify_du", True))
    return {
        "title": title,
        "message": message,
        "level": level,
        "dismissible": dismissible,
        "timeoutSeconds": timeout_seconds,
        "notifyDu": notify_du,
        "choices": [
            {"id": "choice_a", "label": label_a},
            {"id": "choice_b", "label": label_b},
        ],
    }, None


def _normalize_system_notification_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "SumiTalk").strip() or "SumiTalk"
    if len(title) > 80:
        title = title[:80]
    message = str(src.get("message") or src.get("content") or "").strip()
    if not message:
        return None, "message 不能为空"
    if len(message) > 800:
        message = message[:800]
    level = str(src.get("level") or "info").strip().lower()
    if level not in {"info", "message", "success", "warning", "error"}:
        level = "info"
    category = str(src.get("category") or "").strip().lower()
    if category not in {"", "message", "status", "reminder", "event", "error"}:
        category = ""
    open_app = bool(src.get("openApp") if "openApp" in src else src.get("open_app", True))
    return {
        "title": title,
        "message": message,
        "level": level,
        "category": category,
        "openApp": open_app,
    }, None


def _normalize_screen_check_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "渡想查岗").strip() or "渡想查岗"
    if len(title) > 60:
        title = title[:60]
    message = str(src.get("message") or src.get("reason") or "渡想看一眼你现在屏幕上在做什么。只有你同意后才会截图。").strip()
    if not message:
        message = "渡想看一眼你现在屏幕上在做什么。只有你同意后才会截图。"
    if len(message) > 500:
        message = message[:500]
    try:
        timeout_seconds = int(src.get("timeout_seconds") if "timeout_seconds" in src else src.get("timeoutSeconds", 120))
    except Exception:
        timeout_seconds = 120
    timeout_seconds = max(30, min(300, timeout_seconds))
    return {
        "title": title,
        "message": message,
        "timeoutSeconds": timeout_seconds,
    }, None


def _normalize_voice_call_invite_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "渡来电").strip() or "渡来电"
    if len(title) > 60:
        title = title[:60]
    caller_name = str(src.get("callerName") or src.get("caller_name") or "渡").strip() or "渡"
    if len(caller_name) > 24:
        caller_name = caller_name[:24]
    opening_line = str(
        src.get("openingLine")
        or src.get("opening_line")
        or src.get("voice")
        or src.get("message")
        or ""
    ).strip()
    opening_line = _APP_ACTION_VOICE_TAG_RE.sub("", opening_line).strip()
    if not opening_line:
        return None, "opening_line 不能为空"
    if len(opening_line) > 240:
        opening_line = opening_line[:240].rstrip() + "。"
    reason = str(src.get("reason") or "").strip()
    if len(reason) > 200:
        reason = reason[:200]
    urgency = str(src.get("urgency") or "normal").strip().lower()
    if urgency not in {"normal", "important", "urgent"}:
        urgency = "normal"
    call_id = str(src.get("callId") or src.get("call_id") or "").strip()
    if not call_id:
        call_id = "call_" + str(uuid4()).replace("-", "")
    try:
        timeout_seconds = int(src.get("timeout_seconds") if "timeout_seconds" in src else src.get("timeoutSeconds", 180))
    except Exception:
        timeout_seconds = 180
    timeout_seconds = max(30, min(900, timeout_seconds))
    return {
        "title": title,
        "callerName": caller_name,
        "openingLine": opening_line,
        "reason": reason,
        "urgency": urgency,
        "callId": call_id,
        "timeoutSeconds": timeout_seconds,
    }, None


def _normalize_recall_choice(raw: Any, fallback_id: str, fallback_label: str) -> dict:
    if isinstance(raw, dict):
        choice_id = str(raw.get("id") or raw.get("choiceId") or raw.get("choice_id") or fallback_id).strip() or fallback_id
        label = str(raw.get("label") or raw.get("text") or raw.get("title") or fallback_label).strip() or fallback_label
    else:
        choice_id = fallback_id
        label = str(raw or fallback_label).strip() or fallback_label
    return {
        "id": choice_id[:40],
        "label": label[:18],
    }


def _normalize_recall_message_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    raw_ids = src.get("messageIds")
    if raw_ids is None:
        raw_ids = src.get("message_ids")
    if raw_ids is None and src.get("messageId"):
        raw_ids = [src.get("messageId")]
    if raw_ids is None and src.get("message_id"):
        raw_ids = [src.get("message_id")]
    if not isinstance(raw_ids, list):
        return None, "messageIds 必须是数组"
    message_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        mid = str(raw_id or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        message_ids.append(mid[:160])
    if not message_ids:
        return None, "messageIds 不能为空"
    if len(message_ids) > 8:
        message_ids = message_ids[:8]

    popup_src = src.get("popup") if isinstance(src.get("popup"), dict) else {}
    raw_texts = popup_src.get("texts") or src.get("texts")
    texts: list[str] = []
    if isinstance(raw_texts, list):
        for item in raw_texts:
            text = str(item or "").strip()
            if text:
                texts.append(text[:80])
            if len(texts) >= 12:
                break
    if not texts:
        texts = ["为什么", "为什么", "为什么"]

    final_title = str(popup_src.get("finalTitle") or popup_src.get("title") or src.get("finalTitle") or "渡").strip() or "渡"
    final_message = str(
        popup_src.get("finalMessage")
        or popup_src.get("message")
        or src.get("finalMessage")
        or "你刚刚说的话，他想先收走。"
    ).strip()
    reply_text = str(
        popup_src.get("replyText")
        or popup_src.get("reply_text")
        or popup_src.get("noticeText")
        or popup_src.get("notice_text")
        or src.get("replyText")
        or src.get("reply_text")
        or src.get("noticeText")
        or src.get("notice_text")
        or src.get("replacementText")
        or src.get("replacement_text")
        or src.get("responseText")
        or src.get("response_text")
        or ""
    ).strip()
    raw_choices = popup_src.get("choices") or src.get("choices")
    choices: list[dict] = []
    if isinstance(raw_choices, list):
        for idx, raw_choice in enumerate(raw_choices[:2]):
            choices.append(_normalize_recall_choice(raw_choice, f"choice_{idx + 1}", "我知道了" if idx == 0 else "我认错"))
    if not choices:
        choices = [
            {"id": "apologize", "label": "我认错"},
            {"id": "listen", "label": "听你的"},
        ]
    if len(choices) == 1:
        choices.append({"id": "listen", "label": "听你的"})

    try:
        countdown_seconds = int(
            popup_src.get("countdownSeconds")
            if "countdownSeconds" in popup_src
            else popup_src.get("countdown_seconds", src.get("countdownSeconds", 8))
        )
    except Exception:
        countdown_seconds = 8
    countdown_seconds = max(3, min(30, countdown_seconds))
    timeout_choice_id = str(
        popup_src.get("timeoutChoiceId")
        or popup_src.get("timeout_choice_id")
        or src.get("timeoutChoiceId")
        or choices[0].get("id")
        or ""
    ).strip()
    choice_ids = {str(choice.get("id") or "").strip() for choice in choices}
    if timeout_choice_id not in choice_ids:
        timeout_choice_id = str(choices[0].get("id") or "").strip()
    window_id = str(src.get("windowId") or src.get("window_id") or "").strip()
    if not window_id:
        return None, "recall_message 必须带 windowId"
    return {
        "surface": "chat_ui",
        "windowId": window_id[:160],
        "messageIds": message_ids,
        "replyText": reply_text[:500],
        "popup": {
            "texts": texts,
            "finalTitle": final_title[:60],
            "finalMessage": final_message[:240],
            "choices": choices[:2],
            "countdownSeconds": countdown_seconds,
            "timeoutChoiceId": timeout_choice_id,
        },
    }, None


def _action_surface(payload: Any) -> str:
    surface = str((payload or {}).get("surface") or "").strip().lower() if isinstance(payload, dict) else ""
    return "chat_ui" if surface == "chat_ui" else "native"


def _action_window_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("windowId") or payload.get("window_id") or "").strip()


def _public_app_action(item: dict) -> dict:
    return {
        "id": str((item or {}).get("id") or ""),
        "type": str((item or {}).get("type") or ""),
        "payload": (item or {}).get("payload") if isinstance((item or {}).get("payload"), dict) else {},
    }


def _publish_app_action(item: dict) -> None:
    try:
        from services.realtime_publish import publish_chat_ui_device_actions, publish_device_actions

        target_device = str((item or {}).get("deviceId") or "").strip()
        payload = (item or {}).get("payload") if isinstance((item or {}).get("payload"), dict) else {}
        surface = _action_surface(payload)
        if surface == "chat_ui":
            ok = publish_chat_ui_device_actions(
                device_id=target_device,
                window_id=_action_window_id(payload),
                actions=[_public_app_action(item)],
            )
        else:
            ok = publish_device_actions(device_id=target_device, actions=[_public_app_action(item)])
        logger.info(
            "app_action_realtime_publish id=%s type=%s surface=%s target_device=%s window_id=%s ok=%s",
            str((item or {}).get("id") or ""),
            str((item or {}).get("type") or ""),
            surface,
            target_device,
            _action_window_id(payload),
            ok,
        )
    except Exception as e:
        logger.debug("publish_app_action failed id=%s error=%s", str((item or {}).get("id") or ""), e)


def append_app_action(
    action_type: str,
    payload: dict,
    device_id: str = "",
    expires_in_sec: int = _APP_ACTION_EXPIRES_DEFAULT,
    source: str = "tool",
    idempotency_key: str = "",
) -> tuple[Optional[dict], Optional[str]]:
    """向 SumiTalk app 原生命令队列追加一条动作。"""
    action = str(action_type or "").strip()
    if action not in _APP_ACTION_ALLOWLIST:
        return None, f"不允许的 app action: {action}"
    normalized_payload, err = _normalize_app_action_payload(action, payload if isinstance(payload, dict) else {})
    if err:
        return None, err
    try:
        ttl = int(expires_in_sec or _APP_ACTION_EXPIRES_DEFAULT)
    except Exception:
        ttl = _APP_ACTION_EXPIRES_DEFAULT
    ttl = max(_APP_ACTION_EXPIRES_MIN, min(_APP_ACTION_EXPIRES_MAX, ttl))
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_at = (now + timedelta(seconds=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")
    idem = str(idempotency_key or "").strip()
    item = {
        "id": str(uuid4()),
        "type": action,
        "payload": normalized_payload,
        "deviceId": str(device_id or "").strip(),
        "source": str(source or "tool").strip()[:40] or "tool",
        "createdAt": now_iso,
        "expiresAt": expires_at,
        "leasedUntil": "",
        "leasedAt": "",
        "leasedByDeviceId": "",
        "retryCount": 0,
    }
    _ensure_app_actions_bootstrapped()
    with _app_action_write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    _prune_app_action_state(conn, now_iso)
                    if idem:
                        row = conn.execute(
                            """
                            SELECT a.*
                            FROM app_action_idempotency AS i
                            JOIN app_actions AS a ON a.id = i.action_id
                            WHERE i.idem_key = ?
                              AND i.expires_at > ?
                              AND a.status = 'pending'
                            LIMIT 1
                            """,
                            (idem, now_iso),
                        ).fetchone()
                        if row is not None:
                            old = _row_to_app_action(row)
                            logger.info(
                                "app_action_enqueue_duplicate type=%s id=%s target_device=%s source=%s expires_at=%s",
                                action,
                                old["id"],
                                old["deviceId"],
                                item["source"],
                                old["expiresAt"],
                            )
                            conn.execute("COMMIT")
                            return {**old, "duplicate": True}, None
                        conn.execute("DELETE FROM app_action_idempotency WHERE idem_key=?", (idem,))
                    _insert_app_action_row(conn, item, "pending")
                    if idem:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO app_action_idempotency
                                (idem_key, action_id, expires_at)
                            VALUES (?, ?, ?)
                            """,
                            (idem, item["id"], expires_at),
                        )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            logger.info(
                "app_action_enqueued id=%s type=%s target_device=%s source=%s ttl=%s expires_at=%s payload=%s",
                item["id"],
                item["type"],
                item["deviceId"],
                item["source"],
                ttl,
                item["expiresAt"],
                _payload_log_summary(normalized_payload),
            )
            _publish_app_action(item)
            return item, None
        except Exception as e:
            logger.error("append_app_action 失败 type=%s error=%s", action, e, exc_info=True)
            return None, str(e)


def poll_app_actions(device_id: str = "", limit: int = 10, surface: str = "native", window_id: str = "") -> dict:
    """安卓壳轮询待执行 app 原生命令。"""
    device = str(device_id or "").strip()
    wanted_surface = "chat_ui" if str(surface or "").strip().lower() == "chat_ui" else "native"
    wanted_window_id = str(window_id or "").strip()
    try:
        max_items = max(1, min(20, int(limit or 10)))
    except Exception:
        max_items = 10
    now = datetime.now(timezone.utc)
    lease_until = (now + timedelta(seconds=_APP_ACTION_LEASE_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    _ensure_app_actions_bootstrapped()
    with _app_action_write_lock:
        try:
            out = []
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    _prune_app_action_state(conn, now_iso)
                    rows = conn.execute(
                        """
                        SELECT *
                        FROM app_actions
                        WHERE status = 'pending'
                        ORDER BY created_at ASC
                        """
                    ).fetchall()
                    for row in rows:
                        item = _row_to_app_action(row)
                        item_id = item["id"]
                        exp = _parse_utc_iso(item["expiresAt"])
                        if exp and exp <= now:
                            logger.info(
                                "app_action_expired id=%s type=%s target_device=%s leased_by=%s retry=%s expires_at=%s",
                                item_id,
                                item["type"],
                                item["deviceId"],
                                item["leasedByDeviceId"],
                                item["retryCount"],
                                item["expiresAt"],
                            )
                            conn.execute(
                                """
                                UPDATE app_actions
                                SET status='expired', finished_at=?
                                WHERE id=? AND status='pending'
                                """,
                                (now_iso, item_id),
                            )
                            continue
                        target_device = item["deviceId"].strip()
                        if target_device and device and target_device != device:
                            continue
                        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                        item_surface = _action_surface(payload)
                        if item_surface != wanted_surface:
                            continue
                        item_window_id = _action_window_id(payload)
                        if wanted_surface == "chat_ui":
                            if not wanted_window_id or not item_window_id or item_window_id != wanted_window_id:
                                continue
                        leased = _parse_utc_iso(item["leasedUntil"])
                        if leased and leased > now:
                            continue
                        original_retry = int(item.get("retryCount") or 0)
                        retry_count = original_retry
                        if leased and leased <= now:
                            retry_count += 1
                            logger.info(
                                "app_action_lease_retry id=%s type=%s device_id=%s previous_leased_by=%s retry=%s previous_leased_until=%s",
                                item_id,
                                item["type"],
                                device,
                                item["leasedByDeviceId"],
                                retry_count,
                                item["leasedUntil"],
                            )
                        if retry_count >= _APP_ACTION_MAX_RETRY:
                            logger.warning(
                                "app_action_abandoned id=%s type=%s device_id=%s target_device=%s leased_by=%s retry=%s payload=%s",
                                item_id,
                                item["type"],
                                device,
                                item["deviceId"],
                                item["leasedByDeviceId"],
                                retry_count,
                                _payload_log_summary(item.get("payload")),
                            )
                            conn.execute(
                                """
                                UPDATE app_actions
                                SET status='abandoned', finished_at=?, retry_count=?
                                WHERE id=? AND status='pending'
                                """,
                                (now_iso, retry_count, item_id),
                            )
                            continue
                        if len(out) < max_items:
                            conn.execute(
                                """
                                UPDATE app_actions
                                SET leased_until=?, leased_at=?, leased_by_device_id=?, retry_count=?
                                WHERE id=? AND status='pending'
                                """,
                                (lease_until, now_iso, device, retry_count, item_id),
                            )
                            item["leasedUntil"] = lease_until
                            item["leasedAt"] = now_iso
                            item["leasedByDeviceId"] = device
                            item["retryCount"] = retry_count
                            out.append(_public_app_action(item))
                            logger.info(
                                "app_action_leased id=%s type=%s surface=%s window_id=%s device_id=%s target_device=%s retry=%s leased_until=%s via=poll",
                                item_id,
                                item["type"],
                                item_surface,
                                item_window_id,
                                device,
                                target_device,
                                retry_count,
                                lease_until,
                            )
                        elif retry_count != original_retry:
                            conn.execute(
                                "UPDATE app_actions SET retry_count=? WHERE id=? AND status='pending'",
                                (retry_count, item_id),
                            )
                    _prune_app_action_state(conn, now_iso)
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            return {"ok": True, "actions": out, "pollAfterSec": 20}
        except Exception as e:
            logger.error(
                "poll_app_actions 失败 device_id=%s surface=%s window_id=%s error=%s",
                device,
                wanted_surface,
                wanted_window_id,
                e,
                exc_info=True,
            )
            return {"ok": False, "actions": [], "pollAfterSec": 20, "error": str(e)}


def report_app_actions(results: list, device_id: str = "") -> dict:
    """安卓壳回执 app 原生命令执行结果。"""
    if not isinstance(results, list):
        return {"ok": False, "error": "results 必须是数组", "processed": 0}
    device = str(device_id or "").strip()
    now_iso = _utc_now_iso()
    result_map = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "").strip()
        if item_id:
            result_map[item_id] = row
    if not result_map:
        return {"ok": True, "processed": 0, "items": []}

    _ensure_app_actions_bootstrapped()
    with _app_action_write_lock:
        try:
            processed_items = []
            processed_ids = set()
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for item_id, result in result_map.items():
                        row = conn.execute(
                            "SELECT * FROM app_actions WHERE id=? AND status='pending'",
                            (item_id,),
                        ).fetchone()
                        if row is None:
                            continue
                        item = _row_to_app_action(row)
                        target_device = item["deviceId"].strip()
                        if target_device and device and target_device != device:
                            logger.warning(
                                "app_action_result_device_mismatch id=%s type=%s device_id=%s target_device=%s",
                                item_id,
                                item["type"],
                                device,
                                target_device,
                            )
                            continue
                        status = str(result.get("status") or "").strip().lower()
                        if status not in {"done", "failed"}:
                            status = "failed"
                        logger.info(
                            "app_action_result id=%s type=%s device_id=%s target_device=%s status=%s summary=%s",
                            item_id,
                            item["type"],
                            device,
                            target_device,
                            status,
                            _result_log_summary(result),
                        )
                        detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
                        error = str(result.get("error") or "").strip()
                        conn.execute(
                            """
                            UPDATE app_actions
                            SET status=?, finished_at=?, device_id=?, result_json=?, error=?
                            WHERE id=? AND status='pending'
                            """,
                            (
                                status,
                                now_iso,
                                device or target_device,
                                runtime_sqlite.json_dumps(detail),
                                error,
                                item_id,
                            ),
                        )
                        finished = {
                            **item,
                            "status": status,
                            "finishedAt": now_iso,
                            "deviceId": device or target_device,
                            "result": detail,
                            "error": error,
                        }
                        processed_items.append(finished)
                        processed_ids.add(item_id)
                    unmatched_ids = [item_id for item_id in result_map.keys() if item_id not in processed_ids]
                    if unmatched_ids:
                        logger.warning("app_action_result_unmatched device_id=%s ids=%s", device, unmatched_ids)
                    _prune_app_action_state(conn, now_iso)
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            return {"ok": True, "processed": len(processed_items), "items": processed_items}
        except Exception as e:
            logger.error("report_app_actions 失败 device_id=%s error=%s", device, e, exc_info=True)
            return {"ok": False, "error": str(e), "processed": 0}


def list_system_alarm_actions_since(since_iso: str, limit: int = 3) -> list[dict]:
    """只供下一轮动态 system 注入：读取上一轮之后的系统闹钟动作状态。"""
    since_dt = _parse_any_iso_to_utc(since_iso)
    if since_dt is None:
        return []
    window_start = since_dt - timedelta(minutes=5)
    try:
        max_items = max(1, min(int(limit or 3), 5))
    except Exception:
        max_items = 3
    _ensure_app_actions_bootstrapped()
    try:
        with runtime_sqlite.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM app_actions
                WHERE type = 'create_system_alarm'
                ORDER BY created_at DESC
                LIMIT 20
                """
            ).fetchall()
    except Exception as e:
        logger.warning("list_system_alarm_actions_since failed since=%s error=%s", since_iso, e)
        return []

    out: list[dict] = []
    for row in rows:
        item = _row_to_app_action(row)
        status = str(row["status"] or "pending").strip() or "pending"
        created_dt = _parse_any_iso_to_utc(str(row["created_at"] or ""))
        finished_dt = _parse_any_iso_to_utc(str(row["finished_at"] or ""))
        marker_dt = finished_dt or created_dt
        if marker_dt is None or marker_dt <= window_start:
            continue
        item["status"] = status
        if status == "pending":
            item["finishedAt"] = ""
            item["result"] = {}
            item["error"] = ""
        out.append(item)
        if len(out) >= max_items:
            break
    return list(reversed(out))


def get_system_alarm_action(action_id: str) -> Optional[dict]:
    """按动作 id 读取单条系统闹钟动作状态，用于下一轮回执注入。"""
    aid = str(action_id or "").strip()
    if not aid:
        return None
    _ensure_app_actions_bootstrapped()
    try:
        with runtime_sqlite.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM app_actions
                WHERE id = ?
                  AND type = 'create_system_alarm'
                LIMIT 1
                """,
                (aid,),
            ).fetchone()
    except Exception as e:
        logger.warning("get_system_alarm_action failed id=%s error=%s", aid, e)
        return None
    if row is None:
        return None
    item = _row_to_app_action(row)
    status = str(row["status"] or "pending").strip() or "pending"
    item["status"] = status
    if status == "pending":
        item["finishedAt"] = ""
        item["result"] = {}
        item["error"] = ""
    return item
