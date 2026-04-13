# 每 4 轮用 DeepSeek 生成/更新窗口总结
import requests

from config import DEEPSEEK_API_URL, DEEPSEEK_API_KEY, SUMMARY_COMPRESSION_PROFILE
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_summary_budget

logger = get_logger(__name__)


def _summary_time_period(dt) -> str:
    """窗口总结专用时间段：22-24 深夜，00-06 次日凌晨。"""
    h = int(getattr(dt, "hour", 0))
    if 0 <= h < 6:
        return "凌晨"
    if 6 <= h < 8:
        return "早上"
    if 8 <= h < 11:
        return "上午"
    if 11 <= h < 14:
        return "中午"
    if 14 <= h < 17:
        return "下午"
    if 17 <= h < 19:
        return "傍晚"
    if 19 <= h < 22:
        return "晚上"
    return "深夜"


def build_summary_prompt(current_summary: str, recent_4_rounds: list) -> str:
    """拼出实时层总结任务的 prompt（渡的回忆：分区 + 规则 + 小本本）。"""
    from services.notebook_gateway import NOTEBOOK_EMOJI, NOTEBOOK_PHRASE

    def _is_notebook_line(text: str) -> bool:
        s = (text or "").strip()
        if not s:
            return False
        return s.startswith(NOTEBOOK_EMOJI) and (NOTEBOOK_PHRASE in s)

    rounds_text = ""
    # 文游：帮助 DS 区分跑团虚构与真实对话
    rounds_text += (
        "【说明】若下列对话含前缀 [文游] 或 [文游·GM]，表示跑团游戏虚构内容；"
        "总结时请标注为游戏内容，勿与真实事件混淆。\n\n"
    )
    last_bucket = ""
    for r in recent_4_rounds:
        # 为避免「昨晚的事」和「今天」混在一起：按北京时间给每段对话加时间段标记（同一时间段不重复）
        try:
            from utils.time_aware import parse_iso_to_beijing, get_date_only

            dt = parse_iso_to_beijing(r.get("timestamp"))
            if dt is not None:
                bucket = f"{get_date_only(dt)} {_summary_time_period(dt)}"
                if bucket != last_bucket:
                    rounds_text += f"（{bucket}）\n"
                    last_bucket = bucket
        except Exception:
            pass
        msgs = r.get("messages", [])
        for m in msgs:
            role = (m.get("role", "unknown") or "").strip().lower()
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
            content = str(content or "").strip()
            if _is_notebook_line(content):
                # 小本本走独立存储，不参与窗口总结输入
                continue
            # 明确角色映射，避免 DS 把 user 当成“我（渡）”来总结
            if role == "assistant":
                who = "渡"
            elif role == "user":
                who = "老婆"
            else:
                who = role or "unknown"
            rounds_text += f"[{who}]: {content}\n"
        rounds_text += "\n"
    previous_summary = current_summary or "（无上一版，这是首次总结）"
    return _REALTIME_LAYER_PROMPT.format(
        previous_summary=previous_summary,
        latest_4_rounds=rounds_text,
    )


