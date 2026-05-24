import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { useToast } from "./toast";
import { apiJson } from "./api";
import { ChatsHome } from "./ChatsHome";
import { BottomNav, type MainTab } from "./BottomNav";
import { CorePromptEditor } from "./CorePromptEditor";
import { DiagnosticsScreen } from "./DiagnosticsScreen";
import { FullScreenPane } from "./FullScreenPane";
import { MainChatScreen } from "./MainChatScreen";
import { PersonalizationScreen } from "./PersonalizationScreen";
import { FloatingBallSettingRow, ListRow, PageCardRow, SwitchSettingRow } from "./SettingsRows";
import {
  DEFAULT_GROUP_CHAT_TITLE,
  getDisplayGroupChatTitle,
  limitGroupChatTitle,
  resolveChatFontFamily,
  type BubbleStyleKey,
} from "./chatAppearance";
import {
  type ChatFontKey,
  type ChatTimeFormat,
} from "./chatMessages";
import { MAIN_SUMITALK_DISPLAY_WINDOW_ID, buildGroupDisplayWindowId } from "./chatWindowIds";
import {
  BookOpenIcon,
  CalendarIconMini,
  ClockIconMini,
  CodeIcon,
  CpuIcon,
  FeatherIcon,
  FileTextIcon,
  GitMergeIcon,
  HeartIconMini,
  HomeIconMini,
  LogoutIconMini,
  MuteIconMini,
  SmartphoneIconMini,
  SunIconMini,
  ToggleRightIcon,
} from "./icons";
import { SumiOverlay } from "../plugins/sumi-overlay";
import { buildAvatarDataUrl, buildBackgroundDataUrl } from "./imageDataUrl";
import { clampStoredNumber, readStoredBoolean, readStoredNumber, readStoredString } from "./uiStorage";

const LISTEN_BACKGROUND_STORAGE_KEY = "miniapp.listenWithDu.backgroundImage";

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
const ListenWithDuScreen = lazy(() => import("./tabs/ListenWithDuScreen").then((m) => ({ default: m.ListenWithDuScreen })));
const StudyRoomTab = lazy(() => import("./tabs/StudyRoomTab").then((m) => ({ default: m.StudyRoomTab })));

type PanelId = "logs" | "reasoning" | "memory-debug" | "du-notebook" | "stickers" | null;
type SilenceModeResponse = {
  ok?: boolean;
  enabled?: boolean;
  updated_at?: string;
  error?: string;
};
type ChatScreenId = "du" | "group" | "wenyou" | null;

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
  const [showCorePrompt, setShowCorePrompt] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showAlarm, setShowAlarm] = useState(false);
  const [showPersonalization, setShowPersonalization] = useState(false);
  const [showDuDay, setShowDuDay] = useState(false);
  const [showStayWithDu, setShowStayWithDu] = useState(false);
  const [showPixelHome, setShowPixelHome] = useState(false);
  const [showCoRead, setShowCoRead] = useState(false);
  const [showListenWithDu, setShowListenWithDu] = useState(false);
  const [showCallHub, setShowCallHub] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [mainTab, setMainTab] = useState<MainTab>("chats");
  const [activeScreen, setActiveScreen] = useState<ChatScreenId>(null);
  const wenyouBackHandlerRef = useRef<(() => boolean) | null>(null);
  const [silenceModeEnabled, setSilenceModeEnabled] = useState(false);
  const [silenceModeSaving, setSilenceModeSaving] = useState(false);
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
    showTokenCount,
    expandReasoningByDefault,
    chatBackgroundOpacity,
    userBubbleStyle,
    assistantBubbleStyle,
    myAvatarImage,
    duAvatarImage,
    benbenAvatarImage,
    groupChatTitle,
    chatBackgroundImage,
    listenBackgroundImage,
  ]);

  async function handleImageSelection(
    file: File | undefined,
    kind: "myAvatar" | "duAvatar" | "benbenAvatar" | "background" | "listenBackground",
  ) {
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
      const next = await buildAvatarDataUrl(file);
      if (kind === "myAvatar") {
        setMyAvatarImage(next);
        toast("我的头像已更新");
      } else if (kind === "duAvatar") {
        setDuAvatarImage(next);
        toast("渡的头像已更新");
      } else {
        setBenbenAvatarImage(next);
        toast("笨笨头像已更新");
      }
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
    showCorePrompt,
    showCoRead,
    showListenWithDu,
    showDuDay,
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
          <div className="space-y-4">
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
              icon={<HeartIconMini />}
              label="和渡一起听"
              onClick={() => setShowListenWithDu(true)}
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
    if (mainTab === "study") {
      return (
        <LazyPane>
          <StudyRoomTab />
        </LazyPane>
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
    showCorePrompt ||
    showSchedule ||
    showAlarm ||
    showPersonalization ||
    showDuDay ||
    showStayWithDu ||
    showPixelHome ||
    showCoRead ||
    showListenWithDu ||
    showDiagnostics ||
    showCallHub;

  return (
    <div className="relative min-h-dvh safe-bottom overflow-hidden bg-[#FDFDFD] text-gray-900">
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
          showTokenCount={showTokenCount}
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
          onOpenCall={() => setShowCallHub(true)}
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
          showTokenCount={showTokenCount}
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
          onOpenCall={() => setShowCallHub(true)}
        />
      ) : null}
      {activeScreen === "wenyou" ? (
        <FullScreenPane title="文游" accent="wenyou" onBack={handleWenyouBack} edgeSwipeBack>
          <LazyPane><WenyouTab initialView="hub" backHandlerRef={wenyouBackHandlerRef} windowId={sharedChatWindowId} /></LazyPane>
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
        <FullScreenPane title="像素小家" accent="neutral" headerMode="simple" edgeSwipeBack onBack={() => setShowPixelHome(false)}>
          <LazyPane><PixelHomeTab /></LazyPane>
        </FullScreenPane>
      ) : null}
      {showCoRead ? <LazyPane><CoReadScreen onBack={() => setShowCoRead(false)} windowId={sharedChatWindowId} /></LazyPane> : null}
      {showListenWithDu ? <LazyPane><ListenWithDuScreen onBack={() => setShowListenWithDu(false)} backgroundImage={listenBackgroundImage} /></LazyPane> : null}
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
