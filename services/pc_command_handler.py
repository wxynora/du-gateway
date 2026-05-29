# 电脑控制 [PCMD:...]：解析、白名单校验、入队；与手机/Tasker 链路隔离
from __future__ import annotations

import ipaddress
import json
import re
from typing import Optional
from urllib.parse import urlparse

from config import PC_OPEN_APP_ALLOWLIST, PC_URL_DOMAIN_ALLOWLIST
from services.du_thought import compute_visible_streaming
from services.du_daily import compute_visible_streaming as compute_daily_visible_streaming
from services.du_vitals import compute_visible_streaming as compute_vitals_visible_streaming
from services.dynamic_memory_citation import compute_visible_streaming as compute_memory_citation_visible_streaming
from services.interaction_memory import compute_visible_streaming as compute_interaction_visible_streaming
from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)

# 仅匹配首个 PCMD 标签（每条回复约定最多一个）
# 兼容中英文括号/冒号与大小写：如 [PCMD:lock]、［pcmd：lock］、【PCMD:lock】
PCMD_TAG_RE = re.compile(r"[\[［【]\s*PCMD\s*[:：]\s*([^\]］】]+)\s*[\]］】]", re.IGNORECASE)

# open: 别名 → 白名单中的规范名（小写）
_OPEN_APP_ALIASES = {
    "记事本": "notepad",
    "微信": "wechat",
}


def _open_app_canonical(name: str) -> str:
    """将用户输入的应用名映射为白名单用的规范名。"""
    t = (name or "").strip()
    if not t:
        return ""
    if t in _OPEN_APP_ALIASES:
        return _OPEN_APP_ALIASES[t]
    return t.strip().lower()


def _domain_allowed(host: str) -> bool:
    """hostname 是否在 PC_URL_DOMAIN_ALLOWLIST 中（含子域）。"""
    h = (host or "").strip().lower().strip(".")
    if not h:
        return False
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return False
    except ValueError:
        pass
    allowed = set(PC_URL_DOMAIN_ALLOWLIST or [])
    if not allowed:
        return False
    for d in allowed:
        d = (d or "").strip().lower().strip(".")
        if not d:
            continue
        if h == d or h.endswith("." + d):
            return True
    return False


def validate_pc_command_for_queue(inner: str) -> Optional[str]:
    """
    校验并归一化 PC 指令，供写入队列；不通过返回 None。
    inner 为 [PCMD: 与 ] 之间的内容，如 lock、open:notepad、url:https://...
    """
    raw = (inner or "").strip()
    if not raw:
        return None
    low = raw.lower()

    if low in ("lock", "shutdown", "restart", "sleep", "mute"):
        return low

    if low.startswith("shutdown:") or low.startswith("restart:"):
        parts = raw.split(":", 1)
        if len(parts) != 2:
            return None
        action = parts[0].strip().lower()
        sec_raw = parts[1].strip()
        if not sec_raw.isdigit():
            return None
        sec = int(sec_raw)
        if 0 <= sec <= 86400:
            return f"{action}:{sec}"
        return None

    if low.startswith("volume:"):
        rest = raw.split(":", 1)[1].strip()
        if not rest.isdigit():
            return None
        n = int(rest)
        if 0 <= n <= 100:
            return f"volume:{n}"
        return None

    if low.startswith("notify:"):
        parts = raw.split(":", 2)
        if len(parts) < 3:
            return None
        title = (parts[1] or "").strip()
        body = (parts[2] or "").strip()
        if not title and not body:
            return None
        if len(title) > 200 or len(body) > 4000:
            return None
        return f"notify:{title}:{body}"

    if low.startswith("open:"):
        rest = raw.split(":", 1)[1].strip() if ":" in raw else ""
        if not rest:
            return None
        app_part = rest
        note_text = ""
        if ":" in rest:
            app_part, note_text = rest.split(":", 1)
            app_part = (app_part or "").strip()
            note_text = (note_text or "").strip()
        canon = _open_app_canonical(app_part)
        allow = {x.strip().lower() for x in (PC_OPEN_APP_ALLOWLIST or []) if x and str(x).strip()}
        if canon and canon in allow:
            if note_text:
                # 仅记事本支持携带预填内容，格式 open:notepad:内容
                if canon != "notepad":
                    return None
                if len(note_text) > 4000:
                    return None
                return f"open:notepad:{note_text}"
            return f"open:{canon}"
        return None

    if low.startswith("url:"):
        url = raw.split(":", 1)[1].strip() if ":" in raw else ""
        if not url:
            return None
        try:
            p = urlparse(url)
        except Exception:
            return None
        if (p.scheme or "").lower() != "https":
            return None
        host = (p.hostname or "").strip().lower()
        if not host or not _domain_allowed(host):
            return None
        return f"url:{url}"

    if low == "media:play":
        return "media:play"

    return None


