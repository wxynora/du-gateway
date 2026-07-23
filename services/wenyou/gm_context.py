import copy
import json
from typing import Any, Optional

from services.wenyou.common import _compact_text, _normalize_difficulty
from services.wenyou.constants import _WENYOU_TUTORIAL_INSTANCE_ID
from services.wenyou.runtime_state import (
    _default_player_stats,
    _framework_for_runtime,
    _normalize_encounter_profile,
    _normalize_instance_blueprint,
    _normalize_player_count,
    _normalize_tasker_total,
    _normalize_text_list,
)


def _format_tasker_regiment_for_gm(fw: dict) -> str:
    """写入 GM system：难度 + tasker_total 2-13 编制说明 + NPC 档案。"""
    def _show_name(real_name: str, instance_name: str) -> str:
        rn = str(real_name or "").strip()
        inn = str(instance_name or "").strip()
        if inn and inn != rn:
            return f"{rn}（{inn}）"
        return rn

    diff = _normalize_difficulty(fw.get("difficulty"))
    p1n = _show_name(fw.get("player1_name") or "玩家一", fw.get("player1_instance_name") or "")
    p2n = _show_name(fw.get("player2_name") or "玩家二", fw.get("player2_instance_name") or "")
    pc = _normalize_player_count(fw)
    total = _normalize_tasker_total(fw, pc)
    npc_count = max(0, total - pc)
    lines = [
        f"- 难度等级：**{diff}**（D 最易，S 最险；越高则环境越危险、规则越苛刻，NPC 中越容易混有「大佬」或「炮灰」，恶意与博弈也更强）。",
        f"- 编制：tasker_total={total}，当前玩家角色 {pc} 名（玩家一「{p1n}」、玩家二「{p2n}」），NPC 任务者 {npc_count} 名，须在同一副本规则下互动（NPC 可分批登场、可退场或死亡，但须有因果，不得无交代消失）。",
        "- NPC 可与难度相应（内部定位可区分新人/炮灰/老练/大佬），但这些定位不得直接告知玩家；玩家只能通过剧情表现自行判断。注意：NPC 真实立场对玩家默认不可知，不得在设定里直给“好/坏”结论；禁止过度血腥虐待描写。",
        "",
        "NPC 任务者档案（须在剧情中落实）：",
    ]
    if npc_count <= 0:
        return "\n".join(
            [
                f"- 难度等级：**{diff}**（D 最易，S 最险）。",
                f"- 编制：tasker_total={total}，当前玩家角色 {pc} 名（玩家一「{p1n}」、玩家二「{p2n}」），没有其他任务者 NPC。",
                "- 本局只围绕真实玩家角色推进，不要临时生成同场任务者，不要写陌生任务者名单。",
            ]
        )
    for i, n in enumerate(fw.get("npc_taskers") or []):
        if isinstance(n, dict):
            nshow = _show_name(n.get("name", ""), n.get("instance_name", ""))
            status = n.get("status") or "alive"
            intent = n.get("intent") or "未公开"
            lines.append(
                f"  · {i+1}. 「{nshow}」｜{n.get('tier_note', '')}｜公开信息：{n.get('blurb', '')}（公开态度：{n.get('stance', '未知')}；状态：{status}；意图：{intent}）"
            )
    return "\n".join(lines)


def _format_tutorial_guides_for_gm(fw: dict) -> str:
    if not (fw.get("is_tutorial") or str(fw.get("tutorial_id") or "") == _WENYOU_TUTORIAL_INSTANCE_ID):
        return ""
    guides = _normalize_text_list(fw.get("tutorial_guides"), 220, 12)
    if not guides:
        guides = [
            "只在关键节点用一两句【主神提示】引导，不要整段教学说明。",
            "第一轮优先提示可用“观察 / 检查 / 移动 / 使用道具”等基础行动。",
            "玩家卡住时提示可查看任务、背包和角色面板；不要替玩家做选择。",
        ]
    body = "\n".join(f"- {line}" for line in guides)
    return "\n## 新手副本引导（本局额外规则）\n" + body


