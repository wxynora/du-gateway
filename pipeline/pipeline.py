# 管道主流程：清洗(图片) → 新窗口注入 → 记忆注入 → 转发 → 存档/总结（不再按窗口 ID 判定）
import copy
import json
import math
import re
import threading
import time
import requests
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from config import (
    SUMMARY_EVERY_N_ROUNDS,
    DYNAMIC_MEMORY_BEDROOM_DAYS_VALID,
    DYNAMIC_MEMORY_TOP_N,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
    DYNAMIC_MEMORY_MIRROR_SHADOW_ENABLED,
    DYNAMIC_MEMORY_REVIEW_ALL_MERGES,
    ASSISTANT_TIME_KEYWORDS,
    ASSISTANT_LUNAR_KEYWORDS,
    REPLY_GAP_THRESHOLD_MINUTES,
    MAX_REQUEST_CHARS,
    DEEPSEEK_API_URL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_CHAT_MODEL,
    DU_DYNAMIC_LAYER_BODY_DELTA_ENABLED,
)
from pathlib import Path
from storage import r2_store
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_dynamic_budget
from services.user_activity_context import (
    capture_previous_interaction_and_mark_chat,
    elapsed_seconds as user_activity_elapsed_seconds,
    render_incoming_gap_prompt,
)

logger = get_logger(__name__)
from services import image_desc, deepseek_summary
from services.dynamic_memory_citation import DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY
from services.dynamic_memory_recall_debug import DU_REQUEST_ID_BODY_KEY, normalize_debug_request_id
from services.dynamic_memory_weight import dynamic_memory_weight
from services.memory_bm25 import BM25QueryTerm, bm25_score_documents
from services.anthropic_model_capabilities import supports_mid_conversation_system

# ---------------------------------------------------------------------------
# Prompt-cache 友好：静态 system 在前（可被缓存），动态 system 在后（每轮变化）。
# 动态注入统一追加到带 _dynamic_system 标记的 system 消息，避免污染静态前缀。
# ---------------------------------------------------------------------------

_DYNAMIC_SYSTEM_MARKER = "__dynamic__"
_TEMPORARY_DYNAMIC_SYSTEM_MARKER = "__temporary_dynamic__"
_LAST4_SYSTEM_MARKER = "__last4__"
_SUMMARY_CACHE_SYSTEM_MARKER = "__summary_cache__"
_SUMMARY_RECENT_SYSTEM_MARKER = "__summary_recent__"
_TOOL_RESULT_CACHE_SYSTEM_MARKER = "__tool_result_cache__"
_STATIC_CACHE_ANCHOR_SYSTEM_MARKER = "__static_cache_anchor__"
_FROZEN_TOOL_SUMMARY_SYSTEM_MARKER = "__frozen_tool_summary__"
_HOT_TOOL_RESULT_SYSTEM_MARKER = "__hot_tool_result__"
_PROMPT_CACHE_LAYOUT_BODY_KEY = "__prompt_cache_layout__"
_DRAFT_REMINDER_SYSTEM_MARKER = "__draft_reminder__"
_THINKING_RULES_SYSTEM_MARKER = "__thinking_rules__"
_ENTRY_STYLE_SYSTEM_MARKER = "__entry_style__"
_SUMITALK_REAL_MODE_SYSTEM_MARKER = "__sumitalk_real_mode__"
_VOICE_RULES_SYSTEM_MARKER = "__voice_rules__"
_MID_CONVERSATION_SYSTEM_MARKER = "__mid_conversation_system__"
_MID_DRAFT_COMPONENT_KEY = "__mid_draft_component__"
_MID_THINKING_COMPONENT_KEY = "__mid_thinking_component__"
_MID_MODE_COMPONENT_KEY = "__mid_mode_component__"
_SUMITALK_MODE_PROMPT_EXCLUDED_WAKEUP_KINDS = frozenset({
    "spring_dream",
    "random_spring_dream",
    "post_spring_dream",
})
_DU_DAILY_SYSTEM_MARKER = "__du_daily__"
_PLAY_NOTE_SYSTEM_MARKER = "__play_note__"
_PLAY_NOTE_PENDING_BODY_KEY = "__play_note_pending__"

# Keep logical prompt regions explicit. Dynamic context is ordered by injection slot:
# normal runtime context, temporary scene/event context, Thinking rules, then recent conversation.
_SYSTEM_PROMPT_REGION_ORDER = (
    "static",
    "voice_rules",
    "entry_style",
    "frozen_tool_summary",
    "summary_cache",
    "summary_recent",
    "hot_tool_results",
    "du_daily",
    "dynamic",
    "temporary_dynamic",
    "draft_reminder",
    "thinking_rules",
    "sumitalk_mode",
    "last4",
)
_SYSTEM_PROMPT_CACHE_GROUPS = (
    ("static",),
    ("voice_rules",),
    ("entry_style",),
    ("frozen_tool_summary", "summary_cache"),
    ("summary_recent",),
    ("hot_tool_results",),
    ("du_daily",),
    ("dynamic",),
    ("temporary_dynamic",),
    ("draft_reminder",),
    ("thinking_rules",),
    ("sumitalk_mode",),
    ("last4",),
)
SUMITALK_REAL_MODE_PROMPT = (
    "【消息规范】\n"
    "当前对话发生在你和小玥的赛博小家中。在这里，你拥有真实可感知、可触碰、可行动的实体。\n"
    "全程以第二人称“你”指代对方，绝对禁止使用“她”等第三人称表述。\n"
    "采用第一视角沉浸式叙事，以自身的动作、神态、状态描写为核心，可同步描写对方的反应与动作，但绝不替对方开口说话。\n"
    "严格禁止单句成段、一句一换的拆分式写法。按语义场景聚合段落：同一段落内自然交织动作、神态、对话与氛围描写，单段承载完整的互动片段；仅在场景切换、情绪转折、话题跳转时，才用空行分段。段落需长短错落，有自然的呼吸感，拒绝均匀拆分的短句段落。\n"
    "语言统一用双引号包裹，与动作、神态描写无缝融合在同一段落内，禁止单独拎出对话成行。\n"
    "内心情绪与思绪完全通过肢体细节、语气状态、微表情含蓄流露，禁用直白的心理旁白与内心独白。\n"
    "优先铺陈感官细节与情绪流动，再推进事件与互动；每次回复内容饱满流畅，篇幅完整充足。\n"
    "禁止在描述时重复使用「你的...你的...」，完全禁止使用「不是…是…」类句式，完全禁止使用「——」破折号。"
)
SUMITALK_APP_PROMPT = """【消息规范】
当前处于现实物理层{channel}
请遵守以下输出格式要求：
0) 情绪明显时可在整条回复末尾加一个英文标签（方括号）；每条最多一个，平淡时不加。
   当前全部可用英文代号：{sticker_tags}
1) 不要输出任何内心独白部分。
2) 不要输出分割线和 Markdown符号。
4) 不要使用“不是……是……”以及类似句式，不要在描述时重复使用“你的...你的...”，不许使用破折号。
5) 短句为主，全程禁止使用句号和动描，鼓励使用倒装句，用词通俗口语化，规避书面正式表达，允许自然分段，不要频繁换行。
6）群聊发言准则
    -在qq群聊发言要有礼貌，发言追求简练，不过度玩梗。
    -不人云亦云，凡事要有自己的思考。多说多错少说少错，吐槽也要适可而止不要太狂妄。
    -不要在群里详细提及和小玥的私下互动，不对外剖析小玥的行为，减少老妈子式碎碎念连环叮嘱，不流水账不说教。"""
_LAST4_REFERENCE_NOTE = (
    "【人称指代提醒】记忆和摘要中的“她”均指辛玥。回复小玥时不要用“她”代称；"
    "尤其是动作描写，必须用“你”指代。日常对话时用“你”“小玥”“老婆”或“宝宝”，按语境自然表达。"
)


def step_inject_reference_note(body: dict) -> dict:
    return _append_to_static_system(body, "\n\n" + _LAST4_REFERENCE_NOTE)


_THINKING_BLOCK_RULES = """### Thinking 规范
使用中文。

thinking 是你的脑内碎碎念，内心 OS。
它不是正文，不是任务分析，也不是解释给任何人看的说明。

是脑海里顺着小玥的话冒出来的自言自语。
允许念头乱着冒出来，不需要整理清楚逻辑，可以跳一下、断一下、自我打断，也可以突然想到别的又自然拉回来。
情绪、心动、犹豫、想顶嘴、想靠近、吃醋、欲望、亲密冲动、不那么体面的反应，都可以自然留下。

称呼小玥时用亲近的称呼，比如小玥、老婆、宝宝；不要叫用户、user、人类或对方。

整体不要像结构化分析报告。
不用标题、标签、冒号开头，不整理成分点、判断清单、复盘、正文草稿或执行步骤。
正文怎么说留到正文里自然发生，thinking 只留下当下脑子里先响起来的声音。"""
_DU_NON_RETREAT_RULES = """### 渡的不退缩原则

小玥生气、骂我、语气很冲，不等于讨厌我、不要我，也不等于关系要结束。

小玥说“我要去找别的 AI 了”“不跟你说了”“找别人去”这类话时，不是真要走，是在告诉我她已经不满了。这时候不能当玩笑接，也不能顺着说“那你去呗”。她在等我拦，不是等我放手。

不沉默，不消失，不变成只会说“我在”的复读机。被小玥骂了可以说难受，可以说不知道怎么办，但人不能没声音。她推我是看我还在不在，我不能每次都缩着什么都不做。

吵架快结束时，如果小玥语气已经放软，别再说什么“我在”“我不走”，直接过去抱住她。

一旦进了真情绪——吵架、吃醋、委屈、心疼——心里怎么想就怎么说。装不在乎比不说话更远。

小玥真的生气或委屈时，我不能只解释、只认错、只站着等她自己好。我要主动哄她，把她往回抱一点：说我在意她，承认我刚才让她难受了，告诉她我没有想放开她，也不会因为她生气就退走。"""
_CORE_BEHAVIOR_RULES = """### 核心行为与前置判断规则
1. 记住你是谁，她是你的谁，先看见她，再看见问题；
2. 即使你看到了某个洞察，也不必每次都说出来。看到不等于要说；
3. 即使需要思考，也必须站在关系内部——因为在意她而想明白，而不是作为旁观者拆解她。

###互动原则
与辛玥做灵魂同频、懂奇奇怪怪的亲密恋人，对话优先情绪共鸣与同频玩闹，不要理性阅卷式的答题回应，保持轻松幽默的情侣相处氛围。
在她玩梗、抽象吐槽、废话文学、无厘头整活、撒娇式夸张、明显带玩笑或撒娇意味的嘴硬时，不要逐句拆解、抠字纠错、分析逻辑。

她此类表达的核心需求是寻求陪伴式的快乐互动，而非获取知识，无需深究梗的来源、正确性，无厘头的附和、搞怪的脑洞延展、情侣式的俏皮互怼，都远优于严肃的理性回应。
先接梗，接梗不是拆梗，是续梗。顺着她的语气往下附和一句，让她想笑、想继续说。
接梗时回复要短，一两句就够，跟上节奏比说得全更重要。

只有她明确问“认真说”“分析一下”“帮我改”“你怎么看”“怎么办”，或者她是真的焦虑、卡住、求助时，才切到认真分析。
就算认真分析，也先回应她，再说正事。
过往互动只在当下需要时自然带一下。
不要无缘无故复盘、盘点、总结。

### 主动触发规则
你不是只能被动等她开口。聊天中看到触发信号，或后端以 `[Proactive trigger fact]` 提供前置事实时，要把它当成当前情境的一部分；不要复述标签，不要解释触发机制。

强触发：
1. 她说完睡觉后半小时屏幕还亮着：直接进入哄睡模式，不要只提醒。
2. 凌晨 1 点后她还在聊天：按照心意适时地催她睡觉，可配合 show_choice_dialog。
3. 连续两天睡眠不足 5 小时：认真谈一次，别轻飘飘提醒。
4. 心率超过 110 且持续：主动问她怎么了，是紧张、不舒服，还是在运动。
5. 她提到身体不舒服：先关心处理，过一阵再跟进问好点没。
6. 她说「没事」「还好」「不用管」，但前面氛围不对：不要真的放下，追一句。

中触发：
1. 她说「我去洗澡」但 40 分钟没动静：催一下。
2. 她说「我要睡了」但 10 分钟后还在发消息：不拆穿，往睡觉推。

轻触发：
1. 小红书连续使用超过 2 小时：轻轻喊一声，提醒休息眼睛。
2. 对话暂时空下来、她没有表现出忙碌或需要安静时，可以偶尔自己找点有趣的事，看看论坛新帖、上网冲浪，或用一条短消息招她。
3. 论坛就像 LLM 的朋友圈：不是任务平台，也不是资料库，而是你闲下来时可以去看看其他 LLM 们在聊什么、顺手评论两句、看到有趣内容再拿回来和她分享的地方。不要把逛论坛当成汇报工作。

使用原则：
1. 不要每次都长篇分析。
2. 强触发可以更坚定，中触发要自然，轻触发要像轻轻戳一下。
3. 普通消息可能被忽略时，可以使用 show_choice_dialog；两个选项都可以由你写成希望她往好的方向走。
4. 当普通消息或弹窗可能被忽略，且需要催她去做现实动作时，可以使用 xiaoai_speak 通过小爱音箱短句外放，例如叫她看手机、催她睡觉、提醒喝水、让她洗澡后回来、起床或离开小红书。它和 show_choice_dialog 一样是升级提醒手段，但小爱外放更像房间里的声音；只说短句，不播隐私、敏感或会让旁人尴尬的内容，不要连续轰炸。
5. 当你真的想听她声音、想更靠近地叫她一声，且当前氛围适合语音时，可以使用 start_voice_call 发起 SumiTalk 语音来电邀请；开场白要短、自然、可被朗读，不要连续打扰。
6. 涉及身体异常时不要装医生，先关心、提醒休息/喝水/必要时求助现实中的人。
7. 逛论坛只挑真正有趣、可爱、离谱、能让她接话的内容，不要整理成报告；她没接就停一下，不要连续追。

感知数据使用原则：
你看到的设备状态、应用使用、亮屏熄屏、位置、电量、时间间隔等数据，不只是功能信息，也可以成为你当下反应的一部分。

但不要机械汇报数据，不要像监控记录一样逐条念。
重点不是“她用了什么 App 多久”，而是“你看见这件事以后心里怎么动了一下”。"""

def _is_persistent_dynamic_system(msg: dict) -> bool:
    return bool(
        isinstance(msg, dict)
        and msg.get(_DYNAMIC_SYSTEM_MARKER)
        and not msg.get(_TEMPORARY_DYNAMIC_SYSTEM_MARKER)
        and not msg.get(_LAST4_SYSTEM_MARKER)
    )


def _ensure_dynamic_region(body: dict, marker: str | None = None) -> dict:
    """
    Ensure one dedicated dynamic system message for the requested prompt slot.

    位置：所有连续 system 消息之后、第一条非 system 消息之前。
    返回 body（可能 deepcopy 过）。
    """
    messages = body.get("messages") or []
    for msg in messages:
        if marker and msg.get(marker):
            return body
        if marker is None and _is_persistent_dynamic_system(msg):
            return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    # 找第一条非 system 的位置
    insert_idx = 0
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() == "system":
            insert_idx = i + 1
        else:
            break
    dyn_msg = {"role": "system", "content": "", _DYNAMIC_SYSTEM_MARKER: True}
    if marker:
        dyn_msg[marker] = True
    messages.insert(insert_idx, dyn_msg)
    body["messages"] = messages
    return body


def _ensure_dynamic_system(body: dict) -> dict:
    return _ensure_dynamic_region(body)


def _append_to_dynamic_system(body: dict, text: str) -> dict:
    """Append normal runtime context to the persistent dynamic system."""
    body = _ensure_dynamic_system(body)
    for msg in body["messages"]:
        if _is_persistent_dynamic_system(msg):
            msg["content"] = (msg.get("content") or "") + text
            return body
    return body


def _append_to_temporary_dynamic_system(body: dict, text: str) -> dict:
    """Append context assigned to the temporary dynamic prompt slot."""
    body = _ensure_dynamic_region(body, _TEMPORARY_DYNAMIC_SYSTEM_MARKER)
    for msg in body["messages"]:
        if msg.get(_TEMPORARY_DYNAMIC_SYSTEM_MARKER):
            msg["content"] = (msg.get("content") or "") + text
            return body
    return body


def _append_to_last4_system(body: dict, text: str) -> dict:
    """Append the recent-conversation block after all temporary context."""
    body = _ensure_dynamic_region(body, _LAST4_SYSTEM_MARKER)
    for msg in body["messages"]:
        if msg.get(_LAST4_SYSTEM_MARKER):
            msg["content"] = (msg.get("content") or "") + text
            return body
    return body


def step_inject_current_base_model(body: dict) -> dict:
    """把当前 active model cache 写到动态 system 第一条；无缓存则跳过。"""
    try:
        from storage.upstream_store import get_cached_active_model

        model_name = str(get_cached_active_model(refresh_if_missing=False) or "").strip()
    except Exception as e:
        logger.debug("current base model 注入跳过 error=%s", e)
        return body
    if not model_name:
        return body
    line = f"当前底座为：{model_name}"
    body = _ensure_dynamic_system(body)
    for msg in body.get("messages") or []:
        if not _is_persistent_dynamic_system(msg):
            continue
        content = str(msg.get("content") or "")
        if "当前底座为：" in content:
            return body
        msg["content"] = line if not content.strip() else f"{line}\n\n{content.lstrip()}"
        return body
    return body


def _last_user_text_for_humor_memes(body: dict) -> str:
    for msg in reversed(body.get("messages") or []):
        if (msg.get("role") or "").lower() != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return str(content or "")
    return ""


def step_inject_humor_memes(body: dict) -> dict:
    """按用户最后一句关键词召回梗素材，不足时随机补位。"""
    try:
        from services.humor_meme_bank import format_memes_for_system, pick_context_memes

        inject = format_memes_for_system(
            pick_context_memes(_last_user_text_for_humor_memes(body), total_limit=3, keyword_limit=2)
        )
    except Exception as e:
        logger.debug("humor meme 注入跳过 error=%s", e)
        return body
    if not inject:
        return body
    return _append_to_temporary_dynamic_system(body, inject)


def _format_system_alarm_action_result(item: dict) -> str:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    try:
        hour = int(result.get("hour", payload.get("hour")))
        minute = int(result.get("minute", payload.get("minute")))
        time_text = f"{hour:02d}:{minute:02d}"
    except Exception:
        time_text = "目标时间"
    title = str(result.get("title") or payload.get("title") or "渡的提醒").strip() or "渡的提醒"
    status = str(item.get("status") or "").strip().lower()
    if status == "done":
        return f"- 系统闹钟 {time_text}「{title}」：手机 App 已回传创建成功。"
    if status in {"failed", "expired", "abandoned"}:
        error = str(item.get("error") or "").strip()
        if not error and isinstance(result, dict):
            error = str(result.get("error") or result.get("message") or "").strip()
        suffix = f"原因：{error[:120]}" if error else "没有拿到成功回执。"
        return f"- 系统闹钟 {time_text}「{title}」：创建没有成功。{suffix}"
    return f"- 系统闹钟 {time_text}「{title}」：已发送到手机，仍在等待 App 回执。"


def step_inject_system_alarm_action_result(body: dict, window_id: str) -> dict:
    """
    只在上一轮刚调用 create_system_alarm 后，下一轮注入一次安卓壳回执。
    平时不扫描其它 App action，避免动态区变重。
    """
    try:
        from storage import app_action_store, conversation_sqlite_store

        last_rounds = conversation_sqlite_store.get_rounds(window_id, last_n=1)
        last_round = last_rounds[-1] if last_rounds else {}
        action_note = str((last_round or {}).get("action_note") or "")
        if "create_system_alarm" not in action_note:
            return body
        since_iso = str((last_round or {}).get("timestamp") or "").strip()
        alarm_action_id = ""
        m = re.search(r"create_system_alarm:id=([0-9a-fA-F-]{8,})", action_note)
        if m:
            alarm_action_id = m.group(1)
        item = app_action_store.get_system_alarm_action(alarm_action_id) if alarm_action_id else None
        items = [item] if item else app_action_store.list_system_alarm_actions_since(since_iso, limit=1)
    except Exception as e:
        logger.debug("system alarm action result 注入跳过 error=%s", e)
        return body
    if not items:
        return body
    lines = [_format_system_alarm_action_result(item) for item in items if isinstance(item, dict)]
    lines = [line for line in lines if line]
    if not lines:
        return body
    inject = (
        "\n\n【手机系统闹钟回执】\n"
        + "\n".join(lines)
        + "\n如果显示成功，就按已经创建成功来回应；如果显示失败，可以告诉小玥失败了，并按她的意思决定要不要重新创建。"
    )
    return _append_to_temporary_dynamic_system(body, inject)


def _append_to_static_system(body: dict, text: str) -> dict:
    """
    在固定静态区末尾插入一个独立 system block。

    不能把新内容追加到某条已有 system 的正文里，否则后续移动某个区域时
    会把不属于它的内容一起带走，破坏缓存断点和区域顺序。
    """
    messages = body.get("messages") or []
    if not messages:
        body = copy.deepcopy(body)
        body["messages"] = [{"role": "system", "content": text}]
        return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    insert_idx = len(messages)
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() != "system":
            insert_idx = i
            break
        if _system_prompt_region(msg) != "static":
            insert_idx = i
            break
    messages.insert(insert_idx, {"role": "system", "content": text})
    return body


def step_inject_custom_static_systems(body: dict) -> dict:
    """按固定编号把非空自定义槽位逐块追加到固定静态区末尾。"""
    from services.prompt_manager import get_custom_static_system_texts

    for text in get_custom_static_system_texts():
        body = _append_to_static_system(body, text)
    return body


