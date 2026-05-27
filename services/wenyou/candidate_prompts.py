import re
from typing import Any, Optional

from utils.time_aware import now_beijing_iso

from services.wenyou.common import _normalize_difficulty, _normalize_instance_genre
from services.wenyou.constants import _WENYOU_TUTORIAL_INSTANCE_ID


def _normalize_candidate_item(raw: Any, index: int = 0) -> Optional[dict]:
    """大厅候选设定：轻量 seed，选中后再扩展为完整 framework。"""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or raw.get("instance_name") or "").strip()
    premise = str(raw.get("premise") or raw.get("world") or raw.get("description") or "").strip()
    if not title and not premise:
        return None
    tags = raw.get("tags")
    if not isinstance(tags, list):
        tags = []
    clean_tags = [str(x).strip()[:18] for x in tags if str(x).strip()][:5]
    cid = str(raw.get("id") or "").strip()
    if not cid:
        cid = f"cand-{now_beijing_iso().replace(':', '').replace('+', '-')}-{index + 1}"
    out = {
        "id": cid[:80],
        "title": (title or f"未命名候选 {index + 1}")[:40],
        "instance_genre": _normalize_instance_genre(raw.get("instance_genre") or raw.get("genre")),
        "difficulty": _normalize_difficulty(raw.get("difficulty")),
        "tagline": str(raw.get("tagline") or raw.get("hook") or "").strip()[:80],
        "premise": premise[:320],
        "core_task": str(raw.get("core_task") or raw.get("task") or raw.get("conflict") or "").strip()[:220],
        "survival_hook": str(raw.get("survival_hook") or raw.get("first_hook") or "").strip()[:180],
        "risk": str(raw.get("risk") or raw.get("failure_hint") or "").strip()[:180],
        "twist": str(raw.get("twist") or raw.get("mystery") or "").strip()[:180],
        "tags": clean_tags,
        "estimated_length": str(raw.get("estimated_length") or raw.get("length") or "标准").strip()[:20] or "标准",
        "tutorial": bool(raw.get("tutorial") or raw.get("is_tutorial") or cid == _WENYOU_TUTORIAL_INSTANCE_ID),
        "locked": bool(raw.get("locked")),
    }
    if raw.get("forced"):
        out["forced"] = True
    queue_id = str(raw.get("queue_id") or "").strip()
    if queue_id:
        out["queue_id"] = queue_id[:80]
    penalty_type = str(raw.get("penalty_type") or "").strip().lower()
    if penalty_type in {"debt", "pollution", "revive", "contract", "system"}:
        out["penalty_type"] = penalty_type
    return out


def _normalize_candidate_payload(raw: Any) -> list[dict]:
    data = raw if isinstance(raw, dict) else {}
    arr = data.get("items") or data.get("candidates") or []
    if not isinstance(arr, list):
        return []
    out: list[dict] = []
    for i, item in enumerate(arr[:10]):
        normalized = _normalize_candidate_item(item, i)
        if normalized:
            out.append(normalized)
    return out


def format_candidate_expansion_prompt(candidate: Any) -> str:
    """把大厅候选 seed 转成 /story 的 custom 关键词，让 DS 扩展完整 framework。"""
    item = _normalize_candidate_item(candidate, 0)
    if not item:
        return ""
    tags = "、".join(item.get("tags") or [])
    return (
        "请把以下【副本候选设定】扩展成完整无限流副本框架。"
        "必须保留候选的核心题材、危险钩子与悬念，但可以补全 tasker_total、NPC、规则、任务、开场和初始状态。\n\n"
        f"副本名：{item['title']}\n"
        f"类型：{item['instance_genre']}\n"
        f"难度：{item['difficulty']}\n"
        f"展示文案：{item.get('tagline') or ''}\n"
        f"轻量设定：{item.get('premise') or ''}\n"
        f"通关方向：{item.get('core_task') or ''}\n"
        f"生存钩子：{item.get('survival_hook') or ''}\n"
        f"危险方向：{item.get('risk') or ''}\n"
        f"未揭悬念：{item.get('twist') or ''}\n"
        f"标签：{tags or '无'}\n"
        f"篇幅：{item.get('estimated_length') or '标准'}"
    )


