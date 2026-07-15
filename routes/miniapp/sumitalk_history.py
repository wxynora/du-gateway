import hashlib
import json
import logging
import threading
import time

from flask import jsonify, request

from services.sumitalk_history_file import (
    SUMITALK_HISTORY_FILE as _SUMITALK_HISTORY_FILE,
    load_sumitalk_histories,
    prune_sumitalk_histories,
    save_sumitalk_histories,
)
from storage.miniapp_panel_store import is_trusted_device, upsert_trusted_device
from utils.miniapp_panel_auth import issue_panel_token, panel_auth_enabled
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing


sumitalk_logger = logging.getLogger("sumitalk")
_SUMITALK_HISTORY_LOCK = threading.Lock()
_SUMITALK_MAIN_WINDOW_ID = "sumitalk-main"
_HISTORY_LATEST_NOOP_LOG_TTL_SECONDS = 60
_HISTORY_LATEST_NOOP_LOG_CACHE: dict[str, float] = {}


def _load_sumitalk_histories() -> dict:
    return load_sumitalk_histories()


def _save_sumitalk_histories(data: dict) -> bool:
    return save_sumitalk_histories(data)


def _get_sumitalk_history_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _normalize_sumitalk_history_window_id(value) -> str:
    return str(value or "").strip()[:160]


def _canonical_sumitalk_history_window_id(value) -> str:
    wid = _normalize_sumitalk_history_window_id(value)
    return wid or _SUMITALK_MAIN_WINDOW_ID


def _get_sumitalk_history_window_id_from_args() -> str:
    return _normalize_sumitalk_history_window_id(
        request.args.get("window_id") or request.args.get("history_window_id") or ""
    )


def _should_log_history_latest(device_id: str, window_id: str, has_new: bool, latest_key: str, after_key: str) -> bool:
    if has_new:
        return True
    now = time.time()
    if len(_HISTORY_LATEST_NOOP_LOG_CACHE) > 512:
        cutoff = now - _HISTORY_LATEST_NOOP_LOG_TTL_SECONDS
        for key, ts in list(_HISTORY_LATEST_NOOP_LOG_CACHE.items()):
            if ts < cutoff:
                _HISTORY_LATEST_NOOP_LOG_CACHE.pop(key, None)
    cache_key = "|".join(
        [
            str(device_id or "").strip(),
            str(window_id or "").strip(),
            str(latest_key or "").strip()[:64],
            str(after_key or "").strip()[:64],
        ]
    )
    last = _HISTORY_LATEST_NOOP_LOG_CACHE.get(cache_key)
    if last and now - last < _HISTORY_LATEST_NOOP_LOG_TTL_SECONDS:
        return False
    _HISTORY_LATEST_NOOP_LOG_CACHE[cache_key] = now
    return True


def _get_sumitalk_history_window_id_from_body(body: dict) -> str:
    return _normalize_sumitalk_history_window_id(
        (body or {}).get("window_id") or (body or {}).get("history_window_id") or ""
    )


def _sumitalk_history_storage_key(device_id: str, window_id: str = "") -> str:
    did = str(device_id or "").strip()
    wid = _canonical_sumitalk_history_window_id(window_id)
    return did if not wid else f"{did}::{wid}"


