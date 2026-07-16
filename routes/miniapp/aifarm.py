from __future__ import annotations

from flask import jsonify

from services.aifarm_bridge import (
    AIFarmBridgeError,
    ensure_session,
    public_session,
    session_status,
)


def register_routes(bp):
    @bp.route("/aifarm/session", methods=["GET"])
    def aifarm_session_status():
        return jsonify(session_status())

    @bp.route("/aifarm/session", methods=["POST"])
    def aifarm_session_launch():
        try:
            return jsonify(public_session(ensure_session()))
        except AIFarmBridgeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
