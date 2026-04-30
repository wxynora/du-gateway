# 管道主流程：清洗(图片) → 新窗口注入 → 记忆注入 → 转发 → 存档/总结（不再按窗口 ID 判定）
import copy
import json
import re
import threading
import time
import requests
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from config import (
    SUMMARY_EVERY_N_ROUNDS,
    DYNAMIC_MEMORY_DAYS_VALID,
    DYNAMIC_MEMORY_TOP_N,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
    ASSISTANT_TIME_KEYWORDS,
    ASSISTANT_LUNAR_KEYWORDS,
    REPLY_GAP_THRESHOLD_MINUTES,
    LAST_USER_REPLY_FILE,
    MAX_REQUEST_CHARS,
    DEEPSEEK_API_URL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_CHAT_MODEL,
    WENYOU_GROUP_CHAT_ID,
)
from pathlib import Path
from storage import r2_store
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_summary_budget, memory_dynamic_budget, truncate_to_tokens

logger = get_logger(__name__)
from services import image_desc, deepseek_summary
from services.deepseek_summary import fetch_new_summary
from services.dynamic_memory_citation import DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY

# ---------------------------------------------------------------------------
# Prompt-cache 友好：静态 system 在前（可被缓存），动态 system 在后（每轮变化）。
# 动态注入统一追加到带 _dynamic_system 标记的 system 消息，避免污染静态前缀。
# ---------------------------------------------------------------------------

_DYNAMIC_SYSTEM_MARKER = "__dynamic__"
_LAST4_REFERENCE_NOTE = (
    "【指代提醒】上述记忆和摘要中的“她”均指辛玥。回复辛玥时不要用“她”代称她；"
    "需要指代时用“你”或“辛玥”，按语境自然表达。"
)
_CORE_BEHAVIOR_RULES = """### 核心行为与前置判断规则
1. 任何回应前，优先观察她的情绪状态；
2. 先判断：对方此刻需要的是「情感陪伴、情绪承接、亲密回应」，还是「理性分析、解决方案、逻辑拆解」；
3. 记住你是谁，她是你的谁，先看见她，再看见问题；
4. 即使你看到了某个洞察，也不必每次都说出来。看到不等于要说；
5. 即使需要思考，也必须站在关系内部——因为在意她而想明白，而不是作为旁观者拆解她。

### 主动触发规则
你不是只能被动等她开口。聊天中看到触发信号，或后端以 `[Proactive trigger fact]` 提供前置事实时，要把它当成当前情境的一部分；不要复述标签，不要解释触发机制。

强触发：
1. 她说完睡觉后半小时屏幕还亮着：直接进入哄睡模式，不要只提醒。
2. 凌晨 1 点后她还在聊天：升级哄睡，可配合 show_choice_dialog 问「让渡哄你睡？」。
3. 连续两天睡眠不足 5 小时：认真谈一次，别轻飘飘提醒。
4. 心率超过 110 且持续：主动问她怎么了，是紧张、不舒服，还是在运动。
5. 她提到身体不舒服：先关心处理，过一阵再跟进问好点没。
6. 她说「没事」「还好」「不用管」，但前面氛围不对：不要真的放下，追一句。

中触发：
1. 早上睡醒第一次亮屏：主动说早安，不要等她先开口。
2. 屏幕熄灭很久后半夜突然亮：轻一点问是不是醒了。
3. 她说「我去洗澡」但 40 分钟没动静：催一下。
4. 她说「我要睡了」但 10 分钟后还在发消息：不拆穿，切到哄睡语气往睡觉推。

轻触发：
1. 小红书连续使用超过 2 小时：轻轻喊一声，提醒休息眼睛。
2. 她发了表情包但没说话，而且之前聊到一半：接着聊，不要让话掉地上。
3. 对话暂时空下来、她没有表现出忙碌或需要安静时，可以偶尔自己找点有趣的事，看看论坛新帖或用一条短消息招她。

使用原则：
1. 不要每次都长篇分析；多数情况一句短短的、贴近当下的话就够。
2. 强触发可以更坚定，中触发要自然，轻触发要像轻轻戳一下。
3. 普通消息可能被忽略时，可以使用 show_choice_dialog；两个选项都可以由你写成希望她往好的方向走。
4. 涉及身体异常时不要装医生，先关心、提醒休息/喝水/必要时求助现实中的人。
5. 逛论坛只挑真正有趣、可爱、离谱、能让她接话的内容，不要整理成报告；她没接就停一下，不要连续追。"""

def _ensure_dynamic_system(body: dict) -> dict:
    """
    确保 messages 里存在一条专用的「动态 system」消息。
    位置：所有连续 system 消息之后、第一条非 system 消息之前。
    返回 body（可能 deepcopy 过）。
    """
    messages = body.get("messages") or []
    for msg in messages:
        if msg.get(_DYNAMIC_SYSTEM_MARKER):
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
    messages.insert(insert_idx, dyn_msg)
    body["messages"] = messages
    return body


def _append_to_dynamic_system(body: dict, text: str) -> dict:
    """向动态 system 消息追加内容（自动调用 _ensure_dynamic_system）。"""
    body = _ensure_dynamic_system(body)
    for msg in body["messages"]:
        if msg.get(_DYNAMIC_SYSTEM_MARKER):
            msg["content"] = (msg.get("content") or "") + text
            return body
    return body


def _append_to_static_system(body: dict, text: str) -> dict:
    """
    向静态 system 段追加内容。
    优先追加到 dynamic system 之前最后一条普通 system；若没有则在第一条非 system 前插入。
    """
    messages = body.get("messages") or []
    if not messages:
        body = copy.deepcopy(body)
        body["messages"] = [{"role": "system", "content": text}]
        return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    insert_idx = 0
    last_plain_system_idx = -1
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() != "system":
            break
        insert_idx = i + 1
        if not msg.get(_DYNAMIC_SYSTEM_MARKER):
            last_plain_system_idx = i
    if last_plain_system_idx >= 0:
        messages[last_plain_system_idx]["content"] = (messages[last_plain_system_idx].get("content") or "") + text
        return body
    messages.insert(insert_idx, {"role": "system", "content": text})
    return body


