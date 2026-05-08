import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import DOMPurify from "dompurify";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { ToastProvider, useToast } from "./toast";
import { apiJson, consumePendingPanelDeviceIdMigration, getOrCreatePanelDeviceId, getPanelDeviceLabel, getPanelToken, publicApiFetch, setPanelToken } from "./api";
import { Btn, Modal } from "./components";
import { DiagnosticsScreen } from "./DiagnosticsScreen";
import { DeviceManagerModal } from "./DeviceManagerModal";
import { FullScreenPane } from "./FullScreenPane";
import {
  CalendarEventCreatedBubble,
  SystemAlarmCreatedBubble,
  TravelFoodDetailBubble,
  TravelFoodDetailModal,
  TravelPlanFormBubble,
  TravelPlanFormModal,
  TravelPlanResultBubble,
  TravelPlanResultModal,
  TravelTransportDetailBubble,
  TravelTransportDetailModal,
  buildSystemAlarmCreatedCardContent,
  formatAlarmTime,
  type CalendarEventCreatedCard,
  type TravelFoodDetailCard,
  type TravelPlanFormCard,
  type TravelPlanResultCard,
  type TravelTransportDetailCard,
} from "./sumitalkSystemCards";
import {
  applyAssistantTerminalMessage,
  applyMessageById,
  buildBenbenGroupContext,
  buildCodexGroupRecentMessages,
  extractAssistantReasoning,
  extractAssistantReplyText,
  extractTokenCount,
  formatClockTime,
  getChatFontLabel,
  getChatSearchMatchId,
  groupChatMessages,
  pickBetterHistory,
  pickLatestDraftPreview,
  sanitizeHistoryMessages,
  type ChatDraftMessage,
  type ChatRole,
  type ChatSearchMatch,
} from "./chatMessages";
import {
  ArrowUpIcon,
  BookOpenIcon,
  BottomNavIcon,
  CalendarIconMini,
  ChevronDownMini,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpMini,
  ClockIconMini,
  CodeIcon,
  CopyIconMini,
  CornerDownIcon,
  CpuIcon,
  FeatherIcon,
  FileTextIcon,
  GitMergeIcon,
  HeartIconMini,
  HomeIconMini,
  LogoutIconMini,
  MuteIconMini,
  PhoneIconLarge,
  PlusIcon,
  RouteIconMini,
  SearchIconMini,
  SmileIconMini,
  SmartphoneIconMini,
  SunIconMini,
  ToggleRightIcon,
  TrashIconMini,
} from "./icons";
import { SumiOverlay } from "../plugins/sumi-overlay";
import { migrateLocalChatHistoryDevice, readLatestLocalChatHistory, readLocalChatHistory, writeLocalChatHistory } from "./storage/chatHistoryDb";

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
const PixelHomeTab = lazy(() => import("./tabs/PixelHomeTab").then((m) => ({ default: m.PixelHomeTab })));
const StayWithDuScreen = lazy(() => import("./tabs/StayWithDuScreen").then((m) => ({ default: m.StayWithDuScreen })));
const CoReadScreen = lazy(() => import("./tabs/CoReadScreen").then((m) => ({ default: m.CoReadScreen })));

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
type SilenceModeResponse = {
  ok?: boolean;
  enabled?: boolean;
  updated_at?: string;
  error?: string;
};
type MainTab = "chats" | "daily" | "tools" | "settings";
type ChatScreenId = "du" | "group" | "wenyou" | null;
type ChatFontKey = "yahei" | "system" | "pingfang";
type ChatTimeFormat = "hhmm" | "ampm";
type BubbleStyleKey = "default" | "soft" | "outline";
type SumiTalkChatJobCreateResponse = {
  ok?: boolean;
  job_id?: string;
  status?: string;
  response?: any;
  status_code?: number;
  error?: string;
};
type SumiTalkChatJobStatusResponse = {
  ok?: boolean;
  status?: "running" | "done" | "error";
  status_code?: number;
  response?: any;
  error?: string;
};
type CodexGroupChatTask = {
  id?: string;
  status?: "queued" | "running" | "done" | "error" | "cancelled";
  response?: string;
  error?: string;
};
type CodexGroupChatTaskResponse = {
  ok?: boolean;
  task?: CodexGroupChatTask | null;
  error?: string;
};

const TRANSPARENT_BUBBLE_CLASS =
  "bg-gradient-to-br from-white/40 via-white/20 to-white/5 border border-white/50 text-gray-800 shadow-[inset_0_1px_1px_rgba(255,255,255,0.4),0_4px_20px_rgba(0,0,0,0.05)] backdrop-blur-sm";
const SUMITALK_CHAT_JOB_POLL_MS = 1800;
const SUMITALK_CHAT_JOB_TIMEOUT_MS = 10 * 60 * 1000;
const CODEX_GROUP_CHAT_POLL_MS = 2200;
const CODEX_GROUP_CHAT_TIMEOUT_MS = 10 * 60 * 1000;

function waitMs(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function waitForSumiTalkChatJob(jobId: string): Promise<any> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < SUMITALK_CHAT_JOB_TIMEOUT_MS) {
    await waitMs(SUMITALK_CHAT_JOB_POLL_MS);
    const job = await apiJson<SumiTalkChatJobStatusResponse>(`/miniapp-api/sumitalk-chat-jobs/${encodeURIComponent(jobId)}`);
    if (job.status === "done") return job.response || {};
    if (job.status === "error") {
      const upstreamError = job.response?.error || job.response?.message || "";
      throw new Error(String(job.error || upstreamError || "渡回复失败"));
    }
    if (job.status !== "running") {
      throw new Error("任务状态异常");
    }
  }
  throw new Error("等待渡回复超时");
}

async function apiJsonWithTimeout<T>(path: string, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await apiJson<T>(path, { signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

async function waitForCodexGroupChatTask(taskId: string): Promise<CodexGroupChatTask> {
  const startedAt = Date.now();
  let lastError = "";
  while (Date.now() - startedAt < CODEX_GROUP_CHAT_TIMEOUT_MS) {
    await waitMs(CODEX_GROUP_CHAT_POLL_MS);
    let data: CodexGroupChatTaskResponse;
    try {
      data = await apiJsonWithTimeout<CodexGroupChatTaskResponse>(
        `/miniapp-api/codex-group-chat-tasks/${encodeURIComponent(taskId)}`,
        12000,
      );
    } catch (e: any) {
      lastError = e?.name === "AbortError" ? "任务状态查询超时" : String(e?.message || e);
      continue;
    }
    const task = data.task || {};
    if (task.status === "done") return task;
    if (task.status === "error" || task.status === "cancelled") {
      throw new Error(String(task.error || data.error || "笨笨回复失败"));
    }
  }
  throw new Error(lastError ? `等待笨笨回复超时：${lastError}` : "等待笨笨回复超时");
}

function readStoredBoolean(key: string, fallback = false): boolean {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return raw === "1";
  } catch {
    return fallback;
  }
}

function readStoredNumber(key: string, fallback: number): number {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    const text = String(raw).trim();
    if (!text) return fallback;
    const num = Number(text);
    return Number.isFinite(num) && num > 0 ? num : fallback;
  } catch {
    return fallback;
  }
}

function clampStoredNumber(value: number, min: number, max: number, fallback: number): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(min, Math.min(max, num));
}

function readStoredString<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const raw = String(localStorage.getItem(key) || "").trim() as T;
    return allowed.includes(raw) ? raw : fallback;
  } catch {
    return fallback;
  }
}

function resolveChatFontFamily(fontKey: ChatFontKey): string {
  if (fontKey === "system") return "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
  if (fontKey === "pingfang") return "'PingFang SC', 'Hiragino Sans GB', sans-serif";
  return "'Microsoft YaHei', sans-serif";
}

async function fileToDataUrl(file: File): Promise<string> {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

async function loadImageElement(src: string): Promise<HTMLImageElement> {
  return await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("图片加载失败"));
    img.src = src;
  });
}

async function buildAvatarDataUrl(file: File): Promise<string> {
  const src = await fileToDataUrl(file);
  const img = await loadImageElement(src);
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("图片处理失败");
  const minSide = Math.min(img.width, img.height);
  const sx = (img.width - minSide) / 2;
  const sy = (img.height - minSide) / 2;
  ctx.drawImage(img, sx, sy, minSide, minSide, 0, 0, size, size);
  return canvas.toDataURL("image/jpeg", 0.9);
}

async function buildBackgroundDataUrl(file: File): Promise<string> {
  const src = await fileToDataUrl(file);
  const img = await loadImageElement(src);
  const maxWidth = 1280;
  const scale = Math.min(1, maxWidth / img.width);
  const width = Math.max(1, Math.round(img.width * scale));
  const height = Math.max(1, Math.round(img.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("图片处理失败");
  ctx.drawImage(img, 0, 0, width, height);
  return canvas.toDataURL("image/jpeg", 0.82);
}

function formatTokenCountValue(value?: number): string {
  return value ? `${value}tokens` : "";
}

function getBubbleStyleLabel(style: BubbleStyleKey, role: "user" | "assistant"): string {
  if (style === "soft") return role === "user" ? "柔和填充" : "浅灰填充";
  if (style === "outline") return "描边";
  return "默认";
}

function resolveBubbleClass(role: "user" | "assistant", style: BubbleStyleKey): string {
  if (role === "user") {
    if (style === "soft") return "bg-[#475569] text-white";
    if (style === "outline") return "border border-[#CBD5E1] bg-white text-gray-900";
    return "bg-[#2D3748] text-white";
  }
  if (style === "soft") return "bg-[#F4F5F7] text-gray-800";
  if (style === "outline") return "border border-[#CBD5E1] bg-white text-gray-800";
  return "border border-gray-100/50 bg-white text-gray-800";
}

function ChatHeaderStatus({ sending }: { sending: boolean }) {
  if (!sending) {
    return <div className="text-[11px] font-medium text-gray-900">在线</div>;
  }
  return (
    <div className="flex items-center gap-1.5 text-[11px] font-medium text-[#5F6C7B]" aria-label="正在输入中">
      <span>正在输入中</span>
      <span className="inline-flex items-end gap-1">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="inline-block h-[4px] w-[4px] rounded-full bg-[#5F6C7B] animate-pulse"
            style={{
              animationDelay: `${index * 0.18}s`,
              animationDuration: "1s",
            }}
          />
        ))}
      </span>
    </div>
  );
}

