from __future__ import annotations

import re
from typing import Any


DU_REQUEST_ID_BODY_KEY = "__du_request_id"


def normalize_debug_request_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", raw)[:120]


def event_window_id(event: dict) -> str:
    return str((event or {}).get("window_id") or "").strip() or "__default__"


def is_live_preview_recall_event(event: dict) -> bool:
    if not isinstance(event, dict):
        return False
    source = str(event.get("source") or "").strip()
    reason = str(event.get("reason") or "").strip()
    return (
        source == "live_preview"
        or reason.startswith("live_preview_")
        or str(event.get("debug_origin") or "").strip() == "live_preview"
    )


def merge_citation_events_into_recalls(recall_events: list[dict], citation_events: list[dict]) -> list[dict]:
    """Attach actual `[memory N]` citation events back to their recall event."""
    recalls = [dict(e) for e in recall_events if isinstance(e, dict)]
    if not recalls or not citation_events:
        return recalls

    recall_by_request_id = {
        rid: idx
        for idx, recall in enumerate(recalls)
        if (rid := normalize_debug_request_id(recall.get("du_request_id")))
    }
    ordered_recalls = sorted(
        enumerate(recalls),
        key=lambda pair: str((pair[1] or {}).get("timestamp") or ""),
    )
    for citation in sorted(
        [e for e in citation_events if isinstance(e, dict)],
        key=lambda e: str((e or {}).get("timestamp") or ""),
    ):
        cited_window = event_window_id(citation)
        cited_ts = str(citation.get("timestamp") or "")
        if not cited_ts:
            continue

        target_idx = None
        cited_request_id = normalize_debug_request_id(citation.get("du_request_id"))
        if cited_request_id:
            idx = recall_by_request_id.get(cited_request_id)
            if idx is not None and event_window_id(recalls[idx]) == cited_window:
                target_idx = idx
            else:
                continue

        if target_idx is None:
            for idx, recall in ordered_recalls:
                recall_ts = str((recall or {}).get("timestamp") or "")
                if not recall_ts or recall_ts > cited_ts:
                    continue
                if event_window_id(recall) != cited_window:
                    continue
                target_idx = idx

        if target_idx is None:
            continue

        target = recalls[target_idx]
        existing_ids = [
            str(x).strip()
            for x in (target.get("referenced_memory_ids") or [])
            if str(x).strip()
        ]
        seen_ids = set(existing_ids)
        next_ids = existing_ids[:]
        for raw in citation.get("referenced_memory_ids") or []:
            mid = str(raw or "").strip()
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                next_ids.append(mid)

        existing_memories = [
            x for x in (target.get("referenced_memories") or []) if isinstance(x, dict)
        ]
        seen_memory_ids = {str((x or {}).get("id") or "").strip() for x in existing_memories}
        next_memories = existing_memories[:]
        for mem in citation.get("referenced_memories") or []:
            if not isinstance(mem, dict):
                continue
            mid = str(mem.get("id") or "").strip()
            if mid and mid not in seen_memory_ids:
                seen_memory_ids.add(mid)
                next_memories.append(mem)

        target["referenced_memory_ids"] = next_ids
        target["referenced_memories"] = next_memories
        target["assistant_preview"] = str(citation.get("assistant_preview") or target.get("assistant_preview") or "")
        target["citation_timestamp"] = str(citation.get("timestamp") or target.get("citation_timestamp") or "")

    return recalls
