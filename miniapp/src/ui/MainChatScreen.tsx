import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson, consumePendingPanelDeviceIdMigration, getOrCreatePanelDeviceId, setPanelToken } from "./api";
import { AvatarBubble, ChatActionButton, ChatAttachmentBlock, ChatBubbleFrame, ChatHeaderStatus, ChatVoiceTranscriptBlock, HtmlBlock, PlainTextBlock, RichTextBlock, copyText } from "./ChatPresentation";
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
  applySumiTalkChatEventToMessages,
  applyAssistantTerminalMessage,
  applyMessageById,
  buildCodexGroupRecentMessages,
  buildGroupTurnUserContent,
  formatClockTime,
  getChatSearchMatchId,
  groupChatMessages,
  chatAttachmentPreviewLabel,
  normalizeChatAttachments,
  pickBetterHistory,
  sanitizeHistoryMessages,
  sanitizeVoiceTranscriptText,
  shouldShowGroupTime,
  stripTransientChatDisplayParts,
  type ChatAttachment,
  type ChatDisplayPart,
  type ChatDraftMessage,
  type ChatRole,
  type ChatSearchMatch,
  type ChatTimeFormat,
  type ChatToolCallState,
} from "./chatMessages";
import {
  MAIN_SUMITALK_DISPLAY_WINDOW_ID,
  sumitalkHistoryPath,
} from "./chatWindowIds";
import {
  ArrowUpIcon,
  ChevronDownMini,
  ChevronLeftIcon,
  ChevronUpMini,
  KeyboardIconMini,
  MicIconMini,
  PlusIcon,
  SearchIconMini,
} from "./icons";
import { SumiOverlay } from "../plugins/sumi-overlay";
import {
  attachChatJobToOperation,
  completeChatOperation,
  createChatDraftTurn,
  deleteLocalChatHistoryMessages,
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
import { useSumiTalkChatRealtime, type SumiTalkChatRealtimeEvent } from "./hooks/useSumiTalkChatRealtime";
import { readMusicBgmContext } from "./listenBgm";
import { buildAnthropicImageDataUrlFromDataUrl } from "./imageDataUrl";
import { useToast } from "./toast";
import {
  apiJsonWithTimeout,
  isAbortLikeError,
  waitMs,
} from "./chat/sumitalkChatClient";
import {
  createDuReplyAudio,
  resolveRecorderMimeType,
} from "./chat/chatMedia";
import {
  prepareDocumentPrivateChatInput,
  prepareImagesPrivateChatInput,
  prepareTextPrivateChatInput,
  prepareTravelFormPrivateChatInput,
  prepareVoicePrivateChatInput,
  type PreparedPrivateChatInput,
  type PrivateModelContent,
} from "./chat/privateChatInput";
import { DoodleBoardModal } from "./chat/DoodleBoardModal";
import {
  buildPrivateUserContent,
  contentWithAttachmentHint,
  isVoiceTranscriptEcho,
} from "./chat/privateChatHelpers";
import {
  buildPrivateAssistantFailureMessage,
  buildPrivateChatRequestBody,
  runPrivateChatSendFlow,
} from "./chat/privateChatSendFlow";
import { resolveChatSendStageLabel } from "./chat/chatSendStage";
import { recoverSumiTalkOperationFlow } from "./chat/chatRecoveryFlow";
import {
  GROUP_DISCUSSION_MAX_FOLLOWUPS,
  buildGroupDiscussionUserContent,
  buildGroupFreeDiscussionOpeningContent,
  codexGroupTaskStatusText,
  groupDiscussionShouldStop,
  isBenbenCancelCommand,
  isGroupDiscussionContinueCommand,
  isGroupDiscussionStopCommand,
  parseGroupDiscussionContinueTurns,
  resolveEffectiveGroupReplyTargets,
  resolveNextFreeDiscussionSpeaker,
  resolveNextGroupDiscussionSpeaker,
  type GroupDiscussionSnapshot,
  type GroupDiscussionSpeaker,
} from "./chat/groupChatRouting";
import {
  buildGroupAssistantFailureMessage,
  buildGroupChatRequestBody,
  runGroupDuReplyFlow,
} from "./chat/groupChatSendFlow";
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
type ChatSendSource = "text" | "image" | "document" | "voice" | "travel_form" | "group_command" | "retry";
type ActiveChatRequest = {
  attemptId: string;
  clientRequestId: string;
  operationId: string;
  assistantId: string;
  jobId: string;
  source: ChatSendSource;
  abortController: AbortController;
};
type QueuedPrivateInput = {
  content: string;
  displayContent: string;
  attachments: ChatAttachment[];
  source: ChatSendSource;
  modelContent: PrivateModelContent;
  userMessage: ChatDraftMessage;
};
type PrivateInputAggregateMode = "idle" | "armed" | "paused" | "flushing";
type PrivateInputAggregatePauseReason = "cancel" | "failure" | null;
type PendingImageDraft = {
  id: string;
  file: File;
  previewUrl: string;
};
type ChatBubbleMenuTargetBase = {
  id: string;
  messageId?: string;
  role: ChatRole;
  content: string;
  attachments?: ChatAttachment[];
  transcript: string;
  transcriptId: string;
  hasVoice: boolean;
  canRetry: boolean;
  aggregateEditable?: boolean;
  aggregateCanEditText?: boolean;
  operationId?: string;
  status?: ChatDraftMessage["status"];
};
type ChatBubbleMenuTarget = ChatBubbleMenuTargetBase & {
  x: number;
  y: number;
};
type ChatBubbleQuote = {
  role: ChatRole;
  roleLabel: string;
  text: string;
};
type ChatBubbleTouchState = {
  target: ChatBubbleMenuTargetBase;
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
  timer: number;
  menuOpened: boolean;
};
const CODEX_GROUP_CHAT_POLL_MS = 1000;
const CODEX_GROUP_CHAT_TIMEOUT_MS = 10 * 60 * 1000;
const CODEX_GROUP_CHAT_CREATE_TIMEOUT_MS = 30000;
const CODEX_GROUP_CHAT_CREATE_RETRY_TIMEOUT_MS = 45000;
const SUMITALK_PRIVATE_INPUT_IDLE_MS = 15000;
const SUMITALK_PRIVATE_INPUT_BUSY_RETRY_MS = 1200;
const SUMITALK_PRIVATE_INPUT_AGGREGATE_STORAGE_PREFIX = "miniapp.chat.privateInputAggregate.v1";
const SUMITALK_PRIVATE_INPUT_DELETED_STORAGE_PREFIX = "miniapp.chat.privateInputAggregateDeleted.v1";
const SUMITALK_REAL_MODE_STORAGE_PREFIX = "miniapp.chat.realMode.v1";
const SUMITALK_REAL_BODY_STATE_POLL_MS = 5000;

function sumitalkRealModeStorageKey(windowId: string): string {
  return `${SUMITALK_REAL_MODE_STORAGE_PREFIX}:${encodeURIComponent(String(windowId || "default").trim() || "default")}`;
}

function readStoredRealMode(storageKey: string): boolean {
  try {
    return window.localStorage.getItem(storageKey) === "1";
  } catch {
    return false;
  }
}

function writeStoredRealMode(storageKey: string, enabled: boolean) {
  try {
    if (enabled) window.localStorage.setItem(storageKey, "1");
    else window.localStorage.removeItem(storageKey);
  } catch {}
}

function realVitalsNumber(vitals: Record<string, any> | undefined, key: string): number {
  const raw = vitals?.parameters?.[key] ?? vitals?.[key];
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
}

function realModeMoodEmoji(vitals: Record<string, any> | undefined): string {
  if (realVitalsNumber(vitals, "intimacy_heat") >= 0.6) return "🥵";
  const tempo = String(vitals?.tempo || "").trim().toLowerCase();
  if (tempo === "up" || tempo === "settle") return "😄";
  if (tempo === "down") return "😭";
  if (tempo === "spike") return "😠";
  return "😐";
}

function realModeLevel(value: any): string {
  if (value === null || typeof value === "undefined" || value === "") return "?";
  const level = Number(value);
  if (!Number.isFinite(level)) return "?";
  return String(Math.max(0, Math.min(5, Math.round(level))));
}

function realModePenisState(value: any): string {
  const text = String(value || "").replace(/^阴茎状态[:：]?\s*/, "").replace(/状态$/, "").trim();
  return text || "未记录";
}

function formatRealModeBodyStatus(state: any): string {
  const bodyState = state?.du_body_state && typeof state.du_body_state === "object" ? state.du_body_state : {};
  const desireLevel = realModeLevel(bodyState.desire_level);
  const selfControlLevel = realModeLevel(bodyState.self_control_level);
  const penisState = realModePenisState(bodyState.penis_state);
  const mood = realModeMoodEmoji(state?.du_vitals && typeof state.du_vitals === "object" ? state.du_vitals : undefined);
  return `想做指数${desireLevel}/5·自制力${selfControlLevel}/5·${penisState}·${mood}`;
}

function privateInputAggregateDeadlineFromPayload(payload: any): number {
  const expiresAt = Date.parse(String(payload?.expiresAt || ""));
  if (Number.isFinite(expiresAt) && expiresAt > 0) return expiresAt;
  const updatedAt = Date.parse(String(payload?.updatedAt || ""));
  if (Number.isFinite(updatedAt) && updatedAt > 0) return updatedAt + SUMITALK_PRIVATE_INPUT_IDLE_MS;
  return 0;
}

function ToolCallGlyph({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 12 12" aria-hidden="true">
      <path
        fill="currentColor"
        d="M8.6 1.1A2.8 2.8 0 0 0 5.5 4.7L1.8 8.4a1.35 1.35 0 1 0 1.9 1.9l3.7-3.7A2.8 2.8 0 0 0 10.9 3L9 4.9 7.7 3.6l1.9-1.9c-.3-.3-.6-.5-1-.6Z"
      />
    </svg>
  );
}

function ToolStatusGlyph({ state, className = "" }: { state: ChatToolCallState; className?: string }) {
  if (state === "running") {
    return (
      <svg className={className} viewBox="0 0 12 12" aria-hidden="true">
        <circle cx="6" cy="6" r="5" fill="currentColor" opacity="0.18" />
        <circle cx="6" cy="6" r="2.2" fill="currentColor" />
      </svg>
    );
  }
  if (state === "error") {
    return (
      <svg className={className} viewBox="0 0 12 12" aria-hidden="true">
        <circle cx="6" cy="6" r="5" fill="currentColor" />
        <path d="m4.2 4.2 3.6 3.6M7.8 4.2 4.2 7.8" fill="none" stroke="white" strokeWidth="1.35" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg className={className} viewBox="0 0 12 12" aria-hidden="true">
      <circle cx="6" cy="6" r="5" fill="currentColor" />
      <path d="m3.7 6.1 1.5 1.5 3.1-3.4" fill="none" stroke="white" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChatToolCallBlock({ part }: { part: ChatDisplayPart }) {
  const [open, setOpen] = useState(false);
  if (part.kind !== "tool_call") return null;
  const name = String(part.name || "工具").trim() || "工具";
  const state = part.state || "done";
  const statusLabel = state === "running" ? "running" : state === "error" ? "failed" : "done";
  const statusClass = state === "running" ? "text-sky-500" : state === "error" ? "text-rose-500" : "text-gray-400";
  const argsText = String(part.argumentsText || "").trim();
  const resultText = String(part.resultText || "").trim();
  const hasDetails = Boolean(argsText || resultText);

  return (
    <div className="w-fit max-w-full py-0.5 text-[10px] leading-[14px] text-gray-400">
      <button
        type="button"
        className={`grid max-w-full grid-cols-[14px_minmax(0,1fr)] gap-x-1 text-left ${hasDetails ? "cursor-pointer" : "cursor-default"}`}
        onClick={() => hasDetails && setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="col-start-1 row-start-1 flex h-[14px] items-center justify-center text-gray-400">
          <ToolCallGlyph className="h-3 w-3" />
        </span>
        <span className="col-start-2 row-start-1 min-w-0 truncate font-mono text-[10px] font-semibold leading-[14px] text-gray-500">
          {name}
        </span>
        <span className="col-start-1 row-start-2 flex justify-center py-[1px]" aria-hidden="true">
          <span
            className="h-[14px] w-1"
            style={{
              backgroundImage: "radial-gradient(circle, rgba(156, 163, 175, 0.85) 1px, transparent 1.2px)",
              backgroundPosition: "center top",
              backgroundRepeat: "repeat-y",
              backgroundSize: "4px 4px",
            }}
          />
        </span>
        <span className={`col-start-1 row-start-3 flex h-[14px] items-center justify-center ${statusClass}`}>
          <ToolStatusGlyph state={state} className="h-3 w-3" />
        </span>
        <span className={`col-start-2 row-start-3 min-w-0 truncate font-mono text-[10px] font-semibold leading-[14px] ${statusClass}`}>
          {statusLabel}
        </span>
      </button>
      {open && hasDetails ? (
        <div className="ml-[7px] mt-1 space-y-1 border-l border-gray-200 pl-2.5 text-[10px] leading-[15px] text-gray-500">
          {argsText ? (
            <div>
              <div className="mb-0.5 font-semibold text-gray-400">args</div>
              <pre className="max-h-28 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-[14px] text-gray-500">{argsText}</pre>
            </div>
          ) : null}
          {resultText ? (
            <div>
              <div className="mb-0.5 font-semibold text-gray-400">result</div>
              <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-[14px] text-gray-500">{resultText}</pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ChatReasoningBlock({ part }: { part: ChatDisplayPart }) {
  const [open, setOpen] = useState(true);
  if (part.kind !== "reasoning") return null;
  const text = String(part.text || "").trim();
  if (!text) return null;
  const label = part.round ? `碎碎念 · 第${part.round}轮` : "碎碎念";
  return (
    <div className="max-w-full px-1 text-[10px] leading-[15px] text-gray-500">
      <button
        type="button"
        className="flex max-w-full items-center gap-1 text-[10px] font-medium leading-[14px] text-gray-400"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className={`transition-transform ${open ? "rotate-90" : ""}`}>&gt;</span>
        <span>{label}</span>
      </button>
      {open ? (
        <div className="mt-1 max-h-36 overflow-y-auto whitespace-pre-wrap break-words border-l border-gray-200 pl-3 text-[10px] leading-[15px] text-gray-500">
          {text}
        </div>
      ) : null}
    </div>
  );
}

function makeChatAttemptId(clientRequestId: string): string {
  return `attempt-${clientRequestId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function isChatSendSource(value: any): value is ChatSendSource {
  return ["text", "image", "document", "voice", "travel_form", "group_command", "retry"].includes(String(value || "").trim());
}

function privateInputAggregateStorageKey(windowId: string): string {
  return `${SUMITALK_PRIVATE_INPUT_AGGREGATE_STORAGE_PREFIX}:${encodeURIComponent(String(windowId || "default").trim() || "default")}`;
}

function privateInputAggregateDeletedStorageKey(windowId: string): string {
  return `${SUMITALK_PRIVATE_INPUT_DELETED_STORAGE_PREFIX}:${encodeURIComponent(String(windowId || "default").trim() || "default")}`;
}

function normalizePrivateInputAggregateMode(value: any): PrivateInputAggregateMode {
  const mode = String(value || "").trim();
  if (mode === "armed" || mode === "paused" || mode === "flushing") return mode;
  return "idle";
}

function normalizePrivateInputAggregatePauseReason(value: any): PrivateInputAggregatePauseReason {
  const reason = String(value || "").trim();
  if (reason === "cancel" || reason === "failure") return reason;
  return null;
}

function normalizePrivateModelContent(value: any): PrivateModelContent {
  if (Array.isArray(value)) {
    return value
      .filter((part) => part && typeof part === "object")
      .map((part) => ({ ...part }));
  }
  return String(value || "").trim();
}

function isDataImageUrl(value: any): boolean {
  return /^data:image\/[^;,]+;base64,/i.test(String(value || "").trim());
}

function isFetchableImageUrl(value: any): boolean {
  const text = String(value || "").trim();
  return Boolean(text) && !isDataImageUrl(text) && (/^https?:\/\//i.test(text) || text.startsWith("/"));
}

async function blobToDataUrl(blob: Blob): Promise<string> {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(blob);
  });
}

async function fetchImageAsCompressedDataUrl(url: string): Promise<string> {
  const resp = await fetch(url, { credentials: "include" });
  if (!resp.ok) throw new Error(`图片读取失败：HTTP ${resp.status}`);
  const blob = await resp.blob();
  return buildAnthropicImageDataUrlFromDataUrl(await blobToDataUrl(blob));
}

function localImageUrlsFromAttachments(attachments?: ChatAttachment[]): string[] {
  return normalizeChatAttachments(attachments)
    .filter((item) => item.kind === "image")
    .map((item) => String(item.remoteUrl || "").trim())
    .filter(Boolean);
}

function privateModelContentForLocalStorage(modelContent: PrivateModelContent, attachments?: ChatAttachment[]): PrivateModelContent {
  if (!Array.isArray(modelContent)) return modelContent;
  const imageUrls = localImageUrlsFromAttachments(attachments);
  let imageIndex = 0;
  const parts = modelContent
    .filter((part) => part && typeof part === "object")
    .map((part) => {
      const imageUrl = part.image_url && typeof part.image_url === "object" ? part.image_url : null;
      const rawUrl = String(imageUrl?.url || "").trim();
      if (!isDataImageUrl(rawUrl)) return { ...part };
      const replacementUrl = imageUrls[imageIndex++] || "";
      if (!replacementUrl) return { type: "text", text: "[图片]" };
      return {
        ...part,
        image_url: {
          ...imageUrl,
          url: replacementUrl,
        },
      };
    });
  return parts.length === 1 && parts[0]?.type === "text" ? String(parts[0].text || "").trim() : parts;
}

function privateRequestBodyForLocalStorage(body: any, attachments?: ChatAttachment[]): any {
  if (!body || typeof body !== "object") return body;
  const messages = Array.isArray(body.messages) ? body.messages : [];
  return {
    ...body,
    messages: messages.map((message: any) => {
      if (!message || typeof message !== "object") return message;
      return {
        ...message,
        content: privateModelContentForLocalStorage(message.content, attachments),
      };
    }),
  };
}

function stripPreviewUrlsFromAttachments(attachments?: ChatAttachment[]): ChatAttachment[] {
  return normalizeChatAttachments(attachments).map((attachment) => {
    const { previewUrl, ...persistable } = attachment;
    return persistable;
  });
}

function stripPreviewUrlsFromMessages(messages: ChatDraftMessage[]): ChatDraftMessage[] {
  return messages.map((message) => {
    const attachments = stripPreviewUrlsFromAttachments(message.attachments);
    if (!attachments.length) {
      const { attachments: _attachments, ...rest } = message;
      return rest;
    }
    return {
      ...message,
      attachments,
    };
  });
}

async function compressPrivateModelContentDataImages(modelContent: PrivateModelContent): Promise<PrivateModelContent> {
  if (!Array.isArray(modelContent)) return modelContent;
  let changed = false;
  const parts = await Promise.all(modelContent.map(async (part) => {
    if (!part || typeof part !== "object") return part;
      const imageUrl = part.image_url && typeof part.image_url === "object" ? part.image_url : null;
      const rawUrl = String(imageUrl?.url || "").trim();
      if (!isDataImageUrl(rawUrl)) {
        if (!isFetchableImageUrl(rawUrl)) return { ...part };
        const compressedUrl = await fetchImageAsCompressedDataUrl(rawUrl);
        changed = true;
        return {
          ...part,
          image_url: {
            ...imageUrl,
            url: compressedUrl,
          },
        };
      }
      try {
        const compressedUrl = await buildAnthropicImageDataUrlFromDataUrl(rawUrl);
        if (compressedUrl && compressedUrl !== rawUrl) changed = true;
      return {
        ...part,
        image_url: {
          ...imageUrl,
          url: compressedUrl || rawUrl,
        },
      };
    } catch {
      return { ...part };
    }
  }));
  return changed ? parts : modelContent;
}

async function compressQueuedPrivateInputImages(item: QueuedPrivateInput): Promise<QueuedPrivateInput> {
  return {
    ...item,
    modelContent: await compressPrivateModelContentDataImages(item.modelContent),
  };
}

function shouldDropPrivateAggregateAfterFailure(source: ChatSendSource, queued: QueuedPrivateInput[], messages: ChatDraftMessage[]): boolean {
  if (source !== "image" && !queued.some((item) => item.attachments.some((attachment) => attachment.kind === "image"))) return false;
  const tail = messages
    .slice(-6)
    .map((message) => String(message.content || ""))
    .join("\n");
  return /image\s+too\s+large|图片.{0,12}过大|图像.{0,12}过大/i.test(tail);
}

function queuedPrivateInputForLocalStorage(item: QueuedPrivateInput): QueuedPrivateInput {
  const serializable = item;
  const attachments = stripPreviewUrlsFromAttachments(serializable.attachments);
  const userMessage = {
    ...serializable.userMessage,
    attachments: stripPreviewUrlsFromAttachments(serializable.userMessage.attachments),
  };
  return {
    ...serializable,
    attachments,
    userMessage,
    modelContent: privateModelContentForLocalStorage(serializable.modelContent, attachments),
  };
}

function normalizeQueuedPrivateInput(raw: any): QueuedPrivateInput | null {
  if (!raw || typeof raw !== "object") return null;
  const rawUserMessage = sanitizeHistoryMessages([raw.userMessage]).find((message) => message.role === "user");
  const content = String(raw.content ?? rawUserMessage?.content ?? "").trim();
  const displayContent = String(raw.displayContent ?? rawUserMessage?.content ?? content).trim();
  const attachments = normalizeChatAttachments(raw.attachments || rawUserMessage?.attachments);
  if (!content && !attachments.length) return null;
  const source: ChatSendSource = isChatSendSource(raw.source)
    ? raw.source
    : attachments.some((item) => item.kind === "audio")
      ? "voice"
      : attachments.some((item) => item.kind === "image")
        ? "image"
        : attachments.some((item) => item.kind === "document")
          ? "document"
          : "text";
  const fallbackUserMessage: ChatDraftMessage = {
    id: String(rawUserMessage?.id || `user-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`),
    role: "user",
    content: displayContent,
    createdAt: String(rawUserMessage?.createdAt || new Date().toISOString()),
    status: "sent",
    ...(attachments.length ? { attachments } : {}),
  };
  const userMessage: ChatDraftMessage = {
    ...fallbackUserMessage,
    ...rawUserMessage,
    role: "user",
    content: String(rawUserMessage?.content ?? displayContent).trim(),
    status: "sent",
    ...(attachments.length ? { attachments } : {}),
  };
  const modelContent = raw.modelContent == null
    ? buildPrivateUserContent(content, attachments)
    : normalizePrivateModelContent(raw.modelContent);
  return {
    content,
    displayContent,
    attachments,
    source,
    modelContent,
    userMessage,
  };
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

function chatHistoryMergeKey(message: ChatDraftMessage): string {
  const id = String(message?.id || "").trim();
  if (id) return `id:${id}`;
  const clientRequestId = String(message?.clientRequestId || "").trim();
  const role = String(message?.role || "").trim();
  if (clientRequestId && role) return `request:${clientRequestId}:${role}`;
  return `raw:${role}:${String(message?.createdAt || "").trim()}:${String(message?.content || "").trim()}`;
}

function chatHistoryMessageScore(message: ChatDraftMessage): number {
  let score = 0;
  if (String(message?.content || "").trim()) score += 4;
  if (String(message?.reasoning || "").trim()) score += 2;
  if ((message?.attachments || []).length) score += 2;
  if ((message?.displayParts || []).length) score += 2;
  if (message?.tokenCount?.input || message?.tokenCount?.output) score += 1;
  if (message?.status === "sent") score += 3;
  if (message?.status === "failed") score += 2;
  if (message?.status === "pending") score -= 1;
  return score;
}

function chooseChatHistoryMessage(current: ChatDraftMessage, incoming: ChatDraftMessage): ChatDraftMessage {
  if (current.status === "sent" && incoming.status === "pending") return current;
  if (current.status === "failed" && incoming.status === "pending") return current;
  if (incoming.status === "sent" && current.status === "pending") return incoming;
  if (incoming.status === "failed" && current.status === "pending") return incoming;
  return chatHistoryMessageScore(incoming) >= chatHistoryMessageScore(current) ? incoming : current;
}

function chatVoiceTranscriptId(item: ChatAttachment): string {
  return String(item.id || item.remoteKey || item.remoteUrl || "").trim();
}

function chatRoleQuoteLabel(role: ChatRole): string {
  if (role === "user") return "我";
  if (role === "benben") return "笨笨";
  return "渡";
}

function bubbleTargetText(target: ChatBubbleMenuTargetBase): string {
  const transcript = sanitizeVoiceTranscriptText(target.transcript);
  if (target.hasVoice && transcript) return transcript;
  const content = String(target.content || "").trim();
  if (content) return content;
  if (transcript) return transcript;
  return chatAttachmentPreviewLabel(target.attachments);
}

function quotePrefix(quote: ChatBubbleQuote): string {
  return [
    "【引用消息】",
    `${quote.roleLabel}：${quote.text}`,
    "【当前消息】",
  ].join("\n");
}

function contentWithQuote(content: string, quote: ChatBubbleQuote): string {
  return [quotePrefix(quote), String(content || "").trim()].filter(Boolean).join("\n");
}

function modelContentWithQuote(modelContent: PrivateModelContent, quote: ChatBubbleQuote): PrivateModelContent {
  const prefix = quotePrefix(quote);
  if (Array.isArray(modelContent)) {
    const parts = modelContent.map((part) => ({ ...part }));
    const textPart = parts.find((part) => part?.type === "text" && typeof part.text === "string");
    if (textPart) {
      textPart.text = [prefix, String(textPart.text || "").trim()].filter(Boolean).join("\n");
      return parts;
    }
    return [{ type: "text", text: prefix }, ...parts];
  }
  return [prefix, String(modelContent || "").trim()].filter(Boolean).join("\n");
}

function preparedInputWithQuote(prepared: PreparedPrivateChatInput, quote: ChatBubbleQuote): PreparedPrivateChatInput {
  return {
    ...prepared,
    content: contentWithQuote(prepared.content, quote),
    displayContent: prepared.displayContent ?? prepared.content,
    modelContent: modelContentWithQuote(prepared.modelContent, quote),
  };
}

function privateModelContentToParts(modelContent: PrivateModelContent): Array<Record<string, any>> {
  if (Array.isArray(modelContent)) return modelContent.map((part) => ({ ...part }));
  const text = String(modelContent || "").trim();
  return text ? [{ type: "text", text }] : [];
}

function mergePrivateModelContents(contents: PrivateModelContent[]): PrivateModelContent {
  const merged: Array<Record<string, any>> = [];
  const textBuffer: string[] = [];
  const flushText = () => {
    const text = textBuffer.map((item) => String(item || "").trim()).filter(Boolean).join("\n").trim();
    textBuffer.length = 0;
    if (text) merged.push({ type: "text", text });
  };
  for (const content of contents) {
    for (const part of privateModelContentToParts(content)) {
      if (part?.type === "text") {
        const text = String(part.text || "").trim();
        if (text) textBuffer.push(text);
        continue;
      }
      flushText();
      merged.push(part);
    }
  }
  flushText();
  if (merged.length === 1 && merged[0]?.type === "text") return String(merged[0].text || "").trim();
  return merged;
}

function resolveAggregateSource(items: QueuedPrivateInput[]): ChatSendSource {
  if (items.some((item) => item.attachments.some((attachment) => attachment.kind === "audio"))) return "voice";
  if (items.some((item) => item.attachments.some((attachment) => attachment.kind === "image"))) return "image";
  if (items.some((item) => item.attachments.some((attachment) => attachment.kind === "document"))) return "document";
  return items[items.length - 1]?.source || "text";
}

function mergeHistorySnapshots(...snapshots: ChatDraftMessage[][]): ChatDraftMessage[] {
  const merged = new Map<string, ChatDraftMessage>();
  for (const snapshot of snapshots) {
    for (const message of sanitizeHistoryMessages(snapshot || [])) {
      const key = chatHistoryMergeKey(message);
      const current = merged.get(key);
      merged.set(key, current ? chooseChatHistoryMessage(current, message) : message);
    }
  }
  return sanitizeHistoryMessages([...merged.values()]);
}

function hasNonSeedHistoryMessages(messages: ChatDraftMessage[]): boolean {
  return sanitizeHistoryMessages(messages).some((message) => !String(message?.id || "").startsWith("seed-"));
}

function historySnapshotSignature(messages: ChatDraftMessage[]): string {
  return sanitizeHistoryMessages(messages).map((message) => {
    const attachments = normalizeChatAttachments(message.attachments)
      .map((attachment) => [
        attachment.id,
        attachment.kind,
        attachment.remoteKey || "",
        attachment.remoteUrl || "",
        attachment.thumbUrl || "",
        attachment.name || "",
        attachment.size || 0,
      ].join(":"))
      .join(",");
    return [
      message.id,
      message.role,
      message.status || "",
      message.clientRequestId || "",
      message.operationId || "",
      message.jobId || "",
      message.content || "",
      message.reasoning || "",
      message.tokenCount?.input || 0,
      message.tokenCount?.output || 0,
      attachments,
      JSON.stringify(message.displayParts || []),
    ].join("\u0001");
  }).join("\u0002");
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
  const realModeStorageKey = sumitalkRealModeStorageKey(historyWindowId || windowId);
  const [deviceId, setDeviceId] = useState("");
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
  const [sending, setSendingState] = useState(false);
  const [mediaBusy, setMediaBusyValue] = useState(false);
  const [activeSendStageLabel, setActiveSendStageLabel] = useState("");
  const [recordingChatVoice, setRecordingChatVoiceValue] = useState(false);
  const [voiceInputOpen, setVoiceInputOpen] = useState(false);
  const [chatVoiceCancelArmed, setChatVoiceCancelArmed] = useState(false);
  const [privateInputAggregateCount, setPrivateInputAggregateCount] = useState(0);
  const [privateInputAggregateMode, setPrivateInputAggregateModeState] = useState<PrivateInputAggregateMode>("idle");
  const privateInputAggregateCancelable = privateInputAggregateMode === "armed";
  const privateInputAggregateHeld = privateInputAggregateMode === "paused";
  const [pendingImageDrafts, setPendingImageDrafts] = useState<PendingImageDraft[]>([]);
  const [groupDiscussionRunning, setGroupDiscussionRunning] = useState(false);
  const [groupDiscussionStatus, setGroupDiscussionStatus] = useState("");
  const [plusOpen, setPlusOpen] = useState(false);
  const [realModeEnabled, setRealModeEnabled] = useState(() => readStoredRealMode(realModeStorageKey));
  const [realBodyStatusText, setRealBodyStatusText] = useState("");
  const [doodleBoardOpen, setDoodleBoardOpen] = useState(false);
  const [travelFormCard, setTravelFormCard] = useState<TravelPlanFormCard | null>(null);
  const [travelResultCard, setTravelResultCard] = useState<TravelPlanResultCard | null>(null);
  const [travelTransportCard, setTravelTransportCard] = useState<TravelTransportDetailCard | null>(null);
  const [travelFoodCard, setTravelFoodCard] = useState<TravelFoodDetailCard | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);
  const [openVoiceTranscriptId, setOpenVoiceTranscriptId] = useState("");
  const [bubbleMenu, setBubbleMenu] = useState<ChatBubbleMenuTarget | null>(null);
  const [quotedBubble, setQuotedBubble] = useState<ChatBubbleQuote | null>(null);
  const chatBackgroundHeightRef = useRef(
    typeof window !== "undefined"
      ? Math.max(
          Math.round(window.innerHeight || 0),
          Math.round(document.documentElement?.clientHeight || 0),
          Math.round(window.visualViewport?.height || 0),
        )
      : 0,
  );
  const chatShouldStickBottomRef = useRef(true);
  const messagesScrollRef = useRef<HTMLDivElement | null>(null);
  const searchResultRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const lastSearchQueryRef = useRef("");
  const textInputRef = useRef<HTMLTextAreaElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const documentInputRef = useRef<HTMLInputElement | null>(null);
  const sendingRef = useRef(false);
  const pendingImageDraftsRef = useRef<PendingImageDraft[]>([]);
  const mediaBusyRef = useRef(false);
  const recordingChatVoiceRef = useRef(false);
  const chatVoiceStreamRef = useRef<MediaStream | null>(null);
  const chatVoiceRecorderRef = useRef<MediaRecorder | null>(null);
  const chatVoiceChunksRef = useRef<Blob[]>([]);
  const chatVoiceMimeRef = useRef("");
  const chatVoiceStartedAtRef = useRef(0);
  const chatVoicePressingRef = useRef(false);
  const chatVoiceStartYRef = useRef(0);
  const chatVoiceCancelArmedRef = useRef(false);
  const chatVoiceStartPromiseRef = useRef<Promise<boolean> | null>(null);
  const activeChatRequestRef = useRef<ActiveChatRequest | null>(null);
  const privateInputAggregateQueueRef = useRef<QueuedPrivateInput[]>([]);
  const privateInputAggregateTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const privateInputAggregateVersionRef = useRef(0);
  const privateInputAggregateModeRef = useRef<PrivateInputAggregateMode>("idle");
  const privateInputAggregatePauseReasonRef = useRef<PrivateInputAggregatePauseReason>(null);
  const privateInputAggregateFlushingItemsRef = useRef<QueuedPrivateInput[]>([]);
  const privateInputAggregateDeletedMessageIdsRef = useRef<Set<string>>(new Set());
  const privateInputAggregateDeadlineRef = useRef(0);
  const realModeEnabledRef = useRef(realModeEnabled);
  const bubbleTouchRef = useRef<ChatBubbleTouchState | null>(null);
  const remoteHistorySyncingRef = useRef(false);

  function setMediaBusy(next: boolean) {
    mediaBusyRef.current = next;
    setMediaBusyValue(next);
  }

  function setRecordingChatVoice(next: boolean) {
    recordingChatVoiceRef.current = next;
    setRecordingChatVoiceValue(next);
  }

  function setSending(next: boolean) {
    sendingRef.current = next;
    setSendingState(next);
  }

  function setPrivateInputAggregateQueue(items: QueuedPrivateInput[]) {
    privateInputAggregateQueueRef.current = items;
    setPrivateInputAggregateCount(items.length);
  }

  function setPrivateInputAggregateMode(next: PrivateInputAggregateMode, pauseReason: PrivateInputAggregatePauseReason = null) {
    privateInputAggregateModeRef.current = next;
    privateInputAggregatePauseReasonRef.current = next === "paused" ? pauseReason : null;
    setPrivateInputAggregateModeState(next);
    if (next !== "armed" && next !== "paused") {
      setBubbleMenu((current) => (current?.aggregateEditable ? null : current));
    }
  }

  function clearPrivateInputAggregateTimer() {
    if (privateInputAggregateTimerRef.current) {
      window.clearTimeout(privateInputAggregateTimerRef.current);
      privateInputAggregateTimerRef.current = null;
    }
    privateInputAggregateVersionRef.current += 1;
  }

  function resetPrivateInputAggregateMemory() {
    clearPrivateInputAggregateTimer();
    setPrivateInputAggregateQueue([]);
    privateInputAggregateFlushingItemsRef.current = [];
    setPrivateInputAggregateMode("idle");
    privateInputAggregateDeadlineRef.current = 0;
    setActiveSendStageLabel("");
  }

  function privateInputAggregateRemainingMs() {
    const deadline = privateInputAggregateDeadlineRef.current;
    if (!deadline) return 0;
    return Math.max(0, deadline - Date.now());
  }

  function reschedulePrivateInputAggregateWithinDeadline(reason: "idle" | "busy_retry" = "idle") {
    if (!privateInputAggregateQueueRef.current.length) {
      clearPrivateInputAggregateTimer();
      setPrivateInputAggregateMode("idle");
      setActiveSendStageLabel("");
      privateInputAggregateDeadlineRef.current = 0;
      return;
    }
    if (privateInputAggregateModeRef.current === "paused") {
      clearPrivateInputAggregateTimer();
      setActiveSendStageLabel("等待继续输入");
      privateInputAggregateDeadlineRef.current = 0;
      return;
    }
    const remaining = privateInputAggregateRemainingMs();
    if (remaining > 0) {
      setPrivateInputAggregateMode("armed");
      setActiveSendStageLabel("等待继续输入");
      schedulePrivateInputAggregateFlush(remaining, reason);
      return;
    }
    setPrivateInputAggregateMode("armed");
    schedulePrivateInputAggregateFlush(0, reason);
  }

  function refocusTextInputSoon() {
    if (voiceInputOpen) return;
    const focus = () => {
      try {
        textInputRef.current?.focus({ preventScroll: true });
      } catch {
        textInputRef.current?.focus();
      }
    };
    window.requestAnimationFrame(focus);
    window.setTimeout(focus, 60);
  }

  const refreshRealBodyStatus = useCallback(async () => {
    if (!realModeEnabledRef.current) return;
    try {
      const state = await apiJson<any>("/miniapp-api/pixel-home-state");
      setRealBodyStatusText(formatRealModeBodyStatus(state));
    } catch (e: any) {
      logSumiTalkClientEvent("real_mode_body_state_refresh_error", {
        error: String(e?.message || e),
      }, "warning");
    }
  }, []);

  function toggleRealMode() {
    setRealModeEnabled((current) => {
      const next = !current;
      realModeEnabledRef.current = next;
      writeStoredRealMode(realModeStorageKey, next);
      logSumiTalkClientEvent("real_mode_toggle", { enabled: next });
      if (next) void refreshRealBodyStatus();
      else setRealBodyStatusText("");
      return next;
    });
  }

  useEffect(() => {
    pendingImageDraftsRef.current = pendingImageDrafts;
  }, [pendingImageDrafts]);

  useEffect(() => {
    const stored = readStoredRealMode(realModeStorageKey);
    realModeEnabledRef.current = stored;
    setRealModeEnabled(stored);
    if (!stored) setRealBodyStatusText("");
  }, [realModeStorageKey]);

  useEffect(() => {
    realModeEnabledRef.current = realModeEnabled;
    if (!realModeEnabled) {
      setRealBodyStatusText("");
      return;
    }
    void refreshRealBodyStatus();
    const timer = window.setInterval(() => {
      void refreshRealBodyStatus();
    }, SUMITALK_REAL_BODY_STATE_POLL_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [realModeEnabled, realModeStorageKey, refreshRealBodyStatus]);

  useEffect(() => {
    return () => {
      for (const draft of pendingImageDraftsRef.current) {
        URL.revokeObjectURL(draft.previewUrl);
      }
      pendingImageDraftsRef.current = [];
    };
  }, []);

  function clearPendingImageDrafts() {
    if (mediaBusyRef.current) return;
    setPendingImageDrafts((current) => {
      for (const draft of current) {
        URL.revokeObjectURL(draft.previewUrl);
      }
      return [];
    });
  }

  function removePendingImageDraft(id: string) {
    if (mediaBusyRef.current) return;
    setPendingImageDrafts((current) => {
      const target = current.find((draft) => draft.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return current.filter((draft) => draft.id !== id);
    });
  }

  function movePendingImageDraft(id: string, direction: -1 | 1) {
    if (mediaBusyRef.current) return;
    setPendingImageDrafts((current) => {
      const index = current.findIndex((draft) => draft.id === id);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      const [draft] = next.splice(index, 1);
      next.splice(nextIndex, 0, draft);
      return next;
    });
  }

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

  function persistPrivateInputAggregate(reason: string) {
    if (groupChatMode) return;
    const storageKey = historyWindowId ? privateInputAggregateStorageKey(historyWindowId) : "";
    if (!storageKey) return;
    const items = privateInputAggregateQueueRef.current;
    const flushingItems = privateInputAggregateFlushingItemsRef.current;
    try {
      if (!items.length && !flushingItems.length) {
        window.localStorage.removeItem(storageKey);
        return;
      }
      window.localStorage.setItem(storageKey, JSON.stringify({
        schemaVersion: 2,
        windowId: historyWindowId,
        mode: privateInputAggregateModeRef.current,
        pauseReason: privateInputAggregatePauseReasonRef.current,
        holdUntilNextInput: privateInputAggregateModeRef.current === "paused",
        holdReason: privateInputAggregatePauseReasonRef.current,
        expiresAt: privateInputAggregateDeadlineRef.current ? new Date(privateInputAggregateDeadlineRef.current).toISOString() : "",
        updatedAt: new Date().toISOString(),
        items: items.map(queuedPrivateInputForLocalStorage),
        flushingItems: flushingItems.map(queuedPrivateInputForLocalStorage),
      }));
    } catch (e: any) {
      logSumiTalkClientEvent("private_input_aggregate_persist_error", {
        reason,
        error: String(e?.message || e),
      }, "warning");
    }
  }

  function loadPrivateInputAggregateDeletedMessageIds(): Set<string> {
    if (groupChatMode || !historyWindowId) return new Set();
    try {
      const payload = JSON.parse(window.localStorage.getItem(privateInputAggregateDeletedStorageKey(historyWindowId)) || "null");
      const ids = Array.isArray(payload?.ids) ? payload.ids : Array.isArray(payload) ? payload : [];
      return new Set(ids.map((id: any) => String(id || "").trim()).filter(Boolean));
    } catch {
      return new Set();
    }
  }

  function persistPrivateInputAggregateDeletedMessageIds(reason: string) {
    if (groupChatMode || !historyWindowId) return;
    const ids = [...privateInputAggregateDeletedMessageIdsRef.current].filter(Boolean).slice(-500);
    privateInputAggregateDeletedMessageIdsRef.current = new Set(ids);
    try {
      if (!ids.length) {
        window.localStorage.removeItem(privateInputAggregateDeletedStorageKey(historyWindowId));
        return;
      }
      window.localStorage.setItem(privateInputAggregateDeletedStorageKey(historyWindowId), JSON.stringify({
        schemaVersion: 1,
        windowId: historyWindowId,
        updatedAt: new Date().toISOString(),
        ids,
      }));
    } catch (e: any) {
      logSumiTalkClientEvent("private_input_aggregate_deleted_persist_error", {
        reason,
        error: String(e?.message || e),
      }, "warning");
    }
  }

  function rememberDeletedPrivateInputMessages(messageIds: Set<string>, source: string) {
    const current = privateInputAggregateDeletedMessageIdsRef.current;
    let changed = false;
    for (const rawId of messageIds) {
      const id = String(rawId || "").trim();
      if (!id || current.has(id)) continue;
      current.add(id);
      changed = true;
    }
    if (changed) persistPrivateInputAggregateDeletedMessageIds(source);
  }

  function filterDeletedDisplayMessages(nextMessages: ChatDraftMessage[]): ChatDraftMessage[] {
    const deletedIds = privateInputAggregateDeletedMessageIdsRef.current;
    if (!deletedIds.size) return sanitizeHistoryMessages(nextMessages);
    return sanitizeHistoryMessages(nextMessages).filter((message) => !deletedIds.has(String(message.id || "").trim()));
  }

  function restorePrivateInputAggregate() {
    resetPrivateInputAggregateMemory();
    if (groupChatMode || !historyWindowId) return;
    privateInputAggregateDeletedMessageIdsRef.current = loadPrivateInputAggregateDeletedMessageIds();
    const storageKey = privateInputAggregateStorageKey(historyWindowId);
    let payload: any = null;
    try {
      payload = JSON.parse(window.localStorage.getItem(storageKey) || "null");
    } catch {
      payload = null;
    }
    const deletedIds = privateInputAggregateDeletedMessageIdsRef.current;
    const storedItems: QueuedPrivateInput[] = Array.isArray(payload?.items)
      ? payload.items.map(normalizeQueuedPrivateInput).filter((item: QueuedPrivateInput | null): item is QueuedPrivateInput => Boolean(item))
      : [];
    const flushingItems: QueuedPrivateInput[] = Array.isArray(payload?.flushingItems)
      ? payload.flushingItems.map(normalizeQueuedPrivateInput).filter((item: QueuedPrivateInput | null): item is QueuedPrivateInput => Boolean(item))
      : [];
    const filteredStoredItems = storedItems.filter((item) => !deletedIds.has(String(item.userMessage.id || "").trim()));
    const filteredFlushingItems = flushingItems.filter((item) => !deletedIds.has(String(item.userMessage.id || "").trim()));
    const restoredMode = normalizePrivateInputAggregateMode(payload?.mode);
    const restoredPauseReason = normalizePrivateInputAggregatePauseReason(payload?.pauseReason ?? payload?.holdReason);
    const items = restoredMode === "flushing" || filteredFlushingItems.length
      ? [...filteredFlushingItems, ...filteredStoredItems]
      : filteredStoredItems;
    if (!items.length || String(payload?.windowId || "") !== historyWindowId) {
      try {
        window.localStorage.removeItem(storageKey);
      } catch {}
      return;
    }
    const mode: PrivateInputAggregateMode = filteredFlushingItems.length || restoredMode === "flushing"
      ? "paused"
      : restoredMode === "paused" || Boolean(payload?.holdUntilNextInput)
        ? "paused"
        : "armed";
    const pauseReason: PrivateInputAggregatePauseReason = mode === "paused"
      ? (filteredFlushingItems.length || restoredMode === "flushing" ? "failure" : restoredPauseReason || "cancel")
      : null;
    setPrivateInputAggregateMode(mode, pauseReason);
    privateInputAggregateDeadlineRef.current = privateInputAggregateDeadlineFromPayload(payload);
    setPrivateInputAggregateQueue(items);
    privateInputAggregateFlushingItemsRef.current = [];
    logSumiTalkClientEvent("private_input_aggregate_restore", {
      parts: items.length,
      mode,
      pauseReason,
      remainingMs: privateInputAggregateRemainingMs(),
    }, "warning");
    if (mode === "paused") {
      clearPrivateInputAggregateTimer();
      privateInputAggregateDeadlineRef.current = 0;
      setActiveSendStageLabel("等待继续输入");
    } else {
      setActiveSendStageLabel("等待继续输入");
      reschedulePrivateInputAggregateWithinDeadline();
    }
  }

  function queuedPrivateInputForMessage(messageId?: string): QueuedPrivateInput | null {
    const id = String(messageId || "").trim();
    if (!id) return null;
    return privateInputAggregateQueueRef.current.find((item) => item.userMessage.id === id) || null;
  }

  function queuedPrivateInputEditableText(item: QueuedPrivateInput | null): string {
    if (!item || item.source === "voice") return "";
    return String(item.displayContent || item.content || "").trim();
  }

  function queuedPrivateInputCanEditText(item: QueuedPrivateInput | null): boolean {
    return Boolean(item && item.source === "text" && !item.attachments.length && queuedPrivateInputEditableText(item));
  }

  function clearHeldPrivateInputAggregate(reason: string) {
    if (privateInputAggregateModeRef.current !== "paused" || !privateInputAggregateQueueRef.current.length) return;
    clearPrivateInputAggregateTimer();
    setPrivateInputAggregateQueue([]);
    privateInputAggregateFlushingItemsRef.current = [];
    setPrivateInputAggregateMode("idle");
    privateInputAggregateDeadlineRef.current = 0;
    setActiveSendStageLabel("");
    persistPrivateInputAggregate(reason);
    logSumiTalkClientEvent("private_input_aggregate_clear_held", {
      reason,
    }, "warning");
  }

  async function saveDisplayHistoryWithoutAggregateMessages(messageIds: Set<string>, source: string): Promise<ChatDraftMessage[]> {
    rememberDeletedPrivateInputMessages(messageIds, source);
    const currentMessages = filterDeletedDisplayMessages(messagesRef.current);
    const filteredCurrent = currentMessages.filter((msg) => !messageIds.has(String(msg.id || "")));
    const localDeviceId = String(deviceId || await getOrCreatePanelDeviceId()).trim();
    if (!localDeviceId || !historyWindowId) return filteredCurrent;
    const storedMessages = filterDeletedDisplayMessages(await readLocalChatHistory(localDeviceId, historyWindowId));
    const baseMessages = storedMessages.length
      ? filterDeletedDisplayMessages(mergeHistorySnapshots(storedMessages, currentMessages))
      : currentMessages;
    const filteredForStorage = baseMessages.filter((msg) => !messageIds.has(String(msg.id || "")));
    await writeLocalChatHistory(
      localDeviceId,
      historyWindowId,
      stripPreviewUrlsFromMessages(stripTransientChatDisplayParts(filteredForStorage)),
    );
    await deleteLocalChatHistoryMessages(localDeviceId, historyWindowId, [...messageIds]);
    logSumiTalkClientEvent("private_input_aggregate_history_save", {
      source,
      removed: messageIds.size,
      messages: filteredForStorage.length,
    });
    return currentMessages.length ? filteredCurrent : filteredForStorage;
  }

  function applyDisplayHistoryMessages(nextMessages: ChatDraftMessage[]) {
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
  }

  function reschedulePrivateInputAggregateAfterEdit() {
    if (!privateInputAggregateQueueRef.current.length) {
      clearPrivateInputAggregateTimer();
      setPrivateInputAggregateMode("idle");
      setActiveSendStageLabel("");
      privateInputAggregateDeadlineRef.current = 0;
      persistPrivateInputAggregate("edit_empty");
      return;
    }
    if (privateInputAggregateModeRef.current === "paused") {
      clearPrivateInputAggregateTimer();
      privateInputAggregateDeadlineRef.current = 0;
      setActiveSendStageLabel("等待继续输入");
      return;
    }
    reschedulePrivateInputAggregateWithinDeadline();
  }

  async function cancelPendingPrivateInputAggregate() {
    const queued = [...privateInputAggregateQueueRef.current];
    if (!queued.length || privateInputAggregateModeRef.current !== "armed") return;
    clearPrivateInputAggregateTimer();
    setPrivateInputAggregateMode("paused", "cancel");
    privateInputAggregateDeadlineRef.current = 0;
    setActiveSendStageLabel("等待继续输入");
    persistPrivateInputAggregate("cancel_hold");
    logSumiTalkClientEvent("private_input_aggregate_cancel_hold", { parts: queued.length }, "warning");
  }

  async function deletePendingPrivateInput(target: ChatBubbleMenuTargetBase, mode: "delete" | "edit") {
    const messageId = String(target.messageId || "").trim();
    const item = queuedPrivateInputForMessage(messageId);
    const canEditQueued = privateInputAggregateModeRef.current === "paused"
      || (privateInputAggregateModeRef.current === "armed" && privateInputAggregateRemainingMs() > 0);
    if (!item || !canEditQueued) {
      if (privateInputAggregateModeRef.current !== "paused" && privateInputAggregateRemainingMs() <= 0) {
        reschedulePrivateInputAggregateWithinDeadline();
      }
      toast("这条已经开始发送，不能改了");
      setBubbleMenu(null);
      return;
    }
    const editableText = mode === "edit" ? queuedPrivateInputEditableText(item) : "";
    if (mode === "edit" && !editableText) {
      toast("这条没有可编辑的文字");
      setBubbleMenu(null);
      return;
    }
    const messageIds = new Set([messageId]);
    const nextQueue = privateInputAggregateQueueRef.current.filter((queuedItem) => queuedItem.userMessage.id !== messageId);
    clearPrivateInputAggregateTimer();
    let nextMessages: ChatDraftMessage[];
    try {
      nextMessages = await saveDisplayHistoryWithoutAggregateMessages(
        messageIds,
        mode === "edit" ? "private_input_aggregate_edit_remove" : "private_input_aggregate_delete_one",
      );
    } catch (e: any) {
      logSumiTalkClientEvent("private_input_aggregate_delete_history_save_error", {
        mode,
        source: item.source,
        error: String(e?.message || e),
      }, "error");
      toast(`${mode === "edit" ? "编辑" : "删除"}失败：${e?.message || e}`);
      reschedulePrivateInputAggregateWithinDeadline();
      setBubbleMenu(null);
      return;
    }
    applyDisplayHistoryMessages(nextMessages);
    setPrivateInputAggregateQueue(nextQueue);
    persistPrivateInputAggregate(mode === "edit" ? "edit_remove" : "delete_one");
    reschedulePrivateInputAggregateAfterEdit();
    setBubbleMenu(null);
    if (mode === "edit") {
      setInput(editableText);
      refocusTextInputSoon();
    } else {
      toast("已删除");
    }
    logSumiTalkClientEvent(mode === "edit" ? "private_input_aggregate_edit_remove" : "private_input_aggregate_delete_one", {
      remaining: nextQueue.length,
      source: item.source,
    }, "warning");
  }

  useEffect(() => {
    restorePrivateInputAggregate();
    return () => {
      persistPrivateInputAggregate("cleanup");
      if (privateInputAggregateTimerRef.current) {
        window.clearTimeout(privateInputAggregateTimerRef.current);
        privateInputAggregateTimerRef.current = null;
      }
    };
  }, [groupChatMode, historyWindowId]);

  function toggleVoiceTranscript(item: ChatAttachment) {
    const id = chatVoiceTranscriptId(item);
    if (!id) return;
    setOpenVoiceTranscriptId((current) => (current === id ? "" : id));
  }

  function buildBubbleMenuTarget(args: {
    id: string;
    messageId?: string;
    role: ChatRole;
    content: string;
    attachments?: ChatAttachment[];
    status?: ChatDraftMessage["status"];
    operationId?: string;
  }): ChatBubbleMenuTargetBase {
    const attachments = normalizeChatAttachments(args.attachments);
    const audioAttachments = attachments.filter((item) => item.kind === "audio");
    const transcriptItem = audioAttachments.find((item) => String(item.transcript || "").trim()) || audioAttachments[0];
    const transcript = sanitizeVoiceTranscriptText(transcriptItem?.transcript || "", transcriptItem?.durationMs || 0);
    const messageId = String(args.messageId || args.id || "").trim();
    const aggregateItem = args.role === "user" && (privateInputAggregateCancelable || privateInputAggregateHeld)
      ? queuedPrivateInputForMessage(messageId)
      : null;
    const aggregateEditable = Boolean(aggregateItem && (privateInputAggregateCancelable || privateInputAggregateHeld));
    return {
      id: args.id,
      messageId,
      role: args.role,
      content: String(args.content || "").trim(),
      attachments,
      transcript,
      transcriptId: transcriptItem ? chatVoiceTranscriptId(transcriptItem) : "",
      hasVoice: audioAttachments.length > 0,
      canRetry: args.role === "assistant" && args.status === "failed" && Boolean(String(args.operationId || "").trim()),
      aggregateEditable,
      aggregateCanEditText: aggregateEditable && queuedPrivateInputCanEditText(aggregateItem),
      operationId: String(args.operationId || "").trim() || undefined,
      status: args.status,
    };
  }

  function clearBubbleLongPressTimer() {
    const state = bubbleTouchRef.current;
    if (!state?.timer) return;
    window.clearTimeout(state.timer);
    state.timer = 0;
  }

  function openBubbleMenuAt(target: ChatBubbleMenuTargetBase, clientX: number, clientY: number) {
    const itemCount = 2
      + (target.hasVoice ? 1 : 0)
      + (target.canRetry ? 1 : 0)
      + (target.aggregateEditable ? 1 : 0)
      + (target.aggregateCanEditText ? 1 : 0);
    const columns = Math.min(3, Math.max(1, itemCount));
    const rows = Math.ceil(itemCount / columns);
    const width = Math.min(window.innerWidth - 20, Math.max(156, columns * 68));
    const height = rows * 44 + 16;
    const left = Math.max(10, Math.min(clientX - width / 2, window.innerWidth - width - 10));
    const preferredTop = clientY - height - 14;
    const top = preferredTop < 70 ? Math.min(clientY + 14, window.innerHeight - height - 10) : preferredTop;
    setBubbleMenu({ ...target, x: left, y: top });
  }

  function handleBubbleContextMenu(event: React.MouseEvent<HTMLDivElement>, target: ChatBubbleMenuTargetBase) {
    event.preventDefault();
    event.stopPropagation();
    openBubbleMenuAt(target, event.clientX, event.clientY);
  }

  function handleBubbleTouchStart(event: React.TouchEvent<HTMLDivElement>, target: ChatBubbleMenuTargetBase) {
    if (event.touches.length !== 1) return;
    clearBubbleLongPressTimer();
    const touch = event.touches[0];
    const state: ChatBubbleTouchState = {
      target,
      startX: touch.clientX,
      startY: touch.clientY,
      currentX: touch.clientX,
      currentY: touch.clientY,
      timer: 0,
      menuOpened: false,
    };
    state.timer = window.setTimeout(() => {
      const current = bubbleTouchRef.current;
      if (!current) return;
      current.menuOpened = true;
      openBubbleMenuAt(current.target, current.startX, current.startY);
    }, 520);
    bubbleTouchRef.current = state;
  }

  function handleBubbleTouchMove(event: React.TouchEvent<HTMLDivElement>) {
    const state = bubbleTouchRef.current;
    if (!state || event.touches.length !== 1) return;
    const touch = event.touches[0];
    state.currentX = touch.clientX;
    state.currentY = touch.clientY;
    if (Math.abs(state.currentX - state.startX) > 10 || Math.abs(state.currentY - state.startY) > 10) {
      clearBubbleLongPressTimer();
    }
  }

  function quoteBubbleTarget(target: ChatBubbleMenuTargetBase) {
    const text = bubbleTargetText(target);
    if (!text) return;
    setQuotedBubble({
      role: target.role,
      roleLabel: chatRoleQuoteLabel(target.role),
      text,
    });
    setBubbleMenu(null);
  }

  function handleBubbleTouchEnd() {
    const state = bubbleTouchRef.current;
    if (!state) return;
    clearBubbleLongPressTimer();
    bubbleTouchRef.current = null;
    if (state.menuOpened) return;
    const dx = state.currentX - state.startX;
    const dy = state.currentY - state.startY;
    if (dx < -46 && Math.abs(dy) < 36) {
      quoteBubbleTarget(state.target);
    }
  }

  function copyBubbleTarget(target: ChatBubbleMenuTargetBase) {
    const text = bubbleTargetText(target);
    if (!text) {
      toast("这条没什么可复制的");
      setBubbleMenu(null);
      return;
    }
    copyText(text, toast);
    setBubbleMenu(null);
  }

  function revealBubbleTranscript(target: ChatBubbleMenuTargetBase) {
    if (!target.hasVoice) return;
    if (!target.transcript || !target.transcriptId) {
      toast("这条语音还没有转文字");
      setBubbleMenu(null);
      return;
    }
    setOpenVoiceTranscriptId((current) => (current === target.transcriptId ? "" : target.transcriptId));
    setBubbleMenu(null);
  }

  function retryBubbleTarget(target: ChatBubbleMenuTargetBase) {
    if (!target.canRetry || !target.operationId) {
      toast("这条消息不能重试");
      setBubbleMenu(null);
      return;
    }
    setBubbleMenu(null);
    void retrySumiTalkOperation(target.operationId);
  }

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    return () => {
      try {
        if (chatVoiceRecorderRef.current && chatVoiceRecorderRef.current.state !== "inactive") {
          chatVoiceRecorderRef.current.stop();
        }
      } catch {}
      chatVoiceRecorderRef.current = null;
      chatVoiceChunksRef.current = [];
      clearBubbleLongPressTimer();
      if (chatVoiceStreamRef.current) {
        chatVoiceStreamRef.current.getTracks().forEach((track) => track.stop());
        chatVoiceStreamRef.current = null;
      }
    };
  }, []);

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
          try {
            await migrateLocalChatHistoriesToDevice(did);
          } catch (e: any) {
            logSumiTalkClientEvent("chat_local_history_migration_error", {
              source: "device_id_sync_all",
              targetDeviceId: did,
              error: String(e?.message || e),
            }, "warning");
          }
          if (migration?.from && migration.to === did) {
            try {
              await migrateLocalChatHistoryDevice(migration.from, migration.to);
            } catch (e: any) {
              logSumiTalkClientEvent("chat_local_history_migration_error", {
                source: "device_id_sync",
                fromDeviceId: migration.from,
                toDeviceId: migration.to,
                error: String(e?.message || e),
              }, "warning");
            }
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
        try {
          await migrateLocalChatHistoriesToDevice(resolvedDeviceId);
        } catch (e: any) {
          logSumiTalkClientEvent("chat_local_history_migration_error", {
            source: "history_load",
            targetDeviceId: resolvedDeviceId,
            error: String(e?.message || e),
          }, "warning");
        }
        privateInputAggregateDeletedMessageIdsRef.current = loadPrivateInputAggregateDeletedMessageIds();
        const localMessages = filterDeletedDisplayMessages(await readLocalChatHistory(resolvedDeviceId, historyWindowId));
        const localRecoveryWindowIds = groupChatMode
          ? uniqueNonEmptyStrings([historyWindowId, displayHistoryWindowId, windowId])
          : uniqueNonEmptyStrings([historyWindowId, displayHistoryWindowId, windowId, MAIN_SUMITALK_DISPLAY_WINDOW_ID]);
        const localCandidateRows = await readLocalChatHistoryRows(localRecoveryWindowIds);
        const localCandidateMessages = localCandidateRows.reduce(
          (best, row) => {
            const rowMessages = filterDeletedDisplayMessages((row?.messages || []) as ChatDraftMessage[]);
            return pickBetterHistory(rowMessages, best, []);
          },
          [] as ChatDraftMessage[],
        );
        const legacyLocalGroups = [];
        if (!groupChatMode && windowId && windowId !== historyWindowId) {
          legacyLocalGroups.push(filterDeletedDisplayMessages(await readLocalChatHistory(resolvedDeviceId, windowId)));
        }
        if (!groupChatMode && historyWindowId !== MAIN_SUMITALK_DISPLAY_WINDOW_ID) {
          legacyLocalGroups.push(filterDeletedDisplayMessages(await readLocalChatHistory(resolvedDeviceId, MAIN_SUMITALK_DISPLAY_WINDOW_ID)));
        }
        const legacyLocalMessages = legacyLocalGroups.reduce(
          (best, item) => pickBetterHistory(item, best, []),
          [] as ChatDraftMessage[],
        );
        const recoveredLocalMessages = pickBetterHistory(localCandidateMessages, localMessages, []);
        const fallbackLocalMessages = pickBetterHistory(recoveredLocalMessages, legacyLocalMessages, []);
        if (!cancelled && fallbackLocalMessages.length) {
          const nextLocalMessages = filterDeletedDisplayMessages(mergeHistorySnapshots(fallbackLocalMessages, messagesRef.current));
          messagesRef.current = nextLocalMessages;
          setMessages(nextLocalMessages);
          await saveDisplayHistory(nextLocalMessages, {
            localDeviceId: resolvedDeviceId,
            source: "history_local_recovery",
          });
        }
        if (!cancelled) {
          void recoverActiveSumiTalkOperations(resolvedDeviceId);
        }
        let remoteMessages: ChatDraftMessage[] = [];
        try {
          const j = await apiJson<{ ok?: boolean; messages?: ChatDraftMessage[] }>(sumitalkHistoryPath(remoteHistoryWindowId));
          remoteMessages = filterDeletedDisplayMessages(Array.isArray(j?.messages) ? j.messages : []);
        } catch (e: any) {
          logSumiTalkClientEvent("chat_remote_history_load_error", {
            error: String(e?.message || e),
          }, "warning");
        }
        if (cancelled) return;
        const preferredSnapshot = pickBetterHistory(remoteMessages, fallbackLocalMessages, seedMessages);
        const next = filterDeletedDisplayMessages(mergeHistorySnapshots(preferredSnapshot, messagesRef.current));
        messagesRef.current = next;
        setMessages(next);
        if (hasNonSeedHistoryMessages(next)) {
          await saveDisplayHistory(next, {
            localDeviceId: resolvedDeviceId,
            source: "history_remote_merge",
          });
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

  useEffect(() => {
    if (!historyWindowId) return;
    let cancelled = false;
    const recover = (source: string) => {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      void recoverSumiTalkBackendState(source);
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") recover("visibility_visible");
    };
    const onFocus = () => recover("window_focus");
    const onPageShow = () => recover("page_show");
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", onFocus);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [deviceId, historyWindowId, remoteHistoryWindowId, groupChatMode]);

  async function saveDisplayHistory(
    nextMessages: ChatDraftMessage[],
    options: { localDeviceId?: string; strict?: boolean; source?: string } = {},
  ) {
    const sanitizedMessages = stripPreviewUrlsFromMessages(stripTransientChatDisplayParts(filterDeletedDisplayMessages(nextMessages)));
    const resolvedDeviceId = String(options.localDeviceId || deviceId || "").trim();
    if (resolvedDeviceId && historyWindowId) {
      try {
        await writeLocalChatHistory(resolvedDeviceId, historyWindowId, sanitizedMessages);
      } catch (e: any) {
        logSumiTalkClientEvent("chat_local_history_write_error", {
          source: options.source || "saveDisplayHistory",
          error: String(e?.message || e),
          messages: sanitizedMessages.length,
          targetDeviceId: resolvedDeviceId,
        }, "error");
        if (options.strict) throw e;
      }
    }
  }

  function saveDisplayHistoryInBackground(
    nextMessages: ChatDraftMessage[],
    options: { localDeviceId?: string } = {},
  ) {
    void saveDisplayHistory(nextMessages, { localDeviceId: options.localDeviceId }).catch(() => {});
  }

  async function mergeRemoteDisplayHistory(localDeviceId: string, source: string) {
    const did = String(localDeviceId || deviceId || "").trim();
    if (!did || !remoteHistoryWindowId || remoteHistorySyncingRef.current) return;
    remoteHistorySyncingRef.current = true;
    try {
      const j = await apiJson<{ ok?: boolean; messages?: ChatDraftMessage[] }>(sumitalkHistoryPath(remoteHistoryWindowId));
      const remoteMessages = filterDeletedDisplayMessages(Array.isArray(j?.messages) ? j.messages : []);
      if (!remoteMessages.length) return;
      const current = filterDeletedDisplayMessages(messagesRef.current);
      const beforeSignature = historySnapshotSignature(current);
      const preferredSnapshot = pickBetterHistory(remoteMessages, current, seedMessages);
      const next = filterDeletedDisplayMessages(mergeHistorySnapshots(preferredSnapshot, current));
      if (historySnapshotSignature(next) === beforeSignature) return;
      messagesRef.current = next;
      setMessages(next);
      if (hasNonSeedHistoryMessages(next)) {
        await saveDisplayHistory(next, {
          localDeviceId: did,
          source,
        });
      }
      logSumiTalkClientEvent("chat_remote_history_resync_ok", {
        source,
        remoteMessages: remoteMessages.length,
        mergedMessages: next.length,
      });
    } catch (e: any) {
      logSumiTalkClientEvent("chat_remote_history_resync_error", {
        source,
        error: String(e?.message || e),
      }, "warning");
    } finally {
      remoteHistorySyncingRef.current = false;
    }
  }

  async function recoverSumiTalkBackendState(source: string, localDeviceId?: string) {
    const resolvedDeviceId = String(localDeviceId || deviceId || await getOrCreatePanelDeviceId()).trim();
    if (!resolvedDeviceId) return;
    if (!deviceId) setDeviceId(resolvedDeviceId);
    void recoverActiveSumiTalkOperations(resolvedDeviceId);
    void mergeRemoteDisplayHistory(resolvedDeviceId, source);
  }

  function logSumiTalkClientEvent(
    event: string,
    fields: Record<string, string | number | boolean | undefined | null> = {},
    level: "info" | "warning" | "error" = "info",
  ) {
    const safeFields = {
      windowId,
      displayWindowId: remoteHistoryWindowId,
      historyWindowId,
      groupChatMode,
      deviceId,
      ...fields,
    };
    void apiJson("/miniapp-api/logs/client", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level, event, fields: safeFields }),
    }).catch(() => {});
  }

  function logSumiTalkSendStage(
    event: string,
    fields: Record<string, string | number | boolean | undefined | null> = {},
    level: "info" | "warning" | "error" = "info",
  ) {
    const label = resolveChatSendStageLabel(event, fields);
    if (label) setActiveSendStageLabel(label);
    logSumiTalkClientEvent(event, fields, level);
  }

  async function recordChatOperationError(operation: string, action: () => Promise<void>, fields: Record<string, string | number | boolean | undefined | null> = {}) {
    try {
      await action();
    } catch (e: any) {
      logSumiTalkClientEvent("chat_local_operation_write_error", {
        operation,
        error: String(e?.message || e),
        ...fields,
      }, "error");
    }
  }

  async function attachChatJobBestEffort(operationId: string, jobId: string) {
    await recordChatOperationError(
      "attachChatJobToOperation",
      () => attachChatJobToOperation(operationId, jobId),
      { operationId, jobId },
    );
  }

  async function completeChatOperationBestEffort(operationId: string, assistantMessage: ChatDraftMessage) {
    await recordChatOperationError(
      "completeChatOperation",
      () => completeChatOperation(operationId, assistantMessage),
      { operationId, assistantMessageId: assistantMessage.id },
    );
  }

  async function failChatOperationBestEffort(operationId: string, error: string, assistantMessage?: ChatDraftMessage) {
    await recordChatOperationError(
      "failChatOperation",
      () => failChatOperation(operationId, error, assistantMessage),
      { operationId, assistantMessageId: assistantMessage?.id },
    );
  }

  async function persistSumiTalkOperationMessages(nextMessages: ChatDraftMessage[], localDeviceId: string) {
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    if (groupChatMode) {
      await saveDisplayHistory(nextMessages, { localDeviceId });
      saveDisplayHistoryInBackground(nextMessages, { localDeviceId });
    } else {
      await saveDisplayHistory(nextMessages, { localDeviceId });
    }
  }

  async function recoverSumiTalkOperation(
    operation: ChatOperation,
    localDeviceId: string,
    options: { forceCreateJob?: boolean } = {},
  ) {
    const opId = String(operation?.id || "").trim();
    if (!opId || sumitalkOperationRecoveringRef.current.has(opId)) return;
    sumitalkOperationRecoveringRef.current.add(opId);
    try {
      await recoverSumiTalkOperationFlow({
        operation,
        localDeviceId,
        forceCreateJob: Boolean(options.forceCreateJob),
        getMessages: () => messagesRef.current,
        persistMessages: persistSumiTalkOperationMessages,
        attachJob: attachChatJobBestEffort,
        completeOperation: completeChatOperationBestEffort,
        failOperation: failChatOperationBestEffort,
        appendVoiceOutputAudio: (voiceOutput) => {
          void appendAssistantVoiceOutputAudio(voiceOutput);
        },
        logEvent: logSumiTalkSendStage,
      });
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
      // Recovery is authorized by operationId/clientRequestId, not by a foreground attempt.
      // Do not gate this path with isCurrentAttempt; there may be no active UI send after reload/background.
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
        jobId: undefined,
        displayParts: [],
      });
      messagesRef.current = pending;
      setMessages(pending);
      await saveDisplayHistory(pending, { localDeviceId });
    }
    clearHeldPrivateInputAggregate("retry_failed_operation");
    void recoverSumiTalkOperation(operation, localDeviceId, { forceCreateJob: true });
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
      await saveDisplayHistory(nextMessages, { localDeviceId: options.localDeviceId || deviceId });
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

  function applyStreamingSumiTalkChatEvent(event: SumiTalkChatRealtimeEvent): boolean {
    const eventWindowId = String(event?.window_id || (event as any)?.windowId || "").trim();
    const allowedWindowIds = uniqueNonEmptyStrings([
      String(windowId || "__default__").trim() || "__default__",
      historyWindowId,
      remoteHistoryWindowId,
    ]);
    if (eventWindowId && allowedWindowIds.length && !allowedWindowIds.includes(eventWindowId)) return false;
    const current = messagesRef.current;
    const beforeSignature = historySnapshotSignature(current);
    const nextMessages = applySumiTalkChatEventToMessages(current, event);
    if (historySnapshotSignature(nextMessages) === beforeSignature) return false;
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    if (realModeEnabledRef.current) void refreshRealBodyStatus();
    return true;
  }

  useSumiTalkChatRealtime({
    enabled: Boolean(deviceId),
    deviceId,
    windowId: String(windowId || "__default__").trim() || "__default__",
    onEvent: (event: SumiTalkChatRealtimeEvent) => {
      applyStreamingSumiTalkChatEvent(event);
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
    await saveDisplayHistory(pendingMessages, { localDeviceId: params.replyTarget });
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
          await saveDisplayHistory(retryMessages, { localDeviceId: params.replyTarget });
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
      await saveDisplayHistory(queuedMessages, { localDeviceId: params.replyTarget });
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
      await saveDisplayHistory(failedMessages, { localDeviceId: params.replyTarget });
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
      await saveDisplayHistory(idleMessages, { localDeviceId });
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
    await saveDisplayHistory(markedMessages, { localDeviceId });

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
        await saveDisplayHistory(failedMessages, { localDeviceId });
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
    await saveDisplayHistory(pendingMessages, { localDeviceId: params.replyTarget });
    try {
      const result = await runGroupDuReplyFlow({
        source: "group_discussion",
        requestPath: "/miniapp-api/sumitalk-chat-jobs",
        requestBody: buildGroupChatRequestBody({
          model: activeModel,
          userContent: buildGroupDiscussionUserContent(
            messagesRef.current,
            params.topic,
            params.turnIndex,
            params.maxTurns,
          ),
          windowId,
          replyTarget: params.replyTarget,
          clientRequestId,
        }),
        clientRequestId,
        assistantId,
        assistantCreatedAt,
        logEvent: logSumiTalkSendStage,
        onEvent: (event) => {
          applyStreamingSumiTalkChatEvent(event);
        },
      });
      if (!result) return "";
      const finalMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, result.assistantMessage);
      messagesRef.current = finalMessages;
      setMessages(finalMessages);
      await saveDisplayHistory(finalMessages, { localDeviceId: params.replyTarget });
      saveDisplayHistoryInBackground(finalMessages, { localDeviceId: params.replyTarget });
      if (result.voiceText) {
        void appendAssistantVoiceOutputAudio({
          assistantId,
          clientRequestId,
          operationId: "",
          jobId: result.jobId,
          voiceText: result.voiceText,
          localDeviceId: params.replyTarget,
        });
      }
      return result.reply || result.voiceText;
    } catch (e: any) {
      const failedMessages = applyAssistantTerminalMessage(
        messagesRef.current,
        clientRequestId,
        buildGroupAssistantFailureMessage({
          assistantId,
          assistantCreatedAt,
          clientRequestId,
          error: e,
          prefix: "渡接力失败",
        }),
      );
      messagesRef.current = failedMessages;
      setMessages(failedMessages);
      await saveDisplayHistory(failedMessages, { localDeviceId: params.replyTarget });
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
        setActiveSendStageLabel("");
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
        setActiveSendStageLabel("");
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
          await saveDisplayHistory(failedMessages, { localDeviceId: deviceId });
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
    await saveDisplayHistory(nextMessages, { localDeviceId });
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
    await saveDisplayHistory(nextMessages, { localDeviceId });
    saveDisplayHistoryInBackground(nextMessages, { localDeviceId });
  }

  async function appendAssistantVoiceOutputAudio(args: {
    assistantId: string;
    clientRequestId: string;
    operationId: string;
    jobId: string;
    voiceText: string;
    localDeviceId: string;
  }) {
    const voiceText = String(args.voiceText || "").trim();
    if (!voiceText) return;
    const isCurrentAssistantTarget = (message: ChatDraftMessage | undefined): message is ChatDraftMessage => Boolean(
      message
      && message.role === "assistant"
      && message.id === args.assistantId
      && message.clientRequestId === args.clientRequestId
      && (!args.operationId || message.operationId === args.operationId)
      && message.status === "sent",
    );
    const initialTarget = messagesRef.current.find((msg) => msg.id === args.assistantId);
    if (!isCurrentAssistantTarget(initialTarget)) {
      logSumiTalkClientEvent("assistant_voice_tts_skip", {
        clientRequestId: args.clientRequestId,
        operationId: args.operationId,
        jobId: args.jobId,
        reason: "stale_target_before_tts",
      }, "warning");
      return;
    }
    logSumiTalkClientEvent("assistant_voice_tts_start", {
      clientRequestId: args.clientRequestId,
      operationId: args.operationId,
      jobId: args.jobId,
      voiceChars: voiceText.length,
    });
    try {
      const attachment = await createDuReplyAudio(voiceText);
      if (!attachment) return;
      const current = messagesRef.current.find((msg) => msg.id === args.assistantId);
      if (!isCurrentAssistantTarget(current)) {
        logSumiTalkClientEvent("assistant_voice_tts_skip", {
          clientRequestId: args.clientRequestId,
          operationId: args.operationId,
          jobId: args.jobId,
          reason: "stale_target_after_tts",
        }, "warning");
        return;
      }
      const nextMessage: ChatDraftMessage = {
        ...current,
        attachments: normalizeChatAttachments([
          ...(current.attachments || []),
          { ...attachment, transcript: voiceText },
        ]),
      };
      const nextMessages = applyMessageById(messagesRef.current, args.assistantId, nextMessage);
      messagesRef.current = nextMessages;
      setMessages(nextMessages);
      await saveDisplayHistory(nextMessages, { localDeviceId: args.localDeviceId });
      if (args.operationId) {
        await completeChatOperationBestEffort(args.operationId, nextMessage);
      }
      logSumiTalkClientEvent("assistant_voice_tts_ok", {
        clientRequestId: args.clientRequestId,
        operationId: args.operationId,
        jobId: args.jobId,
        bytes: attachment.size || 0,
        mime: attachment.mime || "",
      });
    } catch (e: any) {
      logSumiTalkClientEvent("assistant_voice_tts_error", {
        clientRequestId: args.clientRequestId,
        operationId: args.operationId,
        jobId: args.jobId,
        error: String(e?.message || e),
      }, "warning");
    }
  }

  function shouldAggregatePrivateInput(source: ChatSendSource): boolean {
    return !groupChatMode && source !== "retry" && source !== "travel_form" && source !== "group_command";
  }

  function schedulePrivateInputAggregateFlush(
    delayMs = SUMITALK_PRIVATE_INPUT_IDLE_MS,
    reason: "idle" | "busy_retry" = "idle",
  ) {
    if (!privateInputAggregateQueueRef.current.length || privateInputAggregateModeRef.current === "paused") return;
    setPrivateInputAggregateMode("armed");
    if (privateInputAggregateTimerRef.current) {
      window.clearTimeout(privateInputAggregateTimerRef.current);
      privateInputAggregateTimerRef.current = null;
    }
    const version = privateInputAggregateVersionRef.current + 1;
    privateInputAggregateVersionRef.current = version;
    privateInputAggregateTimerRef.current = window.setTimeout(() => {
      void flushPrivateInputAggregate(version);
    }, delayMs);
    logSumiTalkClientEvent("private_input_aggregate_schedule", {
      parts: privateInputAggregateQueueRef.current.length,
      delayMs,
      reason,
      version,
    });
  }

  async function enqueuePrivateInputAggregate(
    rawContent: string,
    options: { displayContent?: string; attachments?: ChatAttachment[]; source?: ChatSendSource; modelContent?: PrivateModelContent } = {},
  ): Promise<boolean> {
    const content = String(rawContent || "").trim();
    const attachments = normalizeChatAttachments(options.attachments);
    const source: ChatSendSource = options.source
      || (attachments.some((item) => item.kind === "audio") ? "voice" : attachments.some((item) => item.kind === "image") ? "image" : attachments.some((item) => item.kind === "document") ? "document" : "text");
    if (!content && !attachments.length) {
      logSumiTalkClientEvent("private_input_aggregate_skip", { source, reason: "empty" }, "warning");
      return false;
    }
    if (!windowId) {
      logSumiTalkClientEvent("private_input_aggregate_skip", { source, reason: "missing_window_id" }, "warning");
      toast("当前还没拿到聊天窗口 ID，不能接入共享上下文");
      return false;
    }
    if (!activeModel) {
      logSumiTalkClientEvent("private_input_aggregate_skip", { source, reason: "missing_model" }, "warning");
      toast("当前还没拿到可用模型，稍后再试");
      return false;
    }
    const resolvedDeviceId = String(deviceId || await getOrCreatePanelDeviceId()).trim();
    if (resolvedDeviceId && resolvedDeviceId !== deviceId) {
      setDeviceId((prev) => (prev === resolvedDeviceId ? prev : resolvedDeviceId));
    }
    const pendingBefore = privateInputAggregateQueueRef.current.length;
    if (privateInputAggregateModeRef.current === "paused") {
      const queuedSource = resolveAggregateSource(privateInputAggregateQueueRef.current);
      const pauseReason = privateInputAggregatePauseReasonRef.current;
      if (pauseReason === "failure"
        && shouldDropPrivateAggregateAfterFailure(queuedSource, privateInputAggregateQueueRef.current, messagesRef.current)) {
        setPrivateInputAggregateQueue([]);
        setPrivateInputAggregateMode("idle");
        privateInputAggregateDeadlineRef.current = 0;
        persistPrivateInputAggregate("drop_image_too_large_before_resume");
        logSumiTalkClientEvent("private_input_aggregate_drop_image_too_large_before_resume", {
          pendingBefore,
          source,
        }, "warning");
      } else {
        setPrivateInputAggregateMode("armed");
        logSumiTalkClientEvent("private_input_aggregate_resume_after_pause", {
          pendingBefore,
          source,
          pauseReason,
        }, "warning");
      }
    }
    const baseTimestamp = Date.now();
    const displayContent = String(options.displayContent ?? content).trim();
    const userMessage: ChatDraftMessage = {
      id: `user-${baseTimestamp}-${Math.random().toString(36).slice(2, 7)}`,
      role: "user",
      content: displayContent,
      createdAt: new Date(baseTimestamp).toISOString(),
      status: "sent",
      ...(attachments.length ? { attachments } : {}),
    };
    const previousMessages = messagesRef.current;
    const nextMessages = [...messagesRef.current, userMessage];
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    setInput("");
    setPlusOpen(false);
    if (source === "text") refocusTextInputSoon();
    try {
      await saveDisplayHistory(nextMessages, {
        localDeviceId: resolvedDeviceId,
        strict: true,
        source: "private_input_aggregate_append",
      });
    } catch (e: any) {
      messagesRef.current = previousMessages;
      setMessages(previousMessages);
      if (displayContent) {
        setInput((current) => current || displayContent);
        refocusTextInputSoon();
      }
      logSumiTalkClientEvent("private_input_aggregate_append_error", {
        source,
        error: String(e?.message || e),
      }, "error");
      toast(`消息暂存失败：${e?.message || e}`);
      return false;
    }
    const queuedItem: QueuedPrivateInput = {
      content,
      displayContent,
      attachments,
      source,
      modelContent: options.modelContent ?? buildPrivateUserContent(content, attachments),
      userMessage,
    };
    const currentQueue = privateInputAggregateQueueRef.current;
    const shouldPrependRealText = realModeEnabledRef.current
      && source === "text"
      && !attachments.length
      && currentQueue.length > 0
      && currentQueue.some((item) => item.attachments.length > 0)
      && !currentQueue.some((item) => item.source === "text" && !item.attachments.length);
    setPrivateInputAggregateQueue(shouldPrependRealText ? [queuedItem, ...currentQueue] : [...currentQueue, queuedItem]);
    privateInputAggregateDeadlineRef.current = Date.now() + SUMITALK_PRIVATE_INPUT_IDLE_MS;
    setPrivateInputAggregateMode("armed");
    persistPrivateInputAggregate("enqueue");
    if (sendingRef.current) {
      logSumiTalkClientEvent("private_input_aggregate_enqueue_while_busy", {
        pendingBefore,
        source,
      }, "warning");
    }
    setActiveSendStageLabel("等待继续输入");
    schedulePrivateInputAggregateFlush();
    return true;
  }

  async function flushPrivateInputAggregate(expectedVersion: number) {
    if (expectedVersion !== privateInputAggregateVersionRef.current) return;
    if (!privateInputAggregateQueueRef.current.length) return;
    if (privateInputAggregateModeRef.current === "paused") return;
    if (sendingRef.current) {
      logSumiTalkClientEvent("private_input_aggregate_wait_busy", {
        parts: privateInputAggregateQueueRef.current.length,
      }, "warning");
      schedulePrivateInputAggregateFlush(SUMITALK_PRIVATE_INPUT_BUSY_RETRY_MS, "busy_retry");
      return;
    }
    if (mediaBusyRef.current || recordingChatVoiceRef.current || chatVoicePressingRef.current) {
      logSumiTalkClientEvent("private_input_aggregate_wait_media", {
        parts: privateInputAggregateQueueRef.current.length,
        mediaBusy: mediaBusyRef.current,
        recordingVoice: recordingChatVoiceRef.current,
        pressingVoice: chatVoicePressingRef.current,
      }, "warning");
      schedulePrivateInputAggregateFlush(SUMITALK_PRIVATE_INPUT_BUSY_RETRY_MS, "busy_retry");
      return;
    }
    const rawQueued = privateInputAggregateQueueRef.current;
    setPrivateInputAggregateQueue([]);
    privateInputAggregateFlushingItemsRef.current = rawQueued;
    setPrivateInputAggregateMode("flushing");
    privateInputAggregateDeadlineRef.current = 0;
    if (privateInputAggregateTimerRef.current) {
      window.clearTimeout(privateInputAggregateTimerRef.current);
      privateInputAggregateTimerRef.current = null;
    }
    persistPrivateInputAggregate("flush_start");
    if (!rawQueued.length) return;
    let queued: QueuedPrivateInput[];
    try {
      queued = await Promise.all(rawQueued.map(compressQueuedPrivateInputImages));
    } catch (e: any) {
      privateInputAggregateFlushingItemsRef.current = [];
      setPrivateInputAggregateQueue([...rawQueued, ...privateInputAggregateQueueRef.current]);
      setPrivateInputAggregateMode("paused", "failure");
      privateInputAggregateDeadlineRef.current = 0;
      setActiveSendStageLabel("等待继续输入");
      persistPrivateInputAggregate("hold_after_prepare_error");
      logSumiTalkClientEvent("private_input_aggregate_hold_after_prepare_error", {
        parts: rawQueued.length,
        pending: privateInputAggregateQueueRef.current.length,
        error: String(e?.message || e),
      }, "error");
      toast(`消息准备失败：${e?.message || e}，下一条会一起重试`);
      return;
    }
    const content = queued.map((item) => item.content).filter(Boolean).join("\n").trim();
    const attachments = queued.flatMap((item) => item.attachments);
    const source = resolveAggregateSource(queued);
    const modelContent = mergePrivateModelContents(queued.map((item) => item.modelContent));
    setActiveSendStageLabel("");
    logSumiTalkClientEvent("private_input_aggregate_flush", {
      parts: queued.length,
      contentChars: content.length,
      attachments: attachments.length,
      source,
    });
    const ok = await sendChatContentNow(content, {
      displayContent: content,
      attachments,
      source,
      modelContent,
      aggregateUserMessages: queued.map((item) => item.userMessage),
    });
    privateInputAggregateFlushingItemsRef.current = [];
    if (!ok) {
      if (shouldDropPrivateAggregateAfterFailure(source, queued, messagesRef.current)) {
        if (!privateInputAggregateQueueRef.current.length) {
          setPrivateInputAggregateMode("idle");
          privateInputAggregateDeadlineRef.current = 0;
          setActiveSendStageLabel("");
        }
        persistPrivateInputAggregate("drop_image_too_large");
        logSumiTalkClientEvent("private_input_aggregate_drop_image_too_large", {
          parts: queued.length,
          source,
        }, "warning");
      } else {
        setPrivateInputAggregateQueue([...queued, ...privateInputAggregateQueueRef.current]);
        setPrivateInputAggregateMode("paused", "failure");
        privateInputAggregateDeadlineRef.current = 0;
        setActiveSendStageLabel("等待继续输入");
        persistPrivateInputAggregate("hold_after_failure");
        logSumiTalkClientEvent("private_input_aggregate_hold_after_failure", {
          parts: queued.length,
          pending: privateInputAggregateQueueRef.current.length,
          source,
        }, "warning");
      }
    } else {
      if (!privateInputAggregateQueueRef.current.length) {
        setPrivateInputAggregateMode("idle");
        privateInputAggregateDeadlineRef.current = 0;
        setActiveSendStageLabel("");
      } else if (privateInputAggregateModeRef.current === "flushing") {
        privateInputAggregateDeadlineRef.current = Date.now() + SUMITALK_PRIVATE_INPUT_IDLE_MS;
        setPrivateInputAggregateMode("armed");
        setActiveSendStageLabel("等待继续输入");
        schedulePrivateInputAggregateFlush();
      }
      persistPrivateInputAggregate("flush_ok");
    }
  }

  async function sendChatContent(
    rawContent: string,
    options: { displayContent?: string; attachments?: ChatAttachment[]; source?: ChatSendSource; modelContent?: PrivateModelContent } = {},
  ): Promise<boolean> {
    const attachments = normalizeChatAttachments(options.attachments);
    const source: ChatSendSource = options.source
      || (attachments.some((item) => item.kind === "audio") ? "voice" : attachments.some((item) => item.kind === "image") ? "image" : attachments.some((item) => item.kind === "document") ? "document" : "text");
    if (shouldAggregatePrivateInput(source)) {
      return enqueuePrivateInputAggregate(rawContent, { ...options, attachments, source });
    }
    return sendChatContentNow(rawContent, { ...options, attachments, source });
  }

  async function sendChatContentNow(
    rawContent: string,
    options: { displayContent?: string; attachments?: ChatAttachment[]; source?: ChatSendSource; modelContent?: PrivateModelContent; aggregateUserMessages?: ChatDraftMessage[] } = {},
  ): Promise<boolean> {
    const content = String(rawContent || "").trim();
    const attachments = normalizeChatAttachments(options.attachments);
    const source: ChatSendSource = options.source
      || (attachments.some((item) => item.kind === "audio") ? "voice" : attachments.some((item) => item.kind === "image") ? "image" : attachments.some((item) => item.kind === "document") ? "document" : "text");
    const aggregateUserMessages = !groupChatMode
      ? (Array.isArray(options.aggregateUserMessages) ? options.aggregateUserMessages : [])
        .filter((message) => message?.role === "user" && String(message.id || "").trim())
      : [];
    const useAggregateUserMessages = aggregateUserMessages.length > 0;
    const effectiveContent = contentWithAttachmentHint(content, attachments);
    const canSendWhileBusy = groupChatMode && (
      isBenbenCancelCommand(content)
      || (groupDiscussionRunning && isGroupDiscussionStopCommand(content))
      || isGroupDiscussionContinueCommand(content)
    );
    if (!content && !attachments.length) {
      logSumiTalkClientEvent("chat_send_skipped", { source, reason: "empty" }, "warning");
      return false;
    }
    if (sendingRef.current && !canSendWhileBusy) {
      logSumiTalkClientEvent("chat_send_skipped", { source, reason: "busy" }, "warning");
      return false;
    }
    const displayContent = String(options.displayContent ?? content).trim();
    if (!windowId) {
      logSumiTalkClientEvent("chat_send_skipped", { source, reason: "missing_window_id" }, "warning");
      toast("当前还没拿到聊天窗口 ID，不能接入共享上下文");
      return false;
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
      return true;
    }
    if (groupChatMode && isGroupDiscussionContinueCommand(content)) {
      await appendGroupUserMessage(displayContent, resolvedDeviceId);
      const snapshot = groupDiscussionSnapshotRef.current;
      if (!snapshot?.lastContent) {
        toast("还没有可继续的群聊讨论");
        return false;
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
      return true;
    }
    const groupTargets = groupChatMode
      ? resolveEffectiveGroupReplyTargets(content, groupFreeChatEnabled)
      : { du: true, benben: false, mentions: [], benbenMode: "daily_chat" as const, codingThreadKey: "", freeDiscussion: false };
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
      logSumiTalkClientEvent("chat_send_skipped", { source, reason: "missing_model" }, "warning");
      toast("当前还没拿到可用模型，稍后再试");
      return false;
    }
    const baseTimestamp = Date.now();
    const clientRequestId = `sumitalk-${baseTimestamp}-${Math.random().toString(36).slice(2, 10)}`;
    const operationId = shouldRequestDu ? `op-${clientRequestId}` : "";
    const isPrivateDuAttempt = shouldRequestDu && !groupChatMode;
    const attemptId = shouldRequestDu ? makeChatAttemptId(clientRequestId) : "";
    const isCurrentAttempt = () => !isPrivateDuAttempt || (
      activeChatRequestRef.current?.clientRequestId === clientRequestId
      && activeChatRequestRef.current?.attemptId === attemptId
    );
    const skipStaleAttemptUpdate = (stage: string) => {
      if (isCurrentAttempt()) return false;
      logSumiTalkClientEvent("chat_attempt_stale_skip", {
        source,
        stage,
        attemptId,
        clientRequestId,
        operationId,
      }, "warning");
      return true;
    };
    const userMsg: ChatDraftMessage = {
      id: `user-${baseTimestamp}`,
      role: "user",
      content: displayContent,
      createdAt: new Date(baseTimestamp).toISOString(),
      status: "sent",
      clientRequestId,
      operationId: operationId || undefined,
      ...(attachments.length ? { attachments } : {}),
    };
    const operationUserMessages: ChatDraftMessage[] = useAggregateUserMessages
      ? aggregateUserMessages.map((message) => ({
          ...message,
          clientRequestId,
          operationId: operationId || undefined,
          status: "sent" as const,
        }))
      : [userMsg];
    const operationUserMsg = operationUserMessages[operationUserMessages.length - 1] || userMsg;
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
    const nextMessages = useAggregateUserMessages
      ? operationUserMessages.reduce(
          (list, message) => applyMessageById(list, message.id, message),
          messagesRef.current,
        )
      : [...messagesRef.current, userMsg];
    const privateModelContent = !groupChatMode
      ? options.modelContent ?? buildPrivateUserContent(content, attachments)
      : null;
    const requestUserContent = shouldRequestDu
      ? isGroupFreeDiscussion
        ? buildGroupFreeDiscussionOpeningContent(nextMessages, effectiveContent)
        : groupChatMode
        ? buildGroupTurnUserContent(nextMessages, effectiveContent)
        : privateModelContent
      : "";
    const musicBgmContext = shouldRequestDu && !groupChatMode ? readMusicBgmContext() : null;
    const requestPath = shouldRequestDu ? (groupChatMode ? "/miniapp-api/sumitalk-chat-jobs" : "/miniapp-api/sumitalk-chat") : "";
    const requestBody = shouldRequestDu
      ? groupChatMode
        ? buildGroupChatRequestBody({
            model: activeModel,
            userContent: String(requestUserContent || ""),
            windowId,
            replyTarget: resolvedDeviceId,
            clientRequestId,
          })
        : buildPrivateChatRequestBody({
            model: activeModel,
            modelContent: privateModelContent ?? buildPrivateUserContent(content, attachments),
            windowId,
            musicBgmContext,
            replyTarget: resolvedDeviceId,
            clientRequestId,
          })
      : null;
    const draftMessages = [
      ...nextMessages,
      ...(assistantPlaceholder ? [assistantPlaceholder] : []),
      ...(benbenPlaceholder ? [benbenPlaceholder] : []),
    ];
    const retryRequestBody = requestBody
      ? privateRequestBodyForLocalStorage(requestBody, attachments)
      : null;
    const replyTarget = resolvedDeviceId;
    setInput("");
    setPlusOpen(false);
    setActiveSendStageLabel("准备发送");
    setSending(true);
    setMessages(draftMessages);
    messagesRef.current = draftMessages;
    try {
      if (shouldRequestDu && assistantPlaceholder && requestBody) {
        await createChatDraftTurn({
          deviceId: resolvedDeviceId,
          windowId: historyWindowId,
          userMessage: operationUserMsg,
          userMessages: operationUserMessages,
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
              body: retryRequestBody || requestBody,
            },
            retryPayloadSize: JSON.stringify(retryRequestBody || requestBody).length,
            userMessageId: operationUserMsg.id,
            assistantMessageId: assistantId,
            status: "draft",
            createdAt: new Date(baseTimestamp).toISOString(),
            updatedAt: new Date(baseTimestamp).toISOString(),
            retryCount: 0,
            schemaVersion: 1,
          },
        });
      } else {
        await saveDisplayHistory(draftMessages, {
          localDeviceId: resolvedDeviceId,
          strict: true,
          source: "send_draft",
        });
      }
    } catch (e: any) {
      const errorMessage = String(e?.message || e);
      logSumiTalkSendStage("chat_local_draft_write_error", {
        source,
        attemptId,
        clientRequestId,
        operationId,
        error: errorMessage,
      }, "error");
      let failedMessages = draftMessages;
      if (assistantPlaceholder) {
        const failedAssistantMessage = groupChatMode
          ? buildGroupAssistantFailureMessage({
              assistantId,
              assistantCreatedAt,
              clientRequestId,
              operationId,
              error: e,
            })
          : buildPrivateAssistantFailureMessage({
              assistantId,
              assistantCreatedAt,
              clientRequestId,
              operationId,
              cancelled: false,
              error: e,
            });
        failedMessages = applyAssistantTerminalMessage(failedMessages, clientRequestId, failedAssistantMessage);
      }
      if (benbenPlaceholder) {
        failedMessages = applyMessageById(failedMessages, benbenPlaceholderId, {
          id: benbenPlaceholderId,
          role: "benben",
          content: `（笨笨入群失败：${errorMessage}）`,
          createdAt: benbenPlaceholderCreatedAt,
          status: "failed",
          clientRequestId: `${clientRequestId}-benben`,
        });
      }
      messagesRef.current = failedMessages;
      setMessages(failedMessages);
      setActiveSendStageLabel("");
      setSending(false);
      toast(`本地聊天存储失败：${errorMessage}`);
      return false;
    }
    const abortController = shouldRequestDu ? new AbortController() : null;
    if (shouldRequestDu && abortController) {
      activeChatRequestRef.current = {
        attemptId,
        clientRequestId,
        operationId,
        assistantId,
        jobId: "",
        source,
        abortController,
      };
      logSumiTalkSendStage("chat_send_start", {
        source,
        requestPath,
        attemptId,
        clientRequestId,
        operationId,
        contentChars: effectiveContent.length,
        attachments: attachments.length,
        audioAttachments: attachments.filter((item) => item.kind === "audio").length,
        imageAttachments: attachments.filter((item) => item.kind === "image").length,
        documentAttachments: attachments.filter((item) => item.kind === "document").length,
        model: activeModel,
      });
    }
    let benbenCreatePromise: Promise<ChatDraftMessage[]> | null = null;
    let initialDuReply = "";
    try {
      if (shouldRequestBenben) {
        benbenCreatePromise = requestBenbenGroupReply({
          baseMessages: messagesRef.current,
          userContent: effectiveContent,
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
        if (isPrivateDuAttempt) {
          const result = await runPrivateChatSendFlow({
            source,
            requestPath,
            requestBody,
            attemptId,
            clientRequestId,
            operationId,
            assistantId,
            assistantCreatedAt,
            abortSignal: abortController?.signal,
            logEvent: logSumiTalkSendStage,
            skipStaleAttemptUpdate,
            onEvent: (event) => {
              applyStreamingSumiTalkChatEvent(event);
            },
            onJobId: async (jobId) => {
              if (activeChatRequestRef.current?.clientRequestId === clientRequestId && isCurrentAttempt()) {
                activeChatRequestRef.current = { ...activeChatRequestRef.current, jobId };
              }
              await attachChatJobBestEffort(operationId, jobId);
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
              await saveDisplayHistory(pendingWithJob, { localDeviceId: replyTarget });
            },
          });
          if (!result) return false;
          initialDuReply = result.reply || result.voiceText;
          const finalMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, result.assistantMessage);
          await completeChatOperationBestEffort(operationId, result.assistantMessage);
          messagesRef.current = finalMessages;
          setMessages(finalMessages);
          await saveDisplayHistory(finalMessages, { localDeviceId: replyTarget });
          if (result.voiceText) {
            void appendAssistantVoiceOutputAudio({
              assistantId,
              clientRequestId,
              operationId,
              jobId: result.jobId,
              voiceText: result.voiceText,
              localDeviceId: replyTarget,
            });
          }
        } else {
          const result = await runGroupDuReplyFlow({
            source,
            requestPath,
            requestBody,
            attemptId,
            clientRequestId,
            operationId,
            assistantId,
            assistantCreatedAt,
            abortSignal: abortController?.signal,
            logEvent: logSumiTalkSendStage,
            skipStaleAttemptUpdate,
            onEvent: (event) => {
              applyStreamingSumiTalkChatEvent(event);
            },
            onJobId: async (jobId) => {
              if (activeChatRequestRef.current?.clientRequestId === clientRequestId && isCurrentAttempt()) {
                activeChatRequestRef.current = { ...activeChatRequestRef.current, jobId };
              }
              await attachChatJobBestEffort(operationId, jobId);
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
              await saveDisplayHistory(pendingWithJob, { localDeviceId: replyTarget });
            },
          });
          if (!result) return false;
          initialDuReply = result.reply || result.voiceText;
          const finalMessages = applyAssistantTerminalMessage(messagesRef.current, clientRequestId, result.assistantMessage);
          await completeChatOperationBestEffort(operationId, result.assistantMessage);
          messagesRef.current = finalMessages;
          setMessages(finalMessages);
          await saveDisplayHistory(finalMessages, { localDeviceId: replyTarget });
          if (result.voiceText) {
            void appendAssistantVoiceOutputAudio({
              assistantId,
              clientRequestId,
              operationId,
              jobId: result.jobId,
              voiceText: result.voiceText,
              localDeviceId: replyTarget,
            });
          }
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
          topic: effectiveContent,
          replyTarget,
          initialDuReply,
        });
      }
      return true;
    } catch (e: any) {
      const rawErrorMessage = String(e?.message || e);
      const cancelled = Boolean(abortController?.signal.aborted)
        || String(e?.name || "") === "AbortError"
        || /cancel|cancelled|取消/i.test(rawErrorMessage);
      const errorMessage = cancelled ? "已取消发送" : rawErrorMessage;
      if (skipStaleAttemptUpdate(cancelled ? "catch_cancelled" : "catch_failed")) return false;
      logSumiTalkSendStage(cancelled ? "chat_send_cancelled" : "chat_send_error", {
        source,
        attemptId,
        clientRequestId,
        operationId,
        error: errorMessage,
      }, cancelled ? "warning" : "error");
      if (benbenCreatePromise) {
        await benbenCreatePromise.catch(() => messagesRef.current);
      }
      const failedAssistantMessage = shouldRequestDu
        ? groupChatMode
          ? buildGroupAssistantFailureMessage({
              assistantId,
              assistantCreatedAt,
              clientRequestId,
              operationId,
              cancelled,
              error: e,
            })
          : buildPrivateAssistantFailureMessage({
              assistantId,
              assistantCreatedAt,
              clientRequestId,
              operationId,
              cancelled,
              error: e,
            })
        : null;
      const failedMessages = failedAssistantMessage
        ? applyAssistantTerminalMessage(messagesRef.current, clientRequestId, failedAssistantMessage)
        : messagesRef.current;
      if (shouldRequestDu && operationId) {
        await failChatOperationBestEffort(operationId, errorMessage, failedAssistantMessage || undefined);
      }
      messagesRef.current = failedMessages;
      setMessages(failedMessages);
      await saveDisplayHistory(failedMessages, { localDeviceId: replyTarget });
      if (groupChatMode) {
        saveDisplayHistoryInBackground(failedMessages, { localDeviceId: replyTarget });
      }
      toast(cancelled ? "已取消发送" : `发送失败：${e?.message || e}`);
      return false;
    } finally {
      if (isCurrentAttempt()) {
        if (activeChatRequestRef.current?.clientRequestId === clientRequestId) {
          activeChatRequestRef.current = null;
        }
        setActiveSendStageLabel("");
        setSending(false);
      }
    }
  }

  async function sendPendingImageDrafts(): Promise<boolean> {
    const drafts = pendingImageDraftsRef.current;
    if (!drafts.length || sending || mediaBusy) return false;
    const files = drafts.map((draft) => draft.file);
    const realModeText = realModeEnabledRef.current ? input.trim() : "";
    const imageCaptionText = realModeText ? "" : input;
    setMediaBusy(true);
    try {
      logSumiTalkClientEvent("image_upload_start", {
        count: files.length,
        names: files.map((file) => file.name).slice(0, 8).join(", "),
        bytes: files.reduce((sum, file) => sum + file.size, 0),
        realModeText: Boolean(realModeText),
      });
      const prepared = await prepareImagesPrivateChatInput(files, imageCaptionText);
      logSumiTalkClientEvent("image_upload_ok", {
        count: prepared.attachments.length,
        bytes: prepared.attachments.reduce((sum, attachment) => sum + Number(attachment.size || 0), 0),
        hasRemoteUrl: prepared.attachments.some((attachment) => Boolean(attachment.remoteUrl)),
        hasRemoteKey: prepared.attachments.some((attachment) => Boolean(attachment.remoteKey)),
      });
      if (realModeText) {
        const textSent = await sendPreparedPrivateChatInput(prepareTextPrivateChatInput(realModeText));
        if (!textSent) return false;
      }
      const sent = await sendPreparedPrivateChatInput(prepared, { quote: realModeText ? null : undefined });
      if (sent) {
        clearPendingImageDrafts();
      }
      return sent;
    } catch (e: any) {
      logSumiTalkClientEvent("image_upload_error", { error: String(e?.message || e) }, "error");
      toast(`图片发送失败：${e?.message || e}`);
      return false;
    } finally {
      setMediaBusy(false);
    }
  }

  async function sendMessage() {
    if (pendingImageDraftsRef.current.length) {
      await sendPendingImageDrafts();
      return;
    }
    const sent = await sendPreparedPrivateChatInput(prepareTextPrivateChatInput(input));
    if (sent) refocusTextInputSoon();
  }

  async function sendPreparedPrivateChatInput(
    prepared: PreparedPrivateChatInput,
    options: { quote?: ChatBubbleQuote | null } = {},
  ): Promise<boolean> {
    const quote = Object.prototype.hasOwnProperty.call(options, "quote") ? options.quote : quotedBubble;
    const finalPrepared = quote ? preparedInputWithQuote(prepared, quote) : prepared;
    const sent = await sendChatContent(finalPrepared.content, {
      displayContent: finalPrepared.displayContent,
      attachments: finalPrepared.attachments,
      source: finalPrepared.source,
      modelContent: finalPrepared.modelContent,
    });
    if (sent && quote) setQuotedBubble(null);
    if (sent && realModeEnabledRef.current) void refreshRealBodyStatus();
    return sent;
  }

  function openImagePicker() {
    if (sending || mediaBusy) return;
    setPlusOpen(false);
    imageInputRef.current?.click();
  }

  function openDocumentPicker() {
    if (sending || mediaBusy) return;
    setPlusOpen(false);
    documentInputRef.current?.click();
  }

  function openDoodleBoard() {
    if (sending || mediaBusy) return;
    setVoiceInputOpen(false);
    setPlusOpen(false);
    textInputRef.current?.blur();
    setDoodleBoardOpen(true);
  }

  async function sendDoodleImage(file: File): Promise<boolean> {
    if (!file || sending || mediaBusy) return false;
    setMediaBusy(true);
    try {
      const queuedDrafts = pendingImageDraftsRef.current;
      const files = [...queuedDrafts.map((draft) => draft.file), file];
      logSumiTalkClientEvent("doodle_send_start", {
        bytes: file.size,
        mime: file.type,
        pendingImages: queuedDrafts.length,
        totalImages: files.length,
      });
      const prepared = await prepareImagesPrivateChatInput(files, input);
      const sent = await sendPreparedPrivateChatInput(prepared);
      if (sent && queuedDrafts.length) clearPendingImageDrafts();
      logSumiTalkClientEvent(sent ? "doodle_send_ok" : "doodle_send_skip", { bytes: file.size, totalImages: files.length });
      return sent;
    } catch (e: any) {
      logSumiTalkClientEvent("doodle_send_error", { error: String(e?.message || e) }, "error");
      toast(`涂鸦发送失败：${e?.message || e}`);
      return false;
    } finally {
      setMediaBusy(false);
    }
  }

  async function handleImageInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []).filter((file) => file.type.startsWith("image/"));
    event.target.value = "";
    if (!files.length || sending || mediaBusy) return;
    const pickedAt = Date.now();
    const drafts = files.map((file, index) => ({
      id: `image-draft-${pickedAt}-${index}-${Math.random().toString(36).slice(2, 8)}`,
      file,
      previewUrl: URL.createObjectURL(file),
    }));
    setPendingImageDrafts((current) => [...current, ...drafts]);
    setPlusOpen(false);
    logSumiTalkClientEvent("image_queue_add", {
      count: drafts.length,
      pending: pendingImageDraftsRef.current.length + drafts.length,
      names: files.map((file) => file.name).slice(0, 8).join(", "),
      bytes: files.reduce((sum, file) => sum + file.size, 0),
    });
  }

  async function handleDocumentInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    event.target.value = "";
    if (!file || sending || mediaBusy) return;
    setMediaBusy(true);
    try {
      logSumiTalkClientEvent("document_upload_start", { name: file.name, mime: file.type, bytes: file.size });
      const prepared = await prepareDocumentPrivateChatInput(file, input);
      const attachment = prepared.attachments[0];
      logSumiTalkClientEvent("document_upload_ok", {
        name: attachment.name || file.name,
        mime: attachment.mime || file.type,
        bytes: attachment.size || file.size,
        hasRemoteUrl: Boolean(attachment.remoteUrl),
        hasRemoteKey: Boolean(attachment.remoteKey),
      });
      await sendPreparedPrivateChatInput(prepared);
    } catch (e: any) {
      logSumiTalkClientEvent("document_upload_error", { error: String(e?.message || e) }, "error");
      toast(`文档发送失败：${e?.message || e}`);
    } finally {
      setMediaBusy(false);
    }
  }

  async function ensureChatVoiceStream(): Promise<MediaStream> {
    if (chatVoiceStreamRef.current) return chatVoiceStreamRef.current;
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("当前环境不支持麦克风录音");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    chatVoiceStreamRef.current = stream;
    return stream;
  }

  async function beginChatVoiceRecording(): Promise<boolean> {
    if (sending || mediaBusy || recordingChatVoice) return false;
    setMediaBusy(true);
    try {
      logSumiTalkClientEvent("voice_record_start");
      const stream = await ensureChatVoiceStream();
      chatVoiceChunksRef.current = [];
      chatVoiceMimeRef.current = resolveRecorderMimeType();
      const recorder = chatVoiceMimeRef.current ? new MediaRecorder(stream, { mimeType: chatVoiceMimeRef.current }) : new MediaRecorder(stream);
      chatVoiceRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chatVoiceChunksRef.current.push(event.data);
      };
      recorder.start(1000);
      chatVoiceStartedAtRef.current = Date.now();
      setRecordingChatVoice(true);
      logSumiTalkClientEvent("voice_record_started", { mime: chatVoiceMimeRef.current || recorder.mimeType || "" });
      return true;
    } catch (e: any) {
      logSumiTalkClientEvent("voice_record_error", { error: String(e?.message || e) }, "error");
      toast(`录音失败：${e?.message || e}`);
      return false;
    } finally {
      setMediaBusy(false);
    }
  }

  function setChatVoiceCancelIntent(next: boolean) {
    chatVoiceCancelArmedRef.current = next;
    setChatVoiceCancelArmed(next);
  }

  function releaseChatVoicePointer(target: EventTarget & HTMLButtonElement, pointerId: number) {
    try {
      if (target.hasPointerCapture(pointerId)) {
        target.releasePointerCapture(pointerId);
      }
    } catch {
      // Ignore WebView pointer-capture quirks.
    }
  }

  async function stopChatVoiceRecording() {
    const recorder = chatVoiceRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    setMediaBusy(true);
    try {
      const mimeType = chatVoiceMimeRef.current || recorder.mimeType || "audio/webm";
      const recordedDurationMs = chatVoiceStartedAtRef.current ? Math.max(0, Date.now() - chatVoiceStartedAtRef.current) : 0;
      const blob = await new Promise<Blob>((resolve) => {
        const finalize = () => {
          recorder.removeEventListener("stop", finalize);
          resolve(new Blob(chatVoiceChunksRef.current, { type: mimeType }));
        };
        recorder.addEventListener("stop", finalize);
        recorder.stop();
      });
      chatVoiceStartedAtRef.current = 0;
      setRecordingChatVoice(false);
      chatVoiceRecorderRef.current = null;
      chatVoiceChunksRef.current = [];
      if (blob.size <= 0) throw new Error("录音为空");
      logSumiTalkClientEvent("voice_record_stop", { mime: mimeType, bytes: blob.size });
      logSumiTalkClientEvent("voice_stt_start", { mime: mimeType, bytes: blob.size });
      const prepared = await prepareVoicePrivateChatInput(blob, mimeType, recordedDurationMs);
      const transcript = prepared.content;
      const attachment = prepared.attachments[0];
      logSumiTalkClientEvent("voice_stt_ok", {
        mime: mimeType,
        bytes: blob.size,
        textChars: transcript.length,
        provider: prepared.sttProvider || "",
        hasAttachment: Boolean(attachment?.remoteKey || attachment?.remoteUrl),
      });
      await sendPreparedPrivateChatInput(prepared);
    } catch (e: any) {
      setRecordingChatVoice(false);
      logSumiTalkClientEvent("voice_send_error", { error: String(e?.message || e) }, "error");
      toast(`语音发送失败：${e?.message || e}`);
    } finally {
      setMediaBusy(false);
    }
  }

  async function cancelChatVoiceRecording(showToast = true) {
    chatVoicePressingRef.current = false;
    setChatVoiceCancelIntent(false);
    const startPromise = chatVoiceStartPromiseRef.current;
    chatVoiceStartPromiseRef.current = null;
    if (startPromise) await startPromise.catch(() => false);

    const recorder = chatVoiceRecorderRef.current;
    try {
      if (recorder && recorder.state !== "inactive") {
        await new Promise<void>((resolve) => {
          const finalize = () => {
            recorder.removeEventListener("stop", finalize);
            resolve();
          };
          recorder.addEventListener("stop", finalize);
          recorder.stop();
        });
      }
      logSumiTalkClientEvent("voice_record_cancel");
      if (showToast) toast("已取消语音");
    } catch (e: any) {
      logSumiTalkClientEvent("voice_record_cancel_error", { error: String(e?.message || e) }, "error");
    } finally {
      chatVoiceRecorderRef.current = null;
      chatVoiceStartedAtRef.current = 0;
      chatVoiceChunksRef.current = [];
      setRecordingChatVoice(false);
      setMediaBusy(false);
    }
  }

  function handleChatVoicePressStart(event: React.PointerEvent<HTMLButtonElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    event.preventDefault();
    if (sending || mediaBusy || chatVoicePressingRef.current) return;
    chatVoicePressingRef.current = true;
    chatVoiceStartYRef.current = event.clientY;
    setChatVoiceCancelIntent(false);
    setVoiceInputOpen(true);
    setPlusOpen(false);
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Some embedded WebViews do not expose pointer capture.
    }
    chatVoiceStartPromiseRef.current = beginChatVoiceRecording();
  }

  function handleChatVoicePressMove(event: React.PointerEvent<HTMLButtonElement>) {
    if (!chatVoicePressingRef.current) return;
    const shouldCancel = chatVoiceStartYRef.current > 0 && chatVoiceStartYRef.current - event.clientY > 52;
    if (shouldCancel !== chatVoiceCancelArmedRef.current) setChatVoiceCancelIntent(shouldCancel);
  }

  function handleChatVoicePressEnd(event: React.PointerEvent<HTMLButtonElement>) {
    if (!chatVoicePressingRef.current && !chatVoiceStartPromiseRef.current) return;
    event.preventDefault();
    chatVoicePressingRef.current = false;
    releaseChatVoicePointer(event.currentTarget, event.pointerId);
    void (async () => {
      const shouldCancel = chatVoiceCancelArmedRef.current;
      setChatVoiceCancelIntent(false);
      const startPromise = chatVoiceStartPromiseRef.current;
      chatVoiceStartPromiseRef.current = null;
      if (startPromise) await startPromise.catch(() => false);
      if (shouldCancel) {
        await cancelChatVoiceRecording(false);
        toast("已取消语音");
      } else {
        await stopChatVoiceRecording();
      }
    })();
  }

  function handleChatVoicePressCancel(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    releaseChatVoicePointer(event.currentTarget, event.pointerId);
    void cancelChatVoiceRecording(false);
  }

  function toggleVoiceInputPanel() {
    if (recordingChatVoice || chatVoicePressingRef.current) return;
    setPlusOpen(false);
    setVoiceInputOpen((value) => !value);
  }

  const avatarClass = accent === "wenyou"
    ? "bg-[#F8F0F4] text-[#704A5D]"
    : "bg-[#F0F4F8] text-[#4A5568]";
  const benbenGroupActive = groupChatMode;
  const groupedMessages = groupChatMessages(messages, { preserveLineBreaks: realModeEnabled });
  const assistantTyping = (sending || groupDiscussionRunning) && messages.some(
    (msg) => (msg.role === "assistant" || msg.role === "benben") && String(msg.status || "").trim().toLowerCase() === "pending",
  );
  const trimmedInput = input.trim();
  const hasPendingImageDrafts = pendingImageDrafts.length > 0;
  const canSendCurrentInput = Boolean(trimmedInput || hasPendingImageDrafts);
  const canSubmitWhileBusy = groupChatMode && (
    isBenbenCancelCommand(trimmedInput)
    || (groupDiscussionRunning && isGroupDiscussionStopCommand(trimmedInput))
    || isGroupDiscussionContinueCommand(trimmedInput)
  );
  const canCancelQueuedSend = !voiceInputOpen
    && !canSendCurrentInput
    && !sending
    && !mediaBusy
    && privateInputAggregateCancelable
    && privateInputAggregateCount > 0;
  const bubbleMenuItemCount = bubbleMenu
    ? 2
      + (bubbleMenu.hasVoice ? 1 : 0)
      + (bubbleMenu.canRetry ? 1 : 0)
      + (bubbleMenu.aggregateEditable ? 1 : 0)
      + (bubbleMenu.aggregateCanEditText ? 1 : 0)
    : 0;
  const bubbleMenuColumns = Math.min(3, Math.max(1, bubbleMenuItemCount));
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
                  : `${String(part.content || "")} ${chatAttachmentPreviewLabel(part.attachments)}`;
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
  const activeSearchDisplayIndex = searchMatches.length
    ? Math.min(activeSearchIndex, searchMatches.length - 1)
    : 0;
  const activeSearchMatch = searchMatches.length ? searchMatches[activeSearchDisplayIndex] : null;
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
    : "flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-gray-500 transition-colors active:bg-gray-100";
  const chatHeaderCenterPillClass = hasCustomChatBackground
    ? "flex h-10 w-[10.5rem] max-w-full min-w-0 flex-col items-center justify-center rounded-full border border-white/35 bg-white/45 px-3 text-center shadow-[0_8px_24px_rgba(15,23,42,0.10)] backdrop-blur-2xl"
    : "flex h-10 w-[10.5rem] max-w-full min-w-0 flex-col items-center justify-center rounded-full border border-gray-100/80 bg-white/85 px-3 text-center shadow-[0_8px_20px_rgba(15,23,42,0.06)] backdrop-blur-xl";
  const chatHeaderTitleFontSize = Math.max(14, Math.min(16, chatTitleFontSize - 2));
  const chatFooterClass = "overflow-visible";
  const chatInputBarClass = hasCustomChatBackground
    ? "border border-white/40 bg-white/50 shadow-[0_8px_22px_rgba(15,23,42,0.10)] backdrop-blur-2xl"
    : "border border-white/80 bg-white/75 shadow-[0_8px_22px_rgba(15,23,42,0.08)] backdrop-blur-2xl";
  const chatFooterIconButtonClass = hasCustomChatBackground
    ? "bg-white/30 text-gray-700 active:bg-white/50"
    : "bg-white/45 text-gray-600 active:bg-white/75";
  const chatFooterIconButtonActiveClass = hasCustomChatBackground
    ? "bg-white/70 text-gray-900"
    : "bg-white/85 text-gray-900";
  const chatPlusPanelClass = hasCustomChatBackground
    ? "border-white/35 bg-white/50 shadow-[0_8px_22px_rgba(15,23,42,0.10)] backdrop-blur-2xl"
    : "border-white/80 bg-white/75 shadow-[0_8px_22px_rgba(15,23,42,0.08)] backdrop-blur-2xl";
  const chatInputShellClass = hasCustomChatBackground
    ? "bg-white/10"
    : "bg-white/20";
  const chatSearchShellClass = hasCustomChatBackground
    ? "border border-white/25 bg-white/45 shadow-[0_8px_24px_rgba(15,23,42,0.08)] backdrop-blur-xl"
    : "bg-[#F4F5F7]";
  const chatMessageColumnWidthClass = showChatAvatars ? "max-w-[70%]" : "max-w-[78%]";
  const chatHeaderWrapClass = hasCustomChatBackground
    ? `absolute top-0 z-20 w-full border-b px-3 ${realModeEnabled ? "pb-3" : "pb-2"} pt-[calc(env(safe-area-inset-top,0px)+10px)]`
    : `absolute top-0 z-20 w-full border-b px-3 ${realModeEnabled ? "pb-4" : "pb-3"} pt-[calc(env(safe-area-inset-top,0px)+20px)]`;
  const chatRealBodyCapsuleClass = hasCustomChatBackground
    ? "max-w-[calc(100vw-9rem)] truncate rounded-full border border-white/30 bg-white/28 px-2.5 py-[2px] text-[9px] font-medium leading-[13px] text-gray-700/80 shadow-[0_5px_14px_rgba(15,23,42,0.08)] backdrop-blur-2xl"
    : "max-w-[calc(100vw-9rem)] truncate rounded-full border border-gray-100/70 bg-white/58 px-2.5 py-[2px] text-[9px] font-medium leading-[13px] text-gray-500 shadow-[0_5px_14px_rgba(15,23,42,0.05)] backdrop-blur-xl";
  const messagesTopPaddingClass = searchOpen
    ? realModeEnabled
      ? hasCustomChatBackground ? "pt-[164px]" : "pt-[180px]"
      : hasCustomChatBackground ? "pt-[140px]" : "pt-[156px]"
    : realModeEnabled
      ? hasCustomChatBackground ? "pt-[112px]" : "pt-[128px]"
      : hasCustomChatBackground ? "pt-[88px]" : "pt-[104px]";
  const chatBackgroundCanvasHeight = chatBackgroundHeightRef.current ? `${chatBackgroundHeightRef.current}px` : "100lvh";

  const stickChatToBottom = useCallback(() => {
    if (searchOpen) return;
    const el = messagesScrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
      chatShouldStickBottomRef.current = true;
    });
  }, [searchOpen]);

  useEffect(() => {
    if (searchOpen) return;
    const el = messagesScrollRef.current;
    if (!el) return;
    stickChatToBottom();
  }, [messages, searchOpen, voiceInputOpen, plusOpen, quotedBubble, stickChatToBottom]);

  useEffect(() => {
    const el = messagesScrollRef.current;
    if (!el) return;

    const updateStickyState = () => {
      chatShouldStickBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 180;
    };

    updateStickyState();
    el.addEventListener("scroll", updateStickyState, { passive: true });
    return () => {
      el.removeEventListener("scroll", updateStickyState);
    };
  }, []);

  useEffect(() => {
    const el = messagesScrollRef.current;
    if (!el || searchOpen) return;

    let frame = 0;
    const keepBottomIfNeeded = () => {
      if (!chatShouldStickBottomRef.current) return;
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
      });
    };

    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(keepBottomIfNeeded) : null;
    observer?.observe(el);
    window.addEventListener("resize", keepBottomIfNeeded);

    return () => {
      if (frame) cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", keepBottomIfNeeded);
    };
  }, [searchOpen]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (!query) {
      lastSearchQueryRef.current = "";
      setActiveSearchIndex(0);
      return;
    }

    if (lastSearchQueryRef.current !== query) {
      lastSearchQueryRef.current = query;
      setActiveSearchIndex(searchMatches.length > 0 ? searchMatches.length - 1 : 0);
      return;
    }

    setActiveSearchIndex((prev) => {
      if (!searchMatches.length) return 0;
      return Math.min(prev, searchMatches.length - 1);
    });
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
      className="fixed inset-0 z-30 flex h-[100dvh] min-h-[100svh] w-full max-w-full flex-col overflow-hidden overscroll-none bg-transparent"
      style={{
        fontFamily: chatFontFamily,
      } as React.CSSProperties}
    >
      <div
        className="pointer-events-none absolute left-0 top-0 z-0 w-full bg-[#F8F9FA]"
        style={{ height: chatBackgroundCanvasHeight }}
      />
      {hasCustomChatBackground ? (
        <>
          <div
            className="pointer-events-none absolute left-0 top-0 z-0 w-full bg-cover bg-center"
            style={{ backgroundImage: `url(${chatBackgroundImage})`, height: chatBackgroundCanvasHeight }}
          />
          <div
            className="pointer-events-none absolute left-0 top-0 z-0 w-full"
            style={{ backgroundColor: `rgba(248,249,250,${chatBackgroundOverlayAlpha})`, height: chatBackgroundCanvasHeight }}
          />
        </>
      ) : null}
      <div className={`${chatHeaderWrapClass} ${chatChromeClass}`}>
        <div className="grid grid-cols-[2.5rem_minmax(0,1fr)_2.5rem] items-start gap-2">
          <button className={chatHeaderButtonClass} onClick={onBack} aria-label="返回">
            <ChevronLeftIcon />
          </button>
          <div className="flex min-w-0 flex-col items-center justify-start">
            <div className={chatHeaderCenterPillClass}>
              <div
                className="max-w-full truncate font-semibold leading-[1.05] text-gray-900"
                style={{ fontSize: `${chatHeaderTitleFontSize}px` }}
              >
                {title}
              </div>
              <div className="mt-[2px] flex w-full min-w-0 justify-center">
                <ChatHeaderStatus sending={assistantTyping} />
              </div>
            </div>
            {realModeEnabled ? (
              <div className={`mt-1 ${chatRealBodyCapsuleClass}`}>
                {realBodyStatusText || formatRealModeBodyStatus(null)}
              </div>
            ) : null}
          </div>
          <button
            className={`${chatHeaderButtonClass} justify-self-end`}
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
        {groupDiscussionStatus ? (
          <div className="mt-1 flex justify-center">
            <div className="max-w-[72vw] truncate rounded-full bg-amber-50/80 px-3 py-1 text-[10px] font-medium text-amber-700 backdrop-blur">
              {groupDiscussionStatus}
            </div>
          </div>
        ) : null}
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
                  {activeSearchDisplayIndex + 1}/{searchMatches.length}
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
        className={`relative z-10 min-h-0 w-full max-w-full flex-1 overflow-x-hidden overflow-y-auto overscroll-contain px-2 pb-5 ${messagesTopPaddingClass}`}
        style={{
          WebkitOverflowScrolling: "touch",
        }}
      >
        <div className="space-y-4">
          {groupedMessages.map((group, index) => (
            <React.Fragment key={group.id}>
              {showChatTimestamps && shouldShowGroupTime(group.createdAt, groupedMessages[index - 1]?.lastCreatedAt) ? (
                <div className="mb-2 flex justify-center">
                  <span className="rounded-full bg-[rgba(239,239,239,0.62)] px-3 py-1 text-[10px] font-medium text-gray-800">
                    {formatClockTime(group.createdAt, chatTimeFormat)}
                  </span>
                </div>
              ) : null}
              {group.role === "user" ? (
                <div className="flex items-start justify-end space-x-2 rounded-[22px]">
                  <div className={`mt-[2px] flex ${chatMessageColumnWidthClass} flex-col items-end space-y-1.5`}>
                    {groupChatMode ? <div className="px-1 text-[11px] font-medium leading-none text-gray-400">辛玥</div> : null}
                      {group.parts.map((part, index) => {
                        const matchId = getChatSearchMatchId(group.id, index);
                        const isActiveSearchPart = activeSearchMatchId === matchId;
                        const bubbleSkin = transparentBubbleEnabled ? undefined : resolveBubbleSkin(userBubbleStyle);
                        const hasText = Boolean(String(part.content || "").trim());
                        const audioAttachments = normalizeChatAttachments(part.attachments).filter((item) => item.kind === "audio");
                        const hasVoice = audioAttachments.length > 0;
                        const showText = hasText && !hasVoice && !isVoiceTranscriptEcho(part.content, audioAttachments);
                        const bubbleTarget = buildBubbleMenuTarget({
                          id: matchId,
                          messageId: part.messageId,
                          role: group.role,
                          content: part.content,
                          attachments: part.attachments,
                          status: part.status,
                          operationId: part.operationId,
                        });
                        return (
                          <div
                            key={`${group.id}-${index}`}
                            ref={(el) => {
                              searchResultRefs.current[matchId] = el;
                            }}
                            className={`flex max-w-full flex-col items-end gap-1.5 ${isActiveSearchPart ? "rounded-[20px] ring-2 ring-amber-300/90 ring-offset-2 ring-offset-transparent" : ""}`}
                            onContextMenu={(event) => handleBubbleContextMenu(event, bubbleTarget)}
                            onTouchStart={(event) => handleBubbleTouchStart(event, bubbleTarget)}
                            onTouchMove={handleBubbleTouchMove}
                            onTouchEnd={handleBubbleTouchEnd}
                            onTouchCancel={handleBubbleTouchEnd}
                          >
                          <ChatAttachmentBlock attachments={part.attachments} align="right" kinds={["image"]} />
                          {showText ? (
                            <ChatBubbleFrame
                              skin={bubbleSkin}
                              align="right"
                              className={`block max-w-full rounded-[18px] px-2.5 py-[5px] text-left font-medium leading-[1.42] shadow-sm ${
                                transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("user", userBubbleStyle)
                              }`}
                              style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
                            >
                              <PlainTextBlock content={part.content} />
                            </ChatBubbleFrame>
                          ) : null}
                          {hasVoice ? (
                            <ChatBubbleFrame
                              skin={bubbleSkin}
                              align="right"
                              className={`block max-w-full rounded-[18px] px-2 py-[2px] text-left font-medium leading-[1.42] shadow-sm ${
                                transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("user", userBubbleStyle)
                              }`}
                              style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
                            >
                              <ChatAttachmentBlock attachments={audioAttachments} align="right" />
                            </ChatBubbleFrame>
                          ) : null}
                            <ChatVoiceTranscriptBlock
                              attachments={audioAttachments}
                              align="right"
                              openTranscriptId={openVoiceTranscriptId}
                              onTranscriptToggle={toggleVoiceTranscript}
                              showToggle={false}
                            />
                        </div>
                      );
                    })}
                  </div>
                  {showChatAvatars ? (
                    <AvatarBubble image={myAvatarImage} label="我" className="bg-gray-200 text-gray-600" />
                  ) : null}
                </div>
              ) : (
                <div className="flex items-start space-x-2 rounded-[22px]">
                  {showChatAvatars ? (
                    <AvatarBubble
                      image={group.role === "benben" ? benbenAvatarImage : duAvatarImage}
                      label={group.role === "benben" ? "笨" : avatarLabel}
                      className={group.role === "benben" ? "bg-[#FFF3D7] text-[#8A5A10]" : avatarClass}
                    />
                  ) : null}
                  <div className={`mt-[2px] ${chatMessageColumnWidthClass} space-y-1.5`}>
                    {groupChatMode ? (
                      <div className="px-1 text-[11px] font-medium leading-none text-gray-400">
                        {group.role === "benben" ? "笨笨" : avatarLabel || "渡"}
                      </div>
                    ) : null}
	                    {group.parts.map((part, index) => {
	                      const matchId = getChatSearchMatchId(group.id, index);
	                      const isActiveSearchPart = activeSearchMatchId === matchId;
	                      if (part.displayPart?.kind === "reasoning") {
	                        return (
	                          <div
	                            key={`${group.id}-${index}`}
	                            ref={(el) => {
	                              searchResultRefs.current[matchId] = el;
	                            }}
	                            className={`max-w-full rounded-[20px] px-1 ${isActiveSearchPart ? "ring-2 ring-amber-300/90 ring-offset-2 ring-offset-transparent" : ""}`}
	                          >
	                            <ChatReasoningBlock part={part.displayPart} />
	                          </div>
	                        );
	                      }
	                      if (part.displayPart?.kind === "tool_call") {
	                        return (
	                          <div
	                            key={`${group.id}-${index}`}
	                            ref={(el) => {
	                              searchResultRefs.current[matchId] = el;
	                            }}
	                            className={`max-w-full rounded-[20px] px-1 ${isActiveSearchPart ? "ring-2 ring-amber-300/90 ring-offset-2 ring-offset-transparent" : ""}`}
	                          >
	                            {part.reasoning ? (
	                              <details className="group max-w-full text-[10px] text-gray-500">
	                                <summary className="flex cursor-pointer list-none items-center gap-1 text-[10px] font-medium leading-[14px] text-gray-400 [&::-webkit-details-marker]:hidden">
	                                  <span className="transition-transform group-open:rotate-90">&gt;</span>
	                                  <span>碎碎念</span>
	                                </summary>
	                                <div className="mt-1 max-h-36 overflow-y-auto whitespace-pre-wrap break-words pl-4 text-[10px] leading-[15px] text-gray-500">
	                                  {part.reasoning}
	                                </div>
	                              </details>
	                            ) : null}
	                            <ChatToolCallBlock part={part.displayPart} />
	                          </div>
	                        );
	                      }
	                      const bubbleSkin = transparentBubbleEnabled || group.role === "benben" ? undefined : resolveBubbleSkin(assistantBubbleStyle);
	                      const hasText = Boolean(String(part.content || "").trim());
                        const audioAttachments = normalizeChatAttachments(part.attachments).filter((item) => item.kind === "audio");
                        const showText = hasText && !isVoiceTranscriptEcho(part.content, audioAttachments);
                        const hasVoice = audioAttachments.length > 0;
                        const bubbleTarget = buildBubbleMenuTarget({
                          id: matchId,
                          messageId: part.messageId,
                          role: group.role,
                          content: part.content,
                          attachments: part.attachments,
                          status: part.status,
                          operationId: part.operationId,
                        });
                        return (
                          <div
                            key={`${group.id}-${index}`}
                            ref={(el) => {
                              searchResultRefs.current[matchId] = el;
                            }}
                            className={`flex max-w-full flex-col items-start gap-1.5 rounded-[20px] ${isActiveSearchPart ? "ring-2 ring-amber-300/90 ring-offset-2 ring-offset-transparent" : ""}`}
                            onContextMenu={(event) => handleBubbleContextMenu(event, bubbleTarget)}
                            onTouchStart={(event) => handleBubbleTouchStart(event, bubbleTarget)}
                            onTouchMove={handleBubbleTouchMove}
                            onTouchEnd={handleBubbleTouchEnd}
                            onTouchCancel={handleBubbleTouchEnd}
                          >
                          {part.reasoning ? (
                            <details className="group max-w-full text-[10px] text-gray-500">
                              <summary className="flex cursor-pointer list-none items-center gap-1 px-1 text-[10px] font-medium leading-[14px] text-gray-400 [&::-webkit-details-marker]:hidden">
                                <span className="transition-transform group-open:rotate-90">&gt;</span>
                                <span>碎碎念</span>
                              </summary>
                              <div className="mt-1 max-h-36 overflow-y-auto whitespace-pre-wrap break-words px-1 pl-4 text-[10px] leading-[15px] text-gray-500">
                                {part.reasoning}
                              </div>
                            </details>
                          ) : null}
                          <ChatAttachmentBlock attachments={part.attachments} align="left" kinds={["image"]} />
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
	                              {showText ? (
	                                <ChatBubbleFrame
                                  skin={bubbleSkin}
                                  className={`block w-fit max-w-full rounded-[18px] px-2.5 py-[5px] font-medium leading-[1.42] shadow-sm ${
                                    transparentBubbleEnabled
                                      ? TRANSPARENT_BUBBLE_CLASS
                                      : group.role === "benben"
                                        ? "border border-amber-100 bg-[#FFF7E6] text-[#3F2A11]"
                                        : resolveBubbleClass("assistant", assistantBubbleStyle)
                                  }`}
                                  style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
                                >
                                  {part.render === "html" ? (
                                    <HtmlBlock content={part.content} />
                                  ) : part.render === "plain" ? (
                                    <PlainTextBlock content={part.content} />
                                  ) : (
                                    <RichTextBlock content={part.content} />
                                  )}
                                </ChatBubbleFrame>
                              ) : null}
                              {hasVoice ? (
                                <ChatBubbleFrame
                                  skin={bubbleSkin}
                                  className={`block w-fit max-w-full rounded-[18px] px-2 py-[2px] font-medium leading-[1.42] shadow-sm ${
                                    transparentBubbleEnabled
                                      ? TRANSPARENT_BUBBLE_CLASS
                                      : group.role === "benben"
                                        ? "border border-amber-100 bg-[#FFF7E6] text-[#3F2A11]"
                                        : resolveBubbleClass("assistant", assistantBubbleStyle)
                                  }`}
                                  style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
                                >
                                  <ChatAttachmentBlock attachments={audioAttachments} align="left" />
                                </ChatBubbleFrame>
                              ) : null}
                                <ChatVoiceTranscriptBlock
                                  attachments={audioAttachments}
                                  align="left"
                                  openTranscriptId={openVoiceTranscriptId}
                                  onTranscriptToggle={toggleVoiceTranscript}
                                  showToggle={false}
                                />
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

      <input
        ref={imageInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        multiple
        className="hidden"
        onChange={handleImageInputChange}
      />
      <input
        ref={documentInputRef}
        type="file"
        accept=".txt,.md,.markdown,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        onChange={handleDocumentInputChange}
      />
      <div className={`relative z-20 pb-[calc(env(safe-area-inset-bottom,0px)+8px)] ${chatFooterClass}`}>
          <div className={`relative z-10 mx-4 overflow-hidden rounded-[28px] border transition-all duration-300 ease-in-out ${chatPlusPanelClass} ${plusOpen ? "mb-2 h-[194px] opacity-100" : "mb-0 h-0 border-transparent opacity-0"}`}>
            <div className="grid grid-cols-4 gap-x-2 gap-y-3 px-4 pb-4 pt-4">
              <ChatActionButton label="图片" onClick={openImagePicker} />
              <ChatActionButton label="画画" onClick={openDoodleBoard} />
              <ChatActionButton label="文档" onClick={openDocumentPicker} />
              <ChatActionButton label="Real" active={realModeEnabled} onClick={toggleRealMode} />
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
          {pendingImageDrafts.length ? (
            <div className={`relative z-10 mx-4 mb-2 overflow-hidden rounded-[22px] border ${chatPlusPanelClass}`}>
              <div className="flex items-center justify-between px-3 pb-1 pt-2">
                <span className="text-[11px] font-semibold text-gray-600">图片顺序</span>
                <button
                  type="button"
                  className="rounded-full px-2 py-0.5 text-[11px] font-medium text-gray-400 active:bg-white/60 active:text-gray-700 disabled:opacity-35"
                  onClick={clearPendingImageDrafts}
                  disabled={mediaBusy}
                >
                  清空
                </button>
              </div>
              <div className="flex gap-2 overflow-x-auto px-3 pb-3 pt-1 [-webkit-overflow-scrolling:touch]">
                {pendingImageDrafts.map((draft, index) => (
                  <div key={draft.id} className="w-[58px] shrink-0">
                    <div className="relative aspect-[3/4] overflow-hidden rounded-[14px] bg-white/60 shadow-[0_4px_14px_rgba(15,23,42,0.10)]">
                      <img
                        src={draft.previewUrl}
                        alt={`待发送图片 ${index + 1}`}
                        className="h-full w-full object-cover"
                        draggable={false}
                      />
                      <span className="absolute left-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-black/45 px-1 text-[9px] font-semibold leading-4 text-white">
                        {index + 1}
                      </span>
                      <button
                        type="button"
                        className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-white/85 text-[14px] font-semibold leading-none text-gray-500 shadow-sm active:bg-white disabled:opacity-35"
                        onClick={() => removePendingImageDraft(draft.id)}
                        disabled={mediaBusy}
                        aria-label="移除图片"
                        title="移除图片"
                      >
                        ×
                      </button>
                    </div>
                    <div className="mt-1 flex items-center justify-center gap-1">
                      <button
                        type="button"
                        className="flex h-6 w-6 items-center justify-center rounded-full bg-white/55 text-[15px] font-semibold text-gray-500 active:bg-white disabled:opacity-30"
                        onClick={() => movePendingImageDraft(draft.id, -1)}
                        disabled={mediaBusy || index === 0}
                        aria-label="前移图片"
                        title="前移图片"
                      >
                        ‹
                      </button>
                      <button
                        type="button"
                        className="flex h-6 w-6 items-center justify-center rounded-full bg-white/55 text-[15px] font-semibold text-gray-500 active:bg-white disabled:opacity-30"
                        onClick={() => movePendingImageDraft(draft.id, 1)}
                        disabled={mediaBusy || index === pendingImageDrafts.length - 1}
                        aria-label="后移图片"
                        title="后移图片"
                      >
                        ›
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {quotedBubble ? (
            <div className="relative z-10 mx-5 mb-2 flex items-center gap-2 rounded-[18px] border border-white/45 bg-white/70 px-3 py-2 text-left text-[11px] font-medium text-gray-500 shadow-[0_8px_20px_rgba(15,23,42,0.07)] backdrop-blur-xl">
              <span className="shrink-0 text-gray-700">引用</span>
              <span className="min-w-0 flex-1 truncate">
                {quotedBubble.roleLabel}：{quotedBubble.text}
              </span>
              <button
                type="button"
                className="shrink-0 rounded-full px-1.5 text-[14px] leading-5 text-gray-400 active:bg-gray-100 active:text-gray-700"
                onClick={() => setQuotedBubble(null)}
                aria-label="取消引用"
                title="取消引用"
              >
                ×
              </button>
            </div>
          ) : null}
          <div className={`relative z-10 mx-4 mb-1 flex items-end gap-2 rounded-full px-2 py-1 ${chatInputBarClass}`}>
          <button
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${plusOpen ? chatFooterIconButtonActiveClass : chatFooterIconButtonClass}`}
            onClick={() => {
              setVoiceInputOpen(false);
              setPlusOpen((v) => !v);
            }}
          >
            <PlusIcon open={plusOpen} />
          </button>
          {voiceInputOpen ? (
            <button
              type="button"
              className={`flex min-h-[32px] flex-1 touch-none select-none items-center justify-center rounded-full px-3 py-1 text-[14px] font-semibold transition-colors ${
                chatVoiceCancelArmed
                  ? "bg-rose-500 text-white"
                  : recordingChatVoice
                    ? "bg-gray-900 text-white"
                    : `${chatInputShellClass} text-gray-700 active:bg-white/70`
              }`}
              style={{
                WebkitTouchCallout: "none",
                WebkitUserSelect: "none",
                touchAction: "none",
                userSelect: "none",
              } as React.CSSProperties}
              draggable={false}
              onPointerDown={handleChatVoicePressStart}
              onPointerMove={handleChatVoicePressMove}
              onPointerUp={handleChatVoicePressEnd}
              onPointerCancel={handleChatVoicePressCancel}
              onTouchStart={(event) => event.preventDefault()}
              onContextMenu={(event) => event.preventDefault()}
            >
              <span className="pointer-events-none select-none">
                {chatVoiceCancelArmed ? "松手取消" : recordingChatVoice ? "松开发送，上滑取消" : "按住说话"}
              </span>
            </button>
          ) : (
            <div className={`flex min-h-[32px] flex-1 items-center rounded-full px-3 py-1 ${chatInputShellClass}`}>
              <textarea
                ref={textInputRef}
                className="max-h-28 min-h-[22px] w-full resize-none bg-transparent font-medium leading-6 text-gray-900 outline-none placeholder:text-gray-400"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="输入消息..."
                rows={1}
                style={{ fontFamily: chatFontFamily, fontSize: `${chatContentFontSize}px` }}
              />
              <button
                type="button"
                className="ml-1.5 shrink-0 rounded-full p-1 text-gray-400 transition-colors active:text-gray-900"
                aria-label="打开语音输入"
                title="打开语音输入"
                onClick={toggleVoiceInputPanel}
                onContextMenu={(event) => event.preventDefault()}
              >
                <MicIconMini className="h-[19px] w-[19px] stroke-[2]" />
              </button>
            </div>
          )}
          {voiceInputOpen ? (
            <button
              type="button"
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${chatFooterIconButtonActiveClass}`}
              onClick={toggleVoiceInputPanel}
              aria-label="切回文字输入"
              title="切回文字输入"
            >
              <KeyboardIconMini />
            </button>
          ) : canCancelQueuedSend ? (
            <button
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-900 transition-opacity active:opacity-50 disabled:opacity-50"
              onClick={() => void cancelPendingPrivateInputAggregate()}
              aria-label="取消发送"
              title="取消发送"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-500">
                <span className="block h-[11px] w-[11px] rounded-[2px] bg-white" />
              </div>
            </button>
          ) : (
            <button
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-900 transition-opacity active:opacity-50 disabled:opacity-50"
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => void sendMessage()}
              disabled={!canSendCurrentInput || mediaBusy || (sending && !canSubmitWhileBusy)}
              aria-label="发送"
              title="发送"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-900">
                <ArrowUpIcon />
              </div>
            </button>
          )}
          </div>
        </div>
        {bubbleMenu ? (
          <>
            <button
              type="button"
              className="fixed inset-0 z-[70] cursor-default bg-transparent"
              aria-label="关闭气泡菜单"
              onClick={() => setBubbleMenu(null)}
            />
            <div
              className="fixed z-[71] rounded-[18px] bg-[#4b4b4b] px-2.5 py-2 text-white shadow-2xl"
              style={{
                left: `${bubbleMenu.x}px`,
                top: `${bubbleMenu.y}px`,
                gridTemplateColumns: `repeat(${bubbleMenuColumns}, minmax(58px, 1fr))`,
              }}
            >
              <div
                className="grid gap-1"
                style={{ gridTemplateColumns: `repeat(${bubbleMenuColumns}, minmax(58px, 1fr))` }}
              >
                <button
                  type="button"
                  className="rounded-[12px] px-2 py-2.5 text-center text-[13px] font-semibold text-white active:bg-white/15"
                  onClick={() => copyBubbleTarget(bubbleMenu)}
                >
                  复制
                </button>
                {bubbleMenu.hasVoice ? (
                  <button
                    type="button"
                    className="rounded-[12px] px-2 py-2.5 text-center text-[13px] font-semibold text-white active:bg-white/15"
                    onClick={() => revealBubbleTranscript(bubbleMenu)}
                  >
                    {bubbleMenu.transcriptId && openVoiceTranscriptId === bubbleMenu.transcriptId ? "收起文字" : "转文字"}
                  </button>
                ) : null}
                <button
                  type="button"
                  className="rounded-[12px] px-2 py-2.5 text-center text-[13px] font-semibold text-white active:bg-white/15"
                  onClick={() => quoteBubbleTarget(bubbleMenu)}
                >
                  引用
                </button>
                {bubbleMenu.canRetry ? (
                  <button
                    type="button"
                    className="rounded-[12px] px-2 py-2.5 text-center text-[13px] font-semibold text-[#ffe4e4] active:bg-white/15"
                    onClick={() => retryBubbleTarget(bubbleMenu)}
                  >
                    重试
                  </button>
                ) : null}
                {bubbleMenu.aggregateCanEditText ? (
                  <button
                    type="button"
                    className="rounded-[12px] px-2 py-2.5 text-center text-[13px] font-semibold text-white active:bg-white/15"
                    onClick={() => void deletePendingPrivateInput(bubbleMenu, "edit")}
                  >
                    编辑
                  </button>
                ) : null}
                {bubbleMenu.aggregateEditable ? (
                  <button
                    type="button"
                    className="rounded-[12px] px-2 py-2.5 text-center text-[13px] font-semibold text-[#ffe4e4] active:bg-white/15"
                    onClick={() => void deletePendingPrivateInput(bubbleMenu, "delete")}
                  >
                    删除
                  </button>
                ) : null}
              </div>
              <span className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 border-x-[8px] border-t-[9px] border-x-transparent border-t-[#4b4b4b]" />
            </div>
          </>
        ) : null}
        <DoodleBoardModal
          open={doodleBoardOpen}
          disabled={sending || mediaBusy}
          onClose={() => setDoodleBoardOpen(false)}
          onSend={sendDoodleImage}
        />
        {travelFormCard ? (
        <TravelPlanFormModal
          card={travelFormCard}
          sending={sending}
          onClose={() => setTravelFormCard(null)}
          onSubmit={(content) => {
            setTravelFormCard(null);
            void sendPreparedPrivateChatInput(prepareTravelFormPrivateChatInput(content));
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
