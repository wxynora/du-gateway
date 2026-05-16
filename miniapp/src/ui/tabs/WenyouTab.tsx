import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type WenyouView = "home" | "selection" | "game" | "archive";
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
    instance_code?: string;
    instance_name?: string;
    instance_genre?: string;
    difficulty?: string;
  } | null;
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
  vit?: number;
  wis?: number;
  bloodline?: string;
  abilities?: Array<{ name?: string; desc?: string }>;
};

type WenyouSessionPanel = {
  gameId?: string;
  phase?: string;
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
  inventory?: string[];
  clues?: string[];
  history?: Array<{ role?: string; content?: string; timestamp?: string }>;
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
  if (name === "archive") {
    return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M6 7v13h12V7M9 11h6M7 3h10l2 4H5l2-4Z" /></svg>;
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
  const [statusLoading, setStatusLoading] = useState(false);
  const [status, setStatus] = useState<WenyouStatus>({ active: false, session: null });
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesRefreshing, setCandidatesRefreshing] = useState(false);
  const [candidates, setCandidates] = useState<InstanceCandidate[]>([]);
  const [candidateGeneratedAt, setCandidateGeneratedAt] = useState("");
  const [starting, setStarting] = useState(false);
  const [acting, setActing] = useState(false);
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
      if (j.session) setSessionPanel(j.session);
      await loadStatus();
    } catch (e: any) {
      toast(`行动失败：${e?.message || e}`);
    } finally {
      setActing(false);
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
            <button className="wenyou-icon-btn" onClick={() => setView("archive")} aria-label="历史归档">
              <Icon name="archive" />
            </button>
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
                <div><i /> <strong>当前阶段</strong><span>{status.active ? "进行中副本" : "等待接入"}</span></div>
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
              <p><span />阶段: {status.active ? "进行中" : "模拟预览"}</p>
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
        <span>Lv{p.level ?? 1} · {p.rank || "D"}阶</span>
        <span>体 {p.vit ?? 0} / 智 {p.wis ?? 0}</span>
      </div>
      <p>血统：{p.bloodline || "凡人"}</p>
      <p>能力：{abilities.length ? abilities.map((it) => it.name).filter(Boolean).join("、") : "无"}</p>
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
