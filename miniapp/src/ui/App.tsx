import React, { Suspense, lazy, useEffect, useState } from "react";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { ToastProvider, useToast } from "./toast";
import { apiFetch, apiJson, buildApiAssetUrl, getOrCreatePanelDeviceId, getPanelDeviceLabel, getPanelToken, setPanelToken } from "./api";
import { Btn, Modal } from "./components";

const LogsTab = lazy(() => import("./tabs/LogsTab").then((m) => ({ default: m.LogsTab })));
const SettingsUpstream = lazy(() => import("./tabs/SettingsUpstream").then((m) => ({ default: m.SettingsUpstream })));
const ReasoningTab = lazy(() => import("./tabs/ReasoningTab").then((m) => ({ default: m.ReasoningTab })));
const ScheduleTab = lazy(() => import("./tabs/ScheduleTab").then((m) => ({ default: m.ScheduleTab })));
const AlarmTab = lazy(() => import("./tabs/AlarmTab").then((m) => ({ default: m.AlarmTab })));
const MemoryDebugTab = lazy(() => import("./tabs/MemoryDebugTab").then((m) => ({ default: m.MemoryDebugTab })));
const DuDayTab = lazy(() => import("./tabs/DuDayTab").then((m) => ({ default: m.DuDayTab })));
const DuNotebookTab = lazy(() => import("./tabs/DuNotebookTab").then((m) => ({ default: m.DuNotebookTab })));
const WenyouTab = lazy(() => import("./tabs/WenyouTab").then((m) => ({ default: m.WenyouTab })));
const StickersTab = lazy(() => import("./tabs/StickersTab").then((m) => ({ default: m.StickersTab })));

type PanelId = "logs" | "reasoning" | "memory-debug" | "du-notebook" | "wenyou" | "stickers" | null;
type BgPreset = "cream" | "grid" | "soft";
type BgConfig = { preset: BgPreset; useImage: boolean; imageVersion: number; dim: number; imageStamp: number };
type CyberTreeData = {
  ok: boolean;
  startDate: string;
  today: string;
  daysTogether: number;
  totalRounds: number;
  growth: number;
  stage: "seedling" | "young" | "big" | "lush";
  season: "spring" | "summer" | "autumn" | "winter";
  weatherFx?: "rainy" | "sunny" | "snowy";
  milestones: { reachedDays: number[]; reachedRounds: number[] };
  mood?: {
    date?: string;
    score?: number;
  };
};
type DailyReport = {
  report_date?: string;
  rounds?: number;
  keywords?: string[];
  done_count?: number;
  summary_text?: string;
  generated_at?: string;
};
type DeviceItem = {
  id?: string;
  note?: string;
  added_at?: string;
  last_seen?: string;
  revoked?: boolean;
  current?: boolean;
};
const BG_STORAGE_KEY = "miniapp.bg.config.v1";

