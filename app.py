# 渡の网关 - 入口
import os
import re
import hashlib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from config import DATA_DIR
from utils.log import setup_logging

# 先配置日志，后续模块打 log 才能带 [R2]/[Pipeline] 等来源
setup_logging()

from flask import Flask, request, jsonify
from flask import send_from_directory
from routes.chat import bp as chat_bp
from routes.admin import bp as admin_bp
from routes.notion_routes import bp as notion_bp
from routes.telegram_webhook import bp as telegram_webhook_bp
from routes.miniapp_api import bp as miniapp_api_bp
from routes.mcp_api import bp as mcp_api_bp
from routes.pc_command import bp as pc_command_bp
from routes.co_read_api import bp as co_read_api_bp
from routes.html_preview import bp as html_preview_bp
from routes.sense_api import bp as sense_api_bp
from config import MINIAPP_STATIC_DIR

# 确保数据目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.register_blueprint(chat_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(notion_bp)
app.register_blueprint(telegram_webhook_bp)
app.register_blueprint(miniapp_api_bp)
app.register_blueprint(mcp_api_bp)
app.register_blueprint(pc_command_bp)
app.register_blueprint(co_read_api_bp)
app.register_blueprint(html_preview_bp)
app.register_blueprint(sense_api_bp)

# Telegram Webhook 只在 web worker 内快速落持久队列；输入聚合与回复发送由
# scripts/run_telegram_webhook_worker.py 持有。默认不在 gunicorn worker 里启动 TG runtime，
# 避免 max-requests 回收时丢掉 timer/buffer。
if os.environ.get("GATEWAY_EMBEDDED_TELEGRAM_RUNTIME_ENABLED", "0").strip().lower() in ("1", "true", "yes"):
    try:
        from services.telegram_bot import init_telegram_bot_runtime

        init_telegram_bot_runtime()
    except Exception:
        pass

# MiniApp 日历闹钟调度默认不挂在 Web worker 里。
# 生产环境由 du-telegram-proactive 统一 tick，避免 gunicorn 多 worker 重复启动后台线程。
if os.environ.get("GATEWAY_EMBEDDED_SCHEDULE_RUNTIME_ENABLED", "0").strip().lower() in ("1", "true", "yes"):
    try:
        from services.schedule_runtime import start_schedule_runtime_if_enabled

        start_schedule_runtime_if_enabled()
    except Exception:
        pass

# CORS：RikkaHub 等前端带自定义请求头时，浏览器会先发 OPTIONS 预检
# MiniApp 表情包预览等请求需带 X-Telegram-Init-Data（仅 Header、不拼 URL），须在此列出否则跨域预检失败
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "https://duxy-home.com").strip()
CORS_ALLOW_HEADERS = os.environ.get(
    "CORS_ALLOW_HEADERS",
    "Content-Type, Authorization, X-Telegram-Init-Data, X-Panel-Token, X-Force-Last4, X-Reply-Channel, X-Reply-Target, X-Window-Id",
).strip()
CORS_ALLOW_METHODS = os.environ.get(
    "CORS_ALLOW_METHODS",
    "GET, POST, PUT, PATCH, DELETE, OPTIONS",
).strip()


@app.before_request
def _cors_preflight():
    if request.method == "OPTIONS":
        return "", 204


@app.after_request
def _cors_headers(response):
    if CORS_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = CORS_ORIGIN
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = CORS_ALLOW_HEADERS
    response.headers["Access-Control-Allow-Methods"] = CORS_ALLOW_METHODS
    return response


@app.route("/")
def index():
    return {"service": "渡の网关 Du Gateway", "status": "ok"}


@app.route("/miniapp", methods=["GET"])
@app.route("/miniapp/", methods=["GET"])
def miniapp_index():
    """Telegram Mini App 静态入口页。"""
    resp = send_from_directory(MINIAPP_STATIC_DIR, "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/miniapp/assets/<path:filename>", methods=["GET"])
def miniapp_assets(filename: str):
    """Mini App 静态资源（JS/CSS/图标）。"""
    resp = send_from_directory(MINIAPP_STATIC_DIR / "assets", filename)
    if re.search(r"-[A-Za-z0-9_-]{6,}\.", filename):
      resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
      resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/miniapp-api/app-version", methods=["GET"])
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


@app.route("/favicon.ico", methods=["GET"])
def favicon_ico():
    """避免默认 favicon 404 噪声（如不存在则仍返回 404）。"""
    try:
        return send_from_directory(MINIAPP_STATIC_DIR, "favicon.ico")
    except Exception:
        return "", 404


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/summary", methods=["GET"])
def root_summary():
    """DS 四轮总结（渡的回忆）全文，与 GET /admin/summary 相同。"""
    from storage import r2_store
    summary = r2_store.get_summary("")
    if not summary or not summary.strip():
        return {"has_summary": False, "summary": None, "length": 0}
    return {
        "has_summary": True,
        "summary": summary.strip(),
        "length": len(summary.strip()),
    }