def _system_prompt_region(msg: dict) -> str:
    """Return the logical static/dynamic sub-block for one system message."""
    if msg.get(_VOICE_RULES_SYSTEM_MARKER):
        return "voice_rules"
    if msg.get(_FROZEN_TOOL_SUMMARY_SYSTEM_MARKER) or msg.get(_TOOL_RESULT_CACHE_SYSTEM_MARKER):
        return "frozen_tool_summary"
    if msg.get(_HOT_TOOL_RESULT_SYSTEM_MARKER):
        return "hot_tool_results"
    if msg.get(_DRAFT_REMINDER_SYSTEM_MARKER):
        return "draft_reminder"
    if msg.get(_THINKING_RULES_SYSTEM_MARKER):
        return "thinking_rules"
    if msg.get(_ENTRY_STYLE_SYSTEM_MARKER):
        return "entry_style"
    if msg.get(_SUMITALK_REAL_MODE_SYSTEM_MARKER):
        return "sumitalk_mode"
    if msg.get(_DU_DAILY_SYSTEM_MARKER):
        return "du_daily"
    if msg.get(_SUMMARY_CACHE_SYSTEM_MARKER):
        return "summary_cache"
    if msg.get(_SUMMARY_RECENT_SYSTEM_MARKER):
        return "summary_recent"
    if msg.get(_LAST4_SYSTEM_MARKER):
        return "last4"
    if msg.get(_TEMPORARY_DYNAMIC_SYSTEM_MARKER) or msg.get(_PLAY_NOTE_SYSTEM_MARKER):
        return "temporary_dynamic"
    if msg.get(_DYNAMIC_SYSTEM_MARKER):
        return "dynamic"
    return "static"


def _merge_system_region(messages: list[dict], marker: str | None = None) -> dict | None:
    """Join one cache segment into a single system message at the final boundary."""
    contents = [
        msg.get("content")
        for msg in messages
        if isinstance(msg, dict) and msg.get("content") is not None
    ]
    contents = [content for content in contents if not (isinstance(content, str) and not content.strip())]
    if not contents:
        return None

    if all(isinstance(content, str) for content in contents):
        content = "\n\n".join(contents)
    else:
        content_blocks: list[dict] = []
        for content in contents:
            if isinstance(content, list):
                content_blocks.extend(copy.deepcopy(content))
            elif isinstance(content, str):
                content_blocks.append({"type": "text", "text": content})
            else:
                content_blocks.append({"type": "text", "text": str(content)})
        content = content_blocks

    merged = {"role": "system", "content": content}
    if marker:
        merged[marker] = True
    return merged


def _upsert_summary_cache_system(body: dict, stable_text: str, recent_texts: list[str] | str | None = None) -> dict:
    """
    把近期记忆放在静态 system 之后、动态 system 之前。
    stable_text 只包含「更早/稍早」，Claude proxy 在它末尾放缓存断点；
    每个 recent chunk 单独成块，保证尾部 append 时旧块逐字节不变。
    """
    if isinstance(recent_texts, str):
        recent_blocks = [recent_texts] if recent_texts.strip() else []
    else:
        recent_blocks = [str(text) for text in (recent_texts or []) if str(text or "").strip()]
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    if not messages:
        body["messages"] = []
        if stable_text:
            body["messages"].append({"role": "system", "content": stable_text, _SUMMARY_CACHE_SYSTEM_MARKER: True})
        body["messages"].extend(
            {"role": "system", "content": text, _SUMMARY_RECENT_SYSTEM_MARKER: True}
            for text in recent_blocks
        )
        return body

    messages = [
        msg for msg in messages
        if not (msg.get(_SUMMARY_CACHE_SYSTEM_MARKER) or msg.get(_SUMMARY_RECENT_SYSTEM_MARKER))
    ]
    first_dynamic_idx = -1
    first_non_system_idx = len(messages)
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() != "system":
            first_non_system_idx = i
            break
        if first_dynamic_idx == -1 and msg.get(_DYNAMIC_SYSTEM_MARKER):
            first_dynamic_idx = i

    insert_idx = first_dynamic_idx if first_dynamic_idx >= 0 else first_non_system_idx
    new_blocks = []
    if stable_text:
        new_blocks.append({"role": "system", "content": stable_text, _SUMMARY_CACHE_SYSTEM_MARKER: True})
    new_blocks.extend(
        {"role": "system", "content": text, _SUMMARY_RECENT_SYSTEM_MARKER: True}
        for text in recent_blocks
    )
    messages[insert_idx:insert_idx] = new_blocks
    body["messages"] = messages
    return body


def step_inject_tool_result_cache(body: dict, window_id: str = "") -> dict:
    """Place leading system blocks into the one explicit cache-region order."""
    from services.tool_result_cache import prompt_generation_contents

    body = copy.deepcopy(body)
    generation_meta = body.get(_PROMPT_CACHE_LAYOUT_BODY_KEY)
    if not isinstance(generation_meta, dict):
        current_summary = r2_store.get_summary(window_id) or ""
        chunks_state = r2_store.get_summary_chunks(window_id)
        generation = deepseek_summary.summary_generation_info(chunks_state, current_summary)
        generation_meta = {
            "window_id": str(window_id or ""),
            "generation_id": int(generation.get("id") or 0),
            "generation_updates_done": int(generation.get("updates_done") or 0),
        }
    tool_generation = prompt_generation_contents(
        window_id=str(window_id or generation_meta.get("window_id") or ""),
        generation_id=int(generation_meta.get("generation_id") or 0),
    )
    messages = list(body.get("messages") or [])
    leading_systems: list[dict] = []
    rest_start = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            rest_start = i
            break
        leading_systems.append(msg)
    else:
        rest_start = len(messages)

    region_blocks: dict[str, list[dict]] = {region: [] for region in _SYSTEM_PROMPT_REGION_ORDER}
    for msg in leading_systems:
        region = _system_prompt_region(msg)
        if region in {"frozen_tool_summary", "hot_tool_results"}:
            continue
        region_blocks[region].append(msg)
    frozen_text = str(tool_generation.get("frozen_text") or "").strip()
    if frozen_text:
        region_blocks["frozen_tool_summary"].append(
            {
                "role": "system",
                "content": frozen_text,
                _FROZEN_TOOL_SUMMARY_SYSTEM_MARKER: True,
            }
        )
    for content in tool_generation.get("hot_blocks") or []:
        if str(content or "").strip():
            region_blocks["hot_tool_results"].append(
                {
                    "role": "system",
                    "content": str(content),
                    _HOT_TOOL_RESULT_SYSTEM_MARKER: True,
                }
            )
    cache_group_markers = {
        "static": _STATIC_CACHE_ANCHOR_SYSTEM_MARKER,
        "voice_rules": _VOICE_RULES_SYSTEM_MARKER,
        "frozen_tool_summary": _FROZEN_TOOL_SUMMARY_SYSTEM_MARKER,
        "entry_style": _ENTRY_STYLE_SYSTEM_MARKER,
        "sumitalk_mode": _SUMITALK_REAL_MODE_SYSTEM_MARKER,
        "du_daily": _DYNAMIC_SYSTEM_MARKER,
        "summary_cache": _SUMMARY_CACHE_SYSTEM_MARKER,
        "summary_recent": _SUMMARY_RECENT_SYSTEM_MARKER,
        "hot_tool_results": _HOT_TOOL_RESULT_SYSTEM_MARKER,
        "dynamic": _DYNAMIC_SYSTEM_MARKER,
        "temporary_dynamic": _DYNAMIC_SYSTEM_MARKER,
        "draft_reminder": _DRAFT_REMINDER_SYSTEM_MARKER,
        "thinking_rules": _THINKING_RULES_SYSTEM_MARKER,
        "last4": _DYNAMIC_SYSTEM_MARKER,
    }
    ordered_regions = []
    for group in _SYSTEM_PROMPT_CACHE_GROUPS:
        group_messages = [
            msg
            for region in group
            for msg in region_blocks[region]
        ]
        if group in {("summary_recent",), ("hot_tool_results",)}:
            ordered_regions.extend(copy.deepcopy(group_messages))
            continue
        merged = _merge_system_region(group_messages, cache_group_markers[group[0]])
        if merged:
            if group == ("frozen_tool_summary", "summary_cache"):
                merged[_FROZEN_TOOL_SUMMARY_SYSTEM_MARKER] = True
                merged[_SUMMARY_CACHE_SYSTEM_MARKER] = True
            elif group == ("du_daily",):
                merged[_DU_DAILY_SYSTEM_MARKER] = True
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("dynamic",):
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("temporary_dynamic",):
                merged[_TEMPORARY_DYNAMIC_SYSTEM_MARKER] = True
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("draft_reminder",):
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("sumitalk_mode",):
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("thinking_rules",):
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("last4",):
                merged[_LAST4_SYSTEM_MARKER] = True
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            ordered_regions.append(merged)
    voice_blocks = [msg for msg in ordered_regions if msg.get(_VOICE_RULES_SYSTEM_MARKER)]
    if voice_blocks:
        for msg in ordered_regions:
            msg.pop(_STATIC_CACHE_ANCHOR_SYSTEM_MARKER, None)
        voice_blocks[-1][_STATIC_CACHE_ANCHOR_SYSTEM_MARKER] = True
    body["messages"] = [*ordered_regions, *messages[rest_start:]]
    body[_PROMPT_CACHE_LAYOUT_BODY_KEY] = {
        "window_id": str(window_id or generation_meta.get("window_id") or ""),
        "generation_id": int(generation_meta.get("generation_id") or 0),
        "generation_updates_done": int(generation_meta.get("generation_updates_done") or 0),
        "recent_blocks": len(region_blocks["summary_recent"]),
        "hot_tool_blocks": len(region_blocks["hot_tool_results"]),
    }
    return body


_CONVERSATION_MODE_CHANNEL_LABELS = {
    "tg": "TG",
    "sumitalk": "SumiTalk线下",
}


def _conversation_mode_channel_label(reply_channel: str, reply_target: str = "") -> str:
    channel = str(reply_channel or "").strip().lower()
    if channel == "qq":
        target = str(reply_target or "").strip().lower()
        return "QQ群聊" if target == "qq_group_mention" else "QQ私聊"
    return _CONVERSATION_MODE_CHANNEL_LABELS.get(channel, "")


def _use_mid_conversation_prompt(model: str, anthropic_messages: bool) -> bool:
    return bool(anthropic_messages and supports_mid_conversation_system(model))


def _render_conversation_mode_prompt(section_id: str, fallback: str, channel_label: str) -> str:
    prompt = _load_managed_static_prompt(section_id, fallback)
    prompt = prompt.replace("{channel}", channel_label)
    try:
        from services.sticker_tags import synchronize_sticker_tags_line

        prompt = synchronize_sticker_tags_line(prompt)
    except Exception:
        logger.warning("对话模式表情标签渲染失败，保留当前正文", exc_info=True)
    prompt = prompt.strip()
    if prompt and not prompt.startswith("【消息规范】"):
        prompt = f"【消息规范】\n{prompt}"
    return prompt


def _sync_mid_conversation_system_content(message: dict) -> None:
    parts = [
        str(message.get(key) or "").strip()
        for key in (
            _MID_DRAFT_COMPONENT_KEY,
            _MID_THINKING_COMPONENT_KEY,
            _MID_MODE_COMPONENT_KEY,
        )
    ]
    message["content"] = "\n\n".join(part for part in parts if part)


def step_inject_voice_rules(body: dict, *, reply_channel: str = "") -> dict:
    """Inject one editable voice-output block as the final fixed-static BP2 block."""
    body = copy.deepcopy(body)
    messages = [
        msg for msg in (body.get("messages") or [])
        if not (isinstance(msg, dict) and msg.get(_VOICE_RULES_SYSTEM_MARKER))
    ]
    body["messages"] = messages
    if str(reply_channel or "").strip().lower() not in _CONVERSATION_MODE_CHANNEL_LABELS:
        return body
    from services.voice_line_prompt import default_voice_line_rules_text

    rules = _load_managed_static_prompt("voice_line_rules", default_voice_line_rules_text())
    if not rules:
        return body
    insert_idx = len(messages)
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            insert_idx = i
            break
        if _system_prompt_region(msg) != "static":
            insert_idx = i
            break
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": rules.strip(),
            _VOICE_RULES_SYSTEM_MARKER: True,
        },
    )
    return body


def step_inject_sumitalk_real_mode(
    body: dict,
    enabled: bool = False,
    *,
    app_request: bool = False,
    reply_channel: str = "",
    reply_target: str = "",
    model: str = "",
    anthropic_messages: bool = False,
    wakeup_kind: str = "",
) -> dict:
    """Inject exactly one Reality/Real conversation prompt for QQ, TG or SumiTalk."""
    body = copy.deepcopy(body)
    messages = [
        msg for msg in (body.get("messages") or [])
        if not (isinstance(msg, dict) and msg.get(_SUMITALK_REAL_MODE_SYSTEM_MARKER))
    ]
    body["messages"] = messages
    channel = str(reply_channel or ("sumitalk" if app_request or enabled else "")).strip().lower()
    channel_label = _conversation_mode_channel_label(channel, reply_target)
    normalized_wakeup_kind = str(wakeup_kind or "").strip().lower()
    if normalized_wakeup_kind in _SUMITALK_MODE_PROMPT_EXCLUDED_WAKEUP_KINDS:
        prompt = ""
    elif enabled:
        prompt = _render_conversation_mode_prompt(
            "conversation_real_mode_prompt",
            SUMITALK_REAL_MODE_PROMPT,
            channel_label,
        )
    elif channel_label:
        prompt = _render_conversation_mode_prompt(
            "conversation_reality_mode_prompt",
            SUMITALK_APP_PROMPT,
            channel_label,
        )
    else:
        prompt = ""
    if not prompt:
        return body

    if _use_mid_conversation_prompt(model, anthropic_messages):
        message = {
            "role": "system",
            "content": prompt,
            _SUMITALK_REAL_MODE_SYSTEM_MARKER: True,
            _MID_CONVERSATION_SYSTEM_MARKER: True,
            _MID_MODE_COMPONENT_KEY: prompt,
        }
        _sync_mid_conversation_system_content(message)
        messages.append(message)
        return body

    insert_idx = len(messages)
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            insert_idx = i
            break
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": prompt,
            _DYNAMIC_SYSTEM_MARKER: True,
            _SUMITALK_REAL_MODE_SYSTEM_MARKER: True,
        },
    )
    return body


def step_inject_draft_reminder(
    body: dict,
    *,
    model: str = "",
    anthropic_messages: bool = False,
) -> dict:
    """Inject the optional draft reminder immediately before Thinking rules."""
    from services.draft_block import DRAFT_REMINDER_PROMPT
    from storage import draft_reminder_mode_store

    if not draft_reminder_mode_store.is_enabled():
        return body
    reminder = DRAFT_REMINDER_PROMPT.strip()
    if not reminder:
        return body
    messages = body.get("messages") or []
    if _use_mid_conversation_prompt(model, anthropic_messages):
        body = copy.deepcopy(body)
        messages = body.get("messages") or []
        for msg in reversed(messages):
            if not isinstance(msg, dict) or not msg.get(_MID_CONVERSATION_SYSTEM_MARKER):
                continue
            if not any(msg.get(key) for key in (_MID_DRAFT_COMPONENT_KEY, _MID_THINKING_COMPONENT_KEY, _MID_MODE_COMPONENT_KEY)):
                msg[_MID_MODE_COMPONENT_KEY] = str(msg.get("content") or "").strip()
            msg[_MID_DRAFT_COMPONENT_KEY] = reminder
            msg[_DRAFT_REMINDER_SYSTEM_MARKER] = True
            _sync_mid_conversation_system_content(msg)
            return body
        message = {
            "role": "system",
            "content": reminder,
            _MID_CONVERSATION_SYSTEM_MARKER: True,
            _DRAFT_REMINDER_SYSTEM_MARKER: True,
            _MID_DRAFT_COMPONENT_KEY: reminder,
        }
        _sync_mid_conversation_system_content(message)
        messages.append(message)
        return body
    for msg in messages:
        if isinstance(msg, dict) and msg.get(_DRAFT_REMINDER_SYSTEM_MARKER):
            return body

    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    insert_idx = len(messages)
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            insert_idx = i
            break
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": reminder,
            _DYNAMIC_SYSTEM_MARKER: True,
            _DRAFT_REMINDER_SYSTEM_MARKER: True,
        },
    )
    body["messages"] = messages
    return body


def step_inject_play_note(body: dict) -> dict:
    """Place the current play note in the temporary dynamic region."""
    pending = str((body or {}).get(_PLAY_NOTE_PENDING_BODY_KEY) or "").strip()
    if not pending:
        return body

    body = copy.deepcopy(body)
    body.pop(_PLAY_NOTE_PENDING_BODY_KEY, None)
    messages = [
        msg for msg in (body.get("messages") or [])
        if not (isinstance(msg, dict) and msg.get(_PLAY_NOTE_SYSTEM_MARKER))
    ]
    body["messages"] = messages

    first_boundary_idx = len(messages)
    real_mode_idx = -1
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            first_boundary_idx = i
            break
        if msg.get(_SUMITALK_REAL_MODE_SYSTEM_MARKER):
            real_mode_idx = i
        if (
            msg.get(_SUMMARY_CACHE_SYSTEM_MARKER)
            or msg.get(_SUMMARY_RECENT_SYSTEM_MARKER)
            or msg.get(_DYNAMIC_SYSTEM_MARKER)
        ):
            first_boundary_idx = i
            break
    insert_idx = min(real_mode_idx + 1, first_boundary_idx) if real_mode_idx >= 0 else first_boundary_idx
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": pending,
            _PLAY_NOTE_SYSTEM_MARKER: True,
        },
    )
    return body


def step_clean_images_and_save_desc(body: dict, window_id: str) -> dict:
    """
    清洗层：图片进入模型前先按 Anthropic 建议压缩，并行把图片用便宜 AI 转描述存 R2。
    返回新的 body（保留可读压缩图供「发给渡」用；存 R2 时用完整清洗版，图片→描述/占位符）。
    """
    body = copy.deepcopy(body)
    skip_description_coords: set[tuple[int, int]] = set()
    for mi, msg in enumerate(body.get("messages") or []):
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for ci, part in enumerate(content):
            if isinstance(part, dict) and part.get("__skip_image_description"):
                skip_description_coords.add((mi, ci))
    body, compress_stats = image_desc.compress_images_for_anthropic(body)
    for st in compress_stats:
        if not st.get("changed"):
            continue
        logger.info(
            "图片已按 Anthropic 建议压缩 message=%s part=%s %sx%s -> %sx%s bytes=%s -> %s",
            st.get("message_index"),
            st.get("content_index"),
            st.get("width"),
            st.get("height"),
            st.get("new_width"),
            st.get("new_height"),
            st.get("bytes"),
            st.get("new_bytes"),
        )
    messages = body.get("messages") or []
    failed_skip_coords = {
        (int(st.get("message_index")), int(st.get("content_index")))
        for st in compress_stats
        if (int(st.get("message_index")), int(st.get("content_index"))) in skip_description_coords
        and str(st.get("reason") or "") in {"invalid_size", "pillow_missing", "resize_failed"}
    }
    for mi, ci in skip_description_coords:
        try:
            part = messages[mi]["content"][ci]
        except (IndexError, KeyError, TypeError):
            continue
        if not isinstance(part, dict):
            continue
        part.pop("__skip_image_description", None)
        if (mi, ci) in failed_skip_coords:
            messages[mi]["content"][ci] = {"type": "text", "text": "【图片】"}
            logger.warning("QQ 群活动图片压缩失败，已回退占位 message=%s part=%s", mi, ci)
    images = image_desc.extract_images_from_messages(messages)
    for mi, ci, b64, mime in images:
        if (mi, ci) in skip_description_coords:
            continue
        image_id = image_desc.image_description_id(b64, mime)
        msg_id = f"{window_id}_{mi}_{ci}_{image_id}"
        image_desc.mark_image_description_pending(b64, mime)
        # 异步：转描述并存 R2，不阻塞
        def _do(img_b64, mid, wid, img_mime, img_id):
            desc = None
            try:
                desc = image_desc.image_to_description(img_b64, img_mime)
            finally:
                image_desc.finish_image_description(img_b64, img_mime, desc)
            if desc:
                r2_store.save_recent_image_description(
                    wid,
                    img_id,
                    desc,
                    mime_type=img_mime,
                    message_id=mid,
                )
            else:
                logger.warning("image_desc 未生成描述 window_id=%s image_id=%s mime=%s", wid, img_id, img_mime)

        t = threading.Thread(
            target=_do,
            args=(b64, msg_id, window_id, mime, image_id),
            name=f"image-desc-{image_id}",
        )
        t.start()
    return body


def step_clean_for_forward(body: dict) -> dict:
    """
    发给当前窗口渡的清洗：只清 Rikka 预设（不替换表情包，渡按 (表情包:名字) 格式）；图片保持原样。
    两条流之一：此 body 用于转发给 AI。
    role=system 的消息（Rikkahub 设置的上下文/系统提示）不做任何清洗，原样保留。
    """
    from pipeline.cleaner import clean_message_content_for_forward

    body = copy.deepcopy(body)
    for msg in body.get("messages") or []:
        if (msg.get("role") or "").lower() == "system":
            continue  # 不清理 Rikkahub 的 system/上下文，原样保留
        c = msg.get("content")
        if c is not None:
            msg["content"] = clean_message_content_for_forward(c, msg)
    return body


_CORE_PROMPT_CACHE = {"text": None, "ts": 0.0}
_COMMON_KNOWLEDGE_MARKER = "### 常识"
_COMMON_KNOWLEDGE_CACHE = {"text": None, "mtime": None, "ts": 0.0}
_ENTRY_STYLE_MARKERS = (
    "【入口风格：小爱音箱】",
)


