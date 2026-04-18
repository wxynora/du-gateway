import React, { Suspense, lazy, useEffect, useState } from "react";
import { applyTelegramThemeToHtmlClass, getTelegramWebApp, tgReady } from "./tg";
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
const CallHubScreen = lazy(() => import("./tabs/CallHubScreen").then((m) => ({ default: m.CallHubScreen })));

type PanelId = "logs" | "reasoning" | "memory-debug" | "du-notebook" | "stickers" | null;
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
type MainTab = "chats" | "daily" | "tools" | "settings";
type ChatScreenId = "du" | "wenyou" | null;
type ChatDraftMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
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

function Shell({
  onLogout,
  onOpenSecurity,
  onOpenDevices,
}: {
  onLogout?: () => void;
  onOpenSecurity?: () => void;
  onOpenDevices?: () => void;
}) {
  const toast = useToast();
  const [panel, setPanel] = useState<PanelId>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showCorePrompt, setShowCorePrompt] = useState(false);
  const [showBgEditor, setShowBgEditor] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showAlarm, setShowAlarm] = useState(false);
  const [showDuDay, setShowDuDay] = useState(false);
  const [showTree, setShowTree] = useState(false);
  const [showCallHub, setShowCallHub] = useState(false);
  const [showTodayNoteDetail, setShowTodayNoteDetail] = useState(false);
  const [showDailyReportDetail, setShowDailyReportDetail] = useState(false);
  const [mainTab, setMainTab] = useState<MainTab>("chats");
  const [activeScreen, setActiveScreen] = useState<ChatScreenId>(null);
  const [sharedChatWindowId, setSharedChatWindowId] = useState("");
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
    try {
      const tgUid = Number(getTelegramWebApp()?.initDataUnsafe?.user?.id || 0);
      if (tgUid > 0) setSharedChatWindowId(`tg_${tgUid}`);
    } catch {}
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

  const renderMainTab = () => {
    if (mainTab === "daily") {
      return (
        <MainSection title="日常">
          <RowLink
            label="树"
            description={tree ? `第 ${tree.daysTogether || 0} 天 · ${Number(tree.growth || 0).toFixed(0)} 成长值` : "成长状态与今天的树况"}
            onClick={() => setShowTree(true)}
          />
          <RowLink label="渡的一天" description="看今天的小日程和片段" onClick={() => setShowDuDay(true)} />
          <RowLink label="闹钟" description="查看和管理提醒" onClick={() => setShowAlarm(true)} />
          <RowLink label="日历" description="安排和查看日常计划" onClick={() => setShowSchedule(true)} />
        </MainSection>
      );
    }
    if (mainTab === "tools") {
      return (
        <MainSection title="工具">
          <RowLink label="日志" description="查看 / 过滤 / 复制" onClick={() => setPanel("logs")} />
          <RowLink label="思维链" description="最近 10 条推理与工具调用" onClick={() => setPanel("reasoning")} />
          <RowLink label="记忆调试" description="窗口总结与动态召回" onClick={() => setPanel("memory-debug")} />
          <RowLink label="渡的记事本" description="固定注入与条目管理" onClick={() => setPanel("du-notebook")} />
          <RowLink label="核心 Prompt" description="固定注入内容维护" onClick={() => setShowCorePrompt(true)} />
          <RowLink label="上游切换" description="查看并切换当前全局上游" onClick={() => setShowSettings(true)} />
        </MainSection>
      );
    }
    if (mainTab === "settings") {
      return (
        <MainSection title="设置">
          <RowLink label="安全管理" description="登录安全、退出与设备权限" onClick={() => onOpenSecurity?.()} />
          <RowLink label="设备管理" description="查看和撤销当前已登录设备" onClick={() => onOpenDevices?.()} />
          <RowLink label="背景设置" description="背景预设与相册图片同步" onClick={() => setShowBgEditor(true)} />
          {onLogout ? (
            <button
              className="mt-3 flex w-full items-center justify-center rounded-[20px] bg-[#E7D1D0] px-4 py-3 text-sm font-semibold text-[#734b49] shadow-[0_8px_20px_rgba(49,32,28,0.08)] active:scale-[0.99]"
              onClick={onLogout}
            >
              退出登录
            </button>
          ) : null}
        </MainSection>
      );
    }
    return (
      <ChatsHome
        windowId={sharedChatWindowId}
        dailyWhisper={dailyWhisper}
        dailyReport={dailyReport}
        onOpenDu={() => setActiveScreen("du")}
        onOpenWenyou={() => setActiveScreen("wenyou")}
        onOpenTodayNote={() => setShowTodayNoteDetail(true)}
        onOpenDailyReport={() => setShowDailyReportDetail(true)}
        onRefreshDailyReport={refreshDailyReport}
        dailyRefreshing={dailyRefreshing}
      />
    );
  };

  return (
    <div className="relative min-h-dvh safe-bottom overflow-hidden text-cream-text" style={rootStyle}>
      {activeScreen === "du" ? (
        <MainChatScreen
          title="渡"
          windowId={sharedChatWindowId}
          avatarLabel="渡"
          accent="du"
          onBack={() => setActiveScreen(null)}
          onOpenStickers={() => setPanel("stickers")}
          onOpenCall={() => setShowCallHub(true)}
        />
      ) : null}
      {activeScreen === "wenyou" ? (
        <FullScreenPane title="文游" accent="wenyou" onBack={() => setActiveScreen(null)}>
          <LazyPane><WenyouTab initialView="hub" /></LazyPane>
        </FullScreenPane>
      ) : null}
      {!activeScreen ? (
        <>
          <div className="relative min-h-dvh overflow-y-auto pb-[98px]">
            {renderMainTab()}
          </div>
          <BottomNav current={mainTab} onChange={setMainTab} />
        </>
      ) : null}

      {panel === "logs" ? (
        <FullScreenPane title="日志" accent="neutral" onBack={() => setPanel(null)}>
          <LazyPane><LogsTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "reasoning" ? (
        <FullScreenPane title="思维链" accent="neutral" onBack={() => setPanel(null)}>
          <LazyPane><ReasoningTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "memory-debug" ? (
        <FullScreenPane title="记忆调试" accent="neutral" onBack={() => setPanel(null)}>
          <LazyPane><MemoryDebugTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "du-notebook" ? (
        <FullScreenPane title="渡的记事本" accent="neutral" onBack={() => setPanel(null)}>
          <LazyPane><DuNotebookTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "stickers" ? (
        <FullScreenPane title="表情包" accent="neutral" onBack={() => setPanel(null)}>
          <LazyPane><StickersTab /></LazyPane>
        </FullScreenPane>
      ) : null}

      {showSettings ? (
        <FullScreenPane title="上游切换" accent="neutral" onBack={() => setShowSettings(false)}>
          <LazyPane><SettingsUpstream /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showCorePrompt ? <CorePromptEditor onClose={() => setShowCorePrompt(false)} /> : null}
      {showBgEditor ? <BackgroundEditor bg={bg} onChange={setBg} onClose={() => setShowBgEditor(false)} /> : null}
      {showSchedule ? (
        <FullScreenPane title="日历" accent="neutral" onBack={() => setShowSchedule(false)}>
          <LazyPane><ScheduleTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showAlarm ? (
        <FullScreenPane title="闹钟" accent="neutral" onBack={() => setShowAlarm(false)}>
          <LazyPane><AlarmTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showDuDay ? (
        <FullScreenPane title="渡的一天" accent="neutral" onBack={() => setShowDuDay(false)}>
          <LazyPane><DuDayTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showTodayNoteDetail ? (
        <FullScreenPane title="Today note" accent="neutral" onBack={() => setShowTodayNoteDetail(false)}>
          <div className="rounded-[20px] border border-white/60 bg-[rgba(255,255,255,0.9)] px-4 py-4 text-[14px] leading-7 text-cream-text shadow-[0_8px_20px_rgba(44,34,24,0.05)]">
            {dailyWhisper || "今天还没有新的 note。"}
          </div>
        </FullScreenPane>
      ) : null}
      {showDailyReportDetail ? (
        <FullScreenPane title="日报摘要" accent="neutral" onBack={() => setShowDailyReportDetail(false)}>
          <div className="rounded-[20px] border border-white/60 bg-[rgba(255,255,255,0.9)] px-4 py-4 shadow-[0_8px_20px_rgba(44,34,24,0.05)]">
            <div className="space-y-2 text-[13px] leading-6 text-cream-text">
              <div>日期：{dailyReport?.report_date || "-"}</div>
              <div>轮次：{String(dailyReport?.rounds || 0)}</div>
              <div>关键词：{Array.isArray(dailyReport?.keywords) && dailyReport?.keywords?.length ? dailyReport?.keywords?.join(" / ") : "-"}</div>
              <div className="whitespace-pre-wrap rounded-[18px] bg-[rgba(244,247,251,0.92)] px-3 py-3 text-cream-muted">
                {dailyReport?.summary_text || "今天的日报还没生成。"}
              </div>
              <div>更新时间：{dailyReport?.generated_at || "-"}</div>
            </div>
            <div className="mt-3">
              <Btn kind="blue" onClick={refreshDailyReport} disabled={dailyRefreshing}>
                {dailyRefreshing ? "刷新中..." : "刷新日报"}
              </Btn>
            </div>
          </div>
        </FullScreenPane>
      ) : null}
      {showTree ? (
        <FullScreenPane title="树" accent="neutral" onBack={() => setShowTree(false)}>
          <TreeScreen data={tree} onRefresh={loadTree} onClose={() => setShowTree(false)} />
        </FullScreenPane>
      ) : null}
      {showCallHub ? <LazyPane><CallHubScreen onClose={() => setShowCallHub(false)} /></LazyPane> : null}
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
        "group relative min-h-[116px] overflow-hidden rounded-[24px] p-4 text-left shadow-[6px_6px_13px_rgba(170,180,194,0.28),-3px_-3px_7px_rgba(255,255,255,0.52),inset_1px_1px_0_rgba(255,255,255,0.22)] backdrop-blur-xl transition active:scale-[0.99] " +
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
        <span className={"inline-flex h-10 w-10 items-center justify-center rounded-[16px] shadow-[4px_4px_9px_rgba(173,182,196,0.18),-1px_-1px_3px_rgba(255,255,255,0.34)] " + toneMap.badge}>
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

function LineIcon({ name }: { name: "logs" | "reasoning" | "upstream" | "prompt" | "background" | "tree" | "memory" | "notebook" | "wenyou-archives" | "wenyou-hub" | "stickers" | "voice-call" }) {
  const cls = "h-4 w-4 text-cream-text";
  if (name === "logs") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 6h16M4 12h16M4 18h10" /></svg>;
  if (name === "reasoning") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 12h4l2-4 4 8 2-4h4" /></svg>;
  if (name === "memory") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 5h14v14H5zM8 9h8M8 13h8M8 17h5" /></svg>;
  if (name === "notebook") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 4h12v16H6zM9 8h6M9 12h6M9 16h4" /></svg>;
  if (name === "wenyou-archives") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 5h14v14H5zM8 8h8M8 12h8M8 16h6" /></svg>;
  if (name === "wenyou-hub") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3 4 7v5c0 5 3.4 8.7 8 9 4.6-.3 8-4 8-9V7l-8-4zM9 12h6M12 9v6" /></svg>;
  if (name === "stickers") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="9" cy="10" r="1.2" fill="currentColor" /><circle cx="15" cy="10" r="1.2" fill="currentColor" /><path d="M8 14c1.6 2 6.4 2 8 0" /></svg>;
  if (name === "voice-call") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M7 5c4-2 6 0 6 0l2 2c.7.7.9 1.9.4 2.8l-1.3 2.3a1.8 1.8 0 0 0 .2 2l1.5 1.8c.7.8.6 2.1-.2 2.8l-1.3 1.1c-.8.6-1.8.7-2.7.3-3.4-1.7-6.2-4.6-7.9-8-.4-.8-.3-1.9.3-2.6l1.1-1.3c.7-.8 1.9-.9 2.8-.2l1.8 1.5a1.8 1.8 0 0 0 2 .2l2.3-1.3c.9-.5 2.1-.4 2.8.4l2 2s2 2 0 6" /></svg>;
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
          <div className="absolute left-1/2 top-1/2 w-[272px] -translate-x-1/2 -translate-y-[122%] rounded-[32px] bg-[rgba(244,247,251,0.84)] p-4 shadow-[0_8px_18px_rgba(173,182,196,0.22)] backdrop-blur-2xl">
            <div className="grid grid-cols-3 gap-3">
              <button
                className="h-14 rounded-[20px] bg-[#D6E4F2] flex items-center justify-center text-cream-text shadow-[4px_4px_10px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.42)] active:scale-[0.99] transition"
                onClick={onOpenBackground}
                title="背景设置"
              >
                <LineIcon name="background" />
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#F2E7BF] flex items-center justify-center text-cream-text shadow-[4px_4px_10px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.42)] active:scale-[0.99] transition"
                onClick={onOpenSchedule}
                title="日历与提醒"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M7 3v3M17 3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a1 1 0 0 1 1-1z" />
                </svg>
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#EFD5E1] flex items-center justify-center text-cream-text shadow-[4px_4px_10px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.42)] active:scale-[0.99] transition"
                onClick={onOpenAlarm}
                title="闹钟"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <circle cx="12" cy="13" r="7" />
                  <path d="M12 13V9m0 4 3 2M7 4 4 7m13-3 3 3" />
                </svg>
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#D6E4F2] flex items-center justify-center text-cream-text shadow-[4px_4px_10px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.42)] active:scale-[0.99] transition"
                onClick={onOpenDuDay}
                title="渡的一天"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M6 5h12M6 12h12M6 19h8" />
                </svg>
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#F2E7BF] flex items-center justify-center text-cream-text shadow-[4px_4px_10px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.42)] active:scale-[0.99] transition"
                onClick={onOpenTree}
                title="小渡&小玥の树"
              >
                <LineIcon name="tree" />
              </button>
              <button
                className="h-14 rounded-[20px] bg-[#EFD5E1] flex items-center justify-center text-cream-text shadow-[4px_4px_10px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.42)] active:scale-[0.99] transition"
                onClick={onOpenUpstream}
                title="上游切换"
              >
                <LineIcon name="upstream" />
              </button>
              <button
                className="h-14 rounded-[20px] bg-[rgba(244,247,251,0.92)] flex items-center justify-center text-cream-muted shadow-[4px_4px_10px_rgba(173,182,196,0.2),-2px_-2px_5px_rgba(255,255,255,0.42)] active:scale-[0.99] transition"
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
          className="h-[74px] w-[74px] rounded-full bg-[rgba(244,247,251,0.84)] shadow-[6px_6px_14px_rgba(170,180,194,0.24),-3px_-3px_7px_rgba(255,255,255,0.48)] backdrop-blur-2xl flex items-center justify-center text-cream-text"
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

function MainSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-5 pb-8" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 18px)" }}>
      <h1 className="text-[26px] font-medium tracking-tight text-cream-text">{title}</h1>
      <div className="mt-7">{children}</div>
    </div>
  );
}

function contentToPlainText(content: any): string {
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (!part || typeof part !== "object") return "";
        if (part.type === "text") return String(part.text || "").trim();
        if (part.type === "image_url") return "[图片]";
        return "";
      })
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  return "";
}

function pickLatestPreview(rounds: Array<any>): { preview: string; time: string } {
  const list = Array.isArray(rounds) ? rounds : [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const round = list[i];
    const msgs = Array.isArray(round?.messages) ? round.messages : [];
    for (let j = msgs.length - 1; j >= 0; j -= 1) {
      const text = contentToPlainText(msgs[j]?.content);
      if (text) {
        return {
          preview: text,
          time: String(round?.timestamp || "").trim() || "最近",
        };
      }
    }
  }
  return { preview: "", time: "" };
}

function mapRoundsToDraftMessages(rounds: Array<any>): ChatDraftMessage[] {
  const out: ChatDraftMessage[] = [];
  for (const round of Array.isArray(rounds) ? rounds : []) {
    const createdAt = String(round?.timestamp || "").trim() || new Date().toISOString();
    for (const msg of Array.isArray(round?.messages) ? round.messages : []) {
      const role = String(msg?.role || "").trim().toLowerCase();
      if (role !== "user" && role !== "assistant") continue;
      const text = contentToPlainText(msg?.content);
      if (!text) continue;
      out.push({
        id: `${role}-${createdAt}-${out.length}`,
        role: role as "user" | "assistant",
        content: text,
        createdAt,
      });
    }
  }
  return out.slice(-80);
}

function SummaryBlock({
  label,
  text,
  action,
  onClick,
}: {
  label: string;
  text: string;
  action?: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <button
      className="block w-full rounded-[24px] border border-white/60 bg-[rgba(255,255,255,0.7)] px-4 py-4 text-left shadow-[0_10px_28px_rgba(38,32,24,0.04)] active:scale-[0.995]"
      onClick={onClick}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="h-3 w-1 rounded-full bg-[rgba(117,124,142,0.28)]" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cream-muted">{label}</span>
        </div>
        {action}
      </div>
      <div className="mt-3 whitespace-pre-wrap text-[14px] leading-6 text-cream-text">{text}</div>
    </button>
  );
}

function ChatsHome({
  windowId,
  dailyWhisper,
  dailyReport,
  onOpenDu,
  onOpenWenyou,
  onOpenTodayNote,
  onOpenDailyReport,
  onRefreshDailyReport,
  dailyRefreshing,
}: {
  windowId: string;
  dailyWhisper: string;
  dailyReport: DailyReport | null;
  onOpenDu: () => void;
  onOpenWenyou: () => void;
  onOpenTodayNote: () => void;
  onOpenDailyReport: () => void;
  onRefreshDailyReport: () => void;
  dailyRefreshing: boolean;
}) {
  const [duPreview, setDuPreview] = useState("正在同步最近聊天…");
  const [duTime, setDuTime] = useState("主会话");
  const [wenyouPreview, setWenyouPreview] = useState("独立文游会话");
  const [wenyouTime, setWenyouTime] = useState("独立会话");

  const reportSummary = dailyReport
    ? `聊了 ${String(dailyReport.rounds || 0)} 轮 · ${Array.isArray(dailyReport.keywords) && dailyReport.keywords.length ? dailyReport.keywords.join(" / ") : "暂无关键词"}\n${dailyReport.summary_text || ""}`.trim()
    : "今天的日报还没生成。";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!windowId) return;
      try {
        const j = await apiJson<{ rounds?: Array<any> }>(`/miniapp-api/windows/${encodeURIComponent(windowId)}/conversation?last_n=12`);
        if (cancelled) return;
        const picked = pickLatestPreview(j?.rounds || []);
        if (picked.preview) {
          setDuPreview(picked.preview);
          setDuTime(picked.time || "最近");
        }
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, [windowId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const j = await apiJson<{ ok?: boolean; active?: boolean; session?: { instance_name?: string; startedAt?: string } | null }>("/miniapp-api/wenyou/status");
        if (cancelled) return;
        if (j?.ok && j?.active && j?.session) {
          setWenyouPreview(`当前副本：${String(j.session.instance_name || "系统空间进行中")}`);
          setWenyouTime(String(j.session.startedAt || "").trim() || "进行中");
        }
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="px-5 pb-8" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 18px)" }}>
      <h1 className="text-[26px] font-medium tracking-tight text-cream-text">会话</h1>
      <div className="mt-7 space-y-5 rounded-[30px] border border-white/55 bg-[rgba(255,255,255,0.82)] px-4 py-5 shadow-[0_14px_34px_rgba(44,34,24,0.05)]">
        <SummaryBlock label="Today note" text={dailyWhisper || "今天还没有新的 note。"} onClick={onOpenTodayNote} />
        <SummaryBlock
          label="日报摘要"
          text={reportSummary}
          onClick={onOpenDailyReport}
          action={
            <button
              className="rounded-full bg-[rgba(244,247,251,0.92)] px-3 py-1.5 text-[11px] font-semibold text-cream-muted shadow-[0_6px_14px_rgba(44,34,24,0.05)] active:scale-[0.98]"
              onClick={(e) => {
                e.stopPropagation();
                onRefreshDailyReport();
              }}
              disabled={dailyRefreshing}
            >
              {dailyRefreshing ? "刷新中" : "刷新"}
            </button>
          }
        />
      </div>

      <div className="mt-4 overflow-hidden rounded-[28px] border border-white/60 bg-[rgba(255,255,255,0.86)] shadow-[0_12px_30px_rgba(44,34,24,0.05)]">
        <ChatEntryRow
          title="渡"
          preview={duPreview}
          time={duTime}
          badge="置顶"
          tone="du"
          onClick={onOpenDu}
        />
        <div className="mx-4 h-px bg-[rgba(117,124,142,0.08)]" />
        <ChatEntryRow
          title="文游"
          preview={wenyouPreview}
          time={wenyouTime}
          tone="wenyou"
          onClick={onOpenWenyou}
        />
      </div>
    </div>
  );
}

function ChatEntryRow({
  title,
  preview,
  time,
  tone,
  badge,
  onClick,
}: {
  title: string;
  preview: string;
  time: string;
  tone: "du" | "wenyou";
  badge?: string;
  onClick: () => void;
}) {
  const palette = tone === "wenyou"
    ? { shell: "bg-[#F3EDEF] text-[#704A5D]" }
    : { shell: "bg-[#EDF2F7] text-[#4A5568]" };
  return (
    <button className="flex w-full items-center gap-4 px-4 py-4 text-left active:bg-white/55" onClick={onClick}>
      <div className={`flex h-[52px] w-[52px] items-center justify-center rounded-[20px] text-[19px] font-semibold shadow-sm ${palette.shell}`}>
        {title.slice(0, 1)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-[17px] font-medium text-cream-text">{title}</span>
            {badge ? <span className="rounded-full bg-[rgba(244,247,251,0.95)] px-2 py-0.5 text-[10px] font-semibold text-cream-muted">{badge}</span> : null}
          </div>
          <span className="text-[11px] text-cream-muted">{time}</span>
        </div>
        <div className="mt-1 truncate text-[13px] text-cream-muted">{preview}</div>
      </div>
    </button>
  );
}

function RowLink({
  label,
  description,
  onClick,
}: {
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      className="flex w-full items-center gap-3 rounded-[24px] border border-white/60 bg-[rgba(255,255,255,0.86)] px-4 py-4 text-left shadow-[0_10px_28px_rgba(44,34,24,0.05)] active:scale-[0.99]"
      onClick={onClick}
    >
      <div className="h-11 w-11 rounded-full bg-[rgba(244,247,251,0.95)] shadow-[inset_0_1px_2px_rgba(255,255,255,0.8)]" />
      <div className="min-w-0 flex-1">
        <div className="text-[16px] font-medium text-cream-text">{label}</div>
        <div className="mt-1 text-[12px] text-cream-muted">{description}</div>
      </div>
      <span className="text-lg text-cream-muted">›</span>
    </button>
  );
}

function BottomNav({
  current,
  onChange,
}: {
  current: MainTab;
  onChange: (tab: MainTab) => void;
}) {
  const items: Array<{ id: MainTab; label: string }> = [
    { id: "chats", label: "会话" },
    { id: "daily", label: "日常" },
    { id: "tools", label: "工具" },
    { id: "settings", label: "设置" },
  ];
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-white/60 bg-[rgba(255,255,255,0.84)] px-5 pb-[calc(env(safe-area-inset-bottom,0px)+10px)] pt-2 backdrop-blur-xl">
      <div className="mx-auto flex max-w-xl items-center justify-between">
        {items.map((item) => {
          const active = current === item.id;
          return (
            <button
              key={item.id}
              className="flex min-w-[60px] flex-col items-center gap-1.5 px-2 py-2"
              onClick={() => onChange(item.id)}
            >
              <span className={`h-2 w-2 rounded-full ${active ? "bg-cream-text" : "bg-[rgba(117,124,142,0.18)]"}`} />
              <span className={`text-[11px] font-semibold tracking-[0.12em] ${active ? "text-cream-text" : "text-cream-muted"}`}>{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function FullScreenPane({
  title,
  accent,
  onBack,
  children,
}: {
  title: string;
  accent: "du" | "wenyou" | "neutral";
  onBack: () => void;
  children: React.ReactNode;
}) {
  const chipClass = accent === "wenyou"
    ? "bg-[#F3EDEF] text-[#704A5D]"
    : accent === "du"
      ? "bg-[#EDF2F7] text-[#4A5568]"
      : "bg-[#F3F5F8] text-[#5C6473]";
  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-[#F8F9FB]">
      <div className="flex items-center justify-between px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+8px)]">
        <div className="flex items-center gap-2">
          <button className="rounded-full px-3 py-2 text-sm text-cream-muted active:bg-white/65" onClick={onBack}>返回</button>
          <div className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${chipClass}`}>{title.slice(0, 1)}</div>
          <div className="text-[16px] font-medium text-cream-text">{title}</div>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">{children}</div>
    </div>
  );
}

function MainChatScreen({
  title,
  avatarLabel,
  windowId,
  accent,
  onBack,
  onOpenStickers,
  onOpenCall,
}: {
  title: string;
  avatarLabel: string;
  windowId: string;
  accent: "du" | "wenyou";
  onBack: () => void;
  onOpenStickers: () => void;
  onOpenCall: () => void;
}) {
  const toast = useToast();
  const storageKey = `miniapp.chat.${windowId}.messages.v1`;
  const modelKey = `miniapp.chat.${windowId}.model.v1`;
  const [messages, setMessages] = useState<ChatDraftMessage[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      if (Array.isArray(parsed) && parsed.length) return parsed;
    } catch {}
    return [
      {
        id: "seed-1",
        role: "assistant",
        content: "我在。你直接说就好。",
        createdAt: new Date().toISOString(),
      },
    ];
  });
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [activeModel, setActiveModel] = useState(() => {
    try {
      return (localStorage.getItem(modelKey) || "").trim();
    } catch {
      return "";
    }
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!windowId) return;
      try {
        const j = await apiJson<{ rounds?: Array<any> }>(`/miniapp-api/windows/${encodeURIComponent(windowId)}/conversation?last_n=20`);
        if (cancelled) return;
        const mapped = mapRoundsToDraftMessages(j?.rounds || []);
        if (mapped.length) setMessages(mapped);
      } catch (e: any) {
        if (!cancelled) toast(`聊天历史加载失败：${e?.message || e}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [windowId, toast]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(messages.slice(-80)));
    } catch {}
  }, [messages, storageKey]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const j = await apiJson<{ data?: Array<{ id?: string }> }>("/v1/models");
        const ids = Array.isArray(j?.data)
          ? j.data.map((item) => String(item?.id || "").trim()).filter(Boolean)
          : [];
        if (cancelled || !ids.length) return;
        setActiveModel((prev) => {
          const next = prev && ids.includes(prev) ? prev : ids[0];
          try {
            if (next) localStorage.setItem(modelKey, next);
          } catch {}
          return next;
        });
      } catch (e: any) {
        if (!cancelled) toast(`模型列表加载失败：${e?.message || e}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [modelKey, toast]);

  async function sendMessage() {
    const content = input.trim();
    if (!content || sending) return;
    if (!windowId) {
      toast("当前拿不到 Telegram 用户 ID，不能接入共享上下文");
      return;
    }
    if (!activeModel) {
      toast("当前还没拿到可用模型，稍后再试");
      return;
    }
    const userMsg: ChatDraftMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };
    const assistantId = `assistant-${Date.now()}`;
    setInput("");
    setPlusOpen(false);
    setSending(true);
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: assistantId, role: "assistant", content: "", createdAt: new Date().toISOString() },
    ]);
    try {
      const history = [...messages, userMsg].map((msg) => ({ role: msg.role, content: msg.content }));
      const resp = await apiFetch("/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: activeModel,
          messages: history,
          stream: true,
          window_id: windowId,
        }),
      });
      if (!resp.ok || !resp.body) {
        const text = await resp.text();
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          for (const line of part.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6).trim();
            if (!payload || payload === "[DONE]") continue;
            const chunk = JSON.parse(payload);
            const delta = String(chunk?.choices?.[0]?.delta?.content || "");
            if (!delta) continue;
            setMessages((prev) => prev.map((msg) => (msg.id === assistantId ? { ...msg, content: msg.content + delta } : msg)));
          }
        }
      }
    } catch (e: any) {
      setMessages((prev) =>
        prev.map((msg) => (msg.id === assistantId ? { ...msg, content: `（发送失败：${e?.message || e}）` } : msg))
      );
      toast(`发送失败：${e?.message || e}`);
    } finally {
      setSending(false);
    }
  }

  const avatarClass = accent === "wenyou"
    ? "bg-[#F3EDEF] text-[#704A5D]"
    : "bg-[#EDF2F7] text-[#4A5568]";

  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-[#F8F9FB]">
      <div className="flex items-center justify-between border-b border-white/60 bg-[rgba(255,255,255,0.8)] px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+8px)] backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <button className="rounded-full px-3 py-2 text-sm text-cream-muted active:bg-white/65" onClick={onBack}>返回</button>
          <div className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${avatarClass}`}>{avatarLabel}</div>
          <div>
            <div className="text-[16px] font-medium text-cream-text">{title}</div>
            <div className="text-[11px] text-cream-muted">{activeModel ? activeModel : "模型加载中..."}</div>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-4">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={
                  "max-w-[82%] whitespace-pre-wrap rounded-[22px] px-4 py-3 text-[15px] leading-6 shadow-[0_8px_22px_rgba(44,34,24,0.04)] " +
                  (msg.role === "user"
                    ? "rounded-tr-[8px] bg-[#2E3440] text-white"
                    : "rounded-tl-[8px] border border-white/60 bg-[rgba(255,255,255,0.92)] text-cream-text")
                }
              >
                {msg.content || (sending && msg.role === "assistant" ? "…" : "")}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-white/60 bg-[rgba(255,255,255,0.88)] pb-[calc(env(safe-area-inset-bottom,0px)+10px)] backdrop-blur-xl">
        <div className={`grid transition-[grid-template-rows,opacity] duration-300 ${plusOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
          <div className="overflow-hidden">
            <div className="flex gap-6 px-6 pb-2 pt-4">
              <ChatActionButton label="表情包" onClick={() => { setPlusOpen(false); onOpenStickers(); }} />
              <ChatActionButton label="通话" onClick={() => { setPlusOpen(false); onOpenCall(); }} />
            </div>
          </div>
        </div>
        <div className="flex items-end gap-2 px-3 pt-3">
          <button
            className={`rounded-full px-3 py-3 text-sm text-cream-muted transition ${plusOpen ? "bg-white/85" : "bg-transparent active:bg-white/65"}`}
            onClick={() => setPlusOpen((v) => !v)}
          >
            ＋
          </button>
          <div className="flex-1 rounded-[22px] bg-[#F3F5F8] px-4 py-3 shadow-[inset_0_1px_2px_rgba(255,255,255,0.8)]">
            <input
              className="w-full bg-transparent text-[15px] text-cream-text outline-none placeholder:text-cream-muted"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder="输入消息..."
            />
          </div>
          <button
            className="flex h-10 w-10 items-center justify-center rounded-full bg-[#2E3440] text-white shadow-[0_10px_22px_rgba(46,52,64,0.22)] disabled:opacity-50"
            onClick={() => void sendMessage()}
            disabled={sending || !input.trim()}
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  );
}

function ChatActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button className="flex flex-col items-center gap-2" onClick={onClick}>
      <div className="flex h-[58px] w-[58px] items-center justify-center rounded-[20px] bg-[rgba(244,247,251,0.94)] shadow-[0_8px_20px_rgba(44,34,24,0.04)]">
        <span className="text-lg text-cream-muted">{label === "表情包" ? "☺" : "✆"}</span>
      </div>
      <span className="text-[11px] font-semibold text-cream-muted">{label}</span>
    </button>
  );
}

function TreeScreen({
  data,
  onRefresh,
}: {
  data: CyberTreeData | null;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const d = data;
  const growth = Number(d?.growth || 0);
  const seasonLabel =
    d?.season === "spring" ? "春天" : d?.season === "summer" ? "夏天" : d?.season === "autumn" ? "秋天" : "冬天";
  const stageLabel =
    growth < 10 ? "种子/发芽" : growth < 30 ? "小树苗" : growth < 60 ? "小树" : growth < 100 ? "大树" : "满级大树";
  const [refreshing, setRefreshing] = useState(false);

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
    <div className="space-y-3">
      <div className="rounded-[20px] border border-white/60 bg-[rgba(255,255,255,0.9)] px-4 py-4 shadow-[0_8px_20px_rgba(44,34,24,0.05)]">
        <div className="flex items-center gap-3">
          <GrowthTreeSVG
            growthValue={growth}
            season={(d?.season || "spring") as "spring" | "summer" | "autumn" | "winter"}
            weatherFx={(d?.weatherFx || undefined) as "rainy" | "sunny" | "snowy" | undefined}
          />
          <div className="text-xs text-cream-muted">当前：{seasonLabel} · {stageLabel}</div>
        </div>
      </div>
      <div className="rounded-[20px] border border-white/60 bg-[rgba(255,255,255,0.9)] px-4 py-4 shadow-[0_8px_20px_rgba(44,34,24,0.05)] text-[13px] leading-6 text-cream-text">
        <div>在一起第 {d?.daysTogether || 0} 天</div>
        <div>聊了 {d?.totalRounds || 0} 轮</div>
        <div>成长值：{growth.toFixed(2)}</div>
        <div>起始日期：{d?.startDate || "-"}</div>
      </div>
      <div className="rounded-[20px] border border-white/60 bg-[rgba(255,255,255,0.9)] px-4 py-4 shadow-[0_8px_20px_rgba(44,34,24,0.05)]">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[14px] text-cream-text">今日心情温度：{String(d?.mood?.score ?? "-")}/100</div>
          <Btn kind="blue" onClick={refreshMood} disabled={refreshing}>
            {refreshing ? "刷新中..." : "刷新"}
          </Btn>
        </div>
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
  const [showSecurityManager, setShowSecurityManager] = useState(false);

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
      toast("已进入 SumiTalk");
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
    setShowSecurityManager(false);
    toast("已退出登录");
  }

  if (metaLoading) {
    return <LoadingScreen text="正在检查面板登录状态..." />;
  }
  if (!authEnabled || ready) {
    return (
      <ShellWithLogout
        onLogout={authEnabled ? logout : undefined}
        onOpenDevices={authEnabled ? () => setShowSecurityManager(true) : undefined}
        onOpenDeviceManager={authEnabled ? () => setShowDeviceManager(true) : undefined}
        deviceManagerOpen={showDeviceManager}
        onCloseDevices={() => setShowDeviceManager(false)}
        securityManagerOpen={showSecurityManager}
        onCloseSecurityManager={() => setShowSecurityManager(false)}
        onOpenDeviceManagerFromSecurity={() => {
          setShowSecurityManager(false);
          setShowDeviceManager(true);
        }}
      />
    );
  }
  return (
    <div className="min-h-dvh bg-cream-bg px-5 py-6 text-cream-text" style={{ fontFamily: '"Nunito", sans-serif' }}>
      <div className="mx-auto flex min-h-[calc(100dvh-3rem)] max-w-md flex-col items-center justify-center">
        {/* 螃蟹 + 标题 */}
        <div className="mb-6 flex flex-col items-center">
          <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-[20px] bg-[rgba(244,247,251,0.82)] shadow-soft2">
            <ClaudePixelCrabIcon />
          </div>
          <div className="text-[26px] font-bold tracking-tight text-cream-text">
            {secondPrompt && loginStep === "question" ? "Security Check" : "Welcome to SumiTalk"}
          </div>
          <div className="mt-1 text-[15px] text-cream-muted">
            {secondPrompt && loginStep === "question" ? "Answer the question to continue." : "Enter password to continue."}
          </div>
        </div>

        {/* 卡片 */}
        <div className="neo-panel w-full p-6">
          <div className="space-y-4">
            {loginStep === "password" || !secondPrompt ? (
              <label className="block">
                <div className="mb-2 text-[13px] font-semibold text-cream-muted">Password</div>
                <input
                  className="h-12 w-full rounded-[16px] border-none bg-cream-bg px-4 text-[16px] text-cream-text outline-none shadow-[inset_3px_3px_7px_rgba(173,182,196,0.28),inset_-2px_-2px_4px_rgba(255,255,255,0.7)] placeholder:text-cream-muted focus:ring-2 focus:ring-cream-accent/40"
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
                <div className="mb-2 text-[13px] font-semibold text-cream-muted">{secondPrompt}</div>
                <input
                  className="h-12 w-full rounded-[16px] border-none bg-cream-bg px-4 text-[16px] text-cream-text outline-none shadow-[inset_3px_3px_7px_rgba(173,182,196,0.28),inset_-2px_-2px_4px_rgba(255,255,255,0.7)] placeholder:text-cream-muted focus:ring-2 focus:ring-cream-accent/40"
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
              <div className="rounded-[12px] bg-cream-danger/10 px-4 py-2.5 text-[14px] text-cream-danger">
                {errorText}
              </div>
            ) : null}

            <div className="flex items-center justify-center gap-3 pt-1">
              {secondPrompt && loginStep === "question" ? (
                <button
                  type="button"
                  className="min-w-[90px] rounded-[14px] bg-cream-bg px-5 py-3 text-[15px] font-semibold text-cream-muted shadow-soft2 transition active:translate-y-[1px] active:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
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
                className="min-w-[140px] rounded-[14px] bg-cream-accent/80 px-6 py-3 text-[15px] font-bold text-cream-text shadow-soft2 transition active:translate-y-[1px] active:bg-cream-accent/90 active:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void login()}
                disabled={submitting}
              >
                {submitting ? "Verifying..." : secondPrompt && loginStep === "password" ? "Next" : "Sign In"}
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
  onOpenDeviceManager,
  deviceManagerOpen,
  onCloseDevices,
  securityManagerOpen,
  onCloseSecurityManager,
  onOpenDeviceManagerFromSecurity,
}: {
  onLogout?: () => void;
  onOpenDevices?: () => void;
  onOpenDeviceManager?: () => void;
  deviceManagerOpen?: boolean;
  onCloseDevices?: () => void;
  securityManagerOpen?: boolean;
  onCloseSecurityManager?: () => void;
  onOpenDeviceManagerFromSecurity?: () => void;
}) {
  return (
    <>
      <Shell onLogout={onLogout} onOpenSecurity={onOpenDevices} onOpenDevices={onOpenDeviceManager} />
      {securityManagerOpen && onCloseSecurityManager ? (
        <SecurityManagerModal
          onClose={onCloseSecurityManager}
          onOpenDevices={onOpenDeviceManagerFromSecurity}
          onLogout={onLogout}
        />
      ) : null}
      {deviceManagerOpen && onCloseDevices ? <DeviceManagerModal onClose={onCloseDevices} onLogout={onLogout} /> : null}
    </>
  );
}

function SecurityManagerModal({
  onClose,
  onOpenDevices,
  onLogout,
}: {
  onClose: () => void;
  onOpenDevices?: () => void;
  onLogout?: () => void;
}) {
  return (
    <Modal title="安全管理" onClose={onClose}>
      <div className="space-y-3 pb-4">
        <div className="neo-panel-soft p-3 text-xs leading-6 text-cream-muted">
          这里可以管理当前登录安全相关的操作。
        </div>
        {onOpenDevices ? (
          <div className="neo-panel p-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-cream-text">设备管理</div>
              <div className="mt-1 text-xs text-cream-muted">查看已登录设备，撤销某个浏览器的访问权限。</div>
            </div>
            <Btn kind="blue" onClick={onOpenDevices}>进入</Btn>
          </div>
        ) : null}
        {onLogout ? (
          <div className="neo-panel p-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-cream-text">退出登录</div>
              <div className="mt-1 text-xs text-cream-muted">清掉当前浏览器的登录态，回到登录页。</div>
            </div>
            <Btn kind="danger" onClick={onLogout}>退出</Btn>
          </div>
        ) : null}
      </div>
    </Modal>
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
  const [activeKey, setActiveKey] = useState<"a" | "b">("a");
  const [promptA, setPromptA] = useState("");
  const [promptB, setPromptB] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [source, setSource] = useState<string>("");
  const [portrait, setPortrait] = useState<{
    xinyue_candidates?: Array<{ id?: string; summary?: string }>;
    du_candidates?: Array<{ id?: string; summary?: string }>;
    interaction_candidates?: Array<{ id?: string; summary?: string }>;
  } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [j, p] = await Promise.all([
        apiJson<{ ok?: boolean; content?: string; source?: string; error?: string; active_key?: string; prompts?: { a?: string; b?: string } }>("/miniapp-api/core-prompt"),
        apiJson<{ ok?: boolean; xinyue_candidates?: Array<{ id?: string; summary?: string }>; du_candidates?: Array<{ id?: string; summary?: string }>; interaction_candidates?: Array<{ id?: string; summary?: string }> }>("/miniapp-api/portrait-memory"),
      ]);
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setActiveKey(((j.active_key || "a").toString() === "b" ? "b" : "a"));
      setPromptA(((j.prompts?.a ?? j.content) || "").toString());
      setPromptB((j.prompts?.b || "").toString());
      setSource((j.source || "").toString());
      if (p?.ok) setPortrait(p);
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
    const pa = (promptA || "").trim();
    const pb = (promptB || "").trim();
    if (activeKey === "a" && !pa) {
      toast("当前选中的 Prompt A 不能为空");
      return;
    }
    if (activeKey === "b" && !pb) {
      toast("当前选中的 Prompt B 不能为空");
      return;
    }
    const ok = window.confirm("确认保存核心 Prompt 吗？保存后会立即覆盖线上注入内容。");
    if (!ok) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/core-prompt", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_key: activeKey, prompts: { a: promptA, b: promptB } }),
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

  async function copyText(text: string) {
    const content = (text || "").trim();
    if (!content) {
      toast("没有可复制的内容");
      return;
    }
    try {
      await navigator.clipboard.writeText(content);
      toast("已复制");
    } catch (e: any) {
      toast(`复制失败：${e?.message || e}`);
    }
  }

  async function deletePortrait(bucket: "xinyue" | "du" | "interaction", id: string) {
    if (!id) return;
    const ok = window.confirm("确认删除这条候选吗？");
    if (!ok) return;
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/portrait-memory/${encodeURIComponent(bucket)}/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除");
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  return (
    <Modal title="核心 Prompt（3.16）" onClose={onClose}>
      <div className="space-y-3">
        <div className="text-xs text-cream-muted">
          当前来源：{source || "unknown"}。保存后会固定注入到所有对话请求。当前启用：Prompt {activeKey.toUpperCase()}。
        </div>
        <div className="flex items-center gap-2">
          <Btn kind={activeKey === "a" ? "blue" : "dark"} onClick={() => setActiveKey("a")} disabled={loading || saving}>Prompt A</Btn>
          <Btn kind={activeKey === "b" ? "blue" : "dark"} onClick={() => setActiveKey("b")} disabled={loading || saving}>Prompt B</Btn>
        </div>
        <div className="space-y-2">
          <div className="text-xs text-cream-muted">Prompt A</div>
          <textarea
            className="w-full min-h-[24vh] rounded-xl2 bg-cream-card shadow-soft2 p-3 text-sm leading-relaxed"
            value={promptA}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setPromptA(e.target.value)}
            placeholder={loading ? "加载中..." : "在这里编辑 Prompt A"}
          />
        </div>
        <div className="space-y-2">
          <div className="text-xs text-cream-muted">Prompt B</div>
          <textarea
            className="w-full min-h-[24vh] rounded-xl2 bg-cream-card shadow-soft2 p-3 text-sm leading-relaxed"
            value={promptB}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setPromptB(e.target.value)}
            placeholder={loading ? "加载中..." : "在这里编辑 Prompt B"}
          />
        </div>
        <details className="neo-panel-soft px-3 py-3 text-sm">
          <summary className="cursor-pointer select-none">画像层候选</summary>
          <div className="mt-3 space-y-3">
            <PortraitBlock title="辛玥画像候选" bucket="xinyue" items={portrait?.xinyue_candidates || []} onCopy={copyText} onDelete={deletePortrait} />
            <PortraitBlock title="渡画像候选" bucket="du" items={portrait?.du_candidates || []} onCopy={copyText} onDelete={deletePortrait} />
            <PortraitBlock title="相处模式候选" bucket="interaction" items={portrait?.interaction_candidates || []} onCopy={copyText} onDelete={deletePortrait} />
          </div>
        </details>
        <div className="flex items-center gap-2">
          <Btn kind="dark" onClick={load} disabled={loading || saving}>刷新</Btn>
          <Btn kind="dark" onClick={save} disabled={loading || saving}>保存</Btn>
        </div>
      </div>
    </Modal>
  );
}

function PortraitBlock({
  title,
  bucket,
  items,
  onCopy,
  onDelete,
}: {
  title: string;
  bucket: "xinyue" | "du" | "interaction";
  items: Array<{ id?: string; summary?: string }>;
  onCopy: (text: string) => void;
  onDelete: (bucket: "xinyue" | "du" | "interaction", id: string) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="text-xs text-cream-muted">{title} · {items.length}</div>
      {!items.length ? <div className="text-xs text-cream-muted">（暂无）</div> : null}
      {items.map((item, idx) => (
        <div key={item.id || `${title}-${idx}`} className="neo-panel px-3 py-2">
          <div className="whitespace-pre-wrap text-sm leading-relaxed">{String(item.summary || "")}</div>
          <div className="mt-2 flex items-center gap-2">
            <Btn kind="blue" onClick={() => onCopy(String(item.summary || ""))}>复制</Btn>
            {item.id ? <Btn kind="danger" onClick={() => onDelete(bucket, String(item.id || ""))}>删除</Btn> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
