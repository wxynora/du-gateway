import time
import os
from pathlib import Path
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, stream_with_context

from config import MINIAPP_LOG_FILE
from storage import r2_store, whitelist_store, blacklist_store
from storage import upstream_store
from utils.ip_allowlist import enforce_ip_allowlist
from utils.log_reader import stream_logs_sse, tail_logs
from utils.telegram_webapp import enforce_telegram_initdata


bp = Blueprint("miniapp_api", __name__, url_prefix="/miniapp-api")


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

    if not title:
        return jsonify({"ok": False, "error": "title 不能为空"}), 400
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
    )
    if not item:
        return jsonify({"ok": False, "error": "创建失败"}), 500
    return jsonify({"ok": True, "item": item})


@bp.route("/schedule/items/<item_id>/disable", methods=["PUT"])
def miniapp_disable_schedule_item(item_id: str):
    iid = (item_id or "").strip()
    if not iid:
        return jsonify({"ok": False, "error": "缺少 item_id"}), 400
    ok = r2_store.disable_schedule_item(iid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到条目或已是禁用状态"}), 404
    return jsonify({"ok": True, "id": iid, "action": "disable_future"})


@bp.route("/schedule/items/<item_id>/enable", methods=["PUT"])
def miniapp_enable_schedule_item(item_id: str):
    iid = (item_id or "").strip()
    if not iid:
        return jsonify({"ok": False, "error": "缺少 item_id"}), 400
    ok = r2_store.enable_schedule_item(iid)
    if not ok:
        return jsonify({"ok": False, "error": "未找到条目或已是启用状态"}), 404
    return jsonify({"ok": True, "id": iid, "action": "enable"})


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
    payload = {
        "preset": preset,
        "useImage": use_image,
        "imageVersion": max(0, image_version),
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
    conf["imageVersion"] = int(time.time())
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
    return Response(data, mimetype=ctype, headers={"Cache-Control": "public, max-age=300"})


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

