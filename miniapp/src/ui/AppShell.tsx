import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { useToast } from "./toast";
import { apiJson } from "./api";
import { AvatarCropModal } from "./AvatarCropModal";
import { ChatsHome } from "./ChatsHome";
import { BottomNav, type MainTab } from "./BottomNav";
import { DiagnosticsScreen } from "./DiagnosticsScreen";
import { FullScreenPane } from "./FullScreenPane";
import { MainChatScreen } from "./MainChatScreen";
import { PersonalizationScreen } from "./PersonalizationScreen";
import { FloatingBallSettingRow, ListRow, SwitchSettingRow } from "./SettingsRows";
import { PromptManagerScreen } from "./PromptManagerScreen";
import {
  BUBBLE_STYLE_KEYS,
  DEFAULT_GROUP_CHAT_TITLE,
  getDisplayGroupChatTitle,
  limitGroupChatTitle,
  resolveChatFontFamily,
  type BubbleStyleKey,
} from "./chatAppearance";
import {
  CHAT_FONT_KEYS,
  type ChatFontKey,
  type ChatTimeFormat,
} from "./chatMessages";
import { MAIN_SUMITALK_DISPLAY_WINDOW_ID, buildGroupDisplayWindowId } from "./chatWindowIds";
import {
  BrainIconMini,
  BookOpenIcon,
  CabinetFilingIconMini,
  CalendarIconMini,
  ClockIconMini,
  CloudUploadIconMini,
  CpuIcon,
  FeatherIcon,
  FileTextIcon,
  GitMergeIcon,
  GraduationCapIconMini,
  HeadphonesIconMini,
  HeartIconMini,
  HomeIconMini,
  LogoutIconMini,
  NotebookPenIconMini,
  PhoneIconMini,
  SmartphoneIconMini,
  SpeakerIconMini,
  StarIconMini,
  SunIconMini,
  ToggleRightIcon,
  UserRoundCogIconMini,
} from "./icons";
import { SumiOverlay } from "../plugins/sumi-overlay";
import { buildBackgroundDataUrl, fileToDataUrl } from "./imageDataUrl";
import chatScriptFontUrl from "../assets/fonts/cookie-regular.ttf?url";
import { clampStoredNumber, readStoredBoolean, readStoredNumber, readStoredString } from "./uiStorage";
import {
  VOICE_CALL_PENDING_INVITE_KEY,
  normalizeVoiceCallInvite,
  type IncomingVoiceCallInvite,
} from "./voiceCallInvite";
import type { CallHubInitialView } from "./tabs/CallHubScreen";

const LISTEN_BACKGROUND_STORAGE_KEY = "miniapp.listenWithDu.backgroundImage";
const GROUP_FREE_CHAT_MODE_STORAGE_KEY = "miniapp.ui.groupFreeChatMode";

function nextBubbleStyle(style: BubbleStyleKey): BubbleStyleKey {
  const index = BUBBLE_STYLE_KEYS.indexOf(style);
  return BUBBLE_STYLE_KEYS[(index + 1) % BUBBLE_STYLE_KEYS.length] || "default";
}

function nextChatFont(font: ChatFontKey): ChatFontKey {
  const index = CHAT_FONT_KEYS.indexOf(font);
  return CHAT_FONT_KEYS[(index + 1) % CHAT_FONT_KEYS.length] || "system";
}

