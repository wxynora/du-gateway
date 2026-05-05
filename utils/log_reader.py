import os
import time
from collections import deque
from pathlib import Path
from typing import Callable

from utils.log_buffer import tail_lines as tail_buffer_lines
from utils.log_buffer import tail_lines_with_last_idx
from utils.log_buffer import stream_events

TAIL_READ_BLOCK_BYTES = 64 * 1024
TAIL_MAX_SCAN_BYTES = 8 * 1024 * 1024


def resolve_log_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        base_dir = Path(__file__).resolve().parent.parent
        p = base_dir / path
    return str(p)


def tail_file_lines(
    path: str,
    lines: int = 200,
    encoding: str = "utf-8",
    line_filter: Callable[[str], bool] | None = None,
) -> list[str]:
    """
    读取文件末尾 N 行。
    - 目标场景：gateway.log 通常是 utf-8（或包含少量不可解码字符）
    """
    path = (path or "").strip()
    if not path:
        raise FileNotFoundError("empty path")
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    want = max(1, int(lines))
    matched = deque(maxlen=want)
    pending = b""
    scanned = 0
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        while pos > 0 and len(matched) < want and scanned < TAIL_MAX_SCAN_BYTES:
            size = min(TAIL_READ_BLOCK_BYTES, pos, TAIL_MAX_SCAN_BYTES - scanned)
            if size <= 0:
                break
            pos -= size
            f.seek(pos)
            block = f.read(size)
            scanned += len(block)
            parts = (block + pending).splitlines()
            if pos > 0 and parts:
                pending = parts.pop(0)
            else:
                pending = b""
            for raw in reversed(parts):
                text = raw.decode(encoding, errors="replace").rstrip("\n")
                if line_filter and not line_filter(text):
                    continue
                matched.appendleft(text)
                if len(matched) >= want:
                    break
        if len(matched) < want and pending:
            text = pending.decode(encoding, errors="replace").rstrip("\n")
            if not line_filter or line_filter(text):
                matched.appendleft(text)
    return list(matched)


def stream_file_tail_sse(path: str, start_lines: int = 80, poll_interval_s: float = 0.5):
    """
    以 SSE 形式持续推送文件追加内容（类 tail -f）。
    事件格式：data: <line>\n\n  （每行一条，客户端自行拼接）
    """
    path = (path or "").strip()
    if not path:
        yield b"data: [log] empty path\n\n"
        return
    if not os.path.exists(path):
        yield f"data: [log] file_not_found: {path}\n\n".encode("utf-8")
        return

    # 先补发最后 start_lines 行
    if start_lines and start_lines > 0:
        try:
            for line in tail_file_lines(path, lines=start_lines):
                yield ("data: " + line + "\n\n").encode("utf-8")
        except Exception as e:
            yield f"data: [log] tail_failed: {e}\n\n".encode("utf-8")

    # 持续跟随：从文件末尾开始读
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, os.SEEK_END)
        last_heartbeat = time.time()
        while True:
            chunk = f.readline()
            if chunk:
                line = chunk.rstrip("\n")
                yield ("data: " + line + "\n\n").encode("utf-8")
                continue

            # 空闲时心跳，减少某些代理断开
            now = time.time()
            if now - last_heartbeat >= 10:
                yield b": ping\n\n"
                last_heartbeat = now
            time.sleep(max(0.1, float(poll_interval_s)))


def tail_logs(path: str, lines: int = 200, line_filter: Callable[[str], bool] | None = None) -> list[str]:
    """
    日志读取：优先读文件；文件不存在则从进程内 stdout 缓冲读取。
    """
    path = resolve_log_path(path)
    if path:
        p = Path(path)
        if p.exists():
            return tail_file_lines(str(p), lines=lines, line_filter=line_filter)
    out = tail_buffer_lines(lines=lines)
    if line_filter:
        out = [line for line in out if line_filter(line)]
    return out


def stream_logs_sse(
    path: str,
    start_lines: int = 80,
    poll_interval_s: float = 0.5,
    line_filter: Callable[[str], bool] | None = None,
):
    """
    日志流：优先文件 tail；文件不存在则从进程内 stdout 缓冲流式推送。
    事件格式：data: <line>\\n\\n
    """
    path = resolve_log_path(path)
    if path:
        p = Path(path)
        if p.exists():
            for chunk in stream_file_tail_sse(str(p), start_lines=start_lines, poll_interval_s=poll_interval_s):
                if not line_filter or not chunk.startswith(b"data: "):
                    yield chunk
                    continue
                text = chunk.decode("utf-8", errors="replace")
                line = text[6:].rstrip("\n")
                if line_filter(line):
                    yield chunk
        return

    # stdout 缓冲：先补发 last N
    last_lines, last_idx = tail_lines_with_last_idx(lines=start_lines)
    for line in last_lines:
        if not line_filter or line_filter(line):
            yield ("data: " + line + "\n\n").encode("utf-8")

    for typ, payload in stream_events(last_idx=last_idx, poll_timeout_s=poll_interval_s):
        if typ == "ping":
            yield b": ping\n\n"
        else:
            line = str(payload)
            if not line_filter or line_filter(line):
                yield ("data: " + line + "\n\n").encode("utf-8")

