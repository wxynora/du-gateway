from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from flask import jsonify, request

from storage import blacklist_store, r2_store, whitelist_store
from utils.time_aware import now_beijing_iso

logger = logging.getLogger(__name__)

_MEMORY_MAINTENANCE_LOCK = threading.Lock()
_MEMORY_MAINTENANCE_RUNNING = False
_MEMORY_MAINTENANCE_LAST_STARTED = ""
_MEMORY_MAINTENANCE_LAST_FINISHED = ""
_MEMORY_MAINTENANCE_LAST_ERROR = ""


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
    chunk = raw[start + len("【动态记忆】") : end].strip()
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


def _failed_rebuild_ids_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "rebuild_index_failed_ids.json"


def _core_cache_items_for_debug(limit: int) -> dict:
    pending = r2_store.get_core_cache_pending() or []
    rows = [x for x in pending if isinstance(x, dict)]
    rows.sort(key=lambda x: str(x.get("promoted_at") or ""), reverse=True)
    out = []
    for item in rows[:limit]:
        entry_id = str(item.get("id") or "").strip()
        out.append(
            {
                "id": entry_id,
                "memory_id": f"core::{entry_id}" if entry_id else "",
                "content": str(item.get("content") or "").strip(),
                "tag": str(item.get("tag") or "").strip(),
                "promoted_by": str(item.get("promoted_by") or "").strip(),
                "promoted_at": str(item.get("promoted_at") or "").strip(),
                "importance": int(item.get("importance") or 0),
                "mention_count": int(item.get("mention_count") or 0),
                "emotion_label": str(item.get("emotion_label") or "").strip(),
                "scene_type": str(item.get("scene_type") or "").strip(),
                "target_type": str(item.get("target_type") or "").strip(),
            }
        )
    return {"count": len(rows), "visible_count": len(out), "items": out}


def _event_window_id(event: dict) -> str:
    return str((event or {}).get("window_id") or "").strip() or "__default__"


def _merge_citation_events_into_recalls(recall_events: list[dict], citation_events: list[dict]) -> list[dict]:
    """把“实际引用”的调试事件贴回对应的召回事件，前端只需要在召回卡片里高亮。"""
    recalls = [dict(e) for e in recall_events if isinstance(e, dict)]
    if not recalls or not citation_events:
        return recalls

    ordered_recalls = sorted(
        enumerate(recalls),
        key=lambda pair: str((pair[1] or {}).get("timestamp") or ""),
    )
    for citation in sorted(
        [e for e in citation_events if isinstance(e, dict)],
        key=lambda e: str((e or {}).get("timestamp") or ""),
    ):
        cited_ts = str(citation.get("timestamp") or "")
        cited_window = _event_window_id(citation)
        if not cited_ts:
            continue

        target_idx = None
        for idx, recall in ordered_recalls:
            recall_ts = str((recall or {}).get("timestamp") or "")
            if not recall_ts or recall_ts > cited_ts:
                continue
            recall_window = _event_window_id(recall)
            if recall_window != cited_window:
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


def register_routes(bp) -> None:
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
            core_limit = request.args.get("core_limit", type=int, default=120)
            if core_limit < 1:
                core_limit = 1
            if core_limit > 300:
                core_limit = 300
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
            all_events = r2_store.get_dynamic_recall_debug_events(limit=limit * 5) or []
            if not all_events:
                live_preview = _build_live_dynamic_recall_preview(target)
                if live_preview:
                    all_events = [live_preview]
            scope = str(request.args.get("scope") or "all").strip().lower()
            if scope not in ("all", "target"):
                scope = "all"
            if scope == "target" and target:
                events = [
                    e
                    for e in all_events
                    if str((e or {}).get("window_id") or "").strip() in (target, "__default__", "__search_memory__")
                ]
            else:
                events = all_events
            citation_events = [e for e in events if str((e or {}).get("source") or "").strip() == "memory_citation"]
            recall_events = [
                e
                for e in events
                if str((e or {}).get("source") or "").strip() not in ("search_memory", "memory_citation")
            ]
            recall_events = _merge_citation_events_into_recalls(recall_events, citation_events)
            search_events = [e for e in events if str((e or {}).get("source") or "").strip() == "search_memory"]
            maintenance_report = r2_store.get_dynamic_memory_maintenance_report() or {}
            core_cache = _core_cache_items_for_debug(core_limit)
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
                    failed_path = _failed_rebuild_ids_path()
                    if failed_path.exists():
                        failed_payload = json.loads(failed_path.read_text(encoding="utf-8"))
                        failed_ids = failed_payload.get("failed_ids") if isinstance(failed_payload, dict) else []
                        if isinstance(failed_ids, list):
                            failed_ids_preview = [str(x).strip() for x in failed_ids if str(x).strip()][:10]
                            failed_ids_count = len([x for x in failed_ids if str(x).strip()])
                except Exception:
                    failed_ids_count = 0
                    failed_ids_preview = []
                dynamic_stats.update(
                    {
                        "memory_count": len(mems),
                        "memory_tags": mem_tags[:30],
                        "label_complete_count": label_complete_count,
                        "label_missing_count": label_missing_count,
                        "index_tags": (list_existing_tags() or [])[:50],
                        "vector_min_sim": float(VECTOR_MIN_SIM),
                        "vector_topk": int(VECTOR_TOPK),
                        "vector_topn": int(VECTOR_TOPN),
                        "embedding_backend": current_embedding_backend(),
                        "embedding_model": current_embedding_model()
                        or (CF_EMBEDDING_MODEL if (CF_ACCOUNT_ID and CF_API_TOKEN) else EMBEDDING_MODEL),
                        "embed_timeout_seconds": int(EMBED_REQUEST_TIMEOUT_SECONDS),
                        "embed_max_retries": int(EMBED_MAX_RETRIES),
                        "embed_retry_backoff_seconds": float(EMBED_RETRY_BACKOFF_SECONDS),
                        "recent_vector_error": recent_vector_error,
                        "failed_ids_count": failed_ids_count,
                        "failed_ids_preview": failed_ids_preview,
                    }
                )
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
                    "citation_events": citation_events[:limit],
                    "citation_count": len(citation_events[:limit]),
                    "citation_total_count": len(citation_events),
                    "core_cache": core_cache,
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