def _sumitalk_history_candidate_keys(device_id: str, window_id: str = "") -> list[str]:
    did = str(device_id or "").strip()
    if not did:
        return []
    wid = _canonical_sumitalk_history_window_id(window_id)
    keys = [_sumitalk_history_storage_key(did, wid)]
    if wid == _SUMITALK_MAIN_WINDOW_ID:
        keys.append(did)  # 旧版主会话没有 window_id，兼容读回来。
    elif wid.startswith("tg_"):
        keys.append(_sumitalk_history_storage_key(did, _SUMITALK_MAIN_WINDOW_ID))
        keys.append(did)
    out = []
    seen = set()
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _load_sumitalk_history_row(data: dict, device_id: str, window_id: str = "") -> dict:
    rows = []
    for key in _sumitalk_history_candidate_keys(device_id, window_id):
        row = data.get(key) if isinstance(data, dict) else None
        if isinstance(row, dict):
            rows.append(row)
    if not rows:
        return {}
    # Candidate rows are ordered from the exact key to increasingly broad
    # legacy fallbacks. Merge fallbacks first so the exact row wins when the
    # same stable message id exists in more than one storage format.
    messages = _merge_sumitalk_messages(*[(row.get("messages") or []) for row in reversed(rows)])
    updated_at = ""
    latest_dt = None
    for row in rows:
        raw = str(row.get("updated_at") or "").strip()
        dt = parse_iso_to_beijing(raw)
        if raw and (latest_dt is None or (dt and dt > latest_dt)):
            updated_at = raw
            latest_dt = dt
    return {
        "device_id": device_id,
        "window_id": _canonical_sumitalk_history_window_id(window_id),
        "updated_at": updated_at,
        "messages": messages,
    }


def _sumitalk_request_brief() -> dict:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return {
        "remote": request.remote_addr or "",
        "ua": (request.headers.get("User-Agent") or "")[:120],
        "subject": str(payload.get("sub") or "").strip(),
    }


