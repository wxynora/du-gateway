from uuid import uuid4

from flask import Blueprint, jsonify, request


bp = Blueprint("memory_api", __name__)


@bp.route("/summary", methods=["GET"])
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


@bp.route("/dynamic-memory", methods=["GET"])
def root_dynamic_memory():
    """动态层全文，与 GET /admin/dynamic-memory 相同。"""
    from storage import r2_store

    try:
        lst = r2_store.get_dynamic_memory_list() or []
        return {"ok": True, "count": len(lst), "memories": lst}
    except Exception as e:
        return {"ok": False, "error": str(e), "memories": []}, 500


@bp.route("/api/memory/append", methods=["POST"])
def api_memory_append():
    """
    向动态层追加一条记忆（供 MCP / CC 写回）。
    Body JSON: { content: str, importance?: int(1-5), tag?: str, emotion_label?: str, scene_type?: str, target_type?: str }
    鉴权：与 /mcp/* 相同的 Bearer token（MCP_AUTH_MODE / MCP_TOKENS）。
    """
    from utils.mcp_auth import enforce_mcp_auth

    enforce_mcp_auth()

    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True) or {}
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400

    importance = body.get("importance", 3)
    try:
        importance = max(1, min(5, int(importance)))
    except (TypeError, ValueError):
        importance = 3
    tag = (body.get("tag") or "书房").strip()
    if tag not in ("客厅", "书房", "图书馆", "卧室"):
        tag = "书房"
    emotion_label = (body.get("emotion_label") or "").strip().lower()
    scene_type = (body.get("scene_type") or "").strip()
    target_type = (body.get("target_type") or "").strip()
    if emotion_label not in ("positive", "negative", "neutral"):
        emotion_label = "neutral"
    if scene_type not in (
        "problem_solving", "learning", "planning", "emotional_venting",
        "heart_to_heart", "casual_chat", "affection", "conflict",
    ):
        scene_type = ""
    if target_type not in (
        "external_tools", "self_state", "work_career", "our_project",
        "our_relationship", "about_me", "third_party_people", "other_topic",
    ):
        target_type = ""

    from utils.time_aware import now_beijing_iso
    from storage import r2_store
    from pipeline.pipeline import _build_retrieval_text

    now = now_beijing_iso()
    new_entry = {
        "id": str(uuid4()),
        "content": content,
        "retrieval_text": _build_retrieval_text(content),
        "importance": importance,
        "tag": tag,
        "emotion_label": emotion_label,
        "scene_type": scene_type,
        "target_type": target_type,
        "mention_count": 0,
        "created_at": now,
        "last_mentioned": now,
    }

    memories = r2_store.get_dynamic_memory_list() or []
    memories.append(new_entry)
    ok = r2_store.save_dynamic_memory_list(memories)
    if not ok:
        return jsonify({"ok": False, "error": "R2 写入失败"}), 503

    # 向量索引更新（best-effort，失败不影响写入结果）
    try:
        from pipeline.pipeline import _upsert_dynamic_memory_index

        _upsert_dynamic_memory_index(new_entry)
    except Exception:
        pass

    return jsonify({"ok": True, "id": new_entry["id"]})


@bp.route("/api/cc_log", methods=["POST"])
def api_cc_log():
    """
    CC 侧写入一条记录到默认窗口对话历史，伪装成一轮对话，
    后续会被 DS 总结自然消化。
    Body JSON: { content: str, tag?: str }
    """
    from utils.mcp_auth import enforce_mcp_auth

    enforce_mcp_auth()

    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True) or {}
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content 不能为空"}), 400
    tag = (body.get("tag") or "书房").strip()
    if tag not in ("客厅", "书房", "图书馆", "卧室"):
        tag = "书房"

    from utils.time_aware import now_beijing_iso
    from storage import r2_store

    window_id = ""  # 默认窗口
    round_index = r2_store.get_next_round_index(window_id)
    timestamp = now_beijing_iso()
    messages = [
        {"role": "user", "content": f"[{tag} 记录]"},
        {"role": "assistant", "content": content},
    ]
    ok = r2_store.append_conversation_round(window_id, round_index, messages, timestamp)
    if not ok:
        return jsonify({"ok": False, "error": "写入失败"}), 503
    return jsonify({"ok": True, "round_index": round_index})
