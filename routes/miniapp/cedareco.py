from __future__ import annotations

from flask import jsonify

from services.cedareco_bridge import (
    CedarEcoBridgeError,
    ensure_session,
    public_session,
    session_status,
)


def register_routes(bp):
    @bp.route("/cedareco/session", methods=["GET"])
    def cedareco_session_status():
        return jsonify(session_status())

    @bp.route("/cedareco/session", methods=["POST"])
    def cedareco_session_launch():
        try:
            return jsonify(public_session(ensure_session()))
        except CedarEcoBridgeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
