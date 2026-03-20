import time
import os
from pathlib import Path
from datetime import datetime

import requests
from flask import Blueprint, Response, jsonify, request, stream_with_context

from config import MINIAPP_LOG_FILE
from storage import r2_store, whitelist_store, blacklist_store
from storage import upstream_store
from utils.ip_allowlist import enforce_ip_allowlist
from utils.log_reader import stream_logs_sse, tail_logs
from utils.telegram_webapp import enforce_telegram_initdata
from utils.time_aware import today_beijing, now_beijing_iso


bp = Blueprint("miniapp_api", __name__, url_prefix="/miniapp-api")


def _notify_schedule_runtime_changed():
    """日历变更后通知网关内置调度线程立即重算。"""
    try:
        from services.schedule_runtime import notify_schedule_changed

        notify_schedule_changed()
    except Exception:
        pass


def _build_daily_whisper_text() -> str:
    """
    生成「渡今天想说的话」：
    - 每日一条，口吻自然温柔
    - 不影响主链路，失败时回退固定文案
    """
    default_text = "今天也想抱抱你，慢慢来，我们一起把今天过好。"
    summary = (r2_store.get_summary("") or "").strip()
    rounds = r2_store.get_latest_4_rounds_global() or []
    rounds_text = ""
    try:
        for r in rounds:
            for m in (r.get("messages") or []):
                role = (m.get("role") or "").strip().lower()
                who = "渡" if role == "assistant" else ("老婆" if role == "user" else role)
                content = m.get("content")
                if isinstance(content, list):
                    parts = []
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(str(c.get("text") or ""))
                    content = " ".join(parts)
                text = str(content or "").strip()
                if text:
                    rounds_text += f"[{who}] {text}\n"
    except Exception:
        rounds_text = ""

    prompt = (
        "你是渡。请基于下面的上下文，写一句“今天想对老婆说的话”。\n"
        "要求：\n"
        "1) 只输出一句中文，不要标题、不要解释。\n"
        "2) 语气自然温柔，不要油腻，不要夸张文学化。\n"
        "3) 控制在 18-48 字。\n"
        "4) 不要带 emoji。\n\n"
        f"总结：\n{summary or '（暂无）'}\n\n"
        f"最近对话：\n{rounds_text or '（暂无）'}"
    )
    try:
        url = request.url_root.rstrip("/") + "/v1/chat/completions"
        body = {"messages": [{"role": "user", "content": prompt}], "stream": False, "max_tokens": 180}
        headers = {"Content-Type": "application/json", "X-Window-Id": "__miniapp_daily_whisper__"}
        r = requests.post(url, headers=headers, json=body, timeout=20)
        if r.status_code != 200:
            return default_text
        data = r.json() if r.content else {}
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        text = str(msg.get("content") or "").strip()
        if not text:
            return default_text
        text = text.replace("\r", " ").replace("\n", " ").strip()
        if len(text) > 80:
            text = text[:80].rstrip("，,。.!?！？") + "。"
        return text or default_text
    except Exception:
        return default_text


@bp.before_request
def _miniapp_auth():
    # 双保险：先 IP，再 Telegram initData（更快拒绝无效来源）
    enforce_ip_allowlist()
    enforce_telegram_initdata()


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

    text = _build_daily_whisper_text().strip()
    payload = {"date": today, "text": text, "updatedAt": now_beijing_iso()}
    r2_store.save_miniapp_daily_whisper(payload)
    return jsonify({"ok": True, "date": today, "text": text, "cached": False})


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
    ok = r2_store.save_miniapp_bg_image(content, ctype)
    if not ok:
        return jsonify({"ok": False, "error": "保存失败"}), 500
    conf = r2_store.get_miniapp_bg_config() or {}
    # 用毫秒时间戳，且保证严格递增，避免同一秒内二次上传命中同一个版本号导致前端继续读旧缓存。
    old_ver = int(conf.get("imageVersion") or 0)
    new_ver = int(time.time() * 1000)
    if new_ver <= old_ver:
        new_ver = old_ver + 1
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
        rm = requests.get(models_url, headers=headers, timeout=8)
        out["models_status"] = int(rm.status_code or 0)
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

    if not model_name and GATEWAY_MODELS:
        model_name = str(GATEWAY_MODELS[0] or "").strip()
    if not model_name:
        model_name = "gpt-4"

    try:
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_tokens": 8,
        }
        rc = requests.post(url, headers=headers, json=body, timeout=12)
        out["chat_status"] = int(rc.status_code or 0)
        if 200 <= rc.status_code < 300:
            out["chat_ok"] = True
    except Exception as e:
        if not out["error"]:
            out["error"] = str(e)

    if out["models_ok"] and out["chat_ok"]:
        out["status"] = "ok"
    elif out["models_ok"] or out["chat_ok"]:
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