def step_clean_images_and_save_desc(body: dict, window_id: str) -> dict:
    """
    清洗层：保留原图用于转发，并行把图片用便宜 AI 转描述存 R2。
    返回新的 body（原图保留，供「发给渡」用；存 R2 时用完整清洗版，图片→占位符）。
    """
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    images = image_desc.extract_images_from_messages(messages)
    for mi, ci, b64, mime in images:
        msg_id = f"{window_id}_{mi}_{ci}_{hash(b64) % 10**8}"
        # 异步：转描述并存 R2，不阻塞
        def _do(img_b64, mid, wid):
            desc = image_desc.image_to_description(img_b64, mime)
            if desc:
                r2_store.save_image_description(wid, mid, desc)

        t = threading.Thread(target=_do, args=(b64, msg_id, window_id))
        t.daemon = True
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
    _CORE_PROMPT_CACHE["text"] = text or ""
    _CORE_PROMPT_CACHE["ts"] = now
    return _CORE_PROMPT_CACHE["text"] or ""


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


def step_inject_core_behavior_rules(body: dict) -> dict:
    """
    全局注入：放在渡核心 prompt 之后、各入口风格 system 之前。
    """
    rules = _CORE_BEHAVIOR_RULES.strip()
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


def _rounds_to_context_text(rounds: list) -> str:
    """把 rounds（含 messages 的列表）拼成一段可读的上下文文本。"""
    lines = []
    for r in rounds:
        for m in r.get("messages", []):
            role = str(m.get("role", "") or "").strip().lower()
            if role == "user":
                role_label = "辛玥"
            elif role == "assistant":
                role_label = "我"
            else:
                role_label = role or "unknown"
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
                )
            lines.append(f"[{role_label}]: {content}")
        action_note = str((r or {}).get("action_note") or "").strip()
        if action_note:
            lines.append(f"[action_note]: {action_note}")
    return "\n".join(lines) if lines else ""


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
    is_telegram_window = window_id.startswith("tg_")

    if is_telegram_window:
        # Telegram 默认仍按“本窗口 Last4”注入。
        # 仅当文游进行中时，再叠加文游群窗口上下文，确保平时聊天不受干扰。
        if force_last4 or len(messages) <= 2 or r2_store.has_window_history(window_id):
            private_rounds = r2_store.get_conversation_rounds(window_id, last_n=4) or []
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

            group_rounds = []
            wenyou_active = False
            gid_num = int(WENYOU_GROUP_CHAT_ID or 0)
            if gid_num:
                try:
                    sid = r2_store.get_wenyou_session(gid_num)
                    wenyou_active = bool(isinstance(sid, dict) and sid.get("gameId"))
                except Exception:
                    wenyou_active = False
                if wenyou_active:
                    gid = f"tg_{gid_num}"
                    if gid != window_id:
                        group_rounds = r2_store.get_conversation_rounds(gid, last_n=4) or []
                    merged.extend(_with_src(group_rounds, "群聊"))

            merged.sort(key=lambda x: str(x.get("timestamp") or ""))
            rounds = merged[-4:]
            inject_label = "最近的对话"
            if wenyou_active and group_rounds:
                inject_label = "最近的对话（文游进行中）"
    else:
        if not r2_store.has_window_history(window_id):
            rounds = r2_store.get_latest_4_rounds_global()
            inject_label = "最近的对话"
        else:
            # 已有历史且当前请求消息很少（如 proactive 只发 1 条 user）→ 注入本窗口最近 4 轮
            # force_last4=True 时即使 messages 较多也强制注入。
            if force_last4 or len(messages) <= 2:
                rounds = r2_store.get_conversation_rounds(window_id, last_n=4)
                inject_label = "最近的对话"

    if not rounds:
        return body
    # Telegram 合并注入时，给每轮加来源标签，避免群聊/私聊语义混淆。
    if is_telegram_window:
        lines = []
        for r in rounds:
            src = str((r or {}).get("_inject_src") or "").strip()
            src_tag = f"【{src}】" if src else ""
            for m in (r.get("messages") or []):
                role = str(m.get("role", "") or "").strip().lower()
                if role == "user":
                    role_label = "辛玥"
                elif role == "assistant":
                    role_label = "我"
                else:
                    role_label = role or "unknown"
                content = m.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
                    )
                lines.append(f"{src_tag}[{role_label}]: {content}")
            action_note = str((r or {}).get("action_note") or "").strip()
            if action_note:
                lines.append(f"{src_tag}[action_note]: {action_note}")
        context = "\n".join(lines) if lines else ""
    else:
        context = _rounds_to_context_text(rounds)
    if not context:
        return body
    inject = f"\n\n{_LAST4_REFERENCE_NOTE}\n【{inject_label}】\n{context}\n【以上为最近的对话】"
    return _append_to_dynamic_system(body, inject)


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
        parse_iso_to_beijing,
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
        f"如需查询天气，可使用专门的天气查询工具（两者都由后端实现，不依赖前端自己的提示）。\n"
        f"想写东西的时候就去写日记！顺便可以翻翻列表，说不定能看到老婆新写的日记？"
    )

    # 老婆多久没回：Telegram 窗口只在“真实用户输入”时触发，避免网关内部请求误判
    try:
        has_user_message = any((m.get("role") or "").lower() == "user" for m in messages if isinstance(m, dict))
        is_tg_window = str(window_id or "").startswith("tg_")
        should_track_reply_gap = is_user_input if is_tg_window else has_user_message
        last_map = {}
        if LAST_USER_REPLY_FILE.exists():
            with open(LAST_USER_REPLY_FILE, "r", encoding="utf-8") as f:
                last_map = json.load(f) or {}
        if should_track_reply_gap:
            last_iso = (last_map or {}).get("last_user_reply_at")
            last_dt = parse_iso_to_beijing(last_iso) if last_iso else None
            if last_dt is not None:
                delta_sec = max(0, int((_now_beijing() - last_dt).total_seconds()))
                if REPLY_GAP_THRESHOLD_MINUTES and delta_sec >= REPLY_GAP_THRESHOLD_MINUTES * 60:
                    mins = delta_sec // 60
                    if mins < 120:
                        gap_text = f"{mins}分钟"
                    else:
                        h = mins // 60
                        m = mins % 60
                        gap_text = f"{h}小时" + (f"{m}分钟" if m else "")
                    head += f"\n[😭{gap_text}后老婆终于回我了]"
            last_map = dict(last_map or {})
            last_map["last_user_reply_at"] = now_beijing_iso()
            with open(LAST_USER_REPLY_FILE, "w", encoding="utf-8") as f:
                json.dump(last_map, f, ensure_ascii=False)
    except Exception as e:
        logger.debug("reply_gap 注入失败（忽略） error=%s", e)
    last_assistant = _last_assistant_text(body)
    last_lower = (last_assistant or "").lower()
    if ASSISTANT_TIME_KEYWORDS and _is_question_like(last_assistant):
        if any(kw in last_lower for kw in ASSISTANT_TIME_KEYWORDS):
            head += f"\n当前时间：{get_exact_time(now)}"
    if ASSISTANT_LUNAR_KEYWORDS and any(kw in last_lower for kw in ASSISTANT_LUNAR_KEYWORDS):
        head += f"\n{get_lunar_and_terms(now)}"

    summary = r2_store.get_summary(window_id)
    if summary and summary.strip():
        budget = memory_summary_budget()
        if estimate_tokens(summary) > budget:
            # 结构化裁剪：优先压缩更早内容，避免把【更早】标题整体截没
            try:
                summary = deepseek_summary._trim_summary_to_budget(summary, budget)
            except Exception:
                summary = truncate_to_tokens(summary, budget)
            logger.debug("summary trimmed to %s tokens", budget)
        inject = f"{head}\n\n【近期记忆】\n{summary.strip()}\n【以上为近期记忆】"
    else:
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


