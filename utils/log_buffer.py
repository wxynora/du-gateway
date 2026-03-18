import threading
import queue
import time
from collections import deque

# 进程内日志缓冲：用于 gateway.log 不存在时的“fallback_stdio”。
# 只保留最近 N 行，避免内存无限增长。
BUFFER_MAX_LINES = 8000
# SSE 实时推送用队列：超过就丢弃旧消息，保证不会拖垮内存。
QUEUE_MAX_ITEMS = 50000

_lock = threading.Lock()
_deque = deque(maxlen=BUFFER_MAX_LINES)  # list[str]
_queue: queue.Queue[tuple[int, str]] = queue.Queue(maxsize=QUEUE_MAX_ITEMS)
_counter = 0


def add_log_line(line: str) -> int:
    global _counter
    if line is None:
        line = ""
    line = str(line).rstrip("\n")
    with _lock:
        _counter += 1
        idx = _counter
        _deque.append(line)
        try:
            _queue.put_nowait((idx, line))
        except queue.Full:
            # 丢弃：只影响实时流，不影响 tail 接口
            pass
        return idx


def tail_lines(lines: int = 200) -> list[str]:
    n = int(lines or 0)
    if n < 1:
        n = 1
    with _lock:
        return list(_deque)[-n:]


def tail_lines_with_last_idx(lines: int = 200) -> tuple[list[str], int]:
    """返回（最后 N 行文本列表，最后一条的 idx）。"""
    n = int(lines or 0)
    if n < 1:
        n = 1
    with _lock:
        items = list(_deque)[-n:]
        # deque 里目前存的是 str，不存 idx，所以无法严格拿最后 idx
        # 为保证流不重，只能用一个近似方案：直接返回 idx = _counter（全局计数）。
        # 由于我们只做“无文件时的可用 fallback”，这个近似足够。
        return items, int(_counter or 0)


def stream_new_lines(last_idx: int, poll_timeout_s: float = 0.5):
    """
    从 last_idx 之后的日志开始流式产出。
    注意：如果队列丢过日志，last_idx 可能跳过一些 idx，但我们仍只按 idx 递增输出。
    """
    cur = int(last_idx or 0)
    while True:
        try:
            idx, line = _queue.get(timeout=poll_timeout_s)
            if idx > cur:
                cur = idx
                yield line
        except queue.Empty:
            # 让 SSE handler 能发心跳
            continue


def stream_events(last_idx: int, poll_timeout_s: float = 0.5, ping_interval_s: float = 10.0):
    """
    以事件方式流式产出，避免 SSE 空闲断连：
    - 新日志：yield ("data", line)
    - 心跳：yield ("ping", None)
    """
    cur = int(last_idx or 0)
    last_ping = 0.0
    while True:
        try:
            idx, line = _queue.get(timeout=poll_timeout_s)
            if idx > cur:
                cur = idx
                yield ("data", line)
        except queue.Empty:
            now = time.time()
            if not last_ping or now - last_ping >= ping_interval_s:
                last_ping = now
                yield ("ping", None)