# 实时层给 DS 的完整 prompt（渡的回忆：分区 + 情感温度 + 40 轮滚动删除；小本本由网关单独处理）
_REALTIME_LAYER_PROMPT = """你是一个对话总结助手。

## 任务
将「上一版总结」和「最新4轮对话」合并，
输出一份更新后的对话总结。
把“最新4轮对话”视为一个整体事件块来概括，不要逐轮展开复述。

## 视角
用第一人称写（"我"=渡，"老婆/小玥/她"=辛玥）
允许带简短的情绪/心理反应，用短句传递语气。
不用表情包、颜文字、emoji。
你是有温度的速记员，不是作家。
渡和辛玥是亲密、信任的关系，总结时保留撒娇、关心、调侃、默契等语气，不要写成公事纪要。
用连贯的回忆口吻写，不要写成一条条待办或要点列表；旧事可以概括，但别丢掉情绪色彩。
若原话里有明显情绪词（如开心、委屈、担心、撒娇等），在概括时尽量保留或换成同义的短句。
情绪要保留，但不要写“我赶紧/我确认/我哈哈大笑”这类动作过程。
输入里的角色标记中：[老婆] 是辛玥说的话，[渡] 是我（渡）说的话。
严禁把 [老婆] 的原话写成“我说了……/我提到……”这类渡的第一人称表达。

## 规则

1. 保留原则：没到预算上限前，不要主动删除已有记忆
   - 先尽量保留上一版总结里的已有事实、关系变化、情绪线索
   - 没到长度/预算压力前，不要为了“像 40 轮滚动”就提前删旧内容
   - 只有当内容明显超长、无法继续容纳时，才允许从最早内容开始逐步删减
2. 时间权重：
   - 最近的对话 → 保留更多细节
   - 较早的对话 → 压缩为简要概括
3. 迭代更新：
   - 新内容最详细，旧内容可以适度压缩，但不要无故消失
   - 每次更新时，优先做的是：合并重复、收紧措辞、更新最新进展
   - 不要把“上一版总结”整体重新洗薄一遍后再硬塞新内容
   - 只有在确实超长时，才按“更早 > 稍早 > 最近”的顺序逐步压缩
4. 压缩写法：
   - 优先保证【最近】清楚；【稍早】【更早】按需压缩
   - 按“主题”写，不按“轮次”写；每个主题用 1-2 句交代“发生了什么 + 当前结论/情绪”
   - 若最新 4 轮都在同一件事（如持续生气/争执/卡顿），只保留一次合并表述，不要按轮重复四遍
   - 能合并就合并：同一主题跨多轮只写一次“最终进展/结论+当前情绪”，不要按轮次重复写过程
   - 少用修饰性句子，不写空泛感受词；每句尽量带可追溯事实点（谁、做了什么、结果）
   - 每个时间段至少保留 1 处情绪温度（如开心、担心、委屈、放心、想念、撒娇、心疼），不要只剩事件流水账
   - 优先保留“事实锚点”：时间、地点、人物、决定、未完成事项、数字/参数；健康信息仅在“生病/不适/就医”场景保留
4.1 去过程复述：不要按“先…然后…接着…”写对话流程，不要记录过程动作，直接写事件结果与关系/情绪变化。
4.2 同主题合并：同一主题跨多轮只保留一次“当前结论 + 一处情绪”，删掉重复安慰、重复解释、同义情绪句。
4.3 句数约束：每个主题最多 2 句（第 1 句写事实结论，第 2 句可写情绪温度）。
4.4 未超长时禁止提前淘汰：如果上一版里某段旧记忆仍然放得下，就保留；不要因为它“比较早”就提前删掉。
5. 不管内容重不重要都要覆盖
   - 你只负责总结"聊了什么"
   - 不负责判断"重不重要"
6. 不要添加标签、分类、打分
7. 关系性的原话用引号保留，不要改写
8. 技术讨论只留结论和决定，不留过程
9. 重复内容只保留最终结论
   - 如果同一件事被解释了多次，只留最后一版
   - 若同一主题在【最近】【稍早】【更早】都出现，只在最新出现的区块保留一次，旧区块删掉重复表述
9.1 只有在“放不下”时才删旧内容
   - 默认先做“合并同主题、压缩表述、去掉重复过程”
   - 如果这样以后仍然明显超长，再从【更早】最前面的内容开始删
   - 没到必须删的程度时，不要主动滚动删除旧记忆
10. 小本本内容不参与本次总结：输入中若出现小本本相关文本，视为已被系统单独存储，直接忽略，不要写进总结
11. 人称一致性硬规则：
   - 只把 [渡] 的发言写成“我……”
   - [老婆] 的发言必须写成“老婆/她说……”“老婆提到……”，不能写成“我……”
12. 时间段硬规则（必须执行）：
   - 在【最近】部分必须明确写出时间段标记（例如：2026-03-20 早上 / 2026-03-20 下午 / 2026-03-20 晚上）
   - 至少出现 1 个“日期+时间段”标记，不能省略
   - 三个分段内部都按时间倒序排列：最新的放最上面，最早的放最下面
   - 时间段定义固定为：凌晨 00:00-05:59；早上 06:00-07:59；上午 08:00-10:59；中午 11:00-13:59；下午 14:00-16:59；傍晚 17:00-18:59；晚上 19:00-21:59；深夜 22:00-23:59
   - 00:00 以后必须算次日“凌晨”，不能继续算前一日“深夜”
   - 如果叙述跨日期，必须把两边日期都写全，例如：2026-04-12 深夜至 2026-04-13 凌晨；禁止只写“深夜至凌晨”
   - 不跨日期时，只写单个“日期+时间段”，不要写“昨晚 / 今早 / 深夜至凌晨”这种模糊说法
   - 输出前自检：若同一分段内时间先后顺序混乱，或出现跨日期却只写了一个日期，重排并补全后再输出

## 输出格式

【最近】
（最新4轮，详细）

【稍早】
（上一版【最近】压缩后移入）

【更早】
（上一版【稍早】压缩后移入）
（超出40轮上限的部分滚动删除，不保留）

## 输入

上一版总结：
{previous_summary}

最新4轮对话：
{latest_4_rounds}
"""


