import type {
  WenyouCluePanelItem,
  WenyouInventoryItem,
  WenyouPlayerStats,
  WenyouPublicMarker,
  WenyouPublicState,
  WenyouRulesState,
  WenyouSessionPanel,
  WenyouTaskPanelItem,
} from "./types";
import { looksLikeInternalPayload } from "./storyParser";

export function playerDisplayName(player: WenyouPlayerStats | undefined, fallback: string) {
  const name = String(player?.display_name || "").trim();
  return name || fallback;
}

export function replacePlayerAliasText(text: string, playerOneName: string, playerTwoName: string) {
  let out = String(text || "");
  const p1 = String(playerOneName || "").trim();
  const p2 = String(playerTwoName || "").trim();
  if (p1 && p1 !== "玩家一") out = out.replace(/玩家一/g, p1);
  if (p2 && p2 !== "玩家二") out = out.replace(/玩家二/g, p2);
  return out;
}

export function inventoryItemName(item: WenyouInventoryItem | string | undefined): string {
  if (!item) return "";
  return typeof item === "string" ? item : String(item.name || "");
}

export function inventoryItemLabel(item: WenyouInventoryItem | string): string {
  if (typeof item === "string") return item;
  const qty = Number(item.quantity || 1);
  return `${item.name || "未知物品"}${qty > 1 ? ` x${qty}` : ""}`;
}

export function inventoryItemKey(item: WenyouInventoryItem | string, index: number): string {
  if (typeof item === "string") return `${item}-${index}`;
  return String(item.uid || item.id || item.name || index);
}

export function inventoryActionKey(item: WenyouInventoryItem | string): string {
  if (typeof item === "string") return item;
  return String(item.uid || item.id || item.name || "");
}

export function compactPanelText(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    const text = String(value).trim();
    if (!text || looksLikeInternalPayload(text)) return fallback;
    return text;
  }
  return fallback;
}

export function panelObjectStringField(value: unknown, keys: string[]): string {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text.startsWith("{") || !text.endsWith("}")) return "";
  for (const key of keys) {
    const match = text.match(new RegExp(`['"]${key}['"]\\s*:\\s*(['"])([\\s\\S]*?)\\1`));
    if (match?.[2]) return match[2].trim();
  }
  return "";
}

export function itemDisplayDescription(item: { desc?: unknown; effect?: unknown } | unknown): string {
  const source = typeof item === "object" && item !== null
    ? ((item as { desc?: unknown; effect?: unknown }).desc || (item as { desc?: unknown; effect?: unknown }).effect)
    : item;
  const text = compactPanelText(source);
  if (!text) return "";
  const hidden = [
    /^物品形态[:：]/,
    /^时代标签[:：]/,
    /^[a-z_]+_min\s+\d+/i,
    /^rank_min\s+/i,
    /^seal_rank\s+/i,
  ];
  return text
    .split(/[；;]/)
    .map((part) => part.trim())
    .filter((part) => part && !hidden.some((rule) => rule.test(part)))
    .join("；");
}

function requirementLabel(key: string, value: unknown) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return "";
  const labels: Record<string, string> = {
    level_min: "Lv",
    str_min: "力",
    con_min: "体",
    agi_min: "敏",
    int_min: "智",
    spi_min: "精",
    luk_min: "运",
    spi_current_min: "精神力",
  };
  const label = labels[key] || key.replace(/_min$/, "");
  return `${label} ${n}`;
}

export function inventoryRequirementText(item: WenyouInventoryItem): string {
  const chunks: string[] = [];
  if (item.seal_rank) chunks.push(`${item.seal_rank}阶解封`);
  const req = item.requirements && typeof item.requirements === "object" ? item.requirements : {};
  for (const key of ["level_min", "str_min", "con_min", "agi_min", "int_min", "spi_min", "luk_min", "spi_current_min"]) {
    const label = requirementLabel(key, req[key]);
    if (label) chunks.push(label);
  }
  return chunks.join(" / ");
}

export function inventoryStatusBadges(item: WenyouInventoryItem): string[] {
  const badges: string[] = [];
  if (item.quest_item || item.temporary || item.carry_out === false) badges.push("任务物");
  else badges.push("可带出");
  if (item.sealed) badges.push("封印");
  if (item.unique) badges.push("唯一");
  if (item.bound) badges.push("绑定");
  if (item.broken) badges.push("损坏");
  return badges;
}

