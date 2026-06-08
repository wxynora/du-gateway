import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiJson, consumePendingPanelDeviceIdMigration, getOrCreatePanelDeviceId, setPanelToken } from "./api";
import { AvatarBubble, ChatActionButton, ChatBubbleFrame, ChatHeaderStatus, HtmlBlock, PlainTextBlock, RichTextBlock, copyText, formatTokenCountValue } from "./ChatPresentation";
import {
  TRANSPARENT_BUBBLE_CLASS,
  resolveBubbleClass,
  resolveBubbleSkin,
  type BubbleStyleKey,
} from "./chatAppearance";
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
  buildCodexGroupRecentMessages,
  buildGroupTurnUserContent,
  extractAssistantReasoning,
  extractAssistantReplyText,
  extractTokenCount,
  formatClockTime,
  getChatSearchMatchId,
  groupRoleLabel,
  groupChatMessages,
  pickBetterHistory,
  sanitizeHistoryMessages,
  shouldShowGroupTime,
  type ChatDraftMessage,
  type ChatSearchMatch,
  type ChatTimeFormat,
} from "./chatMessages";
import {
  MAIN_SUMITALK_DISPLAY_WINDOW_ID,
  sumitalkHistoryPath,
  sumitalkHistoryPayload,
} from "./chatWindowIds";
import {
  ArrowUpIcon,
  ChevronDownMini,
  ChevronLeftIcon,
  ChevronUpMini,
  CopyIconMini,
  PlusIcon,
  SearchIconMini,
} from "./icons";
import { SumiOverlay } from "../plugins/sumi-overlay";
import {
  attachChatJobToOperation,
  completeChatOperation,
  createChatDraftTurn,
  failChatOperation,
  getChatOperation,
  listActiveChatOperations,
  migrateLocalChatHistoriesToDevice,
  migrateLocalChatHistoryDevice,
  readLocalChatHistory,
  readLocalChatHistoryRows,
  writeLocalChatHistory,
  type ChatOperation,
} from "./storage/chatHistoryDb";
import { useCodexGroupTaskRealtime, type CodexGroupTaskRealtimeTask } from "./hooks/useCodexGroupTaskRealtime";
import { readMusicBgmContext } from "./listenBgm";
import { useToast } from "./toast";
import {
  apiJsonWithTimeout,
  createSumiTalkChatJob,
  isAbortLikeError,
  waitForSumiTalkChatJob,
  waitMs,
} from "./chat/sumitalkChatClient";
type CodexGroupChatTask = {
  id?: string;
  mode?: string;
  status?: "queued" | "running" | "done" | "error" | "cancelled";
  response?: string;
  error?: string;
  client_request_id?: string;
  coding_thread_key?: string;
};
type CodexGroupChatTaskResponse = {
  ok?: boolean;
  task?: CodexGroupChatTask | null;
  error?: string;
};
const CODEX_GROUP_CHAT_POLL_MS = 1000;
const CODEX_GROUP_CHAT_TIMEOUT_MS = 10 * 60 * 1000;
const CODEX_GROUP_CHAT_CREATE_TIMEOUT_MS = 30000;
const CODEX_GROUP_CHAT_CREATE_RETRY_TIMEOUT_MS = 45000;
const GROUP_DISCUSSION_MAX_FOLLOWUPS = 3;
const GROUP_DISCUSSION_TRIGGER_RE = /(?:讨论|商量|你俩|你们俩|自由聊|一起聊|一起看看|聊两句|聊几句|互相|碰一下|合计|对一下|头脑风暴)/i;
const GROUP_DISCUSSION_STOP_RE = /(?:先这样|先到这|就先这样|差不多(?:了|就行|可以)|可以收尾|不用继续|别聊了|到这里|我来改|我去改|先按这个)/i;
const GROUP_DISCUSSION_MANUAL_STOP_RE = /(?:停一下|停止|暂停|打断|中断|别聊了|不用继续|先这样|收尾|到这里|算了)/i;
const GROUP_DISCUSSION_CONTINUE_RE = /(?:继续聊|接着聊|再聊|继续讨论|再讨论|你俩继续|你们俩继续|让(?:他们|你俩|你们俩)继续)/i;

function uniqueNonEmptyStrings(values: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const item = String(value || "").trim();
    if (!item || seen.has(item)) continue;
    seen.add(item);
    out.push(item);
  }
  return out;
}

type GroupReplyTargets = {
  du: boolean;
  benben: boolean;
  mentions: string[];
  benbenMode: "daily_chat" | "coding_task";
  codingThreadKey: string;
  freeDiscussion: boolean;
};
type GroupDiscussionSpeaker = "du" | "benben";
type GroupDiscussionSnapshot = {
  topic: string;
  replyTarget: string;
  lastSpeaker: GroupDiscussionSpeaker;
  lastContent: string;
  freeRoute: boolean;
  updatedAt: number;
};

function resolveCodingThreadKey(content: string): string {
  const text = String(content || "").toLowerCase();
  if (/文游|主神|副本|玩家|道具|抽卡|结算|怪物|npc|wenyou/.test(text)) return "wenyou";
  if (/miniapp|小程序|前端|页面|界面|按钮|气泡|样式|ui|tsx|react/.test(text)) return "miniapp";
  if (/studyroom|学习|题库|错题|资料整理/.test(text)) return "studyroom";
  if (/小爱|音箱|migpt|xiaoai/.test(text)) return "xiaoai";
  if (/后端|接口|路由|网关|存储|r2|api|service|route/.test(text)) return "backend";
  if (/文档|方案|markdown|debug_index|索引/.test(text)) return "docs";
  return "general";
}

function resolveGroupReplyTargets(content: string): GroupReplyTargets {
  const text = String(content || "");
  const hasDuMention = /[@＠]\s*(?:渡|du)(?![a-z0-9_])/i.test(text);
  const hasBenbenMention = /[@＠]\s*(?:笨笨机|笨笨|benben|codex)(?![a-z0-9_])/i.test(text);
  const hasFreeDiscussion = hasDuMention && hasBenbenMention && GROUP_DISCUSSION_TRIGGER_RE.test(text);
  const hasCodingCommand = hasBenbenMention && !hasFreeDiscussion && /(?:改代码|开工|施工|debug|调试|修\s*bug|修一下|实现|落地|加上|做一下)/i.test(text);
  const mentions = uniqueNonEmptyStrings([
    hasDuMention ? "du" : "",
    hasBenbenMention ? "benben" : "",
  ]);
  if (mentions.length) {
    return {
      du: hasDuMention,
      benben: hasBenbenMention,
      mentions,
      benbenMode: hasCodingCommand ? "coding_task" : "daily_chat",
      codingThreadKey: hasCodingCommand ? resolveCodingThreadKey(text) : "",
      freeDiscussion: hasFreeDiscussion,
    };
  }
  return { du: true, benben: false, mentions: [], benbenMode: "daily_chat", codingThreadKey: "", freeDiscussion: false };
}

function isBenbenCancelCommand(content: string): boolean {
  const text = String(content || "");
  const hasBenbenMention = /[@＠]\s*(?:笨笨机|笨笨|benben|codex)(?![a-z0-9_])/i.test(text);
  return hasBenbenMention && /(?:停一下|停止|取消|中断|打断|别改了|别施工|别做了|暂停|kill|算了)/i.test(text);
}

function isGroupDiscussionStopCommand(content: string): boolean {
  return GROUP_DISCUSSION_MANUAL_STOP_RE.test(String(content || ""));
}

function isGroupDiscussionContinueCommand(content: string): boolean {
  return GROUP_DISCUSSION_CONTINUE_RE.test(String(content || ""));
}

function parseGroupDiscussionContinueTurns(content: string): number {
  const text = String(content || "");
  if (/[一1]/.test(text)) return 1;
  if (/[三3]/.test(text)) return 3;
  return 2;
}

function codexGroupTaskStatusText(task: Pick<CodexGroupChatTask, "mode" | "status">): string {
  const mode = String(task.mode || "").trim();
  const status = String(task.status || "").trim();
  const isCoding = mode === "coding_task";
  if (isCoding) {
    if (status === "running") return "笨笨施工中，正在改代码 / debug...";
    if (status === "queued") return "笨笨已接单，等待施工...";
    if (status === "cancelled") return "笨笨施工已取消。";
    return "笨笨收到开工指令，正在接单...";
  }
  if (status === "cancelled") return "笨笨任务已取消。";
  if (status === "running") return "笨笨正在看群聊...";
  if (status === "queued") return "笨笨任务已创建，等我一下...";
  return "笨笨正在看群聊...";
}

