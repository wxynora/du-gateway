import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type WenyouView = "home" | "selection" | "game" | "archive" | "shop" | "rift";
type WenyouInitialView = WenyouView | "archives" | "hub";

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

type WenyouShopItem = {
  id: string;
  name: string;
  kind: string;
  rarity: string;
  price: number;
  desc: string;
};

type WenyouShopView = {
  active?: boolean;
  can_buy?: boolean;
  phase?: string;
  phaseLabel?: string;
  points?: number;
  inventory?: string[];
  generatedAt?: string;
  items?: WenyouShopItem[];
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
  kind: "user" | "system" | "notice" | "loot" | "du";
  text: string;
};

type WenyouPlayerStats = {
  hp?: number;
  hp_max?: number;
  san?: number;
  san_max?: number;
  level?: number;
  rank?: string;
  exp?: number;
  vit?: number;
  wis?: number;
  bloodline?: string;
  abilities?: Array<{ name?: string; desc?: string }>;
  weapons?: string[];
  conditions?: string[];
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
    inventory?: string[];
  };
  wallet?: { points?: number; debts?: number; total_exp?: number } | null;
  settlement?: Record<string, unknown> | null;
  inventory?: string[];
  clues?: string[];
  history?: Array<{ role?: string; content?: string; timestamp?: string }>;
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
};

const TYPE_FILTERS = ["全部类型", "规则怪谈", "剧情解密", "大逃杀", "对抗", "生存撤离", "潜伏调查", "限时任务"];
const DIFFICULTY_FILTERS = ["全部难度", "D", "C", "B", "A", "S"];
const ARCHIVE_FILTERS = ["全部", "已完成", "死亡", "放弃", "进行中"];
const QUICK_ACTIONS = [
  { label: "观察", text: "观察周围环境，留意异常细节。" },
  { label: "检查", text: "检查离我最近的可疑物。" },
  { label: "交谈", text: "尝试和当前场景里的人交谈。" },
  { label: "移动", text: "寻找可以前往的下一个地点。" },
  { label: "使用", text: "打开背包，选择一个合适的物品使用。" },
];
const RIFT_SINGLE_COST = 100;
const RIFT_TEN_COST = 1000;
const RIFT_POOL: Record<RiftRarity, RiftItem[]> = {
  D: [
    { id: "d-bandage", name: "应急绷带", rarity: "D", kind: "物资", desc: "一次性治疗道具。", sigil: "BND" },
    { id: "d-candle", name: "白蜡烛", rarity: "D", kind: "规则", desc: "短暂标记安全区域。", sigil: "CDL" },
    { id: "d-rope", name: "安全绳", rarity: "D", kind: "工具", desc: "降低坠落与脱队风险。", sigil: "RPE" },
  ],
  C: [
    { id: "c-radio", name: "静电收音机", rarity: "C", kind: "线索", desc: "偶尔捕获副本广播残响。", sigil: "RAD" },
    { id: "c-id", name: "空白身份牌", rarity: "C", kind: "潜伏", desc: "可写入一次临时身份。", sigil: "ID" },
    { id: "c-bottle", name: "证言瓶", rarity: "C", kind: "记忆", desc: "封存一段关键证词。", sigil: "MEM" },
  ],
  B: [
    { id: "b-eraser", name: "规则橡皮", rarity: "B", kind: "干涉", desc: "验证性擦除一条低级规则。", sigil: "DEL" },
    { id: "b-ticket", name: "主神治疗券", rarity: "B", kind: "治疗", desc: "结算或安全场景恢复重伤。", sigil: "HEAL" },
    { id: "b-thread", name: "血色牵引线", rarity: "B", kind: "追踪", desc: "锁定一个目标的残留路线。", sigil: "LINE" },
  ],
  A: [
    { id: "a-door", name: "门钥碎片", rarity: "A", kind: "撤离", desc: "拼合后可开启异常出口。", sigil: "GATE" },
    { id: "a-pod", name: "回溯急救仓", rarity: "A", kind: "治疗", desc: "结算阶段移除严重状态。", sigil: "POD" },
    { id: "a-pen", name: "弱改写笔", rarity: "A", kind: "规则", desc: "短暂改写一个可验证条件。", sigil: "PEN" },
  ],
  S: [
    { id: "s-receipt", name: "主神小票", rarity: "S", kind: "凭证", desc: "申请复核一次主神判定。", sigil: "VOID" },
    { id: "s-echo", name: "主神残响", rarity: "S", kind: "能力", desc: "封印体，需阶位解锁完整效果。", sigil: "ECHO" },
    { id: "s-needle", name: "记忆缝针", rarity: "S", kind: "记忆", desc: "缝合一次被污染的关键记忆。", sigil: "NEED" },
  ],
};

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

