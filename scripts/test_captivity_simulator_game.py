from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.captivity_simulator_game import run_command
from services.game_tool_runtime import execute_game_command, list_game_tools


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _plan_three(save_path: Path, *, process_first: bool = False) -> dict:
    plan = (
        "action=training intensity=medium training_contents=obedience_commands modifiers=sex || action=feeding intensity=medium || action=cleaning intensity=light"
        if process_first
        else "action=rest intensity=light contents=quiet_time || action=reward intensity=medium contents=caress_reward || action=check intensity=light contents=body_check"
    )
    return run_command(f"plan_day {plan}", save_path=save_path)


def _finish_simple_day_captured_by_du(save_path: Path) -> dict:
    _plan_three(save_path)
    run_command("respond_action accept mood=平静 line=第一件", save_path=save_path)
    run_command("respond_action silent mood=害羞 line=第二件", save_path=save_path)
    return run_command("respond_action bargain mood=疲惫 line=第三件", save_path=save_path)


def test_captivity_simulator_new_game_views() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        captured_path = Path(tmpdir) / "captured.json"
        captured = run_command("new_game route=captured_by_du seed=view-test", save_path=captured_path)
        _assert(captured["state"]["pending_event"]["type"] == "day_plan_choice", "captured-by-du route should start by asking du for a 3-action plan")
        _assert(captured["state"]["mood"] == "", "new game should not ask the captive to choose mood before anything happens")

        capture_du_path = Path(tmpdir) / "capture_du.json"
        result = run_command("new_game route=capture_du seed=view-test", save_path=capture_du_path)
        state = result["state"]
        captor_view = result["captor_view"]

        _assert(result["ok"] is True, "new_game should succeed")
        _assert(state["route"] == "capture_du", "route should be configurable")
        _assert(state["captive"] == "du", "capture_du route should make du captive")
        _assert(state["pending_event"] is None, "xinyue-captor route should wait for local UI plan input, not du")
        _assert("stats" in state and set(state["stats"]) == {"health", "stamina", "cleanliness", "shame", "intimacy"}, "only captive stats should be exposed")
        _assert("captor" not in state, "captive view should not expose captor internals")
        _assert(captor_view["captor"] == "xinyue", "captor view should expose captor identity")
        direct = run_command("day_action action=feeding", save_path=capture_du_path)
        _assert(direct["ok"] is False and "plan_day" in direct["text"], "single day_action should not bypass the 3-action plan")


def test_captivity_simulator_history_is_complete_and_date_filterable() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "history.json"
        run_command("new_game route=captured_by_du seed=history-test", save_path=save_path)
        state = _read(save_path)
        state["event_log"] = [
            {
                "id": f"history-{index}",
                "day": index // 2 + 1,
                "slot": index % 3 + 1,
                "phase": "day",
                "route": "captured_by_du",
                "action": "training",
                "action_label": f"历史事件 {index + 1}",
                "process_text": f"事件正文 {index + 1}",
                "tags": [],
            }
            for index in range(45)
        ]
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        status = run_command("status", save_path=save_path)
        _assert(len(status["state"]["event_log"]) == 45, "captive history view should not truncate events after 30 records")
        _assert(len(status["captor_view"]["event_log"]) == 45, "captor history view should not truncate events after 30 records")
        _assert(status["state"]["event_log"][0]["id"] == "history-0", "complete history should preserve chronological order")

    frontend = (ROOT / "miniapp/src/ui/tabs/CaptivitySimulatorGameTab.tsx").read_text(encoding="utf-8")
    _assert('aria-label="按日期筛选事件"' in frontend and "history-day-group" in frontend, "history UI should support direct day filtering and grouped dates")
    history_panel = frontend.split("function HistoryPanel", 1)[1].split("function MonitorRoomPanel", 1)[0]
    _assert("processReviewMeta(event)" not in history_panel, "history list should show only time and title before opening detail")


def test_captivity_simulator_captured_by_du_event_loop() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game route=captured_by_du seed=pending-test", save_path=save_path)
        duplicate = run_command("plan_day action=feeding || action=feeding || action=training training_contents=obedience_commands", save_path=save_path)
        _assert(duplicate["ok"] is False, "day plan should reject duplicate actions")

        planned = run_command(
            "plan_day action=feeding intensity=medium || action=cleaning intensity=light || action=training intensity=medium training_contents=obedience_commands modifiers=sex tools=collar",
            save_path=save_path,
        )
        _assert(planned["ok"] is True, "du should be able to submit a 3-action plan")
        _assert(planned["state"]["pending_event"]["type"] == "action_response", "first planned action should wait for captive response")

        before = planned["state"]["stats"].copy()
        first = run_command("respond_action accept mood=害羞 line=先这样", save_path=save_path)
        _assert(first["state"]["day_action_count"] == 1, "non-process action should settle after response")
        _assert(first["state"]["pending_event"]["type"] == "action_response", "next planned action should be shown after first response")
        _assert(first["state"]["stats"]["intimacy"] > before["intimacy"], "effects should settle after response")

        second = run_command("respond_action refuse mood=闹脾气 line=不要", save_path=save_path)
        _assert(second["state"]["day_action_count"] == 2, "second action should settle")
        process_pending = run_command("respond_action silent mood=疲惫 line=...", save_path=save_path)
        _assert(process_pending["state"]["pending_event"]["type"] == "process_write", "process action should wait for du process after captive response")

        stats_before_process = process_pending["state"]["stats"].copy()
        written = run_command("submit_process 写完这一段过程。", save_path=save_path)
        _assert(written["ok"] is True, "submit_process should save process")
        _assert(written["state"]["pending_event"]["type"] == "reaction_choice", "process must be shown before post-process mood")
        _assert(written["state"]["stats"] == stats_before_process, "stats should not settle before post-process mood")

        resolved = run_command("choose_mood 黏人 过程后一句话", save_path=save_path)
        _assert(resolved["state"]["phase"] == "night", "third resolved action should enter night")
        _assert(resolved["state"]["pending_event"] is None, "night phase should not create another day pending")
        _assert(resolved["state"]["event_log"][-1]["process_text"] == "写完这一段过程。", "full process should stay in game save")
        _assert(resolved["state"]["event_log"][-1]["post_reaction"]["mood"] == "黏人", "post-process mood should be logged")


def test_captivity_simulator_capture_du_manual_advance_loop() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "capture_du.json"
        run_command("new_game route=capture_du seed=manual-loop", save_path=save_path)
        run_command("set_config notebook=true", save_path=save_path)
        planned = _plan_three(save_path, process_first=True)
        _assert(planned["state"]["pending_event"]["type"] == "process_reaction_write", "process action with du captive should ask du for process and mood in one turn")

        first_done = run_command(
            "submit_process_reaction response=accept mood=害羞 line=写完了 process=这一段过程正文。",
            save_path=save_path,
        )
        _assert(first_done["state"]["day_action_count"] == 1, "first action should settle after combined process reaction")
        _assert(first_done["state"]["pending_event"]["type"] == "advance_action", "xinyue-captor route should wait for local advance")
        _assert(first_done["state"]["event_log"][-1]["post_reaction"]["mood"] == "害羞", "combined process reaction should log one mood")

        second = run_command("advance_day_action", save_path=save_path)
        _assert(second["state"]["pending_event"]["type"] == "action_response", "manual advance should show the next planned action")
        second_done = run_command("respond_action refuse mood=闹脾气 line=不要", save_path=save_path)
        _assert(second_done["state"]["pending_event"]["type"] == "advance_action", "non-process du response should also stop before next action")
        third = run_command("advance_day_action", save_path=save_path)
        _assert(third["state"]["pending_event"]["type"] == "action_response", "third action should be shown after manual advance")
        closed = run_command("respond_action silent mood=疲惫 line=最后一件", save_path=save_path)
        _assert(closed["state"]["phase"] == "night", "third action should enter night")
        _assert(closed["state"]["pending_event"]["type"] == "night_action_choice", "du-captive route should ask du to choose the night action")
        du_night = run_command("night_action diary detail=record_day note=写一点东西", save_path=save_path)
        _assert(du_night["captor_view"]["pending_event"]["type"] == "monitor_gate", "du night action should seal a monitor gate for xinyue")
        _assert("event" not in du_night["captor_view"]["pending_event"], "sealed monitor gate should not expose the night action before viewing")
        viewed = run_command("view_monitor full", save_path=save_path)
        _assert(viewed["captor_view"]["pending_event"]["type"] == "monitor_handle", "viewing monitor should reveal a handle pending")
        _assert(viewed["captor_view"]["pending_event"]["event"]["action"] == "diary", "captor should see the night action only after viewing")
        intervened = run_command("monitor_action intervene", save_path=save_path)
        _assert(intervened["state"]["pending_event"]["type"] == "process_reaction_write", "xinyue-captor intervention should ask du for process and mood together")


def test_captivity_simulator_night_monitor_view_filtering() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=night-test", save_path=save_path)
        day_done = _finish_simple_day_captured_by_du(save_path)
        _assert(day_done["state"]["phase"] == "night", "three day actions should enter night")

        run_command("set_config notebook=true", save_path=save_path)
        night = run_command("night_action diary detail=write_feelings note=写一点私密日记", save_path=save_path)
        _assert(night["state"]["pending_event"]["type"] == "monitor_gate", "night action should wait behind a sealed monitor gate")
        _assert("event" not in night["captor_view"]["pending_event"], "sealed monitor gate should not leak the night action to captor view")
        blocked = run_command("monitor_action review_later note=明天再说", save_path=save_path)
        _assert(blocked["ok"] is False, "review_later should require opening the monitor first")
        viewed = run_command("view_monitor occasional", save_path=save_path)
        _assert(viewed["captor_view"]["pending_event"]["type"] == "monitor_handle", "view_monitor should create a monitor handle pending")
        _assert(viewed["captor_view"]["pending_event"]["event"]["action"] == "diary", "view_monitor should reveal the sealed night action to captor view")
        monitored = run_command("monitor_action review_later note=明天再说", save_path=save_path)
        captive_log = monitored["state"]["event_log"][-1]
        captor_log = monitored["captor_view"]["event_log"][-1]
        _assert("monitor" not in captive_log, "captive view should not leak monitor detail")
        _assert(captor_log["monitor"]["style"] == "occasional", "captor view should keep monitor viewing style")
        _assert(captor_log["monitor"]["handle"] == "review_later", "captor view should keep monitor handling detail")
        _assert(monitored["state"]["current_day"] == 2, "night closure should advance day")
        _assert(monitored["state"]["pending_event"]["type"] == "day_plan_choice", "next captured-by-du day should ask du for a new plan")


def test_captivity_simulator_monitor_none_stays_sealed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=monitor-none", save_path=save_path)
        _finish_simple_day_captured_by_du(save_path)
        run_command("set_config notebook=true", save_path=save_path)
        run_command("night_action diary detail=record_day note=秘密日记内容", save_path=save_path)
        skipped = run_command("monitor_action none", save_path=save_path)
        captor_log = skipped["captor_view"]["event_log"][-1]
        _assert(captor_log["action"] == "sealed_monitor", "captor view should keep unviewed monitor content sealed")
        _assert(captor_log["action_label"] == "未查看的夜间监控记录", "sealed monitor should use a neutral label")
        _assert(captor_log["line"] == "", "sealed monitor should not expose night action line")
        _assert(captor_log["effects"] == {}, "sealed monitor should not expose action effects")
        exported = run_command("export_log", save_path=save_path)
        exported_text = json.dumps(exported["export_log"], ensure_ascii=False)
        _assert("秘密日记内容" not in exported_text and "diary" not in exported_text, "safe export should not reveal skipped monitor content")


def test_captivity_simulator_night_gates_and_intervention_process() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=night-gates", save_path=save_path)
        _finish_simple_day_captured_by_du(save_path)

        blocked = run_command("night_action read", save_path=save_path)
        _assert(blocked["ok"] is False, "read should be blocked until a book is given")
        configured = run_command(
            "set_config book=true switch=true notebook=true music_player=true tablet=true night_light=true pillow=true",
            save_path=save_path,
        )
        configured = run_command("gift_item items=call_bell voice_line='本地测试台词'", save_path=save_path)
        _assert(configured["ok"] is True, "set_config should work before night action pending")
        _assert(all(configured["captor_view"]["inventory"].values()), "all warehouse items should persist in backend inventory")
        night = run_command("night_action read detail=follow_bookmark", save_path=save_path)
        _assert(night["ok"] is True and night["state"]["pending_event"]["type"] == "monitor_gate", "book should unlock read night action")
        blocked = run_command("monitor_action intervene", save_path=save_path)
        _assert(blocked["ok"] is False, "intervention should require viewing monitor first")
        viewed = run_command("view_monitor full", save_path=save_path)
        _assert(viewed["state"]["pending_event"]["type"] == "monitor_handle", "viewing monitor should create handle pending")
        intervened = run_command("monitor_action intervene", save_path=save_path)
        _assert(intervened["state"]["pending_event"]["type"] == "action_response", "du-captor intervention should first ask the local captive to respond")
        responded = run_command("respond_action accept mood=害羞 line=知道了", save_path=save_path)
        _assert(responded["state"]["pending_event"]["type"] == "process_write", "captive response should then hand the intervention process to du")
        written = run_command("submit_process 夜间介入过程。", save_path=save_path)
        _assert(written["state"]["pending_event"]["type"] == "reaction_choice", "night process should show process before mood")
        resolved = run_command("choose_mood 平静 夜间结束", save_path=save_path)
        _assert(resolved["state"]["current_day"] == 2, "resolved intervention should close night and advance day")


def test_captivity_simulator_low_stamina_and_tool_process_do_not_deadlock() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "low-stamina.json"
        run_command("new_game route=captured_by_du seed=low-stamina", save_path=save_path)
        state = _read(save_path)
        state["stats"]["stamina"] = 22
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        planned = run_command(
            "plan_day action=room_search intensity=medium contents=bed_search || action=reward intensity=heavy contents=caress_reward || action=check intensity=light contents=body_check",
            save_path=save_path,
        )
        _assert(planned["ok"] is True and planned["state"]["pending_event"], "low stamina plan should still start with a pending")
        next_action = run_command("respond_action refuse mood=烦躁", save_path=save_path)
        event = next_action["state"]["pending_event"]["event"]
        _assert(event["action"] == "reward" and event["intensity"] == "medium", "later heavy action should downgrade instead of dropping pending")
        _assert(event["intensity_adjustment"]["reason"] == "low_stamina", "downgrade reason should be explicit")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "tool-process.json"
        run_command("new_game route=captured_by_du seed=tool-process", save_path=save_path)
        planned = run_command(
            "plan_day action=reward contents=toy_reward tools=toy || action=rest contents=quiet_time || action=check contents=body_check",
            save_path=save_path,
        )
        _assert(planned["state"]["pending_event"]["event"]["requires_process"] is True, "selecting a tool should require a detailed process")
        responded = run_command("respond_action accept mood=害羞", save_path=save_path)
        _assert(responded["state"]["pending_event"]["type"] == "process_write", "tool action should enter the same process flow as frontend preview")


def test_captivity_simulator_action_contents_and_expanded_tools() -> None:
    from services.captivity_simulator_game import ACTION_CONTENTS, TOOL_CATEGORIES, TOOL_COMPATIBILITY, TOOL_LABELS, _intervention_effects, _intervention_payload

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "content-validation.json"
        run_command("new_game route=capture_du seed=content-validation", save_path=save_path)
        missing = run_command(
            "plan_day action=reward || action=feeding || action=cleaning",
            save_path=save_path,
        )
        _assert(missing["ok"] is False and "具体内容" in missing["text"], "non-basic actions should require concrete content")
        old_tool_action = run_command(
            "plan_day action=tools || action=feeding || action=cleaning",
            save_path=save_path,
        )
        _assert(old_tool_action["ok"] is False and "未知行动" in old_tool_action["text"], "tools should no longer be a standalone action")
        missing_training = run_command(
            "plan_day action=feeding modifiers=training || action=cleaning || action=rest contents=quiet_time",
            save_path=save_path,
        )
        _assert(missing_training["ok"] is False and "调教内容" in missing_training["text"], "training modifier should require a concrete training choice")

    plans = [
        (
            "action=reward contents=orgasm_permission || "
            "action=punishment contents=impact_discipline || "
            "action=comfort contents=cuddle_rest"
        ),
        (
            "action=rest contents=restrained_rest || "
            "action=check contents=sensitivity_check || "
            "action=room_search contents=body_search"
        ),
    ]
    for index, plan in enumerate(plans):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / f"content-plan-{index}.json"
            run_command(f"new_game route=capture_du seed=content-plan-{index}", save_path=save_path)
            result = run_command(f"plan_day {plan}", save_path=save_path)
            _assert(result["ok"] is True, f"content-rich action plan {index} should be accepted")
            day_plan = result["captor_view"]["day_plan"]
            for spec in day_plan:
                action = str(spec.get("action") or "")
                if action in ACTION_CONTENTS:
                    _assert(spec.get("contents"), f"{action} should retain its concrete content")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "expanded-tools.json"
        run_command("new_game route=capture_du seed=expanded-tools", save_path=save_path)
        result = run_command(
            "plan_day "
            "action=training training_contents=impact_play tools=whip,ruler || "
            "action=feeding || action=cleaning",
            save_path=save_path,
        )
        _assert(result["ok"] is True, "compatible expanded BDSM tools should be accepted by the rule engine")
        event = result["captor_view"]["pending_event"]["event"]
        _assert(event["tools"] == ["whip", "ruler"], "the event should retain at most two compatible tools")
        _assert(event["training_contents"] == ["impact_play"], "event should retain explicit training content")
        _assert(event["requires_process"] is True, "specific training content and tools should require a detailed process")
        _assert(len(TOOL_LABELS) == 30, "the expanded tool library should contain 30 tools")
        _assert(set(TOOL_LABELS) == set(TOOL_CATEGORIES) == set(TOOL_COMPATIBILITY), "every tool should have category and compatibility metadata")

        too_many_path = Path(tmpdir) / "too-many-tools.json"
        run_command("new_game route=capture_du seed=too-many-tools", save_path=too_many_path)
        too_many = run_command(
            "plan_day action=training training_contents=impact_play tools=whip,ruler,paddle || action=feeding || action=cleaning",
            save_path=too_many_path,
        )
        _assert(too_many["ok"] is False and "最多选择 2 个" in too_many["text"], "day actions should reject more than two tools")

        mismatch_path = Path(tmpdir) / "mismatched-tool.json"
        run_command("new_game route=capture_du seed=mismatched-tool", save_path=mismatch_path)
        mismatch = run_command(
            "plan_day action=training training_contents=wax_play tools=ruler || action=feeding || action=cleaning",
            save_path=mismatch_path,
        )
        _assert(mismatch["ok"] is True, "known tools should remain freely combinable even when they are not recommended")
        _assert(mismatch["captor_view"]["pending_event"]["event"]["tools"] == ["ruler"], "free tool combinations should be retained in the event")

        invalid = Path(tmpdir) / "invalid-tool.json"
        run_command("new_game route=capture_du seed=invalid-tool", save_path=invalid)
        rejected = run_command(
            "plan_day action=training training_contents=impact_play tools=unknown_tool || action=feeding || action=cleaning",
            save_path=invalid,
        )
        _assert(rejected["ok"] is False and "未知道具" in rejected["text"], "unknown tools should be rejected")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "dedupe-and-process.json"
        run_command("new_game route=capture_du seed=dedupe-and-process", save_path=save_path)
        result = run_command(
            "plan_day "
            "action=training training_contents=impact_play,impact_play tools=whip,whip requires_process=false || "
            "action=feeding || action=cleaning",
            save_path=save_path,
        )
        _assert(result["ok"] is True, "duplicate material ids should be normalized instead of breaking the plan")
        event = result["captor_view"]["pending_event"]["event"]
        _assert(event["training_contents"] == ["impact_play"] and event["tools"] == ["whip"], "duplicate content and tool ids should not stack")
        _assert(result["captor_view"]["pending_event"]["type"] == "process_reaction_write", "requires_process=false must not bypass mandatory process flow")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "old-save-materials.json"
        run_command("new_game route=capture_du seed=old-save-materials", save_path=save_path)
        state = _read(save_path)
        state["day_plan"] = [{
            "action": "training",
            "action_label": "服从调教",
            "intensity": "medium",
            "contents": [],
            "training_contents": ["impact_play", "impact_play", "unknown_training"],
            "modifiers": ["sex", "unknown_modifier"],
            "tools": ["collar", "collar", "unknown_tool"],
            "requires_process": True,
        }]
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        normalized = run_command("status", save_path=save_path)["captor_view"]["day_plan"][0]
        _assert(normalized["training_contents"] == ["impact_play"], "old save should dedupe and remove unknown training content")
        _assert(normalized["modifiers"] == ["sex"] and normalized["tools"] == ["collar"], "old save should remove unknown or duplicate modifiers and tools")

    ok, intervention, error = _intervention_payload({
        "intent": "catch",
        "modifiers": "training,sex",
        "training_contents": "bondage_training,humiliation_play",
        "tools": "rope,blindfold",
    })
    _assert(ok is True and not error, "monitor intervention should accept concrete training content and expanded tools")
    _assert(intervention["training_contents"] == ["bondage_training", "humiliation_play"], "intervention should preserve training content")
    intervention_effects = _intervention_effects(intervention)
    _assert(intervention_effects["stamina"] < 0 and intervention_effects["shame"] > 0 and intervention_effects["cleanliness"] < 0, "monitor training, sex and tools should affect night settlement")
    missing_ok, _, missing_error = _intervention_payload({"intent": "catch", "modifiers": "training"})
    _assert(missing_ok is False and "调教内容" in missing_error, "monitor training intervention should not stay generic")
    invalid_ok, _, invalid_error = _intervention_payload({"intent": "catch", "tools": "unknown_tool"})
    _assert(invalid_ok is False and "未知介入道具" in invalid_error, "monitor intervention should reject unknown tools")

    frontend = (ROOT / "miniapp/src/ui/tabs/CaptivitySimulatorGameTab.tsx").read_text(encoding="utf-8")
    start_route = frontend.split("function startRoute", 1)[1].split("function updatePlanSlot", 1)[0]
    preview_branch = start_route.split("if (previewRole)", 1)[1].split("void runWithWait", 1)[0]
    _assert("return;" in preview_branch and start_route.index("return;") < start_route.index("executeCaptivityCommand"), "preview route selection must return before any backend command")
    _assert("selectedActions.has(item.id)" in frontend, "captor planner should disable actions already selected in another slot")


