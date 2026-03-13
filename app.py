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

# 确保数据目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.register_blueprint(chat_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(notion_bp)

# CORS：RikkaHub 等前端带自定义请求头（如 X-Assistant-Id）时，浏览器会先发 OPTIONS 预检
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
CORS_ALLOW_HEADERS = "Content-Type, Authorization, X-Assistant-Id, Assistant_id"


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


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    # nohup 时不要开 reloader：子进程的 stdout 可能不进你的 log 文件，导致看不到 [Chat] 等输出
    app.run(host=host, port=port, debug=debug, use_reloader=False)
