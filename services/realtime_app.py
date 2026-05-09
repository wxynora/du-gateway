from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from config import DATA_DIR
from services import codex_group_chat
from storage import r2_store
from storage.miniapp_panel_store import is_trusted_device, touch_trusted_device
from utils.miniapp_panel_auth import panel_auth_enabled, verify_panel_token


logger = logging.getLogger("realtime")

app = FastAPI(title="du-gateway realtime", version="0.1.0")

_SUMITALK_HISTORY_FILE = DATA_DIR / "sumitalk_display_histories.json"
_POLL_INTERVAL_SECONDS = max(1.0, float(os.environ.get("REALTIME_POLL_INTERVAL_SECONDS", "5") or "5"))
_FAIL_BACKOFF_BASE_SECONDS = max(1.0, float(os.environ.get("REALTIME_FAIL_BACKOFF_BASE_SECONDS", "3") or "3"))
_MAX_BACKOFF_SECONDS = max(5.0, float(os.environ.get("REALTIME_MAX_BACKOFF_SECONDS", "60") or "60"))
_ACTION_LIMIT = max(1, int(os.environ.get("REALTIME_ACTION_LIMIT", "5") or "5"))
_CODEX_GROUP_TASK_LIMIT = max(1, int(os.environ.get("REALTIME_CODEX_GROUP_TASK_LIMIT", "50") or "50"))


def _bearer_from_header(raw: str) -> str:
    value = str(raw or "").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def _message_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif "content" in item:
                    parts.append(_message_content_to_text(item.get("content")))
        return "".join(parts).strip()
    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text") or "").strip()
        if "text" in content:
            return str(content.get("text") or "").strip()
        if "content" in content:
            return _message_content_to_text(content.get("content"))
    return str(content).strip()


def _load_history_for_device(device_id: str) -> dict:
    did = str(device_id or "").strip()
    if not did or not _SUMITALK_HISTORY_FILE.exists():
        return {}
    try:
        with _SUMITALK_HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
        if not isinstance(data, dict):
            return {}
        row = data.get(did)
        return row if isinstance(row, dict) else {}
    except Exception as e:
        logger.warning("load history failed device_id=%s error=%s", did, e)
        return {}


def _latest_assistant_message(device_id: str) -> dict:
    row = _load_history_for_device(device_id)
    messages = row.get("messages") if isinstance(row.get("messages"), list) else []
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").strip().lower() != "assistant":
            continue
        content = _message_content_to_text(item.get("content"))
        if not content:
            continue
        msg_id = str(item.get("id") or "").strip()
        created_at = str(item.get("createdAt") or item.get("created_at") or "").strip()
        digest = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:16]
        key = msg_id or f"{created_at}|{digest}"
        return {
            "key": key,
            "id": msg_id,
            "createdAt": created_at,
            "content": content,
            "preview": content[:500],
        }
    return {}


def _codex_group_tasks_for_device(device_id: str) -> list[dict]:
    did = str(device_id or "").strip()
    if not did:
        return []
    try:
        tasks = codex_group_chat.list_tasks(limit=_CODEX_GROUP_TASK_LIMIT)
    except Exception as e:
        logger.warning("load codex group tasks failed device_id=%s error=%s", did, e)
        return []
    out: list[dict] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if str(task.get("reply_target") or "").strip() != did:
            continue
        task_id = str(task.get("id") or "").strip()
        if not task_id:
            continue
        out.append(task)
    return out


def _codex_group_task_state_key(task: dict) -> str:
    status_value = str(task.get("status") or "").strip()
    updated_at = str(task.get("updated_at") or task.get("finished_at") or task.get("claimed_at") or task.get("created_at") or "").strip()
    response_len = len(str(task.get("response") or ""))
    error_len = len(str(task.get("error") or ""))
    return f"{status_value}|{updated_at}|{response_len}|{error_len}"


def _verify_ws(websocket: WebSocket) -> tuple[bool, str, str]:
    token = (
        _bearer_from_header(websocket.headers.get("authorization") or "")
        or str(websocket.headers.get("x-panel-token") or "").strip()
        or str(websocket.query_params.get("panel_token") or "").strip()
    )
    query_device_id = str(websocket.query_params.get("device_id") or "").strip()
    if not panel_auth_enabled():
        if query_device_id:
            return True, query_device_id, ""
        return False, "", "device_id_missing"

    ok, payload, code = verify_panel_token(token)
    if not ok:
        return False, "", code or "panel_token_invalid"

    payload_device_id = str((payload or {}).get("device_id") or "").strip()
    device_id = payload_device_id or query_device_id
    if not device_id:
        return False, "", "device_id_missing"
    if payload_device_id and query_device_id and payload_device_id != query_device_id:
        return False, "", "device_id_mismatch"
    if not payload_device_id and not is_trusted_device(device_id):
        return False, "", "not_trusted"
    touch_trusted_device(device_id)
    return True, device_id, ""


