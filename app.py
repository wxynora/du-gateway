# 渡の网关 - 入口
import os

from dotenv import load_dotenv

load_dotenv()

from config import DATA_DIR
from utils.log import setup_logging

# 先配置日志，后续模块打 log 才能带 [R2]/[Pipeline] 等来源
setup_logging()

from flask import Flask
from routes.chat import bp as chat_bp
from routes.admin import bp as admin_bp
from routes.notion_routes import bp as notion_bp

# 确保数据目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.register_blueprint(chat_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(notion_bp)


@app.route("/")
def index():
    return {"service": "渡の网关 Du Gateway", "status": "ok"}


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=os.environ.get("FLASK_ENV") == "development")