function difficultyStars(value?: string) {
  const map: Record<string, number> = { 新手: 1, 普通: 2, 困难: 3, 噩梦: 5, D: 1, C: 2, B: 3, A: 4, S: 5 };
  const count = map[String(value || "")] || 3;
  return "★".repeat(count) + "☆".repeat(Math.max(0, 5 - count));
}

function colorClass(value?: string) {
  const key = String(value || "");
  if (key === "对抗" || key === "A" || key === "S") return "wenyou-chip-rose";
  if (key === "潜伏调查" || key === "规则怪谈") return "wenyou-chip-purple";
  if (key === "生存撤离" || key === "D") return "wenyou-chip-green";
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
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M6 7v13h12V7M9 11h6M7 3h10l2 4H5l2-4Z" /></svg>;
  }
  if (name === "shop") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 10h14l-1.2 10H6.2L5 10Z" /><path d="M8 10V8a4 4 0 0 1 8 0v2" /><path d="M4 10h16" /></svg>;
  }
  if (name === "play") {
    return <svg className={common} viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7L8 5Z" /></svg>;
  }
  if (name === "list") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></svg>;
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

function pickRiftRarity(): RiftRarity {
  const roll = Math.random() * 100;
  if (roll < 0.3) return "S";
  if (roll < 4.0) return "A";
  if (roll < 16.0) return "B";
  if (roll < 50.0) return "C";
  return "D";
}

function pickRiftItem(rarity: RiftRarity): RiftItem {
  const pool = RIFT_POOL[rarity] || RIFT_POOL.D;
  return pool[Math.floor(Math.random() * pool.length)] || RIFT_POOL.D[0];
}

function generateRiftResults(count: number): RiftPullResult[] {
  const results = Array.from({ length: count }, (_, index) => {
    const rarity = pickRiftRarity();
    return { ...pickRiftItem(rarity), pullId: `rift-${Date.now()}-${index}-${Math.random().toString(16).slice(2)}` };
  });
  if (count === 10 && !results.some((item) => riftRarityRank(item.rarity) >= riftRarityRank("C"))) {
    const item = pickRiftItem("C");
    results[results.length - 1] = { ...item, pullId: `rift-${Date.now()}-guaranteed` };
  }
  return results;
}

