from __future__ import annotations

import os

import requests
from flask import Blueprint, Response, jsonify, request


bp = Blueprint("claude_oauth_sync", __name__)


def _target_base() -> str:
    return os.environ.get("CLAUDE_OAUTH_SYNC_TARGET_BASE", "http://127.0.0.1:8082").strip().rstrip("/")


def _forward_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    for name in ("Authorization", "X-OAuth-Sync-Key", "X-Sync-Key", "X-Api-Key"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    return headers


def _proxy_response(resp: requests.Response) -> Response:
    content_type = resp.headers.get("Content-Type") or "application/json"
    return Response(resp.content, status=resp.status_code, content_type=content_type)


@bp.route("/internal/claude-oauth-status", methods=["GET"])
def claude_oauth_status():
    try:
        resp = requests.get(
            f"{_target_base()}/internal/oauth-status",
            headers=_forward_headers(),
            timeout=10,
        )
        return _proxy_response(resp)
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"claude_oauth_status_unavailable: {e}"}), 502


@bp.route("/internal/claude-oauth-sync", methods=["POST"])
def claude_oauth_sync():
    try:
        headers = _forward_headers()
        headers["Content-Type"] = request.headers.get("Content-Type") or "application/json"
        resp = requests.post(
            f"{_target_base()}/internal/oauth-sync",
            headers=headers,
            data=request.get_data(),
            timeout=20,
        )
        return _proxy_response(resp)
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"claude_oauth_sync_unavailable: {e}"}), 502
