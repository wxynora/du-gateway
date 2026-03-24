import time
import os
import math
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta

import requests
from flask import Blueprint, Response, jsonify, request, stream_with_context

from config import (
    MINIAPP_LOG_FILE,
    R2_PUBLIC_URL,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    TELEGRAM_WENYOU_OWNER_USER_ID,
    WENYOU_GROUP_CHAT_ID,
)
from storage import r2_store, whitelist_store, blacklist_store
from storage import upstream_store
from utils.ip_allowlist import enforce_ip_allowlist
from utils.log_reader import stream_logs_sse, tail_logs
from utils.telegram_webapp import enforce_telegram_initdata
from utils.time_aware import today_beijing, now_beijing_iso


bp = Blueprint("miniapp_api", __name__, url_prefix="/miniapp-api")
logger = logging.getLogger(__name__)


def _wenyou_session_id() -> int:
    return int(WENYOU_GROUP_CHAT_ID or TELEGRAM_WENYOU_OWNER_USER_ID or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)


def _notify_schedule_runtime_changed():
    """日历变更后通知网关内置调度线程立即重算。"""
    try:
        from services.schedule_runtime import notify_schedule_changed

        notify_schedule_changed()
    except Exception:
        pass


def _season_label(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"


def _default_cyber_tree_start_date(today: str) -> str:
    """
    默认从“今年”的纪念日 03-04 开始（不按每年回溯）。
    """
    try:
        y = int(str(today).split("-", 2)[0])
    except Exception:
        return "2026-03-04"
    return f"{y:04d}-03-04"


def _generate_daily_report(today: str) -> dict:
    """按北京日期统计「今日」对话轮次与关键词（从最近存档中筛当日）。"""
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    window_id = f"tg_{uid}" if uid > 0 else ""
    # 拉取足够多的最近轮次，再按日期过滤（单日上限通常远小于此）
    all_rounds = r2_store.get_conversation_rounds(window_id, last_n=500) if window_id else []
    day_rounds: list[dict] = []
    text: list[str] = []
    for r in all_rounds or []:
        dt = _parse_beijing_dt(r.get("timestamp"))
        if not dt:
            continue
        if dt.strftime("%Y-%m-%d") != today:
            continue
        day_rounds.append(r)
        for m in (r.get("messages") or []):
            c = m.get("content")
            if isinstance(c, str):
                text.append(c)
            elif isinstance(c, list):
                parts = []
                for p in c:
                    if isinstance(p, dict) and p.get("type") == "text":
                        parts.append(str(p.get("text") or ""))
                if parts:
                    text.append(" ".join(parts))
    rounds_count = len(day_rounds)
    raw = " ".join(text)
    hot = [k for k in ("提醒", "闹钟", "老婆", "睡觉", "吃饭", "工作", "散步", "晚安", "想你", "记事本") if k in raw]
    if not hot:
        hot = ["陪伴", "日常", "关心"]
    report = {
        "report_date": today,
        "window_id": window_id,
        "rounds": rounds_count,
        "keywords": hot[:3],
        "done_count": 0,
        "summary_text": f"今天我们聊了 {rounds_count} 轮，关键词是 {' / '.join(hot[:3])}。",
        "generated_at": now_beijing_iso(),
    }
    return report


def _parse_beijing_dt(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(tz=None).astimezone()


def _mood_day_wave(seed_text: str) -> int:
    seed = sum(ord(ch) for ch in (seed_text or ""))
    return (seed % 5) - 2


def _message_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or "").strip())
        return " ".join(x for x in parts if x).strip()
    return ""


def _mood_keyword_adjustment(text: str) -> tuple[int, list[str]]:
    raw = str(text or "").strip()
    if not raw:
        return 0, []
    negative = {
        "吵架": -12,
        "生气": -10,
        "冷战": -12,
        "委屈": -8,
        "难过": -8,
        "烦": -4,
        "哭": -7,
        "崩溃": -10,
        "失望": -7,
    }
    positive = {
        "爱你": 8,
        "想你": 5,
        "抱抱": 6,
        "晚安": 3,
        "开心": 6,
        "高兴": 5,
        "谢谢": 2,
        "散步": 3,
        "吃饭": 2,
        "陪你": 5,
    }
    score = 0
    hits: list[str] = []
    for word, delta in negative.items():
        if word in raw:
            score += delta
            hits.append(word)
    for word, delta in positive.items():
        if word in raw:
            score += delta
            hits.append(word)
    return max(-22, min(18, score)), hits[:6]


def _generate_mood_meter(today: str) -> dict:
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    window_id = f"tg_{uid}" if uid > 0 else ""
    rounds = r2_store.get_conversation_rounds(window_id, last_n=24) if window_id else []
    total_recent = len(rounds or [])
    today_count = 0
    latest_dt = None
    today_text_parts: list[str] = []
    for r in rounds or []:
        dt = _parse_beijing_dt(r.get("timestamp"))
        if not dt:
            continue
        if dt.strftime("%Y-%m-%d") == today:
            today_count += 1
            for msg in (r.get("messages") or []):
                if not isinstance(msg, dict):
                    continue
                text = _message_text(msg.get("content"))
                if text:
                    today_text_parts.append(text)
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt

    recency_bonus = 0
    if latest_dt is not None:
        age_hours = max(0.0, (datetime.now(latest_dt.tzinfo) - latest_dt).total_seconds() / 3600.0)
        if age_hours <= 6:
            recency_bonus = 8
        elif age_hours <= 24:
            recency_bonus = 5
        elif age_hours <= 48:
            recency_bonus = 2
        else:
            recency_bonus = -2

    activity_bonus = min(18, today_count * 4) + min(10, max(0, total_recent - 4))
    keyword_bonus, keyword_hits = _mood_keyword_adjustment(" ".join(today_text_parts))
    day_wave = _mood_day_wave(f"{window_id}:{today}")
    score = max(35, min(95, 48 + activity_bonus + recency_bonus + keyword_bonus + day_wave))
    return {
        "date": today,
        "score": score,
        "today_rounds": today_count,
        "recent_rounds": total_recent,
        "keyword_hits": keyword_hits,
        "updated_at": now_beijing_iso(),
    }


def _latest_user_text_from_rounds(rounds: list[dict]) -> str:
    for r in reversed(rounds or []):
        for msg in reversed(r.get("messages") or []):
            if not isinstance(msg, dict):
                continue
            if str(msg.get("role") or "").strip().lower() != "user":
                continue
            text = _message_text(msg.get("content"))
            if text:
                return text
    return ""


