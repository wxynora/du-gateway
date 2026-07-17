from __future__ import annotations

from flask import jsonify, request

from services import wakeup_event_log


def register_routes(bp) -> None:
    @bp.route("/wakeup-events", methods=["GET"])
    def miniapp_wakeup_events():
        try:
            limit = int(request.args.get("limit", 30) or 30)
        except (TypeError, ValueError):
            limit = 30
        data = wakeup_event_log.snapshot(max(1, min(100, limit)))
        return jsonify({"ok": True, **data})