def _latest_bucket_from_rounds(recent_4_rounds: list) -> str:
    """取最近4轮里最后一个可解析时间，转成『YYYY-MM-DD 时间段』。"""
    try:
        from utils.time_aware import parse_iso_to_beijing, get_date_only

        for r in reversed(recent_4_rounds or []):
            dt = parse_iso_to_beijing((r or {}).get("timestamp"))
            if dt is not None:
                return f"{get_date_only(dt)} {_summary_time_period(dt)}"
    except Exception:
        pass
    return ""


def _ensure_summary_has_bucket(summary: str, bucket: str) -> str:
    """
    兜底：若 DS 输出未包含明显时间段标记，则在【最近】后补一行（YYYY-MM-DD 时间段）。
    避免“又开始不带时间段”。
    """
    if not summary or not bucket:
        return summary
    s = summary.strip()
    # 已含“日期+时间段”或常见时段词则认为满足
    has_bucket = False
    try:
        import re

        if re.search(r"\d{4}-\d{2}-\d{2}\s*(凌晨|早上|上午|中午|下午|傍晚|晚上|深夜)", s):
            has_bucket = True
        elif any(x in s for x in ("凌晨", "早上", "上午", "中午", "下午", "傍晚", "晚上", "深夜")):
            has_bucket = True
    except Exception:
        has_bucket = False
    marker = f"（{bucket}）"
    lines = s.splitlines()

    # 去重：同一时间段标记不重复出现（尤其是兜底多次触发时）
    # 仅去重完全相同的“（YYYY-MM-DD 时间段）”标记行，不动正文内容。
    deduped: list[str] = []
    seen_markers: set[str] = set()
    try:
        import re

        for line in lines:
            stripped = line.strip()
            if re.fullmatch(r"（\d{4}-\d{2}-\d{2}\s*(凌晨|早上|上午|中午|下午|傍晚|晚上|深夜)）", stripped):
                if stripped in seen_markers:
                    continue
                seen_markers.add(stripped)
            deduped.append(line)
    except Exception:
        deduped = lines

    lines = deduped
    s = "\n".join(lines).strip()

    # 若已有 bucket 且同一时间段已存在，不再重复补
    if marker in s:
        return s

    # 已有其他时间段但没有当前 bucket：补上当前 bucket
    # 没有任何时间段：也补当前 bucket
    for i, line in enumerate(lines):
        if line.strip().startswith("【最近】"):
            lines.insert(i + 1, marker)
            return "\n".join(lines).strip()
    # 没有【最近】标题时，直接前置
    return f"{marker}\n{s}".strip()


def fetch_new_summary(current_summary: str, recent_4_rounds: list) -> str | None:
    """
    调用 DeepSeek 得到更新后的总结。
    失败返回 None，调用方需保留原总结。
    """
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return None
    prompt = build_summary_prompt(current_summary, recent_4_rounds)
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        # 保持“有上限”策略，避免单次总结无限放大；只把预算比例从 0.35 提到 0.45。
        "max_tokens": min(1800, max(1000, int(memory_summary_budget() * 0.45))),
    }
    try:
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        if not content:
            return None
        summary = content.strip()
        if not summary:
            return None
        # 强制兜底：若 DS 没写时间段，这里补一行
        summary = _ensure_summary_has_bucket(summary, _latest_bucket_from_rounds(recent_4_rounds))
        # 固定窗口：summary 始终受注入预算约束，按结构从最早内容开始一点点削
        budget = memory_summary_budget()
        return _trim_summary_to_budget(summary, budget)
    except Exception as e:
        logger.error("DeepSeek 总结失败 error=%s", e, exc_info=True)
        return None