def _extract_dynamic_memory_lines(system_text: str) -> list[str]:
    raw = str(system_text or "")
    start = raw.find("【动态记忆】")
    end = raw.find("【以上为动态记忆】")
    if start < 0 or end <= start:
        return []
    chunk = raw[start + len("【动态记忆】"):end].strip()
    return [line.strip() for line in chunk.splitlines() if line.strip()]


def _build_live_dynamic_recall_preview(window_id: str) -> dict | None:
    wid = str(window_id or "").strip()
    if not wid:
        return None
    rounds = r2_store.get_conversation_rounds(wid, last_n=6) or []
    query = _latest_user_text_from_rounds(rounds)
    if not query:
        return None
    try:
        from pipeline.pipeline import step_inject_dynamic_memory

        body = {
            "messages": [
                {"role": "system", "content": "debug"},
                {"role": "user", "content": query},
            ]
        }
        out = step_inject_dynamic_memory(body, wid)
        messages = out.get("messages") or []
        system_text = ""
        for msg in messages:
            if str(msg.get("role") or "").strip().lower() == "system":
                system_text = str(msg.get("content") or "")
                break
        lines = _extract_dynamic_memory_lines(system_text)
        refreshed = r2_store.get_dynamic_recall_debug_events(limit=1) or []
        if refreshed:
            return refreshed[0]
        return {
            "timestamp": now_beijing_iso(),
            "window_id": wid,
            "query": query,
            "keywords": [],
            "source": "live_preview",
            "recalled_lines": lines,
            "recalled_count": len(lines),
            "reason": "live_preview_fallback",
        }
    except Exception as e:
        return {
            "timestamp": now_beijing_iso(),
            "window_id": wid,
            "query": query,
            "keywords": [],
            "source": "live_preview",
            "recalled_lines": [],
            "recalled_count": 0,
            "reason": "live_preview_error",
            "vector_error": str(e),
        }


@bp.before_request
def _miniapp_auth():
    # 双保险：先 IP，再 Telegram initData（更快拒绝无效来源）
    enforce_ip_allowlist()
    enforce_telegram_initdata()


@bp.route("/wenyou/last-archive", methods=["GET"])
def miniapp_wenyou_last_archive():
    """
    文游：最近一次 /end 后的归档快照（R2 wenyou/last_archive/{user_id}.json）。
    前端可在结局页拉一次展示框架与历史。
    """
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    arch = r2_store.get_wenyou_last_archive(uid)
    return jsonify({"ok": True, "archive": arch})


@bp.route("/wenyou/archives", methods=["GET"])
def miniapp_wenyou_archives():
    """文游：已通关副本历史列表（按 endedAt 倒序）。"""
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    limit = request.args.get("limit", type=int, default=20)
    items = r2_store.list_wenyou_archives(uid, limit=limit)
    return jsonify({"ok": True, "items": items, "count": len(items)})


@bp.route("/wenyou/archive/<game_id>", methods=["GET"])
def miniapp_wenyou_archive_detail(game_id: str):
    """文游：单个已通关副本详情。"""
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    gid = (game_id or "").strip()
    if not gid:
        return jsonify({"ok": False, "error": "game_id 不能为空"}), 400
    data = r2_store.get_wenyou_archive_by_game_id(uid, gid)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "未找到该归档"}), 404
    fw = data.get("framework") if isinstance(data.get("framework"), dict) else {}
    return jsonify(
        {
            "ok": True,
            "archive": {
                "gameId": str(data.get("gameId") or ""),
                "endedAt": str(data.get("endedAt") or ""),
                "framework": {
                    "instance_code": str(fw.get("instance_code") or ""),
                    "instance_name": str(fw.get("instance_name") or ""),
                    "instance_genre": str(fw.get("instance_genre") or ""),
                    "difficulty": str(fw.get("difficulty") or ""),
                    "world": str(fw.get("world") or ""),
                    "conflict": str(fw.get("conflict") or ""),
                    "failure_hint": str(fw.get("failure_hint") or ""),
                    "reward_hint": str(fw.get("reward_hint") or ""),
                },
                "history_count": len(data.get("history") or []) if isinstance(data.get("history"), list) else 0,
            },
        }
    )


@bp.route("/wenyou/status", methods=["GET"])
def miniapp_wenyou_status():
    """文游：进行中状态（系统空间用于开局前提示）。"""
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return jsonify({"ok": True, "active": False, "session": None})
    fw = (session.get("framework") or {}) if isinstance(session.get("framework"), dict) else {}
    return jsonify(
        {
            "ok": True,
            "active": True,
            "session": {
                "gameId": str(session.get("gameId") or ""),
                "startedAt": str(session.get("startedAt") or ""),
                "instance_code": str(fw.get("instance_code") or ""),
                "instance_name": str(fw.get("instance_name") or ""),
                "instance_genre": str(fw.get("instance_genre") or ""),
                "difficulty": str(fw.get("difficulty") or ""),
            },
        }
    )


@bp.route("/wenyou/story", methods=["POST"])
def miniapp_wenyou_story():
    """文游开局：系统空间可选随机或自定义长描述（keywords）。"""
    uid = _wenyou_session_id()
    if uid == 0:
        return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400
    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode") or "random").strip().lower()
    keywords = str(data.get("keywords") or "").strip()
    if mode not in ("random", "custom"):
        return jsonify({"ok": False, "error": "mode 须为 random 或 custom"}), 400
    if mode == "custom" and not keywords:
        return jsonify({"ok": False, "error": "自定义任务请输入描述"}), 400
    from services.wenyou_service import cmd_story

    text = cmd_story(uid, keywords if mode == "custom" else None)
    need_confirm = ("若确定要开新局" in (text or "")) and ("再发一次" in (text or ""))
    return jsonify({"ok": True, "text": text, "need_confirm_new_game": bool(need_confirm)})