def _normalize_sumitalk_messages(items: list[dict]) -> list[dict]:
    def _safe_display_parts(value) -> list[dict]:
        out: list[dict] = []
        rows = value if isinstance(value, list) else []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or raw.get("type") or "").strip()
            if kind == "text":
                text = str(raw.get("text") or "").strip()
                if not text:
                    continue
                out.append({
                    "id": str(raw.get("id") or f"text-{len(out)}").strip(),
                    "kind": "text",
                    "text": text[:4000],
                })
            elif kind == "tool_call":
                name = str(raw.get("name") or "工具").strip()[:120] or "工具"
                state = str(raw.get("state") or "done").strip()
                if state not in {"running", "done", "error"}:
                    state = "done"
                row = {
                    "id": str(raw.get("id") or raw.get("callId") or f"tool-{len(out)}").strip(),
                    "kind": "tool_call",
                    "name": name,
                    "state": state,
                }
                for src, dst, limit in (
                    ("callId", "callId", 160),
                    ("argumentsText", "argumentsText", 2400),
                    ("resultText", "resultText", 2400),
                ):
                    text = str(raw.get(src) or "").strip()
                    if text:
                        row[dst] = text[:limit]
                try:
                    round_no = int(raw.get("round") or 0)
                    if round_no > 0:
                        row["round"] = round_no
                except Exception:
                    pass
                try:
                    duration_ms = int(raw.get("durationMs") or raw.get("duration_ms") or 0)
                    if duration_ms > 0:
                        row["durationMs"] = duration_ms
                except Exception:
                    pass
                out.append(row)
        return out[:80]

    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant", "benben"}:
            continue
        content = str(item.get("content") or "").strip()
        display_parts = _safe_display_parts(item.get("displayParts") or item.get("display_parts"))
        if not content and not display_parts:
            continue
        reasoning = str(item.get("reasoning") or "").strip()
        raw_token_count = item.get("tokenCount")
        token_count = raw_token_count if isinstance(raw_token_count, dict) else None
        legacy_token_count = 0
        if token_count is None:
            try:
                legacy_token_count = int(raw_token_count or 0)
            except Exception:
                legacy_token_count = 0
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
        if token_count:
            row["tokenCount"] = token_count
        elif legacy_token_count > 0:
            row["tokenCount"] = legacy_token_count
        if display_parts:
            row["displayParts"] = display_parts
        out.append(row)

    id_counts: dict[str, int] = {}
    for row in out:
        message_id = str(row.get("id") or "").strip()
        id_counts[message_id] = id_counts.get(message_id, 0) + 1

    normalized: list[dict] = []
    seen_variant_ids: set[str] = set()
    for row in out:
        message_id = str(row.get("id") or "").strip()
        if id_counts.get(message_id, 0) > 1:
            # Some legacy group-chat batches reused one id for several
            # different Benben messages created in the same turn. Native
            # SQLite uses the id as its identity, so derive a deterministic id
            # for every conflicting variant instead of silently dropping it.
            fingerprint = json.dumps(
                {
                    "role": row.get("role"),
                    "createdAt": row.get("createdAt"),
                    "content": row.get("content"),
                    "displayParts": row.get("displayParts") or [],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            digest = hashlib.sha1(fingerprint.encode("utf-8", errors="ignore")).hexdigest()[:12]
            variant_id = f"{message_id}~{digest}"
            if variant_id in seen_variant_ids:
                continue
            row = dict(row)
            row["id"] = variant_id
            seen_variant_ids.add(variant_id)
        normalized.append(row)
    return normalized


def _merge_sumitalk_messages(*groups: list[dict]) -> list[dict]:
    merged_by_id: dict[str, dict] = {}
    for items in groups:
        for item in _normalize_sumitalk_messages(items or []):
            message_id = str(item.get("id") or "").strip()
            if message_id:
                # Message ids are also the native SQLite identity. Later
                # groups represent newer or more specific copies and replace
                # stale legacy versions of the same logical message.
                merged_by_id[message_id] = item

    merged = list(merged_by_id.values())

    def _sort_key(row: dict) -> tuple[float, str]:
        created_at = str((row or {}).get("createdAt") or "").strip()
        dt = parse_iso_to_beijing(created_at)
        return (dt.timestamp() if dt else 0.0), str((row or {}).get("id") or "").strip()

    merged.sort(key=_sort_key)
    return merged


def _sumitalk_message_poll_key(msg: dict) -> str:
    msg_id = str((msg or {}).get("id") or "").strip()
    if msg_id:
        return msg_id
    created_at = str((msg or {}).get("createdAt") or "").strip()
    content = str((msg or {}).get("content") or "").strip()
    digest = hashlib.sha1(f"{created_at}\n{content}".encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{created_at}|{digest}"


def _sumitalk_message_content_to_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
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
        return "".join(parts).strip()
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "").strip()
    return str(content).strip()


def _latest_sumitalk_assistant_message(messages: list[dict]) -> dict | None:
    for item in reversed(_normalize_sumitalk_messages(messages or [])):
        if str(item.get("role") or "").strip().lower() == "assistant":
            return item
    return None


def _publish_latest_sumitalk_assistant_message(device_id: str, window_id: str, messages: list[dict]) -> None:
    latest = _latest_sumitalk_assistant_message(messages)
    if not latest:
        return
    try:
        msg = dict(latest)
        msg["key"] = _sumitalk_message_poll_key(msg)
        msg["preview"] = _sumitalk_message_content_to_text(msg.get("content"))[:500]
        from services.realtime_publish import publish_assistant_message

        publish_assistant_message(device_id, msg, window_id=window_id)
    except Exception as e:
        sumitalk_logger.debug(
            "history_publish_latest_failed device_id=%s window_id=%s error=%s",
            device_id,
            window_id,
            e,
        )


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
        window_id = _canonical_sumitalk_history_window_id(_get_sumitalk_history_window_id_from_args())
        storage_key = _sumitalk_history_storage_key(device_id, window_id)
        with _SUMITALK_HISTORY_LOCK:
            data = _load_sumitalk_histories()
            row = _load_sumitalk_history_row(data, device_id, window_id)
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
        window_id = _canonical_sumitalk_history_window_id(_get_sumitalk_history_window_id_from_args())
        storage_key = _sumitalk_history_storage_key(device_id, window_id)
        with _SUMITALK_HISTORY_LOCK:
            data = _load_sumitalk_histories()
            row = _load_sumitalk_history_row(data, device_id, window_id)
        messages = _normalize_sumitalk_messages((row or {}).get("messages") or [])
        latest = _latest_sumitalk_assistant_message(messages)
        latest_key = _sumitalk_message_poll_key(latest or {}) if latest else ""
        has_new = bool(latest_key and latest_key != after_key)
        meta = _sumitalk_request_brief()
        if _should_log_history_latest(device_id, window_id, has_new, latest_key, after_key):
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

    @bp.route("/sumitalk-history/stats", methods=["GET"])
    def miniapp_sumitalk_history_stats():
        current_device_id = _get_sumitalk_history_device_id()
        if not current_device_id:
            return jsonify({"ok": False, "error": "缺少设备标识", "rows": []}), 400
        data = _load_sumitalk_histories()
        rows = []
        if isinstance(data, dict):
            for key, row in data.items():
                if not isinstance(row, dict):
                    continue
                device_id = str(row.get("device_id") or "").strip()
                window_id = _canonical_sumitalk_history_window_id(row.get("window_id"))
                if not device_id:
                    raw_key = str(key or "").strip()
                    device_id = raw_key.split("::", 1)[0]
                messages = row.get("messages") if isinstance(row.get("messages"), list) else []
                rows.append({
                    "key": str(key or ""),
                    "device_id": device_id,
                    "window_id": window_id,
                    "count": len(messages),
                    "updated_at": str(row.get("updated_at") or ""),
                    "current": device_id == current_device_id,
                })
        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return jsonify({"ok": True, "device_id": current_device_id, "rows": rows})

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
        window_id = _canonical_sumitalk_history_window_id(_get_sumitalk_history_window_id_from_body(body))
        storage_key = _sumitalk_history_storage_key(device_id, window_id)
        incoming = body.get("messages") or []
        incoming_count = len(incoming) if isinstance(incoming, list) else 0
        with _SUMITALK_HISTORY_LOCK:
            data = _load_sumitalk_histories()
            current_row = _load_sumitalk_history_row(data, device_id, window_id)
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
            data, pruned_count = prune_sumitalk_histories(
                data,
                keep_keys=_sumitalk_history_candidate_keys(device_id, window_id),
            )
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
        if pruned_count:
            sumitalk_logger.info("history_pruned rows=%s reason=ttl_or_row_cap", pruned_count)
        _publish_latest_sumitalk_assistant_message(device_id, window_id, messages)
        return jsonify({"ok": True, "device_id": device_id, "window_id": window_id, "count": len(messages), "updated_at": payload["updated_at"]})

    @bp.route("/sumitalk-history/migrate", methods=["POST"])
    def miniapp_sumitalk_history_migrate():
        auth_device_id = _get_sumitalk_history_device_id()
        old_device_id = auth_device_id
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
        requested_old_device_id = str(body.get("old_device_id") or body.get("from_device_id") or "").strip()
        if requested_old_device_id and requested_old_device_id != auth_device_id:
            if not is_trusted_device(requested_old_device_id):
                return jsonify({"ok": False, "error": "旧设备未授信，不能迁移"}), 403
            old_device_id = requested_old_device_id
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

            source_windows: dict[str, list[tuple[str, dict]]] = {}
            for old_key in old_keys:
                suffix = str(old_key)[len(old_device_id):]
                window_id = suffix[2:] if suffix.startswith("::") else ""
                canonical_window_id = _canonical_sumitalk_history_window_id(window_id)
                old_row = data.get(old_key) if isinstance(data, dict) else None
                if isinstance(old_row, dict):
                    source_windows.setdefault(canonical_window_id, []).append((str(old_key), old_row))

            for canonical_window_id, source_rows in source_windows.items():
                new_key = _sumitalk_history_storage_key(new_device_id, canonical_window_id)
                new_row = data.get(new_key) if isinstance(data, dict) else None

                # The unscoped legacy main row is the oldest fallback. Apply
                # explicit window rows after it, so canonical copies win for
                # identical message ids. Source rows then override any partial
                # copy left by an earlier migration, while destination-only
                # messages remain intact.
                source_rows.sort(key=lambda item: (item[0] != old_device_id, item[0]))
                source_groups = [(row.get("messages") or []) for _, row in source_rows]
                source_messages = _merge_sumitalk_messages(*source_groups)
                existing_messages = _merge_sumitalk_messages((new_row or {}).get("messages") or [])
                source_raw_ids = {
                    str(item.get("id") or "").strip()
                    for group in source_groups
                    for item in group
                    if isinstance(item, dict) and str(item.get("id") or "").strip()
                }
                source_ids = {str(item.get("id") or "").strip() for item in source_messages}
                destination_only_messages = [
                    item for item in existing_messages
                    if str(item.get("id") or "").strip() not in source_raw_ids
                    and str(item.get("id") or "").strip() not in source_ids
                ]
                merged_messages = _merge_sumitalk_messages(
                    destination_only_messages,
                    source_messages,
                )
                payload = {
                    "device_id": new_device_id,
                    "window_id": canonical_window_id,
                    "updated_at": now_beijing_iso(),
                    "messages": merged_messages,
                }
                data[new_key] = payload
                migrated_rows.append({
                    "old_keys": [key for key, _ in source_rows],
                    "new_key": new_key,
                    "window_id": canonical_window_id,
                    "source_count": len(source_messages),
                    "existing_count": len(existing_messages),
                    "merged_count": len(merged_messages),
                    "updated_at": payload["updated_at"],
                })
            keep_keys = [str(key) for key in old_keys]
            for row in migrated_rows:
                new_key = str(row.get("new_key") or "").strip()
                if new_key:
                    keep_keys.append(new_key)
            data, pruned_count = prune_sumitalk_histories(data, keep_keys=keep_keys)
            ok = _save_sumitalk_histories(data)
        if not ok:
            meta = _sumitalk_request_brief()
            total_source = sum(int(row.get("source_count") or 0) for row in migrated_rows)
            total_existing = sum(int(row.get("existing_count") or 0) for row in migrated_rows)
            total_merged = sum(int(row.get("merged_count") or 0) for row in migrated_rows)
            sumitalk_logger.error(
                "history_migrate_failed old_device_id=%s new_device_id=%s source_rows=%s target_rows=%s source_count=%s existing_count=%s merged=%s remote=%s ua=%s",
                old_device_id,
                new_device_id,
                len(old_keys),
                len(migrated_rows),
                total_source,
                total_existing,
                total_merged,
                meta["remote"],
                meta["ua"],
            )
            return jsonify({"ok": False, "error": "迁移失败"}), 500
        meta = _sumitalk_request_brief()
        total_source = sum(int(row.get("source_count") or 0) for row in migrated_rows)
        total_existing = sum(int(row.get("existing_count") or 0) for row in migrated_rows)
        total_merged = sum(int(row.get("merged_count") or 0) for row in migrated_rows)
        latest_updated_at = str((migrated_rows[-1] if migrated_rows else {}).get("updated_at") or "").strip()
        panel_token = ""
        panel_token_ttl = 0
        try:
            upsert_trusted_device(new_device_id)
            if panel_auth_enabled():
                panel_token, panel_token_ttl = issue_panel_token(subject=f"device:{new_device_id}", device_id=new_device_id)
        except Exception as e:
            sumitalk_logger.warning(
                "history_migrate_token_refresh_failed old_device_id=%s new_device_id=%s error=%s",
                old_device_id,
                new_device_id,
                e,
            )
        sumitalk_logger.info(
            "history_migrate_ok old_device_id=%s new_device_id=%s source_rows=%s target_rows=%s source_count=%s existing_count=%s merged=%s copied=%s updated_at=%s remote=%s ua=%s",
            old_device_id,
            new_device_id,
            len(old_keys),
            len(migrated_rows),
            total_source,
            total_existing,
            total_merged,
            bool(total_source),
            latest_updated_at,
            meta["remote"],
            meta["ua"],
        )
        if pruned_count:
            sumitalk_logger.info("history_pruned rows=%s reason=ttl_or_row_cap", pruned_count)
        return jsonify(
            {
                "ok": True,
                "old_device_id": old_device_id,
                "device_id": new_device_id,
                "count": total_merged,
                "rows": len(migrated_rows),
                "source_rows": len(old_keys),
                "source_count": total_source,
                "existing_count": total_existing,
                "copied": bool(total_source),
                "updated_at": latest_updated_at,
                "panel_token": panel_token,
                "expires_in": panel_token_ttl,
            }
        )
