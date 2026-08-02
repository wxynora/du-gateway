#!/usr/bin/env python3
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import wenyou_service as wenyou
from services.wenyou.gm_context import compose_gm_context


def _cross_process_lock_probe(user_id, ready, start_event, active, maximum, guard) -> None:
    with guard:
        ready.value += 1
    start_event.wait(3)
    with wenyou._user_operation_lock(user_id):
        with guard:
            active.value += 1
            maximum.value = max(maximum.value, active.value)
        time.sleep(0.08)
        with guard:
            active.value -= 1


def _player(name: str, *, rank: str = "D", level: int = 1) -> dict:
    data = wenyou._default_player_stats()
    data.update({"display_name": name, "rank": rank, "level": level})
    return data


def _session(*, tutorial: bool = False) -> dict:
    framework = wenyou._tutorial_framework() if tutorial else {
        "instance_code": "TEST-001",
        "instance_name": "测试副本",
        "instance_genre": "剧情解密",
        "difficulty": "D",
        "world": "测试场景",
        "conflict": "找到出口",
        "player1_name": "辛玥",
        "player2_name": "渡",
        "initial_stats": {},
    }
    session = wenyou._new_session(framework)
    session["gameId"] = "test-game"
    session["stats"]["player1"]["display_name"] = "辛玥"
    session["stats"]["player2"]["display_name"] = "渡"
    return session


