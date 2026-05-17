from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "docs" / "wenyou"
OUT_DIR = ROOT / "content" / "default"
SCHEMA_DIR = ROOT / "schemas"

RARITY_FILES = {
    "D": DOC_DIR / "item_catalog_draft_d.md",
    "C": DOC_DIR / "item_catalog_draft_c.md",
    "B": DOC_DIR / "item_catalog_draft_b.md",
    "A": DOC_DIR / "item_catalog_draft_a.md",
    "S": DOC_DIR / "item_catalog_draft_s.md",
}

VALID_ITEM_TYPES = {
    "consumable",
    "weapon",
    "armor",
    "accessory",
    "equippable_tool",
    "material",
    "special",
}


def split_markdown_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def parse_table(path: Path, rarity: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = split_markdown_row(line)
        if len(cells) < 5:
            continue
        if cells[0] in {"道具名字", "---"} or set(cells[0]) <= {"-", ":"}:
            continue
        price_text = re.sub(r"[^0-9]", "", cells[4])
        rows.append(
            {
                "name": cells[0],
                "rarity": cells[1] or rarity,
                "category": cells[2],
                "effect": cells[3],
                "price": price_text or "0",
            }
        )
    return rows


def parse_item_type(effect: str) -> str:
    if "物品形态：武器" in effect:
        return "weapon"
    if "物品形态：防具" in effect:
        return "armor"
    if "物品形态：饰品" in effect:
        return "accessory"
    if "物品形态：可装备工具" in effect:
        return "equippable_tool"
    if "物品形态：材料" in effect:
        return "material"
    if "物品形态：特殊物" in effect:
        return "special"
    return "consumable"


def parse_era_tags(effect: str) -> list[str]:
    m = re.search(r"时代标签：([^；]+)", effect)
    if not m:
        return ["universal"]
    tags = [x.strip() for x in re.split(r"[/,，、]", m.group(1)) if x.strip()]
    return tags or ["universal"]


def parse_equip_slot(effect: str) -> str | None:
    m = re.search(r"槽位\s+([a-z_]+)", effect)
    return m.group(1) if m else None


def parse_requirements(effect: str) -> dict[str, Any]:
    req: dict[str, Any] = {}
    for key, value in re.findall(r"(str|con|agi|int|spi|spi_current|rank)_min\s*([A-Za-z0-9]+)", effect):
        req[f"{key}_min"] = int(value) if value.isdigit() else value.upper()
    if "只能在安全节点" in effect:
        req["safe_node"] = True
    if "只能在主神空间" in effect or "仅主神空间" in effect:
        req["hub_only"] = True
    return req


def parse_use_cost(effect: str) -> dict[str, Any]:
    cost: dict[str, Any] = {}
    patterns = {
        "san": r"SAN\s*[-－]\s*(\d+)",
        "pollution": r"污染\s*[+＋]\s*(\d+)",
        "fatigue": r"疲劳\s*[+＋]\s*(\d+)",
        "debt": r"债务\s*[+＋]\s*(\d+)",
        "threat_clock": r"威胁时钟\s*[+＋]\s*(\d+)",
        "exposure": r"暴露度\s*[+＋]\s*(\d+)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, effect)
        if m:
            cost[key] = int(m.group(1))
    if "耐久 -1" in effect or "耐久-1" in effect:
        cost["durability"] = 1
    return cost


def parse_effect_json(effect: str) -> dict[str, Any]:
    data: dict[str, Any] = {"text": effect}
    hp = re.search(r"恢复\s*(\d+)\s*HP", effect)
    san = re.search(r"恢复\s*(\d+)\s*SAN", effect)
    spi = re.search(r"spi_current\s*\+(\d+)", effect)
    uses = re.search(r"可用\s*(\d+)\s*次", effect)
    durability = re.search(r"耐久\s*(\d+)", effect)
    if hp:
        data["hp_restore"] = int(hp.group(1))
    if "恢复至 HP 上限" in effect:
        data["hp_full"] = True
    if san:
        data["san_restore"] = int(san.group(1))
    if "恢复至 SAN 上限" in effect:
        data["san_full"] = True
    if spi:
        data["spi_restore"] = int(spi.group(1))
    if uses:
        data["uses"] = int(uses.group(1))
    if durability:
        data["durability"] = int(durability.group(1))
    removes = re.findall(r"移除\s*`([^`]+)`", effect)
    if removes:
        data["remove_conditions"] = removes
    return data


def parse_use_phase(effect: str, item_type: str) -> list[str]:
    if "不可在副本内直接使用" in effect:
        return ["hub", "settlement"]
    if "`settlement`" in effect or "结算时" in effect:
        return ["settlement"]
    phases: list[str] = []
    if "主神空间" in effect:
        phases.append("hub")
    if "安全节点" in effect:
        phases.append("safe_node")
    if phases:
        return phases
    if item_type == "material":
        return ["hub", "settlement"]
    return ["instance", "hub", "settlement"]


def compact_effect(effect: str) -> str:
    text = re.sub(r"物品形态：[^；]+；", "", effect)
    text = re.sub(r"时代标签：[^；]+；", "", text)
    return text.strip("； ")


def sql_quote(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def build_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for rarity, path in RARITY_FILES.items():
        rows = parse_table(path, rarity)
        for index, row in enumerate(rows, start=1):
            name = row["name"]
            if name in seen_names:
                raise ValueError(f"duplicate item name: {name}")
            seen_names.add(name)
            effect = row["effect"]
            item_type = parse_item_type(effect)
            if item_type not in VALID_ITEM_TYPES:
                item_type = "consumable"
            consume = item_type == "consumable" or "一次性" in effect
            if item_type in {"weapon", "armor", "accessory", "equippable_tool", "material"}:
                consume = False
            stackable = item_type in {"consumable", "material"} or "可堆叠" in effect
            item = {
                "id": f"wy_{rarity.lower()}_{index:03d}",
                "name": name,
                "rarity": rarity,
                "category": row["category"],
                "item_type": item_type,
                "equip_slot": parse_equip_slot(effect),
                "effect": compact_effect(effect),
                "effect_json": parse_effect_json(effect),
                "requirements": parse_requirements(effect),
                "use_cost": parse_use_cost(effect),
                "tags": [row["category"].replace("类", ""), item_type],
                "era_tags": parse_era_tags(effect),
                "use_phase": parse_use_phase(effect, item_type),
                "consume": consume,
                "stackable": stackable,
                "shop_allowed": rarity in {"D", "C", "B"},
                "gacha_allowed": True,
                "seal_rank": rarity if rarity in {"A", "S"} else None,
                "price": int(row["price"]),
                "weight": 100,
                "enabled": True,
            }
            items.append(item)
    return items


def write_json(items: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "source": "docs/wenyou/item_catalog_draft_*.md",
        "item_count": len(items),
        "items": items,
    }
    (OUT_DIR / "items.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_schema() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Wenyou Item Catalog",
        "type": "object",
        "required": ["schema_version", "items"],
        "properties": {
            "schema_version": {"type": "integer"},
            "source": {"type": "string"},
            "item_count": {"type": "integer"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "name", "rarity", "category", "item_type", "effect", "price"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "rarity": {"enum": ["D", "C", "B", "A", "S"]},
                        "category": {"type": "string"},
                        "item_type": {"enum": sorted(VALID_ITEM_TYPES)},
                        "equip_slot": {"type": ["string", "null"]},
                        "effect": {"type": "string"},
                        "effect_json": {"type": "object"},
                        "requirements": {"type": "object"},
                        "use_cost": {"type": "object"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "era_tags": {"type": "array", "items": {"type": "string"}},
                        "use_phase": {"type": "array", "items": {"type": "string"}},
                        "consume": {"type": "boolean"},
                        "stackable": {"type": "boolean"},
                        "shop_allowed": {"type": "boolean"},
                        "gacha_allowed": {"type": "boolean"},
                        "seal_rank": {"enum": ["D", "C", "B", "A", "S", None]},
                        "price": {"type": "integer", "minimum": 0},
                        "weight": {"type": "integer", "minimum": 0},
                        "enabled": {"type": "boolean"},
                    },
                },
            },
        },
    }
    (SCHEMA_DIR / "item.schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_sql(items: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "-- Wenyou default item catalog seed. Generated from docs/wenyou/item_catalog_draft_*.md.",
        "CREATE TABLE IF NOT EXISTS item_catalog (",
        "  id TEXT PRIMARY KEY,",
        "  name TEXT NOT NULL,",
        "  rarity TEXT NOT NULL CHECK (rarity IN ('D', 'C', 'B', 'A', 'S')),",
        "  item_type TEXT NOT NULL,",
        "  equip_slot TEXT,",
        "  category TEXT NOT NULL,",
        "  effect_json TEXT NOT NULL,",
        "  requirements_json TEXT NOT NULL DEFAULT '{}',",
        "  use_cost_json TEXT NOT NULL DEFAULT '{}',",
        "  tags_json TEXT NOT NULL DEFAULT '[]',",
        "  era_tags_json TEXT NOT NULL DEFAULT '[\"universal\"]',",
        "  use_phase_json TEXT NOT NULL DEFAULT '[]',",
        "  consume INTEGER NOT NULL DEFAULT 1,",
        "  stackable INTEGER NOT NULL DEFAULT 0,",
        "  shop_allowed INTEGER NOT NULL DEFAULT 0,",
        "  gacha_allowed INTEGER NOT NULL DEFAULT 0,",
        "  seal_rank TEXT,",
        "  price INTEGER NOT NULL DEFAULT 0,",
        "  weight INTEGER NOT NULL DEFAULT 100,",
        "  enabled INTEGER NOT NULL DEFAULT 1,",
        "  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,",
        "  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        ");",
        "CREATE INDEX IF NOT EXISTS idx_item_catalog_shop ON item_catalog (shop_allowed, enabled, rarity);",
        "CREATE INDEX IF NOT EXISTS idx_item_catalog_gacha ON item_catalog (gacha_allowed, enabled, rarity);",
        "CREATE INDEX IF NOT EXISTS idx_item_catalog_category ON item_catalog (category, rarity);",
        "CREATE INDEX IF NOT EXISTS idx_item_catalog_type ON item_catalog (item_type, rarity);",
        "",
    ]
    columns = [
        "id",
        "name",
        "rarity",
        "item_type",
        "equip_slot",
        "category",
        "effect_json",
        "requirements_json",
        "use_cost_json",
        "tags_json",
        "era_tags_json",
        "use_phase_json",
        "consume",
        "stackable",
        "shop_allowed",
        "gacha_allowed",
        "seal_rank",
        "price",
        "weight",
        "enabled",
    ]
    for item in items:
        values = [
            item["id"],
            item["name"],
            item["rarity"],
            item["item_type"],
            item["equip_slot"],
            item["category"],
            json.dumps(item["effect_json"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(item["requirements"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(item["use_cost"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(item["tags"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(item["era_tags"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(item["use_phase"], ensure_ascii=False, separators=(",", ":")),
            item["consume"],
            item["stackable"],
            item["shop_allowed"],
            item["gacha_allowed"],
            item["seal_rank"],
            item["price"],
            item["weight"],
            item["enabled"],
        ]
        lines.append(
            f"INSERT OR REPLACE INTO item_catalog ({', '.join(columns)}) VALUES ({', '.join(sql_quote(v) for v in values)});"
        )
    (OUT_DIR / "item_catalog.sql").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    items = build_items()
    write_json(items)
    write_sql(items)
    write_schema()
    counts: dict[str, int] = {}
    for item in items:
        counts[item["rarity"]] = counts.get(item["rarity"], 0) + 1
    print(json.dumps({"item_count": len(items), "counts": counts}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