def _candidate_seed_block(item: dict) -> str:
    tags = "、".join(item.get("tags") or [])
    forced_note = ""
    if item.get("forced"):
        penalty_labels = {
            "debt": "债务清算",
            "pollution": "污染清算",
            "revive": "复活清算/临时身份",
            "contract": "契约追偿",
            "system": "强制清算",
        }
        penalty = str(item.get("penalty_type") or "system")
        player1_code = str(item.get("player1_name_hint") or "玩家一").strip() or "玩家一"
        player2_code = str(item.get("player2_name_hint") or "玩家二").strip() or "玩家二"
        forced_note = (
            "强制清算：是"
            "\n惩罚副本模式：临时 NPC 扮演"
            f"\n结算原因（metadata，不可写成剧情主题）：{penalty_labels.get(penalty, '强制清算')}"
            f"\n清算队列：{item.get('queue_id') or item.get('id') or ''}"
            f"\n玩家一代号（必须作为玩家 NPC 公开姓名）：{player1_code}"
            f"\n玩家二代号（必须作为玩家 NPC 公开姓名）：{player2_code}"
        )
    forced_lines = f"{forced_note}\n" if forced_note else ""
    return (
        f"副本名：{item.get('title') or '未命名副本'}\n"
        f"类型：{item.get('instance_genre') or '剧情解密'}\n"
        f"难度：{item.get('difficulty') or 'C'}\n"
        f"展示文案：{item.get('tagline') or ''}\n"
        f"轻量设定：{item.get('premise') or ''}\n"
        f"通关方向：{item.get('core_task') or ''}\n"
        f"生存钩子：{item.get('survival_hook') or ''}\n"
        f"危险方向：{item.get('risk') or ''}\n"
        f"未揭悬念：{item.get('twist') or ''}\n"
        f"{forced_lines}"
        f"标签：{tags or '无'}\n"
        f"篇幅：{item.get('estimated_length') or '标准'}"
    )


def _infinite_flow_generation_constraints() -> str:
    return """无限流味道约束：
- 如果候选没有明确年代/场景，优先从医院夜班、学校旧楼、老小区、出租屋、家族宅邸、民国婚宴、列车车厢、山村祭祀、公司夜班、商场闭店后、国外古老家族、恶魔/教会、狼人杀式村镇、暴风雪山庄、美恐小镇、公路旅馆、规则怪谈、红蓝阵营规则、猎奇秩序反转、黑暗童话改写等母题中选一个，不要默认写成空泛走廊。
- 规则怪谈母题可以写红方/蓝方、游客/员工、白班/夜班、医护/病患等互相冲突的规则文本；核心是“规则来源不可靠、阵营视角有偏差、错误遵守也会出事”，不要照搬现成作品的具体条文。
- 猎奇/黑暗寓言母题可以写动物与人类地位颠倒、人类被登记饲养或送检、童话婚姻/家族传说的黑暗改写、蓝胡子式密室婚姻、食物链颠倒的村镇；重点是规则、身份压迫和线索验证，不要只堆露骨血腥。
- 副本规则不能像说明书一次讲完；公开规则可以残缺、误导或带适用条件，必须让玩家/任务者通过观察、试探、对照异常后果来验证。
- 正常任务者不能只是背景板；每个副本至少要有 2-3 个可见任务者行为压力，如试探规则、隐瞒线索、误判 NPC、抢占安全区、拉人合作、把别人推出去试错。
- 主神/系统压迫感要克制但存在：只在开场、阶段变化、违规、倒计时、结算预警等关键节点给短提示，不要变成长篇客服播报。
- 失败不应让剧情卡死；错过线索或判断错误时，用威胁时钟推进、任务者受伤/死亡、NPC 身份被怀疑、异常加压、场景封锁或代价结算推动下一段。"""