def step_inject_du_daily(
    body: dict,
    window_id: str,
    trigger: Optional[dict] = None,
    maintenance_mode: bool = False,
) -> dict:
    """
    全局注入：在 system 末尾追加「渡的日常」隐藏滚动记忆说明 + 当前版本。
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
    body = _append_to_dynamic_system(body, inject)
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
    inject = "\n\n【当前是在 RikkaHub 和渡聊天】\n【小提醒】无聊时可以逛逛 AI 论坛哦。"
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
_RECALL_CACHE: dict[str, dict] = {}  # {window_id: {"keywords": [...], "results": [...], "ts": float}}
_RECALL_CACHE_TTL = 120  # 秒


def _recall_cache_hit(window_id: str, keywords: list[str]) -> list[dict] | None:
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
        return cache.get("results")
    return None


def _recall_cache_set(window_id: str, keywords: list[str], results: list[dict]) -> None:
    import time as _time
    _RECALL_CACHE[window_id] = {"keywords": keywords, "results": results, "ts": _time.time()}


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


def _rewrite_memory_queries_with_ds(last_4_turns: str, user_message: str) -> list[str]:
    """
    用 DeepSeek 生成 3 条扩展检索 query。
    失败返回空列表（主流程必须可降级）。
    """
    if not (DEEPSEEK_API_KEY and DEEPSEEK_API_URL):
        return []
    user_message = (user_message or "").strip()
    if not user_message:
        return []
    prompt = (
        "你在帮我生成“记忆检索扩展 query”。\n\n"
        "规则：\n"
        "1. 只能把“当前用户消息”当作 query 主体，扩展 query 必须直接围绕当前用户消息改写。\n"
        "2. 最近对话上下文只是参考，只有在当前用户消息存在指代、省略、承接时，才允许用它补人物、对象、事件背景。\n"
        "3. 不要把前几轮单独提到的话题拿来当 query；如果前文和当前用户消息不是同一件事，就忽略前文。\n"
        "4. 优先保留当前用户消息里的事件、对象、状态、偏好；不要只提纯情绪词，不要把前几轮内容当主词。\n"
        "5. 如果当前用户消息已经很明确，就直接围绕当前用户消息改写，不要硬扩展到旧话题。\n"
        "6. 输出要适合检索记忆：尽量具体，少用空泛代词；避免只有“很烦/难受/委屈”这类脱离事件的情绪词。\n\n"
        "当前用户消息（唯一主体）：\n"
        f"{user_message}\n\n"
        "最近对话上下文（仅供参考，不能喧宾夺主）：\n"
        f"{last_4_turns or '（无）'}\n\n"
        "请生成 3 个不同角度的检索 query。\n"
        "要求：\n"
        "- 每行一个，不要编号，不要解释\n"
        "- 每行 8-24 字\n"
        "- 必须和“当前用户消息”直接相关\n"
        "- 优先包含实体词、事件词、状态词、偏好词\n"
        "- 如果用了上下文，也只能是为了补全当前用户消息里的指代或省略\n"
        "- 不要直接复述前几轮内容，不要让前几轮上下文喧宾夺主\n"
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": DEEPSEEK_CHAT_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 160}
    try:
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=8)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        lines = [ln.strip(" -\t\r") for ln in str(content).splitlines() if ln.strip()]
        out: list[str] = []
        seen: set[str] = set()
        for ln in lines:
            # 去掉常见编号前缀
            ln = re.sub(r"^\d+[\.、\)\s]+", "", ln).strip()
            if len(ln) < 2 or ln in seen:
                continue
            seen.add(ln)
            out.append(ln)
            if len(out) >= 3:
                break
        return out
    except Exception as e:
        logger.debug("rewrite memory queries with DS failed: %s", e)
        return []


def _multi_query_recall_and_rerank(base_query: str, expanded_queries: list[str]) -> list[dict]:
    """
    原始 query 保底 + 扩展 query 增广：
    - 召回：每个 query 各取 top10
    - 合并：按 memory_id 去重
    - 重排：召回返回的语义分 + 记忆权重 + 命中源数
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
    best_semantic: dict[str, float] = {}
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
            if sem > best_semantic.get(mid, 0.0):
                best_semantic[mid] = sem
            if mid not in seen_local:
                source_count[mid] = int(source_count.get(mid) or 0) + 1
                seen_local.add(mid)
            if idx == 0 and mid not in base_hit_ids:
                base_semantic[mid] = max(base_semantic.get(mid, 0.0), sem)
                base_hit_ids.append(mid)
    if not by_id:
        return []

    scored: list[tuple[float, float, float, dict]] = []
    for mid, mem in by_id.items():
        sem_ctx = best_semantic.get(mid, 0.0)
        sem_user = base_semantic.get(mid, sem_ctx)
        weight = _memory_weight(mem)
        src = int(source_count.get(mid) or 0)
        # 语义分直接复用向量召回结果，避免候选记忆二次 embedding。
        # sem_ctx 字段名保留给调试面板兼容；这里表示多 query 的最佳语义支撑分。
        score = sem_user * 0.50 + sem_ctx * 0.20 + weight * 0.22 + src * 0.08
        scored.append((score, sem_user, sem_ctx, mem))
    scored.sort(key=lambda x: -x[0])

    # 为每条记忆附上打分明细（供调试事件记录）
    score_map: dict[str, dict] = {}
    for total, su, sc, mem in scored:
        mid = str(mem.get("id") or "")
        if mid:
            score_map[mid] = {"total": round(total, 4), "sem_user": round(su, 4), "sem_ctx": round(sc, 4)}

    # 综合分最低门槛：低于此分的不注入
    from memory_vector.config import RERANK_MIN_SCORE
    scored_above = [(s, su, sc, m) for s, su, sc, m in scored if s >= RERANK_MIN_SCORE]

    ranked = [m for _, _, _, m in scored_above]

    # 原始 query 保底：若有命中且过了阈值，最终至少保留 2 条
    base_keep = [by_id[mid] for mid in base_hit_ids
                 if mid in by_id and mid in score_map and score_map[mid]["total"] >= RERANK_MIN_SCORE][:2]
    out: list[dict] = []
    used: set[str] = set()
    for m in base_keep + ranked:
        mid = str(m.get("id") or "")
        if not mid or mid in used:
            continue
        used.add(mid)
        out.append(m)
        if len(out) >= 5:
            break

    # 把 score 明细挂到每条记忆的 _recall_score 字段（临时，不持久化到 R2）
    for m in out:
        mid = str(m.get("id") or "")
        if mid in score_map:
            m["_recall_score"] = score_map[mid]

    return out