@bp.route("/status", methods=["GET"])
def miniapp_status():
    """概览页用：复用 admin/status 逻辑（但走 miniapp 的鉴权）。"""
    out = {}
    # 总结记忆
    try:
        s = r2_store.get_summary("")
        out["summary"] = {
            "ok": True,
            "has_summary": bool(s and s.strip()),
            "length": len((s or "").strip()),
        }
    except Exception as e:
        out["summary"] = {"ok": False, "error": str(e)}

    # R2（用总结读作为连通性检测）
    try:
        r2_store.get_summary("")
        out["r2"] = {"ok": True, "message": "可读"}
    except Exception as e:
        out["r2"] = {"ok": False, "error": str(e)}

    # 动态层
    try:
        lst = r2_store.get_dynamic_memory_list() or []
        out["dynamic_memory"] = {"ok": True, "count": len(lst)}
    except Exception as e:
        out["dynamic_memory"] = {"ok": False, "error": str(e)}

    # 核心缓存待审
    try:
        pending = r2_store.get_core_cache_pending() or []
        out["core_cache"] = {"ok": True, "pending_count": len(pending)}
    except Exception as e:
        out["core_cache"] = {"ok": False, "error": str(e)}

    # 小本本
    try:
        entries = r2_store.get_notebook_entries() or []
        out["notebook"] = {"ok": True, "count": len(entries)}
    except Exception as e:
        out["notebook"] = {"ok": False, "error": str(e)}

    # 白/黑名单/最近窗口
    try:
        out["whitelist"] = {"ok": True, "count": len(whitelist_store.list_whitelist())}
    except Exception as e:
        out["whitelist"] = {"ok": False, "error": str(e)}
    try:
        out["blacklist"] = {"ok": True, "count": len(blacklist_store.list_blacklist())}
    except Exception as e:
        out["blacklist"] = {"ok": False, "error": str(e)}
    try:
        out["recent_windows"] = {"ok": True, "count": len(whitelist_store.list_recent_windows(limit=500))}
    except Exception as e:
        out["recent_windows"] = {"ok": False, "error": str(e)}

    return jsonify(out)


@bp.route("/daily-whisper", methods=["GET"])
def miniapp_daily_whisper():
    today = today_beijing()
    force_refresh = request.args.get("refresh", type=int, default=0) == 1
    data = r2_store.get_miniapp_daily_whisper() or {}
    if (not force_refresh) and str(data.get("date") or "") == today and (data.get("text") or "").strip():
        return jsonify({"ok": True, "date": today, "text": str(data.get("text") or "").strip(), "cached": True})

    default_text = "今天也想抱抱你，慢慢来，我们一起把今天过好。"
    try:
        from services.deepseek_summary import fetch_daily_whisper_from_summary

        text = (
            fetch_daily_whisper_from_summary(
                r2_store.get_summary("") or "",
                r2_store.get_latest_4_rounds_global() or [],
            )
            or default_text
        ).strip()
    except Exception:
        text = default_text
    payload = {"date": today, "text": text, "updatedAt": now_beijing_iso()}
    r2_store.save_miniapp_daily_whisper(payload)
    return jsonify({"ok": True, "date": today, "text": text, "cached": False})


@bp.route("/cyber-tree", methods=["GET"])
def miniapp_cyber_tree():
    today = today_beijing()
    meta = r2_store.get_cyber_tree_meta() or {}
    start_date = str(meta.get("startDate") or "").strip() or _default_cyber_tree_start_date(today)
    if not (meta.get("startDate")):
        r2_store.save_cyber_tree_meta({"startDate": start_date, "createdAt": now_beijing_iso()})

    try:
        from datetime import datetime as _dt

        d0 = _dt.strptime(start_date, "%Y-%m-%d").date()
        d1 = _dt.strptime(today, "%Y-%m-%d").date()
        days = max(1, (d1 - d0).days + 1)
    except Exception:
        days = 1
    tg_uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    rounds = 0
    if tg_uid > 0:
        rounds = r2_store.get_window_conversation_rounds(f"tg_{tg_uid}")
    if rounds <= 0:
        rounds = r2_store.get_total_conversation_rounds()
    growth = float(days) * (1.0 + math.log(max(1, rounds)) / 10.0)
    # 阶段阈值调高：按当前纪念日起点，默认应先处于树苗期。
    if growth < 50:
        stage = "seedling"
    elif growth < 140:
        stage = "young"
    elif growth < 320:
        stage = "big"
    else:
        stage = "lush"
    month = int(today.split("-", 2)[1]) if "-" in today else 1
    season = _season_label(month)
    if season == "winter":
        weather_fx = "snowy"
    elif season == "summer":
        weather_fx = "sunny"
    else:
        weather_fx = "rainy"
    milestones = {
        "days": [30, 100, 365],
        "rounds": [300, 1000, 3000],
        "reachedDays": [x for x in (30, 100, 365) if days >= x],
        "reachedRounds": [x for x in (300, 1000, 3000) if rounds >= x],
    }
    mood = r2_store.get_miniapp_mood_meter() or _generate_mood_meter(today)
    if not (r2_store.get_miniapp_mood_meter() or {}).get("date"):
        r2_store.save_miniapp_mood_meter(mood)
    return jsonify(
        {
            "ok": True,
            "startDate": start_date,
            "today": today,
            "daysTogether": days,
            "totalRounds": rounds,
            "growth": round(growth, 2),
            "stage": stage,
            "season": season,
            "weatherFx": weather_fx,
            "milestones": milestones,
            "mood": mood,
        }
    )


@bp.route("/daily-report", methods=["GET"])
def miniapp_daily_report():
    today = today_beijing()
    data = r2_store.get_miniapp_daily_report() or {}
    if str(data.get("report_date") or "") != today:
        data = _generate_daily_report(today)
        r2_store.save_miniapp_daily_report(data)
    return jsonify({"ok": True, "report": data})


@bp.route("/daily-report/refresh", methods=["POST"])
def miniapp_daily_report_refresh():
    today = today_beijing()
    data = _generate_daily_report(today)
    ok = r2_store.save_miniapp_daily_report(data)
    return jsonify({"ok": bool(ok), "report": data})


# 兼容旧前端路径：与 daily-report 行为一致
@bp.route("/weekly-report", methods=["GET"])
def miniapp_weekly_report():
    return miniapp_daily_report()


@bp.route("/weekly-report/refresh", methods=["POST"])
def miniapp_weekly_report_refresh():
    return miniapp_daily_report_refresh()


@bp.route("/mood-meter", methods=["GET"])
def miniapp_mood_meter():
    today = today_beijing()
    data = _generate_mood_meter(today)
    r2_store.save_miniapp_mood_meter(data)
    return jsonify({"ok": True, "mood": data})