def _forced_common_generation_constraints() -> str:
    return f"""{_infinite_flow_generation_constraints()}

普通副本底层规则也必须继承：
- 本局仍须有普通无限流副本结构：副本类型、规则/线索/危险源、通关目标、威胁推进和主神结算；不能只写成单纯 NPC 扮演小剧场。
- 正常任务者总人数仍遵守 2-13 的世界规则；惩罚副本里的“正常任务者队伍”可围绕玩家 NPC 展开，但不要把玩家一或玩家二写进这支正常任务者队伍。
- 惩罚副本的爽点不是玩家自己通关，而是明知自己来自主神空间，却必须演原住民 NPC，借身份、关系、误会、病症、地位或危险把正常任务者往通关方向推。
- 正常任务者和副本 NPC 的真实善恶、隐藏动机、怪物弱点、Boss 真相、隐藏结局都不能在开场或公开短稿里直给；只写公开态度、可见行为和可验证线索。
- 线索必须可验证、能推进任务或规则判断；不要把氛围描写、外貌描写或世界观介绍当线索清单甩给玩家。
- 不要写精确 HP/SAN/积分/EXP/抽卡/掉落/晋升/永久能力到账；这些由后端结算。惩罚副本成功/失败只写清算方向，不直接发奖励。
- Boss 或核心异常默认不可被玩家一或玩家二正面解决；必须保留削弱、封印、规避、感化、揭真相或由正常任务者推进的路径。
- 每条关键推进路径要有 fail-forward：错过线索时可通过发病、问话、误判、异常压力、二次调查或身份关系继续推进，不让剧情卡死。
- opening 和正文固定玩家一视角，用“你/你的”；玩家二只通过玩家一可见、可听、可交流的信息呈现；不得替玩家决定行动、表情、内心独白，不得让玩家主动解释系统或跳出身份。"""


def _forced_candidate_core_prompt(item: dict) -> str:
    player1_code = str(item.get("player1_name_hint") or "玩家一").strip() or "玩家一"
    player2_code = str(item.get("player2_name_hint") or "玩家二").strip() or "玩家二"
    return f"""把【候选设定】扩展成「无限流 · 惩罚副本」核心设定短稿。

世界观前提：
- 这是主神空间体系下的无限流副本，不是普通角色扮演剧本。
- 正常任务者队伍正在按普通无限流逻辑求生、解谜、验证规则、尝试通关。
- 玩家一和玩家二都不是这支正常任务者队伍成员，而是一起被系统塞进该副本世界的原住民 NPC。
- 玩家一和玩家二的核心目标不是自己通关，而是演好各自 NPC，并在不暴露身份的前提下推动正常任务者副本进度。
- 正文后续仍以玩家一视角运行；玩家二是同一清算任务里的 NPC 同伴，不是旁观协助角色。

{_forced_common_generation_constraints()}

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 5-8 行，每行尽量短。
- 必须包含：副本时代/场景、正常任务者的公开任务、玩家一 NPC 身份、玩家二 NPC 身份、两人关系或身份差异、两人的身份如何推动进度、身份矛盾、危险牵引、暴露后果。
- 玩家一 NPC 的公开姓名必须使用「{player1_code}」，不得另起本名、化名、小名或真实姓名；称谓可随时代变化，如“小姐/姑娘/同学/病人/夫人”。
- 玩家二 NPC 的公开姓名必须使用「{player2_code}」，不得另起本名、化名、小名或真实姓名；称谓可随时代和身份变化。
- 若任一玩家代号和家族、时代、地域或身份结构有违和，不能改名消除；必须把违和写成剧情钩子，如收养、过继、随母姓、家产侵占、族谱涂改、冒名顶替或异常刻意保留。
- 玩家 NPC 可以是副本核心人物：被救援对象、被调查对象、嫌疑人、继承人、祭品、病人、规则触发者、线索持有人或仪式核心；两人可以一主一辅，也可以共同牵住主线。
- NPC 身份越接近主线核心，危险越高；必须让 Boss/异常阵营有理由控制、利用、杀死、替换或误导玩家 NPC。
- 结算原因只作为后端 metadata；不要把债务、污染、复活、契约写成剧情主题或副本主线。
- 不要写 opening，不要写属性数值，不要替玩家行动。

严格禁止：
- 禁止把玩家一或玩家二写成普通任务者。
- 禁止把本局写成玩家自己通关、打 Boss、找出口的普通副本。
- 禁止让玩家一或玩家二直接剧透答案、解释系统、带队通关或跳出 NPC 身份。

【候选设定】
{_candidate_seed_block(item)}"""