const LogsTab = lazy(() => import("./tabs/LogsTab").then((m) => ({ default: m.LogsTab })));
const SettingsUpstream = lazy(() => import("./tabs/SettingsUpstream").then((m) => ({ default: m.SettingsUpstream })));
const ReasoningTab = lazy(() => import("./tabs/ReasoningTab").then((m) => ({ default: m.ReasoningTab })));
const ScheduleTab = lazy(() => import("./tabs/ScheduleTab").then((m) => ({ default: m.ScheduleTab })));
const AlarmTab = lazy(() => import("./tabs/AlarmTab").then((m) => ({ default: m.AlarmTab })));
const MemoryDebugTab = lazy(() => import("./tabs/MemoryDebugTab").then((m) => ({ default: m.MemoryDebugTab })));
const MemoryNebulaTab = lazy(() => import("./tabs/MemoryNebulaTab").then((m) => ({ default: m.MemoryNebulaTab })));
const DuDayTab = lazy(() => import("./tabs/DuDayTab").then((m) => ({ default: m.DuDayTab })));
const DuNotebookTab = lazy(() => import("./tabs/DuNotebookTab").then((m) => ({ default: m.DuNotebookTab })));
const BudgetCheckInTab = lazy(() => import("./tabs/BudgetCheckInTab").then((m) => ({ default: m.BudgetCheckInTab })));
const WenyouTab = lazy(() => import("./tabs/WenyouTab").then((m) => ({ default: m.WenyouTab })));
const StickersTab = lazy(() => import("./tabs/StickersTab").then((m) => ({ default: m.StickersTab })));
const CallHubScreen = lazy(() => import("./tabs/CallHubScreen").then((m) => ({ default: m.CallHubScreen })));
const PixelHomeTab = lazy(() => import("./tabs/PixelHomeTab").then((m) => ({ default: m.PixelHomeTab })));
const StayWithDuScreen = lazy(() => import("./tabs/StayWithDuScreen").then((m) => ({ default: m.StayWithDuScreen })));
const CoReadScreen = lazy(() => import("./tabs/CoReadScreen").then((m) => ({ default: m.CoReadScreen })));
const ListenWithDuScreen = lazy(() => import("./tabs/ListenWithDuScreen").then((m) => ({ default: m.ListenWithDuScreen })));
const StudyRoomTab = lazy(() => import("./tabs/StudyRoomTab").then((m) => ({ default: m.StudyRoomTab })));
const XiaoAISettingsTab = lazy(() => import("./tabs/XiaoAISettingsTab").then((m) => ({ default: m.XiaoAISettingsTab })));
const HealthDataScreen = lazy(() => import("./tabs/HealthDataScreen").then((m) => ({ default: m.HealthDataScreen })));
const ReportingManagementScreen = lazy(() => import("./tabs/ReportingManagementScreen").then((m) => ({ default: m.ReportingManagementScreen })));
const ChatStorageManagementScreen = lazy(() => import("./tabs/ChatStorageManagementScreen").then((m) => ({ default: m.ChatStorageManagementScreen })));
const SecretDrawerTab = lazy(() => import("./tabs/SecretDrawerTab").then((m) => ({ default: m.SecretDrawerTab })));

type PanelId = "logs" | "reasoning" | "memory-debug" | "du-notebook" | "study-room" | "budget-checkin" | "secret-drawer" | "stickers" | "xiaoai" | "health-data" | "reporting" | "chat-storage" | null;
type AvatarImageKind = "myAvatar" | "duAvatar" | "benbenAvatar";
type ChatScreenId = "du" | "group" | "wenyou" | null;
type BackHandler = () => boolean;