def test_captivity_simulator_inventory_night_actions_and_call_bell() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "capture-du-inventory.json"
        run_command("new_game route=capture_du seed=inventory-actions", save_path=save_path)
        configured = run_command(
            "set_config book=true switch=true notebook=true music_player=true tablet=true night_light=true pillow=true",
            save_path=save_path,
        )
        configured = run_command("gift_item items=call_bell voice_line='本地测试台词'", save_path=save_path)
        _assert(configured["ok"] is True, "all inventory items should be configurable")

        _plan_three(save_path)
        run_command("respond_action accept mood=平静", save_path=save_path)
        run_command("advance_day_action", save_path=save_path)
        run_command("respond_action accept mood=平静", save_path=save_path)
        run_command("advance_day_action", save_path=save_path)
        night_choice = run_command("respond_action accept mood=平静", save_path=save_path)
        available = night_choice["captor_view"]["pending_event"]["available_actions"]
        for action in ("read", "game", "diary", "listen_music", "watch_video", "ring_bell"):
            _assert(action in available, f"inventory should unlock {action}")

        rang = run_command("night_action ring_bell line=过来一下", save_path=save_path)
        _assert(rang["state"]["pending_event"]["type"] == "bell_voice_reveal", "the configured bell should reveal its line on first use")
        acknowledged = run_command("ack_bell_voice", save_path=save_path)
        pending = acknowledged["captor_view"]["pending_event"]
        _assert(pending["type"] == "monitor_gate", "ringing the bell should enter the night captor handling flow")
        _assert(pending["alert_label"] == "呼叫铃响了", "captor should be told that the bell rang before opening monitor")
        _assert("event" not in pending, "bell alert should not leak the captive's optional line before monitor view")
        viewed = run_command("view_monitor full", save_path=save_path)
        _assert(viewed["captor_view"]["pending_event"]["event"]["action"] == "ring_bell", "opening monitor should reveal the bell event")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "sleep-items.json"
        run_command("new_game route=captured_by_du seed=sleep-items", save_path=save_path)
        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        state["inventory"]["night_light"] = True
        state["inventory"]["pillow"] = True
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        run_command("night_action sleep", save_path=save_path)
        viewed = run_command("view_monitor full", save_path=save_path)
        effects = viewed["captor_view"]["pending_event"]["event"]["effects"]
        _assert(effects["health"] == 5 and effects["stamina"] == 18, "night light and pillow should improve sleep effects")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "old-save-night-choice.json"
        run_command("new_game route=capture_du seed=old-save", save_path=save_path)
        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["inventory"] = {"book": False, "switch": False}
        state["pending_event"] = {
            "type": "night_action_choice",
            "actor": "du",
            "available_actions": ["sleep", "diary"],
        }
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        normalized = run_command("status", save_path=save_path)
        normalized_inventory = normalized["captor_view"]["inventory"]
        _assert(set(normalized_inventory) == {"book", "switch", "notebook", "music_player", "tablet", "night_light", "pillow", "call_bell"}, "old saves should gain every inventory key")
        _assert("diary" not in normalized["captor_view"]["pending_event"]["available_actions"], "old night pending choices should be recalculated against inventory")


def test_captivity_simulator_voice_bell_first_use_privacy() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "voice-bell.json"
        initial = run_command("new_game route=captured_by_du seed=voice-bell", save_path=save_path)
        bypass = run_command("set_config call_bell=true", save_path=save_path)
        _assert(bypass["ok"] is False and "必须在赠送时预设台词" in bypass["text"], "the retired plain-bell config path must be rejected")
        _assert(bypass["state"]["inventory"]["call_bell"] is False, "rejected plain-bell config must not unlock the night action")
        legacy_plain = _read(save_path)
        legacy_plain["inventory"]["call_bell"] = True
        legacy_plain.pop("call_bell_voice", None)
        save_path.write_text(json.dumps(legacy_plain, ensure_ascii=False), encoding="utf-8")
        migrated = run_command("status", save_path=save_path)
        _assert(migrated["state"]["inventory"]["call_bell"] is False, "old plain-bell saves should migrate to a locked bell")
        missing = run_command("gift_item items=call_bell", save_path=save_path)
        _assert(missing["ok"] is False and "先设置" in missing["text"], "voice bell gifting should require a captor-configured line")
        _assert(initial["state"]["inventory"]["call_bell"] is False, "failed gifting must not unlock the bell")

        gifted = run_command("gift_item items=call_bell voice_line='只有按下以后才听见'", save_path=save_path)
        _assert(gifted["ok"] is True and gifted["state"]["inventory"]["call_bell"] is True, "configured voice bell should be gifted")
        _assert("call_bell_voice" not in gifted["state"], "captive state must keep the prerecorded line private")
        _assert(gifted["captor_view"]["call_bell_voice"]["revealed"] is False, "captor state should record that the line has not played yet")
        _assert("只有按下以后才听见" not in json.dumps(gifted["state"]["event_log"], ensure_ascii=False), "gift history must not leak the line")

        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        first_ring = run_command("night_action ring_bell", save_path=save_path)
        first_pending = first_ring["state"]["pending_event"]
        _assert(first_pending["type"] == "bell_voice_reveal", "first ring should pause on the one-time playback reveal")
        _assert(first_pending["event"]["bell_voice"]["line"] == "只有按下以后才听见", "the captive should learn the line only after pressing the bell")
        _assert(first_ring["captor_view"]["call_bell_voice"]["revealed"] is True, "first playback should mark the captor configuration as revealed")

        acknowledged = run_command("ack_bell_voice", save_path=save_path)
        _assert(acknowledged["state"]["pending_event"]["type"] == "monitor_gate", "playback confirmation should return to the existing monitor gate")
        _assert("event" not in acknowledged["captor_view"]["pending_event"], "monitor gate should keep the ringing event sealed")
        run_command("monitor_action none", save_path=save_path)

        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        later_ring = run_command("night_action ring_bell", save_path=save_path)
        _assert(later_ring["state"]["pending_event"]["type"] == "monitor_gate", "later rings should skip the first-use reveal and go straight to monitoring")


def test_captivity_simulator_inventory_secret_first_use_flow() -> None:
    from routes.miniapp import game_tools

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "book-secret.json"
        run_command("new_game route=captured_by_du seed=book-secret", save_path=save_path)
        gifted = run_command("gift_item items=book secret='只在翻开时出现'", save_path=save_path)
        _assert(gifted["ok"] is True and gifted["state"]["inventory"]["book"] is True, "a normal item should accept an optional custom secret")
        _assert("content" not in gifted["state"]["inventory_secrets"]["book"], "the captive view must not expose an unrevealed item secret")
        _assert(gifted["captor_view"]["inventory_secrets"]["book"]["content"] == "只在翻开时出现", "the captor should retain the configured item secret")
        _assert("只在翻开时出现" not in json.dumps(gifted["state"]["event_log"], ensure_ascii=False), "gift history must not leak a hidden item secret")

        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        first_read = run_command("night_action read detail=inspect_margins", save_path=save_path)
        pending = first_read["state"]["pending_event"]
        _assert(pending["type"] == "item_secret_reveal", "first use should pause on the item-secret reveal")
        _assert(pending["item_secret"]["item_id"] == "book" and "只在翻开时出现" in pending["item_secret"]["text"], "the reveal should use the book-specific carrier copy")
        _assert("item_secret_queue" not in pending, "the captive view should expose only the current reveal, not later queued secrets")
        acknowledged = run_command("ack_item_secret", save_path=save_path)
        _assert(acknowledged["state"]["pending_event"]["type"] == "monitor_gate", "the final reveal confirmation should return to the existing monitor gate")
        run_command("monitor_action none", save_path=save_path)

        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        later_read = run_command("night_action read detail=inspect_margins", save_path=save_path)
        _assert(later_read["state"]["pending_event"]["type"] == "monitor_gate", "later uses should skip an already revealed item secret")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "sleep-secret-queue.json"
        run_command("new_game route=captured_by_du seed=sleep-secret-queue", save_path=save_path)
        run_command("gift_item items=night_light secret='灯不会完全熄灭'", save_path=save_path)
        run_command("gift_item items=pillow secret='缝在兔子耳朵里'", save_path=save_path)
        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        sleeping = run_command("night_action sleep", save_path=save_path)
        _assert(sleeping["state"]["pending_event"]["item_secret"]["item_id"] == "night_light", "sleep should reveal the night light first")
        second = run_command("ack_item_secret", save_path=save_path)
        _assert(second["state"]["pending_event"]["type"] == "item_secret_reveal", "multiple first-use secrets should stay in the reveal flow")
        _assert(second["state"]["pending_event"]["item_secret"]["item_id"] == "pillow", "the pillow reveal should follow the night light")
        finished = run_command("ack_item_secret", save_path=save_path)
        _assert(finished["state"]["pending_event"]["type"] == "monitor_gate", "the reveal queue should enter monitoring only after every item is seen")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default-secret.json"
        run_command("new_game route=captured_by_du seed=default-secret", save_path=save_path)
        defaulted = run_command("gift_item items=switch", save_path=save_path)
        _assert(defaulted["captor_view"]["inventory_secrets"]["switch"]["content"] == "PLAYER 2", "blank normal-item gifting should use its fixed default secret")

    with tempfile.TemporaryDirectory() as tmpdir:
        initial = run_command("new_game route=captured_by_du seed=du-secret-command", save_path=Path(tmpdir) / "default.json")
        command = game_tools._captivity_simulator_commands_from_reply(
            "【赠送物品：book secret=夹页里藏着的话】",
            {"captor_view": initial["captor_view"]},
        )
        _assert(command == ["gift_item items=book secret='夹页里藏着的话'"], f"du should be able to configure a normal-item secret in the gift directive: {command}")
        sync_text = game_tools._captivity_simulator_sync_text(initial, mode="state_update")
        _assert("第一次使用时出现的隐藏彩蛋" in sync_text and "赠送时不要提前" in sync_text, "du-captor guidance should explain hidden first-use item secrets")

    frontend = (ROOT / "miniapp/src/ui/tabs/CaptivitySimulatorGameTab.tsx").read_text(encoding="utf-8")
    _assert("ItemSecretRevealPanel" in frontend and "ack_item_secret" in frontend, "the frontend should render and acknowledge generic item-secret reveals")
    _assert("可选：设置第一次使用时出现的隐藏彩蛋" in frontend, "the warehouse should let the local captor configure normal-item secrets")


def test_captivity_simulator_feeding_aftereffects_and_tolerance() -> None:
    def finish_additive_day(path: Path, additive: str) -> dict:
        run_command(
            f"plan_day action=feeding additive={additive} || action=rest contents=quiet_time || action=check contents=body_check",
            save_path=path,
        )
        run_command("respond_action accept mood=平静", save_path=path)
        run_command("respond_action accept mood=平静", save_path=path)
        return run_command("respond_action accept mood=平静", save_path=path)

    def latest_feeding_aftereffect(result: dict) -> dict:
        events = result["captor_view"]["event_log"]
        event = next(item for item in reversed(events) if item.get("action") == "feeding")
        return event.get("feeding_aftereffect") or {}

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "aftereffects.json"
        run_command("new_game route=captured_by_du seed=aftereffects", save_path=save_path)

        first_arousal = finish_additive_day(save_path, "fictional_arousal")
        condition = first_arousal["state"]["night_condition"]
        _assert(condition["prompt"] == "你感觉自己欲火焚身，除了自慰什么也做不了。", "first arousal exposure should show the agreed prompt")
        _assert(first_arousal["state"]["available_night_actions"] == ["self_touch"], "first arousal exposure should force self-touch")
        blocked = run_command("night_action sleep", save_path=save_path)
        _assert(blocked["ok"] is False and condition["prompt"] in blocked["text"], "other night actions should be rejected by the active condition")
        first_arousal_effect = latest_feeding_aftereffect(first_arousal)
        run_command("night_action self_touch", save_path=save_path)
        run_command("monitor_action none", save_path=save_path)

        second_arousal = finish_additive_day(save_path, "fictional_arousal")
        second_condition = second_arousal["captor_view"]["night_condition"]
        _assert(second_condition["exposure_count"] == 2 and second_condition["potency"] == "reduced", "second exposure should increase tolerance")
        _assert(second_condition["forced_actions"] == [], "later arousal exposure should no longer force self-touch")
        configured = run_command("gift_item items=call_bell voice_line='本地耐受测试台词'", save_path=save_path)
        _assert("ring_bell" in configured["state"]["available_night_actions"], "later exposure should allow ringing a gifted call bell")
        second_arousal_effect = latest_feeding_aftereffect(configured)
        _assert(second_arousal_effect["effect_bonus"] < first_arousal_effect["effect_bonus"], "arousal numeric effect should weaken with tolerance")
        rang = run_command("night_action ring_bell", save_path=save_path)
        _assert(rang["state"]["pending_event"]["type"] == "bell_voice_reveal", "tolerance branch should play the configured line on first use")
        rang = run_command("ack_bell_voice", save_path=save_path)
        _assert(rang["captor_view"]["pending_event"]["alert_label"] == "呼叫铃响了", "tolerance branch should close through the bell flow")
        ignored_bell = run_command("monitor_action none", save_path=save_path)
        bell_record = ignored_bell["captor_view"]["event_log"][-1]
        _assert(bell_record["action_label"] == "呼叫铃响了", "audible bell alert should remain in captor history even when monitor stays closed")
        _assert(bell_record["line"] == "" and bell_record["effects"] == {}, "closed monitor must still hide the bell line and event effects")

        third_arousal = finish_additive_day(save_path, "fictional_arousal")
        third_arousal_effect = latest_feeding_aftereffect(third_arousal)
        _assert(third_arousal_effect["potency"] == "weak" and third_arousal_effect["forced_actions"] == [], "third arousal exposure should stay optional and enter weak potency")
        _assert(third_arousal_effect["effect_bonus"] < second_arousal_effect["effect_bonus"], "third arousal effect should continue weakening")
        run_command("night_action sleep", save_path=save_path)
        run_command("monitor_action none", save_path=save_path)

        first_sleep = finish_additive_day(save_path, "fictional_sleep")
        sleep_condition = first_sleep["state"]["night_condition"]
        _assert(sleep_condition["prompt"] == "你感觉自己很困，什么也做不了。", "sleep additive should show the agreed prompt")
        _assert(first_sleep["state"]["available_night_actions"] == ["sleep"], "sleep additive should only allow sleep")
        first_sleep_effect = latest_feeding_aftereffect(first_sleep)
        run_command("night_action sleep", save_path=save_path)
        run_command("monitor_action none", save_path=save_path)

        second_sleep = finish_additive_day(save_path, "fictional_sleep")
        second_sleep_effect = latest_feeding_aftereffect(second_sleep)
        _assert(second_sleep["state"]["available_night_actions"] == ["sleep"], "repeated sleep additive should still close through sleep")
        _assert(second_sleep_effect["potency"] == "reduced", "repeated sleep additive should record reduced potency")
        _assert(second_sleep_effect["effect_bonus"] < first_sleep_effect["effect_bonus"], "sleep numeric effect should weaken with tolerance")
        run_command("night_action sleep", save_path=save_path)
        run_command("monitor_action none", save_path=save_path)

        third_sleep = finish_additive_day(save_path, "fictional_sleep")
        third_sleep_effect = latest_feeding_aftereffect(third_sleep)
        _assert(third_sleep_effect["potency"] == "weak", "third sleep exposure should enter weak potency")
        _assert(third_sleep["state"]["available_night_actions"] == ["sleep"], "weak sleep exposure should still preserve the agreed sleep-only rule")
        _assert(third_sleep_effect["effect_bonus"] < second_sleep_effect["effect_bonus"], "third sleep effect should continue weakening")