@bp.route("/mood-meter/refresh", methods=["POST"])
def miniapp_mood_meter_refresh():
    today = today_beijing()
    data = _generate_mood_meter(today)
    ok = r2_store.save_miniapp_mood_meter(data)
    return jsonify({"ok": bool(ok), "mood": data})


@bp.route("/cyber-tree/start-date", methods=["PUT"])
def miniapp_set_cyber_tree_start_date():
    data = request.get_json(silent=True) or {}
    start_date = str(data.get("startDate") or "").strip()
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except Exception:
        return jsonify({"ok": False, "error": "startDate 格式需为 YYYY-MM-DD"}), 400
    meta = r2_store.get_cyber_tree_meta() or {}
    meta["startDate"] = start_date
    meta["updatedAt"] = now_beijing_iso()
    ok = r2_store.save_cyber_tree_meta(meta)
    return jsonify({"ok": bool(ok), "startDate": start_date})


@bp.route("/windows", methods=["GET"])
def miniapp_windows():
    limit = request.args.get("limit", type=int, default=50)
    if limit > 200:
        limit = 200
    items = whitelist_store.list_recent_windows(limit=limit)
    whitelist = set(whitelist_store.list_whitelist())
    blacklist = set(blacklist_store.list_blacklist())
    for w in items:
        w["whitelisted"] = w.get("id") in whitelist
        w["blacklisted"] = w.get("id") in blacklist
    return jsonify({"windows": items})


@bp.route("/windows/<window_id>/rounds", methods=["GET"])
def miniapp_rounds(window_id: str):
    preview_chars = request.args.get("preview_chars", type=int, default=60)
    if preview_chars < 0:
        preview_chars = 0
    if preview_chars > 200:
        preview_chars = 200
    rounds = r2_store.list_conversation_rounds_preview(window_id or "", preview_chars=preview_chars)
    return jsonify({"window_id": window_id or "", "rounds": rounds, "count": len(rounds)})


@bp.route("/windows/<window_id>/conversation", methods=["GET"])
def miniapp_conversation(window_id: str):
    last_n = request.args.get("last_n", type=int, default=20)
    if last_n < 1:
        last_n = 1
    if last_n > 200:
        last_n = 200
    rounds = r2_store.get_conversation_rounds(window_id or "", last_n=last_n)
    return jsonify({"window_id": window_id or "", "rounds": rounds, "count": len(rounds)})


@bp.route("/windows/<window_id>/rounds/<int:round_index>", methods=["GET"])
def miniapp_round_detail(window_id: str, round_index: int):
    if round_index < 1:
        return jsonify({"error": "round_index 无效"}), 400
    r = r2_store.get_conversation_round_by_index(window_id or "", round_index)
    if not r:
        return jsonify({"ok": False, "error": "未找到该轮"}), 404
    return jsonify({"ok": True, "window_id": window_id or "", "round": r})


@bp.route("/windows/<window_id>/rounds/<int:round_index>", methods=["DELETE"])
def miniapp_delete_round(window_id: str, round_index: int):
    if round_index < 1:
        return jsonify({"error": "round_index 无效"}), 400
    ok = r2_store.delete_conversation_round(window_id or "", round_index)
    return jsonify({"ok": ok, "window_id": window_id or "", "round_index": round_index})


@bp.route("/reasoning/latest", methods=["GET"])
def miniapp_reasoning_latest():
    """
    返回最新思维链（默认 10 条）：
    - 优先最近窗口里最新的 tg_*
    - 回退最近窗口第一条
    - 仅返回 reasoning，不返回原文 content
    """
    limit = request.args.get("limit", type=int, default=10)
    if limit < 1:
        limit = 1
    if limit > 30:
        limit = 30

    recent = whitelist_store.list_recent_windows(limit=200) or []
    target = ""
    for w in recent:
        wid = (w.get("id") or "").strip()
        if wid.startswith("tg_"):
            target = wid
            break
    if not target and recent:
        target = (recent[0].get("id") or "").strip()

    if not target:
        return jsonify({"ok": True, "window_id": "", "items": [], "count": 0})

    rounds = r2_store.get_conversation_rounds(target, last_n=200) or []
    out = []
    for r in reversed(rounds):
        idx = int(r.get("index") or 0)
        ts = (r.get("timestamp") or "").strip()
        msgs = r.get("messages") or []
        reasoning_text = ""
        for m in reversed(msgs):
            role = (m.get("role") or "").strip().lower() if isinstance(m, dict) else ""
            if role != "assistant":
                continue
            val = (
                (m.get("reasoning") or m.get("reasoning_content") or m.get("thinking") or "").strip()
                if isinstance(m, dict)
                else ""
            )
            if val:
                reasoning_text = val
                break
        if reasoning_text:
            out.append({"index": idx, "timestamp": ts, "reasoning": reasoning_text})
        if len(out) >= limit:
            break

    return jsonify({"ok": True, "window_id": target, "items": out, "count": len(out)})


@bp.route("/schedule/items", methods=["GET"])
def miniapp_schedule_items():
    items = r2_store.get_schedule_items() or []
    enabled_count = len([x for x in items if bool(x.get("enabled", True))])
    return jsonify({"ok": True, "items": items, "count": len(items), "enabled_count": enabled_count})


