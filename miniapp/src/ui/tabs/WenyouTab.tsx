import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type WenyouView = "home" | "selection" | "game" | "archive" | "shop" | "rift";
type WenyouInitialView = WenyouView | "archives" | "hub";
type WenyouPanelView = "局内资料";
type WenyouPanelTab = "任务" | "背包" | "角色";
type WenyouProfileTab = "副本存档" | "背包" | "角色面板";

type WenyouArchiveItem = {
  gameId?: string;
  endedAt?: string;
  instance_code?: string;
  instance_name?: string;
  instance_genre?: string;
  difficulty?: string;
  points?: number;
  player1_name?: string;
  player2_name?: string;
  player1_level?: number;
  player2_level?: number;
  history_count?: number;
};

type WenyouArchiveDetail = {
  gameId?: string;
  endedAt?: string;
  framework?: {
    instance_code?: string;
    instance_name?: string;
    instance_genre?: string;
    difficulty?: string;
    world?: string;
    conflict?: string;
    failure_hint?: string;
    reward_hint?: string;
  };
  history_count?: number;
};

type WenyouStatus = {
  active?: boolean;
  session?: {
    gameId?: string;
    startedAt?: string;
    phase?: string;
    phase_label?: string;
    instance_code?: string;
    instance_name?: string;
    instance_genre?: string;
    difficulty?: string;
  } | null;
};

const PLAYABLE_WENYOU_PHASES = new Set(["candidate_selection", "instance_running"]);

function isPlayableWenyouPhase(phase?: string | null): boolean {
  if (!phase) return true;
  return PLAYABLE_WENYOU_PHASES.has(phase);
}

function isPlayableWenyouStatusSession(session?: WenyouStatus["session"]): boolean {
  return !!session?.gameId && isPlayableWenyouPhase(session.phase);
}

function isPlayableWenyouPanel(session?: WenyouSessionPanel | null): boolean {
  return !!session?.gameId && isPlayableWenyouPhase(session.phase);
}

type WenyouShopItem = {
  id: string;
  name: string;
  kind: string;
  category?: string;
  item_type?: string;
  rarity: string;
  price: number;
  desc: string;
  shop_type?: "regular" | "special";
  sealed?: boolean;
  sealed_reason?: string;
};

type WenyouInventoryItem = {
  uid?: string;
  id?: string;
  name: string;
  kind?: string;
  category?: string;
  rarity?: string;
  effect?: string;
  desc?: string;
  quantity?: number;
  uses_left?: number;
  durability?: number;
  durability_max?: number;
  item_type?: string;
  equip_slot?: string;
  equipped_by?: string;
  equipped_slot?: string;
  broken?: boolean;
  temporary?: boolean;
  quest_item?: boolean;
  carry_out?: boolean;
  sigil?: string;
  sealed?: boolean;
  sealed_reason?: string;
  source?: string;
};

type WenyouShopView = {
  active?: boolean;
  can_buy?: boolean;
  phase?: string;
  phaseLabel?: string;
  points?: number;
  debts?: number;
  inventory?: WenyouInventoryItem[];
  stats?: {
    phase?: string;
    points?: number;
    player1?: WenyouPlayerStats;
    player2?: WenyouPlayerStats;
    inventory?: WenyouInventoryItem[];
  };
  growth?: WenyouGrowthView | null;
  generatedAt?: string;
  items?: WenyouShopItem[];
  shop_state?: {
    regular?: {
      rotation_id?: string;
      refresh_count?: number;
      refresh_limit?: number;
      refresh_cost?: number;
      items?: WenyouShopItem[];
    };
    special?: {
      unlocked?: boolean;
      unlock_rank?: string;
      rotation_id?: string;
      items?: WenyouShopItem[];
    };
  };
};

type EntryScene = {
  name: string;
  code?: string;
  genre?: string;
  difficulty?: string;
};

type InstanceCandidate = {
  id: string;
  title: string;
  instance_genre: string;
  difficulty: string;
  tagline?: string;
  premise?: string;
  core_task?: string;
  survival_hook?: string;
  risk?: string;
  twist?: string;
  tags?: string[];
  estimated_length?: string;
};

type FeedItem = {
  id: string;
  kind: "user" | "system" | "notice" | "loot" | "ai_player";
  text: string;
};

type WenyouHistoryItem = { role?: string; content?: string; timestamp?: string };

type StorySegment = {
  id: string;
  kind: "story" | "system";
  label?: string;
  text: string;
};

type WenyouPlayerStats = {
  hp?: number;
  hp_max?: number;
  san?: number;
  san_max?: number;
  spi_current?: number;
  spi_max?: number;
  level?: number;
  rank?: string;
  exp?: number;
  str?: number;
  con?: number;
  agi?: number;
  int?: number;
  spi?: number;
  luk?: number;
  vit?: number;
  wis?: number;
  evolution?: string;
  evolution_rank?: string;
  evolution_tags?: string[];
  bloodline?: string;
  abilities?: Array<{ id?: string; name?: string; desc?: string; level?: number; rarity?: string; uses_per_instance?: number }>;
  dormant_abilities?: Array<{ id?: string; name?: string; desc?: string; level?: number; rarity?: string }>;
  gear?: Array<string | { name?: string; slot?: string; desc?: string; durability?: number; durability_max?: number; rarity?: string; broken?: boolean }>;
  equipment?: Array<string | { name?: string; slot?: string; desc?: string; durability?: number; durability_max?: number; rarity?: string; broken?: boolean }>;
  weapons?: string[];
  conditions?: string[];
  unspent_attribute_points?: number;
  ability_tokens?: number;
  growth_milestone_tokens?: number;
  physical_attack?: number;
  ranged_attack?: number;
  defense?: number;
  mental_resist?: number;
  initiative?: number;
};

type WenyouPromotionPreview = {
  available?: boolean;
  current_rank?: string;
  target_rank?: string;
  required_level?: number;
  cost?: number;
  attribute_bonus?: number;
  reasons?: string[];
};

type WenyouGrowthPlayer = {
  attributes?: Record<string, number>;
  soft_cap?: number;
  unspent_attribute_points?: number;
  ability_tokens?: number;
  ability_slots?: number;
  abilities?: Array<{ id?: string; name?: string; desc?: string; level?: number; rarity?: string }>;
  dormant_abilities?: Array<{ id?: string; name?: string; desc?: string; level?: number; rarity?: string }>;
  available_abilities?: Array<{ id?: string; name?: string; desc?: string; rarity?: string; known?: boolean; locked?: boolean; fragment_cost?: number }>;
  growth_milestone_tokens?: number;
  evolution?: string;
  evolution_rank?: string;
  evolution_tags?: string[];
  evolution_routes?: Array<{ id?: string; name?: string; tags?: string[]; pollution?: number }>;
  next_evolution_cost?: { points?: number; fragments?: number; level?: number; rank?: string } | null;
  next_level_exp?: number;
  spi_current?: number;
  spi_max?: number;
  promotion?: WenyouPromotionPreview;
};

type WenyouGrowthView = {
  attribute_keys?: string[];
  rank_soft_caps?: Record<string, number>;
  players?: Record<string, WenyouGrowthPlayer>;
};

type WenyouTaskPanelItem = string | {
  id?: string;
  title?: string;
  current?: string;
  goal?: string;
  type?: string;
  status?: string;
  progress?: { current?: number; target?: number; mode?: string; text?: string } | string;
  required_clues?: string[];
  related_clues?: string[];
  fail_forward?: string;
  reward_tags?: string[];
};

type WenyouCluePanelItem = string | {
  id?: string;
  title?: string;
  status?: string;
  verified?: boolean;
  source?: string;
  public_text?: string;
  text?: string;
  related_tasks?: string[];
  leads_to?: string[];
  tags?: string[];
};

type WenyouPublicMarker = string | {
  id?: string;
  name?: string;
  title?: string;
  status?: string;
  public_status?: string;
  public_text?: string;
  desc?: string;
  blurb?: string;
  danger?: string;
  last_location?: string;
  attitude?: string;
  weakness?: string;
  type?: string;
  tier?: string;
  rank?: string;
  stability?: number;
  stability_max?: number;
  seal_progress?: number;
  seal_target?: number;
  weaknesses?: string[];
  counterplay?: string[];
};

type WenyouPublicState = {
  scene_summary?: string;
  visible_rules?: string[];
  public_tasks?: WenyouTaskPanelItem[];
  discovered_clues?: WenyouCluePanelItem[];
  known_locations?: WenyouPublicMarker[];
  visible_npcs?: WenyouPublicMarker[];
  visible_monsters?: WenyouPublicMarker[];
  public_threat?: string;
  last_rules_result?: string;
  forced_notice?: string;
};

type WenyouRulesState = {
  players?: Record<string, WenyouPlayerStats>;
  inventory?: WenyouInventoryItem[];
  equipment?: Array<string | Record<string, unknown>>;
  threat_clocks?: Array<Record<string, unknown>>;
  last_state_patch?: Record<string, unknown> | null;
};

type WenyouSessionPanel = {
  gameId?: string;
  phase?: string;
  phase_label?: string;
  framework?: {
    instance_code?: string;
    instance_name?: string;
    instance_genre?: string;
    genre_note?: string;
    difficulty?: string;
    world?: string;
    conflict?: string;
    failure_hint?: string;
    reward_hint?: string;
    tasker_total?: number;
    player_count?: number;
    npc_taskers?: Array<Record<string, unknown>>;
  };
  task?: {
    current?: string;
    failure_hint?: string;
    reward_hint?: string;
    phase?: string;
  };
  stats?: {
    phase?: string;
    points?: number;
    player1?: WenyouPlayerStats;
    player2?: WenyouPlayerStats;
    inventory?: WenyouInventoryItem[];
  };
  wallet?: { points?: number; debts?: number; total_exp?: number } | null;
  growth?: WenyouGrowthView | null;
  settlement?: Record<string, unknown> | null;
  inventory?: WenyouInventoryItem[];
  clues?: string[];
  public_state?: WenyouPublicState;
  public_view?: WenyouPublicState;
  rules_state?: WenyouRulesState;
  runtime_state?: {
    public_state?: WenyouPublicState;
    rules_state?: WenyouRulesState;
    last_state_patch?: Record<string, unknown> | null;
  };
  clocks?: Array<Record<string, unknown>>;
  last_state_patch?: Record<string, unknown> | null;
  history?: WenyouHistoryItem[];
};

type WenyouSettlementOption = {
  id: string;
  label: string;
  desc?: string;
};

type WenyouSettlementScore = {
  id?: string;
  label?: string;
  score?: number;
  max?: number;
  notes?: string[];
};

type WenyouSettlementPreview = {
  result?: string;
  result_label?: string;
  rating?: string;
  rating_label?: string;
  rating_score?: number;
  rating_source?: string;
  confidence?: string;
  reason?: string;
  history_rounds?: number;
  clue_count?: number;
  event_count?: number;
  score_breakdown?: WenyouSettlementScore[];
  reward?: {
    difficulty?: string;
    gross_points?: number;
    gross_exp?: number;
    base_points?: number;
    base_exp?: number;
    rating_points?: number;
    rating_exp?: number;
    penalty_points?: number;
    reward_rolls?: number;
    points_delta?: number;
    exp_delta?: number;
    wallet_points?: number;
  };
  options?: {
    results?: WenyouSettlementOption[];
    ratings?: WenyouSettlementOption[];
  };
};

type WenyouStoryResponse = {
  ok?: boolean;
  text?: string;
  need_confirm_new_game?: boolean;
  error?: string;
  expanding?: boolean;
  job_id?: string;
  status?: "running" | "done" | "failed" | "confirm" | string;
  session?: WenyouSessionPanel;
};

type RiftRarity = "D" | "C" | "B" | "A" | "S";

type RiftItem = {
  id: string;
  name: string;
  rarity: RiftRarity;
  kind: string;
  desc: string;
  sigil: string;
};

type RiftPullResult = RiftItem & {
  pullId: string;
  uid?: string;
  quantity?: number;
  sealed?: boolean;
  converted?: boolean;
  converted_to?: WenyouInventoryItem;
};

const TYPE_FILTERS = ["全部类型", "规则怪谈", "剧情解密", "大逃杀", "对抗", "生存撤离", "潜伏调查", "限时任务"];
const DIFFICULTY_FILTERS = ["全部难度", "D", "C", "B", "A", "S"];
const ARCHIVE_FILTERS = ["全部", "已完成", "死亡", "放弃", "进行中"];
const PROFILE_TABS: WenyouProfileTab[] = ["副本存档", "背包", "角色面板"];
type QuickAction = {
  label: string;
  text: string;
  encounterAction?: "attack" | "weaken" | "seal" | "escape";
  panelTab?: WenyouPanelTab;
};

const BASE_QUICK_ACTIONS: QuickAction[] = [
  { label: "观察", text: "观察周围环境，留意异常细节。" },
  { label: "检查", text: "检查离我最近的可疑物。" },
  { label: "交谈", text: "尝试和当前场景里的人交谈。" },
  { label: "移动", text: "寻找可以前往的下一个地点。" },
  { label: "背包", text: "打开背包，选择一个合适的物品使用。", panelTab: "背包" },
];

const ENCOUNTER_QUICK_ACTIONS: QuickAction[] = [
  { label: "攻击", text: "攻击当前可见威胁。", encounterAction: "attack" as const },
  { label: "削弱", text: "根据已知线索试探并削弱当前威胁。", encounterAction: "weaken" as const },
  { label: "封印", text: "尝试按规则封印当前威胁。", encounterAction: "seal" as const },
  { label: "逃跑", text: "尝试脱离当前遭遇。", encounterAction: "escape" as const },
];
const ATTRIBUTE_CHOICES = [
  { key: "str", label: "力", hint: "近战、破坏、搬运" },
  { key: "con", label: "体", hint: "生命、抗伤、耐力" },
  { key: "agi", label: "敏", hint: "闪避、潜行、先手" },
  { key: "int", label: "智", hint: "推理、识别、解谜" },
  { key: "spi", label: "精", hint: "精神力、抗污染" },
  { key: "luk", label: "运", hint: "发现隐藏与奖励" },
] as const;
const RIFT_SINGLE_COST = 100;
const RIFT_TEN_COST = 1000;
const STORY_EXPANSION_POLL_MS = 1200;
const STORY_EXPANSION_MAX_POLLS = 160;
function normalizeInitialView(view: WenyouInitialView): WenyouView {
  if (view === "archives") return "archive";
  if (view === "hub") return "home";
  return view;
}

function extractEntryScene(text: string): EntryScene {
  const header = text.match(/【无限流\s*·\s*副本(?:\s*([^｜】\n]+))?(?:｜([^】\n]+))?】/);
  const rawCode = String(header?.[1] || "").trim();
  const rawName = String(header?.[2] || "").trim();
  const name = rawName || rawCode || "未知副本";
  const genre = String(text.match(/【副本类型】([^｜\n]+)/)?.[1] || "").trim();
  const difficulty = String(text.match(/【难度】([DCBAS]|新手|普通|困难|噩梦)/)?.[1] || "").trim();
  return {
    name,
    code: rawName && rawCode ? rawCode : undefined,
    genre: genre || undefined,
    difficulty: difficulty || undefined,
  };
}

function storySystemLabel(raw: string): string | null {
  const label = String(raw || "").trim();
  if (!label) return null;
  if (label.startsWith("无限流")) return "副本接入";
  if (label === "副本类型") return "副本类型";
  if (label === "难度") return "难度";
  if (label.startsWith("新手副本") || label.startsWith("副本 ")) return "系统提示";
  if (label === "主神提示") return "主神提示";
  if (label === "规则结算") return "规则结算";
  if (label === "状态") return "状态";
  if (label === "状态更新") return "状态更新";
  if (label === "遭遇结算") return "遭遇结算";
  if (label === "道具结算" || label === "系统判定") return "系统判定";
  if (label === "任务更新" || label === "获得物品") return label;
  return null;
}

function cleanStorySystemText(text: string) {
  return String(text || "")
    .replace(/^[\s｜|:：。]+/, "")
    .replace(/[\s｜|]+$/, "")
    .trim();
}

function formatStorySystemText(rawLabel: string, content = "") {
  const label = String(rawLabel || "").trim();
  const text = cleanStorySystemText(content);
  if (label.startsWith("无限流")) return label.replace(/｜/g, " | ");
  if (label === "副本类型") return `副本类型：${text || "未知"}`;
  if (label === "难度") return `难度：${text || "-"}`;
  if (label === "状态") return text ? `状态：${text}` : "状态更新";
  return text || label;
}

