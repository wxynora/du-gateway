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

# CORS：RikkaHub 等前端带自定义请求头（X-Window-Id、X-Assistant-Id）时，浏览器会先发 OPTIONS 预检，必须允许这些头否则会「无法连接」
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
CORS_ALLOW_HEADERS = "Content-Type, Authorization, X-Window-Id, X-Assistant-Id, X-Add-To-Whitelist"


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


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    # nohup 时不要开 reloader：子进程的 stdout 可能不进你的 log 文件，导致看不到 [Chat] 等输出
    app.run(host=host, port=port, debug=debug, use_reloader=False)