@bp.route("/schedule/items", methods=["POST"])
def miniapp_create_schedule_item():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    datetime_str = (data.get("datetime") or "").strip()
    repeat = (data.get("repeat") or "once").strip().lower()
    note = (data.get("note") or "").strip()
    enabled = bool(data.get("enabled", True))
    weekly_weekday = data.get("weekly_weekday", None)
    weekly_weekdays = data.get("weekly_weekdays", None)
    weekly_time = (data.get("weekly_time") or "").strip()
    daily_time = (data.get("daily_time") or "").strip()
    created_by = (data.get("created_by") or "wife").strip().lower()
    if created_by not in ("wife", "du"):
        created_by = "wife"
    target_role = (data.get("target_role") or "wife").strip().lower()
    if target_role not in ("wife", "du"):
        target_role = "wife"

    if not title:
        return jsonify({"ok": False, "error": "title 不能为空"}), 400
    if repeat not in ("once", "daily", "weekly"):
        repeat = "once"
    if repeat == "weekly":
        weekday_list: list[int] = []
        if isinstance(weekly_weekdays, list):
            for x in weekly_weekdays:
                try:
                    w = int(x)
                except Exception:
                    continue
                if 0 <= w <= 6:
                    weekday_list.append(w)
        elif weekly_weekday is not None:
            try:
                w = int(weekly_weekday)
                if 0 <= w <= 6:
                    weekday_list.append(w)
            except Exception:
                pass
        weekday_list = sorted(set(weekday_list))
        if not weekday_list:
            return jsonify({"ok": False, "error": "weekly_weekdays 无效"}), 400
        try:
            hh, mm = (weekly_time.split(":", 1) + ["0"])[:2]
            hhi = int(hh)
            mmi = int(mm)
            if hhi < 0 or hhi > 23 or mmi < 0 or mmi > 59:
                raise ValueError("invalid")
        except Exception:
            return jsonify({"ok": False, "error": "weekly_time 格式无效"}), 400
        created_items = []
        for w in weekday_list:
            item = r2_store.create_schedule_item(
                title=title,
                datetime_str="",
                repeat=repeat,
                note=note,
                enabled=enabled,
                weekly_weekday=w,
                weekly_time=weekly_time,
                daily_time=daily_time,
                created_by=created_by,
                target_role=target_role,
            )
            if item:
                created_items.append(item)
        if not created_items:
            return jsonify({"ok": False, "error": "创建失败"}), 500
        _notify_schedule_runtime_changed()
        return jsonify({"ok": True, "items": created_items, "count": len(created_items)})
    elif repeat == "daily":
        try:
            hh, mm = (daily_time.split(":", 1) + ["0"])[:2]
            hhi = int(hh)
            mmi = int(mm)
            if hhi < 0 or hhi > 23 or mmi < 0 or mmi > 59:
                raise ValueError("invalid")
        except Exception:
            return jsonify({"ok": False, "error": "daily_time 格式无效"}), 400
    else:
        if not datetime_str:
            return jsonify({"ok": False, "error": "datetime 不能为空"}), 400
        # 允许 ISO（2026-03-20T09:30[:ss][+08:00]）及 datetime-local（2026-03-20T09:30）
        try:
            datetime.fromisoformat(datetime_str)
        except Exception:
            return jsonify({"ok": False, "error": "datetime 格式无效"}), 400

    item = r2_store.create_schedule_item(
        title=title,
        datetime_str=datetime_str,
        repeat=repeat,
        note=note,
        enabled=enabled,
        weekly_weekday=weekly_weekday,
        weekly_time=weekly_time,
        daily_time=daily_time,
        created_by=created_by,
        target_role=target_role,
    )
    if not item:
        return jsonify({"ok": False, "error": "创建失败"}), 500
    _notify_schedule_runtime_changed()
    return jsonify({"ok": True, "item": item})


@bp.route("/schedule/items/<item_id>/disable", methods=["PUT"])
def miniapp_disable_schedule_item(item_id: str):
    iid = (item_id or "").strip()
    if not iid:
        return jsonify({"ok": False, "error": "缺少 item_id"}), 400
    ok = r2_store.disable_schedule_item(iid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到条目或已是禁用状态"}), 404
    _notify_schedule_runtime_changed()
    return jsonify({"ok": True, "id": iid, "action": "disable_future"})


@bp.route("/schedule/items/<item_id>/enable", methods=["PUT"])
def miniapp_enable_schedule_item(item_id: str):
    iid = (item_id or "").strip()
    if not iid:
        return jsonify({"ok": False, "error": "缺少 item_id"}), 400
    ok = r2_store.enable_schedule_item(iid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到条目或已是启用状态"}), 404
    _notify_schedule_runtime_changed()
    return jsonify({"ok": True, "id": iid, "action": "enable"})


@bp.route("/schedule/items/<item_id>", methods=["DELETE"])
def miniapp_delete_schedule_item(item_id: str):
    iid = (item_id or "").strip()
    if not iid:
        return jsonify({"ok": False, "error": "缺少 item_id"}), 400
    ok = r2_store.delete_schedule_item(iid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到该条目"}), 404
    _notify_schedule_runtime_changed()
    return jsonify({"ok": True, "id": iid, "action": "delete"})


@bp.route("/dynamic-memory", methods=["GET"])
def miniapp_dynamic_memory():
    try:
        lst = r2_store.get_dynamic_memory_list() or []
        return jsonify({"ok": True, "count": len(lst), "memories": lst})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "memories": []}), 500


@bp.route("/memory-debug", methods=["GET"])
def miniapp_memory_debug():
    """
    记忆调试视图：
    - 当前窗口记忆总结（summary）
    - 最近动态记忆召回明细（每次注入时记录）
    """
    try:
        limit = request.args.get("limit", type=int, default=10)
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100
        target = ""
        recent = whitelist_store.list_recent_windows(limit=200) or []
        for w in recent:
            wid = (w.get("id") or "").strip()
            if wid.startswith("tg_"):
                target = wid
                break
        if not target and recent:
            target = (recent[0].get("id") or "").strip()
        summary = (r2_store.get_summary(target) or "").strip()
        all_events = r2_store.get_dynamic_recall_debug_events(limit=limit) or []
        if not all_events:
            live_preview = _build_live_dynamic_recall_preview(target)
            if live_preview:
                all_events = [live_preview]
        scope = str(request.args.get("scope") or "all").strip().lower()
        if scope not in ("all", "target"):
            scope = "all"
        if scope == "target" and target:
            events = [e for e in all_events if str((e or {}).get("window_id") or "").strip() in (target, "__default__")]
        else:
            events = all_events
        dynamic_stats = {}
        try:
            from memory_vector.config import (
                VECTOR_MIN_SIM,
                VECTOR_TOPK,
                VECTOR_TOPN,
                CF_ACCOUNT_ID,
                CF_API_TOKEN,
                CF_EMBEDDING_MODEL,
                EMBEDDING_MODEL,
                EMBED_REQUEST_TIMEOUT_SECONDS,
                EMBED_MAX_RETRIES,
                EMBED_RETRY_BACKOFF_SECONDS,
                current_embedding_model,
                current_embedding_backend,
            )
            from memory_vector.vector_index_store import list_existing_tags
            mems = r2_store.get_dynamic_memory_list() or []
            mem_tags = sorted({str((m or {}).get("tag") or "").strip() for m in mems if str((m or {}).get("tag") or "").strip()})
            recent_vector_error = ""
            for e in all_events:
                msg = str((e or {}).get("vector_error") or "").strip()
                if msg:
                    recent_vector_error = msg
                    break
            failed_ids_count = 0
            failed_ids_preview: list[str] = []
            try:
                failed_path = Path(__file__).resolve().parent.parent / "data" / "rebuild_index_failed_ids.json"
                if failed_path.exists():
                    failed_payload = json.loads(failed_path.read_text(encoding="utf-8"))
                    failed_ids = failed_payload.get("failed_ids") if isinstance(failed_payload, dict) else []
                    if isinstance(failed_ids, list):
                        failed_ids_preview = [str(x).strip() for x in failed_ids if str(x).strip()][:10]
                        failed_ids_count = len([x for x in failed_ids if str(x).strip()])
            except Exception:
                failed_ids_count = 0
                failed_ids_preview = []
            dynamic_stats = {
                "memory_count": len(mems),
                "memory_tags": mem_tags[:30],
                "index_tags": (list_existing_tags() or [])[:50],
                "vector_min_sim": float(VECTOR_MIN_SIM),
                "vector_topk": int(VECTOR_TOPK),
                "vector_topn": int(VECTOR_TOPN),
                "embedding_backend": current_embedding_backend(),
                "embedding_model": current_embedding_model() or (CF_EMBEDDING_MODEL if (CF_ACCOUNT_ID and CF_API_TOKEN) else EMBEDDING_MODEL),
                "embed_timeout_seconds": int(EMBED_REQUEST_TIMEOUT_SECONDS),
                "embed_max_retries": int(EMBED_MAX_RETRIES),
                "embed_retry_backoff_seconds": float(EMBED_RETRY_BACKOFF_SECONDS),
                "recent_vector_error": recent_vector_error,
                "failed_ids_count": failed_ids_count,
                "failed_ids_preview": failed_ids_preview,
            }
        except Exception:
            dynamic_stats = {}
        return jsonify(
            {
                "ok": True,
                "window_id": target,
                "scope": scope,
                "summary": summary,
                "summary_exists": bool(summary),
                "recalls": events,
                "count": len(events),
                "total_count": len(all_events),
                "dynamic_stats": dynamic_stats,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "summary": "", "recalls": [], "count": 0}), 500


@bp.route("/core_cache", methods=["GET"])
def miniapp_core_cache():
    pending = r2_store.get_core_cache_pending() or []
    return jsonify({"pending": pending, "count": len(pending)})


@bp.route("/core_cache/<entry_id>", methods=["DELETE"])
def miniapp_delete_core_cache(entry_id: str):
    if not entry_id:
        return jsonify({"error": "缺少 entry_id"}), 400
    ok = r2_store.delete_core_cache_by_id(entry_id)
    return jsonify({"ok": ok, "id": entry_id})


@bp.route("/notebook", methods=["GET"])
def miniapp_notebook_list():
    entries = r2_store.get_notebook_entries() or []
    return jsonify({"entries": entries, "count": len(entries)})


@bp.route("/notebook", methods=["POST"])
def miniapp_notebook_add():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "缺少 content"}), 400
    ok = r2_store.notebook_append_entry(content)
    return jsonify({"ok": ok})


