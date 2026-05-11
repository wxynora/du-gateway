import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiJson, getOrCreatePanelDeviceId, setPanelToken } from "./api";
import { AvatarBubble, ChatActionButton, ChatHeaderStatus, HtmlBlock, PlainTextBlock, RichTextBlock, copyText, formatTokenCountValue } from "./ChatPresentation";
import {
  TRANSPARENT_BUBBLE_CLASS,
  resolveBubbleClass,
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
import { migrateLocalChatHistoryDevice, readLocalChatHistory, readLocalChatHistoryRows, writeLocalChatHistory } from "./storage/chatHistoryDb";
import { useCodexGroupTaskRealtime, type CodexGroupTaskRealtimeTask } from "./hooks/useCodexGroupTaskRealtime";
import { useToast } from "./toast";

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
        if (!deviceId || !historyWindowId) return;
        remoteHistoryReadyRef.current = false;
        remoteHistoryWarningShownRef.current = false;
        const localMessages = sanitizeHistoryMessages(await readLocalChatHistory(deviceId, historyWindowId));
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
          legacyLocalGroups.push(sanitizeHistoryMessages(await readLocalChatHistory(deviceId, windowId)));
        }
        if (!groupChatMode && historyWindowId !== MAIN_SUMITALK_DISPLAY_WINDOW_ID) {
          legacyLocalGroups.push(sanitizeHistoryMessages(await readLocalChatHistory(deviceId, MAIN_SUMITALK_DISPLAY_WINDOW_ID)));
        }
        const legacyLocalMessages = legacyLocalGroups.reduce(
          (best, item) => pickBetterHistory(item, best, []),
          [] as ChatDraftMessage[],
        );
        const recoveredLocalMessages = pickBetterHistory(localCandidateMessages, localMessages, []);
        const fallbackLocalMessages = pickBetterHistory(recoveredLocalMessages, legacyLocalMessages, []);
        if (!cancelled && fallbackLocalMessages.length) {
          setMessages(fallbackLocalMessages);
          await writeLocalChatHistory(deviceId, historyWindowId, fallbackLocalMessages);
        }
        const j = await apiJson<{ ok?: boolean; messages?: ChatDraftMessage[] }>(sumitalkHistoryPath(remoteHistoryWindowId));
        if (cancelled) return;
        if (j?.ok) {
          remoteHistoryReadyRef.current = true;
        }
        const remoteMessages = sanitizeHistoryMessages(Array.isArray(j?.messages) ? j.messages : []);
        const next = pickBetterHistory(remoteMessages, fallbackLocalMessages, seedMessages);
        setMessages(next);
        if (next !== seedMessages && next.length) {
          await writeLocalChatHistory(deviceId, historyWindowId, next);
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
    options: { syncRemote?: boolean; localDeviceId?: string } = {},
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
      await apiJson("/miniapp-api/sumitalk-history", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sumitalkHistoryPayload(sanitizedMessages, remoteHistoryWindowId)),
      });
    } catch {}
  }

  async function applyBenbenTaskTerminal(
    task: CodexGroupTaskRealtimeTask,
    options: { messageId?: string; localDeviceId?: string } = {},
  ): Promise<boolean> {
    const taskId = String(task?.id || "").trim();
    const statusValue = String(task?.status || "").trim();
    if (!taskId || !["done", "error", "cancelled"].includes(statusValue)) return false;
    if (benbenTaskFinalizedRef.current.has(taskId)) return true;

    const currentMessages = messagesRef.current;
    const targetMessageId = String(options.messageId || "").trim()
      || String(currentMessages.find((msg) => msg.role === "benben" && String(msg.jobId || "").trim() === taskId)?.id || "").trim();
    if (!targetMessageId) return false;

    const currentMessage = currentMessages.find((msg) => msg.id === targetMessageId);
    const createdAt = currentMessage?.createdAt || new Date().toISOString();
    const terminalMessage: ChatDraftMessage = statusValue === "done"
      ? {
          id: targetMessageId,
          role: "benben",
          content: String(task.response || "").trim() || "（笨笨没有返回内容）",
          createdAt,
          status: "sent",
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
      void applyBenbenTaskTerminal(task, { localDeviceId: deviceId });
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
    await saveDisplayHistory(pendingMessages, { localDeviceId: params.replyTarget });
    let taskId = "";
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
      taskId = String(created.task?.id || "").trim();
      if (!taskId) throw new Error(created.error || "笨笨任务没有返回 ID");
      const queuedMessages = applyMessageById(messagesRef.current, benbenId, {
        ...pendingMsg,
        content: "笨笨任务已创建，等我一下...",
        status: "pending",
        jobId: taskId,
      });
      messagesRef.current = queuedMessages;
      setMessages(queuedMessages);
      await saveDisplayHistory(queuedMessages, { localDeviceId: params.replyTarget });
      const task = await waitForCodexGroupChatTask(taskId);
      const applied = await applyBenbenTaskTerminal(task, { messageId: benbenId, localDeviceId: params.replyTarget });
      if (!applied) throw new Error("笨笨没有返回内容");
      return messagesRef.current;
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
          const applied = await applyBenbenTaskTerminal(task, { messageId: item.messageId, localDeviceId: deviceId });
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
    await saveDisplayHistory(draftMessages, { syncRemote: groupChatMode, localDeviceId: resolvedDeviceId });
    try {
      const requestUserContent = groupChatMode ? buildGroupTurnUserContent(nextMessages, content) : content;
      const requestWindowId = windowId;
      const requestBody = {
        model: activeModel,
        messages: [{ role: "user", content: requestUserContent }],
        stream: false,
        window_id: requestWindowId,
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
        await saveDisplayHistory(finalMessages, { localDeviceId: replyTarget });
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
      await saveDisplayHistory(failedMessages, { localDeviceId: replyTarget });
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
                    {groupChatMode ? <div className="px-1 text-[11px] font-medium leading-none text-gray-400">辛玥</div> : null}
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
