import Dexie, { type Table } from "dexie";
import {
  canonicalHistoryWindowId,
  historyKey,
  mergeHistoryMessages,
  normalizeHistoryMessages,
  type ChatOperation,
  type ChatHistoryLocalStatRow,
  type ChatHistoryMessage,
  type ChatHistoryRow,
  type ChatHistoryStore,
} from "./chatStore";

class MiniappChatHistoryDb extends Dexie {
  histories!: Table<ChatHistoryRow, string>;
  operations!: Table<ChatOperation, string>;

  constructor() {
    super("miniapp_chat_history_db");
    this.version(1).stores({
      histories: "&key, deviceId, windowId, updatedAt",
    });
    this.version(2).stores({
      histories: "&key, deviceId, windowId, updatedAt",
      operations: "&id, clientRequestId, deviceId, windowId, replyTarget, status, updatedAt, [clientRequestId+windowId+replyTarget]",
    });
  }
}

const db = new MiniappChatHistoryDb();

async function readAllRows(): Promise<ChatHistoryRow[]> {
  try {
    return await db.histories.toArray();
  } catch {
    return [];
  }
}

export const dexieChatStoreFallback: ChatHistoryStore & { readAllRows: () => Promise<ChatHistoryRow[]> } = {
  readAllRows,

  async readLocalChatHistory(deviceId: string, windowId: string): Promise<ChatHistoryMessage[]> {
    const did = String(deviceId || "").trim();
    const wid = String(windowId || "").trim();
    if (!did || !wid) return [];
    try {
      const row = await db.histories.get(historyKey(did, wid));
      return normalizeHistoryMessages(Array.isArray(row?.messages) ? row.messages : []);
    } catch {
      return [];
    }
  },

  async readLocalChatHistoryRows(windowIds: string[]): Promise<ChatHistoryRow[]> {
    const wanted = new Set(
      (Array.isArray(windowIds) ? windowIds : [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    );
    if (!wanted.size) return [];
    try {
      const rows = await db.histories.toArray();
      return rows
        .filter((row) => wanted.has(String(row?.windowId || "").trim()))
        .map((row) => ({ ...row, messages: normalizeHistoryMessages(row.messages || []) }));
    } catch {
      return [];
    }
  },

  async readLatestLocalChatHistory(deviceId: string): Promise<ChatHistoryMessage[]> {
    const did = String(deviceId || "").trim();
    if (!did) return [];
    try {
      const rows = await db.histories.where("deviceId").equals(did).sortBy("updatedAt");
      const latest = rows.length ? rows[rows.length - 1] : null;
      return normalizeHistoryMessages(Array.isArray(latest?.messages) ? latest.messages : []);
    } catch {
      return [];
    }
  },

  async inspectLocalChatHistoryRows(): Promise<ChatHistoryLocalStatRow[]> {
    try {
      const rows = await db.histories.toArray();
      return rows
        .map((row) => ({
          key: String(row?.key || ""),
          deviceId: String(row?.deviceId || ""),
          windowId: String(row?.windowId || ""),
          updatedAt: String(row?.updatedAt || ""),
          count: Array.isArray(row?.messages) ? row.messages.length : 0,
        }))
        .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
    } catch {
      return [];
    }
  },

  async writeLocalChatHistory(deviceId: string, windowId: string, messages: ChatHistoryMessage[]): Promise<void> {
    const did = String(deviceId || "").trim();
    const wid = String(windowId || "").trim();
    if (!did || !wid) return;
    const safeMessages = normalizeHistoryMessages(Array.isArray(messages) ? messages : []);
    try {
      await db.histories.put({
        key: historyKey(did, wid),
        deviceId: did,
        windowId: wid,
        updatedAt: new Date().toISOString(),
        messages: safeMessages,
      });
    } catch {
      // Ignore storage errors to avoid blocking chat flow.
    }
  },

  async migrateLocalChatHistoryDevice(oldDeviceId: string, newDeviceId: string): Promise<void> {
    const oldId = String(oldDeviceId || "").trim();
    const newId = String(newDeviceId || "").trim();
    if (!oldId || !newId || oldId === newId) return;
    try {
      const rows = await db.histories.where("deviceId").equals(oldId).toArray();
      if (!rows.length) return;
      await db.transaction("rw", db.histories, async () => {
        for (const row of rows) {
          const targetWindowId = canonicalHistoryWindowId(row.windowId);
          const key = historyKey(newId, targetWindowId);
          const existing = await db.histories.get(key);
          await db.histories.put({
            ...row,
            key,
            deviceId: newId,
            windowId: targetWindowId,
            updatedAt: new Date().toISOString(),
            messages: mergeHistoryMessages(existing?.messages, row.messages),
          });
          await db.histories.delete(row.key);
        }
      });
    } catch {
      // Ignore migration errors to avoid blocking chat flow.
    }
  },

  async migrateLocalChatHistoriesToDevice(deviceId: string): Promise<void> {
    const did = String(deviceId || "").trim();
    if (!did) return;
    try {
      const rows = await db.histories.toArray();
      if (!rows.length) return;
      await db.transaction("rw", db.histories, async () => {
        for (const row of rows) {
          const sourceKey = String(row?.key || "").trim();
          const targetWindowId = canonicalHistoryWindowId(row.windowId);
          const key = historyKey(did, targetWindowId);
          if (!key) continue;
          const existing = await db.histories.get(key);
          await db.histories.put({
            ...row,
            key,
            deviceId: did,
            windowId: targetWindowId,
            updatedAt: new Date().toISOString(),
            messages: mergeHistoryMessages(existing?.messages, row.messages),
          });
          if (sourceKey && sourceKey !== key) {
            await db.histories.delete(sourceKey);
          }
        }
      });
    } catch {
      // Ignore migration errors to avoid blocking chat flow.
    }
  },

  async createDraftTurn(args): Promise<ChatOperation | null> {
    const did = String(args?.deviceId || "").trim();
    const wid = String(args?.windowId || "").trim();
    const operation = normalizeOperation({ ...args?.operation, deviceId: did, windowId: wid });
    if (!did || !wid || !operation?.id || !operation.clientRequestId) return null;
    try {
      let stored: ChatOperation | null = null;
      await db.transaction("rw", db.histories, db.operations, async () => {
        const existing = await db.operations
          .where("[clientRequestId+windowId+replyTarget]")
          .equals([operation.clientRequestId, wid, operation.replyTarget])
          .first();
        if (existing) {
          stored = normalizeOperation(existing);
          return;
        }
        const current = await db.histories.get(historyKey(did, wid));
        const messages = mergeHistoryMessages(
          current?.messages,
          normalizeHistoryMessages([args.userMessage, args.assistantMessage]),
        );
        await db.histories.put({
          key: historyKey(did, wid),
          deviceId: did,
          windowId: wid,
          updatedAt: new Date().toISOString(),
          messages,
        });
        await db.operations.put(operation);
        stored = operation;
      });
      return stored;
    } catch {
      return null;
    }
  },

  async attachJob(operationId: string, jobId: string): Promise<void> {
    const opId = String(operationId || "").trim();
    const jid = String(jobId || "").trim();
    if (!opId || !jid) return;
    try {
      await db.transaction("rw", db.histories, db.operations, async () => {
        const op = normalizeOperation(await db.operations.get(opId));
        if (!op) return;
        const now = new Date().toISOString();
        await db.operations.update(opId, {
          jobId: jid,
          status: "running",
          updatedAt: now,
          lastAttemptAt: now,
          retryCount: (op.retryCount || 0) + 1,
        });
        await patchHistoryMessage(op.deviceId, op.windowId, op.assistantMessageId || "", {
          jobId: jid,
          status: "pending",
          operationId: op.id,
        });
      });
    } catch {}
  },

  async completeOperation(operationId: string, assistantMessage: ChatHistoryMessage): Promise<void> {
    const opId = String(operationId || "").trim();
    if (!opId) return;
    try {
      await db.transaction("rw", db.histories, db.operations, async () => {
        const op = normalizeOperation(await db.operations.get(opId));
        if (!op) return;
        const now = new Date().toISOString();
        await patchHistoryMessage(op.deviceId, op.windowId, op.assistantMessageId || assistantMessage.id, {
          ...assistantMessage,
          id: op.assistantMessageId || assistantMessage.id,
          role: "assistant",
          status: "sent",
          clientRequestId: op.clientRequestId,
          operationId: op.id,
          jobId: assistantMessage.jobId || op.jobId,
        });
        await db.operations.update(opId, {
          status: "done",
          error: "",
          updatedAt: now,
          jobId: assistantMessage.jobId || op.jobId || "",
        });
      });
    } catch {}
  },

  async failOperation(operationId: string, error: string, assistantMessage?: ChatHistoryMessage): Promise<void> {
    const opId = String(operationId || "").trim();
    if (!opId) return;
    try {
      await db.transaction("rw", db.histories, db.operations, async () => {
        const op = normalizeOperation(await db.operations.get(opId));
        if (!op) return;
        const now = new Date().toISOString();
        if (assistantMessage) {
          await patchHistoryMessage(op.deviceId, op.windowId, op.assistantMessageId || assistantMessage.id, {
            ...assistantMessage,
            id: op.assistantMessageId || assistantMessage.id,
            role: "assistant",
            status: "failed",
            clientRequestId: op.clientRequestId,
            operationId: op.id,
            jobId: assistantMessage.jobId || op.jobId,
          });
        }
        await db.operations.update(opId, {
          status: "failed",
          error: String(error || "").trim(),
          updatedAt: now,
        });
      });
    } catch {}
  },

  async getOperation(operationId: string): Promise<ChatOperation | null> {
    const opId = String(operationId || "").trim();
    if (!opId) return null;
    try {
      return normalizeOperation(await db.operations.get(opId));
    } catch {
      return null;
    }
  },

  async listActiveOperations(deviceId: string, windowId?: string): Promise<ChatOperation[]> {
    const did = String(deviceId || "").trim();
    const wid = String(windowId || "").trim();
    if (!did) return [];
    try {
      const rows = await db.operations.where("deviceId").equals(did).toArray();
      return rows
        .map((row) => normalizeOperation(row))
        .filter((row): row is ChatOperation => Boolean(row))
        .filter((row) => !wid || row.windowId === wid)
        .filter((row) => ["draft", "posting", "running"].includes(row.status))
        .sort((a, b) => String(a.updatedAt || "").localeCompare(String(b.updatedAt || "")));
    } catch {
      return [];
    }
  },
};

function normalizeOperation(raw: any): ChatOperation | null {
  if (!raw || typeof raw !== "object") return null;
  const id = String(raw.id || "").trim();
  const clientRequestId = String(raw.clientRequestId || raw.client_request_id || "").trim();
  const deviceId = String(raw.deviceId || raw.device_id || "").trim();
  const windowId = String(raw.windowId || raw.window_id || "").trim();
  const replyTarget = String(raw.replyTarget || raw.reply_target || deviceId).trim();
  const statusText = String(raw.status || "draft").trim().toLowerCase();
  const status = ["draft", "posting", "running", "done", "failed", "cancelled"].includes(statusText)
    ? statusText as ChatOperation["status"]
    : "draft";
  if (!id || !clientRequestId || !deviceId || !windowId) return null;
  const retryPayload = raw.retryPayload && typeof raw.retryPayload === "object"
    ? raw.retryPayload
    : raw.retry_payload_json && typeof raw.retry_payload_json === "string"
      ? parseJsonObject(raw.retry_payload_json)
      : undefined;
  const now = new Date().toISOString();
  return {
    id,
    clientRequestId,
    deviceId,
    windowId,
    displayWindowId: String(raw.displayWindowId || raw.display_window_id || windowId).trim() || undefined,
    replyTarget,
    model: String(raw.model || "").trim() || undefined,
    retryPayload,
    retryPayloadSize: Number(raw.retryPayloadSize || raw.retry_payload_size || JSON.stringify(retryPayload || {}).length || 0),
    userMessageId: String(raw.userMessageId || raw.user_message_id || "").trim(),
    assistantMessageId: String(raw.assistantMessageId || raw.assistant_message_id || "").trim() || undefined,
    benbenMessageId: String(raw.benbenMessageId || raw.benben_message_id || "").trim() || undefined,
    jobId: String(raw.jobId || raw.job_id || "").trim() || undefined,
    status,
    error: String(raw.error || "").trim() || undefined,
    createdAt: String(raw.createdAt || raw.created_at || now).trim() || now,
    updatedAt: String(raw.updatedAt || raw.updated_at || now).trim() || now,
    lastAttemptAt: String(raw.lastAttemptAt || raw.last_attempt_at || "").trim() || undefined,
    retryCount: Number(raw.retryCount || raw.retry_count || 0),
    schemaVersion: Number(raw.schemaVersion || raw.schema_version || 1),
  };
}

function parseJsonObject(text: string): Record<string, any> | undefined {
  try {
    const parsed = JSON.parse(text || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
}

async function patchHistoryMessage(
  deviceId: string,
  windowId: string,
  messageId: string,
  patch: Partial<ChatHistoryMessage>,
): Promise<void> {
  const did = String(deviceId || "").trim();
  const wid = String(windowId || "").trim();
  const mid = String(messageId || "").trim();
  if (!did || !wid || !mid) return;
  const row = await db.histories.get(historyKey(did, wid));
  const currentMessages = normalizeHistoryMessages(row?.messages || []);
  let replaced = false;
  const messages = currentMessages.map((message) => {
    if (message.id !== mid) return message;
    replaced = true;
    return normalizeHistoryMessages([{ ...message, ...patch, id: message.id, createdAt: message.createdAt }])[0] || message;
  });
  if (!replaced && patch.id) {
    messages.push(...normalizeHistoryMessages([patch as ChatHistoryMessage]));
  }
  await db.histories.put({
    key: historyKey(did, wid),
    deviceId: did,
    windowId: wid,
    updatedAt: new Date().toISOString(),
    messages: mergeHistoryMessages(messages),
  });
}