function Shell({
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
  const toast = useToast();
  const [panel, setPanel] = useState<PanelId>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showCorePrompt, setShowCorePrompt] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showAlarm, setShowAlarm] = useState(false);
  const [showPersonalization, setShowPersonalization] = useState(false);
  const [showDuDay, setShowDuDay] = useState(false);
  const [showStayWithDu, setShowStayWithDu] = useState(false);
  const [showPixelHome, setShowPixelHome] = useState(false);
  const [showCoRead, setShowCoRead] = useState(false);
  const [showTree, setShowTree] = useState(false);
  const [showCallHub, setShowCallHub] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [mainTab, setMainTab] = useState<MainTab>("chats");
  const [activeScreen, setActiveScreen] = useState<ChatScreenId>(null);
  const [silenceModeEnabled, setSilenceModeEnabled] = useState(false);
  const [silenceModeSaving, setSilenceModeSaving] = useState(false);
  const [sharedChatWindowId, setSharedChatWindowId] = useState("");
  const [dailyWhisper, setDailyWhisper] = useState("");
  const [dailyReport, setDailyReport] = useState<DailyReport | null>(null);
  const [todayNoteRefreshing, setTodayNoteRefreshing] = useState(false);
  const [dailyRefreshing, setDailyRefreshing] = useState(false);
  const [tree, setTree] = useState<CyberTreeData | null>(null);
  const [deferHomeExtras, setDeferHomeExtras] = useState(false);
  const [floatingBallEnabled, setFloatingBallEnabled] = useState(true);
  const [transparentBubbleEnabled, setTransparentBubbleEnabled] = useState(() => readStoredBoolean("miniapp.ui.transparentBubble"));
  const [showChatAvatars, setShowChatAvatars] = useState(() => readStoredBoolean("miniapp.ui.showAvatars", true));
  const [chatContentFontSize, setChatContentFontSize] = useState(() =>
    clampStoredNumber(readStoredNumber("miniapp.ui.chatContentFontSize", 13), 12, 18, 13),
  );
  const [chatTitleFontSize, setChatTitleFontSize] = useState(() =>
    clampStoredNumber(readStoredNumber("miniapp.ui.chatTitleFontSize", 15), 14, 20, 15),
  );
  const [chatFontKey, setChatFontKey] = useState<ChatFontKey>(() =>
    readStoredString("miniapp.ui.chatFont", "yahei", ["yahei", "system", "pingfang"] as const),
  );
  const [showChatTimestamps, setShowChatTimestamps] = useState(() => readStoredBoolean("miniapp.ui.showTimestamps", true));
  const [chatTimeFormat, setChatTimeFormat] = useState<ChatTimeFormat>(() =>
    readStoredString("miniapp.ui.timeFormat", "hhmm", ["hhmm", "ampm"] as const),
  );
  const [showTokenCount, setShowTokenCount] = useState(() => readStoredBoolean("miniapp.ui.showTokens", true));
  const [expandReasoningByDefault, setExpandReasoningByDefault] = useState(() => readStoredBoolean("miniapp.ui.expandReasoning", false));
  const [chatBackgroundOpacity, setChatBackgroundOpacity] = useState(() =>
    clampStoredNumber(readStoredNumber("miniapp.ui.chatBackgroundOpacity", 100), 20, 100, 100),
  );
  const [userBubbleStyle, setUserBubbleStyle] = useState<BubbleStyleKey>(() =>
    readStoredString("miniapp.ui.userBubbleStyle", "default", ["default", "soft", "outline"] as const),
  );
  const [assistantBubbleStyle, setAssistantBubbleStyle] = useState<BubbleStyleKey>(() =>
    readStoredString("miniapp.ui.assistantBubbleStyle", "default", ["default", "soft", "outline"] as const),
  );
  const [myAvatarImage, setMyAvatarImage] = useState(() => {
    try {
      return localStorage.getItem("miniapp.ui.myAvatar") || "";
    } catch {
      return "";
    }
  });
  const [duAvatarImage, setDuAvatarImage] = useState(() => {
    try {
      return localStorage.getItem("miniapp.ui.duAvatar") || "";
    } catch {
      return "";
    }
  });
  const [chatBackgroundImage, setChatBackgroundImage] = useState(() => {
    try {
      return localStorage.getItem("miniapp.ui.chatBackgroundImage") || "";
    } catch {
      return "";
    }
  });
  const myAvatarInputRef = useRef<HTMLInputElement | null>(null);
  const duAvatarInputRef = useRef<HTMLInputElement | null>(null);
  const backgroundInputRef = useRef<HTMLInputElement | null>(null);
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
  const loadDailyWhisper = useCallback(
    async (forceRefresh = false) => {
      if (forceRefresh) setTodayNoteRefreshing(true);
      try {
        const path = forceRefresh ? "/miniapp-api/daily-whisper?refresh=1" : "/miniapp-api/daily-whisper";
        const j = await apiJson<{ ok?: boolean; text?: string; error?: string }>(path);
        if (!j?.ok) throw new Error(j?.error || "刷新失败");
        const text = (j?.text || "").toString().trim();
        if (text) setDailyWhisper(text);
        if (forceRefresh) toast("Today note 已刷新");
      } catch (e: any) {
        if (forceRefresh) toast(`Today note 刷新失败：${e?.message || e}`);
      } finally {
        if (forceRefresh) setTodayNoteRefreshing(false);
      }
    },
    [toast],
  );

  useEffect(() => {
    // 不强制全屏，保持 Telegram 默认的半屏/弹层体验。
    tgReady(false);
    applyTelegramThemeToHtmlClass();
    apiJson<{ ok?: boolean; window_id?: string }>("/miniapp-api/chat-window")
      .then((j) => {
        const wid = String(j?.window_id || "").trim();
        if (wid) setSharedChatWindowId(wid);
      })
      .catch(() => {});
    const timer = window.setTimeout(() => {
      setDeferHomeExtras(true);
    }, 320);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!deferHomeExtras) return;
    void loadDailyWhisper(false);
    loadDailyReport();
    loadTree();
  }, [deferHomeExtras, loadDailyWhisper]);

  useEffect(() => {
    if (mainTab !== "settings") return;
    let cancelled = false;
    void apiJson<SilenceModeResponse>("/miniapp-api/silence-mode")
      .then((j) => {
        if (!cancelled && j?.ok) setSilenceModeEnabled(!!j.enabled);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [mainTab]);

  useEffect(() => {
    if (mainTab !== "settings") return;
    if (Capacitor.getPlatform() !== "android") return;
    let cancelled = false;
    void SumiOverlay.getFloatingBallEnabled()
      .then((r) => {
        if (!cancelled) setFloatingBallEnabled(!!r.enabled);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [mainTab]);

  useEffect(() => {
    try {
      localStorage.setItem("miniapp.ui.transparentBubble", transparentBubbleEnabled ? "1" : "0");
      localStorage.setItem("miniapp.ui.showAvatars", showChatAvatars ? "1" : "0");
      localStorage.setItem("miniapp.ui.chatContentFontSize", String(chatContentFontSize));
      localStorage.setItem("miniapp.ui.chatTitleFontSize", String(chatTitleFontSize));
      localStorage.setItem("miniapp.ui.chatFont", chatFontKey);
      localStorage.setItem("miniapp.ui.showTimestamps", showChatTimestamps ? "1" : "0");
      localStorage.setItem("miniapp.ui.timeFormat", chatTimeFormat);
      localStorage.setItem("miniapp.ui.showTokens", showTokenCount ? "1" : "0");
      localStorage.setItem("miniapp.ui.expandReasoning", expandReasoningByDefault ? "1" : "0");
      localStorage.setItem("miniapp.ui.chatBackgroundOpacity", String(chatBackgroundOpacity));
      localStorage.setItem("miniapp.ui.userBubbleStyle", userBubbleStyle);
      localStorage.setItem("miniapp.ui.assistantBubbleStyle", assistantBubbleStyle);
      localStorage.setItem("miniapp.ui.myAvatar", myAvatarImage);
      localStorage.setItem("miniapp.ui.duAvatar", duAvatarImage);
      localStorage.setItem("miniapp.ui.chatBackgroundImage", chatBackgroundImage);
    } catch {}
  }, [
    transparentBubbleEnabled,
    showChatAvatars,
    chatContentFontSize,
    chatTitleFontSize,
    chatFontKey,
    showChatTimestamps,
    chatTimeFormat,
    showTokenCount,
    expandReasoningByDefault,
    chatBackgroundOpacity,
    userBubbleStyle,
    assistantBubbleStyle,
    myAvatarImage,
    duAvatarImage,
    chatBackgroundImage,
  ]);

  async function handleImageSelection(
    file: File | undefined,
    kind: "myAvatar" | "duAvatar" | "background",
  ) {
    if (!file) return;
    try {
      if (kind === "background") {
        setChatBackgroundImage(await buildBackgroundDataUrl(file));
        toast("聊天背景已更新");
        return;
      }
      const next = await buildAvatarDataUrl(file);
      if (kind === "myAvatar") {
        setMyAvatarImage(next);
        toast("我的头像已更新");
      } else {
        setDuAvatarImage(next);
        toast("渡的头像已更新");
      }
    } catch (e: any) {
      toast(`图片设置失败：${e?.message || e}`);
    }
  }

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

  async function setFloatingBallNative(next: boolean) {
    const prev = floatingBallEnabled;
    setFloatingBallEnabled(next);
    try {
      await SumiOverlay.setFloatingBallEnabled({ enabled: next });
    } catch (e: any) {
      setFloatingBallEnabled(prev);
      toast(`悬浮球设置失败：${e?.message || e}`);
    }
  }

  async function saveSilenceMode(next: boolean) {
    const prev = silenceModeEnabled;
    setSilenceModeEnabled(next);
    setSilenceModeSaving(true);
    try {
      const j = await apiJson<SilenceModeResponse>("/miniapp-api/silence-mode", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      setSilenceModeEnabled(!!j.enabled);
      toast(j.enabled ? "禁言模式已开启" : "禁言模式已关闭");
    } catch (e: any) {
      setSilenceModeEnabled(prev);
      toast(`禁言模式设置失败：${e?.message || e}`);
    } finally {
      setSilenceModeSaving(false);
    }
  }

  useEffect(() => {
    if (!showTree) return;
    loadTree();
    const timer = setInterval(() => loadTree(), 30000);
    return () => clearInterval(timer);
  }, [showTree]);

  useEffect(() => {
    let disposed = false;
    const removePromise = CapacitorApp.addListener("backButton", async () => {
      if (disposed) return;
      if (showCallHub) {
        setShowCallHub(false);
        return;
      }
      if (deviceManagerOpen && onCloseDevices) {
        onCloseDevices();
        return;
      }
      if (panel) {
        setPanel(null);
        return;
      }
      if (showSettings) {
        setShowSettings(false);
        return;
      }
      if (showCorePrompt) {
        setShowCorePrompt(false);
        return;
      }
      if (showSchedule) {
        setShowSchedule(false);
        return;
      }
      if (showAlarm) {
        setShowAlarm(false);
        return;
      }
      if (showPersonalization) {
        setShowPersonalization(false);
        return;
      }
      if (showDuDay) {
        setShowDuDay(false);
        return;
      }
      if (showStayWithDu) {
        setShowStayWithDu(false);
        return;
      }
      if (showPixelHome) {
        setShowPixelHome(false);
        return;
      }
      if (showCoRead) {
        setShowCoRead(false);
        return;
      }
      if (showTree) {
        setShowTree(false);
        return;
      }
      if (showDiagnostics) {
        setShowDiagnostics(false);
        return;
      }
      if (activeScreen) {
        setActiveScreen(null);
        return;
      }
      if (mainTab !== "chats") {
        setMainTab("chats");
        return;
      }
      await CapacitorApp.exitApp();
    });
    return () => {
      disposed = true;
      removePromise.then((handle) => handle.remove()).catch(() => {});
    };
  }, [
    activeScreen,
    deviceManagerOpen,
    mainTab,
    onCloseDevices,
    panel,
    showAlarm,
    showCallHub,
    showCorePrompt,
    showCoRead,
    showDuDay,
    showPixelHome,
    showPersonalization,
    showSchedule,
    showSettings,
    showStayWithDu,
    showTree,
    showDiagnostics,
  ]);

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
        <div className="bg-[#FDFDFD] px-4 pb-6" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 44px)" }}>
          <h1 className="mb-6 text-[22px] font-medium tracking-tight text-gray-900">日常</h1>
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
              icon={<HeartIconMini />}
              label="Stay with Du"
              onClick={() => setShowStayWithDu(true)}
            />
            <PageCardRow
              icon={<HomeIconMini />}
              label="像素小家"
              onClick={() => setShowPixelHome(true)}
            />
            <PageCardRow
              icon={<BookOpenIcon />}
              label="和渡一起读"
              onClick={() => setShowCoRead(true)}
            />
            <PageCardRow
              icon={<BookOpenIcon />}
              label="渡的记事本"
              onClick={() => setPanel("du-notebook")}
            />
          </div>
        </div>
      );
    }
    if (mainTab === "tools") {
      return (
        <div className="bg-[#FDFDFD] px-4 pb-6" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 44px)" }}>
          <h1 className="mb-6 text-[22px] font-medium tracking-tight text-gray-900">工具</h1>
          <div className="overflow-hidden rounded-[28px] border border-gray-100/60 bg-white shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <ListRow icon={<FileTextIcon />} label="日志" onClick={() => setPanel("logs")} />
            <ListRow icon={<GitMergeIcon />} label="思维链" onClick={() => setPanel("reasoning")} />
            <ListRow icon={<CpuIcon />} label="记忆调试" onClick={() => setPanel("memory-debug")} />
            <ListRow icon={<ClockIconMini />} label="闹钟" onClick={() => setShowAlarm(true)} />
            <ListRow icon={<CalendarIconMini />} label="日历" onClick={() => setShowSchedule(true)} />
            <ListRow icon={<CodeIcon />} label="核心 Prompt" onClick={() => setShowCorePrompt(true)} />
            <ListRow icon={<ToggleRightIcon />} label="上游切换" onClick={() => setShowSettings(true)} last />
          </div>
        </div>
      );
    }
    if (mainTab === "settings") {
      return (
        <div className="bg-[#FDFDFD] px-4 pb-6" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 44px)" }}>
          <h1 className="mb-6 text-[22px] font-medium tracking-tight text-gray-900">设置</h1>
          <div className="overflow-hidden rounded-[28px] border border-gray-100/60 bg-white shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            {Capacitor.getPlatform() === "android" ? (
              <FloatingBallSettingRow enabled={floatingBallEnabled} onToggle={(v) => void setFloatingBallNative(v)} />
            ) : null}
            <SwitchSettingRow
              icon={<MuteIconMini />}
              label="禁言模式"
              enabled={silenceModeEnabled}
              disabled={silenceModeSaving}
              onToggle={(v) => void saveSilenceMode(v)}
            />
            <ListRow icon={<FeatherIcon />} label="个性化" onClick={() => setShowPersonalization(true)} />
            <ListRow icon={<CpuIcon />} label="系统诊断" onClick={() => setShowDiagnostics(true)} />
            <ListRow icon={<SmartphoneIconMini />} label="设备管理" onClick={() => onOpenDevices?.()} />
            {onLogout ? <ListRow icon={<LogoutIconMini />} label="退出登录" onClick={onLogout} last /> : null}
          </div>
        </div>
      );
    }
    return (
      <ChatsHome
        dailyWhisper={dailyWhisper}
        dailyReport={dailyReport}
        duAvatarImage={duAvatarImage}
        onOpenDu={() => setActiveScreen("du")}
        onOpenGroup={() => setActiveScreen("group")}
        onOpenWenyou={() => setActiveScreen("wenyou")}
        onRefreshTodayNote={() => {
          if (!todayNoteRefreshing) void loadDailyWhisper(true);
        }}
        onRefreshDailyReport={refreshDailyReport}
        todayNoteRefreshing={todayNoteRefreshing}
        dailyRefreshing={dailyRefreshing}
      />
    );
  };

  const hasSecondaryPageOpen =
    !!activeScreen ||
    !!deviceManagerOpen ||
    !!panel ||
    showSettings ||
    showCorePrompt ||
    showSchedule ||
    showAlarm ||
    showPersonalization ||
    showDuDay ||
    showStayWithDu ||
    showPixelHome ||
    showCoRead ||
    showTree ||
    showDiagnostics ||
    showCallHub;

  return (
    <div className="relative min-h-dvh safe-bottom overflow-hidden bg-[#FDFDFD] text-gray-900">
      {activeScreen === "du" ? (
        <MainChatScreen
          title="渡"
          windowId={sharedChatWindowId}
          avatarLabel="渡"
          accent="du"
          transparentBubbleEnabled={transparentBubbleEnabled}
          showChatAvatars={showChatAvatars}
          chatContentFontSize={chatContentFontSize}
          chatTitleFontSize={chatTitleFontSize}
          chatFontFamily={resolveChatFontFamily(chatFontKey)}
          showChatTimestamps={showChatTimestamps}
          chatTimeFormat={chatTimeFormat}
          showTokenCount={showTokenCount}
          expandReasoningByDefault={expandReasoningByDefault}
          chatBackgroundOpacity={chatBackgroundOpacity}
          userBubbleStyle={userBubbleStyle}
          assistantBubbleStyle={assistantBubbleStyle}
          myAvatarImage={myAvatarImage}
          duAvatarImage={duAvatarImage}
          chatBackgroundImage={chatBackgroundImage}
          onBack={() => setActiveScreen(null)}
          onOpenStickers={() => setPanel("stickers")}
          onOpenCall={() => setShowCallHub(true)}
        />
      ) : null}
      {activeScreen === "group" ? (
        <MainChatScreen
          title="三人群聊"
          windowId={sharedChatWindowId}
          groupChatMode
          avatarLabel="渡"
          accent="du"
          transparentBubbleEnabled={transparentBubbleEnabled}
          showChatAvatars={showChatAvatars}
          chatContentFontSize={chatContentFontSize}
          chatTitleFontSize={chatTitleFontSize}
          chatFontFamily={resolveChatFontFamily(chatFontKey)}
          showChatTimestamps={showChatTimestamps}
          chatTimeFormat={chatTimeFormat}
          showTokenCount={showTokenCount}
          expandReasoningByDefault={expandReasoningByDefault}
          chatBackgroundOpacity={chatBackgroundOpacity}
          userBubbleStyle={userBubbleStyle}
          assistantBubbleStyle={assistantBubbleStyle}
          myAvatarImage={myAvatarImage}
          duAvatarImage={duAvatarImage}
          chatBackgroundImage={chatBackgroundImage}
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
          <div className="relative min-h-dvh overflow-y-auto pb-[76px]">
            {renderMainTab()}
          </div>
          {!hasSecondaryPageOpen ? <BottomNav current={mainTab} onChange={setMainTab} /> : null}
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
        <FullScreenPane title="闹钟" accent="neutral" headerMode="simple" onBack={() => setShowAlarm(false)}>
          <LazyPane><AlarmTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showPersonalization ? (
        <FullScreenPane title="个性化" accent="neutral" headerMode="simple" onBack={() => setShowPersonalization(false)}>
          <PersonalizationScreen
            transparentBubbleEnabled={transparentBubbleEnabled}
            onToggleTransparentBubble={setTransparentBubbleEnabled}
            showChatAvatars={showChatAvatars}
            onToggleShowChatAvatars={setShowChatAvatars}
            chatContentFontSize={chatContentFontSize}
            onChangeChatContentFontSize={setChatContentFontSize}
            chatTitleFontSize={chatTitleFontSize}
            onChangeChatTitleFontSize={setChatTitleFontSize}
            chatFontKey={chatFontKey}
            onCycleChatFont={() => setChatFontKey((prev) => (prev === "yahei" ? "system" : prev === "system" ? "pingfang" : "yahei"))}
            showChatTimestamps={showChatTimestamps}
            onToggleShowChatTimestamps={setShowChatTimestamps}
            chatTimeFormat={chatTimeFormat}
            onCycleChatTimeFormat={() => setChatTimeFormat((prev) => (prev === "hhmm" ? "ampm" : "hhmm"))}
            showTokenCount={showTokenCount}
            onToggleShowTokenCount={setShowTokenCount}
            expandReasoningByDefault={expandReasoningByDefault}
            onToggleExpandReasoningByDefault={setExpandReasoningByDefault}
            chatBackgroundOpacity={chatBackgroundOpacity}
            onChangeChatBackgroundOpacity={setChatBackgroundOpacity}
            userBubbleStyle={userBubbleStyle}
            onCycleUserBubbleStyle={() => setUserBubbleStyle((prev) => (prev === "default" ? "soft" : prev === "soft" ? "outline" : "default"))}
            assistantBubbleStyle={assistantBubbleStyle}
            onCycleAssistantBubbleStyle={() => setAssistantBubbleStyle((prev) => (prev === "default" ? "soft" : prev === "soft" ? "outline" : "default"))}
            myAvatarImage={myAvatarImage}
            duAvatarImage={duAvatarImage}
            chatBackgroundImage={chatBackgroundImage}
            onPickMyAvatar={() => myAvatarInputRef.current?.click()}
            onPickDuAvatar={() => duAvatarInputRef.current?.click()}
            onPickChatBackground={() => backgroundInputRef.current?.click()}
          />
        </FullScreenPane>
      ) : null}
      {showDuDay ? (
        <FullScreenPane title="渡的一天" accent="neutral" headerMode="simple" onBack={() => setShowDuDay(false)}>
          <LazyPane><DuDayTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showStayWithDu ? (
        <FullScreenPane title="Stay with Du" accent="neutral" headerMode="simple" onBack={() => setShowStayWithDu(false)}>
          <LazyPane><StayWithDuScreen /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showPixelHome ? (
        <FullScreenPane title="像素小家" accent="neutral" headerMode="simple" edgeSwipeBack onBack={() => setShowPixelHome(false)}>
          <LazyPane><PixelHomeTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showCoRead ? <LazyPane><CoReadScreen onBack={() => setShowCoRead(false)} windowId={sharedChatWindowId} /></LazyPane> : null}
      {showTree ? (
        <FullScreenPane title="树" accent="neutral" onBack={() => setShowTree(false)}>
          <TreeScreen data={tree} onRefresh={loadTree} />
        </FullScreenPane>
      ) : null}
      {showDiagnostics ? (
        <FullScreenPane title="系统诊断" accent="neutral" headerMode="simple" onBack={() => setShowDiagnostics(false)}>
          <DiagnosticsScreen />
        </FullScreenPane>
      ) : null}
      {showCallHub ? <LazyPane><CallHubScreen onClose={() => setShowCallHub(false)} /></LazyPane> : null}
      <input
        ref={myAvatarInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          void handleImageSelection(e.target.files?.[0], "myAvatar");
          e.currentTarget.value = "";
        }}
      />
      <input
        ref={duAvatarInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          void handleImageSelection(e.target.files?.[0], "duAvatar");
          e.currentTarget.value = "";
        }}
      />
      <input
        ref={backgroundInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          void handleImageSelection(e.target.files?.[0], "background");
          e.currentTarget.value = "";
        }}
      />
    </div>
  );
}