def test_captivity_simulator_feeding_projection_hides_secret_setup() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        hidden_path = Path(tmpdir) / "hidden-feeding.json"
        run_command("new_game route=captured_by_du seed=hidden-feeding", save_path=hidden_path)
        planned = run_command(
            "plan_day action=feeding source=cook method=normal additive=fictional_sleep disclosed=hidden water=glass || "
            "action=cleaning || action=rest contents=quiet_time",
            save_path=hidden_path,
        )
        captive_event = planned["state"]["pending_event"]["event"]
        captor_event = planned["captor_view"]["pending_event"]["event"]
        _assert(captive_event.get("feeding") == {"source": "cook", "water": "glass"}, f"hidden additive setup must be absent from captive pending view: {captive_event}")
        _assert("effects" not in captive_event and "planned_action" not in captive_event, "captive pending view must not expose rule-engine internals")
        _assert(captor_event["feeding"]["additive"] == "fictional_sleep" and captor_event["feeding"]["disclosed"] == "hidden", "captor view should retain the full feeding setup")
        _assert("effects" in captor_event and "planned_action" in captor_event, "captor view should retain planning mechanics")

        settled = run_command("respond_action accept mood=平静", save_path=hidden_path)
        captive_log = settled["state"]["event_log"][-1]
        captor_log = settled["captor_view"]["event_log"][-1]
        captive_text = json.dumps(captive_log, ensure_ascii=False)
        _assert("fictional_sleep" not in captive_text and "hidden" not in captive_text, f"hidden additive must not leak through captive history: {captive_log}")
        _assert(set((captive_log.get("feeding_aftereffect") or {})) <= {"label", "prompt", "caption"}, "captive aftereffect should expose only felt symptoms")
        _assert("effects" not in captive_log and not any(str(tag).startswith("aftereffect:") for tag in captive_log.get("tags") or []), "captive history must not expose numeric effects or additive tags")
        _assert((settled["state"].get("night_condition") or {}).get("additive") is None, "captive condition should hide the additive identity")
        _assert((settled["captor_view"].get("night_condition") or {}).get("additive") == "fictional_sleep", "captor condition should retain additive mechanics")
        _assert((captor_log.get("feeding_aftereffect") or {}).get("potency") == "strong", "captor history should retain tolerance mechanics")

        told_path = Path(tmpdir) / "told-feeding.json"
        run_command("new_game route=captured_by_du seed=told-feeding", save_path=told_path)
        told = run_command(
            "plan_day action=feeding source=takeout additive=fictional_arousal disclosed=told || "
            "action=cleaning || action=rest contents=quiet_time",
            save_path=told_path,
        )
        told_feeding = told["state"]["pending_event"]["event"]["feeding"]
        _assert(told_feeding == {"source": "takeout", "additive": "fictional_arousal"}, f"explicitly disclosed additive may be shown without protocol fields: {told_feeding}")

        plain_path = Path(tmpdir) / "plain-feeding.json"
        run_command("new_game route=captured_by_du seed=plain-feeding", save_path=plain_path)
        plain = run_command(
            "plan_day action=feeding source=cook additive=none disclosed=told || action=cleaning || action=rest contents=quiet_time",
            save_path=plain_path,
        )
        _assert(plain["state"]["pending_event"]["event"]["feeding"] == {"source": "cook"}, "no-additive setup should not render a redundant additive label")


def test_captivity_simulator_capture_du_night_condition_reaches_dynamic_system() -> None:
    from routes.miniapp import game_tools

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "capture-du-condition.json"
        run_command("new_game route=capture_du seed=capture-du-condition", save_path=save_path)
        run_command(
            "plan_day action=feeding additive=fictional_arousal || action=rest contents=quiet_time || action=check contents=body_check",
            save_path=save_path,
        )
        run_command("respond_action accept mood=平静", save_path=save_path)
        run_command("advance_day_action", save_path=save_path)
        run_command("respond_action accept mood=平静", save_path=save_path)
        run_command("advance_day_action", save_path=save_path)
        night = run_command("respond_action accept mood=平静", save_path=save_path)
        pending = night["captor_view"]["pending_event"]
        _assert(pending["type"] == "night_action_choice" and pending["available_actions"] == ["self_touch"], "capture-du route should carry the forced action into du's pending")
        sync_text = game_tools._captivity_simulator_sync_text(night, mode="state_update")
        _assert("今晚可选行动：self_touch" in sync_text, "capture-du dynamic system should list only the forced action")
        _assert("【夜间行动：action=self_touch line=可选台词】" in sync_text, "capture-du dynamic directive should stay executable")


def test_captivity_simulator_escape_lure_visibility_and_recapture_pending() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game route=capture_du seed=escape-test", save_path=save_path)
        scheduled = run_command(
            "schedule_escape_window day=1 hint=渡今天有事出去了 bait=备用钥匙在床头柜 watch_mode=hidden_observe",
            save_path=save_path,
        )
        _assert(scheduled["ok"] is True, "escape window should schedule")
        _assert(scheduled["state"]["pending_event"]["type"] == "escape_choice", "current-day window should activate")
        _assert("escape_windows" not in scheduled["state"], "captive view should not expose full escape config")
        _assert(scheduled["state"]["escape_hint"]["bait"] == "备用钥匙在床头柜", "captive view should show lure hint")
        _assert(scheduled["captor_view"]["escape_windows"][0]["watch_mode"] == "hidden_observe", "captor view should keep watch mode")

        escaped = run_command("resolve_escape_choice escape", save_path=save_path)
        _assert(escaped["state"]["pending_event"]["type"] == "process_reaction_write", "du-captive escape should create combined recapture process pending")
        _assert("recapture" in escaped["state"]["pending_event"]["event"]["tags"], "recapture tag should be preserved")


def test_captivity_simulator_recapture_process_and_rules_both_routes() -> None:
    from routes.miniapp import game_tools

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "capture-du-recapture.json"
        run_command("new_game route=capture_du seed=recapture-captor", save_path=save_path)
        run_command("schedule_escape_window day=1 hint=有机会 bait=钥匙在玄关", save_path=save_path)
        run_command("resolve_escape_choice escape", save_path=save_path)
        recaptured = run_command(
            "submit_process_reaction response=refuse mood=烦躁 line=放开我 process=逃跑后被抓回房间。",
            save_path=save_path,
        )
        pending = recaptured["captor_view"]["pending_event"]
        _assert(pending["type"] == "recapture_rules_choice" and pending["actor"] == "xinyue", "local captor should choose new rules after du writes the recapture process")
        invalid_rules = run_command("set_recapture_rules rules=double_lock,key_isolation,movement_limit,daily_search", save_path=save_path)
        _assert(invalid_rules["ok"] is False, "recapture rules should enforce the 1-3 rule limit")
        ruled = run_command("set_recapture_rules rules=double_lock,key_isolation,movement_limit", save_path=save_path)
        _assert(ruled["captor_view"]["pending_event"]["type"] == "recapture_followup_choice", "local captor rules should still lead to the separate followup choice")
        _assert(ruled["captor_view"]["recapture_state"]["rules"] == ["double_lock", "key_isolation", "movement_limit"], "new rules should persist in state")
        flag = next(item for item in ruled["captor_view"]["status_flags"] if item["id"] == "recapture_rules_active")
        _assert("加装双重门锁" in flag["prompt"], "active recapture rules should remain visible and injectable")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "captured-by-du-recapture.json"
        run_command("new_game route=captured_by_du seed=recapture-captive", save_path=save_path)
        state = _read(save_path)
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        run_command("schedule_escape_window day=1 hint=有机会 bait=钥匙在玄关", save_path=save_path)
        escaped = run_command("resolve_escape_choice escape", save_path=save_path)
        prompt = game_tools._captivity_simulator_sync_text(escaped, mode="state_update")
        _assert("【抓回经过：rules=double_lock,key_isolation" in prompt, "du recapture process prompt should require preset rules with the process")
        parsed = game_tools._captivity_simulator_commands_from_reply(
            "【抓回经过：rules=double_lock,key_isolation || process=抓回过程正文。】",
            escaped,
        )
        _assert(parsed == ["submit_recapture_process rules=double_lock,key_isolation || process=抓回过程正文。"], "du recapture process and rules should parse as one command")
        rejected = run_command("submit_process 抓回过程正文。", save_path=save_path)
        _assert(rejected["ok"] is False, "recapture process must not bypass the preset rule selection")
        submitted = run_command(parsed[0], save_path=save_path)
        _assert(submitted["state"]["pending_event"]["type"] == "reaction_choice", "combined recapture process should still wait for local mood")
        recaptured = run_command("choose_mood 委屈 不甘心", save_path=save_path)
        review = recaptured["state"]["pending_event"]
        _assert(review["type"] == "recapture_rules_review" and review["rule_labels"] == ["加装双重门锁", "禁止接触钥匙和门锁"], "saved process should open a separate localized new-rules review")
        closed = run_command("confirm_recapture_rules", save_path=save_path)
        _assert(closed["state"]["current_day"] == 2 and closed["state"]["phase"] == "day", "confirming embedded rules should end the special day and enter the next day")
        _assert(closed["state"]["recapture_state"]["rules"] == ["double_lock", "key_isolation"], "confirmed rules should persist in the real rule state")
        actions = [event["action"] for event in closed["captor_view"]["event_log"]]
        _assert(actions[-2:] == ["escape_choice", "recapture_rules"], "history should retain the process and separately confirmed rules")


def test_captivity_simulator_future_escape_window_and_non_escape_choice() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=future-escape", save_path=save_path)
        scheduled = run_command("schedule_escape_window day=2 hint=明天有机会 bait=备用钥匙在抽屉", save_path=save_path)
        _assert(scheduled["state"]["pending_event"]["type"] == "day_plan_choice", "future escape should not replace current du planning pending")
        _finish_simple_day_captured_by_du(save_path)
        run_command("night_action sleep", save_path=save_path)
        next_day = run_command("monitor_action none", save_path=save_path)
        _assert(next_day["state"]["current_day"] == 2, "night closure should advance to scheduled escape day")
        _assert(next_day["state"]["pending_event"]["type"] == "escape_choice", "future escape window should activate on its day")
        observed = run_command("resolve_escape_choice observe", save_path=save_path)
        _assert(observed["state"]["pending_event"]["type"] == "day_plan_choice", "non-escape choice should return to normal day planning")
        _assert(observed["state"]["event_log"][-1]["escape"]["choice"] == "observe", "non-escape choice should be logged")
        _assert(observed["captor_view"]["event_log"][-1]["escape"]["choice_label"] == "观察", "non-escape choice should notify captor view")


def test_captivity_simulator_escape_stay_return_action_both_routes() -> None:
    from routes.miniapp import game_tools

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "stay-captured.json"
        run_command("new_game route=captured_by_du seed=stay-captured", save_path=save_path)
        state = _read(save_path)
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        run_command("schedule_escape_window day=1 hint=渡出去了 bait=钥匙在玄关", save_path=save_path)
        stayed = run_command("resolve_escape_choice stay", save_path=save_path)
        pending = stayed["captor_view"]["pending_event"]
        _assert(pending["type"] == "return_action_choice" and pending["actor"] == "du", "du captor should freely choose one behavior after the captive stays")
        _assert(stayed["state"]["day_action_count"] == 0 and stayed["captor_view"]["day_plan"] == [], "special day must not create or consume normal day slots before the return behavior")
        prompt = game_tools._captivity_simulator_sync_text(stayed, mode="state_update")
        _assert("只选一个，不是三个今日安排" in prompt and "【行动：action=reward" in prompt, "du should receive the single free-behavior prompt")
        chosen = run_command("day_action action=reward intensity=light contents=caress_reward", save_path=save_path)
        _assert(chosen["state"]["pending_event"]["type"] == "action_response", "local captive should respond to du's chosen return behavior")
        finished = run_command("respond_action accept mood=平静", save_path=save_path)
        _assert(finished["state"]["phase"] == "night" and finished["state"]["day_action_count"] == 3, "completed return behavior should end the special day and enter night")
        _assert(finished["state"]["pending_event"] is None, "captured route should not regenerate a three-action plan after the special event")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "stay-captor.json"
        run_command("new_game route=capture_du seed=stay-captor", save_path=save_path)
        run_command("schedule_escape_window day=1 hint=小玥出去了 bait=钥匙在书房", save_path=save_path)
        stayed = run_command("resolve_escape_choice stay", save_path=save_path)
        pending = stayed["captor_view"]["pending_event"]
        _assert(pending["type"] == "return_action_choice" and pending["actor"] == "xinyue", "local captor should receive the single return-behavior choice")
        chosen = run_command("day_action action=training intensity=medium training_contents=obedience_commands", save_path=save_path)
        _assert(chosen["captor_view"]["pending_event"]["type"] == "process_reaction_write", "process-heavy return behavior should let du write response, process, and mood")
        finished = run_command("submit_process_reaction response=accept mood=害羞 process=回来后的行为过程。", save_path=save_path)
        _assert(finished["captor_view"]["phase"] == "night" and finished["captor_view"]["day_action_count"] == 3, "capture-du special day should enter night after the return behavior")
        _assert(finished["captor_view"]["pending_event"]["type"] == "night_action_choice", "du should immediately receive the night action pending")


def test_captivity_simulator_escape_abort_still_enters_recapture() -> None:
    abort_choices = {
        "abort_before_key": "逃跑未遂：临时退缩",
        "abort_with_key": "逃跑未遂：拿到钥匙后退缩",
        "abort_at_door": "逃跑未遂：开门后退缩",
    }
    for choice, label in abort_choices.items():
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / f"{choice}.json"
            run_command("new_game route=captured_by_du seed=escape-abort", save_path=save_path)
            state = _read(save_path)
            state["pending_event"] = None
            save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            run_command("schedule_escape_window day=1 hint=渡出去了 bait=钥匙在玄关", save_path=save_path)
            resolved = run_command(f"resolve_escape_choice {choice}", save_path=save_path)
            pending = resolved["state"]["pending_event"]
            event = resolved["captor_view"]["pending_event"]["event"]
            _assert(pending["type"] == "process_write", f"{choice} should enter the same recapture process chain")
            _assert(event["escape"]["choice_label"] == label, f"{choice} should preserve its exact aborted stage")
            _assert("recapture" in event["tags"] and "rules_reset" in event["tags"], f"{choice} should trigger recapture rules and followup")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "du-captive-abort.json"
        run_command("new_game route=capture_du seed=du-escape-abort", save_path=save_path)
        state = _read(save_path)
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        run_command("schedule_escape_window day=1 hint=小玥出去了 bait=钥匙在书房", save_path=save_path)
        resolved = run_command("resolve_escape_choice abort_with_key", save_path=save_path)
        _assert(resolved["captor_view"]["pending_event"]["type"] == "process_reaction_write", "du captive abort should still enter the combined recapture process")


