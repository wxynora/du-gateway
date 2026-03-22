# 设备感知（sense/latest.json）→ 渡的 system 注入。
# 阶段一：仅展示 battery（level / charging / timestamp）；其它 type 可先写入 R2，下阶段再补展示。
# 字段约定见 docs/感知模块方案.md
from __future__ import annotations

from typing import Any

from storage import r2_store
from utils.time_aware import get_exact_time
from utils.log import get_logger

logger = get_logger(__name__)

_MAX_SNAPSHOT_CHARS = 800

_SENSE_INJECT_FOOTER = (
    "【以上为网关汇总的老婆设备侧参考状态（Tasker 电量等上报，非她亲口打字）；"
    "除非自然有用，不要在回复里硬复读电量数字。】"
)


def _as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def format_sense_snapshot_for_system() -> str:
    """
    仅格式化 battery 桶；无有效电量数据时返回空串（不注入）。
    """
    try:
        doc = r2_store.get_sense_latest()
    except Exception as e:
        logger.debug("get_sense_latest 失败（跳过注入） error=%s", e)
        return ""
    if not isinstance(doc, dict) or not doc:
        return ""

    bat = _as_dict(doc.get("battery"))
    if not bat or "level" not in bat:
        return ""

    hm = get_exact_time()
    lines: list[str] = [f"[你的当前状态·{hm}]"]
    lv = bat.get("level")
    ch = bat.get("charging")
    if ch is True or str(ch).lower() in ("true", "1", "yes"):
        lines.append(f"电量：{lv}%，充电中")
    elif ch is False or str(ch).lower() in ("false", "0", "no"):
        lines.append(f"电量：{lv}%，未充电")
    else:
        lines.append(f"电量：{lv}%")

    body = "\n".join(lines) + "\n" + _SENSE_INJECT_FOOTER
    if len(body) > _MAX_SNAPSHOT_CHARS:
        body = body[: _MAX_SNAPSHOT_CHARS - 40] + "\n…\n" + _SENSE_INJECT_FOOTER
    return body