def _valid_candidate_design() -> dict:
    return {
        "player_count": 2,
        "tasker_total": 4,
        "npc_taskers": [
            {
                "name": "林岑",
                "instance_name": "",
                "tier_note": "老练",
                "stance": "谨慎戒备",
                "intent": "先核对每节车厢的编号差异",
                "trouble_chance": 10,
                "status": "alive",
                "blurb": "戴旧式腕表的短发女性，正独自记录报站顺序",
            },
            {
                "name": "周既白",
                "instance_name": "",
                "tier_note": "普通",
                "stance": "表面合作",
                "intent": "寻找愿意替他先下车试错的人",
                "trouble_chance": 45,
                "status": "alive",
                "blurb": "背着登山包的高个青年，始终站在车门控制器旁",
            },
        ],
        "npc_private_state": {
            "林岑": {
                "stance": "neutral",
                "intent": "独立确认安全站台后再决定是否共享",
                "trouble_chance": 10,
                "trigger": "确认别人没有故意误导时才交换记录",
            },
            "周既白": {
                "stance": "bad",
                "intent": "利用其他任务者承担第一次下车风险",
                "trouble_chance": 45,
                "trigger": "倒计时不足时会诱导别人先试错",
            },
        },
        "public": {"visible_rules": ["广播报站可能有误。"]},
        "gm_secret": {
            "true_rules": ["车窗倒影不会播报假站名。"],
            "false_rules": ["广播响起后必须立刻下车。"],
            "hidden_endings": [{"name": "列车员归站", "condition": "归还被撕掉的旧车票。"}],
        },
        "instance_blueprint": {
            "blueprint_version": 2,
            "logline": "任务者必须在循环列车中辨认真正站台。",
            "mainline": [
                {
                    "phase": "错站",
                    "goal": "识别广播第一次撒谎",
                    "required_clues": ["broadcast_error"],
                    "fail_forward": "误信广播会失去一节安全车厢，但可从车窗再次验证。",
                },
                {
                    "phase": "倒影",
                    "goal": "确认车窗倒影的报站规律",
                    "required_clues": ["window_shadow"],
                    "fail_forward": "错过倒影会触发精英检票员巡车并留下胸牌线索。",
                },
                {
                    "phase": "归站",
                    "goal": "用列车员胸牌选择封印或撤离路线",
                    "required_clues": ["conductor_badge"],
                    "fail_forward": "选择错误站台会推进终点时钟并开启最后一次撤离窗口。",
                },
            ],
            "side_quests": [
                {
                    "id": "return_ticket",
                    "name": "归还旧车票",
                    "goal": "找到乘客丢失的半张车票",
                    "required_clues": ["ticket_stub"],
                    "resolution": "在检票前把车票塞回七号座椅",
                    "fail_forward": "错过后乘客会变成新的报站噪声源",
                }
            ],
            "hidden_side_quests": [
                {
                    "id": "dead_station_map",
                    "name": "不存在的站台图",
                    "goal": "拼出废弃站台顺序",
                    "required_clues": ["station_map"],
                    "resolution": "在终点前按倒序读出三个站名",
                    "fail_forward": "地图会烧毁，但灰烬仍保留最后一个站名",
                }
            ],
            "hidden_endings": [
                {
                    "name": "列车员归站",
                    "required_clues": ["ticket_stub", "conductor_badge"],
                    "condition": "封印前归还旧车票并唤回列车员本名",
                }
            ],
            "clue_graph": [
                {
                    "id": "broadcast_error",
                    "public_text": "广播站名与线路图不一致。",
                    "obtain_methods": ["核对线路图", "询问不同车厢的任务者"],
                    "leads_to": ["window_shadow"],
                    "supports": "mainline",
                },
                {
                    "id": "window_shadow",
                    "public_text": "车窗倒影中的站名始终比广播晚一站。",
                    "obtain_methods": ["观察熄灯后的车窗", "用镜面物品反射报站屏"],
                    "leads_to": ["conductor_badge"],
                    "supports": "mainline",
                },
                {
                    "id": "conductor_badge",
                    "public_text": "胸牌背面刻着封闭终点的旧编号。",
                    "obtain_methods": ["从精英检票员身上取得", "在乘务室档案柜找到复制件"],
                    "leads_to": [],
                    "supports": "boss:seal",
                },
                {
                    "id": "ticket_stub",
                    "public_text": "半张车票属于已经消失的七号座乘客。",
                    "obtain_methods": ["检查座椅夹层", "交换清洁工的失物袋"],
                    "leads_to": ["conductor_badge"],
                    "supports": "side",
                },
                {
                    "id": "station_map",
                    "public_text": "废弃站名按倒序连成撤离口令。",
                    "obtain_methods": ["拼接撕碎地图", "记录三次错误广播"],
                    "leads_to": ["conductor_badge"],
                    "supports": "hidden/boss:evade",
                },
            ],
            "npc_arcs": {
                "林岑": {
                    "public_pressure": "她必须在终点前确认至少两次报站矛盾",
                    "private_goal": "保住自己的完整记录再决定是否共享",
                    "turning_point": "有人用真实线索换取她的报站表",
                    "exit_condition": "确认安全站台后独立撤离，或因误导被精英检票员锁定",
                },
                "周既白": {
                    "public_pressure": "倒计时越短，他越急于找人替自己试错",
                    "private_goal": "让别人承担第一次下车风险",
                    "turning_point": "他的假站台说法被车窗倒影证伪",
                    "exit_condition": "承认误导并合作，或被自己选择的假站台带走",
                },
            },
            "threat_clocks": [
                {
                    "id": "last_terminal",
                    "name": "终点逼近",
                    "max": 6,
                    "trigger": "误信广播、错过检票或长时间停留",
                    "escalation": "每两格封闭一节车厢",
                    "consequence": "满格后列车进入不可逆终点，仅剩隐藏撤离口令",
                    "visibility": "hidden",
                }
            ],
            "opening_contract": {
                "scene_anchors": ["末班车", "红色报站屏"],
                "initial_clue_id": "broadcast_error",
                "initial_anomaly": "红色报站屏显示不存在的站名",
            },
            "hard_constraints": ["关键线索至少有两种获取方式", "错过线索必须 fail-forward"],
        },
        "encounter_profile": {
            "common": [
                {
                    "id": "paper_passenger",
                    "name": "折票乘客",
                    "tier": "common",
                    "rank": "D",
                    "role": "在普通车厢制造错误人流",
                    "territory": "后三节普通车厢",
                    "behavior": "跟随错误广播起身并挤向车门",
                    "signs": ["口袋露出同号车票", "脚步声没有回音"],
                    "triggers": ["有人响应错误站名"],
                    "weaknesses": ["真实车票编号"],
                    "counterplay": ["留在座位", "出示正确车票"],
                    "ecology_links": ["替无面检票员筛选违规乘客"],
                    "public_text": "一群拿着相同车票、脚步无声的乘客。",
                }
            ],
            "elite": [
                {
                    "id": "faceless_conductor",
                    "name": "无面检票员",
                    "tier": "elite",
                    "rank": "C",
                    "role": "收割被普通乘客挤出安全区的人",
                    "territory": "乘务室与车厢连接处",
                    "behavior": "按错误广播后的座位空缺逐节查票",
                    "signs": ["剪票钳提前响三次", "连接门玻璃变黑"],
                    "triggers": ["有人无票换车厢", "终点时钟达到两格"],
                    "weaknesses": ["旧线路员工胸牌"],
                    "counterplay": ["补全车票", "避开连接门"],
                    "ecology_links": ["把违规记录送给终点站长"],
                    "public_text": "制服整洁却没有五官的检票员。",
                }
            ],
            "boss": {
                "id": "terminal_master",
                "name": "终点站长",
                "tier": "boss",
                "rank": "C",
                "role": "维持循环线路并吞没错误下车者",
                "territory": "不存在的终点站",
                "behavior": "借广播改写站名，并在终点时钟满格时接管所有车门",
                "signs": ["所有车窗同时映出站台", "广播出现两个人声重叠"],
                "triggers": ["终点时钟达到四格", "有人强行破坏驾驶室"],
                "default_invincible": True,
                "can_be_killed": False,
                "counterplay": ["封印旧站编号", "按倒序站名撤离"],
                "weaken_conditions": ["用列车员胸牌关闭一组广播"],
                "seal_conditions": ["在乘务室输入旧终点编号"],
                "escape_conditions": ["集齐废弃站名并倒序读出"],
                "resolution_paths": [
                    {
                        "method": "seal",
                        "required_clues": ["conductor_badge"],
                        "steps": ["取得旧线路胸牌", "在乘务室输入胸牌背面的终点编号"],
                        "failure_cost": "终点时钟推进两格并封闭乘务室",
                    },
                    {
                        "method": "evade",
                        "required_clues": ["station_map"],
                        "steps": ["拼出废弃站名顺序", "在假终点开门前倒序读出口令"],
                        "failure_cost": "撤离口令失效并触发一次全车追猎",
                    },
                ],
                "ecology_links": ["控制折票乘客制造人流", "读取无面检票员提交的违规记录"],
                "public_text": "只在所有车窗倒影中出现的旧制服站长。",
            },
            "spawn_rules": [
                {
                    "trigger": "错误广播结束",
                    "spawns": ["paper_passenger"],
                    "territory": "报站对应车厢",
                    "telegraph": "相同编号车票同时露出口袋",
                    "limit": "每次最多出现一组，正确报站后退场",
                }
            ],
            "ecology_rules": [
                {
                    "source": "paper_passenger",
                    "target": "faceless_conductor",
                    "relationship": "诱导并筛选",
                    "effect": "被挤出座位的人会进入精英检票员巡查名单",
                },
                {
                    "source": "faceless_conductor",
                    "target": "terminal_master",
                    "relationship": "供能",
                    "effect": "每次成功剪票都会推进终点时钟",
                },
            ],
            "territories": [
                {
                    "id": "passenger_cars",
                    "controller": "paper_passenger",
                    "entry_risk": "错误广播后人流会把人推向车门",
                    "safe_condition": "持正确编号车票并留在原座",
                }
            ],
            "balance_notes": "C 级生态；普通怪可规避，精英怪可削弱，Boss 只允许封印或撤离。",
        },
    }


