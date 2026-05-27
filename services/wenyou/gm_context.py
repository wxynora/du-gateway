import json

from services.wenyou.common import _normalize_difficulty
from services.wenyou.constants import _WENYOU_TUTORIAL_INSTANCE_ID
from services.wenyou.runtime_state import (
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