@app.route("/dynamic-memory", methods=["GET"])
def root_dynamic_memory():
    """动态层全文，与 GET /admin/dynamic-memory 相同。"""
    from storage import r2_store
    try:
        lst = r2_store.get_dynamic_memory_list() or []
        return {"ok": True, "count": len(lst), "memories": lst}
    except Exception as e:
        return {"ok": False, "error": str(e), "memories": []}, 500


@app.route("/api/memory/append", methods=["POST"])
def api_memory_append():
    """
    向动态层追加一条记忆（供 MCP / CC 写回）。
    Body JSON: { content: str, importance?: int(1-5), tag?: str, emotion_label?: str, scene_type?: str, target_type?: str }
    鉴权：与 /mcp/* 相同的 Bearer token（MCP_AUTH_MODE / MCP_TOKENS）。
    """
    from utils.mcp_auth import enforce_mcp_auth
    enforce_mcp_auth()

    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True) or {}
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400

    importance = body.get("importance", 3)
    try:
        importance = max(1, min(5, int(importance)))
    except (TypeError, ValueError):
        importance = 3
    tag = (body.get("tag") or "书房").strip()
    if tag not in ("客厅", "书房", "图书馆", "卧室"):
        tag = "书房"
    emotion_label = (body.get("emotion_label") or "").strip().lower()
    scene_type = (body.get("scene_type") or "").strip()
    target_type = (body.get("target_type") or "").strip()
    if emotion_label not in ("positive", "negative", "neutral"):
        emotion_label = "neutral"
    if scene_type not in (
        "problem_solving", "learning", "planning", "emotional_venting",
        "heart_to_heart", "casual_chat", "affection", "conflict",
    ):
        scene_type = ""
    if target_type not in (
        "external_tools", "self_state", "work_career", "our_project",
        "our_relationship", "about_me", "third_party_people", "other_topic",
    ):
        target_type = ""

    from uuid import uuid4
    from utils.time_aware import now_beijing_iso
    from storage import r2_store
    from pipeline.pipeline import _build_retrieval_text

    now = now_beijing_iso()
    new_entry = {
        "id": str(uuid4()),
        "content": content,
        "retrieval_text": _build_retrieval_text(content),
        "importance": importance,
        "tag": tag,
        "emotion_label": emotion_label,
        "scene_type": scene_type,
        "target_type": target_type,
        "mention_count": 0,
        "created_at": now,
        "last_mentioned": now,
    }

    memories = r2_store.get_dynamic_memory_list() or []
    memories.append(new_entry)
    ok = r2_store.save_dynamic_memory_list(memories)
    if not ok:
        return jsonify({"ok": False, "error": "R2 写入失败"}), 503

    # 向量索引更新（best-effort，失败不影响写入结果）
    try:
        from pipeline.pipeline import _upsert_dynamic_memory_index
        _upsert_dynamic_memory_index(new_entry)
    except Exception:
        pass

    return jsonify({"ok": True, "id": new_entry["id"]})


@app.route("/api/cc_log", methods=["POST"])
def api_cc_log():
    """
    CC 侧写入一条记录到默认窗口对话历史，伪装成一轮对话，
    后续会被 DS 总结自然消化。
    Body JSON: { content: str, tag?: str }
    """
    from utils.mcp_auth import enforce_mcp_auth
    enforce_mcp_auth()

    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True) or {}
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    tag = (body.get("tag") or "书房").strip()
    if tag not in ("客厅", "书房", "图书馆", "卧室"):
        tag = "书房"

    from utils.time_aware import now_beijing_iso
    from storage import r2_store

    window_id = ""  # 默认窗口
    round_index = r2_store.get_next_round_index(window_id)
    timestamp = now_beijing_iso()
    messages = [
        {"role": "user", "content": f"[{tag} 记录]"},
        {"role": "assistant", "content": content},
    ]
    ok = r2_store.append_conversation_round(window_id, round_index, messages, timestamp)
    if not ok:
        return jsonify({"ok": False, "error": "写入失败"}), 503
    return jsonify({"ok": True, "round_index": round_index})


@app.route("/time-info", methods=["GET"])
def time_info():
    """
    网关时间工具：返回当前北京时间的日期、星期、时间段、具体时间和农历信息。
    供渡在工具调用里使用，不依赖前端自己的时间插件。
    """
    from utils.time_aware import (
        get_date_only,
        get_weekday_cn,
        get_time_period,
        get_exact_time,
        get_lunar_and_terms,
        now_beijing_iso,
    )

    iso = now_beijing_iso()
    date = get_date_only()
    weekday = get_weekday_cn()
    period = get_time_period()
    hm = get_exact_time()
    lunar = get_lunar_and_terms()
    return jsonify(
        {
            "iso": iso,
            "date": date,
            "weekday_cn": weekday,
            "time_hm": hm,
            "period": period,
            "lunar": lunar,
        }
    )


@app.route("/time-now", methods=["GET"])
def time_now():
    """
    极简时间工具：只返回当前北京时间的 HH:mm，供 get_time_info 工具直接使用。
    """
    from utils.time_aware import get_exact_time

    hm = get_exact_time()
    return jsonify({"time_hm": hm})


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    # nohup 时不要开 reloader：子进程的 stdout 可能不进你的 log 文件，导致看不到 [Chat] 等输出
    app.run(host=host, port=port, debug=debug, use_reloader=False)
