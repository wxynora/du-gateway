import { normalizeChatAttachments, normalizeChatDisplayParts, type ChatAttachment, type ChatDisplayPart } from "../chatMessages";

export type ChatHistoryMessage = {
  id: string;
  role: "user" | "assistant" | "benben";
  content: string;
  createdAt: string;
  status?: "pending" | "sent" | "failed";
  clientRequestId?: string;
  operationId?: string;
  jobId?: string;
  reasoning?: string;
  tokenCount?: {
    input?: number;
    output?: number;
    thinking?: number;
  };
  attachments?: ChatAttachment[];
  displayParts?: ChatDisplayPart[];
};

export type ChatHistoryRow = {
  key: string;
  deviceId: string;
  windowId: string;
  updatedAt: string;
  messages: ChatHistoryMessage[];
};

export type ChatHistoryLocalStatRow = {
  key: string;
  deviceId: string;
  windowId: string;
  updatedAt: string;
  count: number;
};

export type ChatOperationStatus = "draft" | "posting" | "running" | "done" | "failed" | "cancelled";

export type ChatOperation = {
  id: string;
  clientRequestId: string;
  deviceId: string;
  windowId: string;
  displayWindowId?: string;
  replyTarget: string;
  model?: string;
  retryPayload?: Record<string, any>;
  retryPayloadSize?: number;
  userMessageId: string;
  assistantMessageId?: string;
  benbenMessageId?: string;
  jobId?: string;
  status: ChatOperationStatus;
  error?: string;
  createdAt: string;
  updatedAt: string;
  lastAttemptAt?: string;
  retryCount?: number;
  schemaVersion?: number;
};

export interface ChatHistoryStore {
  readLocalChatHistory(deviceId: string, windowId: string): Promise<ChatHistoryMessage[]>;
  readLocalChatHistoryRows(windowIds: string[]): Promise<ChatHistoryRow[]>;
  readLatestLocalChatHistory(deviceId: string): Promise<ChatHistoryMessage[]>;
  inspectLocalChatHistoryRows(): Promise<ChatHistoryLocalStatRow[]>;
  writeLocalChatHistory(deviceId: string, windowId: string, messages: ChatHistoryMessage[]): Promise<void>;
  deleteLocalChatHistoryMessages(deviceId: string, windowId: string, messageIds: string[]): Promise<void>;
  migrateLocalChatHistoryDevice(oldDeviceId: string, newDeviceId: string): Promise<void>;
  migrateLocalChatHistoriesToDevice(deviceId: string): Promise<void>;
  createDraftTurn(args: {
    deviceId: string;
    windowId: string;
    userMessage: ChatHistoryMessage;
    userMessages?: ChatHistoryMessage[];
    assistantMessage: ChatHistoryMessage;
    operation: ChatOperation;
  }): Promise<ChatOperation | null>;
  attachJob(operationId: string, jobId: string): Promise<void>;
  completeOperation(operationId: string, assistantMessage: ChatHistoryMessage): Promise<void>;
  failOperation(operationId: string, error: string, assistantMessage?: ChatHistoryMessage): Promise<void>;
  getOperation(operationId: string): Promise<ChatOperation | null>;
  listActiveOperations(deviceId: string, windowId?: string): Promise<ChatOperation[]>;
}

export function historyKey(deviceId: string, windowId: string): string {
  return `${deviceId}::${windowId || "default"}`;
}

export function canonicalHistoryWindowId(windowId: string): string {
  const wid = String(windowId || "").trim();
  if (!wid) return "sumitalk-main";
  if (wid.startsWith("tg_")) return "sumitalk-main";
  return wid;
}

export function messageKey(message: ChatHistoryMessage): string {
  const id = String(message?.id || "").trim();
  if (id) return `id:${id}`;
  return [
    String(message?.role || "").trim(),
    String(message?.createdAt || "").trim(),
    String(message?.content || "").trim(),
  ].join("|");
}

export function mergeHistoryMessages(...groups: Array<ChatHistoryMessage[] | undefined>): ChatHistoryMessage[] {
  const out: ChatHistoryMessage[] = [];
  const seen = new Set<string>();
  for (const group of groups) {
    for (const message of Array.isArray(group) ? group : []) {
      if (!message || typeof message !== "object") continue;
      const key = messageKey(message);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(message);
    }
  }
  out.sort((a, b) => {
    const at = Date.parse(String(a?.createdAt || ""));
    const bt = Date.parse(String(b?.createdAt || ""));
    const diff = (Number.isFinite(at) ? at : 0) - (Number.isFinite(bt) ? bt : 0);
    return diff || String(a?.id || "").localeCompare(String(b?.id || ""));
  });
  return out;
}

export function normalizeHistoryMessages(messages: ChatHistoryMessage[]): ChatHistoryMessage[] {
  return (Array.isArray(messages) ? messages : [])
    .filter((message): message is ChatHistoryMessage => Boolean(message && typeof message === "object"))
    .map((message) => {
      const role = message.role;
      const rawStatus = String(message.status || "").trim().toLowerCase();
      const status = rawStatus === "pending" || rawStatus === "sent" || rawStatus === "failed" ? rawStatus as ChatHistoryMessage["status"] : undefined;
      const attachments = normalizeChatAttachments((message as any).attachments);
      const displayParts = normalizeChatDisplayParts((message as any).displayParts || (message as any).display_parts);
      return {
        id: String(message.id || "").trim(),
        role,
        content: String(message.content || ""),
        createdAt: String(message.createdAt || "").trim() || new Date().toISOString(),
        ...(status ? { status } : {}),
        ...(message.clientRequestId ? { clientRequestId: String(message.clientRequestId || "").trim() } : {}),
        ...(message.operationId ? { operationId: String(message.operationId || "").trim() } : {}),
        ...(message.jobId ? { jobId: String(message.jobId || "").trim() } : {}),
        ...(message.reasoning ? { reasoning: String(message.reasoning || "") } : {}),
        ...(message.tokenCount ? { tokenCount: message.tokenCount } : {}),
        ...(attachments.length ? { attachments } : {}),
        ...(displayParts.length ? { displayParts } : {}),
      };
    })
    .filter((message) => (
      message.id
      && ["user", "assistant", "benben"].includes(message.role)
      && (
        message.content.trim()
        || (message.attachments?.length || 0) > 0
        || (message.displayParts?.length || 0) > 0
        || (message.role === "assistant" && message.status === "pending")
      )
    ));
}
