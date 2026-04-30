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
  status?: "pending" | "sent" | "failed";
  clientRequestId?: string;
  jobId?: string;
  reasoning?: string;
  tokenCount?: {
    input?: number;
    output?: number;
  };
};

function applyAssistantTerminalMessage(
  currentMessages: ChatDraftMessage[],
  clientRequestId: string,
  assistantMessage: ChatDraftMessage,
): ChatDraftMessage[] {
  const cid = String(clientRequestId || "").trim();
  const list = Array.isArray(currentMessages) ? currentMessages : [];
  if (cid && list.some((msg) => msg.role === "assistant" && msg.clientRequestId === cid && msg.status === "sent")) {
    return list;
  }
  let replaced = false;
  const next = list.map((msg) => {
    if (!cid || msg.role !== "assistant" || msg.clientRequestId !== cid || msg.status === "sent") return msg;
    replaced = true;
    return {
      ...assistantMessage,
      id: msg.id,
      createdAt: msg.createdAt,
      clientRequestId: cid,
      jobId: assistantMessage.jobId || msg.jobId,
    };
  });
  if (!replaced) next.push(assistantMessage);
  return next;
}
type SystemAlarmCreatedCard = {
  type: "system_alarm_created";
  hour: number;
  minute: number;
  title: string;
};
type CalendarEventCreatedCard = {
  type: "calendar_event_created";
  title: string;
  startAt: string;
  endAt?: string;
  startMillis?: number;
  endMillis?: number;
  allDay?: boolean;
  location?: string;
  reminderMinutes?: number;
  eventId?: number | string;
};
type TravelPlanPreference = "auto" | "transit" | "taxi";
type TravelPlanWalkPreference = "low" | "medium" | "high";
type TravelPlanFormCard = {
  type: "travel_plan_form";
  title: string;
  prompt?: string;
  city?: string;
  destinations?: string[];
  food?: string;
  prefer?: TravelPlanPreference;
  walk?: TravelPlanWalkPreference;
};
type TravelPlanRouteSummary = {
  ok?: boolean;
  duration?: string;
  distance?: string;
  walking?: string;
  costYuan?: number;
  taxiCostYuan?: number;
  steps?: string[];
  error?: string;
};
type TravelPlanResultLeg = {
  from: string;
  to: string;
  mode?: string;
  reason?: string;
  transit?: TravelPlanRouteSummary;
  driving?: TravelPlanRouteSummary;
  links?: {
    navi?: string;
    taxi?: string;
  };
  summary?: string[];
};
type TravelPlanResultCard = {
  type: "travel_plan_result";
  title: string;
  origin?: string;
  destinations?: string[];
  optimized?: boolean;
  legs?: TravelPlanResultLeg[];
  personalMapUrl?: string;
  note?: string;
};
type TravelTransportDetailCard = {
  type: "travel_transport_detail";
  title: string;
  planId?: string;
  legId?: string;
  from: string;
  to: string;
  mode?: string;
  reason?: string;
  transit?: TravelPlanRouteSummary;
  driving?: TravelPlanRouteSummary;
  cacheHit?: boolean;
  note?: string;
};
type TravelFoodItem = {
  name: string;
  type?: string;
  address?: string;
  distanceMeters?: number;
  rating?: string;
  cost?: string;
};
type TravelFoodDetailCard = {
  type: "travel_food_detail";
  title: string;
  planId?: string;
  placeId?: string;
  placeName?: string;
  keywords?: string;
  items?: TravelFoodItem[];
  cacheHit?: boolean;
  note?: string;
};
type SumiTalkSystemCard =
  | SystemAlarmCreatedCard
  | CalendarEventCreatedCard
  | TravelPlanFormCard
  | TravelPlanResultCard
  | TravelTransportDetailCard
  | TravelFoodDetailCard;
type DeviceItem = {
  id?: string;
  note?: string;
  added_at?: string;
  last_seen?: string;
  revoked?: boolean;
  current?: boolean;
};
type ChatFontKey = "yahei" | "system" | "pingfang";
type ChatTimeFormat = "hhmm" | "ampm";
type BubbleStyleKey = "default" | "soft" | "outline";
type StayWithDuView = "timeline" | "cinema" | "library";
type StayWithDuEntryType = "node" | "movie" | "book";
type StayTimelineNode = {
  id: string;
  date: string;
  title: string;
  desc: string;
};
type StayMediaItem = {
  id: string;
  title: string;
  note: string;
  date?: string;
};
type StayWithDuData = {
  timeline: StayTimelineNode[];
  moviesTodo: StayMediaItem[];
  moviesDone: StayMediaItem[];
  booksTodo: StayMediaItem[];
  booksDone: StayMediaItem[];
};
type StayWithDuCollection = keyof StayWithDuData;
type CoReadTheme = "light" | "dark" | "paper";
type CoReadMessage = {
  id: string;
  role: "user" | "du";
  text: string;
  createdAt: string;
  status?: "sent" | "pending" | "failed";
};
type CoReadBook = {
  id: string;
  title: string;
  content: string;
  progress: number;
  lastReadAt: string;
  lastSummary: string;
  messages: CoReadMessage[];
};
type CoReadSettings = {
  fontSize: number;
  lineHeight: number;
  marginLevel: number;
  theme: CoReadTheme;
};
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

const TRANSPARENT_BUBBLE_CLASS =
  "bg-gradient-to-br from-white/40 via-white/20 to-white/5 border border-white/50 text-gray-800 shadow-[inset_0_1px_1px_rgba(255,255,255,0.4),0_4px_20px_rgba(0,0,0,0.05)] backdrop-blur-sm";
const STAY_SERIF_FONT = "'Playfair Display', 'Noto Serif SC', 'Songti SC', Georgia, serif";
const STAY_SANS_FONT = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const CO_READ_BOOKS_KEY = "miniapp.coRead.books.v1";
const CO_READ_SETTINGS_KEY = "miniapp.coRead.settings.v1";
const SYSTEM_CARD_PREFIX = "<<<SUMITALK_CARD ";
const SYSTEM_CARD_SUFFIX = ">>>";
const SUMITALK_CHAT_JOB_POLL_MS = 1800;
const SUMITALK_CHAT_JOB_TIMEOUT_MS = 10 * 60 * 1000;

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

function emptyStayWithDuData(): StayWithDuData {
  return {
    timeline: [],
    moviesTodo: [],
    moviesDone: [],
    booksTodo: [],
    booksDone: [],
  };
}

function sanitizeStayTimeline(raw: any): StayTimelineNode[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => ({
      id: String(item?.id || `node_${Date.now()}`),
      date: String(item?.date || ""),
      title: String(item?.title || "").trim(),
      desc: String(item?.desc || "").trim(),
    }))
    .filter((item) => item.title);
}

function sanitizeStayMedia(raw: any): StayMediaItem[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => ({
      id: String(item?.id || `item_${Date.now()}`),
      title: String(item?.title || "").trim(),
      note: String(item?.note || "").trim(),
      date: item?.date ? String(item.date) : undefined,
    }))
    .filter((item) => item.title);
}

function normalizeStayWithDuData(raw: any): StayWithDuData {
  return {
    timeline: sanitizeStayTimeline(raw?.timeline),
    moviesTodo: sanitizeStayMedia(raw?.moviesTodo),
    moviesDone: sanitizeStayMedia(raw?.moviesDone),
    booksTodo: sanitizeStayMedia(raw?.booksTodo),
    booksDone: sanitizeStayMedia(raw?.booksDone),
  };
}

function formatStayDate(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function makeStayItemId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function makeCoReadId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function emptyCoReadSettings(): CoReadSettings {
  return {
    fontSize: 18,
    lineHeight: 1.8,
    marginLevel: 2,
    theme: "light",
  };
}

function normalizeCoReadTheme(value: any): CoReadTheme {
  return value === "dark" || value === "paper" || value === "light" ? value : "light";
}

function normalizeCoReadMessages(raw: any): CoReadMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => ({
      id: String(item?.id || makeCoReadId("msg")),
      role: item?.role === "user" ? "user" as const : "du" as const,
      text: String(item?.text || "").trim(),
      createdAt: String(item?.createdAt || new Date().toISOString()),
      status: item?.status === "pending" || item?.status === "failed" ? item.status : "sent" as const,
    }))
    .filter((item) => item.text);
}

function normalizeCoReadBooks(raw: any): CoReadBook[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => ({
      id: String(item?.id || makeCoReadId("book")),
      title: String(item?.title || "").trim(),
      content: String(item?.content || ""),
      progress: Math.max(0, Math.min(1, Number(item?.progress || 0))),
      lastReadAt: String(item?.lastReadAt || new Date().toISOString()),
      lastSummary: String(item?.lastSummary || "").trim(),
      messages: normalizeCoReadMessages(item?.messages),
    }))
    .filter((item) => item.title && item.content);
}

function readCoReadBooks(): CoReadBook[] {
  try {
    return normalizeCoReadBooks(JSON.parse(localStorage.getItem(CO_READ_BOOKS_KEY) || "[]"));
  } catch {
    return [];
  }
}

function writeCoReadBooks(books: CoReadBook[]) {
  try {
    localStorage.setItem(CO_READ_BOOKS_KEY, JSON.stringify(books));
  } catch {}
}

function readCoReadSettings(): CoReadSettings {
  const fallback = emptyCoReadSettings();
  try {
    const raw = JSON.parse(localStorage.getItem(CO_READ_SETTINGS_KEY) || "{}");
    return {
      fontSize: clampStoredNumber(Number(raw?.fontSize || fallback.fontSize), 15, 24, fallback.fontSize),
      lineHeight: clampStoredNumber(Number(raw?.lineHeight || fallback.lineHeight), 1.4, 2.2, fallback.lineHeight),
      marginLevel: Math.max(1, Math.min(3, Number(raw?.marginLevel || fallback.marginLevel))),
      theme: normalizeCoReadTheme(raw?.theme),
    };
  } catch {
    return fallback;
  }
}

function writeCoReadSettings(settings: CoReadSettings) {
  try {
    localStorage.setItem(CO_READ_SETTINGS_KEY, JSON.stringify(settings));
  } catch {}
}

function stripTxtExtension(filename: string): string {
  return String(filename || "未命名").replace(/\.[^.]+$/, "").trim() || "未命名";
}

function splitCoReadParagraphs(content: string): string[] {
  return String(content || "")
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}|\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatCoReadDate(value: string): string {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "刚刚";
  const month = date.toLocaleString("en-US", { month: "short" }).toUpperCase();
  const day = String(date.getDate()).padStart(2, "0");
  return `${month} ${day}`;
}

function formatCoReadProgress(progress: number): string {
  return `${Math.round(Math.max(0, Math.min(1, progress)) * 1000) / 10}%`;
}

function compactCoReadText(text: string, max = 52): string {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (value.length <= max) return value;
  return `${value.slice(0, max)}...`;
}

