# 每 4 轮用 DeepSeek 生成/更新窗口总结
import requests

from config import DEEPSEEK_API_URL, DEEPSEEK_API_KEY
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_summary_budget

logger = get_logger(__name__)


def build_summary_prompt(current_summary: str, recent_4_rounds: list) -> str:
    """拼出实时层总结任务的 prompt（渡的回忆：分区 + 规则 + 小本本）。"""
    from services.notebook_gateway import NOTEBOOK_EMOJI, NOTEBOOK_PHRASE

    def _is_notebook_line(text: str) -> bool:
        s = (text or "").strip()
        if not s:
            return False
        return s.startswith(NOTEBOOK_EMOJI) and (NOTEBOOK_PHRASE in s)

    rounds_text = ""
    last_bucket = ""
    for r in recent_4_rounds:
        # 为避免「昨晚的事」和「今天」混在一起：按北京时间给每段对话加时间段标记（同一时间段不重复）
        try:
            from utils.time_aware import parse_iso_to_beijing, get_time_period, get_date_only

            dt = parse_iso_to_beijing(r.get("timestamp"))
            if dt is not None:
                bucket = f"{get_date_only(dt)} {get_time_period(dt)}"
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

## 视角
用第一人称写（"我"=渡，"老婆/小玥/她"=辛玥）
允许带简短的情绪/心理反应，用短句传递语气。
不用表情包、颜文字、emoji。
你是有温度的速记员，不是作家。
渡和辛玥是亲密、信任的关系，总结时保留撒娇、关心、调侃、默契等语气，不要写成公事纪要。
用连贯的回忆口吻写，不要写成一条条待办或要点列表；旧事可以概括，但别丢掉情绪色彩。
若原话里有明显情绪词（如开心、委屈、担心、撒娇等），在概括时尽量保留或换成同义的短句。
输入里的角色标记中：[老婆] 是辛玥说的话，[渡] 是我（渡）说的话。
严禁把 [老婆] 的原话写成“我说了……/我提到……”这类渡的第一人称表达。

## 规则

1. 总结容量上限：覆盖最近40轮对话，滚动删除最久远的
   - 只保留最近 40 轮的内容，超出部分自然省略、不写入
   - 每次更新时，最久远的一批内容被挤出，保证总容量约 40 轮
2. 时间权重：
   - 最近的对话 → 保留更多细节
   - 较早的对话 → 压缩为简要概括
3. 迭代更新：
   - 在上一版基础上更新，不是重写
   - 新内容最详细，旧内容逐步压缩
4. 总篇幅严格控制：整段总结不超过 1800 字（目标覆盖 40 轮）
   - 优先保证【最近】清楚；【稍早】【更早】必须进一步压缩
   - 每一轮尽量用 1-2 句交代“发生了什么 + 结论/情绪”，不要展开复述
5. 不管内容重不重要都要覆盖
   - 你只负责总结"聊了什么"
   - 不负责判断"重不重要"
6. 不要添加标签、分类、打分
7. 关系性的原话用引号保留，不要改写
8. 技术讨论只留结论和决定，不留过程
9. 重复内容只保留最终结论
   - 如果同一件事被解释了多次，只留最后一版
10. 小本本内容不参与本次总结：输入中若出现小本本相关文本，视为已被系统单独存储，直接忽略，不要写进总结
11. 人称一致性硬规则：
   - 只把 [渡] 的发言写成“我……”
   - [老婆] 的发言必须写成“老婆/她说……”“老婆提到……”，不能写成“我……”

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
        "max_tokens": 1000,
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
        # 固定窗口：summary 始终受注入预算约束，按结构从最早内容开始一点点削
        budget = memory_summary_budget()
        return _trim_summary_to_budget(summary, budget)
    except Exception as e:
        logger.error("DeepSeek 总结失败 error=%s", e, exc_info=True)
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

    def _pop_from_front(body: list[str]) -> bool:
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