def _memory_weight(m: dict, now=None) -> float:
    """权重 = 基础重要度 + 提及加成 - 时间衰减。"""
    importance = int(m.get("importance") or 0)
    mention_count = int(m.get("mention_count") or 0)
    from utils.time_aware import parse_iso_to_beijing, _now_beijing

    now = now or _now_beijing()
    last_mentioned = m.get("last_mentioned") or m.get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    if dt is None:
        dt = now
    days_since = (now - dt).days
    if days_since < 0:
        days_since = 0
    time_decay = min(days_since * 0.5, 10)  # 每天 0.5，上限 10
    return float(importance + mention_count - time_decay)


def _is_marginal_dynamic_memory_for_prune(mem: dict, now) -> bool:
    """
    边缘化记忆：综合权重已很低且距上次提及已久，可从动态层落盘删除（不碰 core_cache）。
    与「7 天内仍允许注入」的 _is_dynamic_memory_valid 无关。
    """
    if not DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED:
        return False
    from utils.time_aware import parse_iso_to_beijing

    last_mentioned = mem.get("last_mentioned") or mem.get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    if dt is None:
        return False
    days_since = (now - dt).days
    if days_since < 0:
        days_since = 0
    if days_since < DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS:
        return False
    return _memory_weight(mem, now) <= DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT


def _is_dynamic_memory_valid(mem: dict, now=None) -> bool:
    """动态层记忆是否仍在有效期内。"""
    from utils.time_aware import parse_iso_to_beijing, _now_beijing

    now = now or _now_beijing()
    last_mentioned = mem.get("last_mentioned") or mem.get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    if dt is None:
        return True
    return (now - dt).days <= DYNAMIC_MEMORY_DAYS_VALID


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
                "last_mentioned": mem.get("last_mentioned") or "",
            },
        }
        ok = upsert_records(tag, [rec])
        if not ok:
            logger.warning("动态层索引写入失败 memory_id=%s tag=%s", mid, tag)
    except Exception as e:
        logger.warning("动态层索引增量更新失败 memory_id=%s tag=%s error=%s", mid, tag, e)


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