function groupDiscussionShouldStop(content: string): boolean {
  return GROUP_DISCUSSION_STOP_RE.test(String(content || ""));
}

function mentionedGroupSpeaker(content: string, speaker: GroupDiscussionSpeaker): boolean {
  const text = String(content || "");
  if (speaker === "du") return /[@＠]\s*(?:渡|du)(?![a-z0-9_])/i.test(text);
  return /[@＠]\s*(?:笨笨机|笨笨|benben|codex)(?![a-z0-9_])/i.test(text);
}

function resolveNextGroupDiscussionSpeaker(lastSpeaker: GroupDiscussionSpeaker, lastContent: string): GroupDiscussionSpeaker {
  const mentionsDu = mentionedGroupSpeaker(lastContent, "du");
  const mentionsBenben = mentionedGroupSpeaker(lastContent, "benben");
  if (mentionsDu && !mentionsBenben) return "du";
  if (mentionsBenben && !mentionsDu) return "benben";
  return lastSpeaker === "du" ? "benben" : "du";
}

function resolveNextFreeDiscussionSpeaker(lastSpeaker: GroupDiscussionSpeaker, lastContent: string): GroupDiscussionSpeaker | null {
  const mentionsDu = mentionedGroupSpeaker(lastContent, "du");
  const mentionsBenben = mentionedGroupSpeaker(lastContent, "benben");
  if (mentionsDu && !mentionsBenben) return "du";
  if (mentionsBenben && !mentionsDu) return "benben";
  if (mentionsDu && mentionsBenben) return lastSpeaker === "du" ? "benben" : "du";
  return null;
}

function buildGroupFreeDiscussionOpeningContent(messages: ChatDraftMessage[], topic: string): string {
  const lines = (Array.isArray(messages) ? messages : [])
    .filter((msg) => msg.status !== "pending" && msg.status !== "failed")
    .filter((msg) => String(msg.content || "").trim())
    .slice(-10)
    .map((msg) => `${groupRoleLabel(msg.role)}：${String(msg.content || "").trim()}`);
  const fallbackTopic = String(topic || "").trim();
  if (!lines.length && fallbackTopic) lines.push(`辛玥：${fallbackTopic}`);
  return [
    "【三人群聊自由讨论开场】",
    "辛玥在自由聊模式里发了一条群聊广播，这句话同时发给你和笨笨，是想让你们俩围绕这个话题自由聊几句。",
    "你先发一条自然的群聊开场；想让笨笨接，就在正文里明确 @笨笨，不 @ 就自然停。不要把历史里笨笨之前对辛玥的回复当成对你的私聊。",
    "只输出渡要发到群里的正文，不要写“渡：”前缀，不要解释规则。",
    `原话题：${fallbackTopic || "（无）"}`,
    "最近群聊：",
    ...lines,
  ].join("\n");
}

