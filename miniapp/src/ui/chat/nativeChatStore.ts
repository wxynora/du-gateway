import { SumiChatStore } from "../../plugins/sumi-chat-store";
import {
  normalizeHistoryMessages,
  type ChatOperation,
  type ChatHistoryLocalStatRow,
  type ChatHistoryMessage,
  type ChatHistoryRow,
  type ChatHistoryStore,
} from "./chatStore";

let availabilityCache: boolean | null = null;

export async function isNativeChatStoreAvailable(): Promise<boolean> {
  if (!SumiChatStore.isAndroid()) return false;
  if (availabilityCache != null) return availabilityCache;
  try {
    const status = await SumiChatStore.getStatus();
    availabilityCache = Boolean(status?.ok);
  } catch {
    availabilityCache = false;
  }
  return availabilityCache;
}

export const nativeChatStore: ChatHistoryStore = {
  async readLocalChatHistory(deviceId: string, windowId: string): Promise<ChatHistoryMessage[]> {
    const r = await SumiChatStore.listMessages({ deviceId, windowId, limit: 1000 });
    return normalizeHistoryMessages(r.messages || []);
  },

  async readLocalChatHistoryRows(windowIds: string[]): Promise<ChatHistoryRow[]> {
    const r = await SumiChatStore.listHistoryRows({ windowIds });
    return (Array.isArray(r.rows) ? r.rows : []).map((row) => ({
      key: String(row?.key || ""),
      deviceId: String(row?.deviceId || ""),
      windowId: String(row?.windowId || ""),
      updatedAt: String(row?.updatedAt || ""),
      messages: normalizeHistoryMessages(row?.messages || []),
    }));
  },

  async readLatestLocalChatHistory(deviceId: string): Promise<ChatHistoryMessage[]> {
    const r = await SumiChatStore.latestMessages({ deviceId });
    return normalizeHistoryMessages(r.messages || []);
  },

  async inspectLocalChatHistoryRows(): Promise<ChatHistoryLocalStatRow[]> {
    const r = await SumiChatStore.inspectRows();
    return (Array.isArray(r.rows) ? r.rows : []).map((row) => ({
      key: String(row?.key || ""),
      deviceId: String(row?.deviceId || ""),
      windowId: String(row?.windowId || ""),
      updatedAt: String(row?.updatedAt || ""),
      count: Number(row?.count || 0),
    }));
  },

  async writeLocalChatHistory(deviceId: string, windowId: string, messages: ChatHistoryMessage[]): Promise<void> {
    await SumiChatStore.upsertMessages({
      deviceId,
      windowId,
      messages: normalizeHistoryMessages(messages),
    });
  },

  async deleteLocalChatHistoryMessages(deviceId: string, windowId: string, messageIds: string[]): Promise<void> {
    const now = new Date().toISOString();
    const ids = messageIds.map((id) => String(id || "").trim()).filter(Boolean);
    if (!ids.length) return;
    await SumiChatStore.upsertMessages({
      deviceId,
      windowId,
      messages: ids.map((id) => ({
        id,
        role: "user",
        content: "deleted",
        createdAt: now,
        updatedAt: now,
        status: "sent",
        deletedAt: now,
      })) as ChatHistoryMessage[],
    });
  },

  async migrateLocalChatHistoryDevice(oldDeviceId: string, newDeviceId: string): Promise<void> {
    await SumiChatStore.migrateDevice({ oldDeviceId, newDeviceId });
  },

  async migrateLocalChatHistoriesToDevice(_deviceId: string): Promise<void> {
    // Native rows are already keyed by device.
  },

  async createDraftTurn(args): Promise<ChatOperation | null> {
    const r = await SumiChatStore.createDraftTurn(args);
    return normalizeOperation(r.operation);
  },

  async attachJob(operationId: string, jobId: string): Promise<void> {
    await SumiChatStore.attachJob({ operationId, jobId });
  },

  async completeOperation(operationId: string, assistantMessage: ChatHistoryMessage): Promise<void> {
    await SumiChatStore.completeOperation({ operationId, assistantMessage });
  },

  async failOperation(operationId: string, error: string, assistantMessage?: ChatHistoryMessage): Promise<void> {
    await SumiChatStore.failOperation({ operationId, error, assistantMessage });
  },

  async getOperation(operationId: string): Promise<ChatOperation | null> {
    const r = await SumiChatStore.getOperation({ operationId });
    return normalizeOperation(r.operation);
  },

  async listActiveOperations(deviceId: string, windowId?: string): Promise<ChatOperation[]> {
    const r = await SumiChatStore.listActiveOperations({ deviceId, windowId });
    return (Array.isArray(r.operations) ? r.operations : [])
      .map((operation) => normalizeOperation(operation))
      .filter((operation): operation is ChatOperation => Boolean(operation));
  },
};

function normalizeOperation(raw: any): ChatOperation | null {
  if (!raw || typeof raw !== "object") return null;
  const id = String(raw.id || "").trim();
  const clientRequestId = String(raw.clientRequestId || raw.client_request_id || "").trim();
  const deviceId = String(raw.deviceId || raw.device_id || "").trim();
  const windowId = String(raw.windowId || raw.window_id || "").trim();
  if (!id || !clientRequestId || !deviceId || !windowId) return null;
  const statusText = String(raw.status || "draft").trim().toLowerCase();
  const status = ["draft", "posting", "running", "done", "failed", "cancelled"].includes(statusText)
    ? statusText as ChatOperation["status"]
    : "draft";
  return {
    id,
    clientRequestId,
    deviceId,
    windowId,
    displayWindowId: String(raw.displayWindowId || raw.display_window_id || "").trim() || undefined,
    replyTarget: String(raw.replyTarget || raw.reply_target || deviceId).trim(),
    model: String(raw.model || "").trim() || undefined,
    retryPayload: raw.retryPayload && typeof raw.retryPayload === "object" ? raw.retryPayload : undefined,
    retryPayloadSize: Number(raw.retryPayloadSize || raw.retry_payload_size || 0),
    userMessageId: String(raw.userMessageId || raw.user_message_id || "").trim(),
    assistantMessageId: String(raw.assistantMessageId || raw.assistant_message_id || "").trim() || undefined,
    benbenMessageId: String(raw.benbenMessageId || raw.benben_message_id || "").trim() || undefined,
    jobId: String(raw.jobId || raw.job_id || "").trim() || undefined,
    status,
    error: String(raw.error || "").trim() || undefined,
    createdAt: String(raw.createdAt || raw.created_at || "").trim(),
    updatedAt: String(raw.updatedAt || raw.updated_at || "").trim(),
    lastAttemptAt: String(raw.lastAttemptAt || raw.last_attempt_at || "").trim() || undefined,
    retryCount: Number(raw.retryCount || raw.retry_count || 0),
    schemaVersion: Number(raw.schemaVersion || raw.schema_version || 1),
  };
}