def _format_forced_instance_guidance_for_gm(session: dict, fw: dict) -> str:
    forced = session.get("forced_instance") if isinstance(session.get("forced_instance"), dict) else None
    if not forced or str(forced.get("mode") or "") != "npc_labor":
        return ""
    player1 = str(fw.get("player1_name") or "玩家一").strip() or "玩家一"
    player2 = str(fw.get("player2_name") or "玩家二").strip() or "玩家二"
    return f"""
## 惩罚副本 · 临时 NPC 模式（本局额外规则）
- 本局仍是无限流副本：存在正常任务者队伍、规则、线索、危险、通关目标和主神结算。
- 玩家一「{player1}」和玩家二「{player2}」都不是正常任务者，而是一起被系统塞入副本世界的原住民 NPC；两人的公开姓名必须分别使用「{player1}」「{player2}」，不得另起本名、化名、小名或真实姓名。
- 正常任务者才是表层通关队伍，他们的任务可以围绕玩家一 NPC、玩家二 NPC，或两人共同牵涉的生死、秘密、病症、嫌疑、继承权、献祭、异常状态展开。
- 玩家一与玩家二的共同目标是演好 NPC，用符合身份的反应、关系、线索、阻碍或求助推动正常任务者进度；不要把任何一人写成自己通关、打 Boss、找出口的普通任务者。
- 每个关键阶段都要让正常任务者有可见行动压力：试探规则、争执、误判、隐瞒线索、求助玩家 NPC、利用玩家 NPC 或因错误选择受伤/死亡。
- 规则必须通过行动验证，不要一次性公开完整答案；错过线索时用威胁推进、身份被怀疑、任务者伤亡或异常加压继续剧情。
- 主神/系统只在开场、阶段变化、违规、倒计时或结算预警时短促出现，保持压迫感，不要写成长篇说明书。
- 如果任一玩家代号与副本家族、时代、地域或身份结构有违和，不要改名消除；把违和写成剧情钩子，如随母姓、收养、过继、家产侵占、族谱涂改、冒名顶替或异常保留姓名。
- NPC 身份越核心，危险越高；Boss/异常阵营必须有理由控制、利用、杀死、替换或误导玩家 NPC。禁止把核心 NPC 写成安全旁观者。
- 玩家一和玩家二都不能直接说出玩家、任务者、清算对象、外来者、系统或副本真相；不能直接剧透答案、带队通关或跳出 NPC 身份解释机制。
- 正文仍固定玩家一视角；玩家二通过玩家一能看到、听到、交流到的方式出场，不要写成上帝视角双主角。
- 债务、污染、复活、契约等只作为后端清算原因；叙事里不要把它们写成剧情主题或系统工单。
""".strip()


def _format_blueprint_for_gm(fw: dict) -> str:
    bp = _normalize_instance_blueprint(fw.get("instance_blueprint"), fw)
    secret = fw.get("gm_secret") if isinstance(fw.get("gm_secret"), dict) else {}
    payload = {
        "instance_blueprint": bp,
        "gm_secret_summary": {
            "true_rules": secret.get("true_rules") or [],
            "false_rules": secret.get("false_rules") or [],
            "npc_goals": secret.get("npc_goals") or {},
            "npc_private_state": secret.get("npc_private_state") or {},
            "hidden_endings": secret.get("hidden_endings") or [],
        },
        "encounter_profile": _normalize_encounter_profile(fw.get("encounter_profile")),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))[:4000]


def _gm_list_text(items: Any, *, limit: int = 8, item_limit: int = 180) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            parts = []
            title = _compact_text(item.get("title") or item.get("name") or item.get("id"), 80)
            status = _compact_text(item.get("status") or item.get("type") or item.get("public_status"), 40)
            progress_text = (item.get("progress") or {}).get("text") if isinstance(item.get("progress"), dict) else ""
            text = _compact_text(
                item.get("public_text")
                or item.get("text")
                or item.get("reason")
                or progress_text
                or item.get("desc")
                or item.get("blurb"),
                item_limit,
            )
            if title:
                parts.append(title)
            if status:
                parts.append(f"({status})")
            if text and text != title:
                parts.append(text)
            line = " ".join(parts).strip()
        else:
            line = _compact_text(item, item_limit)
        if line:
            out.append(line)
    return out


