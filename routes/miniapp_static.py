import hashlib
import re
from pathlib import Path

from flask import Blueprint, jsonify, send_from_directory

from config import MINIAPP_STATIC_DIR


bp = Blueprint("miniapp_static", __name__)


@bp.route("/miniapp", methods=["GET"])
@bp.route("/miniapp/", methods=["GET"])
def miniapp_index():
    """Telegram Mini App 静态入口页。"""
    resp = send_from_directory(MINIAPP_STATIC_DIR, "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp.route("/miniapp/assets/<path:filename>", methods=["GET"])
def miniapp_assets(filename: str):
    """Mini App 静态资源（JS/CSS/图标）。"""
    resp = send_from_directory(MINIAPP_STATIC_DIR / "assets", filename)
    if re.search(r"-[A-Za-z0-9_-]{6,}\.", filename):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.route("/miniapp-api/app-version", methods=["GET"])
def miniapp_app_version():
    """
    提供 MiniApp 前端版本摘要：用于 APK 判断是否需要强制刷新缓存。
    """
    try:
        index_file: Path = MINIAPP_STATIC_DIR / "index.html"
        if not index_file.exists():
            return jsonify({"ok": False, "error": "miniapp index 不存在"}), 404
        raw = index_file.read_bytes()
        digest = hashlib.sha1(raw).hexdigest()[:12]
        updated_at = int(index_file.stat().st_mtime)
        return jsonify({
            "ok": True,
            "version": f"{updated_at}-{digest}",
            "updated_at": updated_at,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/favicon.ico", methods=["GET"])
def favicon_ico():
    """避免默认 favicon 404 噪声（如不存在则仍返回 404）。"""
    try:
        return send_from_directory(MINIAPP_STATIC_DIR, "favicon.ico")
    except Exception:
        return "", 404