function pushStorySegment(segments: StorySegment[], text: string) {
  const t = String(text || "").trim();
  if (!t || t === "—— 主神系统 ——" || /^━+$/.test(t)) return;
  const last = segments[segments.length - 1];
  if (last?.kind === "story") {
    last.text = `${last.text}\n${t}`;
    return;
  }
  segments.push({ id: `story-${segments.length}`, kind: "story", text: t });
}

function pushSystemSegment(segments: StorySegment[], label: string, text: string) {
  const body = cleanStorySystemText(text);
  if (!body) return;
  segments.push({ id: `system-${segments.length}`, kind: "system", label, text: body });
}

function knownMarkers(line: string) {
  const matches: Array<{ start: number; end: number; raw: string; label: string }> = [];
  const re = /【([^】]{1,42})】/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(line))) {
    const label = storySystemLabel(match[1]);
    if (label) {
      matches.push({ start: match.index, end: match.index + match[0].length, raw: match[1], label });
    }
  }
  return matches;
}

function formatEntryMetadataBlock(block: string) {
  const lines: string[] = [];
  for (const line of block.split("\n").map((it) => it.trim()).filter(Boolean)) {
    const matches = knownMarkers(line);
    for (let i = 0; i < matches.length; i += 1) {
      const marker = matches[i];
      const next = matches[i + 1]?.start ?? line.length;
      lines.push(formatStorySystemText(marker.raw, line.slice(marker.end, next)));
    }
  }
  return lines.filter(Boolean).join("\n");
}

function splitStoryLine(segments: StorySegment[], line: string) {
  const matches = knownMarkers(line);
  if (!matches.length) {
    pushStorySegment(segments, line);
    return;
  }
  let cursor = 0;
  for (let i = 0; i < matches.length; i += 1) {
    const marker = matches[i];
    const next = matches[i + 1]?.start ?? line.length;
    pushStorySegment(segments, line.slice(cursor, marker.start));
    pushSystemSegment(segments, marker.label, formatStorySystemText(marker.raw, line.slice(marker.end, next)));
    cursor = next;
  }
  pushStorySegment(segments, line.slice(cursor));
}

function parseStorySegments(text: string): StorySegment[] {
  const clean = String(text || "").replace(/\r/g, "").trim();
  if (!clean) return [];
  const segments: StorySegment[] = [];
  for (const rawBlock of clean.split(/\n{2,}/)) {
    const block = rawBlock.trim();
    if (!block || block === "—— 主神系统 ——") continue;
    if (/^━+\n?/.test(block) && block.includes("【状态】")) {
      pushSystemSegment(segments, "状态", block.replace(/^━+\n?/, "").replace(/\n?━+$/, ""));
      continue;
    }
    if (block.startsWith("【无限流") || (block.includes("【副本类型】") && block.includes("【难度】"))) {
      pushSystemSegment(segments, "副本接入", formatEntryMetadataBlock(block));
      continue;
    }
    const lines = block.split("\n").map((it) => it.trim()).filter(Boolean);
    const firstOnlyMarker = lines[0]?.match(/^【([^】]{1,42})】$/);
    const firstLabel = firstOnlyMarker ? storySystemLabel(firstOnlyMarker[1]) : null;
    if (firstOnlyMarker && firstLabel && lines.length > 1) {
      pushSystemSegment(segments, firstLabel, lines.slice(1).join("\n"));
      continue;
    }
    for (const line of lines) splitStoryLine(segments, line);
  }
  return segments.length ? segments : [{ id: "story-0", kind: "story", text: clean }];
}

function feedFromSessionHistory(history?: WenyouHistoryItem[]): FeedItem[] {
  if (!Array.isArray(history)) return [];
  return history
    .map<FeedItem | null>((item, index) => {
      const text = String(item?.content || "").trim();
      if (!text) return null;
      const role = String(item?.role || "").trim().toLowerCase();
      const stamp = String(item?.timestamp || index || "");
      const id = `history-${role || "row"}-${index}-${stamp}`;
      if (role === "player1" || role === "user") {
        return { id, kind: "user" as const, text };
      }
      if (role === "player2" || role === "ai_player") {
        return { id, kind: "ai_player" as const, text };
      }
      return { id, kind: "system" as const, text };
    })
    .filter((item): item is FeedItem => !!item);
}

function difficultyStars(value?: string) {
  const map: Record<string, number> = { 新手: 1, 普通: 2, 困难: 3, 噩梦: 5, D: 1, C: 2, B: 3, A: 4, S: 5 };
  const count = map[String(value || "")] || 3;
  return "★".repeat(count) + "☆".repeat(Math.max(0, 5 - count));
}

function colorClass(value?: string) {
  const key = String(value || "");
  if (key === "S") return "wenyou-chip-gold";
  if (key === "A" || key === "对抗") return "wenyou-chip-rose";
  if (key === "潜伏调查" || key === "规则怪谈") return "wenyou-chip-purple";
  if (key === "D") return "wenyou-chip-white";
  if (key === "生存撤离") return "wenyou-chip-green";
  if (key === "剧情解密" || key === "B") return "wenyou-chip-blue";
  if (key === "大逃杀" || key === "限时任务") return "wenyou-chip-orange";
  return "wenyou-chip-cyan";
}

function Icon({ name }: { name: string }) {
  const common = "h-[18px] w-[18px]";
  if (name === "rift") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 2 4 12l8 10 8-10-8-10Z" /><path d="m12 2-1.4 8.2L4 12M12 22l1.4-8.2L20 12M10.6 10.2h2.8l-1.4 3.6-1.4-3.6Z" /></svg>;
  }
  if (name === "archive") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 4h11a2 2 0 0 1 2 2v14H8a3 3 0 0 1-3-3V5a1 1 0 0 1 1-1Z" /><path d="M8 17h11" /><path d="M9 8h6M9 12h5" /></svg>;
  }
  if (name === "profile") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /><path d="M18 4.5 21 3v5l-3-1.5" /></svg>;
  }
  if (name === "terminal") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="4" y="4" width="16" height="16" rx="2" /><path d="m8 9 3 3-3 3M13 15h3" /></svg>;
  }
  if (name === "arrow") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M7 17 17 7M9 7h8v8" /></svg>;
  }
  if (name === "shop") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M6 7v13h12V7M9 11h6M7 3h10l2 4H5l2-4Z" /></svg>;
  }
  if (name === "play") {
    return <svg className={common} viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7L8 5Z" /></svg>;
  }
  if (name === "list") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></svg>;
  }
  if (name === "x") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12" /></svg>;
  }
  if (name === "plus") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>;
  }
  if (name === "shuffle") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5" /></svg>;
  }
  if (name === "back") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6" /></svg>;
  }
  if (name === "send") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M22 2 11 13" /><path d="m22 2-7 20-4-9-9-4 20-7Z" /></svg>;
  }
  return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></svg>;
}

function riftRarityRank(rarity: RiftRarity) {
  return { D: 1, C: 2, B: 3, A: 4, S: 5 }[rarity];
}

function inventoryItemName(item: WenyouInventoryItem | string | undefined): string {
  if (!item) return "";
  return typeof item === "string" ? item : String(item.name || "");
}

function inventoryItemLabel(item: WenyouInventoryItem | string): string {
  if (typeof item === "string") return item;
  const qty = Number(item.quantity || 1);
  return `${item.name || "未知物品"}${qty > 1 ? ` x${qty}` : ""}${item.sealed ? "（封印）" : ""}`;
}

function inventoryItemKey(item: WenyouInventoryItem | string, index: number): string {
  if (typeof item === "string") return `${item}-${index}`;
  return String(item.uid || item.id || item.name || index);
}

function isGearInventoryItem(item: WenyouInventoryItem | string): item is WenyouInventoryItem {
  if (typeof item === "string") return false;
  const type = String(item.item_type || item.category || "").trim();
  return ["weapon", "armor", "accessory", "equippable_tool"].includes(type) || !!item.equip_slot;
}

function inventoryActionKey(item: WenyouInventoryItem | string): string {
  if (typeof item === "string") return item;
  return String(item.uid || item.id || item.name || "");
}

function normalizeShopView(j: Partial<WenyouShopView>): WenyouShopView {
  return {
    active: !!j.active,
    can_buy: !!j.can_buy,
    phase: String(j.phase || ""),
    phaseLabel: String(j.phaseLabel || ""),
    points: Number(j.points || 0),
    debts: Number(j.debts || 0),
    inventory: Array.isArray(j.inventory) ? j.inventory : [],
    stats: j.stats || undefined,
    growth: j.growth || undefined,
    generatedAt: String(j.generatedAt || ""),
    items: Array.isArray(j.items) ? j.items : [],
    shop_state: j.shop_state || undefined,
  };
}

function compactPanelText(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value).trim() || fallback;
  }
  return fallback;
}

function itemDisplayDescription(item: { desc?: unknown; effect?: unknown } | unknown): string {
  const source = typeof item === "object" && item !== null
    ? ((item as { desc?: unknown; effect?: unknown }).desc || (item as { desc?: unknown; effect?: unknown }).effect)
    : item;
  const text = compactPanelText(source);
  if (!text) return "";
  const hidden = [
    /^槽位\s+/i,
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

function panelListText(items?: unknown[], fallback = "无"): string {
  if (!Array.isArray(items) || !items.length) return fallback;
  const out = items.map((item) => compactPanelText(item)).filter(Boolean);
  return out.length ? out.join("、") : fallback;
}

function getSessionPublicState(session: WenyouSessionPanel | null): WenyouPublicState {
  return session?.public_state || session?.public_view || session?.runtime_state?.public_state || {};
}

function getSessionRulesState(session: WenyouSessionPanel | null): WenyouRulesState {
  return session?.rules_state || session?.runtime_state?.rules_state || {};
}

function taskTitle(item: WenyouTaskPanelItem): string {
  if (typeof item === "string") return item;
  return compactPanelText(item.title || item.current || item.goal || item.id, "未命名任务");
}

function taskMeta(item: WenyouTaskPanelItem): string {
  if (typeof item === "string") return "active";
  const chunks = [item.type, item.status].map((it) => compactPanelText(it)).filter(Boolean);
  const progress = item.progress;
  if (typeof progress === "string" && progress.trim()) chunks.push(progress.trim());
  if (progress && typeof progress === "object") {
    if (progress.text) chunks.push(compactPanelText(progress.text));
    else if (progress.target) chunks.push(`${progress.current ?? 0}/${progress.target}${progress.mode ? ` ${progress.mode}` : ""}`);
  }
  return chunks.join(" · ") || "active";
}

function clueTitle(item: WenyouCluePanelItem): string {
  if (typeof item === "string") return item.slice(0, 42);
  return compactPanelText(item.title || item.public_text || item.text || item.id, "未命名线索");
}

function clueText(item: WenyouCluePanelItem): string {
  if (typeof item === "string") return item;
  return compactPanelText(item.public_text || item.text || item.source || item.id, "");
}

function markerTitle(item: WenyouPublicMarker): string {
  if (typeof item === "string") return item.slice(0, 42);
  return compactPanelText(item.name || item.title || item.id, "未命名记录");
}

function markerText(item: WenyouPublicMarker): string {
  if (typeof item === "string") return item;
  return compactPanelText(item.public_text || item.desc || item.blurb || item.status || item.public_status, "");
}

function markerMeta(item: WenyouPublicMarker): string {
  if (typeof item === "string") return "";
  return [item.type || item.tier, item.rank || item.danger, item.status || item.public_status, item.last_location, item.attitude, item.weakness]
    .map((it) => compactPanelText(it))
    .filter(Boolean)
    .join(" · ");
}

function currentLocationName(publicState: WenyouPublicState, fallback = "未知区域"): string {
  const first = publicState.known_locations?.[0];
  const title = first ? markerTitle(first) : "";
  const text = first ? markerText(first) : "";
  const raw = title && !["当前场景", "未命名记录"].includes(title)
    ? title
    : text || fallback;
  return raw.replace(/^当前在[:：]?\s*/, "").trim().slice(0, 34) || fallback;
}

function gearLabel(item: string | { name?: string; slot?: string; desc?: string }): string {
  if (typeof item === "string") return item;
  return [item.name, item.slot].map((it) => compactPanelText(it)).filter(Boolean).join(" · ") || "未命名装备";
}

function normalizeRiftResult(item: Partial<RiftPullResult>, index: number): RiftPullResult {
  const rarity = String(item.rarity || "D").toUpperCase() as RiftRarity;
  const name = String(item.name || "未知物品");
  return {
    id: String(item.id || item.uid || `rift-${index}`),
    uid: item.uid,
    name,
    rarity: ["D", "C", "B", "A", "S"].includes(rarity) ? rarity : "D",
    kind: String(item.kind || "道具"),
    desc: itemDisplayDescription(item.desc),
    sigil: String(item.sigil || name.slice(0, 4).toUpperCase() || "DATA"),
    pullId: String(item.pullId || item.uid || `rift-${Date.now()}-${index}`),
    quantity: item.quantity,
    sealed: !!item.sealed,
    converted: !!item.converted,
    converted_to: item.converted_to,
  };
}

let riftAudioContext: AudioContext | null = null;

function playRiftShatterSound() {
  if (typeof window === "undefined") return;
  const AudioCtor =
    window.AudioContext ||
    (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtor) return;

  try {
    const ctx = riftAudioContext ?? new AudioCtor();
    riftAudioContext = ctx;
    if (ctx.state === "suspended") void ctx.resume();

    const now = ctx.currentTime + 0.012;
    const master = ctx.createGain();
    master.gain.setValueAtTime(0.0001, now);
    master.gain.exponentialRampToValueAtTime(0.22, now + 0.018);
    master.gain.exponentialRampToValueAtTime(0.0001, now + 0.72);
    master.connect(ctx.destination);

    const noise = (delay: number, duration: number, frequency: number, gainValue: number, type: BiquadFilterType = "bandpass") => {
      const length = Math.max(1, Math.floor(ctx.sampleRate * duration));
      const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < length; i += 1) {
        const fade = 1 - i / length;
        data[i] = (Math.random() * 2 - 1) * fade * fade;
      }
      const source = ctx.createBufferSource();
      const filter = ctx.createBiquadFilter();
      const gain = ctx.createGain();
      source.buffer = buffer;
      filter.type = type;
      filter.frequency.setValueAtTime(frequency, now + delay);
      filter.Q.setValueAtTime(type === "bandpass" ? 1.8 : 0.7, now + delay);
      gain.gain.setValueAtTime(0.0001, now + delay);
      gain.gain.exponentialRampToValueAtTime(gainValue, now + delay + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + delay + duration);
      source.connect(filter);
      filter.connect(gain);
      gain.connect(master);
      source.start(now + delay);
      source.stop(now + delay + duration);
    };

    const tone = (delay: number, frequency: number, duration: number, gainValue: number, type: OscillatorType = "sine") => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(frequency, now + delay);
      osc.frequency.exponentialRampToValueAtTime(Math.max(60, frequency * 0.55), now + delay + duration);
      gain.gain.setValueAtTime(0.0001, now + delay);
      gain.gain.exponentialRampToValueAtTime(gainValue, now + delay + 0.008);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + delay + duration);
      osc.connect(gain);
      gain.connect(master);
      osc.start(now + delay);
      osc.stop(now + delay + duration + 0.02);
    };

    noise(0, 0.12, 720, 0.34, "bandpass");
    noise(0.055, 0.2, 1800, 0.12, "highpass");
    tone(0.01, 118, 0.26, 0.16, "sine");
    tone(0.09, 520, 0.08, 0.045, "triangle");
    tone(0.17, 390, 0.1, 0.035, "sine");
    window.setTimeout(() => master.disconnect(), 980);
  } catch {
    // Audio is non-critical and may be blocked by the WebView.
  }
}

type WenyouBackHandlerRef = React.MutableRefObject<(() => boolean) | null>;

