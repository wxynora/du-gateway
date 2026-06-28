from __future__ import annotations

import re
import threading
from collections import Counter
from datetime import datetime

from flask import jsonify, request

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from services.reply_channel_context import resolve_recent_reply_context
from services.pixel_home import (
    build_pixel_home_body_event,
    build_pixel_home_event,
    build_pixel_home_state,
    normalize_spot,
    save_actor_state,
    save_du_body_state,
)
from services.spring_dream import (
    get_spring_dream_archive,
    get_spring_dream_inspiration,
    list_spring_dream_fragment_library,
    list_spring_dream_archives,
    save_spring_dream_inspiration,
)
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, today_beijing


_DAILY_KW_STOPWORDS = {
    "今天",
    "现在",
    "这个",
    "那个",
    "然后",
    "就是",
    "还是",
    "感觉",
    "我们",
    "你们",
    "他们",
    "自己",
    "已经",
    "一下",
    "可能",
    "因为",
    "所以",
    "如果",
    "但是",
    "而且",
    "以及",
    "其实",
    "真的",
    "不会",
    "可以",
    "不要",
    "还有",
    "一个",
    "这个时候",
    "然后呢",
    "知道了",
}

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


def _extract_daily_keywords(texts: list[str], limit: int = 3) -> list[str]:
    """
    从文本中提取高频关键词（中英文），避免固定词表导致“每天都一样”。
    """
    tokens: list[str] = []
    for raw in texts or []:
        s = str(raw or "").strip()
        if not s:
            continue
        for t in re.findall(r"[\u4e00-\u9fff]{2,6}", s):
            t = t.strip()
            if t and t not in _DAILY_KW_STOPWORDS:
                tokens.append(t)
        for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,24}", s):
            lo = t.lower().strip()
            if lo and lo not in _DAILY_KW_STOPWORDS:
                tokens.append(lo)
    if not tokens:
        return []
    cnt = Counter(tokens)
    ranked = sorted(cnt.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [k for k, _ in ranked[: max(1, int(limit or 3))]]


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


def _pixel_home_wakeup_context() -> tuple[str, str, str, dict]:
    payload = request.environ.get("miniapp_panel_payload") or {}
    default_target = str(payload.get("device_id") or "").strip()
    context = resolve_recent_reply_context(default_target=default_target)
    return (
        str(context.get("window_id") or "").strip(),
        str(context.get("target") or "").strip(),
        str(context.get("channel") or "").strip().lower(),
        context.get("meta") if isinstance(context.get("meta"), dict) else {},
    )


def _queue_pixel_home_wakeup(event_text: str) -> dict:
    window_id, target, channel, meta = _pixel_home_wakeup_context()
    if not window_id:
        return {"ok": False, "error": "missing_window_id"}

    def _run_pixel_home_wakeup():
        try:
            from services.conversation_followup import send_pixel_home_wakeup

            send_pixel_home_wakeup(
                window_id=window_id,
                target=target,
                event_text=event_text,
                preferred_channel=channel,
                preferred_meta=meta,
            )
        except Exception as e:
            get_logger(__name__).warning("pixel home wakeup failed window_id=%s error=%s", window_id, e)

    threading.Thread(target=_run_pixel_home_wakeup, name="pixel-home-wakeup", daemon=True).start()
    return {"ok": True, "queued": True}


def _generate_daily_report(today: str) -> dict:
    """按北京日期统计「今日」对话轮次与关键词（从最近存档中筛当日）。"""
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    window_id = f"tg_{uid}" if uid > 0 else ""
    # 拉取足够多的最近轮次，再按日期过滤（单日上限通常远小于此）
    all_rounds = r2_store.get_conversation_rounds(window_id, last_n=500) if window_id else []
    day_rounds: list[dict] = []
    user_text: list[str] = []
    all_text: list[str] = []
    for r in all_rounds or []:
        dt = _parse_beijing_dt(r.get("timestamp"))
        if not dt:
            continue
        if dt.strftime("%Y-%m-%d") != today:
            continue
        day_rounds.append(r)
        for m in (r.get("messages") or []):
            if not isinstance(m, dict):
                continue
            tx = _message_text(m.get("content"))
            if not tx:
                continue
            all_text.append(tx)
            role = str(m.get("role") or "").strip().lower()
            if role == "user":
                user_text.append(tx)
    rounds_count = len(day_rounds)
    # 优先用户消息关键词，避免被助手高频措辞“刷屏”成固定词。
    hot = _extract_daily_keywords(user_text, limit=3)
    if not hot:
        hot = _extract_daily_keywords(all_text, limit=3)
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


def _mood_day_wave(seed_text: str) -> int:
    seed = sum(ord(ch) for ch in (seed_text or ""))
    return (seed % 5) - 2


def _extract_last_user_message_text(msgs: list[dict]) -> str:
    for m in reversed(msgs or []):
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip().lower() != "user":
            continue
        text = _message_text(m.get("content"))
        if text:
            return text
    return ""


def _tool_call_name(tc: dict) -> str:
    if not isinstance(tc, dict):
        return ""
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    return str(fn.get("name") or "").strip()


def _summarize_alarm_actions(msgs: list[dict]) -> list[str]:
    labels: list[str] = []
    for m in msgs or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip().lower() != "assistant":
            continue
        tcs = m.get("tool_calls") or []
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            name = _tool_call_name(tc)
            if not name:
                continue
            label = ""
            if name == "exchange_diary_create":
                label = "写了日记"
            elif name == "daily_whisper_write":
                label = "写了气泡"
            elif name in {"forum_read_feed", "forum_open_thread"}:
                label = "看了论坛"
            elif name == "note_write":
                label = "写了便签"
            elif name in {
                "schedule_list",
                "get_time_info",
                "search_memory",
                "exchange_diary_list",
                "exchange_diary_read",
                "exchange_diary_comment_create",
            }:
                label = ""
            if label and label not in labels:
                labels.append(label)
    return labels


def _build_du_day_events(today: str) -> list[dict]:
    out: list[dict] = []

    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    window_id = f"tg_{uid}" if uid > 0 else ""
    rounds = r2_store.get_conversation_rounds(window_id, last_n=240) if window_id else []
    for r in rounds or []:
        dt = _parse_beijing_dt(r.get("timestamp"))
        if not dt or dt.strftime("%Y-%m-%d") != today:
            continue
        msgs = r.get("messages") or []
        user_text = _extract_last_user_message_text(msgs)
        if not user_text.startswith("你给自己定的「"):
            continue
        actions = _summarize_alarm_actions(msgs)
        out.append(
            {
                "kind": "routine",
                "timestamp": dt.isoformat(),
                "time": dt.strftime("%H:%M"),
                "title": "Morning Alarm",
                "subtitle": "醒来第一件事" if "醒来第一件事" in user_text else "",
                "actions": actions,
            }
        )

    for item in r2_store.get_proactive_decision_memory_items() or []:
        at = str(item.get("at") or "").strip()
        dt = _parse_beijing_dt(at)
        if not dt or dt.strftime("%Y-%m-%d") != today:
            continue
        action = str(item.get("action") or "").strip() or "unknown"
        reason = str(item.get("reason") or "").strip() or "—"
        if action == "error":
            continue
        lowered_reason = reason.lower()
        if "gateway_status=" in lowered_reason or "http 403" in lowered_reason or "403" in lowered_reason:
            continue
        out.append(
            {
                "kind": "decision",
                "timestamp": dt.isoformat(),
                "time": dt.strftime("%H:%M"),
                "title": "Active Reach",
                "decision_label": f"渡选择了 {action}",
                "reason": reason,
            }
        )

    out.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    return out


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


def register_routes(bp) -> None:
    @bp.route("/daily-whisper", methods=["GET"])
    def miniapp_daily_whisper():
        today = today_beijing()
        data = r2_store.get_miniapp_daily_whisper() or {}
        saved_text = str(data.get("text") or "").strip()
        saved_date = str(data.get("date") or "").strip()
        if saved_text:
            return jsonify(
                {
                    "ok": True,
                    "date": saved_date or today,
                    "text": saved_text,
                    "cached": True,
                    "stale": bool(saved_date and saved_date != today),
                    "by": data.get("by") or None,
                    "updatedAt": data.get("updatedAt") or None,
                }
            )
        return jsonify({"ok": True, "date": today, "text": "", "cached": False, "missing": True})

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

    @bp.route("/du-day", methods=["GET"])
    def miniapp_du_day():
        today = today_beijing()
        items = _build_du_day_events(today)
        return jsonify({"ok": True, "date": today, "items": items, "count": len(items)})

    @bp.route("/spring-dream-archives", methods=["GET"])
    def miniapp_spring_dream_archives():
        try:
            limit = int(request.args.get("limit") or 50)
        except Exception:
            limit = 50
        items = list_spring_dream_archives(limit=limit)
        return jsonify({"ok": True, "items": items, "count": len(items)})

    @bp.route("/spring-dream-archives/<archive_id>", methods=["GET"])
    def miniapp_spring_dream_archive_detail(archive_id: str):
        item = get_spring_dream_archive(archive_id)
        if not item:
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/spring-dream-inspiration", methods=["GET"])
    def miniapp_spring_dream_inspiration_get():
        data = get_spring_dream_inspiration()
        return jsonify({"ok": True, **data})

    @bp.route("/spring-dream-fragments", methods=["GET"])
    def miniapp_spring_dream_fragments():
        try:
            limit = int(request.args.get("limit") or 120)
        except Exception:
            limit = 120
        data = list_spring_dream_fragment_library(limit=limit)
        return jsonify({"ok": True, **data})

    @bp.route("/spring-dream-inspiration", methods=["PUT"])
    def miniapp_spring_dream_inspiration_put():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            data = {}
        stars = data.get("stars")
        if stars is None:
            stars = data.get("fragments")
        saved = save_spring_dream_inspiration(stars)
        return jsonify({"ok": True, **saved})

    @bp.route("/pixel-home-state", methods=["GET"])
    def miniapp_pixel_home_state():
        return jsonify(build_pixel_home_state())

    @bp.route("/pixel-home-state/xinyue", methods=["PUT"])
    def miniapp_pixel_home_xinyue_state():
        data = request.get_json(silent=True) or {}
        spot = normalize_spot((data or {}).get("spot") or (data or {}).get("location"), "home")
        activity = str((data or {}).get("activity") or (data or {}).get("doing") or "").strip() or "待着"
        actor = save_actor_state("xinyue", spot, activity, source="manual")
        return jsonify({"ok": bool(actor.get("ok")), "xinyue": actor, "state": build_pixel_home_state()})

    @bp.route("/pixel-home-state/du-body", methods=["PUT"])
    def miniapp_pixel_home_du_body_state():
        data = request.get_json(silent=True) or {}
        body_state = save_du_body_state(data or {})
        event_text = ""
        wakeup = {"ok": False, "skipped": True}
        if body_state.get("toy_changed"):
            event_text = build_pixel_home_body_event(body_state)
            wakeup = _queue_pixel_home_wakeup(event_text)
        return jsonify({"ok": bool(body_state.get("ok")), "du_body_state": body_state, "event_text": event_text, "wakeup": wakeup, "state": build_pixel_home_state()})

    @bp.route("/pixel-home-event", methods=["POST"])
    def miniapp_pixel_home_event():
        data = request.get_json(silent=True) or {}
        spot = normalize_spot((data or {}).get("spot") or (data or {}).get("location"), "home")
        action = str((data or {}).get("action") or (data or {}).get("activity") or "").strip() or "待着"
        actor = save_actor_state("xinyue", spot, action, source="miniapp_event")
        event_text = build_pixel_home_event(spot, action)
        wakeup = _queue_pixel_home_wakeup(event_text)
        return jsonify({"ok": True, "event_text": event_text, "xinyue": actor, "wakeup": wakeup, "state": build_pixel_home_state()})

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