def _verify_token_for_device(token: str, device_id: str) -> tuple[bool, str, str]:
    did = str(device_id or "").strip()
    if not panel_auth_enabled():
        return (True, did, "") if did else (False, "", "device_id_missing")
    ok, payload, code = verify_panel_token(token)
    if not ok:
        return False, "", code or "panel_token_invalid"
    payload_device_id = str((payload or {}).get("device_id") or "").strip()
    if payload_device_id:
        if did and did != payload_device_id:
            return False, "", "device_id_mismatch"
        did = payload_device_id
    if not did:
        return False, "", "device_id_missing"
    if not payload_device_id and not is_trusted_device(did):
        return False, "", "not_trusted"
    touch_trusted_device(did)
    return True, did, ""


async def _send_json(websocket: WebSocket, payload: dict) -> None:
    await websocket.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


async def _receiver_loop(websocket: WebSocket, device_id: str) -> None:
    while True:
        raw = await websocket.receive_text()
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            await _send_json(websocket, {"type": "error", "error": "invalid_json"})
            continue
        kind = str(data.get("type") or "").strip()
        if kind in {"ping", "heartbeat"}:
            await _send_json(websocket, {"type": "pong", "ts": int(time.time())})
            continue
        if kind in {"device_action_results", "device_actions_done"}:
            results = data.get("results")
            if not isinstance(results, list):
                await _send_json(websocket, {"type": "device_action_results_ack", "ok": False, "error": "results must be list"})
                continue
            result = await asyncio.to_thread(r2_store.report_app_actions, results, device_id=device_id)
            await _send_json(websocket, {"type": "device_action_results_ack", **(result or {})})
            continue
        await _send_json(websocket, {"type": "error", "error": f"unknown_type:{kind or '(empty)'}"})


async def _sender_loop(websocket: WebSocket, device_id: str) -> None:
    last_message_key = str(websocket.query_params.get("last_message_key") or "").strip()
    last_codex_task_states: dict[str, str] = {}
    if not last_message_key:
        latest = await asyncio.to_thread(_latest_assistant_message, device_id)
        last_message_key = str(latest.get("key") or "")
        await _send_json(websocket, {"type": "ready", "device_id": device_id, "latest_message_key": last_message_key})

    failures = 0
    while True:
        try:
            latest = await asyncio.to_thread(_latest_assistant_message, device_id)
            latest_key = str(latest.get("key") or "")
            if latest_key and latest_key != last_message_key:
                last_message_key = latest_key
                await _send_json(websocket, {"type": "assistant_message", "message": latest})

            actions = await asyncio.to_thread(r2_store.poll_app_actions, device_id=device_id, limit=_ACTION_LIMIT)
            pending = actions.get("actions") if isinstance(actions, dict) else None
            if isinstance(pending, list) and pending:
                await _send_json(websocket, {"type": "device_actions", "actions": pending})

            codex_tasks = await asyncio.to_thread(_codex_group_tasks_for_device, device_id)
            for task in codex_tasks:
                task_id = str(task.get("id") or "").strip()
                if not task_id:
                    continue
                state_key = _codex_group_task_state_key(task)
                if not state_key or last_codex_task_states.get(task_id) == state_key:
                    continue
                last_codex_task_states[task_id] = state_key
                await _send_json(websocket, {"type": "codex_group_chat_task", "task": task})

            failures = 0
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        except WebSocketDisconnect:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            failures += 1
            logger.warning("realtime sender failed device_id=%s failures=%s error=%s", device_id, failures, e)
            delay = min(_MAX_BACKOFF_SECONDS, _FAIL_BACKOFF_BASE_SECONDS * (2 ** min(failures, 5)))
            await asyncio.sleep(delay)


@app.get("/health")
async def health():
    return {"ok": True, "service": "du-gateway-realtime"}


@app.get("/realtime/latest")
async def realtime_latest(
    device_id: str = "",
    panel_token: str = "",
    authorization: str = Header(default=""),
    x_panel_token: str = Header(default="", alias="X-Panel-Token"),
):
    token = _bearer_from_header(authorization) or str(x_panel_token or "").strip() or str(panel_token or "").strip()
    ok, did, code = _verify_token_for_device(token, device_id)
    if not ok:
        http_status = 503 if code == "panel_auth_misconfigured" else (403 if code in {"not_trusted", "device_id_mismatch"} else 401)
        return JSONResponse({"ok": False, "error": code}, status_code=http_status)
    return {"ok": True, "device_id": did, "message": await asyncio.to_thread(_latest_assistant_message, did)}


@app.websocket("/ws/device")
async def websocket_device(websocket: WebSocket):
    ok, device_id, code = _verify_ws(websocket)
    if not ok:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=code[:120])
        return

    await websocket.accept()
    logger.info("device websocket connected device_id=%s client=%s", device_id, websocket.client)
    receiver = asyncio.create_task(_receiver_loop(websocket, device_id))
    sender = asyncio.create_task(_sender_loop(websocket, device_id))
    try:
        done, pending = await asyncio.wait({receiver, sender}, return_when=asyncio.FIRST_EXCEPTION)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        receiver.cancel()
        sender.cancel()
        logger.info("device websocket disconnected device_id=%s", device_id)
