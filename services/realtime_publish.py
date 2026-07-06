from __future__ import annotations

import hashlib
import logging
import os
from typing import Any
from uuid import uuid4

import requests


logger = logging.getLogger("realtime_publish")

_PUBLISH_ENABLED = os.environ.get("REALTIME_PUBLISH_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
_PUBLISH_URL = os.environ.get("REALTIME_PUBLISH_URL", "http://127.0.0.1:5010/internal/publish").strip()
_PUBLISH_TIMEOUT_SECONDS = max(0.1, float(os.environ.get("REALTIME_PUBLISH_TIMEOUT_SECONDS", "0.6") or "0.6"))
_INTERNAL_TOKEN = (
    os.environ.get("REALTIME_INTERNAL_TOKEN", "").strip()
    or os.environ.get("MINIAPP_PANEL_SIGNING_SECRET", "").strip()
)


def _post_event(payload: dict) -> bool:
    if not _PUBLISH_ENABLED or not _PUBLISH_URL:
        return False
    try:
        headers = {"Content-Type": "application/json"}
        if _INTERNAL_TOKEN:
            headers["X-Realtime-Token"] = _INTERNAL_TOKEN
        resp = requests.post(_PUBLISH_URL, headers=headers, json=payload, timeout=_PUBLISH_TIMEOUT_SECONDS)
        if 200 <= resp.status_code < 300:
            return True
        logger.warning(
            "realtime publish non-2xx status=%s type=%s device_id=%s preview=%s",
            resp.status_code,
            payload.get("type"),
            payload.get("device_id"),
            resp.text[:200],
        )
        return False
    except Exception as e:
        logger.debug(
            "realtime publish failed type=%s device_id=%s error=%s",
            payload.get("type"),
            payload.get("device_id"),
            e,
        )
        return False


def _message_preview(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()[:500]
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif "text" in item:
                    parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()[:500]
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "").strip()[:500]
    return str(content).strip()[:500]


def publish_assistant_message(device_id: str, message: dict, window_id: str = "") -> bool:
    did = str(device_id or "").strip()
    if not did or not isinstance(message, dict):
        return False
    msg = dict(message)
    if not str(msg.get("key") or "").strip():
        msg_id = str(msg.get("id") or "").strip()
        created_at = str(msg.get("createdAt") or msg.get("created_at") or "").strip()
        content = _message_preview(msg.get("content"))
        digest = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:16]
        msg["key"] = msg_id or f"{created_at}|{digest}"
    if not str(msg.get("preview") or "").strip():
        msg["preview"] = _message_preview(msg.get("content"))
    return _post_event({
        "type": "assistant_message",
        "event_id": uuid4().hex,
        "device_id": did,
        "window_id": str(window_id or "").strip(),
        "message": msg,
    })


def publish_device_actions(device_id: str = "", actions: list[dict] | None = None) -> bool:
    rows = [row for row in (actions or []) if isinstance(row, dict)]
    if not rows:
        return False
    return _post_event({
        "type": "device_actions",
        "event_id": uuid4().hex,
        "device_id": str(device_id or "").strip(),
        "actions": rows,
    })


def publish_chat_ui_device_actions(device_id: str = "", window_id: str = "", actions: list[dict] | None = None) -> bool:
    rows = [row for row in (actions or []) if isinstance(row, dict)]
    if not rows:
        return False
    return _post_event({
        "type": "chat_ui_device_actions",
        "event_id": uuid4().hex,
        "device_id": str(device_id or "").strip(),
        "window_id": str(window_id or "").strip(),
        "actions": rows,
    })


def publish_codex_group_task(task: dict | None) -> bool:
    if not isinstance(task, dict):
        return False
    return _post_event({
        "type": "codex_group_chat_task",
        "event_id": uuid4().hex,
        "device_id": str(task.get("reply_target") or "").strip(),
        "task": task,
    })


def publish_sumitalk_chat_event(device_id: str, event: dict, window_id: str = "") -> bool:
    did = str(device_id or "").strip()
    if not did or not isinstance(event, dict):
        return False
    return _post_event({
        "type": "sumitalk_chat_event",
        "event_id": str(event.get("event_id") or uuid4().hex),
        "device_id": did,
        "window_id": str(window_id or event.get("window_id") or "").strip(),
        "event": event,
    })
