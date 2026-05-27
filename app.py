# 渡の网关 - 入口
import os

from dotenv import load_dotenv

load_dotenv()

from config import DATA_DIR
from utils.log import setup_logging

# 先配置日志，后续模块打 log 才能带 [R2]/[Pipeline] 等来源
setup_logging()

from flask import Flask, request
from routes.chat import bp as chat_bp
from routes.admin import bp as admin_bp
from routes.notion_routes import bp as notion_bp
from routes.telegram_webhook import bp as telegram_webhook_bp
from routes.miniapp_api import bp as miniapp_api_bp
from routes.mcp_api import bp as mcp_api_bp
from routes.pc_command import bp as pc_command_bp
from routes.co_read_api import bp as co_read_api_bp
from routes.html_preview import bp as html_preview_bp
from routes.memory_api import bp as memory_api_bp
from routes.miniapp_static import bp as miniapp_static_bp
from routes.sense_api import bp as sense_api_bp
from routes.time_api import bp as time_api_bp
from routes.claude_oauth_sync import bp as claude_oauth_sync_bp
from routes.music_melody_api import bp as music_melody_api_bp
from routes.xiaoai_api import bp as xiaoai_api_bp

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
app.register_blueprint(memory_api_bp)
app.register_blueprint(miniapp_static_bp)
app.register_blueprint(sense_api_bp)
app.register_blueprint(time_api_bp)
app.register_blueprint(claude_oauth_sync_bp)
app.register_blueprint(music_melody_api_bp)
app.register_blueprint(xiaoai_api_bp)

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


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    # nohup 时不要开 reloader：子进程的 stdout 可能不进你的 log 文件，导致看不到 [Chat] 等输出
    app.run(host=host, port=port, debug=debug, use_reloader=False)
