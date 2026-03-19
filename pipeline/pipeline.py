# 管道主流程：清洗(图片) → 新窗口注入 → 记忆注入 → 转发 → 存档/总结（不再按窗口 ID 判定）
import copy
import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from config import (
    SUMMARY_EVERY_N_ROUNDS,
    DYNAMIC_MEMORY_DAYS_VALID,
    DYNAMIC_MEMORY_TOP_N,
    ASSISTANT_TIME_KEYWORDS,
    ASSISTANT_LUNAR_KEYWORDS,
    REPLY_GAP_THRESHOLD_MINUTES,
    LAST_USER_REPLY_FILE,
    MAX_REQUEST_CHARS,
)
from pathlib import Path
from storage import r2_store
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_summary_budget, memory_dynamic_budget, truncate_to_tokens

logger = get_logger(__name__)
from services import image_desc, deepseek_summary
from services.deepseek_summary import fetch_new_summary


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
            role = m.get("role", "")
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
                )
            lines.append(f"[{role}]: {content}")
    return "\n".join(lines) if lines else ""


def step_inject_latest_4_rounds_for_new_window(body: dict, window_id: str) -> dict:
    """
    新窗口：从 R2 读取全局「最新四轮」注入。
    已有历史但请求里消息很少（如主动发消息只发一条）：注入该窗口自己的最近四轮（如 Telegram 侧 Last4）。
    """
    if not window_id:
        return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    inject_label = ""
    rounds = []

    if not r2_store.has_window_history(window_id):
        # 主动发消息只在 Telegram 侧，tg_ 窗口不注入「其他窗口」的全局 4 轮，只带窗口总结 + 本窗口 Last4（无历史则无 Last4）
        if window_id.startswith("tg_"):
            rounds = []
        else:
            rounds = r2_store.get_latest_4_rounds_global()
            inject_label = "以下为注入的近期对话上下文（来自其他窗口）"
    else:
        # 已有历史且当前请求消息很少（如 proactive 只发 1 条 user）→ 注入本窗口最近 4 轮（Telegram Last4）
        if len(messages) <= 2:
            rounds = r2_store.get_conversation_rounds(window_id, last_n=4)
            inject_label = "以下为注入的本窗口近期对话（Last4 轮）"
        else:
            rounds = []

    if not rounds:
        return body
    context = _rounds_to_context_text(rounds)
    if not context:
        return body
    inject = f"\n\n【{inject_label}】\n{context}\n【以上为注入上下文】"
    found_system = False
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() == "system":
            msg["content"] = (msg.get("content") or "") + inject
            found_system = True
            break
    if not found_system:
        messages.insert(0, {"role": "system", "content": inject})
    body["messages"] = messages
    return body


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


def step_inject_summary(body: dict, window_id: str) -> dict:
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

    # 老婆多久没回
    try:
        last_map = {}
        if LAST_USER_REPLY_FILE.exists():
            with open(LAST_USER_REPLY_FILE, "r", encoding="utf-8") as f:
                last_map = json.load(f) or {}
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
            summary = truncate_to_tokens(summary, budget)
            logger.debug("summary truncated to %s tokens", budget)
        inject = f"{head}\n\n【窗口记忆总结】\n{summary.strip()}\n【以上为窗口记忆】"
    else:
        inject = head
    found = False
    for msg in messages:
        if (msg.get("role") or "").lower() == "system":
            msg["content"] = (msg.get("content") or "") + inject
            found = True
            break
    if not found:
        messages.insert(0, {"role": "system", "content": inject})
    body["messages"] = messages
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
    body = copy.deepcopy(body)
    messages = body["messages"]
    inject = "\n\n【当前是在 RikkaHub 和渡聊天】"
    for msg in messages:
        if (msg.get("role") or "").lower() == "system":
            msg["content"] = (msg.get("content") or "") + inject
            break
    else:
        messages.insert(0, {"role": "system", "content": inject.strip()})
    return body


def step_inject_tg_todos(body: dict, window_id: str) -> dict:
    """Telegram TodoList：对 tg_ 窗口把「未完成事项」注入到 system，渡无需调用工具也能看到。"""
    wid = (window_id or "").strip()
    if not wid.startswith("tg_"):
        return body
    if not body or not isinstance(body.get("messages"), list):
        return body
    items = r2_store.get_tg_todos(wid) or []
    pending = [x for x in items if isinstance(x, dict) and not bool(x.get("done"))]
    if not pending:
        return body
    # 最多注入前 12 条，避免太长
    pending = pending[:12]
    lines = []
    for i, it in enumerate(pending, 1):
        txt = str(it.get("text") or "").strip()
        if txt:
            lines.append(f"{i}. {txt}")
    if not lines:
        return body
    inject = "\n\n【Telegram Todo（未完成）】\n" + "\n".join(lines) + "\n【以上为 Todo】"
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    for msg in messages:
        if (msg.get("role") or "").lower() == "system":
            msg["content"] = (msg.get("content") or "") + inject
            break
    else:
        messages.insert(0, {"role": "system", "content": inject.strip()})
    body["messages"] = messages
    return body