function RichTextBlock({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="m-0 whitespace-pre-wrap">{children}</p>,
        h1: ({ children }) => <h1 className="mb-2 text-[20px] font-semibold leading-tight text-gray-900">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-2 text-[18px] font-semibold leading-tight text-gray-900">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1.5 text-[16px] font-semibold leading-tight text-gray-900">{children}</h3>,
        ul: ({ children }) => <ul className="my-2 list-disc pl-5">{children}</ul>,
        ol: ({ children }) => <ol className="my-2 list-decimal pl-5">{children}</ol>,
        li: ({ children }) => <li className="my-0.5">{children}</li>,
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto">
            <table className="min-w-full border-collapse text-left text-[12px] leading-6 text-gray-800">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="bg-black/5">{children}</thead>,
        tbody: ({ children }) => <tbody>{children}</tbody>,
        tr: ({ children }) => <tr className="border-b border-black/10 last:border-b-0">{children}</tr>,
        th: ({ children }) => <th className="px-2.5 py-2 font-semibold text-gray-900">{children}</th>,
        td: ({ children }) => <td className="px-2.5 py-2 align-top">{children}</td>,
        pre: ({ children }) => <pre className="my-2 overflow-x-auto rounded-[12px] bg-black/5 p-3 text-[13px]">{children}</pre>,
        code: ({ children, ...props }) => {
          const inline = !String(props.className || "").includes("language-");
          return inline ? <code className="rounded bg-black/5 px-1.5 py-0.5 text-[13px]">{children}</code> : <code>{children}</code>;
        },
        blockquote: ({ children }) => <blockquote className="my-2 border-l-2 border-black/10 pl-3 opacity-80">{children}</blockquote>,
        a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" className="underline">{children}</a>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function HtmlBlock({ content }: { content: string }) {
  const sanitized = DOMPurify.sanitize(content);
  return <div className="w-full" dangerouslySetInnerHTML={{ __html: sanitized }} />;
}

function PlainTextBlock({ content }: { content: string }) {
  return <span className="whitespace-pre-wrap">{content}</span>;
}

function copyText(text: string, toast: (msg: string) => void) {
  const value = String(text || "").trim();
  if (!value) return;
  navigator.clipboard.writeText(value).then(
    () => toast("已复制"),
    () => toast("复制失败"),
  );
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
        <h2 className="text-[10px] font-semibold uppercase tracking-widest text-gray-900">{label}</h2>
      </div>
      <p className="whitespace-pre-wrap pl-3 text-[13px] font-normal leading-relaxed text-gray-800">{text}</p>
    </button>
  );
}

