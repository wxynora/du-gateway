from __future__ import annotations

import logging

from flask import jsonify

from services import du_longterm_memory

logger = logging.getLogger(__name__)


def register_routes(bp):
    @bp.route("/longterm-memory", methods=["GET"])
    def get_longterm_memory():
        try:
            latest = du_longterm_memory.get_latest_longterm_memory()
        except Exception:
            logger.exception("longterm memory latest read failed")
            return jsonify({"ok": False, "error": "longterm_memory_read_failed"}), 500

        if not isinstance(latest, dict):
            return jsonify(
                {
                    "ok": True,
                    "exists": False,
                    "content": "",
                    "covered_through": "",
                    "updated_at": "",
                    "schema_version": None,
                    "model": "",
                    "prompt_version": "",
                }
            )

        return jsonify(
            {
                "ok": True,
                "exists": True,
                "content": str(latest.get("content") or ""),
                "covered_through": str(latest.get("covered_through") or ""),
                "updated_at": str(latest.get("updated_at") or ""),
                "schema_version": latest.get("schema_version"),
                "model": str(latest.get("model") or ""),
                "prompt_version": str(latest.get("prompt_version") or ""),
            }
        )