export function WenyouTab({ initialView = "home" }: { initialView?: WenyouInitialView }) {
  const toast = useToast();
  const normalizedInitialView = normalizeInitialView(initialView);
  const [view, setView] = useState<WenyouView>(() => normalizedInitialView);
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
  const [sessionPanel, setSessionPanel] = useState<WenyouSessionPanel | null>(null);
  const [panelView, setPanelView] = useState<"任务" | "背包" | "状态" | "线索" | null>(null);
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
  const actionInputRef = useRef<HTMLInputElement | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([
    {
      id: "scene-1",
      kind: "system",
      text: "你站在三楼尽头的走廊里，空气中弥漫着陈旧木头和消毒水混合的怪味。应急灯闪着微弱的绿光，墙上的影子像被拉长的手。",
    },
    { id: "notice-1", kind: "notice", text: "任务更新：尝试确认这堵“不存在”的墙壁。" },
    { id: "loot-1", kind: "loot", text: "获得物品：【染血的校徽】已放入背包。" },
  ]);

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
      const nextStatus = { active: !!j.active, session: j.session || null };
      setStatus(nextStatus);
      if (nextStatus.active && nextStatus.session?.instance_name) {
        setActiveScene({
          name: nextStatus.session.instance_name || "未命名副本",
          code: nextStatus.session.instance_code || undefined,
          genre: nextStatus.session.instance_genre || undefined,
          difficulty: nextStatus.session.difficulty || undefined,
        });
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
      setSessionPanel(j.active ? (j.session || null) : null);
      return j.session || null;
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
      setShop({
        active: !!j.active,
        can_buy: !!j.can_buy,
        phase: String(j.phase || ""),
        phaseLabel: String(j.phaseLabel || ""),
        points: Number(j.points || 0),
        inventory: Array.isArray(j.inventory) ? j.inventory : [],
        generatedAt: String(j.generatedAt || ""),
        items: Array.isArray(j.items) ? j.items : [],
      });
    } catch (e: any) {
      toast(`加载系统商店失败：${e?.message || e}`);
    } finally {
      setShopLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadStatus();
    loadArchives();
  }, [loadStatus, loadArchives]);

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
    if (view === "selection" && !candidates.length && !candidatesLoading) {
      loadCandidates(false);
    }
  }, [candidates.length, candidatesLoading, loadCandidates, view]);

  useEffect(() => {
    if (view === "game") {
      loadSessionPanel();
    }
  }, [loadSessionPanel, view]);

  useEffect(() => {
    if (view === "shop") {
      loadShop();
    }
  }, [loadShop, view]);

  useEffect(() => {
    if (view === "rift") {
      loadShop();
      loadSessionPanel();
    }
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

  const currentScene: EntryScene = activeScene || {
    name: status.session?.instance_name || "幽灵校舍：不存在的404室",
    code: status.session?.instance_code || "ZS-9527",
    genre: status.session?.instance_genre || "规则怪谈",
    difficulty: status.session?.difficulty || "普通",
  };
  const riftPointRaw = shop?.points ?? sessionPanel?.wallet?.points;
  const riftPoints = riftPointPreview ?? (riftPointRaw == null ? 10000 : Number(riftPointRaw || 0));

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
      setShop({
        active: !!j.active,
        can_buy: !!j.can_buy,
        phase: String(j.phase || ""),
        phaseLabel: String(j.phaseLabel || ""),
        points: Number(j.points || 0),
        inventory: Array.isArray(j.inventory) ? j.inventory : [],
        generatedAt: String(j.generatedAt || ""),
        items: Array.isArray(j.items) ? j.items : [],
      });
      toast(j.message || `已购买【${item.name}】`);
      await loadSessionPanel();
    } catch (e: any) {
      toast(`购买失败：${e?.message || e}`);
    } finally {
      setShopBuyingId("");
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

  async function startStory(mode: "random" | "custom", keywords = "", fallback?: EntryScene, candidate?: InstanceCandidate) {
    if (mode === "custom" && !keywords.trim() && !candidate) {
      toast("请填写任务描述");
      return;
    }
    setStarting(true);
    try {
      const j = await apiJson<{ ok?: boolean; text?: string; need_confirm_new_game?: boolean; error?: string }>("/miniapp-api/wenyou/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, keywords: mode === "custom" ? keywords : "", candidate }),
      });
      if (!j?.ok) throw new Error(j?.error || "开局失败");
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
        { id: `notice-${Date.now()}`, kind: "notice", text: "任务更新：确认当前环境，找到第一条可行动线索。" },
      ]);
      setView("game");
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
    setView("selection");
    loadCandidates(true, keywords);
  }

  async function submitAction() {
    const text = actionText.trim();
    if (!text) return;
    setActing(true);
    try {
      const j = await apiJson<{ ok?: boolean; text?: string; du_action?: string; session?: WenyouSessionPanel; error?: string }>("/miniapp-api/wenyou/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, player: "player1", auto_go: true }),
      });
      if (!j?.ok) throw new Error(j?.error || "行动失败");
      const gmText = String(j.text || "");
      const duAction = String(j.du_action || "").trim();
      const stamp = Date.now();
      setFeed((prev) => [
        ...prev,
        { id: `u-${stamp}`, kind: "user", text },
        ...(duAction ? [{ id: `du-${stamp}`, kind: "du" as const, text: duAction }] : []),
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
      const text = String(j.text || "已进入结算。");
      setFeed((prev) => [...prev, { id: `settlement-${Date.now()}`, kind: "notice", text }]);
      setSettlementDraftOpen(false);
      setSettlementPreview(null);
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
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
      setSettlementDraftOpen(false);
      setSettlementPreview(null);
      setSettlementResult("");
      setSettlementRating("");
      await loadStatus();
      await loadArchives();
      setView("archive");
    } catch (e: any) {
      toast(`归档失败：${e?.message || e}`);
    } finally {
      setSettlementLoading(false);
    }
  }

  function showPlaceholder(name: string) {
    setPanelView(name as "任务" | "背包" | "状态" | "线索");
    loadSessionPanel();
  }

  function useInventoryItem(item: string) {
    const next = `使用道具【${item}】：`;
    setActionText(next);
    setPanelView(null);
    toast("已填入行动，发送后才结算本轮");
    window.setTimeout(() => actionInputRef.current?.focus(), 0);
  }

  function startRiftPull(count: 1 | 10) {
    const cost = count === 1 ? RIFT_SINGLE_COST : RIFT_TEN_COST;
    if (riftOverlay !== "closed") return;
    if (riftPoints < cost) {
      toast("主神积分不足，裂隙没有响应");
      return;
    }
    setRiftPointPreview(Math.max(0, riftPoints - cost));
    setRiftPullCount(count);
    setRiftResults(generateRiftResults(count));
    setRiftRevealed([]);
    setRiftOverlay("opening");
    window.setTimeout(() => setRiftOverlay("results"), 920);
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
        <section className="wenyou-screen wenyou-home">
          <div className="wenyou-page-head">
            <div>
              <div className="wenyou-title-mark"><span />主神空间</div>
              <p>{statusLoading ? "同步主神空间..." : `编号: ${currentScene.code || "ZS-9527"} | 等级: E-`}</p>
            </div>
            <div className="wenyou-page-head-actions">
              <button className="wenyou-icon-btn wenyou-icon-btn-rift" onClick={() => setView("rift")} aria-label="命运裂隙">
                <Icon name="rift" />
              </button>
              <button className="wenyou-icon-btn" onClick={() => setView("shop")} aria-label="系统商店">
                <Icon name="shop" />
              </button>
            </div>
          </div>

          <div className="wenyou-instance-card">
            <div className="wenyou-instance-glow" />
            <div className="wenyou-instance-body">
              <div className="wenyou-instance-top">
                <div>
                  <span className={`wenyou-chip ${colorClass("rose")}`}>{currentScene.genre || "未知类型"}</span>
                  <h2>{currentScene.name}</h2>
                </div>
                <span className="wenyou-difficulty">难度: {difficultyStars(currentScene.difficulty)}</span>
              </div>
              <div className="wenyou-objectives">
                <div><i /> <strong>当前阶段</strong><span>{status.active ? (status.session?.phase_label || "副本中") : "等待接入"}</span></div>
                <div><i /> <strong>当前目标</strong><span>找到第一条可验证线索，并活过开场。</span></div>
              </div>
              <div className="wenyou-bars">
                <StatusBar label="生命值 VIT" value={85} tone="green" />
                <StatusBar label="理智值 SAN" value={62} tone="cyan" />
                <StatusBar label="污染度 INF" value={12} tone="purple" />
              </div>
            </div>
          </div>

          <div className="wenyou-home-actions">
            <button className="wenyou-primary-btn" onClick={() => status.active || activeScene ? setView("game") : setView("selection")}>
              <Icon name="play" />{status.active || activeScene ? "继续副本" : "开始副本"}
            </button>
            <div className="wenyou-action-grid">
              <button onClick={() => setView("selection")}><Icon name="list" />选择副本</button>
              <button onClick={() => setRandomOpen(true)}><Icon name="shuffle" />随机进入</button>
            </div>
          </div>
        </section>
      ) : null}

      {view === "shop" ? (
        <section className="wenyou-screen">
          <Header title="系统商店" onBack={() => setView("home")} />
          <div className="wenyou-shop-brief">
            <div>
              <span>主神积分</span>
              <strong>{shopLoading ? "同步中" : String(shop?.points ?? 0)}</strong>
              {shop?.phaseLabel ? <em>{shop.phaseLabel}</em> : null}
            </div>
            <div className="wenyou-shop-brief-actions">
              <button onClick={() => setView("rift")}><Icon name="rift" />命运裂隙</button>
              <button onClick={() => setView("archive")}><Icon name="archive" />历史归档</button>
            </div>
          </div>
          <div className="wenyou-generation-status">
            <div>
              <strong>今日货架</strong>
              <span>{shop?.generatedAt ? `${shop.generatedAt} 刷新 · ${shop?.items?.length || 0} 件商品` : "系统正在配货"}</span>
            </div>
            <button onClick={loadShop} disabled={shopLoading}>{shopLoading ? "同步中..." : "同步"}</button>
          </div>
          {!shopLoading && !shop?.can_buy ? (
            <div className="wenyou-shop-lock">
              {shop?.active
                ? "副本进行中，系统商店关闭；只能使用背包已有物品，进入结算后再购买。"
                : "当前没有可写入背包的副本。开始副本或进入结算阶段后，可用主神积分购买道具。"}
            </div>
          ) : null}
          <div className="wenyou-shop-grid">
            {shopLoading ? <div className="wenyou-empty">主神商店正在校准货架...</div> : null}
            {(shop?.items || []).map((item) => {
              const owned = (shop?.inventory || []).includes(item.name);
              const disabled = !shop?.can_buy || owned || shopBuyingId === item.id || Number(shop?.points || 0) < Number(item.price || 0);
              return (
                <article key={item.id} className={`wenyou-shop-card wenyou-shop-rarity-${item.rarity || "D"}`}>
                  <div className="wenyou-shop-card-top">
                    <span>{item.kind || "道具"}</span>
                    <strong>{item.rarity || "D"}</strong>
                  </div>
                  <h3>{item.name}</h3>
                  <p>{item.desc}</p>
                  <div className="wenyou-shop-card-bottom">
                    <b>{item.price} pts</b>
                    <button onClick={() => buyShopItem(item)} disabled={disabled}>
                      {owned ? "已拥有" : shopBuyingId === item.id ? "购买中" : "购买"}
                    </button>
                  </div>
                </article>
              );
            })}
            {!shopLoading && !(shop?.items || []).length ? <div className="wenyou-empty">今日货架为空。</div> : null}
          </div>
        </section>
      ) : null}

      {view === "rift" ? (
        <section className="wenyou-screen wenyou-rift-screen">
          <div className="wenyou-rift-noise" />
          <div className="wenyou-rift-top">
            <button onClick={() => setView("home")} aria-label="返回主神空间"><Icon name="back" /></button>
            <div>
              <h1>命运裂隙</h1>
              <p>FATE RIFT // MIXED POOL</p>
            </div>
            <button onClick={() => setView("shop")} aria-label="系统商店"><Icon name="shop" /></button>
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
              <div><span>S RATE</span><strong>0.3%</strong></div>
              <i />
              <div><span>A RATE</span><strong>3.7%</strong></div>
              <i />
              <div><span>B RATE</span><strong>12%</strong></div>
            </div>
          </main>

          <footer className="wenyou-rift-footer">
            <p>裂隙展开 / 命运信号同步 / 数据显影</p>
            <div className="wenyou-rift-currency">
              <span>主神积分</span>
              <strong>{shopLoading ? "同步中" : riftPoints.toLocaleString()}</strong>
            </div>
            <div className="wenyou-rift-actions">
              <button onClick={() => startRiftPull(1)} disabled={riftOverlay !== "closed" || riftPoints < RIFT_SINGLE_COST}>
                <span>裂隙牵引 x1</span>
                <b>{RIFT_SINGLE_COST}</b>
              </button>
              <button onClick={() => startRiftPull(10)} disabled={riftOverlay !== "closed" || riftPoints < RIFT_TEN_COST}>
                <em>保底 C+</em>
                <span>裂隙牵引 x10</span>
                <b>{RIFT_TEN_COST}</b>
              </button>
            </div>
          </footer>
        </section>
      ) : null}

      {view === "selection" ? (
        <section className="wenyou-screen">
          <Header title="副本大厅" onBack={() => setView("home")} />
          <div className="wenyou-generation-status">
            <div>
              <strong>候选设定池</strong>
              <span>{candidateGeneratedAt ? `上次生成：${candidateGeneratedAt.slice(0, 16).replace("T", " ")}` : "未生成候选"}</span>
            </div>
            <button onClick={() => loadCandidates(true, search)} disabled={candidatesRefreshing || candidatesLoading}>
              {candidatesRefreshing ? "生成中..." : "刷新候选"}
            </button>
          </div>
          <div className="wenyou-search">
            <span>⌕</span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索候选，或作为刷新关键词..." />
          </div>
          <FilterRow items={TYPE_FILTERS} value={typeFilter} onChange={setTypeFilter} />
          <FilterRow items={DIFFICULTY_FILTERS} value={difficultyFilter} onChange={setDifficultyFilter} />
          <div className="wenyou-instance-list">
            {candidatesLoading ? <div className="wenyou-empty">主神正在生成候选设定池...</div> : null}
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
                  {starting ? "扩展中..." : "选中并扩展"}
                </button>
              </article>
            ))}
            {!candidatesLoading && !filteredCandidates.length ? <div className="wenyou-empty">没有匹配的候选。换个筛选，或者刷新生成一批。</div> : null}
          </div>
        </section>
      ) : null}

      {view === "game" ? (
        <section className="wenyou-screen wenyou-game">
          <div className="wenyou-game-top">
            <button onClick={() => setView("home")} aria-label="返回主神空间"><Icon name="back" /></button>
            <div>
              <h2>{currentScene.name}</h2>
              <p><span />阶段: {sessionPanel?.phase_label || status.session?.phase_label || (status.active ? "进行中" : "模拟预览")}</p>
            </div>
            <button onClick={() => showPlaceholder("状态")}>VIT</button>
          </div>

          <div className="wenyou-feed">
            <div className="wenyou-time-chip">{new Date().toLocaleDateString()} 23:45:12</div>
            {feed.map((item) => {
              if (item.kind === "user") return <div key={item.id} className="wenyou-user-bubble">{item.text}</div>;
              if (item.kind === "notice") return <SystemNotice key={item.id} tone="cyan" label="任务更新" text={item.text} />;
              if (item.kind === "loot") return <SystemNotice key={item.id} tone="purple" label="获得物品" text={item.text} />;
              if (item.kind === "du") return <SystemNotice key={item.id} tone="purple" label="渡的行动" text={item.text} />;
              return <div key={item.id} className="wenyou-story-text">{item.text}</div>;
            })}
          </div>

          <div className="wenyou-command">
            <div className="wenyou-panel-shortcuts">
              {["任务", "背包", "状态", "线索"].map((item) => (
                <button key={item} onClick={() => showPlaceholder(item)}>{item}</button>
              ))}
            </div>
            <div className="wenyou-quick-actions">
              {QUICK_ACTIONS.map((item) => (
                <button key={item.label} onClick={() => setActionText(item.text)}>
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
            {sessionPanel?.phase === "settlement" && sessionPanel.settlement ? (
              <SettlementGranted settlement={sessionPanel.settlement} />
            ) : null}
            {sessionPanel?.phase !== "settlement" && settlementDraftOpen ? (
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
            <div className="wenyou-settlement-actions">
              {sessionPanel?.phase === "settlement" ? (
                <>
                  <button onClick={() => setView("shop")} disabled={settlementLoading}>系统商店</button>
                  <button onClick={archiveSettlement} disabled={settlementLoading}>{settlementLoading ? "归档中..." : "归档本局"}</button>
                </>
              ) : (
                <button onClick={openSettlementDraft} disabled={acting || settlementLoading}>{settlementLoading ? "结算校准中..." : "申请结算"}</button>
              )}
            </div>
            <div className="wenyou-input-row">
              <input ref={actionInputRef} value={actionText} onChange={(e) => setActionText(e.target.value)} placeholder={acting ? "主神演算中..." : "输入你的行动..."} disabled={acting} onKeyDown={(e) => { if (e.key === "Enter") submitAction(); }} />
              <button onClick={submitAction} aria-label="发送行动" disabled={acting}><Icon name="send" /></button>
            </div>
          </div>
        </section>
      ) : null}

      {view === "archive" ? (
        <section className="wenyou-screen">
          <Header title="历史归档" onBack={() => setView("home")} />
          <FilterRow items={ARCHIVE_FILTERS} value={archiveFilter} onChange={setArchiveFilter} />
          <div className="wenyou-archive-list">
            {archiveFilter === "进行中" && status.active ? (
              <ArchiveCard active title={currentScene.name} genre={currentScene.genre || "未知"} difficulty={currentScene.difficulty || "-"} turns="进行中" onPrimary={() => setView("game")} />
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
        </section>
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
              <button onClick={startRandom} disabled={candidatesRefreshing}>{candidatesRefreshing ? "生成中..." : "生成候选池"}</button>
            </div>
          </div>
        </div>
      ) : null}

      {panelView ? (
        <PanelModal
          view={panelView}
          session={sessionPanel}
          acting={acting}
          onClose={() => setPanelView(null)}
          onUseItem={useInventoryItem}
        />
      ) : null}
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
      <div className="wenyou-rift-results-wrap">
        {phase === "opening" ? (
          <div className="wenyou-rift-opening-text">
            <span>FATE SIGNAL</span>
            <strong>裂隙展开中</strong>
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
        {count !== 1 ? <button onClick={onRevealAll} disabled={allRevealed}>REVEAL DATA</button> : null}
        <button onClick={onClose}>CONFIRM SYNCHRONY</button>
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
            <small>{item.desc}</small>
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

function StatusBar({ label, value, tone }: { label: string; value: number; tone: "green" | "cyan" | "purple" }) {
  return (
    <div className={`wenyou-status wenyou-status-${tone}`}>
      <div><span>{label}</span><span>{value}/100</span></div>
      <i><b style={{ width: `${value}%` }} /></i>
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
          <span>SETTLEMENT CHECK</span>
          <strong>{preview?.result_label || "结算校准"}</strong>
        </div>
        <b>{preview?.rating_label || rating || "-"}</b>
      </div>
      <div className="wenyou-settlement-meter" aria-label={`评级分 ${score}`}>
        <span style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
      <div className="wenyou-settlement-meta">
        <span>评级分 {score}</span>
        <span>线索 {preview?.clue_count ?? 0}</span>
        <span>回合 {preview?.history_rounds ?? 0}</span>
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
        <button onClick={onConfirm} disabled={loading}>{loading ? "结算中..." : "确认进入结算"}</button>
      </div>
    </div>
  );
}

function SettlementGranted({ settlement }: { settlement: Record<string, unknown> }) {
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

function PanelModal({
  view,
  session,
  acting,
  onClose,
  onUseItem,
}: {
  view: "任务" | "背包" | "状态" | "线索";
  session: WenyouSessionPanel | null;
  acting: boolean;
  onClose: () => void;
  onUseItem: (item: string) => void;
}) {
  const stats = session?.stats || {};
  const inventory = session?.inventory || stats.inventory || [];
  const clues = session?.clues || [];
  const task = session?.task || {};
  return (
    <div className="wenyou-modal">
      <button className="wenyou-modal-backdrop" onClick={onClose} aria-label="关闭面板" />
      <div className="wenyou-random-panel wenyou-panel-modal">
        <span className="wenyou-random-line" />
        <div className="wenyou-panel-title">
          <h2>{view}</h2>
          <button onClick={onClose}>关闭</button>
        </div>

        {!session ? <div className="wenyou-empty">当前没有进行中的副本。</div> : null}

        {session && view === "任务" ? (
          <div className="wenyou-panel-body">
            <PanelRow label="当前阶段" value={task.phase || "副本"} />
            <PanelRow label="主神任务" value={task.current || "暂无任务同步"} />
            <PanelRow label="失败倾向" value={task.failure_hint || "未知"} />
            <PanelRow label="通关回报" value={task.reward_hint || "未知"} />
          </div>
        ) : null}

        {session && view === "背包" ? (
          <div className="wenyou-panel-body">
            {inventory.length ? inventory.map((item) => (
              <div className="wenyou-inventory-row" key={item}>
                <span>{item}</span>
                <button onClick={() => onUseItem(item)} disabled={acting}>{acting ? "演算中" : "填入"}</button>
              </div>
            )) : <div className="wenyou-empty">背包为空。</div>}
          </div>
        ) : null}

        {session && view === "状态" ? (
          <div className="wenyou-panel-body">
            <PanelRow label="主神积分" value={String(stats.points ?? 0)} />
            <PlayerStatCard title="玩家一" player={stats.player1} />
            <PlayerStatCard title="玩家二 · 渡" player={stats.player2} />
          </div>
        ) : null}

        {session && view === "线索" ? (
          <div className="wenyou-panel-body">
            {clues.length ? clues.map((item, index) => (
              <div className="wenyou-clue-row" key={`${item}-${index}`}>{item}</div>
            )) : <div className="wenyou-empty">暂无线索备忘。</div>}
          </div>
        ) : null}
      </div>
    </div>
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

function PlayerStatCard({ title, player }: { title: string; player?: WenyouPlayerStats }) {
  const p = player || {};
  const abilities = p.abilities || [];
  return (
    <div className="wenyou-stat-card">
      <h3>{title}</h3>
      <div className="wenyou-stat-grid">
        <span>HP {p.hp ?? 0}/{p.hp_max ?? 0}</span>
        <span>SAN {p.san ?? 0}/{p.san_max ?? 0}</span>
        <span>Lv{p.level ?? 1} · {p.rank || "D"}阶 · EXP {p.exp ?? 0}</span>
        <span>体 {p.vit ?? 0} / 智 {p.wis ?? 0}</span>
      </div>
      <p>血统：{p.bloodline || "凡人"}</p>
      <p>能力：{abilities.length ? abilities.map((it) => it.name).filter(Boolean).join("、") : "无"}</p>
      <p>状态：{p.conditions?.length ? p.conditions.join("、") : "无"}</p>
    </div>
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
