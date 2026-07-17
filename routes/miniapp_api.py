from flask import Blueprint, jsonify, request

from config import (
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
)
from storage import whitelist_store
from utils.ip_allowlist import enforce_ip_allowlist
from utils.miniapp_panel_auth import (
    enforce_panel_token,
)
from utils.telegram_webapp import enforce_telegram_initdata
from routes.miniapp.codex_group_chat import register_routes as register_codex_group_chat_routes
from routes.miniapp.device_actions import register_routes as register_device_actions_routes
from routes.miniapp.device_state import register_routes as register_device_state_routes
from routes.miniapp.co_read import register_routes as register_co_read_routes
from routes.miniapp.dashboard import register_routes as register_dashboard_routes
from routes.miniapp.diagnostics import register_routes as register_diagnostics_routes
from routes.miniapp.du_pages import register_routes as register_du_pages_routes
from routes.miniapp.exchange_diary import register_routes as register_exchange_diary_routes
from routes.miniapp.game_tools import register_routes as register_game_tools_routes
from routes.miniapp.studyroom import register_routes as register_studyroom_routes
from routes.miniapp.logs import register_routes as register_logs_routes
from routes.miniapp.media import register_routes as register_media_routes
from routes.miniapp.memory_panel import register_routes as register_memory_panel_routes
from routes.miniapp.midterm_memory import register_routes as register_midterm_memory_routes
from routes.miniapp.music_bgm import register_routes as register_music_bgm_routes
from routes.miniapp.music_netease import register_routes as register_music_netease_routes
from routes.miniapp.notes import register_routes as register_notes_routes
from routes.miniapp.panel_auth import register_routes as register_panel_auth_routes
from routes.miniapp.private_draw import register_routes as register_private_draw_routes
from routes.miniapp.reasoning import register_routes as register_reasoning_routes
from routes.miniapp.schedule import register_routes as register_schedule_routes
from routes.miniapp.secret_drawer import register_routes as register_secret_drawer_routes
from routes.miniapp.settings import register_routes as register_settings_routes
from routes.miniapp.stickers import register_routes as register_stickers_routes
from routes.miniapp.sumitalk_chat_jobs import register_routes as register_sumitalk_chat_job_routes
from routes.miniapp.sumitalk_history import register_routes as register_sumitalk_history_routes
from routes.miniapp.upstreams import register_routes as register_upstreams_routes
from routes.miniapp.wenyou import register_routes as register_wenyou_routes
from routes.miniapp.xiaoai import register_routes as register_xiaoai_routes
from routes.miniapp.aifarm import register_routes as register_aifarm_routes


bp = Blueprint("miniapp_api", __name__, url_prefix="/miniapp-api")
register_codex_group_chat_routes(bp)
register_co_read_routes(bp)
register_dashboard_routes(bp)
register_device_actions_routes(bp)
register_device_state_routes(bp)
register_diagnostics_routes(bp)
register_du_pages_routes(bp)
register_exchange_diary_routes(bp)
register_game_tools_routes(bp)
register_studyroom_routes(bp)
register_logs_routes(bp)
register_media_routes(bp)
register_memory_panel_routes(bp)
register_midterm_memory_routes(bp)
register_music_bgm_routes(bp)
register_music_netease_routes(bp)
register_notes_routes(bp)
register_panel_auth_routes(bp)
register_private_draw_routes(bp)
register_reasoning_routes(bp)
register_schedule_routes(bp)
register_secret_drawer_routes(bp)
register_settings_routes(bp)
register_stickers_routes(bp)
register_sumitalk_chat_job_routes(bp)
register_sumitalk_history_routes(bp)
register_upstreams_routes(bp)
register_wenyou_routes(bp)
register_xiaoai_routes(bp)
register_aifarm_routes(bp)


def _resolve_primary_chat_window_id() -> str:
    recent = whitelist_store.list_recent_windows(limit=200) or []
    for w in recent:
        wid = str((w or {}).get("id") or "").strip()
        if wid.startswith("tg_"):
            return wid
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid > 0:
        return f"tg_{uid}"
    if recent:
        return str((recent[0] or {}).get("id") or "").strip()
    return ""


@bp.before_request
def _miniapp_auth():
    # 双保险：先 IP，再 Telegram initData（更快拒绝无效来源）
    if (
        request.path.rstrip("/").endswith("/panel-auth/meta")
        or request.path.rstrip("/").endswith("/panel-auth/check-password")
        or request.path.rstrip("/").endswith("/panel-auth/verify")
        or request.path.rstrip("/").endswith("/panel-auth/native-device/pair")
        or request.path.rstrip("/").endswith("/client-error")
        or request.path.rstrip("/").endswith("/tts-preview")
        or request.path.rstrip("/").endswith("/stickers/tags-public")
        or request.path.rstrip("/").endswith("/stickers/resolve")
        or request.path.rstrip("/").endswith("/stickers/raw-public")
        or request.path.rstrip("/").endswith("/chat-media/raw-public")
        or "/miniapp-api/voice-call/tts-audio/" in request.path
        or request.path.rstrip("/").endswith("/device-screenshots/raw-public")
    ):
        enforce_ip_allowlist()
        return None
    enforce_ip_allowlist()
    panel_block = enforce_panel_token()
    if panel_block is not None:
        return panel_block
    if request.environ.get("miniapp_panel_payload"):
        return None
    enforce_telegram_initdata()


@bp.route("/chat-window", methods=["GET"])
def miniapp_chat_window():
    return jsonify({"ok": True, "window_id": _resolve_primary_chat_window_id()})
