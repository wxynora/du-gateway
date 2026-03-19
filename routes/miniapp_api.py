import time
import os
from pathlib import Path

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