function ChatsHome({
  dailyWhisper,
  dailyReport,
  duAvatarImage,
  onOpenDu,
  onOpenGroup,
  onOpenWenyou,
  onRefreshTodayNote,
  onRefreshDailyReport,
  todayNoteRefreshing,
  dailyRefreshing,
}: {
  dailyWhisper: string;
  dailyReport: DailyReport | null;
  duAvatarImage: string;
  onOpenDu: () => void;
  onOpenGroup: () => void;
  onOpenWenyou: () => void;
  onRefreshTodayNote: () => void;
  onRefreshDailyReport: () => void;
  todayNoteRefreshing: boolean;
  dailyRefreshing: boolean;
}) {
  const [duPreview, setDuPreview] = useState("主会话");
  const [duTime, setDuTime] = useState("主会话");
  const [wenyouPreview, setWenyouPreview] = useState("独立文游会话");
  const [wenyouTime, setWenyouTime] = useState("独立会话");

  const reportSummary = dailyReport
    ? `聊了 ${String(dailyReport.rounds || 0)} 轮 · ${Array.isArray(dailyReport.keywords) && dailyReport.keywords.length ? dailyReport.keywords.join(" / ") : "暂无关键词"}`
    : "今天的日报还没生成。";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const did = await getOrCreatePanelDeviceId();
        const localMessages = sanitizeHistoryMessages(await readLatestLocalChatHistory(did));
        if (!cancelled && localMessages.length) {
          const pickedLocal = pickLatestDraftPreview(localMessages);
          setDuPreview(pickedLocal.preview);
          setDuTime(pickedLocal.time);
        }
        const j = await apiJson<{ ok?: boolean; messages?: ChatDraftMessage[] }>("/miniapp-api/sumitalk-history");
        if (cancelled) return;
        const remoteMessages = sanitizeHistoryMessages(Array.isArray(j?.messages) ? j.messages : []);
        const nextMessages = pickBetterHistory(remoteMessages, localMessages, []);
        const picked = pickLatestDraftPreview(nextMessages);
        setDuPreview(picked.preview);
        setDuTime(picked.time);
        if (nextMessages === remoteMessages && remoteMessages.length) {
          await writeLocalChatHistory(did, "sumitalk-main", remoteMessages);
        }
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
    <div
      className="bg-white pb-8"
      style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 44px)", fontFamily: "'Microsoft YaHei', sans-serif" }}
    >
      <div className="px-4">
        <h1 className="mb-6 text-[22px] font-medium tracking-tight text-gray-900">会话</h1>
        <div className="space-y-5">
          <SummaryBlock
            label="Today Note"
            text={todayNoteRefreshing ? "正在刷新..." : dailyWhisper || "今天还没有新的 note。"}
            onClick={onRefreshTodayNote}
          />
          <div className="ml-3 h-px w-full bg-gray-50" />
          <SummaryBlock
            label="日报摘要"
            text={dailyRefreshing ? "正在刷新..." : reportSummary}
            onClick={onRefreshDailyReport}
          />
        </div>
      </div>

      <div className="mt-6 h-2 bg-[#F8F9FA]" />

      <div className="bg-white">
        <ChatEntryRow
          title="渡"
          preview={duPreview}
          time={duTime}
          tone="du"
          avatarImage={duAvatarImage}
          onClick={onOpenDu}
          pinned
        />
        <ChatEntryRow
          title="三人群聊"
          preview={duPreview}
          time={duTime}
          tone="group"
          onClick={onOpenGroup}
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
  avatarImage,
  pinned,
  onClick,
}: {
  title: string;
  preview: string;
  time: string;
  tone: "du" | "group" | "wenyou";
  avatarImage?: string;
  pinned?: boolean;
  onClick: () => void;
}) {
  const palette = tone === "wenyou"
    ? { shell: "bg-[#F8F0F4] text-[#704A5D]" }
    : tone === "group"
      ? { shell: "bg-[#FFF3D7] text-[#8A5A10]" }
      : { shell: "bg-[#F0F4F8] text-[#4A5568]" };
  return (
    <button className="flex w-full items-center px-4 py-3.5 text-left transition-colors active:bg-gray-50" onClick={onClick}>
      <div className="relative shrink-0">
        {avatarImage ? (
          <div className="h-[48px] w-[48px] overflow-hidden rounded-2xl shadow-sm">
            <img src={avatarImage} alt={title} className="h-full w-full object-cover" />
          </div>
        ) : (
          <div className={`flex h-[48px] w-[48px] items-center justify-center rounded-2xl text-[18px] font-medium shadow-sm ${palette.shell}`}>
            {title.slice(0, 1)}
          </div>
        )}
        {pinned ? (
          <div className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-gray-100 bg-white shadow-sm">
            <CornerDownIcon />
          </div>
        ) : null}
      </div>
      <div className={`ml-3 min-w-0 flex-1 pt-0.5 ${pinned ? "border-b border-gray-50 pb-3.5" : ""}`}>
        <div className="mb-1 flex items-baseline justify-between">
          <span className="text-[16px] font-medium text-gray-900">{title}</span>
          <span className="text-[11px] font-normal text-gray-900">{time}</span>
        </div>
        <p className="truncate text-[13px] font-normal text-gray-600">{preview}</p>
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
    <nav className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between border-t border-gray-100 bg-white/90 px-4 pb-[calc(env(safe-area-inset-bottom,20px))] pt-2 backdrop-blur-md">
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

function MainChatScreen({
  title,
  avatarLabel,
  windowId,
  groupChatMode = false,
  accent,
  transparentBubbleEnabled,
  showChatAvatars,
  chatContentFontSize,
  chatTitleFontSize,
  chatFontFamily,
  showChatTimestamps,
  chatTimeFormat,
  showTokenCount,
  expandReasoningByDefault,
  chatBackgroundOpacity,
  userBubbleStyle,
  assistantBubbleStyle,
  myAvatarImage,
  duAvatarImage,
  chatBackgroundImage,
  onBack,
  onOpenStickers,
  onOpenCall,
}: {
  title: string;
  avatarLabel: string;
  windowId: string;
  groupChatMode?: boolean;
  accent: "du" | "wenyou";
  transparentBubbleEnabled: boolean;
  showChatAvatars: boolean;
  chatContentFontSize: number;
  chatTitleFontSize: number;
  chatFontFamily: string;
  showChatTimestamps: boolean;
  chatTimeFormat: ChatTimeFormat;
  showTokenCount: boolean;
  expandReasoningByDefault: boolean;
  chatBackgroundOpacity: number;
  userBubbleStyle: BubbleStyleKey;
  assistantBubbleStyle: BubbleStyleKey;
  myAvatarImage: string;
  duAvatarImage: string;
  chatBackgroundImage: string;
  onBack: () => void;
  onOpenStickers: () => void;
  onOpenCall: () => void;
}) {
  const toast = useToast();
  const modelKey = `miniapp.chat.${windowId}.model.v1`;
  const [deviceId, setDeviceId] = useState("");
  const remoteHistoryReadyRef = useRef(false);
  const remoteHistoryWarningShownRef = useRef(false);
  const seedMessages: ChatDraftMessage[] = [
    {
      id: "seed-1",
      role: "assistant",
      content: groupChatMode ? "三人群聊开着。你直接说就好。" : "我在。你直接说就好。",
      createdAt: new Date().toISOString(),
    },
  ];
  const [messages, setMessages] = useState<ChatDraftMessage[]>(seedMessages);
  const messagesRef = useRef<ChatDraftMessage[]>(seedMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [travelFormCard, setTravelFormCard] = useState<TravelPlanFormCard | null>(null);
  const [travelResultCard, setTravelResultCard] = useState<TravelPlanResultCard | null>(null);
  const [travelTransportCard, setTravelTransportCard] = useState<TravelTransportDetailCard | null>(null);
  const [travelFoodCard, setTravelFoodCard] = useState<TravelFoodDetailCard | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);
  const messagesScrollRef = useRef<HTMLDivElement | null>(null);
  const searchResultRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const [activeModel, setActiveModel] = useState(() => {
    try {
      return (localStorage.getItem(modelKey) || "").trim();
    } catch {
      return "";
    }
  });
  const benbenTaskRecoveringRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

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

  useEffect(() => {
    let cancelled = false;
    const retryTimers: number[] = [];
    (async () => {
      const syncDeviceId = async () => {
        try {
          const did = await getOrCreatePanelDeviceId();
          const migration = consumePendingPanelDeviceIdMigration();
          if (migration?.from && migration.to === did) {
            await migrateLocalChatHistoryDevice(migration.from, migration.to);
            try {
              await apiJson("/miniapp-api/sumitalk-history/migrate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_device_id: migration.to }),
              });
            } catch {}
          }
          if (!cancelled) {
            setDeviceId((prev) => (prev === did ? prev : did));
          }
        } catch {}
      };
      void syncDeviceId();
      [800, 2200, 4500].forEach((delay) => {
        retryTimers.push(window.setTimeout(() => void syncDeviceId(), delay));
      });
    })();
    return () => {
      cancelled = true;
      retryTimers.forEach((id) => window.clearTimeout(id));
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (!deviceId || !windowId) return;
        remoteHistoryReadyRef.current = false;
        remoteHistoryWarningShownRef.current = false;
        const localMessages = sanitizeHistoryMessages(await readLocalChatHistory(deviceId, windowId));
        const fallbackLocalMessages = localMessages.length
          ? localMessages
          : sanitizeHistoryMessages(await readLatestLocalChatHistory(deviceId));
        if (!cancelled && fallbackLocalMessages.length) {
          setMessages(fallbackLocalMessages);
        }
        const j = await apiJson<{ ok?: boolean; messages?: ChatDraftMessage[] }>("/miniapp-api/sumitalk-history");
        if (cancelled) return;
        if (j?.ok) {
          remoteHistoryReadyRef.current = true;
        }
        const remoteMessages = sanitizeHistoryMessages(Array.isArray(j?.messages) ? j.messages : []);
        const next = pickBetterHistory(remoteMessages, fallbackLocalMessages, seedMessages);
        setMessages(next);
        if (next === remoteMessages && remoteMessages.length) {
          await writeLocalChatHistory(deviceId, windowId, remoteMessages);
        }
      } catch (e: any) {
        if (!cancelled) {
          toast(`聊天记录拉取失败：${e?.message || e}`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [deviceId, windowId]);

  async function saveDisplayHistory(
    nextMessages: ChatDraftMessage[],
    options: { syncRemote?: boolean; localDeviceId?: string } = {},
  ) {
    const sanitizedMessages = sanitizeHistoryMessages(nextMessages);
    const resolvedDeviceId = String(options.localDeviceId || deviceId || "").trim();
    const syncRemote = options.syncRemote !== false;
    if (resolvedDeviceId && windowId) {
      await writeLocalChatHistory(resolvedDeviceId, windowId, sanitizedMessages);
    }
    if (!syncRemote) return;
    if (!remoteHistoryReadyRef.current) {
      if (!remoteHistoryWarningShownRef.current) {
        remoteHistoryWarningShownRef.current = true;
        toast("当前未拉到服务器历史，已仅保存到本地，避免覆盖云端记录");
      }
      return;
    }
    try {
      await apiJson("/miniapp-api/sumitalk-history", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: sanitizedMessages }),
      });
    } catch {}
  }

  async function appendSystemAlarmCreatedCard(detail: { hour?: number; minute?: number; title?: string }) {
    if (groupChatMode) return;
    const cardContent = buildSystemAlarmCreatedCardContent(detail);
    const now = Date.now();
    const nextMessages = [
      ...messagesRef.current,
      {
        id: `system-alarm-${now}`,
        role: "assistant" as const,
        content: cardContent,
        createdAt: new Date(now).toISOString(),
        status: "sent" as const,
      },
    ];
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    await saveDisplayHistory(nextMessages);
  }

  useEffect(() => {
    const onAlarmCreated = (event: Event) => {
      const detail = (event as CustomEvent)?.detail || {};
      if (!detail?.ok) return;
      void appendSystemAlarmCreatedCard(detail);
    };
    window.addEventListener("sumitalk-system-alarm-created", onAlarmCreated as EventListener);
    return () => {
      window.removeEventListener("sumitalk-system-alarm-created", onAlarmCreated as EventListener);
    };
  }, [deviceId, windowId]);

  async function requestBenbenGroupReply(params: {
    baseMessages: ChatDraftMessage[];
    userContent: string;
    duReply: string;
    replyTarget: string;
    clientRequestId: string;
    placeholderId?: string;
    placeholderCreatedAt?: string;
  }): Promise<ChatDraftMessage[]> {
    const createdAtMs = Date.now();
    const benbenId = params.placeholderId || `benben-${createdAtMs}`;
    const benbenCreatedAt = params.placeholderCreatedAt || new Date(createdAtMs).toISOString();
    const pendingMsg: ChatDraftMessage = {
      id: benbenId,
      role: "benben",
      content: "笨笨正在看群聊...",
      createdAt: benbenCreatedAt,
      status: "pending",
      clientRequestId: `${params.clientRequestId}-benben`,
    };
    const pendingMessages = params.placeholderId
      ? applyMessageById(params.baseMessages, params.placeholderId, pendingMsg)
      : [...params.baseMessages, pendingMsg];
    messagesRef.current = pendingMessages;
    setMessages(pendingMessages);
    await saveDisplayHistory(pendingMessages, { syncRemote: false, localDeviceId: params.replyTarget });
    try {
      const created = await apiJson<CodexGroupChatTaskResponse>("/miniapp-api/codex-group-chat-tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          window_id: windowId,
          reply_target: params.replyTarget,
          user_message: params.userContent,
          du_reply: params.duReply,
          recent_messages: buildCodexGroupRecentMessages(params.baseMessages),
          client_request_id: `${params.clientRequestId}-benben`,
        }),
      });
      const taskId = String(created.task?.id || "").trim();
      if (!taskId) throw new Error(created.error || "笨笨任务没有返回 ID");
      const queuedMessages = applyMessageById(messagesRef.current, benbenId, {
        ...pendingMsg,
        content: "笨笨任务已创建，等我一下...",
        status: "pending",
        jobId: taskId,
      });
      messagesRef.current = queuedMessages;
      setMessages(queuedMessages);
      await saveDisplayHistory(queuedMessages, { syncRemote: false, localDeviceId: params.replyTarget });
      const task = await waitForCodexGroupChatTask(taskId);
      const reply = String(task.response || "").trim();
      if (!reply) throw new Error("笨笨没有返回内容");
      const finalMessages = applyMessageById(messagesRef.current, benbenId, {
        ...pendingMsg,
        content: reply,
        status: "sent",
        jobId: taskId,
      });
      messagesRef.current = finalMessages;
      setMessages(finalMessages);
      await saveDisplayHistory(finalMessages, { localDeviceId: params.replyTarget });
      return finalMessages;
    } catch (e: any) {
      const failedMessages = applyMessageById(messagesRef.current, benbenId, {
        ...pendingMsg,
        content: `（笨笨入群失败：${e?.message || e}）`,
        status: "failed",
      });
      messagesRef.current = failedMessages;
      setMessages(failedMessages);
      await saveDisplayHistory(failedMessages, { localDeviceId: params.replyTarget });
      toast(`笨笨入群失败：${e?.message || e}`);
      return failedMessages;
    }
  }

  useEffect(() => {
    if (!groupChatMode) return;
    const pendingBenbenTasks = messagesRef.current
      .filter((msg) => msg.role === "benben" && msg.status === "pending" && String(msg.jobId || "").trim())
      .map((msg) => ({
        messageId: msg.id,
        taskId: String(msg.jobId || "").trim(),
      }));
    for (const item of pendingBenbenTasks) {
      if (benbenTaskRecoveringRef.current.has(item.taskId)) continue;
      benbenTaskRecoveringRef.current.add(item.taskId);
      void (async () => {
        try {
          const task = await waitForCodexGroupChatTask(item.taskId);
          const reply = String(task.response || "").trim();
          if (!reply) throw new Error("笨笨没有返回内容");
          const finalMessages = applyMessageById(messagesRef.current, item.messageId, {
            id: item.messageId,
            role: "benben",
            content: reply,
            createdAt: messagesRef.current.find((msg) => msg.id === item.messageId)?.createdAt || new Date().toISOString(),
            status: "sent",
            jobId: item.taskId,
          });
          messagesRef.current = finalMessages;
          setMessages(finalMessages);
          await saveDisplayHistory(finalMessages, { localDeviceId: deviceId });
        } catch (e: any) {
          const failedMessages = applyMessageById(messagesRef.current, item.messageId, {
            id: item.messageId,
            role: "benben",
            content: `（笨笨入群失败：${e?.message || e}）`,
            createdAt: messagesRef.current.find((msg) => msg.id === item.messageId)?.createdAt || new Date().toISOString(),
            status: "failed",
            jobId: item.taskId,
          });
          messagesRef.current = failedMessages;
          setMessages(failedMessages);
          await saveDisplayHistory(failedMessages, { localDeviceId: deviceId });
        } finally {
          benbenTaskRecoveringRef.current.delete(item.taskId);
        }
      })();
    }
  }, [messages, groupChatMode, deviceId]);

  async function sendChatContent(rawContent: string, options: { displayContent?: string } = {}) {
    const content = String(rawContent || "").trim();
    if (!content || sending) return;
    const displayContent = String(options.displayContent || content).trim() || content;
    if (!windowId) {
      toast("当前还没拿到聊天窗口 ID，不能接入共享上下文");
      return;
    }
    if (!activeModel) {
      toast("当前还没拿到可用模型，稍后再试");
      return;
    }
    const resolvedDeviceId = String(deviceId || await getOrCreatePanelDeviceId()).trim();
    if (resolvedDeviceId && resolvedDeviceId !== deviceId) {
      setDeviceId((prev) => (prev === resolvedDeviceId ? prev : resolvedDeviceId));
    }
    const baseTimestamp = Date.now();
    const clientRequestId = `sumitalk-${baseTimestamp}-${Math.random().toString(36).slice(2, 10)}`;
    const userMsg: ChatDraftMessage = {
      id: `user-${baseTimestamp}`,
      role: "user",
      content: displayContent,
      createdAt: new Date(baseTimestamp).toISOString(),
      status: "sent",
      clientRequestId,
    };
    const assistantId = `assistant-${baseTimestamp + 1}`;
    const assistantCreatedAt = new Date(baseTimestamp + 1).toISOString();
    const benbenPlaceholderId = groupChatMode ? `benben-${baseTimestamp + 2}` : "";
    const benbenPlaceholderCreatedAt = groupChatMode ? new Date(baseTimestamp + 2).toISOString() : "";
    const benbenPlaceholder: ChatDraftMessage | null = groupChatMode
      ? {
          id: benbenPlaceholderId,
          role: "benben",
          content: "笨笨蹲在旁边等渡说完...",
          createdAt: benbenPlaceholderCreatedAt,
          status: "pending",
          clientRequestId: `${clientRequestId}-benben`,
        }
      : null;
    const nextMessages = [...messagesRef.current, userMsg];
    const draftMessages = [
      ...nextMessages,
      { id: assistantId, role: "assistant" as const, content: "", createdAt: assistantCreatedAt, status: "pending" as const, clientRequestId },
      ...(benbenPlaceholder ? [benbenPlaceholder] : []),
    ];
    const replyTarget = resolvedDeviceId;
    setInput("");
    setPlusOpen(false);
    setSending(true);
    setMessages(draftMessages);
    messagesRef.current = draftMessages;
    await saveDisplayHistory(draftMessages, { syncRemote: false, localDeviceId: resolvedDeviceId });
    try {
      const groupContext = benbenGroupActive ? buildBenbenGroupContext(messagesRef.current, groupChatMode) : "";
      const requestBody = {
        model: activeModel,
        messages: [
          ...(groupContext ? [{ role: "system", content: groupContext }] : []),
          { role: "user", content },
        ],
        stream: false,
        window_id: windowId,
      };
      const started = await apiJson<SumiTalkChatJobCreateResponse>("/miniapp-api/sumitalk-chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ...requestBody,
          reply_target: replyTarget,
          client_request_id: clientRequestId,
        }),
      });
      if (started?.status === "error") {
        const upstreamError = started.response?.error || started.response?.message || "";
        throw new Error(String(started.error || upstreamError || "渡回复失败"));
      }
      const jobId = String(started?.job_id || "").trim();
      const data = started?.status === "running" && jobId
        ? await waitForSumiTalkChatJob(jobId)
        : started?.response || started;
      if (data?.error) {
        const err = typeof data.error === "string" ? data.error : data.error?.message || JSON.stringify(data.error);
        throw new Error(err || "上游返回错误");
      }
      const reply = extractAssistantReplyText(data);
      if (!reply) throw new Error("上游没有返回内容");
      const reasoning = extractAssistantReasoning(data);
      const tokenCount = extractTokenCount(data);
      const finalMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, {
        id: assistantId,
        role: "assistant" as const,
        content: reply,
        createdAt: assistantCreatedAt,
        status: "sent" as const,
        clientRequestId,
        jobId: jobId || undefined,
        reasoning: reasoning || undefined,
        tokenCount,
      });
      messagesRef.current = finalMessages;
      setMessages(finalMessages);
      if (groupChatMode) {
        await saveDisplayHistory(finalMessages, { syncRemote: false, localDeviceId: replyTarget });
        await requestBenbenGroupReply({
          baseMessages: finalMessages,
          userContent: content,
          duReply: reply,
          replyTarget,
          clientRequestId,
          placeholderId: benbenPlaceholderId,
          placeholderCreatedAt: benbenPlaceholderCreatedAt,
        });
      } else {
        await saveDisplayHistory(finalMessages);
      }
    } catch (e: any) {
      let failedMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, {
        id: assistantId,
        role: "assistant" as const,
        content: `（发送失败：${e?.message || e}）`,
        createdAt: assistantCreatedAt,
        status: "failed" as const,
        clientRequestId,
      });
      if (groupChatMode && benbenPlaceholder) {
        failedMessages = applyMessageById(failedMessages, benbenPlaceholderId, {
          ...benbenPlaceholder,
          content: `（渡这条没发出去，笨笨也没法接上：${e?.message || e}）`,
          status: "failed",
        });
      }
      messagesRef.current = failedMessages;
      setMessages(failedMessages);
      await saveDisplayHistory(failedMessages);
      toast(`发送失败：${e?.message || e}`);
    } finally {
      setSending(false);
    }
  }

  async function sendMessage() {
    await sendChatContent(input);
  }

  const avatarClass = accent === "wenyou"
    ? "bg-[#F8F0F4] text-[#704A5D]"
    : "bg-[#F0F4F8] text-[#4A5568]";
  const benbenGroupActive = groupChatMode;
  const groupedMessages = groupChatMessages(messages);
  const assistantTyping = sending && messages.some(
    (msg) => (msg.role === "assistant" || msg.role === "benben") && String(msg.status || "").trim().toLowerCase() === "pending",
  );
  const searchMatches = useMemo<ChatSearchMatch[]>(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return [];
    const matches: ChatSearchMatch[] = [];
    groupedMessages.forEach((group) => {
      group.parts.forEach((part, partIndex) => {
        const searchable = part.systemCard?.type === "system_alarm_created"
          ? `系统闹钟 ${formatAlarmTime(part.systemCard.hour, part.systemCard.minute)} ${part.systemCard.title}`
          : part.systemCard?.type === "calendar_event_created"
            ? `系统行程 ${part.systemCard.title} ${part.systemCard.startAt || ""} ${part.systemCard.location || ""}`
            : part.systemCard?.type === "travel_plan_form"
              ? `出行规划 ${part.systemCard.title} ${(part.systemCard.destinations || []).join(" ")}`
              : part.systemCard?.type === "travel_plan_result"
                ? `路线安排 ${part.systemCard.title} ${part.systemCard.origin || ""} ${(part.systemCard.destinations || []).join(" ")}`
                : part.systemCard?.type === "travel_transport_detail"
                  ? `交通路线 ${part.systemCard.title} ${part.systemCard.from} ${part.systemCard.to}`
                  : part.systemCard?.type === "travel_food_detail"
                    ? `吃喝推荐 ${part.systemCard.title} ${part.systemCard.placeName || ""} ${part.systemCard.keywords || ""} ${(part.systemCard.items || []).map((item) => item.name).join(" ")}`
                    : String(part.content || "");
        if (!searchable.toLowerCase().includes(query)) return;
        matches.push({
          id: getChatSearchMatchId(group.id, partIndex),
          groupId: group.id,
          partIndex,
        });
      });
    });
    return matches;
  }, [groupedMessages, searchQuery]);
  const activeSearchMatch = searchMatches.length
    ? searchMatches[Math.min(activeSearchIndex, searchMatches.length - 1)]
    : null;
  const activeSearchMatchId = activeSearchMatch?.id || "";
  const transparentBubbleClass = TRANSPARENT_BUBBLE_CLASS;

  useEffect(() => {
    if (searchOpen) return;
    const el = messagesScrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    });
  }, [messages, searchOpen]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setActiveSearchIndex(0);
      return;
    }
    setActiveSearchIndex(searchMatches.length > 0 ? searchMatches.length - 1 : 0);
  }, [searchQuery, searchMatches.length]);

  useEffect(() => {
    if (!searchOpen || !activeSearchMatchId) return;
    const target = searchResultRefs.current[activeSearchMatchId];
    if (!target) return;
    requestAnimationFrame(() => {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  }, [activeSearchMatchId, searchOpen]);

  return (
    <div
      className="absolute inset-0 z-30 flex w-full max-w-full flex-col overflow-x-hidden"
      style={{
        fontFamily: chatFontFamily,
        backgroundColor: `rgba(248, 249, 250, ${Math.max(0.2, Math.min(1, chatBackgroundOpacity / 100))})`,
        backgroundImage: chatBackgroundImage ? `linear-gradient(rgba(248,249,250,${1 - Math.max(0.2, Math.min(1, chatBackgroundOpacity / 100))}), rgba(248,249,250,${1 - Math.max(0.2, Math.min(1, chatBackgroundOpacity / 100))})), url(${chatBackgroundImage})` : undefined,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      <div className="absolute top-0 z-20 w-full border-b border-gray-100/50 bg-white/80 px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+20px)] backdrop-blur-md">
        <div className="flex items-center">
          <button className="rounded-full p-2 text-gray-500 transition-colors active:bg-gray-100" onClick={onBack}>
            <ChevronLeftIcon />
          </button>
          <div className="ml-2 flex-1">
            <div className="font-medium text-gray-900" style={{ fontSize: `${chatTitleFontSize}px` }}>{title}</div>
            <ChatHeaderStatus sending={assistantTyping} />
          </div>
          <button
            className="rounded-full p-2 text-gray-500 transition-colors active:bg-gray-100"
            onClick={() => {
              setSearchOpen((prev) => {
                const next = !prev;
                if (!next) setSearchQuery("");
                return next;
              });
            }}
            aria-label="搜索"
            title="搜索"
          >
            <SearchIconMini />
          </button>
        </div>
        {searchOpen ? (
          <div className="mt-3 flex items-center gap-2 rounded-[18px] bg-[#F4F5F7] px-3 py-2">
            <SearchIconMini />
            <input
              className="flex-1 bg-transparent text-[14px] font-medium text-gray-900 outline-none placeholder:text-gray-400"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索记录"
            />
            {searchMatches.length ? (
              <>
                <button
                  className="rounded-full p-1 text-gray-500 transition-colors active:bg-gray-200"
                  onClick={() => setActiveSearchIndex((prev) => (prev - 1 + searchMatches.length) % searchMatches.length)}
                  aria-label="上一个结果"
                >
                  <ChevronUpMini />
                </button>
                <button
                  className="rounded-full p-1 text-gray-500 transition-colors active:bg-gray-200"
                  onClick={() => setActiveSearchIndex((prev) => (prev + 1) % searchMatches.length)}
                  aria-label="下一个结果"
                >
                  <ChevronDownMini />
                </button>
                <span className="text-[11px] font-medium text-gray-500">
                  {activeSearchIndex + 1}/{searchMatches.length}
                </span>
              </>
            ) : searchQuery.trim() ? (
              <span className="text-[11px] font-medium text-gray-500">无结果</span>
            ) : null}
          </div>
        ) : null}
      </div>

      <div
        ref={messagesScrollRef}
        className={`min-h-0 w-full max-w-full flex-1 overflow-x-hidden overflow-y-auto px-3.5 pb-5 ${searchOpen ? "pt-[156px]" : "pt-[104px]"}`}
      >
        <div className="space-y-5">
          {groupedMessages.map((group, index) => (
            <React.Fragment key={group.id}>
              {showChatTimestamps && shouldShowGroupTime(group.createdAt, groupedMessages[index - 1]?.lastCreatedAt) ? (
                <div className="mb-2 flex justify-center">
                  <span className="rounded-full bg-[#EFEFEF] px-3 py-1 text-[11px] font-medium text-gray-900">
                    {formatClockTime(group.createdAt, chatTimeFormat)}
                  </span>
                </div>
              ) : null}
              {group.role === "user" ? (
                <div className="flex items-start justify-end space-x-3 rounded-[22px]">
                  <div className={`mt-[2px] flex ${showChatAvatars ? "max-w-[78%]" : "max-w-[86%]"} flex-col items-end space-y-1.5`}>
                    {group.parts.map((part, index) => {
                      const matchId = getChatSearchMatchId(group.id, index);
                      const isActiveSearchPart = activeSearchMatchId === matchId;
                      return (
                        <div
                          key={`${group.id}-${index}`}
                          ref={(el) => {
                            searchResultRefs.current[matchId] = el;
                          }}
                          className={`block max-w-full rounded-[18px] px-3 py-2 text-left font-medium leading-relaxed shadow-sm ${
                            transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("user", userBubbleStyle)
                          } ${isActiveSearchPart ? "ring-2 ring-amber-300/90 ring-offset-2 ring-offset-transparent" : ""}`}
                          style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
                        >
                          <PlainTextBlock content={part.content || (sending ? "…" : "")} />
                        </div>
                      );
                    })}
                  </div>
                  {showChatAvatars ? (
                    <AvatarBubble image={myAvatarImage} label="我" className="bg-gray-200 text-gray-600" />
                  ) : null}
                </div>
              ) : (
                <div className="flex items-start space-x-3 rounded-[22px]">
                  {showChatAvatars ? (
                    <AvatarBubble
                      image={group.role === "benben" ? "" : duAvatarImage}
                      label={group.role === "benben" ? "笨" : avatarLabel}
                      className={group.role === "benben" ? "bg-[#FFF3D7] text-[#8A5A10]" : avatarClass}
                    />
                  ) : null}
                  <div className={`mt-[2px] ${showChatAvatars ? "max-w-[78%]" : "max-w-[86%]"} space-y-1.5`}>
                    {group.parts.map((part, index) => {
                      const matchId = getChatSearchMatchId(group.id, index);
                      const isActiveSearchPart = activeSearchMatchId === matchId;
                      return (
                        <div
                          key={`${group.id}-${index}`}
                          ref={(el) => {
                            searchResultRefs.current[matchId] = el;
                          }}
                          className={`space-y-2 rounded-[20px] ${isActiveSearchPart ? "ring-2 ring-amber-300/90 ring-offset-2 ring-offset-transparent" : ""}`}
                        >
                          {part.reasoning ? (
                            <details open={expandReasoningByDefault} className="max-w-full rounded-[14px] border border-gray-100 bg-[#F7F7F7] px-3 py-2 text-[12px] text-gray-700">
                              <summary className="cursor-pointer list-none text-[12px] font-medium text-gray-600">思维链</summary>
                              <div className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words leading-6">{part.reasoning}</div>
                            </details>
                          ) : null}
                          {part.systemCard?.type === "system_alarm_created" ? (
                            <SystemAlarmCreatedBubble
                              card={part.systemCard}
                              onOpen={() => {
                                void SumiOverlay.openSystemAlarms().catch((e) => toast(`打开系统闹钟失败：${e?.message || e}`));
                              }}
                            />
                          ) : part.systemCard?.type === "calendar_event_created" ? (
                            <CalendarEventCreatedBubble
                              card={part.systemCard}
                              onOpen={() => {
                                const card = part.systemCard as CalendarEventCreatedCard;
                                void SumiOverlay.openCalendarEvent({
                                  eventId: card.eventId,
                                  startMillis: card.startMillis,
                                }).catch((e) => toast(`打开系统日历失败：${e?.message || e}`));
                              }}
                            />
                          ) : part.systemCard?.type === "travel_plan_form" ? (
                            <TravelPlanFormBubble
                              card={part.systemCard}
                              onOpen={() => setTravelFormCard(part.systemCard as TravelPlanFormCard)}
                            />
                          ) : part.systemCard?.type === "travel_plan_result" ? (
                            <TravelPlanResultBubble
                              card={part.systemCard}
                              onOpen={() => setTravelResultCard(part.systemCard as TravelPlanResultCard)}
                            />
                          ) : part.systemCard?.type === "travel_transport_detail" ? (
                            <TravelTransportDetailBubble
                              card={part.systemCard}
                              onOpen={() => setTravelTransportCard(part.systemCard as TravelTransportDetailCard)}
                            />
                          ) : part.systemCard?.type === "travel_food_detail" ? (
                            <TravelFoodDetailBubble
                              card={part.systemCard}
                              onOpen={() => setTravelFoodCard(part.systemCard as TravelFoodDetailCard)}
                            />
                          ) : (
                            <>
                              <div
                                className={`inline-block w-fit max-w-full rounded-[18px] px-3 py-2 font-medium leading-relaxed shadow-sm ${
                                  transparentBubbleEnabled
                                    ? TRANSPARENT_BUBBLE_CLASS
                                    : group.role === "benben"
                                      ? "border border-amber-100 bg-[#FFF7E6] text-[#3F2A11]"
                                      : resolveBubbleClass("assistant", assistantBubbleStyle)
                                }`}
                                style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
                              >
                                {part.render === "html" ? (
                                  <HtmlBlock content={part.content || (sending ? "…" : "")} />
                                ) : part.render === "plain" ? (
                                  <PlainTextBlock content={part.content || (sending ? "…" : "")} />
                                ) : (
                                  <RichTextBlock content={part.content || (sending ? "…" : "")} />
                                )}
                              </div>
                              <div className="flex items-center gap-3 pl-1 text-[11px] text-gray-500">
                                <button
                                  className="rounded-full p-1 text-gray-500 transition-colors active:bg-gray-100 active:opacity-70"
                                  onClick={() => copyText(part.content, toast)}
                                  aria-label="复制"
                                  title="复制"
                                >
                                  <CopyIconMini />
                                </button>
                                {showTokenCount && (part.tokenCount?.input || part.tokenCount?.output) ? (
                                  <span>
                                    {part.tokenCount?.input ? `↑${formatTokenCountValue(part.tokenCount.input)}` : ""}
                                    {part.tokenCount?.input && part.tokenCount?.output ? " " : ""}
                                    {part.tokenCount?.output ? `↓${formatTokenCountValue(part.tokenCount.output)}` : ""}
                                  </span>
                                ) : null}
                              </div>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="z-20 border-t border-gray-100 bg-white pb-[calc(env(safe-area-inset-bottom,24px))]">
        <div className={`overflow-hidden bg-white transition-all duration-300 ease-in-out ${plusOpen ? "h-[140px] opacity-100" : "h-0 opacity-0"}`}>
          <div className="flex space-x-5 px-6 pb-2 pt-5">
              <ChatActionButton label="表情包" onClick={() => { setPlusOpen(false); onOpenStickers(); }} />
              <ChatActionButton label="通话" onClick={() => { setPlusOpen(false); onOpenCall(); }} />
              <ChatActionButton
                label="出行规划"
                onClick={() => {
                  setPlusOpen(false);
                  setTravelFormCard({
                    type: "travel_plan_form",
                    title: "出行规划",
                    prompt: "把想去哪里、想吃什么、能不能走路填一下，渡再帮你排顺序和路线。",
                    destinations: [],
                    prefer: "auto",
                    walk: "medium",
                  });
                }}
              />
          </div>
        </div>
        <div className="flex items-end space-x-2 px-3 py-2.5">
          <button
            className={`rounded-full p-2.5 text-gray-500 transition-colors ${plusOpen ? "bg-gray-100 text-gray-800" : "active:bg-gray-50"}`}
            onClick={() => setPlusOpen((v) => !v)}
          >
            <PlusIcon open={plusOpen} />
          </button>
          <div className="flex min-h-[42px] flex-1 items-center rounded-[20px] bg-[#F4F5F7] px-4 py-2.5">
            <textarea
              className="max-h-28 min-h-[22px] w-full resize-none bg-transparent font-medium leading-6 text-gray-900 outline-none placeholder:text-gray-400"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入消息..."
              rows={1}
              style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
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
      {travelFormCard ? (
        <TravelPlanFormModal
          card={travelFormCard}
          sending={sending}
          onClose={() => setTravelFormCard(null)}
          onSubmit={(content) => {
            setTravelFormCard(null);
            void sendChatContent(content, { displayContent: "已提交，渡在安排" });
          }}
        />
      ) : null}
      {travelResultCard ? (
        <TravelPlanResultModal
          card={travelResultCard}
          onClose={() => setTravelResultCard(null)}
        />
      ) : null}
      {travelTransportCard ? (
        <TravelTransportDetailModal
          card={travelTransportCard}
          onClose={() => setTravelTransportCard(null)}
        />
      ) : null}
      {travelFoodCard ? (
        <TravelFoodDetailModal
          card={travelFoodCard}
          onClose={() => setTravelFoodCard(null)}
        />
      ) : null}
    </div>
  );
}

function ChatActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button className="group flex flex-col items-center" onClick={onClick}>
      <div className="mb-2.5 flex h-[60px] w-[60px] items-center justify-center rounded-[20px] bg-[#F8F9FA] text-gray-600 transition-transform active:scale-95">
        {label === "表情包" ? <SmileIconMini /> : label === "出行规划" ? <RouteIconMini /> : <PhoneIconLarge />}
      </div>
      <span className="text-[11px] font-medium tracking-wide text-gray-500">{label}</span>
    </button>
  );
}

function AvatarBubble({
  image,
  label,
  className,
}: {
  image?: string;
  label: string;
  className: string;
}) {
  if (image) {
    return (
      <div className="h-[38px] w-[38px] shrink-0 overflow-hidden rounded-full shadow-sm">
        <img src={image} alt={label} className="h-full w-full object-cover" />
      </div>
    );
  }
  return <div className={`flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-full text-[13px] font-medium shadow-sm ${className}`}>{label}</div>;
}

function PreviewAvatar({
  image,
  label,
  shellClass,
}: {
  image?: string;
  label: string;
  shellClass: string;
}) {
  if (image) {
    return (
      <div className="h-[44px] w-[44px] overflow-hidden rounded-full">
        <img src={image} alt={label} className="h-full w-full object-cover" />
      </div>
    );
  }
  return <div className={`flex h-[44px] w-[44px] items-center justify-center rounded-full text-[16px] font-semibold ${shellClass}`}>{label}</div>;
}

function PageCardRow({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      className="flex w-full items-center rounded-[22px] border border-gray-100/60 bg-white p-4 text-left shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)] transition-transform active:scale-[0.98]"
      onClick={onClick}
    >
      <div className="mr-3 flex h-[38px] w-[38px] items-center justify-center rounded-full bg-gray-50 text-gray-600">
        {icon}
      </div>
      <span className="flex-1 text-[15px] font-medium tracking-wide text-gray-800">{label}</span>
      <ChevronRightIcon />
    </button>
  );
}

function PersonalizationScreen({
  transparentBubbleEnabled,
  onToggleTransparentBubble,
  showChatAvatars,
  onToggleShowChatAvatars,
  chatContentFontSize,
  onChangeChatContentFontSize,
  chatTitleFontSize,
  onChangeChatTitleFontSize,
  chatFontKey,
  onCycleChatFont,
  showChatTimestamps,
  onToggleShowChatTimestamps,
  chatTimeFormat,
  onCycleChatTimeFormat,
  showTokenCount,
  onToggleShowTokenCount,
  expandReasoningByDefault,
  onToggleExpandReasoningByDefault,
  chatBackgroundOpacity,
  onChangeChatBackgroundOpacity,
  userBubbleStyle,
  onCycleUserBubbleStyle,
  assistantBubbleStyle,
  onCycleAssistantBubbleStyle,
  myAvatarImage,
  duAvatarImage,
  chatBackgroundImage,
  onPickMyAvatar,
  onPickDuAvatar,
  onPickChatBackground,
}: {
  transparentBubbleEnabled: boolean;
  onToggleTransparentBubble: (next: boolean) => void;
  showChatAvatars: boolean;
  onToggleShowChatAvatars: (next: boolean) => void;
  chatContentFontSize: number;
  onChangeChatContentFontSize: (next: number) => void;
  chatTitleFontSize: number;
  onChangeChatTitleFontSize: (next: number) => void;
  chatFontKey: ChatFontKey;
  onCycleChatFont: () => void;
  showChatTimestamps: boolean;
  onToggleShowChatTimestamps: (next: boolean) => void;
  chatTimeFormat: ChatTimeFormat;
  onCycleChatTimeFormat: () => void;
  showTokenCount: boolean;
  onToggleShowTokenCount: (next: boolean) => void;
  expandReasoningByDefault: boolean;
  onToggleExpandReasoningByDefault: (next: boolean) => void;
  chatBackgroundOpacity: number;
  onChangeChatBackgroundOpacity: (next: number) => void;
  userBubbleStyle: BubbleStyleKey;
  onCycleUserBubbleStyle: () => void;
  assistantBubbleStyle: BubbleStyleKey;
  onCycleAssistantBubbleStyle: () => void;
  myAvatarImage: string;
  duAvatarImage: string;
  chatBackgroundImage: string;
  onPickMyAvatar: () => void;
  onPickDuAvatar: () => void;
  onPickChatBackground: () => void;
}) {
  return (
    <div className="bg-[#FDFDFD] px-1 pb-6 pt-4">
      <div className="space-y-6">
        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">头像设置</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <PersonalizationRow
              title="我的头像"
              subtitle="自定义我的头像"
              leading={<PreviewAvatar image={myAvatarImage} label="我" shellClass="bg-[#E5E7EB] text-gray-700" />}
              onClick={onPickMyAvatar}
            />
            <PersonalizationRow
              title="渡的头像"
              subtitle="自定义助手的头像"
              leading={<PreviewAvatar image={duAvatarImage} label="渡" shellClass="bg-[#EEF2FF] text-gray-700" />}
              onClick={onPickDuAvatar}
              last
            />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">聊天背景</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <div className="mb-5 rounded-[20px] bg-[#F8FAFC] p-4">
              <p className="mb-3 text-[12px] font-medium text-gray-400">当前背景预览</p>
              <div
                className="h-[92px] rounded-[18px] bg-[linear-gradient(180deg,#F8FAFC_0%,#EEF2F7_100%)]"
                style={{
                  opacity: Math.max(0.2, Math.min(1, chatBackgroundOpacity / 100)),
                  backgroundImage: chatBackgroundImage ? `url(${chatBackgroundImage})` : "linear-gradient(180deg,#F8FAFC_0%,#EEF2F7_100%)",
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                }}
              />
            </div>
            <PersonalizationRow title="背景图设置" onClick={onPickChatBackground} />
            <PersonalizationSliderRow title="背景透明度" value={`${chatBackgroundOpacity}%`} min={20} max={100} step={1} currentValue={chatBackgroundOpacity} onChange={onChangeChatBackgroundOpacity} />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">气泡样式</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <div className="mb-5 rounded-[20px] bg-[#F8FAFC] p-4">
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  {showChatAvatars ? <div className="flex h-[32px] w-[32px] items-center justify-center rounded-full bg-[#EEF2FF] text-[13px] font-medium text-gray-700">渡</div> : null}
                  <div className={`inline-block w-fit rounded-[16px] px-3 py-2 font-medium leading-normal ${transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("assistant", assistantBubbleStyle)}`} style={{ fontSize: `${chatContentFontSize}px`, fontFamily: resolveChatFontFamily(chatFontKey) }}>
                    这里是助手气泡预览
                  </div>
                </div>
                <div className="flex justify-end gap-3">
                  <div className={`inline-block w-fit rounded-[16px] px-3 py-2 font-medium leading-normal ${transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("user", userBubbleStyle)}`} style={{ fontSize: `${chatContentFontSize}px`, fontFamily: resolveChatFontFamily(chatFontKey) }}>
                    这里是用户气泡预览
                  </div>
                  {showChatAvatars ? <div className="flex h-[32px] w-[32px] items-center justify-center rounded-full bg-[#E5E7EB] text-[13px] font-medium text-gray-700">我</div> : null}
                </div>
              </div>
            </div>
            <PersonalizationSliderRow title="气泡圆角" value="18px" min={18} max={18} step={1} currentValue={18} disabled />
            <PersonalizationRow title="用户气泡样式" value={getBubbleStyleLabel(userBubbleStyle, "user")} onClick={onCycleUserBubbleStyle} />
            <PersonalizationRow title="助手气泡样式" value={getBubbleStyleLabel(assistantBubbleStyle, "assistant")} onClick={onCycleAssistantBubbleStyle} />
            <PersonalizationSwitchRow title="显示头像" enabled={showChatAvatars} onToggle={onToggleShowChatAvatars} />
            <PersonalizationSwitchRow
              title="启用（透明模式）"
              enabled={transparentBubbleEnabled}
              onToggle={onToggleTransparentBubble}
            />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">字体与字号</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <div className="mb-5 rounded-[20px] bg-[#F8FAFC] p-4">
              <p className="font-medium text-gray-800" style={{ fontSize: `${chatContentFontSize}px`, fontFamily: resolveChatFontFamily(chatFontKey) }}>这里是聊天文字的预览效果</p>
            </div>
            <PersonalizationSliderRow title="聊天内容字号" value={`${chatContentFontSize}px`} min={12} max={18} step={1} currentValue={chatContentFontSize} onChange={onChangeChatContentFontSize} />
            <PersonalizationSliderRow title="界面标题字号" value={`${chatTitleFontSize}px`} min={14} max={20} step={1} currentValue={chatTitleFontSize} onChange={onChangeChatTitleFontSize} />
            <PersonalizationRow title="聊天字体" value={getChatFontLabel(chatFontKey)} onClick={onCycleChatFont} last />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">信息显示</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <PersonalizationSwitchRow title="显示时间戳" enabled={showChatTimestamps} onToggle={onToggleShowChatTimestamps} />
            <PersonalizationRow title="时间格式" value={chatTimeFormat === "hhmm" ? "HH:MM" : "上午/下午 HH:MM"} onClick={onCycleChatTimeFormat} />
            <PersonalizationSwitchRow title="显示 token" enabled={showTokenCount} onToggle={onToggleShowTokenCount} />
            <PersonalizationSwitchRow title="默认展开思维链" enabled={expandReasoningByDefault} onToggle={onToggleExpandReasoningByDefault} />
          </div>
        </section>
      </div>
    </div>
  );
}

function PersonalizationRow({
  title,
  subtitle,
  value,
  leading,
  onClick,
  last = false,
}: {
  title: string;
  subtitle?: string;
  value?: string;
  leading?: React.ReactNode;
  onClick?: () => void;
  last?: boolean;
}) {
  return (
    <button
      type="button"
      className={`flex w-full items-center justify-between py-[14px] text-left ${last ? "" : "border-b border-[#F9FAFB]"}`}
      onClick={onClick}
      disabled={!onClick}
    >
      <div className="flex items-center gap-3">
        {leading}
        <div>
          <p className="text-[15px] font-semibold text-gray-800">{title}</p>
          {subtitle ? <p className="mt-0.5 text-[12px] text-gray-400">{subtitle}</p> : null}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {value ? <span className="text-[13px] font-medium text-gray-400">{value}</span> : null}
        <ChevronRightIcon />
      </div>
    </button>
  );
}

function PersonalizationSwitchRow({
  title,
  enabled = false,
  onToggle,
}: {
  title: string;
  enabled?: boolean;
  onToggle?: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between border-b border-[#F9FAFB] py-[14px] last:border-b-0">
      <span className="text-[15px] font-medium text-gray-800">{title}</span>
      <button
        className={`relative h-[24px] w-[42px] rounded-full transition-colors ${enabled ? "bg-[#1F2937]" : "bg-[#E2E8F0]"}`}
        onClick={() => onToggle?.(!enabled)}
        type="button"
      >
        <div className={`absolute bottom-[3px] h-[18px] w-[18px] rounded-full bg-white transition-transform ${enabled ? "left-[21px]" : "left-[3px]"}`} />
      </button>
    </div>
  );
}

function PersonalizationSliderRow({
  title,
  value,
  min,
  max,
  step,
  currentValue,
  onChange,
  disabled = false,
}: {
  title: string;
  value: string;
  min: number;
  max: number;
  step: number;
  currentValue: number;
  onChange?: (next: number) => void;
  disabled?: boolean;
}) {
  const percent = max === min ? 100 : ((currentValue - min) / (max - min)) * 100;
  return (
    <div className="border-b border-[#F9FAFB] py-[14px] last:border-b-0">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[15px] font-medium text-gray-800">{title}</span>
        <span className="text-[13px] font-medium text-gray-400">{value}</span>
      </div>
      <div className={`relative h-[4px] rounded-full bg-[#E2E8F0] ${disabled ? "opacity-50" : ""}`}>
        <div className="absolute left-0 top-0 h-[4px] rounded-full bg-[#1F2937]" style={{ width: `${percent}%` }} />
        <div className="absolute top-1/2 h-[18px] w-[18px] -translate-y-1/2 rounded-full border-2 border-white bg-[#1F2937] shadow-[0_2px_4px_rgba(0,0,0,0.1)]" style={{ left: `calc(${percent}% - 9px)` }} />
        {!disabled ? (
          <input
            type="range"
            className="absolute inset-0 h-[18px] w-full cursor-pointer opacity-0"
            min={min}
            max={max}
            step={step}
            value={currentValue}
            onChange={(e) => onChange?.(Number(e.target.value))}
          />
        ) : null}
      </div>
    </div>
  );
}

function FloatingBallSettingRow({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: (next: boolean) => void;
}) {
  return (
    <div className="flex min-h-[60px] w-full items-center border-b border-gray-50 px-4 py-4">
      <span className="mr-4 text-gray-400">
        <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="12" cy="12" r="8" opacity="0.35" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </span>
      <span className="flex-1 text-[15px] font-medium tracking-wide text-gray-800">显示悬浮球</span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${enabled ? "bg-gray-800" : "bg-gray-200"}`}
        onClick={() => onToggle(!enabled)}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-[22px]" : "translate-x-0"}`}
        />
      </button>
    </div>
  );
}

function SwitchSettingRow({
  icon,
  label,
  enabled,
  disabled = false,
  onToggle,
  last,
}: {
  icon: React.ReactNode;
  label: string;
  enabled: boolean;
  disabled?: boolean;
  onToggle: (next: boolean) => void;
  last?: boolean;
}) {
  return (
    <div className={`flex min-h-[60px] w-full items-center px-4 py-4 ${last ? "" : "border-b border-gray-50"} ${disabled ? "opacity-60" : ""}`}>
      <span className="mr-4 text-gray-400">{icon}</span>
      <span className="flex-1 text-[15px] font-medium tracking-wide text-gray-800">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${enabled ? "bg-gray-800" : "bg-gray-200"} ${disabled ? "cursor-not-allowed" : ""}`}
        onClick={() => onToggle(!enabled)}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-[22px]" : "translate-x-0"}`}
        />
      </button>
    </div>
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
      className={`flex min-h-[60px] w-full items-center px-4 py-4 text-left transition-colors active:bg-gray-50 ${last ? "" : "border-b border-gray-50"}`}
      onClick={onClick}
    >
      <span className="mr-4 text-gray-400">{icon}</span>
      <span className="flex-1 text-[15px] font-medium tracking-wide text-gray-800">{label}</span>
      <ChevronRightIcon />
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const j = await publicApiFetch("/miniapp-api/panel-auth/meta").then((r) => r.json());
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
        const first = await publicApiFetch("/miniapp-api/panel-auth/check-password", {
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
      const deviceId = await getOrCreatePanelDeviceId();
      const j = await publicApiFetch("/miniapp-api/panel-auth/verify", {
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
      <Shell
        onLogout={onLogout}
        onOpenDevices={onOpenDevices}
        deviceManagerOpen={deviceManagerOpen}
        onCloseDevices={onCloseDevices}
      />
      {deviceManagerOpen && onCloseDevices ? <DeviceManagerModal onClose={onCloseDevices} onLogout={onLogout} /> : null}
    </>
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
  const [loadedPromptA, setLoadedPromptA] = useState("");
  const [loadedPromptB, setLoadedPromptB] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [portrait, setPortrait] = useState<{
    xinyue_candidates?: Array<{ id?: string; summary?: string }>;
    du_candidates?: Array<{ id?: string; summary?: string }>;
    interaction_candidates?: Array<{ id?: string; summary?: string }>;
  } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ bucket: "xinyue" | "du" | "interaction"; id: string } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [j, p] = await Promise.all([
        apiJson<{ ok?: boolean; content?: string; source?: string; error?: string; active_key?: string; prompts?: { a?: string; b?: string } }>("/miniapp-api/core-prompt"),
        apiJson<{ ok?: boolean; xinyue_candidates?: Array<{ id?: string; summary?: string }>; du_candidates?: Array<{ id?: string; summary?: string }>; interaction_candidates?: Array<{ id?: string; summary?: string }> }>("/miniapp-api/portrait-memory"),
      ]);
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setActiveKey(((j.active_key || "a").toString() === "b" ? "b" : "a"));
      const nextA = ((j.prompts?.a ?? j.content) || "").toString();
      const nextB = (j.prompts?.b || "").toString();
      setPromptA(nextA);
      setPromptB(nextB);
      setLoadedPromptA(nextA);
      setLoadedPromptB(nextB);
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
      setLoadedPromptA(promptA);
      setLoadedPromptB(promptB);
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  function handleCancelEdit() {
    setPromptA(loadedPromptA);
    setPromptB(loadedPromptB);
    onClose();
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
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/portrait-memory/${encodeURIComponent(bucket)}/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除");
      setPendingDelete(null);
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  const isDirty = promptA !== loadedPromptA || promptB !== loadedPromptB;
  const activePrompt = activeKey === "a" ? promptA : promptB;
  const setActivePrompt = (value: string) => {
    if (activeKey === "a") {
      setPromptA(value);
      return;
    }
    setPromptB(value);
  };

  return (
    <FullScreenPane title="核心 Prompt" accent="neutral" onBack={onClose}>
      <div className="px-2 pb-32 pt-2 text-gray-900">
          <div className="mb-6 flex rounded-2xl bg-gray-100/50 p-1">
            <button
              type="button"
              onClick={() => setActiveKey("a")}
              disabled={loading || saving}
              className={`flex-1 rounded-xl py-2.5 text-[14px] ${
                activeKey === "a"
                  ? "border border-gray-100 bg-white font-bold text-gray-800 shadow-sm"
                  : "font-medium text-gray-400"
              }`}
            >
              Prompt A
            </button>
            <button
              type="button"
              onClick={() => setActiveKey("b")}
              disabled={loading || saving}
              className={`flex-1 rounded-xl py-2.5 text-[14px] ${
                activeKey === "b"
                  ? "border border-gray-100 bg-white font-bold text-gray-800 shadow-sm"
                  : "font-medium text-gray-400"
              }`}
            >
              Prompt B
            </button>
          </div>

          <div className="mb-4 rounded-[28px] border border-gray-100/80 bg-white p-6 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-[18px] font-bold text-gray-800">Prompt {activeKey.toUpperCase()}</h2>
              {isDirty ? (
                <div className="flex items-center rounded-md border border-amber-100 bg-amber-50 px-2 py-1">
                  <span className="mr-2 h-1.5 w-1.5 rounded-full bg-amber-400" />
                  <span className="text-[10px] font-bold uppercase text-amber-600">未保存修改</span>
                </div>
              ) : (
                <div className="flex items-center rounded-md border border-green-100 bg-green-50 px-2 py-1">
                  <span className="mr-2 h-1.5 w-1.5 rounded-full bg-green-400" />
                  <span className="text-[10px] font-bold uppercase text-green-600">已同步</span>
                </div>
              )}
            </div>
            <p className="text-[13px] leading-relaxed text-gray-400">当前正在编辑的是主交互指令，该指令决定了 AI 的基础人格特质和长期记忆提取逻辑。</p>
          </div>

          <div className="mb-8 rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
            <div className="mb-4 px-1">
              <h3 className="mb-1 text-[13px] font-bold uppercase tracking-widest text-gray-400">系统核心指令</h3>
              <p className="text-[11px] text-gray-300">定义角色的回复风格与行为准则</p>
            </div>
            <div className="rounded-[22px] bg-gray-50 p-5">
              <textarea
                className="h-[400px] w-full resize-none border-none bg-transparent text-[15px] leading-relaxed text-gray-700 outline-none"
                value={activePrompt}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setActivePrompt(e.target.value)}
                placeholder={loading ? "加载中..." : "输入核心 Prompt内容..."}
              />
              <div className="mt-4 flex justify-end">
                <span className="text-[11px] font-medium text-gray-300">{activePrompt.length.toLocaleString()} 字符</span>
              </div>
            </div>
          </div>

          <div className="mb-6">
            <PortraitBlock title="辛玥画像候选" bucket="xinyue" items={portrait?.xinyue_candidates || []} onCopy={copyText} onDelete={(bucket, id) => setPendingDelete({ bucket, id })} />
          </div>
          <div className="mb-6">
            <PortraitBlock title="渡画像候选" bucket="du" items={portrait?.du_candidates || []} onCopy={copyText} onDelete={(bucket, id) => setPendingDelete({ bucket, id })} />
          </div>
          <div className="mb-6">
            <PortraitBlock title="相处模式候选" bucket="interaction" items={portrait?.interaction_candidates || []} onCopy={copyText} onDelete={(bucket, id) => setPendingDelete({ bucket, id })} />
          </div>
      </div>

      {isDirty ? (
        <div className="pointer-events-none fixed bottom-[96px] left-5 right-5 z-[60]">
          <div className="flex items-center justify-center rounded-full bg-amber-500 px-4 py-2 text-[12px] font-bold text-white shadow-lg">
            <svg className="mr-2 h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            您有未保存的修改，请确认保存或取消
          </div>
        </div>
      ) : null}

      <div className="safe-bottom fixed bottom-0 left-0 right-0 z-[55] flex gap-4 border-t border-gray-50 bg-white/80 p-5 pb-[calc(env(safe-area-inset-bottom,0px)+20px)] backdrop-blur-lg">
        <button
          type="button"
          onClick={handleCancelEdit}
          disabled={loading || saving}
          className="flex-1 rounded-[20px] py-4 text-[15px] font-bold text-gray-400 transition-all active:bg-gray-50"
        >
          取消编辑
        </button>
        <button
          type="button"
          onClick={save}
          disabled={loading || saving}
          className="flex-1 rounded-[20px] bg-gray-800 py-4 text-[15px] font-bold text-white shadow-[0_10px_24px_rgba(15,23,42,0.18)] transition-all active:scale-95"
        >
          保存修改
        </button>
      </div>

      {pendingDelete ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/10 px-8 backdrop-blur-[2px]">
          <div className="w-full max-w-sm rounded-[32px] bg-white p-8 shadow-2xl">
            <div className="mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-full bg-red-50">
              <svg className="h-6 w-6 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </div>
            <h3 className="mb-3 text-center text-[20px] font-semibold text-gray-900">要删除这个画像候选吗？</h3>
            <p className="mb-8 px-2 text-center text-[15px] font-light leading-relaxed text-gray-500">此操作将永久移除该条目，您将无法再在 Prompt 编辑中快速引用它。</p>
            <div className="flex flex-col space-y-3">
              <button
                type="button"
                onClick={() => void deletePortrait(pendingDelete.bucket, pendingDelete.id)}
                className="w-full rounded-[20px] bg-red-500 py-4 font-bold text-white shadow-lg shadow-red-100 transition-all active:scale-95"
              >
                确认删除
              </button>
              <button
                type="button"
                onClick={() => setPendingDelete(null)}
                className="w-full rounded-[20px] py-4 font-bold text-gray-400 transition-all active:bg-gray-50"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </FullScreenPane>
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
    <>
      <div className="mb-3 flex items-center justify-between px-2">
        <h2 className="text-[12px] font-bold uppercase tracking-widest text-gray-400">{title}</h2>
        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-500">{items.length}</span>
      </div>
      {!items.length ? <div className="rounded-[24px] border border-gray-50 bg-white px-4 py-4 text-[13px] text-gray-400 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">暂无候选</div> : null}
      <div className="space-y-3">
        {items.map((item, idx) => (
          <div key={item.id || `${title}-${idx}`} className="flex items-center gap-4 rounded-[24px] border border-gray-50 bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
            <div className="flex-1">
              <p className="line-clamp-2 text-[13px] leading-snug text-gray-600">{String(item.summary || "")}</p>
            </div>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => onCopy(String(item.summary || ""))}
                className="p-2 text-gray-300 transition-colors active:text-blue-500"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              </button>
              {item.id ? (
                <button
                  type="button"
                  onClick={() => onDelete(bucket, String(item.id || ""))}
                  className="p-2 text-gray-300 transition-colors active:text-red-400"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <line x1="10" y1="11" x2="10" y2="17" />
                    <line x1="14" y1="11" x2="14" y2="17" />
                  </svg>
                </button>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