def _candidate_core_prompt(item: dict) -> str:
    if item.get("forced"):
        return _forced_candidate_core_prompt(item)
    return f"""把【候选设定】扩展成副本核心设定短稿。

{_infinite_flow_generation_constraints()}

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 4-7 行，每行尽量短。
- 必须包含：副本内部场景、核心矛盾、玩家公开任务、隐藏悬念、危险规则方向。
- 只写副本核心，不写长期主神空间剧情。
- 必须写出正常任务者队伍的压力感：至少暗示 2-3 个任务者的可见行为方向，如试探规则、争抢线索、误判 NPC、害怕退缩、想利用别人或试图合作。
- 如果候选写明“强制清算：是”，必须保留清算类型、身份限制、暴露后果和失败代价；不要改写成普通自愿接取副本。
- 不要写 opening，不要写属性数值，不要替玩家行动。

【候选设定】
{_candidate_seed_block(item)}"""


def _clean_ds_block(text: Any, limit: int = 1200) -> str:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", raw, flags=re.M).strip()
    lines = [line.strip(" \t-•") for line in raw.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)[:limit].strip()


def _candidate_canon_block(item: dict, core_text: str) -> str:
    if not isinstance(item, dict):
        return ""
    return (
        _candidate_seed_block(item)
        + "\n\n核心短稿：\n"
        + _clean_ds_block(core_text, 1200)
    ).strip()


def _forced_candidate_blueprint_prompt(item: dict, core_text: str = "") -> str:
    player1_code = str(item.get("player1_name_hint") or "玩家一").strip() or "玩家一"
    player2_code = str(item.get("player2_name_hint") or "玩家二").strip() or "玩家二"
    return f"""基于【已确定核心设定】生成「无限流 · 惩罚副本」蓝图短稿。

本局底层结构：
- 这仍然是无限流副本：存在主神空间、正常任务者队伍、规则、线索、危险、通关目标和结算。
- 但玩家一和玩家二都不是正常任务者；两人是一起被塞进副本世界的 NPC。
- 正常任务者才是表层主角，他们的主线可以围绕玩家一 NPC、玩家二 NPC，或两人共同关系展开。
- 玩家一和玩家二的隐藏工作是演好各自 NPC，用符合身份的方式推动正常任务者进度，并避免暴露。
- 蓝图内部要明确两人的 NPC 身份、关系、可配合边界；正文运行时仍固定玩家一视角。
- 本局不是让玩家自己通关；玩家只能通过 NPC 身份把正常任务者推到验证规则、找到弱点、封印/规避核心异常的路上。

{_forced_common_generation_constraints()}

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 按三段写：入戏、推动、收束。
- 每段都写：两名玩家 NPC 的表演目标 / 正常任务者进度 / 可给出的线索或阻碍 / 规则验证方式 / 系统压迫节点 / 任一方暴露风险 / 错过时如何付代价 fail-forward。
- 额外列出：玩家一 NPC 身份契约、玩家二 NPC 身份契约、两人关系或配合边界、正常任务者公开任务、身份违和钩子、Boss/异常对玩家 NPC 的危险牵引、暴露给任务者/怪物阵营的后果、隐藏支线/隐藏结局方向。
- 玩家 NPC 身份可以很核心，甚至是被救援、被调查、被怀疑、被保护或被献祭的对象；越核心越危险。
- 玩家一 NPC 的公开姓名必须使用「{player1_code}」，玩家二 NPC 的公开姓名必须使用「{player2_code}」；不得另起姓名。
- 结算原因只写成“后端清算原因”，不得让债务/污染/复活/契约成为剧情主线。
- 怪物或 Boss 默认不可由玩家一或玩家二正面解决；两人只能通过 NPC 身份引导任务者发现削弱、封印、规避或真相路径。
- 只给 GM/后端内部短纲，不要整段剧透给玩家。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""


def _candidate_blueprint_prompt(item: dict, core_text: str = "") -> str:
    if item.get("forced"):
        return _forced_candidate_blueprint_prompt(item, core_text)
    return f"""基于【已确定核心设定】生成副本蓝图短稿。