function pickCoReadVisibleText(book: CoReadBook): string {
  const content = String(book.content || "").replace(/\s+/g, " ").trim();
  if (!content) return "";
  const start = Math.max(0, Math.floor(content.length * Math.max(0, Math.min(1, book.progress))) - 160);
  return content.slice(start, start + 420);
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
  const [showCoRead, setShowCoRead] = useState(false);
  const [showTree, setShowTree] = useState(false);
  const [showCallHub, setShowCallHub] = useState(false);
  const [mainTab, setMainTab] = useState<MainTab>("chats");
  const [activeScreen, setActiveScreen] = useState<ChatScreenId>(null);
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
      if (showTree) {
        setShowTree(false);
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
    showDuDay,
    showPersonalization,
    showSchedule,
    showSettings,
    showStayWithDu,
    showTree,
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
            <ListRow icon={<FeatherIcon />} label="个性化" onClick={() => setShowPersonalization(true)} />
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
    showCoRead ||
    showTree ||
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
          <StayWithDuScreen />
        </FullScreenPane>
      ) : null}
      {showCoRead ? <CoReadScreen onBack={() => setShowCoRead(false)} /> : null}
      {showTree ? (
        <FullScreenPane title="树" accent="neutral" onBack={() => setShowTree(false)}>
          <TreeScreen data={tree} onRefresh={loadTree} />
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

function StayWithDuScreen() {
  const toast = useToast();
  const [activeView, setActiveView] = useState<StayWithDuView>("timeline");
  const [data, setData] = useState<StayWithDuData>(() => emptyStayWithDuData());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);
  const [entryType, setEntryType] = useState<StayWithDuEntryType>("node");
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [date, setDate] = useState(() => formatStayDate());

  const load = useCallback(async (showSpinner = false) => {
    if (saving) return;
    if (showSpinner) setLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; data?: StayWithDuData; error?: string }>("/miniapp-api/stay-with-du");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setData(normalizeStayWithDuData(j.data));
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [saving, toast]);

  useEffect(() => {
    void load(true);
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => void load(false), 5000);
    const onVisible = () => {
      if (document.visibilityState === "visible") void load(false);
    };
    const onFocus = () => void load(false);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  const timeline = useMemo(
    () => [...data.timeline].sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))),
    [data.timeline],
  );

  const resetForm = (nextType: StayWithDuEntryType = entryType) => {
    setEntryType(nextType);
    setTitle("");
    setDesc("");
    setDate(formatStayDate());
  };

  const openAddSheet = (nextType?: StayWithDuEntryType) => {
    resetForm(nextType || (activeView === "cinema" ? "movie" : activeView === "library" ? "book" : "node"));
    setAdding(true);
  };

  const entryTypeOptions: Array<{ id: StayWithDuEntryType; label: string }> = [
    { id: "node", label: "Important node" },
    { id: "movie", label: "Movie" },
    { id: "book", label: "Book" },
  ];

  async function saveData(next: StayWithDuData, successText?: string) {
    const prev = data;
    setData(next);
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; data?: StayWithDuData; error?: string }>("/miniapp-api/stay-with-du", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: next }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      setData(normalizeStayWithDuData(j.data || next));
      if (successText) toast(successText);
      return true;
    } catch (e: any) {
      setData(prev);
      toast(`保存失败：${e?.message || e}`);
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function addEntry() {
    const cleanTitle = title.trim();
    if (!cleanTitle || saving) return;
    const cleanDesc = desc.trim();
    const cleanDate = date.trim() || formatStayDate();
    let next: StayWithDuData;
    if (entryType === "movie") {
      next = {
        ...data,
        moviesTodo: [{ id: makeStayItemId("movie"), title: cleanTitle, note: cleanDesc }, ...data.moviesTodo],
      };
    } else if (entryType === "book") {
      next = {
        ...data,
        booksTodo: [{ id: makeStayItemId("book"), title: cleanTitle, note: cleanDesc }, ...data.booksTodo],
      };
    } else {
      next = {
        ...data,
        timeline: [
          { id: makeStayItemId("node"), date: cleanDate, title: cleanTitle, desc: cleanDesc },
          ...data.timeline,
        ],
      };
    }
    const ok = await saveData(next, "已保存");
    if (!ok) return;
    setAdding(false);
    resetForm(entryType);
  }

  async function completeMovie(id: string) {
    if (saving) return;
    const item = data.moviesTodo.find((it) => it.id === id);
    if (!item) return;
    await saveData(
      {
        ...data,
        moviesTodo: data.moviesTodo.filter((it) => it.id !== id),
        moviesDone: [{ ...item, date: formatStayDate() }, ...data.moviesDone],
      },
      "已移到一起看过",
    );
  }

  async function completeBook(id: string) {
    if (saving) return;
    const item = data.booksTodo.find((it) => it.id === id);
    if (!item) return;
    await saveData(
      {
        ...data,
        booksTodo: data.booksTodo.filter((it) => it.id !== id),
        booksDone: [{ ...item, date: formatStayDate() }, ...data.booksDone],
      },
      "已移到一起读过",
    );
  }

  async function deleteStayItem(section: StayWithDuCollection, id: string) {
    if (saving || !id) return;
    await saveData(
      {
        ...data,
        [section]: data[section].filter((item) => item.id !== id),
      } as StayWithDuData,
      "已删除",
    );
  }

  return (
    <div className="-mx-3.5 min-h-full bg-[#FBF8F6] px-5 pb-[126px] pt-5 text-[#3D2B29]" style={{ fontFamily: STAY_SANS_FONT }}>
      <div className="mx-auto max-w-xl">
        <div className="mb-7 flex items-end justify-between gap-4">
          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#C87D60]">stay with du</div>
            <h2 className="text-[30px] font-normal leading-none" style={{ fontFamily: STAY_SERIF_FONT }}>
              our little archive
            </h2>
          </div>
          <div className="rounded-full border border-[#E8D8D0] bg-white/[0.55] px-3 py-1.5 text-[12px] font-medium text-[#8B6F68]">
            {timeline.length} nodes
          </div>
        </div>

        {loading ? <StayEmptyState text="加载中..." /> : null}

        {activeView === "timeline" ? (
          <div className="relative pl-8">
            <div className="absolute bottom-2 left-[11px] top-2 w-px bg-[#E6D2CA]" />
            {timeline.length ? (
              <div className="space-y-7">
                {timeline.map((item) => (
                  <div key={item.id} className="relative pr-10">
                    <div className="absolute -left-[31px] top-1.5 h-[16px] w-[16px] rounded-full border-[3px] border-[#FBF8F6] bg-[#C87D60] shadow-[0_0_0_1px_rgba(200,125,96,0.22)]" />
                    <div className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#C87D60]">{item.date || "Today"}</div>
                    <div className="mt-1 text-[22px] font-normal leading-7 text-[#3D2B29]" style={{ fontFamily: STAY_SERIF_FONT }}>{item.title}</div>
                    {item.desc ? <div className="mt-2 text-[14px] leading-6 text-[#7A625D]">{item.desc}</div> : null}
                    <button
                      type="button"
                      className="absolute right-0 top-0 flex h-8 w-8 items-center justify-center rounded-full text-[#A68B84] transition-colors active:bg-[#EDE1DC] disabled:opacity-40"
                      onClick={() => void deleteStayItem("timeline", item.id)}
                      disabled={saving}
                      aria-label="删除时间线节点"
                      title="删除"
                    >
                      <TrashIconMini />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <StayEmptyState text="重要节点会放在这里。" />
            )}
          </div>
        ) : null}

        {activeView === "cinema" ? (
          <div className="space-y-8">
            <StayMediaSection
              title="Want to watch"
              items={data.moviesTodo}
              emptyText="想看的电影先空着。"
              onComplete={completeMovie}
              onDelete={(id) => void deleteStayItem("moviesTodo", id)}
              disabled={saving}
            />
            <StayMediaSection
              title="Watched together"
              items={data.moviesDone}
              emptyText="一起看过的电影会出现在这里。"
              onDelete={(id) => void deleteStayItem("moviesDone", id)}
              disabled={saving}
              done
            />
          </div>
        ) : null}

        {activeView === "library" ? (
          <div className="space-y-8">
            <StayMediaSection
              title="Want to read"
              items={data.booksTodo}
              emptyText="想一起读的书先空着。"
              onComplete={completeBook}
              onDelete={(id) => void deleteStayItem("booksTodo", id)}
              disabled={saving}
            />
            <StayMediaSection
              title="Read together"
              items={data.booksDone}
              emptyText="一起读完的书会出现在这里。"
              onDelete={(id) => void deleteStayItem("booksDone", id)}
              disabled={saving}
              done
            />
          </div>
        ) : null}
      </div>

      <button
        type="button"
        className="fixed right-5 z-40 flex h-[54px] w-[54px] items-center justify-center rounded-full bg-[#C87D60] text-white shadow-[0_12px_26px_rgba(200,125,96,0.35)] active:scale-95"
        style={{ bottom: "calc(env(safe-area-inset-bottom, 0px) + 88px)" }}
        onClick={() => openAddSheet()}
        disabled={saving}
        aria-label="新增"
      >
        <PlusIcon open={adding} />
      </button>

      <nav
        className="fixed inset-x-0 bottom-0 z-30 border-t border-[#E8D8D0] bg-[#FBF8F6]/95 px-4 pt-2 backdrop-blur-md"
        style={{ paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 10px)" }}
      >
        <div className="mx-auto grid max-w-xl grid-cols-3 gap-2">
          {[
            { id: "timeline" as const, label: "timeline" },
            { id: "cinema" as const, label: "cinema" },
            { id: "library" as const, label: "library" },
          ].map((item) => {
            const active = activeView === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={`rounded-full px-3 py-2.5 text-[12px] font-semibold uppercase tracking-[0.12em] transition-colors ${
                  active ? "bg-[#3D2B29] text-[#FBF8F6]" : "text-[#8B6F68] active:bg-[#EDE1DC]"
                }`}
                onClick={() => setActiveView(item.id)}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </nav>

      {adding ? (
        <div className="fixed inset-0 z-50 flex items-end bg-[#3D2B29]/20 px-4 pt-12 backdrop-blur-sm">
          <form
            className="mx-auto w-full max-w-xl rounded-t-[24px] border border-[#E8D8D0] bg-[#FBF8F6] px-5 pb-[calc(env(safe-area-inset-bottom,0px)+18px)] pt-5 shadow-[0_-16px_42px_rgba(61,43,41,0.18)]"
            onSubmit={(e) => {
              e.preventDefault();
              void addEntry();
            }}
          >
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[15px] font-semibold text-[#3D2B29]">Record memory</div>
              <button
                type="button"
                className="rounded-full px-3 py-1.5 text-[13px] font-medium text-[#8B6F68] active:bg-[#EDE1DC]"
                onClick={() => setAdding(false)}
                disabled={saving}
              >
                取消
              </button>
            </div>
            <div className="mb-4 grid grid-cols-3 gap-2">
              {entryTypeOptions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`rounded-full border px-3 py-2 text-[12px] font-semibold transition-colors ${
                    entryType === item.id
                      ? "border-[#C87D60] bg-[#C87D60] text-white"
                      : "border-[#E8D8D0] bg-white/60 text-[#7A625D]"
                  }`}
                  onClick={() => setEntryType(item.id)}
                  disabled={saving}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="space-y-3">
              <input
                className="h-12 w-full rounded-[16px] border border-[#E8D8D0] bg-white/70 px-4 text-[15px] font-medium text-[#3D2B29] outline-none placeholder:text-[#B59B93] focus:border-[#C87D60]"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={entryType === "node" ? "重要节点" : entryType === "movie" ? "片名" : "书名"}
                disabled={saving}
                style={{ fontFamily: STAY_SERIF_FONT }}
              />
              {entryType === "node" ? (
                <input
                  type="date"
                  className="h-12 w-full rounded-[16px] border border-[#E8D8D0] bg-white/70 px-4 text-[15px] font-medium text-[#3D2B29] outline-none focus:border-[#C87D60]"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  disabled={saving}
                  style={{ fontFamily: STAY_SANS_FONT }}
                />
              ) : null}
              <textarea
                className="min-h-[96px] w-full resize-none rounded-[16px] border border-[#E8D8D0] bg-white/70 px-4 py-3 text-[14px] leading-6 text-[#3D2B29] outline-none placeholder:text-[#B59B93] focus:border-[#C87D60]"
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder="备注"
                disabled={saving}
                style={{ fontFamily: STAY_SERIF_FONT }}
              />
            </div>
            <button
              type="submit"
              className="mt-4 h-12 w-full rounded-full bg-[#3D2B29] text-[14px] font-semibold text-[#FBF8F6] disabled:opacity-40"
              disabled={saving || !title.trim()}
            >
              {saving ? "Saving..." : "Record Memory"}
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function CoReadScreen({ onBack }: { onBack: () => void }) {
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const readerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const pendingTimerRef = useRef<number | null>(null);
  const [books, setBooks] = useState<CoReadBook[]>(() => readCoReadBooks());
  const [activeBookId, setActiveBookId] = useState("");
  const [settings, setSettings] = useState<CoReadSettings>(() => readCoReadSettings());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [selectedText, setSelectedText] = useState("");
  const [selectionToolbar, setSelectionToolbar] = useState<{ x: number; y: number } | null>(null);
  const [chatExpanded, setChatExpanded] = useState(false);

  const activeBook = useMemo(() => books.find((book) => book.id === activeBookId) || null, [activeBookId, books]);
  const paragraphs = useMemo(() => splitCoReadParagraphs(activeBook?.content || ""), [activeBook?.content]);
  const recentMessages = activeBook ? activeBook.messages.slice(-6) : [];
  const visibleMessages = chatExpanded ? recentMessages : recentMessages.slice(-3);
  const theme = settings.theme === "dark"
    ? {
        shell: "bg-[#111111] text-[#F8F8F8]",
        panel: "border-[#2A2A2A] bg-[#171717]",
        soft: "bg-[#1F1F1F] text-[#D8D8D8]",
        muted: "text-[#8C8C8C]",
        input: "border-[#333333] bg-[#181818] text-[#F8F8F8] placeholder:text-[#777777]",
        dock: "border-[#2A2A2A] bg-[#111111]/95",
      }
    : settings.theme === "paper"
      ? {
          shell: "bg-[#F4F1EA] text-[#352D28]",
          panel: "border-[#E1D8CC] bg-[#FBF8F1]",
          soft: "bg-[#ECE4D8] text-[#6E5B4E]",
          muted: "text-[#8A786B]",
          input: "border-[#DED2C2] bg-[#FFFDF8] text-[#352D28] placeholder:text-[#A9998B]",
          dock: "border-[#DED2C2] bg-[#F4F1EA]/95",
        }
      : {
          shell: "bg-white text-[#111111]",
          panel: "border-[#EAEAEA] bg-white",
          soft: "bg-[#F7F7F7] text-[#555555]",
          muted: "text-[#888888]",
          input: "border-[#EAEAEA] bg-white text-[#111111] placeholder:text-[#A0A0A0]",
          dock: "border-[#EAEAEA] bg-white/95",
        };
  const readerPadding = settings.marginLevel === 1 ? "px-5" : settings.marginLevel === 3 ? "px-8" : "px-6";

  useEffect(() => {
    return () => {
      if (pendingTimerRef.current) window.clearTimeout(pendingTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!activeBookId || !activeBook) return;
    requestAnimationFrame(() => {
      const el = readerRef.current;
      if (!el) return;
      const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
      el.scrollTo({ top: maxScroll * Math.max(0, Math.min(1, activeBook.progress)), behavior: "auto" });
    });
  }, [activeBookId]);

  function setBooksAndPersist(nextBooks: CoReadBook[] | ((prev: CoReadBook[]) => CoReadBook[])) {
    setBooks((prev) => {
      const next = typeof nextBooks === "function" ? nextBooks(prev) : nextBooks;
      writeCoReadBooks(next);
      return next;
    });
  }

  function updateSettings(nextSettings: CoReadSettings | ((prev: CoReadSettings) => CoReadSettings)) {
    setSettings((prev) => {
      const next = typeof nextSettings === "function" ? nextSettings(prev) : nextSettings;
      writeCoReadSettings(next);
      return next;
    });
  }

  function updateActiveBook(updater: (book: CoReadBook) => CoReadBook) {
    if (!activeBook) return;
    setBooksAndPersist((prev) => prev.map((book) => (book.id === activeBook.id ? updater(book) : book)));
  }

  async function importTxtFile(file?: File | null) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".txt") && file.type && file.type !== "text/plain") {
      toast("只能导入 TXT");
      return;
    }
    try {
      const content = await file.text();
      const clean = content.replace(/\u0000/g, "").trim();
      if (!clean) throw new Error("文件里没有可读内容");
      const now = new Date().toISOString();
      const book: CoReadBook = {
        id: makeCoReadId("book"),
        title: stripTxtExtension(file.name),
        content: clean,
        progress: 0,
        lastReadAt: now,
        lastSummary: "还没有共读记录。",
        messages: [],
      };
      setBooksAndPersist((prev) => [book, ...prev]);
      setActiveBookId(book.id);
      setSelectedText("");
      setSelectionToolbar(null);
      toast("已导入");
    } catch (e: any) {
      toast(`导入失败：${e?.message || e}`);
    }
  }

  function deleteBook(bookId: string) {
    const target = books.find((book) => book.id === bookId);
    if (!target) return;
    if (!window.confirm(`删除《${target.title}》？`)) return;
    setBooksAndPersist((prev) => prev.filter((book) => book.id !== bookId));
    if (activeBookId === bookId) setActiveBookId("");
    toast("已删除");
  }

  function handleReaderScroll() {
    const el = readerRef.current;
    if (!el || !activeBook) return;
    const maxScroll = Math.max(1, el.scrollHeight - el.clientHeight);
    const nextProgress = Math.max(0, Math.min(1, el.scrollTop / maxScroll));
    if (Math.abs(nextProgress - activeBook.progress) < 0.015) return;
    updateActiveBook((book) => ({
      ...book,
      progress: nextProgress,
      lastReadAt: new Date().toISOString(),
    }));
  }

  function captureSelection() {
    const selection = window.getSelection();
    const text = String(selection?.toString() || "").replace(/\s+/g, " ").trim();
    if (!selection || text.length < 2 || selection.rangeCount < 1) {
      setSelectionToolbar(null);
      return;
    }
    const rect = selection.getRangeAt(0).getBoundingClientRect();
    setSelectedText(text.slice(0, 1200));
    setSelectionToolbar({
      x: Math.max(16, Math.min(window.innerWidth - 148, rect.left + rect.width / 2 - 74)),
      y: Math.max(90, rect.top - 46),
    });
  }

  function focusCoReadInput() {
    setChatExpanded(true);
    setSelectionToolbar(null);
    inputRef.current?.focus();
  }

  function copySelectedText() {
    if (!selectedText) return;
    navigator.clipboard.writeText(selectedText).then(
      () => toast("已复制"),
      () => toast("复制失败"),
    );
    setSelectionToolbar(null);
  }

  function sendCoReadMessage() {
    if (!activeBook) return;
    const cleanInput = input.trim();
    const context = selectedText || pickCoReadVisibleText(activeBook);
    if (!cleanInput && !context) {
      toast("先选一段或写一句");
      return;
    }
    const now = Date.now();
    const userText = cleanInput || "想和渡聊这一段";
    const pendingId = makeCoReadId("du");
    const userMessage: CoReadMessage = {
      id: makeCoReadId("user"),
      role: "user",
      text: userText,
      createdAt: new Date(now).toISOString(),
      status: "sent",
    };
    const pendingMessage: CoReadMessage = {
      id: pendingId,
      role: "du",
      text: "渡在看这一段...",
      createdAt: new Date(now + 1).toISOString(),
      status: "pending",
    };
    setInput("");
    setChatExpanded(true);
    setSelectionToolbar(null);
    updateActiveBook((book) => ({
      ...book,
      messages: [...book.messages, userMessage, pendingMessage],
      lastReadAt: new Date(now).toISOString(),
    }));
    if (pendingTimerRef.current) window.clearTimeout(pendingTimerRef.current);
    pendingTimerRef.current = window.setTimeout(() => {
      const snippet = compactCoReadText(context, 46);
      const reply = snippet
        ? `我看到这一段了。这里可以先抓住「${snippet}」这个点，后面我们就沿着它往下聊。`
        : "我在这本书里跟上你了，继续问我就行。";
      setBooks((prev) => {
        const next = prev.map((book) => {
          if (book.id !== activeBook.id) return book;
          return {
            ...book,
            lastSummary: `渡：${compactCoReadText(reply, 64)}`,
            messages: book.messages.map((msg) => (
              msg.id === pendingId
                ? { ...msg, text: reply, status: "sent" as const }
                : msg
            )),
          };
        });
        writeCoReadBooks(next);
        return next;
      });
    }, 700);
  }

  if (activeBook) {
    return (
      <div className={`absolute inset-0 z-30 flex flex-col overflow-hidden ${theme.shell}`}>
        <header className={`z-20 flex items-center border-b px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)] ${theme.dock}`}>
          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-full transition-colors active:bg-black/5"
            onClick={() => {
              setActiveBookId("");
              setSelectedText("");
              setSelectionToolbar(null);
            }}
            aria-label="返回书架"
          >
            <ChevronLeftIcon />
          </button>
          <div className="min-w-0 flex-1 text-center">
            <div className="truncate text-[13px] font-semibold">{activeBook.title}</div>
            <div className={`mt-0.5 text-[11px] font-mono ${theme.muted}`}>{formatCoReadProgress(activeBook.progress)}</div>
          </div>
          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-full transition-colors active:bg-black/5"
            onClick={() => setSettingsOpen(true)}
            aria-label="阅读设置"
          >
            <SettingsIconMini />
          </button>
        </header>

        <div
          ref={readerRef}
          className={`min-h-0 flex-1 overflow-y-auto ${readerPadding} pb-[224px] pt-5`}
          onScroll={handleReaderScroll}
          onMouseUp={captureSelection}
          onTouchEnd={() => window.setTimeout(captureSelection, 80)}
          style={{ fontSize: `${settings.fontSize}px`, lineHeight: settings.lineHeight }}
        >
          <div className="mx-auto max-w-[720px] text-justify">
            {paragraphs.map((paragraph, index) => (
              <p key={`${index}-${paragraph.slice(0, 12)}`} className="mb-5">
                {paragraph}
              </p>
            ))}
          </div>
        </div>

        {selectionToolbar ? (
          <div
            className="fixed z-50 flex items-center gap-3 rounded-[14px] bg-[#111111] px-4 py-2 text-[13px] font-semibold text-white shadow-[0_12px_28px_rgba(0,0,0,0.25)]"
            style={{ left: selectionToolbar.x, top: selectionToolbar.y }}
          >
            <button type="button" onClick={focusCoReadInput}>共读</button>
            <div className="h-4 w-px bg-white/25" />
            <button type="button" onClick={copySelectedText}>复制</button>
          </div>
        ) : null}

        <div className={`fixed inset-x-0 bottom-0 z-40 border-t px-5 pt-3 backdrop-blur-md ${theme.dock}`} style={{ paddingBottom: "calc(env(safe-area-inset-bottom,0px)+14px)" }}>
          {selectedText ? (
            <div className={`mb-2 flex items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-medium ${theme.soft}`}>
              <span className="min-w-0 flex-1 truncate">已选中：{compactCoReadText(selectedText, 42)}</span>
              <button type="button" className="shrink-0" onClick={() => setSelectedText("")}>清除</button>
            </div>
          ) : null}
          {visibleMessages.length ? (
            <button
              type="button"
              className="mb-3 flex max-h-[128px] w-full flex-col gap-2 overflow-hidden text-left"
              onClick={() => setChatExpanded((prev) => !prev)}
            >
              {visibleMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={`max-w-[86%] rounded-[14px] px-3 py-2 text-[13px] leading-5 ${
                    msg.role === "user"
                      ? "self-end rounded-br-[5px] bg-[#111111] text-white"
                      : msg.status === "pending"
                        ? `self-start bg-transparent px-0 font-mono ${theme.muted}`
                        : `self-start rounded-bl-[5px] ${theme.soft}`
                  }`}
                >
                  {msg.text}
                </div>
              ))}
            </button>
          ) : null}
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              className={`h-11 min-w-0 flex-1 rounded-full border px-4 text-[14px] font-medium outline-none ${theme.input}`}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="和渡聊这段"
              onKeyDown={(e) => {
                if (e.key === "Enter") sendCoReadMessage();
              }}
            />
            <button
              type="button"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#111111] text-white transition-transform active:scale-95 disabled:opacity-40"
              onClick={sendCoReadMessage}
              disabled={!input.trim() && !selectedText}
              aria-label="发送"
            >
              <SendIconMini />
            </button>
          </div>
        </div>

        {settingsOpen ? (
          <div className="fixed inset-0 z-50 flex items-end bg-black/10" onClick={() => setSettingsOpen(false)}>
            <div
              className={`w-full rounded-t-[28px] border px-6 pb-[calc(env(safe-area-inset-bottom,0px)+26px)] pt-6 shadow-[0_-16px_42px_rgba(0,0,0,0.12)] ${theme.panel}`}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-5 flex items-center justify-between">
                <div className="text-[15px] font-semibold">阅读设置</div>
                <button type="button" className={`rounded-full px-3 py-1.5 text-[13px] ${theme.muted}`} onClick={() => setSettingsOpen(false)}>完成</button>
              </div>
              <div className="space-y-6">
                <section>
                  <div className={`mb-3 font-mono text-[11px] uppercase tracking-[0.12em] ${theme.muted}`}>typography</div>
                  <div className="grid grid-cols-2 gap-3">
                    <button type="button" className={`h-11 rounded-full border text-[13px] font-semibold ${theme.panel}`} onClick={() => updateSettings((prev) => ({ ...prev, fontSize: Math.max(15, prev.fontSize - 1) }))}>- A</button>
                    <button type="button" className={`h-11 rounded-full border text-[13px] font-semibold ${theme.panel}`} onClick={() => updateSettings((prev) => ({ ...prev, fontSize: Math.min(24, prev.fontSize + 1) }))}>A +</button>
                  </div>
                </section>
                <section>
                  <div className={`mb-3 font-mono text-[11px] uppercase tracking-[0.12em] ${theme.muted}`}>theme</div>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { id: "light" as const, label: "LIGHT", cls: "bg-white text-black" },
                      { id: "dark" as const, label: "DARK", cls: "bg-[#111] text-white" },
                      { id: "paper" as const, label: "PAPER", cls: "bg-[#F4F1EA] text-[#433]" },
                    ].map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={`h-12 rounded-[14px] border font-mono text-[11px] ${item.cls} ${settings.theme === item.id ? "ring-2 ring-[#111111]" : ""}`}
                        onClick={() => updateSettings((prev) => ({ ...prev, theme: item.id }))}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </section>
                <section>
                  <div className={`mb-3 font-mono text-[11px] uppercase tracking-[0.12em] ${theme.muted}`}>spacing</div>
                  <PersonalizationSliderRow
                    title="行距"
                    value={String(settings.lineHeight.toFixed(1))}
                    min={1.4}
                    max={2.2}
                    step={0.1}
                    currentValue={settings.lineHeight}
                    onChange={(next) => updateSettings((prev) => ({ ...prev, lineHeight: next }))}
                  />
                  <div className="mt-4 grid grid-cols-3 gap-2">
                    {[1, 2, 3].map((level) => (
                      <button
                        key={level}
                        type="button"
                        className={`h-9 rounded-full border text-[12px] font-semibold ${settings.marginLevel === level ? "bg-[#111111] text-white" : theme.panel}`}
                        onClick={() => updateSettings((prev) => ({ ...prev, marginLevel: level }))}
                      >
                        边距 {level}
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="absolute inset-0 z-30 flex flex-col overflow-hidden bg-white text-[#111111]">
      <header className="z-20 flex items-center gap-2 border-b border-[#F1F1F1] bg-white px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)]">
        <button type="button" className="flex h-11 w-11 items-center justify-center rounded-full transition-colors active:bg-gray-50" onClick={onBack} aria-label="返回">
          <ChevronLeftIcon />
        </button>
        <div className="flex-1 text-[22px] font-bold">和渡一起读</div>
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-full bg-[#111111] text-white transition-transform active:scale-95"
          onClick={() => fileInputRef.current?.click()}
          aria-label="导入 TXT"
        >
          <PlusIcon open={false} />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-[112px] pt-5">
        {books.length ? (
          <div className="mx-auto max-w-xl space-y-4">
            {books.map((book) => (
              <button
                key={book.id}
                type="button"
                className="w-full rounded-[24px] border border-[#EAEAEA] bg-white p-5 text-left shadow-[0_8px_24px_rgba(0,0,0,0.025)] transition-transform active:scale-[0.99]"
                onClick={() => {
                  setActiveBookId(book.id);
                  setSelectedText("");
                  setSelectionToolbar(null);
                  setChatExpanded(false);
                }}
              >
                <div className="mb-5 flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 text-[18px] font-semibold uppercase leading-6">{book.title}</div>
                  <div className="font-mono text-[11px] lowercase text-[#AAAAAA]">txt</div>
                </div>
                <div className="mb-5 flex items-center gap-6">
                  <div>
                    <div className="mb-1 font-mono text-[11px] lowercase tracking-[0.05em] text-[#AAAAAA]">progress</div>
                    <div className="font-mono text-[16px] font-medium">{formatCoReadProgress(book.progress)}</div>
                  </div>
                  <div className="h-8 w-px bg-black/10" />
                  <div>
                    <div className="mb-1 font-mono text-[11px] lowercase tracking-[0.05em] text-[#AAAAAA]">last read</div>
                    <div className="font-mono text-[16px] font-medium">{formatCoReadDate(book.lastReadAt)}</div>
                  </div>
                  <button
                    type="button"
                    className="ml-auto flex h-9 w-9 items-center justify-center rounded-full text-[#9A9A9A] transition-colors active:bg-gray-50"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteBook(book.id);
                    }}
                    aria-label="删除"
                  >
                    <TrashIconMini />
                  </button>
                </div>
                <div className="line-clamp-2 text-[13px] leading-5 text-[#777777]">{book.lastSummary || "还没有共读记录。"}</div>
              </button>
            ))}
          </div>
        ) : (
          <div className="flex min-h-[58vh] flex-col items-center justify-center text-center">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-[#F7F7F7] text-[#777777]">
              <BookOpenIcon />
            </div>
            <div className="text-[16px] font-semibold text-[#111111]">还没有导入的书</div>
            <div className="mt-2 max-w-[240px] text-[13px] leading-5 text-[#888888]">先放一本 TXT 进来，再和渡一起读。</div>
          </div>
        )}
      </div>

      <button
        type="button"
        className="fixed inset-x-5 bottom-[calc(env(safe-area-inset-bottom,0px)+20px)] z-40 h-14 rounded-full bg-[#111111] font-mono text-[12px] font-semibold uppercase tracking-[0.08em] text-white shadow-[0_12px_26px_rgba(0,0,0,0.18)] active:scale-[0.99]"
        onClick={() => fileInputRef.current?.click()}
      >
        导入 TXT 资料
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".txt,text/plain"
        className="hidden"
        onChange={(e) => {
          void importTxtFile(e.target.files?.[0]);
          e.currentTarget.value = "";
        }}
      />
    </div>
  );
}

function StayMediaSection({
  title,
  items,
  emptyText,
  done = false,
  onComplete,
  onDelete,
  disabled = false,
}: {
  title: string;
  items: StayMediaItem[];
  emptyText: string;
  done?: boolean;
  onComplete?: (id: string) => void;
  onDelete?: (id: string) => void;
  disabled?: boolean;
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[13px] font-semibold uppercase tracking-[0.18em] text-[#C87D60]">{title}</h3>
        <span className="text-[12px] font-medium text-[#A68B84]">{items.length}</span>
      </div>
      {items.length ? (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex min-h-[74px] items-start gap-3 rounded-[18px] border border-[#E8D8D0] bg-white/[0.62] px-4 py-3 shadow-[0_8px_22px_rgba(61,43,41,0.04)]"
            >
              <input
                type="checkbox"
                className="mt-1 h-5 w-5 shrink-0 accent-[#C87D60]"
                checked={done}
                readOnly={done}
                disabled={disabled}
                onChange={() => {
                  if (!done) onComplete?.(item.id);
                }}
              />
              <span className="min-w-0 flex-1">
                <span
                  className={`block text-[18px] font-normal leading-6 ${done ? "text-[#7A625D] line-through decoration-[#A68B84] decoration-1" : "text-[#3D2B29]"}`}
                  style={{ fontFamily: STAY_SERIF_FONT }}
                >
                  {item.title}
                </span>
                {item.note ? <span className="mt-1 block text-[13px] leading-5 text-[#8B6F68]">{item.note}</span> : null}
                {item.date ? <span className="mt-2 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[#C87D60]">{item.date}</span> : null}
              </span>
              <button
                type="button"
                className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#A68B84] transition-colors active:bg-[#EDE1DC] disabled:opacity-40"
                onClick={() => onDelete?.(item.id)}
                disabled={disabled}
                aria-label={`删除 ${item.title}`}
                title="删除"
              >
                <TrashIconMini />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <StayEmptyState text={emptyText} />
      )}
    </section>
  );
}

function StayEmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[18px] border border-dashed border-[#E8D8D0] px-4 py-5 text-[13px] leading-6 text-[#8B6F68]">
      {text}
    </div>
  );
}

function contentToPlainText(content: any): string {
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part.trim();
        if (!part || typeof part !== "object") return "";
        if (part.type === "text" || part.type === "output_text" || part.type === "input_text") {
          if (typeof part.text === "string") return String(part.text || "").trim();
          if (part.text && typeof part.text === "object" && typeof part.text.value === "string") {
            return String(part.text.value || "").trim();
          }
        }
        if (typeof part.content === "string") return String(part.content || "").trim();
        if (part.type === "image_url") return "[图片]";
        return "";
      })
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  if (content && typeof content === "object") {
    if (typeof content.text === "string") return String(content.text || "").trim();
    if (content.text && typeof content.text === "object" && typeof content.text.value === "string") {
      return String(content.text.value || "").trim();
    }
    if (typeof content.content === "string") return String(content.content || "").trim();
    if (Array.isArray(content.content)) return contentToPlainText(content.content);
  }
  return "";
}

function extractLegacyMessageField(msg: any, keys: string[]): any {
  if (!msg || typeof msg !== "object") return "";
  for (const key of keys) {
    const value = (msg as any)?.[key];
    if (value == null) continue;
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value) && value.length) return value;
    if (value && typeof value === "object") return value;
  }
  return "";
}

function extractMessageContentSource(msg: any): any {
  if (msg == null) return "";
  if (typeof msg === "string") return msg;
  return extractLegacyMessageField(msg, [
    "content",
    "text",
    "message",
    "body",
    "value",
    "reply",
    "response",
    "markdown",
    "html",
    "parts",
  ]);
}

function extractMessageReasoningSource(msg: any): any {
  if (!msg || typeof msg !== "object") return "";
  return extractLegacyMessageField(msg, [
    "reasoning",
    "reasoningContent",
    "reasoning_content",
    "thinking",
    "thoughts",
  ]);
}

function fallbackRawContentText(content: any): string {
  if (content == null) return "";
  if (typeof content === "string") return content.trim();
  if (typeof content === "number" || typeof content === "boolean") return String(content).trim();
  try {
    const raw = JSON.stringify(content);
    return typeof raw === "string" ? raw.trim() : "";
  } catch {
    return "";
  }
}

function extractAssistantMessage(data: any): any {
  const choice = Array.isArray(data?.choices) ? data.choices[0] : null;
  if (choice?.message) return choice.message;
  if (data?.message && typeof data.message === "object") return data.message;
  return {};
}

function extractAssistantReplyText(data: any): string {
  const msg = extractAssistantMessage(data);
  return contentToPlainText(msg?.content) || contentToPlainText(data?.content) || "";
}

function extractAssistantReasoning(data: any): string {
  const msg = extractAssistantMessage(data);
  return contentToPlainText(extractMessageReasoningSource(msg));
}

function extractTokenCount(data: any): { input?: number; output?: number } | undefined {
  const usage = data?.usage || {};
  const input = Number(usage?.prompt_tokens || usage?.input_tokens || usage?.promptTokens || usage?.inputTokens || 0);
  const output = Number(usage?.completion_tokens || usage?.output_tokens || usage?.completionTokens || usage?.outputTokens || 0);
  const safeInput = Number.isFinite(input) && input > 0 ? input : 0;
  const safeOutput = Number.isFinite(output) && output > 0 ? output : 0;
  if (!safeInput && !safeOutput) return undefined;
  return {
    input: safeInput || undefined,
    output: safeOutput || undefined,
  };
}

type ChatMessageGroup = {
  id: string;
  role: "user" | "assistant";
  createdAt: string;
  lastCreatedAt: string;
  parts: Array<{ content: string; render: "plain" | "rich" | "html"; reasoning?: string; tokenCount?: { input?: number; output?: number }; systemCard?: SumiTalkSystemCard | null }>;
};

type ChatSearchMatch = {
  id: string;
  groupId: string;
  partIndex: number;
};

function getChatSearchMatchId(groupId: string, partIndex: number): string {
  return `${groupId}::${partIndex}`;
}

function formatClockTime(value: string, timeFormat: ChatTimeFormat = "hhmm"): string {
  const raw = String(value || "").trim();
  if (!raw) return "最近";
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) {
    const m = raw.match(/(\d{2}):(\d{2})/);
    if (!m) return "最近";
    if (timeFormat === "ampm") {
      const hour = Number(m[1]);
      const period = hour >= 12 ? "下午" : "上午";
      const displayHour = String(hour % 12 || 12).padStart(2, "0");
      return `${period} ${displayHour}:${m[2]}`;
    }
    return `${m[1]}:${m[2]}`;
  }
  const hh = String(dt.getHours()).padStart(2, "0");
  const mm = String(dt.getMinutes()).padStart(2, "0");
  if (timeFormat === "ampm") {
    const hour = dt.getHours();
    const period = hour >= 12 ? "下午" : "上午";
    return `${period} ${String(hour % 12 || 12).padStart(2, "0")}:${mm}`;
  }
  return `${hh}:${mm}`;
}

function getChatFontLabel(fontKey: ChatFontKey): string {
  if (fontKey === "system") return "系统默认";
  if (fontKey === "pingfang") return "苹方";
  return "微软雅黑";
}

function shouldShowGroupTime(current: string, previous?: string): boolean {
  const cur = new Date(String(current || ""));
  if (Number.isNaN(cur.getTime())) return !previous;
  if (!previous) return true;
  const prev = new Date(String(previous || ""));
  if (Number.isNaN(prev.getTime())) return true;
  const dayChanged =
    cur.getFullYear() !== prev.getFullYear() ||
    cur.getMonth() !== prev.getMonth() ||
    cur.getDate() !== prev.getDate();
  if (dayChanged) return true;
  return cur.getTime() - prev.getTime() >= 5 * 60 * 1000;
}

function pickLatestDraftPreview(messages: ChatDraftMessage[]): { preview: string; time: string } {
  const list = Array.isArray(messages) ? messages : [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const msg = list[i];
    if (msg?.role === "assistant" && String(msg?.status || "").trim().toLowerCase() === "pending") continue;
    const text = String(msg?.content || "").trim();
    if (!text) continue;
    const systemCard = firstSystemCard(text);
    if (systemCard?.type === "system_alarm_created") {
      return {
        preview: `已创建 ${formatAlarmTime(systemCard.hour, systemCard.minute)} 系统闹钟`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "calendar_event_created") {
      return {
        preview: `已创建系统行程：${systemCard.title}`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "travel_plan_form") {
      return {
        preview: `填写${systemCard.title || "出行规划"}表单`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "travel_plan_result") {
      return {
        preview: `${systemCard.title || "渡安排好了"}：${(systemCard.destinations || []).join("、") || "路线"}`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "travel_transport_detail") {
      return {
        preview: `${systemCard.title || "这段怎么走"}：${systemCard.from} 到 ${systemCard.to}`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "travel_food_detail") {
      return {
        preview: `${systemCard.title || "附近吃这些"}：${systemCard.placeName || systemCard.keywords || "吃喝"}`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    return {
      preview: text,
      time: formatClockTime(String(msg?.createdAt || "").trim()),
    };
  }
  return { preview: "主会话", time: "主会话" };
}

function isHtmlBlock(content: string): boolean {
  const raw = String(content || "").trim();
  if (!raw) return false;
  return /<\/?[a-z][\s\S]*>/i.test(raw);
}

function isCodeBlock(content: string): boolean {
  const raw = String(content || "").trim();
  if (!raw) return false;
  return /```[\s\S]*```/.test(raw) || /^( {4}|\t).+/m.test(raw);
}

function hasMarkdownSyntax(content: string): boolean {
  const raw = String(content || "").trim();
  if (!raw) return false;
  // Only treat as markdown when explicit syntax appears.
  return /(^|\n)\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|>\s)|```|`[^`\n]+`|\[.+?\]\(.+?\)|\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|\|.+\|/.test(raw);
}

function detectMessageRender(role: "user" | "assistant", content: string): "plain" | "rich" | "html" {
  const raw = String(content || "").replace(/\r/g, "").trim();
  if (!raw) return "plain";
  if (role === "user") return "plain";
  if (isHtmlBlock(raw)) return "html";
  if (isCodeBlock(raw)) return "rich";
  if (hasMarkdownSyntax(raw)) return "rich";
  return "plain";
}

function stripInlineBase64Images(content: string): string {
  const raw = String(content || "");
  if (!raw) return "";
  return raw.replace(/data:image\/[a-zA-Z0-9.+-]+;base64,[a-zA-Z0-9+/=\s]+/g, "[图片base64已省略，请改用图片URL]");
}

function historyRenderableScore(messages: ChatDraftMessage[]): number {
  const list = Array.isArray(messages) ? messages : [];
  return list.reduce((score, msg) => {
    const content = String(msg?.content || "").trim();
    const reasoning = String(msg?.reasoning || "").trim();
    if (content) return score + 2;
    if (reasoning) return score + 1;
    return score;
  }, 0);
}

function parseChatMessageTime(value: string): number {
  const raw = String(value || "").trim();
  if (!raw) return 0;
  const ts = Date.parse(raw);
  if (Number.isFinite(ts)) return ts;
  const m = raw.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?([+-]\d{2}:?\d{2})?$/);
  if (!m) return 0;
  const normalized = `${m[1]}T${m[2]}${m[3] || "+08:00"}`;
  const next = Date.parse(normalized);
  return Number.isFinite(next) ? next : 0;
}

function latestHistoryTimestamp(messages: ChatDraftMessage[]): number {
  const list = Array.isArray(messages) ? messages : [];
  return list.reduce((latest, msg) => {
    if (msg?.role === "assistant" && String(msg?.status || "").trim().toLowerCase() === "pending") {
      return latest;
    }
    const ts = parseChatMessageTime(String(msg?.createdAt || ""));
    return ts > latest ? ts : latest;
  }, 0);
}

function sortHistoryMessages(messages: ChatDraftMessage[]): ChatDraftMessage[] {
  const list = Array.isArray(messages) ? [...messages] : [];
  list.sort((a, b) => {
    const diff = parseChatMessageTime(String(a?.createdAt || "")) - parseChatMessageTime(String(b?.createdAt || ""));
    if (diff !== 0) return diff;
    const roleA = String(a?.role || "").trim().toLowerCase();
    const roleB = String(b?.role || "").trim().toLowerCase();
    if (roleA !== roleB) {
      if (roleA === "user") return -1;
      if (roleB === "user") return 1;
    }
    return String(a?.id || "").localeCompare(String(b?.id || ""));
  });
  return list;
}

function pickBetterHistory(primary: ChatDraftMessage[], fallback: ChatDraftMessage[], seed: ChatDraftMessage[]): ChatDraftMessage[] {
  const primaryScore = historyRenderableScore(primary);
  const fallbackScore = historyRenderableScore(fallback);
  const primaryLatest = latestHistoryTimestamp(primary);
  const fallbackLatest = latestHistoryTimestamp(fallback);
  if (primaryScore <= 0 && fallbackScore <= 0) return seed;
  if (fallbackLatest > primaryLatest) return fallback.length ? fallback : (primary.length ? primary : seed);
  if (primaryLatest > fallbackLatest) return primary.length ? primary : (fallback.length ? fallback : seed);
  if (fallbackScore > primaryScore) return fallback.length ? fallback : (primary.length ? primary : seed);
  return primary.length ? primary : (fallback.length ? fallback : seed);
}

function sanitizeHistoryMessages(messages: ChatDraftMessage[]): ChatDraftMessage[] {
  const list = Array.isArray(messages) ? messages : [];
  return sortHistoryMessages(list.map((msg) => {
      const rawContent = extractMessageContentSource(msg);
      const rawReasoning = extractMessageReasoningSource(msg);
      const normalizedRole = String(msg?.role || "").trim().toLowerCase();
      const reasoning = contentToPlainText(rawReasoning) || fallbackRawContentText(rawReasoning);
      const rawStatus = String((msg as any)?.status || "").trim().toLowerCase();
      const status = rawStatus === "pending" || rawStatus === "sent" || rawStatus === "failed"
        ? rawStatus as ChatDraftMessage["status"]
        : undefined;
      const content = status === "pending" && normalizedRole === "assistant"
        ? ""
        : stripInlineBase64Images(contentToPlainText(rawContent) || fallbackRawContentText(rawContent));
      let tokenCount: { input?: number; output?: number } | undefined;
      if (msg?.tokenCount && typeof msg.tokenCount === "object") {
        const input = Number(msg.tokenCount.input || 0);
        const output = Number(msg.tokenCount.output || 0);
        tokenCount = {
          input: Number.isFinite(input) && input > 0 ? input : undefined,
          output: Number.isFinite(output) && output > 0 ? output : undefined,
        };
      } else {
        const legacyCount = Number((msg as any)?.tokenCount || 0);
        if (Number.isFinite(legacyCount) && legacyCount > 0) {
          tokenCount = { output: legacyCount };
        }
      }
      return {
        ...msg,
        content,
        status,
        clientRequestId: String((msg as any)?.clientRequestId || "").trim() || undefined,
        jobId: String((msg as any)?.jobId || "").trim() || undefined,
        reasoning: reasoning || undefined,
        tokenCount,
      };
    }));
}

function groupChatMessages(messages: ChatDraftMessage[]): ChatMessageGroup[] {
  const groups: ChatMessageGroup[] = [];
  for (const msg of messages) {
    if (msg?.role === "assistant" && String(msg?.status || "").trim().toLowerCase() === "pending") continue;
    const normalizedContent = String(msg?.content || "").trim();
    const normalizedReasoning = String(msg?.reasoning || "").trim();
    if (!normalizedContent && !normalizedReasoning) continue;
    const segments = msg.role === "assistant"
      ? splitSystemCardSegments(normalizedContent)
      : [{ content: normalizedContent, systemCard: null }];
    const safeParts = (segments.length ? segments : [{ content: normalizedContent, systemCard: null }])
      .filter((segment) => String(segment.content || "").trim() || segment.systemCard || normalizedReasoning)
      .map((segment, index) => ({
        content: String(segment.content || "").trim(),
        render: segment.systemCard ? "plain" as const : detectMessageRender(msg.role, String(segment.content || "").trim()),
        reasoning: index === 0 ? normalizedReasoning || undefined : undefined,
        tokenCount: index === 0 ? msg.tokenCount : undefined,
        systemCard: segment.systemCard,
      }));
    const last = groups[groups.length - 1];
    if (last && last.role === msg.role && !shouldShowGroupTime(msg.createdAt, last.lastCreatedAt)) {
      last.parts.push(...safeParts);
      last.lastCreatedAt = msg.createdAt;
      continue;
    }
    groups.push({
      id: msg.id,
      role: msg.role,
      createdAt: msg.createdAt,
      lastCreatedAt: msg.createdAt,
      parts: [...safeParts],
    });
  }
  return groups;
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

function formatAlarmTime(hour: number, minute: number): string {
  const h = Number.isFinite(hour) ? Math.max(0, Math.min(23, Math.floor(hour))) : 0;
  const m = Number.isFinite(minute) ? Math.max(0, Math.min(59, Math.floor(minute))) : 0;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function buildSystemAlarmCreatedCardContent(input: { hour?: number; minute?: number; title?: string }): string {
  const payload: SystemAlarmCreatedCard = {
    type: "system_alarm_created",
    hour: Math.max(0, Math.min(23, Math.floor(Number(input.hour ?? 0) || 0))),
    minute: Math.max(0, Math.min(59, Math.floor(Number(input.minute ?? 0) || 0))),
    title: String(input.title || "渡的提醒").trim() || "渡的提醒",
  };
  return `${SYSTEM_CARD_PREFIX}${JSON.stringify(payload)}${SYSTEM_CARD_SUFFIX}`;
}

function parseSystemAlarmCreatedCard(content: string): SystemAlarmCreatedCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "system_alarm_created") return null;
    const hour = Number(parsed.hour);
    const minute = Number(parsed.minute);
    if (!Number.isFinite(hour) || hour < 0 || hour > 23) return null;
    if (!Number.isFinite(minute) || minute < 0 || minute > 59) return null;
    return {
      type: "system_alarm_created",
      hour: Math.floor(hour),
      minute: Math.floor(minute),
      title: String(parsed.title || "渡的提醒").trim() || "渡的提醒",
    };
  } catch {
    return null;
  }
}

function parseCalendarEventCreatedCard(content: string): CalendarEventCreatedCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "calendar_event_created") return null;
    const title = String(parsed.title || "渡的行程").trim() || "渡的行程";
    const startAt = String(parsed.startAt || parsed.start_at || "").trim();
    const startMillis = Number(parsed.startMillis || 0);
    if (!startAt && (!Number.isFinite(startMillis) || startMillis <= 0)) return null;
    const card: CalendarEventCreatedCard = {
      type: "calendar_event_created",
      title,
      startAt,
      endAt: String(parsed.endAt || parsed.end_at || "").trim() || undefined,
      startMillis: Number.isFinite(startMillis) && startMillis > 0 ? Math.floor(startMillis) : undefined,
      allDay: Boolean(parsed.allDay || parsed.all_day),
    };
    const endMillis = Number(parsed.endMillis || 0);
    if (Number.isFinite(endMillis) && endMillis > 0) card.endMillis = Math.floor(endMillis);
    const location = String(parsed.location || "").trim();
    if (location) card.location = location;
    const reminder = Number(parsed.reminderMinutes ?? parsed.reminder_minutes);
    if (Number.isFinite(reminder)) card.reminderMinutes = Math.floor(reminder);
    const eventId = String(parsed.eventId || "").trim();
    if (eventId) card.eventId = eventId;
    return card;
  } catch {
    return null;
  }
}

function normalizeTravelPrefer(value: unknown): TravelPlanPreference {
  const raw = String(value || "").trim();
  if (raw === "transit" || raw === "taxi") return raw;
  return "auto";
}

function normalizeTravelWalk(value: unknown): TravelPlanWalkPreference {
  const raw = String(value || "").trim();
  if (raw === "low" || raw === "high") return raw;
  return "medium";
}

function parseTravelPlanFormCard(content: string): TravelPlanFormCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "travel_plan_form") return null;
    const destinations = Array.isArray(parsed.destinations)
      ? parsed.destinations.map((item: unknown) => String(item || "").trim()).filter(Boolean).slice(0, 6)
      : [];
    return {
      type: "travel_plan_form",
      title: String(parsed.title || "出行规划").trim() || "出行规划",
      prompt: String(parsed.prompt || "").trim() || undefined,
      city: String(parsed.city || "").trim() || undefined,
      destinations,
      food: String(parsed.food || "").trim() || undefined,
      prefer: normalizeTravelPrefer(parsed.prefer),
      walk: normalizeTravelWalk(parsed.walk),
    };
  } catch {
    return null;
  }
}

function parseStringList(value: unknown, limit = 8): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || "").trim()).filter(Boolean).slice(0, limit);
}

function parseTravelRouteSummary(value: unknown): TravelPlanRouteSummary {
  if (!value || typeof value !== "object") return {};
  const raw = value as Record<string, unknown>;
  const costYuan = Number(raw.costYuan ?? raw.cost_yuan);
  const taxiCostYuan = Number(raw.taxiCostYuan ?? raw.taxi_cost_yuan);
  const out: TravelPlanRouteSummary = {
    ok: Boolean(raw.ok),
    duration: String(raw.duration || "").trim() || undefined,
    distance: String(raw.distance || "").trim() || undefined,
    walking: String(raw.walking || raw.walking_distance || "").trim() || undefined,
    steps: parseStringList(raw.steps, 6),
    error: String(raw.error || "").trim() || undefined,
  };
  if (Number.isFinite(costYuan) && costYuan > 0) out.costYuan = costYuan;
  if (Number.isFinite(taxiCostYuan) && taxiCostYuan > 0) out.taxiCostYuan = taxiCostYuan;
  return out;
}

function parseTravelPlanResultCard(content: string): TravelPlanResultCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "travel_plan_result") return null;
    const legs = Array.isArray(parsed.legs)
      ? parsed.legs.map((item: unknown) => {
        const leg = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
        const links = (leg.links && typeof leg.links === "object" ? leg.links : {}) as Record<string, unknown>;
        return {
          from: String(leg.from || "起点").trim() || "起点",
          to: String(leg.to || "终点").trim() || "终点",
          mode: String(leg.mode || "").trim() || undefined,
          reason: String(leg.reason || "").trim() || undefined,
          transit: parseTravelRouteSummary(leg.transit),
          driving: parseTravelRouteSummary(leg.driving),
          links: {
            navi: String(links.navi || "").trim() || undefined,
            taxi: String(links.taxi || "").trim() || undefined,
          },
          summary: parseStringList(leg.summary, 5),
        };
      }).slice(0, 6)
      : [];
    return {
      type: "travel_plan_result",
      title: String(parsed.title || "渡安排好了").trim() || "渡安排好了",
      origin: String(parsed.origin || "").trim() || undefined,
      destinations: parseStringList(parsed.destinations, 8),
      optimized: Boolean(parsed.optimized),
      legs,
      personalMapUrl: String(parsed.personalMapUrl || parsed.personal_map_url || "").trim() || undefined,
      note: String(parsed.note || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

function parseTravelTransportDetailCard(content: string): TravelTransportDetailCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "travel_transport_detail") return null;
    return {
      type: "travel_transport_detail",
      title: String(parsed.title || "这段怎么走").trim() || "这段怎么走",
      planId: String(parsed.planId || parsed.plan_id || "").trim() || undefined,
      legId: String(parsed.legId || parsed.leg_id || "").trim() || undefined,
      from: String(parsed.from || "起点").trim() || "起点",
      to: String(parsed.to || "终点").trim() || "终点",
      mode: String(parsed.mode || "").trim() || undefined,
      reason: String(parsed.reason || "").trim() || undefined,
      transit: parseTravelRouteSummary(parsed.transit),
      driving: parseTravelRouteSummary(parsed.driving),
      cacheHit: Boolean(parsed.cacheHit ?? parsed.cache_hit),
      note: String(parsed.note || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

function parseTravelFoodDetailCard(content: string): TravelFoodDetailCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "travel_food_detail") return null;
    const items = Array.isArray(parsed.items)
      ? parsed.items.map((item: unknown) => {
        const rawItem = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
        const distanceMeters = Number(rawItem.distanceMeters ?? rawItem.distance_meters);
        const out: TravelFoodItem = {
          name: String(rawItem.name || "").trim(),
          type: String(rawItem.type || "").trim() || undefined,
          address: String(rawItem.address || "").trim() || undefined,
          rating: String(rawItem.rating || "").trim() || undefined,
          cost: String(rawItem.cost || "").trim() || undefined,
        };
        if (Number.isFinite(distanceMeters) && distanceMeters > 0) out.distanceMeters = distanceMeters;
        return out;
      }).filter((item: TravelFoodItem) => item.name).slice(0, 8)
      : [];
    return {
      type: "travel_food_detail",
      title: String(parsed.title || "附近吃这些").trim() || "附近吃这些",
      planId: String(parsed.planId || parsed.plan_id || "").trim() || undefined,
      placeId: String(parsed.placeId || parsed.place_id || "").trim() || undefined,
      placeName: String(parsed.placeName || parsed.place_name || "").trim() || undefined,
      keywords: String(parsed.keywords || "").trim() || undefined,
      items,
      cacheHit: Boolean(parsed.cacheHit ?? parsed.cache_hit),
      note: String(parsed.note || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

function parseSumiTalkSystemCard(content: string): SumiTalkSystemCard | null {
  return (
    parseSystemAlarmCreatedCard(content)
    || parseCalendarEventCreatedCard(content)
    || parseTravelPlanFormCard(content)
    || parseTravelPlanResultCard(content)
    || parseTravelTransportDetailCard(content)
    || parseTravelFoodDetailCard(content)
  );
}

function splitSystemCardSegments(content: string): Array<{ content: string; systemCard: SumiTalkSystemCard | null }> {
  const raw = String(content || "");
  const out: Array<{ content: string; systemCard: SumiTalkSystemCard | null }> = [];
  let cursor = 0;
  while (cursor < raw.length) {
    const start = raw.indexOf(SYSTEM_CARD_PREFIX, cursor);
    if (start < 0) {
      const rest = raw.slice(cursor).trim();
      if (rest) out.push({ content: rest, systemCard: null });
      break;
    }
    const before = raw.slice(cursor, start).trim();
    if (before) out.push({ content: before, systemCard: null });
    const end = raw.indexOf(SYSTEM_CARD_SUFFIX, start + SYSTEM_CARD_PREFIX.length);
    if (end < 0) {
      const rest = raw.slice(start).trim();
      if (rest) out.push({ content: rest, systemCard: null });
      break;
    }
    const marker = raw.slice(start, end + SYSTEM_CARD_SUFFIX.length).trim();
    const systemCard = parseSumiTalkSystemCard(marker);
    if (systemCard) {
      out.push({ content: marker, systemCard });
    } else {
      out.push({ content: marker, systemCard: null });
    }
    cursor = end + SYSTEM_CARD_SUFFIX.length;
  }
  return out;
}

function firstSystemCard(content: string): SumiTalkSystemCard | null {
  for (const segment of splitSystemCardSegments(content)) {
    if (segment.systemCard) return segment.systemCard;
  }
  return null;
}

function SystemAlarmCreatedBubble({ card, onOpen }: { card: SystemAlarmCreatedCard; onOpen: () => void }) {
  return (
    <button
      className="block w-full max-w-[260px] rounded-[20px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-semibold text-amber-800">系统闹钟</span>
        <span className="text-[11px] font-medium text-amber-700">点击查看</span>
      </div>
      <div className="text-[30px] font-bold leading-none text-gray-900">{formatAlarmTime(card.hour, card.minute)}</div>
      <div className="mt-2 text-[13px] font-medium leading-5 text-gray-700">{card.title}</div>
    </button>
  );
}

function formatCalendarCardTime(value?: string, millis?: number, allDay?: boolean): string {
  const ts = Number.isFinite(Number(millis || 0)) && Number(millis || 0) > 0
    ? Number(millis)
    : Date.parse(String(value || ""));
  if (!Number.isFinite(ts)) return allDay ? "全天" : "时间待确认";
  const date = new Date(ts);
  if (allDay) {
    return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", weekday: "short" }).format(date);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function CalendarEventCreatedBubble({ card, onOpen }: { card: CalendarEventCreatedCard; onOpen: () => void }) {
  const start = formatCalendarCardTime(card.startAt, card.startMillis, card.allDay);
  const end = card.endAt || card.endMillis ? formatCalendarCardTime(card.endAt, card.endMillis, card.allDay) : "";
  return (
    <button
      className="block w-full max-w-[290px] rounded-[22px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-semibold text-emerald-800">系统行程</span>
        <span className="text-[11px] font-medium text-emerald-700">点击查看</span>
      </div>
      <div className="text-[15px] font-bold leading-5 text-gray-900">{card.title}</div>
      <div className="mt-2 text-[13px] font-medium leading-5 text-gray-700">{end ? `${start} - ${end}` : start}</div>
      {card.location ? <div className="mt-1 text-[12px] leading-5 text-gray-500">{card.location}</div> : null}
      {typeof card.reminderMinutes === "number" && card.reminderMinutes >= 0 ? (
        <div className="mt-2 text-[11px] font-medium text-emerald-700">提前 {card.reminderMinutes} 分钟提醒</div>
      ) : null}
    </button>
  );
}

function TravelPlanFormBubble({ card, onOpen }: { card: TravelPlanFormCard; onOpen: () => void }) {
  const placeText = card.destinations?.length ? card.destinations.join("、") : "填写想去的地方";
  return (
    <button
      className="block w-full max-w-[300px] rounded-[22px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-semibold text-sky-800">{card.title || "出行规划"}</span>
        <span className="text-[11px] font-medium text-sky-700">点击填写</span>
      </div>
      <div className="text-[15px] font-bold leading-5 text-gray-900">{placeText}</div>
      <div className="mt-2 text-[12px] leading-5 text-gray-500">
        {card.prompt || "填完后渡会综合位置、交通、吃饭和步行接受度来规划。"}
      </div>
    </button>
  );
}

function splitTravelFormText(value: string): string[] {
  return String(value || "")
    .split(/[\n,，、;；]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 8);
}

function travelPreferLabel(value: TravelPlanPreference): string {
  if (value === "transit") return "地铁公交优先";
  if (value === "taxi") return "打车优先";
  return "自动比较";
}

function travelWalkLabel(value: TravelPlanWalkPreference): string {
  if (value === "low") return "少走路";
  if (value === "high") return "可以多走";
  return "可以走一点";
}

function TravelPlanFormModal({
  card,
  sending,
  onClose,
  onSubmit,
}: {
  card: TravelPlanFormCard;
  sending: boolean;
  onClose: () => void;
  onSubmit: (content: string) => void;
}) {
  const toast = useToast();
  const [useCurrentLocation, setUseCurrentLocation] = useState(true);
  const [origin, setOrigin] = useState("");
  const [city, setCity] = useState(card.city || "");
  const [destinations, setDestinations] = useState((card.destinations || []).join("\n"));
  const [walk, setWalk] = useState<TravelPlanWalkPreference>(card.walk || "medium");
  const [prefer, setPrefer] = useState<TravelPlanPreference>(card.prefer || "auto");
  const [note, setNote] = useState(card.food ? `想吃：${card.food}` : "");

  const inputClass = "w-full rounded-xl border border-[#FFECDA] bg-white px-4 py-3 text-[14px] font-medium leading-5 text-[#5C4D3E] outline-none placeholder:text-[#B8A998] focus:border-[#FF8C42] focus:shadow-[0_0_0_2px_rgba(255,140,66,0.10)]";
  const pillClass = (active: boolean, extra = "") =>
    `${extra} rounded-full border px-4 py-2 text-[14px] font-medium leading-5 transition-colors active:scale-[0.98] ${
      active ? "border-[#FF8C42] bg-[#FF8C42] text-white" : "border-[#FFECDA] bg-white text-[#8D7B68]"
    }`;
  const sectionTitleClass = "mb-3 flex items-center gap-1.5 text-[15px] font-bold text-[#5C4D3E]";
  const renderSection = (icon: string, title: string, children: React.ReactNode) => (
    <div className="mb-8">
      <div className={sectionTitleClass}>
        <span className="text-[16px] leading-none" aria-hidden="true">
          {icon}
        </span>
        {title}
      </div>
      {children}
    </div>
  );

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const places = splitTravelFormText(destinations);
    if (!places.length) {
      toast("先填想去的地方");
      return;
    }
    if (!useCurrentLocation && !origin.trim()) {
      toast("填一下出发地，或者选用最近定位");
      return;
    }
    const lines = [
      "帮我做一个轻量出行规划，信息如下：",
      `出发地：${useCurrentLocation ? "用我最近定位/当前位置" : origin.trim()}`,
      city.trim() ? `城市：${city.trim()}` : "",
      `想去的地方：${places.join("、")}`,
      `步行接受度：${travelWalkLabel(walk)}`,
      `交通偏好：${travelPreferLabel(prefer)}`,
      note.trim() ? `补充：${note.trim()}` : "",
      "请只做第一轮轻量总规划：综合位置距离安排游玩顺序，每段只给推荐交通方式、大致耗时/步行/打车参考即可，不用逐站逐步写得很细；吃饭只简单提醒，不要展开查店。",
    ].filter(Boolean);
    onSubmit(lines.join("\n"));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/20" role="dialog" aria-modal="true">
      <button type="button" className="absolute inset-0 h-full w-full cursor-default" aria-label="关闭出行规划表单" onClick={onClose} />
      <form
        className="relative z-10 flex h-[92vh] max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-t-[32px] bg-[#FFF9F2] shadow-[0_-10px_25px_rgba(0,0,0,0.10)]"
        onSubmit={handleSubmit}
      >
        <div className="flex justify-center py-3">
          <div className="h-1.5 w-10 rounded-full bg-[#E5D5C5]" />
        </div>

        <div className="flex items-start justify-between px-6 pb-4">
          <div>
            <h1 className="text-2xl font-bold text-[#5C4D3E]">想去哪玩？</h1>
            <p className="mt-1 text-sm text-[#A89A8B]">先填最关键的，细节后面再聊</p>
          </div>
          <button
            type="button"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#F3E9DD] text-lg font-semibold leading-none text-[#8D7B68] active:scale-[0.96]"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 pb-36 [scrollbar-color:#E5D5C5_transparent]">
          {renderSection(
            "📍",
            "出发地",
            <>
              <div className="mb-3 flex gap-3">
                <button type="button" className={pillClass(useCurrentLocation)} onClick={() => setUseCurrentLocation(true)}>
                  用当前位置
                </button>
                <button type="button" className={pillClass(!useCurrentLocation)} onClick={() => setUseCurrentLocation(false)}>
                  手动填写
                </button>
              </div>
              {!useCurrentLocation ? (
                <input className={inputClass} value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="酒店 / 车站 / 地址" />
              ) : null}
            </>,
          )}

          {renderSection(
            "🏙️",
            "城市",
            <input className={inputClass} value={city} onChange={(e) => setCity(e.target.value)} placeholder="比如 上海" />,
          )}

          {renderSection(
            "⭐",
            "想去的地方",
            <textarea
              className={`${inputClass} h-24 resize-none`}
              value={destinations}
              onChange={(e) => setDestinations(e.target.value)}
              placeholder="一行一个地点，比如：上海迪士尼、武康路、咖啡店"
            />,
          )}

          {renderSection(
            "👟",
            "步行接受度",
            <div className="flex gap-2">
              {(["low", "medium", "high"] as TravelPlanWalkPreference[]).map((item) => (
                <button key={item} type="button" className={pillClass(walk === item, "flex-1 px-2")} onClick={() => setWalk(item)}>
                  {travelWalkLabel(item)}
                </button>
              ))}
            </div>,
          )}

          {renderSection(
            "🚇",
            "交通偏好",
            <div className="flex gap-2">
              {(["auto", "transit", "taxi"] as TravelPlanPreference[]).map((item) => (
                <button key={item} type="button" className={pillClass(prefer === item, "flex-1 px-2")} onClick={() => setPrefer(item)}>
                  {travelPreferLabel(item)}
                </button>
              ))}
            </div>,
          )}

          {renderSection(
            "📝",
            "补充",
            <textarea
              className={`${inputClass} h-24 resize-none`}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="比如 想吃甜品 / 不想太赶 / 预算控制一下"
            />,
          )}
        </div>

        <div className="absolute bottom-0 left-0 right-0 flex flex-col gap-3 border-t border-[#FFECDA] bg-[#FFF9F2] p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
          <p className="text-center text-xs text-[#A89A8B]">提交后只显示：已提交，渡在安排</p>
          <button
            type="submit"
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#FF8C42] py-4 text-lg font-bold text-white shadow-lg shadow-orange-200 transition-all active:scale-[0.98] disabled:opacity-50"
            disabled={sending}
          >
            ✨ 让渡安排
          </button>
        </div>
      </form>
    </div>
  );
}

function travelModeLabel(value?: string): string {
  const raw = String(value || "").trim();
  if (raw === "taxi") return "打车";
  if (raw === "transit") return "地铁公交";
  if (raw === "walking") return "步行";
  return raw || "建议";
}

function formatYuan(value?: number): string {
  if (!Number.isFinite(Number(value || 0)) || Number(value || 0) <= 0) return "";
  return `${Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 1)}元`;
}

function TravelPlanResultBubble({ card, onOpen }: { card: TravelPlanResultCard; onOpen: () => void }) {
  const legs = card.legs || [];
  const order = card.destinations?.length ? card.destinations : legs.map((leg) => leg.to).filter(Boolean);
  return (
    <button
      className="relative block w-full max-w-[345px] text-left transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="absolute -left-[8px] top-5 h-0 w-0 border-y-[8px] border-r-[12px] border-y-transparent border-r-[#FFF9F2]" />
      <div className="flex flex-col gap-4 overflow-hidden rounded-[28px] border border-[#FFEEDB] bg-[#FFF9F2] p-5 shadow-[0_10px_25px_-5px_rgba(255,180,100,0.10),0_8px_10px_-6px_rgba(255,180,100,0.10)]">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-orange-100 text-[16px]">✨</div>
            <span className="truncate text-[18px] font-bold text-[#5C4D3E]">{card.title || "渡安排好了"}</span>
          </div>
          <span className="shrink-0 text-[18px] leading-none text-[#A89A8B]">•••</span>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-1.5 text-[#8D7B68]">
            <span className="shrink-0 text-[15px] text-orange-400">📍</span>
            <span className="truncate text-[14px]">
              {card.origin ? (
                <>
                  从 <span className="font-medium text-[#5C4D3E]">{card.origin}</span> 出发
                </>
              ) : (
                "路线已规划"
              )}
            </span>
          </div>
          {card.optimized ? (
            <div className="flex shrink-0 items-center gap-1 rounded-full border border-[#D0E7D2] bg-[#E8F5E9] px-2 py-0.5">
              <span className="text-[10px] text-[#4CAF50]">✨</span>
              <span className="text-[11px] font-bold text-[#4CAF50]">已顺路排序</span>
            </div>
          ) : null}
        </div>

        {order.length ? (
          <div className="flex flex-wrap gap-2">
            {order.slice(0, 4).map((name, index) => (
              <div key={`${name}-${index}`} className="flex max-w-full items-center gap-2 rounded-xl border border-[#FFECDA] bg-white px-3 py-1.5 shadow-sm">
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white ${index % 2 === 0 ? "bg-orange-400" : "bg-blue-300"}`}>
                  {index + 1}
                </span>
                <span className="truncate text-[14px] font-medium text-[#5C4D3E]">{name}</span>
              </div>
            ))}
            {order.length > 4 ? (
              <div className="flex items-center rounded-xl border border-[#FFECDA] bg-white px-3 py-1.5 text-[12px] font-bold text-[#A89A8B] shadow-sm">
                +{order.length - 4}
              </div>
            ) : null}
          </div>
        ) : null}

        {legs.length ? (
          <div className="relative py-1 pl-6">
            <div className="absolute bottom-0 left-1.5 top-0 border-l-2 border-dashed border-orange-200" />
            <div className="space-y-4">
              {legs.slice(0, 3).map((leg, index) => {
                const preferred = leg.mode === "taxi" ? leg.driving : leg.transit;
                const brief = [
                  travelModeLabel(leg.mode),
                  preferred?.duration,
                  leg.mode === "taxi" ? preferred?.distance : preferred?.walking ? `步行${preferred.walking}` : "",
                ].filter(Boolean);
                return (
                  <div key={`${leg.from}-${leg.to}-${index}`} className="relative">
                    <div className="absolute -left-[22px] top-1.5 h-2 w-2 rounded-full border-2 border-white bg-orange-400" />
                    <div className="flex min-w-0 flex-col">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-[14px] font-bold text-[#5C4D3E]">{leg.from}</span>
                        <span className="shrink-0 text-[12px] text-[#A89A8B]">→</span>
                        <span className="truncate text-[14px] font-bold text-[#5C4D3E]">{leg.to}</span>
                      </div>
                      <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2 text-[12px] text-[#A89A8B]">
                        <span>{leg.mode === "taxi" ? "🚗" : "🚇"}</span>
                        <span>{brief.join(" · ") || leg.reason || "路线详情见卡片"}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        <div className="flex items-center justify-center gap-1 border-t border-[#FFF1E0] pt-2">
          <span className="text-[12px] text-[#A89A8B]">点击查看详情</span>
          <span className="text-[12px] text-[#A89A8B]">›</span>
        </div>
      </div>
    </button>
  );
}

function TravelPlanResultModal({ card, onClose }: { card: TravelPlanResultCard; onClose: () => void }) {
  const legs = card.legs || [];
  const order = card.destinations?.length ? card.destinations : legs.map((leg) => leg.to).filter(Boolean);
  return (
    <Modal title={card.title || "渡安排好了"} onClose={onClose}>
      <div className="space-y-3">
        <div className="rounded-[18px] bg-white px-3 py-3">
          <div className="text-[12px] font-semibold text-gray-500">顺序</div>
          <div className="mt-2 space-y-1.5">
            {card.origin ? <div className="text-[13px] font-semibold text-gray-900">0. {card.origin}</div> : null}
            {order.map((name, index) => (
              <div key={`${name}-${index}`} className="text-[13px] font-semibold text-gray-900">{index + 1}. {name}</div>
            ))}
          </div>
          {card.optimized ? <div className="mt-2 text-[11px] text-indigo-700">已按位置做顺路排序</div> : null}
        </div>
        {legs.map((leg, index) => {
          const transitCost = formatYuan(leg.transit?.costYuan);
          const taxiCost = formatYuan(leg.transit?.taxiCostYuan);
          return (
            <div key={`${leg.from}-${leg.to}-${index}`} className="rounded-[18px] bg-white px-3 py-3">
              <div className="text-[12px] font-semibold text-gray-500">第 {index + 1} 段</div>
              <div className="mt-1 text-[15px] font-bold leading-5 text-gray-900">{leg.from}{" -> "}{leg.to}</div>
              <div className="mt-2 rounded-[14px] bg-indigo-50 px-3 py-2 text-[12px] font-semibold leading-5 text-indigo-800">
                推荐：{travelModeLabel(leg.mode)}{leg.reason ? `，${leg.reason}` : ""}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <div className="rounded-[14px] bg-gray-50 px-3 py-2">
                  <div className="text-[11px] font-semibold text-gray-500">地铁公交</div>
                  <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-800">
                    {leg.transit?.ok ? [leg.transit.duration, leg.transit.walking ? `步行${leg.transit.walking}` : "", transitCost].filter(Boolean).join(" · ") : (leg.transit?.error || "无结果")}
                  </div>
                </div>
                <div className="rounded-[14px] bg-gray-50 px-3 py-2">
                  <div className="text-[11px] font-semibold text-gray-500">打车/驾车</div>
                  <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-800">
                    {leg.driving?.ok ? [leg.driving.duration, leg.driving.distance, taxiCost ? `预估${taxiCost}` : ""].filter(Boolean).join(" · ") : (leg.driving?.error || "无结果")}
                  </div>
                </div>
              </div>
              {leg.transit?.steps?.length ? (
                <div className="mt-2 space-y-1">
                  {leg.transit.steps.map((step, stepIndex) => (
                    <div key={`${step}-${stepIndex}`} className="text-[12px] leading-5 text-gray-600">{stepIndex + 1}. {step}</div>
                  ))}
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {leg.links?.navi ? (
                  <a className="rounded-full bg-gray-900 px-3 py-2 text-[12px] font-semibold text-white" href={leg.links.navi} target="_blank" rel="noreferrer">打开导航</a>
                ) : null}
                {leg.links?.taxi ? (
                  <a className="rounded-full bg-gray-100 px-3 py-2 text-[12px] font-semibold text-gray-800" href={leg.links.taxi} target="_blank" rel="noreferrer">打开打车</a>
                ) : null}
              </div>
            </div>
          );
        })}
        {card.personalMapUrl ? (
          <a className="block rounded-[18px] bg-gray-900 px-4 py-3 text-center text-[13px] font-semibold text-white" href={card.personalMapUrl} target="_blank" rel="noreferrer">打开高德专属地图</a>
        ) : null}
        {card.note ? <div className="px-1 text-[11px] leading-5 text-gray-500">{card.note}</div> : null}
      </div>
    </Modal>
  );
}

function formatMeters(value?: number): string {
  const meters = Number(value || 0);
  if (!Number.isFinite(meters) || meters <= 0) return "";
  if (meters < 1000) return `${Math.round(meters)}米`;
  return `${(meters / 1000).toFixed(1)}公里`;
}

function TravelTransportDetailBubble({ card, onOpen }: { card: TravelTransportDetailCard; onOpen: () => void }) {
  const preferred = card.mode === "taxi" ? card.driving : card.transit;
  const brief = [
    travelModeLabel(card.mode),
    preferred?.duration,
    card.mode === "taxi" ? preferred?.distance : preferred?.walking ? `步行${preferred.walking}` : "",
  ].filter(Boolean).join(" · ");
  return (
    <button
      className="block w-full max-w-[320px] rounded-[22px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[12px] font-semibold text-gray-500">{card.title || "这段怎么走"}</span>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">{card.cacheHit ? "已缓存" : "刚查到"}</span>
      </div>
      <div className="text-[15px] font-bold leading-5 text-gray-900">{card.from} → {card.to}</div>
      <div className="mt-2 text-[12px] leading-5 text-gray-600">{brief || card.reason || "点击查看这一段路线"}</div>
    </button>
  );
}

function TravelTransportDetailModal({ card, onClose }: { card: TravelTransportDetailCard; onClose: () => void }) {
  const transitCost = formatYuan(card.transit?.costYuan);
  const taxiCost = formatYuan(card.transit?.taxiCostYuan);
  return (
    <Modal title={card.title || "这段怎么走"} onClose={onClose}>
      <div className="space-y-3">
        <div className="rounded-[18px] bg-white px-3 py-3">
          <div className="text-[12px] font-semibold text-gray-500">路线</div>
          <div className="mt-1 text-[15px] font-bold leading-5 text-gray-900">{card.from}{" -> "}{card.to}</div>
          <div className="mt-2 rounded-[14px] bg-gray-50 px-3 py-2 text-[12px] font-semibold leading-5 text-gray-800">
            推荐：{travelModeLabel(card.mode)}{card.reason ? `，${card.reason}` : ""}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-[18px] bg-white px-3 py-3">
            <div className="text-[11px] font-semibold text-gray-500">地铁公交</div>
            <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-800">
              {card.transit?.ok ? [card.transit.duration, card.transit.walking ? `步行${card.transit.walking}` : "", transitCost].filter(Boolean).join(" · ") : (card.transit?.error || "无结果")}
            </div>
          </div>
          <div className="rounded-[18px] bg-white px-3 py-3">
            <div className="text-[11px] font-semibold text-gray-500">打车/驾车</div>
            <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-800">
              {card.driving?.ok ? [card.driving.duration, card.driving.distance, taxiCost ? `预估${taxiCost}` : ""].filter(Boolean).join(" · ") : (card.driving?.error || "无结果")}
            </div>
          </div>
        </div>
        {card.transit?.steps?.length ? (
          <div className="rounded-[18px] bg-white px-3 py-3">
            <div className="text-[12px] font-semibold text-gray-500">换乘步骤</div>
            <div className="mt-2 space-y-1">
              {card.transit.steps.map((step, index) => (
                <div key={`${step}-${index}`} className="text-[12px] leading-5 text-gray-600">{index + 1}. {step}</div>
              ))}
            </div>
          </div>
        ) : null}
        {card.note ? <div className="px-1 text-[11px] leading-5 text-gray-500">{card.note}</div> : null}
      </div>
    </Modal>
  );
}

function TravelFoodDetailBubble({ card, onOpen }: { card: TravelFoodDetailCard; onOpen: () => void }) {
  const first = card.items?.[0]?.name;
  return (
    <button
      className="block w-full max-w-[320px] rounded-[22px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[12px] font-semibold text-gray-500">{card.title || "附近吃这些"}</span>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">{card.cacheHit ? "已缓存" : "刚查到"}</span>
      </div>
      <div className="text-[15px] font-bold leading-5 text-gray-900">{card.placeName || card.keywords || "附近"}</div>
      <div className="mt-2 text-[12px] leading-5 text-gray-600">{first ? `比如 ${first}` : "点击查看候选"}</div>
    </button>
  );
}

function TravelFoodDetailModal({ card, onClose }: { card: TravelFoodDetailCard; onClose: () => void }) {
  return (
    <Modal title={card.title || "附近吃这些"} onClose={onClose}>
      <div className="space-y-3">
        <div className="rounded-[18px] bg-white px-3 py-3">
          <div className="text-[12px] font-semibold text-gray-500">位置</div>
          <div className="mt-1 text-[15px] font-bold leading-5 text-gray-900">{card.placeName || "附近"}</div>
          {card.keywords ? <div className="mt-1 text-[12px] leading-5 text-gray-500">关键词：{card.keywords}</div> : null}
        </div>
        {(card.items || []).map((item, index) => {
          const distance = formatMeters(item.distanceMeters);
          const meta = [distance, item.rating ? `评分${item.rating}` : "", item.cost ? `人均${item.cost}` : ""].filter(Boolean).join(" · ");
          return (
            <div key={`${item.name}-${index}`} className="rounded-[18px] bg-white px-3 py-3">
              <div className="text-[14px] font-bold leading-5 text-gray-900">{item.name}</div>
              {meta ? <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-700">{meta}</div> : null}
              {item.address ? <div className="mt-1 text-[12px] leading-5 text-gray-500">{item.address}</div> : null}
            </div>
          );
        })}
        {!(card.items || []).length ? <div className="rounded-[18px] bg-white px-3 py-3 text-[13px] text-gray-500">这次没查到稳定候选。</div> : null}
        {card.note ? <div className="px-1 text-[11px] leading-5 text-gray-500">{card.note}</div> : null}
      </div>
    </Modal>
  );
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
  tone: "du" | "wenyou";
  avatarImage?: string;
  pinned?: boolean;
  onClick: () => void;
}) {
  const palette = tone === "wenyou"
    ? { shell: "bg-[#F8F0F4] text-[#704A5D]" }
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

function FullScreenPane({
  title,
  accent,
  onBack,
  headerMode = "default",
  edgeSwipeBack = false,
  children,
}: {
  title: string;
  accent: "du" | "wenyou" | "neutral";
  onBack: () => void;
  headerMode?: "default" | "simple";
  edgeSwipeBack?: boolean;
  children: React.ReactNode;
}) {
  const swipeRef = useRef({ tracking: false, startX: 0, startY: 0, latestX: 0, latestY: 0 });

  function handleTouchStart(e: React.TouchEvent<HTMLDivElement>) {
    if (!edgeSwipeBack) return;
    const touch = e.touches[0];
    if (!touch || touch.clientX > 36) {
      swipeRef.current.tracking = false;
      return;
    }
    swipeRef.current = {
      tracking: true,
      startX: touch.clientX,
      startY: touch.clientY,
      latestX: touch.clientX,
      latestY: touch.clientY,
    };
  }

  function handleTouchMove(e: React.TouchEvent<HTMLDivElement>) {
    if (!swipeRef.current.tracking) return;
    const touch = e.touches[0];
    if (!touch) return;
    swipeRef.current.latestX = touch.clientX;
    swipeRef.current.latestY = touch.clientY;
  }

  function handleTouchEnd() {
    const swipe = swipeRef.current;
    swipeRef.current.tracking = false;
    if (!edgeSwipeBack || !swipe.tracking) return;
    const dx = swipe.latestX - swipe.startX;
    const dy = Math.abs(swipe.latestY - swipe.startY);
    if (dx >= 72 && dx > dy * 1.5) {
      onBack();
    }
  }

  return (
    <div
      className="absolute inset-0 z-30 flex w-full max-w-full flex-col overflow-x-hidden bg-[#FDFDFD]"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={() => {
        swipeRef.current.tracking = false;
      }}
    >
      {headerMode === "simple" ? (
        <div className="border-b border-gray-100/50 bg-white px-4 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)]">
          <button className="flex items-center gap-2 text-gray-900" onClick={onBack}>
            <ChevronLeftIcon />
            <span className="text-[15px] font-medium">{title}</span>
          </button>
        </div>
      ) : (
        <div className="absolute top-0 z-20 flex w-full items-center border-b border-gray-100/50 bg-white/80 px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)] backdrop-blur-md">
          <button className="rounded-full p-2 text-gray-500 transition-colors active:bg-gray-100" onClick={onBack}>
            <ChevronLeftIcon />
          </button>
          <div className="ml-2 text-[15px] font-medium text-gray-900">{title}</div>
        </div>
      )}
      <div className={`min-h-0 w-full max-w-full flex-1 overflow-x-hidden overflow-y-auto px-3.5 pb-4 ${headerMode === "simple" ? "pt-0" : "pt-[82px]"}`}>{children}</div>
    </div>
  );
}

function MainChatScreen({
  title,
  avatarLabel,
  windowId,
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
      content: "我在。你直接说就好。",
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
    const nextMessages = [...messagesRef.current, userMsg];
    const draftMessages = [
      ...nextMessages,
      { id: assistantId, role: "assistant" as const, content: "", createdAt: assistantCreatedAt, status: "pending" as const, clientRequestId },
    ];
    const replyTarget = resolvedDeviceId;
    setInput("");
    setPlusOpen(false);
    setSending(true);
    setMessages(draftMessages);
    messagesRef.current = draftMessages;
    await saveDisplayHistory(draftMessages, { syncRemote: false, localDeviceId: resolvedDeviceId });
    try {
      const requestBody = {
        model: activeModel,
        messages: [{ role: "user", content }],
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
      await saveDisplayHistory(finalMessages);
    } catch (e: any) {
      const failedMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, {
        id: assistantId,
        role: "assistant" as const,
        content: `（发送失败：${e?.message || e}）`,
        createdAt: assistantCreatedAt,
        status: "failed" as const,
        clientRequestId,
      });
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
  const groupedMessages = groupChatMessages(messages);
  const assistantTyping = sending && messages.some(
    (msg) => msg.role === "assistant" && String(msg.status || "").trim().toLowerCase() === "pending",
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
                    <AvatarBubble image={duAvatarImage} label={avatarLabel} className={avatarClass} />
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
                                  transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("assistant", assistantBubbleStyle)
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

function PhoneIconLarge() {
  return <svg className="h-7 w-7 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.9.34 1.78.65 2.62a2 2 0 0 1-.45 2.11L8 9.91a16 16 0 0 0 6 6l1.46-1.31a2 2 0 0 1 2.11-.45c.84.31 1.72.53 2.62.65A2 2 0 0 1 22 16.92z" /></svg>;
}

function SmileIconMini() {
  return <svg className="h-7 w-7 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2" /><line x1="9" y1="9" x2="9.01" y2="9" /><line x1="15" y1="9" x2="15.01" y2="9" /></svg>;
}

function RouteIconMini() {
  return <svg className="h-7 w-7 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="19" r="2" /><circle cx="18" cy="5" r="2" /><path d="M8 19h3a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7" /></svg>;
}

function FeatherIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.24 3.76a6 6 0 0 0-8.48 0L4 11.52V20h8.48l7.76-7.76a6 6 0 0 0 0-8.48z" /><line x1="16" y1="8" x2="2" y2="22" /><line x1="17.5" y1="15" x2="9" y2="15" /><line x1="13.5" y1="19" x2="9" y2="19" /></svg>;
}

function SunIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></svg>;
}

function HeartIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 0 0 0-7.78z" /></svg>;
}

function ClockIconMini() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>;
}

function SearchIconMini() {
  return <svg className="h-[16px] w-[16px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>;
}

function SettingsIconMini() {
  return <svg className="h-[18px] w-[18px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51c.6.25 1.29.11 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82c.25.6.85 1 1.51 1H21a2 2 0 0 1 0 4h-.09c-.66 0-1.26.4-1.51 1z" /></svg>;
}

function SendIconMini() {
  return <svg className="h-[17px] w-[17px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2 11 13" /><path d="m22 2-7 20-4-9-9-4 20-7Z" /></svg>;
}

function ChevronUpMini() {
  return <svg className="h-[14px] w-[14px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m18 15-6-6-6 6" /></svg>;
}

function ChevronDownMini() {
  return <svg className="h-[14px] w-[14px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>;
}

function CopyIconMini() {
  return <svg className="h-[15px] w-[15px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="11" height="11" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>;
}

function TrashIconMini() {
  return <svg className="h-[15px] w-[15px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v5M14 11v5" /></svg>;
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

function DeviceManagerModal({ onClose, onLogout }: { onClose: () => void; onLogout?: () => void }) {
  const toast = useToast();
  const [items, setItems] = useState<DeviceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; items?: DeviceItem[] }>("/miniapp-api/panel-auth/list");
      const next = Array.isArray(j?.items) ? j.items.filter((it) => !it?.revoked) : [];
      setItems(next);
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
      toast("设备已删除");
      setItems((prev) => prev.filter((it) => String(it.id || "") !== deviceId));
    } catch (e: any) {
      toast(`撤销失败：${e?.message || e}`);
    } finally {
      setBusyId("");
    }
  }

  const currentItem = items.find((it) => !!it.current) || null;
  const otherItems = items.filter((it) => !it.current);

  function getDeviceIcon(item: DeviceItem): "phone" | "tablet" | "desktop" {
    const note = String(item.note || "").toLowerCase();
    if (note.includes("ipad") || note.includes("tablet")) return "tablet";
    if (note.includes("iphone") || note.includes("android") || note.includes("mobile")) return "phone";
    return "desktop";
  }

  function getDeviceTitle(item: DeviceItem): string {
    return String(item.note || "设备").replace(/\s*@\s*.+$/, "").trim() || "设备";
  }

  function getDeviceSubtitle(item: DeviceItem): string {
    const note = String(item.note || "").trim();
    const m = note.match(/@\s*(.+)$/);
    return m?.[1]?.trim() || "SumiTalk";
  }

  function renderDeviceIcon(kind: "phone" | "tablet" | "desktop", active = false) {
    const cls = active ? "text-blue-500" : "text-gray-400";
    if (kind === "phone") {
      return (
        <svg className={`h-6 w-6 ${cls}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="5" y="2" width="14" height="20" rx="2" ry="2" />
          <line x1="12" y1="18" x2="12.01" y2="18" />
        </svg>
      );
    }
    if (kind === "tablet") {
      return (
        <svg className={`h-6 w-6 ${cls}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4" y="2" width="16" height="20" rx="2" ry="2" />
          <line x1="12" y1="18" x2="12.01" y2="18" />
        </svg>
      );
    }
    return (
      <svg className={`h-6 w-6 ${cls}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
    );
  }

  return (
    <FullScreenPane title="设备管理" accent="neutral" onBack={onClose} edgeSwipeBack>
      <div className="px-2 pb-8 pt-2">
        <div className="px-1 pt-4">
          <div className="mb-4 flex items-center justify-between px-1">
            <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">当前使用的设备</h2>
          </div>

          {currentItem ? (
            <div className="relative overflow-hidden rounded-[28px] border border-gray-100/80 border-l-4 border-l-blue-500 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
              <div className="flex items-start">
                <div className="mr-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50">
                  {renderDeviceIcon(getDeviceIcon(currentItem), true)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-bold text-blue-500">正在使用</span>
                    <span className="text-[12px] font-medium text-gray-400">{currentItem.last_seen || "刚刚"}</span>
                  </div>
                  <h3 className="mt-1 text-[18px] font-bold text-gray-800">{getDeviceTitle(currentItem)}</h3>
                  <p className="mt-1 text-[13px] font-light text-gray-500">{getDeviceSubtitle(currentItem)}</p>
                </div>
              </div>
            </div>
          ) : !loading ? (
            <div className="rounded-[24px] border border-gray-100 bg-white px-5 py-4 text-[13px] text-gray-400 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
              当前没有可识别设备。
            </div>
          ) : null}
        </div>

        <div className="mt-8 px-1">
          <div className="mb-4 flex items-center justify-between px-1">
            <div className="flex items-baseline gap-2">
              <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">其他授信设备</h2>
              <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-500">{otherItems.length}</span>
            </div>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="rounded-full px-3 py-1.5 text-[12px] font-semibold text-gray-400 transition active:bg-gray-50"
            >
              {loading ? "刷新中..." : "刷新"}
            </button>
          </div>

          {otherItems.length ? (
            <div className="space-y-4">
              {otherItems.map((item) => {
                const id = String(item.id || "");
                return (
                  <div key={id} className="group rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
                    <div className="flex items-start">
                      <div className="mr-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gray-50">
                        {renderDeviceIcon(getDeviceIcon(item))}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <span className="rounded-full bg-green-50 px-2.5 py-1 text-[10px] font-bold text-green-500">正常</span>
                          <span className="text-[12px] font-medium text-gray-400">{item.last_seen || "-"}</span>
                        </div>
                        <h3 className="mt-1 text-[17px] font-bold text-gray-800">{getDeviceTitle(item)}</h3>
                        <div className="mt-3 flex items-center justify-between gap-3">
                          <p className="text-[13px] font-light text-gray-500">{getDeviceSubtitle(item)}</p>
                          <button
                            type="button"
                            onClick={() => void revoke(id, false)}
                            disabled={busyId === id}
                            className="rounded-full bg-red-50 px-3 py-1 text-[13px] font-semibold text-red-400 transition active:scale-95 disabled:opacity-60"
                          >
                            {busyId === id ? "处理中..." : "撤销"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : !loading ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-blue-50">
                <svg className="h-10 w-10 text-blue-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <h3 className="mb-2 text-[18px] font-medium text-gray-800">暂无其他设备</h3>
              <p className="px-10 text-[14px] leading-relaxed text-gray-400">当前仅有这一台设备连接到你的 SumiTalk 账号</p>
            </div>
          ) : null}
        </div>
      </div>
    </FullScreenPane>
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