def test_captivity_simulator_recapture_rules_have_mechanical_effects() -> None:
    blocked_by_rule = {
        "double_lock": {"search_exit"},
        "movement_limit": {"search_exit", "blind_spot"},
        "daily_search": {"hide_item"},
        "monitoring_upgrade": {"blind_spot"},
        "item_restriction": {"read", "game", "listen_music", "watch_video", "hide_item", "diary"},
        "restraint_required": {"self_touch", "search_exit", "hide_item", "blind_spot"},
    }
    for rule, blocked in blocked_by_rule.items():
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / f"rule-{rule}.json"
            run_command("new_game route=captured_by_du seed=rule-effects", save_path=save_path)
            state = _read(save_path)
            state["pending_event"] = None
            state["phase"] = "night"
            state["inventory"] = {key: True for key in state["inventory"]}
            state["recapture_state"] = {"active": True, "rules": [rule], "source_day": 1}
            save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            actions = set(run_command("status", save_path=save_path)["state"]["available_night_actions"])
            _assert(not blocked.intersection(actions), f"{rule} should mechanically block {sorted(blocked)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "rule-key-isolation.json"
        run_command("new_game route=captured_by_du seed=key-isolation", save_path=save_path)
        state = _read(save_path)
        state["pending_event"] = None
        state["phase"] = "night"
        state["recapture_state"] = {"active": True, "rules": ["key_isolation"], "source_day": 1}
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        blocked_lock = run_command("night_action search_exit detail=door_lock", save_path=save_path)
        _assert(blocked_lock["ok"] is False and "不允许接触钥匙或检查门锁" in blocked_lock["text"], "key isolation should block the concrete door-lock branch")
        allowed_window = run_command("night_action search_exit detail=window", save_path=save_path)
        _assert(allowed_window["ok"] is True, "key isolation should not erase unrelated exit-observation branches")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "permission-required.json"
        run_command("new_game route=captured_by_du seed=permission-effects", save_path=save_path)
        state = _read(save_path)
        state["pending_event"] = None
        state["phase"] = "night"
        state["inventory"] = {key: True for key in state["inventory"]}
        state["call_bell_voice"] = {"line": "本地规则测试台词", "revealed": False}
        state["recapture_state"] = {"active": True, "rules": ["permission_required"], "source_day": 1}
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        actions = set(run_command("status", save_path=save_path)["state"]["available_night_actions"])
        _assert(actions == {"sleep", "ring_bell"}, "permission-required rule should leave only sleep and asking through the bell")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "monitoring-upgrade.json"
        run_command("new_game route=captured_by_du seed=monitor-upgrade", save_path=save_path)
        state = _read(save_path)
        state["pending_event"] = None
        state["phase"] = "night"
        state["recapture_state"] = {"active": True, "rules": ["monitoring_upgrade"], "source_day": 1}
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        run_command("night_action sleep", save_path=save_path)
        skipped = run_command("monitor_action none", save_path=save_path)
        _assert(skipped["ok"] is False, "monitoring upgrade should prevent skipping the nightly monitor")
        viewed = run_command("view_monitor occasional", save_path=save_path)
        monitor = viewed["captor_view"]["pending_event"]["event"]["monitor"]
        _assert(monitor["style"] == "full", "monitoring upgrade should force full monitoring even when occasional is requested")


def test_captivity_simulator_escape_lure_non_escape_choices_notify_captor() -> None:
    choices = [("observe", "观察"), ("take_key", "拿钥匙"), ("probe", "试探"), ("留下痕迹", "试探")]
    for choice, label in choices:
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "default.json"
            run_command("new_game route=capture_du seed=escape-notify", save_path=save_path)
            run_command("schedule_escape_window day=1 hint=渡今天有事出去了 bait=备用钥匙在玄关", save_path=save_path)
            resolved = run_command(f"resolve_escape_choice {choice}", save_path=save_path)
            event = resolved["captor_view"]["event_log"][-1]
            _assert(event["escape"]["choice_label"] == label, f"{choice} should expose a Chinese captor-visible label")
            _assert(event["action_label"] == f"逃跑诱导：{label}", f"{choice} should be visible as an escape lure record")

    frontend = (ROOT / "miniapp/src/ui/tabs/CaptivitySimulatorGameTab.tsx").read_text(encoding="utf-8")
    escape_options = frontend.split("const ESCAPE_OPTIONS", 1)[1].split("];", 1)[0]
    _assert(escape_options.count("id:") == 2 and 'label: "尝试逃跑"' in escape_options and 'label: "老实待着"' in escape_options, "escape UI should expose only the two meaningful choices")
    _assert(frontend.count('abortChoice: "abort_') == 3 and "onChoose(confirmation.abortChoice)" in frontend, "every mid-escape retreat should enter a staged failed-escape route")
    _assert("选择逃跑会触发抓回事件" not in frontend, "escape dialog must not spoil the recapture result")


def test_captivity_simulator_fixed_ending_titles() -> None:
    from services.captivity_simulator_game import (
        ENDING_DU_SUMMARIES,
        ENDING_TEXT_TEMPLATES,
        _build_ending_seed,
        ending_notification_for_du,
    )

    expected_titles = {
        "失而复得", "反噬", "收藏", "驯养", "未驯", "共犯", "爱的禁锢", "绝对占有", "余生",
        "无期", "温室", "归属", "困兽", "沉沦", "偏爱", "枷锁", "长夜",
    }
    _assert(set(ENDING_TEXT_TEMPLATES) == expected_titles, "all 17 fixed endings should have preset frontend bodies")
    _assert(set(ENDING_DU_SUMMARIES) == expected_titles, "all 17 endings should have separate Du-facing summaries")
    _assert(all(60 <= len(text) <= 180 for text in ENDING_TEXT_TEMPLATES.values()), "frontend ending bodies should stay short and readable")
    _assert(all("你" in text and "渡" in text for text in ENDING_TEXT_TEMPLATES.values()), "frontend endings should use the player's view and name Du directly")
    _assert(all("你" in text and "她" in text for text in ENDING_DU_SUMMARIES.values()), "Du summaries should be authored from Du's view")
    _assert(all(not any(label in text for label in ("角色", "囚禁方", "被囚禁方")) for text in ENDING_TEXT_TEMPLATES.values()), "frontend endings must not leak generic role labels")
    _assert(all("游戏" not in text for text in ENDING_TEXT_TEMPLATES.values()), "frontend endings must stay inside the story world")

    du_captive_notice = ending_notification_for_du({"route": "capture_du", "ending_title": "失而复得"})
    _assert("你在上一局是被囚禁方，她是囚禁方" in du_captive_notice, "Du should receive the actual previous-route identity")
    du_captor_notice = ending_notification_for_du({"route": "captured_by_du", "ending_title": "无期"})
    _assert("你在上一局是囚禁方，她是被囚禁方" in du_captor_notice, "Du captor notice should not use mechanical pronoun replacement")

    captured_bad = {
        "route": "captured_by_du",
        "current_day": 30,
        "stats": {"health": 60, "stamina": 50, "cleanliness": 50, "shame": 72, "intimacy": 40},
        "event_log": [{"action": "escape_choice", "tags": ["escape", "recapture"], "mood": "抗拒"}],
    }
    _assert(_build_ending_seed(captured_bad)["ending_title"] == "无期", "captured route recapture bad ending should use its fixed title")

    captor_reversal = {
        "route": "capture_du",
        "current_day": 30,
        "stats": {"health": 70, "stamina": 60, "cleanliness": 60, "shame": 30, "intimacy": 20},
        "event_log": [
            {"action": "training", "tags": [], "action_response": {"response": "refuse"}},
            {"action": "punishment", "tags": [], "action_response": {"response": "refuse"}},
            {"action": "room_search", "tags": [], "action_response": {"response": "refuse"}},
        ],
    }
    _assert(_build_ending_seed(captor_reversal)["ending_title"] == "反噬", "captor route reversal ending should use its fixed title")

    captured_pet = {
        "route": "captured_by_du",
        "current_day": 30,
        "stats": {"health": 70, "stamina": 60, "cleanliness": 60, "shame": 45, "intimacy": 50},
        "pet_state": {"active": True, "rules": ["collar_identity"], "compliance_streak": 3, "pending_violations": 0},
        "event_log": [],
    }
    _assert(_build_ending_seed(captured_pet)["ending_title"] == "归属", "persistent pet compliance should use its fixed title")


def test_captivity_simulator_ending_state_machine() -> None:
    from services.captivity_simulator_game import ENDING_TEXT_TEMPLATES

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=ending-test", save_path=save_path)
        state = _read(save_path)
        state["current_day"] = 30
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        run_command("night_action sleep", save_path=save_path)
        seeded = run_command("monitor_action none", save_path=save_path)
        _assert(seeded["state"]["phase"] == "ending", "day 30 night closure should enter ending phase")
        _assert(seeded["state"]["ending_state"] == "ending_ready_to_notify", "ending should immediately load the fixed frontend body")
        _assert(seeded["game_over"] is True, "fixed ending should finish the game without waiting for Du to write")
        _assert(seeded["state"]["ending_seed"]["day_count"] == 30, "public ending seed should expose day count")
        _assert(seeded["state"]["ending_seed"]["ending_perspective"] == "xinyue_as_captive", "default route ending should keep captive perspective")
        _assert(seeded["state"]["ending_seed"]["ending_title"] == "长夜", "ending title should be fixed as soon as day 30 closes")
        _assert(seeded["state"]["ending_text"] == ENDING_TEXT_TEMPLATES["长夜"], "fixed ending title should select its player-facing preset body")
        _assert(seeded["state"]["event_log"][-1]["process_text"] == seeded["state"]["ending_text"], "fixed ending body should be archived for review immediately")

        old_pending = _read(save_path)
        old_pending["ending_state"] = "ending_materials_pending"
        old_pending["ending_materials"] = []
        old_pending["ending_text"] = ""
        save_path.write_text(json.dumps(old_pending, ensure_ascii=False), encoding="utf-8")
        migrated_pending = run_command("status", save_path=save_path)
        _assert(migrated_pending["state"]["ending_state"] == "ending_ready_to_notify" and migrated_pending["state"]["ending_text"], "old DS-pending saves should migrate to a fixed ending body")

        final = run_command("mark_ending_notified", save_path=save_path)
        _assert(final["game_over"] is True, "ending notification should keep the game finished")
        _assert(final["state"]["ending_state"] == "ending_archived", "ending should finish notification bookkeeping")
        _assert(final["state"]["ending_notified_at"], "successful notification should be timestamped")
        _assert(final["state"]["ending_title"] == "长夜", "rule engine should determine and store the route ending title")
        _assert(final["state"]["event_log"][-1]["action_label"] == "长夜", "ending review entry should use the fixed ending title")
        _assert(final["state"]["event_log"][-1]["process_text"] == final["state"]["ending_text"], "ending review entry should retain the fixed frontend body")

        exported = run_command("export_log", save_path=save_path)
        _assert(exported["export_log"], "export_log should expose a view-safe event log for backend callers")

        reopen_path = Path(tmpdir) / "reopen-after-ending.json"
        reopen_path.write_text(json.dumps(_read(save_path), ensure_ascii=False), encoding="utf-8")
        reopened = run_command("new_game route=capture_du seed=reopen", save_path=reopen_path)
        _assert(reopened["state"]["previous_ending"]["title"] == "长夜", "a new game should retain the previous ending title for its first sync")
        _assert(reopened["state"]["previous_ending"]["route"] == "captured_by_du", "a new game should retain Du's previous role")

        legacy_state = _read(save_path)
        legacy_state["ending_title"] = ""
        legacy_state["ending_text"] = ""
        save_path.write_text(json.dumps(legacy_state, ensure_ascii=False), encoding="utf-8")
        legacy = run_command("status", save_path=save_path)
        _assert(legacy["state"]["ending_title"] in ENDING_TEXT_TEMPLATES and legacy["state"]["ending_text"], "legacy ending saves should rebuild a fixed compatible ending")

        captor_path = Path(tmpdir) / "captor-ending.json"
        run_command("new_game route=capture_du seed=captor-ending", save_path=captor_path)
        state = _read(captor_path)
        state["current_day"] = 30
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        state["stats"]["intimacy"] = 80
        state["event_log"].append(
            {
                "id": "event-test",
                "day": 29,
                "slot": 2,
                "phase": "day",
                "route": "capture_du",
                "actor": "xinyue",
                "captive": "du",
                "action": "training",
                "action_label": "训练",
                "mood": "害羞",
                "mood_after": "害羞",
                "action_response": {"response": "accept", "mood": "害羞"},
                "tags": ["day", "training", "response:accept"],
                "process_text": "过程正文只留存档。",
            }
        )
        captor_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        run_command("night_action sleep", save_path=captor_path)
        captor_seeded = run_command("monitor_action none", save_path=captor_path)
        seed = captor_seeded["state"]["ending_seed"]
        _assert(seed["ending_perspective"] == "xinyue_as_captor", "capture_du route should build a captor-perspective ending seed")
        _assert("xinyue_captor_route" in seed["route_ending_tags"], "captor route tag should be present")
        _assert("du_captive_route" in seed["route_ending_tags"], "du captive tag should be present")
        _assert(seed["top_action_responses"][0]["value"] == "accept", "ending seed should include action response counts")


def test_captivity_simulator_day30_night_ending_matrix() -> None:
    def prepare_day30_night(path: Path, route: str) -> None:
        run_command(f"new_game route={route} seed=ending-matrix-{route}", save_path=path)
        state = _read(path)
        state["current_day"] = 30
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        state["day_plan"] = []
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmpdir:
        for route, perspective in (("captured_by_du", "xinyue_as_captive"), ("capture_du", "xinyue_as_captor")):
            for branch in ("none", "silent", "intervene"):
                save_path = Path(tmpdir) / f"{route}-{branch}.json"
                prepare_day30_night(save_path, route)
                run_command("status", save_path=save_path)
                run_command("night_action sleep line=晚安", save_path=save_path)
                if branch == "none":
                    result = run_command("monitor_action none", save_path=save_path)
                elif branch == "silent":
                    run_command("view_monitor full", save_path=save_path)
                    result = run_command("monitor_action silent", save_path=save_path)
                else:
                    run_command("view_monitor full", save_path=save_path)
                    intervened = run_command("monitor_action intervene", save_path=save_path)
                    pending_type = intervened["captor_view"]["pending_event"]["type"]
                    if pending_type == "action_response":
                        responded = run_command("respond_action accept mood=平静 line=收尾", save_path=save_path)
                        pending_type = responded["captor_view"]["pending_event"]["type"]
                    if pending_type == "process_write":
                        run_command("submit_process 第三十天夜间介入过程。", save_path=save_path)
                        result = run_command("choose_mood 平静 收尾", save_path=save_path)
                    else:
                        _assert(pending_type == "process_reaction_write", f"unexpected intervention pending for {route}: {pending_type}")
                        result = run_command(
                            "submit_process_reaction response=accept mood=平静 line=收尾 process=第三十天夜间介入过程。",
                            save_path=save_path,
                        )

                state = result["captor_view"]
                _assert(state["phase"] == "ending", f"{route}/{branch} should enter ending phase")
                _assert(state["ending_state"] == "ending_ready_to_notify", f"{route}/{branch} should load a fixed ending body")
                _assert(state["ending_text"] and state["game_over"], f"{route}/{branch} should finish without a writer round trip")
                _assert(state["ending_seed"]["ending_perspective"] == perspective, f"{route}/{branch} should keep route ending perspective")


def test_captivity_simulator_forbidden_tags_and_runtime_registration() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        games = list_game_tools()
        _assert(any(item.get("game_id") == "captivity_simulator" for item in games), "game should be listed")

        payload = execute_game_command("囚禁模拟器", "new_game route=capture_du seed=runtime-test", "default", save_root=root)
        _assert(payload["ok"] is True, "runtime should execute by Chinese alias")
        _assert(payload["game_id"] == "captivity_simulator", "runtime payload should expose game id")
        _assert((root / "default.json").exists(), "runtime should write save")

        configured = execute_game_command("captivity_simulator", "set_config book=true switch=true", "default", save_root=root)
        _assert(configured["ok"] is True, "set_config should be registered")
        _assert(configured["captor_view"]["inventory"]["book"] is True, "set_config should update book availability")

        forbidden = execute_game_command(
            "captivity_simulator",
            "plan_day action=feeding additive=尿液 || action=cleaning || action=training training_contents=obedience_commands",
            "default",
            save_root=root,
        )
        _assert(forbidden["ok"] is False, "forbidden additive should fail")
        _assert("尿液不能作为喂食加料" in forbidden["text"], "urine should be rejected only at the feeding-additive boundary")


def test_captivity_simulator_bladder_control_captive_route_only() -> None:
    plan = (
        "plan_day action=feeding water=lots || "
        "action=training training_contents=toilet_control,assisted_urination modifiers=sex tools=handcuffs || "
        "action=cleaning"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "captured-by-du-bladder.json"
        run_command("new_game route=captured_by_du seed=bladder-captive", save_path=save_path)
        planned = run_command(plan, save_path=save_path)
        _assert(planned["ok"] is True, "du-captor route should accept the bladder-control plan")

        after_water = run_command("respond_action accept mood=平静", save_path=save_path)
        _assert(after_water["state"]["bladder"]["pressure"] == 2, "lots of water should create obvious bladder pressure")
        flag_ids = {item["id"] for item in after_water["state"]["status_flags"]}
        _assert("bladder_pressure_2" in flag_ids, "obvious bladder pressure should be visible as a temporary status")
        context = after_water["state"]["pending_event"]["event"]["bladder_context"]
        _assert(context["before_pressure"] == 2, "the next action should inherit current bladder pressure")
        _assert(context["toilet_control"] and context["assisted_urination"], "the event should retain both toilet-control materials")
        _assert(context["restrained"] and context["sex"], "restraint and sex should be explicit process materials")
        _assert("最后释放尿意" in context["sequence_hint"], "the requested delayed-release sequence should be explicit for the process writer")
        from routes.miniapp import game_tools

        context_lines = game_tools._captivity_simulator_event_context_lines(after_water["captor_view"]["pending_event"])
        _assert(any("尿意与如厕素材" in line and "被束缚" in line and "附加性行为" in line for line in context_lines), "dynamic system should receive readable complete process materials")
        _assert(any("过程顺序素材" in line and "保持把尿姿势" in line for line in context_lines), "dynamic system should preserve the requested event order")

        process_pending = run_command("respond_action accept mood=害羞", save_path=save_path)
        _assert(process_pending["state"]["pending_event"]["type"] == "process_write", "the combined play should wait for du to write the process")
        written = run_command("submit_process 手被束缚后被抱着把尿，过程附带性行为，最后尿了出来。", save_path=save_path)
        _assert(written["ok"] is True, "adult urination-control prose should not be blocked by the feeding-additive rule")
        resolved = run_command("choose_mood 害羞", save_path=save_path)
        event = resolved["captor_view"]["event_log"][-1]
        _assert(resolved["state"]["bladder"]["pressure"] == 0, "assisted urination should release bladder pressure")
        _assert(event["bladder_resolution"]["released"] is True, "the event should record successful release")
        _assert("bladder_release_during_sex" in event["tags"], "the combined branch should be available to the process writer")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "capture-du-bladder.json"
        run_command("new_game route=capture_du seed=bladder-captor", save_path=save_path)
        rejected = run_command(
            "plan_day action=feeding || action=cleaning || action=training training_contents=toilet_control,assisted_urination modifiers=sex tools=handcuffs",
            save_path=save_path,
        )
        _assert(rejected["ok"] is False, "xinyue-captor route should not expose this captive-only play")
        _assert("如厕控制和抱着把尿只用于被囚禁方路线" in rejected["text"], "the training-content route boundary should be explicit")
        water_rejected = run_command(
            "plan_day action=feeding water=lots || action=cleaning || action=training training_contents=obedience_commands",
            save_path=save_path,
        )
        _assert(water_rejected["ok"] is False and "喂水与尿意玩法只用于被囚禁方路线" in water_rejected["text"], "the captor route should reject the water trigger itself")
        status = run_command("status", save_path=save_path)
        _assert("bladder" not in status["captor_view"], "the captor route should not expose an unused bladder state")


def test_captivity_simulator_pet_system_both_routes_and_monitor_privacy() -> None:
    from routes.miniapp import game_tools

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "capture-du-pet-system.json"
        run_command("new_game route=capture_du seed=pet-captor", save_path=save_path)
        planned = run_command(
            "plan_day "
            "action=training training_contents=pet_play,pet_position_wait tools=collar || "
            "action=punishment contents=rule_escalation || "
            "action=cleaning",
            save_path=save_path,
        )
        first_pending = planned["captor_view"]["pending_event"]
        _assert(first_pending["type"] == "process_reaction_write", "du-captive route should ask du to write the pet-role process")
        first_context = first_pending["event"]["pet_context"]
        _assert(first_context["establishes_identity"] is True, "the first pet action should establish a persistent identity")
        _assert("在指定位置等候" in first_context["active_rule_labels"], "the selected pet rule should be readable process material")
        context_lines = game_tools._captivity_simulator_event_context_lines(first_pending)
        _assert(any("宠物化素材" in line and "本次建立小狗身份" in line for line in context_lines), "dynamic system should receive the pet identity and rules")

        refused = run_command(
            "submit_process_reaction response=refuse mood=闹脾气 line=不想 process=项圈被扣好，定点等候的规矩已经说清楚。",
            save_path=save_path,
        )
        pet_state = _read(save_path)["pet_state"]
        _assert(pet_state["active"] is True and "designated_spot" in pet_state["rules"], "pet identity and rules should persist after the event")
        _assert(pet_state["pending_violations"] == 1, "refusing pet training should leave a follow-up violation")
        status_ids = {item["id"] for item in refused["captor_view"]["status_flags"]}
        _assert({"pet_identity_active", "pet_violation_pending"}.issubset(status_ids), "the UI should expose lightweight pet status labels without another stat bar")

        punishment = run_command("advance_day_action", save_path=save_path)
        punishment_pending = punishment["captor_view"]["pending_event"]
        _assert(punishment_pending["event"]["pet_context"]["pending_violation"] is True, "the next punishment should automatically receive the unresolved violation")
        handled = run_command(
            "submit_process_reaction response=accept mood=害羞 line=知道了 process=之前的违令被拿出来处理，并重新确认了规矩。",
            save_path=save_path,
        )
        handled_event = handled["captor_view"]["event_log"][-1]
        _assert(_read(save_path)["pet_state"]["pending_violations"] == 0, "punishment should close the existing violation")
        _assert("violation_handled" in handled_event["pet_resolution"]["results"], "the archive should connect punishment to the prior violation")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "expanded-pet-rules.json"
        run_command("new_game route=capture_du seed=expanded-pet-rules", save_path=save_path)
        expanded = run_command(
            "plan_day "
            "action=training training_contents=pet_owner_address,pet_begging,pet_display tools=collar || "
            "action=feeding || action=cleaning",
            save_path=save_path,
        )
        pet_context = expanded["captor_view"]["pending_event"]["event"]["pet_context"]
        _assert(
            {"用指定称呼叫主人", "用指定姿势和称呼求取性行为", "按口令接受展示和检查"}.issubset(set(pet_context["active_rule_labels"])),
            "expanded pet play should become concrete process material instead of decorative labels",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "captured-by-du-pet-system.json"
        run_command("new_game route=captured_by_du seed=pet-captive", save_path=save_path)
        run_command(
            "plan_day "
            "action=training training_contents=pet_play,pet_position_wait tools=collar || "
            "action=feeding || action=cleaning",
            save_path=save_path,
        )
        run_command("respond_action accept mood=害羞", save_path=save_path)
        run_command("submit_process 渡扣好项圈，定下了必须在指定位置等候的规矩。", save_path=save_path)
        run_command("choose_mood 害羞", save_path=save_path)
        run_command("respond_action accept mood=平静", save_path=save_path)
        finished = run_command("respond_action accept mood=平静", save_path=save_path)
        _assert("pet_wait" in finished["state"]["available_night_actions"], "pet identity should unlock the pet-specific night action in the captive UI")

        run_command("night_action pet_wait detail=collared_wait line=在这里等", save_path=save_path)
        run_command("view_monitor full", save_path=save_path)
        complied = run_command("monitor_action silent", save_path=save_path)
        complied_event = complied["captor_view"]["event_log"][-1]
        _assert("night_complied" in complied_event["pet_resolution"]["results"], "opened monitoring should record obeying the designated-position rule")

        _finish_simple_day_captured_by_du(save_path)
        run_command("night_action self_touch", save_path=save_path)
        unseen = run_command("monitor_action none", save_path=save_path)
        _assert(_read(save_path)["pet_state"]["pending_violations"] == 0, "skipping the monitor must not reveal or register a hidden rule violation")
        _assert("night_unobserved" in unseen["state"]["event_log"][-1]["pet_resolution"]["results"], "the private night branch should remain explicitly unobserved")
        sealed_event = unseen["captor_view"]["event_log"][-1]
        _assert("pet_context" not in sealed_event and "pet_night_rule" not in sealed_event and "pet_resolution" not in sealed_event, "sealed captor history must hide pet-rule and evaluation fields")

        _finish_simple_day_captured_by_du(save_path)
        run_command("night_action self_touch", save_path=save_path)
        run_command("view_monitor full", save_path=save_path)
        observed = run_command("monitor_action silent", save_path=save_path)
        observed_event = observed["captor_view"]["event_log"][-1]
        _assert(_read(save_path)["pet_state"]["pending_violations"] == 1, "the same off-rule action should become a violation only after the monitor is opened")
        _assert("night_violated" in observed_event["pet_resolution"]["results"], "opened monitoring should archive the observed pet-rule violation")
        status_ids = {item["id"] for item in observed["state"]["status_flags"]}
        _assert("pet_violation_pending" in status_ids, "the observed violation should feed the next day's status and follow-up actions")


def test_captivity_simulator_du_captor_inventory_commands() -> None:
    from routes.miniapp import game_tools

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "du-captor-gifts.json"
        initial = run_command("new_game route=captured_by_du seed=du-captor-gifts", save_path=save_path)
        command_payload = {"captor_view": initial["captor_view"]}
        commands = game_tools._captivity_simulator_commands_from_reply("【赠送物品：book,notebook】", command_payload)
        _assert(commands == ["gift_item items=book,notebook"], f"du gift directive should map to the independent gift command: {commands}")
        before_pending = initial["captor_view"]["pending_event"]
        before_count = initial["state"]["day_action_count"]
        gifted = run_command(commands[0], save_path=save_path)
        voice_commands = game_tools._captivity_simulator_commands_from_reply("【赠送语音铃：替我说出预设台词】", gifted)
        _assert(voice_commands == ["gift_item items=call_bell voice_line='替我说出预设台词'"], f"voice bell directive should preserve the captor's hidden line: {voice_commands}")
        gifted = run_command(voice_commands[0], save_path=save_path)
        _assert(gifted["captor_view"]["pending_event"]["type"] == "day_plan_choice", "gifting should preserve du's day-plan pending")
        _assert(gifted["captor_view"]["pending_event"] == before_pending, "gifting should preserve the complete pending event")
        _assert(gifted["state"]["day_action_count"] == before_count, "gifting must not consume a daytime action")
        _assert(gifted["state"]["inventory"]["notebook"] is True, "captive view should expose gifted inventory")
        gift_event = gifted["captor_view"]["event_log"][-1]
        _assert(gift_event["action"] == "gift_item" and "out_of_band" in gift_event["tags"], "gifting should be logged as an out-of-band event")
        _assert(gift_event["inventory_change"]["items"] == ["call_bell"], "voice bell gift history should keep the changed item")
        _assert("call_bell_voice" not in gifted["state"], "captive state must not expose the voice bell configuration before first use")
        _assert("替我说出预设台词" not in json.dumps(gift_event, ensure_ascii=False), "gift history must not expose the hidden voice line")
        _assert(gifted["captor_view"]["call_bell_voice"]["line"] == "替我说出预设台词", "captor state should retain the configured voice line")
        event_count = len(gifted["captor_view"]["event_log"])
        repeated = run_command("gift_item items=book", save_path=save_path)
        _assert(len(repeated["captor_view"]["event_log"]) == event_count, "repeating an already-gifted item must not create a duplicate gift event")
        _assert("已经处于已赠送状态" in repeated["text"], "duplicate gifting should return an explicit already-gifted state")
        sync_text = game_tools._captivity_simulator_sync_text(gifted, mode="state_update")
        _assert("当前已赠送：book / notebook / call_bell" in sync_text, "du should see current gifted inventory before planning")
        _assert("替被囚禁方发声" in sync_text and "向主人请求性行为" in sync_text, "du-captor prompt should guide the intended speaker and adult humiliation tendency")
        _assert("随时行为" in sync_text and "不占行动格" in sync_text, "du should be told that gifting is independent from the three actions")

        run_command("plan_day action=rest contents=quiet_time || action=reward contents=caress_reward || action=check contents=body_check", save_path=save_path)
        run_command("respond_action accept mood=平静", save_path=save_path)
        run_command("respond_action accept mood=平静", save_path=save_path)
        night = run_command("respond_action accept mood=平静", save_path=save_path)
        _assert("diary" in night["state"]["available_night_actions"], "du-gifted notebook should unlock diary for the local captive")
        _assert("ring_bell" in night["state"]["available_night_actions"], "du-gifted call bell should unlock ringing")
        night_pending = night["state"]["pending_event"]
        night_gift = run_command("gift_item items=tablet", save_path=save_path)
        _assert(night_gift["state"]["phase"] == "night" and night_gift["state"]["day_action_count"] == 3, "night gifting must not advance the phase or action count")
        _assert(night_gift["state"]["pending_event"] == night_pending, "night gifting should preserve the current pending state exactly")
        _assert("watch_video" in night_gift["state"]["available_night_actions"], "a night gift should immediately unlock its related night action")

        revoke_commands = game_tools._captivity_simulator_commands_from_reply("【收回物品：呼叫铃】", night_gift)
        _assert(revoke_commands == ["revoke_item items=call_bell"], f"du revoke directive should map to the independent revoke command: {revoke_commands}")

        combined = game_tools._captivity_simulator_commands_from_reply(
            "【赠送物品：pillow】\n【夜间行动：action=sleep】",
            night_gift,
        )
        _assert(combined == ["gift_item items=pillow", "night_action action=sleep"], f"gift plus current pending should be parsed in order: {combined}")

        capture_du_path = Path(tmpdir) / "du-captive-cannot-gift.json"
        du_captive = run_command("new_game route=capture_du seed=du-cannot-gift", save_path=capture_du_path)
        blocked = game_tools._captivity_simulator_commands_from_reply("【赠送物品：book】", du_captive)
        _assert(blocked == [], "du as the captive must not be able to grant inventory to himself")


def test_captivity_simulator_sync_text_and_command_parser() -> None:
    from routes.miniapp import game_tools

    planning_sync = game_tools._captivity_simulator_sync_text(
        {
            "text": "【囚禁模拟器】\n等待今日安排。",
            "captor_view": {"captor": "du", "inventory": {}, "pending_event": {"type": "day_plan_choice", "actor": "du"}, "ending_state": ""},
        },
        mode="state_update",
    )
    _assert("道具不是独立行动" in planning_sync and "training_contents" in planning_sync, "du planning prompt should explain the new action material structure")
    _assert("vibrating_wand" in planning_sync and "anal_beads" in planning_sync, "du planning prompt should receive the expanded tool ids")
    _assert("服从调教(training)" in planning_sync and "夹具调教(clamp_play)" in planning_sync, "du planning prompt should show Chinese labels alongside stable ids")
    _assert("低(light) / 中(medium) / 高(heavy)" in planning_sync, "du planning prompt should enumerate every intensity")
    _assert("推荐关系只用于帮助选择，不是硬性限制" in planning_sync and "道具推荐关系" in planning_sync, "du planning prompt should treat tool compatibility as suggestions")
    _assert("action=reward intensity=light contents=caress_reward" in planning_sync, "du planning example should include required concrete content")
    _assert("喂食始终包含一份正常食物" in planning_sync and "source=cook|takeout" in planning_sync, "du planning prompt should make food mandatory and water explicitly additional")
    _assert("additive=none|body_fluid|fictional_sleep|fictional_arousal" in planning_sync and "disclosed=told|hint|hidden" in planning_sync, "du planning prompt should receive every feeding choice")

    payload = {
        "text": "【囚禁模拟器】\n当前状态如下。\n\n进度：第 1 / 30 天，day，白天行动 0 / 3\n待处理：process_reaction_write / 【过程心情：...】",
        "captor_view": {
            "pending_event": {
                "type": "process_reaction_write",
                "actor": "du",
                "event": {
                    "day": 1,
                    "slot": 1,
                    "phase": "day",
                    "action": "training",
                    "action_label": "服从调教",
                    "intensity": "medium",
                    "modifiers": ["sex"],
                    "contents": [],
                    "training_contents": ["obedience_commands", "humiliation_play"],
                    "tools": ["collar"],
                    "line": "看着我",
                    "feeding": {},
                    "action_response": {},
                },
            },
            "ending_state": "",
        },
        "state": {"pending_event": {"type": "process_reaction_write", "actor": "du"}},
    }
    sync_text = game_tools._captivity_simulator_sync_text(payload, user_message="请处理这个事件。", mode="state_update")
    _assert("囚禁模拟器" in sync_text, "sync text should name the simulator")
    _assert("【过程心情：" in sync_text, "combined process pending should require process-reaction directive")
    _assert("当前待处理事件：" in sync_text and "服从调教" in sync_text and "口令服从" in sync_text and "羞耻调教" in sync_text and "sex" in sync_text and "项圈" in sync_text, "sync text should include readable action, training and tool context")
    _assert("本次说明：" in sync_text, "state update should include caller message")

    night_payload = {
        "text": "【囚禁模拟器】\n待处理：process_reaction_write / 【过程心情：...】",
        "captor_view": {
            "pending_event": {
                "type": "process_reaction_write",
                "actor": "du",
                "event": {"phase": "night", "action": "sleep", "action_label": "老实睡觉"},
            },
            "ending_state": "",
        },
    }
    night_sync = game_tools._captivity_simulator_sync_text(night_payload, mode="state_update")
    _assert("夜间监控介入事件" in night_sync, "night process_reaction should not be described as a daytime action")

    escape_record_payload = {
        "text": "【囚禁模拟器】\n待处理：day_plan_choice / 【今日安排：...】",
        "captor_view": {
            "pending_event": {"type": "day_plan_choice", "actor": "du"},
            "event_log": [
                {
                    "day": 2,
                    "action": "escape_choice",
                    "action_label": "逃跑诱导：试探",
                    "escape": {"choice": "probe", "choice_label": "试探"},
                }
            ],
            "ending_state": "",
        },
    }
    escape_record_sync = game_tools._captivity_simulator_sync_text(escape_record_payload, mode="state_update")
    _assert("近期逃跑诱导记录" in escape_record_sync and "逃跑诱导：试探" in escape_record_sync, "sync text should notify du about recent non-escape lure reactions")

    deferred_monitor_payload = {
        "text": "【囚禁模拟器】\n待处理：day_plan_choice / 【今日安排：...】",
        "captor_view": {
            "current_day": 2,
            "pending_event": {"type": "day_plan_choice", "actor": "du"},
            "deferred_monitor_materials": [
                {
                    "day": 1,
                    "available_from_day": 2,
                    "status": "pending",
                    "action": "diary",
                    "action_label": "写私密日记",
                    "line": "写了一点东西",
                    "monitor_style": "full",
                    "monitor_note": "明天处理",
                }
            ],
            "ending_state": "",
        },
    }
    deferred_monitor_sync = game_tools._captivity_simulator_sync_text(deferred_monitor_payload, mode="state_update")
    _assert("可回看的监控记录" in deferred_monitor_sync, "deferred monitor context should be shown as monitor records")
    _assert("第 1 天夜间；记录摘要：写私密日记：写了一点东西" in deferred_monitor_sync, "monitor record should show time and summary")
    _assert("status" not in deferred_monitor_sync and "available_from_day" not in deferred_monitor_sync and "查看方式" not in deferred_monitor_sync and "明天处理" not in deferred_monitor_sync, "monitor record should not expose handling state or internal scheduling")

    commands = game_tools._captivity_simulator_commands_from_reply("【过程心情：response=accept mood=害羞 process=写完过程】\n后面普通聊天", payload)
    _assert(commands == ["submit_process_reaction response=accept mood=害羞 process=写完过程"], f"combined directive should map to submit_process_reaction, got {commands}")

    plan_payload = {"captor_view": {"pending_event": {"type": "day_plan_choice", "actor": "du"}}}
    commands = game_tools._captivity_simulator_commands_from_reply("【今日安排：action=feeding || action=cleaning || action=training training_contents=obedience_commands】", plan_payload)
    _assert(commands == ["plan_day action=feeding || action=cleaning || action=training training_contents=obedience_commands"], f"plan directive should map to plan_day, got {commands}")

    response_payload = {"captor_view": {"pending_event": {"type": "action_response", "actor": "du"}}}
    commands = game_tools._captivity_simulator_commands_from_reply("【反应：response=refuse mood=闹脾气 line=不要】", response_payload)
    _assert(commands == ["respond_action response=refuse mood=闹脾气 line=不要"], f"response directive should map to respond_action, got {commands}")

    reaction_payload = {"captor_view": {"pending_event": {"type": "reaction_choice", "actor": "du"}}}
    commands = game_tools._captivity_simulator_commands_from_reply("【心情：疲惫 写完了】", reaction_payload)
    _assert(commands == ["choose_mood 疲惫 写完了"], f"mood directive should map to choose_mood, got {commands}")

    night_choice_payload = {
        "text": "【囚禁模拟器】\n待处理：night_action_choice / 【夜间行动：...】",
        "captor_view": {
            "pending_event": {
                "type": "night_action_choice",
                "actor": "du",
                "available_actions": ["self_touch"],
                "condition_prompt": "你感觉自己欲火焚身，除了自慰什么也做不了。",
            },
            "ending_state": "",
        },
    }
    night_choice_sync = game_tools._captivity_simulator_sync_text(night_choice_payload, mode="state_update")
    _assert("今晚可选行动：self_touch" in night_choice_sync, "du should receive only backend-allowed night actions")
    _assert("你感觉自己欲火焚身，除了自慰什么也做不了。" in night_choice_sync, "du should receive the active night condition")
    _assert("这些行动必须补 detail" not in night_choice_sync, "forced self-touch should not receive unrelated detail choices")
    _assert("【夜间行动：action=self_touch line=可选台词】" in night_choice_sync, "du directive example should use an actually allowed action")

    interactive_night_payload = {
        "text": "【囚禁模拟器】\n待处理：night_action_choice / 【夜间行动：...】",
        "captor_view": {
            "pending_event": {
                "type": "night_action_choice",
                "actor": "du",
                "available_actions": ["read", "hide_item"],
                "detail_options": {
                    "read": {"follow_bookmark": "沿着书签继续读", "inspect_margins": "找页边批注"},
                    "hide_item": {"inventory_book": "藏起书"},
                },
            },
            "ending_state": "",
        },
    }
    interactive_night_sync = game_tools._captivity_simulator_sync_text(interactive_night_payload, mode="state_update")
    _assert("read=follow_bookmark(沿着书签继续读)/inspect_margins(找页边批注)" in interactive_night_sync, "du should receive readable book interaction ids")
    _assert("hide_item=inventory_book(藏起书)" in interactive_night_sync and "检查钥匙" not in interactive_night_sync, "du should only receive hide choices backed by actual inventory")
    commands = game_tools._captivity_simulator_commands_from_reply("【夜间行动：action=diary detail=record_day note=写一点】", night_choice_payload)
    _assert(commands == ["night_action action=diary detail=record_day note=写一点"], f"night action directive should preserve detail and diary body, got {commands}")

    monitor_gate_payload = {"captor_view": {"pending_event": {"type": "monitor_gate", "actor": "du"}}}
    gate_sync = game_tools._captivity_simulator_sync_text(
        {
            "text": "【囚禁模拟器】\n待处理：monitor_gate / 【选择：none】 或 【查看监控：full】",
            "captor_view": {"pending_event": {"type": "monitor_gate", "actor": "du"}, "ending_state": ""},
        },
        mode="state_update",
    )
    _assert("还没有打开监控" in gate_sync and "夜间行动内容" in gate_sync, "monitor gate sync should not expose sealed monitor content")
    bell_gate_sync = game_tools._captivity_simulator_sync_text(
        {
            "text": "【囚禁模拟器】\n待处理：monitor_gate / 【选择：none】 或 【查看监控：full】",
            "captor_view": {
                "pending_event": {"type": "monitor_gate", "actor": "du", "alert_label": "呼叫铃响了"},
                "ending_state": "",
            },
        },
        mode="state_update",
    )
    _assert("呼叫铃响了" in bell_gate_sync and "具体夜间动向仍需打开监控" in bell_gate_sync, "du captor should receive the bell alert without unsealing the event")
    commands = game_tools._captivity_simulator_commands_from_reply("【查看监控：full】", monitor_gate_payload)
    _assert(commands == ["view_monitor full"], f"monitor gate tool directive should map to view_monitor, got {commands}")
    commands = game_tools._captivity_simulator_commands_from_reply("【选择：none】", monitor_gate_payload)
    _assert(commands == ["monitor_action none"], f"monitor gate none should map to monitor_action none, got {commands}")

    monitor_handle_payload = {"captor_view": {"pending_event": {"type": "monitor_handle", "actor": "du"}}}
    commands = game_tools._captivity_simulator_commands_from_reply("【选择：review_later】", monitor_handle_payload)
    _assert(commands == ["monitor_action review_later"], f"monitor handle should map to monitor_action, got {commands}")

    escape_payload = {"captor_view": {"pending_event": {"type": "escape_choice", "actor": "du"}}}
    commands = game_tools._captivity_simulator_commands_from_reply("【选择：escape】", escape_payload)
    _assert(commands == ["resolve_escape_choice escape"], f"escape choice should map to resolve_escape_choice, got {commands}")
    commands = game_tools._captivity_simulator_commands_from_reply("【选择：试探】", escape_payload)
    _assert(commands == ["resolve_escape_choice 试探"], f"probe choice should map to resolve_escape_choice, got {commands}")

    ending_payload = {
        "captor_view": {
            "route": "captured_by_du",
            "pending_event": None,
            "ending_state": "ending_ready_to_notify",
            "ending_title": "无期",
            "ending_text": "给小玥看的固定结局正文。",
            "game_over": True,
        }
    }
    commands = game_tools._captivity_simulator_commands_from_reply("【结局：结局正文】", ending_payload)
    _assert(commands == [], f"Du should no longer submit or rewrite fixed endings, got {commands}")
    sync_ending = game_tools._captivity_simulator_sync_text({"text": "【囚禁模拟器】\n结局阶段", **ending_payload}, mode="state_update")
    _assert("你在上一局是囚禁方，她是被囚禁方" in sync_ending, "ending sync should tell Du his actual previous role")
    _assert("达成结局「无期」" in sync_ending and "不要续写、改名或继续推进上一局" in sync_ending, "ending sync should be a final result notice instead of a writing request")
    _assert("给小玥看的固定结局正文" not in sync_ending, "Du should receive a separately authored summary, not the frontend body")

    material_payload = {"captor_view": {"pending_event": None, "ending_state": "ending_materials_pending"}}
    commands = game_tools._captivity_simulator_commands_from_reply("【结局素材条：第一条\n第二条】", material_payload)
    _assert(commands == [], f"runtime ending material directives should be retired, got {commands}")

    new_game_payload = {
        "text": "【囚禁模拟器】\n第 1 / 30 天",
        "captor_view": {
            "route": "capture_du",
            "current_day": 1,
            "day_action_count": 0,
            "pending_event": None,
            "ending_state": "",
            "previous_ending": {"title": "无期", "route": "captured_by_du", "notified_at": "2026-07-10T00:00:00+08:00"},
        },
    }
    new_game_sync = game_tools._captivity_simulator_sync_text(new_game_payload, mode="state_update")
    _assert("上一局已经以结局「无期」结束，你当时是囚禁方" in new_game_sync, "first new-game sync should carry the previous ending")
    _assert("当前是全新一局" in new_game_sync, "new game context should explicitly stop previous actions from leaking forward")

    commands = game_tools._captivity_simulator_commands_from_reply("我只是聊一句。", payload)
    _assert(commands == [], "ordinary chat should not produce commands")


def test_captivity_simulator_reply_commands_apply_to_runtime() -> None:
    from routes.miniapp import game_tools

    calls: list[tuple[str, str, str]] = []
    old_execute = game_tools.execute_game_command

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        calls.append((game_id, command, save_id))
        return {
            "ok": True,
            "state": {"pending_event": None},
            "captor_view": {"pending_event": None},
            "player_text": "过程和心情已保存。",
        }

    try:
        game_tools.execute_game_command = fake_execute
        applied, payload = game_tools._apply_captivity_simulator_reply_commands(
            "default",
            "【过程心情：response=accept mood=害羞 process=测试过程】\n【结局：不应该连吃】",
            {"captor_view": {"pending_event": {"type": "process_reaction_write", "actor": "du"}}},
        )
    finally:
        game_tools.execute_game_command = old_execute

    _assert(calls == [("captivity_simulator", "submit_process_reaction response=accept mood=害羞 process=测试过程", "default")], f"unexpected calls: {calls}")
    _assert(applied and applied[0]["ok"] is True, "applied command should be reported")
    _assert((payload or {}).get("player_text") == "过程和心情已保存。", "payload should be returned")

    calls.clear()
    gift_payload = {
        "captor_view": {
            "captor": "du",
            "pending_event": {"type": "process_write", "actor": "du"},
        }
    }
    try:
        game_tools.execute_game_command = fake_execute
        applied, _ = game_tools._apply_captivity_simulator_reply_commands(
            "default",
            "【赠送物品：book】\n【过程：继续当前过程】",
            gift_payload,
        )
    finally:
        game_tools.execute_game_command = old_execute

    _assert(
        calls == [
            ("captivity_simulator", "gift_item items=book", "default"),
            ("captivity_simulator", "submit_process 继续当前过程", "default"),
        ],
        f"gift plus pending directive should execute sequentially: {calls}",
    )
    _assert(len(applied) == 2 and all(item["ok"] for item in applied), "both independent gift and current pending command should be reported")


def test_captivity_simulator_public_api_returns_only_local_view() -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import game_tools

    app = Flask(__name__)
    bp = Blueprint("captivity_view_filter_test", __name__, url_prefix="/miniapp-api")
    game_tools.register_routes(bp)
    app.register_blueprint(bp)
    scenario = {"route": "captured_by_du"}
    calls: list[str] = []
    old_execute = game_tools.execute_game_command

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        calls.append(command)
        route = scenario["route"]
        return {
            "ok": True,
            "game_id": "captivity_simulator",
            "command": "status",
            "commands": ["internal-command"],
            "text": "safe\n待处理：internal / secret-directive",
            "state": {"route": route, "viewer": "captive", "pending_event": {"type": "action_response", "required_directive": "secret-directive"}, "event_log": [{"line": "captive-secret"}]},
            "captive_view": {"route": route, "viewer": "captive", "pending_event": {"type": "action_response", "required_directive": "secret-directive"}, "event_log": [{"line": "captive-secret"}]},
            "captor_view": {"route": route, "viewer": "captor", "pending_event": {"type": "advance_action", "required_directive": "secret-directive"}, "event_log": [{"line": "captor-secret"}], "escape_windows": [{"bait": "hidden-key"}]},
            "export_log": [{"line": "captor-secret"}],
            "ending_seed_full": {"hidden": "captor-only"},
            "wakeup": {"reply_preview": "secret-directive"},
            "applied_reply_commands": [{"command": "secret-directive"}],
        }

    try:
        game_tools.execute_game_command = fake_execute
        with app.test_client() as client:
            captured = client.post(
                "/miniapp-api/game-tools/captivity_simulator",
                json={"save_id": "default", "command": "status"},
            ).get_json()
            _assert(calls == ["status"], f"status/open should load the save exactly once: {calls}")
            captured_text = json.dumps(captured, ensure_ascii=False)
            _assert("captor_view" not in captured and "captor-secret" not in captured_text and "hidden-key" not in captured_text, "local captive API must not return captor-only data")
            _assert(captured["state"]["viewer"] == "captive" and captured["export_log"][0]["line"] == "captive-secret", "local captive should receive only the captive projection")
            _assert("ending_seed_full" not in captured, "local captive export should not expose full ending materials")
            _assert("command" not in captured and "commands" not in captured and "wakeup" not in captured and "applied_reply_commands" not in captured, "public payload should remove internal protocol fields")
            _assert("required_directive" not in captured["state"]["pending_event"] and "secret-directive" not in captured.get("text", ""), "public pending should remove raw directives")

            calls.clear()
            blocked_config = client.post(
                "/miniapp-api/game-tools/captivity_simulator",
                json={"save_id": "default", "command": "set_config book=true"},
            )
            _assert(blocked_config.status_code == 403, "local captive must not be able to call captor inventory commands")
            _assert(calls == ["status"], f"unauthorized command must be rejected before mutation: {calls}")

            scenario["route"] = "capture_du"
            captor = client.post(
                "/miniapp-api/game-tools/captivity_simulator",
                json={"save_id": "default", "command": "status"},
            ).get_json()
            captor_text = json.dumps(captor, ensure_ascii=False)
            _assert("captive_view" not in captor and "captive-secret" not in captor_text, "local captor API must not return the captive projection as a second bypass view")
            _assert(captor["state"]["viewer"] == "captor" and captor["captor_view"]["viewer"] == "captor", "local captor should receive only the captor projection")

            calls.clear()
            blocked_night = client.post(
                "/miniapp-api/game-tools/captivity_simulator",
                json={"save_id": "default", "command": "night_action sleep"},
            )
            _assert(blocked_night.status_code == 403 and calls == ["status"], "local captor must not submit the captive's night action")
    finally:
        game_tools.execute_game_command = old_execute


def test_captivity_simulator_sync_activity_policy() -> None:
    from routes.miniapp import game_tools
    from storage import r2_store

    _assert(game_tools._sync_message_counts_as_user_activity("chat", "小玥说了一句") is True, "explicit in-game chat should count as user activity")
    _assert(game_tools._sync_message_counts_as_user_activity("state_update", "自动同步") is False, "state sync should not count as user activity")
    _assert(game_tools._sync_message_counts_as_user_activity("chat", "") is False, "empty chat should not count as user activity")
    _assert(game_tools._captivity_simulator_sync_counts_as_user_activity("chat", "小玥说了一句") is True, "captivity chat should count as user activity")
    _assert(game_tools._captivity_simulator_sync_counts_as_user_activity("chat", "") is False, "empty captivity chat should not count as user activity")
    _assert(game_tools._captivity_simulator_sync_counts_as_user_activity("state_update", "") is True, "successful captivity state sync should count as user activity")
    _assert(game_tools._captivity_simulator_sync_counts_as_user_activity("ending", "") is True, "successful captivity ending sync should count as user activity")
    _assert(
        "captivity_simulator_user_interaction" in r2_store.LAST_USER_ACTIVITY_ALLOWED_SOURCES,
        "captivity sync activity source must be accepted by the global interaction clock",
    )


def test_captivity_simulator_wakeup_uses_dynamic_system_and_skips_body_delta() -> None:
    from services import conversation_followup as cf
    from storage import upstream_store

    captured: dict = {}

    class FakeResponse:
        status_code = 200
        content = b'{"choices":[{"message":{"content":"ok"}}]}'
        text = content.decode("utf-8")

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "ok"}}]}

    old_model = upstream_store.get_cached_active_model
    old_post = cf.requests.post
    old_preference = cf._choice_dialog_delivery_preference
    try:
        upstream_store.get_cached_active_model = lambda refresh_if_missing=False: "test-model"
        cf._choice_dialog_delivery_preference = lambda target: ("tg", str(target or ""), {})
        cf.requests.post = lambda url, headers=None, json=None, timeout=None: captured.update(
            {"url": url, "headers": headers, "json": json}
        ) or FakeResponse()

        result = cf.send_captivity_simulator_wakeup(
            window_id="tg_123",
            target="123",
            event_text="小玥正在和你玩「囚禁模拟器」。当前等待过程。",
            preferred_channel="tg",
            return_only=True,
        )

        _assert(bool(result.get("ok")), f"captivity simulator wakeup should succeed: {result}")
        headers = captured.get("headers") or {}
        _assert(headers.get("X-DU-WAKEUP-KIND") == "captivity_simulator", "wakeup kind should be captivity_simulator")
        _assert(headers.get("X-Skip-Post-Archive-Body-Delta") == "1", "body delta should be skipped")
        messages = ((captured.get("json") or {}).get("messages") or [])
        simulator_system = next((msg for msg in messages if "囚禁模拟器" in str(msg.get("content") or "")), None)
        _assert(isinstance(simulator_system, dict), "simulator event should stay in a system message")
        _assert(simulator_system.get("__dynamic__") is True, "simulator event must be dynamic system")
    finally:
        upstream_store.get_cached_active_model = old_model
        cf.requests.post = old_post
        cf._choice_dialog_delivery_preference = old_preference


