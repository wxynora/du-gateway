# 清洗层初筛：识别失败对话 → 整轮作废（老婆问 + 渡的错误回复）不存 R2
# 基础版：长度 + 错误关键词；测试时可追加规则

from config import FAILED_RESPONSE_MIN_LENGTH, FAILED_RESPONSE_ERROR_KEYWORDS


def get_assistant_content_text(message: dict) -> str:
    """从助手端返回的 message 中取出纯文本内容（用于判断是否失败）。"""
    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
            else:
                parts.append(str(c))
        return " ".join(parts).strip()
    return str(content).strip()


def is_failed_response(response: str) -> bool:
    """
    判断是否为失败对话（渡的回复异常/错误）。
    任一命中则视为失败，不存档、不触发总结。
    """
    if not response or not isinstance(response, str):
        return True
    text = response.strip()
    if not text:
        return True

    lower = text.lower()
    has_error_kw = any((kw and kw in lower) for kw in FAILED_RESPONSE_ERROR_KEYWORDS)
    is_too_short = len(text) < FAILED_RESPONSE_MIN_LENGTH

    # 新规则：只有「过短 + 含错误关键词」才判为失败
    # 例如 "嗯。""好。""来。" 属于正常短回复，不应被过滤。
    return bool(is_too_short and has_error_kw)