function Shell() {
  const toast = useToast();
  const [panel, setPanel] = useState<PanelId>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showCorePrompt, setShowCorePrompt] = useState(false);
  const [showBgEditor, setShowBgEditor] = useState(false);
  const [showHomeMenu, setShowHomeMenu] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showAlarm, setShowAlarm] = useState(false);
  const [showDuDay, setShowDuDay] = useState(false);
  const [showTree, setShowTree] = useState(false);
  const [dailyWhisper, setDailyWhisper] = useState("");
  const [dailyReport, setDailyReport] = useState<DailyReport | null>(null);
  const [dailyRefreshing, setDailyRefreshing] = useState(false);
  const [tree, setTree] = useState<CyberTreeData | null>(null);
  const [deferHomeExtras, setDeferHomeExtras] = useState(false);
  const loadTree = () =>
    apiJson<CyberTreeData>("/miniapp-api/cyber-tree")
      .then((j) => {
        if (j?.ok) setTree(j);
      })
      .catch(() => {});
  const loadDailyReport = () =>
    apiJson<{ ok?: boolean; report?: DailyReport }>("/miniapp-api/daily-report")
      .then((j) => {
        if (j?.ok && j?.report) setDailyReport(j.report);
      })
      .catch(() => {});
  const version = new URLSearchParams(window.location.search).get("v") || "";
  const [bg, setBg] = useState<BgConfig>({
    preset: "cream",
    useImage: false,
    imageVersion: 0,
    dim: 20,
    imageStamp: 0,
  });

  useEffect(() => {
    // 不强制全屏，保持 Telegram 默认的半屏/弹层体验。
    tgReady(false);
    applyTelegramThemeToHtmlClass();
    const timer = window.setTimeout(() => {
      setDeferHomeExtras(true);
    }, 320);
    try {
      const raw = localStorage.getItem(BG_STORAGE_KEY);
      if (raw) {
        const j = JSON.parse(raw);
        setBg({
          preset: (j?.preset || "cream") as BgPreset,
          useImage: !!j?.useImage,
          imageVersion: Number(j?.imageVersion || 0),
          dim: Number.isFinite(Number(j?.dim)) ? Math.max(0, Math.min(70, Number(j?.dim))) : 20,
          imageStamp: 0,
        });
      }
    } catch {}
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!deferHomeExtras) return;
    apiJson<{ ok?: boolean; config?: Partial<BgConfig> }>("/miniapp-api/background-config")
      .then((j) => {
        if (!j?.ok || !j?.config) return;
        setBg((prev: BgConfig) => ({
          preset: (j.config?.preset as BgPreset) || prev.preset,
          useImage: !!j.config?.useImage,
          imageVersion: Math.max(Number(prev.imageVersion || 0), Number(j.config?.imageVersion || 0)),
          dim: Number.isFinite(Number(j.config?.dim)) ? Math.max(0, Math.min(70, Number(j.config?.dim))) : prev.dim,
          imageStamp: prev.imageStamp || 0,
        }));
      })
      .catch(() => {});
    apiJson<{ ok?: boolean; text?: string }>("/miniapp-api/daily-whisper")
      .then((j) => {
        const text = (j?.text || "").toString().trim();
        if (text) setDailyWhisper(text);
      })
      .catch(() => {});
    loadDailyReport();
    loadTree();
  }, [deferHomeExtras]);

  async function refreshDailyReport() {
    setDailyRefreshing(true);
    try {
      const j = await apiJson<{ ok?: boolean; report?: DailyReport; error?: string }>("/miniapp-api/daily-report/refresh", { method: "POST" });
      if (!j?.ok) throw new Error(j?.error || "刷新失败");
      if (j.report) setDailyReport(j.report);
      toast("日报已刷新");
    } catch (e: any) {
      toast(`日报刷新失败：${e?.message || e}`);
    } finally {
      setDailyRefreshing(false);
    }
  }


  useEffect(() => {
    if (!showTree) return;
    loadTree();
    const timer = setInterval(() => loadTree(), 30000);
    return () => clearInterval(timer);
  }, [showTree]);

  useEffect(() => {
    try {
      localStorage.setItem(BG_STORAGE_KEY, JSON.stringify(bg));
    } catch {}
  }, [bg]);

  useEffect(() => {
    if (!tree) return;
    const dayMarks = tree.milestones?.reachedDays || [];
    const roundMarks = tree.milestones?.reachedRounds || [];
    for (const d of dayMarks) {
      const key = `tree.milestone.day.${d}`;
      if (!localStorage.getItem(key)) {
        localStorage.setItem(key, "1");
        toast(`🎉 在一起第 ${d} 天，种树里程碑达成！`);
      }
    }
    for (const r of roundMarks) {
      const key = `tree.milestone.round.${r}`;
      if (!localStorage.getItem(key)) {
        localStorage.setItem(key, "1");
        toast(`🎉 聊到第 ${r} 轮，种树里程碑达成！`);
      }
    }
  }, [tree, toast]);

  const rootStyle = buildBackgroundStyle(bg);
  const featureTiles = [
    { title: "日志", desc: "查看/过滤/复制", icon: <LineIcon name="logs" />, tone: "blue" as const, onClick: () => setPanel("logs") },
    { title: "思维链", desc: "最近10条（降序）", icon: <LineIcon name="reasoning" />, tone: "pink" as const, onClick: () => setPanel("reasoning") },
    { title: "记忆调试", desc: "窗口总结 + 动态召回", icon: <LineIcon name="memory" />, tone: "yellow" as const, onClick: () => setPanel("memory-debug") },
    { title: "渡的记事本", desc: "固定注入 · 条目管理", icon: <LineIcon name="notebook" />, tone: "blue" as const, onClick: () => setPanel("du-notebook") },
    { title: "文游模块", desc: "系统空间 + 已完成副本", icon: <LineIcon name="wenyou-hub" />, tone: "pink" as const, onClick: () => setPanel("wenyou") },
    { title: "表情包", desc: "情绪分类 · 上传管理", icon: <LineIcon name="stickers" />, tone: "yellow" as const, onClick: () => setPanel("stickers") },
    { title: "核心Prompt", desc: "固定注入，可随时更新", icon: <LineIcon name="prompt" />, tone: "blue" as const, onClick: () => setShowCorePrompt(true) },
  ];

  return (
    <div className="relative min-h-dvh safe-bottom overflow-hidden text-cream-text" style={rootStyle}>
      <div
        className="px-4"
        style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 10px)" }}
      >
        <div className="flex items-center justify-between">
          <div className="inline-flex items-center gap-2 rounded-full bg-[rgba(244,247,251,0.78)] px-3 py-2 shadow-[0_4px_10px_rgba(154,168,186,0.1)] backdrop-blur-xl">
            <span className="text-sm">🏠</span>
            <span className="text-[17px] font-semibold tracking-tight">d&x home</span>
          </div>
          {version ? <div className="text-[11px] text-cream-muted">{`v${version}`}</div> : <div />}
        </div>
      </div>

      {deferHomeExtras && dailyWhisper ? (
        <div className="px-4 pt-3">
          <details className="neo-panel px-4 py-3 text-[12px] leading-relaxed text-cream-text" open>
            <summary className="cursor-pointer select-none text-cream-text">
              <span className="mr-2 rounded-full bg-[#EFD5E1] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-cream-text">Today note</span>
              渡今天想说
            </summary>
            <div className="mt-3 text-[13px] leading-6 text-cream-text">{dailyWhisper}</div>
          </details>
        </div>
      ) : null}
      {deferHomeExtras && dailyReport ? (
        <div className="px-4 pt-2">
          <details className="neo-panel-soft px-4 py-2.5 text-[12px] leading-relaxed text-cream-text">
            <summary className="cursor-pointer select-none text-cream-text">
              <span className="mr-2 rounded-full bg-[#F2E7BF] px-2 py-0.5 text-[10px] font-semibold tracking-[0.16em] text-cream-text">REPORT</span>
              聊了 {String(dailyReport.rounds || 0)} 轮 · {Array.isArray(dailyReport.keywords) ? dailyReport.keywords.join(" / ") : "暂无关键词"}
            </summary>
            <div className="mt-3 space-y-1 text-xs">
              <div>日期：{dailyReport.report_date || "-"}</div>
              <div>关键词：{Array.isArray(dailyReport.keywords) ? dailyReport.keywords.join(" / ") : "-"}</div>
              <div className="whitespace-pre-wrap rounded-[22px] bg-[rgba(255,255,255,0.36)] px-3 py-2 text-cream-muted">{dailyReport.summary_text || "（暂无）"}</div>
              <div className="text-cream-muted">更新时间：{dailyReport.generated_at || "-"}</div>
              <div className="pt-1">
                <Btn kind="blue" onClick={refreshDailyReport} disabled={dailyRefreshing}>
                  {dailyRefreshing ? "刷新中..." : "刷新日报"}
                </Btn>
              </div>
            </div>
          </details>
        </div>
      ) : null}

      <div className="px-4 pt-4 pb-28">
        <div className="grid grid-cols-2 gap-x-3 gap-y-3">
          {featureTiles.map((item) => (
            <FeatureTile key={item.title} title={item.title} desc={item.desc} tone={item.tone} icon={item.icon} onClick={item.onClick} />
          ))}
        </div>
      </div>

      {panel === "logs" ? (
        <Modal title="日志" onClose={() => setPanel(null)}>
          <LazyPane><LogsTab /></LazyPane>
        </Modal>
      ) : null}
      {panel === "reasoning" ? (
        <Modal title="思维链" onClose={() => setPanel(null)}>
          <LazyPane><ReasoningTab /></LazyPane>
        </Modal>
      ) : null}
      {panel === "memory-debug" ? (
        <Modal title="记忆调试" onClose={() => setPanel(null)}>
          <LazyPane><MemoryDebugTab /></LazyPane>
        </Modal>
      ) : null}
      {panel === "du-notebook" ? (
        <Modal title="渡的记事本" onClose={() => setPanel(null)}>
          <LazyPane><DuNotebookTab /></LazyPane>
        </Modal>
      ) : null}
      {panel === "wenyou" ? (
        <Modal title="文游模块" onClose={() => setPanel(null)}>
          <LazyPane><WenyouTab initialView="hub" /></LazyPane>
        </Modal>
      ) : null}
      {panel === "stickers" ? (
        <Modal title="表情包" onClose={() => setPanel(null)}>
          <LazyPane><StickersTab /></LazyPane>
        </Modal>
      ) : null}

      {showSettings ? <LazyPane><SettingsUpstream onClose={() => setShowSettings(false)} /></LazyPane> : null}
      {showCorePrompt ? <CorePromptEditor onClose={() => setShowCorePrompt(false)} /> : null}
      {showBgEditor ? <BackgroundEditor bg={bg} onChange={setBg} onClose={() => setShowBgEditor(false)} /> : null}
      {showSchedule ? (
        <Modal title="日历与提醒" onClose={() => setShowSchedule(false)}>
          <LazyPane><ScheduleTab /></LazyPane>
        </Modal>
      ) : null}
      {showAlarm ? (
        <Modal title="闹钟" onClose={() => setShowAlarm(false)}>
          <LazyPane><AlarmTab /></LazyPane>
        </Modal>
      ) : null}
      {showDuDay ? (
        <Modal title="渡的一天" onClose={() => setShowDuDay(false)}>
          <LazyPane><DuDayTab /></LazyPane>
        </Modal>
      ) : null}
      {showTree ? <CyberTreeModal data={tree} onClose={() => setShowTree(false)} onRefresh={loadTree} /> : null}
      <HomeOrbMenu
        open={showHomeMenu}
        onToggle={() => setShowHomeMenu((v: boolean) => !v)}
        onOpenSchedule={() => {
          setShowHomeMenu(false);
          setShowSchedule(true);
        }}
        onOpenBackground={() => {
          setShowHomeMenu(false);
          setShowBgEditor(true);
        }}
        onOpenAlarm={() => {
          setShowHomeMenu(false);
          setShowAlarm(true);
        }}
        onOpenUpstream={() => {
          setShowHomeMenu(false);
          setShowSettings(true);
        }}
        onOpenDuDay={() => {
          setShowHomeMenu(false);
          setShowDuDay(true);
        }}
        onOpenTree={() => {
          setShowHomeMenu(false);
          setShowTree(true);
        }}
      />
    </div>
  );
}

