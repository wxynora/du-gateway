# 管道主流程：白名单判断 → 清洗(图片) → 新窗口注入 → 记忆注入 → 转发 → 存档/总结
import copy
import json
import re
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from config import (
    WINDOW_ID_HEADER,
    ADD_TO_WHITELIST_HEADER,
    SUMMARY_EVERY_N_ROUNDS,
    DYNAMIC_MEMORY_DAYS_VALID,
    ASSISTANT_TIME_KEYWORDS,
    ASSISTANT_LUNAR_KEYWORDS,
    REPLY_GAP_THRESHOLD_MINUTES,
    LAST_USER_REPLY_FILE,
)
from storage import whitelist_store, r2_store
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_summary_budget, memory_dynamic_budget, truncate_to_tokens

logger = get_logger(__name__)
from services import image_desc, deepseek_summary
from services.deepseek_summary import fetch_new_summary


def get_window_id(headers: dict, body: Optional[dict] = None) -> str:
    """从请求头或 body 中取窗口 ID。支持 body 里的 id、window_id，或 Headers 的 X-Window-Id。"""
    wid = (headers or {}).get(WINDOW_ID_HEADER) or (headers or {}).get(
        WINDOW_ID_HEADER.lower().replace("-", "_")
    )
    if wid:
        return (wid if isinstance(wid, str) else str(wid)).strip()
    if body:
        for key in ("window_id", "id", "assistant_id"):
            v = body.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def get_assistant_id(headers: dict, body: Optional[dict] = None) -> str:
    """从请求里取 assistant_id（用于「只允许某 assistant_id 走后续进程」的过滤）。"""
    aid = (headers or {}).get("X-Assistant-Id") or (headers or {}).get("x_assistant_id")
    if aid and isinstance(aid, str) and aid.strip():
        return aid.strip()
    if body and isinstance(body.get("assistant_id"), str) and body["assistant_id"].strip():
        return body["assistant_id"].strip()
    return ""


def should_add_to_whitelist(headers: dict) -> bool:
    """是否本请求要求将当前窗口加入白名单。"""
    v = (headers or {}).get(ADD_TO_WHITELIST_HEADER) or (headers or {}).get(
        ADD_TO_WHITELIST_HEADER.lower().replace("-", "_")
    )
    return str(v).lower() in ("true", "1", "yes")


def step_whitelist_and_record(
    window_id: str, headers: dict
) -> tuple[bool, Optional[str]]:
    """
    白名单判断 + 可选加入白名单 + 记录最近窗口。
    返回 (是否走完整流程, 错误信息)。
    """
    # 一键加白名单
    if should_add_to_whitelist(headers):
        whitelist_store.add_to_whitelist(window_id)
    whitelist_store.record_recent_window(window_id)
    in_list = whitelist_store.is_whitelisted(window_id)
    return in_list, None


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
    发给当前窗口渡的清洗：只清 Rikka 预设 + 表情包→文字（图片保持原样）。
    两条流之一：此 body 用于转发给 AI。
    """
    from pipeline.cleaner import clean_message_content_for_forward

    body = copy.deepcopy(body)
    for msg in body.get("messages") or []:
        c = msg.get("content")
        if c is not None:
            msg["content"] = clean_message_content_for_forward(c)
    return body


def step_inject_latest_4_rounds_for_new_window(body: dict, window_id: str) -> dict:
    """
    若是新窗口（R2 中无该窗口历史），从 R2 读取全局「最新四轮」注入到请求。
    注入方式：在 system 或 messages 开头插入一段「近期上下文」。
    """
    if not window_id:
        return body
    if r2_store.has_window_history(window_id):
        return body
    rounds = r2_store.get_latest_4_rounds_global()
    if not rounds:
        return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    # 拼成一段文本，插入到第一条 system 消息末尾，若无 system 则插入一条
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
    context = "\n".join(lines)
    inject = f"\n\n【以下为注入的近期对话上下文（来自其他窗口）】\n{context}\n【以上为注入上下文】"
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
    从 R2 读取全局总结，按 token 预算截断后注入 system 末尾。
    常驻：今日日期（北京时间）+ 当前大概时段；system 加一句「如需知道当前几点，可使用 get_time_info 工具」。
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

    summary = r2_store.get_summary(window_id)
    if not summary or not window_id:
        return body
    budget = memory_summary_budget()
    if estimate_tokens(summary) > budget:
        summary = truncate_to_tokens(summary, budget)
        logger.debug("summary truncated to %s tokens", budget)
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    now = None  # time_aware 内用北京时间
    today = get_date_only(now)
    weekday = get_weekday_cn(now)
    period = get_time_period(now)
    head = f"\n\n今日：{today}（{weekday}），当前大概：{period}\n如需知道当前几点，可使用 get_time_info 工具"

    # 老婆多久没回：读取网关上次收到 user 回复时间（本地持久化，全局一份）
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
        # 更新本次 user 回复时间（以注入时刻为准，全局）
        last_map = dict(last_map or {})
        last_map["last_user_reply_at"] = now_beijing_iso()
        with open(LAST_USER_REPLY_FILE, "w", encoding="utf-8") as f:
            json.dump(last_map, f, ensure_ascii=False)
    except Exception as e:
        logger.debug("reply_gap 注入失败（忽略） error=%s", e)
    last_assistant = _last_assistant_text(body)
    last_lower = (last_assistant or "").lower()
    # 兜底具体时间：渡的上一轮是问句且含 几点/时间/现在
    if ASSISTANT_TIME_KEYWORDS and _is_question_like(last_assistant):
        if any(kw in last_lower for kw in ASSISTANT_TIME_KEYWORDS):
            head += f"\n当前时间：{get_exact_time(now)}"
    # 农历节气宜忌：渡的上一轮含 农历/节气/宜忌/黄历
    if ASSISTANT_LUNAR_KEYWORDS and any(kw in last_lower for kw in ASSISTANT_LUNAR_KEYWORDS):
        head += f"\n{get_lunar_and_terms(now)}"
    inject = f"{head}\n\n【窗口记忆总结】\n{summary}\n【以上为窗口记忆】"
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


def _extract_keywords(text: str) -> list:
    """从当前对话文本中提取简单关键词（用于匹配动态层）。"""
    if not text or not isinstance(text, str):
        return []
    # 按空格、常见标点分词，过滤过短
    parts = re.split(r"[\s,，。！？、；：]+", text)
    keywords = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:  # 至少 2 字符
            keywords.append(p)
        elif len(p) == 1 and "\u4e00" <= p <= "\u9fff":
            keywords.append(p)
    return list(set(keywords))


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
    """
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
    for t in scored:
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