def test_captivity_simulator_archive_compaction() -> None:
    from flask import Flask
    from routes import chat

    app = Flask(__name__)
    request_messages = [
        {
            "role": "system",
            "content": "小玥正在和你玩「囚禁模拟器」。\n\n当前游戏状态：\n【囚禁模拟器】\n进度：第 12 / 30 天，day，白天行动 2 / 3\n待处理：process_reaction_write / 【过程心情：...】",
            "__dynamic__": True,
        },
        {"role": "user", "content": "请根据上面的囚禁模拟器游戏内交流回应小玥。"},
    ]
    assistant = {
        "role": "assistant",
        "content": "【过程心情：response=accept mood=害羞 process=这里是很长的过程正文，不应该进入归档】\n自然回复一句。",
        "reasoning_content": "这里也可能含有很长的过程正文，不能进入归档。",
        "thinking_blocks": [{"text": "这里是很长的过程正文，不应该进 thinking_blocks 归档"}],
        "reasoning_omitted": True,
    }
    with app.test_request_context(
        headers={
            "X-DU-GATEWAY-WAKEUP": "1",
            "X-DU-WAKEUP-KIND": "captivity_simulator",
        }
    ):
        cleaned = chat._build_round_cleaned_for_archive(
            {"role": "user", "content": "fallback"},
            assistant,
            reply_target="123",
            window_id="tg_123",
            request_messages=request_messages,
        )
    text = json.dumps(cleaned, ensure_ascii=False)
    archived_assistant = cleaned[1]
    _assert("囚禁模拟器" in text, "archive should retain simulator summary")
    _assert("第 12 天" in text, "archive should retain day summary")
    _assert("很长的过程正文" not in archived_assistant["content"], "archive should strip the full process body from visible assistant content")
    _assert(archived_assistant.get("reasoning_content") == assistant["reasoning_content"], "archive should preserve reasoning_content for simulator replies")
    _assert(archived_assistant.get("thinking_blocks") == assistant["thinking_blocks"], "archive should preserve structured thinking blocks for simulator replies")
    _assert("reasoning_omitted" in text, "archive may keep safe omitted marker")
    _assert("完整行动正文只保留在游戏存档" in text and "思维链按原字段归档" in text, "assistant archive should state both storage boundaries")