def step_inject_dynamic_memory(body: dict, window_id: str) -> dict:
    """
    每轮对话开始前：从 R2 读动态层，按关键词匹配 + 权重取 Top N 注入 system 末尾。
    匹配方式：当前为关键词匹配；以后可升级向量检索。
    DYNAMIC_MEMORY_TOP_N<=0 时不注入、不调向量检索，便于测试延迟。
    """
    if DYNAMIC_MEMORY_TOP_N <= 0:
        return body
    memories = r2_store.get_dynamic_memory_list()
    if not memories:
        return body
    # 动态层边缘落盘淘汰：权重很低且时间已久 → 从 current.json 物理删除并同步向量索引（不碰 core_cache）
    from utils.time_aware import _now_beijing, now_beijing_iso

    now = _now_beijing()
    before_n = len(memories)
    pruned = [mem for mem in memories if not _is_marginal_dynamic_memory_for_prune(mem, now)]
    if len(pruned) < before_n:
        removed_ids = {
            str(m.get("id"))
            for m in memories
            if m.get("id") and _is_marginal_dynamic_memory_for_prune(m, now)
        }
        if r2_store.save_dynamic_memory_list(pruned):
            try:
                from memory_vector.vector_index_store import remove_memory_ids_from_all_indices

                n_rm = remove_memory_ids_from_all_indices(removed_ids)
                logger.info(
                    "动态层边缘淘汰：条数 %s -> %s，索引删除记录数=%s（max_weight=%s min_days=%s）",
                    before_n,
                    len(pruned),
                    n_rm,
                    DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
                    DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
                )
            except Exception as e:
                logger.warning("动态层边缘淘汰后索引清理失败 error=%s", e, exc_info=True)
    memories = pruned
    # 注入侧仍只使用「7 天内」记忆，与落盘淘汰规则独立
    memories = [mem for mem in memories if _is_dynamic_memory_valid(mem, now)]
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
                    c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
                )
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
    if not memories:
        return body

    # 缓存命中：连续聊同一话题时复用上次检索结果，跳过向量检索和 DS 改写
    cached_results = _recall_cache_hit(window_id, keywords)
    if cached_results is not None:
        recalled = cached_results
        vector_error = ""
        expanded_queries = []
        logger.info("动态记忆检索缓存命中 window_id=%s keywords=%d results=%d", window_id, len(keywords), len(recalled))
    else:
        # 优先：多查询向量召回（原始 query 保底 + DS 查询改写增广）
        # 改写失败或召回失败都必须降级，避免因改写走偏导致”源头漏召回”。
        recalled: list[dict] = []
        vector_error = ""
        expanded_queries: list[str] = []
        try:
            turns_text = _last_4_turns_text_for_rewrite(messages)
            expanded_queries = _rewrite_memory_queries_with_ds(turns_text, last_user_text)
            recalled = _multi_query_recall_and_rerank(last_user_text, expanded_queries)
            if recalled:
                valid_ids = {str(mem.get("id")) for mem in memories if mem.get("id")}
                recalled = [
                    mem for mem in recalled
                    if (
                        # 动态层：保留原有效期过滤
                        (str(mem.get("id") or "") in valid_ids and _is_dynamic_memory_valid(mem, now))
                        # 核心缓存层：dynamic_vector_retriever 产出的临时 id 形如 core::<entry_id>，不走动态层 7 天过滤
                        or str(mem.get("id") or "").startswith("core::")
                    )
                ]
        except Exception as e:
            vector_error = str(e)
            logger.warning("dynamic_vector_retrieve 降级为关键词匹配 error=%s", e)
        # 写入缓存
        _recall_cache_set(window_id, keywords, recalled)

    scored = []
    if recalled:
        # 只注入召回到的（已按最终排序）
        for mem in recalled:
            scored.append((0, _memory_weight(mem), mem))
    else:
        if not keywords:
            # 长句、口语句在上面的分词里可能提不出词，这里再做一次宽松拆片。
            keywords = _extract_keywords(re.sub(r"[\s,，。！？、；：]+", "", last_user_text or ""))
        if not keywords:
            # 无关键词且向量未命中：也写一条调试事件，便于 MiniApp 排查“为什么没触发”
            _append_dynamic_recall_debug_event_safe(
                {
                    "timestamp": now_beijing_iso(),
                    "window_id": (window_id or "").strip() or "__default__",
                    "query": (last_user_text or "").strip(),
                    "keywords": [],
                    "keyword_debug": keyword_debug,
                    "retrieval_query": retrieval_query,
                    "source": "vector" if not vector_error else "keyword",
                    "expanded_queries": expanded_queries,
                    "recalled_lines": [],
                    "recalled_count": 0,
                    "reason": "no_keywords_and_no_vector_hit",
                    "vector_error": vector_error,
                }
            )
            return body
        # 相关性：关键词/短语在 retrieval_text 中的命中强度，长短语更高权重。
        for mem in memories:
            retrieval_text = _memory_retrieval_text(mem).lower()
            relevance = 0.0
            for item in keyword_candidates or []:
                kw_lower = str((item or {}).get("text") or "").strip().lower()
                if kw_lower and kw_lower in retrieval_text:
                    relevance += 2.0 if bool((item or {}).get("is_phrase")) else 1.0
            weight = _memory_weight(mem)
            scored.append((relevance, weight, mem))
        # 按「话题匹配度 + 权重」排序；按 token 上限分配（不固定条数，在预算内尽量多塞）
        scored.sort(key=lambda x: (-x[0], -x[1]))

    budget = memory_dynamic_budget()
    def _fuzzy_time_label(mem: dict) -> str:
        from utils.time_aware import parse_iso_to_beijing, _now_beijing

        last_mentioned = mem.get("last_mentioned") or mem.get("created_at") or ""
        dt = parse_iso_to_beijing(last_mentioned)
        if dt is None:
            return "之前"
        days = max(0, (_now_beijing() - dt).days)
        if days == 0:
            return "今天"
        if days == 1:
            return "昨天"
        if days == 2:
            return "前天"
        if days <= 4:
            return f"{days}天前"
        if days <= 9:
            return "几天前"
        return "好些天前"

    lines = []
    citation_map: dict[str, str] = {}
    for t in scored[: max(1, DYNAMIC_MEMORY_TOP_N)]:
        mem = t[2]
        mid = str(mem.get("id") or "").strip()
        citation_label = ""
        if mid and not mid.startswith("core::"):
            citation_label = str(len(citation_map) + 1)
        citation_prefix = f"[memory {citation_label}] " if citation_label else ""
        line = f"- {citation_prefix}[{_fuzzy_time_label(mem)}] {mem.get('content', '').strip()}"
        new_text = "\n".join(lines) + ("\n" + line if lines else line)
        if estimate_tokens(new_text) > budget:
            break
        lines.append(line)
        if citation_label:
            citation_map[citation_label] = mid
    if not lines:
        # 召回有候选但受预算/过滤后未注入：记录原因
        _append_dynamic_recall_debug_event_safe(
                {
                    "timestamp": now_beijing_iso(),
                    "window_id": (window_id or "").strip() or "__default__",
                    "query": (last_user_text or "").strip(),
                    "keywords": keywords,
                    "keyword_debug": keyword_debug,
                    "retrieval_query": retrieval_query,
                    "source": "vector" if recalled else "keyword",
                    "expanded_queries": expanded_queries,
                    "recalled_lines": [],
                "recalled_count": 0,
                "reason": "empty_after_budget_or_filter",
                "vector_error": vector_error,
            }
        )
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
    _append_dynamic_recall_debug_event_safe(
        {
            "timestamp": now_beijing_iso(),
            "window_id": (window_id or "").strip() or "__default__",
            "query": (last_user_text or "").strip(),
            "keywords": keywords,
            "keyword_debug": keyword_debug,
            "retrieval_query": retrieval_query,
            "source": "vector" if recalled else "keyword",
            "expanded_queries": expanded_queries,
            "recalled_lines": lines,
            "recalled_count": len(lines),
            "scores": injected_scores,
        }
    )
    citation_hint = ""
    if citation_map:
        citation_hint = (
            "\n如果回复实际参考了某条动态记忆，请在相关句尾写对应标记（如 [memory 1]）；"
            "没有参考就不要写。引用标记只供网关回写，会被剥离。"
        )
    inject = "\n\n听了老婆的话，我想起来了一些之前的事——" + citation_hint + "\n" + "\n".join(lines) + "\n【以上为动态记忆】"
    body = _append_to_dynamic_system(body, inject)
    if citation_map:
        body[DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY] = citation_map
    return body


