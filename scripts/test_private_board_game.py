from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.game_tool_runtime import execute_game_command, list_game_tools
from services import private_board_tool
from services.private_board_game import (
    BOARD_SLOTS,
    CHOICE_PENALTY_CARDS,
    DEFAULT_LIMIT_OPTIONS,
    PLAYER_VIEW_NAMES,
    REVIEW_PENALTY_CARDS,
    THEME_CELL_STYLES,
    THEME_LIMIT_OPTIONS,
    _available_choice_options,
    _filter_options_for_actor,
    _filter_options_for_theme,
    _filter_pose_options,
    _limit_options_for_theme,
    _public_cell_events,
    _theme_profile_for,
    _translate_line,
    run_command,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_private_board_views() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        result = run_command("new_game seed=view-test", save_path=save_path)
        du_text = str(result.get("du_text") or "")
        player_text = str(result.get("player_text") or "")
        _assert("小玥" in du_text and "我" in du_text, "du view should use 小玥/我")
        _assert("渡" in player_text and "我" in player_text, "player view should use 我/渡")
        _assert("小玥" not in player_text, "player view should not show 小玥 label")
        _assert("位置：" in du_text and "跑道：" not in du_text, "du text should use compact positions, not full board lane")
        _assert("位置：" in player_text and "跑道：" not in player_text, "player text should use compact positions, not full board lane")
        _assert(_translate_line("我掷出 1，小玥继续。", PLAYER_VIEW_NAMES) == "渡掷出 1，我继续。", "actor labels should translate")
        _assert(_translate_line("我获得 Pass卡。", PLAYER_VIEW_NAMES) == "渡获得 Pass卡。", "reward actor label should translate")
        _assert(_translate_line("我选择「测试」。", PLAYER_VIEW_NAMES) == "渡选择「测试」。", "choice actor label should translate")
        _assert(_translate_line("任务：保留我的普通文本", PLAYER_VIEW_NAMES) == "任务：保留我的普通文本", "ordinary 我 should stay untouched")
        _assert(result["state"]["theme_profile"].get("theme"), "new game should draw an opening theme")
        theme_options = result["state"].get("theme_options") or []
        expected_theme_options = next(slot.get("options") for slot in BOARD_SLOTS if slot.get("key") == "theme")
        _assert(theme_options == list(expected_theme_options), "player state should expose the real board theme pool for the slot UI")
        _assert(result["state"]["theme_profile"].get("theme") in theme_options, "drawn theme should come from exposed theme options")
        _assert("开局抽到主题" in player_text, "new game text should show opening theme")
        reward_positions = [
            int(item.get("position") or 0)
            for item in result["state"].get("cell_events") or []
            if item.get("kind") in {"reward", "forward_reward", "clear_reward"}
        ]
        _assert(reward_positions == [5, 22, 32], "pass reward cells should stay reduced")
        review_positions = [
            int(item.get("position") or 0)
            for item in result["state"].get("cell_events") or []
            if item.get("kind") == "penalty_review"
        ]
        choice_positions = [
            int(item.get("position") or 0)
            for item in result["state"].get("cell_events") or []
            if item.get("kind") == "penalty_choice"
        ]
        _assert(review_positions == [4, 11, 20, 26, 33], "review penalty cells should be evenly distributed")
        _assert(choice_positions == [9, 21, 30], "choice penalty cells should not cluster")
        event_positions = {int(item.get("position") or 0) for item in result["state"].get("cell_events") or []}
        expected_empty_positions = {2, 7, 16, 19, 25, 28}
        _assert(event_positions == set(range(2, 36)) - expected_empty_positions, "board should keep exactly six empty cells")
        event_kinds = {str(item.get("kind") or "") for item in result["state"].get("cell_events") or []}
        _assert({"back", "move_other", "move_self", "reset_self"}.issubset(event_kinds), "board should include prank movement cells")
        cell_27 = next((item for item in result["state"].get("cell_events") or [] if int(item.get("position") or 0) == 27), {})
        _assert(cell_27.get("kind") == "reset_self", "cell 27 should send the landing player back to start")


def test_private_board_reset_self_cell() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=reset-self-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["positions"]["xinyue"] = 26
        state["positions"]["du"] = 5
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        result = run_command("roll 1", save_path=save_path)
        _assert(result["state"]["positions"]["xinyue"] == 0, "cell 27 should reset current actor to start")
        _assert(result["state"].get("game_over") is False, "cell 27 should not finish the game")
        _assert("重回起点" in str(result.get("player_text") or ""), "cell 27 result should name the reset event")


def test_private_board_action_lock() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=lock-test", save_path=save_path)
        run_command("roll 1", save_path=save_path)
        du_lock = run_command("roll 3", save_path=save_path)
        state = du_lock["state"]
        _assert(state["positions"]["du"] == 3, "du should land on action-lock cell")
        _assert(state["turn_actor"] == "xinyue", "turn should pass to xinyue")
        _assert(any(s.get("blocks_action") for s in state["statuses"]["du"]), "du should have a blocking status")

        after_xinyue = run_command("roll 1", save_path=save_path)
        state = after_xinyue["state"]
        _assert(state["turn_actor"] == "du", "du should recover after one locked action")
        _assert(not any(s.get("blocks_action") for s in state["statuses"]["du"]), "blocking status should be consumed")
        _assert(any(s.get("slot") == "prop" for s in state["statuses"]["du"]), "prop punishment should remain after blocked action is consumed")


def test_private_board_double_blocked_turn_stays_drivable() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=double-block-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["statuses"]["xinyue"].append({
            "id": "x-lock",
            "slot": "prop",
            "label": "道具",
            "value": "测试停步",
            "duration_type": "actions",
            "remaining_actions": 1,
            "blocks_action": True,
        })
        state["statuses"]["du"].append({
            "id": "du-lock",
            "slot": "prop",
            "label": "道具",
            "value": "测试停步",
            "duration_type": "actions",
            "remaining_actions": 1,
            "blocks_action": True,
        })
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        skipped = run_command("roll", save_path=save_path)
        state = skipped["state"]
        player_text = str(skipped.get("player_text") or "")
        _assert(state["turn_actor"] == "xinyue", "double blocked no-action turn should return control to xinyue")
        _assert(not any(s.get("blocks_action") for s in state["statuses"]["xinyue"]), "xinyue block should be consumed")
        _assert(not any(s.get("blocks_action") for s in state["statuses"]["du"]), "du block should be consumed")
        _assert(any(s.get("slot") == "prop" for s in state["statuses"]["xinyue"]), "xinyue prop should remain after block is consumed")
        _assert(any(s.get("slot") == "prop" for s in state["statuses"]["du"]), "du prop should remain after block is consumed")
        _assert("渡也没有行动权" in player_text, "player text should explain du's skipped no-action turn")
        _assert("道具惩罚：测试停步" in player_text, "prop status should read as punishment, not usable item")
        _assert("已解除" not in player_text, "blocked action consumption should not read as clearing the prop")
        _assert("停步已结束" in player_text, "blocked action consumption should explain only the no-action effect ended")


def test_private_board_registered_game_tool() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        games = list_game_tools()
        _assert(any(g.get("game_id") == "private_board" for g in games), "private_board should be listed")
        payload = execute_game_command("private_board", "new_game seed=tool-test", "default", save_root=root)
        _assert(payload.get("ok") is True, "tool payload should succeed")
        _assert(payload.get("game_id") == "private_board", "tool payload should expose private_board")
        _assert("player_text" in payload, "tool payload should include player_text for frontend")
        _assert((root / "default.json").exists(), "tool should save default game")


def test_private_board_openai_tool_adapter() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        private_board_tool.SAVE_ROOT = Path(tmpdir)
        tools = private_board_tool.get_private_board_tools_for_inject()
        _assert(tools and tools[0]["function"]["name"] == "private_board", "private board tool schema should be exposed")
        raw = private_board_tool.execute_private_board_tool({"command": "new_game seed=adapter-test"})
        payload = json.loads(raw)
        _assert(payload.get("ok") is True, "private board adapter should execute command")
        _assert(payload.get("game_id") == "private_board", "private board adapter should expose game_id")
        _assert("pending_event" in (payload.get("state") or {}), "adapter payload should expose pending event state")


def test_private_board_concurrent_rolls_do_not_drop_steps() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=concurrent-test", save_path=save_path)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run_command, "roll 1", save_path) for _ in range(2)]
            for future in futures:
                future.result()

        result = run_command("status", save_path=save_path)
        state = result["state"]
        _assert(state["positions"]["xinyue"] == 1, "xinyue roll should persist")
        _assert(state["positions"]["du"] == 1, "du roll should persist")
        pending = state.get("pending_event") or {}
        _assert(pending.get("type") == "duel", "same-cell concurrent rolls should trigger duel instead of dropping a step")
        _assert(state["turn_actor"] == pending.get("current_actor"), "turn should stay on the duel actor")
        player_text = str(result.get("player_text") or "")
        _assert(
            "我和渡触发" in player_text or "渡和我触发" in player_text,
            "player text should translate duel actor names",
        )


def test_private_board_theme_direction_filters() -> None:
    expected_directions = {
        "成人师生play": "du_leads",
        "上司下属play": "du_leads",
        "女仆主人play": "du_leads",
        "大小姐管家play": "xinyue_leads",
        "医生检查play": "du_leads",
        "秘书老板play": "du_leads",
        "成人补课play": "du_leads",
        "骑士公主play": "du_leads",
        "吸血鬼人类play": "xinyue_leads",
    }
    for theme, direction in expected_directions.items():
        profile = _theme_profile_for(theme)
        _assert(profile["direction"] == direction, f"{theme} should be {direction}")

    teacher_state = {"theme_profile": _theme_profile_for("成人师生play")}
    butler_state = {"theme_profile": _theme_profile_for("大小姐管家play")}
    _assert(butler_state["theme_profile"]["direction"] == "xinyue_leads", "butler theme should be xinyue-led")

    teacher_limits = _limit_options_for_theme(teacher_state)
    _assert(THEME_LIMIT_OPTIONS["成人师生play"][0] in teacher_limits, "teacher theme should include teacher-specific limit")
    _assert(any("教鞭" in item for item in teacher_limits), "teacher limits should match teacher theme")
    _assert(any("不许主动触碰对方" in item for item in teacher_limits), "teacher theme should include common limits")
    _assert(not any("医生" in item for item in teacher_limits), "teacher limits should not include doctor limits")
    _assert(all("小玥" not in item for item in teacher_limits), "board limits should not reuse private-home wording")
    butler_limits = _limit_options_for_theme(butler_state)
    _assert(any("小姐" in item for item in butler_limits), "butler theme should include butler-specific limit")
    _assert(any("不许主动触碰对方" in item for item in butler_limits), "butler theme should include common limits")
    _assert(not any("医生" in item for item in butler_limits), "butler theme should not include doctor limits")
    pet_limits = _limit_options_for_theme({"theme_profile": _theme_profile_for("主人宠物play")})
    _assert(any("主人喂食" in item for item in pet_limits), "pet theme should include pet-specific limits")
    _assert(not any("医生" in item for item in pet_limits), "pet theme should not include doctor limits")
    _assert(_limit_options_for_theme({}) == list(DEFAULT_LIMIT_OPTIONS), "missing theme should use default board limits")


def test_private_board_theme_cell_events() -> None:
    teacher_state = {"theme_profile": _theme_profile_for("成人师生play"), "board_size": 36}
    teacher_events = {item["position"]: item for item in _public_cell_events(teacher_state)}
    _assert(teacher_events[3]["name"] == "课堂罚停", "teacher theme should rename lock cell")
    _assert(teacher_events[11]["name"] == "课后任务", "teacher theme should rename task cell")
    _assert("行动权" in teacher_events[3]["effect"], "cell event should expose frontend effect text")

    butler_state = {"theme_profile": _theme_profile_for("大小姐管家play"), "board_size": 36}
    butler_events = {item["position"]: item for item in _public_cell_events(butler_state)}
    _assert(butler_events[11]["name"] == "管家侍奉", "butler theme should rename task cell")
    _assert(butler_events[21]["name"] == "礼仪规矩", "butler theme should rename limit cell")

    teacher_places = _filter_options_for_theme(
        teacher_state,
        "place",
        ["车后座", "教室讲台边"],
    )
    _assert(teacher_places == ["教室讲台边"], "teacher theme should prefer classroom places")
    butler_props = _filter_options_for_theme(
        butler_state,
        "prop",
        ["震动棒", "铃铛项圈"],
    )
    _assert(butler_props == ["铃铛项圈"], "butler theme should prefer matching props")


def test_private_board_review_penalty_cards_seed_pool() -> None:
    names = {str(card.get("name") or "") for card in REVIEW_PENALTY_CARDS}
    expected = {"反向诱惑", "全部暴露！", "羞耻台词大放送", "自慰陈述", "真心话点名"}
    _assert(expected.issubset(names), "approved review cards should be in the seed pool")
    _assert(len(REVIEW_PENALTY_CARDS) >= 5, "review penalty pool should have enough variety")
    for card in REVIEW_PENALTY_CARDS:
        text = "\n".join(str(card.get(key) or "") for key in ("task", "submission", "pass_result", "reject_prompt"))
        _assert(str(card.get("type") or "") == "review", "review penalty card type should be review")
        _assert(card.get("pass_allowed") is True, "review penalty card should allow Pass")
        _assert("对方" in text, "review card should use 对方 wording")
        _assert("主导方" not in text, "review card should not use 主导方 wording")
    truth_cards = [card for card in REVIEW_PENALTY_CARDS if "真心话" in str(card.get("name") or "")]
    _assert(len(truth_cards) == 1, "truth task should not duplicate the question flow")
    truth_question = next(card for card in truth_cards if str(card.get("id") or "") == "truth_question_by_partner")
    _assert(truth_question.get("task") == "这是一张真心话任务。请诚实回答对方的问题。", "truth question answer task should be direct")
    _assert(truth_question.get("submission") == "写下你对这个问题的回答。", "truth question submission should be a complete hint")
    _assert(truth_question.get("waiting_task") == "对方正在出题中。", "truth question waiting text should be explicit")
    _assert("很想知道答案" in str(truth_question.get("question_prompt") or ""), "truth question should give the questioner a prompt")
    for card in CHOICE_PENALTY_CARDS:
        has_final_material = any(str((choice.get("effect") or {}).get("slot") or "") in {"place", "pose"} for choice in card.get("choices") or [])
        if has_final_material:
            _assert(card.get("pass_allowed") is False, "final-material choice cards should not be Pass-skippable")
            _assert("惩罚" not in str(card.get("prompt") or ""), "final-material choice prompt should not call it a punishment")
    _assert("单向规则" not in names, "rule editing card should not be in penalty review pool")
    _assert("真心话追问" not in names, "duplicated truth followup card should not be in penalty review pool")
    _assert("主动索求" not in names, "unapproved active request card should not be in penalty review pool")
    _assert("惩罚复盘" not in names, "unapproved recap card should not be in penalty review pool")
    _assert("主题指令改写" not in names, "unapproved theme rewrite card should not be in penalty review pool")
    _assert("忍耐陈述" not in names, "rejected overlapping card should not be in penalty review pool")
    _assert("弱点坦白契约" not in names, "overlapping weakness card should not be in penalty review pool")
    _assert("秘密信号对表" not in names, "rejected secret signal card should not be in penalty review pool")
    _assert("自我处理报告" not in names, "awkward masturbation card name should not be in penalty review pool")
    _assert("自慰报告" not in names, "rejected masturbation card name should not be in penalty review pool")


def test_private_board_corpus_pruned_terms() -> None:
    banned = {
        "NTR幻想",
        "身份倒置",
        "反差诱惑",
        "秘密恋人",
        "支配臣服",
        "露出边缘",
        "身体崇拜",
        "感官剥夺",
        "和好炮",
        "久别重逢",
        "Alpha易感期",
        "临时标记",
        "强占有欲",
        "发情期交配成结",
        "民国旧上海play",
        "古代宫廷play",
        "电话做爱",
        "远程指令play",
        "电话指令",
        "陌生恋人play",
        "办公室偷情",
        "偷情play",
        "邻居偷情play",
        "摄影师模特play",
        "温度play",
        "吃醋惩罚",
        "强势命令",
        "奖惩调教",
        "罚跪调教",
        "命令羞耻",
        "体液标记",
        "皮革手套",
        "围巾",
        "网袜",
        "穿戴式玩具",
        "双头假阳具",
        "震动子弹",
        "透明胶带",
        "发绳",
        "跳蛋遥控器",
        "白衬衫",
        "领带",
        "皮带",
        "丝袜",
        "黑丝袜",
        "制服外套",
        "口红",
        "蜂蜜",
        "奶油",
        "冰棒",
        "电动牙刷",
        "浴缸骑乘",
        "天台雨后",
        "温室角落",
        "水族馆玻璃前",
        "成结",
        "易感期",
    }
    slot_text = "\n".join(
        str(option)
        for slot in BOARD_SLOTS
        for option in (slot.get("options") or [])
    )
    style_text = json.dumps(THEME_CELL_STYLES, ensure_ascii=False)
    for term in banned:
        _assert(term not in slot_text, f"{term} should not remain in board slots")
        _assert(term not in style_text, f"{term} should not remain in board theme styles")
    raw_pose_options = next(slot.get("options") for slot in BOARD_SLOTS if slot.get("key") == "pose")
    board_pose_options = _filter_pose_options([str(item) for item in raw_pose_options])
    _assert("浴缸骑乘" not in board_pose_options, "board final pose should not contain location-specific pose wording")
    _assert("骑乘位" in board_pose_options, "board final pose should keep the posture after stripping the location")


def test_private_board_final_pose_is_note_material() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=pose-material", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["positions"]["xinyue"] = 7
        state["final_note_items"] = [
            {"slot": "place", "label": "地点", "value": "旧地点", "duration_type": "until_finish"},
            {"slot": "pose", "label": "姿势", "value": "旧姿势", "duration_type": "until_finish"},
            {"slot": "pose", "label": "姿势", "value": "新姿势", "duration_type": "until_finish"},
            {"slot": "pose", "label": "姿势", "value": "浴缸骑乘", "duration_type": "until_finish"},
        ]
        state["statuses"]["xinyue"] = [
            {"slot": "prop", "label": "道具", "value": "测试道具", "duration_type": "until_clear"}
        ]
        state["statuses"]["du"] = [
            {"slot": "place", "label": "地点", "value": "迁移地点", "duration_type": "until_finish"},
            {"slot": "pose", "label": "姿势", "value": "迁移姿势", "duration_type": "until_finish"},
        ]
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        status = run_command("status", save_path=save_path)
        places = [item for item in status["state"]["final_note_items"] if item.get("slot") == "place"]
        _assert(len(places) == 1 and places[0]["value"] == "迁移地点", "final place should migrate and keep only the latest value")
        poses = [item for item in status["state"]["final_note_items"] if item.get("slot") == "pose"]
        _assert(len(poses) == 1 and poses[0]["value"] == "迁移姿势", "final pose should migrate and keep only the latest value")
        _assert("浴缸骑乘" not in str(status["state"]["final_note_items"]), "final pose migration should clean location-specific pose wording")
        _assert(not any(item.get("slot") == "place" for item in status["state"]["statuses"]["du"]), "place should not stay in actor status")
        _assert(not any(item.get("slot") == "pose" for item in status["state"]["statuses"]["du"]), "pose should not stay in actor status")

        cleared = run_command("roll 1", save_path=save_path)
        _assert(cleared["state"]["statuses"]["xinyue"] == [], "clear cell should clear normal player status")
        places = [item for item in cleared["state"]["final_note_items"] if item.get("slot") == "place"]
        _assert(len(places) == 1 and places[0]["value"] == "迁移地点", "clear cell should not remove final place")
        poses = [item for item in cleared["state"]["final_note_items"] if item.get("slot") == "pose"]
        _assert(len(poses) == 1 and poses[0]["value"] == "迁移姿势", "clear cell should not remove final pose")
        _assert("最终地点：迁移地点" in str(cleared.get("player_text") or ""), "player text should show final place separately")
        _assert("最终姿势：迁移姿势" in str(cleared.get("player_text") or ""), "player text should show final pose separately")


def test_private_board_choice_penalty_cards_filter_unavailable_options() -> None:
    _assert(len(CHOICE_PENALTY_CARDS) == 8, "choice penalty pool should start with 8 cards")
    _assert(not any(slot.get("key") == "task" for slot in BOARD_SLOTS), "status slots should not include task corpus")
    for card in CHOICE_PENALTY_CARDS:
        _assert(str(card.get("type") or "") == "choice", "choice penalty card type should be choice")
        has_final_material = any(str((choice.get("effect") or {}).get("slot") or "") in {"place", "pose"} for choice in card.get("choices") or () if isinstance(choice, dict))
        if has_final_material:
            _assert(card.get("pass_allowed") is False, "final-material choice card should not allow Pass")
        else:
            _assert(card.get("pass_allowed") is True, "ordinary choice penalty card should allow Pass")
        choices = [choice for choice in card.get("choices") or () if isinstance(choice, dict)]
        _assert(len(choices) >= 2, "choice penalty card should provide at least two choices")
        for choice in choices:
            _assert(str(choice.get("id") or "") != "add_task", "choice penalty should not add task status")
            effect = choice.get("effect") if isinstance(choice.get("effect"), dict) else {}
            _assert(str(effect.get("slot") or "") != "task", "choice penalty should not target task status")
            text = "\n".join(str(choice.get(key) or "") for key in ("label", "id"))
            _assert("分钟" not in text and "一周" not in text, "choice penalty card should not use real time wording")

    no_prop_state = {"statuses": {"xinyue": []}}
    with_prop_state = {"statuses": {"xinyue": [{"slot": "prop", "label": "道具惩罚", "value": "跳蛋"}]}}
    with_plain_prop_state = {"statuses": {"xinyue": [{"slot": "prop", "label": "道具惩罚", "value": "眼罩"}]}}
    upgrade_cards = [
        card
        for card in CHOICE_PENALTY_CARDS
        if any(str(choice.get("id") or "") == "upgrade_prop_level" for choice in card.get("choices") or () if isinstance(choice, dict))
    ]
    _assert(upgrade_cards, "choice pool should include prop level upgrade options")
    for card in upgrade_cards:
        no_prop_choices = _available_choice_options(card, no_prop_state, "xinyue")
        with_prop_choices = _available_choice_options(card, with_prop_state, "xinyue")
        with_plain_prop_choices = _available_choice_options(card, with_plain_prop_state, "xinyue")
        _assert(
            not any(choice.get("id") == "upgrade_prop_level" for choice in no_prop_choices),
            "prop upgrade choice should be unavailable when actor has no prop status",
        )
        _assert(
            not any(choice.get("id") == "upgrade_prop_level" for choice in with_plain_prop_choices),
            "prop upgrade choice should be unavailable when actor only has non-levelable prop status",
        )
        _assert(
            any(choice.get("id") == "upgrade_prop_level" for choice in with_prop_choices),
            "prop upgrade choice should be available when actor has a levelable prop status",
        )


def test_private_board_human_actor_prop_safety_filter() -> None:
    options = ["眼罩", "锁精环", "项圈", "阴蒂吸吮器", "吸乳器"]
    xinyue_options = _filter_options_for_actor("xinyue", "prop", options)
    du_options = _filter_options_for_actor("du", "prop", options)
    _assert("锁精环" not in xinyue_options, "human player should never receive cock-ring prop options")
    _assert("锁精环" in du_options, "du prop options may still include cock-ring options")
    _assert("阴蒂吸吮器" not in du_options, "du should never receive clitoral prop options")
    _assert("吸乳器" not in du_options, "du should never receive breast-pump prop options")
    _assert("阴蒂吸吮器" in xinyue_options, "xinyue prop options may still include clitoral props")
    _assert(_filter_options_for_actor("xinyue", "limit", ["锁精环限制"]) == ["锁精环限制"], "safety filter should only apply to prop options")


def test_private_board_pending_review_flow_and_pass_card() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=pending-review-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["positions"]["xinyue"] = 10
        state["hands"]["xinyue"]["pass"] = 1
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        landed = run_command("roll 1", save_path=save_path)
        state = landed["state"]
        pending = state.get("pending_event") or {}
        _assert(pending.get("type") == "review", "review cell should create pending review event")
        _assert(pending.get("actor") == "xinyue", "pending actor should be landing player")
        _assert(state["turn_actor"] == "xinyue", "turn should pause on pending event")

        submitted = run_command("submit 我完成了任务描述", save_path=save_path)
        pending = submitted["state"].get("pending_event") or {}
        _assert(pending.get("phase") == "submitted", "submit should mark review as submitted")
        _assert("我完成了任务描述" in str(pending.get("submission_text") or ""), "submission text should persist for review")

        rejected = run_command("reject", save_path=save_path)
        pending = rejected["state"].get("pending_event") or {}
        _assert(pending.get("phase") == "assigned", "reject should return review to assigned phase")
        _assert(int(pending.get("reject_count") or 0) == 1, "reject count should increase")

        skipped = run_command("pass", save_path=save_path)
        state = skipped["state"]
        _assert(state.get("pending_event") is None, "pass card should clear pending event")
        _assert(state["hands"]["xinyue"]["pass"] == 0, "pass card should be consumed")
        _assert(state.get("pass_skips_used") == 1, "pass skip counter should increase")
        _assert(state["turn_actor"] == "du", "skipping should advance turn")

        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["hands"]["xinyue"]["pass"] = 1
        state["pending_event"] = {
            "type": "choice",
            "actor": "xinyue",
            "name": "第二个惩罚",
            "pass_allowed": True,
            "choices": [{"id": "prop", "label": "道具惩罚"}],
        }
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        blocked = run_command("pass", save_path=save_path)
        state = blocked["state"]
        _assert(state.get("pending_event") is not None, "second pass should not clear pending event")
        _assert(state["hands"]["xinyue"]["pass"] == 1, "second pass should not consume card")
        _assert("已经使用过一次" in str(blocked.get("du_text") or ""), "second pass should explain per-game limit")


def test_private_board_truth_question_flow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=truth-question-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        card = next(card for card in REVIEW_PENALTY_CARDS if str(card.get("id") or "") == "truth_question_by_partner")
        state["turn_actor"] = "du"
        state["pending_event"] = {
            "id": "truth-test",
            "type": "review",
            "card_id": "truth_question_by_partner",
            "name": card["name"],
            "actor": "xinyue",
            "reviewer": "du",
            "phase": "questioning",
            "task": card["task"],
            "submission": card["submission"],
            "question_prompt": card["question_prompt"],
            "question_text": "",
            "waiting_task": card["waiting_task"],
            "pass_result": card["pass_result"],
            "reject_prompt": card["reject_prompt"],
            "pass_allowed": True,
            "cell": 11,
            "theme": "测试主题",
            "reject_count": 0,
            "submission_text": "",
        }
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        status = run_command("status", save_path=save_path)
        _assert("对方正在出题中" in str(status.get("player_text") or ""), "player should see waiting-for-question text")
        _assert("请问对方一个你很想知道答案却一直没有问的问题" in str(status.get("du_text") or ""), "questioner should see question prompt")

        questioned = run_command("submit 你最想知道什么？", save_path=save_path)
        pending = questioned["state"].get("pending_event") or {}
        _assert(pending.get("phase") == "assigned", "question submission should move to answer phase")
        _assert(pending.get("question_text") == "你最想知道什么？", "question text should persist")
        _assert(questioned["state"]["turn_actor"] == "xinyue", "answer phase should return to answer actor")
        _assert("题目：你最想知道什么？" in str(questioned.get("player_text") or ""), "player text should include the question")
        _assert("提交要求：写下你对这个问题的回答。" in str(questioned.get("player_text") or ""), "player text should ask for the answer clearly")

        answered = run_command("submit 我的回答", save_path=save_path)
        pending = answered["state"].get("pending_event") or {}
        _assert(pending.get("phase") == "submitted", "answer submission should enter review phase")
        _assert(pending.get("submission_text") == "我的回答", "answer text should persist")
        _assert(answered["state"]["turn_actor"] == "du", "review phase should go to questioner/reviewer")


def test_private_board_pending_choice_flow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=pending-choice-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["positions"]["xinyue"] = 8
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        landed = run_command("roll 1", save_path=save_path)
        state = landed["state"]
        pending = state.get("pending_event") or {}
        _assert(pending.get("type") == "choice", "choice cell should create pending choice event")
        choices = pending.get("choices") or []
        _assert(choices, "choice pending event should expose frontend choices")
        first_choice = str(choices[0].get("id") or "")
        chosen = run_command(f"choose {first_choice}", save_path=save_path)
        state = chosen["state"]
        _assert(state.get("pending_event") is None, "choice should clear pending event")
        _assert(state["turn_actor"] == "du", "choice settlement should advance turn")


def test_private_board_same_cell_duel_flow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=duel-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["positions"]["xinyue"] = 4
        state["positions"]["du"] = 5
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        landed = run_command("roll 1", save_path=save_path)
        pending = landed["state"].get("pending_event") or {}
        _assert(pending.get("type") == "duel", "same cell should trigger rps duel")
        _assert(pending.get("current_actor") == "xinyue", "landing actor should choose first")
        _assert("剪刀石头布对抗" in str(landed.get("player_text") or ""), "player text should show duel")

        first = run_command("choose 石头", save_path=save_path)
        pending = first["state"].get("pending_event") or {}
        _assert(pending.get("type") == "duel", "duel should wait for second pick")
        _assert(pending.get("current_actor") == "du", "du should choose second")
        _assert(first["state"]["turn_actor"] == "du", "turn should move to du for second pick")

        settled = run_command("剪刀石头布: 剪刀", save_path=save_path)
        state = settled["state"]
        _assert(state.get("pending_event") is None, "duel should settle after both picks")
        _assert(state["positions"]["xinyue"] == 8, "winner should move forward 3")
        _assert(state["positions"]["du"] == 2, "loser should move backward 3")
        _assert(state["turn_actor"] == "du", "turn should pass to the original next actor")
        _assert("系统判定" in str(settled.get("player_text") or ""), "settlement should be system judged")


def test_private_board_du_triggered_duel_still_xinyue_first() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=du-triggered-duel", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "du"
        state["positions"]["xinyue"] = 5
        state["positions"]["du"] = 4
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        landed = run_command("roll 1", save_path=save_path)
        pending = landed["state"].get("pending_event") or {}
        _assert(pending.get("type") == "duel", "du landing on same cell should trigger duel")
        _assert(pending.get("current_actor") == "xinyue", "xinyue should always choose first")
        _assert(landed["state"]["turn_actor"] == "xinyue", "turn should move to xinyue for first pick")


def test_private_board_finish_generates_final_note() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=finish-note-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["positions"]["xinyue"] = 35
        state["statuses"]["xinyue"] = [{"slot": "prop", "label": "道具惩罚", "value": "赢家旧状态"}]
        state["statuses"]["du"] = [
            {"slot": "prop", "label": "道具惩罚", "value": "目标状态"},
            {"slot": "place", "label": "地点", "value": "床尾"},
            {"slot": "pose", "label": "姿势", "value": "跪趴"},
        ]
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        finished = run_command("roll 1", save_path=save_path)
        state = finished["state"]
        note = state.get("final_note") or {}
        _assert(state.get("game_over") is True, "finish should end game")
        _assert(state.get("winner") == "xinyue", "landing actor should win")
        _assert(state["statuses"]["xinyue"] == [], "winner statuses should be cleared")
        _assert(state["statuses"]["du"], "other player statuses should remain for final note")
        _assert(not any(item.get("slot") == "place" for item in state["statuses"]["du"]), "place should not stay in actor status")
        _assert(not any(item.get("slot") == "pose" for item in state["statuses"]["du"]), "pose should not stay in actor status")
        _assert(note.get("target") == "du", "final note should target the other player")
        _assert(note.get("final_place") == "床尾", "final note should expose final place")
        _assert(note.get("final_pose") == "跪趴", "final note should expose final pose")
        _assert("你先到终点，你的状态已清空" in str(note.get("text") or ""), "player final note should address the winner as 你")
        _assert("我先到终点，我的状态已清空" not in str(note.get("text") or ""), "player final note should not use 我的状态")
        _assert("床尾" in str(note.get("text") or ""), "final note should include final place")
        _assert("跪趴" in str(note.get("text") or ""), "final note should include final pose")
        _assert("请尽情享受你们的ooxx吧" in str(note.get("text") or ""), "final note should include closing line")

        sent = run_command("final_note_sent", save_path=save_path)
        note = (sent["state"].get("final_note") or {})
        _assert(note.get("sent") is True, "final note should be marked as sent")


def test_private_board_winner_can_append_final_status() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=append-final-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["turn_actor"] = "xinyue"
        state["positions"]["xinyue"] = 35
        state["statuses"]["xinyue"] = [{"slot": "prop", "label": "道具惩罚", "value": "赢家旧状态"}]
        state["statuses"]["du"] = []
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        finished = run_command("roll 1", save_path=save_path)
        _assert(finished["state"].get("winner") == "xinyue", "xinyue should win the test game")
        _assert(finished["state"]["statuses"]["du"] == [], "du should start final note with no status")
        _assert("没有遗留状态" in str((finished["state"].get("final_note") or {}).get("text") or ""), "empty target status should be explicit")

        appended = run_command("append_final_status prop 眼罩 level=3", save_path=save_path)
        state = appended["state"]
        note = state.get("final_note") or {}
        appended_prop = next((item for item in state["statuses"]["du"] if item.get("slot") == "prop" and item.get("value") == "眼罩"), None)
        _assert(appended_prop is not None, "winner should append target prop status")
        _assert(appended_prop.get("duration_type") == "final_note", "final append status should not use until_finish duration")
        _assert(appended_prop.get("level") == 1, "non-levelable final prop should ignore selected level")
        _assert("眼罩（3档）" not in str(appended.get("player_text") or ""), "non-levelable final prop should not show prop level")
        _assert("眼罩" in str(note.get("target_status") or ""), "final note should expose appended target status")
        _assert("眼罩（3档）" not in str(note.get("target_status") or ""), "final note target status should not expose level for eye mask")
        _assert("到终点前有效" not in str(note.get("target_status") or ""), "final note target status should not show finish duration")
        _assert("渡当前状态：道具惩罚：眼罩" in str(note.get("text") or ""), "final note text should include appended target status")
        _assert("到终点前有效" not in str(note.get("text") or ""), "final note text should not show finish duration for appended statuses")
        appended_levelable = run_command("append_final_status prop 跳蛋 level=3", save_path=save_path)
        _assert("跳蛋（3档）" in str((appended_levelable["state"].get("final_note") or {}).get("target_status") or ""), "levelable final prop should keep selected level")
        saved = json.loads(save_path.read_text(encoding="utf-8"))
        saved["statuses"]["du"][0]["duration_type"] = "until_finish"
        save_path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        migrated = run_command("status", save_path=save_path)
        migrated_prop = next((item for item in migrated["state"]["statuses"]["du"] if item.get("slot") == "prop" and item.get("value") == "眼罩"), None)
        _assert(migrated_prop and migrated_prop.get("duration_type") == "final_note", "old final append duration should be migrated")
        _assert("到终点前有效" not in str((migrated["state"].get("final_note") or {}).get("target_status") or ""), "migrated final append should not show finish duration")

        saved = json.loads(save_path.read_text(encoding="utf-8"))
        saved["statuses"]["du"].extend([
            {
                "slot": "prop",
                "label": "道具惩罚",
                "value": "震动乳夹",
                "duration_type": "actions",
                "remaining_actions": 3,
                "blocks_action": True,
                "level": 2,
            },
            {
                "slot": "limit",
                "label": "限制",
                "value": "不准抬头",
                "duration_type": "until_clear",
            },
        ])
        save_path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        durationless = run_command("status", save_path=save_path)
        note = durationless["state"].get("final_note") or {}
        _assert("震动乳夹（2档）" in str(note.get("target_status") or ""), "final note target status should keep levelable prop level without action counter")
        _assert("不准抬头" in str(note.get("target_status") or ""), "final note target status should keep clearable limit text")
        _assert("停步剩余" not in str(note.get("target_status") or ""), "final note target status should hide action counter")
        _assert("待解除" not in str(note.get("target_status") or ""), "final note target status should hide clearable duration")
        _assert("停步剩余" not in str(note.get("text") or ""), "final note text should hide action counter")
        _assert("待解除" not in str(note.get("text") or ""), "final note text should hide clearable duration")

        removed_prop = run_command("remove_final_status prop 跳蛋", save_path=save_path)
        state = removed_prop["state"]
        note = state.get("final_note") or {}
        _assert(not any(item.get("slot") == "prop" and item.get("value") == "跳蛋" for item in state["statuses"]["du"]), "winner should remove toggled final prop status")
        _assert("跳蛋" not in str(note.get("target_status") or ""), "removed final prop should disappear from final note")

        appended_limit = run_command("append_final_status limit 不准提前结束", save_path=save_path)
        state = appended_limit["state"]
        note = state.get("final_note") or {}
        _assert(any(item.get("slot") == "limit" and item.get("value") == "不准提前结束" for item in state["statuses"]["du"]), "winner should append target limit status")
        _assert("不准提前结束" in str(note.get("target_status") or ""), "final note should expose appended target limit")
        rejected_slot = run_command("append_final_status pose 骑乘位", save_path=save_path)
        _assert("道具惩罚或限制" in str(rejected_slot.get("player_text") or ""), "final append should reject final pose edits")

        sent = run_command("final_note_sent", save_path=save_path)
        rejected = run_command("append_final_status limit 追加限制", save_path=save_path)
        rejected_remove = run_command("remove_final_status prop 眼罩", save_path=save_path)
        _assert((sent["state"].get("final_note") or {}).get("sent") is True, "final note should be sent")
        _assert("已经发送" in str(rejected.get("player_text") or ""), "sent final note should reject later appends")
        _assert("已经发送" in str(rejected_remove.get("player_text") or ""), "sent final note should reject later removals")


def test_private_board_migrates_ended_save_without_final_note() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=ended-migration-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["game_over"] = True
        state["winner"] = "xinyue"
        state["positions"]["xinyue"] = 36
        state["theme_profile"] = {"theme": "感官剥夺", "direction": "du_leads", "direction_label": "渡主导"}
        state["statuses"]["xinyue"] = [{"slot": "limit", "label": "限制", "value": "赢家旧状态"}]
        state["statuses"]["du"] = [{"slot": "prop", "label": "道具惩罚", "value": "避孕套"}]
        state["final_note"] = {"winner": "xinyue", "target": "du", "theme": "感官剥夺", "sent": False}
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        payload = run_command("status", save_path=save_path)
        state = payload["state"]
        note = state.get("final_note") or {}
        _assert(state["statuses"]["xinyue"] == [], "ended save migration should clear winner statuses")
        _assert(state["statuses"]["du"] == [], "ended save migration should remove invalid prop statuses")
        _assert(note.get("target") == "du", "ended save migration should create final note")
        _assert(note.get("theme") != "感官剥夺", "ended save migration should replace removed themes")
        _assert("请尽情享受你们的ooxx吧" in str(note.get("text") or ""), "migrated final note should expose text")
        _assert("避孕套" not in str(payload.get("player_text") or ""), "invalid prop should not leak into player text")


def test_private_board_review_feedback() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=review-feedback-test", save_path=save_path)
        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["pending_event"] = {
            "id": "review-feedback",
            "type": "review",
            "name": "真心话点名",
            "actor": "xinyue",
            "reviewer": "du",
            "phase": "submitted",
            "submission_text": "测试提交",
            "reject_prompt": "请重新提交。",
            "reject_count": 0,
        }
        state["turn_actor"] = "du"
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        approved = run_command("approve 做得不错，过。", save_path=save_path)
        approved_text = "\n".join(
            str(approved.get(key) or "")
            for key in ("text", "du_text", "player_text")
        )
        _assert("验收反馈：做得不错，过。" in approved_text, "approve feedback should be rendered in result text")

        state = json.loads(save_path.read_text(encoding="utf-8"))
        state["pending_event"] = {
            "id": "review-feedback-reject",
            "type": "review",
            "name": "真心话点名",
            "actor": "xinyue",
            "reviewer": "du",
            "phase": "submitted",
            "submission_text": "测试提交",
            "reject_prompt": "请重新提交。",
            "reject_count": 0,
        }
        state["turn_actor"] = "du"
        save_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        rejected = run_command("reject 这里重写具体一点。", save_path=save_path)
        pending = (rejected.get("state") or {}).get("pending_event") or {}
        _assert(pending.get("phase") == "assigned", "reject should reopen the task")
        _assert(pending.get("last_reject_reason") == "这里重写具体一点。", "reject feedback should be persisted on pending")


def test_private_board_wakeup_uses_dynamic_system() -> None:
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

        result = cf.send_private_board_wakeup(
            window_id="tg_123",
            target="123",
            event_text="小玥同步了本轮涩涩走格棋状态：等待渡选择。",
            preferred_channel="tg",
            return_only=True,
        )

        _assert(bool(result.get("ok")), f"private board wakeup should succeed: {result}")
        messages = ((captured.get("json") or {}).get("messages") or [])
        board_system = next((msg for msg in messages if "涩涩走格棋" in str(msg.get("content") or "")), None)
        _assert(isinstance(board_system, dict), "private board event should stay in a system message")
        _assert(board_system.get("role") == "system", "private board event should be a system event")
        _assert(board_system.get("__dynamic__") is True, "private board event must be dynamic system, not static prefix")
        _assert(
            all(
                msg.get("__dynamic__") or "涩涩走格棋" not in str(msg.get("content") or "")
                for msg in messages
                if isinstance(msg, dict) and msg.get("role") == "system"
            ),
            "private board content must not appear in a plain static system message",
        )
    finally:
        upstream_store.get_cached_active_model = old_model
        cf.requests.post = old_post
        cf._choice_dialog_delivery_preference = old_preference


def test_private_board_sync_marks_global_activity_time() -> None:
    import types

    from routes.miniapp import game_tools

    captured: list[str] = []
    fake_r2_store = types.SimpleNamespace(
        save_last_telegram_user_activity_at=lambda value: captured.append(str(value)) or True
    )
    fake_storage = types.SimpleNamespace(r2_store=fake_r2_store)
    old_storage = sys.modules.get("storage")
    old_r2_store = sys.modules.get("storage.r2_store")
    try:
        sys.modules["storage"] = fake_storage
        sys.modules["storage.r2_store"] = fake_r2_store
        game_tools._mark_private_board_sync_activity("2026-07-07T22:55:00+08:00")
    finally:
        if old_storage is None:
            sys.modules.pop("storage", None)
        else:
            sys.modules["storage"] = old_storage
        if old_r2_store is None:
            sys.modules.pop("storage.r2_store", None)
        else:
            sys.modules["storage.r2_store"] = old_r2_store

    _assert(
        captured == ["2026-07-07T22:55:00+08:00"],
        f"private board sync should mark global activity time, got {captured}",
    )


def test_private_board_state_update_sync_includes_message() -> None:
    from routes.miniapp import game_tools

    text = game_tools._private_board_sync_text(
        {
            "text": "【涩涩走格棋】\n当前局面如下。",
            "state": {
                "turn_actor": "du",
                "pending_event": {
                    "type": "review",
                    "actor": "du",
                    "phase": "assigned",
                    "name": "反向诱惑",
                },
            },
        },
        user_message="小玥打回了你的惩罚任务：这里重写具体一点。",
        mode="state_update",
    )

    _assert("本次说明：" in text, "state_update sync should include the caller message heading")
    _assert("这里重写具体一点" in text, "state_update sync should include reject feedback")
    _assert(text.index("本次说明：") < text.index("当前棋局："), "sync message should appear before board text")


def test_private_board_reply_command_parser() -> None:
    from routes.miniapp import game_tools

    commands = game_tools._private_board_commands_from_reply("【描述：重写后的具体指令】\n\n这次够具体了。")
    _assert(commands == ["submit 重写后的具体指令"], f"description reply should become submit, got {commands}")

    commands = game_tools._private_board_commands_from_reply("【通过：可以】\n【掷骰】")
    _assert(commands == ["approve 可以", "roll"], f"approve + roll should parse in order, got {commands}")

    commands = game_tools._private_board_commands_from_reply("我只是聊一句，不处理棋局。")
    _assert(commands == [], f"ordinary chat should not produce game commands, got {commands}")


def test_private_board_reply_commands_apply_to_game_runtime() -> None:
    from routes.miniapp import game_tools

    calls: list[tuple[str, str, str]] = []
    old_execute = game_tools.execute_game_command

    def fake_execute(game_id: str, command: str, save_id: str) -> dict:
        calls.append((game_id, command, save_id))
        return {
            "ok": True,
            "state": {"pending_event": {"phase": "submitted", "submission_text": "重写后的具体指令"}},
            "player_text": "渡提交了「反向诱惑」，等待我验收。",
        }

    try:
        game_tools.execute_game_command = fake_execute
        applied, payload = game_tools._apply_private_board_reply_commands("default", "【描述：重写后的具体指令】")
    finally:
        game_tools.execute_game_command = old_execute

    _assert(calls == [("private_board", "submit 重写后的具体指令", "default")], f"unexpected calls: {calls}")
    _assert(applied and applied[0].get("command") == "submit 重写后的具体指令", f"unexpected applied: {applied}")
    _assert(((payload or {}).get("state") or {}).get("pending_event", {}).get("phase") == "submitted", "payload should reflect submitted state")


def test_private_board_du_followup_after_applied_roll() -> None:
    from routes.miniapp import game_tools

    payload = {
        "state": {
            "turn_actor": "du",
            "pending_event": {
                "type": "review",
                "actor": "du",
                "reviewer": "xinyue",
                "phase": "assigned",
                "name": "自慰陈述",
            },
        },
    }
    _assert(game_tools._private_board_needs_du_followup(payload), "du pending task after roll should trigger another followup")
    _assert(
        game_tools._private_board_du_followup_message(payload) == "现在需要渡提交惩罚任务。",
        "du review assignment should use task submission followup message",
    )

    submitted = {
        "state": {
            "turn_actor": "xinyue",
            "pending_event": {
                "type": "review",
                "actor": "du",
                "reviewer": "xinyue",
                "phase": "submitted",
                "name": "自慰陈述",
            },
        },
    }
    _assert(not game_tools._private_board_needs_du_followup(submitted), "du submitted task should stop at xinyue review")


if __name__ == "__main__":
    test_private_board_views()
    test_private_board_reset_self_cell()
    test_private_board_action_lock()
    test_private_board_double_blocked_turn_stays_drivable()
    test_private_board_registered_game_tool()
    test_private_board_openai_tool_adapter()
    test_private_board_concurrent_rolls_do_not_drop_steps()
    test_private_board_theme_direction_filters()
    test_private_board_theme_cell_events()
    test_private_board_review_penalty_cards_seed_pool()
    test_private_board_corpus_pruned_terms()
    test_private_board_final_pose_is_note_material()
    test_private_board_choice_penalty_cards_filter_unavailable_options()
    test_private_board_human_actor_prop_safety_filter()
    test_private_board_pending_review_flow_and_pass_card()
    test_private_board_truth_question_flow()
    test_private_board_pending_choice_flow()
    test_private_board_same_cell_duel_flow()
    test_private_board_du_triggered_duel_still_xinyue_first()
    test_private_board_finish_generates_final_note()
    test_private_board_winner_can_append_final_status()
    test_private_board_migrates_ended_save_without_final_note()
    test_private_board_review_feedback()
    test_private_board_wakeup_uses_dynamic_system()
    test_private_board_sync_marks_global_activity_time()
    test_private_board_state_update_sync_includes_message()
    test_private_board_reply_command_parser()
    test_private_board_reply_commands_apply_to_game_runtime()
    test_private_board_du_followup_after_applied_roll()
    print("private_board_game tests ok")