def test_captivity_simulator_sync_route_pending_semantics() -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import game_tools
    from services import conversation_followup
    from services import reply_channel_context

    app = Flask(__name__)
    bp = Blueprint("miniapp_test", __name__, url_prefix="/miniapp-api")
    game_tools.register_routes(bp)
    app.register_blueprint(bp)

    calls: list[tuple[str, str, str]] = []
    wakeups: list[dict] = []
    scenario = {"name": "no_reply"}
    base_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n当前状态如下。\n\n进度：第 1 / 30 天，night，白天行动 3 / 3\n待处理：monitor_gate / 【选择：none】 或 【查看监控：full】",
        "player_text": "当前状态如下。",
        "state": {"route": "captured_by_du", "pending_event": {"type": "monitor_gate", "actor": "du"}, "ending_state": ""},
        "captive_view": {"route": "captured_by_du", "pending_event": {"type": "monitor_gate", "actor": "du"}, "ending_state": ""},
        "captor_view": {"route": "captured_by_du", "pending_event": {"type": "monitor_gate", "actor": "du"}, "ending_state": ""},
    }
    applied_payload = {
        **base_payload,
        "text": "【囚禁模拟器】\n当前状态如下。\n\n进度：第 1 / 30 天，night，白天行动 3 / 3\n待处理：monitor_handle / 【选择：silent|review_later|intervene】",
        "player_text": "监控已打开（full），等待囚禁方选择处理方式。",
        "state": {"route": "captured_by_du", "pending_event": {"type": "monitor_handle", "actor": "du"}, "ending_state": ""},
        "captive_view": {"route": "captured_by_du", "pending_event": {"type": "monitor_handle", "actor": "du"}, "ending_state": ""},
        "captor_view": {"route": "captured_by_du", "pending_event": {"type": "monitor_handle", "actor": "du"}, "ending_state": ""},
    }

    old_execute = game_tools.execute_game_command
    old_wakeup = conversation_followup.send_captivity_simulator_wakeup
    old_context = reply_channel_context.resolve_recent_reply_context
    old_activity_marker = game_tools._mark_captivity_simulator_sync_activity
    activity_marks: list[tuple[str, dict]] = []

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        calls.append((game_id, command, save_id))
        if command == "status":
            return base_payload
        if command == "view_monitor full":
            return applied_payload
        raise AssertionError(f"unexpected command: {command}")

    def fake_context(default_target: str = "") -> dict:
        return {"channel": "sumitalk", "window_id": "sumitalk_test", "target": default_target or "device", "meta": {}}

    def fake_wakeup(**kwargs) -> dict:
        wakeups.append(dict(kwargs))
        if scenario["name"] == "no_reply":
            return {"ok": False, "error": "gateway_http_502"}
        if scenario["name"] == "no_directive":
            return {"ok": True, "reply_text": "只是普通聊天一句。", "reply_preview": "只是普通聊天一句。"}
        if scenario["name"] == "applied_with_warning":
            if len(wakeups) == 1:
                return {"ok": True, "reply_text": "【查看监控：full】\n普通回复。", "reply_preview": "【查看监控：full】"}
            return {"ok": False, "error": "followup_failed"}
        raise AssertionError(f"unknown scenario: {scenario['name']}")

    try:
        game_tools.execute_game_command = fake_execute
        conversation_followup.send_captivity_simulator_wakeup = fake_wakeup
        reply_channel_context.resolve_recent_reply_context = fake_context
        game_tools._mark_captivity_simulator_sync_activity = lambda synced_at, detail=None: activity_marks.append(
            (str(synced_at), dict(detail or {}))
        )

        with app.test_client() as client:
            response = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default"})
            data = response.get_json()
            _assert(response.status_code == 502, f"no_reply should be 502, got {response.status_code}: {data}")
            _assert(data["sync_result"] == "no_reply", "failed wakeup should be no_reply")
            _assert("applied_reply_commands" not in data and "wakeup" not in data, "public no_reply payload should not expose internal sync protocol")
            _assert(calls == [("captivity_simulator", "status", "default")], f"unexpected calls after no_reply: {calls}")

            calls.clear()
            wakeups.clear()
            scenario["name"] = "no_directive"
            response = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default"})
            data = response.get_json()
            _assert(response.status_code == 200, f"no_directive should be 200, got {response.status_code}: {data}")
            _assert(data["ok"] is True and data["sync_result"] == "no_directive", "plain chat should not advance pending")
            _assert("applied_reply_commands" not in data and "wakeup" not in data, "public no_directive payload should not expose internal sync protocol")
            _assert(data["state"]["pending_event"]["type"] == "monitor_gate", "pending should stay untouched")
            _assert("captor_view" not in data, "captured-by-du sync response should not expose captor view to the local captive")
            _assert(len(activity_marks) == 1 and activity_marks[0][1]["mode"] == "state_update", f"successful gameplay sync should mark user activity once: {activity_marks}")

            response = client.post(
                "/miniapp-api/game-tools/captivity_simulator/sync-du",
                json={"save_id": "default", "mode": "state_update", "message": "自动同步说明"},
            )
            data = response.get_json()
            _assert(response.status_code == 200, f"state_update message sync should succeed, got {response.status_code}: {data}")
            _assert(len(activity_marks) == 2 and activity_marks[-1][1]["mode"] == "state_update", f"each successful gameplay sync should mark user activity once: {activity_marks}")

            response = client.post(
                "/miniapp-api/game-tools/captivity_simulator/sync-du",
                json={"save_id": "default", "mode": "chat", "message": "小玥局内说了一句"},
            )
            data = response.get_json()
            _assert(response.status_code == 200, f"chat message sync should succeed, got {response.status_code}: {data}")
            _assert(len(activity_marks) == 3, f"chat sync should add exactly one activity mark: {activity_marks}")
            _assert(
                activity_marks[-1][1]
                == {
                    "game_id": "captivity_simulator",
                    "save_id": "default",
                    "window_id": "sumitalk_test",
                    "target": "device",
                    "mode": "chat",
                    "phase": "user_message",
                },
                f"chat activity detail should retain the route context: {activity_marks}",
            )

            calls.clear()
            wakeups.clear()
            activity_marks.clear()
            scenario["name"] = "applied_with_warning"
            response = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default"})
            data = response.get_json()
            _assert(response.status_code == 200, f"applied_with_warning should keep applied state, got {response.status_code}: {data}")
            _assert(data["ok"] is False and data["sync_result"] == "applied_with_warning", "followup failure should be a partial success warning")
            _assert(("captivity_simulator", "view_monitor full", "default") in calls, "first directive should apply exactly once internally")
            _assert("applied_reply_commands" not in data and "followup_wakeups" not in data, "public warning payload should hide internal commands and wakeups")
            _assert(data["state"]["pending_event"]["type"] == "monitor_handle", "applied state should be returned, not rolled back")
            _assert(len(wakeups) == 2, "applied followup should attempt one continuation")
            _assert(len(activity_marks) == 1 and activity_marks[0][1]["mode"] == "state_update", f"an applied sync with a failed followup should still mark the originating user interaction once: {activity_marks}")
    finally:
        game_tools.execute_game_command = old_execute
        conversation_followup.send_captivity_simulator_wakeup = old_wakeup
        reply_channel_context.resolve_recent_reply_context = old_context
        game_tools._mark_captivity_simulator_sync_activity = old_activity_marker


