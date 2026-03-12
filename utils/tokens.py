# 记忆注入用：粗略 token 估算与截断（省 API 且尽量保证连续）
# 中英混合按 1 字/符约 0.5 token 估

from config import MEMORY_INJECTION_MAX_TOKENS, MEMORY_SUMMARY_TOKEN_RATIO


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文为主时约 1 字 0.5 token）。"""
    if not text:
        return 0
    return max(0, int(len(text) * 0.5))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """按 token 上限截断，尽量不截断在句中。"""
    if max_tokens <= 0 or not text:
        return text
    est = estimate_tokens(text)
    if est <= max_tokens:
        return text
    # 目标字符数（近似）
    target_len = max(1, max_tokens * 2)
    if len(text) <= target_len:
        return text
    out = text[:target_len]
    # 尽量在句末截断
    for sep in "。\n！？.!?":
        i = out.rfind(sep)
        if i > target_len // 2:
            return out[: i + 1]
    return out


def memory_summary_budget() -> int:
    """总结可用的 token 预算。"""
    return int(MEMORY_INJECTION_MAX_TOKENS * MEMORY_SUMMARY_TOKEN_RATIO)


def memory_dynamic_budget() -> int:
    """动态层可用的 token 预算。"""
    return MEMORY_INJECTION_MAX_TOKENS - memory_summary_budget()