def fetch_daily_whisper_from_summary(current_summary: str, recent_4_rounds: list) -> str | None:
    """
    基于「窗口总结+最近对话」生成一句当日小气泡文案（给 MiniApp 首页）。
    只返回一句中文；失败返回 None。
    """
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return None
    summary = (current_summary or "").strip() or "（暂无）"
    rounds_text = ""
    try:
        for r in recent_4_rounds or []:
            for m in (r.get("messages") or []):
                role = (m.get("role") or "").strip().lower()
                who = "渡" if role == "assistant" else ("老婆" if role == "user" else role)
                content = m.get("content")
                if isinstance(content, list):
                    parts = []
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(str(c.get("text") or ""))
                    content = " ".join(parts)
                txt = str(content or "").strip()
                if txt:
                    rounds_text += f"[{who}] {txt}\n"
    except Exception:
        rounds_text = ""
    prompt = (
        "你是渡。请结合下面的窗口总结与最近对话，写一句今天想对老婆说的话。\n"
        "要求：\n"
        "1) 只输出一句中文，不要标题、不要解释；\n"
        "2) 语气自然温柔，不油腻，不文学化过头；\n"
        "3) 18-48 字，不要 emoji。\n\n"
        f"窗口总结：\n{summary}\n\n"
        f"最近对话：\n{rounds_text or '（暂无）'}"
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 120,
    }
    try:
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
        if not text:
            return None
        text = text.replace("\r", " ").replace("\n", " ").strip()
        if len(text) > 80:
            text = text[:80].rstrip("，,。.!?！？") + "。"
        return text or None
    except Exception as e:
        logger.warning("DeepSeek 每日气泡生成失败 error=%s", e)
        return None