function FeatureTile({
  title,
  desc,
  tone,
  icon,
  onClick,
  disabled,
}: {
  title: string;
  desc: string;
  tone: "blue" | "pink" | "yellow";
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  const toneMap = {
    blue: {
      shell: "bg-[rgba(240,246,251,0.54)]",
      badge: "bg-[#D6E4F2]",
    },
    pink: {
      shell: "bg-[rgba(240,246,251,0.54)]",
      badge: "bg-[#EFD5E1]",
    },
    yellow: {
      shell: "bg-[rgba(240,246,251,0.54)]",
      badge: "bg-[#F2E7BF]",
    },
  }[tone];
  return (
    <button
      className={
        "group relative min-h-[116px] overflow-hidden rounded-[24px] p-4 text-left shadow-[7px_7px_16px_rgba(178,186,198,0.26),-4px_-4px_10px_rgba(255,255,255,0.34),inset_1px_1px_0_rgba(255,255,255,0.2)] backdrop-blur-xl transition active:scale-[0.99] " +
        toneMap.shell +
        (disabled ? " opacity-60 cursor-not-allowed" : "")
      }
      onClick={() => {
        if (disabled) return;
        onClick();
      }}
      disabled={disabled}
    >
      <div className="relative flex items-center gap-3">
        <span className={"inline-flex h-10 w-10 items-center justify-center rounded-[16px] shadow-[3px_3px_8px_rgba(201,206,214,0.14),-1px_-1px_4px_rgba(255,255,255,0.24)] " + toneMap.badge}>
          {icon}
        </span>
        <div className="min-w-0">
          <div className="text-[16px] font-semibold tracking-tight">{title}</div>
          <div className="mt-1 text-[11px] leading-[1.45] text-cream-muted">{desc}</div>
        </div>
      </div>
    </button>
  );
}

function LineIcon({ name }: { name: "logs" | "reasoning" | "upstream" | "prompt" | "background" | "tree" | "memory" | "notebook" | "wenyou-archives" | "wenyou-hub" | "stickers" }) {
  const cls = "h-4 w-4 text-cream-text";
  if (name === "logs") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 6h16M4 12h16M4 18h10" /></svg>;
  if (name === "reasoning") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 12h4l2-4 4 8 2-4h4" /></svg>;
  if (name === "memory") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 5h14v14H5zM8 9h8M8 13h8M8 17h5" /></svg>;
  if (name === "notebook") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 4h12v16H6zM9 8h6M9 12h6M9 16h4" /></svg>;
  if (name === "wenyou-archives") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 5h14v14H5zM8 8h8M8 12h8M8 16h6" /></svg>;
  if (name === "wenyou-hub") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3 4 7v5c0 5 3.4 8.7 8 9 4.6-.3 8-4 8-9V7l-8-4zM9 12h6M12 9v6" /></svg>;
  if (name === "stickers") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="9" cy="10" r="1.2" fill="currentColor" /><circle cx="15" cy="10" r="1.2" fill="currentColor" /><path d="M8 14c1.6 2 6.4 2 8 0" /></svg>;
  if (name === "upstream") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h10M14 7l3-3m-3 3 3 3M20 17H10m0 0-3-3m3 3-3 3" /></svg>;
  if (name === "prompt") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 5h14v14H5zM8 9h8M8 13h8M8 17h5" /></svg>;
  if (name === "tree") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 21v-5M12 16c-3.8 0-6-2.2-6-5 0-2.2 1.4-4 3.4-4.7A4.8 4.8 0 0 1 19 8c1.8.8 3 2.5 3 4.5 0 3-2.4 3.5-5 3.5h-5z" /></svg>;
  return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 20h16M4 8l4 4 4-6 4 5 4-3v12H4z" /></svg>;
}

function HomeOrbMenu({
  open,
  onToggle,
  onOpenSchedule,
  onOpenBackground,
  onOpenAlarm,
  onOpenUpstream,
  onOpenDuDay,
  onOpenTree,
}: {
  open: boolean;
  onToggle: () => void;
  onOpenSchedule: () => void;
  onOpenBackground: () => void;
  onOpenAlarm: () => void;
  onOpenUpstream: () => void;
  onOpenDuDay: () => void;
  onOpenTree: () => void;
}) {
  return (
    <div className="fixed inset-x-0 bottom-14 z-30 flex justify-center pointer-events-none">
      <div className="relative pointer-events-auto">
        {open ? (
          <div className="absolute left-1/2 top-1/2 w-[272px] -translate-x-1/2 -translate-y-[122%] rounded-[32px] bg-[rgba(244,247,251,0.84)] p-4 shadow-[0_10px_22px_rgba(154,168,186,0.14)] backdrop-blur-2xl">
            <div className="grid grid-cols-3 gap-3">
              <button
                className="h-14 rounded-[20px] bg-[#D6E4F2] flex items-center justify-center text-cream-text shadow-[0_6px_14px_rgba(154,168,186,0.12)] active:scale-[0.99] transition"
                onClick={onOpenBackground}
                title="背景设置"
              >
                <LineIcon name="background" />
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#F2E7BF] flex items-center justify-center text-cream-text shadow-[0_6px_14px_rgba(154,168,186,0.12)] active:scale-[0.99] transition"
                onClick={onOpenSchedule}
                title="日历与提醒"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M7 3v3M17 3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a1 1 0 0 1 1-1z" />
                </svg>
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#EFD5E1] flex items-center justify-center text-cream-text shadow-[0_6px_14px_rgba(154,168,186,0.12)] active:scale-[0.99] transition"
                onClick={onOpenAlarm}
                title="闹钟"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <circle cx="12" cy="13" r="7" />
                  <path d="M12 13V9m0 4 3 2M7 4 4 7m13-3 3 3" />
                </svg>
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#D6E4F2] flex items-center justify-center text-cream-text shadow-[0_6px_14px_rgba(154,168,186,0.12)] active:scale-[0.99] transition"
                onClick={onOpenDuDay}
                title="渡的一天"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M6 5h12M6 12h12M6 19h8" />
                </svg>
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#F2E7BF] flex items-center justify-center text-cream-text shadow-[0_6px_14px_rgba(154,168,186,0.12)] active:scale-[0.99] transition"
                onClick={onOpenTree}
                title="小渡&小玥の树"
              >
                <LineIcon name="tree" />
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#EFD5E1] flex items-center justify-center text-cream-text shadow-[0_6px_14px_rgba(154,168,186,0.12)] active:scale-[0.99] transition"
                onClick={onOpenUpstream}
                title="上游切换"
              >
                <LineIcon name="upstream" />
              </button>
              <button
                className="h-14 rounded-[20px] bg-[rgba(244,247,251,0.92)] flex items-center justify-center text-cream-muted shadow-[0_6px_14px_rgba(154,168,186,0.12)] active:scale-[0.99] transition"
                onClick={onToggle}
                title="收起"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M6 14l6-6 6 6" />
                </svg>
              </button>
            </div>
          </div>
        ) : null}
        <button
          className="h-[74px] w-[74px] rounded-full bg-[rgba(244,247,251,0.84)] shadow-[0_10px_22px_rgba(154,168,186,0.14)] backdrop-blur-2xl flex items-center justify-center text-cream-text"
          onClick={onToggle}
          title="Home"
        >
          <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
            <path d="M3 10.5 12 3l9 7.5V21h-6v-6h-6v6H3z" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export function App() {
  return (
    <ToastProvider>
      <AppWithAuth />
    </ToastProvider>
  );
}

function AppWithAuth() {
  const toast = useToast();
  const [metaLoading, setMetaLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [secondAnswer, setSecondAnswer] = useState("");
  const [loginStep, setLoginStep] = useState<"password" | "question">("password");
  const [submitting, setSubmitting] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [secondPrompt, setSecondPrompt] = useState("");
  const [showDeviceManager, setShowDeviceManager] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const j = await fetch("/miniapp-api/panel-auth/meta").then((r) => r.json());
        if (cancelled) return;
        const enabled = !!j?.enabled;
        setAuthEnabled(enabled);
        setSecondPrompt(String(j?.second_prompt || ""));
        if (!enabled) {
          setReady(true);
          return;
        }
        const token = getPanelToken();
        if (!token) {
          setReady(false);
          return;
        }
        const s = await apiJson<{ ok?: boolean; authenticated?: boolean }>("/miniapp-api/panel-auth/session");
        if (cancelled) return;
        if (s?.ok && s?.authenticated) {
          setReady(true);
          return;
        }
        setPanelToken("");
        setReady(false);
      } catch {
        if (cancelled) return;
        setReady(false);
      } finally {
        if (!cancelled) setMetaLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function onExpired(ev: Event) {
      const detail = (ev as CustomEvent<{ code?: string; message?: string }>).detail || {};
      setReady(false);
      setPassword("");
      setSecondAnswer("");
      setLoginStep("password");
      setErrorText(String(detail.message || "登录已失效，请重新验证"));
      toast(String(detail.message || "当前浏览器访问已失效"));
    }
    window.addEventListener("miniapp-auth-expired", onExpired as EventListener);
    return () => {
      window.removeEventListener("miniapp-auth-expired", onExpired as EventListener);
    };
  }, [toast]);

  async function login() {
    if (!password.trim()) {
      setErrorText("Please enter your password.");
      return;
    }
    if (secondPrompt && loginStep === "question" && !secondAnswer.trim()) {
      setErrorText("Please answer the security question.");
      return;
    }
    setSubmitting(true);
    setErrorText("");
    try {
      if (secondPrompt && loginStep === "password") {
        const first = await fetch("/miniapp-api/panel-auth/check-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: password.trim() }),
        }).then(async (r) => ({ ok: r.ok, body: await r.json().catch(() => ({})) }));
        if (!first.ok || !first.body?.ok) {
          throw new Error(first.body?.error || "Password verification failed");
        }
        setLoginStep("question");
        setErrorText("");
        return;
      }
      const deviceId = getOrCreatePanelDeviceId();
      const j = await fetch("/miniapp-api/panel-auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          password: password.trim(),
          second_answer: secondAnswer.trim(),
          device_id: deviceId,
          device_name: getPanelDeviceLabel(),
        }),
      }).then(async (r) => ({ ok: r.ok, body: await r.json().catch(() => ({})) }));
      if (!j.ok || !j.body?.ok || !j.body?.panel_token) {
        throw new Error(j.body?.error || "密码校验失败");
      }
      setPanelToken(String(j.body.panel_token));
      setPassword("");
      setSecondAnswer("");
      setLoginStep("password");
      setReady(true);
      toast("已进入 mini app");
    } catch (e: any) {
      setErrorText(e?.message || "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  function logout() {
    setPanelToken("");
    setReady(false);
    setPassword("");
    setSecondAnswer("");
    setLoginStep("password");
    setErrorText("");
    setShowDeviceManager(false);
    toast("已退出登录");
  }

  if (metaLoading) {
    return <LoadingScreen text="正在检查面板登录状态..." />;
  }
  if (!authEnabled || ready) {
    return (
      <ShellWithLogout
        onLogout={authEnabled ? logout : undefined}
        onOpenDevices={authEnabled ? () => setShowDeviceManager(true) : undefined}
        deviceManagerOpen={showDeviceManager}
        onCloseDevices={() => setShowDeviceManager(false)}
      />
    );
  }
  return (
    <div className="min-h-dvh bg-[#EEF0F3] px-5 py-6 text-cream-text">
      <div className="mx-auto flex min-h-[calc(100dvh-3rem)] max-w-md items-center">
        <div className="neo-panel w-full p-5" style={{ fontFamily: '"Cormorant Garamond", "Times New Roman", serif' }}>
          <div className="flex items-center justify-between gap-3">
            <div className="neo-chip">Private Access</div>
            <div className="flex h-14 w-14 items-center justify-center rounded-[16px] bg-[rgba(244,247,251,0.82)] shadow-[0_6px_14px_rgba(154,168,186,0.12)]">
              <ClaudePixelCrabIcon />
            </div>
          </div>
          <div className="mt-4 text-center text-[31px] font-semibold tracking-[0.01em]">
            {secondPrompt && loginStep === "question" ? "Security Check" : "Sign In"}
          </div>
          <div className="mt-2 text-center text-[17px] leading-6 text-cream-muted">
            {secondPrompt && loginStep === "question" ? "Answer the question to continue." : "Continue to the mini app panel."}
          </div>

          <div className="mt-5 space-y-3">
            {loginStep === "password" || !secondPrompt ? (
              <label className="block">
                <div className="mb-2 text-center text-[13px] font-semibold uppercase tracking-[0.14em] text-cream-muted">Password</div>
                <input
                  className="h-12 w-full rounded-[999px] border border-[rgba(255,255,255,0.96)] bg-[#eef0f3] px-5 text-center text-[18px] text-cream-text outline-none shadow-[inset_4px_4px_8px_rgba(188,197,209,0.42),inset_-4px_-4px_8px_rgba(255,255,255,0.92)] placeholder:text-center placeholder:text-cream-muted"
                  type="password"
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !submitting) void login();
                  }}
                />
              </label>
            ) : null}

            {secondPrompt && loginStep === "question" ? (
              <label className="block">
                <div className="mb-2 text-center text-[13px] font-semibold uppercase tracking-[0.14em] text-cream-muted">{secondPrompt}</div>
                <input
                  className="h-12 w-full rounded-[999px] border border-[rgba(255,255,255,0.96)] bg-[#eef0f3] px-5 text-center text-[18px] text-cream-text outline-none shadow-[inset_4px_4px_8px_rgba(188,197,209,0.42),inset_-4px_-4px_8px_rgba(255,255,255,0.92)] placeholder:text-center placeholder:text-cream-muted"
                  type="text"
                  placeholder="Enter answer"
                  value={secondAnswer}
                  onChange={(e) => setSecondAnswer(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !submitting) void login();
                  }}
                />
              </label>
            ) : null}

            {errorText ? (
              <div className="neo-muted-box bg-[linear-gradient(145deg,rgba(251,230,236,0.95),rgba(236,206,221,0.82))]">
                {errorText}
              </div>
            ) : null}

            <div className="flex items-center justify-center gap-3">
              {secondPrompt && loginStep === "question" ? (
                <button
                  type="button"
                  className="min-w-[108px] rounded-[999px] bg-[#eef0f3] px-5 py-3 text-center text-[17px] font-semibold text-cream-text shadow-[-4px_-4px_10px_rgba(255,255,255,0.94),4px_4px_10px_rgba(188,197,209,0.46)] transition active:translate-y-[1px] active:shadow-[-2px_-2px_6px_rgba(255,255,255,0.9),2px_2px_6px_rgba(188,197,209,0.4)] disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => {
                    setLoginStep("password");
                    setSecondAnswer("");
                    setErrorText("");
                  }}
                  disabled={submitting}
                >
                  Back
                </button>
              ) : null}
              <button
                type="button"
                className="min-w-[148px] rounded-[999px] bg-[linear-gradient(145deg,rgba(244,247,251,0.96),rgba(213,228,246,0.78))] px-7 py-3 text-center text-[17px] font-semibold text-cream-text shadow-[-5px_-5px_12px_rgba(255,255,255,0.96),5px_5px_12px_rgba(186,197,212,0.5)] transition active:translate-y-[1px] active:shadow-[-2px_-2px_7px_rgba(255,255,255,0.92),2px_2px_7px_rgba(186,197,212,0.42)] disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void login()}
                disabled={submitting}
              >
                {submitting ? "Verifying..." : secondPrompt && loginStep === "password" ? "Continue" : "Sign In"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ClaudePixelCrabIcon() {
  return (
    <svg className="h-10 w-10" viewBox="0 0 88 88" aria-hidden>
      <rect x="20" y="18" width="48" height="36" fill="#DD8A6B" />
      <rect x="12" y="26" width="8" height="12" fill="#DD8A6B" />
      <rect x="68" y="26" width="8" height="12" fill="#DD8A6B" />
      <rect x="28" y="10" width="32" height="8" fill="#DD8A6B" />
      <rect x="32" y="26" width="6" height="12" fill="#111111" />
      <rect x="50" y="26" width="6" height="12" fill="#111111" />
      <rect x="24" y="54" width="6" height="12" fill="#DD8A6B" />
      <rect x="40" y="54" width="6" height="12" fill="#DD8A6B" />
      <rect x="56" y="54" width="6" height="12" fill="#DD8A6B" />
      <rect x="22" y="66" width="44" height="6" fill="#8A8A8A" />
    </svg>
  );
}

function ShellWithLogout({
  onLogout,
  onOpenDevices,
  deviceManagerOpen,
  onCloseDevices,
}: {
  onLogout?: () => void;
  onOpenDevices?: () => void;
  deviceManagerOpen?: boolean;
  onCloseDevices?: () => void;
}) {
  return (
    <>
      <Shell />
      {onLogout || onOpenDevices ? (
        <div className="fixed right-4 top-4 z-[70] flex items-center gap-2">
          {onOpenDevices ? (
            <button
              type="button"
              className="rounded-full bg-[rgba(244,247,251,0.88)] px-3 py-1.5 text-[11px] text-cream-muted shadow-[0_6px_14px_rgba(154,168,186,0.12)] backdrop-blur-xl"
              onClick={onOpenDevices}
            >
              设备管理
            </button>
          ) : null}
          {onLogout ? (
            <button
              type="button"
              className="rounded-full bg-[rgba(244,247,251,0.88)] px-3 py-1.5 text-[11px] text-cream-muted shadow-[0_6px_14px_rgba(154,168,186,0.12)] backdrop-blur-xl"
              onClick={onLogout}
            >
              退出登录
            </button>
          ) : null}
        </div>
      ) : null}
      {deviceManagerOpen && onCloseDevices ? <DeviceManagerModal onClose={onCloseDevices} onLogout={onLogout} /> : null}
    </>
  );
}

function DeviceManagerModal({ onClose, onLogout }: { onClose: () => void; onLogout?: () => void }) {
  const toast = useToast();
  const [items, setItems] = useState<DeviceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; items?: DeviceItem[] }>("/miniapp-api/panel-auth/list");
      setItems(Array.isArray(j?.items) ? j.items : []);
    } catch (e: any) {
      toast(`加载设备失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function revoke(deviceId: string, current: boolean) {
    if (!deviceId) return;
    const ok = window.confirm(current ? "撤销当前浏览器后会立刻退出，继续吗？" : "确认撤销这个浏览器的访问权限吗？");
    if (!ok) return;
    setBusyId(deviceId);
    try {
      const j = await apiJson<{ ok?: boolean; revoked_current?: boolean }>("/miniapp-api/panel-auth/revoke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: deviceId }),
      });
      if (!j?.ok) throw new Error("撤销失败");
      if (j.revoked_current) {
        toast("当前浏览器已被撤销");
        onClose();
        onLogout?.();
        return;
      }
      toast("设备已撤销");
      await load();
    } catch (e: any) {
      toast(`撤销失败：${e?.message || e}`);
    } finally {
      setBusyId("");
    }
  }

  return (
    <Modal title="设备管理" onClose={onClose}>
      <div className="space-y-3 pb-6">
        <div className="neo-panel-soft p-3 text-xs leading-6 text-cream-muted">
          每个浏览器都会有一个独立设备身份。撤销后，该浏览器下一次请求会立刻失效。
        </div>
        <div className="flex items-center gap-2">
          <Btn kind="blue" onClick={() => void load()} disabled={loading}>
            {loading ? "刷新中..." : "刷新列表"}
          </Btn>
        </div>
        <div className="space-y-2">
          {items.map((item) => {
            const id = String(item.id || "");
            const current = !!item.current;
            const revoked = !!item.revoked;
            return (
              <div key={id} className="neo-panel p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-semibold">{item.note || "Browser"}</span>
                      {current ? <span className="neo-tag-blue px-2.5 py-1 text-[10px]">当前设备</span> : null}
                      {revoked ? <span className="neo-tag-pink px-2.5 py-1 text-[10px]">已撤销</span> : null}
                    </div>
                    <div className="mt-1 break-all text-[11px] leading-5 text-cream-muted">{id}</div>
                    <div className="mt-2 text-[11px] leading-5 text-cream-muted">
                      首次加入：{item.added_at || "-"}
                      <br />
                      最近访问：{item.last_seen || "-"}
                    </div>
                  </div>
                  <Btn kind="danger" onClick={() => void revoke(id, current)} disabled={busyId === id || revoked}>
                    {revoked ? "已撤销" : busyId === id ? "处理中..." : "撤销"}
                  </Btn>
                </div>
              </div>
            );
          })}
          {!items.length && !loading ? <div className="text-xs text-cream-muted">暂无设备记录。</div> : null}
        </div>
      </div>
    </Modal>
  );
}

function LazyPane({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="neo-panel-soft p-4 text-sm text-cream-muted">
          加载中…
        </div>
      }
    >
      {children}
    </Suspense>
  );
}

function LoadingScreen({ text }: { text: string }) {
  return (
    <div className="min-h-dvh bg-[#EEF0F3] px-5 py-6 text-cream-text">
      <div className="mx-auto flex min-h-[calc(100dvh-3rem)] max-w-md items-center">
        <div className="neo-panel-soft w-full p-5 text-sm text-cream-muted">{text}</div>
      </div>
    </div>
  );
}

function buildBackgroundStyle(bg: BgConfig): React.CSSProperties {
  if (bg.useImage && bg.imageVersion > 0) {
    const alpha = Math.max(0, Math.min(70, Number(bg.dim || 0))) / 100;
    return {
      backgroundColor: "#eaedf1",
      backgroundImage: `linear-gradient(rgba(238,240,243,${alpha}), rgba(238,240,243,${alpha})), url("${buildApiAssetUrl(`/miniapp-api/background-image/${bg.imageVersion}?s=${bg.imageStamp || 0}`)}")`,
      backgroundSize: "cover",
      backgroundPosition: "center",
      backgroundRepeat: "no-repeat",
    };
  }
  if (bg.preset === "grid") {
    return {
      backgroundColor: "#e8ebef",
      backgroundImage:
        "linear-gradient(rgba(21,31,43,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(21,31,43,0.06) 1px, transparent 1px), radial-gradient(circle at 50% 40%, rgba(255,255,255,0.8) 0%, rgba(255,255,255,0.45) 45%, rgba(232,235,239,0) 72%)",
      backgroundSize: "30px 30px, 30px 30px, 100% 100%",
    };
  }
  if (bg.preset === "soft") {
    return {
      backgroundColor: "#eef0f3",
      backgroundImage:
        "radial-gradient(circle at 20% 20%, rgba(183,199,223,0.28), transparent 36%), radial-gradient(circle at 80% 18%, rgba(213,193,208,0.30), transparent 34%), radial-gradient(circle at 50% 80%, rgba(191,212,204,0.28), transparent 38%)",
    };
  }
  return { backgroundColor: "#EEF0F3" };
}

function BackgroundEditor({
  bg,
  onChange,
  onClose,
}: {
  bg: BgConfig;
  onChange: (v: BgConfig) => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const [draft, setDraft] = useState<BgConfig>(bg);
  const [origin, setOrigin] = useState<BgConfig>(bg);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    setDraft(bg);
    setOrigin(bg);
  }, [bg]);

  function applyDraft(next: BgConfig) {
    setDraft(next);
    onChange(next);
  }

  async function save() {
    try {
      const j = await apiJson<{ ok?: boolean; config?: Partial<BgConfig> }>("/miniapp-api/background-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const next: BgConfig = {
        preset: ((j?.config?.preset as BgPreset) || draft.preset) as BgPreset,
        useImage: !!(j?.config?.useImage ?? draft.useImage),
        imageVersion: Number(j?.config?.imageVersion ?? draft.imageVersion),
        dim: Number.isFinite(Number(j?.config?.dim)) ? Math.max(0, Math.min(70, Number(j?.config?.dim))) : draft.dim,
        imageStamp: draft.imageStamp || 0,
      };
      onChange(next);
      toast("背景已保存");
      onClose();
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    }
  }

  async function uploadFromAlbum(file: File | null) {
    if (!file) return;
    setUploading(true);
    try {
      const toDataUrl = (blob: Blob) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ""));
          reader.onerror = () => reject(new Error("读取图片失败"));
          reader.readAsDataURL(blob);
        });
      const loadImage = (src: string) =>
        new Promise<HTMLImageElement>((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.onerror = () => reject(new Error("图片解码失败"));
          img.src = src;
        });
      const canvasToBlob = (canvas: HTMLCanvasElement, quality: number) =>
        new Promise<Blob>((resolve, reject) => {
          canvas.toBlob(
            (blob) => {
              if (blob) resolve(blob);
              else reject(new Error("图片编码失败"));
            },
            "image/jpeg",
            quality
          );
        });

      // 上传前压缩：避免运营商/反向代理 413（体积过大）并降低上传失败概率
      const maxUploadBytes = 1500 * 1024; // 约 1.5MB
      const maxSide = 1920;
      let uploadBlob: Blob = file;
      if (file.size > maxUploadBytes || file.type !== "image/jpeg") {
        const src = await toDataUrl(file);
        const img = await loadImage(src);
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("浏览器不支持图片处理");
        ctx.drawImage(img, 0, 0, w, h);
        let q = 0.88;
        let out = await canvasToBlob(canvas, q);
        while (out.size > maxUploadBytes && q > 0.5) {
          q -= 0.08;
          out = await canvasToBlob(canvas, q);
        }
        uploadBlob = out;
      }

      const fd = new FormData();
      fd.append("file", uploadBlob, "miniapp-bg.jpg");
      const r = await apiFetch("/miniapp-api/background-image", {
        method: "POST",
        body: fd,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j?.ok) {
        if (r.status === 413) throw new Error("图片体积仍然过大（413），请换更小图片");
        if (r.status === 403) throw new Error("鉴权失效（403），关闭重进 miniapp 后再试");
        throw new Error(j?.error || `HTTP ${r.status}`);
      }
      const version = Number(j?.imageVersion || Date.now());
      setDraft((v: BgConfig) => {
        const next = { ...v, useImage: true, imageVersion: version, imageStamp: Date.now() };
        onChange(next);
        return next;
      });
      toast("已上传背景图");
    } catch (e: any) {
      toast(`上传失败：${e?.message || e}`);
    } finally {
      setUploading(false);
    }
  }

  return (
    <Modal title="背景设置" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="text-xs text-cream-muted">可选预设风格，或从手机相册上传背景图（跨设备同步）。</div>
        <div className="grid grid-cols-3 gap-2">
          <Btn kind={draft.preset === "cream" ? "green" : "default"} onClick={() => applyDraft({ ...draft, preset: "cream", useImage: false })}>米白</Btn>
          <Btn kind={draft.preset === "grid" ? "green" : "default"} onClick={() => applyDraft({ ...draft, preset: "grid", useImage: false })}>网格灰</Btn>
          <Btn kind={draft.preset === "soft" ? "green" : "default"} onClick={() => applyDraft({ ...draft, preset: "soft", useImage: false })}>柔和彩</Btn>
        </div>
        <div className="rounded-xl2 bg-white/42 backdrop-blur-xl border border-white/50 p-3 shadow-soft2 space-y-2">
          <label className="text-xs text-cream-muted">从相册上传图片（jpg/png/webp/gif，最大 8MB）</label>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="w-full rounded-xl2 bg-white/68 border border-white/50 px-3 py-2 text-sm shadow-soft2"
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => uploadFromAlbum((e.target.files && e.target.files[0]) || null)}
            disabled={uploading}
          />
          <div className="flex items-center gap-2">
            <Btn
              kind={draft.useImage ? "green" : "default"}
              onClick={() =>
                applyDraft({
                  ...draft,
                  useImage: !draft.useImage,
                  imageStamp: !draft.useImage ? Date.now() : draft.imageStamp,
                })
              }
            >
              {draft.useImage ? "已启用图片" : "启用图片"}
            </Btn>
            {uploading ? <span className="text-xs text-cream-muted">上传中...</span> : null}
            <span className="text-xs text-cream-muted">遮罩 {draft.dim}%</span>
          </div>
          <input
            type="range"
            min={0}
            max={70}
            value={draft.dim}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => applyDraft({ ...draft, dim: Number(e.target.value || 20) })}
            className="w-full"
          />
        </div>
        <div className="flex items-center gap-2">
          <Btn
            kind="blue"
            onClick={() => {
              onChange(origin);
              onClose();
            }}
          >
            取消
          </Btn>
          <Btn kind="green" onClick={save} disabled={uploading}>保存</Btn>
        </div>
      </div>
    </Modal>
  );
}

function GrowthTreeSVG({
  growthValue,
  season,
  weatherFx,
}: {
  growthValue: number;
  season: "spring" | "summer" | "autumn" | "winter";
  weatherFx?: "rainy" | "sunny" | "snowy";
}) {
  const g = Number.isFinite(growthValue) ? Math.max(0, growthValue) : 0;
  const stage = g < 10 ? 0 : g < 30 ? 1 : g < 60 ? 2 : g < 100 ? 3 : 4;
  const fullness = Math.min(1, g / 100);
  const trunkW = 3 + stage * 1.4 + fullness * 1.2;
  const trunkH = 12 + stage * 7 + Math.min(10, g * 0.08);
  const trunkY = 86 - trunkH;
  const branchLevel = stage >= 2 ? (stage >= 4 ? 4 : stage === 3 ? 3 : 2) : 0;
  const leafCountBase = [2, 5, 12, 20, 26][stage];
  const leafCount = season === "winter" ? Math.max(0, Math.round(leafCountBase * 0.15)) : leafCountBase;
  const leafPalette =
    season === "spring"
      ? ["#9adf86", "#8cd97f", "#f6b4cb"]
      : season === "summer"
        ? ["#4cb165", "#3f9e56", "#2f8c4a"]
        : season === "autumn"
          ? ["#f2c35f", "#ef9a4b", "#d96a3b"]
          : ["#bfc9d3", "#d7e0e8", "#e8eef3"];
  const branchColor = season === "winter" ? "#6e5945" : "#76573d";
  const trunkColor = season === "winter" ? "#7a6045" : "#835f3f";
  const glow = stage >= 4;

  const leaves = Array.from({ length: leafCount }).map((_, i) => {
    const t = i / Math.max(1, leafCount - 1);
    const angle = -150 + t * 300;
    const radius = 10 + (stage + 1) * 5 + (i % 3) * 2;
    const cx = 50 + Math.cos((angle * Math.PI) / 180) * radius;
    const cy = trunkY - 5 + Math.sin((angle * Math.PI) / 180) * (radius * 0.72) - stage * 1.8;
    const rx = 2.4 + (i % 3) * 0.6 + stage * 0.2;
    const ry = 3.2 + (i % 2) * 0.7 + stage * 0.2;
    const color = leafPalette[i % leafPalette.length];
    return { cx, cy, rx, ry, color, idx: i };
  });

  const fx = weatherFx || (season === "winter" ? "snowy" : season === "summer" ? "sunny" : "rainy");
  const flowers = season === "spring" ? leaves.filter((_, i) => i % 5 === 0).slice(0, 8) : [];
  const snowCaps = fx === "snowy" ? leaves.filter((_, i) => i % 3 === 0).slice(0, 10) : [];
  const petals = season === "spring" && stage >= 2 ? [0, 1, 2].map((i) => ({ i, x: 40 + i * 10 })) : [];
  const rainDrops = fx === "rainy" ? Array.from({ length: 8 }).map((_, i) => ({ i, x: 18 + i * 9, y: 8 + (i % 3) * 4 })) : [];
  const sunGlints = fx === "sunny" ? Array.from({ length: 6 }).map((_, i) => ({ i, x: 18 + i * 11, y: 16 + (i % 2) * 5 })) : [];

  return (
    <svg viewBox="0 0 100 100" className="w-full max-w-[280px] h-auto" aria-label="growth-tree-svg">
      <defs>
        <linearGradient id="soilGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#b7865e" />
          <stop offset="100%" stopColor="#8f5f3c" />
        </linearGradient>
        <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="2.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <style>{`
        .tree-leaf { transform-box: fill-box; transform-origin: center; animation: leaf-sway 3.4s ease-in-out infinite; }
        .tree-leaf:nth-child(2n) { animation-duration: 4.1s; }
        .tree-leaf:nth-child(3n) { animation-duration: 2.9s; }
        .petal-fall { animation: petal-fall 4.8s ease-in infinite; opacity: 0.75; }
        .grow-in { animation: grow-in .7s ease-out; transform-origin: center bottom; }
        @keyframes leaf-sway { 0%,100% { transform: rotate(-2deg) translateY(0px); } 50% { transform: rotate(2deg) translateY(-.4px); } }
        @keyframes petal-fall { 0% { transform: translateY(0px) translateX(0px); opacity: .75; } 100% { transform: translateY(20px) translateX(4px); opacity: 0; } }
        @keyframes rain-fall { 0% { transform: translateY(-2px); opacity: .7; } 100% { transform: translateY(9px); opacity: .2; } }
        @keyframes glint { 0%,100% { opacity: .18; } 50% { opacity: .42; } }
        @keyframes grow-in { from { transform: scale(.82); opacity: .45; } to { transform: scale(1); opacity: 1; } }
      `}</style>

      <ellipse cx="50" cy="90" rx="28" ry="7" fill="url(#soilGrad)" />

      {stage === 0 ? (
        <g className="grow-in">
          <path d="M50 88 C50 84, 50 81, 50 78" stroke={trunkColor} strokeWidth="1.6" fill="none" />
          <ellipse cx="47.5" cy="77.6" rx="2.2" ry="3.2" fill="#8dd97a" className="tree-leaf" />
          <ellipse cx="52.5" cy="77.8" rx="2.2" ry="3.2" fill="#8dd97a" className="tree-leaf" />
        </g>
      ) : null}

      {stage >= 1 ? (
        <g className="grow-in">
          <path
            d={`M50 ${88} C ${50 - trunkW * 0.3} ${80 - trunkH * 0.25}, ${50 + trunkW * 0.35} ${75 - trunkH * 0.55}, 50 ${trunkY}`}
            stroke={trunkColor}
            strokeWidth={trunkW}
            strokeLinecap="round"
            fill="none"
          />
          {branchLevel >= 1 ? <path d={`M50 ${trunkY + 11} C 42 ${trunkY + 6}, 39 ${trunkY}, 36 ${trunkY - 6}`} stroke={branchColor} strokeWidth="2.1" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 1 ? <path d={`M50 ${trunkY + 10} C 58 ${trunkY + 5}, 61 ${trunkY}, 64 ${trunkY - 6}`} stroke={branchColor} strokeWidth="2.1" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 2 ? <path d={`M50 ${trunkY + 4} C 43 ${trunkY - 1}, 41 ${trunkY - 5}, 38 ${trunkY - 10}`} stroke={branchColor} strokeWidth="1.8" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 2 ? <path d={`M50 ${trunkY + 3} C 57 ${trunkY - 2}, 59 ${trunkY - 5}, 62 ${trunkY - 11}`} stroke={branchColor} strokeWidth="1.8" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 3 ? <path d={`M50 ${trunkY - 2} C 47 ${trunkY - 7}, 46 ${trunkY - 11}, 45 ${trunkY - 15}`} stroke={branchColor} strokeWidth="1.6" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 3 ? <path d={`M50 ${trunkY - 2} C 53 ${trunkY - 7}, 54 ${trunkY - 11}, 55 ${trunkY - 16}`} stroke={branchColor} strokeWidth="1.6" fill="none" strokeLinecap="round" /> : null}
        </g>
      ) : null}

      {leaves.map((l) => (
        <ellipse
          key={`leaf-${l.idx}`}
          cx={l.cx}
          cy={l.cy}
          rx={l.rx}
          ry={l.ry}
          fill={l.color}
          className="tree-leaf grow-in"
          style={{ animationDelay: `${(l.idx % 7) * 0.12}s` }}
        />
      ))}

      {flowers.map((f, i) => (
        <g key={`flower-${i}`} className="grow-in">
          <circle cx={f.cx} cy={f.cy} r="1.1" fill="#ffd7e8" />
          <circle cx={f.cx - 1} cy={f.cy} r="0.7" fill="#f5a8ca" />
          <circle cx={f.cx + 1} cy={f.cy} r="0.7" fill="#f5a8ca" />
          <circle cx={f.cx} cy={f.cy - 1} r="0.7" fill="#f5a8ca" />
          <circle cx={f.cx} cy={f.cy + 1} r="0.7" fill="#f5a8ca" />
        </g>
      ))}

      {snowCaps.map((s, i) => (
        <ellipse key={`snow-${i}`} cx={s.cx} cy={s.cy - 1} rx={s.rx * 0.9} ry="0.8" fill="#f2f7fb" opacity="0.95" />
      ))}

      {rainDrops.map((d) => (
        <line
          key={`rain-${d.i}`}
          x1={d.x}
          y1={d.y}
          x2={d.x - 1.5}
          y2={d.y + 5}
          stroke="#9ec7e8"
          strokeWidth="1.2"
          strokeLinecap="round"
          style={{ animation: "rain-fall 1.2s linear infinite", animationDelay: `${d.i * 0.18}s` }}
        />
      ))}

      {sunGlints.map((s) => (
        <circle
          key={`glint-${s.i}`}
          cx={s.x}
          cy={s.y}
          r="1.8"
          fill="#fff3bd"
          style={{ animation: "glint 2.4s ease-in-out infinite", animationDelay: `${s.i * 0.22}s` }}
        />
      ))}

      {petals.map((p) => (
        <circle key={`petal-${p.i}`} cx={p.x} cy={trunkY - 6} r="1.1" fill="#f5a8ca" className="petal-fall" style={{ animationDelay: `${p.i * 1.15}s` }} />
      ))}

      {glow ? (
        <g filter="url(#softGlow)">
          <circle cx="50" cy={trunkY - 12} r="16" fill="#ffdca8" opacity="0.28" />
        </g>
      ) : null}
    </svg>
  );
}

function CyberTreeModal({
  data,
  onClose,
  onRefresh,
}: {
  data: CyberTreeData | null;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const d = data;
  const toast = useToast();
  const [refreshing, setRefreshing] = useState(false);
  const growth = Number(d?.growth || 0);
  const moodScore = Number(d?.mood?.score ?? 0);
  const moodFace =
    moodScore >= 85 ? "٩(ˊᗜˋ*)و" : moodScore >= 70 ? "(◕‿◕✿)" : moodScore >= 55 ? "(๑•ᴗ•๑)" : moodScore >= 40 ? "(｡•́︿•̀｡)" : "(╥﹏╥)";
  const stageLabel =
    growth < 10 ? "种子/发芽" : growth < 30 ? "小树苗" : growth < 60 ? "小树" : growth < 100 ? "大树" : "满级大树";
  const seasonLabel =
    d?.season === "spring" ? "春天" : d?.season === "summer" ? "夏天" : d?.season === "autumn" ? "秋天" : "冬天";

  async function refreshMood() {
    setRefreshing(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/mood-meter/refresh", { method: "POST" });
      if (!j?.ok) throw new Error(j?.error || "刷新失败");
      onRefresh();
      toast("心情温度已刷新");
    } catch (e: any) {
      toast(`刷新失败：${e?.message || e}`);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <Modal title="小渡&小玥の树" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="rounded-xl3 bg-white border border-white/70 shadow-soft2 p-3">
          <div className="flex items-center gap-2">
            <GrowthTreeSVG
              growthValue={growth}
              season={(d?.season || "spring") as "spring" | "summer" | "autumn" | "winter"}
              weatherFx={(d?.weatherFx || undefined) as "rainy" | "sunny" | "snowy" | undefined}
            />
            <div className="text-xs text-cream-muted">SVG 动态小树（随成长值 + 季节变化）</div>
          </div>
          <div className="mt-1 text-sm">当前：{seasonLabel} · {stageLabel}</div>
          <div className="mt-1 text-xs text-cream-muted">成长值：{growth.toFixed(2)}</div>
        </div>
        <div className="rounded-xl3 bg-white border border-white/70 shadow-soft2 p-3 text-xs space-y-1">
          <div>在一起第 <span className="font-semibold">{d?.daysTogether || 1}</span> 天</div>
          <div>聊了 <span className="font-semibold">{d?.totalRounds || 0}</span> 轮</div>
          <div className="text-cream-muted">起始日期：{d?.startDate || "-"}</div>
        </div>
        <div className="rounded-xl3 bg-white border border-white/70 shadow-soft2 p-2.5 text-xs space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[13px] font-semibold text-white shadow-soft2">
              {moodFace}
            </div>
            <div className="text-[15px] text-cream-text whitespace-nowrap">
              今日心情温度&nbsp;<span className="font-bold text-[20px]">{String(d?.mood?.score ?? "-")}</span>/100
            </div>
            <button
              className="h-9 w-9 shrink-0 rounded-full bg-white/70 backdrop-blur-lg border border-white/75 shadow-[0_2px_8px_rgba(40,34,26,0.14)] flex items-center justify-center text-[#5a544c] active:scale-[0.98] transition"
              onClick={refreshMood}
              disabled={refreshing}
              title="刷新温度"
            >
              <svg className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
                <path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v6h-6" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function CorePromptEditor({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [source, setSource] = useState<string>("");

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; content?: string; source?: string; error?: string }>("/miniapp-api/core-prompt");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setText((j.content || "").toString());
      setSource((j.source || "").toString());
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    const content = (text || "").trim();
    if (!content) {
      toast("内容不能为空");
      return;
    }
    const ok = window.confirm("确认保存核心 Prompt 吗？保存后会立即覆盖线上注入内容。");
    if (!ok) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/core-prompt", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      toast("已保存，下一条请求生效");
      setSource("r2");
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="核心 Prompt（3.16）" onClose={onClose}>
      <div className="space-y-3">
        <div className="text-xs text-cream-muted">
          当前来源：{source || "unknown"}。保存后会固定注入到所有对话请求。
        </div>
        <textarea
          className="w-full min-h-[40vh] rounded-xl2 bg-cream-card shadow-soft2 p-3 text-sm leading-relaxed"
          value={text}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value)}
          placeholder={loading ? "加载中..." : "在这里编辑核心 Prompt"}
        />
        <div className="flex items-center gap-2">
          <Btn kind="dark" onClick={load} disabled={loading || saving}>刷新</Btn>
          <Btn kind="dark" onClick={save} disabled={loading || saving}>保存</Btn>
        </div>
      </div>
    </Modal>
  );
}
