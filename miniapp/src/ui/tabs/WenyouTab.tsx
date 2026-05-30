import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";
import {
  clueText,
  clueTitle,
  compactPanelText,
  currentLocationName,
  getSessionPublicState,
  getSessionRulesState,
  inventoryActionKey,
  inventoryItemKey,
  inventoryItemLabel,
  inventoryMetaText,
  inventoryRequirementText,
  inventorySellBlockLabel,
  inventoryStatusBadges,
  inventoryItemName,
  inventoryUseBlockLabel,
  itemDisplayDescription,
  markerMeta,
  markerText,
  markerTitle,
  panelListText,
  playerDisplayName,
  replacePlayerAliasText,
  taskMeta,
  taskTitle,
} from "../wenyou/panelFormatters";
import { extractEntryScene, feedFromSessionHistory, parseStorySegments } from "../wenyou/storyParser";
import type {
  EntryScene,
  FeedItem,
  StoryActionOption,
  WenyouCluePanelItem,
  WenyouGrowthPlayer,
  WenyouGrowthView,
  WenyouHistoryItem,
  WenyouInventoryItem,
  WenyouPlayerStats,
  WenyouPublicMarker,
  WenyouPublicState,
  WenyouRulesState,
  WenyouSessionPanel,
  WenyouShopItem,
  WenyouShopView,
  WenyouTaskPanelItem,
  WenyouTeamChannel,
} from "../wenyou/types";
import wenyouCardRevealUrl from "../../assets/sfx/wenyou_card_reveal.flac";
import wenyouHubLoopUrl from "../../assets/sfx/wenyou_hub_loop.mp3";
import wenyouIntroLoopUrl from "../../assets/sfx/wenyou_intro_loop.mp3";
import wenyouKeyClickUrl from "../../assets/sfx/wenyou_key_click.wav";

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
  entry?: {
    tutorial_required?: boolean;
    player_name?: string;
    player2_name?: string;
    player_name_required?: boolean;
    player2_name_required?: boolean;
    tutorial_code?: string;
    tutorial_title?: string;
  };
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
  forced?: boolean;
  locked?: boolean;
  queue_id?: string;
  penalty_type?: string;
  reason?: string;
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

type RiftIconType =
  | "defense"
  | "heal"
  | "rule"
  | "clue"
  | "tool"
  | "escape"
  | "memory"
  | "supply"
  | "attack"
  | "material"
  | "special";

const TYPE_FILTERS = ["全部类型", "规则怪谈", "剧情解密", "大逃杀", "对抗", "生存撤离", "潜伏调查", "限时任务"];
const DIFFICULTY_FILTERS = ["全部难度", "D", "C", "B", "A", "S"];
const ARCHIVE_FILTERS = ["全部", "已完成", "死亡", "进行中"];
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
];

const ENCOUNTER_QUICK_ACTIONS: QuickAction[] = [
  { label: "攻击", text: "攻击当前可见威胁。", encounterAction: "attack" as const },
  { label: "逃跑", text: "尝试脱离当前遭遇。", encounterAction: "escape" as const },
];
const ATTRIBUTE_CHOICES = [
  { key: "str", label: "力", hint: "近战、破坏、搬运", tone: "str" },
  { key: "con", label: "体", hint: "生命、抗伤、耐力", tone: "con" },
  { key: "agi", label: "敏", hint: "闪避、潜行、追逐", tone: "agi" },
  { key: "int", label: "智", hint: "推理、识别、解谜", tone: "int" },
  { key: "spi", label: "精", hint: "精神力、抗污染", tone: "spi" },
  { key: "luk", label: "运", hint: "发现隐藏与奖励", tone: "luk" },
] as const;
const ATTRIBUTE_DISPLAY_MAX = 20;
const RIFT_SINGLE_COST = 100;
const RIFT_TEN_COST = 1000;
const STORY_EXPANSION_POLL_MS = 1200;
const STORY_EXPANSION_MAX_POLLS = 160;
function normalizeInitialView(view: WenyouInitialView): WenyouView {
  if (view === "archives") return "archive";
  if (view === "hub") return "home";
  return view;
}

function teammateDisplayName(name?: string) {
  const clean = String(name || "").trim();
  return clean && clean !== "玩家二" ? clean : "队友";
}

function selfDisplayName(name?: string) {
  const clean = String(name || "").trim();
  return clean && clean !== "玩家一" ? clean : "你";
}

function SignalText({
  as: Tag = "span",
  className = "",
  children,
}: {
  as?: "span" | "h1" | "h2" | "b";
  className?: string;
  children: string;
}) {
  return (
    <Tag className={`wenyou-signal-text ${className}`.trim()} aria-label={children}>
      <span className="wenyou-signal-main">{children}</span>
      <span className="wenyou-signal-layer wenyou-signal-layer-cyan" aria-hidden="true">{children}</span>
      <span className="wenyou-signal-layer wenyou-signal-layer-rose" aria-hidden="true">{children}</span>
    </Tag>
  );
}

function formatWenyouArchiveTime(value?: string) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
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
  if (name === "channel") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12a8 8 0 0 1 16 0" /><path d="M7 12a5 5 0 0 1 10 0" /><path d="M10 12a2 2 0 0 1 4 0" /><path d="M12 14v6" /></svg>;
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

function WalkieTalkieGlyph() {
  return (
    <span className="wenyou-walkie-glyph" aria-hidden="true">
      <svg viewBox="0 0 64 64" fill="none">
        <path className="walkie-antenna" d="M26 10v11" />
        <circle className="walkie-dot" cx="26" cy="9" r="3" />
        <rect className="walkie-body" x="17" y="21" width="27" height="34" rx="4" />
        <path className="walkie-side" d="M44 26h4v15h-4" />
        <path className="walkie-wave" d="M49 25c3 3 4.5 6 4.5 10S52 42 49 45" />
        <path className="walkie-wave" d="M45 29c1.8 1.8 2.6 3.7 2.6 6S46.8 39.2 45 41" />
        <text x="21" y="35" className="walkie-text">CH-T</text>
        <path className="walkie-slots" d="M23 40h15M23 44h15M23 48h15" />
      </svg>
    </span>
  );
}