def strip_first_pcmd_tag(text: str) -> str:
    """去掉首个 [PCMD:...] 标签（不改变其它内容）。"""
    if not text:
        return text
    if not PCMD_TAG_RE.search(text):
        return text
    return PCMD_TAG_RE.sub("", text, count=1).strip()


def process_pcmd_in_assistant_text(text: str) -> tuple[str, bool]:
    """
    从助手正文中解析首个 [PCMD:...]：校验并入队，并从可见文本中移除。
    返回 (可见正文, 是否成功入队)。
    校验失败时仍移除标签，避免把控制串展示给用户。
    """
    if not text or not isinstance(text, str):
        return text or "", False
    m = PCMD_TAG_RE.search(text)
    if not m:
        return text, False
    inner = (m.group(1) or "").strip()
    normalized = validate_pc_command_for_queue(inner)
    visible = PCMD_TAG_RE.sub("", text, count=1).strip()
    if not normalized:
        logger.info("PCMD 校验未通过，已跳过入队 inner=%s", inner[:120])
        return visible, False
    try:
        item = r2_store.append_pc_command(normalized)
        if item:
            logger.info("PCMD 已入队 id=%s cmd=%s", item.get("id"), normalized[:80])
            return visible, True
    except Exception as e:
        logger.warning("PCMD 入队失败 cmd=%s error=%s", normalized, e)
    return visible, False


def visible_prefix_pcmd(acc: str) -> str:
    """
    流式拼接：去掉已闭合的 [PCMD:...]；若出现未闭合的 [PCMD: 则只展示其之前内容。
    """
    if not acc:
        return ""
    s = acc
    while True:
        m = PCMD_TAG_RE.search(s)
        if not m:
            break
        s = s[: m.start()] + s[m.end() :]
    start = re.search(r"[\[［【]\s*PCMD\s*[:：]", s, flags=re.IGNORECASE)
    if start:
        rest = s[start.end() :]
        if not re.search(r"[\]］】]", rest):
            s = s[: start.start()].rstrip()
    return s


class PcmdDuThoughtStreamState:
    """
    流式 SSE：先按 PCMD 规则隐藏/剥离标签，再应用心事块可见性（与 DuThought 顺序一致）。
    """

    def __init__(self, dynamic_memory_citation_map: Optional[dict] = None) -> None:
        self.raw_acc = ""
        self._last_visible_len = 0
        self.dynamic_memory_citation_map = dynamic_memory_citation_map or {}

    def feed_delta(self, delta_piece: str) -> str:
        self.raw_acc += delta_piece
        after_pcmd = visible_prefix_pcmd(self.raw_acc)
        visible = compute_visible_streaming(after_pcmd)
        visible = compute_vitals_visible_streaming(visible)
        visible = compute_interaction_visible_streaming(visible)
        visible = compute_daily_visible_streaming(visible)
        try:
            from services.conversation_followup import compute_visible_streaming as compute_followup_visible_streaming
            visible = compute_followup_visible_streaming(visible)
        except Exception:
            pass
        visible = compute_memory_citation_visible_streaming(visible, self.dynamic_memory_citation_map)
        out = visible[self._last_visible_len :]
        self._last_visible_len = len(visible)
        return out


def transform_sse_chunk_bytes(chunk: bytes, state: PcmdDuThoughtStreamState) -> bytes:
    """解析 OpenAI 风格 SSE，改写 delta.content（PCMD + 心事）。"""
    try:
        text = chunk.decode("utf-8")
    except Exception:
        return chunk
    lines = text.split("\n")
    out_lines: list[str] = []
    for line in lines:
        if line.startswith("data: ") and line[6:].strip() != "[DONE]":
            payload = line[6:]
            try:
                j = json.loads(payload)
                ch0 = (j.get("choices") or [{}])[0]
                delta = ch0.get("delta") or {}
                c = delta.get("content")
                if c is not None and isinstance(c, str):
                    new_c = state.feed_delta(c)
                    delta["content"] = new_c
                    ch0["delta"] = delta
                    j["choices"][0] = ch0
                    out_lines.append("data: " + json.dumps(j, ensure_ascii=False))
                else:
                    out_lines.append(line)
            except (json.JSONDecodeError, KeyError, TypeError, IndexError):
                out_lines.append(line)
        else:
            out_lines.append(line)
    return "\n".join(out_lines).encode("utf-8")


def strip_pcmd_and_enqueue_from_full_text(full_text: str) -> str:
    """
    对整段助手正文：入队 + 去掉标签（用于流式结束后的存档与非流式兜底）。
    """
    visible, _ = process_pcmd_in_assistant_text(full_text or "")
    return visible
