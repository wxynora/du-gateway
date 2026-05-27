from __future__ import annotations

from flask import jsonify, request

from storage.xiaoai_store import (
    get_xiaoai_config,
    get_xiaoai_status,
    list_xiaoai_logs,
    save_xiaoai_config,
)


def register_routes(bp) -> None:
    @bp.route("/xiaoai/overview", methods=["GET"])
    def miniapp_xiaoai_overview():
        limit = request.args.get("limit", type=int, default=80)
        return jsonify(
            {
                "ok": True,
                "config": get_xiaoai_config(),
                "status": get_xiaoai_status(),
                "logs": list_xiaoai_logs(limit=limit),
            }
        )

    @bp.route("/xiaoai/config", methods=["GET"])
    def miniapp_xiaoai_config_get():
        return jsonify({"ok": True, "config": get_xiaoai_config()})

    @bp.route("/xiaoai/config", methods=["PUT"])
    def miniapp_xiaoai_config_put():
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"ok": False, "error": "需要 JSON 对象"}), 400
        return jsonify({"ok": True, "config": save_xiaoai_config(body)})

    @bp.route("/xiaoai/status", methods=["GET"])
    def miniapp_xiaoai_status_get():
        return jsonify({"ok": True, "status": get_xiaoai_status()})

    @bp.route("/xiaoai/logs", methods=["GET"])
    def miniapp_xiaoai_logs_get():
        limit = request.args.get("limit", type=int, default=120)
        return jsonify({"ok": True, "logs": list_xiaoai_logs(limit=limit)})
