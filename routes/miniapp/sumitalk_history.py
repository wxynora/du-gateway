import hashlib
import json
import logging
import threading

from flask import jsonify, request

from config import DATA_DIR
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing


sumitalk_logger = logging.getLogger("sumitalk")
_SUMITALK_HISTORY_FILE = DATA_DIR / "sumitalk_display_histories.json"
_SUMITALK_HISTORY_LOCK = threading.Lock()
_SUMITALK_HISTORY_MAX_MESSAGES = 80


def _load_sumitalk_histories() -> dict:
    try:
        if not _SUMITALK_HISTORY_FILE.exists():
            return {}
        with _SUMITALK_HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        sumitalk_logger.warning("history_load_failed path=%s error=%s", _SUMITALK_HISTORY_FILE, e)
        return {}


def _save_sumitalk_histories(data: dict) -> bool:
    try:
        _SUMITALK_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _SUMITALK_HISTORY_FILE.open("w", encoding="utf-8") as f:
            json.dump(data or {}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        sumitalk_logger.exception(
            "history_save_exception path=%s device_rows=%s",
            _SUMITALK_HISTORY_FILE,
            len(data or {}) if isinstance(data, dict) else 0,
        )
        return False


def _get_sumitalk_history_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _normalize_sumitalk_history_window_id(value) -> str:
    return str(value or "").strip()[:160]


def _get_sumitalk_history_window_id_from_args() -> str:
    return _normalize_sumitalk_history_window_id(
        request.args.get("window_id") or request.args.get("history_window_id") or ""
    )


def _get_sumitalk_history_window_id_from_body(body: dict) -> str:
    return _normalize_sumitalk_history_window_id(
        (body or {}).get("window_id") or (body or {}).get("history_window_id") or ""
    )


def _sumitalk_history_storage_key(device_id: str, window_id: str = "") -> str:
    did = str(device_id or "").strip()
    wid = _normalize_sumitalk_history_window_id(window_id)
    return did if not wid else f"{did}::{wid}"


def _sumitalk_request_brief() -> dict:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return {
        "remote": request.remote_addr or "",
        "ua": (request.headers.get("User-Agent") or "")[:120],
        "subject": str(payload.get("sub") or "").strip(),
    }


def _normalize_sumitalk_messages(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant", "benben"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        reasoning = str(item.get("reasoning") or "").strip()
        try:
            token_count = int(item.get("tokenCount") or 0)
        except Exception:
            token_count = 0
        created_at = str(item.get("createdAt") or item.get("created_at") or "").strip() or now_beijing_iso()
        msg_id = str(item.get("id") or "").strip() or f"{role}-{created_at}-{len(out)}"
        row = {
            "id": msg_id,
            "role": role,
            "content": content,
            "createdAt": created_at,
        }
        if reasoning:
            row["reasoning"] = reasoning
        if token_count > 0:
            row["tokenCount"] = token_count
        out.append(row)
    return out[-_SUMITALK_HISTORY_MAX_MESSAGES:]


def _merge_sumitalk_messages(*groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for items in groups:
        for item in _normalize_sumitalk_messages(items or []):
            key = (
                str(item.get("id") or "").strip(),
                str(item.get("role") or "").strip(),
                str(item.get("createdAt") or "").strip(),
                str(item.get("content") or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

    def _sort_key(row: dict) -> tuple[float, str]:
        created_at = str((row or {}).get("createdAt") or "").strip()
        dt = parse_iso_to_beijing(created_at)
        return (dt.timestamp() if dt else 0.0), str((row or {}).get("id") or "").strip()

    merged.sort(key=_sort_key)
    return merged[-_SUMITALK_HISTORY_MAX_MESSAGES:]


def _sumitalk_message_poll_key(msg: dict) -> str:
    msg_id = str((msg or {}).get("id") or "").strip()
    if msg_id:
        return msg_id
    created_at = str((msg or {}).get("createdAt") or "").strip()
    content = str((msg or {}).get("content") or "").strip()
    digest = hashlib.sha1(f"{created_at}\n{content}".encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{created_at}|{digest}"


def _latest_sumitalk_assistant_message(messages: list[dict]) -> dict | None:
    for item in reversed(_normalize_sumitalk_messages(messages or [])):
        if str(item.get("role") or "").strip().lower() == "assistant":
            return item
    return None


def register_routes(bp) -> None:
    @bp.route("/sumitalk-history", methods=["GET"])
    def miniapp_sumitalk_history():
        device_id = _get_sumitalk_history_device_id()
        if not device_id:
            meta = _sumitalk_request_brief()
            sumitalk_logger.warning(
                "history_get_reject reason=missing_device_id remote=%s subject=%s ua=%s",
                meta["remote"],
                meta["subject"],
                meta["ua"],
            )
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        window_id = _get_sumitalk_history_window_id_from_args()
        storage_key = _sumitalk_history_storage_key(device_id, window_id)
        with _SUMITALK_HISTORY_LOCK:
            data = _load_sumitalk_histories()
            row = data.get(storage_key) if isinstance(data, dict) else None
        messages = _normalize_sumitalk_messages((row or {}).get("messages") or [])
        meta = _sumitalk_request_brief()
        sumitalk_logger.info(
            "history_get_ok device_id=%s window_id=%s messages=%s updated_at=%s known_devices=%s file_exists=%s remote=%s ua=%s",
            device_id,
            window_id,
            len(messages),
            str((row or {}).get("updated_at") or "").strip(),
            len(data or {}) if isinstance(data, dict) else 0,
            _SUMITALK_HISTORY_FILE.exists(),
            meta["remote"],
            meta["ua"],
        )
        return jsonify({
            "ok": True,
            "device_id": device_id,
            "window_id": window_id,
            "messages": messages,
            "count": len(messages),
            "updated_at": str((row or {}).get("updated_at") or "").strip(),
        })

    @bp.route("/sumitalk-history/latest", methods=["GET"])
    def miniapp_sumitalk_history_latest():
        device_id = _get_sumitalk_history_device_id()
        if not device_id:
            meta = _sumitalk_request_brief()
            sumitalk_logger.warning(
                "history_latest_reject reason=missing_device_id remote=%s subject=%s ua=%s",
                meta["remote"],
                meta["subject"],
                meta["ua"],
            )
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        after_key = str(request.args.get("after_key") or request.args.get("after") or "").strip()
        window_id = _get_sumitalk_history_window_id_from_args()
        storage_key = _sumitalk_history_storage_key(device_id, window_id)
        with _SUMITALK_HISTORY_LOCK:
            data = _load_sumitalk_histories()
            row = data.get(storage_key) if isinstance(data, dict) else None
        messages = _normalize_sumitalk_messages((row or {}).get("messages") or [])
        latest = _latest_sumitalk_assistant_message(messages)
        latest_key = _sumitalk_message_poll_key(latest or {}) if latest else ""
        has_new = bool(latest_key and latest_key != after_key)
        meta = _sumitalk_request_brief()
        sumitalk_logger.info(
            "history_latest_ok device_id=%s window_id=%s count=%s has_new=%s latest_key=%s after_key=%s updated_at=%s remote=%s ua=%s",
            device_id,
            window_id,
            len(messages),
            has_new,
            latest_key[:32],
            after_key[:32],
            str((row or {}).get("updated_at") or "").strip(),
            meta["remote"],
            meta["ua"],
        )
        return jsonify({
            "ok": True,
            "device_id": device_id,
            "window_id": window_id,
            "count": len(messages),
            "updated_at": str((row or {}).get("updated_at") or "").strip(),
            "latest_key": latest_key,
            "has_new": has_new,
            "message": latest if has_new else None,
            "messages": [latest] if has_new and latest else [],
        })

    @bp.route("/sumitalk-history", methods=["PUT"])
    def miniapp_sumitalk_history_save():
        device_id = _get_sumitalk_history_device_id()
        if not device_id:
            meta = _sumitalk_request_brief()
            sumitalk_logger.warning(
                "history_put_reject reason=missing_device_id remote=%s subject=%s ua=%s",
                meta["remote"],
                meta["subject"],
                meta["ua"],
            )
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        body = request.get_json(silent=True) or {}
        window_id = _get_sumitalk_history_window_id_from_body(body)
        storage_key = _sumitalk_history_storage_key(device_id, window_id)
        incoming = body.get("messages") or []
        incoming_count = len(incoming) if isinstance(incoming, list) else 0
        with _SUMITALK_HISTORY_LOCK:
            data = _load_sumitalk_histories()
            current_row = data.get(storage_key) if isinstance(data, dict) else None
            current_count = len((current_row or {}).get("messages") or [])
            messages = _merge_sumitalk_messages(
                (current_row or {}).get("messages") or [],
                incoming,
            )
            payload = {
                "device_id": device_id,
                "window_id": window_id,
                "updated_at": now_beijing_iso(),
                "messages": messages,
            }
            data[storage_key] = payload
            ok = _save_sumitalk_histories(data)
        if not ok:
            meta = _sumitalk_request_brief()
            sumitalk_logger.error(
                "history_put_failed device_id=%s window_id=%s incoming=%s current=%s merged=%s remote=%s ua=%s",
                device_id,
                window_id,
                incoming_count,
                current_count,
                len(messages),
                meta["remote"],
                meta["ua"],
            )
            return jsonify({"ok": False, "error": "保存失败"}), 500
        meta = _sumitalk_request_brief()
        sumitalk_logger.info(
            "history_put_ok device_id=%s window_id=%s incoming=%s current=%s merged=%s updated_at=%s remote=%s ua=%s",
            device_id,
            window_id,
            incoming_count,
            current_count,
            len(messages),
            payload["updated_at"],
            meta["remote"],
            meta["ua"],
        )
        return jsonify({"ok": True, "device_id": device_id, "window_id": window_id, "count": len(messages), "updated_at": payload["updated_at"]})

    @bp.route("/sumitalk-history/migrate", methods=["POST"])
    def miniapp_sumitalk_history_migrate():
        old_device_id = _get_sumitalk_history_device_id()
        if not old_device_id:
            meta = _sumitalk_request_brief()
            sumitalk_logger.warning(
                "history_migrate_reject reason=missing_old_device_id remote=%s subject=%s ua=%s",
                meta["remote"],
                meta["subject"],
                meta["ua"],
            )
            return jsonify({"ok": False, "error": "缺少旧设备标识"}), 400
        body = request.get_json(silent=True) or {}
        new_device_id = str(body.get("new_device_id") or "").strip()
        if not new_device_id:
            meta = _sumitalk_request_brief()
            sumitalk_logger.warning(
                "history_migrate_reject reason=missing_new_device_id old_device_id=%s remote=%s ua=%s",
                old_device_id,
                meta["remote"],
                meta["ua"],
            )
            return jsonify({"ok": False, "error": "缺少新设备标识"}), 400
        if new_device_id == old_device_id:
            sumitalk_logger.info("history_migrate_skip reason=same_device device_id=%s", new_device_id)
            return jsonify({"ok": True, "device_id": new_device_id, "count": 0, "copied": False})
        migrated_rows: list[dict] = []
        with _SUMITALK_HISTORY_LOCK:
            data = _load_sumitalk_histories()
            old_keys = [
                key for key in list(data.keys())
                if key == old_device_id or str(key).startswith(f"{old_device_id}::")
            ] if isinstance(data, dict) else []
            for old_key in old_keys:
                suffix = str(old_key)[len(old_device_id):]
                window_id = suffix[2:] if suffix.startswith("::") else ""
                new_key = f"{new_device_id}{suffix}"
                old_row = data.get(old_key) if isinstance(data, dict) else None
                new_row = data.get(new_key) if isinstance(data, dict) else None
                merged_messages = _merge_sumitalk_messages(
                    (old_row or {}).get("messages") or [],
                    (new_row or {}).get("messages") or [],
                )
                payload = {
                    "device_id": new_device_id,
                    "window_id": window_id,
                    "updated_at": now_beijing_iso(),
                    "messages": merged_messages,
                }
                data[new_key] = payload
                migrated_rows.append({
                    "old_key": old_key,
                    "new_key": new_key,
                    "window_id": window_id,
                    "old_count": len((old_row or {}).get("messages") or []),
                    "new_count": len((new_row or {}).get("messages") or []),
                    "merged_count": len(merged_messages),
                    "updated_at": payload["updated_at"],
                })
            ok = _save_sumitalk_histories(data)
        if not ok:
            meta = _sumitalk_request_brief()
            total_old = sum(int(row.get("old_count") or 0) for row in migrated_rows)
            total_new = sum(int(row.get("new_count") or 0) for row in migrated_rows)
            total_merged = sum(int(row.get("merged_count") or 0) for row in migrated_rows)
            sumitalk_logger.error(
                "history_migrate_failed old_device_id=%s new_device_id=%s rows=%s old_count=%s new_count=%s merged=%s remote=%s ua=%s",
                old_device_id,
                new_device_id,
                len(migrated_rows),
                total_old,
                total_new,
                total_merged,
                meta["remote"],
                meta["ua"],
            )
            return jsonify({"ok": False, "error": "迁移失败"}), 500
        meta = _sumitalk_request_brief()
        total_old = sum(int(row.get("old_count") or 0) for row in migrated_rows)
        total_new = sum(int(row.get("new_count") or 0) for row in migrated_rows)
        total_merged = sum(int(row.get("merged_count") or 0) for row in migrated_rows)
        latest_updated_at = str((migrated_rows[-1] if migrated_rows else {}).get("updated_at") or "").strip()
        sumitalk_logger.info(
            "history_migrate_ok old_device_id=%s new_device_id=%s rows=%s old_count=%s new_count=%s merged=%s copied=%s updated_at=%s remote=%s ua=%s",
            old_device_id,
            new_device_id,
            len(migrated_rows),
            total_old,
            total_new,
            total_merged,
            bool(total_old),
            latest_updated_at,
            meta["remote"],
            meta["ua"],
        )
        return jsonify(
            {
                "ok": True,
                "old_device_id": old_device_id,
                "device_id": new_device_id,
                "count": total_merged,
                "rows": len(migrated_rows),
                "copied": bool(total_old),
                "updated_at": latest_updated_at,
            }
        )