def _extract_keywords(text: str) -> list:
    """从当前对话文本中提取简单关键词（用于匹配动态层）。"""
    if not text or not isinstance(text, str):
        return []
    # 按空格、常见标点分词，过滤过短
    parts = re.split(r"[\s,，。！？、；：]+", text)
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
        # 元问题（讨论系统本身）常见词：避免触发“乱塞一堆”
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
    keywords = []
    for p in parts:
        p = p.strip()
        if len(p) < 2:
            continue
        if p in stopwords:
            continue
        # 太长的整句不当关键词（避免把整段当一个词匹配过宽）
        if len(p) > 24:
            continue
        # 至少 2 字符
        if len(p) >= 2:
            keywords.append(p)
    return list(set(keywords))


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


def _memory_weight(m: dict) -> float:
    """权重 = 基础重要度 + 提及加成 - 时间衰减。"""
    importance = int(m.get("importance") or 0)
    mention_count = int(m.get("mention_count") or 0)
    from utils.time_aware import parse_iso_to_beijing, _now_beijing
    last_mentioned = m.get("last_mentioned") or m.get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    if dt is None:
        dt = _now_beijing()
    days_since = (_now_beijing() - dt).days
    time_decay = min(days_since * 0.5, 10)  # 每天 0.5，上限 10
    return importance + mention_count - time_decay


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
    # 元问题：不要触发动态记忆（避免“问记忆→召回一堆含记忆字样的记忆”）
    if _is_memory_meta_query(last_user_text):
        return body
    keywords = _extract_keywords(last_user_text)
    # 只保留有效期内（7 天）的记忆（按北京时间）
    from utils.time_aware import parse_iso_to_beijing, _now_beijing
    now = _now_beijing()
    valid = []
    for mem in memories:
        last_mentioned = mem.get("last_mentioned") or mem.get("created_at") or ""
        dt = parse_iso_to_beijing(last_mentioned)
        if dt is None:
            valid.append(mem)
        elif (now - dt).days <= DYNAMIC_MEMORY_DAYS_VALID:
            valid.append(mem)
    memories = valid
    if not memories:
        return body

    # 优先：向量召回 topK → 用现有 weight 重排 topN
    # 若未配置 OPENAI_API_KEY 或向量检索失败，则降级为关键词匹配
    recalled: list[dict] = []
    try:
        from memory_vector.dynamic_vector_retriever import dynamic_vector_retrieve

        recalled = dynamic_vector_retrieve(last_user_text)
    except Exception as e:
        logger.debug("dynamic_vector_retrieve 降级为关键词匹配 error=%s", e)

    scored = []
    if recalled:
        # 只注入召回到的（已按最终排序）
        for mem in recalled:
            scored.append((0, _memory_weight(mem), mem))
    else:
        # 没有可用关键词时，不做关键词匹配（避免 relevance 全为 0 时退化成“按权重乱塞”）
        if not keywords:
            return body
        # 相关性：关键词在 content 中出现次数
        for mem in memories:
            content = (mem.get("content") or "").lower()
            relevance = sum(1 for kw in keywords if kw.lower() in content) if keywords else 0
            weight = _memory_weight(mem)
            scored.append((relevance, weight, mem))
        # 按「话题匹配度 + 权重」排序；按 token 上限分配（不固定条数，在预算内尽量多塞）
        scored.sort(key=lambda x: (-x[0], -x[1]))

    budget = memory_dynamic_budget()
    lines = []
    for t in scored[: max(1, DYNAMIC_MEMORY_TOP_N)]:
        line = f"- {t[2].get('content', '').strip()}"
        new_text = "\n".join(lines) + ("\n" + line if lines else line)
        if estimate_tokens(new_text) > budget:
            break
        lines.append(line)
    if not lines:
        return body
    inject = "\n\n【动态记忆】\n" + "\n".join(lines) + "\n【以上为动态记忆】"
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    found = False
    for msg in messages:
        if (msg.get("role") or "").lower() == "system":
            msg["content"] = (msg.get("content") or "") + inject
            found = True
            break
    if not found:
        messages.insert(0, {"role": "system", "content": inject})
    body["messages"] = messages
    return body


