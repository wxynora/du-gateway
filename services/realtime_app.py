from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from services import codex_group_chat
from services.sumitalk_history_file import SUMITALK_HISTORY_FILE as _SUMITALK_HISTORY_FILE
from services.sumitalk_history_file import load_sumitalk_histories
from storage import r2_store
from storage.miniapp_panel_store import is_trusted_device, touch_trusted_device
from utils.miniapp_panel_auth import panel_auth_enabled, verify_panel_token


logger = logging.getLogger("realtime")

app = FastAPI(title="du-gateway realtime", version="0.1.0")

_SUMITALK_MAIN_WINDOW_ID = "sumitalk-main"
_POLL_INTERVAL_SECONDS = max(1.0, float(os.environ.get("REALTIME_POLL_INTERVAL_SECONDS", "60") or "60"))
_FAIL_BACKOFF_BASE_SECONDS = max(1.0, float(os.environ.get("REALTIME_FAIL_BACKOFF_BASE_SECONDS", "3") or "3"))
_MAX_BACKOFF_SECONDS = max(5.0, float(os.environ.get("REALTIME_MAX_BACKOFF_SECONDS", "60") or "60"))
_ACTION_LIMIT = max(1, int(os.environ.get("REALTIME_ACTION_LIMIT", "5") or "5"))
_CODEX_GROUP_TASK_LIMIT = max(1, int(os.environ.get("REALTIME_CODEX_GROUP_TASK_LIMIT", "50") or "50"))
_INTERNAL_TOKEN = (
    os.environ.get("REALTIME_INTERNAL_TOKEN", "").strip()
    or os.environ.get("MINIAPP_PANEL_SIGNING_SECRET", "").strip()
)


class RealtimeConnection:
    def __init__(self, websocket: WebSocket, device_id: str, window_id: str) -> None:
        self.websocket = websocket
        self.device_id = str(device_id or "").strip()
        self.window_id = str(window_id or "").strip() or _SUMITALK_MAIN_WINDOW_ID
        self.send_lock = asyncio.Lock()
        self.last_codex_task_states: dict[str, str] = {}

    async def send_json(self, payload: dict) -> None:
        async with self.send_lock:
            await self.websocket.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


class RealtimeConnectionManager:
    def __init__(self) -> None:
        self._connections: set[RealtimeConnection] = set()
        self._lock = asyncio.Lock()

    async def add(self, conn: RealtimeConnection) -> None:
        async with self._lock:
            self._connections.add(conn)

    async def remove(self, conn: RealtimeConnection) -> None:
        async with self._lock:
            self._connections.discard(conn)

    async def broadcast(self, payload: dict, device_id: str = "", window_id: str = "") -> int:
        did = str(device_id or "").strip()
        wid = str(window_id or "").strip()
        async with self._lock:
            targets = [
                conn
                for conn in self._connections
                if (not did or conn.device_id == did)
                and (not wid or conn.window_id == wid)
            ]
        if str((payload or {}).get("type") or "").strip() in {"device_actions", "chat_ui_device_actions"}:
            logger.info(
                "device_actions_broadcast_targets target_device=%s target_window=%s targets=%s",
                did,
                wid,
                [conn.device_id for conn in targets],
            )
        sent = 0
        dead: list[RealtimeConnection] = []
        for conn in targets:
            try:
                await conn.send_json(payload)
                sent += 1
            except Exception as e:
                logger.warning(
                    "realtime broadcast failed device_id=%s window_id=%s error=%s",
                    conn.device_id,
                    conn.window_id,
                    e,
                )
                dead.append(conn)
        if dead:
            async with self._lock:
                for conn in dead:
                    self._connections.discard(conn)
        return sent

    async def stats(self) -> dict:
        async with self._lock:
            rows = list(self._connections)
        by_device: dict[str, int] = {}
        for conn in rows:
            by_device[conn.device_id] = by_device.get(conn.device_id, 0) + 1
        return {"connections": len(rows), "devices": by_device}


_connections = RealtimeConnectionManager()


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


def _history_storage_key(device_id: str, window_id: str = _SUMITALK_MAIN_WINDOW_ID) -> str:
    did = str(device_id or "").strip()
    wid = str(window_id or "").strip() or _SUMITALK_MAIN_WINDOW_ID
    return f"{did}::{wid}" if wid else did


