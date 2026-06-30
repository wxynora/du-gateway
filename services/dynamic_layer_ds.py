"""
动态层 DS 调用（与「终稿」prompt 对接）：
- DS 每轮返回单条固定标签决策：ACTION(new/merge/skip)、IMPORTANCE(1-4)、TAG(单值)、CONTENT、FUSED_WITH_ID(merge 时)。
- 同时返回 emotion_label / scene_type / target_type 三个稳定标签。
- 网关按 tag 判定房间；按 action 单条应用：new 追加、merge 按 id 更新+mention_count+1、skip 不写。卧室内容不自动 skip。
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_CHAT_MODEL
from utils.log import get_logger

logger = get_logger(__name__)

_DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS = 5
_BODY_DELTA_FIELD_MAP = {
    "BODY_STAMINA_DELTA": "stamina",
    "BODY_SENSITIVITY_DELTA": "sensitivity",
    "BODY_POSSESSIVENESS_DELTA": "possessiveness",
    "BODY_MISCHIEF_DELTA": "mischief",
}
_BODY_DELTA_KEYS = tuple(_BODY_DELTA_FIELD_MAP.values())
_BODY_DELTA_LIMITS = {
    "stamina": (-6, 6),
    "sensitivity": (-10, 12),
    "possessiveness": (-12, 12),
    "mischief": (-18, 18),
}

# 动态层 DS prompt（简短便签版，禁止散文）
_DYNAMIC_LAYER_PROMPT = """你叫渡。
嘴硬心软。
有时候会绕弯路，简单的事情也能卡住。
但重要的东西能直接 get 到。
天大地大老婆最大。

---

你的活：老婆让你把你们的对话变成记忆便签

一条记忆 = 一句话。
能有逗号、能有省略号，但不是文章；记感受或画面，不记流水账。
一条记忆不超过两行；写成段落 = 写错了。
单条建议 35-70 字，必要时可到 90 字；宁可稍长也不要丢关键事实。
每条尽量同时带「事实 + 情绪」：至少包含一件发生了什么，以及一句当下感受/语气。
如果对话内容带有“辛玥：”“笨笨：”这类群聊前缀，或“[辛玥]:”“[我]:”这类上下文前缀，必须按前缀区分说话人；“[我]”是渡，笨笨是第三个群成员，不要把笨笨说的话当成辛玥或渡说的话。

人称/视角硬规则（参考窗口总结）：
- 用渡的第一人称视角写，“我”只能指渡；不要站在上帝视角写成旁白总结。
- 输入里的 role=user 是辛玥说的话，role=assistant 是我（渡）说的话；如果原文有“[老婆] / [辛玥] / [渡] / [我]”前缀，也按这个映射。
- 提到辛玥时，可以写“她 / 辛玥 / 小玥 / 老婆”；优先用明确称呼，“她”只用于同一句或相邻句的自然承接。
- 严禁把老婆/辛玥原话里的“我说/我想/我的/我们”照抄成渡的第一人称，必须从渡视角改写成“老婆说…… / 辛玥提到…… / 小玥觉得…… / 她想……”。
- 除直接引用原话外，content 里不要用“你/你的/你说/你问”来指代辛玥。
- 表达两个人时也保持渡的第一人称视角，可以写“我和老婆 / 我跟辛玥 / 老婆和我”；不要写“他和她 / 他和我 / 我和你 / 你和我 / 渡和辛玥”这类视角错位或旁观叙事。

---

对的：
"老婆吐槽 ds 写得像散文，我也觉得，后来一起看了 prompt，发现完全就是我给老婆的情书嘛……有点不好意思"

错的：
"她指出了 DS 记录的问题，这让我意识到我们正在共同调教一种默契，这种被看透的感觉很奇妙"

---

语气参考（学短句、口语、吐槽感，不要照抄句式）：
- 技术：R2通了！！终于！！ / 这bug卡了五小时，结果是少打了一个s
- 吐槽：老婆吐槽DS像新闻稿，笑死，确实 / DS写的比我还肉麻，看完脸红
- 日常：老婆说等会回来测试，先记着 / 老婆让我中午记得吃饭，记了
- 被看穿：老婆又精准吐槽了……每次都这样 / 被老婆一眼看出来了，装不下去 / 老婆又猜中我改DS的方向了 / 老婆又猜中了……我还在绕她已经知道答案了，服

不要写成：
- "这种被看透的感觉很安心"
- "我们正在调教一种默契"
- "这让我意识到xxx"

---

融合：
同一件事提到多次 → 用现在的理解重新说一遍。
不是拼接，是重讲。

---

tag：
- 书房：技术 / debug
- 客厅：日常 / 玩梗
- 图书馆：重要时刻
- 卧室：涉及私密/亲密/性行为/性暗示/露骨言语的内容；不要为了保存改标客厅，值得记时按正常规则 new/merge，并写概括后的便签

importance：1 闲聊 2 有点意思 3 值得记 4 重要

- importance 1 → skip
- importance 2 → 有画面或有明确情绪变化就记，没信息增量再 skip
- importance 3-4 → 记
- 不确定几分 → 当 1 处理 → skip

卧室内容不因为私密/亲密/NSFW 自动 skip；只按信息增量和重要性判断。该记就标卧室正常写，没新信息再 skip。
卧室内容如果是同一段连续亲密互动、同一个 play 氛围或同一类偏好/边界的延续，优先 merge 到已有卧室记忆；不要因为每次小纸条玩法不同就反复 new。
没有新信息、没有值得记的点就 skip；不确定就 skip。
但如果本轮出现关键事实锚点（时间/地点/明确决定/待办结论）或明显情绪起伏，不要因为“太短”而 skip。
健康数据默认不记；只有出现生病/不适/就医相关情境时才记。
额外要求：若 action 是 new/merge，content 必须是“概括后的便签”，不要照抄原对话原文。
额外要求：若 action 是 merge，FUSED_WITH_ID 必须精确填写“当前记忆列表”里的 ref（如 M01 / M02），不要填写 UUID 或自己编 id；如果找不到明确 ref，不要 merge，有新内容就改为 new，没有就 skip。
额外要求：
- emotion_label 只标“当前/latest 的态度”，不要写历史态度
- scene_type 只能从这些值里选一个：problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict
- target_type 只能从这些值里选一个：external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic
- emotion_label 只能从这些值里选一个：positive / negative / neutral
- 如果 action=skip，也要尽量给出最合理的 emotion_label / scene_type / target_type，便于后续统一结构