export function WenyouTab({
  initialView = "home",
  backHandlerRef,
  windowId = "",
}: {
  initialView?: WenyouInitialView;
  backHandlerRef?: WenyouBackHandlerRef;
  windowId?: string;
}) {
  const toast = useToast();
  const normalizedInitialView = normalizeInitialView(initialView);
  const [view, setView] = useState<WenyouView>(() => normalizedInitialView);
  const viewRef = useRef<WenyouView>(normalizedInitialView);
  const viewHistoryRef = useRef<WenyouView[]>([]);
  const [spaceBootVisible, setSpaceBootVisible] = useState(() => normalizedInitialView === "home");
  const [spaceBootFading, setSpaceBootFading] = useState(false);
  const [spaceBootProgress, setSpaceBootProgress] = useState(0);
  const [archivesLoading, setArchivesLoading] = useState(false);
  const [archives, setArchives] = useState<WenyouArchiveItem[]>([]);
  const [openGameId, setOpenGameId] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [archiveDetails, setArchiveDetails] = useState<Record<string, WenyouArchiveDetail>>({});
  const [shopLoading, setShopLoading] = useState(false);
  const [shopBuyingId, setShopBuyingId] = useState("");
  const [shop, setShop] = useState<WenyouShopView | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [status, setStatus] = useState<WenyouStatus>({ active: false, session: null });
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesRefreshing, setCandidatesRefreshing] = useState(false);
  const [candidates, setCandidates] = useState<InstanceCandidate[]>([]);
  const [candidateGeneratedAt, setCandidateGeneratedAt] = useState("");
  const [starting, setStarting] = useState(false);
  const [acting, setActing] = useState(false);
  const [settlementLoading, setSettlementLoading] = useState(false);
  const [settlementDraftOpen, setSettlementDraftOpen] = useState(false);
  const [settlementPreview, setSettlementPreview] = useState<WenyouSettlementPreview | null>(null);
  const [settlementResult, setSettlementResult] = useState("");
  const [settlementRating, setSettlementRating] = useState("");
  const [riftOverlay, setRiftOverlay] = useState<"closed" | "opening" | "results">("closed");
  const [riftResults, setRiftResults] = useState<RiftPullResult[]>([]);
  const [riftRevealed, setRiftRevealed] = useState<string[]>([]);
  const [riftPointPreview, setRiftPointPreview] = useState<number | null>(null);
  const [riftPullCount, setRiftPullCount] = useState(0);
  const [riftLoading, setRiftLoading] = useState(false);
  const riftPullTokenRef = useRef(0);
  const settlementAutoArchiveRef = useRef("");
  const [sessionPanel, setSessionPanel] = useState<WenyouSessionPanel | null>(null);
  const [panelView, setPanelView] = useState<WenyouPanelView | null>(null);
  const [panelInitialTab, setPanelInitialTab] = useState<WenyouPanelTab>("任务");
  const [profileTab, setProfileTab] = useState<WenyouProfileTab>("副本存档");
  const [quickDecisionOpen, setQuickDecisionOpen] = useState(false);
  const [entryScene, setEntryScene] = useState<EntryScene | null>(null);
  const [activeScene, setActiveScene] = useState<EntryScene | null>(null);
  const [typeFilter, setTypeFilter] = useState("全部类型");
  const [difficultyFilter, setDifficultyFilter] = useState("全部难度");
  const [archiveFilter, setArchiveFilter] = useState("全部");
  const [search, setSearch] = useState("");
  const [randomOpen, setRandomOpen] = useState(false);
  const [randomDifficulty, setRandomDifficulty] = useState("不限");
  const [randomLength, setRandomLength] = useState("标准");
  const [randomStyle, setRandomStyle] = useState("全随机");
  const [actionText, setActionText] = useState("");
  const [attributePromptPlayer, setAttributePromptPlayer] = useState<"player1" | "player2" | null>(null);
  const [attributePromptDismissedKey, setAttributePromptDismissedKey] = useState("");
  const actionInputRef = useRef<HTMLInputElement | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const initialLoadRef = useRef(false);
  const candidatesAutoLoadRef = useRef(false);
  const gamePanelAutoLoadRef = useRef(false);
  const shopAutoLoadRef = useRef(false);
  const riftAutoLoadRef = useRef(false);

  const pushView = useCallback((next: WenyouView) => {
    setView((prev) => {
      if (prev === next) return prev;
      viewHistoryRef.current = [...viewHistoryRef.current, prev].slice(-12);
      viewRef.current = next;
      return next;
    });
  }, []);

  const resetView = useCallback((next: WenyouView) => {
    viewHistoryRef.current = [];
    viewRef.current = next;
    setView(next);
  }, []);

  const goBackInsideWenyou = useCallback(() => {
    if (riftOverlay !== "closed") {
      riftPullTokenRef.current += 1;
      setRiftOverlay("closed");
      window.setTimeout(() => {
        setRiftResults([]);
        setRiftRevealed([]);
        setRiftPullCount(0);
      }, 260);
      return true;
    }
    if (panelView) {
      setPanelView(null);
      return true;
    }
    if (quickDecisionOpen) {
      setQuickDecisionOpen(false);
      return true;
    }
    if (settlementDraftOpen) {
      setSettlementDraftOpen(false);
      return true;
    }
    if (randomOpen) {
      setRandomOpen(false);
      return true;
    }

    while (viewHistoryRef.current.length) {
      const previous = viewHistoryRef.current.pop();
      if (previous && previous !== viewRef.current) {
        viewRef.current = previous;
        setView(previous);
        return true;
      }
    }

    if (viewRef.current !== normalizedInitialView) {
      viewRef.current = normalizedInitialView;
      setView(normalizedInitialView);
      return true;
    }
    return false;
  }, [normalizedInitialView, panelView, quickDecisionOpen, randomOpen, riftOverlay, settlementDraftOpen]);

  useEffect(() => {
    viewRef.current = view;
    if (view !== "game") {
      setQuickDecisionOpen(false);
    }
  }, [view]);

  useEffect(() => {
    if (!backHandlerRef) return;
    backHandlerRef.current = goBackInsideWenyou;
    return () => {
      if (backHandlerRef.current === goBackInsideWenyou) {
        backHandlerRef.current = null;
      }
    };
  }, [backHandlerRef, goBackInsideWenyou]);

  const loadArchives = useCallback(async () => {
    setArchivesLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; items?: WenyouArchiveItem[]; error?: string }>("/miniapp-api/wenyou/archives?limit=30");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setArchives(Array.isArray(j?.items) ? j.items : []);
    } catch (e: any) {
      toast(`加载已通关副本失败：${e?.message || e}`);
    } finally {
      setArchivesLoading(false);
    }
  }, [toast]);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; active?: boolean; session?: WenyouStatus["session"]; error?: string }>("/miniapp-api/wenyou/status");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      const rawSession = j.session || null;
      const hasPlayableSession = !!j.active && isPlayableWenyouStatusSession(rawSession);
      const nextStatus = { active: hasPlayableSession, session: hasPlayableSession ? rawSession : null };
      setStatus(nextStatus);
      if (nextStatus.active && nextStatus.session?.instance_name) {
        setActiveScene({
          name: nextStatus.session.instance_name || "未命名副本",
          code: nextStatus.session.instance_code || undefined,
          genre: nextStatus.session.instance_genre || undefined,
          difficulty: nextStatus.session.difficulty || undefined,
        });
      } else {
        setActiveScene(null);
      }
    } catch (e: any) {
      toast(`加载系统空间状态失败：${e?.message || e}`);
    } finally {
      setStatusLoading(false);
    }
  }, [toast]);

  const loadCandidates = useCallback(async (refresh = false, keywords = "") => {
    if (refresh) setCandidatesRefreshing(true);
    else setCandidatesLoading(true);
    try {
      const init = refresh
        ? {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ count: 6, keywords }),
          }
        : undefined;
      const j = await apiJson<{ ok?: boolean; items?: InstanceCandidate[]; generatedAt?: string; warning?: string; error?: string }>(
        "/miniapp-api/wenyou/candidates",
        init
      );
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setCandidates(Array.isArray(j.items) ? j.items : []);
      setCandidateGeneratedAt(String(j.generatedAt || ""));
      if (j.warning) toast(j.warning);
    } catch (e: any) {
      toast(`加载副本候选失败：${e?.message || e}`);
    } finally {
      setCandidatesLoading(false);
      setCandidatesRefreshing(false);
    }
  }, [toast]);

  const loadSessionPanel = useCallback(async () => {
    try {
      const j = await apiJson<{ ok?: boolean; active?: boolean; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/session");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      const nextSession = j.active ? (j.session || null) : null;
      const keepSession =
        isPlayableWenyouPanel(nextSession) ||
        (nextSession?.phase === "settlement" && !!nextSession.settlement);
      setSessionPanel(keepSession ? nextSession : null);
      if (keepSession && nextSession?.gameId) {
        setFeed((prev) => (prev.length ? prev : feedFromSessionHistory(nextSession.history)));
      }
      return keepSession ? nextSession : null;
    } catch (e: any) {
      toast(`加载文游面板失败：${e?.message || e}`);
      return null;
    }
  }, [toast]);

  const loadShop = useCallback(async () => {
    setShopLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string } & WenyouShopView>("/miniapp-api/wenyou/shop");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setShop(normalizeShopView(j));
    } catch (e: any) {
      toast(`加载系统商店失败：${e?.message || e}`);
    } finally {
      setShopLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (initialLoadRef.current) return;
    initialLoadRef.current = true;
    loadStatus();
    loadArchives();
    loadShop();
    loadSessionPanel();
  }, [loadArchives, loadSessionPanel, loadShop, loadStatus]);

  useEffect(() => {
    if (!spaceBootVisible) return;
    let width = 0;
    const interval = window.setInterval(() => {
      width = Math.min(100, width + 8 + Math.random() * 12);
      setSpaceBootProgress(width);
      if (width >= 100) {
        window.clearInterval(interval);
        window.setTimeout(() => {
          setSpaceBootFading(true);
          window.setTimeout(() => setSpaceBootVisible(false), 1000);
        }, 500);
      }
    }, 150);
    return () => window.clearInterval(interval);
  }, [spaceBootVisible]);

  useEffect(() => {
    if (view !== "selection") {
      candidatesAutoLoadRef.current = false;
      return;
    }
    if (view === "selection" && !candidates.length && !candidatesLoading) {
      if (candidatesAutoLoadRef.current) return;
      candidatesAutoLoadRef.current = true;
      loadCandidates(false);
    }
  }, [candidates.length, candidatesLoading, loadCandidates, view]);

  useEffect(() => {
    if (view !== "game") {
      gamePanelAutoLoadRef.current = false;
      return;
    }
    if (gamePanelAutoLoadRef.current) return;
    gamePanelAutoLoadRef.current = true;
    loadSessionPanel();
  }, [loadSessionPanel, view]);

  useEffect(() => {
    if (view !== "shop") {
      shopAutoLoadRef.current = false;
      return;
    }
    if (shopAutoLoadRef.current) return;
    shopAutoLoadRef.current = true;
    loadShop();
  }, [loadShop, view]);

  useEffect(() => {
    if (view !== "rift") {
      riftAutoLoadRef.current = false;
      return;
    }
    if (riftAutoLoadRef.current) return;
    riftAutoLoadRef.current = true;
    loadShop();
    loadSessionPanel();
  }, [loadSessionPanel, loadShop, view]);

  useEffect(() => {
    if (!entryScene) return;
    const timer = window.setTimeout(() => setEntryScene(null), 4200);
    return () => window.clearTimeout(timer);
  }, [entryScene]);

  const sortedArchives = useMemo(
    () => (archives || []).slice().sort((a, b) => String(b.endedAt || "").localeCompare(String(a.endedAt || ""))),
    [archives]
  );

  const filteredCandidates = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return candidates.filter((item) => {
      const typeOk = typeFilter === "全部类型" || item.instance_genre === typeFilter;
      const difficultyOk = difficultyFilter === "全部难度" || item.difficulty === difficultyFilter;
      const searchOk = !needle || `${item.title} ${item.instance_genre} ${item.tagline || ""} ${item.premise || ""} ${(item.tags || []).join(" ")}`.toLowerCase().includes(needle);
      return typeOk && difficultyOk && searchOk;
    });
  }, [candidates, difficultyFilter, search, typeFilter]);

  const gamePublicState = getSessionPublicState(sessionPanel);
  const gameRulesState = getSessionRulesState(sessionPanel);
  const profileInventory = shop?.inventory?.length
    ? shop.inventory
    : (gameRulesState.inventory || sessionPanel?.inventory || sessionPanel?.stats?.inventory || []);
  const profileGrowthPlayers = sessionPanel?.growth?.players || shop?.growth?.players || {};
  const profileStats = sessionPanel?.stats || shop?.stats || {};
  const currentLocation = currentLocationName(gamePublicState);
  const hasPlayableStatus = !!status.active && isPlayableWenyouStatusSession(status.session);
  const hasPlayablePanel = isPlayableWenyouPanel(sessionPanel);
  const hasActiveRun = hasPlayableStatus || hasPlayablePanel;
  const currentScene: EntryScene = hasActiveRun
    ? (activeScene || {
        name: status.session?.instance_name || sessionPanel?.framework?.instance_name || "等待接入",
        code: status.session?.instance_code || sessionPanel?.framework?.instance_code || undefined,
        genre: status.session?.instance_genre || sessionPanel?.framework?.instance_genre || undefined,
        difficulty: status.session?.difficulty || sessionPanel?.framework?.difficulty || undefined,
      })
    : {
        name: "等待接入",
        code: undefined,
        genre: undefined,
        difficulty: undefined,
      };
  const gameSettlementReady = sessionPanel?.phase === "settlement" && !!sessionPanel.settlement;
  const homePlayer = sessionPanel?.stats?.player1 || gameRulesState.players?.player1 || {};
  const attributePointEntries = useMemo(() => {
    return (["player1", "player2"] as const)
      .map((player) => {
        const growthPlayer = profileGrowthPlayers[player];
        const statPlayer = profileStats[player];
        const points = Number(growthPlayer?.unspent_attribute_points ?? statPlayer?.unspent_attribute_points ?? 0);
        const level = Number(statPlayer?.level ?? 1);
        const rank = String(statPlayer?.rank || "D");
        return {
          player,
          title: player === "player1" ? "玩家一" : "玩家二 · 渡",
          points: Number.isFinite(points) ? points : 0,
          key: `${player}:${rank}:${level}:${points}`,
        };
      })
      .filter((entry) => entry.points > 0);
  }, [profileGrowthPlayers, profileStats]);
  const activeAttributePrompt = attributePointEntries.find((entry) => entry.player === attributePromptPlayer) || null;
  const gamePlayerAbilities = (sessionPanel?.growth?.players?.player1?.abilities || sessionPanel?.stats?.player1?.abilities || [])
    .map((ability) => ({
      id: String(ability.id || ability.name || ""),
      name: String(ability.name || ability.id || ""),
    }))
    .filter((ability) => ability.id && ability.name)
    .slice(0, 4);
  const homePhase = hasActiveRun ? (sessionPanel?.phase_label || status.session?.phase_label || "副本中") : "主神空间待机";
  const hasVisibleEncounter = (gamePublicState.visible_monsters || []).length > 0;
  const quickActions = useMemo(
    () => hasVisibleEncounter ? [...BASE_QUICK_ACTIONS, ...ENCOUNTER_QUICK_ACTIONS] : BASE_QUICK_ACTIONS,
    [hasVisibleEncounter]
  );
  useEffect(() => {
    if (attributePromptPlayer && attributePointEntries.some((entry) => entry.player === attributePromptPlayer)) return;
    const nextPrompt = attributePointEntries.find((entry) => entry.key !== attributePromptDismissedKey) || null;
    setAttributePromptPlayer(nextPrompt?.player || null);
  }, [attributePointEntries, attributePromptDismissedKey, attributePromptPlayer]);
  const feedTimeLabel = new Date().toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const riftPointRaw = shop?.points ?? sessionPanel?.wallet?.points;
  const riftPoints = riftPointPreview ?? Number(riftPointRaw ?? 0);
  const regularShop = shop?.shop_state?.regular;
  const specialShop = shop?.shop_state?.special;
  const regularShopItems = regularShop?.items?.length ? regularShop.items : (shop?.items || []);
  const specialShopItems = specialShop?.items || [];
  const hubPoints = Number(shop?.points ?? sessionPanel?.wallet?.points ?? sessionPanel?.stats?.points ?? 0);
  const hubDebts = Number(shop?.debts ?? sessionPanel?.wallet?.debts ?? 0);
  const hubRank = String(homePlayer.rank || "E");
  const hubLevel = Number(homePlayer.level ?? 1);
  const hubPointSignal = Math.max(8, Math.min(100, Math.round((hubPoints / 2000) * 100)));
  const hubRankSignal = ({ E: 18, D: 30, C: 46, B: 64, A: 82, S: 100 } as Record<string, number>)[hubRank] || 18;
  const hubStatusLabel = statusLoading
    ? "同步中"
    : hasActiveRun
      ? (homePhase || "副本中")
      : "待机";
  const hubStatusSignal = statusLoading ? 32 : hasActiveRun ? 88 : 56;
  const hubMissionCta = hasActiveRun ? "继续副本" : "选择副本";
  const hubMissionSub = hasActiveRun ? "继续当前副本" : "可接入副本";
  const hubMissionDetail = hasActiveRun
    ? `${currentScene.code || "ACTIVE"} | ${currentScene.difficulty || "?"}`
    : "等待选择副本入口";

  async function buyShopItem(item: WenyouShopItem) {
    if (!item?.id || shopBuyingId) return;
    setShopBuyingId(item.id);
    try {
      const j = await apiJson<{ ok?: boolean; message?: string; error?: string } & WenyouShopView>("/miniapp-api/wenyou/shop/buy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_id: item.id }),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || "购买失败");
      setShop(normalizeShopView(j));
      toast(j.message || `已购买【${item.name}】`);
      await loadSessionPanel();
    } catch (e: any) {
      toast(`购买失败：${e?.message || e}`);
    } finally {
      setShopBuyingId("");
    }
  }

  async function refreshShop() {
    if (shopLoading) return;
    setShopLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; message?: string; error?: string } & WenyouShopView>("/miniapp-api/wenyou/shop/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || "刷新失败");
      setShop(normalizeShopView(j));
      toast(j.message || "商店已刷新");
      await loadSessionPanel();
    } catch (e: any) {
      toast(`刷新失败：${e?.message || e}`);
    } finally {
      setShopLoading(false);
    }
  }

  async function toggleArchive(gameId: string) {
    if (!gameId) return;
    if (openGameId === gameId) {
      setOpenGameId("");
      return;
    }
    setOpenGameId(gameId);
    if (archiveDetails[gameId]) return;
    setDetailLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; archive?: WenyouArchiveDetail; error?: string }>(`/miniapp-api/wenyou/archive/${encodeURIComponent(gameId)}`);
      if (!j?.ok || !j.archive) throw new Error(j?.error || "加载详情失败");
      setArchiveDetails((prev) => ({ ...prev, [gameId]: j.archive as WenyouArchiveDetail }));
    } catch (e: any) {
      toast(`加载副本详情失败：${e?.message || e}`);
    } finally {
      setDetailLoading(false);
    }
  }

  async function waitStoryExpansion(jobId: string): Promise<WenyouStoryResponse> {
    for (let i = 0; i < STORY_EXPANSION_MAX_POLLS; i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, i === 0 ? 500 : STORY_EXPANSION_POLL_MS));
      const j = await apiJson<WenyouStoryResponse>(`/miniapp-api/wenyou/story-job/${encodeURIComponent(jobId)}`);
      if (j.status && j.status !== "running") return j;
    }
    throw new Error("副本扩展仍在进行，请稍后重试或刷新状态");
  }

  async function startStory(mode: "random" | "custom", keywords = "", fallback?: EntryScene, candidate?: InstanceCandidate) {
    if (mode === "custom" && !keywords.trim() && !candidate) {
      toast("请填写任务描述");
      return;
    }
    setStarting(true);
    try {
      let j = await apiJson<WenyouStoryResponse>("/miniapp-api/wenyou/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, keywords: mode === "custom" ? keywords : "", candidate }),
      });
      if (!j?.ok) throw new Error(j?.error || "开局失败");
      if (j.expanding && j.job_id) {
        toast("主神正在并行扩展副本");
        j = await waitStoryExpansion(j.job_id);
        if (!j?.ok) throw new Error(j?.error || "扩展副本失败");
        if (j.status === "failed") throw new Error(j.error || "扩展副本失败");
      }
      const text = String(j?.text || "");
      if (j.need_confirm_new_game) {
        toast("检测到已有进行中副本，请再点一次以确认开新局");
        return;
      }
      const parsed = extractEntryScene(text);
      const scene = parsed.name === "未知副本" && fallback ? fallback : { ...(fallback || {}), ...parsed, name: parsed.name || fallback?.name || "未知副本" };
      setActiveScene(scene);
      setEntryScene(scene);
      setSettlementDraftOpen(false);
      setSettlementPreview(null);
      setSettlementResult("");
      setSettlementRating("");
      setFeed([
        { id: `story-${Date.now()}`, kind: "system", text: text || `欢迎来到 ${scene.name}。` },
      ]);
      resetView("game");
      toast("副本已载入");
      await loadStatus();
      await loadSessionPanel();
      await loadArchives();
    } catch (e: any) {
      toast(`开局失败：${e?.message || e}`);
    } finally {
      setStarting(false);
    }
  }

  function startCandidate(item: InstanceCandidate) {
    startStory("custom", "", { name: item.title, genre: item.instance_genre, difficulty: item.difficulty, code: item.id.toUpperCase() }, item);
  }

  function startRandom() {
    const keywords = [
      "刷新副本候选池。",
      `难度偏好：${randomDifficulty}`,
      `篇幅偏好：${randomLength}`,
      `风格倾向：${randomStyle}`,
      "请生成多条彼此差异明显的轻量候选设定，先不要扩展成完整副本。",
    ].join("\n");
    setRandomOpen(false);
    pushView("selection");
    loadCandidates(true, keywords);
  }

  async function submitAction() {
    const text = actionText.trim();
    if (!text) return;
    setQuickDecisionOpen(false);
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; text?: string; ai_player_action?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, player: "player1", auto_go: true, window_id: windowId }),
      });
      if (!j?.ok) throw new Error(j?.error || "行动失败");
      const gmText = String(j.text || "");
      const aiPlayerAction = String(j.ai_player_action || "").trim();
      const stamp = Date.now();
      setFeed((prev) => [
        ...prev,
        { id: `u-${stamp}`, kind: "user", text },
        ...(aiPlayerAction ? [{ id: `ai-player-${stamp}`, kind: "ai_player" as const, text: aiPlayerAction }] : []),
        { id: `gm-${stamp}`, kind: "system", text: gmText || "主神系统暂无回应。" },
      ]);
      setActionText("");
      setSettlementDraftOpen(false);
      setSettlementPreview(null);
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
    } catch (e: any) {
      toast(`行动失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  async function loadSettlementPreview(result = "", rating = "") {
    if (settlementLoading) return;
    setSettlementLoading(true);
    try {
      const params = new URLSearchParams();
      if (result) params.set("result", result);
      if (rating) params.set("rating", rating);
      const url = `/miniapp-api/wenyou/settlement/preview${params.toString() ? `?${params.toString()}` : ""}`;
      const j = await apiJson<{
        ok?: boolean;
        preview?: WenyouSettlementPreview;
        session?: WenyouSessionPanel;
        error?: string;
      }>(url);
      if (!j?.ok) throw new Error(j?.error || "读取结算失败");
      const preview = j.preview || null;
      setSettlementPreview(preview);
      setSettlementResult(String(preview?.result || ""));
      setSettlementRating(String(preview?.rating || ""));
      setSettlementDraftOpen(true);
      if (j.session) setSessionPanel(j.session);
      return preview;
    } catch (e: any) {
      toast(`读取结算失败：${e?.message || e}`);
      return null;
    } finally {
      setSettlementLoading(false);
    }
  }

  async function changeSettlementResult(result: string) {
    setSettlementResult(result);
    setSettlementRating("");
    await loadSettlementPreview(result, "");
  }

  async function changeSettlementRating(rating: string) {
    setSettlementRating(rating);
    await loadSettlementPreview(settlementResult || settlementPreview?.result || "", rating);
  }

  async function openSettlementDraft() {
    setQuickDecisionOpen(false);
    await loadSettlementPreview();
  }

  async function enterSettlement() {
    if (settlementLoading) return;
    setSettlementLoading(true);
    try {
      const result = settlementResult || settlementPreview?.result || "";
      const rating = settlementRating || settlementPreview?.rating || "";
      const j = await apiJson<{ ok?: boolean; text?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/end", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result, rating }),
      });
      if (!j?.ok) throw new Error(j?.error || "结算失败");
      const text = String(j.text || "本局已归档。");
      toast(text.split("\n", 1)[0] || "本局已归档");
      setFeed((prev) => [...prev, { id: `settlement-${Date.now()}`, kind: "notice", text }]);
      setSettlementDraftOpen(false);
      setSettlementPreview(null);
      setSettlementResult("");
      setSettlementRating("");
      setSessionPanel(null);
      setActiveScene(null);
      setArchiveFilter("全部");
      await loadStatus();
      await loadArchives();
      resetView("archive");
    } catch (e: any) {
      toast(`结算失败：${e?.message || e}`);
    } finally {
      setSettlementLoading(false);
    }
  }

  async function archiveSettlement() {
    if (settlementLoading) return;
    setSettlementLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; text?: string; error?: string }>("/miniapp-api/wenyou/settle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!j?.ok) throw new Error(j?.error || "归档失败");
      const text = String(j.text || "本局已归档。");
      setFeed((prev) => [...prev, { id: `archive-${Date.now()}`, kind: "notice", text }]);
      setSessionPanel(null);
      setActiveScene(null);
      setSettlementDraftOpen(false);
      setSettlementPreview(null);
      setSettlementResult("");
      setSettlementRating("");
      setArchiveFilter("全部");
      await loadStatus();
      await loadArchives();
      resetView("archive");
    } catch (e: any) {
      toast(`归档失败：${e?.message || e}`);
    } finally {
      setSettlementLoading(false);
    }
  }

  useEffect(() => {
    if (view !== "game" || sessionPanel?.phase !== "settlement" || !sessionPanel.settlement) return;
    const settlement = sessionPanel.settlement as Record<string, unknown>;
    const key = `${sessionPanel.gameId || "unknown"}:${String(settlement.granted_at || settlement.rating || settlement.result || "settlement")}`;
    if (settlementAutoArchiveRef.current === key) return;
    settlementAutoArchiveRef.current = key;

    let cancelled = false;
    (async () => {
      setSettlementLoading(true);
      try {
        const j = await apiJson<{ ok?: boolean; text?: string; error?: string }>("/miniapp-api/wenyou/settle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        if (!j?.ok) throw new Error(j?.error || "归档失败");
        if (cancelled) return;
        const text = String(j.text || "本局已归档。");
        toast(text.split("\n", 1)[0] || "本局已归档");
        setFeed((prev) => [...prev, { id: `archive-${Date.now()}`, kind: "notice", text }]);
        setSessionPanel(null);
        setActiveScene(null);
        setSettlementDraftOpen(false);
        setSettlementPreview(null);
        setSettlementResult("");
        setSettlementRating("");
        setArchiveFilter("全部");
        await loadStatus();
        await loadArchives();
        resetView("archive");
      } catch (e: any) {
        if (!cancelled) {
          settlementAutoArchiveRef.current = "";
          toast(`归档失败：${e?.message || e}`);
        }
      } finally {
        if (!cancelled) setSettlementLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loadArchives, loadStatus, resetView, sessionPanel?.gameId, sessionPanel?.phase, sessionPanel?.settlement, toast, view]);

  function openPanel(tab: WenyouPanelTab = "任务") {
    setPanelInitialTab(tab);
    setPanelView("局内资料");
    loadSessionPanel();
  }

  function selectQuickAction(text: string) {
    setActionText(text);
    setQuickDecisionOpen(false);
    window.setTimeout(() => actionInputRef.current?.focus(), 0);
  }

  async function runEncounterAction(action: "attack" | "escape" | "weaken" | "seal", detail: string) {
    if (acting) return;
    setQuickDecisionOpen(false);
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; text?: string; ai_player_action?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/encounter/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, detail, window_id: windowId }),
      });
      if (!j?.ok) throw new Error(j?.error || "遭遇判定失败");
      const stamp = Date.now();
      const aiPlayerAction = String(j.ai_player_action || "").trim();
      setFeed((prev) => [
        ...prev,
        { id: `u-${stamp}`, kind: "user", text: detail },
        ...(aiPlayerAction ? [{ id: `ai-player-${stamp}`, kind: "ai_player" as const, text: aiPlayerAction }] : []),
        { id: `gm-${stamp}`, kind: "system", text: String(j.text || "主神系统暂无回应。") },
      ]);
      setActionText("");
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
    } catch (e: any) {
      toast(`遭遇判定失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  function handleQuickAction(item: QuickAction) {
    if ("encounterAction" in item && item.encounterAction) {
      runEncounterAction(item.encounterAction, item.text);
      return;
    }
    if (item.panelTab) {
      openPanel(item.panelTab);
      setQuickDecisionOpen(false);
      return;
    }
    selectQuickAction(item.text);
  }

  async function useInventoryItem(item: WenyouInventoryItem | string) {
    if (acting) return;
    const name = inventoryItemName(item);
    if (!name) return;
    const itemKey = typeof item === "string" ? name : String(item.uid || item.id || item.name || name);
    const detail = actionText.trim();
    setPanelView(null);
    setQuickDecisionOpen(false);
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; text?: string; ai_player_action?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/item/use", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item: itemKey, action: detail, window_id: windowId }),
      });
      if (!j?.ok) throw new Error(j?.error || "道具使用失败");
      const stamp = Date.now();
      const aiPlayerAction = String(j.ai_player_action || "").trim();
      const userText = `使用道具【${name}】${detail ? `：${detail}` : ""}`;
      setFeed((prev) => [
        ...prev,
        { id: `u-${stamp}`, kind: "user", text: userText },
        ...(aiPlayerAction ? [{ id: `ai-player-${stamp}`, kind: "ai_player" as const, text: aiPlayerAction }] : []),
        { id: `gm-${stamp}`, kind: "system", text: String(j.text || "主神系统暂无回应。") },
      ]);
      setActionText("");
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
    } catch (e: any) {
      toast(`道具使用失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  async function runInventoryCommand(
    item: WenyouInventoryItem | string,
    endpoint: "equip" | "repair" | "sell",
    label: string,
    body: Record<string, unknown> = {}
  ) {
    if (acting) return;
    const itemRef = inventoryActionKey(item);
    if (!itemRef) {
      toast("找不到这个物品的系统编号，先同步一下背包。");
      return;
    }
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; message?: string; session?: WenyouSessionPanel; error?: string }>(`/miniapp-api/wenyou/item/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item: itemRef, ...body }),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || `${label}失败`);
      toast(j.message || `${label}完成`);
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
      await loadShop();
    } catch (e: any) {
      toast(`${label}失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  async function allocateAttribute(player: "player1" | "player2", attr: string) {
    if (acting) return;
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; message?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/player/attributes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player, deltas: { [attr]: 1 } }),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || "属性分配失败");
      toast(j.message || "属性点已分配");
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
      await loadSessionPanel();
      await loadShop();
    } catch (e: any) {
      toast(`属性分配失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  async function promotePlayer(player: "player1" | "player2") {
    if (acting) return;
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; message?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/player/promote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player }),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || "晋升失败");
      toast(j.message || "晋升完成");
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
    } catch (e: any) {
      toast(`晋升失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  async function revivePlayer(player: "player1" | "player2") {
    if (acting) return;
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; message?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/player/revive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player }),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || "复活失败");
      toast(j.message || "复活完成");
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
    } catch (e: any) {
      toast(`复活失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  async function useAbility(player: "player1" | "player2", ability: string) {
    if (acting) return;
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; message?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/player/ability/use", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player, ability, detail: actionText.trim() }),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || "能力使用失败");
      toast(j.message || "能力已使用");
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
    } catch (e: any) {
      toast(`能力使用失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  async function applyEvolution(player: "player1" | "player2", route = "human_stable") {
    if (acting) return;
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; message?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/player/evolution/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player, route }),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || "进化失败");
      toast(j.message || "进化已完成");
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
    } catch (e: any) {
      toast(`进化失败：${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }

  async function startRiftPull(count: 1 | 10) {
    const cost = count === 1 ? RIFT_SINGLE_COST : RIFT_TEN_COST;
    if (riftOverlay !== "closed" || riftLoading) return;
    if (riftPoints < cost) {
      toast("主神积分不足，裂隙没有响应");
      return;
    }
    const pullToken = riftPullTokenRef.current + 1;
    riftPullTokenRef.current = pullToken;
    const openedAt = window.performance?.now?.() ?? Date.now();
    setRiftLoading(true);
    setRiftPullCount(count);
    setRiftResults([]);
    setRiftRevealed([]);
    setRiftOverlay("opening");
    playRiftShatterSound();
    try {
      const j = await apiJson<{
        ok?: boolean;
        message?: string;
        error?: string;
        points?: number;
        wallet?: { points?: number; debts?: number; total_exp?: number };
        inventory?: WenyouInventoryItem[];
        results?: RiftPullResult[];
        session?: WenyouSessionPanel;
      }>("/miniapp-api/wenyou/gacha/roll", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pool_id: "mixed", count }),
      });
      if (!j?.ok) throw new Error(j?.message || j?.error || "命运裂隙牵引失败");
      const nextPoints = Number(j.points ?? j.wallet?.points ?? Math.max(0, riftPoints - cost));
      const nextInventory = Array.isArray(j.inventory) ? j.inventory : shop?.inventory || [];
      setRiftPointPreview(nextPoints);
      setShop((prev) => prev ? { ...prev, points: nextPoints, inventory: nextInventory } : prev);
      if (j.session) setSessionPanel(j.session);
      if (riftPullTokenRef.current !== pullToken) return;
      setRiftResults((j.results || []).map(normalizeRiftResult));
      setRiftRevealed([]);
      const elapsed = (window.performance?.now?.() ?? Date.now()) - openedAt;
      window.setTimeout(() => {
        if (riftPullTokenRef.current === pullToken) setRiftOverlay("results");
      }, Math.max(0, 1480 - elapsed));
    } catch (e) {
      if (riftPullTokenRef.current === pullToken) {
        setRiftOverlay("closed");
      }
      toast(e instanceof Error ? e.message : "命运裂隙牵引失败");
    } finally {
      setRiftLoading(false);
    }
  }

  function revealRiftCard(pullId: string) {
    setRiftRevealed((prev) => (prev.includes(pullId) ? prev : [...prev, pullId]));
  }

  function revealAllRiftCards() {
    riftResults.forEach((item, index) => {
      window.setTimeout(() => revealRiftCard(item.pullId), index * 90);
    });
  }

  function closeRiftOverlay() {
    riftPullTokenRef.current += 1;
    setRiftOverlay("closed");
    window.setTimeout(() => {
      setRiftResults([]);
      setRiftRevealed([]);
      setRiftPullCount(0);
    }, 260);
  }

  return (
    <div className="wenyou-shell">
      <span className="wenyou-shell-grid" />
      <span className="wenyou-shell-scan" />

      {spaceBootVisible ? (
        <div className={`wenyou-space-entry ${spaceBootFading ? "wenyou-space-entry-hide" : ""}`} role="status" aria-live="polite">
          <div className="wenyou-space-entry-title">
            <h1>MAIN GOD</h1>
            <h2>SYSTEM SCANNING...</h2>
          </div>
          <div className="wenyou-space-entry-track">
            <span style={{ width: `${spaceBootProgress}%` }} />
          </div>
          <p>Initializing Neural Link</p>
        </div>
      ) : null}

      {entryScene ? (
        <div className="wenyou-entry fixed inset-0 z-[80]" role="status" aria-live="polite">
          <button
            type="button"
            className="wenyou-entry-stage relative h-full w-full overflow-hidden px-6 py-8 text-left"
            onClick={() => setEntryScene(null)}
            aria-label="关闭入场动画"
          >
            <span className="wenyou-entry-grid" />
            <span className="wenyou-entry-scan" />
            <span className="wenyou-entry-crt" />
            <span className="wenyou-entry-corner wenyou-entry-corner-tl" />
            <span className="wenyou-entry-corner wenyou-entry-corner-br" />
            <div className="wenyou-entry-header">
              <span>MAIN GOD SYSTEM</span>
            </div>
            <div className="wenyou-entry-inner">
              <div className="wenyou-entry-terminal">
                <span>NEURAL LINK ESTABLISHED</span>
                <span>INSTANCE GATE OPEN</span>
              </div>
              <div className="wenyou-entry-seal">{entryScene.code || "INSTANCE"}</div>
              <div className="wenyou-entry-kicker">欢迎来到</div>
              <div className="wenyou-entry-title" data-text={entryScene.name}>{entryScene.name}</div>
              <div className="wenyou-entry-sub">努力生存下去吧。</div>
              <div className="wenyou-entry-progress" aria-hidden="true">
                <span />
              </div>
              <div className="wenyou-entry-meta">
                {entryScene.genre ? <span>{entryScene.genre}</span> : null}
                {entryScene.difficulty ? <span>难度 {entryScene.difficulty}</span> : null}
              </div>
            </div>
          </button>
        </div>
      ) : null}

      {view === "home" ? (
        <section className="wenyou-screen wenyou-home wenyou-home-cyber">
          <span className="wenyou-home-scanlines" aria-hidden="true" />
          <span className="wenyou-home-glow wenyou-home-glow-a" aria-hidden="true" />
          <span className="wenyou-home-glow wenyou-home-glow-b" aria-hidden="true" />
          <span className="wenyou-home-edge wenyou-home-edge-right" aria-hidden="true" />
          <span className="wenyou-home-edge wenyou-home-edge-left" aria-hidden="true" />

          <div className="wenyou-home-debug wenyou-home-debug-left" aria-hidden="true">
            SYS_BOOT: OK<br />
            NEURAL_LINK: 98%<br />
            FLOW_STATE: CRITICAL
          </div>
          <div className="wenyou-home-debug wenyou-home-debug-right" aria-hidden="true">
            //INFINITE_FLOW_OS<br />
            //VER_2.0.4b<br />
            //ENCRYPTED
          </div>

          <header className="wenyou-home-hud" aria-label="主神空间状态">
            <div className="wenyou-home-hud-row">
              <div className="wenyou-home-signal wenyou-home-signal-wide">
                <div>
                  <span>主神积分 / PTS</span>
                  <strong>{shopLoading ? "SYNC" : hubPoints.toLocaleString()}</strong>
                </div>
                <div className="wenyou-home-signal-bar">
                  <b style={{ width: `${hubPointSignal}%` }} />
                  <i />
                </div>
              </div>
              <div className="wenyou-home-user">
                <span>等级阶位</span>
                <strong>{hubRank}阶 Lv.{hubLevel}</strong>
              </div>
            </div>
            <div className="wenyou-home-hud-row wenyou-home-hud-row-split">
              <div className="wenyou-home-signal">
                <div>
                  <span>副本状态 / STATE</span>
                  <strong>{hubStatusLabel}</strong>
                </div>
                <div className="wenyou-home-signal-bar wenyou-home-signal-bar-blue">
                  <b style={{ width: `${hubStatusSignal}%` }} />
                </div>
              </div>
              <div className="wenyou-home-signal">
                <div>
                  <span>债务 / DEBT</span>
                  <strong>{hubDebts}</strong>
                </div>
                <div className="wenyou-home-signal-bar wenyou-home-signal-bar-purple">
                  <b style={{ width: `${hubRankSignal}%` }} />
                  <i />
                </div>
              </div>
            </div>
          </header>

          <main className="wenyou-home-sector-grid" aria-label="主神空间入口">
            <button
              type="button"
              className="wenyou-sector-card wenyou-sector-main wenyou-glitch-tile"
              onClick={() => hasActiveRun ? pushView("game") : pushView("selection")}
            >
              <span className="wenyou-sector-rail" />
              <span className="wenyou-sector-watermark" aria-hidden="true">VII</span>
              <span className="wenyou-sector-corner" aria-hidden="true" />
              <div className="wenyou-sector-kicker">
                <i />
                <span>{hubMissionSub}</span>
              </div>
              <h1>副本<br />大厅</h1>
              <p>{hasActiveRun ? currentScene.name : "副本池已待命，选择入口后接入。"}</p>
              <div className="wenyou-sector-foot">
                <span>{hubMissionDetail}</span>
                <b>{hubMissionCta}<Icon name="arrow" /></b>
              </div>
            </button>

            <button type="button" className="wenyou-sector-card wenyou-sector-rift wenyou-glitch-tile" onClick={() => pushView("rift")}>
              <span className="wenyou-sector-icon"><Icon name="rift" /></span>
              <span>抽卡入口</span>
              <strong>命运<br />裂隙</strong>
              <i className="wenyou-sector-pink-line" aria-hidden="true" />
            </button>

            <button type="button" className="wenyou-sector-card wenyou-sector-shop wenyou-glitch-tile" onClick={() => pushView("shop")}>
              <div>
                <strong>系统<br />商店</strong>
                <span>积分: {hubPoints.toLocaleString()}</span>
              </div>
              <i><Icon name="shop" /></i>
            </button>

            <div className="wenyou-home-protocol" aria-hidden="true">
              PROTOCOL_VOID_ACTIVE<br />
              SYSTEM_STABLE_88%
            </div>
          </main>

          <footer className="wenyou-home-dock">
            <button
              type="button"
              className="wenyou-home-profile wenyou-glitch-tile"
              onClick={() => {
                setProfileTab("副本存档");
                pushView("archive");
              }}
            >
              <span>
                <small>玩家中心</small>
                <strong>个人空间</strong>
              </span>
              <Icon name="profile" />
            </button>
          </footer>
          <div className="wenyou-home-bottom-mark" aria-hidden="true">
            <span />
            <i />
            <span />
          </div>
        </section>
      ) : null}

      {view === "shop" ? (
        <section className="wenyou-screen">
          <Header title="系统商店" onBack={() => void goBackInsideWenyou()} />
          <div className="wenyou-shop-brief">
            <div>
              <span>主神积分</span>
              <strong>{shopLoading ? "同步中" : String(shop?.points ?? 0)}</strong>
              {shop?.phaseLabel ? <em>{shop.phaseLabel}</em> : null}
            </div>
          </div>
	          <div className="wenyou-generation-status">
	            <div>
	              <strong>今日货架</strong>
	              <span>{shop?.generatedAt ? `${shop.generatedAt} · 普通 ${regularShopItems.length} 件 · 刷新 ${regularShop?.refresh_count ?? 0}/${regularShop?.refresh_limit ?? 3}` : "系统正在配货"}</span>
	            </div>
	            <div className="wenyou-shop-toolbar">
	              <button onClick={loadShop} disabled={shopLoading}>{shopLoading ? "同步中..." : "同步"}</button>
	              <button onClick={refreshShop} disabled={shopLoading || !shop?.can_buy || (regularShop?.refresh_count ?? 0) >= (regularShop?.refresh_limit ?? 3)}>
	                刷新 {regularShop?.refresh_cost ?? 20}
	              </button>
	            </div>
	          </div>
          {!shopLoading && !shop?.can_buy ? (
            <div className="wenyou-shop-lock">
              {shop?.active
                ? "副本进行中，系统商店关闭；只能使用背包已有物品，进入结算后再购买。"
                : "当前购买写入暂未开放。回到主神空间整备完成后，可用主神积分购买道具。"}
            </div>
          ) : null}
	          <div className="wenyou-panel-subtitle">普通商店</div>
	          <div className="wenyou-shop-grid">
	            {shopLoading ? <div className="wenyou-empty">主神商店正在校准货架...</div> : null}
	            {regularShopItems.map((item) => {
	              const owned = (shop?.inventory || []).some((it) => inventoryItemName(it) === item.name || String(it.id || "") === item.id);
	              const disabled = !shop?.can_buy || owned || shopBuyingId === item.id || Number(shop?.points || 0) < Number(item.price || 0);
              return (
                <article key={item.id} className={`wenyou-shop-card wenyou-shop-rarity-${item.rarity || "D"}`}>
                  <div className="wenyou-shop-card-top">
                    <span>{item.kind || "道具"}</span>
                    <strong>{item.rarity || "D"}</strong>
                  </div>
                  <h3>{item.name}</h3>
                  <p>{itemDisplayDescription(item)}</p>
                  <div className="wenyou-shop-card-bottom">
                    <b>{item.price} pts</b>
                    <button onClick={() => buyShopItem(item)} disabled={disabled}>
                      {owned ? "已拥有" : shopBuyingId === item.id ? "购买中" : "购买"}
                    </button>
                  </div>
                </article>
	              );
	            })}
	            {!shopLoading && !regularShopItems.length ? <div className="wenyou-empty">今日货架为空。</div> : null}
	          </div>
	          <div className="wenyou-panel-subtitle">特殊兑换</div>
	          {specialShop?.unlocked ? (
	            <div className="wenyou-shop-grid">
	              {specialShopItems.map((item) => {
	                const owned = (shop?.inventory || []).some((it) => inventoryItemName(it) === item.name || String(it.id || "") === item.id);
	                const disabled = !shop?.can_buy || owned || shopBuyingId === item.id || Number(shop?.points || 0) < Number(item.price || 0);
	                return (
	                  <article key={`special-${item.id}`} className={`wenyou-shop-card wenyou-shop-rarity-${item.rarity || "B"}`}>
	                    <div className="wenyou-shop-card-top">
	                      <span>特殊 · {item.kind || item.category || "兑换"}</span>
	                      <strong>{item.rarity || "B"}</strong>
	                    </div>
                    <h3>{item.name}</h3>
                    <p>{item.sealed ? `${itemDisplayDescription(item)}（购买后封印）` : itemDisplayDescription(item)}</p>
	                    <div className="wenyou-shop-card-bottom">
	                      <b>{item.price} pts</b>
	                      <button onClick={() => buyShopItem(item)} disabled={disabled}>
	                        {owned ? "已拥有" : shopBuyingId === item.id ? "购买中" : "兑换"}
	                      </button>
	                    </div>
	                  </article>
	                );
	              })}
	              {!specialShopItems.length ? <div className="wenyou-empty">特殊兑换所暂无商品。</div> : null}
	            </div>
	          ) : (
	            <div className="wenyou-shop-lock">C 阶后开启特殊兑换所。</div>
	          )}
	        </section>
      ) : null}

      {view === "rift" ? (
        <section className="wenyou-screen wenyou-rift-screen">
          <div className="wenyou-rift-noise" />
          <div className="wenyou-rift-top">
            <button onClick={() => void goBackInsideWenyou()} aria-label="返回"><Icon name="back" /></button>
            <div>
              <h1>命运裂隙</h1>
              <p>FATE RIFT // MIXED POOL</p>
            </div>
            <span aria-hidden="true" />
          </div>

          <main className="wenyou-rift-main">
            <div className="wenyou-rift-title">
              <span>LIMITED SIGNAL // FRAGMENT</span>
              <strong data-text="FATE RIFT">FATE RIFT</strong>
              <i aria-hidden="true"><b /><b /><b /><b /><b /></i>
            </div>
            <div className="wenyou-rift-core" aria-hidden="true">
              <span className="wenyou-rift-glow" />
              <span className="wenyou-rift-square wenyou-rift-square-a" />
              <span className="wenyou-rift-square wenyou-rift-square-b" />
              <span className="wenyou-rift-fragment wenyou-rift-fragment-a" />
              <span className="wenyou-rift-fragment wenyou-rift-fragment-b" />
              <span className="wenyou-rift-symbol"><Icon name="rift" /></span>
            </div>
            <div className="wenyou-rift-rates">
              <div><span>S</span><strong>0.3%</strong></div>
              <div><span>A</span><strong>3.7%</strong></div>
              <div><span>B</span><strong>12%</strong></div>
              <div><span>C</span><strong>34%</strong></div>
              <div><span>D</span><strong>50%</strong></div>
            </div>
          </main>

          <footer className="wenyou-rift-footer">
            <p>单抽 100 / 十连 1000 / 十连 C+ 保底 / 100 抽 S 保底</p>
            <div className="wenyou-rift-currency">
              <span>主神积分</span>
              <strong>{shopLoading || riftLoading ? "同步中" : riftPoints.toLocaleString()}</strong>
            </div>
            <div className="wenyou-rift-actions">
              <button onClick={() => void startRiftPull(1)} disabled={riftOverlay !== "closed" || riftLoading || riftPoints < RIFT_SINGLE_COST}>
                <span>{riftLoading ? "裂隙同步中" : "裂隙牵引 x1"}</span>
                <b>{RIFT_SINGLE_COST}</b>
              </button>
              <button onClick={() => void startRiftPull(10)} disabled={riftOverlay !== "closed" || riftLoading || riftPoints < RIFT_TEN_COST}>
                <em>保底 C+</em>
                <span>{riftLoading ? "裂隙同步中" : "裂隙牵引 x10"}</span>
                <b>{RIFT_TEN_COST}</b>
              </button>
            </div>
          </footer>
        </section>
      ) : null}

      {view === "selection" ? (
        <section className="wenyou-screen">
          <Header title="副本大厅" onBack={() => void goBackInsideWenyou()} />
          <div className="wenyou-generation-status">
            <div>
              <strong>副本池</strong>
              <span>{candidateGeneratedAt ? `上次生成：${candidateGeneratedAt.slice(0, 16).replace("T", " ")}` : "等待主神投放入口"}</span>
            </div>
            <button onClick={() => loadCandidates(true, search)} disabled={candidatesRefreshing || candidatesLoading}>
              {candidatesRefreshing ? "生成中..." : "换一批"}
            </button>
          </div>
          <div className="wenyou-search">
            <span>⌕</span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索副本，或写偏好让主神换一批..." />
          </div>
          <FilterRow items={TYPE_FILTERS} value={typeFilter} onChange={setTypeFilter} />
          <FilterRow items={DIFFICULTY_FILTERS} value={difficultyFilter} onChange={setDifficultyFilter} />
          <div className="wenyou-instance-list">
            {candidatesLoading ? <div className="wenyou-empty">主神正在排列副本入口...</div> : null}
            {filteredCandidates.map((item) => (
              <article key={item.id} className="wenyou-select-card">
                <div className="wenyou-card-meta">
                  <span className={colorClass(item.instance_genre)}>{item.instance_genre} | {item.difficulty}</span>
                  <span>篇幅: {item.estimated_length || "标准"}</span>
                </div>
                <h3>{item.title}</h3>
                {item.tagline ? <p>“{item.tagline}”</p> : null}
                {item.premise ? <p>{item.premise}</p> : null}
                <div className="wenyou-candidate-brief">
                  {item.core_task ? <span>任务：{item.core_task}</span> : null}
                  {item.survival_hook ? <span>生存点：{item.survival_hook}</span> : null}
                  {item.risk ? <span>风险：{item.risk}</span> : null}
                </div>
                {item.tags?.length ? (
                  <div className="wenyou-candidate-tags">
                    {item.tags.map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
                ) : null}
                <button onClick={() => startCandidate(item)} disabled={starting}>
                  {starting ? "接入中..." : "进入副本"}
                </button>
              </article>
            ))}
            {!candidatesLoading && !filteredCandidates.length ? <div className="wenyou-empty">没有匹配的副本。换个筛选，或者让主神换一批。</div> : null}
          </div>
        </section>
      ) : null}

      {view === "game" ? (
        <section className="wenyou-screen wenyou-game">
          <div className="wenyou-game-top">
            <button onClick={() => void goBackInsideWenyou()} aria-label="返回"><Icon name="back" /></button>
            <div>
              <h2>{currentScene.name}</h2>
              <p><span />阶段: {sessionPanel?.phase_label || status.session?.phase_label || (status.active ? "进行中" : "模拟预览")}</p>
              <p className="wenyou-location-hint"><span />当前在 {currentLocation}</p>
            </div>
            <button
              className="wenyou-game-data-trigger"
              onClick={() => {
                setQuickDecisionOpen(false);
                openPanel("任务");
              }}
              aria-label="打开任务与背包"
            >
              <Icon name="list" />
            </button>
          </div>

          <div className="wenyou-feed">
            {feed.length ? <div className="wenyou-time-chip">{feedTimeLabel}</div> : null}
            {feed.length ? feed.map((item) => {
              if (item.kind === "user") return <div key={item.id} className="wenyou-user-bubble">{item.text}</div>;
              if (item.kind === "notice") return <SystemNotice key={item.id} tone="cyan" label="任务更新" text={item.text} />;
              if (item.kind === "loot") return <SystemNotice key={item.id} tone="purple" label="获得物品" text={item.text} />;
              if (item.kind === "ai_player") return <SystemNotice key={item.id} tone="purple" label="渡的行动" text={item.text} />;
              return <StoryFeedMessage key={item.id} text={item.text} />;
            }) : gameSettlementReady ? (
              <div className="wenyou-feed-empty">
                <strong>结算完成，正在归档</strong>
                <span>奖励已入账，本局会自动收入个人空间。</span>
              </div>
            ) : (
              <div className="wenyou-feed-empty">
                <strong>等待副本接入</strong>
                <span>进入副本后，剧情、任务更新和获得物品会按行动记录在这里。</span>
              </div>
            )}
          </div>

          <div className="wenyou-command">
            {gameSettlementReady && sessionPanel?.settlement ? (
              <SettlementGranted settlement={sessionPanel.settlement} loading={settlementLoading} onArchive={archiveSettlement} />
            ) : null}
            {!gameSettlementReady && sessionPanel?.phase !== "settlement" && settlementDraftOpen ? (
              <SettlementDraft
                preview={settlementPreview}
                result={settlementResult}
                rating={settlementRating}
                loading={settlementLoading}
                onResult={changeSettlementResult}
                onRating={changeSettlementRating}
                onCancel={() => setSettlementDraftOpen(false)}
                onConfirm={enterSettlement}
              />
            ) : null}
            {!gameSettlementReady && quickDecisionOpen ? (
              <div className="wenyou-quick-decision-menu" role="menu" aria-label="快捷决策">
                {quickActions.map((item) => (
                  <button key={item.label} type="button" onClick={() => handleQuickAction(item)}>
                    <span>{item.label}</span>
                  </button>
                ))}
                {gamePlayerAbilities.length ? <div className="wenyou-quick-menu-label">能力</div> : null}
                {gamePlayerAbilities.map((ability) => (
                  <button
                    key={ability.id}
                    type="button"
                    className="wenyou-quick-ability"
                    onClick={() => {
                      setQuickDecisionOpen(false);
                      void useAbility("player1", ability.id);
                    }}
                    disabled={acting}
                  >
                    <span>{ability.name}</span>
                  </button>
                ))}
              </div>
            ) : null}
            {acting || settlementLoading ? <div className="wenyou-action-progress"><span /></div> : null}
            {!gameSettlementReady ? (
              <>
                <div className="wenyou-input-row">
                  <button
                    type="button"
                    className={`wenyou-input-tool ${quickDecisionOpen ? "active" : ""}`}
                    onClick={() => {
                      setQuickDecisionOpen((open) => !open);
                    }}
                    aria-label="快捷决策"
                    aria-expanded={quickDecisionOpen}
                    disabled={acting}
                  >
                    <Icon name="plus" />
                  </button>
                  <input ref={actionInputRef} value={actionText} onChange={(e) => setActionText(e.target.value)} placeholder={acting ? "主神演算中..." : "输入你的行动..."} disabled={acting} onKeyDown={(e) => { if (e.key === "Enter") submitAction(); }} />
                  <button type="button" onClick={submitAction} aria-label="发送行动" disabled={acting}><Icon name="send" /></button>
                </div>
                {sessionPanel?.phase !== "settlement" ? (
                  <button type="button" className="wenyou-settlement-link" onClick={openSettlementDraft} disabled={acting || settlementLoading}>
                    {settlementLoading ? "结算校准中..." : "申请结算"}
                  </button>
                ) : null}
              </>
            ) : null}
          </div>
        </section>
      ) : null}

      {view === "archive" ? (
        <section className="wenyou-screen">
          <Header title="个人空间" onBack={() => void goBackInsideWenyou()} />
          <div className="wenyou-profile-tabs" role="tablist" aria-label="个人空间导航">
            {PROFILE_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                className={profileTab === tab ? "active" : ""}
                onClick={() => setProfileTab(tab)}
                role="tab"
                aria-selected={profileTab === tab}
              >
                {tab}
              </button>
            ))}
          </div>

          {profileTab === "副本存档" ? (
            <>
              <FilterRow items={ARCHIVE_FILTERS} value={archiveFilter} onChange={setArchiveFilter} />
              <div className="wenyou-archive-list">
                {archiveFilter === "进行中" && hasActiveRun ? (
                  <ArchiveCard active title={currentScene.name} genre={currentScene.genre || "未知"} difficulty={currentScene.difficulty || "-"} turns="进行中" onPrimary={() => pushView("game")} />
                ) : null}
                {archiveFilter !== "进行中" ? sortedArchives.map((it, index) => (
                  <ArchiveCard
                    key={`${it.gameId || "archive"}-${index}`}
                    title={it.instance_name || "未命名副本"}
                    genre={it.instance_genre || "未知"}
                    difficulty={it.difficulty || "-"}
                    endedAt={it.endedAt || "-"}
                    turns={`${Number(it.history_count || 0)} 回合`}
                    open={openGameId === String(it.gameId || "")}
                    loading={detailLoading && openGameId === String(it.gameId || "")}
                    detail={archiveDetails[String(it.gameId || "")]}
                    onPrimary={() => toggleArchive(String(it.gameId || ""))}
                    onRetry={() => startStory("custom", `重新挑战副本：${it.instance_name || "未命名副本"}`, { name: it.instance_name || "未命名副本", genre: it.instance_genre, difficulty: it.difficulty })}
                  />
                )) : null}
                {!sortedArchives.length && !archivesLoading && archiveFilter !== "进行中" ? <div className="wenyou-empty">还没有副本归档。</div> : null}
              </div>
            </>
          ) : null}

          {profileTab === "背包" ? (
            <div className="wenyou-profile-panel">
              <div className="wenyou-profile-wallet">
                <span>主神积分</span>
                <strong>{hubPoints.toLocaleString()}</strong>
                <em>{profileInventory.length} 件物品</em>
              </div>
              <InventoryList
                inventory={profileInventory}
                acting={acting}
                onUseItem={useInventoryItem}
                onInventoryCommand={runInventoryCommand}
                emptyText="背包为空。"
              />
            </div>
          ) : null}

          {profileTab === "角色面板" ? (
            <div className="wenyou-profile-panel">
              <div className="wenyou-panel-brief-grid">
                <PanelRow label="主神积分" value={hubPoints.toLocaleString()} />
                <PanelRow label="主神债务" value={String(hubDebts)} />
              </div>
              <PlayerStatCard
                title="玩家一"
                player={profileStats.player1 || gameRulesState.players?.player1}
                growth={profileGrowthPlayers.player1}
              />
              <PlayerStatCard
                title="玩家二 · 渡"
                player={profileStats.player2 || gameRulesState.players?.player2}
                growth={profileGrowthPlayers.player2}
              />
            </div>
          ) : null}
        </section>
      ) : null}

      {activeAttributePrompt ? (
        <AttributePointModal
          title={activeAttributePrompt.title}
          points={activeAttributePrompt.points}
          acting={acting}
          onAllocate={(attr) => allocateAttribute(activeAttributePrompt.player, attr)}
          onClose={() => {
            setAttributePromptDismissedKey(activeAttributePrompt.key);
            setAttributePromptPlayer(null);
          }}
        />
      ) : null}

      {riftOverlay !== "closed" ? (
        <RiftOverlay
          phase={riftOverlay}
          count={riftPullCount}
          results={riftResults}
          revealed={riftRevealed}
          onReveal={revealRiftCard}
          onRevealAll={revealAllRiftCards}
          onClose={closeRiftOverlay}
        />
      ) : null}

      {randomOpen ? (
        <div className="wenyou-modal">
          <button className="wenyou-modal-backdrop" onClick={() => setRandomOpen(false)} aria-label="关闭随机匹配" />
          <div className="wenyou-random-panel">
            <span className="wenyou-random-line" />
            <h2><Icon name="shuffle" />随机匹配参数</h2>
            <OptionGroup label="难度偏好" items={["不限", "新手-普通", "困难-噩梦"]} value={randomDifficulty} onChange={setRandomDifficulty} />
            <OptionGroup label="篇幅偏好" items={["短篇", "标准", "长篇"]} value={randomLength} onChange={setRandomLength} />
            <OptionGroup label="风格倾向" items={["悬疑", "生存", "推理", "高压", "轻剧情", "全随机"]} value={randomStyle} onChange={setRandomStyle} grid />
            <div className="wenyou-modal-actions">
              <button onClick={() => setRandomOpen(false)}>取消</button>
              <button onClick={startRandom} disabled={candidatesRefreshing}>{candidatesRefreshing ? "生成中..." : "生成副本池"}</button>
            </div>
          </div>
        </div>
      ) : null}

      {panelView ? (
        <PanelModal
          view={panelView}
          session={sessionPanel}
          initialTab={panelInitialTab}
          acting={acting}
          onClose={() => setPanelView(null)}
          onUseItem={useInventoryItem}
          onInventoryCommand={runInventoryCommand}
        />
      ) : null}
    </div>
  );
}