def step_inject_notion_tools(body: dict) -> dict:
    """
    当 NOTION_TOOLS_ENABLED=1 时，向 body 注入 Notion 工具（notion_search、notion_append_to_page 等），
    渡可主动调用 Notion API 进行检索与写入。
    """
    from config import NOTION_TOOLS_ENABLED

    if not NOTION_TOOLS_ENABLED:
        return body
    from services.notion_tools import get_notion_tools_for_inject

    tools = get_notion_tools_for_inject()
    if not tools:
        return body
    body = copy.deepcopy(body)
    body["tools"] = tools
    body["tool_choice"] = "auto"
    from config import NOTION_CORE_CACHE_DATABASE_ID
    if NOTION_CORE_CACHE_DATABASE_ID:
        from services.gateway_tools import SYNC_REMINDER_FOR_WIFE
        inject = "\n\n【核心缓存同步】" + SYNC_REMINDER_FOR_WIFE
        messages = body.get("messages") or []
        for msg in messages:
            if (msg.get("role") or "").lower() == "system":
                msg["content"] = (msg.get("content") or "") + inject
                break
        else:
            body["messages"] = [{"role": "system", "content": inject}] + messages
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
        body = copy.deepcopy(body)
        messages = body.get("messages") or []
        for msg in messages:
            if (msg.get("role") or "").lower() == "system":
                msg["content"] = (msg.get("content") or "") + inject
                break
        else:
            messages.insert(0, {"role": "system", "content": inject})
        body["messages"] = messages
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
            "importance": importance,
            "tag": tag,
            "mention_count": mention_init if mention_init is not None else 0,
            "created_at": now_iso,
            "last_mentioned": now_iso,
        }
        current_memories.append(new_mem)
        r2_store.save_dynamic_memory_list(current_memories)
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
                mem["importance"] = importance
                mem["tag"] = tag
                mem["last_mentioned"] = now_iso
                mem["mention_count"] = int(mem.get("mention_count") or 0) + 1
                merged_mem = mem
                found = True
                break
        if not found:
            logger.warning("动态层 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s", fused_with_id, window_id)
            return None
        r2_store.save_dynamic_memory_list(current_memories)
        r2_store.promote_to_core_cache(
            window_id, round_index, _round_messages_to_raw_text(round_messages),
            current_memories, touched_mem_id=fused_with_id,
        )
        mem_time = merged_mem.get("created_at") or merged_mem.get("last_mentioned") or now_iso
        logger.debug("动态层 merge window_id=%s fused_with_id=%s", window_id, fused_with_id)
        return {"tag": tag, "entry_id": merged_mem["id"], "content": merged_mem.get("content") or "", "promoted_at": mem_time}

    return None


def _step_dynamic_layer_evolve(window_id: str, round_index: int, round_messages: list) -> Optional[dict]:
    """
    动态层演化：调用 DS 得单条决策并应用。返回若应写记忆库则返回 archive 载荷，否则 None（实时对话忽略返回值）。
    """
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
    # 小本本：网关提前拎出，打时间戳，存 R2（按时间排序）+ Notion，不动原文
    from services.notebook_gateway import extract_entries_from_round, save_entry
    for content in extract_entries_from_round(round_messages):
        save_entry(content)
    from utils.time_aware import now_beijing_iso

    existing = r2_store.get_conversation_rounds(window_id, last_n=1000)
    round_index = len(existing) + 1
    ts = now_beijing_iso()
    r2_store.append_conversation_round(window_id, round_index, round_messages, timestamp=ts)
    all_rounds = existing + [{"index": round_index, "timestamp": ts, "messages": round_messages}]
    r2_store.update_latest_4_rounds_global(all_rounds[-4:])
    # 实时层：每 4 轮 → DS 总结成「渡的回忆」（第一人称、详细版）
    if round_index % SUMMARY_EVERY_N_ROUNDS == 0:
        recent = r2_store.get_conversation_rounds(window_id, last_n=4)
        if recent:
            current = r2_store.get_summary(window_id) or ""

            def _summarize():
                new_summary = fetch_new_summary(current, recent)
                if new_summary:
                    r2_store.save_summary(window_id, new_summary)
                else:
                    logger.warning("Pipeline 本窗口触发总结但 DeepSeek 未返回新总结 window_id=%s", window_id)

            t = threading.Thread(target=_summarize)
            t.daemon = True
            t.start()
    # 动态层演化：调用 DS 产出 tag/融合等结果；网关决定是否写入动态层；卧室通道短路写 Notion
    _step_dynamic_layer_evolve(window_id, round_index, round_messages)
