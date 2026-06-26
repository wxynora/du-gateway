from __future__ import annotations

from pathlib import Path

from flask import jsonify, request

from services import prompt_manager
from services import sumitalk_block_mode
from storage import million_plan_mode_store, r2_store, silence_mode_store, sumitalk_block_mode_store
from utils.time_aware import now_beijing_iso


def _core_prompt_file_path() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts" / "du_core_prompt.txt"


def _prompt_updated_by_device() -> str:
    payload = request.environ.get("miniapp_panel_payload") if isinstance(request.environ.get("miniapp_panel_payload"), dict) else {}
    device_id = str((payload or {}).get("device_id") or "").strip()
    subject = str((payload or {}).get("sub") or "").strip()
    return device_id or subject or "miniapp"


def register_routes(bp) -> None:
    @bp.route("/core-prompt", methods=["GET"])
    def miniapp_get_core_prompt():
        """
        读取“核心 Prompt（3.16）”：
        - 若 R2 已有自定义内容，返回该内容
        - 否则回退读取本地 prompts/du_core_prompt.txt（只读展示）
        """
        cfg = r2_store.get_core_prompt_config()
        text = r2_store.get_core_prompt_text()
        source = "r2"
        if text is None and cfg is None:
            source = "file"
            try:
                p = _core_prompt_file_path()
                text = p.read_text(encoding="utf-8") if p.exists() else ""
            except Exception:
                text = ""
            cfg = {"active_key": "a", "prompts": {"a": (text or ""), "b": ""}}
        return jsonify(
            {
                "ok": True,
                "source": source,
                "content": (text or ""),
                "active_key": str((cfg or {}).get("active_key") or "a"),
                "prompts": ((cfg or {}).get("prompts") or {"a": (text or ""), "b": ""}),
            }
        )

    @bp.route("/portrait-memory", methods=["GET"])
    def miniapp_get_portrait_memory():
        xinyue = r2_store.get_xinyue_portrait_candidates() or []
        du = r2_store.get_du_portrait_candidates() or []
        interaction = r2_store.get_interaction_candidates() or []
        return jsonify(
            {
                "ok": True,
                "xinyue_candidates": xinyue,
                "du_candidates": du,
                "interaction_candidates": interaction,
                "counts": {
                    "xinyue": len(xinyue),
                    "du": len(du),
                    "interaction": len(interaction),
                },
            }
        )

    @bp.route("/portrait-memory/<bucket>/<entry_id>", methods=["DELETE"])
    def miniapp_delete_portrait_memory(bucket: str, entry_id: str):
        b = str(bucket or "").strip().lower()
        eid = str(entry_id or "").strip()
        if b not in ("xinyue", "du", "interaction"):
            return jsonify({"ok": False, "error": "bucket 无效"}), 400
        if not eid:
            return jsonify({"ok": False, "error": "缺少 entry_id"}), 400
        if b == "xinyue":
            ok = r2_store.delete_xinyue_portrait_candidate(eid)
        elif b == "du":
            ok = r2_store.delete_du_portrait_candidate(eid)
        else:
            ok = r2_store.delete_interaction_candidate(eid)
        if not ok:
            return jsonify({"ok": False, "error": "未找到该候选"}), 404
        return jsonify({"ok": True, "bucket": b, "id": eid})

    @bp.route("/core-prompt", methods=["PUT"])
    def miniapp_put_core_prompt():
        data = request.get_json(silent=True) or {}
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else None
        active_key = str(data.get("active_key") or "a").strip() or "a"
        if prompts is not None:
            pa = str(prompts.get("a") or "").strip()
            pb = str(prompts.get("b") or "").strip()
            if not pa and not pb:
                return jsonify({"ok": False, "error": "至少保留一套 prompt"}), 400
            if active_key == "a" and not pa:
                return jsonify({"ok": False, "error": "当前选中的 prompt A 不能为空"}), 400
            if active_key == "b" and not pb:
                return jsonify({"ok": False, "error": "当前选中的 prompt B 不能为空"}), 400
            ok = r2_store.save_core_prompt_config({"active_key": active_key, "prompts": {"a": pa, "b": pb}})
            return jsonify({"ok": ok})

        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"ok": False, "error": "content 不能为空"}), 400
        ok = r2_store.save_core_prompt_text(content)
        return jsonify({"ok": ok})

    @bp.route("/prompt-manager", methods=["GET"])
    def miniapp_prompt_manager_list():
        return jsonify({"ok": True, "sections": prompt_manager.list_prompt_sections()})

    @bp.route("/prompt-manager/sections/<section_id>", methods=["GET"])
    def miniapp_prompt_manager_get_section(section_id: str):
        detail = prompt_manager.get_prompt_section_detail(section_id)
        if not detail:
            return jsonify({"ok": False, "error": "未知 prompt section"}), 404
        return jsonify({"ok": True, **detail})

    @bp.route("/prompt-manager/sections/<section_id>", methods=["PUT"])
    def miniapp_prompt_manager_save_section(section_id: str):
        data = request.get_json(silent=True) or {}
        content = str(data.get("content") or "")
        base_revision_raw = data.get("base_revision")
        try:
            base_revision = int(base_revision_raw) if base_revision_raw is not None else None
        except Exception:
            return jsonify({"ok": False, "error": "base_revision 无效"}), 400
        result = prompt_manager.save_prompt_section(
            section_id,
            content,
            base_revision=base_revision,
            updated_by_device=_prompt_updated_by_device(),
        )
        if not result.get("ok"):
            status = 409 if result.get("code") == "revision_conflict" else 400
            return jsonify(result), status
        return jsonify(result)

    @bp.route("/prompt-manager/sections/<section_id>/rollback", methods=["POST"])
    def miniapp_prompt_manager_rollback_section(section_id: str):
        data = request.get_json(silent=True) or {}
        backup_id = str(data.get("backup_id") or "").strip()
        if not backup_id:
            return jsonify({"ok": False, "error": "backup_id 不能为空"}), 400
        result = prompt_manager.rollback_prompt_section(
            section_id,
            backup_id,
            updated_by_device=_prompt_updated_by_device(),
        )
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)

    @bp.route("/silence-mode", methods=["GET"])
    def miniapp_get_silence_mode():
        state = silence_mode_store.get_state()
        return jsonify({"ok": True, **state})

    @bp.route("/silence-mode", methods=["PUT"])
    def miniapp_put_silence_mode():
        data = request.get_json(silent=True) or {}
        raw = data.get("enabled")
        if isinstance(raw, str):
            enabled = raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            enabled = bool(raw)
        state = silence_mode_store.set_enabled(enabled, updated_at=now_beijing_iso())
        return jsonify({"ok": True, **state})

    @bp.route("/million-plan-mode", methods=["GET"])
    def miniapp_get_million_plan_mode():
        state = million_plan_mode_store.get_state()
        return jsonify({"ok": True, **state})

    @bp.route("/million-plan-mode", methods=["PUT"])
    def miniapp_put_million_plan_mode():
        data = request.get_json(silent=True) or {}
        raw = data.get("enabled")
        if isinstance(raw, str):
            enabled = raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            enabled = bool(raw)
        state = million_plan_mode_store.set_enabled(enabled, updated_at=now_beijing_iso())
        return jsonify({"ok": True, **state})

    @bp.route("/sumitalk-block-mode", methods=["GET"])
    def miniapp_get_sumitalk_block_mode():
        state = sumitalk_block_mode_store.get_state()
        return jsonify({"ok": True, **state})

    @bp.route("/sumitalk-block-mode", methods=["PUT"])
    def miniapp_put_sumitalk_block_mode():
        data = request.get_json(silent=True) or {}
        raw = data.get("enabled")
        if isinstance(raw, str):
            enabled = raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            enabled = bool(raw)
        previous = sumitalk_block_mode_store.get_state()
        state = sumitalk_block_mode_store.set_enabled(enabled, updated_at=now_beijing_iso())
        notice = {"context_ok": False, "created_at": ""}
        if enabled and not previous.get("enabled"):
            notice = sumitalk_block_mode.send_block_notice(
                created_at=state.get("updated_at") or now_beijing_iso(),
                reason="sumitalk_block_mode_enabled",
            )
            if notice.get("context_ok"):
                state = sumitalk_block_mode_store.mark_initial_notice_sent(notice.get("created_at") or now_beijing_iso())
        return jsonify({"ok": True, **state, "notice": notice})