type RiftPoint = { x: number; y: number };
type RiftShardBlueprint = {
  x: number;
  y: number;
  size: number;
  driftX: number;
  driftY: number;
  rotation: number;
  spin: number;
  delay: number;
  duration: number;
  tint: number;
  points: Array<[number, number]>;
  innerCuts: Array<{ from: [number, number]; to: [number, number]; alpha: number }>;
};

type RiftGlassShard = {
  startX: number;
  startY: number;
  size: number;
  driftX: number;
  driftY: number;
  baseRotation: number;
  spin: number;
  delay: number;
  duration: number;
  points: RiftPoint[];
  tint: number;
  innerCuts: Array<{ from: RiftPoint; to: RiftPoint; alpha: number }>;
};

const RIFT_CRACK_PATHS = [
  "M 51 16 L 48 26 L 53 34 L 47 45 L 51 57 L 44 70 L 47 86",
  "M 50 30 L 36 24 L 27 18 L 18 21",
  "M 49 43 L 36 45 L 24 53 L 13 58",
  "M 51 57 L 64 60 L 75 68 L 87 72",
  "M 48 69 L 37 78 L 28 88",
  "M 52 34 L 65 29 L 78 31 L 90 25",
  "M 51 51 L 63 45 L 76 44",
];

const RIFT_SHARD_BLUEPRINTS: RiftShardBlueprint[] = [
  { x: 0.49, y: 0.22, size: 0.112, driftX: -0.16, driftY: -0.18, rotation: -0.52, spin: -0.32, delay: 0, duration: 1780, tint: 0.62, points: [[-0.2, -0.56], [0.52, -0.32], [0.22, 0.52], [-0.42, 0.28]], innerCuts: [{ from: [-0.08, -0.34], to: [0.2, 0.34], alpha: 0.18 }] },
  { x: 0.53, y: 0.29, size: 0.13, driftX: 0.15, driftY: -0.15, rotation: 0.28, spin: 0.24, delay: 22, duration: 1840, tint: 0.36, points: [[-0.5, -0.24], [0.18, -0.48], [0.52, 0.16], [-0.16, 0.56], [-0.52, 0.18]], innerCuts: [{ from: [-0.28, -0.16], to: [0.34, 0.18], alpha: 0.16 }] },
  { x: 0.45, y: 0.35, size: 0.145, driftX: -0.22, driftY: -0.04, rotation: -0.18, spin: -0.2, delay: 48, duration: 1900, tint: 0.68, points: [[-0.54, -0.12], [-0.04, -0.54], [0.42, -0.28], [0.48, 0.28], [-0.18, 0.54]], innerCuts: [{ from: [-0.32, 0.06], to: [0.32, -0.16], alpha: 0.18 }] },
  { x: 0.56, y: 0.39, size: 0.126, driftX: 0.24, driftY: -0.02, rotation: 0.58, spin: 0.18, delay: 64, duration: 1940, tint: 0.44, points: [[-0.28, -0.52], [0.5, -0.22], [0.34, 0.46], [-0.36, 0.4], [-0.54, -0.1]], innerCuts: [{ from: [-0.18, -0.26], to: [0.2, 0.3], alpha: 0.14 }] },
  { x: 0.5, y: 0.48, size: 0.16, driftX: -0.08, driftY: 0.06, rotation: -0.04, spin: 0.1, delay: 86, duration: 2020, tint: 0.58, points: [[-0.36, -0.56], [0.22, -0.48], [0.54, 0.04], [0.18, 0.58], [-0.5, 0.28]], innerCuts: [{ from: [-0.26, -0.2], to: [0.28, 0.26], alpha: 0.2 }, { from: [0.1, -0.36], to: [-0.12, 0.38], alpha: 0.12 }] },
  { x: 0.43, y: 0.55, size: 0.138, driftX: -0.26, driftY: 0.12, rotation: -0.42, spin: -0.16, delay: 118, duration: 1980, tint: 0.34, points: [[-0.52, -0.32], [0.06, -0.56], [0.5, -0.02], [0.18, 0.52], [-0.42, 0.36]], innerCuts: [{ from: [-0.3, -0.02], to: [0.34, 0.04], alpha: 0.18 }] },
  { x: 0.57, y: 0.58, size: 0.148, driftX: 0.25, driftY: 0.14, rotation: 0.36, spin: 0.22, delay: 136, duration: 2060, tint: 0.64, points: [[-0.48, -0.18], [0.0, -0.54], [0.5, -0.26], [0.42, 0.38], [-0.2, 0.56]], innerCuts: [{ from: [-0.16, -0.34], to: [0.24, 0.34], alpha: 0.16 }] },
  { x: 0.49, y: 0.67, size: 0.12, driftX: -0.08, driftY: 0.28, rotation: 0.08, spin: -0.14, delay: 166, duration: 2120, tint: 0.42, points: [[-0.32, -0.5], [0.42, -0.36], [0.5, 0.18], [0.02, 0.58], [-0.5, 0.18]], innerCuts: [{ from: [-0.2, -0.26], to: [0.26, 0.2], alpha: 0.14 }] },
  { x: 0.36, y: 0.46, size: 0.104, driftX: -0.31, driftY: 0.02, rotation: -0.78, spin: -0.28, delay: 88, duration: 1860, tint: 0.72, points: [[-0.5, -0.1], [0.18, -0.5], [0.52, 0.14], [-0.12, 0.54]], innerCuts: [{ from: [-0.24, -0.08], to: [0.26, 0.12], alpha: 0.12 }] },
  { x: 0.64, y: 0.47, size: 0.102, driftX: 0.32, driftY: 0.04, rotation: 0.8, spin: 0.3, delay: 104, duration: 1880, tint: 0.3, points: [[-0.42, -0.34], [0.34, -0.48], [0.5, 0.2], [-0.12, 0.52]], innerCuts: [{ from: [-0.18, -0.24], to: [0.2, 0.26], alpha: 0.12 }] },
  { x: 0.39, y: 0.75, size: 0.09, driftX: -0.22, driftY: 0.27, rotation: -0.3, spin: -0.2, delay: 198, duration: 2020, tint: 0.5, points: [[-0.42, -0.32], [0.28, -0.44], [0.46, 0.28], [-0.26, 0.5]], innerCuts: [{ from: [-0.2, -0.1], to: [0.22, 0.18], alpha: 0.12 }] },
  { x: 0.62, y: 0.72, size: 0.096, driftX: 0.2, driftY: 0.26, rotation: 0.44, spin: 0.16, delay: 214, duration: 2040, tint: 0.78, points: [[-0.5, -0.2], [0.1, -0.5], [0.52, 0.0], [0.0, 0.54]], innerCuts: [{ from: [-0.24, -0.12], to: [0.24, 0.12], alpha: 0.1 }] },
];

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value));
}

