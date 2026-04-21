import Dexie, { type Table } from "dexie";

export type ChatHistoryMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  reasoning?: string;
  tokenCount?: {
    input?: number;
    output?: number;
  };
};

type ChatHistoryRow = {
  key: string;
  deviceId: string;
  windowId: string;
  updatedAt: string;
  messages: ChatHistoryMessage[];
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
