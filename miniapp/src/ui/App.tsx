import React, { Suspense, lazy, useEffect, useState } from "react";
import { applyTelegramThemeToHtmlClass, getTelegramWebApp, tgReady } from "./tg";
import { ToastProvider, useToast } from "./toast";
import { apiFetch, apiJson, getOrCreatePanelDeviceId, getPanelDeviceLabel, getPanelToken, setPanelToken } from "./api";
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
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!deferHomeExtras) return;
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

  const renderMainTab = () => {
    if (mainTab === "daily") {
      return (
        <div className="bg-[#FDFDFD] px-6 pb-8" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 56px)" }}>
          <h1 className="mb-8 text-[26px] font-medium tracking-tight text-gray-900">日常</h1>
          <div className="space-y-4">
            <PageCardRow
              icon={<FeatherIcon />}
              label="树"
              onClick={() => setShowTree(true)}
            />
            <PageCardRow
              icon={<SunIconMini />}
              label="渡的一天"
              onClick={() => setShowDuDay(true)}
            />
            <PageCardRow
              icon={<ClockIconMini />}
              label="闹钟"
              onClick={() => setShowAlarm(true)}
            />
            <PageCardRow
              icon={<CalendarIconMini />}
              label="日历"
              onClick={() => setShowSchedule(true)}
            />
          </div>
        </div>
      );
    }
    if (mainTab === "tools") {
      return (
        <div className="bg-[#FDFDFD] px-6 pb-8" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 56px)" }}>
          <h1 className="mb-8 text-[26px] font-medium tracking-tight text-gray-900">工具</h1>
          <div className="overflow-hidden rounded-[28px] border border-gray-100/60 bg-white shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <ListRow icon={<FileTextIcon />} label="日志" onClick={() => setPanel("logs")} />
            <ListRow icon={<GitMergeIcon />} label="思维链" onClick={() => setPanel("reasoning")} />
            <ListRow icon={<CpuIcon />} label="记忆调试" onClick={() => setPanel("memory-debug")} />
            <ListRow icon={<BookOpenIcon />} label="渡的记事本" onClick={() => setPanel("du-notebook")} />
            <ListRow icon={<CodeIcon />} label="核心 Prompt" onClick={() => setShowCorePrompt(true)} />
            <ListRow icon={<ToggleRightIcon />} label="上游切换" onClick={() => setShowSettings(true)} last />
          </div>
        </div>
      );
    }
    if (mainTab === "settings") {
      return (
        <div className="bg-[#FDFDFD] px-6 pb-8" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 56px)" }}>
          <h1 className="mb-8 text-[26px] font-medium tracking-tight text-gray-900">设置</h1>
          <div className="overflow-hidden rounded-[28px] border border-gray-100/60 bg-white shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <ListRow icon={<ShieldIconMini />} label="安全管理" onClick={() => onOpenSecurity?.()} />
            <ListRow icon={<SmartphoneIconMini />} label="设备管理" onClick={() => onOpenDevices?.()} />
            {onLogout ? <ListRow icon={<LogoutIconMini />} label="退出登录" onClick={onLogout} last /> : null}
          </div>
        </div>
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
    <div className="relative min-h-dvh safe-bottom overflow-hidden bg-[#FDFDFD] text-gray-900">
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
          <div className="relative min-h-dvh overflow-y-auto pb-[80px]">
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
  onClick,
}: {
  label: string;
  text: string;
  onClick?: () => void;
}) {
  return (
    <button
      className="block w-full text-left active:opacity-80"
      onClick={onClick}
    >
      <div className="mb-2.5 flex items-center">
        <div className="mr-2 h-3 w-1 rounded-full bg-gray-200" />
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">{label}</h2>
      </div>
      <p className="whitespace-pre-wrap pl-3 text-[15px] font-light leading-relaxed text-gray-800">{text}</p>
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
    <div className="bg-white pb-8" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 56px)" }}>
      <div className="px-6">
        <h1 className="mb-8 text-[26px] font-medium tracking-tight text-gray-900">会话</h1>
        <div className="space-y-7">
          <SummaryBlock label="Today Note" text={dailyWhisper || "今天还没有新的 note。"} onClick={onOpenTodayNote} />
          <div className="ml-3 h-px w-full bg-gray-50" />
          <SummaryBlock label="日报摘要" text={reportSummary} onClick={onOpenDailyReport} />
        </div>
      </div>

      <div className="mt-8 h-3 bg-[#F8F9FA]" />

      <div className="bg-white">
        <ChatEntryRow
          title="渡"
          preview={duPreview}
          time={duTime}
          tone="du"
          onClick={onOpenDu}
          pinned
        />
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
  pinned,
  onClick,
}: {
  title: string;
  preview: string;
  time: string;
  tone: "du" | "wenyou";
  pinned?: boolean;
  onClick: () => void;
}) {
  const palette = tone === "wenyou"
    ? { shell: "bg-[#F8F0F4] text-[#704A5D]" }
    : { shell: "bg-[#F0F4F8] text-[#4A5568]" };
  return (
    <button className="flex w-full items-center px-6 py-4 text-left transition-colors active:bg-gray-50" onClick={onClick}>
      <div className="relative shrink-0">
        <div className={`flex h-[52px] w-[52px] items-center justify-center rounded-2xl text-[20px] font-medium shadow-sm ${palette.shell}`}>
          {title.slice(0, 1)}
        </div>
        {pinned ? (
          <div className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-gray-100 bg-white shadow-sm">
            <CornerDownIcon />
          </div>
        ) : null}
      </div>
      <div className={`ml-4 min-w-0 flex-1 pt-1 ${pinned ? "border-b border-gray-50 pb-4" : ""}`}>
        <div className="mb-1 flex items-baseline justify-between">
          <span className="text-[17px] font-medium text-gray-900">{title}</span>
          <span className="text-[12px] font-light text-gray-400">{time}</span>
        </div>
        <p className="truncate text-[14px] font-light text-gray-500">{preview}</p>
      </div>
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
    <nav className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between border-t border-gray-100 bg-white/90 px-6 pb-[calc(env(safe-area-inset-bottom,24px))] pt-2 backdrop-blur-md">
      <div className="mx-auto flex w-full max-w-xl items-center justify-between">
        {items.map((item) => {
          const active = current === item.id;
          return (
            <button
              key={item.id}
              className={`flex flex-col items-center p-2 transition-colors ${active ? "text-gray-900" : "text-gray-400 hover:text-gray-600"}`}
              onClick={() => onChange(item.id)}
            >
              <BottomNavIcon id={item.id} />
              <span className="text-[10px] font-medium tracking-wide">{item.label}</span>
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
    ? "bg-[#F8F0F4] text-[#704A5D]"
    : accent === "du"
      ? "bg-[#F0F4F8] text-[#4A5568]"
      : "bg-[#F4F5F7] text-[#5C6473]";
  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-[#FDFDFD]">
      <div className="absolute top-0 z-20 flex w-full items-center justify-between border-b border-gray-100/50 bg-white/80 px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)] backdrop-blur-md">
        <div className="flex items-center">
          <button className="rounded-full p-2 text-gray-500 transition-colors active:bg-gray-100" onClick={onBack}>
            <ChevronLeftIcon />
          </button>
          <div className={`ml-1 mr-3 flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium ${chipClass}`}>{title.slice(0, 1)}</div>
          <div className="text-[16px] font-medium text-gray-900">{title}</div>
        </div>
        <div className="w-10" />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-[88px]">{children}</div>
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
    ? "bg-[#F8F0F4] text-[#704A5D]"
    : "bg-[#F0F4F8] text-[#4A5568]";

  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-[#F8F9FA]">
      <div className="absolute top-0 z-20 flex w-full items-center justify-between border-b border-gray-100/50 bg-white/80 px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)] backdrop-blur-md">
        <div className="flex items-center">
          <button className="rounded-full p-2 text-gray-500 transition-colors active:bg-gray-100" onClick={onBack}>
            <ChevronLeftIcon />
          </button>
          <div className={`ml-1 mr-3 flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium ${avatarClass}`}>{avatarLabel}</div>
          <div className="text-[16px] font-medium text-gray-900">{title}</div>
        </div>
        <button className="rounded-full p-3 text-gray-500 transition-colors active:bg-gray-100" onClick={onOpenCall}>
          <PhoneIconMini />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-6 pt-[100px]">
        <div className="mb-2 flex justify-center">
          <span className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Today</span>
        </div>
        <div className="space-y-7">
          {messages.map((msg) => (
            msg.role === "user" ? (
              <div key={msg.id} className="flex items-start justify-end space-x-4">
                <div className="max-w-[75%] space-y-2">
                  <div className="rounded-[20px] rounded-tr-sm bg-[#2D3748] px-5 py-4 text-[15px] font-light leading-relaxed text-white shadow-sm">
                    {msg.content || (sending ? "…" : "")}
                  </div>
                </div>
                <div className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-full bg-gray-200 text-[14px] font-medium text-gray-600 shadow-sm">我</div>
              </div>
            ) : (
              <div key={msg.id} className="flex items-start space-x-4">
                <div className={`flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-full text-[14px] font-medium shadow-sm ${avatarClass}`}>{avatarLabel}</div>
                <div className="max-w-[75%] space-y-2">
                  <div className="rounded-[20px] rounded-tl-sm border border-gray-100/50 bg-white px-5 py-4 text-[15px] font-light leading-relaxed text-gray-800 shadow-sm">
                    {msg.content || (sending ? "…" : "")}
                  </div>
                </div>
              </div>
            )
          ))}
        </div>
      </div>

      <div className="z-20 border-t border-gray-100 bg-white pb-[calc(env(safe-area-inset-bottom,24px))]">
        <div className={`overflow-hidden bg-white transition-all duration-300 ease-in-out ${plusOpen ? "h-[140px] opacity-100" : "h-0 opacity-0"}`}>
          <div className="flex space-x-8 px-8 pb-2 pt-6">
              <ChatActionButton label="表情包" onClick={() => { setPlusOpen(false); onOpenStickers(); }} />
              <ChatActionButton label="通话" onClick={() => { setPlusOpen(false); onOpenCall(); }} />
          </div>
        </div>
        <div className="flex items-end space-x-2 px-3 py-3">
          <button
            className={`rounded-full p-2.5 text-gray-500 transition-colors ${plusOpen ? "bg-gray-100 text-gray-800" : "active:bg-gray-50"}`}
            onClick={() => setPlusOpen((v) => !v)}
          >
            <PlusIcon open={plusOpen} />
          </button>
          <div className="flex min-h-[42px] flex-1 items-center rounded-[20px] bg-[#F4F5F7] px-4 py-2.5">
            <input
              className="w-full bg-transparent text-[15px] font-light text-gray-900 outline-none placeholder:text-gray-400"
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
            className="p-2.5 text-gray-900 transition-opacity active:opacity-50 disabled:opacity-50"
            onClick={() => void sendMessage()}
            disabled={sending || !input.trim()}
          >
            <div className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-gray-900">
              <ArrowUpIcon />
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

function ChatActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button className="group flex flex-col items-center" onClick={onClick}>
      <div className="mb-2.5 flex h-[60px] w-[60px] items-center justify-center rounded-[20px] bg-[#F8F9FA] text-gray-600 transition-transform active:scale-95">
        {label === "表情包" ? <SmileIconMini /> : <PhoneIconLarge />}
      </div>
      <span className="text-[11px] font-medium tracking-wide text-gray-500">{label}</span>
    </button>
  );
}

function PageCardRow({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      className="flex w-full items-center rounded-[24px] border border-gray-100/60 bg-white p-5 text-left shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)] transition-transform active:scale-[0.98]"
      onClick={onClick}
    >
      <div className="mr-4 flex h-[42px] w-[42px] items-center justify-center rounded-full bg-gray-50 text-gray-600">
        {icon}
      </div>
      <span className="flex-1 text-[16px] font-medium tracking-wide text-gray-800">{label}</span>
      <ChevronRightIcon />
    </button>
  );
}

function ListRow({
  icon,
  label,
  onClick,
  last,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  last?: boolean;
}) {
  return (
    <button
      className={`flex min-h-[64px] w-full items-center px-6 py-[18px] text-left transition-colors active:bg-gray-50 ${last ? "" : "border-b border-gray-50"}`}
      onClick={onClick}
    >
      <span className="mr-4 text-gray-400">{icon}</span>
      <span className="flex-1 text-[16px] font-medium tracking-wide text-gray-800">{label}</span>
      <ChevronRightIcon />
    </button>
  );
}

function BottomNavIcon({ id }: { id: MainTab }) {
  const cls = "mb-1 h-[22px] w-[22px]";
  if (id === "chats") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8A8.5 8.5 0 0 1 12.5 3h.5a8.48 8.48 0 0 1 8 8z" /></svg>;
  if (id === "daily") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></svg>;
  if (id === "tools") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></svg>;
  return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c0 .66.39 1.26 1 1.51.17.07.35.1.54.1H21a2 2 0 0 1 0 4h-.09c-.19 0-.37.03-.54.1-.61.25-1 .85-1 1.51z" /></svg>;
}

function ChevronLeftIcon() {
  return <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>;
}

function ChevronRightIcon() {
  return <svg className="h-[18px] w-[18px] text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>;
}

function CornerDownIcon() {
  return <svg className="h-2.5 w-2.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="10 15 15 20 20 15" /><path d="M4 4h7a4 4 0 0 1 4 4v12" /></svg>;
}

function PlusIcon({ open }: { open: boolean }) {
  return (
    <svg className={`h-[22px] w-[22px] transition-transform duration-200 ${open ? "rotate-45" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function ArrowUpIcon() {
  return <svg className="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 19 7-7-7-7" transform="rotate(-90 12 12)" /></svg>;
}

function PhoneIconMini() {
  return <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.9.34 1.78.65 2.62a2 2 0 0 1-.45 2.11L8 9.91a16 16 0 0 0 6 6l1.46-1.31a2 2 0 0 1 2.11-.45c.84.31 1.72.53 2.62.65A2 2 0 0 1 22 16.92z" /></svg>;
}

function PhoneIconLarge() {
  return <svg className="h-7 w-7 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.9.34 1.78.65 2.62a2 2 0 0 1-.45 2.11L8 9.91a16 16 0 0 0 6 6l1.46-1.31a2 2 0 0 1 2.11-.45c.84.31 1.72.53 2.62.65A2 2 0 0 1 22 16.92z" /></svg>;
}

function SmileIconMini() {
  return <svg className="h-7 w-7 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2" /><line x1="9" y1="9" x2="9.01" y2="9" /><line x1="15" y1="9" x2="15.01" y2="9" /></svg>;
}

function FeatherIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.24 3.76a6 6 0 0 0-8.48 0L4 11.52V20h8.48l7.76-7.76a6 6 0 0 0 0-8.48z" /><line x1="16" y1="8" x2="2" y2="22" /><line x1="17.5" y1="15" x2="9" y2="15" /><line x1="13.5" y1="19" x2="9" y2="19" /></svg>;
}

function SunIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></svg>;
}

function ClockIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>;
}

function CalendarIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></svg>;
}

function FileTextIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" /></svg>;
}

function GitMergeIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="18" r="3" /><circle cx="6" cy="6" r="3" /><path d="M6 9v6a3 3 0 0 0 3 3h6" /><path d="M18 15V9a3 3 0 0 0-3-3H9" /></svg>;
}

function CpuIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2" /><rect x="9" y="9" width="6" height="6" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" /></svg>;
}

function BookOpenIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" /></svg>;
}

function CodeIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></svg>;
}

function ToggleRightIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="10" rx="5" ry="5" /><circle cx="16" cy="12" r="3" /></svg>;
}

function ShieldIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>;
}

function SmartphoneIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="7" y="2" width="10" height="20" rx="2" ry="2" /><line x1="12" y1="18" x2="12.01" y2="18" /></svg>;
}

function LogoutIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></svg>;
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