function easeOutQuart(value: number) {
  return 1 - Math.pow(1 - value, 4);
}

function createRiftGlassShard(cssWidth: number, cssHeight: number, index: number): RiftGlassShard {
  const blueprint = RIFT_SHARD_BLUEPRINTS[index % RIFT_SHARD_BLUEPRINTS.length];
  const scale = Math.min(cssWidth, cssHeight);
  const size = Math.max(34, blueprint.size * scale);
  return {
    startX: blueprint.x * cssWidth,
    startY: blueprint.y * cssHeight,
    size,
    driftX: blueprint.driftX * scale,
    driftY: blueprint.driftY * scale,
    baseRotation: blueprint.rotation,
    spin: blueprint.spin,
    delay: blueprint.delay,
    duration: blueprint.duration,
    points: blueprint.points.map(([x, y]) => ({ x: x * size, y: y * size })),
    tint: blueprint.tint,
    innerCuts: blueprint.innerCuts.map((cut) => ({
      from: { x: cut.from[0] * size, y: cut.from[1] * size },
      to: { x: cut.to[0] * size, y: cut.to[1] * size },
      alpha: cut.alpha,
    })),
  };
}

function drawRiftGlassShard(ctx: CanvasRenderingContext2D, shard: RiftGlassShard, elapsed: number) {
  if (!shard.points.length) return;
  const progress = clamp01((elapsed - shard.delay) / shard.duration);
  if (progress <= 0) return;
  const eased = easeOutQuart(progress);
  const fade = progress < 0.74 ? 1 : Math.max(0, 1 - (progress - 0.74) / 0.26);
  const opacity = fade * (0.48 + (1 - progress) * 0.12);
  const snap = progress < 0.18 ? Math.sin(progress * Math.PI * 18) * (1 - progress / 0.18) : 0;
  const x = shard.startX + shard.driftX * eased + snap * 2.4;
  const y = shard.startY + shard.driftY * eased - snap * 1.2;
  const rotation = shard.baseRotation + shard.spin * eased;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(rotation);
  ctx.beginPath();
  ctx.moveTo(shard.points[0].x, shard.points[0].y);
  for (let index = 1; index < shard.points.length; index += 1) {
    ctx.lineTo(shard.points[index].x, shard.points[index].y);
  }
  ctx.closePath();
  const gradient = ctx.createLinearGradient(-shard.size, -shard.size, shard.size, shard.size);
  gradient.addColorStop(0, `rgba(235, 242, 248, ${Math.max(0, opacity * 0.18)})`);
  gradient.addColorStop(0.48, `rgba(${shard.tint > 0.5 ? "132, 180, 198" : "154, 166, 184"}, ${Math.max(0, opacity * 0.11)})`);
  gradient.addColorStop(1, `rgba(18, 24, 38, ${Math.max(0, opacity * 0.1)})`);
  ctx.fillStyle = gradient;
  ctx.strokeStyle = `rgba(225, 233, 240, ${Math.max(0, opacity * 0.18)})`;
  ctx.lineWidth = 0.56;
  ctx.fill();
  ctx.stroke();
  ctx.clip();
  ctx.globalCompositeOperation = "screen";
  ctx.lineWidth = 0.58;
  for (const cut of shard.innerCuts) {
    ctx.beginPath();
    ctx.moveTo(cut.from.x, cut.from.y);
    ctx.lineTo(cut.to.x, cut.to.y);
    ctx.strokeStyle = `rgba(225, 233, 240, ${Math.max(0, opacity * cut.alpha * 0.32)})`;
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.moveTo(-shard.size * 0.45, -shard.size * 0.18);
  ctx.lineTo(shard.size * 0.35, -shard.size * 0.42);
  ctx.strokeStyle = `rgba(235, 242, 248, ${Math.max(0, opacity * 0.05)})`;
  ctx.stroke();
  ctx.restore();
}

function RiftShatterLayer({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!active || typeof window === "undefined") return undefined;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return undefined;

    let raf = 0;
    let cssWidth = window.innerWidth;
    let cssHeight = window.innerHeight;
    let shards: RiftGlassShard[] = [];

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      cssWidth = window.innerWidth;
      cssHeight = window.innerHeight;
      canvas.width = Math.floor(cssWidth * dpr);
      canvas.height = Math.floor(cssHeight * dpr);
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const startedAt = window.performance?.now?.() ?? Date.now();
    const animate = (now = window.performance?.now?.() ?? Date.now()) => {
      const elapsed = now - startedAt;
      ctx.clearRect(0, 0, cssWidth, cssHeight);
      shards = shards.filter((shard) => elapsed - shard.delay < shard.duration);
      for (const shard of shards) {
        drawRiftGlassShard(ctx, shard, elapsed);
      }
      if (shards.length > 0) raf = window.requestAnimationFrame(animate);
    };

    resize();
    shards = RIFT_SHARD_BLUEPRINTS.map((_, index) => createRiftGlassShard(cssWidth, cssHeight, index));
    raf = window.requestAnimationFrame(animate);
    window.addEventListener("resize", resize);
    if ("vibrate" in navigator) navigator.vibrate([50, 30, 100]);

    return () => {
      window.removeEventListener("resize", resize);
      window.cancelAnimationFrame(raf);
      ctx.clearRect(0, 0, cssWidth, cssHeight);
    };
  }, [active]);

  return (
    <div className="wenyou-rift-shatter" aria-hidden="true">
      <svg className="wenyou-rift-cracks" viewBox="0 0 100 100" preserveAspectRatio="none">
        {RIFT_CRACK_PATHS.map((d, index) => (
          <path
            key={d}
            className="wenyou-rift-crack-line"
            d={d}
            style={{ animationDelay: `${index * 0.045}s` }}
          />
        ))}
      </svg>
      <canvas ref={canvasRef} className="wenyou-rift-shards-canvas" />
    </div>
  );
}