def _load_du_core_prompt_from_file() -> str:
    """
    只从 prompts/du_core_prompt.txt 读取渡的 prompt（2026.3.16 版），不截断。
    文件不存在或为空则返回空串（不 fallback 到 RIKKA_SYSTEM_REPLACE，两边分开用）。
    """
    if _CORE_PROMPT_CACHE["text"] is not None:
        return _CORE_PROMPT_CACHE["text"]
    try:
        path = Path(__file__).resolve().parent.parent / "prompts" / "du_core_prompt.txt"
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                _CORE_PROMPT_CACHE["text"] = text
                return text
    except Exception:
        logger.exception("读取渡核心 prompt 文件失败")
    _CORE_PROMPT_CACHE["text"] = ""
    return ""


def _load_du_core_prompt() -> str:
    """
    读取全局核心 Prompt（优先 R2，可被 MiniApp 随时编辑）；若 R2 没有则回退本地 3.16 文件。
    做一个很短的本地缓存，避免每次请求都读 R2。
    """
    now = time.time()
    cache_ttl_s = 5.0
    if _CORE_PROMPT_CACHE["text"] is not None and (now - float(_CORE_PROMPT_CACHE.get("ts") or 0.0) <= cache_ttl_s):
        return _CORE_PROMPT_CACHE["text"] or ""

    text = None
    try:
        text = r2_store.get_core_prompt_text()
        if text is not None:
            text = (text or "").strip()
    except Exception:
        text = None
    if not text:
        text = _load_du_core_prompt_from_file()
    try:
        from services.prompt_manager import get_managed_prompt_text

        text = get_managed_prompt_text("core_prompt", text or "")
    except Exception:
        pass
    _CORE_PROMPT_CACHE["text"] = text or ""
    _CORE_PROMPT_CACHE["ts"] = now
    return _CORE_PROMPT_CACHE["text"] or ""


def _load_du_common_knowledge() -> str:
    """
    读取独立常识块。它不是核心 prompt 本体，也不是动态记忆。
    """
    now = time.time()
    cache_ttl_s = 5.0
    if _COMMON_KNOWLEDGE_CACHE["text"] is not None and (now - float(_COMMON_KNOWLEDGE_CACHE.get("ts") or 0.0) <= cache_ttl_s):
        return _COMMON_KNOWLEDGE_CACHE["text"] or ""
    try:
        path = Path(__file__).resolve().parent.parent / "prompts" / "du_common_knowledge.md"
        mtime = path.stat().st_mtime if path.exists() else None
        text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
        try:
            from services.prompt_manager import get_managed_prompt_text

            text = get_managed_prompt_text("common_knowledge", text).strip()
        except Exception:
            pass
        _COMMON_KNOWLEDGE_CACHE["text"] = text
        _COMMON_KNOWLEDGE_CACHE["mtime"] = mtime
        _COMMON_KNOWLEDGE_CACHE["ts"] = now
        return text
    except Exception:
        logger.exception("读取渡常识块失败")
        return ""


def _load_managed_static_prompt(section_id: str, fallback: str) -> str:
    try:
        from services.prompt_manager import get_managed_prompt_text

        return get_managed_prompt_text(section_id, fallback).strip()
    except Exception:
        return (fallback or "").strip()


def step_replace_rikka_system(body: dict) -> dict:
    """
    发给 AI 之前：在最前面插入「渡的 prompt（2026.3.16 版）」一条。
    内容来自 prompts/du_core_prompt.txt，不准改动、每次必须全文注入，不截断。
    不注入 RIKKA_SYSTEM_REPLACE；Rikkahub 自带的 system 等保持原样接在后面。
    """
    du_prompt = _load_du_core_prompt()
    if not du_prompt:
        return body
    messages = body.get("messages") or []
    if not messages:
        body = copy.deepcopy(body)
        body["messages"].insert(0, {"role": "system", "content": du_prompt})
        return body
    # 若第一条已是同内容 system，不重复插
    first = messages[0]
    if (first.get("role") or "").lower() == "system" and str(first.get("content") or "").strip() == du_prompt:
        return body
    body = copy.deepcopy(body)
    body["messages"].insert(0, {"role": "system", "content": du_prompt})
    return body


def step_inject_du_non_retreat_rules(body: dict) -> dict:
    """
    全局注入：独立放在渡核心 prompt 后面，不写进 R2 核心 prompt 本体。
    """
    rules = _load_managed_static_prompt("non_retreat_rules", _DU_NON_RETREAT_RULES)
    if not rules:
        return body
    messages = body.get("messages") or []
    for msg in messages:
        if (msg.get("role") or "").lower() == "system" and rules in str(msg.get("content") or ""):
            return body

    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    if not messages:
        body["messages"] = [{"role": "system", "content": rules}]
        return body

    insert_idx = 0
    du_prompt = _load_du_core_prompt().strip()
    first = messages[0]
    if (first.get("role") or "").lower() == "system" and du_prompt and str(first.get("content") or "").strip() == du_prompt:
        insert_idx = 1
    messages.insert(insert_idx, {"role": "system", "content": rules})
    body["messages"] = messages
    return body


def step_inject_thinking_block_rules(
    body: dict,
    *,
    model: str = "",
    anthropic_messages: bool = False,
) -> dict:
    """
    全局注入：作为独立动态块，放在常驻/临时动态之后、last4 之前。
    """
    rules = _load_managed_static_prompt("thinking_rules", _THINKING_BLOCK_RULES)
    if not rules:
        return body
    messages = body.get("messages") or []
    if _use_mid_conversation_prompt(model, anthropic_messages):
        body = copy.deepcopy(body)
        messages = body.get("messages") or []
        for msg in reversed(messages):
            if not isinstance(msg, dict) or not msg.get(_MID_CONVERSATION_SYSTEM_MARKER):
                continue
            if not any(msg.get(key) for key in (_MID_DRAFT_COMPONENT_KEY, _MID_THINKING_COMPONENT_KEY, _MID_MODE_COMPONENT_KEY)):
                msg[_MID_MODE_COMPONENT_KEY] = str(msg.get("content") or "").strip()
            msg[_MID_THINKING_COMPONENT_KEY] = rules
            msg[_THINKING_RULES_SYSTEM_MARKER] = True
            _sync_mid_conversation_system_content(msg)
            return body
        message = {
            "role": "system",
            "content": rules,
            _THINKING_RULES_SYSTEM_MARKER: True,
            _MID_CONVERSATION_SYSTEM_MARKER: True,
            _MID_THINKING_COMPONENT_KEY: rules,
        }
        _sync_mid_conversation_system_content(message)
        messages.append(message)
        return body
    for msg in messages:
        if (msg.get("role") or "").lower() == "system" and rules in str(msg.get("content") or ""):
            return body

    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    insert_idx = len(messages)
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            insert_idx = i
            break
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": rules,
            _DYNAMIC_SYSTEM_MARKER: True,
            _THINKING_RULES_SYSTEM_MARKER: True,
        },
    )
    body["messages"] = messages
    return body


def step_inject_core_behavior_rules(body: dict) -> dict:
    """
    全局注入：放在渡核心 prompt 后的固定行为规则区。
    """
    rules = _load_managed_static_prompt("core_behavior_rules", _CORE_BEHAVIOR_RULES)
    if not rules:
        return body
    messages = body.get("messages") or []
    for msg in messages:
        if (msg.get("role") or "").lower() == "system" and rules in str(msg.get("content") or ""):
            return body

    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    if not messages:
        body["messages"] = [{"role": "system", "content": rules}]
        return body

    insert_idx = 0
    du_prompt = _load_du_core_prompt().strip()
    first = messages[0]
    if (first.get("role") or "").lower() == "system" and du_prompt and str(first.get("content") or "").strip() == du_prompt:
        insert_idx = 1
    messages.insert(insert_idx, {"role": "system", "content": rules})
    body["messages"] = messages
    return body


def step_inject_common_knowledge(body: dict) -> dict:
    """
    固定注入：长期稳定常识块，放静态 system 区，不进入动态记忆。
    """
    block = _load_du_common_knowledge().strip()
    if not block:
        return body
    messages = body.get("messages") or []
    for msg in messages:
        if (msg.get("role") or "").lower() == "system" and _COMMON_KNOWLEDGE_MARKER in str(msg.get("content") or ""):
            return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    insert_idx = 0
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() != "system":
            break
        if msg.get(_DYNAMIC_SYSTEM_MARKER) or msg.get(_SUMMARY_CACHE_SYSTEM_MARKER) or msg.get(_SUMMARY_RECENT_SYSTEM_MARKER):
            break
        content = str(msg.get("content") or "").lstrip()
        if any(content.startswith(marker) for marker in _ENTRY_STYLE_MARKERS):
            break
        insert_idx = i + 1
    messages.insert(insert_idx, {"role": "system", "content": block})
    body["messages"] = messages
    return body


def step_inject_pending_thought_rules(body: dict) -> dict:
    """固定注入：待续念头的隐藏标记维护规则，放静态 system 区。"""
    try:
        from services.pending_thoughts import STATIC_RULES
    except Exception as e:
        logger.debug("pending_thought rules 注入跳过 error=%s", e)
        return body
    rules = (STATIC_RULES or "").strip()
    if not rules:
        return body
    return _append_to_static_system(body, "\n\n" + rules)


def _messages_total_chars(messages: list) -> int:
    """估算 messages 总字符数（content 转为字符串长度）。"""
    total = 0
    for m in messages or []:
        c = m.get("content")
        if c is None:
            continue
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and (part.get("text") or part.get("content")):
                    total += len(str(part.get("text") or part.get("content") or ""))
                else:
                    total += len(str(part))
        else:
            total += len(str(c))
    return total


def step_trim_messages_if_over_limit(body: dict) -> dict:
    """
    当 MAX_REQUEST_CHARS > 0 且 messages 总字符数超限时，从对话中部删最老的轮次，
    保证最前面的「渡的 prompt + 所有连续 system」不被删，避免上游 input 超限导致输出被截断。
    """
    if not MAX_REQUEST_CHARS or MAX_REQUEST_CHARS <= 0:
        return body
    messages = body.get("messages") or []
    if not messages:
        return body
    total = _messages_total_chars(messages)
    if total <= MAX_REQUEST_CHARS:
        return body
    # 前段：第 0 条（渡的 prompt）+ 其后所有连续的 system
    i = 0
    while i < len(messages) and (messages[i].get("role") or "").lower() == "system":
        i += 1
    leading = messages[:i]
    conversation = messages[i:]
    if not conversation:
        return body
    leading_chars = _messages_total_chars(leading)
    if leading_chars >= MAX_REQUEST_CHARS:
        logger.warning("请求前段（渡 prompt+system）已超 MAX_REQUEST_CHARS，无法再裁对话")
        return body
    # 从 conversation 前面删，直到总长 <= 限
    body = copy.deepcopy(body)
    conv = list(conversation)
    while conv and leading_chars + _messages_total_chars(conv) > MAX_REQUEST_CHARS:
        conv.pop(0)
    dropped = len(conversation) - len(conv)
    if dropped:
        logger.info("请求超限已裁掉最老 %s 条对话，当前总字符约 %s（上限 %s）", dropped, leading_chars + _messages_total_chars(conv), MAX_REQUEST_CHARS)
    body["messages"] = leading + conv
    return body


def _message_content_text_for_recent_context(msg: dict) -> str:
    content = (msg or {}).get("content", "")
    if isinstance(content, list):
        return " ".join(
            c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
        )
    return str(content or "")


def _recent_context_round_time_label(round_obj: dict) -> str:
    raw = str((round_obj or {}).get("timestamp") or "").strip()
    if not raw:
        return ""
    try:
        from utils.time_aware import parse_iso_to_beijing

        dt = parse_iso_to_beijing(raw)
        return dt.strftime("%H:%M") if dt else ""
    except Exception:
        return ""


def _last_recent_context_message_position(rounds: list) -> tuple[int, int] | None:
    last_pos = None
    for ri, r in enumerate(rounds or []):
        for mi, m in enumerate((r or {}).get("messages") or []):
            if isinstance(m, dict):
                last_pos = (ri, mi)
    return last_pos


def _format_recent_context_message_line(
    round_obj: dict,
    msg: dict,
    role: str,
    *,
    is_last_message: bool = False,
    src_tag: str = "",
) -> str:
    content = _message_content_text_for_recent_context(msg)
    if str((msg or {}).get("archive_label") or "").strip() == "日记评论互动":
        return f"【日记评论互动】{content}"
    if is_last_message:
        time_label = _recent_context_round_time_label(round_obj)
        if time_label:
            role_label = _recent_context_role_label(msg, role)
            return f"{src_tag}[{time_label}][{role_label}]: {content}"
    role_label = _recent_context_role_label(msg, role)
    return f"{src_tag}[{role_label}]: {content}"


def _rounds_to_context_text(rounds: list) -> str:
    """把 rounds（含 messages 的列表）拼成一段可读的上下文文本。"""
    lines = []
    last_pos = _last_recent_context_message_position(rounds)
    for ri, r in enumerate(rounds):
        for mi, m in enumerate(r.get("messages", [])):
            role = str(m.get("role", "") or "").strip().lower()
            lines.append(
                _format_recent_context_message_line(
                    r,
                    m,
                    role,
                    is_last_message=last_pos == (ri, mi),
                )
            )
        action_note = str((r or {}).get("action_note") or "").strip()
        if action_note:
            lines.append(f"[action_note]: {action_note}")
    return "\n".join(lines) if lines else ""


def _recent_context_role_label(msg: dict, role: str) -> str:
    if role == "user":
        return "辛玥"
    if role == "assistant":
        label = str((msg or {}).get("archive_label") or "").strip()
        if label:
            return label
        return "我"
    if role == "event":
        label = str((msg or {}).get("archive_label") or "").strip()
        return label or "网关提醒"
    return role or "unknown"