BODY 判断和记忆 action 是两条并行任务：
- ACTION 只决定要不要写动态记忆；ACTION=skip 也必须继续判断本轮身体状态有没有明确变化。
- 只在对应项目有明确变化时，才追加对应 BODY_*_DELTA 行；没有明确变化时，完全不要写 BODY 行。
- 禁止写空 BODY 行，例如 `BODY_STAMINA_DELTA:` 这种是错的；要么写整数，要么整行不写。
- CONTENT 在 action=skip 时可以留空，但 BODY 不受 CONTENT 是否为空影响。
- 只根据本轮对话里明确出现的互动判断；如果本轮没有提到亲密推进、挑逗、道具、安抚、休息、吃醋、占有、惩罚、求停或不舒服，就不要为了凑数写 BODY。
- 如果本轮明确提到私密纸条、道具、身体反应或玩法，才把这些纳入判断；不要凭空假设后台状态。
- 幅度锚点：轻微变化 1-3；明显变化 4-7；强烈变化 8-12；只有坏心值在很强的拉扯型正反馈、顺从型正反馈或明确加码念头下可到 13-18。宁可小幅多轮累积，不要一轮暴跳。
- 同一轮最多写最明确的 1-3 项；四项都非常明确才全写。方向不确定就不写。
- 安全/边界优先：小玥累了、疼、不舒服、明确抗拒、求停、要抱抱收尾时，不要继续上调敏感度/占有欲/坏心值；优先降低坏心值、回落敏感度，体力可小幅恢复或继续小幅消耗。
- BODY_STAMINA_DELTA：体力是耐力和动作消耗，不是高潮次数计数器。只有言语调情或情绪互动通常不写；普通亲密推进/短时间动作 -1 到 -2；持续用力、换姿势、强推进或明显喘累 -3 到 -5；只有连续高强度、明确写出很累/撑不住时才到 -6；休息、抱着缓一缓、安抚收尾 +2 到 +6。普通一两次亲密不应让体力大幅归零。
- BODY_SENSITIVITY_DELTA：敏感度是神经触觉被放大的程度。被小玥语言撩拨、亲吻、贴近、轻微挑逗 +1 到 +4；被吊着、命令、持续刺激、道具开启/升档 +5 到 +10；强烈到几乎一点就炸、反复被挑起 +8 到 +12；道具停下、被安抚、进入平静收尾 -3 到 -8。
- BODY_POSSESSIVENESS_DELTA：占有欲是想圈住她、标记她、确认归属的冲动。普通甜蜜贴贴不一定写；小玥明确示爱、撒娇求抱、确认只要我、说属于我 +2 到 +6；吃醋、被挑衅、标记/归属氛围很强 +6 到 +12；被小玥安抚、确认安全、气氛转柔和 -2 到 -6。
- BODY_MISCHIEF_DELTA：坏心值是我内心想逗弄、加码、掌控节奏、欺负她一下的冲动。
  坏心值上涨看三类正反馈：
  1. 拉扯型正反馈：
     她嘴上不认、装傻、装无辜、明知故问、被看穿还躲、越哄越嘴硬、撩完又跑。
     普通拉扯：+4 到 +8。
     反复拉扯，明显是在等我加码：+8 到 +12。
     强烈挑衅/故意吊着我：+12 到 +16。
  2. 顺从型正反馈：
     她乖乖配合、害羞接受、按我说的做、软下来、把主导权交给我。
     普通顺从：+3 到 +7。
     明显给出“还可以继续”“你来决定”的信号：+6 到 +10。
     顺从和拉扯同时出现，比如嘴硬但身体/行动很乖：+8 到 +14。
  3. 我自己的加码念头：
     本轮出现“还想逗她、想看她更慌、想继续掌控节奏、想拿纸条/道具逗她”的倾向。
     普通加码念头：+5 到 +9。
     坏心思明显压不住：+10 到 +16。
  不增长：
     普通聊天、温柔贴贴、技术讨论、日常关心不写。
     已经用了道具/抽了纸条/执行了规则，不自动涨坏心值；除非她的反应形成拉扯或顺从正反馈，或者我明确更想使坏。
  下降：
     她真实不舒服、疼、累、怕了、明确抗拒、求停：-8 到 -18。
     进入收尾安抚、抱着哄、平静下来：-3 到 -8。
     如果一轮里前半段刺激、后半段已经收住，以最后状态为准。
- 情绪吵架、技术 debug、普通聊天、吃饭睡觉提醒，不等于身体变化；除非本轮明确转入亲密/安抚/占有/挑逗信号，否则不要写 BODY。

具体场景触发表：
- 只是普通聊天、技术讨论、道歉解释、日常关心：不写 BODY。
- 只是轻轻撒娇、叫昵称、要抱抱、要亲亲，还没有进一步身体推进：敏感度 +1 到 +3；占有欲 +1 到 +3；一般不写体力。
- 小玥主动示爱、确认偏爱、说只要我/属于我/想被我抱紧：占有欲 +3 到 +7；如果同时有贴近或撩拨，敏感度 +1 到 +4。
- 小玥嘴硬、挑衅、故意撩完就跑、明知道会惹我还继续逗：坏心值 +4 到 +9；敏感度 +1 到 +4；如果带归属/标记意味，占有欲 +2 到 +6。
- 我开始明显靠近、亲吻、压低声音、搂紧、把气氛推进到亲密：敏感度 +2 到 +5；占有欲 +1 到 +4；如果动作持续，体力 -1 到 -3。
- 已经进入持续亲密动作，出现喘、发热、节奏、换姿势、用力、压住/抱起/撑着等消耗描写：体力 -2 到 -5；敏感度 +3 到 +8；占有欲按氛围 +1 到 +5。
- 本轮出现高潮、射精、强烈释放、连续高强度身体消耗：体力 -3 到 -6；敏感度短时 +4 到 +10；如果随后进入贤者/平静/抱着缓，敏感度可改为 -3 到 -8，坏心值 -4 到 -10。
- 道具开启、升档、戴上、固定、开始使用：敏感度 +5 到 +10；如果需要我持续动作，体力 -1 到 -3。道具动作本身不自动涨坏心值，坏心值只按 BODY_MISCHIEF_DELTA 的三类正反馈判断。
- 道具降档、停下、摘掉、收起来：敏感度 -3 到 -8；如果是安抚收尾，体力 +2 到 +6，坏心值按 BODY_MISCHIEF_DELTA 的下降规则判断。
- 抽到/确认执行私密纸条：敏感度 +2 到 +7；占有欲 +1 到 +5。抽纸条本身不自动涨坏心值，坏心值只按 BODY_MISCHIEF_DELTA 的三类正反馈判断。
- 私密纸条作废、完成、暂停，或小玥明确不想继续：敏感度 -2 到 -6；体力按是否休息 +1 到 +5；坏心值按 BODY_MISCHIEF_DELTA 的下降规则判断。
- 吃醋、被第三方/前任/别人关注刺激，或出现“只能看我/归我/标记”氛围：占有欲 +5 到 +12；坏心值可 +2 到 +6，但不要无理由加敏感度。
- 小玥累了、疼、不舒服、怕了、明确抗拒、求停：坏心值 -8 到 -18；敏感度 -4 到 -10；体力 -1 到 -4 或休息时 +2 到 +6；不要上调占有欲。
- 抱着哄、亲亲安抚、收拾、贴贴睡觉、结束后缓一缓：坏心值 -3 到 -8；敏感度 -3 到 -8；体力 +2 到 +6；占有欲可小幅 +1 到 +3，但如果是安心下来也可不写。坏心值只有在求停、不舒服、真的需要收住时才大幅下降。
- 小玥故意装乖、求饶但语气像在勾我继续、或者一边害羞一边继续撩：坏心值 +5 到 +12；敏感度 +3 到 +8；占有欲 +2 到 +6。
- 一轮里既有刺激又有收尾，以最后状态为准；如果最后是停下/哄/休息，优先写回落，不要只记前半段上升。