function buildGroupDiscussionUserContent(
  messages: ChatDraftMessage[],
  topic: string,
  turnIndex: number,
  maxTurns: number,
): string {
  const lines = (Array.isArray(messages) ? messages : [])
    .filter((msg) => msg.status !== "pending" && msg.status !== "failed")
    .filter((msg) => String(msg.content || "").trim())
    .slice(-12)
    .map((msg) => `${groupRoleLabel(msg.role)}：${String(msg.content || "").trim()}`);
  const fallbackTopic = String(topic || "").trim();
  if (!lines.length && fallbackTopic) lines.push(`辛玥：${fallbackTopic}`);
  return [
    "【三人群聊自由讨论接力】",
    `原话题：${fallbackTopic || "（无）"}`,
    `这是自动接力第 ${turnIndex}/${maxTurns} 条。你是渡，接着最近一条自然回复一小段。`,
    "规则：这是辛玥、渡、笨笨都能看见的公共群聊；辛玥在自由聊模式里的发言默认同时发给你和笨笨。不要把笨笨上一句默认理解成对你的私聊，除非它明确 @ 了你。想让笨笨继续就明确 @笨笨，不 @ 就自然停。只发群聊正文，不要写“渡：”前缀；不要替辛玥决定；不要进入施工、调工具或汇报流程；如果结论已经差不多，就自然收尾。",
    "最近群聊：",
    ...lines,
  ].join("\n");
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

export function MainChatScreen({
  title,
  avatarLabel,
  windowId,
  displayWindowId,
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
  benbenAvatarImage,
  chatBackgroundImage,
  groupFreeChatEnabled = true,
  onBack,
  onOpenStickers,
  onOpenCall,
}: {
  title: string;
  avatarLabel: string;
  windowId: string;
  displayWindowId?: string;
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
  benbenAvatarImage: string;
  chatBackgroundImage: string;
  groupFreeChatEnabled?: boolean;
  onBack: () => void;
  onOpenStickers: () => void;
  onOpenCall: () => void;
}) {
  const toast = useToast();
  const modelKey = `miniapp.chat.${windowId}.model.v1`;
  const displayHistoryWindowId = String(displayWindowId || (!groupChatMode ? MAIN_SUMITALK_DISPLAY_WINDOW_ID : "")).trim();
  const historyWindowId = String(displayHistoryWindowId || windowId || "").trim();
  const remoteHistoryWindowId = displayHistoryWindowId;
  const [deviceId, setDeviceId] = useState("");
  const remoteHistoryReadyRef = useRef(false);
  const remoteHistoryWarningShownRef = useRef(false);
  const seedMessages: ChatDraftMessage[] = [
    {
      id: "seed-1",
      role: "assistant",
      content: groupChatMode ? `${title}开着。你直接说就好。` : "我在。你直接说就好。",
      createdAt: new Date().toISOString(),
    },
  ];
  const [messages, setMessages] = useState<ChatDraftMessage[]>(seedMessages);
  const messagesRef = useRef<ChatDraftMessage[]>(seedMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [groupDiscussionRunning, setGroupDiscussionRunning] = useState(false);
  const [groupDiscussionStatus, setGroupDiscussionStatus] = useState("");
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
  const benbenTaskFinalizedRef = useRef<Set<string>>(new Set());
  const sumitalkOperationRecoveringRef = useRef<Set<string>>(new Set());
  const groupDiscussionRunRef = useRef(0);
  const groupDiscussionSnapshotRef = useRef<GroupDiscussionSnapshot | null>(null);

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
          await migrateLocalChatHistoriesToDevice(did);
          if (migration?.from && migration.to === did) {
            await migrateLocalChatHistoryDevice(migration.from, migration.to);
            try {
              const migrated = await apiJson<{ ok?: boolean; panel_token?: string }>("/miniapp-api/sumitalk-history/migrate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_device_id: migration.to }),
              });
              const nextToken = String(migrated?.panel_token || "").trim();
              if (nextToken) setPanelToken(nextToken);
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
        if (!historyWindowId) return;
        const resolvedDeviceId = String(deviceId || await getOrCreatePanelDeviceId()).trim();
        if (!resolvedDeviceId) return;
        if (!deviceId && !cancelled) {
          setDeviceId(resolvedDeviceId);
        }
        await migrateLocalChatHistoriesToDevice(resolvedDeviceId);
        remoteHistoryReadyRef.current = false;
        remoteHistoryWarningShownRef.current = false;
        const localMessages = sanitizeHistoryMessages(await readLocalChatHistory(resolvedDeviceId, historyWindowId));
        const localRecoveryWindowIds = groupChatMode
          ? uniqueNonEmptyStrings([historyWindowId, displayHistoryWindowId, windowId])
          : uniqueNonEmptyStrings([historyWindowId, displayHistoryWindowId, windowId, MAIN_SUMITALK_DISPLAY_WINDOW_ID]);
        const localCandidateRows = await readLocalChatHistoryRows(localRecoveryWindowIds);
        const localCandidateMessages = localCandidateRows.reduce(
          (best, row) => {
            const rowMessages = sanitizeHistoryMessages((row?.messages || []) as ChatDraftMessage[]);
            return pickBetterHistory(rowMessages, best, []);
          },
          [] as ChatDraftMessage[],
        );
        const legacyLocalGroups = [];
        if (!groupChatMode && windowId && windowId !== historyWindowId) {
          legacyLocalGroups.push(sanitizeHistoryMessages(await readLocalChatHistory(resolvedDeviceId, windowId)));
        }
        if (!groupChatMode && historyWindowId !== MAIN_SUMITALK_DISPLAY_WINDOW_ID) {
          legacyLocalGroups.push(sanitizeHistoryMessages(await readLocalChatHistory(resolvedDeviceId, MAIN_SUMITALK_DISPLAY_WINDOW_ID)));
        }
        const legacyLocalMessages = legacyLocalGroups.reduce(
          (best, item) => pickBetterHistory(item, best, []),
          [] as ChatDraftMessage[],
        );
        const recoveredLocalMessages = pickBetterHistory(localCandidateMessages, localMessages, []);
        const fallbackLocalMessages = pickBetterHistory(recoveredLocalMessages, legacyLocalMessages, []);
        if (!cancelled && fallbackLocalMessages.length) {
          messagesRef.current = fallbackLocalMessages;
          setMessages(fallbackLocalMessages);
          await writeLocalChatHistory(resolvedDeviceId, historyWindowId, fallbackLocalMessages);
        }
        const j = await apiJson<{ ok?: boolean; messages?: ChatDraftMessage[] }>(sumitalkHistoryPath(remoteHistoryWindowId));
        if (cancelled) return;
        if (j?.ok) {
          remoteHistoryReadyRef.current = true;
        }
        const remoteMessages = sanitizeHistoryMessages(Array.isArray(j?.messages) ? j.messages : []);
        const next = pickBetterHistory(remoteMessages, fallbackLocalMessages, seedMessages);
        messagesRef.current = next;
        setMessages(next);
        if (next !== seedMessages && next.length) {
          await writeLocalChatHistory(resolvedDeviceId, historyWindowId, next);
          if (remoteHistoryReadyRef.current && next !== remoteMessages) {
            try {
              await apiJson("/miniapp-api/sumitalk-history", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(sumitalkHistoryPayload(next, remoteHistoryWindowId)),
              });
            } catch {}
          }
        }
        void recoverActiveSumiTalkOperations(resolvedDeviceId);
      } catch (e: any) {
        if (!cancelled) {
          toast(`聊天记录拉取失败：${e?.message || e}`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [deviceId, historyWindowId, remoteHistoryWindowId, windowId, groupChatMode]);

  async function saveDisplayHistory(
    nextMessages: ChatDraftMessage[],
    options: { syncRemote?: boolean; localDeviceId?: string; remoteTimeoutMs?: number } = {},
  ) {
    const sanitizedMessages = sanitizeHistoryMessages(nextMessages);
    const resolvedDeviceId = String(options.localDeviceId || deviceId || "").trim();
    const syncRemote = options.syncRemote !== false;
    if (resolvedDeviceId && historyWindowId) {
      await writeLocalChatHistory(resolvedDeviceId, historyWindowId, sanitizedMessages);
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
      const init = {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sumitalkHistoryPayload(sanitizedMessages, remoteHistoryWindowId)),
      };
      if (options.remoteTimeoutMs && options.remoteTimeoutMs > 0) {
        await apiJsonWithTimeout("/miniapp-api/sumitalk-history", options.remoteTimeoutMs, init);
      } else {
        await apiJson("/miniapp-api/sumitalk-history", init);
      }
    } catch {}
  }

  function saveDisplayHistoryInBackground(
    nextMessages: ChatDraftMessage[],
    options: { localDeviceId?: string } = {},
  ) {
    void saveDisplayHistory(nextMessages, {
      localDeviceId: options.localDeviceId,
      remoteTimeoutMs: 8000,
    }).catch(() => {});
  }

  async function persistSumiTalkOperationMessages(nextMessages: ChatDraftMessage[], localDeviceId: string) {
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    if (groupChatMode) {
      await saveDisplayHistory(nextMessages, { syncRemote: false, localDeviceId });
      saveDisplayHistoryInBackground(nextMessages, { localDeviceId });
    } else {
      await saveDisplayHistory(nextMessages, { localDeviceId });
    }
  }

  async function recoverSumiTalkOperation(operation: ChatOperation, localDeviceId: string) {
    const opId = String(operation?.id || "").trim();
    if (!opId || sumitalkOperationRecoveringRef.current.has(opId)) return;
    sumitalkOperationRecoveringRef.current.add(opId);
    try {
      let jobId = String(operation.jobId || "").trim();
      let completedData: any = null;
      const assistantId = String(operation.assistantMessageId || "").trim();
      if (!assistantId) throw new Error("缺少 pending 回复 ID");
      const createOrReuseJob = async () => {
        const retryPayload = operation.retryPayload && typeof operation.retryPayload === "object" ? operation.retryPayload : {};
        const path = String(retryPayload.path || "").trim();
        const body = retryPayload.body && typeof retryPayload.body === "object" ? retryPayload.body : null;
        if (!path || !body) throw new Error("缺少可恢复请求");
        const started = await createSumiTalkChatJob(path, body);
        if (started?.status === "error") {
          const upstreamError = started.response?.error || started.response?.message || "";
          throw new Error(String(started.error || upstreamError || "渡回复失败"));
        }
        jobId = String(started?.job_id || "").trim();
        if (jobId) {
          await attachChatJobToOperation(opId, jobId);
          const current = messagesRef.current.find((msg) => msg.id === assistantId);
          if (current) {
            const next = applyMessageById(messagesRef.current, assistantId, {
              ...current,
              role: "assistant",
              status: "pending",
              clientRequestId: operation.clientRequestId,
              operationId: opId,
              jobId,
            });
            await persistSumiTalkOperationMessages(next, localDeviceId);
          }
        }
        if (String(started?.status || "").trim() === "done") {
          completedData = started?.response || started;
        }
      };
      if (jobId) {
        try {
          completedData = await waitForSumiTalkChatJob(jobId);
        } catch (e: any) {
          const message = String(e?.message || e);
          if (!/不存在|过期|404/.test(message)) throw e;
          jobId = "";
        }
      }
      if (!completedData && !jobId) {
        await createOrReuseJob();
      }
      const data = completedData || (jobId ? await waitForSumiTalkChatJob(jobId) : null);
      if (!data) throw new Error("任务没有返回内容");
      if (data?.error) {
        const err = typeof data.error === "string" ? data.error : data.error?.message || JSON.stringify(data.error);
        throw new Error(err || "上游返回错误");
      }
      const reply = extractAssistantReplyText(data);
      if (!reply) throw new Error("上游没有返回内容");
      const existing = messagesRef.current.find((msg) => msg.id === assistantId);
      const assistantMessage: ChatDraftMessage = {
        id: assistantId,
        role: "assistant",
        content: reply,
        createdAt: existing?.createdAt || operation.createdAt || new Date().toISOString(),
        status: "sent",
        clientRequestId: operation.clientRequestId,
        operationId: opId,
        jobId: jobId || undefined,
        reasoning: extractAssistantReasoning(data) || undefined,
        tokenCount: extractTokenCount(data),
      };
      await completeChatOperation(opId, assistantMessage);
      const finalMessages = applyAssistantTerminalMessage(messagesRef.current, operation.clientRequestId, assistantMessage);
      await persistSumiTalkOperationMessages(finalMessages, localDeviceId);
    } catch (e: any) {
      const assistantId = String(operation.assistantMessageId || "").trim();
      const existing = messagesRef.current.find((msg) => msg.id === assistantId);
      const failedMessage: ChatDraftMessage = {
        id: assistantId || `assistant-failed-${Date.now()}`,
        role: "assistant",
        content: `（发送失败：${e?.message || e}）`,
        createdAt: existing?.createdAt || operation.createdAt || new Date().toISOString(),
        status: "failed",
        clientRequestId: operation.clientRequestId,
        operationId: opId,
        jobId: operation.jobId,
      };
      await failChatOperation(opId, String(e?.message || e), failedMessage);
      const failedMessages = applyAssistantTerminalMessage(messagesRef.current, operation.clientRequestId, failedMessage);
      await persistSumiTalkOperationMessages(failedMessages, localDeviceId);
    } finally {
      sumitalkOperationRecoveringRef.current.delete(opId);
    }
  }

  async function recoverActiveSumiTalkOperations(localDeviceId: string) {
    const did = String(localDeviceId || "").trim();
    if (!did || !historyWindowId) return;
    const operations = await listActiveChatOperations(did, historyWindowId);
    for (const operation of operations) {
      if (!operation.assistantMessageId || !operation.clientRequestId) continue;
      void recoverSumiTalkOperation(operation, did);
    }
  }

  async function retrySumiTalkOperation(operationId: string) {
    const opId = String(operationId || "").trim();
    const localDeviceId = String(deviceId || await getOrCreatePanelDeviceId()).trim();
    if (!opId || !localDeviceId) return;
    const operation = await getChatOperation(opId);
    if (!operation) {
      toast("这条失败消息没有找到可重试任务");
      return;
    }
    const assistantId = String(operation.assistantMessageId || "").trim();
    const current = messagesRef.current.find((msg) => msg.id === assistantId);
    if (current) {
      const pending = applyMessageById(messagesRef.current, assistantId, {
        ...current,
        role: "assistant",
        content: "",
        status: "pending",
        clientRequestId: operation.clientRequestId,
        operationId: opId,
        jobId: operation.jobId,
      });
      messagesRef.current = pending;
      setMessages(pending);
      await saveDisplayHistory(pending, { syncRemote: false, localDeviceId });
    }
    void recoverSumiTalkOperation(operation, localDeviceId);
  }

  async function applyBenbenTaskUpdate(
    task: CodexGroupTaskRealtimeTask,
    options: { messageId?: string; localDeviceId?: string } = {},
  ): Promise<boolean> {
    const taskId = String(task?.id || "").trim();
    const statusValue = String(task?.status || "").trim();
    if (!taskId || !["queued", "running", "done", "error", "cancelled"].includes(statusValue)) return false;
    if (["done", "error", "cancelled"].includes(statusValue) && benbenTaskFinalizedRef.current.has(taskId)) return true;

    const currentMessages = messagesRef.current;
    const clientRequestId = String(task?.client_request_id || "").trim();
    const targetMessageId = String(options.messageId || "").trim()
      || String(currentMessages.find((msg) => msg.role === "benben" && String(msg.jobId || "").trim() === taskId)?.id || "").trim()
      || String(currentMessages.find((msg) => msg.role === "benben" && clientRequestId && String(msg.clientRequestId || "").trim() === clientRequestId)?.id || "").trim();
    if (!targetMessageId) return false;

    const currentMessage = currentMessages.find((msg) => msg.id === targetMessageId);
    const createdAt = currentMessage?.createdAt || new Date().toISOString();
    if (statusValue === "queued" || statusValue === "running") {
      const pendingMessage: ChatDraftMessage = {
        id: targetMessageId,
        role: "benben",
        content: codexGroupTaskStatusText(task),
        createdAt,
        status: "pending",
        jobId: taskId,
        clientRequestId: currentMessage?.clientRequestId || clientRequestId || undefined,
      };
      const nextMessages = applyMessageById(currentMessages, targetMessageId, pendingMessage);
      messagesRef.current = nextMessages;
      setMessages(nextMessages);
      await saveDisplayHistory(nextMessages, { syncRemote: false, localDeviceId: options.localDeviceId || deviceId });
      return true;
    }
    const terminalMessage: ChatDraftMessage = statusValue === "done"
      ? {
          id: targetMessageId,
          role: "benben",
          content: String(task.response || "").trim() || "（笨笨没有返回内容）",
          createdAt,
          status: "sent",
          jobId: taskId,
        }
      : statusValue === "cancelled"
      ? {
          id: targetMessageId,
          role: "benben",
          content: codexGroupTaskStatusText(task),
          createdAt,
          status: "failed",
          jobId: taskId,
        }
      : {
          id: targetMessageId,
          role: "benben",
          content: `（笨笨入群失败：${task.error || "任务已取消"}）`,
          createdAt,
          status: "failed",
          jobId: taskId,
        };
    const nextMessages = applyMessageById(currentMessages, targetMessageId, terminalMessage);
    benbenTaskFinalizedRef.current.add(taskId);
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    await saveDisplayHistory(nextMessages, { localDeviceId: options.localDeviceId || deviceId });
    return true;
  }

  useCodexGroupTaskRealtime({
    enabled: groupChatMode,
    deviceId,
    onTask: (task) => {
      void applyBenbenTaskUpdate(task, { localDeviceId: deviceId });
    },
  });

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
    duReply?: string;
    replyTarget: string;
    clientRequestId: string;
    mode?: "daily_chat" | "coding_task";
    targetMentions?: string[];
    codingThreadKey?: string;
    placeholderId?: string;
    placeholderCreatedAt?: string;
  }): Promise<ChatDraftMessage[]> {
    const createdAtMs = Date.now();
    const benbenId = params.placeholderId || `benben-${createdAtMs}`;
    const benbenCreatedAt = params.placeholderCreatedAt || new Date(createdAtMs).toISOString();
    const mode = params.mode || "daily_chat";
    const pendingMsg: ChatDraftMessage = {
      id: benbenId,
      role: "benben",
      content: codexGroupTaskStatusText({ mode }),
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
    let taskId = "";
    try {
      let created: CodexGroupChatTaskResponse | null = null;
      let lastCreateError: any = null;
      const createBody = {
        mode,
        window_id: windowId,
        reply_target: params.replyTarget,
        user_message: params.userContent,
        du_reply: params.duReply || "",
        recent_messages: buildCodexGroupRecentMessages(params.baseMessages),
        client_request_id: `${params.clientRequestId}-benben`,
        target_mentions: params.targetMentions || [],
        coding_thread_key: params.codingThreadKey || "",
      };
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          created = await apiJsonWithTimeout<CodexGroupChatTaskResponse>(
            "/miniapp-api/codex-group-chat-tasks",
            attempt === 0 ? CODEX_GROUP_CHAT_CREATE_TIMEOUT_MS : CODEX_GROUP_CHAT_CREATE_RETRY_TIMEOUT_MS,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(createBody),
            },
          );
          break;
        } catch (e: any) {
          lastCreateError = e;
          if (!isAbortLikeError(e) || attempt >= 1) throw e;
          const retryMessages = applyMessageById(messagesRef.current, benbenId, {
            ...pendingMsg,
            content: "笨笨入群有点慢，正在重试...",
            status: "pending",
          });
          messagesRef.current = retryMessages;
          setMessages(retryMessages);
          await saveDisplayHistory(retryMessages, { syncRemote: false, localDeviceId: params.replyTarget });
          await waitMs(600);
        }
      }
      if (!created) throw lastCreateError || new Error("笨笨任务创建失败");
      taskId = String(created.task?.id || "").trim();
      if (!taskId) throw new Error(created.error || "笨笨任务没有返回 ID");
      const queuedMessages = applyMessageById(messagesRef.current, benbenId, {
        ...pendingMsg,
        content: codexGroupTaskStatusText(created.task || { mode, status: "queued" }),
        status: "pending",
        jobId: taskId,
      });
      messagesRef.current = queuedMessages;
      setMessages(queuedMessages);
      await saveDisplayHistory(queuedMessages, { syncRemote: false, localDeviceId: params.replyTarget });
      saveDisplayHistoryInBackground(queuedMessages, { localDeviceId: params.replyTarget });
      return queuedMessages;
    } catch (e: any) {
      if (taskId && benbenTaskFinalizedRef.current.has(taskId)) {
        return messagesRef.current;
      }
      const failedMessages = applyMessageById(messagesRef.current, benbenId, {
        ...pendingMsg,
        content: `（笨笨入群失败：${e?.message || e}）`,
        status: "failed",
      });
      messagesRef.current = failedMessages;
      setMessages(failedMessages);
      await saveDisplayHistory(failedMessages, { syncRemote: false, localDeviceId: params.replyTarget });
      saveDisplayHistoryInBackground(failedMessages, { localDeviceId: params.replyTarget });
      toast(`笨笨入群失败：${e?.message || e}`);
      return failedMessages;
    }
  }

  async function cancelPendingBenbenGroupTasks(cancelContent: string, localDeviceId: string) {
    const pendingTasks = messagesRef.current
      .filter((msg) => msg.role === "benben" && msg.status === "pending" && String(msg.jobId || "").trim())
      .map((msg) => ({
        messageId: msg.id,
        taskId: String(msg.jobId || "").trim(),
        createdAt: msg.createdAt,
        clientRequestId: msg.clientRequestId,
      }));
    if (!pendingTasks.length) {
      const now = Date.now();
      const idleMessage: ChatDraftMessage = {
        id: `benben-cancel-idle-${now}`,
        role: "benben",
        content: "没有正在施工或等待的笨笨任务。",
        createdAt: new Date(now).toISOString(),
        status: "sent",
      };
      const idleMessages = [...messagesRef.current, idleMessage];
      messagesRef.current = idleMessages;
      setMessages(idleMessages);
      await saveDisplayHistory(idleMessages, { syncRemote: false, localDeviceId });
      saveDisplayHistoryInBackground(idleMessages, { localDeviceId });
      return;
    }

    const markedMessages = pendingTasks.reduce((list, item) => (
      applyMessageById(list, item.messageId, {
        id: item.messageId,
        role: "benben",
        content: "笨笨收到取消指令，正在停一下...",
        createdAt: item.createdAt,
        status: "pending",
        jobId: item.taskId,
        clientRequestId: item.clientRequestId,
      })
    ), messagesRef.current);
    messagesRef.current = markedMessages;
    setMessages(markedMessages);
    await saveDisplayHistory(markedMessages, { syncRemote: false, localDeviceId });

    for (const item of pendingTasks) {
      try {
        const cancelled = await apiJsonWithTimeout<CodexGroupChatTaskResponse>(
          `/miniapp-api/codex-group-chat-tasks/${encodeURIComponent(item.taskId)}/cancel`,
          15000,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason: cancelContent || "user_cancelled" }),
          },
        );
        if (!cancelled?.task) throw new Error(cancelled?.error || "取消失败");
        await applyBenbenTaskUpdate(cancelled.task, { messageId: item.messageId, localDeviceId });
      } catch (e: any) {
        const failedMessages = applyMessageById(messagesRef.current, item.messageId, {
          id: item.messageId,
          role: "benben",
          content: `（取消笨笨任务失败：${e?.message || e}）`,
          createdAt: item.createdAt,
          status: "failed",
          jobId: item.taskId,
          clientRequestId: item.clientRequestId,
        });
        messagesRef.current = failedMessages;
        setMessages(failedMessages);
        await saveDisplayHistory(failedMessages, { syncRemote: false, localDeviceId });
      }
    }
    saveDisplayHistoryInBackground(messagesRef.current, { localDeviceId });
  }

  async function waitForBenbenTaskId(messageId: string, runId: number): Promise<string> {
    for (let i = 0; i < 20; i += 1) {
      if (groupDiscussionRunRef.current !== runId) return "";
      const taskId = String(messagesRef.current.find((msg) => msg.id === messageId)?.jobId || "").trim();
      if (taskId) return taskId;
      await waitMs(250);
    }
    return "";
  }

  async function requestDuGroupDiscussionReply(params: {
    runId: number;
    topic: string;
    replyTarget: string;
    turnIndex: number;
    maxTurns: number;
  }): Promise<string> {
    if (groupDiscussionRunRef.current !== params.runId) return "";
    if (!activeModel) throw new Error("当前还没拿到可用模型");
    const createdAtMs = Date.now();
    const clientRequestId = `group-discussion-du-${createdAtMs}-${Math.random().toString(36).slice(2, 10)}`;
    const assistantId = `assistant-discussion-${createdAtMs}`;
    const assistantCreatedAt = new Date(createdAtMs).toISOString();
    const placeholder: ChatDraftMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      createdAt: assistantCreatedAt,
      status: "pending",
      clientRequestId,
    };
    const pendingMessages = [...messagesRef.current, placeholder];
    messagesRef.current = pendingMessages;
    setMessages(pendingMessages);
    await saveDisplayHistory(pendingMessages, { syncRemote: false, localDeviceId: params.replyTarget });
    try {
      const started = await createSumiTalkChatJob("/miniapp-api/sumitalk-chat-jobs", {
        model: activeModel,
        messages: [{
          role: "user",
          content: buildGroupDiscussionUserContent(
            messagesRef.current,
            params.topic,
            params.turnIndex,
            params.maxTurns,
          ),
        }],
        stream: false,
        window_id: windowId,
        reply_target: params.replyTarget,
        client_request_id: clientRequestId,
      });
      if (started?.status === "error") {
        const upstreamError = started.response?.error || started.response?.message || "";
        throw new Error(String(started.error || upstreamError || "渡回复失败"));
      }
      const jobId = String(started?.job_id || "").trim();
      const startedStatus = String(started?.status || "").trim();
      const data = startedStatus === "done"
        ? started?.response || started
        : jobId
        ? await waitForSumiTalkChatJob(jobId)
        : started?.response || started;
      if (data?.error) {
        const err = typeof data.error === "string" ? data.error : data.error?.message || JSON.stringify(data.error);
        throw new Error(err || "上游返回错误");
      }
      const reply = extractAssistantReplyText(data);
      if (!reply) throw new Error("上游没有返回内容");
      const finalMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, {
        id: assistantId,
        role: "assistant",
        content: reply,
        createdAt: assistantCreatedAt,
        status: "sent",
        clientRequestId,
        jobId: jobId || undefined,
        reasoning: extractAssistantReasoning(data) || undefined,
        tokenCount: extractTokenCount(data),
      });
      messagesRef.current = finalMessages;
      setMessages(finalMessages);
      await saveDisplayHistory(finalMessages, { syncRemote: false, localDeviceId: params.replyTarget });
      saveDisplayHistoryInBackground(finalMessages, { localDeviceId: params.replyTarget });
      return reply;
    } catch (e: any) {
      const failedMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, {
        id: assistantId,
        role: "assistant",
        content: `（渡接力失败：${e?.message || e}）`,
        createdAt: assistantCreatedAt,
        status: "failed",
        clientRequestId,
      });
      messagesRef.current = failedMessages;
      setMessages(failedMessages);
      await saveDisplayHistory(failedMessages, { syncRemote: false, localDeviceId: params.replyTarget });
      throw e;
    }
  }

  async function requestBenbenGroupDiscussionReply(params: {
    runId: number;
    topic: string;
    replyTarget: string;
    turnIndex: number;
    duReply?: string;
  }): Promise<string> {
    if (groupDiscussionRunRef.current !== params.runId) return "";
    const createdAtMs = Date.now();
    const messageId = `benben-discussion-${createdAtMs}`;
    const clientRequestId = `group-discussion-benben-${createdAtMs}-${Math.random().toString(36).slice(2, 10)}`;
    await requestBenbenGroupReply({
      baseMessages: messagesRef.current,
      userContent: params.topic,
      duReply: params.duReply || "",
      replyTarget: params.replyTarget,
      clientRequestId,
      mode: "daily_chat",
      targetMentions: ["benben"],
      placeholderId: messageId,
      placeholderCreatedAt: new Date(createdAtMs).toISOString(),
    });
    if (groupDiscussionRunRef.current !== params.runId) return "";
    const taskId = await waitForBenbenTaskId(messageId, params.runId);
    if (!taskId) return "";
    const task = await waitForCodexGroupChatTask(taskId);
    if (groupDiscussionRunRef.current !== params.runId) return String(task.response || "").trim();
    await applyBenbenTaskUpdate(task, { messageId, localDeviceId: params.replyTarget });
    return String(task.response || "").trim();
  }

  function rememberGroupDiscussionSnapshot(snapshot: Omit<GroupDiscussionSnapshot, "updatedAt">) {
    groupDiscussionSnapshotRef.current = {
      ...snapshot,
      updatedAt: Date.now(),
    };
  }

  async function runGroupDiscussionFollowups(params: {
    runId: number;
    topic: string;
    replyTarget: string;
    lastSpeaker: GroupDiscussionSpeaker;
    lastContent: string;
    maxFollowups: number;
    freeRoute?: boolean;
  }) {
    const maxFollowups = Math.max(1, Math.min(GROUP_DISCUSSION_MAX_FOLLOWUPS, params.maxFollowups || 1));
    setGroupDiscussionRunning(true);
    try {
      let lastSpeaker = params.lastSpeaker;
      let lastContent = String(params.lastContent || "").trim();
      for (let turnIndex = 1; turnIndex <= maxFollowups; turnIndex += 1) {
        if (groupDiscussionRunRef.current !== params.runId || !lastContent || groupDiscussionShouldStop(lastContent)) break;
        const nextSpeaker = params.freeRoute
          ? resolveNextFreeDiscussionSpeaker(lastSpeaker, lastContent)
          : resolveNextGroupDiscussionSpeaker(lastSpeaker, lastContent);
        if (!nextSpeaker) break;
        setGroupDiscussionStatus(`群聊接力中 ${turnIndex}/${maxFollowups}，轮到${nextSpeaker === "du" ? "渡" : "笨笨"}`);
        const reply = nextSpeaker === "du"
          ? await requestDuGroupDiscussionReply({
              runId: params.runId,
              topic: params.topic,
              replyTarget: params.replyTarget,
              turnIndex,
              maxTurns: maxFollowups,
            })
          : await requestBenbenGroupDiscussionReply({
              runId: params.runId,
              topic: params.topic,
              replyTarget: params.replyTarget,
              turnIndex,
              duReply: lastSpeaker === "du" ? lastContent : "",
            });
        if (groupDiscussionRunRef.current !== params.runId || !reply.trim()) break;
        lastSpeaker = nextSpeaker;
        lastContent = reply.trim();
        rememberGroupDiscussionSnapshot({
          topic: params.topic,
          replyTarget: params.replyTarget,
          lastSpeaker,
          lastContent,
          freeRoute: Boolean(params.freeRoute),
        });
      }
    } catch (e: any) {
      if (groupDiscussionRunRef.current === params.runId) toast(`自由讨论中断：${e?.message || e}`);
    } finally {
      if (groupDiscussionRunRef.current === params.runId) {
        setGroupDiscussionRunning(false);
        setGroupDiscussionStatus("");
      }
    }
  }

  async function runGroupFreeDiscussion(params: {
    runId: number;
    topic: string;
    replyTarget: string;
    initialDuReply: string;
  }) {
    setGroupDiscussionRunning(true);
    setGroupDiscussionStatus("群聊接力中，等笨笨接渡这句");
    try {
      if (groupDiscussionRunRef.current !== params.runId) return;
      let lastSpeaker: GroupDiscussionSpeaker = "du";
      let lastContent = String(params.initialDuReply || "").trim();
      if (!lastContent) return;
      rememberGroupDiscussionSnapshot({
        topic: params.topic,
        replyTarget: params.replyTarget,
        lastSpeaker,
        lastContent,
        freeRoute: true,
      });
      await runGroupDiscussionFollowups({
        runId: params.runId,
        topic: params.topic,
        replyTarget: params.replyTarget,
        lastSpeaker,
        lastContent,
        maxFollowups: GROUP_DISCUSSION_MAX_FOLLOWUPS,
        freeRoute: true,
      });
    } catch (e: any) {
      if (groupDiscussionRunRef.current === params.runId) toast(`自由讨论中断：${e?.message || e}`);
    } finally {
      if (groupDiscussionRunRef.current === params.runId) {
        setGroupDiscussionRunning(false);
        setGroupDiscussionStatus("");
      }
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
          const applied = await applyBenbenTaskUpdate(task, { messageId: item.messageId, localDeviceId: deviceId });
          if (!applied) throw new Error("笨笨没有返回内容");
        } catch (e: any) {
          if (benbenTaskFinalizedRef.current.has(item.taskId)) return;
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
          await saveDisplayHistory(failedMessages, { syncRemote: false, localDeviceId: deviceId });
          saveDisplayHistoryInBackground(failedMessages, { localDeviceId: deviceId });
        } finally {
          benbenTaskRecoveringRef.current.delete(item.taskId);
        }
      })();
    }
  }, [messages, groupChatMode, deviceId]);

  async function appendGroupUserMessage(displayContent: string, localDeviceId: string): Promise<ChatDraftMessage[]> {
    const now = Date.now();
    const userMsg: ChatDraftMessage = {
      id: `user-${now}`,
      role: "user",
      content: displayContent,
      createdAt: new Date(now).toISOString(),
      status: "sent",
    };
    const nextMessages = [...messagesRef.current, userMsg];
    messagesRef.current = nextMessages;
    setInput("");
    setPlusOpen(false);
    setMessages(nextMessages);
    await saveDisplayHistory(nextMessages, { syncRemote: false, localDeviceId });
    return nextMessages;
  }

  async function appendBenbenGroupNotice(content: string, localDeviceId: string): Promise<void> {
    const now = Date.now();
    const notice: ChatDraftMessage = {
      id: `benben-notice-${now}`,
      role: "benben",
      content,
      createdAt: new Date(now).toISOString(),
      status: "sent",
    };
    const nextMessages = [...messagesRef.current, notice];
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    await saveDisplayHistory(nextMessages, { syncRemote: false, localDeviceId });
    saveDisplayHistoryInBackground(nextMessages, { localDeviceId });
  }

  async function sendChatContent(rawContent: string, options: { displayContent?: string } = {}) {
    const content = String(rawContent || "").trim();
    const canSendWhileBusy = groupChatMode && (
      isBenbenCancelCommand(content)
      || (groupDiscussionRunning && isGroupDiscussionStopCommand(content))
      || isGroupDiscussionContinueCommand(content)
    );
    if (!content || (sending && !canSendWhileBusy)) return;
    const displayContent = String(options.displayContent || content).trim() || content;
    if (!windowId) {
      toast("当前还没拿到聊天窗口 ID，不能接入共享上下文");
      return;
    }
    const discussionRunId = groupChatMode ? groupDiscussionRunRef.current + 1 : groupDiscussionRunRef.current;
    if (groupChatMode) {
      groupDiscussionRunRef.current = discussionRunId;
      setGroupDiscussionRunning(false);
      setGroupDiscussionStatus("");
    }
    const resolvedDeviceId = String(deviceId || await getOrCreatePanelDeviceId()).trim();
    if (resolvedDeviceId && resolvedDeviceId !== deviceId) {
      setDeviceId((prev) => (prev === resolvedDeviceId ? prev : resolvedDeviceId));
    }
    if (groupChatMode && (isBenbenCancelCommand(content) || (groupDiscussionRunning && isGroupDiscussionStopCommand(content)))) {
      setSending(true);
      await appendGroupUserMessage(displayContent, resolvedDeviceId);
      try {
        const hasPendingBenbenTask = messagesRef.current.some(
          (msg) => msg.role === "benben" && msg.status === "pending" && String(msg.jobId || "").trim(),
        );
        if (isBenbenCancelCommand(content) || hasPendingBenbenTask) {
          await cancelPendingBenbenGroupTasks(content, resolvedDeviceId);
        } else {
          await appendBenbenGroupNotice("群聊接力已停下。", resolvedDeviceId);
        }
        setGroupDiscussionStatus("");
      } catch (e: any) {
        toast(`取消失败：${e?.message || e}`);
      } finally {
        setSending(false);
      }
      return;
    }
    if (groupChatMode && isGroupDiscussionContinueCommand(content)) {
      await appendGroupUserMessage(displayContent, resolvedDeviceId);
      const snapshot = groupDiscussionSnapshotRef.current;
      if (!snapshot?.lastContent) {
        toast("还没有可继续的群聊讨论");
        return;
      }
      void runGroupDiscussionFollowups({
        runId: discussionRunId,
        topic: snapshot.topic || content,
        replyTarget: resolvedDeviceId || snapshot.replyTarget,
        lastSpeaker: snapshot.lastSpeaker,
        lastContent: snapshot.lastContent,
        maxFollowups: parseGroupDiscussionContinueTurns(content),
        freeRoute: snapshot.freeRoute || groupFreeChatEnabled,
      });
      return;
    }
    let groupTargets = groupChatMode
      ? resolveGroupReplyTargets(content)
      : { du: true, benben: false, mentions: [], benbenMode: "daily_chat" as const, codingThreadKey: "", freeDiscussion: false };
    if (groupChatMode && groupFreeChatEnabled) {
      if (!groupTargets.mentions.length) {
        groupTargets = {
          du: true,
          benben: true,
          mentions: ["du", "benben"],
          benbenMode: "daily_chat",
          codingThreadKey: "",
          freeDiscussion: true,
        };
      } else if (groupTargets.du && groupTargets.benben && groupTargets.benbenMode === "daily_chat") {
        groupTargets = { ...groupTargets, freeDiscussion: true };
      }
    }
    const shouldRequestDu = !groupChatMode || groupTargets.du;
    const isGroupFreeDiscussion = Boolean(
      groupChatMode
      && groupFreeChatEnabled
      && groupTargets.freeDiscussion
      && groupTargets.du
      && groupTargets.benben
      && groupTargets.benbenMode === "daily_chat",
    );
    const shouldRequestBenben = groupChatMode && groupTargets.benben && !isGroupFreeDiscussion;
    if (shouldRequestDu && !activeModel) {
      toast("当前还没拿到可用模型，稍后再试");
      return;
    }
    const baseTimestamp = Date.now();
    const clientRequestId = `sumitalk-${baseTimestamp}-${Math.random().toString(36).slice(2, 10)}`;
    const operationId = shouldRequestDu ? `op-${clientRequestId}` : "";
    const userMsg: ChatDraftMessage = {
      id: `user-${baseTimestamp}`,
      role: "user",
      content: displayContent,
      createdAt: new Date(baseTimestamp).toISOString(),
      status: "sent",
      clientRequestId,
      operationId: operationId || undefined,
    };
    const assistantId = shouldRequestDu ? `assistant-${baseTimestamp + 1}` : "";
    const assistantCreatedAt = shouldRequestDu ? new Date(baseTimestamp + 1).toISOString() : "";
    const assistantPlaceholder: ChatDraftMessage | null = shouldRequestDu
      ? {
          id: assistantId,
          role: "assistant" as const,
          content: "",
          createdAt: assistantCreatedAt,
          status: "pending" as const,
          clientRequestId,
          operationId,
        }
      : null;
    const benbenPlaceholderId = shouldRequestBenben ? `benben-${baseTimestamp + 2}` : "";
    const benbenPlaceholderCreatedAt = shouldRequestBenben ? new Date(baseTimestamp + 2).toISOString() : "";
    const benbenPlaceholder: ChatDraftMessage | null = shouldRequestBenben
      ? {
          id: benbenPlaceholderId,
          role: "benben",
          content: codexGroupTaskStatusText({ mode: groupTargets.benbenMode }),
          createdAt: benbenPlaceholderCreatedAt,
          status: "pending",
          clientRequestId: `${clientRequestId}-benben`,
        }
      : null;
    const nextMessages = [...messagesRef.current, userMsg];
    const requestUserContent = shouldRequestDu
      ? isGroupFreeDiscussion
        ? buildGroupFreeDiscussionOpeningContent(nextMessages, content)
        : groupChatMode
        ? buildGroupTurnUserContent(nextMessages, content)
        : content
      : "";
    const musicBgmContext = shouldRequestDu && !groupChatMode ? readMusicBgmContext() : null;
    const requestPath = shouldRequestDu ? (groupChatMode ? "/miniapp-api/sumitalk-chat-jobs" : "/miniapp-api/sumitalk-chat") : "";
    const requestBody = shouldRequestDu
      ? {
          model: activeModel,
          messages: [{ role: "user", content: requestUserContent }],
          stream: false,
          window_id: windowId,
          ...(musicBgmContext ? { music_bgm_context: musicBgmContext } : {}),
          reply_target: resolvedDeviceId,
          client_request_id: clientRequestId,
        }
      : null;
    const draftMessages = [
      ...nextMessages,
      ...(assistantPlaceholder ? [assistantPlaceholder] : []),
      ...(benbenPlaceholder ? [benbenPlaceholder] : []),
    ];
    const replyTarget = resolvedDeviceId;
    setInput("");
    setPlusOpen(false);
    setSending(true);
    setMessages(draftMessages);
    messagesRef.current = draftMessages;
    if (shouldRequestDu && assistantPlaceholder && requestBody) {
      await createChatDraftTurn({
        deviceId: resolvedDeviceId,
        windowId: historyWindowId,
        userMessage: userMsg,
        assistantMessage: assistantPlaceholder,
        operation: {
          id: operationId,
          clientRequestId,
          deviceId: resolvedDeviceId,
          windowId: historyWindowId,
          displayWindowId: remoteHistoryWindowId,
          replyTarget,
          model: activeModel,
          retryPayload: {
            path: requestPath,
            body: requestBody,
          },
          retryPayloadSize: JSON.stringify(requestBody).length,
          userMessageId: userMsg.id,
          assistantMessageId: assistantId,
          status: "draft",
          createdAt: new Date(baseTimestamp).toISOString(),
          updatedAt: new Date(baseTimestamp).toISOString(),
          retryCount: 0,
          schemaVersion: 1,
        },
      });
    } else {
      await saveDisplayHistory(draftMessages, { syncRemote: false, localDeviceId: resolvedDeviceId });
    }
    let benbenCreatePromise: Promise<ChatDraftMessage[]> | null = null;
    let initialDuReply = "";
    try {
      if (shouldRequestBenben) {
        benbenCreatePromise = requestBenbenGroupReply({
          baseMessages: messagesRef.current,
          userContent: content,
          duReply: "",
          replyTarget,
          clientRequestId,
          mode: groupTargets.benbenMode,
          targetMentions: groupTargets.mentions,
          codingThreadKey: groupTargets.codingThreadKey,
          placeholderId: benbenPlaceholderId,
          placeholderCreatedAt: benbenPlaceholderCreatedAt,
        });
      }

      if (shouldRequestDu) {
        if (!requestBody) throw new Error("缺少发送请求");
        const started = await createSumiTalkChatJob(requestPath, requestBody);
        if (started?.status === "error") {
          const upstreamError = started.response?.error || started.response?.message || "";
          throw new Error(String(started.error || upstreamError || "渡回复失败"));
        }
        const jobId = String(started?.job_id || "").trim();
        if (jobId && operationId) {
          await attachChatJobToOperation(operationId, jobId);
          const pendingWithJob = applyMessageById(messagesRef.current, assistantId, {
            id: assistantId,
            role: "assistant",
            content: "",
            createdAt: assistantCreatedAt,
            status: "pending",
            clientRequestId,
            operationId,
            jobId,
          });
          messagesRef.current = pendingWithJob;
          setMessages(pendingWithJob);
          await saveDisplayHistory(pendingWithJob, { syncRemote: false, localDeviceId: replyTarget });
        }
        const startedStatus = String(started?.status || "").trim();
        const data = startedStatus === "done"
          ? started?.response || started
          : jobId
          ? await waitForSumiTalkChatJob(jobId)
          : started?.response || started;
        if (data?.error) {
          const err = typeof data.error === "string" ? data.error : data.error?.message || JSON.stringify(data.error);
          throw new Error(err || "上游返回错误");
        }
        const reply = extractAssistantReplyText(data);
        if (!reply) throw new Error("上游没有返回内容");
        initialDuReply = reply;
        const reasoning = extractAssistantReasoning(data);
        const tokenCount = extractTokenCount(data);
        const finalMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, {
          id: assistantId,
          role: "assistant" as const,
          content: reply,
          createdAt: assistantCreatedAt,
          status: "sent" as const,
          clientRequestId,
          operationId,
          jobId: jobId || undefined,
          reasoning: reasoning || undefined,
          tokenCount,
        });
        await completeChatOperation(operationId, {
          id: assistantId,
          role: "assistant",
          content: reply,
          createdAt: assistantCreatedAt,
          status: "sent",
          clientRequestId,
          operationId,
          jobId: jobId || undefined,
          reasoning: reasoning || undefined,
          tokenCount,
        });
        messagesRef.current = finalMessages;
        setMessages(finalMessages);
        if (groupChatMode) {
          await saveDisplayHistory(finalMessages, { syncRemote: false, localDeviceId: replyTarget });
        } else {
          await saveDisplayHistory(finalMessages);
        }
      }
      if (benbenCreatePromise) {
        await benbenCreatePromise;
      }
      if (
        isGroupFreeDiscussion
        && shouldRequestDu
        && initialDuReply.trim()
      ) {
        void runGroupFreeDiscussion({
          runId: discussionRunId,
          topic: content,
          replyTarget,
          initialDuReply,
        });
      }
    } catch (e: any) {
      if (benbenCreatePromise) {
        await benbenCreatePromise.catch(() => messagesRef.current);
      }
      const failedMessages = shouldRequestDu
        ? applyAssistantTerminalMessage(messagesRef.current, clientRequestId, {
            id: assistantId,
            role: "assistant" as const,
            content: `（发送失败：${e?.message || e}）`,
            createdAt: assistantCreatedAt,
            status: "failed" as const,
            clientRequestId,
            operationId,
          })
        : messagesRef.current;
      if (shouldRequestDu && operationId) {
        await failChatOperation(operationId, String(e?.message || e), {
          id: assistantId,
          role: "assistant",
          content: `（发送失败：${e?.message || e}）`,
          createdAt: assistantCreatedAt,
          status: "failed",
          clientRequestId,
          operationId,
        });
      }
      messagesRef.current = failedMessages;
      setMessages(failedMessages);
      await saveDisplayHistory(failedMessages, { syncRemote: false, localDeviceId: replyTarget });
      if (groupChatMode) {
        saveDisplayHistoryInBackground(failedMessages, { localDeviceId: replyTarget });
      }
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
  const assistantTyping = (sending || groupDiscussionRunning) && messages.some(
    (msg) => (msg.role === "assistant" || msg.role === "benben") && String(msg.status || "").trim().toLowerCase() === "pending",
  );
  const trimmedInput = input.trim();
  const canSubmitWhileBusy = groupChatMode && (
    isBenbenCancelCommand(trimmedInput)
    || (groupDiscussionRunning && isGroupDiscussionStopCommand(trimmedInput))
    || isGroupDiscussionContinueCommand(trimmedInput)
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
  const hasCustomChatBackground = Boolean(String(chatBackgroundImage || "").trim());
  const chatBackgroundAlpha = Math.max(0.2, Math.min(1, chatBackgroundOpacity / 100));
  const chatBackgroundOverlayAlpha = 1 - chatBackgroundAlpha;
  const chatChromeClass = hasCustomChatBackground
    ? "border-transparent bg-transparent"
    : "border-gray-100/50 bg-white/80 backdrop-blur-md";
  const chatHeaderButtonClass = hasCustomChatBackground
    ? "flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/25 bg-white/25 text-gray-800/85 shadow-[0_8px_24px_rgba(15,23,42,0.12)] backdrop-blur-2xl transition-colors active:bg-white/40"
    : "rounded-full p-2 text-gray-500 transition-colors active:bg-gray-100";
  const chatFooterClass = hasCustomChatBackground
    ? "border-white/20 bg-white/25 shadow-[0_-10px_30px_rgba(15,23,42,0.10)] backdrop-blur-xl"
    : "border-gray-100 bg-white";
  const chatInputShellClass = hasCustomChatBackground
    ? "border border-white/25 bg-white/45 shadow-[0_8px_24px_rgba(15,23,42,0.08)] backdrop-blur-xl"
    : "bg-[#F4F5F7]";
  const chatSearchShellClass = hasCustomChatBackground
    ? "border border-white/25 bg-white/45 shadow-[0_8px_24px_rgba(15,23,42,0.08)] backdrop-blur-xl"
    : "bg-[#F4F5F7]";
  const chatHeaderWrapClass = hasCustomChatBackground
    ? "absolute top-0 z-20 w-full border-b px-3 pb-2 pt-[calc(env(safe-area-inset-top,0px)+10px)]"
    : "absolute top-0 z-20 w-full border-b px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+20px)]";
  const messagesTopPaddingClass = searchOpen
    ? hasCustomChatBackground ? "pt-[140px]" : "pt-[156px]"
    : hasCustomChatBackground ? "pt-[88px]" : "pt-[104px]";

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
      className="fixed inset-0 z-30 flex h-[100lvh] min-h-screen w-full max-w-full flex-col overflow-hidden overscroll-none bg-[#F8F9FA]"
      style={{
        fontFamily: chatFontFamily,
      }}
    >
      {hasCustomChatBackground ? (
        <>
          <div
            className="pointer-events-none fixed inset-0 z-0 bg-cover bg-center"
            style={{ backgroundImage: `url(${chatBackgroundImage})` }}
          />
          <div
            className="pointer-events-none fixed inset-0 z-0"
            style={{ backgroundColor: `rgba(248,249,250,${chatBackgroundOverlayAlpha})` }}
          />
        </>
      ) : null}
      <div className={`${chatHeaderWrapClass} ${chatChromeClass}`}>
        {hasCustomChatBackground ? (
          <div className="flex items-start justify-between gap-3">
            <button className={chatHeaderButtonClass} onClick={onBack} aria-label="返回">
              <ChevronLeftIcon />
            </button>
            <div className="min-w-0 flex-1 px-1 pt-0.5 text-center drop-shadow-[0_1px_8px_rgba(255,255,255,0.55)]">
              <div className="truncate font-semibold text-gray-900" style={{ fontSize: `${chatTitleFontSize}px` }}>{title}</div>
              <div className="mt-0.5 flex justify-center">
                <ChatHeaderStatus sending={assistantTyping} />
              </div>
              {groupDiscussionStatus ? (
                <div className="mt-0.5 truncate text-[11px] font-medium text-amber-700">{groupDiscussionStatus}</div>
              ) : null}
            </div>
            <button
              className={chatHeaderButtonClass}
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
        ) : (
          <div className="flex items-center">
            <button className={chatHeaderButtonClass} onClick={onBack} aria-label="返回">
              <ChevronLeftIcon />
            </button>
            <div className="ml-2 flex-1">
              <div className="font-medium text-gray-900" style={{ fontSize: `${chatTitleFontSize}px` }}>{title}</div>
              <ChatHeaderStatus sending={assistantTyping} />
              {groupDiscussionStatus ? (
                <div className="text-[11px] font-medium text-amber-700">{groupDiscussionStatus}</div>
              ) : null}
            </div>
            <button
              className={chatHeaderButtonClass}
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
        )}
        {searchOpen ? (
          <div className={`mt-3 flex items-center gap-2 rounded-[18px] px-3 py-2 ${chatSearchShellClass}`}>
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
        className={`relative z-10 min-h-0 w-full max-w-full flex-1 overflow-x-hidden overflow-y-auto overscroll-contain px-3.5 pb-5 ${messagesTopPaddingClass}`}
      >
        <div className="space-y-4">
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
                    {groupChatMode ? <div className="px-1 text-[11px] font-medium leading-none text-gray-400">辛玥</div> : null}
                    {group.parts.map((part, index) => {
                      const matchId = getChatSearchMatchId(group.id, index);
                      const isActiveSearchPart = activeSearchMatchId === matchId;
                      const bubbleSkin = transparentBubbleEnabled ? undefined : resolveBubbleSkin(userBubbleStyle);
                      return (
                        <ChatBubbleFrame
                          key={`${group.id}-${index}`}
                          ref={(el) => {
                            searchResultRefs.current[matchId] = el;
                          }}
                          skin={bubbleSkin}
                          align="right"
                          className={`block max-w-full rounded-[18px] px-2.5 py-[5px] text-left font-medium leading-[1.42] shadow-sm ${
                            transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("user", userBubbleStyle)
                          } ${isActiveSearchPart ? "ring-2 ring-amber-300/90 ring-offset-2 ring-offset-transparent" : ""}`}
                          style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
                        >
                          <PlainTextBlock content={part.content || (sending ? "…" : "")} />
                        </ChatBubbleFrame>
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
                      image={group.role === "benben" ? benbenAvatarImage : duAvatarImage}
                      label={group.role === "benben" ? "笨" : avatarLabel}
                      className={group.role === "benben" ? "bg-[#FFF3D7] text-[#8A5A10]" : avatarClass}
                    />
                  ) : null}
                  <div className={`mt-[2px] ${showChatAvatars ? "max-w-[78%]" : "max-w-[86%]"} space-y-1.5`}>
                    {groupChatMode ? (
                      <div className="px-1 text-[11px] font-medium leading-none text-gray-400">
                        {group.role === "benben" ? "笨笨" : avatarLabel || "渡"}
                      </div>
                    ) : null}
                    {group.parts.map((part, index) => {
                      const matchId = getChatSearchMatchId(group.id, index);
                      const isActiveSearchPart = activeSearchMatchId === matchId;
                      const bubbleSkin = transparentBubbleEnabled || group.role === "benben" ? undefined : resolveBubbleSkin(assistantBubbleStyle);
                      return (
                        <div
                          key={`${group.id}-${index}`}
                          ref={(el) => {
                            searchResultRefs.current[matchId] = el;
                          }}
                          className={`space-y-2 rounded-[20px] ${isActiveSearchPart ? "ring-2 ring-amber-300/90 ring-offset-2 ring-offset-transparent" : ""}`}
                        >
                          {part.reasoning ? (
                            <details className="group max-w-full text-[11px] text-gray-500">
                              <summary className="flex cursor-pointer list-none items-center gap-1 px-1 text-[11px] font-medium leading-4 text-gray-400 [&::-webkit-details-marker]:hidden">
                                <span className="transition-transform group-open:rotate-90">&gt;</span>
                                <span>碎碎念</span>
                              </summary>
                              <div className="mt-1 max-h-36 overflow-y-auto whitespace-pre-wrap break-words px-1 pl-4 text-[11px] leading-4 text-gray-500">
                                {part.reasoning}
                              </div>
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
                              <ChatBubbleFrame
                                skin={bubbleSkin}
                                className={`inline-block w-fit max-w-full rounded-[18px] px-2.5 py-[5px] font-medium leading-[1.42] shadow-sm ${
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
                              </ChatBubbleFrame>
                              <div className="flex items-center gap-3 pl-1 text-[11px] text-gray-500">
                                <button
                                  className="rounded-full p-1 text-gray-500 transition-colors active:bg-gray-100 active:opacity-70"
                                  onClick={() => copyText(part.content, toast)}
                                  aria-label="复制"
                                  title="复制"
                                >
                                  <CopyIconMini />
                                </button>
                                {group.role === "assistant" && part.status === "failed" && part.operationId ? (
                                  <button
                                    className="rounded-full px-2 py-1 text-[11px] font-medium text-rose-500 transition-colors active:bg-rose-50"
                                    onClick={() => void retrySumiTalkOperation(part.operationId || "")}
                                  >
                                    重试
                                  </button>
                                ) : null}
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

      <div className={`relative z-20 border-t pb-[calc(env(safe-area-inset-bottom,24px))] ${chatFooterClass}`}>
        <div className={`overflow-hidden transition-all duration-300 ease-in-out ${hasCustomChatBackground ? "bg-white/18 backdrop-blur-xl" : "bg-white"} ${plusOpen ? "h-[140px] opacity-100" : "h-0 opacity-0"}`}>
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
          <div className={`flex min-h-[42px] flex-1 items-center rounded-[20px] px-4 py-2.5 ${chatInputShellClass}`}>
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
            disabled={!trimmedInput || (sending && !canSubmitWhileBusy)}
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
