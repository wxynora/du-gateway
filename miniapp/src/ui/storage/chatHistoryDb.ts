import { dexieChatStoreFallback } from "../chat/dexieChatStoreFallback";
import { nativeChatStore, isNativeChatStoreAvailable } from "../chat/nativeChatStore";
import {
  canonicalHistoryWindowId,
  mergeHistoryMessages,
  normalizeHistoryMessages,
  type ChatOperation,
  type ChatHistoryLocalStatRow,
  type ChatHistoryMessage,
  type ChatHistoryRow,
  type ChatHistoryStore,
} from "../chat/chatStore";

export type { ChatOperation, ChatHistoryLocalStatRow, ChatHistoryMessage, ChatHistoryRow };

const migratedNativeDeviceIds = new Set<string>();

async function preferredStore(): Promise<ChatHistoryStore> {
  return await isNativeChatStoreAvailable() ? nativeChatStore : dexieChatStoreFallback;
}

async function migrateDexieRowsToNative(deviceId: string): Promise<void> {
  const did = String(deviceId || "").trim();
  if (!did || migratedNativeDeviceIds.has(did) || !(await isNativeChatStoreAvailable())) return;
  migratedNativeDeviceIds.add(did);
  try {
    const rows = await dexieChatStoreFallback.readAllRows();
    if (!rows.length) return;
    for (const row of rows) {
      const rowDeviceId = String(row?.deviceId || did).trim() || did;
      const windowId = canonicalHistoryWindowId(row?.windowId || "");
      const messages = normalizeHistoryMessages(row?.messages || []);
      if (!rowDeviceId || !windowId || !messages.length) continue;
      const existing = await nativeChatStore.readLocalChatHistory(rowDeviceId, windowId);
      await nativeChatStore.writeLocalChatHistory(
        rowDeviceId,
        windowId,
        mergeHistoryMessages(existing, messages),
      );
    }
  } catch {
    migratedNativeDeviceIds.delete(did);
  }
}

async function withFallback<T>(nativeAction: () => Promise<T>, fallbackAction: () => Promise<T>): Promise<T> {
  if (!(await isNativeChatStoreAvailable())) return fallbackAction();
  try {
    return await nativeAction();
  } catch {
    return fallbackAction();
  }
}

export async function readLocalChatHistory(deviceId: string, windowId: string): Promise<ChatHistoryMessage[]> {
  const did = String(deviceId || "").trim();
  if (did) await migrateDexieRowsToNative(did);
  return withFallback(
    () => nativeChatStore.readLocalChatHistory(deviceId, windowId),
    () => dexieChatStoreFallback.readLocalChatHistory(deviceId, windowId),
  );
}

export async function readLocalChatHistoryRows(windowIds: string[]): Promise<ChatHistoryRow[]> {
  return withFallback(
    () => nativeChatStore.readLocalChatHistoryRows(windowIds),
    () => dexieChatStoreFallback.readLocalChatHistoryRows(windowIds),
  );
}

export async function readLatestLocalChatHistory(deviceId: string): Promise<ChatHistoryMessage[]> {
  const did = String(deviceId || "").trim();
  if (did) await migrateDexieRowsToNative(did);
  return withFallback(
    () => nativeChatStore.readLatestLocalChatHistory(deviceId),
    () => dexieChatStoreFallback.readLatestLocalChatHistory(deviceId),
  );
}

export async function inspectLocalChatHistoryRows(): Promise<ChatHistoryLocalStatRow[]> {
  return withFallback(
    () => nativeChatStore.inspectLocalChatHistoryRows(),
    () => dexieChatStoreFallback.inspectLocalChatHistoryRows(),
  );
}

export async function writeLocalChatHistory(deviceId: string, windowId: string, messages: ChatHistoryMessage[]): Promise<void> {
  const store = await preferredStore();
  await store.writeLocalChatHistory(deviceId, windowId, messages);
}

export async function migrateLocalChatHistoryDevice(oldDeviceId: string, newDeviceId: string): Promise<void> {
  await dexieChatStoreFallback.migrateLocalChatHistoryDevice(oldDeviceId, newDeviceId);
  if (await isNativeChatStoreAvailable()) {
    await nativeChatStore.migrateLocalChatHistoryDevice(oldDeviceId, newDeviceId).catch(() => {});
    migratedNativeDeviceIds.delete(String(oldDeviceId || "").trim());
    migratedNativeDeviceIds.delete(String(newDeviceId || "").trim());
    await migrateDexieRowsToNative(newDeviceId);
  }
}

export async function migrateLocalChatHistoriesToDevice(deviceId: string): Promise<void> {
  await dexieChatStoreFallback.migrateLocalChatHistoriesToDevice(deviceId);
  await migrateDexieRowsToNative(deviceId);
}

export async function createChatDraftTurn(args: {
  deviceId: string;
  windowId: string;
  userMessage: ChatHistoryMessage;
  assistantMessage: ChatHistoryMessage;
  operation: ChatOperation;
}): Promise<ChatOperation | null> {
  return withFallback(
    () => nativeChatStore.createDraftTurn(args),
    () => dexieChatStoreFallback.createDraftTurn(args),
  );
}

export async function attachChatJobToOperation(operationId: string, jobId: string): Promise<void> {
  await withFallback(
    () => nativeChatStore.attachJob(operationId, jobId),
    () => dexieChatStoreFallback.attachJob(operationId, jobId),
  );
}

export async function completeChatOperation(operationId: string, assistantMessage: ChatHistoryMessage): Promise<void> {
  await withFallback(
    () => nativeChatStore.completeOperation(operationId, assistantMessage),
    () => dexieChatStoreFallback.completeOperation(operationId, assistantMessage),
  );
}

export async function failChatOperation(operationId: string, error: string, assistantMessage?: ChatHistoryMessage): Promise<void> {
  await withFallback(
    () => nativeChatStore.failOperation(operationId, error, assistantMessage),
    () => dexieChatStoreFallback.failOperation(operationId, error, assistantMessage),
  );
}

export async function getChatOperation(operationId: string): Promise<ChatOperation | null> {
  return withFallback(
    () => nativeChatStore.getOperation(operationId),
    () => dexieChatStoreFallback.getOperation(operationId),
  );
}

export async function listActiveChatOperations(deviceId: string, windowId?: string): Promise<ChatOperation[]> {
  return withFallback(
    () => nativeChatStore.listActiveOperations(deviceId, windowId),
    () => dexieChatStoreFallback.listActiveOperations(deviceId, windowId),
  );
}