{_infinite_flow_generation_constraints()}

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 按三段写：开场、探索、收束。
- 每段写“阶段目标 / 关键线索 / 规则验证方式 / 正常任务者可见行为 / 系统压迫节点 / 错过线索时如何付代价推进”。
- 额外列出：普通支线、隐藏支线、隐藏结局、威胁时钟、NPC 任务者立场边界、怪物/核心压力源简表。
- NPC 任务者立场边界只写公开态度和可见行为，不直给真实善恶；真实立场留给后端隐藏状态。
- 怪物生态只写普通怪/精英怪/Boss 或核心压力源的用途和解法；Boss 默认不可正面战胜。
- 结算只看真实玩家角色/玩家队伍；NPC 结局只作为支线/隐藏目标证据，不自动影响评级。
- 如果候选写明“强制清算：是”，蓝图必须列出身份边界、暴露给任务者/怪物阵营的后果，以及成功/失败如何回到后端清算；不要写成普通任务者竞赛。
- 只给 GM/后端内部短纲，不要整段剧透给玩家。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""


def _forced_candidate_opening_prompt(item: dict, core_text: str = "") -> str:
    player1_code = str(item.get("player1_name_hint") or "玩家一").strip() or "玩家一"
    player2_code = str(item.get("player2_name_hint") or "玩家二").strip() or "玩家二"
    return f"""基于【已确定核心设定】生成「无限流 · 惩罚副本」开场正文。

{_forced_common_generation_constraints()}

输出要求：
- 只写开场正文，不要 JSON，不要 markdown 代码块。
- 5-9 句，像小说正文一样续写，必须保留无限流质感：白光/传送/主神提示音/刻板广播/副本载入感至少出现一种。
- 固定以玩家一为视角中心，用第二人称“你/你的”指代玩家一。
- 开场要让玩家明确感到：自己和玩家二都被塞进了副本原住民 NPC 身份，而不是作为普通任务者入场。
- 玩家一 NPC 的公开姓名必须使用「{player1_code}」；可以用称谓组合，如“某家大小姐{player1_code}”“{player1_code}小姐”“{player1_code}同学”，但不得另起姓名。
- 玩家二 NPC 的公开姓名必须使用「{player2_code}」；只能通过玩家一当前能看到、听到、交流到的方式出现，不要写成普通任务者。
- 必须出现或暗示正常任务者队伍的存在；他们可以是被请来的医生、调查员、道士、学生、住户、警员、求生者等，正在按普通无限流逻辑接近主线。
- 可以让正常任务者的表层任务围绕玩家 NPC 展开，例如治疗、保护、调查、看守、护送、判断两人中某一人或两人的关系是否异常。
- 开场必须有正常任务者的可见动作压力：至少出现一个人在试探、争执、害怕、隐瞒、保护或误判；不要把其他任务者写成静态路人。
- 只给一条可被验证的异常/规则苗头，不要把完整规则档案直接发给玩家。
- 不要把后端结算原因念给玩家；不要说“债务/污染/契约工单”等说明书词。
- 不要输出任务者名单、线索列表、规则档案或情报卡。
- 如果写系统/主神广播，必须独立成行：`【系统提示】广播内容`。
- 不要替玩家做行动决定，不要写玩家主动解释系统或直接剧透。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""


def _candidate_opening_prompt(item: dict, core_text: str = "") -> str:
    if item.get("forced"):
        return _forced_candidate_opening_prompt(item, core_text)
    return f"""基于【已确定核心设定】生成副本开场正文。

{_infinite_flow_generation_constraints()}

输出要求：
- 只写开场正文，不要 JSON，不要 markdown 代码块。
- 4-8 句，像小说正文一样续写，含主神传送/白光/提示音/刻板广播之一。
- 落入副本场景，点出第一处异常。
- 开场必须有正常任务者的可见动作压力：至少出现一个人在试探、争执、害怕、隐瞒、保护或误判；不要把其他任务者写成静态路人。
- 只给一条可被验证的异常/规则苗头，不要把完整规则档案直接发给玩家。
- 只写玩家可见开场，不剧透隐藏支线、隐藏结局、NPC 真实立场或威胁时钟精确值。
- 如果写系统/主神广播，必须独立成行：`【系统提示】广播内容`，不要混在叙事长句里。
- 未经玩家看见名牌、听见自我介绍或主神点名前，不要直接写 NPC 姓名；用“戴眼镜的年轻男性”“穿冲锋衣的短发女性”等可见特征称呼。
- 不要输出任务者名单、线索列表、规则档案或情报卡。普通环境描写不是线索。
- 如果候选写明“强制清算：是”，开场要让玩家感到入口被锁定/被迫接入，但不要把隐藏规则、清算队列或后端状态直接念成说明书。
- 不要替玩家做行动决定。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""