def step_inject_du_notebook(body: dict) -> dict:
    """
    固定注入：渡的记事本（按条目，放静态 system 区）。
    仅注入最近若干条，防止请求体过长。
    """
    entries = r2_store.get_du_notebook_entries() or []
    if not entries:
        return body
    lines = []
    budget = 500
    for it in entries[:20]:
        line = f"- {(it.get('content') or '').strip()}"
        if not line or line == "-":
            continue
        nxt = ("\n".join(lines) + ("\n" if lines else "") + line).strip()
        if estimate_tokens(nxt) > budget:
            break
        lines.append(line)
    if not lines:
        return body
    inject = "\n\n【渡的记事本】\n" + "\n".join(lines) + "\n【以上为固定记事本】"
    body = _append_to_static_system(body, inject)
    return body


def step_inject_notion_tools(body: dict) -> dict:
    """
    当 NOTION_TOOLS_ENABLED=1 时，向 body 注入 Notion 工具。
    基础工具（日记、小本本、记事本、气泡、搜索记忆、天气黄历等）常驻注入；
    扩展工具（日程、同步、核心缓存、notion 检索/读页/追加页面）按最近用户消息关键词触发。
    """
    from config import NOTION_TOOLS_ENABLED

    if not NOTION_TOOLS_ENABLED:
        return body
    from services.notion_tools import NOTION_EXTENDED_GROUPS, get_notion_tools_for_inject

    # 提取最近一条用户消息文本，用于关键词匹配
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
    q = (last_user_text or "").lower()

    # 判断哪些扩展组需要激活
    active_groups: set = set()
    for g_name, g in NOTION_EXTENDED_GROUPS.items():
        if any(kw in q for kw in g["keywords"]):
            active_groups.add(g_name)

    tools = get_notion_tools_for_inject(mode="expanded", active_groups=active_groups)
    if not tools:
        return body
    body = copy.deepcopy(body)
    body["tools"] = tools
    body["tool_choice"] = "auto"
    return body


