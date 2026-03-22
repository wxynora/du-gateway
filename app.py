# 渡の网关 - 入口
import os

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

# Telegram（Webhook）运行时初始化：命令菜单等。放在 app 启动阶段，避免依赖 Blueprint 钩子。
try:
    from services.telegram_bot import init_telegram_bot_runtime

    init_telegram_bot_runtime()
except Exception:
    pass

# MiniApp 日历闹钟内置调度：网关启动后自动跑（不需要单独脚本）
try:
    from services.schedule_runtime import start_schedule_runtime_if_enabled

    start_schedule_runtime_if_enabled()
except Exception:
    pass

# CORS：RikkaHub 等前端带自定义请求头（如 X-Assistant-Id）时，浏览器会先发 OPTIONS 预检
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
CORS_ALLOW_HEADERS = "Content-Type, Authorization"


@app.before_request
def _cors_preflight():
    if request.method == "OPTIONS":
        return "", 204


@app.after_request
def _cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = CORS_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = CORS_ALLOW_HEADERS
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/")
def index():
    return {"service": "渡の网关 Du Gateway", "status": "ok"}


@app.route("/miniapp", methods=["GET"])
@app.route("/miniapp/", methods=["GET"])
def miniapp_index():
    """Telegram Mini App 静态入口页。"""
    return send_from_directory(MINIAPP_STATIC_DIR, "index.html")


@app.route("/miniapp/assets/<path:filename>", methods=["GET"])
def miniapp_assets(filename: str):
    """Mini App 静态资源（JS/CSS/图标）。"""
    return send_from_directory(MINIAPP_STATIC_DIR / "assets", filename)


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


@app.route("/api/sense", methods=["POST", "OPTIONS"])
def api_sense():
    """
    设备感知上报：按 type 合并写入 R2 sense/latest.json，并为本桶设置 updatedAt（UTC）；
    同时追加一条到 sense/history/YYYY-MM-DD.json（北京日期）。
    请求体示例：{"type":"battery","level":87,"charging":false,"timestamp":1234567890}
    """
    if request.method == "OPTIONS":
        return "", 204
    from storage import r2_store

    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400
    sense_type = body.get("type")
    if not isinstance(sense_type, str) or not sense_type.strip():
        return jsonify({"ok": False, "error": "缺少 type 或 type 非字符串"}), 400
    patch = {k: v for k, v in body.items() if k != "type"}
    ok = r2_store.merge_and_save_sense_bucket(sense_type.strip(), patch)
    if not ok:
        return jsonify({"ok": False, "error": "R2 未配置或写入失败"}), 503
    return jsonify({"ok": True})


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    # nohup 时不要开 reloader：子进程的 stdout 可能不进你的 log 文件，导致看不到 [Chat] 等输出
    app.run(host=host, port=port, debug=debug, use_reloader=False)