@bp.route("/notebook/<ts>", methods=["DELETE"])
def miniapp_notebook_delete(ts: str):
    ts = (ts or "").strip()
    if not ts:
        return jsonify({"error": "缺少 timestamp"}), 400
    ok = r2_store.notebook_delete_entry_by_timestamp(ts)
    return jsonify({"ok": ok, "timestamp": ts})


@bp.route("/du-notebook", methods=["GET"])
def miniapp_du_notebook_list():
    items = r2_store.get_du_notebook_entries() or []
    return jsonify({"ok": True, "items": items, "count": len(items)})


@bp.route("/du-notebook", methods=["POST"])
def miniapp_du_notebook_add():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    entry = r2_store.add_du_notebook_entry(content)
    if not entry:
        return jsonify({"ok": False, "error": "新增失败"}), 500
    return jsonify({"ok": True, "entry": entry})


@bp.route("/du-notebook/<entry_id>", methods=["PUT"])
def miniapp_du_notebook_update(entry_id: str):
    eid = (entry_id or "").strip()
    if not eid:
        return jsonify({"ok": False, "error": "缺少 entry_id"}), 400
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    ok = r2_store.update_du_notebook_entry(eid, content)
    if not ok:
        return jsonify({"ok": False, "error": "未找到条目或更新失败"}), 404
    return jsonify({"ok": True, "id": eid})