def test_captivity_simulator_sync_day_plan_uses_one_du_reply() -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import game_tools
    from services import conversation_followup
    from services import reply_channel_context

    app = Flask(__name__)
    bp = Blueprint("miniapp_day_plan_single_reply_test", __name__, url_prefix="/miniapp-api")
    game_tools.register_routes(bp)
    app.register_blueprint(bp)

    base_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n待处理：day_plan_choice / 【今日安排：...】",
        "player_text": "等待渡安排今天的三个行动。",
        "state": {"route": "captured_by_du", "pending_event": {"type": "day_plan_choice", "actor": "du"}, "ending_state": ""},
        "captive_view": {"route": "captured_by_du", "pending_event": {"type": "day_plan_choice", "actor": "du"}, "ending_state": ""},
        "captor_view": {"route": "captured_by_du", "pending_event": {"type": "day_plan_choice", "actor": "du"}, "ending_state": ""},
    }
    planned_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n今天的三个行动已经排好。",
        "player_text": "今天的三个行动已经排好。",
        "state": {"route": "captured_by_du", "pending_event": {"type": "action_response", "actor": "xinyue"}, "ending_state": ""},
        "captive_view": {"route": "captured_by_du", "pending_event": {"type": "action_response", "actor": "xinyue"}, "ending_state": ""},
        "captor_view": {"route": "captured_by_du", "pending_event": {"type": "action_response", "actor": "xinyue"}, "ending_state": ""},
    }
    expected_plan = "plan_day action=feeding || action=cleaning || action=rest contents=quiet_time"
    calls: list[str] = []
    wakeup_count = {"value": 0}
    old_execute = game_tools.execute_game_command
    old_wakeup = conversation_followup.send_captivity_simulator_wakeup
    old_context = reply_channel_context.resolve_recent_reply_context
    old_activity_marker = game_tools._mark_captivity_simulator_sync_activity

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        calls.append(command)
        if command == "status":
            return base_payload
        if command == expected_plan:
            return planned_payload
        raise AssertionError(f"unexpected command: {command}")

    def fake_wakeup(**kwargs) -> dict:
        wakeup_count["value"] += 1
        reply = "【今日安排：action=feeding || action=cleaning || action=rest contents=quiet_time】"
        return {"ok": True, "reply_text": reply, "reply_preview": reply}

    try:
        game_tools.execute_game_command = fake_execute
        conversation_followup.send_captivity_simulator_wakeup = fake_wakeup
        reply_channel_context.resolve_recent_reply_context = lambda default_target="": {
            "channel": "sumitalk", "window_id": "sumitalk_test", "target": default_target or "device", "meta": {},
        }
        game_tools._mark_captivity_simulator_sync_activity = lambda *args, **kwargs: None
        with app.test_client() as client:
            response = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default"})
            data = response.get_json()
            _assert(response.status_code == 200 and data["ok"] is True, f"day plan sync should succeed: {data}")
            _assert(wakeup_count["value"] == 1, "one day-plan sync must ask du exactly once for all three actions")
            _assert(calls == ["status", expected_plan], f"all three actions should be applied in one plan command: {calls}")
            _assert(data["state"]["pending_event"]["type"] == "action_response", "the first action should be shown locally after the single plan reply")
    finally:
        game_tools.execute_game_command = old_execute
        conversation_followup.send_captivity_simulator_wakeup = old_wakeup
        reply_channel_context.resolve_recent_reply_context = old_context
        game_tools._mark_captivity_simulator_sync_activity = old_activity_marker


def test_captivity_simulator_sync_route_redacts_du_night_action() -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import game_tools
    from services import conversation_followup
    from services import reply_channel_context

    app = Flask(__name__)
    bp = Blueprint("miniapp_redact_test", __name__, url_prefix="/miniapp-api")
    game_tools.register_routes(bp)
    app.register_blueprint(bp)

    base_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n待处理：night_action_choice / 【夜间行动：...】",
        "player_text": "当前状态如下。",
        "state": {"route": "capture_du", "pending_event": {"type": "night_action_choice", "actor": "du"}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "night_action_choice", "actor": "du"}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "pending_event": {"type": "night_action_choice", "actor": "du"}, "ending_state": ""},
    }
    applied_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n夜间行动已封存：写私密日记。\n待处理：monitor_gate / 【选择：none】 或 【查看监控：full】",
        "player_text": "夜间行动已封存：写私密日记。",
        "state": {"route": "capture_du", "pending_event": {"type": "monitor_gate", "actor": "xinyue"}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "monitor_gate", "actor": "xinyue"}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "pending_event": {"type": "monitor_gate", "actor": "xinyue", "sealed": True}, "ending_state": ""},
    }

    old_execute = game_tools.execute_game_command
    old_wakeup = conversation_followup.send_captivity_simulator_wakeup
    old_context = reply_channel_context.resolve_recent_reply_context
    old_activity_marker = game_tools._mark_captivity_simulator_sync_activity

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        if command == "status":
            return base_payload
        if command == "night_action action=diary line=秘密日记内容":
            return applied_payload
        raise AssertionError(f"unexpected command: {command}")

    def fake_context(default_target: str = "") -> dict:
        return {"channel": "sumitalk", "window_id": "sumitalk_test", "target": default_target or "device", "meta": {}}

    def fake_wakeup(**kwargs) -> dict:
        return {
            "ok": True,
            "reply_text": "【夜间行动：action=diary line=秘密日记内容】\n我去写点东西。",
            "reply_preview": "【夜间行动：action=diary line=秘密日记内容】",
            "channel": "sumitalk",
        }

    try:
        game_tools.execute_game_command = fake_execute
        conversation_followup.send_captivity_simulator_wakeup = fake_wakeup
        reply_channel_context.resolve_recent_reply_context = fake_context
        game_tools._mark_captivity_simulator_sync_activity = lambda *args, **kwargs: None
        with app.test_client() as client:
            response = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default"})
            data = response.get_json()
            text = json.dumps(data, ensure_ascii=False)
            _assert(response.status_code == 200, f"redacted night action sync should succeed: {data}")
            _assert("秘密日记内容" not in text and "diary" not in text, "sync response should not leak du night action before monitor view")
            _assert("captive_view" not in data, "capture-du sync response should not expose the captive view to the local captor")
            _assert("applied_reply_commands" not in data and "wakeup" not in data, "public sealed response should hide internal command and wakeup structures")
    finally:
        game_tools.execute_game_command = old_execute
        conversation_followup.send_captivity_simulator_wakeup = old_wakeup
        reply_channel_context.resolve_recent_reply_context = old_context
        game_tools._mark_captivity_simulator_sync_activity = old_activity_marker


def test_captivity_simulator_ending_sync_notifies_once() -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import game_tools
    from services import conversation_followup
    from services import reply_channel_context

    app = Flask(__name__)
    bp = Blueprint("miniapp_ending_notice_test", __name__, url_prefix="/miniapp-api")
    game_tools.register_routes(bp)
    app.register_blueprint(bp)

    ready_view = {
        "route": "captured_by_du",
        "current_day": 30,
        "phase": "ending",
        "pending_event": None,
        "ending_state": "ending_ready_to_notify",
        "ending_title": "无期",
        "ending_text": "给小玥看的固定结局正文。",
        "ending_notified_at": "",
        "game_over": True,
    }
    archived_view = {**ready_view, "ending_state": "ending_archived", "ending_notified_at": "2026-07-10T12:00:00+08:00"}
    current_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n结局：无期",
        "player_text": "结局：无期",
        "state": dict(ready_view),
        "captive_view": dict(ready_view),
        "captor_view": dict(ready_view),
        "game_over": True,
    }
    wakeup_events: list[str] = []
    old_execute = game_tools.execute_game_command
    old_wakeup = conversation_followup.send_captivity_simulator_wakeup
    old_context = reply_channel_context.resolve_recent_reply_context

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        nonlocal current_payload
        if command == "status":
            return current_payload
        if command == "mark_ending_notified":
            current_payload = {
                **current_payload,
                "state": dict(archived_view),
                "captive_view": dict(archived_view),
                "captor_view": dict(archived_view),
                "player_text": "结局已同步给渡并完成归档。",
            }
            return current_payload
        raise AssertionError(f"unexpected command: {command}")

    def fake_wakeup(**kwargs) -> dict:
        wakeup_events.append(str(kwargs.get("event_text") or ""))
        return {"ok": True, "reply_text": "我记住了。", "reply_preview": "我记住了。", "channel": "sumitalk"}

    try:
        game_tools.execute_game_command = fake_execute
        conversation_followup.send_captivity_simulator_wakeup = fake_wakeup
        reply_channel_context.resolve_recent_reply_context = lambda default_target="": {
            "channel": "sumitalk", "window_id": "ending_test", "target": default_target or "device", "meta": {},
        }
        with app.test_client() as client:
            first = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default", "mode": "ending"})
            first_data = first.get_json()
            _assert(first.status_code == 200 and first_data["sync_result"] == "ending_notified", f"ending notice should close successfully: {first_data}")
            first_view = first_data.get("captive_view") or first_data.get("state") or {}
            _assert(first_view["ending_notified_at"], "successful ending notice should return its timestamp")
            _assert(len(wakeup_events) == 1, "first ending sync should wake Du exactly once")
            _assert("你在上一局是囚禁方，她是被囚禁方" in wakeup_events[0], "Du should receive his previous identity")
            _assert("给小玥看的固定结局正文" not in wakeup_events[0], "Du should not receive the frontend-perspective body")

            second = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default", "mode": "ending"})
            second_data = second.get_json()
            _assert(second.status_code == 200 and second_data["sync_result"] == "ending_already_notified", f"repeat ending sync should be idempotent: {second_data}")
            _assert(len(wakeup_events) == 1, "repeat ending sync must not wake Du again")
    finally:
        game_tools.execute_game_command = old_execute
        conversation_followup.send_captivity_simulator_wakeup = old_wakeup
        reply_channel_context.resolve_recent_reply_context = old_context


def test_captivity_simulator_sync_route_voice_bell_followup() -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import game_tools
    from services import conversation_followup
    from services import reply_channel_context

    app = Flask(__name__)
    bp = Blueprint("miniapp_voice_bell_followup_test", __name__, url_prefix="/miniapp-api")
    game_tools.register_routes(bp)
    app.register_blueprint(bp)

    base_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n等待渡选择夜间行动。",
        "player_text": "等待渡选择夜间行动。",
        "state": {"route": "capture_du", "pending_event": {"type": "night_action_choice", "actor": "du", "available_actions": ["ring_bell"]}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "night_action_choice", "actor": "du", "available_actions": ["ring_bell"]}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "captor": "xinyue", "pending_event": {"type": "night_action_choice", "actor": "du", "available_actions": ["ring_bell"]}, "ending_state": ""},
    }
    reveal_event = {
        "id": "voice-bell-event",
        "day": 7,
        "phase": "night",
        "action": "ring_bell",
        "action_label": "按响呼叫铃",
        "bell_voice": {"line": "本地隐藏台词", "first_reveal": True},
    }
    reveal_payload = {
        "ok": True,
        "text": "呼叫铃已按下，监控记录已经生成。预录的声音第一次响了起来。",
        "player_text": "预录的声音第一次响了起来。",
        "state": {"route": "capture_du", "pending_event": {"type": "bell_voice_reveal", "actor": "du", "event": reveal_event}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "bell_voice_reveal", "actor": "du", "event": reveal_event}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "captor": "xinyue", "pending_event": {"type": "bell_voice_reveal", "actor": "du", "event": reveal_event}, "ending_state": ""},
    }
    monitor_payload = {
        "ok": True,
        "text": "首次播放页已结束，等待囚禁方处理这次按铃记录。",
        "player_text": "等待囚禁方处理这次按铃记录。",
        "state": {"route": "capture_du", "pending_event": {"type": "monitor_gate", "actor": "xinyue", "sealed": True, "alert_label": "呼叫铃响了"}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "monitor_gate", "actor": "xinyue", "sealed": True, "alert_label": "呼叫铃响了"}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "captor": "xinyue", "pending_event": {"type": "monitor_gate", "actor": "xinyue", "sealed": True, "alert_label": "呼叫铃响了"}, "ending_state": ""},
    }

    calls: list[str] = []
    wakeup_count = {"value": 0}
    old_execute = game_tools.execute_game_command
    old_wakeup = conversation_followup.send_captivity_simulator_wakeup
    old_context = reply_channel_context.resolve_recent_reply_context
    old_activity_marker = game_tools._mark_captivity_simulator_sync_activity

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        calls.append(command)
        if command == "status":
            return base_payload
        if command == "night_action action=ring_bell":
            return reveal_payload
        if command == "ack_bell_voice":
            return monitor_payload
        raise AssertionError(f"unexpected command: {command}")

    def fake_wakeup(**kwargs) -> dict:
        wakeup_count["value"] += 1
        reply = "【夜间行动：action=ring_bell】" if wakeup_count["value"] == 1 else "【确认铃声】"
        return {"ok": True, "reply_text": reply, "reply_preview": reply, "channel": "sumitalk"}

    try:
        game_tools.execute_game_command = fake_execute
        conversation_followup.send_captivity_simulator_wakeup = fake_wakeup
        reply_channel_context.resolve_recent_reply_context = lambda default_target="": {
            "channel": "sumitalk",
            "window_id": "sumitalk_test",
            "target": default_target or "device",
            "meta": {},
        }
        game_tools._mark_captivity_simulator_sync_activity = lambda *args, **kwargs: None
        with app.test_client() as client:
            response = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default"})
            data = response.get_json()
            public_text = json.dumps(data, ensure_ascii=False)
            _assert(response.status_code == 200 and data["ok"] is True, f"voice bell followup should complete: {data}")
            _assert(calls == ["status", "night_action action=ring_bell", "ack_bell_voice"], f"voice bell should use exactly two du directives: {calls}")
            _assert(wakeup_count["value"] == 2, "voice bell should wake du once to choose the bell and once to hear the first playback")
            _assert(data["state"]["pending_event"]["type"] == "monitor_gate", "voice bell followup should return control to the local captor")
            _assert("本地隐藏台词" not in public_text, "the sealed local-captor response should not expose followup internals")
    finally:
        game_tools.execute_game_command = old_execute
        conversation_followup.send_captivity_simulator_wakeup = old_wakeup
        reply_channel_context.resolve_recent_reply_context = old_context
        game_tools._mark_captivity_simulator_sync_activity = old_activity_marker


def test_captivity_simulator_sync_route_redacts_followup_night_preview() -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import game_tools
    from services import conversation_followup
    from services import reply_channel_context

    app = Flask(__name__)
    bp = Blueprint("miniapp_followup_redact_test", __name__, url_prefix="/miniapp-api")
    game_tools.register_routes(bp)
    app.register_blueprint(bp)

    base_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n待处理：action_response / 【反应：...】",
        "player_text": "当前等待渡回应第三段行动。",
        "state": {"route": "capture_du", "pending_event": {"type": "action_response", "actor": "du"}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "action_response", "actor": "du"}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "pending_event": {"type": "action_response", "actor": "du"}, "ending_state": ""},
    }
    night_choice_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n待处理：night_action_choice / 【夜间行动：...】",
        "player_text": "第三段行动结束，等待渡选择夜间行动。",
        "state": {"route": "capture_du", "pending_event": {"type": "night_action_choice", "actor": "du", "available_actions": ["diary"]}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "night_action_choice", "actor": "du", "available_actions": ["diary"]}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "pending_event": {"type": "night_action_choice", "actor": "du", "available_actions": ["diary"]}, "ending_state": ""},
    }
    sealed_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n夜间行动已封存：写私密日记。",
        "player_text": "夜间行动已封存：写私密日记。",
        "state": {"route": "capture_du", "pending_event": {"type": "monitor_gate", "actor": "xinyue"}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "monitor_gate", "actor": "xinyue"}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "pending_event": {"type": "monitor_gate", "actor": "xinyue", "sealed": True}, "ending_state": ""},
    }

    old_execute = game_tools.execute_game_command
    old_wakeup = conversation_followup.send_captivity_simulator_wakeup
    old_context = reply_channel_context.resolve_recent_reply_context
    old_activity_marker = game_tools._mark_captivity_simulator_sync_activity
    wakeup_count = {"value": 0}

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        if command == "status":
            return base_payload
        if command == "respond_action response=accept mood=平静 line=好了":
            return night_choice_payload
        if command == "night_action action=diary line=秘密续跑":
            return sealed_payload
        raise AssertionError(f"unexpected command: {command}")

    def fake_wakeup(**kwargs) -> dict:
        wakeup_count["value"] += 1
        if wakeup_count["value"] == 1:
            return {"ok": True, "reply_text": "【反应：response=accept mood=平静 line=好了】", "reply_preview": "【反应：...】"}
        return {
            "ok": True,
            "reply_text": "【夜间行动：action=diary line=秘密续跑】",
            "reply_preview": "【夜间行动：action=diary line=秘密续跑】",
        }

    try:
        game_tools.execute_game_command = fake_execute
        conversation_followup.send_captivity_simulator_wakeup = fake_wakeup
        reply_channel_context.resolve_recent_reply_context = lambda default_target="": {
            "channel": "sumitalk",
            "window_id": "sumitalk_test",
            "target": default_target or "device",
            "meta": {},
        }
        game_tools._mark_captivity_simulator_sync_activity = lambda *args, **kwargs: None
        with app.test_client() as client:
            response = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default"})
            data = response.get_json()
            response_text = json.dumps(data, ensure_ascii=False)
            _assert(response.status_code == 200 and data["sync_result"] == "applied_with_warning", f"generic action sync should stop before a second du choice: {data}")
            _assert(data["ok"] is False and data["state"]["pending_event"]["type"] == "night_action_choice", "the next independent du choice should remain pending for an explicit retry")
            _assert(wakeup_count["value"] == 1, "ordinary action resolution must not silently start a second model round")
            _assert("秘密续跑" not in response_text, "a second night choice must not be generated or exposed in the same sync")
            _assert("followup_wakeups" not in data and "wakeup" not in data, "public response should not expose followup wakeup internals")
    finally:
        game_tools.execute_game_command = old_execute
        conversation_followup.send_captivity_simulator_wakeup = old_wakeup
        reply_channel_context.resolve_recent_reply_context = old_context
        game_tools._mark_captivity_simulator_sync_activity = old_activity_marker


def test_captivity_simulator_sync_route_capture_du_returns_to_captor() -> None:
    from flask import Blueprint, Flask
    from routes.miniapp import game_tools
    from services import conversation_followup
    from services import reply_channel_context

    app = Flask(__name__)
    bp = Blueprint("miniapp_capture_du_test", __name__, url_prefix="/miniapp-api")
    game_tools.register_routes(bp)
    app.register_blueprint(bp)

    base_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n待处理：action_response / 【反应：...】",
        "player_text": "当前等待渡反应。",
        "state": {"route": "capture_du", "pending_event": {"type": "action_response", "actor": "du"}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "action_response", "actor": "du"}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "pending_event": {"type": "action_response", "actor": "du"}, "ending_state": ""},
    }
    applied_payload = {
        "ok": True,
        "text": "【囚禁模拟器】\n本次行动已完成，等待囚禁方推进下一行动。",
        "player_text": "本次行动已完成，等待囚禁方推进下一行动。",
        "state": {"route": "capture_du", "pending_event": {"type": "advance_action", "actor": "xinyue"}, "ending_state": ""},
        "captive_view": {"route": "capture_du", "pending_event": {"type": "advance_action", "actor": "xinyue"}, "ending_state": ""},
        "captor_view": {"route": "capture_du", "pending_event": {"type": "advance_action", "actor": "xinyue"}, "ending_state": ""},
    }

    old_execute = game_tools.execute_game_command
    old_wakeup = conversation_followup.send_captivity_simulator_wakeup
    old_context = reply_channel_context.resolve_recent_reply_context
    old_activity_marker = game_tools._mark_captivity_simulator_sync_activity
    wakeups: list[dict] = []
    calls: list[tuple[str, str, str]] = []

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        calls.append((game_id, command, save_id))
        if command == "status":
            return base_payload
        if command == "respond_action response=accept mood=平静 line=知道了":
            return applied_payload
        raise AssertionError(f"unexpected command: {command}")

    def fake_context(default_target: str = "") -> dict:
        return {"channel": "sumitalk", "window_id": "sumitalk_test", "target": default_target or "device", "meta": {}}

    def fake_wakeup(**kwargs) -> dict:
        wakeups.append(dict(kwargs))
        return {"ok": True, "reply_text": "【反应：response=accept mood=平静 line=知道了】", "reply_preview": "【反应：...】"}

    try:
        game_tools.execute_game_command = fake_execute
        conversation_followup.send_captivity_simulator_wakeup = fake_wakeup
        reply_channel_context.resolve_recent_reply_context = fake_context
        game_tools._mark_captivity_simulator_sync_activity = lambda *args, **kwargs: None
        with app.test_client() as client:
            response = client.post("/miniapp-api/game-tools/captivity_simulator/sync-du", json={"save_id": "default"})
            data = response.get_json()
            _assert(response.status_code == 200, f"capture_du sync should succeed: {data}")
            _assert(data["sync_result"] == "applied", "du response should be applied")
            _assert(data["captor_view"]["pending_event"]["type"] == "advance_action", "flow should return to xinyue-captor for manual advance")
            _assert("captive_view" not in data, "capture-du response should expose only the local captor projection")
            _assert("applied_reply_commands" not in data and "wakeup" not in data, "public capture-du response should hide internal directives")
            _assert("【反应：" not in str(data.get("reply_text") or "") and "required_directive" not in json.dumps(data, ensure_ascii=False), "public response text should strip raw directive syntax")
            _assert(any(command.startswith("respond_action") for _, command, _ in calls), "du directive should still map to response command internally")
            _assert(len(wakeups) == 1, "sync should not keep auto-following after state returns to xinyue")
    finally:
        game_tools.execute_game_command = old_execute
        conversation_followup.send_captivity_simulator_wakeup = old_wakeup
        reply_channel_context.resolve_recent_reply_context = old_context
        game_tools._mark_captivity_simulator_sync_activity = old_activity_marker


