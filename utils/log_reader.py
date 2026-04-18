import os
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Callable

from utils.log_buffer import tail_lines as tail_buffer_lines
from utils.log_buffer import tail_lines_with_last_idx
from utils.log_buffer import stream_events


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

    # 简单实现：顺序读（日志一般不会大到不可接受；后续需要再做反向 seek 优化）
    dq = deque(maxlen=max(1, int(lines)))
    with open(path, "r", encoding=encoding, errors="replace") as f:
        for line in f:
            text = line.rstrip("\n")
            if line_filter and not line_filter(text):
                continue
            dq.append(text)
    return list(dq)


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


def tail_journal_logs(unit: str, lines: int = 200, line_filter: Callable[[str], bool] | None = None) -> list[str]:
    name = str(unit or "").strip()
    if not name:
        raise ValueError("empty systemd unit")
    cmd = ["journalctl", "-u", name, "-n", str(max(1, int(lines))), "--no-pager", "-o", "cat"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise RuntimeError("journalctl not found") from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"journalctl exit={proc.returncode}"
        raise RuntimeError(err)
    out: list[str] = []
    for line in (proc.stdout or "").splitlines():
        text = line.rstrip("\n")
        if line_filter and not line_filter(text):
            continue
        out.append(text)
    return out


def stream_journal_logs_sse(
    unit: str,
    start_lines: int = 80,
    line_filter: Callable[[str], bool] | None = None,
):
    name = str(unit or "").strip()
    if not name:
        yield b"data: [log] empty systemd unit\n\n"
        return
    cmd = ["journalctl", "-u", name, "-n", str(max(0, int(start_lines))), "-f", "--no-pager", "-o", "cat"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        yield b"data: [log] journalctl_not_found\n\n"
        return

    last_heartbeat = time.time()
    try:
        if proc.stdout is None:
            yield b"data: [log] journalctl_no_stdout\n\n"
            return
        while True:
            line = proc.stdout.readline()
            if line:
                text = line.rstrip("\n")
                if not line_filter or line_filter(text):
                    yield ("data: " + text + "\n\n").encode("utf-8")
                last_heartbeat = time.time()
                continue
            if proc.poll() is not None:
                code = proc.returncode or 0
                if code != 0:
                    yield f"data: [log] journalctl_exit={code}\n\n".encode("utf-8")
                return
            now = time.time()
            if now - last_heartbeat >= 10:
                yield b": ping\n\n"
                last_heartbeat = now
            time.sleep(0.2)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


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


def tail_service_logs(unit: str, lines: int = 200, line_filter: Callable[[str], bool] | None = None) -> list[str]:
    return tail_journal_logs(unit, lines=lines, line_filter=line_filter)


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


def stream_service_logs_sse(
    unit: str,
    start_lines: int = 80,
    line_filter: Callable[[str], bool] | None = None,
):
    yield from stream_journal_logs_sse(unit, start_lines=start_lines, line_filter=line_filter)

