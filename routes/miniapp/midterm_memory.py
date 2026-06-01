from __future__ import annotations

from flask import jsonify, request

from storage import du_state_store


def register_routes(bp) -> None:
    @bp.route("/midterm-memory", methods=["GET"])
    def miniapp_get_midterm_memory():
        data = du_state_store.get_du_midterm_memory() or {}
        latest = data.get("latest") if isinstance(data, dict) else None
        previous = data.get("previous") if isinstance(data, dict) else []
        return jsonify(
            {
                "ok": True,
                "latest": latest if isinstance(latest, dict) else None,
                "previous": previous if isinstance(previous, list) else [],
                "updated_at": data.get("updated_at") if isinstance(data, dict) else "",
            }
        )

    @bp.route("/midterm-memory/refresh", methods=["POST"])
    def miniapp_refresh_midterm_memory():
        from services.du_midterm_memory import generate_midterm_memory

        data = request.get_json(silent=True) or {}
        save = bool(data.get("save", True))
        force = bool(data.get("force", True))
        result = generate_midterm_memory(save=save, force=force)
        status = 200 if result.get("ok") else 500
        return jsonify(result), status

    @bp.route("/midterm-memory/preview", methods=["POST"])
    def miniapp_preview_midterm_memory():
        from services.du_midterm_memory import generate_midterm_memory

        result = generate_midterm_memory(save=False, force=True)
        status = 200 if result.get("ok") else 500
        return jsonify(result), status
