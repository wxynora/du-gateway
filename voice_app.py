# 渡の网关 - 独立语音服务入口
from dotenv import load_dotenv
from flask import Flask
from flask_sock import Sock

load_dotenv()

from utils.log import setup_logging

setup_logging()

from routes.miniapp_voice_ws import register_voice_call_ws


app = Flask(__name__)
sock = Sock(app)
register_voice_call_ws(sock)


@app.route("/health")
def health():
    return {"status": "ok", "service": "du-gateway-voice"}