export function inventoryMetaText(item: WenyouInventoryItem): string {
  const chunks = [
    item.rarity,
    item.category || item.kind,
    item.uses_left !== undefined ? `次数 ${item.uses_left}` : "",
    item.durability !== undefined ? `耐久 ${item.durability}/${item.durability_max ?? "?"}` : "",
  ].filter(Boolean);
  return chunks.join(" · ");
}

export function inventoryUseBlockLabel(item: WenyouInventoryItem, acting = false): string {
  if (acting) return "演算中";
  if (item.broken) return "损坏";
  if (item.sealed) return "封印中";
  return "使用";
}

export function inventorySellBlockLabel(item: WenyouInventoryItem): string {
  if (item.quest_item || item.temporary || item.carry_out === false) return "不可出售";
  if (item.unique || item.bound) return "不可出售";
  return "出售";
}

export function panelListText(items?: unknown[], fallback = "无"): string {
  if (!Array.isArray(items) || !items.length) return fallback;
  const out = items.map((item) => compactPanelText(item)).filter(Boolean);
  return out.length ? out.join("、") : fallback;
}

export function getSessionPublicState(session: WenyouSessionPanel | null): WenyouPublicState {
  return session?.public_state || session?.public_view || session?.runtime_state?.public_state || {};
}

export function getSessionRulesState(session: WenyouSessionPanel | null): WenyouRulesState {
  return session?.rules_state || session?.runtime_state?.rules_state || {};
}

export function taskTitle(item: WenyouTaskPanelItem): string {
  if (typeof item === "string") {
    const parsed = panelObjectStringField(item, ["title", "current", "goal", "public_text", "text"]);
    return compactPanelText(parsed || item, "任务已同步");
  }
  return compactPanelText(item.title || item.current || item.goal || item.id, "未命名任务");
}

export function taskMeta(item: WenyouTaskPanelItem): string {
  if (typeof item === "string") return looksLikeInternalPayload(item) ? "" : "active";
  const chunks = [item.type, item.status].map((it) => compactPanelText(it)).filter(Boolean);
  const progress = item.progress;
  if (typeof progress === "string" && progress.trim()) chunks.push(progress.trim());
  if (progress && typeof progress === "object") {
    if (progress.text) chunks.push(compactPanelText(progress.text));
    else if (progress.target) chunks.push(`${progress.current ?? 0}/${progress.target}${progress.mode ? ` ${progress.mode}` : ""}`);
  }
  return chunks.join(" · ") || "active";
}

export function clueTitle(item: WenyouCluePanelItem): string {
  if (typeof item === "string") {
    const parsed = panelObjectStringField(item, ["title", "name", "public_text", "text", "id"]);
    return compactPanelText(parsed || item, "线索已记录").slice(0, 42);
  }
  return compactPanelText(item.title || item.public_text || item.text || item.id, "未命名线索");
}

export function clueText(item: WenyouCluePanelItem): string {
  if (typeof item === "string") return compactPanelText(panelObjectStringField(item, ["public_text", "text", "reason", "title", "id"]) || item, "");
  return compactPanelText(item.public_text || item.text || item.source || item.id, "");
}

export function markerTitle(item: WenyouPublicMarker): string {
  if (typeof item === "string") {
    const parsed = panelObjectStringField(item, ["name", "title", "public_text", "text", "id"]);
    return compactPanelText(parsed || item, "记录已同步").slice(0, 42);
  }
  return compactPanelText(item.name || item.title || item.id, "未命名记录");
}

export function markerText(item: WenyouPublicMarker): string {
  if (typeof item === "string") return compactPanelText(panelObjectStringField(item, ["public_text", "text", "desc", "status"]) || item, "");
  return compactPanelText(item.public_text || item.desc || item.blurb || item.status || item.public_status, "");
}

export function markerMeta(item: WenyouPublicMarker): string {
  if (typeof item === "string") return "";
  return [item.type || item.tier, item.rank || item.danger, item.status || item.public_status, item.last_location, item.attitude, item.weakness]
    .map((it) => compactPanelText(it))
    .filter(Boolean)
    .join(" · ");
}

export function currentLocationName(publicState: WenyouPublicState, fallback = "未知区域"): string {
  const first = publicState.known_locations?.[0];
  const cleanFallback = compactPanelText(fallback, "未知区域");
  const genericTitles = new Set(["当前场景", "当前区域", "未命名记录", "未知区域", "current_location"]);
  const title = first ? markerTitle(first) : "";
  const text = first && !genericTitles.has(title) ? markerText(first) : "";
  const raw = title && !genericTitles.has(title)
    ? title
    : text || cleanFallback;
  return raw.replace(/^当前在[:：]?\s*/, "").trim().slice(0, 34) || cleanFallback;
}