def _history_candidate_keys(device_id: str, window_id: str = _SUMITALK_MAIN_WINDOW_ID) -> list[str]:
    did = str(device_id or "").strip()
    wid = str(window_id or "").strip() or _SUMITALK_MAIN_WINDOW_ID
    if not did:
        return []
    keys = [_history_storage_key(did, wid)]
    if wid == _SUMITALK_MAIN_WINDOW_ID:
        keys.append(did)
    out = []
    seen = set()
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _sort_history_messages(messages: list[dict]) -> list[dict]:
    def _key(row: dict) -> tuple[str, str]:
        return (
            str((row or {}).get("createdAt") or (row or {}).get("created_at") or ""),
            str((row or {}).get("id") or ""),
        )

    return sorted([m for m in messages if isinstance(m, dict)], key=_key)


def _load_history_for_device(device_id: str, window_id: str = _SUMITALK_MAIN_WINDOW_ID) -> dict:
    did = str(device_id or "").strip()
    if not did or not _SUMITALK_HISTORY_FILE.exists():
        return {}
    try:
        data = load_sumitalk_histories()
        if not isinstance(data, dict):
            return {}
        rows = [data.get(key) for key in _history_candidate_keys(did, window_id)]
        rows = [row for row in rows if isinstance(row, dict)]
        if not rows:
            return {}
        messages = []
        seen = set()
        for row in rows:
            for item in row.get("messages") or []:
                if not isinstance(item, dict):
                    continue
                key = (
                    str(item.get("id") or ""),
                    str(item.get("role") or ""),
                    str(item.get("createdAt") or ""),
                    str(item.get("content") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                messages.append(item)
        return {"messages": _sort_history_messages(messages)}
    except Exception as e:
        logger.warning("load history failed device_id=%s error=%s", did, e)
        return {}


def _latest_assistant_message(device_id: str, window_id: str = _SUMITALK_MAIN_WINDOW_ID) -> dict:
    row = _load_history_for_device(device_id, window_id=window_id)
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


async def _send_json(conn: RealtimeConnection, payload: dict) -> None:
    await conn.send_json(payload)


async def _receiver_loop(conn: RealtimeConnection) -> None:
    while True:
        raw = await conn.websocket.receive_text()
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            await _send_json(conn, {"type": "error", "error": "invalid_json"})
            continue
        kind = str(data.get("type") or "").strip()
        if kind in {"ping", "heartbeat"}:
            await _send_json(conn, {"type": "pong", "ts": int(time.time())})
            continue
        if kind in {"device_action_results", "device_actions_done"}:
            results = data.get("results")
            if not isinstance(results, list):
                await _send_json(conn, {"type": "device_action_results_ack", "ok": False, "error": "results must be list"})
                continue
            result = await asyncio.to_thread(r2_store.report_app_actions, results, device_id=conn.device_id)
            logger.info(
                "device_action_results_realtime device_id=%s count=%s ok=%s processed=%s ids=%s statuses=%s",
                conn.device_id,
                len(results),
                bool(isinstance(result, dict) and result.get("ok")),
                (result or {}).get("processed") if isinstance(result, dict) else "",
                [str((x or {}).get("id") or "") for x in results if isinstance(x, dict)],
                [str((x or {}).get("status") or "") for x in results if isinstance(x, dict)],
            )
            if isinstance(result, dict) and result.get("ok"):
                try:
                    from routes.miniapp.device_actions import _wake_du_for_device_action_results

                    queued = await asyncio.to_thread(
                        _wake_du_for_device_action_results,
                        conn.device_id,
                        result.get("items") or [],
                    )
                    if queued:
                        result["proactive_wakeup_queued"] = queued
                except Exception as e:
                    logger.warning("device action realtime wake failed device_id=%s error=%s", conn.device_id, e)
            await _send_json(conn, {"type": "device_action_results_ack", **(result or {})})
            continue
        await _send_json(conn, {"type": "error", "error": f"unknown_type:{kind or '(empty)'}"})


async def _sender_loop(conn: RealtimeConnection) -> None:
    last_message_key = str(conn.websocket.query_params.get("last_message_key") or "").strip()
    if not last_message_key:
        latest = await asyncio.to_thread(_latest_assistant_message, conn.device_id, conn.window_id)
        last_message_key = str(latest.get("key") or "")
        await _send_json(conn, {
            "type": "ready",
            "device_id": conn.device_id,
            "window_id": conn.window_id,
            "latest_message_key": last_message_key,
            "poll_interval_seconds": _POLL_INTERVAL_SECONDS,
        })

    failures = 0
    while True:
        try:
            latest = await asyncio.to_thread(_latest_assistant_message, conn.device_id, conn.window_id)
            latest_key = str(latest.get("key") or "")
            if latest_key and latest_key != last_message_key:
                last_message_key = latest_key
                await _send_json(conn, {"type": "assistant_message", "message": latest, "source": "fallback_poll"})

            actions = await asyncio.to_thread(r2_store.poll_app_actions, device_id=conn.device_id, limit=_ACTION_LIMIT, surface="native")
            pending = actions.get("actions") if isinstance(actions, dict) else None
            if isinstance(pending, list) and pending:
                logger.info(
                    "device_actions_send_realtime device_id=%s source=fallback_poll count=%s ids=%s types=%s",
                    conn.device_id,
                    len(pending),
                    [str((x or {}).get("id") or "") for x in pending if isinstance(x, dict)],
                    [str((x or {}).get("type") or "") for x in pending if isinstance(x, dict)],
                )
                await _send_json(conn, {"type": "device_actions", "actions": pending, "source": "fallback_poll"})

            chat_ui_actions = await asyncio.to_thread(
                r2_store.poll_app_actions,
                device_id=conn.device_id,
                limit=_ACTION_LIMIT,
                surface="chat_ui",
                window_id=conn.window_id,
            )
            chat_ui_pending = chat_ui_actions.get("actions") if isinstance(chat_ui_actions, dict) else None
            if isinstance(chat_ui_pending, list) and chat_ui_pending:
                logger.info(
                    "chat_ui_device_actions_send_realtime device_id=%s window_id=%s source=fallback_poll count=%s ids=%s types=%s",
                    conn.device_id,
                    conn.window_id,
                    len(chat_ui_pending),
                    [str((x or {}).get("id") or "") for x in chat_ui_pending if isinstance(x, dict)],
                    [str((x or {}).get("type") or "") for x in chat_ui_pending if isinstance(x, dict)],
                )
                await _send_json(conn, {"type": "chat_ui_device_actions", "actions": chat_ui_pending, "source": "fallback_poll"})

            codex_tasks = await asyncio.to_thread(_codex_group_tasks_for_device, conn.device_id)
            for task in codex_tasks:
                task_id = str(task.get("id") or "").strip()
                if not task_id:
                    continue
                state_key = _codex_group_task_state_key(task)
                if not state_key or conn.last_codex_task_states.get(task_id) == state_key:
                    continue
                conn.last_codex_task_states[task_id] = state_key
                await _send_json(conn, {"type": "codex_group_chat_task", "task": task, "source": "fallback_poll"})

            failures = 0
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        except WebSocketDisconnect:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            failures += 1
            logger.warning("realtime sender failed device_id=%s failures=%s error=%s", conn.device_id, failures, e)
            delay = min(_MAX_BACKOFF_SECONDS, _FAIL_BACKOFF_BASE_SECONDS * (2 ** min(failures, 5)))
            await asyncio.sleep(delay)


def _is_local_request(request: Request) -> bool:
    host = str((request.client.host if request.client else "") or "").strip()
    return host in {"127.0.0.1", "::1", "localhost"}


def _internal_publish_authorized(request: Request, token: str) -> tuple[bool, str]:
    if not _is_local_request(request):
        return False, "local_only"
    if _INTERNAL_TOKEN and str(token or "").strip() != _INTERNAL_TOKEN:
        return False, "bad_internal_token"
    return True, ""


def _event_payload_from_internal(body: dict) -> tuple[str, str, dict]:
    event_type = str((body or {}).get("type") or "").strip()
    device_id = str((body or {}).get("device_id") or (body or {}).get("deviceId") or "").strip()
    window_id = str((body or {}).get("window_id") or (body or {}).get("windowId") or "").strip()
    payload: dict[str, Any] = {
        "type": event_type,
        "event_id": str((body or {}).get("event_id") or uuid4().hex),
        "source": "publish",
    }
    if event_type == "assistant_message":
        message = (body or {}).get("message")
        payload["message"] = message if isinstance(message, dict) else {}
        if window_id:
            payload["window_id"] = window_id
    elif event_type in {"device_actions", "chat_ui_device_actions"}:
        actions = (body or {}).get("actions")
        payload["actions"] = actions if isinstance(actions, list) else []
        if window_id:
            payload["window_id"] = window_id
    elif event_type == "codex_group_chat_task":
        task = (body or {}).get("task")
        payload["task"] = task if isinstance(task, dict) else {}
    else:
        payload.update({k: v for k, v in (body or {}).items() if k not in {"device_id", "deviceId", "window_id", "windowId"}})
    return device_id, window_id, payload


@app.get("/health")
async def health():
    stats = await _connections.stats()
    return {"ok": True, "service": "du-gateway-realtime", "realtime": stats}


@app.post("/internal/publish")
async def internal_publish(request: Request, x_realtime_token: str = Header(default="", alias="X-Realtime-Token")):
    ok, code = _internal_publish_authorized(request, x_realtime_token)
    if not ok:
        return JSONResponse({"ok": False, "error": code}, status_code=403 if code == "local_only" else 401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "body_must_be_object"}, status_code=400)
    device_id, window_id, payload = _event_payload_from_internal(body)
    if not payload.get("type"):
        return JSONResponse({"ok": False, "error": "missing_type"}, status_code=400)
    sent = await _connections.broadcast(payload, device_id=device_id, window_id=window_id)
    if payload.get("type") in {"device_actions", "chat_ui_device_actions"}:
        actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
        logger.info(
            "device_actions_broadcast type=%s target_device=%s target_window=%s sent=%s count=%s ids=%s types=%s",
            payload.get("type"),
            device_id,
            window_id,
            sent,
            len(actions),
            [str((x or {}).get("id") or "") for x in actions if isinstance(x, dict)],
            [str((x or {}).get("type") or "") for x in actions if isinstance(x, dict)],
        )
    return {"ok": True, "sent": sent, "type": payload.get("type"), "event_id": payload.get("event_id")}


@app.get("/realtime/latest")
async def realtime_latest(
    device_id: str = "",
    window_id: str = _SUMITALK_MAIN_WINDOW_ID,
    panel_token: str = "",
    authorization: str = Header(default=""),
    x_panel_token: str = Header(default="", alias="X-Panel-Token"),
):
    token = _bearer_from_header(authorization) or str(x_panel_token or "").strip() or str(panel_token or "").strip()
    ok, did, code = _verify_token_for_device(token, device_id)
    if not ok:
        http_status = 503 if code == "panel_auth_misconfigured" else (403 if code in {"not_trusted", "device_id_mismatch"} else 401)
        return JSONResponse({"ok": False, "error": code}, status_code=http_status)
    return {"ok": True, "device_id": did, "window_id": window_id or _SUMITALK_MAIN_WINDOW_ID, "message": await asyncio.to_thread(_latest_assistant_message, did, window_id or _SUMITALK_MAIN_WINDOW_ID)}


@app.websocket("/ws/device")
async def websocket_device(websocket: WebSocket):
    ok, device_id, code = _verify_ws(websocket)
    if not ok:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=code[:120])
        return

    await websocket.accept()
    window_id = str(websocket.query_params.get("window_id") or "").strip() or _SUMITALK_MAIN_WINDOW_ID
    conn = RealtimeConnection(websocket, device_id, window_id)
    await _connections.add(conn)
    logger.info("device websocket connected device_id=%s window_id=%s client=%s", device_id, window_id, websocket.client)
    receiver = asyncio.create_task(_receiver_loop(conn))
    sender = asyncio.create_task(_sender_loop(conn))
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
        await _connections.remove(conn)
        logger.info("device websocket disconnected device_id=%s window_id=%s", device_id, window_id)