@bp.route("/du-notebook/<entry_id>", methods=["DELETE"])
def miniapp_du_notebook_delete(entry_id: str):
    eid = (entry_id or "").strip()
    if not eid:
        return jsonify({"ok": False, "error": "缺少 entry_id"}), 400
    ok = r2_store.delete_du_notebook_entry(eid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到该条目"}), 404
    return jsonify({"ok": True, "id": eid})


@bp.route("/core-prompt", methods=["GET"])
def miniapp_get_core_prompt():
    """
    读取“核心 Prompt（3.16）”：
    - 若 R2 已有自定义内容，返回该内容
    - 否则回退读取本地 prompts/du_core_prompt.txt（只读展示）
    """
    text = r2_store.get_core_prompt_text()
    source = "r2"
    if text is None:
        source = "file"
        try:
            p = Path(__file__).resolve().parent.parent / "prompts" / "du_core_prompt.txt"
            text = p.read_text(encoding="utf-8") if p.exists() else ""
        except Exception:
            text = ""
    return jsonify({"ok": True, "source": source, "content": (text or "")})


@bp.route("/core-prompt", methods=["PUT"])
def miniapp_put_core_prompt():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    ok = r2_store.save_core_prompt_text(content)
    return jsonify({"ok": ok})


@bp.route("/background-config", methods=["GET"])
def miniapp_get_background_config():
    data = r2_store.get_miniapp_bg_config() or {}
    return jsonify(
        {
            "ok": True,
            "config": {
                "preset": (data.get("preset") or "cream"),
                "useImage": bool(data.get("useImage")),
                "imageVersion": int(data.get("imageVersion") or 0),
                "dim": int(data.get("dim") or 20),
            },
        }
    )


@bp.route("/background-config", methods=["PUT"])
def miniapp_put_background_config():
    data = request.get_json(silent=True) or {}
    preset = (data.get("preset") or "cream").strip()
    if preset not in ("cream", "grid", "soft"):
        preset = "cream"
    dim = int(data.get("dim") or 20)
    dim = max(0, min(70, dim))
    use_image = bool(data.get("useImage"))
    image_version = int(data.get("imageVersion") or 0)
    # 防止客户端携带旧 draft 覆盖新图版本号：配置保存时版本号只允许前进不回退。
    current = r2_store.get_miniapp_bg_config() or {}
    current_ver = int(current.get("imageVersion") or 0)
    payload = {
        "preset": preset,
        "useImage": use_image,
        "imageVersion": max(current_ver, max(0, image_version)),
        "dim": dim,
    }
    ok = r2_store.save_miniapp_bg_config(payload)
    return jsonify({"ok": ok, "config": payload})


@bp.route("/background-image", methods=["POST"])
def miniapp_upload_background_image():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "缺少 file"}), 400
    ctype = (f.mimetype or "").strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        return jsonify({"ok": False, "error": "仅支持 jpg/png/webp/gif"}), 400
    content = f.read()
    if not content:
        return jsonify({"ok": False, "error": "文件为空"}), 400
    if len(content) > 8 * 1024 * 1024:
        return jsonify({"ok": False, "error": "图片过大（最大 8MB）"}), 400
    conf = r2_store.get_miniapp_bg_config() or {}
    # 用毫秒时间戳，且保证严格递增，避免同一秒内二次上传命中同一个版本号导致前端继续读旧缓存。
    old_ver = int(conf.get("imageVersion") or 0)
    new_ver = int(time.time() * 1000)
    if new_ver <= old_ver:
        new_ver = old_ver + 1

    # 同时写“最新别名键 + 版本化键”，规避顽固缓存回旧图问题
    ok = r2_store.save_miniapp_bg_image(content, ctype, image_version=new_ver)
    if not ok:
        return jsonify({"ok": False, "error": "保存失败"}), 500
    conf["imageVersion"] = new_ver
    conf["useImage"] = True
    conf["dim"] = max(0, min(70, int(conf.get("dim") or 20)))
    conf["preset"] = conf.get("preset") or "cream"
    r2_store.save_miniapp_bg_config(conf)
    return jsonify({"ok": True, "imageVersion": int(conf["imageVersion"])})


@bp.route("/background-image", methods=["GET"])
def miniapp_get_background_image():
    data, ctype = r2_store.get_miniapp_bg_image()
    if not data:
        return jsonify({"ok": False, "error": "暂无背景图"}), 404
    # 背景图支持频繁替换：这里禁用强缓存，实际刷新仍由 imageVersion 控制兜底。
    return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})


@bp.route("/background-image/<int:image_version>", methods=["GET"])
def miniapp_get_background_image_versioned(image_version: int):
    """
    版本化路径读取背景图：
    - 目的：避免 WebView/代理对同一路径缓存过于激进导致“明明上传了仍显示旧图”。
    - 实际图片仍取当前存储，版本号用于强制路径变化。
    """
    data, ctype = r2_store.get_miniapp_bg_image(image_version=image_version)
    if not data:
        return jsonify({"ok": False, "error": "暂无背景图"}), 404
    return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})


# ---------- 表情包 stickers/（MiniApp 管理 + 无公网时读图代理） ----------


@bp.route("/stickers/tags", methods=["GET"])
def miniapp_stickers_tags():
    from services.sticker_tags import STICKER_EMOTION_TAGS

    return jsonify({"ok": True, "tags": list(STICKER_EMOTION_TAGS)})


@bp.route("/stickers/mapping", methods=["GET"])
def miniapp_stickers_mapping_get():
    m = r2_store.get_stickers_mapping() or {}
    return jsonify(
        {
            "ok": True,
            "mapping": m,
            "public_base": (R2_PUBLIC_URL or "").strip().rstrip("/"),
        }
    )


@bp.route("/stickers/rebuild", methods=["POST"])
def miniapp_stickers_rebuild():
    data = r2_store.rebuild_stickers_mapping_from_r2()
    ok = r2_store.save_stickers_mapping(data)
    return jsonify({"ok": bool(ok), "mapping": data})


@bp.route("/stickers/upload", methods=["POST"])
def miniapp_stickers_upload():
    tag = (request.form.get("tag") or "").strip().lower()
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "缺少 file"}), 400
    content = f.read()
    if not content:
        return jsonify({"ok": False, "error": "文件为空"}), 400
    if len(content) > 8 * 1024 * 1024:
        return jsonify({"ok": False, "error": "单张不超过 8MB"}), 400
    ctype = (f.mimetype or "").strip().lower() or "image/jpeg"
    key = r2_store.upload_sticker_file(tag, f.filename or "sticker.jpg", content, ctype)
    if not key:
        return jsonify({"ok": False, "error": "上传失败（检查标签名与格式 jpg/png/webp/gif）"}), 400
    return jsonify({"ok": True, "key": key})


@bp.route("/stickers/item", methods=["DELETE"])
def miniapp_stickers_delete():
    body = request.get_json(silent=True) or {}
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "缺少 key"}), 400
    ok = r2_store.delete_sticker_object(key)
    if not ok:
        return jsonify({"ok": False, "error": "删除失败或 key 无效"}), 400
    return jsonify({"ok": True, "key": key})


@bp.route("/stickers/raw", methods=["GET"])
def miniapp_stickers_raw():
    """无 R2 公网域名时，前端用此 URL 预览图片（需 MiniApp 鉴权）。"""
    key = (request.args.get("key") or "").strip()
    if not key.startswith("stickers/") or ".." in key:
        return jsonify({"ok": False, "error": "key 无效"}), 400
    data, ctype = r2_store.get_object_bytes(key)
    if not data:
        return jsonify({"ok": False, "error": "未找到"}), 404
    mt = ctype if ctype and ctype.startswith("image/") else "image/jpeg"
    return Response(data, mimetype=mt, headers={"Cache-Control": "public, max-age=300"})