function riftRarityRank(rarity: RiftRarity) {
  return { D: 1, C: 2, B: 3, A: 4, S: 5 }[rarity];
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

function riftIconType(item: { kind?: unknown; category?: unknown; name?: unknown; desc?: unknown }): RiftIconType {
  const raw = [item.kind, item.category, item.name, item.desc].map((it) => String(it || "")).join(" ").toLowerCase();
  if (/防|护|盾|甲|armor|defen|guard|protect/.test(raw)) return "defense";
  if (/治疗|治愈|恢复|药|绷带|急救|heal|hp|san|精神/.test(raw)) return "heal";
  if (/规则|改写|橡皮|主神|凭证|判定|rule/.test(raw)) return "rule";
  if (/线索|侦测|调查|证言|钥匙|收音机|clue|detect|search/.test(raw)) return "clue";
  if (/工具|手电|绳|撬|粉笔|维修|扳手|tool|wrench|flashlight/.test(raw)) return "tool";
  if (/撤离|出口|车票|门|位移|escape|door|gate/.test(raw)) return "escape";
  if (/记忆|精神|梦|针|memory|mind/.test(raw)) return "memory";
  if (/补给|口粮|氧气|蜡烛|supply|ration/.test(raw)) return "supply";
  if (/攻击|武器|斧|棍|刀|weapon|attack|combat/.test(raw)) return "attack";
  if (/材料|碎片|结晶|核心|残片|fragment|material|crystal/.test(raw)) return "material";
  return "special";
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

function installWenyouButtonSound(root: HTMLElement) {
  const pool = Array.from({ length: 4 }, () => {
    const audio = new Audio(wenyouKeyClickUrl);
    audio.preload = "auto";
    audio.volume = 0.5;
    return audio;
  });
  let cursor = 0;

  const play = () => {
    const audio = pool[cursor] || pool[0];
    cursor = (cursor + 1) % pool.length;
    try {
      audio.currentTime = 0;
      void audio.play().catch(() => undefined);
    } catch {
      // UI sound is optional; WebViews can block playback before user activation.
    }
  };

  const onClick = (event: MouseEvent) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest("button");
    if (!button || !root.contains(button)) return;
    const realButton = button as HTMLButtonElement;
    if (realButton.disabled || realButton.getAttribute("aria-disabled") === "true") return;
    play();
  };

  root.addEventListener("click", onClick, true);
  return () => {
    root.removeEventListener("click", onClick, true);
    for (const audio of pool) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
  };
}

const riftCardRevealSound = (() => {
  let pool: HTMLAudioElement[] | null = null;
  let cursor = 0;
  return () => {
    if (typeof window === "undefined") return;
    if (!pool) {
      pool = Array.from({ length: 5 }, () => {
        const audio = new Audio(wenyouCardRevealUrl);
        audio.preload = "auto";
        audio.volume = 0.62;
        return audio;
      });
    }
    const audio = pool[cursor] || pool[0];
    cursor = (cursor + 1) % pool.length;
    try {
      audio.currentTime = 0;
      void audio.play().catch(() => undefined);
    } catch {
      // Card reveal audio is decorative and can be blocked by the WebView.
    }
  };
})();

type WenyouMusicMode = "intro" | "hub" | "off";

const wenyouMusic = (() => {
  let current: HTMLAudioElement | null = null;
  let mode: WenyouMusicMode = "off";

  const stop = () => {
    if (!current) return;
    current.pause();
    current.currentTime = 0;
    current = null;
    mode = "off";
  };

  const play = (nextMode: Exclude<WenyouMusicMode, "off">) => {
    if (typeof window === "undefined") return;
    if (mode === nextMode && current) return;
    stop();
    const audio = new Audio(nextMode === "intro" ? wenyouIntroLoopUrl : wenyouHubLoopUrl);
    audio.loop = true;
    audio.preload = "auto";
    audio.volume = nextMode === "intro" ? 0.34 : 0.2;
    current = audio;
    mode = nextMode;
    try {
      void audio.play().catch(() => undefined);
    } catch {
      // Background music can be blocked until the WebView receives user input.
    }
  };

  return {
    setMode(nextMode: WenyouMusicMode) {
      if (nextMode === "off") stop();
      else play(nextMode);
    },
    stop,
  };
})();

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
  const shellRef = useRef<HTMLDivElement | null>(null);
  const normalizedInitialView = normalizeInitialView(initialView);
  const [view, setView] = useState<WenyouView>(() => normalizedInitialView);
  const viewRef = useRef<WenyouView>(normalizedInitialView);
  const viewHistoryRef = useRef<WenyouView[]>([]);
  const [spaceBootVisible, setSpaceBootVisible] = useState(() => normalizedInitialView === "home");
  const [spaceBootComplete, setSpaceBootComplete] = useState(false);
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
  const [statusLoading, setStatusLoading] = useState(true);
  const [status, setStatus] = useState<WenyouStatus>({ active: false, session: null });
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesRefreshing, setCandidatesRefreshing] = useState(false);
  const [candidates, setCandidates] = useState<InstanceCandidate[]>([]);
  const [candidateGeneratedAt, setCandidateGeneratedAt] = useState("");
  const [starting, setStarting] = useState(false);
  const [tutorialName, setTutorialName] = useState("");
  const [tutorialPlayerTwoName, setTutorialPlayerTwoName] = useState("");
  const [tutorialNameStep, setTutorialNameStep] = useState<"player1" | "player2">("player1");
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
  const [forcedPrompt, setForcedPrompt] = useState<InstanceCandidate | null>(null);
  const [forcedPromptLoading, setForcedPromptLoading] = useState(false);
  const riftPullTokenRef = useRef(0);
  const settlementAutoArchiveRef = useRef("");
  const settlementAutoPreviewRef = useRef("");
  const forcedPromptCheckRef = useRef("");
  const [sessionPanel, setSessionPanel] = useState<WenyouSessionPanel | null>(null);
  const [panelView, setPanelView] = useState<WenyouPanelView | null>(null);
  const [panelInitialTab, setPanelInitialTab] = useState<WenyouPanelTab>("任务");
  const [profileTab, setProfileTab] = useState<WenyouProfileTab>("副本存档");
  const [quickDecisionOpen, setQuickDecisionOpen] = useState(false);
  const [teamChannelOpen, setTeamChannelOpen] = useState(false);
  const [teamChannelText, setTeamChannelText] = useState("");
  const [teamChannelSending, setTeamChannelSending] = useState(false);
  const [entryScene, setEntryScene] = useState<EntryScene | null>(null);
  const [entryScenePending, setEntryScenePending] = useState(false);
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

  useEffect(() => {
    const root = shellRef.current;
    if (!root) return undefined;
    return installWenyouButtonSound(root);
  }, []);

  useEffect(() => () => wenyouMusic.stop(), []);

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
    if (teamChannelOpen) {
      setTeamChannelOpen(false);
      return true;
    }
    if (settlementDraftOpen) {
      setSettlementDraftOpen(false);
      return true;
    }
    if (entryScenePending) {
      return true;
    }
    if (randomOpen) {
      setRandomOpen(false);
      return true;
    }
    if (forcedPrompt) {
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
  }, [entryScenePending, forcedPrompt, normalizedInitialView, panelView, quickDecisionOpen, randomOpen, riftOverlay, settlementDraftOpen, teamChannelOpen]);

  useEffect(() => {
    viewRef.current = view;
    if (view !== "game") {
      setQuickDecisionOpen(false);
      setTeamChannelOpen(false);
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
      const j = await apiJson<{ ok?: boolean; active?: boolean; entry?: WenyouStatus["entry"]; session?: WenyouStatus["session"]; error?: string }>("/miniapp-api/wenyou/status");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      const rawSession = j.session || null;
      const hasPlayableSession = !!j.active && isPlayableWenyouStatusSession(rawSession);
      const nextStatus = { active: hasPlayableSession, entry: j.entry || undefined, session: hasPlayableSession ? rawSession : null };
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
      setCandidates(Array.isArray(j.items) ? j.items.filter((it) => !it?.forced) : []);
      setCandidateGeneratedAt(String(j.generatedAt || ""));
      if (j.warning) toast(j.warning);
    } catch (e: any) {
      toast(`加载副本候选失败：${e?.message || e}`);
    } finally {
      setCandidatesLoading(false);
      setCandidatesRefreshing(false);
    }
  }, [toast]);

  const loadForcedPrompt = useCallback(async () => {
    setForcedPromptLoading(true);
    try {
      const j = await apiJson<{
        ok?: boolean;
        forced?: boolean;
        item?: InstanceCandidate | null;
        items?: InstanceCandidate[];
        error?: string;
      }>("/miniapp-api/wenyou/forced-instance");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      const item = (j.item && j.item.forced ? j.item : null) || (Array.isArray(j.items) ? j.items.find((it) => it?.forced) : null) || null;
      setForcedPrompt(item);
      return item;
    } catch (e: any) {
      toast(`加载强制副本失败：${e?.message || e}`);
      return null;
    } finally {
      setForcedPromptLoading(false);
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
    setSpaceBootComplete(false);
    let width = 0;
    const interval = window.setInterval(() => {
      width = Math.min(100, width + 8 + Math.random() * 12);
      setSpaceBootProgress(width);
      if (width >= 100) {
        window.clearInterval(interval);
        window.setTimeout(() => setSpaceBootComplete(true), 350);
      }
    }, 150);
    return () => window.clearInterval(interval);
  }, [spaceBootVisible]);

  useEffect(() => {
    if (!spaceBootVisible || !spaceBootComplete || statusLoading) return;
    setSpaceBootFading(true);
    const timer = window.setTimeout(() => setSpaceBootVisible(false), 520);
    return () => window.clearTimeout(timer);
  }, [spaceBootComplete, spaceBootVisible, statusLoading]);

  useEffect(() => {
    const p1 = String(status.entry?.player_name || "").trim();
    const p2 = String(status.entry?.player2_name || "").trim();
    if (p1) setTutorialName((prev) => (prev.trim() ? prev : p1));
    if (p2) setTutorialPlayerTwoName((prev) => (prev.trim() ? prev : p2));
    if (p1 && !p2) setTutorialNameStep("player2");
    else if (!p1) setTutorialNameStep("player1");
  }, [status.entry?.player2_name, status.entry?.player_name]);

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
    if (!entryScene || entryScenePending) return;
    const timer = window.setTimeout(() => setEntryScene(null), 4200);
    return () => window.clearTimeout(timer);
  }, [entryScene, entryScenePending]);

  const sortedArchives = useMemo(
    () => (archives || []).slice().sort((a, b) => String(b.endedAt || "").localeCompare(String(a.endedAt || ""))),
    [archives]
  );

  const filteredCandidates = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return candidates.filter((item) => {
      if (item.forced) return false;
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
  const currentLocationFallback = status.session?.instance_name || sessionPanel?.framework?.instance_name || "未知区域";
  const currentLocation = currentLocationName(gamePublicState, currentLocationFallback);
  const hasPlayableStatus = !!status.active && isPlayableWenyouStatusSession(status.session);
  const hasPlayablePanel = isPlayableWenyouPanel(sessionPanel);
  const hasActiveRun = hasPlayableStatus || hasPlayablePanel;
  const hasPlayerOneCode = !!String(status.entry?.player_name || "").trim();
  const hasPlayerTwoCode = !!String(status.entry?.player2_name || "").trim();
  const hasPlayerCodes = hasPlayerOneCode && hasPlayerTwoCode;
  const isEntryResolving = view === "home" && !spaceBootVisible && statusLoading && !status.entry && !hasActiveRun;
  const needsTutorialIntro = !hasActiveRun && !statusLoading && !hasPlayerCodes;
  const hubMusicView = !spaceBootVisible && ["home", "archive", "selection", "shop", "rift"].includes(view);
  const musicMode: WenyouMusicMode = hubMusicView
    ? view === "home" && (needsTutorialIntro || isEntryResolving)
      ? "intro"
      : "hub"
    : "off";
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

  useEffect(() => {
    if (view !== "home") {
      forcedPromptCheckRef.current = "";
      return;
    }
    if (spaceBootVisible || statusLoading || hasActiveRun || forcedPrompt || forcedPromptLoading) return;
    const key = `${view}:${String(status.entry?.player_name || "")}:${String(status.entry?.player2_name || "")}`;
    if (forcedPromptCheckRef.current === key) return;
    forcedPromptCheckRef.current = key;
    void loadForcedPrompt();
  }, [
    forcedPrompt,
    forcedPromptLoading,
    hasActiveRun,
    loadForcedPrompt,
    spaceBootVisible,
    status.entry?.player2_name,
    status.entry?.player_name,
    statusLoading,
    view,
  ]);

  const gameSettlementReady = sessionPanel?.phase === "settlement" && !!sessionPanel.settlement;
  const gameAwaitingSettlement = sessionPanel?.phase === "settlement" && !sessionPanel.settlement;
  const homePlayer = sessionPanel?.stats?.player1 || gameRulesState.players?.player1 || {};
  const playerOneName = playerDisplayName(profileStats.player1 || gameRulesState.players?.player1 || homePlayer, String(status.entry?.player_name || "").trim() || "玩家一");
  const playerTwoName = playerDisplayName(profileStats.player2 || gameRulesState.players?.player2, String(status.entry?.player2_name || "").trim() || "玩家二");
  const playerOneTitle = selfDisplayName(playerOneName);
  const playerTwoTitle = teammateDisplayName(playerTwoName);
  const displayNarrativeText = useCallback((text: string) => replacePlayerAliasText(text, playerOneName, playerTwoName), [playerOneName, playerTwoName]);
  const aiPlayerActionLabel = `${playerTwoTitle}的行动`;
  const teamChannel = sessionPanel?.team_channel || null;
  const teamChannelLabel = teamChannel?.label || (hasActiveRun ? "信号稳定" : "未接入");
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
          title: player === "player1" ? selfDisplayName(playerDisplayName(statPlayer, playerOneName)) : teammateDisplayName(playerDisplayName(statPlayer, playerTwoName)),
          points: Number.isFinite(points) ? points : 0,
          key: `${player}:${rank}:${level}:${points}`,
        };
      })
      .filter((entry) => entry.points > 0);
  }, [playerOneName, playerTwoName, profileGrowthPlayers, profileStats]);
  const activeAttributePrompt = attributePointEntries.find((entry) => entry.player === attributePromptPlayer) || null;
  const gameCoreAbility = sessionPanel?.growth?.players?.player1?.core_ability || sessionPanel?.stats?.player1?.core_ability || null;
  const gamePlayerAbilities = gameCoreAbility?.id || gameCoreAbility?.name
    ? [{ id: String(gameCoreAbility.id || gameCoreAbility.name || ""), name: String(gameCoreAbility.name || gameCoreAbility.id || "核心能力") }]
    : [];
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
  const regularShopItems = regularShop?.items?.length ? regularShop.items : (shop?.items || []);
  const hubPoints = Number(shop?.points ?? sessionPanel?.wallet?.points ?? sessionPanel?.stats?.points ?? 0);
  const hubDebts = Number(shop?.debts ?? sessionPanel?.wallet?.debts ?? 0);

  useEffect(() => {
    wenyouMusic.setMode(musicMode);
  }, [musicMode]);
  const hubRank = String(homePlayer.rank || "E");
  const hubLevel = Number(homePlayer.level ?? 1);
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

  async function startStory(
    mode: "random" | "custom",
    keywords = "",
    fallback?: EntryScene,
    candidate?: InstanceCandidate,
    playerName = "",
    playerTwoName = "",
    options: { immediateEntry?: boolean } = {}
  ) {
    if (mode === "custom" && !keywords.trim() && !candidate) {
      toast("请填写任务描述");
      return;
    }
    setStarting(true);
    if (options.immediateEntry && fallback) {
      setActiveScene(fallback);
      setEntryScene(fallback);
      setEntryScenePending(true);
      resetView("game");
    }
    try {
      let j = await apiJson<WenyouStoryResponse>("/miniapp-api/wenyou/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          keywords: mode === "custom" ? keywords : "",
          candidate,
          player_name: playerName.trim(),
          player2_name: playerTwoName.trim(),
        }),
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
        if (options.immediateEntry) {
          setEntryScene(null);
          setEntryScenePending(false);
          resetView("home");
        }
        toast("检测到已有进行中副本，请再点一次以确认开新局");
        return;
      }
      const parsed = extractEntryScene(text);
      const scene = parsed.name === "未知副本" && fallback ? fallback : { ...(fallback || {}), ...parsed, name: parsed.name || fallback?.name || "未知副本" };
      setActiveScene(scene);
      setEntryScenePending(false);
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
      if (options.immediateEntry) {
        setEntryScene(null);
        setEntryScenePending(false);
        resetView("home");
        void loadForcedPrompt();
      }
      toast(`开局失败：${e?.message || e}`);
    } finally {
      setStarting(false);
    }
  }

  function startTutorialIntro() {
    const name = tutorialName.trim();
    const teammateName = tutorialPlayerTwoName.trim();
    if (!name) {
      toast("请输入你的代号");
      setTutorialNameStep("player1");
      return;
    }
    if (tutorialNameStep === "player1") {
      setTutorialNameStep("player2");
      return;
    }
    if (!teammateName) {
      toast("请输入你队友的代号");
      setTutorialNameStep("player2");
      return;
    }
    startStory(
      "random",
      "",
      {
        name: status.entry?.tutorial_title || "白箱回廊",
        code: status.entry?.tutorial_code || "T-000",
        genre: "剧情解密",
        difficulty: "D",
      },
      undefined,
      name,
      teammateName
    );
  }

  function startCandidate(item: InstanceCandidate) {
    const scene = { name: item.title, genre: item.instance_genre, difficulty: item.difficulty, code: item.id.toUpperCase() };
    setForcedPrompt(null);
    startStory("custom", "", scene, item, "", "", { immediateEntry: !!item.forced });
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

  function focusFreeActionInput() {
    setQuickDecisionOpen(false);
    window.setTimeout(() => actionInputRef.current?.focus(), 0);
  }

  async function submitAction(inputText?: string) {
    const text = String(inputText ?? actionText).trim();
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

  async function sendTeamChannel(inputText?: string) {
    const text = String(inputText ?? teamChannelText).trim();
    if (!text || teamChannelSending) return;
    setQuickDecisionOpen(false);
    setTeamChannelSending(true);
    try {
      const j = await apiJson<{
        ok?: boolean;
        message?: string;
        reply?: string;
        warning?: string;
        session?: WenyouSessionPanel;
        error?: string;
      }>("/miniapp-api/wenyou/team-channel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, window_id: windowId }),
      });
      if (!j?.ok) throw new Error(j?.error || "对讲机发送失败");
      if (j.session) setSessionPanel(j.session);
      if (j.warning) toast(j.warning);
      setTeamChannelText("");
    } catch (e: any) {
      toast(`对讲机失败：${e?.message || e}`);
    } finally {
      setTeamChannelSending(false);
    }
  }

  function handleStoryActionOption(option: StoryActionOption) {
    if (acting) return;
    if (option.free) {
      focusFreeActionInput();
      return;
    }
    setActionText(option.text);
    void submitAction(option.text);
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

  useEffect(() => {
    if (view !== "game" || !gameAwaitingSettlement || settlementDraftOpen || settlementLoading || settlementPreview) return;
    const key = `${sessionPanel?.gameId || ""}:${sessionPanel?.phase || ""}`;
    if (settlementAutoPreviewRef.current === key) return;
    settlementAutoPreviewRef.current = key;
    setSettlementDraftOpen(true);
    void loadSettlementPreview();
  }, [gameAwaitingSettlement, settlementDraftOpen, settlementLoading, settlementPreview, sessionPanel?.gameId, view]);

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
      const forced = await loadForcedPrompt();
      resetView(forced ? "home" : "archive");
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
      const forced = await loadForcedPrompt();
      resetView(forced ? "home" : "archive");
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
        const forced = await loadForcedPrompt();
        resetView(forced ? "home" : "archive");
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
  }, [loadArchives, loadForcedPrompt, loadStatus, resetView, sessionPanel?.gameId, sessionPanel?.phase, sessionPanel?.settlement, toast, view]);

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
    endpoint: "sell",
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
    setRiftRevealed((prev) => {
      if (prev.includes(pullId)) return prev;
      riftCardRevealSound();
      return [...prev, pullId];
    });
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

  const tutorialActiveName = tutorialNameStep === "player1" ? tutorialName : tutorialPlayerTwoName;
  const tutorialActiveLabel = tutorialNameStep === "player1" ? "你的代号" : "队友的代号";
  const tutorialPromptLine = tutorialNameStep === "player1" ? "【请输入你的代号】" : "【请输入你队友的代号】";
  const tutorialSubmitText = starting ? "接入中..." : tutorialNameStep === "player1" ? "确认代号" : "进入白箱回廊";

  return (
    <div ref={shellRef} className="wenyou-shell">
      <span className="wenyou-shell-grid" />
      <span className="wenyou-shell-scan" />

      {spaceBootVisible ? (
        <div className={`wenyou-space-entry ${spaceBootFading ? "wenyou-space-entry-hide" : ""}`} role="status" aria-live="polite">
          <div className="wenyou-space-entry-title">
            <SignalText as="h1" className="wenyou-signal-text-heavy">FATE NEXUS</SignalText>
            <SignalText as="h2" className="wenyou-space-entry-scan-title">REALITY LINK SCANNING...</SignalText>
          </div>
          <div className="wenyou-space-entry-track">
            <span style={{ width: `${spaceBootProgress}%` }} />
          </div>
          <p>Connecting to Fate Nexus</p>
        </div>
      ) : null}

      {entryScene ? (
        <div className={`wenyou-entry fixed inset-0 z-[80] ${entryScenePending ? "wenyou-entry-pending" : ""}`} role="status" aria-live="polite">
          <button
            type="button"
            className="wenyou-entry-stage relative h-full w-full overflow-hidden px-6 py-8 text-left"
            onClick={() => {
              if (!entryScenePending) setEntryScene(null);
            }}
            aria-label={entryScenePending ? "副本接入中" : "关闭入场动画"}
          >
            <span className="wenyou-entry-grid" />
            <span className="wenyou-entry-scan" />
            <span className="wenyou-entry-crt" />
            <span className="wenyou-entry-corner wenyou-entry-corner-tl" />
            <span className="wenyou-entry-corner wenyou-entry-corner-br" />
            <div className="wenyou-entry-header">
              <span>FATE NEXUS PROTOCOL</span>
            </div>
            <div className="wenyou-entry-inner">
              <div className="wenyou-entry-terminal">
                <span>{entryScenePending ? "CLEARANCE ROUTE LOCKED" : "NEURAL LINK ESTABLISHED"}</span>
                <span>{entryScenePending ? "INSTANCE GATE CONNECTING" : "INSTANCE GATE OPEN"}</span>
              </div>
              <div className="wenyou-entry-seal">{entryScene.code || "INSTANCE"}</div>
              <div className="wenyou-entry-kicker">{entryScenePending ? "正在接入" : "欢迎来到"}</div>
              <div className="wenyou-entry-title" data-text={entryScene.name}>{entryScene.name}</div>
              <div className="wenyou-entry-sub">{entryScenePending ? "入口已锁定，副本正在展开。" : "努力生存下去吧。"}</div>
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
        isEntryResolving ? (
        <section className="wenyou-screen wenyou-home wenyou-home-cyber wenyou-tutorial-gate wenyou-tutorial-gate-loading">
          <span className="wenyou-home-scanlines" aria-hidden="true" />
          <span className="wenyou-home-edge wenyou-home-edge-right" aria-hidden="true" />
          <span className="wenyou-home-edge wenyou-home-edge-left" aria-hidden="true" />
          <div className="wenyou-tutorial-copy">
            <SignalText>SYNCING TASKER FILE</SignalText>
            <SignalText as="h1" className="wenyou-signal-text-heavy">正在接入副本入口。</SignalText>
          </div>
        </section>
        ) : needsTutorialIntro ? (
        <section className="wenyou-screen wenyou-home wenyou-home-cyber wenyou-tutorial-gate">
          <span className="wenyou-home-scanlines" aria-hidden="true" />
          <span className="wenyou-home-edge wenyou-home-edge-right" aria-hidden="true" />
          <span className="wenyou-home-edge wenyou-home-edge-left" aria-hidden="true" />
          <div className="wenyou-home-debug wenyou-home-debug-left" aria-hidden="true">
            FILE: NEW_TASKER<br />
            INSTANCE: T-000<br />
            STATUS: AWAKE
          </div>
          <div className="wenyou-tutorial-copy">
            <SignalText>WHITE CORRIDOR // T-000</SignalText>
            <SignalText as="h1" className="wenyou-signal-text-heavy">你醒来的时候，耳边先是一阵很轻的电流声。</SignalText>
            <p>白光铺满视野，像有人把世界擦到只剩一种颜色。远处有一扇没有把手的门，门上浮着一行黑字。</p>
            <div className="wenyou-tutorial-terminal" aria-label="主神系统提示">
              <SignalText as="b">【新任务者档案未建立】</SignalText>
              <SignalText as="b">{tutorialPromptLine}</SignalText>
            </div>
          </div>
          <form
            className="wenyou-tutorial-form"
            onSubmit={(event) => {
              event.preventDefault();
              startTutorialIntro();
            }}
          >
            <label htmlFor="wenyou-tasker-name">{tutorialActiveLabel}</label>
            <input
              id="wenyou-tasker-name"
              value={tutorialActiveName}
              maxLength={16}
              autoComplete="off"
              onChange={(event) => {
                if (tutorialNameStep === "player1") setTutorialName(event.target.value);
                else setTutorialPlayerTwoName(event.target.value);
              }}
              disabled={starting}
            />
            <button type="submit" disabled={starting || !tutorialActiveName.trim()}>
              {tutorialSubmitText}
            </button>
          </form>
        </section>
        ) : (
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
            <div className="wenyou-home-brand">
              <span>FATE NEXUS</span>
              <strong>主神空间</strong>
            </div>
            <div className="wenyou-home-user">
              <span>等级阶位</span>
              <strong>{hubRank}阶 Lv.{hubLevel}</strong>
              <div className="wenyou-home-user-stats" aria-label="主神资产">
                <span><em>主神积分</em><b>{shopLoading ? "SYNC" : hubPoints.toLocaleString()}</b></span>
                <span><em>债务</em><b>{hubDebts.toLocaleString()}</b></span>
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
        )
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
              <span>{candidateGeneratedAt ? `上次生成：${candidateGeneratedAt.slice(0, 16).replace("T", " ")}` : "等待系统投放入口"}</span>
            </div>
            <button onClick={() => loadCandidates(true, search)} disabled={candidatesRefreshing || candidatesLoading}>
              {candidatesRefreshing ? "生成中..." : "换一批"}
            </button>
          </div>
          <div className="wenyou-search">
            <span>⌕</span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索副本，或写偏好让系统换一批..." />
          </div>
          <FilterRow items={TYPE_FILTERS} value={typeFilter} onChange={setTypeFilter} />
          <FilterRow items={DIFFICULTY_FILTERS} value={difficultyFilter} onChange={setDifficultyFilter} />
          <div className="wenyou-instance-list">
            {candidatesLoading ? <div className="wenyou-empty">系统正在排列副本入口...</div> : null}
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
            {!candidatesLoading && !filteredCandidates.length ? <div className="wenyou-empty">没有匹配的副本。换个筛选，或者让系统换一批。</div> : null}
          </div>
        </section>
      ) : null}

      {view === "game" ? (
        <section className="wenyou-screen wenyou-game">
          <div className="wenyou-game-top">
            <button onClick={() => void goBackInsideWenyou()} aria-label="返回"><Icon name="back" /></button>
            <div className="wenyou-game-title">
              <h2>{currentScene.name}</h2>
              <p><span />阶段: {sessionPanel?.phase_label || status.session?.phase_label || (status.active ? "进行中" : "模拟预览")}</p>
              <p className="wenyou-location-hint"><span />当前在 {currentLocation}</p>
            </div>
            <div className="wenyou-game-top-actions">
              {!gameSettlementReady && !gameAwaitingSettlement ? (
                <button
                  type="button"
                  className={`wenyou-team-channel-toggle wenyou-team-channel-toggle-top ${teamChannelOpen ? "active" : ""}`}
                  onClick={() => {
                    setQuickDecisionOpen(false);
                    setTeamChannelOpen((open) => !open);
                  }}
                  aria-expanded={teamChannelOpen}
                  aria-label={`打开对讲机，${teamChannelLabel}`}
                >
                  <WalkieTalkieGlyph />
                  <small>{teamChannelLabel}</small>
                </button>
              ) : null}
              <button
                className="wenyou-game-data-trigger"
                onClick={() => {
                  setQuickDecisionOpen(false);
                  setTeamChannelOpen(false);
                  openPanel("任务");
                }}
                aria-label="打开任务与背包"
              >
                <Icon name="list" />
              </button>
            </div>
          </div>
          {!gameSettlementReady && !gameAwaitingSettlement && teamChannelOpen ? (
            <div className="wenyou-team-channel-modal" role="dialog" aria-modal="true" aria-label="对讲机频道">
              <button
                type="button"
                className="wenyou-team-channel-scrim"
                onClick={() => setTeamChannelOpen(false)}
                aria-label="关闭对讲机"
              />
              <TeamChannelPanel
                channel={teamChannel}
                peerName={playerTwoTitle}
                text={teamChannelText}
                sending={teamChannelSending}
                disabled={false}
                onText={setTeamChannelText}
                onClose={() => setTeamChannelOpen(false)}
                onSend={(value) => void sendTeamChannel(value)}
              />
            </div>
          ) : null}

          <div className="wenyou-feed">
            {feed.length ? <div className="wenyou-time-chip">{feedTimeLabel}</div> : null}
            {feed.length ? feed.map((item) => {
              const itemText = displayNarrativeText(item.text);
              if (item.kind === "user") return <div key={item.id} className="wenyou-user-bubble">{itemText}</div>;
              if (item.kind === "notice") return <SystemNotice key={item.id} tone="cyan" label="任务更新" text={itemText} />;
              if (item.kind === "loot") return <SystemNotice key={item.id} tone="purple" label="获得物品" text={itemText} />;
              if (item.kind === "ai_player") return <SystemNotice key={item.id} tone="purple" label={aiPlayerActionLabel} text={itemText} />;
              return <StoryFeedMessage key={item.id} text={itemText} disabled={acting || gameAwaitingSettlement} onAction={handleStoryActionOption} />;
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
            {!gameSettlementReady && (settlementDraftOpen || gameAwaitingSettlement) ? (
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
            {!gameSettlementReady && !gameAwaitingSettlement && quickDecisionOpen ? (
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
            {!gameSettlementReady && !gameAwaitingSettlement ? (
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
                  <button type="button" onClick={() => submitAction()} aria-label="发送行动" disabled={acting}><Icon name="send" /></button>
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
        <section className="wenyou-screen wenyou-profile-screen">
          <div className="wenyou-profile-hero">
            <button type="button" className="wenyou-profile-back" onClick={() => void goBackInsideWenyou()} aria-label="返回">
              <Icon name="back" />
            </button>
            <div className="wenyou-profile-title">
              <h1>个人空间</h1>
              <p>PERSONAL SPACE</p>
            </div>
            <div className="wenyou-profile-status" aria-label="个人空间状态">
              <span>STATUS : STABLE</span>
              <span>ONLINE</span>
              <span>SYNC : NORMAL</span>
              <span>MENTAL STATE : CLEAN</span>
            </div>
          </div>
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
                <span>背包库存</span>
                <strong>{profileInventory.length}</strong>
                <em>{profileInventory.length ? "可调取物品" : "暂无可用物品"}</em>
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
              <PlayerStatCard
                title={playerOneTitle}
                player={profileStats.player1 || gameRulesState.players?.player1}
                growth={profileGrowthPlayers.player1}
              />
              <PlayerStatCard
                title={playerTwoTitle}
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

      {forcedPrompt ? (
        <ForcedInstanceModal
          candidate={forcedPrompt}
          loading={starting || forcedPromptLoading}
          onEnter={() => startCandidate(forcedPrompt)}
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
          playerOneName={playerOneName}
          playerTwoName={playerTwoName}
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
  const [detailItem, setDetailItem] = useState<RiftPullResult | null>(null);
  const allRevealed = results.length > 0 && results.every((item) => revealed.includes(item.pullId));
  const hasS = results.some((item) => item.rarity === "S");
  const closeDetail = () => setDetailItem(null);
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
            {results[0] ? <RiftCard item={results[0]} revealed={revealed.includes(results[0].pullId)} large onReveal={onReveal} onInspect={setDetailItem} /> : null}
          </div>
        ) : null}
        {phase === "results" && count !== 1 ? (
          <div className="wenyou-rift-results-scroll">
            <div className="wenyou-rift-results-grid">
              {results.map((item) => (
                <RiftCard key={item.pullId} item={item} revealed={revealed.includes(item.pullId)} onReveal={onReveal} onInspect={setDetailItem} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
      {detailItem ? <RiftItemDetail item={detailItem} onClose={closeDetail} /> : null}
      <div className={`wenyou-rift-overlay-actions ${phase === "results" ? "is-visible" : ""}`}>
        {count !== 1 ? <button onClick={onRevealAll} disabled={allRevealed}>全部显影</button> : null}
        <button onClick={onClose}>收束裂隙</button>
      </div>
    </div>
  );
}

function RiftItemGlyph({ type }: { type: RiftIconType }) {
  const stroke = "currentColor";
  const common = { fill: "none", stroke, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (type === "defense") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="M32 8 50 15v14c0 13-7 22-18 27C21 51 14 42 14 29V15l18-7Z" /><path {...common} d="M32 15v32M22 27h20" /></svg>;
  }
  if (type === "heal") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="M25 10h14M28 10v9l-8 8v22c0 4 3 7 7 7h10c4 0 7-3 7-7V27l-8-8v-9" /><path {...common} d="M32 31v14M25 38h14" /></svg>;
  }
  if (type === "rule") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="M18 8h22l8 8v40H18V8Z" /><path {...common} d="M40 8v10h10M24 28h16M24 36h13M24 44h9" /><path {...common} d="m43 38 5 5-9 9-5 1 1-5 8-10Z" /></svg>;
  }
  if (type === "clue") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><circle {...common} cx="28" cy="28" r="15" /><path {...common} d="m39 39 13 13M23 28h10M28 23v10" /></svg>;
  }
  if (type === "tool") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="M44 10a13 13 0 0 0-15 17L12 44a6 6 0 0 0 8 8l17-17a13 13 0 0 0 17-15l-9 9-10-10 9-9Z" /></svg>;
  }
  if (type === "escape") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="M18 9h26v46H18V9Z" /><path {...common} d="M44 32h12M50 26l6 6-6 6M36 32h.1" /></svg>;
  }
  if (type === "memory") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="M8 32s9-15 24-15 24 15 24 15-9 15-24 15S8 32 8 32Z" /><circle {...common} cx="32" cy="32" r="7" /><path {...common} d="M32 9v5M18 14l3 5M46 14l-3 5" /></svg>;
  }
  if (type === "supply") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="M12 22 32 11l20 11v21L32 54 12 43V22Z" /><path {...common} d="M12 22 32 33l20-11M32 33v21M22 17l20 11" /></svg>;
  }
  if (type === "attack") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="m48 8 8 8-30 30-10 2 2-10L48 8Z" /><path {...common} d="m38 18 8 8M16 48l-8 8" /></svg>;
  }
  if (type === "material") {
    return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="m32 7 16 18-16 32-16-32L32 7Z" /><path {...common} d="M16 25h32M32 7v50M23 25l9 32 9-32" /></svg>;
  }
  return <svg viewBox="0 0 64 64" aria-hidden="true"><path {...common} d="M32 7 52 19v26L32 57 12 45V19L32 7Z" /><path {...common} d="M32 7v18M12 19l20 12 20-12M32 31v26" /><path {...common} d="m24 20 8-5 8 5" /></svg>;
}

function RiftCard({
  item,
  revealed,
  large,
  onReveal,
  onInspect,
}: {
  item: RiftPullResult;
  revealed: boolean;
  large?: boolean;
  onReveal: (pullId: string) => void;
  onInspect: (item: RiftPullResult) => void;
}) {
  const stars = Array.from({ length: riftRarityRank(item.rarity) });
  const iconType = item.converted && item.converted_to ? "material" : riftIconType(item);
  return (
    <button
      type="button"
      className={`wenyou-rift-card wenyou-rift-card-${item.rarity} ${large ? "wenyou-rift-card-large" : ""} ${revealed ? "is-revealed" : ""}`}
      onClick={() => (revealed ? onInspect(item) : onReveal(item.pullId))}
      aria-label={revealed ? `查看 ${item.name}` : `显影 ${item.name}`}
    >
      <span className="wenyou-rift-card-inner">
        <span className="wenyou-rift-card-back">
          <i />
          <b>{item.sigil}</b>
        </span>
        <span className="wenyou-rift-card-front">
          <span className="wenyou-rift-card-art">
            <span className={`wenyou-rift-item-icon wenyou-rift-item-icon-${iconType}`}>
              <RiftItemGlyph type={iconType} />
            </span>
          </span>
          <span className="wenyou-rift-card-copy">
            <em>{item.rarity} // {item.kind}</em>
            <strong>{item.name}</strong>
            <span>{stars.map((_, index) => <i key={index} />)}</span>
          </span>
        </span>
      </span>
    </button>
  );
}

function RiftItemDetail({ item, onClose }: { item: RiftPullResult; onClose: () => void }) {
  const detail = item.converted && item.converted_to
    ? `重复获得，已转化为：${inventoryItemLabel(item.converted_to)}。`
    : item.sealed
      ? `${itemDisplayDescription(item) || "道具效果待鉴定"}（阶位不足，已封印）`
      : itemDisplayDescription(item) || "道具效果待鉴定。";
  return (
    <div className="wenyou-rift-detail" role="dialog" aria-modal="true">
      <button type="button" className="wenyou-rift-detail-close" onClick={onClose} aria-label="关闭详情"><Icon name="x" /></button>
      <span>{item.rarity} // {item.kind}</span>
      <strong>{item.name}</strong>
      <p>{detail}</p>
    </div>
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

function StoryFeedMessage({
  text,
  disabled,
  onAction,
}: {
  text: string;
  disabled?: boolean;
  onAction: (option: StoryActionOption) => void;
}) {
  const segments = parseStorySegments(text);
  return (
    <div className="wenyou-message-stack">
      {segments.map((segment) => (
        segment.kind === "actions" ? (
          <ActionOptions key={segment.id} options={segment.options || []} disabled={disabled} onAction={onAction} />
        ) : segment.kind === "system" ? (
          <SystemNotice key={segment.id} tone="cyan" label={segment.label || "系统提示"} text={segment.text} />
        ) : (
          <div key={segment.id} className="wenyou-story-text">{segment.text}</div>
        )
      ))}
    </div>
  );
}

function TeamChannelPanel({
  channel,
  peerName,
  text,
  sending,
  disabled,
  onText,
  onClose,
  onSend,
}: {
  channel: WenyouTeamChannel | null;
  peerName: string;
  text: string;
  sending: boolean;
  disabled?: boolean;
  onText: (value: string) => void;
  onClose: () => void;
  onSend: (value?: string) => void;
}) {
  const messages = Array.isArray(channel?.messages) ? channel?.messages || [] : [];
  const blocked = !!channel?.blocked;
  const frequency = channel?.frequency || "CH-02";
  const status = String(channel?.status || "online");
  const noise = Number(channel?.noise ?? 0);
  const safeNoise = Number.isFinite(noise) ? Math.max(0, Math.min(100, Math.round(noise))) : 0;
  const signalBars = blocked || status === "offline" || status === "interrupted"
    ? 1
    : Math.max(2, Math.min(8, 8 - Math.floor(safeNoise / 14)));
  const quickMessages = [
    { label: "呼叫队友", text: "收到吗？你那边现在安全吗？" },
    { label: "报位置", text: "报一下你的位置和周围最明显的东西。" },
    { label: "交换线索", text: "我这边有新线索，我们对一下规则。" },
    { label: "约定会合", text: "找一个相对安全的位置会合，你能走哪条路线？" },
  ];
  const formatLogTime = (value?: string) => {
    const date = value ? new Date(value) : null;
    if (!date || Number.isNaN(date.getTime())) return "--:--:--";
    return date.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  const formatChannelText = (value?: string) => String(value || "")
    .replace(/玩家一/g, "你")
    .replace(/玩家二/g, peerName);
  return (
    <div className={`wenyou-team-channel-panel wenyou-channel-state-${status}`}>
      <span className="wenyou-team-channel-corner tl" />
      <span className="wenyou-team-channel-corner tr" />
      <span className="wenyou-team-channel-corner bl" />
      <span className="wenyou-team-channel-corner br" />
      <div className="wenyou-team-channel-head">
        <span className="wenyou-team-channel-pill"><i />{channel?.label || "信号稳定"}</span>
        <span>COMMS-LINK</span>
        <button type="button" onClick={onClose} aria-label="关闭对讲机">关闭</button>
      </div>
      <div className="wenyou-team-channel-frequency">
        <span>队友频道 // {peerName}</span>
        <strong>{frequency}</strong>
        <span>{channel?.current_location || "位置未同步"}</span>
        <div className="wenyou-team-channel-signal" aria-label={`信号强度 ${signalBars}/8`}>
          {Array.from({ length: 8 }, (_, index) => <i key={index} className={index < signalBars ? "active" : ""} />)}
        </div>
      </div>
      <div className="wenyou-team-channel-wave" aria-hidden="true">
        <span>REAL-TIME_SIG_STREAM</span>
        {Array.from({ length: 18 }, (_, index) => <i key={index} style={{ animationDelay: `${index * -0.07}s` }} />)}
      </div>
      {channel?.risk ? <p className="wenyou-team-channel-risk">{formatChannelText(channel.risk)}</p> : null}
      <div className="wenyou-team-channel-log">
        {messages.length ? messages.slice(-8).map((item, index) => (
          <div
            key={item.id || `${item.sender}-${index}`}
            className={`wenyou-team-channel-msg ${item.sender === "player1" ? "from-self" : item.sender === "player2" ? "from-peer" : "from-system"}`}
          >
            <span className="wenyou-team-channel-time">{formatLogTime(item.timestamp)}</span>
            <p>{formatChannelText(item.text)}</p>
            <em>{item.sender === "player1" ? "你" : item.sender === "player2" ? peerName : "系统"}</em>
          </div>
        )) : <div className="wenyou-team-channel-empty">对讲机暂无记录</div>}
      </div>
      <div className="wenyou-team-channel-quick">
        {quickMessages.map((item) => (
          <button key={item.label} type="button" disabled={disabled || sending || blocked} onClick={() => onSend(item.text)}>
            {item.label}
          </button>
        ))}
      </div>
      <div className="wenyou-team-channel-input">
        <input
          value={text}
          onChange={(e) => onText(e.target.value)}
          placeholder={blocked ? "信号中断..." : sending ? "调频中..." : `按住频段发给${peerName}...`}
          disabled={disabled || sending || blocked}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSend();
          }}
        />
        <button type="button" disabled={disabled || sending || blocked || !text.trim()} onClick={() => onSend()}>
          <Icon name="send" />
          <span>发送</span>
        </button>
      </div>
      <div className="wenyou-team-channel-sys">
        <span>队友频道不消耗回合</span>
        <span>{blocked ? "LINK_BLOCKED" : sending ? "TRANSMITTING" : "READY"}</span>
      </div>
    </div>
  );
}

function ActionOptions({
  options,
  disabled,
  onAction,
}: {
  options: StoryActionOption[];
  disabled?: boolean;
  onAction: (option: StoryActionOption) => void;
}) {
  if (!options.length) return null;
  return (
    <div className="wenyou-action-options" aria-label="行动选项">
      {options.map((option) => (
        <button
          key={option.key}
          type="button"
          className={option.free ? "wenyou-action-option-free" : ""}
          disabled={disabled}
          onClick={() => onAction(option)}
        >
          <span>{option.key}</span>
          <b>{option.text}</b>
        </button>
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

function ForcedInstanceModal({
  candidate,
  loading,
  onEnter,
}: {
  candidate: InstanceCandidate;
  loading: boolean;
  onEnter: () => void;
}) {
  const title = candidate.title || "强制扮演副本";
  const reason = candidate.core_task || candidate.premise || "你和队友将以副本原住民身份接入，维持身份，并推动正常任务者接近主线。";
  const streamLog = [
    "0XFF001 IDENTITY_MASK_REQUIRED",
    "0XFF002 NPC_ROLE_BOUND",
    "0XFF003 TASKER_ROUTE_OBSERVED",
    "0XFF004 SPOILER_CHANNEL_BLOCKED",
    "0XFF005 SCENE_LOGIC_LOCKED",
    "0XFF006 DIRECT_EXIT_DENIED",
    "0XFF007 COMMS_MONITORED",
    "0XFF008 ROLE_EXPOSURE_WARN",
    "0XFF009 INSTANCE_LOCKED",
    "0XFF010 RETURN_GATE_CLOSED",
  ].join("\n");
  return (
    <div className="wenyou-modal wenyou-forced-modal" role="dialog" aria-modal="true" aria-label="强制惩罚副本">
      <span className="wenyou-modal-backdrop" aria-hidden="true" />
      <div className="wenyou-forced-panel">
        <div className="wenyou-forced-stream" aria-hidden="true">
          <pre>{streamLog}{`\n${streamLog}\n${streamLog}`}</pre>
        </div>
        <span className="wenyou-forced-scanline" aria-hidden="true" />
        <div className="wenyou-forced-content">
          <div className="wenyou-forced-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
              <path d="M12 9v4" />
              <path d="M12 17h.01" />
            </svg>
          </div>
          <h2>IDENTITY LOCKED</h2>
          <p>
            强制扮演 / {candidate.difficulty || "C"} 级：{title} 已锁定。{reason}
          </p>
          <div className="wenyou-forced-actions">
            <button className="wenyou-forced-enter" onClick={onEnter} disabled={loading}>{loading ? "接入中" : "进入副本"}</button>
          </div>
        </div>
        <span className="wenyou-forced-corner wenyou-forced-corner-tl" aria-hidden="true" />
        <span className="wenyou-forced-corner wenyou-forced-corner-tr" aria-hidden="true" />
        <span className="wenyou-forced-corner wenyou-forced-corner-bl" aria-hidden="true" />
        <span className="wenyou-forced-corner wenyou-forced-corner-br" aria-hidden="true" />
      </div>
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
          <span>副本报告预览</span>
          <strong>{preview?.result_label || "结算校准"}</strong>
        </div>
        <b>{preview?.rating_label || rating || "-"}</b>
      </div>
      <div className="wenyou-settlement-meter" aria-label={`评级分 ${score}`}>
        <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
      <div className="wenyou-settlement-meta">
        <span>评级分 {score}</span>
        <span>回合 {preview?.history_rounds ?? 0}</span>
        <span>{preview?.confidence === "manual" ? "手动确认" : "规则预估"}</span>
      </div>
      {preview?.reason ? <p className="wenyou-settlement-reason"><b>评级依据</b>{preview.reason}</p> : null}
      <div className="wenyou-settlement-reward">
        <div><span>积分入账</span><strong>+{reward.gross_points ?? reward.points_delta ?? 0}</strong></div>
        <div><span>经验</span><strong>+{reward.gross_exp ?? reward.exp_delta ?? 0}</strong></div>
        <div><span>掉落机会</span><strong>{reward.reward_rolls ?? 0} 次</strong></div>
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
  const rewardRolls = Number(settlement.reward_rolls || 0);
  return (
    <div className="wenyou-settlement-draft wenyou-settlement-granted">
      <div className="wenyou-settlement-head">
        <div>
          <span>副本报告已归档</span>
          <strong>{result}</strong>
        </div>
        <b>{rating}</b>
      </div>
      <div className="wenyou-settlement-reward">
        <div><span>入账积分</span><strong>+{Number(settlement.points_delta || 0)}</strong></div>
        <div><span>经验</span><strong>+{Number(settlement.exp_delta || 0)}</strong></div>
        <div><span>掉落机会</span><strong>{rewardRolls} 次</strong></div>
      </div>
      <div className="wenyou-settlement-meta">
        <span>当前积分 {Number(settlement.wallet_points || 0)}</span>
        {settlement.debt_delta ? <span>债务变化 {Number(settlement.debt_delta || 0)}</span> : null}
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
  playerOneName,
  playerTwoName,
  onClose,
  onUseItem,
  onInventoryCommand,
}: {
  view: WenyouPanelView;
  session: WenyouSessionPanel | null;
  initialTab: WenyouPanelTab;
  acting: boolean;
  playerOneName: string;
  playerTwoName: string;
  onClose: () => void;
  onUseItem: (item: WenyouInventoryItem | string) => void;
  onInventoryCommand: (
    item: WenyouInventoryItem | string,
    endpoint: "sell",
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
                    <PanelRow label="当前位置" value={currentLocationName(publicState, session.framework?.instance_name || "当前副本")} />
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
                    title={selfDisplayName(playerDisplayName(stats.player1, playerOneName))}
                    player={stats.player1}
                    growth={growthPlayers.player1}
                  />
                  <PlayerStatCard
                    title={teammateDisplayName(playerDisplayName(stats.player2, playerTwoName))}
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
    endpoint: "sell",
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
        const broken = typeof item !== "string" && !!item.broken;
        const lockedForSale = typeof item !== "string" && (!!item.quest_item || item.carry_out === false || !!item.temporary || !!item.unique || !!item.bound);
        const requirements = typeof item === "string" ? "" : inventoryRequirementText(item);
        const badges = typeof item === "string" ? [] : inventoryStatusBadges(item);
        const meta = typeof item === "string" ? "" : inventoryMetaText(item);
        return (
          <div className={`wenyou-inventory-row ${sealed ? "sealed" : ""} ${broken ? "broken" : ""}`} key={inventoryItemKey(item, index)}>
            <span className="wenyou-inventory-main">
              <strong>{inventoryItemLabel(item)}</strong>
              {typeof item !== "string" ? (
                <>
                  <em className="wenyou-inventory-badges">
                    {badges.map((badge) => <b key={badge}>{badge}</b>)}
                  </em>
                  {meta ? <small>{meta}</small> : null}
                  {detail ? <small>{detail}</small> : null}
                  {item.sealed_reason || requirements ? <small className="wenyou-inventory-warning">{item.sealed_reason || `解封条件：${requirements}`}</small> : null}
                </>
              ) : null}
            </span>
            <div className="wenyou-inventory-actions">
              <button type="button" onClick={() => onUseItem(item)} disabled={acting || sealed || broken}>{typeof item === "string" ? (acting ? "演算中" : "使用") : inventoryUseBlockLabel(item, acting)}</button>
              <button type="button" onClick={() => onInventoryCommand(item, "sell", "出售")} disabled={acting || lockedForSale}>{typeof item === "string" ? "出售" : inventorySellBlockLabel(item)}</button>
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
  const roleMap: Record<string, string> = { gm: "GM", player1: "你", player2: "队友", system: "系统" };
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
  const coreAbility = growth?.core_ability || p.core_ability || null;
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
  const attrValue = (key: typeof ATTRIBUTE_CHOICES[number]["key"]) => {
    if (key === "con") return num(p.con ?? p.vit);
    if (key === "int") return num(p.int ?? p.wis);
    return num(p[key]);
  };
  const attributes = ATTRIBUTE_CHOICES.map((attr) => {
    const value = attrValue(attr.key);
    return {
      ...attr,
      value,
      fill: Math.max(0, Math.min(100, (value / ATTRIBUTE_DISPLAY_MAX) * 100)),
    };
  });
  const battleStats = [
    ["攻击", p.physical_attack],
    ["防御", p.defense],
    ["精神抗性", p.mental_resist],
  ];
  const abilitySummary = coreAbility?.name || "新手副本通关后生成";
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
        {attributes.map((attr) => (
          <span key={attr.key} className={`wenyou-attr-meter wenyou-attr-meter-${attr.tone}`}>
            <small>{attr.label}</small>
            <i className="wenyou-attr-meter-track" aria-hidden="true">
              <em style={{ width: `${attr.fill}%` }} />
            </i>
            <b>{attr.value}</b>
          </span>
        ))}
      </div>

      {compact ? null : (
        <div className="wenyou-character-notes">
          <p><span>核心能力</span><strong>{abilitySummary}</strong></p>
          {coreAbility?.desc ? <p><span>效果</span><strong>{coreAbility.desc}</strong></p> : null}
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
  const endedAtLabel = formatWenyouArchiveTime(endedAt);
  return (
    <article className={`wenyou-archive-card ${active ? "active" : ""}`}>
      <div className="wenyou-archive-top">
        <div>
          <span>{active ? "状态: 进行中" : "结局: 已归档"}</span>
          <h3>{title}</h3>
        </div>
        <time>{endedAtLabel || "现在"}</time>
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