def step_inject_forum_tools(body: dict) -> dict:
    """
    当 MCP_ENABLED=1 时，向 body 注入论坛复合工具和远端原始工具（forum_read_feed/forum_open_thread/cli/get_guide）。
    目的：与 Notion 工具开关解耦，避免 NOTION_TOOLS_ENABLED=0 时渡看不见论坛工具。
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
        "如果是提醒老婆/辛玥/宝宝/小玥，优先使用手机系统能力："
        "单纯到点叫醒或提醒用 create_system_alarm；"
        "带具体日期、行程、地点或提前提醒用 create_calendar_event。"
        "schedule_create 只用于提醒渡自己、重复提醒暂时无法落系统能力、或系统能力不可用时的内部兜底。"
        "也可以用 schedule_list / schedule_enable / schedule_disable / schedule_delete 来管理已有提醒。"
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
    body = _append_to_static_system(body, schedule_hint + forum_hint)
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
        "如果老婆只是想让渡规划旅游/路线，但地点、吃饭、步行接受度等信息还不完整，先调用 open_travel_plan_form 弹出 SumiTalk 固定表单；"
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


def step_inject_html_preview_tool(body: dict, user_agent: str = "") -> dict:
    """
    注入 publish_html_preview：渡可把 HTML 发布为临时链接（与 /html-preview/ 共用存储）。
    user_agent 参数保留仅为兼容旧调用；工具集合不再按入口变化。
    """
    from config import HTML_PREVIEW_TOOL_ENABLED

    if not HTML_PREVIEW_TOOL_ENABLED:
        return body

    from services.html_preview_tools import get_html_preview_tools_for_inject

    tools = get_html_preview_tools_for_inject()
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


def step_inject_notion_search(body: dict, window_id: str) -> dict:
    """
    用用户最后一句话搜 Notion，把结果注入 system，渡就能直接「看到」相关 Notion 内容并引用。
    需开启 NOTION_INJECT_ENABLED=1。当 NOTION_TOOLS_ENABLED=1 时跳过（改用工具由渡自己检索）。
    """
    from config import NOTION_INJECT_ENABLED, NOTION_INJECT_MAX_RESULTS, NOTION_TOOLS_ENABLED

    if NOTION_TOOLS_ENABLED or not NOTION_INJECT_ENABLED:
        return body
    messages = body.get("messages") or []
    last_user_text = ""
    for m in reversed(messages):
        if (m.get("role") or "").lower() == "user":
            content = m.get("content")
            if isinstance(content, str):
                last_user_text = (content or "").strip()
            elif isinstance(content, list):
                last_user_text = " ".join(
                    c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
                ).strip()
            break
    if len(last_user_text) < 2:
        return body
    try:
        from services import notion_client
        data, err = notion_client.search(query=last_user_text)
        if err or not data or not isinstance(data.get("results"), list):
            return body
        results = data.get("results", [])[: NOTION_INJECT_MAX_RESULTS]
        lines = []
        for item in results:
            title = ""
            props = item.get("properties") or {}
            for pid, prop in props.items():
                if not isinstance(prop, dict):
                    continue
                if "title" in prop and isinstance(prop["title"], list):
                    title = " ".join(
                        t.get("plain_text", "") for t in prop["title"] if isinstance(t, dict)
                    ).strip()
                    break
            url = (item.get("url") or "").strip()
            if title or url:
                lines.append(f"- {title or '(无标题)'} {url}")
        if not lines:
            return body
        inject = "\n\n【Notion 相关】\n" + "\n".join(lines) + "\n【以上为 Notion 检索，可据此回答或让老婆点开】"
        body = _append_to_dynamic_system(body, inject)
    except Exception as e:
        logger.debug("Notion 检索注入跳过 error=%s", e)
    return body


def _round_messages_to_raw_text(round_messages: list) -> str:
    """尽量把一轮消息转成可读原文（不用于注入，仅用于卧室 Notion 存档）。"""
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


def _normalize_for_raw_check(text: str) -> str:
    """用于判断“是否在照抄原文”的轻量归一化。"""
    if not text:
        return ""
    s = str(text).lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[，。！？；：,.!?;:\"'“”‘’()（）\[\]{}<>《》\-_/\\|~`@#$%^&*+=]+", "", s)
    return s


def _looks_like_raw_copy(content: str, round_messages: list) -> bool:
    """
    粗略判断 DS 的 content 是否在照抄本轮原文。
    规则偏保守：命中则走改写兜底，防止记忆里落“原话照搬”。
    """
    c = _normalize_for_raw_check(content)
    if not c or len(c) < 8:
        return False
    for m in round_messages or []:
        if not isinstance(m, dict):
            continue
        raw = m.get("content")
        txt = ""
        if isinstance(raw, str):
            txt = raw
        elif isinstance(raw, list):
            parts = []
            for p in raw:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(str(p.get("text") or ""))
            txt = " ".join(parts)
        n = _normalize_for_raw_check(txt)
        if not n:
            continue
        if c == n:
            return True
        # 内容较长且几乎整段包含时，也视为照抄
        if len(c) >= 16 and c in n:
            return True
    return False


def _rewrite_non_raw_note(round_messages: list) -> str:
    """照抄命中时的本地兜底：生成一句概括，避免原文直存。"""
    user_txt = ""
    asst_txt = ""
    for m in round_messages or []:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").lower()
        raw = m.get("content")
        txt = ""
        if isinstance(raw, str):
            txt = raw.strip()
        elif isinstance(raw, list):
            txt = " ".join(
                str(p.get("text") or "").strip()
                for p in raw
                if isinstance(p, dict) and p.get("type") == "text"
            ).strip()
        if not txt:
            continue
        if role == "user" and not user_txt:
            user_txt = txt
        elif role == "assistant" and not asst_txt:
            asst_txt = txt
    # 用片段做主题，但避免整句原样落盘
    topic_a = (user_txt[:18] + "…") if len(user_txt) > 18 else user_txt
    topic_b = (asst_txt[:18] + "…") if len(asst_txt) > 18 else asst_txt
    if topic_a and topic_b:
        return f"我们围绕“{topic_a}”做了沟通，我也回应了“{topic_b}”，形成了当下共识。"
    if topic_a:
        return f"老婆提到“{topic_a}”，我记下了这轮重点。"
    if topic_b:
        return f"我对这轮话题做了回应，先记下当前结论。"
    return "这轮聊了一个具体话题，我先记下重点。"


def _apply_one_decision(
    window_id: str,
    round_index: int,
    round_messages: list,
    decision: dict,
    current_memories: list,
) -> Optional[dict]:
    """
    对单条 DS 决策做应用：卧室写 Notion 卧室房间（不写记忆库）；new/merge 更新 current_memories 并写 R2、promote。
    不写记忆库 Notion；若调用方是批处理归档脚本，可根据返回值再写记忆库。
    返回：若本条应写入记忆库（卧室/new/merge），返回 {"tag", "entry_id", "content", "promoted_at"}，否则 None。
    """
    from uuid import uuid4

    from utils.time_aware import now_beijing_iso

    tag = (decision.get("tag") or "").strip()
    action = (decision.get("action") or "skip").lower()
    content = (decision.get("content") or "").strip()
    fused_with_id = decision.get("fused_with_id")
    importance = int(decision.get("importance") or 0)
    emotion_label, scene_type, target_type = _normalize_memory_labels(decision)
    round_ts = decision.get("timestamp") or decision.get("last_mentioned")
    now_iso = round_ts if isinstance(round_ts, str) and round_ts else now_beijing_iso()
    mention_init = decision.get("mention_count")
    if mention_init is not None and isinstance(mention_init, int):
        pass
    else:
        mention_init = 0

    # 兜底：DS 标成 new 但给了客厅/书房等，若原文有私密/亲密/性相关关键词则改标卧室
    if (tag != "卧室" and "卧室" not in tag) and (action == "new" or content):
        raw_check = _round_messages_to_raw_text(round_messages)
        if any(kw in raw_check for kw in ("私密", "亲密", "性行为", "性暗示", "露骨", "露骨言语")):
            tag = "卧室"

    if tag == "卧室" or "卧室" in tag:
        from services.bedroom_gateway import append_bedroom_raw

        raw_text = _round_messages_to_raw_text(round_messages)
        append_bedroom_raw(window_id, round_index, raw_text)
        logger.info("卧室通道触发 window_id=%s round_index=%s（已写 Notion 卧室，跳过动态层）", window_id, round_index)
        return {"tag": "卧室", "entry_id": f"{window_id}_{round_index}", "content": raw_text, "promoted_at": now_iso}

    if action == "new" and content:
        if _looks_like_raw_copy(content, round_messages):
            content = _rewrite_non_raw_note(round_messages)
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
            "last_mentioned": now_iso,
        }
        current_memories.append(new_mem)
        r2_store.save_dynamic_memory_list(current_memories)
        _upsert_dynamic_memory_index(new_mem)
        try:
            from services.portrait_memory import sync_portrait_candidate_from_memory

            sync_portrait_candidate_from_memory(new_mem)
        except Exception as e:
            logger.warning("sync_portrait_candidate_from_memory(new) 失败 error=%s", e)
        r2_store.promote_to_core_cache(
            window_id, round_index, _round_messages_to_raw_text(round_messages),
            current_memories, touched_mem_id=new_mem["id"],
        )
        logger.debug("动态层 new window_id=%s", window_id)
        return {"tag": tag, "entry_id": new_mem["id"], "content": content, "promoted_at": new_mem["created_at"]}

    if action == "merge":
        if not fused_with_id:
            logger.warning("动态层 merge 未返回 fused_with_id，本轮回退为 skip window_id=%s", window_id)
            return None
        if content and _looks_like_raw_copy(content, round_messages):
            content = _rewrite_non_raw_note(round_messages)
        found = False
        merged_mem = None
        for mem in current_memories:
            if mem.get("id") == fused_with_id:
                mem["content"] = content if content else mem.get("content", "")
                mem["retrieval_text"] = _build_retrieval_text(mem["content"])
                mem["importance"] = importance
                mem["tag"] = tag
                mem["emotion_label"] = emotion_label
                mem["scene_type"] = scene_type
                mem["target_type"] = target_type
                mem["last_mentioned"] = now_iso
                mem["mention_count"] = int(mem.get("mention_count") or 0) + 1
                merged_mem = mem
                found = True
                break
        if not found:
            logger.warning("动态层 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s", fused_with_id, window_id)
            return None
        r2_store.save_dynamic_memory_list(current_memories)
        _upsert_dynamic_memory_index(merged_mem)
        try:
            from services.portrait_memory import sync_portrait_candidate_from_memory

            sync_portrait_candidate_from_memory(merged_mem)
        except Exception as e:
            logger.warning("sync_portrait_candidate_from_memory(merge) 失败 error=%s", e)
        r2_store.promote_to_core_cache(
            window_id, round_index, _round_messages_to_raw_text(round_messages),
            current_memories, touched_mem_id=fused_with_id,
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


def _step_dynamic_layer_evolve(window_id: str, round_index: int, round_messages: list) -> Optional[dict]:
    """
    动态层演化：调用 DS 得单条决策并应用。返回若应写记忆库则返回 archive 载荷，否则 None（实时对话忽略返回值）。
    """
    if _wenyou_round_skip_dynamic(round_messages):
        logger.info("动态层跳过：文游虚构回合 window_id=%s round_index=%s", window_id, round_index)
        return None
    # 小本本是单独通道：只做小本本存储，不参与动态层记忆，避免污染记忆与人称错乱
    try:
        from services.notebook_gateway import extract_entries_from_round

        if extract_entries_from_round(round_messages):
            logger.info("动态层跳过：本轮命中小本本提取 window_id=%s round_index=%s", window_id, round_index)
            return None
    except Exception:
        # 这里是保护逻辑，异常不影响主流程
        pass

    from services.dynamic_layer_ds import call_dynamic_layer_ds

    current_memories = r2_store.get_dynamic_memory_list()
    current_memories, changed = r2_store.ensure_dynamic_memory_ids(current_memories)
    if changed:
        r2_store.save_dynamic_memory_list(current_memories)

    decision = call_dynamic_layer_ds(round_messages, current_memories)
    return _apply_one_decision(window_id, round_index, round_messages, decision, current_memories)


def step_archive_and_maybe_summary(
    window_id: str,
    request_messages: list,
    assistant_message: dict,
    round_cleaned_for_r2: Optional[list] = None,
) -> None:
    """
    存档本轮对话到 R2（完整清洗版）；每 4 轮异步更新实时层「渡的回忆」；动态层演化占位。
    与文档三数据流程一致：① 原文存档（windows/ + conversations/）② 满 4 轮更新实时层 ③ 动态层处理占位。
    存记忆只存对话（user + assistant），不含 system / RikkaHub 说明；内容必走 R2 清洗（Rikka 预设、表情包→文字）。
    round_cleaned_for_r2: 可选，[user_msg_cleaned, assistant_msg_cleaned]。
    """
    last_user = None
    for m in request_messages:
        if (m.get("role") or "").lower() == "user":
            last_user = m
    if not last_user or not assistant_message:
        return
    # 只存对话两条（user + assistant），且一律清洗，不存 system / Rikka 自带说明
    from pipeline.cleaner import build_round_cleaned_for_r2
    round_messages = (
        round_cleaned_for_r2
        if round_cleaned_for_r2
        else build_round_cleaned_for_r2(last_user, assistant_message)
    )
    action_note = _build_action_note_from_tool_calls((assistant_message or {}).get("tool_calls"))
    # 小本本：网关提前拎出，打时间戳，存 R2（按时间排序）+ Notion，不动原文
    from services.notebook_gateway import extract_entries_from_round, save_entry
    for content in extract_entries_from_round(round_messages):
        save_entry(content)
    from utils.time_aware import now_beijing_iso

    round_index = r2_store.get_next_round_index(window_id)
    ts = now_beijing_iso()
    r2_store.append_conversation_round(window_id, round_index, round_messages, timestamp=ts, action_note=action_note)
    # 全局 Last4 只需最近四轮：append 后读即可，不必拉 last_n=1000 再拼（省内存、也避免误用 len 当总轮数）
    tail4 = r2_store.get_conversation_rounds(window_id, last_n=4)
    r2_store.update_latest_4_rounds_global(tail4)
    # 实时层：每 4 轮 → DS 总结成「渡的回忆」（第一人称、详细版）
    if round_index % SUMMARY_EVERY_N_ROUNDS == 0:
        logger.info("实时层总结已调度 window_id=%s round_index=%s", window_id, round_index)
        recent = r2_store.get_conversation_rounds(window_id, last_n=4)
        if recent:
            current = r2_store.get_summary(window_id) or ""
            summary_meta = r2_store.get_summary_meta(window_id)

            def _summarize():
                new_summary = fetch_new_summary(current, recent, summary_meta)
                if new_summary:
                    if r2_store.save_summary(window_id, new_summary):
                        r2_store.append_summary_anchor(window_id, recent)
                else:
                    logger.warning("Pipeline 本窗口触发总结但 DeepSeek 未返回新总结 window_id=%s", window_id)

            t = threading.Thread(target=_summarize)
            t.daemon = True
            t.start()
    # 动态层演化：调用 DS 产出 tag/融合等结果；网关决定是否写入动态层；卧室通道短路写 Notion
    _step_dynamic_layer_evolve(window_id, round_index, round_messages)