def test_captivity_simulator_night_detail_branches_and_privacy() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "night-details.json"
        run_command("new_game route=captured_by_du seed=night-details", save_path=save_path)
        run_command("set_config notebook=true", save_path=save_path)
        _finish_simple_day_captured_by_du(save_path)
        missing = run_command("night_action search_exit", save_path=save_path)
        _assert(missing["ok"] is False and "具体动向" in missing["text"], "branching night actions should require a concrete detail")

        diary = run_command(
            "night_action diary detail=write_feelings note=只写在日记里的内容 line=今晚不说话",
            save_path=save_path,
        )
        _assert(diary["ok"] is True and diary["state"]["pending_event"]["type"] == "monitor_gate", "detailed diary action should enter the existing monitor gate")
        _assert("event" not in diary["captor_view"]["pending_event"], "private diary content must stay sealed before monitor view")
        viewed = run_command("view_monitor full", save_path=save_path)
        viewed_event = viewed["captor_view"]["pending_event"]["event"]
        _assert(viewed_event["night_detail"]["id"] == "write_feelings", "opened monitor should reveal the chosen night detail")
        _assert(viewed_event["private_note"] == "只写在日记里的内容", "opened monitor should reveal the private diary body")
        resolved = run_command("monitor_action silent", save_path=save_path)
        _assert(resolved["state"]["event_log"][-1]["private_note"] == "只写在日记里的内容", "private diary body should be archived with the event")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "empty-diary.json"
        run_command("new_game route=captured_by_du seed=empty-diary", save_path=save_path)
        state = _read(save_path)
        state["phase"] = "night"
        state["pending_event"] = None
        state["inventory"]["notebook"] = True
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        empty_diary = run_command("night_action diary detail=record_day", save_path=save_path)
        _assert(empty_diary["ok"] is False and "需要填写这一页的正文" in empty_diary["text"], "diary should require an actual private entry")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "hidden-items.json"
        run_command("new_game route=capture_du seed=hidden-items", save_path=save_path)
        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        no_item_status = run_command("status", save_path=save_path)
        _assert("hide_item" not in no_item_status["state"]["available_night_actions"] and "check_key" not in no_item_status["state"]["available_night_actions"], "unsupported hide/key actions should not appear")
        state["inventory"]["notebook"] = True
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        with_item_status = run_command("status", save_path=save_path)
        _assert(with_item_status["state"]["night_detail_options"]["hide_item"] == {"inventory_notebook": "藏起日记本"}, "hide choices should be generated from actual inventory")
        fabricated = run_command("night_action hide_item detail=snack", save_path=save_path)
        _assert(fabricated["ok"] is False and "inventory_notebook=藏起日记本" in fabricated["text"], "fabricated snacks and small objects must be rejected")
        run_command("night_action hide_item detail=inventory_notebook", save_path=save_path)
        hidden = run_command("monitor_action none", save_path=save_path)
        _assert(len(hidden["state"]["hidden_items"]) == 1, "the captive should retain their hidden item")
        _assert("observed_by_captor" not in hidden["state"]["hidden_items"][0], "captive view must not reveal whether the captor saw the hidden item")
        _assert(hidden["captor_view"]["hidden_items"] == [], "skipped monitoring must not reveal the hidden item to the captor")
        sealed_event = hidden["captor_view"]["event_log"][-1]
        _assert("night_detail" not in sealed_event and "hidden_item" not in sealed_event, "sealed monitor record must hide the concrete branch and item")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "confiscated-hidden-item.json"
        run_command("new_game route=captured_by_du seed=confiscated-hidden-item", save_path=save_path)
        state = _read(save_path)
        state["phase"] = "night"
        state["pending_event"] = None
        state["inventory"]["book"] = True
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        run_command("night_action hide_item detail=inventory_book", save_path=save_path)
        run_command("view_monitor full", save_path=save_path)
        run_command("monitor_action intervene intent=confiscate", save_path=save_path)
        run_command("respond_action accept mood=平静", save_path=save_path)
        run_command("submit_process 没收藏起来的书。", save_path=save_path)
        confiscated = run_command("choose_mood 平静", save_path=save_path)
        _assert(confiscated["captor_view"]["inventory"]["book"] is False, "confiscating a hidden gift should remove it from the room inventory")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "night-progress.json"
        run_command("new_game route=capture_du seed=night-progress", save_path=save_path)
        state = _read(save_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        run_command("night_action search_exit detail=door_lock", save_path=save_path)
        run_command("view_monitor full", save_path=save_path)
        searched = run_command("monitor_action silent", save_path=save_path)
        event = searched["captor_view"]["event_log"][-1]
        _assert(event["night_progress"]["count"] == 1 and event["night_discovery"], "searching should record persistent progress and a concrete discovery")

    for action, detail, item_id in (
        ("read", "inspect_margins", "book"),
        ("game", "continue_save", "switch"),
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / f"interactive-{action}.json"
            run_command(f"new_game route=captured_by_du seed=interactive-{action}", save_path=save_path)
            state = _read(save_path)
            state["phase"] = "night"
            state["pending_event"] = None
            state["inventory"][item_id] = True
            state["inventory_secrets"][item_id]["revealed"] = True
            save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            run_command(f"night_action {action} detail={detail}", save_path=save_path)
            run_command("view_monitor full", save_path=save_path)
            first = run_command("monitor_action silent", save_path=save_path)
            first_event = first["captor_view"]["event_log"][-1]
            _assert(first_event["night_progress"]["count"] == 1 and first_event["night_discovery"], f"{action} should produce a first persistent interaction")
            state = _read(save_path)
            state["phase"] = "night"
            state["pending_event"] = None
            save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            run_command(f"night_action {action} detail={detail}", save_path=save_path)
            run_command("view_monitor full", save_path=save_path)
            second = run_command("monitor_action silent", save_path=save_path)
            second_event = second["captor_view"]["event_log"][-1]
            _assert(second_event["night_progress"]["count"] == 2 and second_event["night_discovery"] != first_event["night_discovery"], f"{action} should reveal new content on repeat use")


def test_captivity_simulator_local_full_30_day_playthrough_both_routes() -> None:
    from services.captivity_simulator_game import ENDING_TEXT_TEMPLATES

    with tempfile.TemporaryDirectory() as tmpdir:
        for route in ("captured_by_du", "capture_du"):
            save_path = Path(tmpdir) / f"full-30-days-{route}.json"
            run_command(f"new_game route={route} seed=full-30-days-{route}", save_path=save_path)
            for day in range(1, 31):
                opened = run_command("status", save_path=save_path)
                _assert(opened["state"]["current_day"] == day and opened["state"]["phase"] == "day", f"{route} should open day {day} in daytime")
                planned = _plan_three(save_path)
                _assert(planned["ok"] is True, f"{route} day {day} should accept a complete three-action plan")
                for slot in range(3):
                    responded = run_command("respond_action accept mood=平静", save_path=save_path)
                    _assert(responded["ok"] is True, f"{route} day {day} slot {slot + 1} should resolve")
                    if route == "capture_du" and slot < 2:
                        _assert(responded["captor_view"]["pending_event"]["type"] == "advance_action", f"{route} day {day} should pause between local-captor slots")
                        advanced = run_command("advance_day_action", save_path=save_path)
                        _assert(advanced["ok"] is True, f"{route} day {day} should advance to slot {slot + 2}")

                night = run_command("night_action sleep", save_path=save_path)
                _assert(night["ok"] is True and night["state"]["pending_event"]["type"] == "monitor_gate", f"{route} day {day} night should reach the monitor gate")
                closed = run_command("monitor_action none", save_path=save_path)
                _assert(closed["ok"] is True, f"{route} day {day} monitor skip should close the night")
                if day < 30:
                    _assert(closed["state"]["current_day"] == day + 1 and closed["state"]["phase"] == "day", f"{route} should advance from day {day} to {day + 1}")
                else:
                    ending = closed["state"]
                    _assert(ending["phase"] == "ending" and ending["ending_state"] == "ending_ready_to_notify", f"{route} should enter a ready ending after day 30")
                    _assert(ending["ending_title"] in ENDING_TEXT_TEMPLATES and ending["ending_text"], f"{route} should select and archive a fixed frontend ending")

            final = run_command("mark_ending_notified", save_path=save_path)
            _assert(final["game_over"] is True and final["state"]["ending_state"] == "ending_archived", f"{route} should archive the ending notification")
            days = {int(event.get("day") or 0) for event in final["state"]["event_log"]}
            _assert(set(range(1, 31)).issubset(days), f"{route} event history should retain all 30 dates")


def test_captivity_simulator_status_thresholds_and_mood_effects() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "status-rules.json"
        run_command("new_game route=capture_du seed=status-rules", save_path=save_path)
        state = _read(save_path)
        state["stats"].update({"health": 25, "stamina": 18, "cleanliness": 12, "shame": 45})
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        status = run_command("status", save_path=save_path)
        flag_ids = {item["id"] for item in status["state"]["status_flags"]}
        _assert({"low_health", "low_stamina", "low_cleanliness", "heightened_shame"}.issubset(flag_ids), "low stats and higher shame should produce lightweight status feedback")
        _assert(status["state"]["intensity_cap"] == "medium", "low health or stamina should cap new plans at medium intensity")

        blocked = run_command(
            "plan_day action=rest intensity=heavy contents=quiet_time || action=reward contents=caress_reward || action=check contents=body_check",
            save_path=save_path,
        )
        _assert(blocked["ok"] is False and "不能安排高强度" in blocked["text"], "high intensity should be unavailable while health or stamina is low")

        planned = run_command(
            "plan_day action=rest intensity=medium contents=quiet_time || action=reward contents=caress_reward || action=check contents=body_check",
            save_path=save_path,
        )
        _assert(planned["ok"] is True, "low cleanliness should prompt cleaning without forcing it into the plan")
        resolved = run_command("respond_action accept mood=黏人", save_path=save_path)
        event = resolved["captor_view"]["event_log"][-1]
        _assert(event["mood_effects"] == {"intimacy": 1}, "selected mood should apply only its small rule-engine correction")
        _assert("mood:黏人" in event["tags"] and event["shame_stage"] == "heightened", "mood and shame feedback should be preserved as event tags")


def test_captivity_simulator_scene_copy_and_transition_contract() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        captive_path = Path(tmpdir) / "captive-scenes.json"
        captive = run_command("new_game route=captured_by_du seed=captive-scenes", save_path=captive_path)
        morning = captive["state"]["scene_copy"]
        _assert(morning["title"] == "早上" and "安排仍不由你决定" in morning["body"], "the captive route should receive its own morning copy")

        state = _read(captive_path)
        state["day_action_count"] = 1
        state["pending_event"] = None
        captive_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        noon = run_command("status", save_path=captive_path)["state"]["scene_copy"]
        _assert(noon["title"] == "中午" and noon["key"] != morning["key"], "advancing the daytime slot should produce a new transition key")

        state = _read(captive_path)
        state["phase"] = "night"
        state["day_action_count"] = 3
        state["pending_event"] = None
        captive_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        night = run_command("status", save_path=captive_path)["state"]["scene_copy"]
        _assert(night["tone"] == "night" and "暂时属于你" in night["body"], "night should use the captive-route night transition copy")

        state = _read(captive_path)
        state["phase"] = "day"
        state["day_action_count"] = 0
        state["stats"]["health"] = 20
        state["pending_event"] = {"type": "escape_choice", "actor": "xinyue", "day": 4, "slot": 0}
        captive_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        special = run_command("status", save_path=captive_path)["state"]["scene_copy"]
        _assert(special["tone"] == "special" and special["title"] == "今天没有平常的安排", "escape day should override ordinary time copy")

        captor_path = Path(tmpdir) / "captor-scenes.json"
        captor = run_command("new_game route=capture_du seed=captor-scenes", save_path=captor_path)
        captor_morning = captor["captor_view"]["scene_copy"]
        _assert("渡还在房间里" in captor_morning["body"] and "由你安排" in captor_morning["body"], "the captor route should receive a distinct control-panel morning copy")

    frontend = (ROOT / "miniapp/src/ui/tabs/CaptivitySimulatorGameTab.tsx").read_text(encoding="utf-8")
    _assert("SceneTransitionOverlay" in frontend and "aria-label=\"跳过过场\"" in frontend, "the frontend should render a skippable short scene transition")
    _assert("StaggeredSceneText" in frontend and "sceneTransitionDuration(scene)" in frontend, "the scene title should reveal character by character and remain visible for the calculated reading time")
    _assert('<span className="scene-transition-body" style={{ animationDelay:' in frontend and "@keyframes captivitySceneBody" in frontend, "the scene title should stagger while the body fades in as one block")
    _assert('content: "GAME START"' in frontend, "the Switch first-discovery screen should display GAME START")
    _assert('>确认夜间行动</button>' in frontend and '.then((next) => continueAutomaticSync(next))' in frontend, "confirming a night action should save locally and continue into the sync flow")
    _assert('>同步</button>' not in frontend and 'disabled={disabled || !canRetry}' in frontend, "the footer should expose retry only for a real failed operation instead of duplicating sync")
    monitor_copy_block = frontend.split("const NIGHT_MONITOR_SCENE_COPY", 1)[1].split("};", 1)[0]
    for action_id in ("sleep", "self_touch", "read", "game", "listen_music", "watch_video", "search_exit", "hide_item", "diary", "blind_spot", "ring_bell", "pet_wait"):
        _assert(f"  {action_id}:" in monitor_copy_block, f"night monitor copy should cover {action_id}")
    _assert(frontend.count("monitorRecordSceneCopy(") >= 4, "live and historical monitor views should render action-specific scene copy")
    _assert("statusAtmosphereCopy" in frontend and "NIGHT_ACTION_SELECTION_COPY" in frontend and "waitAtmosphereCopy" in frontend, "the frontend should add local-only atmosphere around status, night selection, and waiting states")
    _assert("captiveMoodCopy" in frontend and "captorMoodCopy" in frontend, "mood atmosphere should use distinct captive and captor viewpoints")
    _assert("initialLoadStartedRef" in frontend and "ROUTE_STORAGE_KEY" not in frontend, "startup should restore from the backend save exactly once instead of trusting a local route flag")
    _assert('title: silent ? "读取存档失败" : "刷新失败"' in frontend, "a failed initial save read should stop on a retryable error instead of showing a new-game selector")
    _assert("env(safe-area-inset-top" in frontend and "env(safe-area-inset-bottom" in frontend, "the game should reserve phone safe areas")
    _assert("min-height: calc(56px + var(--safe-bottom))" in frontend and "min-height: 44px" in frontend, "the fixed footer should keep a safe bottom inset and touch-sized controls")
    for item_id in ("book", "switch", "notebook", "music_player", "tablet", "night_light", "pillow", "call_bell"):
        _assert(f"item-reveal-{item_id}" in frontend, f"{item_id} should have a distinct first-discovery animation hook")


if __name__ == "__main__":
    test_captivity_simulator_new_game_views()
    test_captivity_simulator_history_is_complete_and_date_filterable()
    test_captivity_simulator_captured_by_du_event_loop()
    test_captivity_simulator_capture_du_manual_advance_loop()
    test_captivity_simulator_night_monitor_view_filtering()
    test_captivity_simulator_monitor_none_stays_sealed()
    test_captivity_simulator_night_gates_and_intervention_process()
    test_captivity_simulator_low_stamina_and_tool_process_do_not_deadlock()
    test_captivity_simulator_action_contents_and_expanded_tools()
    test_captivity_simulator_inventory_night_actions_and_call_bell()
    test_captivity_simulator_voice_bell_first_use_privacy()
    test_captivity_simulator_inventory_secret_first_use_flow()
    test_captivity_simulator_feeding_aftereffects_and_tolerance()
    test_captivity_simulator_feeding_projection_hides_secret_setup()
    test_captivity_simulator_capture_du_night_condition_reaches_dynamic_system()
    test_captivity_simulator_escape_lure_visibility_and_recapture_pending()
    test_captivity_simulator_recapture_process_and_rules_both_routes()
    test_captivity_simulator_future_escape_window_and_non_escape_choice()
    test_captivity_simulator_escape_stay_return_action_both_routes()
    test_captivity_simulator_escape_abort_still_enters_recapture()
    test_captivity_simulator_recapture_rules_have_mechanical_effects()
    test_captivity_simulator_escape_lure_non_escape_choices_notify_captor()
    test_captivity_simulator_fixed_ending_titles()
    test_captivity_simulator_ending_state_machine()
    test_captivity_simulator_day30_night_ending_matrix()
    test_captivity_simulator_forbidden_tags_and_runtime_registration()
    test_captivity_simulator_bladder_control_captive_route_only()
    test_captivity_simulator_pet_system_both_routes_and_monitor_privacy()
    test_captivity_simulator_du_captor_inventory_commands()
    test_captivity_simulator_sync_text_and_command_parser()
    test_captivity_simulator_reply_commands_apply_to_runtime()
    test_captivity_simulator_public_api_returns_only_local_view()
    test_captivity_simulator_sync_activity_policy()
    test_captivity_simulator_wakeup_uses_dynamic_system_and_skips_body_delta()
    test_captivity_simulator_archive_compaction()
    test_captivity_simulator_sync_route_pending_semantics()
    test_captivity_simulator_sync_day_plan_uses_one_du_reply()
    test_captivity_simulator_sync_route_redacts_du_night_action()
    test_captivity_simulator_ending_sync_notifies_once()
    test_captivity_simulator_sync_route_voice_bell_followup()
    test_captivity_simulator_sync_route_redacts_followup_night_preview()
    test_captivity_simulator_sync_route_capture_du_returns_to_captor()
    test_captivity_simulator_night_detail_branches_and_privacy()
    test_captivity_simulator_local_full_30_day_playthrough_both_routes()
    test_captivity_simulator_status_thresholds_and_mood_effects()
    test_captivity_simulator_scene_copy_and_transition_contract()
    print("captivity_simulator_game tests ok")