class WenyouLogicRegressionTests(unittest.TestCase):
    def test_failed_tutorial_remains_retryable_even_with_legacy_pack_flag(self) -> None:
        wallet = wenyou._normalize_wallet(
            {
                "tutorial_completed": True,
                "tutorial_completed_at": "old-time",
                "tutorial_completion_result": "failed",
                "newbie_starter_pack_granted": True,
            }
        )
        self.assertFalse(wallet["tutorial_completed"])
        self.assertEqual(wallet["tutorial_completed_at"], "")
        self.assertTrue(wenyou._should_offer_tutorial(1, wallet))

    def test_tutorial_settlement_rewards_both_personal_accounts_and_bags(self) -> None:
        session = _session(tutorial=True)
        session["history"].extend(
            [
                {"role": "player1", "content": "我观察红灯。"},
                {"role": "player2", "content": "我检查白色光轨。"},
            ]
        )
        wallet = wenyou._normalize_wallet(
            {
                "points": 10,
                "wallets": {
                    "player1": {"points": 10, "debts": 0},
                    "player2": {"points": 50, "debts": 0},
                },
            }
        )
        with patch.object(wenyou, "_load_wenyou_wallet", return_value=wallet), patch.object(
            wenyou, "_save_wenyou_wallet"
        ), patch.object(wenyou, "_roll_settlement_rewards", return_value=[]):
            settlement = wenyou._grant_settlement_reward(1, session, result="standard_clear", rating="B")

        p1_reward = settlement["player_rewards"]["player1"]
        p2_reward = settlement["player_rewards"]["player2"]
        self.assertEqual(p1_reward["points_delta"], p2_reward["points_delta"])
        self.assertEqual(
            wenyou._player_account(wallet, "player2")["points"] - wenyou._player_account(wallet, "player1")["points"],
            40,
        )
        self.assertTrue(settlement["newbie_starter_pack"]["granted"])
        for player_id in wenyou._WENYOU_PLAYER_IDS:
            inventory = wenyou._get_player_inventory(wallet, player_id)
            self.assertGreaterEqual(len(inventory), 2)
            self.assertEqual(
                {item.get("id") for item in inventory},
                set(wenyou._WENYOU_TUTORIAL_GIFT_ITEM_IDS),
            )

    def test_gm_context_lists_inventory_by_owner(self) -> None:
        session = _session()
        session["stats"]["inventories"] = {
            "player1": [{"id": "p1_item", "name": "红色钥匙"}],
            "player2": [{"id": "p2_item", "name": "旧对讲机"}],
            "task_items": [{"id": "task_item", "name": "门禁记录"}],
        }
        session["stats"]["inventory"] = session["stats"]["inventories"]["player1"]
        context = compose_gm_context(session)
        self.assertIn("辛玥：红色钥匙", context)
        self.assertIn("渡：旧对讲机", context)
        self.assertIn("队伍任务物：门禁记录", context)

    def test_candidate_expansion_persists_variable_tasker_cast(self) -> None:
        candidate = {
            "id": "cand-taskers",
            "title": "停运末班车",
            "instance_genre": "规则怪谈",
            "difficulty": "C",
            "premise": "封闭列车在不存在的站台间循环。",
            "core_task": "确认安全下车条件。",
            "survival_hook": "广播会故意报错站名。",
            "risk": "错误下车会被留在废弃站台。",
            "twist": "列车员并不属于列车。",
        }

        def fake_deepseek(messages, system="", temperature=0.7, timeout_seconds=120):
            prompt = str((messages or [{}])[0].get("content") or "")
            if "核心设定短稿" in prompt:
                return "列车在午夜后进入废弃线路，任务者必须交叉验证广播和车窗倒影。"
            if "完整结构设计" in prompt:
                return json.dumps(_valid_candidate_design(), ensure_ascii=False)
            if "开场正文" in prompt:
                return (
                    "白光散去，你站在摇晃的末班车里。"
                    "头顶的红色报站屏显示不存在的站名，车窗里却映着另一处站台。"
                )
            self.fail(f"unexpected prompt: {prompt[:80]}")

        with patch.object(wenyou, "call_wenyou_deepseek", side_effect=fake_deepseek):
            framework, error = wenyou.generate_framework_from_candidate(candidate)

        self.assertIsNone(error)
        self.assertIsNotNone(framework)
        self.assertEqual(framework["player_count"], 2)
        self.assertEqual(framework["tasker_total"], 4)
        self.assertEqual([item["name"] for item in framework["npc_taskers"]], ["林岑", "周既白"])
        self.assertEqual(
            framework["gm_secret"]["npc_private_state"]["周既白"]["intent"],
            "利用其他任务者承担第一次下车风险",
        )
        self.assertEqual(framework["instance_blueprint"]["side_quests"][0]["id"], "return_ticket")
        self.assertEqual(framework["instance_blueprint"]["opening_contract"]["initial_clue_id"], "broadcast_error")
        self.assertEqual(framework["encounter_profile"]["common"][0]["id"], "paper_passenger")
        self.assertEqual(
            framework["encounter_profile"]["boss"]["resolution_paths"][1]["method"],
            "evade",
        )
        gm_blueprint = json.loads(wenyou._format_blueprint_for_gm(framework))
        self.assertEqual(
            gm_blueprint["encounter_profile"]["boss"]["resolution_paths"][1]["method"],
            "evade",
        )
        session = wenyou._new_session(framework)
        self.assertEqual(session["clocks"][0]["id"], "last_terminal")
        self.assertEqual(session["clocks"][0]["value"], 0)
        regiment = wenyou._format_tasker_regiment_for_gm(framework)
        self.assertIn("自己的通关、生存与结算", regiment)
        self.assertNotIn("主神档案尚未同步", regiment)

    def test_semantic_validation_rejects_boss_without_executable_paths(self) -> None:
        design = _valid_candidate_design()
        design["opening"] = (
            "你站在末班车里，红色报站屏显示不存在的站名，"
            "车窗倒影里是另一处站台。"
        )
        design["encounter_profile"]["boss"]["resolution_paths"] = []
        errors = wenyou._generated_framework_semantic_errors(design)
        self.assertIn("Boss 缺少至少两条可执行解法", errors)

    def test_semantic_validation_rejects_opening_that_ignores_blueprint(self) -> None:
        design = _valid_candidate_design()
        design["opening"] = "白光散去，你站在一条陌生走廊里。"
        errors = wenyou._generated_framework_semantic_errors(design)
        self.assertIn("开场未包含至少两个蓝图场景锚点", errors)
        self.assertIn("开场未包含蓝图 initial_anomaly", errors)

    def test_candidate_tasker_cast_rejects_placeholder_profiles(self) -> None:
        cast, error = wenyou._normalize_candidate_tasker_cast(
            {
                "player_count": 2,
                "tasker_total": 3,
                "npc_taskers": [
                    {
                        "name": "任务者3",
                        "intent": "等待玩家行动",
                        "blurb": "主神档案尚未同步",
                    }
                ],
                "npc_private_state": {
                    "任务者3": {
                        "stance": "unknown",
                        "intent": "等待",
                        "trouble_chance": 0,
                        "trigger": "无",
                    }
                },
            }
        )
        self.assertIsNone(cast)
        self.assertIn("真实姓名", error)

    def test_forced_candidate_requires_normal_taskers(self) -> None:
        cast, error = wenyou._normalize_candidate_tasker_cast(
            {
                "player_count": 2,
                "tasker_total": 2,
                "npc_taskers": [],
                "npc_private_state": {},
            },
            forced=True,
        )
        self.assertIsNone(cast)
        self.assertIn("至少需要 2 名正常任务者", error)

    def test_custom_framework_rejects_missing_tasker_profiles_without_inventing_them(self) -> None:
        raw_framework = {
            "instance_code": "CUSTOM-1",
            "instance_name": "失名旅馆",
            "instance_genre": "剧情解密",
            "difficulty": "D",
            "player_count": 2,
            "tasker_total": 3,
            "world": "旅馆里所有住客的姓名都被划掉了。",
            "conflict": "确认自己的房号并找到出口。",
            "player1_name": "玩家一",
            "player1_role": "新任务者",
            "player2_name": "玩家二",
            "player2_role": "新任务者",
            "npc_taskers": [],
            "gm_secret": {"npc_private_state": {}},
            "opening": "白光散去，你站在旅馆前台。",
        }
        with patch.object(
            wenyou,
            "call_wenyou_deepseek",
            return_value=json.dumps(raw_framework, ensure_ascii=False),
        ):
            framework, error = wenyou.generate_framework_custom("失名旅馆")
        self.assertIsNone(framework)
        self.assertIn("任务者编制无效", error)
        self.assertIn("数量不一致", error)

    def test_custom_framework_rejects_semantically_incomplete_blueprint(self) -> None:
        raw_framework = {
            "instance_code": "CUSTOM-2",
            "instance_name": "空壳病院",
            "instance_genre": "剧情解密",
            "difficulty": "D",
            "player_count": 2,
            "tasker_total": 2,
            "world": "夜间病院封锁了所有出口。",
            "conflict": "确认封锁原因并找到出口。",
            "player1_name": "玩家一",
            "player1_role": "新任务者",
            "player2_name": "玩家二",
            "player2_role": "新任务者",
            "npc_taskers": [],
            "gm_secret": {"npc_private_state": {}},
            "instance_blueprint": {
                "mainline": [{"phase": "开场", "goal": "进入病院"}],
                "side_quests": [],
                "hidden_side_quests": [],
                "clue_graph": [],
            },
            "encounter_profile": {"common": [], "elite": [], "boss": {}, "spawn_rules": []},
            "opening": "白光散去，你站在一条陌生走廊里。",
        }
        with patch.object(
            wenyou,
            "call_wenyou_deepseek",
            return_value=json.dumps(raw_framework, ensure_ascii=False),
        ):
            framework, error = wenyou.generate_framework_custom("空壳病院")
        self.assertIsNone(framework)
        self.assertIn("语义验收", error)
        self.assertIn("支线", error)

    def test_custom_framework_accepts_closed_blueprint_and_monster_ecology(self) -> None:
        raw_framework = _valid_candidate_design()
        raw_framework.update(
            {
                "instance_code": "CUSTOM-3",
                "instance_name": "停运末班车",
                "instance_genre": "规则怪谈",
                "genre_note": "通过广播与倒影差异验证站台规则。",
                "difficulty": "C",
                "world": "封闭列车在不存在的站台间循环。",
                "player1_name": "玩家一",
                "player1_role": "任务者",
                "player2_name": "玩家二",
                "player2_role": "任务者",
                "conflict": "确认安全下车条件。",
                "failure_hint": "错误下车会被留在废弃站台。",
                "reward_hint": "按完成度结算。",
                "opening": (
                    "白光散去，你站在摇晃的末班车里。"
                    "头顶的红色报站屏显示不存在的站名，车窗里映着另一处站台。"
                ),
            }
        )
        raw_framework["public"].update(
            {
                "instance_name": "停运末班车",
                "genre": ["规则怪谈"],
                "difficulty": "C",
                "public_task": "确认安全下车条件。",
            }
        )
        raw_framework["gm_secret"]["npc_private_state"] = raw_framework.pop("npc_private_state")
        with patch.object(
            wenyou,
            "call_wenyou_deepseek",
            return_value=json.dumps(raw_framework, ensure_ascii=False),
        ):
            framework, error = wenyou.generate_framework_custom("停运末班车")
        self.assertIsNone(error)
        self.assertEqual(framework["instance_blueprint"]["side_quests"][0]["id"], "return_ticket")
        self.assertEqual(framework["encounter_profile"]["ecology_rules"][0]["source"], "paper_passenger")

    def test_runtime_does_not_invent_placeholder_taskers(self) -> None:
        framework = wenyou._framework_for_runtime(
            {
                "instance_name": "残缺旧档",
                "player_count": 2,
                "tasker_total": 6,
                "npc_taskers": [],
            }
        )
        self.assertEqual(framework["tasker_total"], 2)
        self.assertEqual(framework["npc_taskers"], [])

    def test_framework_prompt_does_not_hardcode_player_identity_or_appearance(self) -> None:
        prompt_text = "\n".join(
            [
                wenyou._FRAMEWORK_SYSTEM,
                wenyou._framework_prompt_random(
                    {
                        "difficulty": "D",
                        "instance_genre": "剧情解密",
                        "world": "旧宅",
                        "conflict": "调查",
                        "role_a": "",
                        "role_b": "",
                    }
                ),
                wenyou._framework_prompt_custom("民国旧宅"),
            ]
        )
        for forbidden in ("辛玥", "黑色长发黑眼", "银色短发", "一米六多", "一米八多", "薄肌"):
            self.assertNotIn(forbidden, prompt_text)

    def test_item_requirements_use_holder_stats_not_team_maximum(self) -> None:
        session = _session()
        session["stats"]["player1"].update({"rank": "S", "level": 10, "str": 30})
        session["stats"]["player2"].update({"rank": "D", "level": 1, "str": 10})
        item = {"name": "封印重刃", "seal_rank": "A", "requirements": {"level_min": 5, "str_min": 20}}
        self.assertEqual(wenyou._item_requirement_blockers(item, session, "player1"), [])
        blockers = wenyou._item_requirement_blockers(item, session, "player2")
        self.assertIn("需达到 A 阶", blockers)
        self.assertIn("需等级 5", blockers)
        self.assertIn("需力量 20", blockers)

    def test_core_ability_samples_only_the_requested_player(self) -> None:
        session = _session(tutorial=True)
        session["history"] = [
            {"role": "gm", "content": "怪物攻击，你只能战斗。"},
            {"role": "player1", "content": "我观察门缝并记录线索。"},
            {"role": "player2", "content": "我冲过去砸门。"},
        ]
        source = wenyou._core_ability_text_source(session, "player1")
        scores = wenyou._score_core_ability_archetypes(session, "player1")
        self.assertIn("观察门缝", source)
        self.assertNotIn("怪物攻击", source)
        self.assertNotIn("砸门", source)
        self.assertGreater(scores["observe"], 0)
        self.assertEqual(scores["combat"], 0)

    def test_long_term_growth_round_trips_between_wallet_and_new_session(self) -> None:
        wallet = wenyou._normalize_wallet({})
        wallet["players"]["player1"].update({"level": 4, "exp": 35, "rank": "C", "str": 14})
        wallet["players"]["player2"].update(
            {
                "level": 3,
                "exp": 20,
                "rank": "C",
                "agi": 13,
                "core_ability": {"id": "core_escape", "name": "退路直觉", "rarity": "D"},
            }
        )
        session = _session()
        wenyou._sync_session_players_with_wallet(session, wallet)
        self.assertEqual(session["stats"]["player1"]["level"], 4)
        self.assertEqual(session["stats"]["player1"]["str"], 14)
        self.assertEqual(session["stats"]["player2"]["rank"], "C")
        self.assertEqual(session["stats"]["player2"]["core_ability"]["id"], "core_escape")

        session["stats"]["player2"]["agi"] = 14
        session["stats"]["player2"]["unspent_attribute_points"] = 2
        wenyou._sync_wallet_players_from_session(wallet, session, ["player2"])
        self.assertEqual(wallet["players"]["player2"]["agi"], 14)
        self.assertEqual(wallet["players"]["player2"]["unspent_attribute_points"], 2)

    def test_same_user_mutations_are_serialized(self) -> None:
        state = {"active": 0, "maximum": 0}
        guard = threading.Lock()

        @wenyou._serialized_user_operation
        def mutate(user_id: int) -> None:
            with guard:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
            time.sleep(0.03)
            with guard:
                state["active"] -= 1

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: mutate(99), range(4)))
        self.assertEqual(state["maximum"], 1)

    @unittest.skipIf(wenyou.fcntl is None, "fcntl unavailable")
    def test_same_user_mutations_are_serialized_across_processes(self) -> None:
        ctx = multiprocessing.get_context("fork")
        ready = ctx.Value("i", 0)
        active = ctx.Value("i", 0)
        maximum = ctx.Value("i", 0)
        guard = ctx.Lock()
        start_event = ctx.Event()
        processes = [
            ctx.Process(target=_cross_process_lock_probe, args=(101, ready, start_event, active, maximum, guard))
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        deadline = time.time() + 3
        while ready.value < 2 and time.time() < deadline:
            time.sleep(0.01)
        start_event.set()
        for process in processes:
            process.join(3)
        self.assertEqual([process.exitcode for process in processes], [0, 0])
        self.assertEqual(maximum.value, 1)

    def test_nonstackable_shop_item_cannot_be_bought_twice(self) -> None:
        item = {"id": "unique_test", "name": "唯一测试物", "price": 100, "stackable": False, "rarity": "D"}
        wallet = wenyou._normalize_wallet(
            {
                "points": 500,
                "inventory": [{**item, "uid": "owned", "quantity": 1}],
            }
        )
        with patch.object(wenyou.r2_store, "get_wenyou_session", return_value=None), patch.object(
            wenyou, "_load_wenyou_wallet", return_value=wallet
        ), patch.object(wenyou, "_shop_offer_items", return_value=[item]), patch.object(
            wenyou, "get_shop_view", return_value={"active": False}
        ), patch.object(wenyou, "_save_wenyou_wallet"):
            ok, message, _ = wenyou.buy_shop_item(1, item_id=item["id"], actor_id="player1")
        self.assertFalse(ok)
        self.assertIn("已有", message)
        self.assertEqual(wenyou._player_account(wallet, "player1")["points"], 500)

    def test_invalid_actor_never_falls_back_to_player_one(self) -> None:
        ok, message, payload = wenyou.buy_shop_item(1, item_id="anything", actor_id="gm")
        self.assertFalse(ok)
        self.assertEqual(payload["error_code"], "INVALID_ACTOR")
        self.assertIn("无效", message)
        ok, message = wenyou.cmd_record_action(1, "替玩家行动", player="gm")
        self.assertFalse(ok)
        self.assertIn("无效", message)
        self.assertEqual(wenyou.compose_ai_player_context(_session(), actor_id="gm")["error_code"], "INVALID_ACTOR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