def _step_dynamic_layer_evolve(window_id: str, round_index: int, round_messages: list) -> None:
    """
    动态层演化：调用 DS 得单条决策（tag / action / content / fused_with_id），网关单条应用。
    卧室只看 tag === "卧室"，不写动态层，只写 Notion 卧室。
    """
    from uuid import uuid4

    from services.dynamic_layer_ds import call_dynamic_layer_ds

    current_memories = r2_store.get_dynamic_memory_list()
    current_memories, changed = r2_store.ensure_dynamic_memory_ids(current_memories)
    if changed:
        r2_store.save_dynamic_memory_list(current_memories)

    decision = call_dynamic_layer_ds(round_messages, current_memories)
    tag = (decision.get("tag") or "").strip()
    action = (decision.get("action") or "skip").lower()
    content = (decision.get("content") or "").strip()
    fused_with_id = decision.get("fused_with_id")
    importance = int(decision.get("importance") or 0)

    # 卧室短路：只看 tag，不写动态层，只额外写 Notion 卧室房间
    if tag == "卧室" or "卧室" in tag:
        from services.bedroom_gateway import append_bedroom_raw

        append_bedroom_raw(window_id, round_index, _round_messages_to_raw_text(round_messages))
        logger.info("卧室通道触发 window_id=%s round_index=%s（已写 Notion，跳过动态层）", window_id, round_index)
        return

    from utils.time_aware import now_beijing_iso
    now_iso = now_beijing_iso()

    if action == "new" and content:
        new_mem = {
            "id": str(uuid4()),
            "content": content,
            "importance": importance,
            "tag": tag,
            "mention_count": 0,
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
        return

    if action == "merge":
        if not fused_with_id:
            logger.warning("动态层 merge 未返回 fused_with_id，本轮回退为 skip window_id=%s", window_id)
            return
        found = False
        for mem in current_memories:
            if mem.get("id") == fused_with_id:
                mem["content"] = content if content else mem.get("content", "")
                mem["importance"] = importance
                mem["tag"] = tag
                mem["last_mentioned"] = now_iso
                mem["mention_count"] = int(mem.get("mention_count") or 0) + 1
                found = True
                break
        if not found:
            logger.warning("动态层 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s", fused_with_id, window_id)
            return
        r2_store.save_dynamic_memory_list(current_memories)
        r2_store.promote_to_core_cache(
            window_id, round_index, _round_messages_to_raw_text(round_messages),
            current_memories, touched_mem_id=fused_with_id,
        )
        logger.debug("动态层 merge window_id=%s fused_with_id=%s", window_id, fused_with_id)
        return

    # skip（或 action 无效）：不写动态层


def step_archive_and_maybe_summary(
    window_id: str,
    request_messages: list,
    assistant_message: dict,
    round_cleaned_for_r2: Optional[list] = None,
) -> None:
    """
    存档本轮对话到 R2（完整清洗版）；每 4 轮异步更新实时层「渡的回忆」；动态层演化占位。
    与文档三数据流程一致：① 原文存档（windows/ + conversations/）② 满 4 轮更新实时层 ③ 动态层处理占位。
    round_cleaned_for_r2: 可选，[user_msg_cleaned, assistant_msg_cleaned]。
    """
    if not window_id:
        return
    last_user = None
    for m in request_messages:
        if (m.get("role") or "").lower() == "user":
            last_user = m
    if not last_user or not assistant_message:
        return
    round_messages = round_cleaned_for_r2 if round_cleaned_for_r2 else [last_user, assistant_message]
    # 小本本：网关提前拎出，打时间戳，存 R2（按时间排序）+ Notion，不动原文
    from services.notebook_gateway import extract_entries_from_round, save_entry
    for content in extract_entries_from_round(round_messages):
        save_entry(content)
    existing = r2_store.get_conversation_rounds(window_id, last_n=1000)
    round_index = len(existing) + 1
    r2_store.append_conversation_round(window_id, round_index, round_messages)
    all_rounds = existing + [{"index": round_index, "messages": round_messages}]
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
