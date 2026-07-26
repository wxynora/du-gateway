from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import timedelta

from flask import jsonify, request

from config import (
    DYNAMIC_MEMORY_BEDROOM_DAYS_VALID,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
)
from storage import memory_organizer_store, r2_store, recent_window_store
from utils.time_aware import _now_beijing, parse_iso_to_beijing

logger = logging.getLogger(__name__)

_DEFAULT_PAGE_SIZE = 40
_MAX_PAGE_SIZE = 100


def _page_limit() -> int:
    value = request.args.get("limit", type=int, default=_DEFAULT_PAGE_SIZE)
    return max(1, min(_MAX_PAGE_SIZE, int(value or _DEFAULT_PAGE_SIZE)))


def _stable_id(item: dict, prefix: str) -> str:
    item_id = str(item.get("id") or item.get("memory_id") or "").strip()
    if item_id:
        return item_id
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}::{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _with_stable_ids(rows: list[dict], prefix: str) -> list[dict]:
    out = []
    seen: dict[str, int] = {}
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        base_id = _stable_id(item, prefix)
        occurrence = seen.get(base_id, 0) + 1
        seen[base_id] = occurrence
        item["id"] = base_id if occurrence == 1 else f"{base_id}::{occurrence}"
        out.append(item)
    return out


def _core_rows() -> tuple[list[dict], set[str]]:
    raw_rows = [item for item in (r2_store.get_core_cache_pending() or []) if isinstance(item, dict)]
    rows = _with_stable_ids(raw_rows, "core")
    rows.sort(key=lambda item: (str(item.get("promoted_at") or ""), str(item.get("id") or "")), reverse=True)
    protected_ids: set[str] = set()
    for item in rows:
        item_id = str(item.get("id") or "").strip()
        source_memory_id = str(item.get("source_memory_id") or "").strip()
        if item_id:
            protected_ids.add(item_id)
        if source_memory_id:
            protected_ids.add(source_memory_id)
        item["memory_id"] = f"core::{item_id}" if item_id else ""
        item["review_pending"] = isinstance(item.get("pending_merge"), dict)
    return rows, protected_ids


def _prune_at(memory: dict, now, core_protected: bool):
    if core_protected or str(memory.get("tag") or "").strip() == "图书馆":
        return None
    last_mentioned = memory.get("last_mentioned") or memory.get("created_at") or ""
    last_dt = parse_iso_to_beijing(str(last_mentioned))
    if last_dt is None:
        return None

    if str(memory.get("tag") or "").strip() == "卧室":
        return last_dt + timedelta(days=max(0, int(DYNAMIC_MEMORY_BEDROOM_DAYS_VALID)) + 1)
    if not DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED:
        return None

    base_weight = int(memory.get("importance") or 0) + int(memory.get("mention_count") or 0)
    min_days = max(0, int(DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS))
    max_decay_day = 35
    for days_since in range(min_days, max(min_days, max_decay_day) + 1):
        decay_days = max(0, days_since - 15)
        time_decay = min(decay_days * 0.1, 2.0)
        if float(base_weight - time_decay) <= float(DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT):
            return last_dt + timedelta(days=days_since)
    return None


def _dynamic_rows(core_protected_ids: set[str]) -> list[dict]:
    now = _now_beijing()
    rows = _with_stable_ids(
        [item for item in (r2_store.get_dynamic_memory_list() or []) if isinstance(item, dict)],
        "dynamic",
    )
    for item in rows:
        item_id = str(item.get("id") or "").strip()
        core_protected = bool(item_id and item_id in core_protected_ids)
        prune_at = _prune_at(item, now, core_protected)
        item["core_protected"] = core_protected
        item["prune_at"] = prune_at.isoformat() if prune_at is not None else ""
        item["at_risk"] = bool(prune_at is not None and now >= prune_at)
    rows.sort(
        key=lambda item: (
            str(item.get("updated_at") or item.get("last_mentioned") or item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return rows


def _audit_rows() -> list[dict]:
    rows = [item for item in (r2_store.get_dynamic_ds_audit_events(limit=300) or []) if isinstance(item, dict)]
    return _with_stable_ids(rows, "audit")


def _primary_window_id() -> str:
    recent = recent_window_store.list_recent_windows(limit=200) or []
    for item in recent:
        window_id = str((item or {}).get("id") or "").strip()
        if window_id.startswith("tg_"):
            return window_id
    if recent:
        return str((recent[0] or {}).get("id") or "").strip()
    return ""


def _respond(payload: dict, *, started: float, endpoint: str, item_count: int):
    response = jsonify(payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    response_bytes = len(response.get_data())
    response.headers["X-Memory-Organizer-Elapsed-Ms"] = str(elapsed_ms)
    response.headers["X-Memory-Organizer-Response-Bytes"] = str(response_bytes)
    response.headers["X-Memory-Organizer-Item-Count"] = str(max(0, int(item_count or 0)))
    logger.info(
        "memory_organizer endpoint=%s elapsed_ms=%.3f response_bytes=%s item_count=%s",
        endpoint,
        elapsed_ms,
        response_bytes,
        item_count,
    )
    return response


def _page_payload(kind: str, loader):
    cursor = str(request.args.get("cursor") or "").strip()
    revision = str(request.args.get("revision") or "").strip()
    limit = _page_limit()
    if cursor:
        return memory_organizer_store.continue_page(
            expected_kind=kind,
            cursor=cursor,
            requested_revision=revision,
            limit=limit,
        )
    items, metadata = loader()
    return memory_organizer_store.start_page(
        kind=kind,
        current_items=items,
        metadata=metadata,
        requested_revision=revision,
        limit=limit,
    )


def register_routes(bp):
    @bp.route("/memory-organizer/summary", methods=["GET"])
    def memory_organizer_summary():
        started = time.perf_counter()
        try:
            core_rows, protected_ids = _core_rows()
            dynamic_rows = _dynamic_rows(protected_ids)
            pending_core = [item for item in core_rows if item.get("review_pending")]
            dynamic_snapshot = memory_organizer_store.save_snapshot(
                "dynamic",
                dynamic_rows,
                {
                    "total_count": len(dynamic_rows),
                    "at_risk_count": sum(1 for item in dynamic_rows if item.get("at_risk")),
                    "core_protected_count": sum(1 for item in dynamic_rows if item.get("core_protected")),
                },
            )
            core_snapshot = memory_organizer_store.save_snapshot(
                "core:all",
                core_rows,
                {
                    "filter": "all",
                    "all_count": len(core_rows),
                    "pending_count": len(pending_core),
                },
            )
            pending_snapshot = memory_organizer_store.save_snapshot(
                "core:pending",
                pending_core,
                {
                    "filter": "pending",
                    "all_count": len(core_rows),
                    "pending_count": len(pending_core),
                },
            )
            window_id = _primary_window_id()
            summary = str(r2_store.get_summary(window_id) or "").strip()
            payload = {
                "ok": True,
                "window_id": window_id,
                "summary": summary,
                "summary_exists": bool(summary),
                "dynamic": {
                    "revision": dynamic_snapshot["revision"],
                    **dynamic_snapshot["metadata"],
                },
                "core": {
                    "revision": core_snapshot["revision"],
                    "pending_revision": pending_snapshot["revision"],
                    **core_snapshot["metadata"],
                },
            }
            return _respond(
                payload,
                started=started,
                endpoint="summary",
                item_count=len(dynamic_rows) + len(core_rows),
            )
        except Exception as exc:
            logger.exception("memory organizer summary failed")
            return _respond(
                {"ok": False, "error": str(exc)},
                started=started,
                endpoint="summary",
                item_count=0,
            ), 500

    @bp.route("/memory-organizer/dynamic", methods=["GET"])
    def memory_organizer_dynamic():
        started = time.perf_counter()
        try:
            def load_dynamic():
                _, protected_ids = _core_rows()
                items = _dynamic_rows(protected_ids)
                return items, {
                    "total_count": len(items),
                    "at_risk_count": sum(1 for item in items if item.get("at_risk")),
                    "core_protected_count": sum(1 for item in items if item.get("core_protected")),
                }

            page = _page_payload("dynamic", load_dynamic)
            payload = {"ok": True, **page}
            return _respond(
                payload,
                started=started,
                endpoint="dynamic",
                item_count=len(page["items"]) + len(page["deleted_ids"]),
            )
        except ValueError as exc:
            return _respond(
                {"ok": False, "error": str(exc)},
                started=started,
                endpoint="dynamic",
                item_count=0,
            ), 400
        except Exception as exc:
            logger.exception("memory organizer dynamic failed")
            return _respond(
                {"ok": False, "error": str(exc)},
                started=started,
                endpoint="dynamic",
                item_count=0,
            ), 500

    @bp.route("/memory-organizer/core", methods=["GET"])
    def memory_organizer_core():
        started = time.perf_counter()
        try:
            cursor = str(request.args.get("cursor") or "").strip()
            requested_filter = str(request.args.get("filter") or "").strip().lower()
            if cursor and not requested_filter:
                cursor_kind = memory_organizer_store.cursor_kind(cursor)
                requested_filter = cursor_kind.split(":", 1)[1] if cursor_kind.startswith("core:") else ""
            core_filter = requested_filter or "all"
            if core_filter not in {"all", "pending"}:
                raise ValueError("filter must be pending or all")
            kind = f"core:{core_filter}"

            def load_core():
                rows, _ = _core_rows()
                pending_rows = [item for item in rows if item.get("review_pending")]
                items = pending_rows if core_filter == "pending" else rows
                return items, {
                    "filter": core_filter,
                    "all_count": len(rows),
                    "pending_count": len(pending_rows),
                }

            page = _page_payload(kind, load_core)
            payload = {"ok": True, **page}
            return _respond(
                payload,
                started=started,
                endpoint="core",
                item_count=len(page["items"]) + len(page["deleted_ids"]),
            )
        except ValueError as exc:
            return _respond(
                {"ok": False, "error": str(exc)},
                started=started,
                endpoint="core",
                item_count=0,
            ), 400
        except Exception as exc:
            logger.exception("memory organizer core failed")
            return _respond(
                {"ok": False, "error": str(exc)},
                started=started,
                endpoint="core",
                item_count=0,
            ), 500

    @bp.route("/memory-organizer/audit", methods=["GET"])
    def memory_organizer_audit():
        started = time.perf_counter()
        try:
            def load_audit():
                items = _audit_rows()
                return items, {"total_count": len(items)}

            page = _page_payload("audit", load_audit)
            payload = {"ok": True, **page}
            return _respond(
                payload,
                started=started,
                endpoint="audit",
                item_count=len(page["items"]) + len(page["deleted_ids"]),
            )
        except ValueError as exc:
            return _respond(
                {"ok": False, "error": str(exc)},
                started=started,
                endpoint="audit",
                item_count=0,
            ), 400
        except Exception as exc:
            logger.exception("memory organizer audit failed")
            return _respond(
                {"ok": False, "error": str(exc)},
                started=started,
                endpoint="audit",
                item_count=0,
            ), 500
