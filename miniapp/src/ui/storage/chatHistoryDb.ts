import Dexie, { type Table } from "dexie";

export type ChatHistoryMessage = {
  id: string;
  role: "user" | "assistant" | "benben";
  content: string;
  createdAt: string;
  status?: "pending" | "sent" | "failed";
  reasoning?: string;
  tokenCount?: {
    input?: number;
    output?: number;
  };
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

class MiniappChatHistoryDb extends Dexie {
  histories!: Table<ChatHistoryRow, string>;

  constructor() {
    super("miniapp_chat_history_db");
    this.version(1).stores({
      histories: "&key, deviceId, windowId, updatedAt",
    });
  }
}

const db = new MiniappChatHistoryDb();

function historyKey(deviceId: string, windowId: string): string {
  return `${deviceId}::${windowId || "default"}`;
}

function canonicalHistoryWindowId(windowId: string): string {
  const wid = String(windowId || "").trim();
  if (!wid) return "sumitalk-main";
  if (wid.startsWith("tg_")) return "sumitalk-main";
  return wid;
}

function messageKey(message: ChatHistoryMessage): string {
  const id = String(message?.id || "").trim();
  if (id) return `id:${id}`;
  return [
    String(message?.role || "").trim(),
    String(message?.createdAt || "").trim(),
    String(message?.content || "").trim(),
  ].join("|");
}

function mergeHistoryMessages(...groups: Array<ChatHistoryMessage[] | undefined>): ChatHistoryMessage[] {
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

export async function readLocalChatHistory(deviceId: string, windowId: string): Promise<ChatHistoryMessage[]> {
  const did = String(deviceId || "").trim();
  const wid = String(windowId || "").trim();
  if (!did || !wid) return [];
  try {
    const row = await db.histories.get(historyKey(did, wid));
    return Array.isArray(row?.messages) ? row.messages : [];
  } catch {
    return [];
  }
}

export async function readLocalChatHistoryRows(windowIds: string[]): Promise<ChatHistoryRow[]> {
  const wanted = new Set(
    (Array.isArray(windowIds) ? windowIds : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
  if (!wanted.size) return [];
  try {
    const rows = await db.histories.toArray();
    return rows.filter((row) => wanted.has(String(row?.windowId || "").trim()));
  } catch {
    return [];
  }
}

export async function readLatestLocalChatHistory(deviceId: string): Promise<ChatHistoryMessage[]> {
  const did = String(deviceId || "").trim();
  if (!did) return [];
  try {
    const rows = await db.histories.where("deviceId").equals(did).sortBy("updatedAt");
    const latest = rows.length ? rows[rows.length - 1] : null;
    return Array.isArray(latest?.messages) ? latest.messages : [];
  } catch {
    return [];
  }
}

export async function inspectLocalChatHistoryRows(): Promise<ChatHistoryLocalStatRow[]> {
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
}

export async function writeLocalChatHistory(deviceId: string, windowId: string, messages: ChatHistoryMessage[]): Promise<void> {
  const did = String(deviceId || "").trim();
  const wid = String(windowId || "").trim();
  if (!did || !wid) return;
  const safeMessages = Array.isArray(messages) ? messages : [];
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
}

export async function migrateLocalChatHistoryDevice(oldDeviceId: string, newDeviceId: string): Promise<void> {
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
}

export async function migrateLocalChatHistoriesToDevice(deviceId: string): Promise<void> {
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
}