def _gm_mapping_text(items: Any, *, limit: int = 8, item_limit: int = 180) -> list[str]:
    if isinstance(items, dict):
        return _gm_list_text(list(items.values()), limit=limit, item_limit=item_limit)
    return _gm_list_text(items, limit=limit, item_limit=item_limit)


def _gm_inventory_owner_lines(items: Any, player1_name: str, player2_name: str) -> list[str]:
    if not isinstance(items, dict):
        return []
    if not any(isinstance(items.get(key), list) and items.get(key) for key in ("player1", "player2", "task_items")):
        return []
    lines: list[str] = []
    for key, label in (("player1", player1_name), ("player2", player2_name), ("task_items", "队伍任务物")):
        names = _gm_list_text(items.get(key), limit=14, item_limit=80)
        lines.append(f"{label}：{'、'.join(names) if names else '无'}")
    return lines


def _gm_join(items: Any, *, empty: str = "无", limit: int = 8, item_limit: int = 180) -> str:
    lines = _gm_list_text(items, limit=limit, item_limit=item_limit)
    return "；".join(lines) if lines else empty


def _gm_join_mapping(items: Any, *, empty: str = "无", limit: int = 8, item_limit: int = 180) -> str:
    lines = _gm_mapping_text(items, limit=limit, item_limit=item_limit)
    return "；".join(lines) if lines else empty


def _gm_player_summary(player: Any, fallback_name: str) -> str:
    p = copy.deepcopy(player) if isinstance(player, dict) else _default_player_stats()
    name = _compact_text(p.get("display_name") or fallback_name, 40)
    core = p.get("core_ability") if isinstance(p.get("core_ability"), dict) else None
    ability = _compact_text(core.get("name") if core else "", 60) or "无"
    conditions = _gm_join(p.get("conditions"), empty="无", limit=6, item_limit=40)
    return (
        f"{name}：HP {int(p.get('hp') or 0)}/{int(p.get('hp_max') or 0)}，"
        f"SAN {int(p.get('san') or 0)}/{int(p.get('san_max') or 0)}，"
        f"精神力 {int(p.get('spi_current') or 0)}/{int(p.get('spi_max') or 0)}，"
        f"Lv{int(p.get('level') or 1)}·{p.get('rank') or 'D'}阶，"
        f"力{int(p.get('str') or 0)}/体{int(p.get('con') or p.get('vit') or 0)}/敏{int(p.get('agi') or 0)}/"
        f"智{int(p.get('int') or p.get('wis') or 0)}/精{int(p.get('spi') or 0)}/运{int(p.get('luk') or 0)}，"
        f"核心能力：{ability}，状态：{conditions}"
    )


def _gm_card_context(card: Any) -> list[str]:
    data = card if isinstance(card, dict) else {}
    if not data:
        return []
    cur = data.get("current_instance") if isinstance(data.get("current_instance"), dict) else {}
    recent = [x for x in (data.get("recent_rounds") or []) if isinstance(x, dict)]
    milestones = _normalize_text_list(data.get("story_milestones"), 220, 8)
    questions = _normalize_text_list(data.get("open_questions"), 180, 6)
    if not cur and not recent and not milestones and not questions:
        return []
    lines: list[str] = ["## 连续性卡片（模型压缩摘要）"]
    if cur:
        lines.append(
            "- 当前卡片："
            f"{_compact_text(cur.get('instance'), 120) or '未知副本'}｜"
            f"{_compact_text(cur.get('genre'), 40) or '未知类型'}｜"
            f"难度 {cur.get('difficulty') or '-'}｜阶段 {_compact_text(cur.get('phase'), 40) or '-'}"
        )
        if cur.get("task"):
            lines.append(f"- 卡片任务：{_compact_text(cur.get('task'), 220)}")
        if cur.get("clues"):
            lines.append(f"- 卡片已知线索：{_gm_join(cur.get('clues'), limit=8, item_limit=160)}")
    if milestones:
        lines.append("- 长期剧情节点：" + "；".join(milestones[:6]))
    if questions:
        lines.append("- 待验证问题：" + "；".join(questions[:6]))
    if recent:
        lines.append("- 最近回合摘要：")
        for item in recent[:5]:
            p1 = _compact_text(item.get("player1_action"), 140) or "无"
            p2 = _compact_text(item.get("player2_action"), 140) or "无"
            gm = _compact_text(item.get("gm_result"), 240) or "无"
            lines.append(f"  · {p1} / {p2} => {gm}")
    return lines