export function AppShell({
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
  const [showPromptManager, setShowPromptManager] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showAlarm, setShowAlarm] = useState(false);
  const [showPersonalization, setShowPersonalization] = useState(false);
  const [showDuDay, setShowDuDay] = useState(false);
  const [showStayWithDu, setShowStayWithDu] = useState(false);
  const [showPixelHome, setShowPixelHome] = useState(false);
  const [showMemoryNebula, setShowMemoryNebula] = useState(false);
  const [showCoRead, setShowCoRead] = useState(false);
  const [showListenWithDu, setShowListenWithDu] = useState(false);
  const [listenWithDuMounted, setListenWithDuMounted] = useState(false);
  const [showCallHub, setShowCallHub] = useState(false);
  const [callHubInitialView, setCallHubInitialView] = useState<CallHubInitialView>("home");
  const [incomingVoiceCallInvite, setIncomingVoiceCallInvite] = useState<IncomingVoiceCallInvite | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [mainTab, setMainTab] = useState<MainTab>("chats");
  const [activeScreen, setActiveScreen] = useState<ChatScreenId>(null);
  const wenyouBackHandlerRef = useRef<(() => boolean) | null>(null);
  const callHubBackHandlerRef = useRef<BackHandler | null>(null);
  const secretDrawerBackHandlerRef = useRef<BackHandler | null>(null);
  const [groupFreeChatEnabled, setGroupFreeChatEnabled] = useState(() => readStoredBoolean(GROUP_FREE_CHAT_MODE_STORAGE_KEY, true));
  const [sharedChatWindowId, setSharedChatWindowId] = useState("");
  const [dailyWhisper, setDailyWhisper] = useState("");
  const [todayNoteRefreshing, setTodayNoteRefreshing] = useState(false);
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
    readStoredString("miniapp.ui.chatFont", "system", CHAT_FONT_KEYS),
  );
  const [showChatTimestamps, setShowChatTimestamps] = useState(() => readStoredBoolean("miniapp.ui.showTimestamps", true));
  const [chatTimeFormat, setChatTimeFormat] = useState<ChatTimeFormat>(() =>
    readStoredString("miniapp.ui.timeFormat", "hhmm", ["hhmm", "ampm"] as const),
  );
  const [expandReasoningByDefault, setExpandReasoningByDefault] = useState(() => readStoredBoolean("miniapp.ui.expandReasoning", false));
  const [chatBackgroundOpacity, setChatBackgroundOpacity] = useState(() =>
    clampStoredNumber(readStoredNumber("miniapp.ui.chatBackgroundOpacity", 100), 20, 100, 100),
  );
  const [userBubbleStyle, setUserBubbleStyle] = useState<BubbleStyleKey>(() =>
    readStoredString("miniapp.ui.userBubbleStyle", "default", BUBBLE_STYLE_KEYS),
  );
  const [assistantBubbleStyle, setAssistantBubbleStyle] = useState<BubbleStyleKey>(() =>
    readStoredString("miniapp.ui.assistantBubbleStyle", "default", BUBBLE_STYLE_KEYS),
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
  const [benbenAvatarImage, setBenbenAvatarImage] = useState(() => {
    try {
      return localStorage.getItem("miniapp.ui.benbenAvatar") || "";
    } catch {
      return "";
    }
  });
  const [groupChatTitle, setGroupChatTitle] = useState(() => {
    try {
      return limitGroupChatTitle(localStorage.getItem("miniapp.ui.groupChatTitle") || DEFAULT_GROUP_CHAT_TITLE);
    } catch {
      return DEFAULT_GROUP_CHAT_TITLE;
    }
  });
  const [chatBackgroundImage, setChatBackgroundImage] = useState(() => {
    try {
      return localStorage.getItem("miniapp.ui.chatBackgroundImage") || "";
    } catch {
      return "";
    }
  });
  const [listenBackgroundImage, setListenBackgroundImage] = useState(() => {
    try {
      return localStorage.getItem(LISTEN_BACKGROUND_STORAGE_KEY) || "";
    } catch {
      return "";
    }
  });
  const myAvatarInputRef = useRef<HTMLInputElement | null>(null);
  const duAvatarInputRef = useRef<HTMLInputElement | null>(null);
  const benbenAvatarInputRef = useRef<HTMLInputElement | null>(null);
  const backgroundInputRef = useRef<HTMLInputElement | null>(null);
  const listenBackgroundInputRef = useRef<HTMLInputElement | null>(null);
  const [avatarCropDraft, setAvatarCropDraft] = useState<{
    kind: AvatarImageKind;
    src: string;
    title: string;
  } | null>(null);
  const groupChatDisplayTitle = getDisplayGroupChatTitle(groupChatTitle);
  const handleWenyouBack = useCallback(() => {
    if (wenyouBackHandlerRef.current?.()) return;
    setActiveScreen(null);
  }, []);
  const loadDailyWhisper = useCallback(
    async (forceRefresh = false) => {
      if (forceRefresh) setTodayNoteRefreshing(true);
      try {
        const path = forceRefresh ? "/miniapp-api/daily-whisper?refresh=1" : "/miniapp-api/daily-whisper";
        const j = await apiJson<{ ok?: boolean; text?: string; error?: string }>(path);
        if (!j?.ok) throw new Error(j?.error || "刷新失败");
        const text = (j?.text || "").toString().trim();
        if (text) setDailyWhisper(text);
        if (forceRefresh) toast(text ? "Today note 已刷新" : "还没有新的 note，继续显示上一条");
      } catch (e: any) {
        if (forceRefresh) toast(`Today note 刷新失败：${e?.message || e}`);
      } finally {
        if (forceRefresh) setTodayNoteRefreshing(false);
      }
    },
    [toast],
  );

  const handleIncomingVoiceCallInvite = useCallback((raw: unknown) => {
    const invite = normalizeVoiceCallInvite(raw);
    if (!invite) return;
    setIncomingVoiceCallInvite((prev) => (prev?.callId === invite.callId ? prev : invite));
    setCallHubInitialView("voice");
    setMainTab("chats");
    setShowCallHub(true);
  }, []);

  const openCallHub = useCallback((initialView: CallHubInitialView) => {
    setCallHubInitialView(initialView);
    setShowCallHub(true);
  }, []);

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
    try {
      const pending = localStorage.getItem(VOICE_CALL_PENDING_INVITE_KEY);
      if (pending) {
        localStorage.removeItem(VOICE_CALL_PENDING_INVITE_KEY);
        handleIncomingVoiceCallInvite(pending);
      }
    } catch {}
    const listener = (event: Event) => {
      handleIncomingVoiceCallInvite((event as CustomEvent).detail);
    };
    window.addEventListener("sumitalk-voice-call-invite", listener);
    return () => window.removeEventListener("sumitalk-voice-call-invite", listener);
  }, [handleIncomingVoiceCallInvite]);

  useEffect(() => {
    if (!deferHomeExtras) return;
    void loadDailyWhisper(false);
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
      localStorage.setItem("miniapp.ui.expandReasoning", expandReasoningByDefault ? "1" : "0");
      localStorage.setItem("miniapp.ui.chatBackgroundOpacity", String(chatBackgroundOpacity));
      localStorage.setItem("miniapp.ui.userBubbleStyle", userBubbleStyle);
      localStorage.setItem("miniapp.ui.assistantBubbleStyle", assistantBubbleStyle);
      localStorage.setItem(GROUP_FREE_CHAT_MODE_STORAGE_KEY, groupFreeChatEnabled ? "1" : "0");
      localStorage.setItem("miniapp.ui.myAvatar", myAvatarImage);
      localStorage.setItem("miniapp.ui.duAvatar", duAvatarImage);
      localStorage.setItem("miniapp.ui.benbenAvatar", benbenAvatarImage);
      localStorage.setItem("miniapp.ui.groupChatTitle", limitGroupChatTitle(groupChatTitle));
      localStorage.setItem("miniapp.ui.chatBackgroundImage", chatBackgroundImage);
      localStorage.setItem(LISTEN_BACKGROUND_STORAGE_KEY, listenBackgroundImage);
    } catch {}
  }, [
    transparentBubbleEnabled,
    showChatAvatars,
    chatContentFontSize,
    chatTitleFontSize,
    chatFontKey,
    showChatTimestamps,
    chatTimeFormat,
    expandReasoningByDefault,
    chatBackgroundOpacity,
    userBubbleStyle,
    assistantBubbleStyle,
    groupFreeChatEnabled,
    myAvatarImage,
    duAvatarImage,
    benbenAvatarImage,
    groupChatTitle,
    chatBackgroundImage,
    listenBackgroundImage,
  ]);

  function applyAvatarImage(kind: AvatarImageKind, dataUrl: string) {
    if (kind === "myAvatar") {
      setMyAvatarImage(dataUrl);
      toast("我的头像已更新");
    } else if (kind === "duAvatar") {
      setDuAvatarImage(dataUrl);
      toast("渡的头像已更新");
    } else {
      setBenbenAvatarImage(dataUrl);
      toast("笨笨头像已更新");
    }
  }

  async function handleImageSelection(file: File | undefined, kind: AvatarImageKind | "background" | "listenBackground") {
    if (!file) return;
    try {
      if (kind === "background") {
        setChatBackgroundImage(await buildBackgroundDataUrl(file));
        toast("聊天背景已更新");
        return;
      }
      if (kind === "listenBackground") {
        setListenBackgroundImage(await buildBackgroundDataUrl(file));
        toast("一起听背景已更新");
        return;
      }
      const src = await fileToDataUrl(file);
      setAvatarCropDraft({
        kind,
        src,
        title: kind === "myAvatar" ? "我的头像" : kind === "duAvatar" ? "渡的头像" : "笨笨头像",
      });
    } catch (e: any) {
      toast(`图片设置失败：${e?.message || e}`);
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

  function saveGroupFreeChatMode(next: boolean) {
    setGroupFreeChatEnabled(next);
    toast(next ? "自由聊模式已开启" : "自由聊模式已关闭");
  }

  useEffect(() => {
    let disposed = false;
    const removePromise = CapacitorApp.addListener("backButton", async () => {
      if (disposed) return;
      if (showCallHub) {
        if (callHubBackHandlerRef.current?.()) return;
        setShowCallHub(false);
        return;
      }
      if (deviceManagerOpen && onCloseDevices) {
        onCloseDevices();
        return;
      }
      if (panel === "secret-drawer" && secretDrawerBackHandlerRef.current?.()) {
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
      if (showPromptManager) {
        setShowPromptManager(false);
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
      if (showMemoryNebula) {
        setShowMemoryNebula(false);
        return;
      }
      if (showCoRead) {
        setShowCoRead(false);
        return;
      }
      if (showListenWithDu) {
        setShowListenWithDu(false);
        return;
      }
      if (showDiagnostics) {
        setShowDiagnostics(false);
        return;
      }
      if (activeScreen === "wenyou" && wenyouBackHandlerRef.current?.()) {
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
    showPromptManager,
    showCoRead,
    showListenWithDu,
    showDuDay,
    showMemoryNebula,
    showPixelHome,
    showPersonalization,
    showSchedule,
    showSettings,
    showStayWithDu,
    showDiagnostics,
  ]);

  const renderMainTab = () => {
    if (mainTab === "daily") {
      return (
        <div className="bg-[#FDFDFD] px-4 pb-6" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 44px)" }}>
          <h1 className="mb-6 text-[22px] font-medium tracking-tight text-gray-900">日常</h1>
          <div className="overflow-hidden rounded-[28px] border border-gray-100/60 bg-white shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <ListRow
              icon={<SunIconMini />}
              label="渡的一天"
              onClick={() => setShowDuDay(true)}
            />
            <ListRow
              icon={<HeartIconMini />}
              label="Stay with Du"
              onClick={() => setShowStayWithDu(true)}
            />
            <ListRow
              icon={<HomeIconMini />}
              label="小家"
              onClick={() => setShowPixelHome(true)}
            />
            <ListRow
              icon={<StarIconMini />}
              label="记忆星云"
              onClick={() => setShowMemoryNebula(true)}
            />
            <ListRow
              icon={<BookOpenIcon />}
              label="和渡一起读"
              onClick={() => setShowCoRead(true)}
            />
            <ListRow
              icon={<HeadphonesIconMini />}
              label="和渡一起听"
              onClick={() => {
                setListenWithDuMounted(true);
                setShowListenWithDu(true);
              }}
            />
            <ListRow
              icon={<PhoneIconMini />}
              label="通话记录"
              onClick={() => openCallHub("records")}
            />
            <ListRow
              icon={<NotebookPenIconMini />}
              label="渡的记事本"
              onClick={() => setPanel("du-notebook")}
            />
            <ListRow
              icon={<CabinetFilingIconMini />}
              label="秘密抽屉"
              onClick={() => setPanel("secret-drawer")}
              last
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
            <ListRow icon={<BrainIconMini />} label="记忆调试" onClick={() => setPanel("memory-debug")} />
            <ListRow icon={<HeartIconMini />} label="健康数据" onClick={() => setPanel("health-data")} />
            <ListRow icon={<GraduationCapIconMini />} label="学习" onClick={() => setPanel("study-room")} />
            <ListRow icon={<CalendarIconMini />} label="存钱打卡" onClick={() => setPanel("budget-checkin")} />
            <ListRow icon={<ClockIconMini />} label="闹钟" onClick={() => setShowAlarm(true)} />
            <ListRow icon={<CalendarIconMini />} label="日历" onClick={() => setShowSchedule(true)} />
            <ListRow icon={<SpeakerIconMini />} label="小爱音箱" onClick={() => setPanel("xiaoai")} last />
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
              icon={<GitMergeIcon />}
              label="自由聊模式"
              enabled={groupFreeChatEnabled}
              onToggle={saveGroupFreeChatMode}
            />
            <ListRow icon={<UserRoundCogIconMini />} label="Prompt 管理" onClick={() => setShowPromptManager(true)} />
            <ListRow icon={<FeatherIcon />} label="个性化" onClick={() => setShowPersonalization(true)} />
            <ListRow icon={<CpuIcon />} label="系统诊断" onClick={() => setShowDiagnostics(true)} />
            <ListRow icon={<ToggleRightIcon />} label="API管理" onClick={() => setShowSettings(true)} />
            <ListRow icon={<CloudUploadIconMini />} label="上报管理" onClick={() => setPanel("reporting")} />
            <ListRow icon={<FileTextIcon />} label="记忆存储管理" onClick={() => setPanel("chat-storage")} />
            <ListRow icon={<SmartphoneIconMini />} label="设备管理" onClick={() => onOpenDevices?.()} />
            {onLogout ? <ListRow icon={<LogoutIconMini />} label="退出登录" onClick={onLogout} last /> : null}
          </div>
        </div>
      );
    }
    return (
      <ChatsHome
        dailyWhisper={dailyWhisper}
        duAvatarImage={duAvatarImage}
        benbenAvatarImage={benbenAvatarImage}
        groupTitle={groupChatDisplayTitle}
        privateWindowId={MAIN_SUMITALK_DISPLAY_WINDOW_ID}
        groupWindowId={buildGroupDisplayWindowId(sharedChatWindowId)}
        onOpenDu={() => setActiveScreen("du")}
        onOpenGroup={() => setActiveScreen("group")}
        onOpenWenyou={() => setActiveScreen("wenyou")}
        onRefreshTodayNote={() => {
          if (!todayNoteRefreshing) void loadDailyWhisper(true);
        }}
        todayNoteRefreshing={todayNoteRefreshing}
      />
    );
  };

  const hasSecondaryPageOpen =
    !!activeScreen ||
    !!deviceManagerOpen ||
    !!panel ||
    showSettings ||
    showPromptManager ||
    showSchedule ||
    showAlarm ||
    showPersonalization ||
    showDuDay ||
    showStayWithDu ||
    showPixelHome ||
    showMemoryNebula ||
    showCoRead ||
    showListenWithDu ||
    showDiagnostics ||
    showCallHub;

  return (
    <div className="relative min-h-dvh safe-bottom overflow-hidden bg-[#FDFDFD] text-gray-900">
      <style>
        {`@font-face {
          font-family: 'SumiChatScript';
          src: url("${chatScriptFontUrl}") format("truetype");
          font-style: normal;
          font-weight: 400;
          font-display: swap;
        }`}
      </style>
      {activeScreen === "du" ? (
        <MainChatScreen
          title="渡"
          windowId={sharedChatWindowId}
          displayWindowId={MAIN_SUMITALK_DISPLAY_WINDOW_ID}
          avatarLabel="渡"
          accent="du"
          transparentBubbleEnabled={transparentBubbleEnabled}
          showChatAvatars={showChatAvatars}
          chatContentFontSize={chatContentFontSize}
          chatTitleFontSize={chatTitleFontSize}
          chatFontFamily={resolveChatFontFamily(chatFontKey)}
          showChatTimestamps={showChatTimestamps}
          chatTimeFormat={chatTimeFormat}
          expandReasoningByDefault={expandReasoningByDefault}
          chatBackgroundOpacity={chatBackgroundOpacity}
          userBubbleStyle={userBubbleStyle}
          assistantBubbleStyle={assistantBubbleStyle}
          myAvatarImage={myAvatarImage}
          duAvatarImage={duAvatarImage}
          benbenAvatarImage={benbenAvatarImage}
          chatBackgroundImage={chatBackgroundImage}
          onBack={() => setActiveScreen(null)}
          onOpenStickers={() => setPanel("stickers")}
          onOpenCall={() => openCallHub("voice")}
        />
      ) : null}
      {activeScreen === "group" ? (
        <MainChatScreen
          title={groupChatDisplayTitle}
          windowId={sharedChatWindowId}
          displayWindowId={buildGroupDisplayWindowId(sharedChatWindowId)}
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
          expandReasoningByDefault={expandReasoningByDefault}
          chatBackgroundOpacity={chatBackgroundOpacity}
          userBubbleStyle={userBubbleStyle}
          assistantBubbleStyle={assistantBubbleStyle}
          myAvatarImage={myAvatarImage}
          duAvatarImage={duAvatarImage}
          benbenAvatarImage={benbenAvatarImage}
          chatBackgroundImage={chatBackgroundImage}
          groupFreeChatEnabled={groupFreeChatEnabled}
          onBack={() => setActiveScreen(null)}
          onOpenStickers={() => setPanel("stickers")}
          onOpenCall={() => openCallHub("voice")}
        />
      ) : null}
      {activeScreen === "wenyou" ? (
        <FullScreenPane title="文游" accent="wenyou" onBack={handleWenyouBack} edgeSwipeBack>
          <LazyPane><WenyouTab initialView="hub" backHandlerRef={wenyouBackHandlerRef} windowId={sharedChatWindowId} /></LazyPane>
        </FullScreenPane>
      ) : null}
      {!activeScreen ? (
        <>
          <div className="relative min-h-dvh overflow-y-auto pb-[104px]">
            {renderMainTab()}
          </div>
          {!hasSecondaryPageOpen ? <BottomNav current={mainTab} onChange={setMainTab} /> : null}
        </>
      ) : null}

      {panel === "logs" ? (
        <FullScreenPane title="日志" accent="neutral" headerRightPortalId="logs-header-status" onBack={() => setPanel(null)}>
          <LazyPane><LogsTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "reasoning" ? (
        <FullScreenPane title="思维链" accent="neutral" onBack={() => setPanel(null)}>
          <LazyPane><ReasoningTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "memory-debug" ? (
        <FullScreenPane title="记忆调试" accent="neutral" headerMode="simple" headerRightPortalId="memory-debug-header-status" onBack={() => setPanel(null)}>
          <LazyPane><MemoryDebugTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "du-notebook" ? (
        <FullScreenPane title="渡的记事本" accent="neutral" onBack={() => setPanel(null)}>
          <LazyPane><DuNotebookTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "study-room" ? (
        <FullScreenPane title="学习" accent="neutral" headerMode="simple" onBack={() => setPanel(null)}>
          <LazyPane><StudyRoomTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "budget-checkin" ? (
        <FullScreenPane title="存钱打卡" accent="neutral" headerMode="simple" onBack={() => setPanel(null)}>
          <LazyPane><BudgetCheckInTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "secret-drawer" ? (
        <LazyPane><SecretDrawerTab onExit={() => setPanel(null)} backHandlerRef={secretDrawerBackHandlerRef} /></LazyPane>
      ) : null}
      {panel === "stickers" ? (
        <FullScreenPane title="表情包" accent="neutral" onBack={() => setPanel(null)}>
          <LazyPane><StickersTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "xiaoai" ? (
        <FullScreenPane title="小爱音箱" accent="neutral" headerMode="simple" onBack={() => setPanel(null)}>
          <LazyPane><XiaoAISettingsTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "health-data" ? (
        <FullScreenPane title="健康数据" accent="neutral" headerMode="simple" headerRightPortalId="health-data-header-actions" onBack={() => setPanel(null)}>
          <LazyPane><HealthDataScreen /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "reporting" ? (
        <FullScreenPane title="上报管理" accent="neutral" headerMode="simple" headerRightPortalId="reporting-header-actions" onBack={() => setPanel(null)}>
          <LazyPane><ReportingManagementScreen /></LazyPane>
        </FullScreenPane>
      ) : null}
      {panel === "chat-storage" ? (
        <FullScreenPane title="记忆存储管理" accent="neutral" headerMode="simple" headerRightPortalId="chat-storage-header-actions" onBack={() => setPanel(null)}>
          <LazyPane><ChatStorageManagementScreen /></LazyPane>
        </FullScreenPane>
      ) : null}

      {showSettings ? (
        <FullScreenPane title="API管理" accent="neutral" onBack={() => setShowSettings(false)}>
          <LazyPane><SettingsUpstream /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showPromptManager ? <PromptManagerScreen onClose={() => setShowPromptManager(false)} /> : null}
      {showSchedule ? (
        <FullScreenPane title="日历" accent="neutral" onBack={() => setShowSchedule(false)}>
          <LazyPane><ScheduleTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showAlarm ? (
        <FullScreenPane title="闹钟" accent="neutral" headerMode="simple" headerRightPortalId="alarm-header-status" onBack={() => setShowAlarm(false)}>
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
            onCycleChatFont={() => setChatFontKey(nextChatFont)}
            showChatTimestamps={showChatTimestamps}
            onToggleShowChatTimestamps={setShowChatTimestamps}
            chatTimeFormat={chatTimeFormat}
            onCycleChatTimeFormat={() => setChatTimeFormat((prev) => (prev === "hhmm" ? "ampm" : "hhmm"))}
            expandReasoningByDefault={expandReasoningByDefault}
            onToggleExpandReasoningByDefault={setExpandReasoningByDefault}
            chatBackgroundOpacity={chatBackgroundOpacity}
            onChangeChatBackgroundOpacity={setChatBackgroundOpacity}
            userBubbleStyle={userBubbleStyle}
            onCycleUserBubbleStyle={() => setUserBubbleStyle(nextBubbleStyle)}
            assistantBubbleStyle={assistantBubbleStyle}
            onCycleAssistantBubbleStyle={() => setAssistantBubbleStyle(nextBubbleStyle)}
            myAvatarImage={myAvatarImage}
            duAvatarImage={duAvatarImage}
            benbenAvatarImage={benbenAvatarImage}
            groupChatTitle={groupChatTitle}
            chatBackgroundImage={chatBackgroundImage}
            listenBackgroundImage={listenBackgroundImage}
            onPickMyAvatar={() => myAvatarInputRef.current?.click()}
            onPickDuAvatar={() => duAvatarInputRef.current?.click()}
            onPickBenbenAvatar={() => benbenAvatarInputRef.current?.click()}
            onChangeGroupChatTitle={(next) => setGroupChatTitle(limitGroupChatTitle(next))}
            onPickChatBackground={() => backgroundInputRef.current?.click()}
            onPickListenBackground={() => listenBackgroundInputRef.current?.click()}
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
        <LazyPane><PixelHomeTab /></LazyPane>
      ) : null}
      {showMemoryNebula ? (
        <LazyPane><MemoryNebulaTab onBack={() => setShowMemoryNebula(false)} /></LazyPane>
      ) : null}
      {showCoRead ? <LazyPane><CoReadScreen onBack={() => setShowCoRead(false)} windowId={sharedChatWindowId} /></LazyPane> : null}
      {listenWithDuMounted ? (
        <LazyPane>
          <ListenWithDuScreen
            onBack={() => setShowListenWithDu(false)}
            isActive={showListenWithDu}
            backgroundImage={listenBackgroundImage}
            myAvatarImage={myAvatarImage}
            duAvatarImage={duAvatarImage}
          />
        </LazyPane>
      ) : null}
      {showDiagnostics ? (
        <FullScreenPane title="系统诊断" accent="neutral" headerMode="simple" onBack={() => setShowDiagnostics(false)}>
          <DiagnosticsScreen />
        </FullScreenPane>
      ) : null}
      {showCallHub ? (
        <LazyPane>
          <CallHubScreen
            onClose={() => setShowCallHub(false)}
            duAvatarImage={duAvatarImage}
            initialView={callHubInitialView}
            backHandlerRef={callHubBackHandlerRef}
            incomingInvite={incomingVoiceCallInvite}
            onIncomingInviteConsumed={() => setIncomingVoiceCallInvite(null)}
          />
        </LazyPane>
      ) : null}
      {avatarCropDraft ? (
        <AvatarCropModal
          src={avatarCropDraft.src}
          title={avatarCropDraft.title}
          onCancel={() => setAvatarCropDraft(null)}
          onConfirm={(dataUrl) => {
            applyAvatarImage(avatarCropDraft.kind, dataUrl);
            setAvatarCropDraft(null);
          }}
        />
      ) : null}
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
        ref={benbenAvatarInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          void handleImageSelection(e.target.files?.[0], "benbenAvatar");
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
      <input
        ref={listenBackgroundInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          void handleImageSelection(e.target.files?.[0], "listenBackground");
          e.currentTarget.value = "";
        }}
      />
    </div>
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