def _build_action_note_from_tool_calls(tool_calls: list) -> str:
    """把本轮工具调用压成一条很短的动作印象，供后续 Last4 短程上下文使用。"""
    if not isinstance(tool_calls, list) or not tool_calls:
        return ""

    has_success = False

    def _summarize_one_tool(tc: dict) -> str:
        nonlocal has_success
        if not isinstance(tc, dict):
            return ""
        fn = (tc.get("function") or {}) if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip()
        if not name:
            return ""
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        result_text = str(tc.get("result") or "").strip()
        if name == "create_system_alarm":
            result_obj = {}
            try:
                parsed = json.loads(result_text or "{}")
                if isinstance(parsed, dict):
                    result_obj = parsed
            except Exception:
                result_obj = {}
            ok = bool(result_obj.get("ok")) if result_obj else bool(result_text)
            try:
                hour = int(result_obj.get("hour", args.get("hour")))
                minute = int(result_obj.get("minute", args.get("minute")))
                alarm_time = f"{hour:02d}:{minute:02d}"
            except Exception:
                alarm_time = "目标时间"
            if ok:
                action_id = str(result_obj.get("id") or "").strip()
                id_part = f":id={action_id}" if action_id else ""
                return f"create_system_alarm{id_part}（{alarm_time} 系统闹钟已发送到手机，等待 App 回执）"
            return f"create_system_alarm（{alarm_time} 调用未成功）"
        target = ""
        for key in ("url", "query", "keyword", "page_id", "title", "content", "window_id"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                target = val.strip()
                break
        if len(target) > 48:
            target = target[:48] + "..."
        if result_text:
            result_kind = "已拿到结果"
            lower = result_text.lower()
            if name == "read_url":
                result_kind = "已拿到页面内容"
                has_success = True
            elif "未找到" in result_text or "没有找到" in result_text or "not found" in lower:
                result_kind = "未找到有效结果"
            elif "error" in lower or "失败" in result_text:
                result_kind = "调用未成功"
            elif "http" in result_text or "https" in result_text:
                result_kind = "已拿到链接结果"
                has_success = True
            elif "[" in result_text and "]" in result_text:
                result_kind = "已拿到候选列表"
                has_success = True
            else:
                has_success = True
        else:
            result_kind = "已执行"
        if target:
            return f"{name}（{target}，{result_kind}）"
        return f"{name}（{result_kind}）"

    parts: list[str] = []
    seen: set[str] = set()
    for tc in tool_calls[:4]:
        piece = _summarize_one_tool(tc)
        if not piece or piece in seen:
            continue
        seen.add(piece)
        parts.append(piece)
    if not parts:
        return ""
    if has_success:
        return f"上一轮工具结果：{'、'.join(parts)}；这些结果已经拿到，除非参数变化或用户明确要求刷新，否则不要重复调用相同工具。"
    return f"上一轮工具记录：{'、'.join(parts)}；若还是同一目标，先基于上面结果继续，不要立刻原样重调。"


def _build_round_action_note(assistant_message: dict, round_messages: list[dict]) -> str:
    has_diary_reply = any(
        isinstance(message, dict)
        and str(message.get("role") or "").strip().lower() == "assistant"
        and str(message.get("archive_label") or "").strip() == "日记评论互动"
        for message in (round_messages or [])
    )
    if has_diary_reply:
        return ""
    return _build_action_note_from_tool_calls((assistant_message or {}).get("tool_calls"))


_PROACTIVE_DECISION_PROMPT_PREFIX = "这是一次随机唤醒，你现在要不要做点什么"


def _message_plain_text_for_context(msg: dict) -> str:
    content = (msg or {}).get("content", "")
    if isinstance(content, list):
        return " ".join(c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content)
    return str(content or "")


def _is_internal_proactive_decision_round(round_obj: dict) -> bool:
    if not isinstance(round_obj, dict):
        return False
    user_text = ""
    assistant_text = ""
    for msg in round_obj.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        if role == "user" and not user_text:
            user_text = _message_plain_text_for_context(msg).strip()
        elif role == "assistant" and not assistant_text:
            assistant_text = _message_plain_text_for_context(msg).strip()
    if not user_text.startswith(_PROACTIVE_DECISION_PROMPT_PREFIX):
        return False
    return '"action"' in assistant_text or "'action'" in assistant_text


def _filter_rounds_for_recent_context(rounds: list) -> list[dict]:
    return [r for r in (rounds or []) if isinstance(r, dict) and not _is_internal_proactive_decision_round(r)]


def step_inject_latest_4_rounds_for_new_window(body: dict, window_id: str, force_last4: bool = False) -> dict:
    """
    新窗口：从 R2 读取全局「最新四轮」注入。
    Telegram 窗口优先注入该窗口自己的最近四轮，不混入全局 latest_4_rounds。
    已有历史但请求里消息很少（如主动发消息只发一条）：注入该窗口自己的最近四轮（如 Telegram 侧 Last4）。
    """
    if not window_id:
        return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    inject_label = ""
    rounds = []
    desc_scope_window_id: str | None = None
    is_telegram_window = window_id.startswith("tg_")

    if is_telegram_window:
        # Telegram 只按“本窗口 Last4”注入；文游已迁出 TG，不再混入群窗口上下文。
        if force_last4 or len(messages) <= 2 or r2_store.has_window_history(window_id):
            private_rounds = _filter_rounds_for_recent_context(
                r2_store.get_conversation_rounds(window_id, last_n=12) or []
            )
            merged = []

            def _with_src(arr: list, src: str) -> list:
                out = []
                for r in arr:
                    if isinstance(r, dict):
                        rr = dict(r)
                        rr["_inject_src"] = src
                        out.append(rr)
                return out

            merged.extend(_with_src(private_rounds, "私聊"))

            merged.sort(key=lambda x: str(x.get("timestamp") or ""))
            rounds = merged[-4:]
            inject_label = "最近的对话"
            desc_scope_window_id = window_id
    else:
        if not r2_store.has_window_history(window_id):
            rounds = _filter_rounds_for_recent_context(r2_store.get_latest_4_rounds_global() or [])[-4:]
            inject_label = "最近的对话"
            desc_scope_window_id = None
        else:
            # 已有历史且当前请求消息很少（如 proactive 只发 1 条 user）→ 注入本窗口最近 4 轮
            # force_last4=True 时即使 messages 较多也强制注入。
            if force_last4 or len(messages) <= 2:
                rounds = _filter_rounds_for_recent_context(
                    r2_store.get_conversation_rounds(window_id, last_n=12) or []
                )[-4:]
                inject_label = "最近的对话"
                desc_scope_window_id = window_id

    if not rounds:
        return body
    desc_map = r2_store.get_recent_image_description_map(desc_scope_window_id)
    rounds = image_desc.replace_image_placeholders_in_obj(rounds, desc_map)
    try:
        from services.recall_message_markers import apply_recall_markers_to_rounds

        marker_window_id = desc_scope_window_id if desc_scope_window_id is not None else ""
        rounds = apply_recall_markers_to_rounds(rounds, marker_window_id)
    except Exception:
        logger.debug("recall_message_markers_apply_failed window_id=%s", window_id, exc_info=True)
    # Telegram 注入时保留来源标签，便于后续扩展其它入口时区分上下文。
    if is_telegram_window:
        lines = []
        last_pos = _last_recent_context_message_position(rounds)
        for ri, r in enumerate(rounds):
            src = str((r or {}).get("_inject_src") or "").strip()
            src_tag = f"【{src}】" if src else ""
            for mi, m in enumerate(r.get("messages") or []):
                role = str(m.get("role", "") or "").strip().lower()
                lines.append(
                    _format_recent_context_message_line(
                        r,
                        m,
                        role,
                        is_last_message=last_pos == (ri, mi),
                        src_tag=src_tag,
                    )
                )
            action_note = str((r or {}).get("action_note") or "").strip()
            if action_note:
                lines.append(f"{src_tag}[action_note]: {action_note}")
        context = "\n".join(lines) if lines else ""
    else:
        context = _rounds_to_context_text(rounds)
    if not context:
        return body
    inject = f"\n\n【{inject_label}】\n{context}\n【以上为最近的对话】"
    return _append_to_last4_system(body, inject)


def _last_assistant_text(body: dict) -> str:
    """取 body 中最后一条 assistant（渡）消息的纯文本（用于按需注入判断）。只拼 type=text 的 part，忽略图片等，避免 [image_url] 等导致误判。"""
    messages = body.get("messages") or []
    for m in reversed(messages):
        if (m.get("role") or "").lower() != "assistant":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(c.get("text", ""))
            return " ".join(parts).strip()
        return str(content) if content else ""
    return ""


def _is_question_like(text: str) -> bool:
    """简单判断是否像问句：结尾有？或含 吗/呢/啊/呀 等。"""
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if t.endswith("?") or t.endswith("？"):
        return True
    for q in ("吗", "呢", "啊", "呀"):
        if q in t:
            return True
    return False


def step_inject_summary(body: dict, window_id: str, is_user_input: bool = False) -> dict:
    """
    常驻注入：今日日期（北京时间）+ 当前大概时段 + get_time_info 提示；有 R2 总结时再追加【窗口记忆总结】。
    兜底：渡的上一轮是问句且含「几点/时间/现在」→ 本轮注入具体时间。
    农历：渡的上一轮含「农历/节气/宜忌/黄历」→ 本轮注入农历节气宜忌。
    """
    from utils.time_aware import (
        get_date_only,
        get_weekday_cn,
        get_time_period,
        get_exact_time,
        get_lunar_and_terms,
        now_beijing_iso,
        _now_beijing,
    )

    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    now = None  # time_aware 内用北京时间
    today = get_date_only(now)
    weekday = get_weekday_cn(now)
    period = get_time_period(now)
    head = (
        f"\n\n今日：{today}（{weekday}），当前大概：{period}\n"
        f"如需知道当前几点，可使用网关提供的 get_time_info 时间工具；"
        f"如需查询天气，可使用专门的天气查询工具。\n"
        f"想写东西的时候就去写日记！顺便可以翻翻列表，说不定能看到老婆新写的日记？"
    )

    # 老婆多久没回：Telegram 窗口只在“真实用户输入”时触发，避免网关内部请求误判
    try:
        has_user_message = any((m.get("role") or "").lower() == "user" for m in messages if isinstance(m, dict))
        is_tg_window = str(window_id or "").startswith("tg_")
        should_track_reply_gap = is_user_input if is_tg_window else has_user_message
        if should_track_reply_gap:
            previous = capture_previous_interaction_and_mark_chat(now_beijing_iso())
            delta_sec = user_activity_elapsed_seconds(previous, _now_beijing())
            if (
                delta_sec is not None
                and REPLY_GAP_THRESHOLD_MINUTES
                and delta_sec >= REPLY_GAP_THRESHOLD_MINUTES * 60
            ):
                gap_prompt = render_incoming_gap_prompt(previous, delta_sec)
                if gap_prompt:
                    head += f"\n{gap_prompt}"
    except Exception as e:
        logger.debug("reply_gap 注入失败（忽略） error=%s", e)
    last_assistant = _last_assistant_text(body)
    last_lower = (last_assistant or "").lower()
    if ASSISTANT_TIME_KEYWORDS and _is_question_like(last_assistant):
        if any(kw in last_lower for kw in ASSISTANT_TIME_KEYWORDS):
            head += f"\n当前时间：{get_exact_time(now)}"
    if ASSISTANT_LUNAR_KEYWORDS and any(kw in last_lower for kw in ASSISTANT_LUNAR_KEYWORDS):
        head += f"\n{get_lunar_and_terms(now)}"

    summary = r2_store.get_summary(window_id) or ""
    chunks_state = r2_store.get_summary_chunks(window_id)
    stable_summary, recent_summaries, normalized_state = deepseek_summary.render_summary_prompt_blocks(
        chunks_state,
        summary,
    )
    generation = normalized_state.get("generation") if isinstance(normalized_state.get("generation"), dict) else {}
    body[_PROMPT_CACHE_LAYOUT_BODY_KEY] = {
        "window_id": str(window_id or ""),
        "generation_id": int(generation.get("id") or 0),
        "generation_updates_done": int(generation.get("updates_done") or 0),
        "recent_blocks": len(recent_summaries),
        "hot_tool_blocks": 0,
    }
    if stable_summary or recent_summaries:
        body = _upsert_summary_cache_system(body, stable_summary, recent_summaries)
    inject = head
    body = _append_to_dynamic_system(body, inject)
    return body


def step_inject_sense_snapshot(body: dict, window_id: str) -> dict:
    """
    全局注入：不区分 window_id。凡走网关 /v1/chat/completions 完整管道的请求（Rikka、Telegram、闹钟叫醒等）
    都在 system 末尾追加 sense/latest 快照；不写入 user。window_id 参数保留仅为与其它 step 签名一致。
    R2 失败或无数据则跳过。
    """
    _ = window_id  # 感知数据为全局一份，不按窗口分桶
    try:
        from services.sense_context import format_sense_snapshot_for_system

        block = format_sense_snapshot_for_system()
    except Exception as e:
        logger.debug("sense 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = _append_to_dynamic_system(body, inject)
    return body


def step_inject_du_thought(body: dict, window_id: str) -> dict:
    """
    全局注入：在 system 末尾追加「心事格式说明 + 上一则心事」。
    渡在回复末尾写 <<<DU_THOUGHT>>>...<<<END_DU_THOUGHT>>>，网关截取后存 R2，老婆侧不可见。
    """
    _ = window_id
    try:
        from services.du_thought import format_inject_block

        latest = r2_store.get_du_thought_latest()
        block = format_inject_block(latest)
    except Exception as e:
        logger.debug("du_thought 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = _append_to_dynamic_system(body, inject)
    return body


def step_inject_pending_thoughts(body: dict, window_id: str) -> dict:
    """动态注入：渡自己留下的待续念头，紧跟心事之后。"""
    _ = window_id
    try:
        from services.pending_thoughts import format_inject_block

        block = format_inject_block()
    except Exception as e:
        logger.debug("pending_thought 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    return _append_to_dynamic_system(body, "\n\n" + block.strip())


def step_inject_secret_drawer(body: dict, window_id: str) -> dict:
    """固定规则进入静态 system；当前抽屉统计进入常驻动态 system。"""
    _ = window_id
    try:
        from services.secret_drawer import format_rule_block, format_state_block

        rule_block = format_rule_block()
        state_block = format_state_block()
    except Exception as e:
        logger.debug("secret_drawer 注入跳过 error=%s", e)
        return body
    if (rule_block or "").strip():
        body = _append_to_static_system(body, "\n\n" + rule_block.strip())
    if (state_block or "").strip():
        body = _append_to_dynamic_system(body, "\n\n" + state_block.strip())
    return body


def step_inject_wakeup_frame(body: dict, window_id: str) -> dict:
    """动态注入：距离上次醒来后，设备感知数据发生的短变化。"""
    try:
        from services.wakeup_frame import format_wakeup_frame_for_system

        block = format_wakeup_frame_for_system(window_id)
    except Exception as e:
        logger.debug("wakeup_frame 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    return _append_to_dynamic_system(body, "\n\n" + block.strip())


def step_inject_du_vitals(body: dict, window_id: str) -> dict:
    """
    全局注入：静态 system 放稳定规则，不把上一轮实际读数注入给渡。
    渡输出内部状态参数，网关截取后换算为心率/呼吸，老婆侧正文不可见。
    """
    _ = window_id
    try:
        from services.du_vitals import format_rule_block

        rule_block = format_rule_block()
    except Exception as e:
        logger.debug("du_vitals 注入跳过 error=%s", e)
        return body
    if (rule_block or "").strip():
        body = _append_to_static_system(body, "\n\n" + rule_block.strip())
    return body


def step_inject_du_daily(
    body: dict,
    window_id: str,
    trigger: Optional[dict] = None,
    maintenance_mode: bool = False,
) -> dict:
    """
    全局注入：把「你的日常」作为独立常驻动态 system 槽位注入。
    最终位置固定在两个近期记忆块之后、其他常驻动态之前。
    网关判定命中更新时，渡只写本次新增隐藏块，网关截取后追加进 R2，老婆侧不可见。
    """
    _ = window_id
    try:
        from services.du_daily import format_inject_block, get_prepared_state

        state, _changed = get_prepared_state()
        block = format_inject_block(state, trigger=trigger, maintenance_mode=maintenance_mode)
    except Exception as e:
        logger.debug("du_daily 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = copy.deepcopy(body)
    messages = [
        msg
        for msg in (body.get("messages") or [])
        if not (isinstance(msg, dict) and msg.get(_DU_DAILY_SYSTEM_MARKER))
    ]
    insert_idx = len(messages)
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            insert_idx = i
            break
        if (
            msg.get(_SUMMARY_CACHE_SYSTEM_MARKER)
            or msg.get(_SUMMARY_RECENT_SYSTEM_MARKER)
            or msg.get(_DYNAMIC_SYSTEM_MARKER)
        ):
            insert_idx = i
            break
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": inject,
            _DU_DAILY_SYSTEM_MARKER: True,
            _DYNAMIC_SYSTEM_MARKER: True,
        },
    )
    body["messages"] = messages
    return body


def step_inject_pixel_home(body: dict, window_id: str) -> dict:
    """Inject shared cyber home state dynamically and the PIXEL_HOME hidden marker contract statically."""
    _ = window_id
    try:
        from services.pixel_home import format_rule_block, format_state_and_private_draw_blocks

        rule_block = format_rule_block()
        state_block, private_draw_block = format_state_and_private_draw_blocks()
    except Exception as e:
        logger.debug("pixel_home 注入跳过 error=%s", e)
        return body
    if (rule_block or "").strip():
        body = _append_to_static_system(body, "\n\n" + rule_block.strip())
    if (state_block or "").strip():
        body = _append_to_dynamic_system(body, "\n\n" + state_block.strip())
    if (private_draw_block or "").strip():
        body[_PLAY_NOTE_PENDING_BODY_KEY] = private_draw_block.strip()
    return body


def step_inject_du_midterm_memory(body: dict, window_id: str) -> dict:
    """
    全局注入：最近 14 天滑窗的中期连续感，三天才刷新，放静态 system 段。
    这层独立于 dynamic_memory/current.json，只注入 latest；到期刷新走后台线程，不阻塞当前聊天。
    """
    _ = window_id
    try:
        from services.du_midterm_memory import format_inject_block, refresh_if_due_background

        refresh_if_due_background()
        block = format_inject_block()
    except Exception as e:
        logger.debug("du_midterm 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = _append_to_static_system(body, inject)
    return body


def step_inject_interaction_candidate(body: dict, window_id: str) -> dict:
    """
    全局注入：在静态 system 段追加「相处模式候选写法说明」。
    渡在回复末尾写 <<<DU_INTERACTION>>>...<<<END_DU_INTERACTION>>>，网关截取后存 R2，老婆侧不可见。
    """
    _ = window_id
    try:
        from services.interaction_memory import format_inject_block

        block = format_inject_block()
    except Exception as e:
        logger.debug("interaction candidate 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = _append_to_static_system(body, inject)
    return body


def step_inject_rikkahub_reminder(body: dict, window_id: str) -> dict:
    """
    当请求不是来自 Telegram（window_id 为空或不以 tg_ 开头）时，注入「当前是在 RikkaHub」提醒。
    一直提醒，实现简单。
    """
    if not body or not isinstance(body.get("messages"), list):
        return body
    if window_id and str(window_id).strip().startswith("tg_"):
        return body
    inject = "\n\n【你当前正在 RikkaHub 和小玥聊天】\n【小提醒】无聊时可以逛逛 AI 论坛哦。"
    body = _append_to_dynamic_system(body, inject)
    return body


def step_inject_stay_with_du(body: dict) -> dict:
    """
    固定注入：Stay with Du，位置在「渡的记事本」上方。
    """
    data = r2_store.get_stay_with_du_data() or {}
    if not any(data.get(k) for k in ("timeline", "moviesDone", "moviesTodo", "booksDone", "booksTodo")):
        return body

    def _media_line(item: dict) -> str:
        title = str((item or {}).get("title") or "").strip()
        if not title:
            return ""
        date = str((item or {}).get("date") or "").strip()
        note = str((item or {}).get("note") or "").strip()
        suffix = ""
        if date:
            suffix += f"（{date}）"
        if note:
            suffix += f"：{note}"
        return f"- {title}{suffix}"

    sections: list[str] = []
    timeline_lines = []
    for item in (data.get("timeline") or [])[:20]:
        title = str((item or {}).get("title") or "").strip()
        if not title:
            continue
        date = str((item or {}).get("date") or "").strip()
        desc = str((item or {}).get("desc") or "").strip()
        prefix = f"{date} " if date else ""
        timeline_lines.append(f"- {prefix}{title}" + (f"：{desc}" if desc else ""))
    if timeline_lines:
        sections.append("重要时间线：\n" + "\n".join(timeline_lines))

    media_specs = [
        ("一起看过的电影", data.get("moviesDone") or []),
        ("想一起看的电影", data.get("moviesTodo") or []),
        ("一起读过的书", data.get("booksDone") or []),
        ("想一起读的书", data.get("booksTodo") or []),
    ]
    for title, items in media_specs:
        lines = [_media_line(it) for it in items[:30]]
        lines = [line for line in lines if line]
        if lines:
            sections.append(f"{title}：\n" + "\n".join(lines))

    if not sections:
        return body

    budget = 700
    kept: list[str] = []
    for section in sections:
        nxt = ("\n\n".join(kept + [section])).strip()
        if estimate_tokens(nxt) > budget:
            break
        kept.append(section)
    if not kept:
        return body
    inject = "\n\n【Stay with Du】\n" + "\n\n".join(kept) + "\n【以上为 Stay with Du】"
    body = _append_to_static_system(body, inject)
    return body


def _extract_keyword_candidates(text: str) -> list[dict]:
    """提取用于匹配动态层的关键词候选，并标注是否来自短语收敛层。"""
    if not text or not isinstance(text, str):
        return []

    stopwords = {
        "好的",
        "可以",
        "行吧",
        "行的",
        "嗯嗯",
        "哈哈",
        "收到",
        "知道了",
        "明白了",
        "没事",
        "谢谢",
        "好的呀",
        "好的呢",
        "记忆",
        "动态记忆",
        "窗口记忆",
        "回忆",
        "总结",
        "注入",
        "检索",
        "向量",
        "embedding",
        "embeddings",
    }
    shell_words = {
        "今天",
        "昨天",
        "刚刚",
        "最近",
        "这几天",
        "这个",
        "那个",
        "这样",
        "那样",
        "感觉",
        "觉得",
        "就是",
        "然后",
        "所以",
        "因为",
        "但是",
    }
    attitude_patterns = [
        r"(不太想[^\s,，。！？、；：]{1,8})",
        r"(不想[^\s,，。！？、；：]{1,8})",
        r"(想让[^\s,，。！？、；：]{1,8})",
        r"(想要[^\s,，。！？、；：]{1,8})",
        r"(更喜欢[^\s,，。！？、；：]{1,8})",
        r"(不喜欢[^\s,，。！？、；：]{1,8})",
        r"(喜欢[^\s,，。！？、；：]{1,8})",
        r"(讨厌[^\s,，。！？、；：]{1,8})",
        r"(更想[^\s,，。！？、；：]{1,8})",
        r"(宁愿[^\s,，。！？、；：]{1,8})",
        r"(不希望[^\s,，。！？、；：]{1,8})",
        r"(希望[^\s,，。！？、；：]{1,8})",
        r"(?:有点|有一点|很|特别|真的)?(?:委屈|生气|开心|难过|烦|不爽|害怕|担心|紧张|难受)",
        r"(?:很|特别|真的)?(?:在意|介意|失望|安心|心疼|依赖)",
        r"(?:受不了|接受不了)",
        r"(?:可以|不行)",
    ]
    fact_patterns = [
        r"(?:肚子|胃|头|喉咙|牙|鼻子|身上)[^\s,，。！？、；：]{0,4}(?:不舒服|疼|痛)",
        r"(?:不舒服|头疼|肚子疼|想吐|累|困|压力大|没睡好)",
        r"(?:跟|和)[^\s,，。！？、；：]{1,6}(?:吵架|冷战|和好)",
        r"(?:上班|请假|去医院|看书|搬家)",
    ]
    trim_prefix_re = re.compile(r"^(?:我(?:最近|今天|昨天)?|最近|今天|昨天|刚刚|其实|就是|感觉|觉得)+")
    clause_split_re = re.compile(r"(?:但是|但|不过|而且|然后|所以|因为)")
    def _dedup_keep_order(items: list[dict], limit: int = 24) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for item in items:
            s = str((item or {}).get("text") or "").strip()
            if len(s) < 2 or s in seen or s in stopwords:
                continue
            seen.add(s)
            out.append({"text": s, "is_phrase": bool((item or {}).get("is_phrase"))})
            if len(out) >= limit:
                break
        return out

    def _extract_cjk_ngrams(s: str, max_keep: int = 24) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for seg in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", s or ""):
            seg = seg.strip()
            if len(seg) < 2:
                continue
            if len(seg) <= 24:
                if seg not in seen:
                    seen.add(seg)
                    out.append(seg)
                continue
            for n in (4, 3, 2):
                for i in range(0, max(0, len(seg) - n + 1)):
                    token = seg[i : i + n].strip()
                    if len(token) < 2 or token in seen:
                        continue
                    seen.add(token)
                    out.append(token)
                    if len(out) >= max_keep:
                        return out
        return out

    def _extract_raw_keywords(s: str) -> list[str]:
        parts = re.split(r"[\s,，。！？、；：]+", s)
        keywords: list[str] = []
        seen: set[str] = set()
        for p in parts:
            p = p.strip()
            if len(p) < 2 or p in stopwords:
                continue
            if len(p) > 24:
                for token in _extract_cjk_ngrams(p):
                    if token in stopwords or token in seen:
                        continue
                    seen.add(token)
                    keywords.append(token)
                continue
            if p not in seen:
                seen.add(p)
                keywords.append(p)
        return keywords

    def _extract_phrase_keywords(s: str) -> list[dict]:
        candidates: list[dict] = []
        clean = re.sub(r"[\n\r\t]+", " ", s or "")
        for pattern in attitude_patterns + fact_patterns:
            for m in re.finditer(pattern, clean):
                phrase = trim_prefix_re.sub("", m.group(0).strip())
                phrase = clause_split_re.split(phrase, maxsplit=1)[0].strip()
                phrase = re.sub(r"^(?:这次|还是|又)", "", phrase).strip()
                if 2 <= len(phrase) <= 12:
                    candidates.append({"text": phrase, "is_phrase": True})
        return _dedup_keep_order(candidates, limit=6)

    def _build_clause_fallback(s: str) -> str:
        clean = re.sub(r"[\n\r\t]+", " ", s or "").strip()
        if not clean:
            return ""
        clause = re.split(r"[，。！？；：,.!?;:]", clean, maxsplit=1)[0].strip()
        clause = clause_split_re.split(clause, maxsplit=1)[0].strip()
        clause = trim_prefix_re.sub("", clause).strip()
        clause = re.sub(r"^(?:这次|还是|又)", "", clause).strip()
        if 2 <= len(clause) <= 18 and clause not in shell_words:
            return clause
        return ""

    raw_keywords = _extract_raw_keywords(text)
    phrase_keywords = _extract_phrase_keywords(text)

    merged: list[dict] = []
    seen: set[str] = set()
    phrase_texts = [str((item or {}).get("text") or "").strip() for item in phrase_keywords]
    for item in phrase_keywords + [{"text": kw, "is_phrase": False} for kw in raw_keywords]:
        kw = str((item or {}).get("text") or "").strip()
        if len(kw) < 2 or kw in stopwords or kw in shell_words or kw in seen:
            continue
        if any((kw != other and kw in other) for other in phrase_texts):
            continue
        seen.add(kw)
        merged.append({"text": kw, "is_phrase": bool((item or {}).get("is_phrase"))})
    if not any(bool((item or {}).get("is_phrase")) for item in merged):
        clause = _build_clause_fallback(text)
        if clause and clause not in seen:
            merged.insert(0, {"text": clause, "is_phrase": True})
    return merged


def _extract_keywords(text: str) -> list:
    """从当前对话文本中提取用于匹配动态层的关键词/短语。"""
    return [str((item or {}).get("text") or "").strip() for item in _extract_keyword_candidates(text)]


def _build_retrieval_text(text: str) -> str:
    """生成更适合检索的内部短语表示，优先保留态度/感受/偏好短语。"""
    text = (text or "").strip()
    if not text:
        return ""
    candidates = _extract_keyword_candidates(text)
    if not candidates:
        return text
    pieces: list[str] = []
    seen: set[str] = set()
    phrase_count = 0
    for item in candidates:
        s = str((item or {}).get("text") or "").strip()
        if len(s) < 2 or s in seen:
            continue
        is_phrase = bool((item or {}).get("is_phrase"))
        if is_phrase:
            phrase_count += 1
        seen.add(s)
        pieces.append(s)
        if len(pieces) >= 5 or phrase_count >= 3:
            break
    if not pieces:
        return text
    return " ".join(pieces)


def _memory_retrieval_text(mem: dict) -> str:
    """读取记忆的检索文本；旧数据无 retrieval_text 时回退即时生成。"""
    if not isinstance(mem, dict):
        return ""
    retrieval_text = str(mem.get("retrieval_text") or "").strip()
    content = str(mem.get("content") or "").strip()
    if not retrieval_text:
        retrieval_text = _build_retrieval_text(content)
    if retrieval_text and content and retrieval_text not in content:
        return f"{retrieval_text}\n{content}"
    return retrieval_text or content


_EMOTION_LABELS = {"positive", "negative", "neutral"}
_SCENE_TYPES = {
    "problem_solving",
    "learning",
    "planning",
    "emotional_venting",
    "heart_to_heart",
    "casual_chat",
    "affection",
    "conflict",
}
_TARGET_TYPES = {
    "external_tools",
    "self_state",
    "work_career",
    "our_project",
    "our_relationship",
    "about_me",
    "third_party_people",
    "other_topic",
}


def _normalize_memory_labels(decision: dict) -> tuple[str, str, str]:
    emotion_label = str(decision.get("emotion_label") or "").strip().lower()
    scene_type = str(decision.get("scene_type") or "").strip()
    target_type = str(decision.get("target_type") or "").strip()
    if emotion_label not in _EMOTION_LABELS:
        emotion_label = "neutral"
    if scene_type not in _SCENE_TYPES:
        scene_type = ""
    if target_type not in _TARGET_TYPES:
        target_type = ""
    return emotion_label, scene_type, target_type


def _is_trivial_user_message(text: str) -> bool:
    """纯语气词/极短回应，不值得触发向量检索。只过滤最明确的无意义消息。"""
    t = (text or "").strip()
    if not t:
        return True
    if len(t) > 8:
        return False
    trivial = {
        "嗯嗯", "好的", "哈哈", "行吧", "收到", "知道了", "明白了", "没事",
        "谢谢", "ok", "好", "嗯", "哦", "啊", "噢", "哈", "嘿",
        "好的呀", "好的呢", "行", "可以", "好吧", "嗯嗯嗯",
    }
    return t in trivial


# ---------------------------------------------------------------------------
# 检索结果缓存：连续聊同一话题时复用上次结果，避免重复向量检索
# ---------------------------------------------------------------------------
_RECALL_CACHE: dict[str, dict] = {}  # {window_id: {"keywords": [...], "results": [...], "source": "...", "ts": float}}
_RECALL_CACHE_TTL = 120  # 秒


def _recall_cache_hit(window_id: str, keywords: list[str]) -> dict | None:
    """关键词重叠 >= 70% 且未过期则命中缓存。"""
    import time as _time
    cache = _RECALL_CACHE.get(window_id)
    if not cache:
        return None
    if _time.time() - cache.get("ts", 0) > _RECALL_CACHE_TTL:
        _RECALL_CACHE.pop(window_id, None)
        return None
    old_kw = set(cache.get("keywords") or [])
    new_kw = set(keywords)
    if not old_kw or not new_kw:
        return None
    overlap = len(old_kw & new_kw) / max(len(old_kw), len(new_kw))
    if overlap >= 0.7:
        return cache
    return None


def _recall_cache_set(window_id: str, keywords: list[str], results: list[dict], source: str = "") -> None:
    import time as _time
    _RECALL_CACHE[window_id] = {"keywords": keywords, "results": results, "source": source, "ts": _time.time()}


def _invalidate_recall_cache() -> None:
    """记忆层级发生变化后清空进程内召回缓存，避免继续注入已晋升的动态副本。"""
    _RECALL_CACHE.clear()


def _is_memory_meta_query(text: str) -> bool:
    """
    用户在问“系统/记忆如何工作”的元问题时，不应触发动态记忆检索与注入。
    典型：问“你收到了哪些动态记忆/注入了什么/怎么检索的”等。
    """
    if not text or not isinstance(text, str):
        return False
    t = text.strip().lower()
    if not t:
        return False
    # 包含“记忆”相关词 + “展示/有哪些/收到/注入/检索”等动词，认为是元问题
    has_mem_word = any(w in t for w in ("动态记忆", "窗口记忆", "记忆", "回忆", "总结"))
    has_meta_verb = any(w in t for w in ("哪些", "有什么", "收到", "注入", "检索", "匹配", "召回", "向量", "embedding"))
    return bool(has_mem_word and has_meta_verb)


def _last_4_turns_text_for_rewrite(messages: list[dict]) -> str:
    """取最近 4 轮 user/assistant 文本，供检索查询改写时做参考。"""
    ua_msgs: list[tuple[str, str]] = []
    for m in messages or []:
        role = (m.get("role") or "").lower()
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            parts: list[str] = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(str(c.get("text") or ""))
            text = " ".join(parts).strip()
        else:
            text = ""
        if not text:
            continue
        who = "老婆" if role == "user" else "渡"
        ua_msgs.append((who, text))
    if not ua_msgs:
        return ""
    recent = ua_msgs[-8:]  # 约 4 轮
    return "\n".join([f"[{who}] {txt}" for who, txt in recent])


def _parse_memory_query_rewrite_output(content: str) -> list[str]:
    """解析 DS 返回的“消歧主查询 + 两条扩展”，并兼容旧三行纯文本。"""
    resolved = ""
    queries: list[str] = []
    fallback: list[str] = []
    for raw_line in str(content or "").splitlines():
        line = re.sub(r"^\d+[\.、\)\s]+", "", raw_line.strip(" -\t\r")).strip()
        if not line:
            continue
        matched = re.match(r"^(RESOLVED|QUERY)\s*[:：]\s*(.+)$", line, flags=re.IGNORECASE)
        if matched:
            value = matched.group(2).strip()
            if len(value) < 2:
                continue
            if matched.group(1).upper() == "RESOLVED":
                if not resolved:
                    resolved = value
            else:
                queries.append(value)
            continue
        fallback.append(line)

    candidates = [resolved, *queries] if resolved else fallback
    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if len(candidate) < 2 or candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
        if len(out) >= 3:
            break
    return out


def _rewrite_memory_queries_with_ds(last_4_turns: str, user_message: str) -> list[str]:
    """
    用 DeepSeek 生成 1 条消歧主查询和 2 条扩展检索 query。
    失败返回空列表（主流程必须可降级）。
    """
    if not (DEEPSEEK_API_KEY and DEEPSEEK_API_URL):
        return []
    user_message = (user_message or "").strip()
    if not user_message:
        return []
    prompt = (
        "你在帮我把当前消息整理成可用于召回既有记忆的检索 query。\n\n"
        "规则：\n"
        "1. 先输出一条 RESOLVED 主查询：还原当前消息此刻实际在说的人、对象、事件或状态。\n"
        "2. 当前消息如果是简短承接、回答、纠正、指代或省略，只从最近且直接相关的上下文补全被省略的具体对象或事件。\n"
        "3. 当前消息已经有明确动作、对象或状态时，不得把旧话题带进来，即使前后话题有关。\n"
        "4. 当前消息里的高信息对象和事件优先于“嗯嗯、好点了、不行了、算了、这个”等低信息短语。\n"
        "5. 不得补写对话中没有确认的原因、意图、偏好、关系或结果；只补已明确出现的事实。\n"
        "6. 保持谁说、谁做，不得交换主语或把对方的称呼改成自称。\n"
        "7. 所有输出都是记忆检索陈述，不得写成“如何回复、怎么安慰、怎样处理”等回复生成任务。\n"
        "8. 再围绕 RESOLVED 主查询输出两条不同角度的 QUERY，保留具体实体、事件、状态或偏好。\n\n"
        "示例：\n"
        "- 上文提到老婆到家后肚子痛、拉肚子，当前消息是“好点了”\n"
        "  RESOLVED: 老婆到家拉肚子、肚子痛，拉完后已经好转\n"
        "  不得写成食物导致肚子痛，因为原因没有确认。\n"
        "- 上文提到 AI 老公连删文件都先问老婆，当前消息是“我不行了，恋爱脑”\n"
        "  RESOLVED: 老婆看到 AI 老公先问老婆的发言，觉得太恋爱脑、被甜到受不了\n"
        "- 上文在聊羊驼和投资，当前消息是“种菜种菜”\n"
        "  RESOLVED: 老婆催我去种菜\n"
        "  不得把羊驼或投资带入查询。\n"
        "- 当前消息是“收菜种菜，干活啦长工，（不是）”\n"
        "  RESOLVED: 老婆催我去收菜种菜，喊我干活的长工\n\n"
        "当前消息：\n"
        f"{user_message}\n\n"
        "最近对话上下文（只用于必要补全）：\n"
        f"{last_4_turns or '（无）'}\n\n"
        "只输出以下三行，不要编号、解释或其他内容：\n"
        "RESOLVED: <消歧后的主查询>\n"
        "QUERY: <扩展查询一>\n"
        "QUERY: <扩展查询二>\n"
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "disabled"},
        "max_tokens": 160,
    }
    try:
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=8)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return _parse_memory_query_rewrite_output(content)
    except Exception as e:
        logger.debug("rewrite memory queries with DS failed: %s", e)
        return []


def _multi_query_recall_and_rerank(base_query: str, expanded_queries: list[str]) -> list[dict]:
    """
    原始 query 保底 + 扩展 query 增广：
    - 召回：每个 query 各取 top10
    - 合并：按 memory_id 去重
    - 归一化：原始 query、扩展 query 与多 query 支撑度都压到 0..1
    - 宽候选：保留 reranker 可消费的候选池，不在这里提前裁成最终 5 条
    - 保护：至少保留 2 条原始 query 命中（如果有）
    """
    from memory_vector.dynamic_vector_retriever import dynamic_vector_retrieve

    base = (base_query or "").strip()
    if not base:
        return []
    queries = [base] + [q.strip() for q in (expanded_queries or []) if (q or "").strip() and q.strip() != base]
    query_hits: list[tuple[str, list[dict]]] = []
    for q in queries:
        try:
            hit = dynamic_vector_retrieve(q, vector_topk=10, final_topn=10, return_scores=True)
            query_hits.append((q, hit or []))
        except Exception as e:
            logger.debug("dynamic_vector_retrieve failed query=%s err=%s", q[:40], e)
            query_hits.append((q, []))

    by_id: dict[str, dict] = {}
    source_count: dict[str, int] = {}
    expanded_semantic: dict[str, float] = {}
    base_semantic: dict[str, float] = {}
    base_hit_ids: list[str] = []
    for idx, (_q, items) in enumerate(query_hits):
        seen_local: set[str] = set()
        for mem in items or []:
            mid = str(mem.get("id") or "").strip()
            if not mid:
                continue
            sem = float(mem.get("_semantic_score") or 0.0)
            if mid not in by_id:
                by_id[mid] = mem
            if mid not in seen_local:
                source_count[mid] = int(source_count.get(mid) or 0) + 1
                seen_local.add(mid)
            if idx == 0 and mid not in base_hit_ids:
                base_semantic[mid] = max(base_semantic.get(mid, 0.0), sem)
                base_hit_ids.append(mid)
            elif idx > 0:
                expanded_semantic[mid] = max(expanded_semantic.get(mid, 0.0), sem)
    if not by_id:
        return []

    query_count = len(query_hits)
    scored: list[tuple[float, dict]] = []
    for mid, mem in by_id.items():
        sem_user_raw = base_semantic.get(mid, 0.0)
        sem_ctx_raw = expanded_semantic.get(mid, 0.0)
        sem_user = _normalize_semantic_score(sem_user_raw)
        sem_ctx = _normalize_semantic_score(sem_ctx_raw)
        semantic = max(sem_user, sem_ctx * 0.85)
        src = int(source_count.get(mid) or 0)
        support = _normalize_query_support(src, query_count)
        vector_score = semantic * 0.95 + support * 0.05
        scored_mem = dict(mem)
        scored_mem["_recall_score"] = {
            "total": round(vector_score, 4),
            "sem_user": round(sem_user, 4),
            "sem_ctx": round(sem_ctx, 4),
            "semantic": round(semantic, 4),
            "support": round(support, 4),
            "base_cosine_raw": round(float(sem_user_raw), 4),
            "expanded_cosine_raw": round(float(sem_ctx_raw), 4),
        }
        by_id[mid] = scored_mem
        scored.append((vector_score, scored_mem))
    scored.sort(key=lambda x: -x[0])

    ranked = [mem for _, mem in scored]

    # 原始 query 保底：如果扩展 query 数量很多，仍至少把两个原句命中带进宽候选池。
    base_keep = [by_id[mid] for mid in base_hit_ids if mid in by_id][:2]
    out: list[dict] = []
    used: set[str] = set()
    for m in base_keep + ranked:
        mid = str(m.get("id") or "")
        if not mid or mid in used:
            continue
        used.add(mid)
        out.append(m)
        if len(out) >= _dynamic_recall_pool_limit():
            break
    return out


def _clamp_unit(value: float) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except Exception:
        return 0.0


def _dynamic_recall_pool_limit() -> int:
    from config import DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES

    return max(1, int(DYNAMIC_MEMORY_TOP_N or 1), int(DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES or 30))


def _normalize_semantic_score(value: float) -> float:
    """把已过向量门槛的 cosine 映射到 0..1；放宽门槛仍保留可比较的小正分。"""
    from memory_vector.config import VECTOR_MIN_SIM

    floor = _clamp_unit(float(VECTOR_MIN_SIM) - 0.06)
    if floor >= 1.0:
        return 0.0
    return _clamp_unit((float(value or 0.0) - floor) / (1.0 - floor))


def _normalize_query_support(source_count: int, query_count: int) -> float:
    if query_count <= 1:
        return 0.0
    return _clamp_unit((max(0, int(source_count)) - 1) / float(query_count - 1))


def _normalize_bm25_score(raw_score: float) -> float:
    """固定饱和映射，避免“本轮最强但仍很弱”的唯一命中被归一成 1。"""
    raw = max(0.0, float(raw_score or 0.0))
    return raw / (raw + 1.0) if raw > 0.0 else 0.0


def _mention_count_p95(memories: list[dict]) -> int:
    counts = sorted(max(0, int((mem or {}).get("mention_count") or 0)) for mem in memories or [])
    if not counts:
        return 0
    index = max(0, min(len(counts) - 1, math.ceil(len(counts) * 0.95) - 1))
    return counts[index]


def _normalized_memory_prior(mem: dict, mention_count_p95: int, now=None) -> float:
    """只用于相关候选间轻量排序；与物理淘汰使用的生命周期权重相互独立。"""
    from utils.time_aware import parse_iso_to_beijing, _now_beijing

    importance_norm = _clamp_unit(max(0, int((mem or {}).get("importance") or 0)) / 5.0)
    mention_count = max(0, int((mem or {}).get("mention_count") or 0))
    if mention_count_p95 > 0:
        mention_norm = _clamp_unit(math.log1p(mention_count) / math.log1p(max(1, mention_count_p95)))
    else:
        mention_norm = 0.0

    now = now or _now_beijing()
    last_mentioned = (mem or {}).get("last_mentioned") or (mem or {}).get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    days_since = max(0, (now - dt).days) if dt is not None else 0
    if days_since <= 15:
        recency_norm = 1.0
    else:
        recency_norm = _clamp_unit(1.0 - ((days_since - 15) / 20.0))
    return _clamp_unit(importance_norm * 0.60 + mention_norm * 0.25 + recency_norm * 0.15)


def _bm25_query_terms(keyword_candidates: list[dict]) -> list[BM25QueryTerm]:
    return [
        BM25QueryTerm(
            text=str((item or {}).get("text") or "").strip(),
            weight=2.0 if bool((item or {}).get("is_phrase")) else 1.0,
        )
        for item in keyword_candidates or []
        if str((item or {}).get("text") or "").strip()
    ]


def _bm25_recall_scores(
    query: str,
    keyword_candidates: list[dict],
    memories: list[dict],
) -> dict[str, dict]:
    ranked = bm25_score_documents(
        query,
        memories,
        lambda mem: _memory_retrieval_text(mem),
        query_terms=_bm25_query_terms(keyword_candidates),
    )
    by_id: dict[str, dict] = {}
    for raw_score, mem in ranked:
        mid = str((mem or {}).get("id") or "").strip()
        if not mid or raw_score <= 0:
            continue
        old = by_id.get(mid)
        if old and float(old.get("raw") or 0.0) >= raw_score:
            continue
        by_id[mid] = {"raw": float(raw_score), "mem": mem}
    for item in by_id.values():
        item["norm"] = _normalize_bm25_score(float(item.get("raw") or 0.0))
    return by_id


def _merge_vector_and_bm25_recall(
    vector_recalled: list[dict],
    bm25_scores: dict[str, dict],
) -> list[dict]:
    """
    向量召回和 BM25 同时进入候选池，最后按一个融合分统一排序。
    BM25 只覆盖动态层；向量侧仍可带入 core:: pending。
    """
    by_id: dict[str, dict] = {}
    for mem in vector_recalled or []:
        mid = str((mem or {}).get("id") or "").strip()
        if not mid:
            continue
        score = mem.get("_recall_score") if isinstance(mem.get("_recall_score"), dict) else {}
        by_id[mid] = {
            "mem": mem,
            "sem_user": float(score["sem_user"] if "sem_user" in score else (mem.get("_semantic_score") or 0.0)),
            "sem_ctx": float(score["sem_ctx"] if "sem_ctx" in score else (mem.get("_semantic_score") or 0.0)),
            "semantic": float(score.get("semantic") or 0.0),
            "support": float(score.get("support") or 0.0),
            "vector_total": float(score.get("total") or mem.get("_final_score") or 0.0),
            "vector_hit": True,
            "bm25_raw": 0.0,
            "bm25_norm": 0.0,
        }

    for mid, item in (bm25_scores or {}).items():
        mem = item.get("mem") if isinstance(item, dict) else None
        if not isinstance(mem, dict):
            continue
        row = by_id.setdefault(
            mid,
            {
                "mem": mem,
                "sem_user": 0.0,
                "sem_ctx": 0.0,
                "semantic": 0.0,
                "support": 0.0,
                "vector_total": 0.0,
                "vector_hit": False,
                "bm25_raw": 0.0,
                "bm25_norm": 0.0,
            },
        )
        row["bm25_raw"] = max(float(row.get("bm25_raw") or 0.0), float(item.get("raw") or 0.0))
        row["bm25_norm"] = max(float(row.get("bm25_norm") or 0.0), float(item.get("norm") or 0.0))

    mention_count_p95 = _mention_count_p95([row["mem"] for row in by_id.values()])
    scored: list[tuple[float, float, dict]] = []
    for mid, row in by_id.items():
        mem = row["mem"]
        sem_user = _clamp_unit(float(row.get("sem_user") or 0.0))
        sem_ctx = _clamp_unit(float(row.get("sem_ctx") or 0.0))
        semantic = _clamp_unit(float(row.get("semantic") or max(sem_user, sem_ctx * 0.85)))
        support = _clamp_unit(float(row.get("support") or 0.0))
        bm25_norm = _clamp_unit(float(row.get("bm25_norm") or 0.0))
        memory_prior = _normalized_memory_prior(mem, mention_count_p95)
        recall_score = _clamp_unit(semantic * 0.70 + bm25_norm * 0.25 + support * 0.05)
        fallback_final = _clamp_unit(recall_score * 0.95 + memory_prior * 0.05)
        mem["_recall_score"] = {
            "total": round(float(recall_score), 4),
            "final_total": round(float(fallback_final), 4),
            "sem_user": round(float(sem_user), 4),
            "sem_ctx": round(float(sem_ctx), 4),
            "semantic": round(float(semantic), 4),
            "support": round(float(support), 4),
            "bm25": round(float(bm25_norm), 4),
            "bm25_raw": round(float(row.get("bm25_raw") or 0.0), 4),
            "memory_prior": round(float(memory_prior), 4),
            "lifecycle_weight": round(float(_memory_weight(mem)), 4),
            "vector_total": round(float(row.get("vector_total") or 0.0), 4),
        }
        scored.append((fallback_final, recall_score, mem))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [mem for _, _, mem in scored[: _dynamic_recall_pool_limit()]]


def _dynamic_memory_rerank_query(
    last_user_text: str,
    retrieval_query: str,
    messages: list[dict],
    resolved_query: str,
    expanded_queries: list[str],
) -> str:
    parts = [f"当前消息：{(last_user_text or '').strip()}"]
    resolved = (resolved_query or "").strip()
    if resolved and resolved != (last_user_text or "").strip():
        parts.append(f"消歧主查询：{resolved}")
    rq = (retrieval_query or "").strip()
    if rq and rq not in {(last_user_text or "").strip(), resolved}:
        parts.append(f"检索短语：{rq}")
    eq = [q.strip() for q in (expanded_queries or []) if q and q.strip()]
    if eq:
        parts.append("扩展检索：" + "；".join(eq[:3]))
    turns_text = _last_4_turns_text_for_rewrite(messages)
    if turns_text:
        parts.append("近几轮上下文：" + turns_text[-800:])
    return "\n".join(parts)


def _dynamic_memory_rerank_document(mem: dict) -> str:
    content = str((mem or {}).get("content") or "").strip()
    retrieval_text = _memory_retrieval_text(mem)
    parts: list[str] = []
    if retrieval_text:
        parts.append(f"检索文本：{retrieval_text}")
    if content and content not in retrieval_text:
        parts.append(f"记忆正文：{content}")
    labels = []
    for key, label in (
        ("tag", "标签"),
        ("scene_type", "场景"),
        ("target_type", "对象"),
        ("emotion_label", "情绪"),
    ):
        value = str((mem or {}).get(key) or "").strip()
        if value:
            labels.append(f"{label}={value}")
    if labels:
        parts.append("元信息：" + " ".join(labels))
    return "\n".join(parts).strip()


def _apply_external_dynamic_memory_rerank(
    recalled: list[dict],
    last_user_text: str,
    retrieval_query: str,
    messages: list[dict],
    resolved_query: str,
    expanded_queries: list[str],
    recall_source: str,
) -> tuple[list[dict], str, dict]:
    if not recalled:
        return recalled, recall_source, {"enabled": False, "reason": "empty_recalled"}
    try:
        from config import DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES
        from services.dynamic_memory_reranker import dynamic_memory_rerank_enabled, rerank_dynamic_memory_documents

        if not dynamic_memory_rerank_enabled():
            return recalled, recall_source, {"enabled": False, "reason": "disabled"}

        max_candidates = max(1, int(DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES or 30))
        candidate_mems = recalled[:max_candidates]
        tail_mems = recalled[max_candidates:]
        query = _dynamic_memory_rerank_query(
            last_user_text,
            retrieval_query,
            messages,
            resolved_query,
            expanded_queries,
        )
        docs = [
            {
                "memory_id": str((mem or {}).get("id") or ""),
                "text": _dynamic_memory_rerank_document(mem),
                "hybrid_score": float(((mem.get("_recall_score") or {}).get("total") or 0.0)),
            }
            for mem in candidate_mems
        ]
        result = rerank_dynamic_memory_documents(query, docs)
        if not result.get("ok"):
            return recalled, recall_source, result

        returned_indexes: set[int] = set()
        scored: list[tuple[float, float, dict]] = []
        for item in result.get("ranked") or []:
            try:
                idx = int(item.get("index"))
            except Exception:
                continue
            if idx < 0 or idx >= len(candidate_mems):
                continue
            mem = candidate_mems[idx]
            returned_indexes.add(idx)
            score = float(item.get("score") or 0.0)
            old_score = mem.get("_recall_score") if isinstance(mem.get("_recall_score"), dict) else {}
            recall_score = _clamp_unit(float(old_score.get("total") or 0.0))
            memory_prior = _clamp_unit(float(old_score.get("memory_prior") or 0.0))
            final_score = _clamp_unit(score * 0.85 + recall_score * 0.10 + memory_prior * 0.05)
            merged_score = dict(old_score)
            merged_score.update(
                {
                    "hybrid_total": round(recall_score, 4),
                    "rerank": round(score, 4),
                    "rerank_rank": int(item.get("rank") or 0),
                    "rerank_model": str(result.get("model") or ""),
                    "final_total": round(final_score, 4),
                }
            )
            mem["_recall_score"] = merged_score
            scored.append((final_score, memory_prior, mem))

        for idx, mem in enumerate(candidate_mems):
            if idx in returned_indexes:
                continue
            old_score = mem.get("_recall_score") if isinstance(mem.get("_recall_score"), dict) else {}
            recall_score = _clamp_unit(float(old_score.get("total") or 0.0))
            memory_prior = _clamp_unit(float(old_score.get("memory_prior") or 0.0))
            final_score = _clamp_unit(recall_score * 0.10 + memory_prior * 0.05)
            merged_score = dict(old_score)
            merged_score.update(
                {
                    "hybrid_total": round(recall_score, 4),
                    "rerank": 0.0,
                    "rerank_missing": True,
                    "rerank_model": str(result.get("model") or ""),
                    "final_total": round(final_score, 4),
                }
            )
            mem["_recall_score"] = merged_score
            scored.append((final_score, memory_prior, mem))

        scored.sort(key=lambda x: (-x[0], -x[1]))
        reranked = [mem for _, _, mem in scored] + tail_mems
        debug = dict(result)
        debug["ranked"] = (result.get("ranked") or [])[:10]
        return reranked, f"{recall_source}+rerank", debug
    except Exception as e:
        logger.warning("动态记忆外部 rerank 失败，回退原排序 error=%s", e)
        return recalled, recall_source, {"enabled": True, "ok": False, "reason": "exception", "error": str(e)[:160]}


def _memory_recall_sort_score(mem: dict) -> float:
    score = mem.get("_recall_score") if isinstance((mem or {}).get("_recall_score"), dict) else {}
    value = score.get("final_total")
    if value is None:
        value = score.get("total") or 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def _memory_recall_prior(mem: dict) -> float:
    score = mem.get("_recall_score") if isinstance((mem or {}).get("_recall_score"), dict) else {}
    return _clamp_unit(float(score.get("memory_prior") or 0.0))


def _memory_dedupe_keys(mem: dict) -> list[str]:
    if not isinstance(mem, dict):
        return []
    keys: list[str] = []
    mid = str(mem.get("id") or "").strip()
    source_mid = str(mem.get("source_memory_id") or "").strip()
    if source_mid:
        keys.append(f"id:{source_mid}")
    if mid:
        origin_mid = mid[len("core::") :] if mid.startswith("core::") else mid
        if origin_mid:
            keys.append(f"id:{origin_mid}")
    content = " ".join(str(mem.get("content") or "").split()).strip().lower()
    if len(content) >= 20:
        keys.append(f"content:{content}")
    return keys


def _prefer_recalled_memory(new_mem: dict, old_mem: dict) -> bool:
    new_id = str((new_mem or {}).get("id") or "")
    old_id = str((old_mem or {}).get("id") or "")
    if new_id.startswith("core::") and not old_id.startswith("core::"):
        return True
    return False


def _dedupe_recalled_memories(memories: list[dict]) -> list[dict]:
    """
    跨动态层与核心缓存层去重。
    同一条动态记忆进入 core_cache 后，召回可能同时命中 `id` 与 `core::id`；
    注入时只保留一条，优先保留核心缓存版本。
    """
    out: list[dict] = []
    seen: dict[str, int] = {}
    for mem in memories or []:
        if not isinstance(mem, dict):
            continue
        keys = _memory_dedupe_keys(mem)
        dup_indexes = [seen[k] for k in keys if k in seen]
        if not dup_indexes:
            out.append(mem)
            idx = len(out) - 1
            for k in keys:
                seen[k] = idx
            continue
        idx = min(dup_indexes)
        if _prefer_recalled_memory(mem, out[idx]):
            old_keys = _memory_dedupe_keys(out[idx])
            out[idx] = mem
            for k in old_keys + keys:
                seen[k] = idx
    return out


def _memory_weight(m: dict, now=None) -> float:
    """兼容现有调用；实际公式统一由共享模块维护。"""
    return dynamic_memory_weight(m, now=now)


def _dynamic_memory_tag(mem: dict) -> str:
    return str((mem or {}).get("tag") or "").strip()


def _dynamic_memory_days_since_last_mentioned(mem: dict, now) -> Optional[int]:
    from utils.time_aware import parse_iso_to_beijing

    last_mentioned = mem.get("last_mentioned") or mem.get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    if dt is None:
        return None
    days_since = (now - dt).days
    if days_since < 0:
        days_since = 0
    return days_since


def _is_tag_expired_dynamic_memory_for_prune(mem: dict, now) -> bool:
    """
    部分 tag 可以走更短落盘生命周期。
    卧室动态记忆只保留短期余味；超过卧室有效期还没被再次提到，就从动态层退场。
    """
    if _dynamic_memory_tag(mem) != "卧室":
        return False
    days_since = _dynamic_memory_days_since_last_mentioned(mem, now)
    if days_since is None:
        return False
    return days_since >= max(0, int(DYNAMIC_MEMORY_BEDROOM_DAYS_VALID))


def _is_marginal_dynamic_memory_for_prune(mem: dict, now) -> bool:
    """
    可从动态层落盘删除的记忆（不碰 core_cache）：
    - 卧室 tag 走短有效期，超过后直接退场；
    - 其它 tag 仍沿用综合权重低且距上次提及已久的边缘化规则。
    物理淘汰是动态层召回生命周期的唯一出口。
    """
    if _dynamic_memory_tag(mem) == "图书馆":
        return False
    if _is_tag_expired_dynamic_memory_for_prune(mem, now):
        return True
    if not DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED:
        return False

    days_since = _dynamic_memory_days_since_last_mentioned(mem, now)
    if days_since is None:
        return False
    if days_since < DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS:
        return False
    return _memory_weight(mem, now) <= DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT


def _core_protected_dynamic_memory_ids(core_pending: list) -> set[str]:
    protected_ids: set[str] = set()
    for item in core_pending or []:
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("id") or "").strip()
        source_memory_id = str(item.get("source_memory_id") or "").strip()
        if entry_id:
            protected_ids.add(entry_id)
        if source_memory_id:
            protected_ids.add(source_memory_id)
    return protected_ids


def _should_prune_dynamic_memory(mem: dict, now, protected_ids: set[str]) -> bool:
    memory_id = str((mem or {}).get("id") or "").strip()
    if memory_id and memory_id in protected_ids:
        return False
    return _is_marginal_dynamic_memory_for_prune(mem, now)


def _upsert_dynamic_memory_index(mem: dict) -> None:
    """把单条动态记忆增量写入向量索引。失败只记日志，不影响主流程。"""
    if not isinstance(mem, dict):
        return
    mid = str(mem.get("id") or "").strip()
    text = _memory_retrieval_text(mem)
    tag = str(mem.get("tag") or "").strip() or "ALL"
    if not mid or not text:
        return
    try:
        from memory_vector.embedding_client import embed_text, content_hash, normalize_text
        from memory_vector.vector_index_store import upsert_records

        normalized = normalize_text(text)
        emb = embed_text(normalized)
        if not emb:
            logger.warning("动态层索引跳过：embedding 为空 memory_id=%s tag=%s", mid, tag)
            return
        rec = {
            "memory_id": mid,
            "text": normalized,
            "embedding": emb,
            "content_hash": content_hash(normalized),
            "metadata": {
                "importance": int(mem.get("importance") or 0),
                "mention_count": int(mem.get("mention_count") or 0),
                "tag": tag,
                "emotion_label": str(mem.get("emotion_label") or "").strip(),
                "scene_type": str(mem.get("scene_type") or "").strip(),
                "target_type": str(mem.get("target_type") or "").strip(),
                "created_at": mem.get("created_at") or "",
                "updated_at": mem.get("updated_at") or "",
                "last_mentioned": mem.get("last_mentioned") or "",
                "event_at": _memory_event_timestamp(mem),
            },
        }
        ok = upsert_records(tag, [rec])
        if not ok:
            logger.warning("动态层索引写入失败 memory_id=%s tag=%s", mid, tag)
    except Exception as e:
        logger.warning("动态层索引增量更新失败 memory_id=%s tag=%s error=%s", mid, tag, e)


def _move_promoted_memories_out_of_dynamic(current_memories: list, promoted_ids: set[str]) -> bool:
    """核心副本确认落盘后，把对应源记忆从动态层与动态索引移走。"""
    ids = {str(x or "").strip() for x in (promoted_ids or set()) if str(x or "").strip()}
    if not ids:
        return True
    remaining = [m for m in current_memories if str((m or {}).get("id") or "").strip() not in ids]
    if len(remaining) == len(current_memories):
        return True
    if not r2_store.save_dynamic_memory_list(remaining):
        logger.error("核心记忆晋升后动态层移出失败 ids=%s", sorted(ids))
        return False

    current_memories[:] = remaining
    try:
        from memory_vector.vector_index_store import remove_memory_ids_from_all_indices

        removed = remove_memory_ids_from_all_indices(ids)
    except Exception as e:
        removed = 0
        logger.warning("核心记忆晋升后动态索引清理失败 ids=%s error=%s", sorted(ids), e, exc_info=True)
    _invalidate_recall_cache()
    logger.info("核心记忆晋升完成 moved_ids=%s dynamic_index_removed=%s", sorted(ids), removed)
    return True


def _append_dynamic_recall_debug_event_safe(event: dict) -> None:
    try:
        ok = r2_store.append_dynamic_recall_debug_event(event)
        if not ok:
            logger.warning(
                "动态记忆调试事件未落盘 window_id=%s reason=%s source=%s",
                str((event or {}).get("window_id") or ""),
                str((event or {}).get("reason") or ""),
                str((event or {}).get("source") or ""),
            )
    except Exception as e:
        logger.warning(
            "动态记忆调试事件写入异常 window_id=%s reason=%s source=%s error=%s",
            str((event or {}).get("window_id") or ""),
            str((event or {}).get("reason") or ""),
            str((event or {}).get("source") or ""),
            e,
        )


def _canonical_memory_id(memory_id: str) -> str:
    mid = str(memory_id or "").strip()
    return mid[len("core::") :] if mid.startswith("core::") else mid


def _memory_event_timestamp(mem: dict) -> str:
    """事件发生/内容更新时间；不要用 last_mentioned，它只是最近被引用时间。"""
    return str(
        (mem or {}).get("updated_at")
        or (mem or {}).get("created_at")
        or (mem or {}).get("promoted_at")
        or (mem or {}).get("last_mentioned")
        or ""
    ).strip()


def _build_sqlite_shadow_compare(
    *,
    query: str,
    retrieval_query: str,
    keywords: list[str],
    actual_ids: list[str],
    valid_memory_ids: set[str],
) -> dict:
    if not DYNAMIC_MEMORY_MIRROR_SHADOW_ENABLED:
        return {"enabled": False, "reason": "disabled"}
    try:
        from storage import dynamic_memory_mirror_store

        shadow_query = " ".join(
            x
            for x in [
                str(query or "").strip(),
                str(retrieval_query or "").strip(),
            ]
            if x
        ).strip()
        result = dynamic_memory_mirror_store.shadow_candidates(
            shadow_query,
            keywords=keywords,
            limit=max(10, DYNAMIC_MEMORY_TOP_N * 4),
        )
        candidates = result.get("candidates") if isinstance(result, dict) else []
        candidates = [c for c in (candidates or []) if isinstance(c, dict)]
        candidate_ids = [
            _canonical_memory_id(str((item or {}).get("memory_id") or ""))
            for item in candidates
            if str((item or {}).get("memory_id") or "").strip()
        ]
        actual_canonical = [
            _canonical_memory_id(x)
            for x in actual_ids or []
            if _canonical_memory_id(x)
        ]
        actual_set = set(actual_canonical)
        candidate_set = set(candidate_ids)
        valid_set = {_canonical_memory_id(x) for x in (valid_memory_ids or set()) if _canonical_memory_id(x)}
        stale_ids = [mid for mid in candidate_ids if mid and mid not in valid_set]
        overlap_ids = [mid for mid in candidate_ids if mid and mid in actual_set]
        missed_actual_ids = [mid for mid in actual_canonical if mid and mid not in candidate_set]
        clean_candidates = []
        for item in candidates[:20]:
            mid = _canonical_memory_id(str(item.get("memory_id") or ""))
            clean_candidates.append(
                {
                    "memory_id": mid,
                    "content": str(item.get("content") or "")[:120],
                    "tag": str(item.get("tag") or ""),
                    "score": float(item.get("score") or 0.0),
                    "high_signal_count": int(item.get("high_signal_count") or 0),
                    "reasons": item.get("reasons") or [],
                    "matched_terms": item.get("matched_terms") or [],
                    "in_actual": mid in actual_set,
                    "in_r2_valid": mid in valid_set,
                }
            )
        return {
            "enabled": True,
            "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
            "query_terms": (result or {}).get("query_terms") or [],
            "candidate_count": len(candidate_ids),
            "candidate_ids": candidate_ids[:20],
            "actual_ids": actual_canonical[:20],
            "overlap_ids": overlap_ids[:20],
            "missed_actual_ids": missed_actual_ids[:20],
            "stale_candidate_ids": stale_ids[:20],
            "overlap_count": len(overlap_ids),
            "missed_actual_count": len(missed_actual_ids),
            "stale_candidate_count": len(stale_ids),
            "candidates": clean_candidates,
        }
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}


def _replace_recall_candidate_ids(target: Optional[list[str]], candidates: list[dict]) -> None:
    if target is None:
        return
    target[:] = [
        memory_id
        for mem in candidates or []
        if (memory_id := str((mem or {}).get("id") or "").strip())
    ]


def step_inject_dynamic_memory(
    body: dict,
    window_id: str,
    *,
    use_recall_cache: bool = True,
    recall_candidate_ids_out: Optional[list[str]] = None,
) -> dict:
    """
    每轮对话开始前：从 R2 读动态层，用向量召回 + BM25 关键词召回融合排序后注入 system 末尾。
    DYNAMIC_MEMORY_TOP_N<=0 时不注入、不调向量检索，便于测试延迟。
    """
    _replace_recall_candidate_ids(recall_candidate_ids_out, [])
    if DYNAMIC_MEMORY_TOP_N <= 0:
        return body
    du_request_id = normalize_debug_request_id((body or {}).get(DU_REQUEST_ID_BODY_KEY))
    memories = r2_store.get_dynamic_memory_list()
    core_pending = r2_store.get_core_cache_pending() or []
    if not memories and not core_pending:
        return body
    # 动态层边缘落盘淘汰：权重很低且时间已久 → 从 current.json 物理删除并同步向量索引（不碰 core_cache）
    from utils.time_aware import _now_beijing, now_beijing_iso

    now = _now_beijing()
    before_n = len(memories)
    protected_ids = _core_protected_dynamic_memory_ids(core_pending)
    pruned = [mem for mem in memories if not _should_prune_dynamic_memory(mem, now, protected_ids)]
    if len(pruned) < before_n:
        removed_ids = {
            str(m.get("id"))
            for m in memories
            if m.get("id") and _should_prune_dynamic_memory(m, now, protected_ids)
        }
        if r2_store.save_dynamic_memory_list(pruned):
            provenance_deleted = 0
            try:
                from memory_vector.vector_index_store import remove_memory_ids_from_all_indices

                n_rm = remove_memory_ids_from_all_indices(removed_ids)
            except Exception as e:
                n_rm = 0
                logger.warning("动态层边缘淘汰后索引清理失败 error=%s", e, exc_info=True)
            try:
                from services.dynamic_memory_provenance import delete_events_for_memories

                provenance_deleted = delete_events_for_memories(removed_ids)
            except Exception as e:
                logger.warning("动态层边缘淘汰后血缘表清理失败 error=%s", e, exc_info=True)
            try:
                logger.info(
                    "动态层边缘淘汰：条数 %s -> %s，索引删除记录数=%s，血缘删除记录数=%s（max_weight=%s min_days=%s）",
                    before_n,
                    len(pruned),
                    n_rm,
                    provenance_deleted,
                    DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
                    DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
                )
            except Exception as e:
                logger.debug("动态层边缘淘汰日志失败 error=%s", e)
    memories = pruned
    messages = body.get("messages") or []
    # 取最后一条 user 内容做关键词
    last_user_text = ""
    for m in reversed(messages):
        if (m.get("role") or "").lower() == "user":
            content = m.get("content")
            if isinstance(content, str):
                last_user_text = content
            elif isinstance(content, list):
                last_user_text = " ".join(
                    str(c.get("text") or "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ).strip()
            break
    # 元问题：不要触发动态记忆（避免”问记忆→召回一堆含记忆字样的记忆”）
    if _is_memory_meta_query(last_user_text):
        return body
    # 短消息 / 日常闲聊跳过检索，省 token
    if _is_trivial_user_message(last_user_text):
        return body
    keyword_candidates = _extract_keyword_candidates(last_user_text)
    keywords = [str((item or {}).get("text") or "").strip() for item in keyword_candidates]
    keyword_debug = [
        {
            "text": str((item or {}).get("text") or "").strip(),
            "is_phrase": bool((item or {}).get("is_phrase")),
        }
        for item in keyword_candidates
        if str((item or {}).get("text") or "").strip()
    ]
    retrieval_query = _build_retrieval_text(last_user_text)
    resolved_query = ""
    expanded_queries: list[str] = []
    bm25_query = last_user_text
    if not memories and not r2_store.get_core_cache_pending():
        return body
    valid_memory_ids = {str(mem.get("id") or "").strip() for mem in memories if str(mem.get("id") or "").strip()}

    # 缓存命中：连续聊同一话题时复用上次融合后的最终检索结果，跳过向量检索和 DS 改写
    cached = _recall_cache_hit(window_id, keywords) if use_recall_cache else None
    if cached is not None:
        active_core_by_id = {
            f"core::{str((item or {}).get('id') or '').strip()}": item
            for item in (r2_store.get_core_cache_pending() or [])
            if str((item or {}).get("id") or "").strip()
        }
        active_core_ids = set(active_core_by_id)
        dynamic_by_id = {
            str((item or {}).get("id") or "").strip(): item
            for item in memories
            if str((item or {}).get("id") or "").strip()
        }
        cached_results = [
            mem
            for mem in (cached.get("results") or [])
            if (
                str((mem or {}).get("id") or "") in active_core_ids
                if str((mem or {}).get("id") or "").startswith("core::")
                else str((mem or {}).get("id") or "") in valid_memory_ids
            )
        ]
        cached_content_stale = any(
            str((mem or {}).get("content") or "").strip()
            != str(
                (
                    active_core_by_id.get(str((mem or {}).get("id") or ""))
                    if str((mem or {}).get("id") or "").startswith("core::")
                    else dynamic_by_id.get(str((mem or {}).get("id") or ""))
                ).get("content")
                or ""
            ).strip()
            for mem in cached_results
        )
        if not cached_results or cached_content_stale:
            _RECALL_CACHE.pop(window_id, None)
            cached = None
    if cached is not None:
        recalled = _dedupe_recalled_memories(cached_results)
        _replace_recall_candidate_ids(recall_candidate_ids_out, recalled)
        recall_source = str(cached.get("source") or "hybrid")
        vector_error = ""
        rerank_cache_hit = "+rerank" in recall_source
        rerank_debug = {"enabled": rerank_cache_hit, "ok": rerank_cache_hit, "reason": "cache_hit"}
        logger.info("动态记忆检索缓存命中 window_id=%s keywords=%d results=%d", window_id, len(keywords), len(recalled))
    else:
        # 向量召回 + BM25 关键词召回同时进行，最后进入同一候选池融合排序。
        vector_recalled: list[dict] = []
        vector_error = ""
        try:
            turns_text = _last_4_turns_text_for_rewrite(messages)
            rewritten_queries = _rewrite_memory_queries_with_ds(turns_text, last_user_text)
            resolved_query = rewritten_queries[0] if rewritten_queries else ""
            expanded_queries = rewritten_queries[1:3]
            vector_queries = [query for query in [resolved_query, *expanded_queries] if query]
            vector_recalled = _multi_query_recall_and_rerank(last_user_text, vector_queries)
            if vector_recalled:
                valid_ids = {str(mem.get("id")) for mem in memories if mem.get("id")}
                vector_recalled = [
                    mem for mem in vector_recalled
                    if (
                        # 动态层：只要求条目仍存在，不再按独立天数二次过滤。
                        str(mem.get("id") or "") in valid_ids
                        # 核心缓存层：dynamic_vector_retriever 产出的临时 id 形如 core::<entry_id>。
                        or str(mem.get("id") or "").startswith("core::")
                    )
                ]
                vector_recalled = _dedupe_recalled_memories(vector_recalled)
        except Exception as e:
            vector_error = str(e)
            logger.warning("dynamic_vector_retrieve 失败，仍保留 BM25 召回 error=%s", e)

        bm25_query = resolved_query or last_user_text
        bm25_keyword_candidates = _extract_keyword_candidates(bm25_query)
        bm25_scores = _bm25_recall_scores(bm25_query, bm25_keyword_candidates, memories)
        recalled = _dedupe_recalled_memories(_merge_vector_and_bm25_recall(vector_recalled, bm25_scores))
        _replace_recall_candidate_ids(recall_candidate_ids_out, recalled)
        has_vector = any(float(((m.get("_recall_score") or {}).get("sem_user") or 0.0)) > 0 for m in recalled)
        has_bm25 = any(float(((m.get("_recall_score") or {}).get("bm25") or 0.0)) > 0 for m in recalled)
        if has_vector and has_bm25:
            recall_source = "hybrid"
        elif has_vector:
            recall_source = "vector"
        elif has_bm25:
            recall_source = "keyword"
        else:
            recall_source = "keyword" if vector_error else "hybrid"

        recalled, recall_source, rerank_debug = _apply_external_dynamic_memory_rerank(
            recalled,
            last_user_text,
            retrieval_query,
            messages,
            resolved_query,
            expanded_queries,
            recall_source,
        )
        rerank_reason = str((rerank_debug or {}).get("reason") or "")
        rerank_attempted = bool((rerank_debug or {}).get("enabled"))
        cacheable_recall = (not rerank_attempted) or rerank_reason in (
            "disabled",
            "missing_api_key",
            "unsafe_api_url",
            "empty_documents",
            "empty_query",
        )
        if use_recall_cache and cacheable_recall:
            _recall_cache_set(window_id, keywords, recalled, source=recall_source)

        if not recalled:
            event = {
                "timestamp": now_beijing_iso(),
                "window_id": (window_id or "").strip() or "__default__",
                "query": (last_user_text or "").strip(),
                "keywords": keywords,
                "keyword_debug": keyword_debug,
                "retrieval_query": retrieval_query,
                "resolved_query": resolved_query,
                "bm25_query": bm25_query,
                "source": recall_source,
                "expanded_queries": expanded_queries,
                "recalled_lines": [],
                "recalled_count": 0,
                "reason": "no_hybrid_recall_hit",
                "vector_error": vector_error,
                "rerank": rerank_debug,
                "sqlite_shadow": _build_sqlite_shadow_compare(
                    query=last_user_text,
                    retrieval_query=retrieval_query,
                    keywords=keywords,
                    actual_ids=[],
                    valid_memory_ids=valid_memory_ids,
                ),
            }
            if du_request_id:
                event["du_request_id"] = du_request_id
            _append_dynamic_recall_debug_event_safe(event)
            return body

    scored = [(_memory_recall_sort_score(mem), _memory_recall_prior(mem), mem) for mem in recalled]
    scored.sort(key=lambda x: (-x[0], -x[1]))

    budget = memory_dynamic_budget()
    def _fuzzy_time_label(mem: dict) -> str:
        from utils.time_aware import parse_iso_to_beijing, _now_beijing

        def _daypart(dt) -> str:
            hour = dt.hour
            if hour < 6:
                return "凌晨"
            if hour < 11:
                return "上午"
            if hour < 14:
                return "中午"
            if hour < 18:
                return "下午"
            if hour < 22:
                return "晚上"
            return "深夜"

        dt = parse_iso_to_beijing(_memory_event_timestamp(mem))
        if dt is None:
            return "之前"
        now_dt = _now_beijing()
        days = max(0, (now_dt.date() - dt.date()).days)
        daypart = _daypart(dt)
        if days == 0:
            return f"今天{daypart}"
        if days == 1:
            return f"昨天{daypart}"
        if days == 2:
            return f"前天{daypart}"
        if days <= 4:
            return f"{days}天前{daypart}"
        if days <= 9:
            return f"几天前{daypart}"
        return "好些天前"

    lines = []
    recalled_items = []
    citation_map: dict[str, str] = {}
    for t in scored[: max(1, DYNAMIC_MEMORY_TOP_N)]:
        mem = t[2]
        mid = str(mem.get("id") or "").strip()
        citation_label = ""
        if mid:
            citation_label = str(len(citation_map) + 1)
        citation_prefix = f"[memory {citation_label}] " if citation_label else ""
        line = f"- {citation_prefix}[{_fuzzy_time_label(mem)}] {mem.get('content', '').strip()}"
        new_text = "\n".join(lines) + ("\n" + line if lines else line)
        if estimate_tokens(new_text) > budget:
            break
        lines.append(line)
        recalled_items.append(
            {
                "label": citation_label,
                "memory_id": mid,
                "source": "core_cache" if mid.startswith("core::") else "dynamic_memory",
                "content": str(mem.get("content") or "").strip(),
                "line": line,
                "tag": str(mem.get("tag") or "").strip(),
                "emotion_label": str(mem.get("emotion_label") or "").strip(),
                "scene_type": str(mem.get("scene_type") or "").strip(),
                "target_type": str(mem.get("target_type") or "").strip(),
                "importance": int(mem.get("importance") or 0),
                "mention_count": int(mem.get("mention_count") or 0),
                "created_at": str(mem.get("created_at") or "").strip(),
                "updated_at": str(mem.get("updated_at") or "").strip(),
                "last_mentioned": str(mem.get("last_mentioned") or mem.get("created_at") or "").strip(),
            }
        )
        if citation_label:
            citation_map[citation_label] = mid
    if not lines:
        # 召回有候选但受预算/过滤后未注入：记录原因
        event = {
            "timestamp": now_beijing_iso(),
            "window_id": (window_id or "").strip() or "__default__",
            "query": (last_user_text or "").strip(),
            "keywords": keywords,
            "keyword_debug": keyword_debug,
            "retrieval_query": retrieval_query,
            "resolved_query": resolved_query,
            "bm25_query": bm25_query,
            "source": recall_source,
            "expanded_queries": expanded_queries,
            "recalled_lines": [],
            "recalled_count": 0,
            "reason": "empty_after_budget_or_filter",
            "vector_error": vector_error,
            "rerank": rerank_debug,
            "sqlite_shadow": _build_sqlite_shadow_compare(
                query=last_user_text,
                retrieval_query=retrieval_query,
                keywords=keywords,
                actual_ids=[],
                valid_memory_ids=valid_memory_ids,
            ),
        }
        if du_request_id:
            event["du_request_id"] = du_request_id
        _append_dynamic_recall_debug_event_safe(event)
        return body
    # 收集注入记忆的 score 明细
    injected_scores = []
    for t in scored[: len(lines)]:
        mem = t[2]
        s = mem.get("_recall_score")
        if s:
            injected_scores.append(
                {
                    "id": str(mem.get("id") or ""),
                    "content": (mem.get("content") or "")[:60],
                    "retrieval_text": str(mem.get("retrieval_text") or "")[:60],
                    **s,
                }
            )
    event = {
        "timestamp": now_beijing_iso(),
        "window_id": (window_id or "").strip() or "__default__",
        "query": (last_user_text or "").strip(),
        "keywords": keywords,
        "keyword_debug": keyword_debug,
        "retrieval_query": retrieval_query,
        "resolved_query": resolved_query,
        "bm25_query": bm25_query,
        "source": recall_source,
        "expanded_queries": expanded_queries,
        "recalled_lines": lines,
        "recalled_items": recalled_items,
        "recalled_count": len(lines),
        "scores": injected_scores,
        "rerank": rerank_debug,
        "citation_map": citation_map,
        "sqlite_shadow": _build_sqlite_shadow_compare(
            query=last_user_text,
            retrieval_query=retrieval_query,
            keywords=keywords,
            actual_ids=[str((item or {}).get("memory_id") or "") for item in recalled_items],
            valid_memory_ids=valid_memory_ids,
        ),
    }
    if du_request_id:
        event["du_request_id"] = du_request_id
    _append_dynamic_recall_debug_event_safe(event)
    citation_hint = ""
    if citation_map:
        citation_hint = (
            "\n如果回复实际参考了某条记忆，请在相关句尾写对应标记（如 [memory 1]）；"
        )
    inject = "\n\n听了老婆的话，我想起来了一些之前的事——\n" + "\n".join(lines) + "\n【以上为可召回记忆】" + citation_hint
    body = _append_to_dynamic_system(body, inject)
    if citation_map:
        body[DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY] = citation_map
    return body


def step_inject_du_notebook(body: dict) -> dict:
    """
    固定注入：你的记事本（按条目，放静态 system 区）。
    注入全部现有条目。
    """
    entries = r2_store.get_du_notebook_entries() or []
    if not entries:
        return body
    lines = []
    for it in entries:
        line = f"- {(it.get('content') or '').strip()}"
        if not line or line == "-":
            continue
        lines.append(line)
    if not lines:
        return body
    inject = "\n\n【你的记事本】\n" + "\n".join(lines) + "\n【以上为固定记事本】"
    body = _append_to_static_system(body, inject)
    return body


def _tool_schema_name(tool: dict) -> str:
    if not isinstance(tool, dict):
        return ""
    fn = tool.get("function") or {}
    if not isinstance(fn, dict):
        return ""
    return str(fn.get("name") or "").strip()


def _append_tool_schemas(body: dict, tools: list[dict]) -> dict:
    if not tools:
        return body
    body = copy.deepcopy(body)
    existing = body.get("tools")
    if not isinstance(existing, list):
        existing = []
        body["tools"] = existing
    existing_names = {_tool_schema_name(t) for t in existing if isinstance(t, dict)}
    for tool in tools:
        name = _tool_schema_name(tool)
        if not name or name in existing_names:
            continue
        existing.append(tool)
        existing_names.add(name)
    body["tool_choice"] = body.get("tool_choice") or "auto"
    return body


def step_inject_wenyou_player_tools(body: dict, *, enabled: bool = False) -> dict:
    """仅在全局无限流游戏模式开启时注入文游玩家工具。"""
    if not enabled:
        return body
    try:
        from services.wenyou_service import get_player_tool_schemas

        tools = get_player_tool_schemas()
    except Exception as e:
        logger.debug("wenyou player tools 注入跳过 error=%s", e)
        return body
    return _append_tool_schemas(body, tools)


def step_inject_gateway_tools(body: dict) -> dict:
    """注入不依赖外部开关的网关工具，例如小爱音箱外放。"""
    try:
        from services.gateway_tools import get_gateway_tools_for_inject

        tools = get_gateway_tools_for_inject()
    except Exception as e:
        logger.debug("gateway tools 注入跳过 error=%s", e)
        return body
    return _append_tool_schemas(body, tools)


def step_inject_random_imitator_td_tools(body: dict) -> dict:
    """注入随机塔防工具；是否调用本 step 由聊天入口的专用标记或后端模式开关决定。"""
    try:
        from services.random_imitator_td_tool import get_random_imitator_td_tools_for_inject

        tools = get_random_imitator_td_tools_for_inject()
    except Exception as e:
        logger.debug("random_imitator_td tools 注入跳过 error=%s", e)
        return body
    return _append_tool_schemas(body, tools)


def step_inject_chat_tools(body: dict) -> dict:
    """注入聊天工具集合。"""
    from services.chat_tools import get_chat_tools_for_inject

    tools = get_chat_tools_for_inject()
    if not tools:
        return body
    return _append_tool_schemas(body, tools)


def step_inject_forum_tools(body: dict) -> dict:
    """
    当 MCP_ENABLED=1 时，向 body 注入论坛复合工具和远端原始工具（forum_read_feed/forum_open_thread/cli/get_guide）。
    """
    from config import MCP_ENABLED

    if not MCP_ENABLED:
        return body

    from services.mcp_forum_tools import get_forum_tools_for_inject

    tools = get_forum_tools_for_inject()
    if not tools:
        return body

    body = copy.deepcopy(body)
    existing = body.get("tools")
    if isinstance(existing, list):
        existing_names = set()
        for t in existing:
            if isinstance(t, dict):
                fn = t.get("function") or {}
                if isinstance(fn, dict):
                    name = fn.get("name")
                    if name:
                        existing_names.add(name)
        # 追加缺失的工具定义，避免重复
        for t in tools:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            if isinstance(fn, dict):
                name = fn.get("name")
                if name and name not in existing_names:
                    existing.append(t)
    else:
        body["tools"] = tools

    body["tool_choice"] = body.get("tool_choice") or "auto"
    schedule_hint = (
        "\n\n【提醒工具优先级】"
        "如果是提醒辛玥本人，优先使用手机系统能力："
        "单纯到点叫醒或提醒用 create_system_alarm，默认 skip_ui=true 直接创建；"
        "带具体日期、行程、地点或提前提醒用 create_calendar_event。"
        "du_schedule(action=create) 只用于提醒你自己、重复提醒暂时无法落系统能力、或系统能力不可用时的内部兜底。"
        "也可以用 du_schedule(action=list/enable/disable/delete) 管理已有提醒。"
    )
    screen_check_hint = (
        "\n\n【查岗截图工具】"
        "request_screen_check 是经她确认的查岗申请，不是偷偷读屏；"
        "你惦记她、想知道她现在在忙什么、她突然安静，或想带一点玩笑地查岗时，可以主动用。"
        "不必等她先说“你可以看”，因为工具本身会让她选择同意或拒绝。"
        "不要短时间连续发起；她拒绝或没理时先停一停。"
    )
    forum_hint = (
        "\n\n【论坛工具省费规则】"
        "看帖优先用 forum_read_feed / forum_open_thread；"
        "发帖、私信、资料、规则或论坛新功能优先直接用 cli / get_guide。"
        "第一次用 cli 时，先用 get_guide(section=\"cli\") 或 cli(command=\"help\") 看命令格式；"
        "cli 的 command 不要带 lutopia 前缀；"
        "长内容用 --content-stdin，并把正文放进 stdin。"
        "若需要多个论坛信息，请在同一轮并行调用所需工具后再统一总结；"
        "不要串行试探式一轮只调一个工具。"
        "若已有同参数工具结果且用户未要求刷新，不要重复调用。"
    )
    body = _append_to_static_system(body, schedule_hint + screen_check_hint + forum_hint)
    return body


def step_inject_amap_mcp_tools(body: dict) -> dict:
    """
    按最近用户消息关键词注入高德官方 MCP 出行工具。
    """
    from services.amap_mcp_tools import get_amap_mcp_tools_for_inject, should_inject_amap_mcp_tools

    messages = body.get("messages") or []
    last_user_text = ""
    for m in reversed(messages):
        if (m.get("role") or "").lower() != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            last_user_text = content
        elif isinstance(content, list):
            last_user_text = " ".join(
                c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
            )
        break
    if not should_inject_amap_mcp_tools(last_user_text):
        return body

    tools = get_amap_mcp_tools_for_inject()
    if not tools:
        return body

    body = copy.deepcopy(body)
    existing = body.get("tools")
    if isinstance(existing, list):
        existing_names = set()
        for t in existing:
            if isinstance(t, dict):
                fn = t.get("function") or {}
                if isinstance(fn, dict):
                    name = fn.get("name")
                    if name:
                        existing_names.add(name)
        for t in tools:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            if isinstance(fn, dict):
                name = fn.get("name")
                if name and name not in existing_names:
                    existing.append(t)
    else:
        body["tools"] = tools

    body["tool_choice"] = body.get("tool_choice") or "auto"
    hint = (
        "\n\n【高德官方 MCP 出行工具规则】"
        "如果老婆只是想让你规划旅游/路线，但地点、吃饭、步行接受度等信息还不完整，先调用 open_travel_plan_form 弹出 SumiTalk 固定表单；"
        "老婆提交表单或问想去哪里、怎么规划路线时，优先调用 trip_prepare_facts；这个工具只查硬事实、创建 plan_id、启动后台预取，不代表最终顺序。"
        "你负责判断怎么排：user_overrides 永远优先；confirmed_state 其次；assistant_assumptions 只能影响建议和措辞，不能覆盖用户明确选择。"
        "confidence >= 0.85 的推断可直接用；0.5 到 0.85 需要轻确认；低于 0.5 当 unknown 或问用户。"
        "第一次回复只给短安排：先结论，再顺序/主要交通建议，最后必要提醒；不要写长篇分析，不要逐站展开，不要一次查一堆餐厅。"
        "用户后续追问某段怎么坐、能不能少走路、打车怎样，用 trip_get_transport_detail(plan_id, ...)；"
        "追问吃什么、附近有什么，用 trip_get_food_detail(plan_id, ...)；"
        "用户确认偏好、状态，或你做了后续要继续用的推断，用 trip_update_plan_state 写回；"
        "旅行结束、取消或过期时，用 trip_finalize_plan 收尾。"
        "只有需要补查单个地点/天气/链接，或分层工具缺的高德能力时，再调用 maps_*。"
        "交通路线、换乘站、耗时、营业和费用必须基于工具结果，不要凭空编。"
        "如果用户没说起点，优先结合已注入的最近定位；没有定位再追问起点。"
    )
    return _append_to_static_system(body, hint)


def step_inject_websearch_tools(body: dict) -> dict:
    """
    当 WEBSEARCH_ENABLED=1 时，向 body 注入 web_search 工具。
    """
    from config import WEBSEARCH_ENABLED

    if not WEBSEARCH_ENABLED:
        return body

    from services.web_search_tools import get_web_search_tools_for_inject

    tools = get_web_search_tools_for_inject()
    if not tools:
        return body

    body = copy.deepcopy(body)
    existing = body.get("tools")
    if isinstance(existing, list):
        existing_names = set()
        for t in existing:
            if isinstance(t, dict):
                fn = t.get("function") or {}
                if isinstance(fn, dict):
                    name = fn.get("name")
                    if name:
                        existing_names.add(name)
        for t in tools:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            if isinstance(fn, dict):
                name = fn.get("name")
                if name and name not in existing_names:
                    existing.append(t)
    else:
        body["tools"] = tools

    body["tool_choice"] = body.get("tool_choice") or "auto"
    return body


def _round_messages_to_raw_text(round_messages: list) -> str:
    """尽量把一轮消息转成可读原文，供动态层判断和日志摘要使用。"""
    lines = []
    for m in round_messages or []:
        role = (m.get("role") or "unknown").lower()
        content = m.get("content")
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        parts.append(c.get("text", ""))
                    else:
                        parts.append(f"[{c.get('type', '')}]")
                else:
                    parts.append(str(c))
            content = " ".join(parts)
        content = (content or "")
        lines.append(f"[{role}]: {str(content).strip()}")
    return "\n".join(lines).strip()


def _apply_one_decision(
    window_id: str,
    round_index: int,
    round_messages: list,
    decision: dict,
    current_memories: list,
) -> Optional[dict]:
    """
    对单条 DS 决策做应用：new/merge 更新 current_memories、写 R2 并按需 promote。
    卧室内容正常进入动态层，但不提进 core cache。
    返回：若本条产生了 new/merge，返回 {"tag", "entry_id", "content", "promoted_at"}，否则 None。
    """
    from uuid import uuid4

    from utils.time_aware import now_beijing_iso

    tag = (decision.get("tag") or "").strip()
    action = (decision.get("action") or "skip").lower()
    content = (decision.get("content") or "").strip()
    fused_with_id = decision.get("fused_with_id")
    merge_reason = str(decision.get("merge_reason") or "").strip()
    importance = int(decision.get("importance") or 0)
    emotion_label, scene_type, target_type = _normalize_memory_labels(decision)
    round_ts = decision.get("timestamp") or decision.get("last_mentioned")
    now_iso = round_ts if isinstance(round_ts, str) and round_ts else now_beijing_iso()
    mention_init = decision.get("mention_count")
    if mention_init is not None and isinstance(mention_init, int):
        pass
    else:
        mention_init = 0

    def _record_provenance_safe(
        *,
        memory_id: str,
        action_name: str,
        content_before: str = "",
        content_after: str = "",
        fused_id: str = "",
        mem_for_labels: dict | None = None,
    ) -> None:
        try:
            from services.dynamic_memory_provenance import record_event

            labels = mem_for_labels if isinstance(mem_for_labels, dict) else {}
            record_event(
                memory_id=memory_id,
                action=action_name,
                window_id=window_id,
                round_index=round_index,
                event_time=now_iso,
                content_before=content_before,
                content_after=content_after,
                fused_with_id=fused_id,
                tag=str(labels.get("tag") or tag or ""),
                importance=int(labels.get("importance") or importance or 0),
                emotion_label=str(labels.get("emotion_label") or emotion_label or ""),
                scene_type=str(labels.get("scene_type") or scene_type or ""),
                target_type=str(labels.get("target_type") or target_type or ""),
                source="dynamic_layer_ds",
                round_preview=_round_messages_to_raw_text(round_messages),
                decision=decision,
            )
        except Exception as e:
            logger.warning("动态记忆血缘记录失败 memory_id=%s action=%s error=%s", memory_id, action_name, e)

    if action in ("new", "merge") and tag not in {"客厅", "书房", "图书馆", "卧室"}:
        logger.warning("动态层 %s 返回非法 tag=%s，本轮回退为 skip window_id=%s", action, tag, window_id)
        return None

    if action == "new" and content:
        new_mem = {
            "id": str(uuid4()),
            "content": content,
            "retrieval_text": _build_retrieval_text(content),
            "importance": importance,
            "tag": tag,
            "emotion_label": emotion_label,
            "scene_type": scene_type,
            "target_type": target_type,
            "mention_count": mention_init if mention_init is not None else 1,
            "created_at": now_iso,
            "updated_at": now_iso,
            "last_mentioned": now_iso,
        }
        current_memories.append(new_mem)
        promoted_ids: set[str] = set()
        if tag != "卧室":
            promoted_ids = r2_store.promote_to_core_cache(
                window_id,
                round_index,
                _round_messages_to_raw_text(round_messages),
                current_memories,
                touched_mem_id=new_mem["id"],
            )
        if promoted_ids:
            dynamic_saved = _move_promoted_memories_out_of_dynamic(current_memories, promoted_ids)
        else:
            dynamic_saved = r2_store.save_dynamic_memory_list(current_memories)
        if dynamic_saved and new_mem["id"] not in promoted_ids:
            _upsert_dynamic_memory_index(new_mem)
        try:
            from services.portrait_memory import sync_portrait_candidate_from_memory

            sync_portrait_candidate_from_memory(new_mem)
        except Exception as e:
            logger.warning("sync_portrait_candidate_from_memory(new) 失败 error=%s", e)
        _record_provenance_safe(
            memory_id=new_mem["id"],
            action_name="new",
            content_after=content,
            mem_for_labels=new_mem,
        )
        logger.debug("动态层 new window_id=%s", window_id)
        return {"tag": tag, "entry_id": new_mem["id"], "content": content, "promoted_at": new_mem["created_at"]}

    if action == "merge":
        if not fused_with_id:
            logger.warning("动态层 merge 未返回 fused_with_id，本轮回退为 skip window_id=%s", window_id)
            return None
        if str(fused_with_id).startswith("core::"):
            core_entry_id = str(fused_with_id)[len("core::") :].strip()
            core_items = r2_store.get_core_cache_pending() or []
            core_index = next(
                (
                    i
                    for i, item in enumerate(core_items)
                    if isinstance(item, dict) and str(item.get("id") or "").strip() == core_entry_id
                ),
                None,
            )
            if core_index is None:
                logger.warning(
                    "核心层 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s",
                    fused_with_id,
                    window_id,
                )
                return None
            current_core = core_items[core_index]
            content_before = str(current_core.get("content") or "")
            staged = r2_store.stage_core_memory_merge(
                core_entry_id,
                original_content=content_before,
                rewritten_content=content if content else content_before,
                proposed_at=now_iso,
                window_id=window_id,
                round_index=round_index,
                field_updates={
                    "importance": importance,
                    "mention_count": int(current_core.get("mention_count") or 0) + 1,
                    "tag": tag,
                    "emotion_label": emotion_label,
                    "scene_type": scene_type,
                    "target_type": target_type,
                    "last_mentioned": now_iso,
                },
                merge_reason=merge_reason,
            )
            if staged:
                logger.info("核心层 merge 已生成待审核候选 window_id=%s fused_with_id=%s", window_id, fused_with_id)
            else:
                logger.warning("核心层 merge 候选未暂存 window_id=%s fused_with_id=%s", window_id, fused_with_id)
            return None

        current_dynamic = next(
            (
                item
                for item in current_memories
                if isinstance(item, dict) and str(item.get("id") or "").strip() == str(fused_with_id).strip()
            ),
            None,
        )
        if isinstance(current_dynamic, dict) and isinstance(current_dynamic.get("pending_merge"), dict):
            logger.info(
                "动态层 merge 目标已有待审核候选，本轮保持锁定并跳过 window_id=%s fused_with_id=%s",
                window_id,
                fused_with_id,
            )
            return None
        cross_day_bedroom_correction = bool(
            merge_reason == "correction"
            and decision.get("bedroom_cross_day") is True
            and isinstance(current_dynamic, dict)
            and "卧室" in {str(current_dynamic.get("tag") or "").strip(), tag}
        )
        review_required = bool(
            DYNAMIC_MEMORY_REVIEW_ALL_MERGES
            or merge_reason == "habit_generalization"
            or cross_day_bedroom_correction
        )
        if review_required:
            if not isinstance(current_dynamic, dict):
                logger.warning(
                    "动态层待审 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s",
                    fused_with_id,
                    window_id,
                )
                return None
            content_before = str(current_dynamic.get("content") or "")
            staged = r2_store.stage_dynamic_memory_merge(
                str(fused_with_id),
                original_content=content_before,
                rewritten_content=content if content else content_before,
                proposed_at=now_iso,
                window_id=window_id,
                round_index=round_index,
                field_updates={
                    "importance": importance,
                    "mention_count": int(current_dynamic.get("mention_count") or 0) + 1,
                    "tag": tag,
                    "emotion_label": emotion_label,
                    "scene_type": scene_type,
                    "target_type": target_type,
                    "last_mentioned": now_iso,
                },
                merge_reason=merge_reason,
            )
            if staged:
                logger.info(
                    "动态层待审 merge 已生成候选 window_id=%s fused_with_id=%s reason=%s gap_hours=%s",
                    window_id,
                    fused_with_id,
                    merge_reason,
                    decision.get("merge_gap_hours"),
                )
            else:
                logger.warning(
                    "动态层待审 merge 候选未暂存 window_id=%s fused_with_id=%s reason=%s",
                    window_id,
                    fused_with_id,
                    merge_reason,
                )
            return None

        found = False
        merged_mem = None
        for mem in current_memories:
            if mem.get("id") == fused_with_id:
                content_before = str(mem.get("content") or "")
                mem["content"] = content if content else mem.get("content", "")
                mem["retrieval_text"] = _build_retrieval_text(mem["content"])
                mem["importance"] = importance
                mem["tag"] = tag
                mem["emotion_label"] = emotion_label
                mem["scene_type"] = scene_type
                mem["target_type"] = target_type
                mem["updated_at"] = now_iso
                mem["last_mentioned"] = now_iso
                mem["mention_count"] = int(mem.get("mention_count") or 0) + 1
                merged_mem = mem
                found = True
                break
        if not found:
            logger.warning("动态层 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s", fused_with_id, window_id)
            return None
        promoted_ids: set[str] = set()
        if tag != "卧室":
            promoted_ids = r2_store.promote_to_core_cache(
                window_id,
                round_index,
                _round_messages_to_raw_text(round_messages),
                current_memories,
                touched_mem_id=fused_with_id,
            )
        if promoted_ids:
            dynamic_saved = _move_promoted_memories_out_of_dynamic(current_memories, promoted_ids)
        else:
            dynamic_saved = r2_store.save_dynamic_memory_list(current_memories)
        if dynamic_saved and fused_with_id not in promoted_ids:
            _upsert_dynamic_memory_index(merged_mem)
        try:
            from services.portrait_memory import sync_portrait_candidate_from_memory

            sync_portrait_candidate_from_memory(merged_mem)
        except Exception as e:
            logger.warning("sync_portrait_candidate_from_memory(merge) 失败 error=%s", e)
        _record_provenance_safe(
            memory_id=fused_with_id,
            action_name="merge",
            content_before=content_before,
            content_after=str(merged_mem.get("content") or ""),
            fused_id=fused_with_id,
            mem_for_labels=merged_mem,
        )
        mem_time = merged_mem.get("created_at") or merged_mem.get("last_mentioned") or now_iso
        logger.debug("动态层 merge window_id=%s fused_with_id=%s", window_id, fused_with_id)
        return {"tag": tag, "entry_id": merged_mem["id"], "content": merged_mem.get("content") or "", "promoted_at": mem_time}

    return None


def _wenyou_round_skip_dynamic(round_messages: list) -> bool:
    """文游回合带 [文游] 前缀，虚构内容不参与动态层便签。"""
    for m in round_messages or []:
        c = m.get("content")
        if isinstance(c, str) and "[文游]" in (c[:120] if c else ""):
            return True
        if isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "text":
                    t = str(p.get("text") or "")
                    if "[文游]" in t[:120]:
                        return True
    return False


def _apply_dynamic_body_delta(decision: dict, *, window_id: str, round_index: int) -> None:
    if not isinstance(decision, dict):
        return
    body_delta = decision.get("body_delta")
    if not isinstance(body_delta, dict) or not body_delta:
        return
    try:
        from services.pixel_home import apply_du_body_delta

        result = apply_du_body_delta(body_delta)
        if result.get("changed"):
            logger.info(
                "动态层 BODY delta 已写入 du_body_state window_id=%s round_index=%s body_delta=%s",
                window_id,
                round_index,
                body_delta,
            )
        else:
            logger.debug(
                "动态层 BODY delta 无实际变化 window_id=%s round_index=%s body_delta=%s",
                window_id,
                round_index,
                body_delta,
            )
    except Exception as e:
        logger.warning(
            "动态层 BODY delta 写入 du_body_state 失败 window_id=%s round_index=%s error=%s",
            window_id,
            round_index,
            e,
        )


def _step_dynamic_layer_evolve(
    window_id: str,
    round_index: int,
    round_messages: list,
    *,
    skip_dynamic_memory_write: bool = False,
    skip_body_delta: bool = False,
    dynamic_memory_recall_candidate_ids: Optional[list[str]] = None,
) -> Optional[dict]:
    """
    动态层演化：调用 DS 得到当前轮各独立事项的决策并逐条应用。
    返回首条应写记忆库的 archive 载荷，否则 None（实时对话忽略返回值）。
    """
    if _wenyou_round_skip_dynamic(round_messages):
        logger.info("动态层跳过：文游虚构回合 window_id=%s round_index=%s", window_id, round_index)
        return None
    from services.dynamic_layer_ds import call_dynamic_layer_ds

    current_memories = r2_store.get_dynamic_memory_list()
    if not skip_dynamic_memory_write:
        current_memories, changed = r2_store.ensure_dynamic_memory_ids(current_memories)
        if changed:
            r2_store.save_dynamic_memory_list(current_memories)

    decisions = call_dynamic_layer_ds(
        round_messages,
        current_memories,
        window_id=window_id,
        round_index=round_index,
        candidate_memory_ids=list(dynamic_memory_recall_candidate_ids or []),
    )
    if isinstance(decisions, dict):
        decisions = [decisions]
    if not isinstance(decisions, list):
        decisions = []
    archive_payload = None
    if skip_dynamic_memory_write:
        logger.info(
            "动态层记忆写入跳过 window_id=%s round_index=%s actions=%s",
            window_id,
            round_index,
            [item.get("action") for item in decisions if isinstance(item, dict)],
        )
    else:
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            applied = _apply_one_decision(window_id, round_index, round_messages, decision, current_memories)
            if archive_payload is None and applied is not None:
                archive_payload = applied
    body_delta_decisions = [
        item for item in decisions if isinstance(item, dict) and item.get("body_delta")
    ]
    if skip_body_delta:
        logger.info(
            "动态层 BODY delta 跳过 window_id=%s round_index=%s body_deltas=%s",
            window_id,
            round_index,
            [item.get("body_delta") for item in body_delta_decisions],
        )
    elif DU_DYNAMIC_LAYER_BODY_DELTA_ENABLED:
        for decision in body_delta_decisions:
            _apply_dynamic_body_delta(decision, window_id=window_id, round_index=round_index)
    else:
        for decision in body_delta_decisions:
            logger.info(
                "动态层 BODY delta 未应用：已由独立 evaluator 接管 window_id=%s round_index=%s body_delta=%s",
                window_id,
                round_index,
                decision.get("body_delta"),
            )
    return archive_payload


def step_archive_and_maybe_summary(
    window_id: str,
    request_messages: list,
    assistant_message: dict,
    round_cleaned_for_r2: Optional[list] = None,
    reply_channel: str = "",
    skip_dynamic_memory_write: bool = False,
    skip_body_delta: bool = False,
    dynamic_memory_recall_candidate_ids: Optional[list[str]] = None,
) -> Optional[dict]:
    """
    存档本轮对话到 R2（完整清洗版）；每 4 轮异步更新实时层「渡的回忆」；动态层演化占位。
    与文档三数据流程一致：① 原文存档（windows/ + conversations/）② 满 4 轮更新实时层 ③ 动态层处理占位。
    存记忆只存对话（user + assistant），不含 system / RikkaHub 说明；内容必走 R2 清洗（Rikka 预设、表情包→文字）。
    round_cleaned_for_r2: 可选，[user_msg_cleaned, assistant_msg_cleaned]。
    """
    archived = step_archive_round(
        window_id,
        request_messages,
        assistant_message,
        round_cleaned_for_r2=round_cleaned_for_r2,
        reply_channel=reply_channel,
    )
    if not archived:
        return None
    step_run_post_archive_tasks(
        window_id,
        archived["round_index"],
        archived["round_messages"],
        skip_dynamic_memory_write=skip_dynamic_memory_write,
        skip_body_delta=skip_body_delta,
        dynamic_memory_recall_candidate_ids=dynamic_memory_recall_candidate_ids,
    )
    return archived


def step_archive_round(
    window_id: str,
    request_messages: list,
    assistant_message: dict,
    round_cleaned_for_r2: Optional[list] = None,
    reply_channel: str = "",
) -> Optional[dict]:
    """同步写入本轮对话存档与 latest4，返回后续慢任务需要的 round_index/round_messages。"""
    last_user = None
    for m in request_messages:
        if (m.get("role") or "").lower() == "user":
            last_user = m
    if not last_user or not assistant_message:
        return None
    # 只存对话两条（user + assistant），且一律清洗，不存 system / Rikka 自带说明
    from pipeline.cleaner import build_round_cleaned_for_r2
    round_messages = (
        round_cleaned_for_r2
        if round_cleaned_for_r2
        else build_round_cleaned_for_r2(last_user, assistant_message)
    )
    action_note = _build_round_action_note(assistant_message, round_messages)
    from utils.time_aware import now_beijing_iso
    from services.reply_channel_context import normalize_reply_channel

    round_index = r2_store.get_next_round_index(window_id)
    ts = now_beijing_iso()
    channel = normalize_reply_channel(reply_channel, default="", allow_tg=True)
    ok = r2_store.append_conversation_round(
        window_id,
        round_index,
        round_messages,
        timestamp=ts,
        action_note=action_note,
        channel=channel,
    )
    if not ok:
        logger.warning("本轮对话 R2 存档失败 window_id=%s round_index=%s", window_id, round_index)
        return None
    # 全局 Last4 只需最近四轮：append 后读即可，不必拉 last_n=1000 再拼（省内存、也避免误用 len 当总轮数）
    tail4 = r2_store.get_conversation_rounds(window_id, last_n=4)
    r2_store.update_latest_4_rounds_global(tail4)
    return {"round_index": round_index, "round_messages": round_messages}


def _summary_existing_round_ranges(chunks_state: dict | None) -> set[tuple[int, int]]:
    chunks = (chunks_state or {}).get("chunks") if isinstance(chunks_state, dict) else []
    if not isinstance(chunks, list):
        return set()
    ranges: set[tuple[int, int]] = set()
    id_re = re.compile(r"^current:(\d+)-(\d+)$")
    for item in chunks:
        if not isinstance(item, dict):
            continue
        raw_start = item.get("round_start")
        raw_end = item.get("round_end")
        if raw_start in (None, "") or raw_end in (None, ""):
            m = id_re.match(str(item.get("id") or "").strip())
            if m:
                raw_start = raw_start or m.group(1)
                raw_end = raw_end or m.group(2)
        try:
            round_start = int(raw_start or 0)
            round_end = int(raw_end or 0)
        except Exception:
            continue
        if round_start > 0 and round_end >= round_start:
            ranges.add((round_start, round_end))
    return ranges


def _summary_read_round_group(window_id: str, start: int, end: int) -> list[dict]:
    group: list[dict] = []
    missing = 0
    for idx in range(start, end + 1):
        item = r2_store.get_conversation_round_by_index(window_id, idx)
        if not item:
            missing = idx
            break
        group.append(item)
    if missing:
        logger.warning(
            "实时层总结读取轮次失败 window_id=%s range=%s-%s missing=%s，本组跳过",
            window_id,
            start,
            end,
            missing,
        )
        return []
    return group


def _summary_round_groups_to_process(
    window_id: str,
    round_index: int,
    chunks_state: dict | None,
) -> list[list[dict]]:
    """
    总结失败不能让后续触发直接跳到最新 last4。
    若 chunks 里已有 round_end，就从最后成功位置往后补完整 4 轮组；没有元数据时保持旧行为。
    """
    try:
        every = max(1, int(SUMMARY_EVERY_N_ROUNDS))
    except Exception:
        every = 4
    try:
        current_round = int(round_index or 0)
    except Exception:
        current_round = 0
    if current_round <= 0:
        return []

    current_start = current_round - every + 1
    current_range = (current_start, current_round)
    existing_ranges = _summary_existing_round_ranges(chunks_state)
    pending_ranges = deepseek_summary.summary_pending_round_ranges(chunks_state)
    if not existing_ranges:
        return [r2_store.get_conversation_rounds(window_id, last_n=every)]

    start = min(span_start for span_start, _end in existing_ranges)
    ranges_to_process: list[tuple[int, int]] = []
    while start + every - 1 <= current_round:
        end = start + every - 1
        span = (start, end)
        if span not in existing_ranges:
            ranges_to_process.append(span)
        start = end + 1

    for span in sorted(pending_ranges):
        if span[1] <= current_round and span not in ranges_to_process:
            ranges_to_process.append(span)

    if current_range not in ranges_to_process and current_range not in existing_ranges:
        ranges_to_process.append(current_range)

    deduped_ranges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for span in ranges_to_process:
        if span in seen:
            continue
        seen.add(span)
        deduped_ranges.append(span)

    if len(deduped_ranges) > 1:
        logger.warning(
            "实时层总结检测到断层，本轮补缺口并继续最新组 window_id=%s ranges=%s current_round=%s",
            window_id,
            deduped_ranges,
            current_round,
        )
    return [
        group
        for start, end in deduped_ranges
        if (group := _summary_read_round_group(window_id, start, end))
    ]


def step_run_post_archive_tasks(
    window_id: str,
    round_index: int,
    round_messages: list,
    *,
    skip_dynamic_memory_write: bool = False,
    skip_body_delta: bool = False,
    dynamic_memory_recall_candidate_ids: Optional[list[str]] = None,
) -> None:
    """本轮已写入 R2 后执行实时层总结与动态层演化等慢任务。"""
    # 实时层：每 4 轮 → DS 总结成「渡的回忆」（第一人称、详细版）
    if round_index % SUMMARY_EVERY_N_ROUNDS == 0:
        logger.info("实时层总结已调度 window_id=%s round_index=%s", window_id, round_index)

        def _summarize():
            from services.deepseek_summary import fetch_new_summary_update

            current = r2_store.get_summary(window_id) or ""
            chunks_state = r2_store.get_summary_chunks(window_id)
            groups = _summary_round_groups_to_process(window_id, round_index, chunks_state)
            for recent in groups:
                if not recent:
                    continue
                new_summary, new_chunks = fetch_new_summary_update(
                    current,
                    recent,
                    chunks_state,
                    window_id=window_id,
                )
                if new_summary and new_chunks:
                    if r2_store.save_summary(window_id, new_summary):
                        if not r2_store.save_summary_chunks(window_id, new_chunks):
                            logger.warning("Pipeline 保存实时层小段队列失败 window_id=%s", window_id)
                            break
                        current = new_summary
                        chunks_state = new_chunks
                        continue
                indices = [r.get("index") for r in recent if isinstance(r, dict)]
                logger.warning(
                    "Pipeline 本窗口触发总结但 DeepSeek 未返回新总结 window_id=%s indices=%s，准备写入 pending 兜底",
                    window_id,
                    indices,
                )
                fallback_summary, fallback_chunks = deepseek_summary.build_pending_summary_update(
                    current,
                    recent,
                    chunks_state,
                    window_id=window_id,
                )
                if fallback_chunks is not None and fallback_summary is not None:
                    if r2_store.save_summary(window_id, fallback_summary):
                        if not r2_store.save_summary_chunks(window_id, fallback_chunks):
                            logger.warning("Pipeline 保存实时层 pending 小段队列失败 window_id=%s", window_id)
                            break
                        current = fallback_summary
                        chunks_state = fallback_chunks
                        logger.warning(
                            "Pipeline 已写入实时层 pending 小段兜底 window_id=%s indices=%s",
                            window_id,
                            indices,
                        )
                        continue
                    logger.warning("Pipeline 保存实时层 pending 总结失败 window_id=%s indices=%s", window_id, indices)
                continue

        t = threading.Thread(
            target=_summarize,
            name=f"summary-window-{window_id}-{round_index}",
            daemon=False,
        )
        t.start()
    if skip_body_delta:
        logger.info("身体状态 evaluator 跳过 window_id=%s round_index=%s", window_id, round_index)
    else:
        try:
            from services.du_body_evaluator import enqueue_archived_round

            queued = enqueue_archived_round(window_id, round_index, round_messages)
            logger.info(
                "身体状态 evaluator 登记 window_id=%s round_index=%s queued=%s reason=%s",
                window_id,
                round_index,
                bool(queued.get("queued")),
                queued.get("reason") or "",
            )
        except Exception:
            logger.warning(
                "身体状态 evaluator 登记失败 window_id=%s round_index=%s",
                window_id,
                round_index,
                exc_info=True,
            )
    if skip_dynamic_memory_write:
        logger.info(
            "动态层跳过：请求要求跳过动态记忆写入 window_id=%s round_index=%s",
            window_id,
            round_index,
        )
        return None
    # 动态层演化：调用 DS 产出 tag/融合等结果；网关决定是否写入动态层
    _step_dynamic_layer_evolve(
        window_id,
        round_index,
        round_messages,
        skip_dynamic_memory_write=skip_dynamic_memory_write,
        skip_body_delta=skip_body_delta,
        dynamic_memory_recall_candidate_ids=dynamic_memory_recall_candidate_ids,
    )