def _gm_history_window(history: Any, *, limit: int = 6) -> list[str]:
    if not isinstance(history, list):
        return []
    out: list[str] = []
    for item in history[-limit:]:
        if not isinstance(item, dict):
            continue
        role = _compact_text(item.get("role"), 30)
        content = _compact_text(item.get("content"), 260)
        if role and content:
            out.append(f"{role}：{content}")
    return out


def compose_gm_context(
    session: Any,
    *,
    wenyou_card: Optional[dict] = None,
    public_state: Optional[dict] = None,
    rules_state: Optional[dict] = None,
    current_round: Optional[dict] = None,
    history_limit: int = 6,
) -> str:
    """Build the compact GM context block from runtime state and the continuity card.

    The block is prompt-only: GM may use it for continuity, but state facts still come
    from the backend runtime/rules state and later state patches.
    """
    sess = session if isinstance(session, dict) else {}
    fw = _framework_for_runtime(sess.get("framework") or {})
    stats = sess.get("stats") if isinstance(sess.get("stats"), dict) else {}
    runtime = sess.get("runtime_state") if isinstance(sess.get("runtime_state"), dict) else {}
    public = public_state if isinstance(public_state, dict) else runtime.get("public_state") if isinstance(runtime.get("public_state"), dict) else {}
    rules = rules_state if isinstance(rules_state, dict) else runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    player1 = stats.get("player1") if isinstance(stats.get("player1"), dict) else {}
    player2 = stats.get("player2") if isinstance(stats.get("player2"), dict) else {}
    p1_name = _compact_text(player1.get("display_name") or fw.get("player1_name") or "玩家一", 40)
    p2_name = _compact_text(player2.get("display_name") or fw.get("player2_name") or "玩家二", 40)
    phase = _compact_text(sess.get("phase") or (stats.get("phase") if isinstance(stats, dict) else ""), 40) or "instance_running"
    tasks = public.get("public_tasks") if isinstance(public.get("public_tasks"), list) else []
    clues = public.get("discovered_clues") if isinstance(public.get("discovered_clues"), list) else []
    locations = public.get("known_locations") if isinstance(public.get("known_locations"), list) else []
    rules_visible = public.get("visible_rules") if isinstance(public.get("visible_rules"), list) else []
    npcs = public.get("visible_npcs") if isinstance(public.get("visible_npcs"), list) else []
    monsters = public.get("visible_monsters") if isinstance(public.get("visible_monsters"), list) else []
    current_location = "副本内"
    if locations and isinstance(locations[0], dict):
        current_location = _compact_text(locations[0].get("name") or locations[0].get("public_text"), 80) or current_location
    elif public.get("scene_summary"):
        current_location = "当前场景"
    clocks = sess.get("clocks") if isinstance(sess.get("clocks"), list) else []
    clock_lines = []
    for clock in clocks[:6]:
        if not isinstance(clock, dict):
            continue
        name = _compact_text(clock.get("name") or clock.get("id"), 60)
        max_value = max(1, int(clock.get("max") or 1))
        value = max(0, int(clock.get("value") or 0))
        visibility = _compact_text(clock.get("visibility") or "hidden", 20)
        if name:
            clock_lines.append(f"{name} {value}/{max_value}({visibility})")
    team_channel = sess.get("team_channel") if isinstance(sess.get("team_channel"), dict) else {}
    signal = team_channel.get("signal") if isinstance(team_channel.get("signal"), dict) else {}
    signal_label = _compact_text(signal.get("label") or signal.get("status"), 40) if signal else ""
    inventory_lines = _gm_inventory_owner_lines(stats.get("inventories"), p1_name, p2_name)
    if not inventory_lines:
        inventory_lines = _gm_inventory_owner_lines(rules.get("inventories"), p1_name, p2_name)
    if not inventory_lines:
        legacy_items = _gm_list_text(rules.get("inventory") or stats.get("inventory"), limit=14, item_limit=80)
        inventory_lines = [f"{p1_name}：{'、'.join(legacy_items) if legacy_items else '无'}"]
    round_lines = []
    if isinstance(current_round, dict):
        p1 = _compact_text(current_round.get("player1"), 260)
        p2 = _compact_text(current_round.get("player2"), 260)
        if p1 or p2:
            round_lines.append(f"- {p1_name}：{p1 or '本轮暂无行动'}")
            round_lines.append(f"- {p2_name}：{p2 or '本轮暂无行动'}")
    lines = [
        "[WENYOU_GM_CONTEXT]",
        "用途：这是后端每轮生成的压缩上下文。GM 只用它维持连续性；精确数值、背包、任务和结算以后端 runtime_state/rules_state 为准。",
        "不要把本块原文输出给玩家；不要照抄 JSON 或面板；只把玩家可感知的信息写进正文。",
        "",
        "## 当前副本状态",
        f"- game_id：{_compact_text(sess.get('gameId'), 80) or '-'}",
        f"- 副本：{_compact_text(fw.get('instance_code'), 40)}｜{_compact_text(fw.get('instance_name'), 80) or '未命名'}｜{_compact_text(fw.get('instance_genre'), 40)}｜难度 {fw.get('difficulty') or '-'}",
        f"- 阶段：{phase}；当前位置：{current_location}；公开威胁：{_compact_text(public.get('public_threat'), 80) or '平稳'}",
        f"- 当前任务：{_gm_join(tasks, limit=6, item_limit=150) or _compact_text(fw.get('conflict'), 180) or '暂无'}",
        f"- 场景摘要：{_compact_text(public.get('scene_summary') or fw.get('world'), 260) or '暂无'}",
        f"- 公开规则：{_gm_join(rules_visible, limit=8, item_limit=160)}",
        f"- 已知线索：{_gm_join(clues, limit=10, item_limit=170)}",
        f"- 已知地点：{_gm_join(locations, limit=8, item_limit=140)}",
        f"- 可见 NPC：{_gm_join(npcs, limit=10, item_limit=140)}",
        f"- 可见怪物/异常：{_gm_join(monsters, limit=8, item_limit=160)}",
        f"- 威胁时钟（可隐藏）：{'；'.join(clock_lines) if clock_lines else '无'}",
        "",
        "## 玩家与资源",
        f"- {_gm_player_summary(player1, p1_name)}",
        f"- {_gm_player_summary(player2, p2_name)}",
        f"- 背包/任务物：{'；'.join(inventory_lines) if inventory_lines else '无'}",
        f"- 上轮规则结果：{_compact_text(public.get('last_rules_result'), 260) or '无'}",
    ]
    if signal_label:
        lines.append(f"- 对讲机状态：{signal_label}；风险：{_compact_text(signal.get('risk'), 160) or '无'}")
    forced = sess.get("forced_instance") if isinstance(sess.get("forced_instance"), dict) else None
    if forced:
        lines.append(f"- 强制/惩罚副本：{json.dumps(forced, ensure_ascii=False, separators=(',', ':'))[:700]}")
    if round_lines:
        lines.extend(["", "## 本轮待结算行动（只作对齐，最终行动见最新 user 消息）", *round_lines])
    card_lines = _gm_card_context(wenyou_card)
    if card_lines:
        lines.extend(["", *card_lines])
    rules_private = [
        f"任务进度：{_gm_join_mapping(rules.get('task_progress'), limit=8, item_limit=160)}",
        f"规则线索：{_gm_join_mapping(rules.get('clue_state'), limit=8, item_limit=160)}",
        f"地点状态：{_gm_join_mapping(rules.get('location_state'), limit=6, item_limit=140)}",
        f"NPC 状态：{_gm_join_mapping(rules.get('npc_state'), limit=8, item_limit=140)}",
        f"怪物实例：{_gm_join(rules.get('monster_instances'), limit=8, item_limit=160)}",
    ]
    lines.extend(["", "## 后端规则态摘要（内部，不要直接剧透）", *["- " + x for x in rules_private]])
    history_lines = _gm_history_window(sess.get("history"), limit=history_limit)
    if history_lines:
        lines.extend(["", "## 最近原始历史窗口（只辅助语气承接）", *[f"- {x}" for x in history_lines]])
    lines.append("[/WENYOU_GM_CONTEXT]")
    return "\n".join(lines)