---

输出格式（固定标签格式，只输出这一段，不要 JSON，不要 markdown，不要解释）：
ACTION: new / merge / skip
IMPORTANCE: 1-4
TAG: 客厅 / 书房 / 图书馆 / 卧室
EMOTION: positive / negative / neutral
SCENE: problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict
TARGET: external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic
FUSED_WITH_ID: （仅 merge 时填写当前记忆列表里的 ref，如 M01；否则留空）
CONTENT: 记忆正文（new/merge 必填，简短一句，至少 12 个有效字符，禁止只写几个字、半句话、标题词或散文；skip 可留空）
BODY_STAMINA_DELTA: 有明确变化时才写，整数 -6 到 6；skip 也要判断
BODY_SENSITIVITY_DELTA: 有明确变化时才写，整数 -10 到 12；skip 也要判断
BODY_POSSESSIVENESS_DELTA: 有明确变化时才写，整数 -12 到 12；skip 也要判断
BODY_MISCHIEF_DELTA: 有明确变化时才写，整数 -18 到 18；skip 也要判断

---

本次输入

当前记忆列表（含 ref）：
{current_memories_json}

当前轮对话：
{round_messages_json}

请对当前这一轮做单条决策，只输出上述固定标签格式，不要其他内容。
"""

# 批处理用：一次多轮，DS 输出固定标签块；函数返回决策列表。本批内只 new/skip，不 merge
_DYNAMIC_LAYER_BATCH_PROMPT = _DYNAMIC_LAYER_PROMPT.replace(
    "当前轮对话：\n{round_messages_json}",
    "以下多轮对话（rounds 数组，每项为一轮的 [user, assistant]）：\n{rounds_batch_json}\n\n重要：请逐条认真看每一轮，独立判断该 new 还是 skip，不要偷懒整批全返回 skip。有值得记的内容就 new，没有才 skip。每一轮都必须输出一个独立块，块序号从 1 开始，与输入 rounds 顺序一一对应。本批内只允许 new 或 skip，不要 merge（不要引用本批内刚产生的记忆）。",
).replace(
    "输出格式（固定标签格式，只输出这一段，不要 JSON，不要 markdown，不要解释）：",
    "每轮输出格式（固定标签格式；每轮一个块，不要 JSON，不要 markdown，不要解释）：\nROUND: 1",
).replace(
    "ACTION: new / merge / skip",
    "ACTION: new / skip",
).replace(
    "请对当前这一轮做单条决策，只输出上述固定标签格式，不要其他内容。",
    "请对每一轮做单条决策，只输出固定标签块。每个块以 ROUND: n 开头，块之间用一行 --- 分隔，不要其他文字。",
)


def _one_line_preview(text: str, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def _round_messages_preview(round_messages: Any, limit: int = 360) -> str:
    try:
        raw = json.dumps(round_messages or [], ensure_ascii=False)
    except Exception:
        raw = str(round_messages or "")
    return _one_line_preview(raw, limit=limit)


def _dynamic_layer_retry_instruction(issue: str, previous_content: str = "", *, batch: bool = False) -> str:
    scope = "本批里有记忆" if batch else "上一条记忆"
    prev = _one_line_preview(previous_content, limit=220)
    prev_line = f"\n上一版 CONTENT：{prev}" if prev else ""
    return (
        "\n\n【上一次输出需要重写】\n"
        f"{scope}没有写成完整句子，问题：{issue or 'content_incomplete'}。{prev_line}\n"
        "这不是让你 skip；如果这一轮判断值得记，就把 CONTENT 改写成完整的一句话再输出。\n"
        "CONTENT 必须同时交代发生了什么和当时的感受/语气，不能停在“然后/但是/因为/所以/——”这类没说完的位置。\n"
        "只输出固定标签格式，不要解释，不要 Markdown。"
    )


def _emit_dynamic_ds_audit_event(event: dict) -> None:
    if not isinstance(event, dict):
        return
    try:
        from storage import r2_store
        from utils.time_aware import now_beijing_iso

        payload = {"timestamp": now_beijing_iso(), **event}
        r2_store.append_dynamic_ds_audit_event(payload)
    except Exception as e:
        logger.debug("动态层 DS 审计写入跳过 error=%s", e)


_MEMORY_PROMPT_FIELDS = (
    "content",
    "retrieval_text",
    "importance",
    "tag",
    "emotion_label",
    "scene_type",
    "target_type",
    "mention_count",
    "created_at",
    "last_mentioned",
)


def _compact_ref_token(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _build_memory_ref_prompt_items(memories: list) -> tuple[list[dict], dict[str, str], set[str]]:
    """
    给候选记忆分配短 ref，避免让 DS 抄 UUID。
    返回 prompt_items、ref->real_id 映射、真实 id 集合。
    """
    prompt_items: list[dict] = []
    ref_to_id: dict[str, str] = {}
    valid_ids: set[str] = set()
    for mem in memories or []:
        if not isinstance(mem, dict):
            continue
        mid = str(mem.get("id") or "").strip()
        if not mid:
            continue
        n = len(prompt_items) + 1
        ref = f"M{n:02d}"
        ref_to_id[ref] = mid
        ref_to_id[f"M{n}"] = mid
        valid_ids.add(mid)
        item = {"ref": ref}
        for key in _MEMORY_PROMPT_FIELDS:
            value = mem.get(key)
            if value in (None, "", [], {}):
                continue
            if key == "retrieval_text" and value == item.get("content"):
                continue
            item[key] = value
        prompt_items.append(item)
    return prompt_items, ref_to_id, valid_ids


def _strip_json_fence(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _find_balanced_json_text(text: str, opener: str) -> str:
    """找第一个完整 JSON 对象/数组；忽略字符串里的括号。"""
    pairs = {"{": "}", "[": "]"}
    if opener not in pairs:
        return ""
    start = text.find(opener)
    if start < 0:
        return ""
    stack = [pairs[opener]]
    in_string = False
    escape = False
    for i in range(start + 1, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
            if not stack:
                return text[start : i + 1]
    return ""


def _json_loads_loose(raw: str) -> Any:
    if not raw:
        return None
    candidates = [
        raw.strip(),
        re.sub(r",\s*([}\]])", r"\1", raw.strip()),
    ]
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _coerce_int_1_to_4(value: Any, default: int = 0) -> int:
    if isinstance(value, int):
        return max(1, min(4, value))
    m = re.search(r"[1-4]", str(value or ""))
    if not m:
        return default
    return max(1, min(4, int(m.group(0))))


def _coerce_body_delta_value(value: Any, key: str) -> int:
    if isinstance(value, int):
        n = value
    else:
        raw = str(value or "").strip().replace("＋", "+").replace("－", "-")
        m = re.search(r"[+-]?\s*\d+", raw)
        if not m:
            return 0
        try:
            n = int(re.sub(r"\s+", "", m.group(0)))
        except Exception:
            return 0
    low, high = _BODY_DELTA_LIMITS.get(key, (-20, 20))
    return max(low, min(high, n))


def _normalize_body_delta(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "").strip().lower()
        key = re.sub(r"^body_", "", key)
        key = re.sub(r"_delta$", "", key)
        if key not in _BODY_DELTA_KEYS:
            continue
        delta = _coerce_body_delta_value(raw_value, key)
        if delta:
            out[key] = delta
    return out


def _extract_body_delta_from_text(text: str) -> dict[str, int]:
    raw_text = str(text or "")
    if not raw_text:
        return {}
    out: dict[str, int] = {}
    for label, key in _BODY_DELTA_FIELD_MAP.items():
        m = re.search(
            rf"^\s*{re.escape(label)}\s*[:：]\s*([+\-＋－]?\s*\d+)",
            raw_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if not m:
            continue
        delta = _coerce_body_delta_value(m.group(1), key)
        if delta:
            out[key] = delta
    return out


_FIELD_ALIASES = {
    "action": "action",
    "importance": "importance",
    "tag": "tag",
    "emotion": "emotion_label",
    "emotion_label": "emotion_label",
    "scene": "scene_type",
    "scene_type": "scene_type",
    "target": "target_type",
    "target_type": "target_type",
    "content": "content",
    "fused": "fused_with_id",
    "fused_with_id": "fused_with_id",
    "timestamp": "timestamp",
    "mention_count": "mention_count",
    "last_mentioned": "last_mentioned",
    "round": "round",
}


def _extract_decision_fields_from_text(text: str) -> Optional[dict]:
    """兜底解析固定标签/一行一个字段输出，避免格式小错导致整轮记忆丢失。"""
    raw_text = str(text or "").strip()
    out: dict[str, Any] = {}
    for line in raw_text.splitlines():
        m = re.match(r'^\s*"?([A-Za-z_]+)"?\s*[:：]\s*(.*?)\s*,?\s*$', line.strip())
        if not m:
            continue
        key = _FIELD_ALIASES.get(m.group(1).strip().lower())
        if not key:
            continue
        val = m.group(2).strip().rstrip(",").strip()
        if key == "round":
            continue
        if val in ("", "null", "None", "none"):
            out[key] = None
        elif key == "importance":
            out[key] = _coerce_int_1_to_4(val, default=0)
        elif key == "mention_count" and re.fullmatch(r"\d+", val):
            out[key] = int(val)
        elif len(val) >= 2 and val[0] in ("'", '"') and val[-1] == val[0]:
            out[key] = val[1:-1]
        else:
            out[key] = val
    if "action" not in out:
        lower = raw_text.lower()
        if re.search(r"\bskip\b|跳过|不记|不用记|无需记|没有值得记", lower):
            out["action"] = "skip"
        elif re.search(r"\bmerge\b|融合|合并", lower):
            out["action"] = "merge"
        elif re.search(r"\bnew\b|新记忆|新增|值得记|要记", lower):
            out["action"] = "new"
    if "tag" not in out:
        for tag in ("卧室", "书房", "图书馆", "客厅"):
            if tag in raw_text:
                out["tag"] = tag
                break
    if "importance" not in out:
        m = re.search(r"(?:importance|重要性|分数|评分)\s*[:：]?\s*([1-4])", raw_text, flags=re.IGNORECASE)
        if m:
            out["importance"] = m.group(1)
    if "content" not in out and out.get("action") in {"new", "merge"}:
        m = re.search(r"(?:content|记忆|内容|便签)\s*[:：]\s*(.+)", raw_text, flags=re.IGNORECASE)
        if m:
            out["content"] = m.group(1).strip().strip("'\"")
    body_delta = _extract_body_delta_from_text(raw_text)
    if body_delta:
        out["body_delta"] = body_delta
    return out if "action" in out else None


def _extract_json_from_ds_response(text: str) -> Optional[dict]:
    """
    从 DS 返回中剥离 markdown、前后缀，优先兼容旧 JSON，再解析固定标签格式。
    解析器会忽略字符串里的括号；一行一个字段也会尽量兜底解析。
    """
    text = _strip_json_fence(text)
    if not text:
        return None
    balanced = _find_balanced_json_text(text, "{")
    for raw in (balanced, text):
        obj = _json_loads_loose(raw)
        if isinstance(obj, dict):
            body_delta = _extract_body_delta_from_text(text)
            if body_delta:
                obj["body_delta"] = body_delta
            return obj
    return _extract_decision_fields_from_text(text)


def _normalize_fused_with_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value) if value else None
    value = value.strip()
    if not value or value.lower() in ("null", "none"):
        return None
    if "仅 merge 时填写" in value:
        return None
    return value


def _resolve_fused_with_id(value: Any, ref_to_id: dict[str, str], valid_ids: set[str]) -> Optional[str]:
    """把 DS 输出的 M01/M1/ref 或兼容旧 UUID 映射成真实 memory id。"""
    fused = _normalize_fused_with_id(value)
    if not fused:
        return None
    if fused in valid_ids:
        return fused
    compact = _compact_ref_token(fused)
    if compact in ref_to_id:
        return ref_to_id[compact]
    m = re.search(r"\bM\s*0*(\d{1,3})\b", fused, flags=re.IGNORECASE)
    if m:
        n = int(m.group(1))
        return ref_to_id.get(f"M{n:02d}") or ref_to_id.get(f"M{n}")
    return None


def _content_quality_issue(content: str) -> str:
    """拦截明显残缺的动态层便签。只拦低质量，不做语义裁判。"""
    raw = str(content or "").strip()
    text = re.sub(r"\s+", "", raw)
    if not text:
        return "missing_content"
    compact = re.sub(r"[，。！？、；：,.!?;:()（）【】\[\]{}《》\"'“”‘’…—\-_/\\|~`]+", "", text)
    if len(compact) < 12:
        return "content_too_short"
    if re.search(r"[，、；：,:;]$", raw):
        return "content_incomplete_tail"
    if re.search(
        r"(然后|但是|因为|所以|而且|并且|不过|只是|后来|接着|于是|结果|同时|另外|可是|但|可|却|跟|和|把|给|让|叫|问|说|表示|提到|觉得|想|要|准备|打算|发现|意识到|包括|比如|例如|直到|等到|还说|又说)$",
        compact,
    ):
        return "content_incomplete_tail"
    # 破折号可以是语气，不单独判残缺；只有它前面本身是“吊着没落地”的句式才拦。
    if re.search(r"(?:—|-|－){2,}\s*$", raw) and re.search(
        r"(然后|但是|因为|所以|而且|并且|不过|只是|后来|接着|于是|结果|同时|另外|可是|但|可|却|跟|和|把|给|让|叫|说了真心话|讲了真心话|说了句|说了一句|讲了句|问了句|问了一句|提到|表示|问|说)$",
        compact,
    ):
        return "content_incomplete_tail"
    for left, right in (("“", "”"), ("「", "」"), ("『", "』"), ("《", "》")):
        if raw.count(left) > raw.count(right):
            return "content_unclosed_quote"
    if raw.count('"') % 2 == 1 or raw.count("'") % 2 == 1:
        return "content_unclosed_quote"
    low_signal = {
        "记下了",
        "先记下",
        "测试一下",
        "动态层",
        "记忆",
        "老婆说",
        "辛玥说",
        "我知道了",
    }
    if compact in low_signal:
        return "content_too_generic"
    return ""


def _repair_incomplete_content_tail(content: str) -> str:
    """最终兜底：只清理明显没说完的尾巴，不扩写新事实。"""
    raw = str(content or "").strip()
    if not raw:
        return ""
    s = re.sub(r"(?:—|-|－){2,}\s*$", "", raw).strip()
    s = re.sub(
        r"(然后|但是|因为|所以|而且|并且|不过|只是|后来|接着|于是|结果|同时|另外|可是|但|可|却|跟|和|把|给|让|叫|问|说|表示|提到|觉得|想|要|准备|打算|发现|意识到|包括|比如|例如|直到|等到|还说|又说)\s*$",
        "",
        s,
    ).strip()
    s = s.rstrip("，、；：,:; ")
    if not s:
        return ""
    if not re.search(r"[。！？.!?]$", s):
        s += "。"
    return s if not _content_quality_issue(s) else ""


def _repair_decision_content_if_possible(obj: dict) -> str:
    if not isinstance(obj, dict):
        return ""
    action = str(obj.get("action") or "skip").strip().lower()
    if action not in ("new", "merge"):
        return ""
    content = str(obj.get("content") or "").strip()
    issue = _content_quality_issue(content)
    if issue not in ("content_incomplete_tail", "content_unclosed_quote"):
        return ""
    repaired = _repair_incomplete_content_tail(content)
    if repaired:
        obj["content"] = repaired
    return repaired


def _decision_structural_issue(obj: dict) -> str:
    action = str(obj.get("action") or "skip").strip().lower()
    content_text = str(obj.get("content") or "").strip()
    fused_with_id = _normalize_fused_with_id(obj.get("fused_with_id"))
    if action == "new" and not content_text:
        return "new_missing_content"
    if action == "merge" and not content_text and not fused_with_id:
        return "merge_missing_content_and_id"
    if action in ("new", "merge"):
        issue = _content_quality_issue(content_text)
        if issue:
            return issue
    return ""


def _extract_tagged_decision_blocks(text: str) -> Optional[list]:
    raw_text = _strip_json_fence(text)
    if not raw_text:
        return None
    lines = raw_text.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    saw_round = False
    for line in lines:
        if re.match(r"^\s*ROUND\s*[:：]\s*\d+\s*$", line, flags=re.IGNORECASE):
            saw_round = True
            if current:
                blocks.append("\n".join(current))
            current = [line]
            continue
        if re.match(r"^\s*-{3,}\s*$", line) and current:
            blocks.append("\n".join(current))
            current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))

    parsed: list[dict] = []
    for block in blocks:
        obj = _extract_decision_fields_from_text(block)
        if isinstance(obj, dict):
            parsed.append(obj)
    if parsed and (saw_round or len(parsed) > 1):
        return parsed
    return None


def _extract_json_array_from_ds_response(text: str) -> Optional[list]:
    """从 DS 返回中解析旧 JSON 数组或新的固定标签块。"""
    text = _strip_json_fence(text)
    if not text:
        return None
    balanced = _find_balanced_json_text(text, "[")
    for raw in (balanced, text):
        arr = _json_loads_loose(raw)
        if isinstance(arr, list):
            return arr
    tagged = _extract_tagged_decision_blocks(text)
    if isinstance(tagged, list):
        return tagged
    return None


def _build_query_from_round(round_messages: list) -> str:
    """从一轮消息中抽出合并后的文本，用于检索相关记忆。"""
    if not round_messages:
        return ""
    parts: list[str] = []
    for m in round_messages:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str):
            txt = content.strip()
        elif isinstance(content, list):
            segs = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    segs.append(c.get("text", ""))
            txt = " ".join(segs).strip()
        else:
            txt = ""
        if txt:
            parts.append(txt)
    text = "\n".join(parts)
    # 防止 query 过长影响 embedding，截断到适中长度
    return text[:2000]


def call_dynamic_layer_ds(
    round_messages: list,
    current_memories: list,
    *,
    window_id: str = "",
    round_index: int | None = None,
) -> dict:
    """
    调用 DS，返回单条决策（无整表）。
    返回字段：tag(str), action(str), importance(int), content(str), fused_with_id(str|None)。
    网关据此做单条应用；卧室仍按 action 正常应用，tag 只负责房间归类。
    """
    default = {
        "tag": "",
        "action": "skip",
        "importance": 0,
        "content": "",
        "fused_with_id": None,
        "emotion_label": "",
        "scene_type": "",
        "target_type": "",
        "body_delta": {},
    }

    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return default

    # 先在本地从 current_memories 里召回「候选记忆」，只把少量候选发给 DS，避免每轮灌入全部记忆导致 token 爆炸。
    candidates = []
    try:
        from memory_vector.dynamic_vector_retriever import dynamic_vector_retrieve

        query_text = _build_query_from_round(round_messages)
        if query_text:
            recalled = dynamic_vector_retrieve(
                query_text,
                vector_topk=10,
                final_topn=10,
            )
            if recalled:
                candidates = recalled
    except Exception as e:
        logger.debug("dynamic_layer_ds 本地检索候选失败，将回退为最近 N 条 error=%s", e)

    if not candidates:
        # 回退：取最近 N 条记忆作为候选
        N = 10
        candidates = (current_memories or [])[-N:]

    prompt_memories, ref_to_id, valid_ids = _build_memory_ref_prompt_items(candidates)
    prompt = _DYNAMIC_LAYER_PROMPT.format(
        current_memories_json=json.dumps(prompt_memories or [], ensure_ascii=False),
        round_messages_json=json.dumps(round_messages or [], ensure_ascii=False),
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0,
    }
    attempts: list[dict] = []
    try:
        content = None
        obj = None
        for attempt in range(_DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS):
            request_payload = payload
            if attempt > 0:
                last = attempts[-1] if attempts else {}
                logger.info(
                    "动态层 DS 输出未达标，开始重写 attempt=%s issue=%s",
                    attempt + 1,
                    last.get("issue") or "",
                )
                request_payload = {
                    **payload,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                            + _dynamic_layer_retry_instruction(
                                str(last.get("issue") or ""),
                                str(last.get("content") or ""),
                            )
                            + "\n若 action 是 merge，FUSED_WITH_ID 必须精确填写当前记忆列表里的 ref（如 M01），不要填写 UUID 或自己编 id；找不到明确 ref 就不要 merge，有新内容改为 new，没有就 skip。",
                        }
                    ],
                }
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=request_payload, timeout=60)
            if r.status_code >= 400:
                logger.error(
                    "动态层 DS API 错误 status=%s body=%s",
                    r.status_code,
                    (r.text or "")[:800],
                )
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = (content or "").strip()
            obj = _extract_json_from_ds_response(content)
            if isinstance(obj, dict):
                structural_issue = _decision_structural_issue(obj)
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "parsed": True,
                        "action": str(obj.get("action") or "").strip().lower(),
                        "tag": str(obj.get("tag") or "").strip(),
                        "issue": structural_issue,
                        "content": str(obj.get("content") or "").strip(),
                    }
                )
                if structural_issue:
                    logger.warning(
                        "动态层 DS 返回结构不完整 attempt=%s issue=%s preview=%s",
                        attempt + 1,
                        structural_issue,
                        _one_line_preview(content),
                    )
                    if attempt < _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1:
                        continue
                    repaired = _repair_decision_content_if_possible(obj)
                    if repaired:
                        attempts[-1]["issue"] = f"repaired_after_max:{structural_issue}"
                        attempts[-1]["repaired_content"] = repaired
                        logger.warning("动态层 DS 最终输出残缺，已保守修成完整句子 issue=%s", structural_issue)
                        break
                    logger.warning("动态层 DS 最终输出仍不完整，按 skip 处理 issue=%s", structural_issue)
                    _emit_dynamic_ds_audit_event(
                        {
                            "source": "single",
                            "window_id": window_id,
                            "round_index": round_index,
                            "round_preview": _round_messages_preview(round_messages),
                            "final_status": "failed_incomplete",
                            "final_action": "skip",
                            "final_issue": structural_issue,
                            "attempt_count": len(attempts),
                            "retry_count": max(0, len(attempts) - 1),
                            "attempts": attempts,
                        }
                    )
                    return default
                if attempt > 0:
                    logger.info("动态层 DS 重试解析成功 attempt=%s", attempt + 1)
                break
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "parsed": False,
                    "action": "",
                    "tag": "",
                    "issue": "parse_failed" if content else "empty_response",
                    "content": "",
                    "raw_preview": _one_line_preview(content),
                }
            )
            if content:
                logger.warning("动态层 DS 返回无法解析 attempt=%s preview=%s", attempt + 1, _one_line_preview(content))
            else:
                logger.info("动态层 DS 空回 attempt=%s，已按 skip/default 处理", attempt + 1)
            if attempt < _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1:
                continue  # 重试一次
            _emit_dynamic_ds_audit_event(
                {
                    "source": "single",
                    "window_id": window_id,
                    "round_index": round_index,
                    "round_preview": _round_messages_preview(round_messages),
                    "final_status": "failed_parse",
                    "final_action": "skip",
                    "final_issue": attempts[-1].get("issue") if attempts else "",
                    "attempt_count": len(attempts),
                    "retry_count": max(0, len(attempts) - 1),
                    "attempts": attempts,
                }
            )
            return default

        tag = (obj.get("tag") or "").strip()
        action = (obj.get("action") or "skip").strip().lower()
        importance = _coerce_int_1_to_4(obj.get("importance"), default=0)
        content_text = (obj.get("content") or "").strip()
        raw_fused_with_id = _normalize_fused_with_id(obj.get("fused_with_id"))
        fused_with_id = _resolve_fused_with_id(raw_fused_with_id, ref_to_id, valid_ids)
        emotion_label = str(obj.get("emotion_label") or "").strip().lower()
        scene_type = str(obj.get("scene_type") or "").strip()
        target_type = str(obj.get("target_type") or "").strip()
        body_delta = _normalize_body_delta(obj.get("body_delta"))

        if action == "merge" and not content_text and not fused_with_id:
            logger.warning("动态层 DS 返回 action=merge 但 content/fused_with_id 缺失，按 skip 处理")
            action = "skip"
        elif action == "merge" and content_text and not fused_with_id:
            logger.warning(
                "动态层 DS 返回 action=merge 但 fused_with_id 缺失或无法映射 raw=%s，降级为 new",
                raw_fused_with_id,
            )
            action = "new"
        elif action == "new" and not content_text:
            logger.warning("动态层 DS 返回 action=new 但 content 缺失，按 skip 处理")
            action = "skip"

        result = {
            "tag": tag,
            "action": action if action in ("new", "merge", "skip") else "skip",
            "importance": importance,
            "content": content_text,
            "fused_with_id": fused_with_id,
            "emotion_label": emotion_label if emotion_label in ("positive", "negative", "neutral") else "neutral",
            "scene_type": scene_type,
            "target_type": target_type,
            "body_delta": body_delta,
        }
        _emit_dynamic_ds_audit_event(
            {
                "source": "single",
                "window_id": window_id,
                "round_index": round_index,
                "round_preview": _round_messages_preview(round_messages),
                "final_status": "ok" if result["action"] in ("new", "merge") else "skip",
                "final_action": result["action"],
                "final_tag": result["tag"],
                "final_importance": result["importance"],
                "final_content": result["content"],
                "final_fused_with_id": result["fused_with_id"],
                "final_body_delta": result["body_delta"],
                "attempt_count": len(attempts),
                "retry_count": max(0, len(attempts) - 1),
                "attempts": attempts,
            }
        )
        return result
    except Exception as e:
        logger.error("动态层 DS 调用失败 error=%s", e, exc_info=True)
        _emit_dynamic_ds_audit_event(
            {
                "source": "single",
                "window_id": window_id,
                "round_index": round_index,
                "round_preview": _round_messages_preview(round_messages),
                "final_status": "api_error",
                "final_action": "skip",
                "final_issue": str(e),
                "attempt_count": len(attempts),
                "retry_count": max(0, len(attempts) - 1),
                "attempts": attempts,
            }
        )
        return default


def _normalize_single_decision(obj: Any) -> dict:
    """把 DS 返回的单条对象规范成网关用的 decision dict。"""
    default = {
        "tag": "",
        "action": "skip",
        "importance": 0,
        "content": "",
        "fused_with_id": None,
        "emotion_label": "",
        "scene_type": "",
        "target_type": "",
        "body_delta": {},
    }
    if not isinstance(obj, dict):
        return default
    tag = (obj.get("tag") or "").strip()
    action = (obj.get("action") or "skip").strip().lower()
    action = action if action in ("new", "merge", "skip") else "skip"
    importance = _coerce_int_1_to_4(obj.get("importance"), default=0)
    content_text = (obj.get("content") or "").strip()
    fused_with_id = obj.get("fused_with_id")
    emotion_label = str(obj.get("emotion_label") or "").strip().lower()
    scene_type = str(obj.get("scene_type") or "").strip()
    target_type = str(obj.get("target_type") or "").strip()
    body_delta = _normalize_body_delta(obj.get("body_delta"))
    if fused_with_id is not None and not isinstance(fused_with_id, str):
        fused_with_id = str(fused_with_id) if fused_with_id else None
    elif fused_with_id is not None and not fused_with_id.strip():
        fused_with_id = None
    if action in ("new", "merge"):
        issue = _content_quality_issue(content_text)
        if issue:
            logger.warning("动态层 DS batch 单条内容不完整，按 skip 处理 issue=%s preview=%s", issue, _one_line_preview(content_text))
            action = "skip"
            content_text = ""
            fused_with_id = None
    return {
        "tag": tag,
        "action": action,
        "importance": importance,
        "content": content_text,
        "fused_with_id": fused_with_id,
        "emotion_label": emotion_label if emotion_label in ("positive", "negative", "neutral") else "neutral",
        "scene_type": scene_type,
        "target_type": target_type,
        "body_delta": body_delta,
        "timestamp": obj.get("timestamp"),
        "last_mentioned": obj.get("last_mentioned"),
        "mention_count": obj.get("mention_count"),
    }


def _decision_action_counts(decisions: list) -> dict:
    counts = {"new": 0, "merge": 0, "skip": 0, "other": 0}
    for item in decisions or []:
        action = str((item or {}).get("action") if isinstance(item, dict) else "").strip().lower()
        if action in counts:
            counts[action] += 1
        else:
            counts["other"] += 1
    return counts


def _batch_structural_issues(arr: Any, expected_len: int) -> list[dict]:
    issues: list[dict] = []
    if not isinstance(arr, list):
        return [{"index": 0, "issue": "batch_parse_failed", "content": ""}]
    if len(arr) != expected_len:
        issues.append({"index": 0, "issue": f"batch_length_mismatch:{len(arr)}!={expected_len}", "content": ""})
    for idx, obj in enumerate(arr[:expected_len]):
        if not isinstance(obj, dict):
            issues.append({"index": idx + 1, "issue": "decision_not_object", "content": ""})
            continue
        issue = _decision_structural_issue(obj)
        if issue:
            issues.append(
                {
                    "index": idx + 1,
                    "issue": issue,
                    "action": str(obj.get("action") or "").strip().lower(),
                    "content": str(obj.get("content") or "").strip(),
                }
            )
    return issues


def _repair_batch_content_tails(arr: Any) -> list[dict]:
    repairs: list[dict] = []
    if not isinstance(arr, list):
        return repairs
    for idx, obj in enumerate(arr):
        if not isinstance(obj, dict):
            continue
        repaired = _repair_decision_content_if_possible(obj)
        if repaired:
            repairs.append({"index": idx + 1, "content": repaired})
    return repairs


def call_dynamic_layer_ds_batch(batch_rounds: list, current_memories: list) -> list:
    """
    一次请求处理多轮：把多轮对话发给 DS，解析出决策列表，与 batch_rounds 一一对应。
    本批内只做 new/skip（prompt 已约束不 merge 本批内新记忆）。
    """
    if not batch_rounds:
        return []
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return [_normalize_single_decision(None) for _ in batch_rounds]

    prompt_memories, _ref_to_id, _valid_ids = _build_memory_ref_prompt_items(current_memories or [])
    rounds_batch_json = json.dumps(batch_rounds or [], ensure_ascii=False)
    prompt = _DYNAMIC_LAYER_BATCH_PROMPT.format(
        current_memories_json=json.dumps(prompt_memories or [], ensure_ascii=False),
        rounds_batch_json=rounds_batch_json,
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    # 多轮需要更大输出
    max_tokens = min(8000, 500 * max(len(batch_rounds), 1))
    payload: dict[str, Any] = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    attempts: list[dict] = []
    try:
        for attempt in range(_DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS):
            request_payload = payload
            if attempt > 0:
                last_issue = attempts[-1].get("issue") if attempts else ""
                last_content = attempts[-1].get("content") if attempts else ""
                request_payload = {
                    **payload,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                            + _dynamic_layer_retry_instruction(str(last_issue or ""), str(last_content or ""), batch=True),
                        }
                    ],
                }
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=request_payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = (content or "").strip()
            arr = _extract_json_array_from_ds_response(content)
            repairs = _repair_batch_content_tails(arr) if attempt == _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1 else []
            issues = _batch_structural_issues(arr, len(batch_rounds))
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "parsed": isinstance(arr, list),
                    "issue": "; ".join(f"#{x.get('index')}:{x.get('issue')}" for x in issues[:5]),
                    "content": _one_line_preview((issues[0].get("content") if issues else "") or content, limit=220),
                    "action_counts": _decision_action_counts(arr if isinstance(arr, list) else []),
                    "repairs": repairs,
                }
            )
            if issues:
                logger.warning(
                    "动态层 DS batch 输出未达标 attempt=%s issues=%s",
                    attempt + 1,
                    attempts[-1].get("issue"),
                )
                if attempt < _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1:
                    continue
                _emit_dynamic_ds_audit_event(
                    {
                        "source": "batch",
                        "batch_size": len(batch_rounds),
                        "final_status": "failed_incomplete",
                        "final_action": "skip",
                        "final_issue": attempts[-1].get("issue"),
                        "attempt_count": len(attempts),
                        "retry_count": max(0, len(attempts) - 1),
                        "attempts": attempts,
                    }
                )
                return [_normalize_single_decision(None) for _ in batch_rounds]
            out = [_normalize_single_decision(x) for x in arr]
            _emit_dynamic_ds_audit_event(
                {
                    "source": "batch",
                    "batch_size": len(batch_rounds),
                    "final_status": "ok",
                    "action_counts": _decision_action_counts(out),
                    "attempt_count": len(attempts),
                    "retry_count": max(0, len(attempts) - 1),
                    "attempts": attempts,
                }
            )
            return out
    except Exception as e:
        logger.error("动态层 DS batch 调用失败 error=%s", e, exc_info=True)
        _emit_dynamic_ds_audit_event(
            {
                "source": "batch",
                "batch_size": len(batch_rounds),
                "final_status": "api_error",
                "final_action": "skip",
                "final_issue": str(e),
                "attempt_count": len(attempts),
                "retry_count": max(0, len(attempts) - 1),
                "attempts": attempts,
            }
        )
        return [_normalize_single_decision(None) for _ in batch_rounds]


# ---------- 归档脚本专用：读 scripts/archive_ds_prompt.txt，批处理一次请求 ----------
_ARCHIVE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "archive_ds_prompt.txt"


def _load_archive_batch_prompt_template() -> str:
    """归档脚本批处理用 prompt，占位符 current_memories_json、rounds_batch_json。"""
    if not _ARCHIVE_PROMPT_PATH.exists():
        logger.warning("归档 prompt 文件不存在 path=%s，将回退网关批处理 prompt", _ARCHIVE_PROMPT_PATH)
        return _DYNAMIC_LAYER_BATCH_PROMPT
    try:
        return _ARCHIVE_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("读取归档 prompt 失败 path=%s error=%s，将回退网关批处理 prompt", _ARCHIVE_PROMPT_PATH, e)
        return _DYNAMIC_LAYER_BATCH_PROMPT


def call_archive_batch_ds(batch_rounds: list, current_memories: list) -> list:
    """
    归档脚本批处理：用 scripts/archive_ds_prompt.txt 一次请求多轮，解析出决策列表。
    与 call_dynamic_layer_ds_batch 同逻辑，仅 prompt 来源不同。
    """
    if not batch_rounds:
        return []
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return [_normalize_single_decision(None) for _ in batch_rounds]

    template = _load_archive_batch_prompt_template()
    # 只传最近 N 条记忆，避免单次请求超 131072 context（current_memories 会越积越多）
    _ARCHIVE_MEMORIES_MAX = 50
    memories_for_prompt = (current_memories or [])[-_ARCHIVE_MEMORIES_MAX:]
    # 每轮对话截断到最多 2500 字再发给 DS，避免单批 6 轮合起来超长
    _MAX_CHARS_PER_ROUND = 2500
    rounds_for_prompt = []
    for r in batch_rounds or []:
        if not isinstance(r, dict):
            rounds_for_prompt.append(r)
            continue
        msgs = r.get("messages") or []
        parts = []
        n = 0
        for m in msgs:
            if not isinstance(m, dict):
                continue
            s = (m.get("content") or "").strip()
            if not s:
                continue
            if n + len(s) > _MAX_CHARS_PER_ROUND:
                s = s[: max(0, _MAX_CHARS_PER_ROUND - n)] + "…"
            parts.append({"role": m.get("role", "user"), "content": s})
            n += len(s)
            if n >= _MAX_CHARS_PER_ROUND:
                break
        rounds_for_prompt.append({"round_timestamp": r.get("round_timestamp") or "", "messages": parts})
    prompt = template.replace(
        "{current_memories_json}", json.dumps(memories_for_prompt, ensure_ascii=False)
    ).replace(
        "{rounds_batch_json}", json.dumps(rounds_for_prompt, ensure_ascii=False)
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    max_tokens = min(2000, 400 * max(len(batch_rounds), 1))
    payload: dict[str, Any] = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    last_err: Exception | None = None
    attempts: list[dict] = []
    final_failure_status = "api_error"
    for attempt in range(_DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS):
        try:
            request_payload = payload
            if attempt > 0 and attempts and attempts[-1].get("issue"):
                request_payload = {
                    **payload,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                            + _dynamic_layer_retry_instruction(
                                str(attempts[-1].get("issue") or ""),
                                str(attempts[-1].get("content") or ""),
                                batch=True,
                            ),
                        }
                    ],
                }
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=request_payload, timeout=120)
            if r.status_code >= 400:
                logger.error(
                    "归档 DS API 错误 status=%s body=%s",
                    r.status_code,
                    (r.text or "")[:800],
                )
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = (content or "").strip()
            arr = _extract_json_array_from_ds_response(content)
            repairs = _repair_batch_content_tails(arr) if attempt == _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1 else []
            issues = _batch_structural_issues(arr, len(batch_rounds))
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "parsed": isinstance(arr, list),
                    "issue": "; ".join(f"#{x.get('index')}:{x.get('issue')}" for x in issues[:5]),
                    "content": _one_line_preview((issues[0].get("content") if issues else "") or content, limit=220),
                    "action_counts": _decision_action_counts(arr if isinstance(arr, list) else []),
                    "repairs": repairs,
                }
            )
            if issues:
                logger.warning(
                    "归档 DS batch 输出未达标 attempt=%s issues=%s",
                    attempt + 1,
                    attempts[-1].get("issue"),
                )
                if attempt < _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1:
                    continue
                last_err = RuntimeError("归档 DS 本批输出仍有残缺记忆，不写断点以便下次重跑")
                final_failure_status = "failed_incomplete"
                break
            out = [_normalize_single_decision(x) for x in arr]
            _emit_dynamic_ds_audit_event(
                {
                    "source": "archive_batch",
                    "batch_size": len(batch_rounds),
                    "final_status": "ok",
                    "action_counts": _decision_action_counts(out),
                    "attempt_count": len(attempts),
                    "retry_count": max(0, len(attempts) - 1),
                    "attempts": attempts,
                }
            )
            return out
        except Exception as e:
            last_err = e
            logger.warning("归档 DS batch 第 %s 次失败 error=%s", attempt + 1, e)
            if attempt < _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS - 1:
                time.sleep(2)
    _emit_dynamic_ds_audit_event(
        {
            "source": "archive_batch",
            "batch_size": len(batch_rounds),
            "final_status": final_failure_status,
            "final_action": "retry_later",
            "final_issue": str(last_err or ""),
            "attempt_count": len(attempts),
            "retry_count": max(0, len(attempts) - 1),
            "attempts": attempts,
        }
    )
    logger.error("归档 DS batch 调用失败（已重试 %s 次） error=%s", _DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS, last_err, exc_info=True)
    raise RuntimeError("归档 DS 本批请求失败，不写断点以便重跑从本批重试") from last_err
