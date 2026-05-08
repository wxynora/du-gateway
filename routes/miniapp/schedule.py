from __future__ import annotations

from datetime import datetime

from flask import jsonify, request

from storage import r2_store


def _notify_schedule_runtime_changed():
    """日历变更后通知网关内置调度线程立即重算。"""
    try:
        from services.schedule_runtime import notify_schedule_changed

        notify_schedule_changed()
    except Exception:
        pass


def register_routes(bp) -> None:
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
