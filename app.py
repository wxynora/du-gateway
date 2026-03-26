# 渡の网关 - 入口
import os
import re

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

# CORS：RikkaHub 等前端带自定义请求头时，浏览器会先发 OPTIONS 预检
# MiniApp 表情包预览等请求需带 X-Telegram-Init-Data（仅 Header、不拼 URL），须在此列出否则跨域预检失败
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
CORS_ALLOW_HEADERS = os.environ.get(
    "CORS_ALLOW_HEADERS",
    "Content-Type, Authorization, X-Telegram-Init-Data",
).strip()


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


def _normalize_location_patch(patch: dict) -> tuple[dict | None, str | None]:
    """
    Tasker 可把 %LOC 整串放在 loc 里（「纬度,经度」），网关拆成 lat/lng 再写入 R2。
    若已带 lat+lng 则转 float，并去掉 loc/LOC。loc 格式错误时返回错误信息。
    """
    p = dict(patch)
    has_lat = p.get("lat") not in (None, "")
    has_lng = p.get("lng") not in (None, "")
    has_loc = (p.get("loc") not in (None, "")) or (p.get("LOC") not in (None, ""))

    if has_lat and has_lng:
        try:
            p["lat"] = float(p["lat"])
            p["lng"] = float(p["lng"])
        except (TypeError, ValueError):
            return None, "lat/lng 须为数字"
        p.pop("loc", None)
        p.pop("LOC", None)
        return p, None

    if not has_loc:
        p.pop("loc", None)
        p.pop("LOC", None)
        return p, None

    raw = p.get("loc") if p.get("loc") not in (None, "") else p.get("LOC")
    raw = str(raw).strip()
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    if len(parts) != 2:
        return None, 'loc 须为 "纬度,经度" 两段，英文逗号分隔'
    try:
        p["lat"] = float(parts[0])
        p["lng"] = float(parts[1])
    except ValueError:
        return None, "loc 须为有效数字"
    p.pop("loc", None)
    p.pop("LOC", None)
    return p, None


def _normalize_health_patch(patch: dict) -> dict:
    """
    health 归一化：支持客户端直接上传 raw_text（如「88 脉搏/分 - 0 步数 - 63% 电池」），
    网关端自动提取 heart_rate / steps。
    """
    p = dict(patch)
    raw_text = str(p.get("raw_text") or p.get("text") or "").strip()
    if not raw_text:
        return p

    # 心率：优先匹配「88 脉搏/分」，兼容 bpm 文案
    m_hr = re.search(r"(\d+)\s*(?:脉搏/分|bpm)", raw_text, flags=re.IGNORECASE)
    if m_hr:
        try:
            p["heart_rate"] = int(m_hr.group(1))
        except Exception:
            pass

    # 步数：匹配「0 步数」或「1234 steps」
    m_steps = re.search(r"(?:-\s*)?(\d+)\s*(?:步数|steps?)", raw_text, flags=re.IGNORECASE)
    if m_steps:
        try:
            p["steps"] = int(m_steps.group(1))
        except Exception:
            pass

    return p


@app.route("/api/sense", methods=["POST", "OPTIONS"])
def api_sense():
    """
    设备感知上报：按 type 合并写入 R2 sense/latest.json，并为本桶设置 updatedAt（UTC）；
    同时追加一条到 sense/history/YYYY-MM-DD.json（北京日期）。
    请求体示例：{"type":"battery","level":87,"charging":false,"timestamp":1234567890}
    location 可传 loc 为 Tasker %LOC 展开串：{"type":"location","loc":"31.2,121.5","timestamp":...}
    若配置 AMAP_API_KEY，会调用高德逆地理并写入 address。
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
    if sense_type.strip().lower() == "location":
        patch, loc_err = _normalize_location_patch(patch)
        if loc_err:
            return jsonify({"ok": False, "error": loc_err}), 400
        from services.amap_geocode import enrich_location_patch_with_amap_address

        patch = enrich_location_patch_with_amap_address(patch)
    if sense_type.strip().lower() == "health":
        patch = _normalize_health_patch(patch)
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