@bp.route("/logs", methods=["GET"])
def miniapp_logs_tail():
    lines = request.args.get("lines", type=int, default=200)
    if lines < 1:
        lines = 1
    if lines > 2000:
        lines = 2000
    try:
        out_lines = tail_logs(MINIAPP_LOG_FILE, lines=lines)
        file_exists = False
        try:
            log_file = (MINIAPP_LOG_FILE or "").strip()
            if log_file:
                base_dir = Path(__file__).resolve().parent.parent
                p = Path(log_file)
                if not p.is_absolute():
                    p = base_dir / log_file
                file_exists = p.exists()
        except Exception:
            file_exists = False
        return jsonify(
            {
                "ok": True,
                "file": MINIAPP_LOG_FILE,
                "lines": out_lines,
                "count": len(out_lines),
                "source": "file" if file_exists else "stdout",
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/logs/stream", methods=["GET"])
def miniapp_logs_stream():
    # SSE：类 tail -f
    start_lines = request.args.get("start_lines", type=int, default=80)
    if start_lines < 0:
        start_lines = 0
    if start_lines > 500:
        start_lines = 500

    def gen():
        # 给客户端一个 ready 信号，避免某些代理等到首 chunk 才认为连接成功
        yield b": ready\n\n"
        time.sleep(0.01)
        yield from stream_logs_sse(MINIAPP_LOG_FILE, start_lines=start_lines)

    return Response(
        stream_with_context(gen()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/upstreams", methods=["GET"])
def miniapp_get_upstreams():
    data = upstream_store.load_upstreams()
    # 不把 api_key 明文回传到前端；仅用于显示与切换
    items = [
        {"name": it.get("name") or "", "url": it.get("url") or ""}
        for it in (data.get("items") or [])
    ]
    return jsonify({"active": int(data.get("active") or 0), "items": items})


@bp.route("/upstreams", methods=["PUT"])
def miniapp_put_upstreams():
    """
    切换 active（只允许切换，不允许新增/删除 URL）。
    """
    data = request.get_json(silent=True) or {}
    active = int(data.get("active") or 0)
    ok = upstream_store.set_active(active)
    saved = upstream_store.load_upstreams()
    return jsonify({"ok": ok, "active": int(saved.get("active") or 0)})


@bp.route("/upstreams/active", methods=["PUT"])
def miniapp_set_active_upstream():
    data = request.get_json(silent=True) or {}
    idx = int(data.get("active") or 0)
    ok = upstream_store.set_active(idx)
    return jsonify({"ok": ok, "active": idx})


def _chat_url_to_models_url(chat_url: str) -> str:
    base = (chat_url or "").strip().rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/v1/models"


def _probe_upstream_item(it: dict) -> dict:
    url = (it.get("url") or "").strip()
    name = (it.get("name") or "").strip()
    api_key = (it.get("api_key") or "").strip()
    out = {
        "name": name,
        "url": url,
        "models_ok": False,
        "chat_ok": False,
        "models_status": 0,
        "chat_status": 0,
        "model_count": 0,
        "error": "",
        "note": "",
        "status": "fail",
    }
    if not url:
        out["error"] = "URL 为空"
        return out

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    model_name = ""
    try:
        models_url = _chat_url_to_models_url(url)
        rm = requests.get(models_url, headers=headers, timeout=12)
        out["models_status"] = int(rm.status_code or 0)
        if rm.status_code >= 400:
            logger.warning(
                "上游探活 models 异常 name=%s status=%s url=%s body=%s",
                name or "(empty)",
                rm.status_code,
                models_url,
                (rm.text or "")[:300],
            )
        if 200 <= rm.status_code < 300:
            data = rm.json() if rm.content else {}
            lst = data.get("data") if isinstance(data, dict) else None
            if isinstance(lst, list):
                out["model_count"] = len(lst)
                if lst:
                    first = lst[0]
                    if isinstance(first, dict):
                        model_name = str(first.get("id") or "").strip()
                    elif isinstance(first, str):
                        model_name = first.strip()
            out["models_ok"] = True
    except Exception as e:
        out["error"] = str(e)

    if not model_name:
        out["note"] = "models 未返回可用模型，已跳过 chat 探活"
        if out["models_ok"]:
            out["status"] = "degraded"
        return out

    try:
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_tokens": 8,
        }
        rc = requests.post(url, headers=headers, json=body, timeout=20)
        out["chat_status"] = int(rc.status_code or 0)
        if rc.status_code >= 400:
            logger.warning(
                "上游探活 chat 异常 name=%s status=%s model=%s url=%s body=%s",
                name or "(empty)",
                rc.status_code,
                model_name,
                url,
                (rc.text or "")[:300],
            )
        if 200 <= rc.status_code < 300:
            out["chat_ok"] = True
    except Exception as e:
        msg = str(e)
        if "Read timed out" in msg and out["models_ok"]:
            out["note"] = "chat 探活超时（上游可能可用，但较慢）"
        elif not out["error"]:
            out["error"] = msg

    # 探活以“chat 实际可用”优先：
    # - chat_ok=True：即便 /v1/models 不标准或暂时失败，也至少算可用（或部分异常）
    # - models_ok=True 但 chat_ok=False：只能算部分异常，不能算真正可用
    if out["chat_ok"] and out["models_ok"]:
        out["status"] = "ok"
    elif out["chat_ok"]:
        out["status"] = "degraded"
        if not out["note"]:
            out["note"] = "chat 可用，但 models 探测失败或上游未标准实现 /v1/models"
    elif out["models_ok"]:
        out["status"] = "degraded"
    return out


@bp.route("/upstreams/probe", methods=["POST"])
def miniapp_probe_upstreams():
    data = request.get_json(silent=True) or {}
    idx = data.get("index", None)
    probe_all = bool(data.get("all"))
    upstreams = upstream_store.load_upstreams()
    items = upstreams.get("items") or []
    active = int(upstreams.get("active") or 0)

    targets: list[tuple[int, dict]] = []
    if probe_all:
        targets = [(i, it) for i, it in enumerate(items) if isinstance(it, dict)]
    else:
        try:
            i = int(idx if idx is not None else active)
        except Exception:
            i = active
        if i < 0 or i >= len(items):
            return jsonify({"ok": False, "error": "index 无效"}), 400
        targets = [(i, items[i])]

    results = []
    for i, it in targets:
        r = _probe_upstream_item(it)
        r["index"] = i
        r["isActive"] = i == active
        results.append(r)

    status = "ok"
    if any((x.get("status") == "fail") for x in results):
        status = "degraded" if any((x.get("status") == "ok") for x in results) else "fail"
    return jsonify({"ok": True, "status": status, "results": results, "count": len(results)})