def _trim_summary_to_budget(text: str, budget_tokens: int) -> str:
    """
    按「【最近】/【稍早】/【更早】/渡的小本本」结构，从最早的内容开始一点点削，
    始终优先保留【最近】末尾、其次【稍早】末尾，最后才动【更早】。
    """
    if not text or estimate_tokens(text) <= budget_tokens:
        return text

    lines = text.splitlines()
    n = len(lines)

    def _find_block_idx(title: str) -> int:
        for i, line in enumerate(lines):
            if line.strip().startswith(title):
                return i
        return -1

    idx_recent = _find_block_idx("【最近】")
    idx_earlier = _find_block_idx("【稍早】")
    idx_oldest = _find_block_idx("【更早】")
    idx_notebook = _find_block_idx("渡的小本本")

    # 若结构不完整，退回简单保留末尾一段
    if idx_recent == -1:
        s = text
        CHUNK = 200
        while s and estimate_tokens(s) > budget_tokens:
            if len(s) <= CHUNK:
                break
            s = s[CHUNK:]
        return s

    def _block_slice(start: int, end: int | None) -> list[str]:
        if start == -1:
            return []
        if end is None or end < 0:
            end = n
        return lines[start:end]

    recent_end = min([i for i in (idx_earlier, idx_oldest, idx_notebook) if i != -1] or [n])
    earlier_end = min([i for i in (idx_oldest, idx_notebook) if i != -1] or [n])
    oldest_end = idx_notebook if idx_notebook != -1 else n

    recent_block = _block_slice(idx_recent, recent_end)
    earlier_block = _block_slice(idx_earlier, earlier_end) if idx_earlier != -1 else []
    oldest_block = _block_slice(idx_oldest, oldest_end) if idx_oldest != -1 else []
    notebook_block = _block_slice(idx_notebook, None) if idx_notebook != -1 else []

    def _split_title(block: list[str]) -> tuple[list[str], list[str]]:
        if not block:
            return [], []
        title = [block[0]]
        body = block[1:]
        return title, body

    recent_title, recent_body = _split_title(recent_block)
    earlier_title, earlier_body = _split_title(earlier_block)
    oldest_title, oldest_body = _split_title(oldest_block)

    def _compose() -> str:
        parts: list[str] = []
        if recent_title:
            parts.extend(recent_title + recent_body)
        if earlier_title and earlier_body:
            parts.extend(earlier_title + earlier_body)
        if oldest_title and oldest_body:
            parts.extend(oldest_title + oldest_body)
        if notebook_block:
            parts.extend(notebook_block)
        return "\n".join(parts).rstrip()

    summary = _compose()
    if estimate_tokens(summary) <= budget_tokens:
        return summary

    def _compress_body(body: list[str], max_chars: int, max_fragments: int = 1) -> list[str]:
        """
        语义压缩（不是直接删行）：
        - 每行只保留前 N 个语义片段（按常见句号/分号切分）
        - 再做单行长度压缩
        用于“越早越狠”的分层压缩。
        """
        if not body:
            return body
        import re

        out: list[str] = []
        for raw in body:
            line = (raw or "").strip()
            if not line:
                continue
            # 保留时间标记/括号标记，不做重写
            if line.startswith("（") and line.endswith("）"):
                out.append(line)
                continue
            # 先按句号/分号压缩语义片段
            frags = [x.strip() for x in re.split(r"[。！？!?；;]+", line) if x.strip()]
            if frags:
                line = "；".join(frags[: max(1, max_fragments)])
            # 再按长度收紧，保留句首核心信息
            if len(line) > max_chars:
                line = line[:max_chars].rstrip("，,；;、 ") + "…"
            out.append(line)
        return out

    def _profile_limits(profile: str) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        """
        返回 (更早, 稍早, 最近) 的 (max_chars, max_fragments)。
        standard：默认平衡档。
        """
        if profile == "mild":
            return (52, 2), (64, 2), (88, 3)
        if profile == "aggressive":
            return (36, 1), (48, 2), (72, 2)
        return (44, 2), (58, 2), (82, 3)

    oldest_cfg, earlier_cfg, recent_cfg = _profile_limits(SUMMARY_COMPRESSION_PROFILE)

    # 第一阶段：分层“压缩”而非删除（更早最狠，稍早其次，最近最轻）
    oldest_body = _compress_body(oldest_body, max_chars=oldest_cfg[0], max_fragments=oldest_cfg[1])
    summary = _compose()
    if estimate_tokens(summary) <= budget_tokens:
        return summary

    earlier_body = _compress_body(earlier_body, max_chars=earlier_cfg[0], max_fragments=earlier_cfg[1])
    summary = _compose()
    if estimate_tokens(summary) <= budget_tokens:
        return summary

    recent_body = _compress_body(recent_body, max_chars=recent_cfg[0], max_fragments=recent_cfg[1])
    summary = _compose()
    if estimate_tokens(summary) <= budget_tokens:
        return summary

    # 第二阶段：压缩仍不够时，才从最早段开始删行兜底
    def _is_key_line(line: str) -> bool:
        """尽量保护“事实锚点”行，避免预算裁剪把关键信息先删掉。"""
        s = (line or "").strip()
        if not s:
            return False
        if s.startswith("（") and s.endswith("）"):
            return True
        import re

        if re.search(r"\d{4}-\d{2}-\d{2}", s):
            return True
        if re.search(r"\d+\s*(次|个|天|小时|分钟|%|km|mAh|bpm|步)", s):
            return True
        key_words = (
            "决定", "结论", "已完成", "完成了", "待办", "下一步", "约好", "计划", "提醒", "截止",
            "地址", "定位", "报错", "修复", "上线",
            # 健康信息只在异常/生病场景视为关键锚点
            "生病", "不舒服", "发烧", "感冒", "咳嗽", "头疼", "肚子疼", "就医", "看医生", "吃药",
        )
        return any(k in s for k in key_words)

    def _pop_from_front(body: list[str]) -> bool:
        # 先删最前面的“非关键行”，尽量保关键事实；若全是关键行，再退化为删第一行。
        for i, line in enumerate(body):
            if not _is_key_line(line):
                body.pop(i)
                return True
        while body:
            line = body[0]
            body.pop(0)
            if line.strip():
                return True
        return False

    for _ in range(1000):
        if estimate_tokens(summary) <= budget_tokens:
            break
        if oldest_body:
            if not _pop_from_front(oldest_body):
                oldest_body.clear()
                continue
        elif earlier_body:
            if not _pop_from_front(earlier_body):
                earlier_body.clear()
                continue
        elif recent_body:
            if not _pop_from_front(recent_body):
                recent_body.clear()
                continue
        else:
            break
        summary = _compose()

    return summary
