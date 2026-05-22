import json
import re
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from services.wenyou.constants import _WENYOU_DEFAULT_ABILITIES
from utils.log import get_logger


logger = get_logger(__name__)


def _normalize_ability_definition(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    raw_id = str(raw.get("id") or raw.get("name") or "ability").strip().lower()
    ability_id = re.sub(r"[^a-z0-9_\u4e00-\u9fff-]+", "_", raw_id).strip("_")[:80] or "ability"
    name = str(raw.get("name") or "").strip()
    if not ability_id or not name:
        return None
    uses = raw.get("uses") if isinstance(raw.get("uses"), dict) else {}
    unlock = raw.get("unlock") if isinstance(raw.get("unlock"), dict) else {}
    rarity = str(raw.get("rarity") or unlock.get("rank_min") or "D").strip().upper()
    if rarity not in {"D", "C", "B", "A", "S"}:
        rarity = "D"
    rank_min = str(unlock.get("rank_min") or raw.get("rank_min") or rarity).strip().upper()
    if rank_min not in {"D", "C", "B", "A", "S"}:
        rank_min = rarity
    tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    return {
        "id": ability_id,
        "name": name[:80],
        "rarity": rarity,
        "slot_type": str(raw.get("slot_type") or "active").strip()[:40] or "active",
        "uses_per_instance": max(1, int(raw.get("uses_per_instance") or uses.get("per_instance") or 1)),
        "cooldown_instances": max(0, int(raw.get("cooldown_instances") or uses.get("cooldown_instances") or uses.get("cooldown") or 0)),
        "rank_min": rank_min,
        "desc": str(raw.get("desc") or raw.get("description") or raw.get("effect") or "").strip()[:260],
        "tags": [str(x).strip()[:40] for x in tags if str(x).strip()][:12],
        "effect_json": raw.get("effect_json") if isinstance(raw.get("effect_json"), dict) else {},
    }


def _load_content_ability_catalog() -> dict[str, dict[str, Any]]:
    path = Path(BASE_DIR) / "content" / "default" / "abilities.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("文游能力目录加载失败 path=%s err=%s", path, exc)
        return {}
    raw_items = data.get("abilities") if isinstance(data, dict) else data
    if not isinstance(raw_items, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for raw in raw_items:
        item = _normalize_ability_definition(raw)
        if item:
            out[str(item["id"])] = item
    return out


_WENYOU_ABILITY_CATALOG = {**_WENYOU_DEFAULT_ABILITIES, **_load_content_ability_catalog()}