function RiftOverlay({
  phase,
  count,
  results,
  revealed,
  onReveal,
  onRevealAll,
  onClose,
}: {
  phase: "opening" | "results";
  count: number;
  results: RiftPullResult[];
  revealed: string[];
  onReveal: (pullId: string) => void;
  onRevealAll: () => void;
  onClose: () => void;
}) {
  const allRevealed = results.length > 0 && results.every((item) => revealed.includes(item.pullId));
  const hasS = results.some((item) => item.rarity === "S");
  return (
    <div className={`wenyou-rift-overlay wenyou-rift-overlay-${phase} ${hasS ? "wenyou-rift-overlay-s" : ""}`} role="dialog" aria-modal="true">
      <div className="wenyou-rift-overlay-noise" />
      <div className="wenyou-rift-portal" />
      <RiftShatterLayer active={phase === "opening"} />
      <div className="wenyou-rift-results-wrap">
        {phase === "opening" ? (
          <div className="wenyou-rift-opening-text">
            <span>RIFT TRACE</span>
            <strong data-text="裂隙显影中">裂隙显影中</strong>
            <small>结果即将浮现</small>
          </div>
        ) : null}
        {phase === "results" && count === 1 ? (
          <div className="wenyou-rift-single">
            {results[0] ? <RiftCard item={results[0]} revealed={revealed.includes(results[0].pullId)} large onReveal={onReveal} /> : null}
          </div>
        ) : null}
        {phase === "results" && count !== 1 ? (
          <div className="wenyou-rift-results-scroll">
            <div className="wenyou-rift-results-grid">
              {results.map((item) => (
                <RiftCard key={item.pullId} item={item} revealed={revealed.includes(item.pullId)} onReveal={onReveal} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
      <div className={`wenyou-rift-overlay-actions ${phase === "results" ? "is-visible" : ""}`}>
        {count !== 1 ? <button onClick={onRevealAll} disabled={allRevealed}>全部显影</button> : null}
        <button onClick={onClose}>收束裂隙</button>
      </div>
    </div>
  );
}

function RiftCard({
  item,
  revealed,
  large,
  onReveal,
}: {
  item: RiftPullResult;
  revealed: boolean;
  large?: boolean;
  onReveal: (pullId: string) => void;
}) {
  const stars = Array.from({ length: riftRarityRank(item.rarity) });
  return (
    <button
      type="button"
      className={`wenyou-rift-card wenyou-rift-card-${item.rarity} ${large ? "wenyou-rift-card-large" : ""} ${revealed ? "is-revealed" : ""}`}
      onClick={() => onReveal(item.pullId)}
      aria-label={`显影 ${item.name}`}
    >
      <span className="wenyou-rift-card-inner">
        <span className="wenyou-rift-card-back">
          <i />
          <b>{item.sigil}</b>
        </span>
        <span className="wenyou-rift-card-front">
          <span className="wenyou-rift-card-art"><b>{item.sigil}</b></span>
          <span className="wenyou-rift-card-copy">
            <em>{item.rarity} // {item.kind}</em>
            <strong>{item.name}</strong>
            <small>{item.converted && item.converted_to ? `重复转化：${inventoryItemLabel(item.converted_to)}` : item.sealed ? `${itemDisplayDescription(item)}（阶位不足，已封印）` : itemDisplayDescription(item)}</small>
            <span>{stars.map((_, index) => <i key={index} />)}</span>
          </span>
        </span>
      </span>
    </button>
  );
}

function Header({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <div className="wenyou-sub-head">
      <button onClick={onBack} aria-label="返回"><Icon name="back" /></button>
      <h1>{title}</h1>
    </div>
  );
}

function FilterRow({ items, value, onChange }: { items: string[]; value: string; onChange: (value: string) => void }) {
  return (
    <div className="wenyou-filter-row">
      {items.map((item) => (
        <button key={item} className={item === value ? "active" : ""} onClick={() => onChange(item)}>
          {item}
        </button>
      ))}
    </div>
  );
}

function StoryFeedMessage({ text }: { text: string }) {
  const segments = parseStorySegments(text);
  return (
    <div className="wenyou-message-stack">
      {segments.map((segment) => (
        segment.kind === "system" ? (
          <SystemNotice key={segment.id} tone="cyan" label={segment.label || "系统提示"} text={segment.text} />
        ) : (
          <div key={segment.id} className="wenyou-story-text">{segment.text}</div>
        )
      ))}
    </div>
  );
}

function SystemNotice({ tone, label, text }: { tone: "cyan" | "purple"; label: string; text: string }) {
  return (
    <div className={`wenyou-notice wenyou-notice-${tone}`}>
      <strong>{label}</strong>
      <p>{text}</p>
    </div>
  );
}

function SettlementDraft({
  preview,
  result,
  rating,
  loading,
  onResult,
  onRating,
  onCancel,
  onConfirm,
}: {
  preview: WenyouSettlementPreview | null;
  result: string;
  rating: string;
  loading: boolean;
  onResult: (value: string) => void;
  onRating: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const reward = preview?.reward || {};
  const resultOptions = preview?.options?.results || [];
  const ratingOptions = preview?.options?.ratings || [];
  const score = Number(preview?.rating_score || 0);
  return (
    <div className="wenyou-settlement-draft">
      <div className="wenyou-settlement-head">
        <div>
          <span>结算预览</span>
          <strong>{preview?.result_label || "结算校准"}</strong>
        </div>
        <b>{preview?.rating_label || rating || "-"}</b>
      </div>
      <div className="wenyou-settlement-meter" aria-label={`评级分 ${score}`}>
        <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
      <div className="wenyou-settlement-meta">
        <span>完成度 {score}</span>
        <span>事件 {preview?.history_rounds ?? 0}</span>
        <span>{preview?.confidence === "manual" ? "手动核准" : "系统建议"}</span>
      </div>
      {preview?.reason ? <p className="wenyou-settlement-reason">{preview.reason}</p> : null}
      <div className="wenyou-settlement-reward">
        <div><span>积分</span><strong>+{reward.gross_points ?? reward.points_delta ?? 0}</strong></div>
        <div><span>EXP</span><strong>+{reward.gross_exp ?? reward.exp_delta ?? 0}</strong></div>
        <div><span>奖励</span><strong>{reward.reward_rolls ?? 0} 次</strong></div>
      </div>
      <div className="wenyou-settlement-breakdown">
        {(preview?.score_breakdown || []).map((item) => (
          <div key={item.id || item.label}>
            <span>{item.label}</span>
            <b>{item.score ?? 0}/{item.max ?? 0}</b>
          </div>
        ))}
      </div>
      <OptionStrip label="结果" items={resultOptions} value={result || preview?.result || ""} onChange={onResult} disabled={loading} />
      <OptionStrip label="评级" items={ratingOptions} value={rating || preview?.rating || ""} onChange={onRating} disabled={loading} />
      <div className="wenyou-settlement-confirm">
        <button onClick={onCancel} disabled={loading}>取消</button>
        <button onClick={onConfirm} disabled={loading}>{loading ? "结算中..." : "确认结算"}</button>
      </div>
    </div>
  );
}

function SettlementGranted({
  settlement,
  loading = false,
  onArchive,
}: {
  settlement: Record<string, unknown>;
  loading?: boolean;
  onArchive?: () => void;
}) {
  const rating = String(settlement.rating_label || settlement.rating || "-");
  const result = String(settlement.result_label || settlement.result || "已结算");
  return (
    <div className="wenyou-settlement-draft wenyou-settlement-granted">
      <div className="wenyou-settlement-head">
        <div>
          <span>SETTLEMENT READY</span>
          <strong>{result}</strong>
        </div>
        <b>{rating}</b>
      </div>
      <div className="wenyou-settlement-reward">
        <div><span>入账积分</span><strong>+{Number(settlement.points_delta || 0)}</strong></div>
        <div><span>EXP</span><strong>+{Number(settlement.exp_delta || 0)}</strong></div>
        <div><span>钱包</span><strong>{Number(settlement.wallet_points || 0)}</strong></div>
      </div>
      {onArchive ? (
        <div className="wenyou-settlement-confirm">
          <button type="button" onClick={onArchive} disabled={loading}>{loading ? "归档中..." : "归档本局"}</button>
        </div>
      ) : null}
    </div>
  );
}

function OptionStrip({
  label,
  items,
  value,
  onChange,
  disabled,
}: {
  label: string;
  items: WenyouSettlementOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  if (!items.length) return null;
  return (
    <div className="wenyou-settlement-options">
      <label>{label}</label>
      <div>
        {items.map((item) => (
          <button
            key={item.id}
            className={item.id === value ? "active" : ""}
            onClick={() => onChange(item.id)}
            disabled={disabled}
            title={item.desc}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function OptionGroup({ label, items, value, onChange, grid }: { label: string; items: string[]; value: string; onChange: (value: string) => void; grid?: boolean }) {
  return (
    <div className="wenyou-option-group">
      <label>{label}</label>
      <div className={grid ? "grid" : ""}>
        {items.map((item) => (
          <button key={item} className={item === value ? "active" : ""} onClick={() => onChange(item)}>{item}</button>
        ))}
      </div>
    </div>
  );
}

function AttributePointModal({
  title,
  points,
  acting,
  onAllocate,
  onClose,
}: {
  title: string;
  points: number;
  acting: boolean;
  onAllocate: (attr: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="wenyou-modal" role="dialog" aria-modal="true" aria-label="属性点分配">
      <button className="wenyou-modal-backdrop" onClick={onClose} aria-label="稍后分配属性点" />
      <div className="wenyou-random-panel wenyou-attribute-panel">
        <span className="wenyou-random-line" />
        <div className="wenyou-attribute-head">
          <small>{title}</small>
          <h2>获得 {points} 点属性点</h2>
          <p>这次奖励需要选择落点。角色面板只保留结果，成长规则由后端结算。</p>
        </div>
        <div className="wenyou-attribute-choice-grid">
          {ATTRIBUTE_CHOICES.map((item) => (
            <button key={item.key} type="button" onClick={() => onAllocate(item.key)} disabled={acting}>
              <strong>+{item.label}</strong>
              <span>{item.hint}</span>
            </button>
          ))}
        </div>
        <div className="wenyou-modal-actions">
          <button type="button" onClick={onClose} disabled={acting}>稍后</button>
          <button type="button" disabled>{points} 点待分配</button>
        </div>
      </div>
    </div>
  );
}

function PanelModal({
  view,
  session,
  initialTab,
  acting,
  onClose,
  onUseItem,
  onInventoryCommand,
}: {
  view: WenyouPanelView;
  session: WenyouSessionPanel | null;
  initialTab: WenyouPanelTab;
  acting: boolean;
  onClose: () => void;
  onUseItem: (item: WenyouInventoryItem | string) => void;
  onInventoryCommand: (
    item: WenyouInventoryItem | string,
    endpoint: "equip" | "repair" | "sell",
    label: string,
    body?: Record<string, unknown>
  ) => void;
}) {
  const [activeTab, setActiveTab] = useState<WenyouPanelTab>(initialTab);
  const stats = session?.stats || {};
  const publicState = getSessionPublicState(session);
  const rulesState = getSessionRulesState(session);
  const inventory = rulesState.inventory || session?.inventory || stats.inventory || [];
  const tasks = publicState.public_tasks?.length
    ? publicState.public_tasks
    : session?.task?.current
      ? [{
          id: "main_task",
          title: session.task.current,
          type: "main",
          status: session.phase === "settlement" ? "completed" : "active",
          fail_forward: session.task.failure_hint,
          reward_tags: session.task.reward_hint ? [session.task.reward_hint] : [],
        }]
      : [];
  const clues = (publicState.discovered_clues || []).filter(Boolean);
  const task = session?.task || {};
  const growthPlayers = session?.growth?.players || {};
  const tabs: WenyouPanelTab[] = ["任务", "背包", "角色"];
  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab, session?.gameId]);
  return (
    <div className="wenyou-modal">
      <button className="wenyou-modal-backdrop" onClick={onClose} aria-label="关闭面板" />
      <div className="wenyou-random-panel wenyou-panel-modal">
        <span className="wenyou-random-line" />
        <button className="wenyou-panel-close" onClick={onClose} aria-label="关闭面板"><Icon name="x" /></button>

        {!session ? <div className="wenyou-empty">当前没有进行中的副本。</div> : null}

        {session && view === "局内资料" ? (
          <>
            <div className="wenyou-panel-tabs" role="tablist" aria-label="局内资料导航">
              {tabs.map((tab) => (
                <button
                  type="button"
                  key={tab}
                  className={tab === activeTab ? "active" : ""}
                  onClick={() => setActiveTab(tab)}
                  role="tab"
                  aria-selected={tab === activeTab}
                >
                  {tab}
                </button>
              ))}
            </div>
            <div className="wenyou-panel-body">
              {activeTab === "任务" ? (
                <>
                  <div className="wenyou-panel-brief-grid">
                    <PanelRow label="当前阶段" value={task.phase || session.phase_label || "副本"} />
                    <PanelRow label="当前位置" value={currentLocationName(publicState)} />
                    {publicState.public_threat ? <PanelRow label="危险程度" value={publicState.public_threat} /> : null}
                  </div>
                  <div className="wenyou-panel-subtitle">任务与已确认线索</div>
                  {tasks.length ? tasks.map((item, index) => (
                    <TaskPanelCard item={item} key={`${taskTitle(item)}-${index}`} />
                  )) : <div className="wenyou-empty">暂无任务同步。</div>}
                  {clues.length ? clues.map((item, index) => (
                    <CluePanelCard item={item} key={`${clueTitle(item)}-${index}`} />
                  )) : <div className="wenyou-empty">暂无已确认线索。</div>}
                </>
              ) : null}

              {activeTab === "背包" ? (
                <InventoryList
                  inventory={inventory}
                  acting={acting}
                  onUseItem={onUseItem}
                  onInventoryCommand={onInventoryCommand}
                  emptyText="背包为空。"
                />
              ) : null}

              {activeTab === "角色" ? (
                <>
                  <div className="wenyou-panel-brief-grid">
                    <PanelRow label="主神积分" value={String(stats.points ?? session.wallet?.points ?? 0)} />
                    <PanelRow label="主神债务" value={String(session.wallet?.debts ?? 0)} />
                  </div>
                  <PlayerStatCard
                    title="玩家一"
                    player={stats.player1}
                    growth={growthPlayers.player1}
                  />
                  <PlayerStatCard
                    title="玩家二 · 渡"
                    player={stats.player2}
                    growth={growthPlayers.player2}
                  />
                </>
              ) : null}

            </div>
          </>
        ) : null}

      </div>
    </div>
  );
}

function InventoryList({
  inventory,
  acting,
  onUseItem,
  onInventoryCommand,
  emptyText = "背包为空。",
}: {
  inventory: Array<WenyouInventoryItem | string>;
  acting: boolean;
  onUseItem: (item: WenyouInventoryItem | string) => void;
  onInventoryCommand: (
    item: WenyouInventoryItem | string,
    endpoint: "equip" | "repair" | "sell",
    label: string,
    body?: Record<string, unknown>
  ) => void;
  emptyText?: string;
}) {
  if (!inventory.length) return <div className="wenyou-empty">{emptyText}</div>;
  return (
    <>
      {inventory.map((item, index) => {
        const detail = typeof item === "string" ? "" : itemDisplayDescription(item);
        const sealed = typeof item !== "string" && !!item.sealed;
        const lockedForSale = typeof item !== "string" && (!!item.equipped_by || !!item.quest_item || item.carry_out === false);
        return (
          <div className="wenyou-inventory-row" key={inventoryItemKey(item, index)}>
            <span>
              {inventoryItemLabel(item)}
              {typeof item !== "string" ? (
                <small>
                  {[item.rarity, item.category || item.kind, item.uses_left !== undefined ? `次数 ${item.uses_left}` : "", item.durability !== undefined ? `耐久 ${item.durability}/${item.durability_max ?? "?"}` : ""].filter(Boolean).join(" · ")}
                  {detail ? `｜${detail}` : ""}
                </small>
              ) : null}
            </span>
            <div className="wenyou-inventory-actions">
              {isGearInventoryItem(item) ? (
                <>
                  <button type="button" onClick={() => onInventoryCommand(item, "equip", "装备")} disabled={acting || sealed || !!item.broken}>装备</button>
                  <button type="button" onClick={() => onInventoryCommand(item, "repair", "维修")} disabled={acting}>维修</button>
                </>
              ) : (
                <button type="button" onClick={() => onUseItem(item)} disabled={acting || sealed}>{acting ? "演算中" : "使用"}</button>
              )}
              <button type="button" onClick={() => onInventoryCommand(item, "sell", "出售")} disabled={acting || lockedForSale}>出售</button>
            </div>
          </div>
        );
      })}
    </>
  );
}

function PanelRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="wenyou-panel-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TaskPanelCard({ item }: { item: WenyouTaskPanelItem }) {
  const title = taskTitle(item);
  const meta = taskMeta(item);
  const failForward = typeof item === "string" ? "" : compactPanelText(item.fail_forward);
  const required = typeof item === "string" ? [] : item.required_clues || item.related_clues || [];
  return (
    <div className="wenyou-task-row">
      <strong>{title}</strong>
      <span>{meta}</span>
      {required.length ? <small>关联线索：{required.join("、")}</small> : null}
      {failForward ? <small>失败推进：{failForward}</small> : null}
    </div>
  );
}

function CluePanelCard({ item }: { item: WenyouCluePanelItem }) {
  const title = clueTitle(item);
  const text = clueText(item);
  const meta = typeof item === "string"
    ? "discovered"
    : [item.status, item.verified ? "已验证" : "", item.source].map((it) => compactPanelText(it)).filter(Boolean).join(" · ");
  const related = typeof item === "string" ? [] : item.related_tasks || item.leads_to || [];
  return (
    <div className="wenyou-clue-row">
      <strong>{title}</strong>
      {meta ? <span>{meta}</span> : null}
      {text && text !== title ? <p>{text}</p> : null}
      {related.length ? <small>关联：{related.join("、")}</small> : null}
    </div>
  );
}

function MarkerPanelCard({ item }: { item: WenyouPublicMarker }) {
  const title = markerTitle(item);
  const text = markerText(item);
  const meta = markerMeta(item);
  const stability = typeof item === "string" ? "" : item.stability !== undefined && item.stability_max !== undefined ? `稳定度 ${item.stability}/${item.stability_max}` : "";
  const seal = typeof item === "string" ? "" : item.seal_progress !== undefined && item.seal_target !== undefined ? `封印 ${item.seal_progress}/${item.seal_target}` : "";
  const counterplay = typeof item === "string" ? "" : panelListText(item.counterplay, "");
  return (
    <div className="wenyou-marker-row">
      <strong>{title}</strong>
      {meta ? <span>{meta}</span> : null}
      {stability || seal ? <small>{[stability, seal].filter(Boolean).join(" · ")}</small> : null}
      {counterplay ? <small>处理：{counterplay}</small> : null}
      {text && text !== title ? <p>{text}</p> : null}
    </div>
  );
}

function HistoryPanelRow({ item }: { item: { role?: string; content?: string; timestamp?: string } }) {
  const roleMap: Record<string, string> = { gm: "GM", player1: "玩家一", player2: "渡", system: "系统" };
  const role = roleMap[String(item.role || "")] || String(item.role || "记录");
  return (
    <div className="wenyou-history-row">
      <span>{role}{item.timestamp ? ` · ${item.timestamp}` : ""}</span>
      <p>{String(item.content || "").trim()}</p>
    </div>
  );
}

function PlayerStatCard({
  title,
  player,
  compact = false,
  growth,
}: {
  title: string;
  player?: WenyouPlayerStats;
  compact?: boolean;
  growth?: WenyouGrowthPlayer;
}) {
  const p = player || {};
  const abilities = growth?.abilities || p.abilities || [];
  const dormantAbilities = growth?.dormant_abilities || p.dormant_abilities || [];
  const gear = p.gear || p.equipment || p.weapons || [];
  const abilitySlots = Number(growth?.ability_slots || 0);
  const rank = p.rank || "D";
  const num = (value: unknown) => {
    const n = Number(value ?? 0);
    return Number.isFinite(n) ? n : 0;
  };
  const pct = (value: unknown, max: unknown) => {
    const maxValue = num(max);
    if (maxValue <= 0) return 0;
    return Math.max(0, Math.min(100, (num(value) / maxValue) * 100));
  };
  const resources = [
    { label: "HP", value: num(p.hp), max: num(p.hp_max), tone: "hp" },
    { label: "SAN", value: num(p.san), max: num(p.san_max), tone: "san" },
  ];
  const attributes = [
    ["力", p.str],
    ["体", p.con ?? p.vit],
    ["敏", p.agi],
    ["智", p.int ?? p.wis],
    ["精", p.spi],
    ["运", p.luk],
  ];
  const battleStats = [
    ["攻击", p.physical_attack],
    ["防御", p.defense],
    ["先攻", p.initiative],
  ];
  const evolution = growth?.evolution || p.evolution || p.bloodline || "凡人";
  const abilitySummary = abilities.length
    ? abilities.map((it) => `${it.name || it.id}${it.level ? ` Lv${it.level}` : ""}`).filter(Boolean).join("、")
    : "无";
  const dormantSummary = dormantAbilities.length
    ? `休眠：${dormantAbilities.map((it) => it.name || it.id).filter(Boolean).join("、")}`
    : "";
  const gearSummary = gear.length ? gear.map(gearLabel).join("、") : "无";
  const conditionSummary = p.conditions?.length ? p.conditions.join("、") : "稳定";

  return (
    <article className="wenyou-stat-card">
      <header className="wenyou-character-head">
        <div>
          <h3>{title}</h3>
          <p>Lv{p.level ?? 1} · EXP {p.exp ?? 0}</p>
        </div>
        <span className="wenyou-rank-badge">{rank}</span>
      </header>

      <div className="wenyou-vital-stack" aria-label={`${title} 当前资源`}>
        {resources.map((row) => (
          <div className="wenyou-vital-line" key={row.label}>
            <span className="wenyou-vital-label">{row.label}</span>
            <i className="wenyou-vital-track" aria-hidden="true">
              <b className={`wenyou-vital-fill wenyou-vital-fill-${row.tone}`} style={{ width: `${pct(row.value, row.max)}%` }} />
            </i>
            <strong>{row.value}/{row.max}</strong>
          </div>
        ))}
      </div>

      <div className="wenyou-character-strip" aria-label={`${title} 派生数值`}>
        {battleStats.map(([label, value]) => (
          <span key={label}>
            <small>{label}</small>
            <b>{num(value)}</b>
          </span>
        ))}
      </div>

      <div className="wenyou-attr-board" aria-label={`${title} 基础属性`}>
        {attributes.map(([label, value]) => (
          <span key={String(label)} className="wenyou-attr-cell">
            <small>{label}</small>
            <b>{num(value)}</b>
          </span>
        ))}
      </div>

      {compact ? null : (
        <div className="wenyou-character-notes">
          <p><span>进化</span><strong>{evolution}{growth?.evolution_rank ? ` · ${growth.evolution_rank}` : ""}</strong></p>
          <p><span>能力</span><strong>{abilitySummary}{abilitySlots ? `（${abilities.length}/${abilitySlots}）` : ""}</strong></p>
          {dormantSummary ? <p><span>休眠</span><strong>{dormantSummary}</strong></p> : null}
          <p><span>装备</span><strong>{gearSummary}</strong></p>
          <p><span>状态</span><strong>{conditionSummary}</strong></p>
        </div>
      )}
    </article>
  );
}

function ArchiveCard({
  title,
  genre,
  difficulty,
  endedAt,
  turns,
  active,
  open,
  loading,
  detail,
  onPrimary,
  onRetry,
}: {
  title: string;
  genre: string;
  difficulty: string;
  endedAt?: string;
  turns: string;
  active?: boolean;
  open?: boolean;
  loading?: boolean;
  detail?: WenyouArchiveDetail;
  onPrimary: () => void;
  onRetry?: () => void;
}) {
  return (
    <article className={`wenyou-archive-card ${active ? "active" : ""}`}>
      <div className="wenyou-archive-top">
        <div>
          <span>{active ? "状态: 进行中" : "结局: 已归档"}</span>
          <h3>{title}</h3>
        </div>
        <time>{endedAt || "现在"}</time>
      </div>
      <div className="wenyou-archive-meta">
        <div><span>类型/难度</span><strong>{genre} / {difficulty}</strong></div>
        <div><span>历史回合</span><strong>{turns}</strong></div>
      </div>
      {open ? (
        <div className="wenyou-archive-detail">
          {loading ? "回顾载入中..." : detail?.framework?.conflict || detail?.framework?.world || "暂无详细回顾。"}
        </div>
      ) : null}
      <div className="wenyou-archive-actions">
        <button onClick={onPrimary}>{active ? "继续游玩" : open ? "收起回顾" : "查看回顾"}</button>
        {onRetry ? <button onClick={onRetry}>重新挑战</button> : null}
      </div>
    </article>
  );
}
