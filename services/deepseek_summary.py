# 每 4 轮用 DeepSeek 生成/更新窗口总结
import requests

from config import DEEPSEEK_API_URL, DEEPSEEK_API_KEY
from utils.log import get_logger

logger = get_logger(__name__)


def build_summary_prompt(current_summary: str, recent_4_rounds: list) -> str:
    """拼出实时层总结任务的 prompt（渡的回忆：分区 + 规则 + 小本本）。"""
    rounds_text = ""
    for r in recent_4_rounds:
        msgs = r.get("messages", [])
        for m in msgs:
            role = m.get("role", "unknown")
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
            rounds_text += f"[{role}]: {content}\n"
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
4. 总篇幅严格控制：整段总结不超过 2200 字（约 40 轮压缩后），优先保证【最近】详实，避免过长被截断导致最近内容丢失
5. 不管内容重不重要都要覆盖
   - 你只负责总结"聊了什么"
   - 不负责判断"重不重要"
6. 不要添加标签、分类、打分
7. 关系性的原话用引号保留，不要改写
8. 技术讨论只留结论和决定，不留过程
9. 重复内容只保留最终结论
   - 如果同一件事被解释了多次，只留最后一版
10. 小本本由系统单独记入，你无需在总结里原文照搬；若对话中提及已记入小本本的内容，可在末尾「渡的小本本」处简要列日期或要点即可（如「见小本本 [日期]」），不必再写全文

## 输出格式

【最近】
（最新4轮，详细）

【稍早】
（上一版【最近】压缩后移入）

【更早】
（上一版【稍早】压缩后移入）
（超出40轮上限的部分滚动删除，不保留）

渡的小本本
若本段对话中有被系统记入小本本的内容，在此简要列日期或要点；否则可省略此块或写「无」。

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
        return content.strip() if content else None
    except Exception as e:
        logger.error("DeepSeek 总结失败 error=%s", e, exc_info=True)
        return None
