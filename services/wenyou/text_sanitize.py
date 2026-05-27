import re

from services.wenyou.common import _first_json_object_span


def _strip_event_intent_block(text: str) -> str:
    """Hide backend-only event intent from player-facing history/display."""
    if not text or "【事件意图】" not in text:
        return (text or "").strip()
    marker = "【事件意图】"
    idx = text.find(marker)
    span = _first_json_object_span(text, idx)
    if not span:
        tail = text.find("\n", idx)
        end = len(text) if tail < 0 else tail + 1
    else:
        end = span[1]
    return (text[:idx].rstrip() + "\n" + text[end:].lstrip()).strip()


def _strip_main_god_panel(text: str) -> str:
    """去掉【事件意图】与【主神面板】，供注入与展示叙事。"""
    body = (text or "").split("【主神面板】", 1)[0] if text else ""
    return _strip_event_intent_block(body).strip()


def _strip_player_brief_blocks(text: str) -> str:
    """去掉给面板/线索板读取的备忘块，避免挤进主叙事。"""
    headings = (
        "规则备忘",
        "线索备忘",
        "安全区·威胁备忘",
        "阵营备忘",
        "撤离·物资备忘",
        "身份·嫌疑备忘",
        "时限备忘",
    )
    lines = str(text or "").splitlines()
    out: list[str] = []
    skipping = False
    for raw in lines:
        line = raw.strip()
        if any(f"【{heading}】" in line for heading in headings):
            skipping = True
            continue
        if skipping:
            if not line:
                continue
            if re.match(r"^[-*·\d一二三四五六七八九十]+[、.．:：]\s*", line):
                continue
            if line.startswith(("规则", "线索", "注", "来源", "（来源", "【待验证】", "【疑似", "【已证")):
                continue
            if any(mark in line for mark in ("【待验证】", "【疑似假】", "【已证真】", "待验证", "疑似假", "已证真")) and any(k in line for k in ("规则", "线索", "来源", "注")):
                continue
            skipping = False
        out.append(raw)
    cleaned = "\n".join(out)
    cleaned = re.sub(r"(?m)^\s*[—\-]+\s*主神系统\s*[—\-]+\s*$", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*-{3,}\s*$", "", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
