import { nativeChatStore, isNativeChatStoreAvailable } from "../chat/nativeChatStore";
import { SumiChatStore } from "../../plugins/sumi-chat-store";
import {
  type ChatOperation,
  type ChatHistoryLocalStatRow,
  type ChatHistoryMessage,
  type ChatHistoryRow,
} from "../chat/chatStore";

export type { ChatOperation, ChatHistoryLocalStatRow, ChatHistoryMessage, ChatHistoryRow };

export type ChatStorageOverview = {
  deviceId: string;
  backend: "sqlite" | "unavailable";
  nativeAvailable: boolean;
  nativeSchemaVersion?: number;
  nativeError?: string;
  nativeRows: ChatHistoryLocalStatRow[];
  activeOperations: ChatOperation[];
  updatedAt: string;
};

async function readWithNativeFallback<T>(nativeAction: () => Promise<T>, fallbackValue: T): Promise<T> {
  if (!(await isNativeChatStoreAvailable())) return fallbackValue;
  try {
    return await nativeAction();
  } catch {
    return fallbackValue;
  }
}

async function mutateNativeOrThrow<T>(operation: string, nativeAction: () => Promise<T>, nonAndroidFallback: T): Promise<T> {
  if (!(await isNativeChatStoreAvailable())) {
    if (!SumiChatStore.isAndroid()) return nonAndroidFallback;
    throw new Error(`聊天本地存储不可用：${operation}`);
  }
  try {
    return await nativeAction();
  } catch (e: any) {
    throw new Error(`聊天本地存储写入失败：${operation}：${e?.message || e}`);
  }
}

export async function readLocalChatHistory(deviceId: string, windowId: string): Promise<ChatHistoryMessage[]> {
  return readWithNativeFallback(
    () => nativeChatStore.readLocalChatHistory(deviceId, windowId),
    [],
  );
}

export async function readLocalChatHistoryRows(windowIds: string[]): Promise<ChatHistoryRow[]> {
  return readWithNativeFallback(
    () => nativeChatStore.readLocalChatHistoryRows(windowIds),
    [],
  );
}

export async function readLatestLocalChatHistory(deviceId: string): Promise<ChatHistoryMessage[]> {
  return readWithNativeFallback(
    () => nativeChatStore.readLatestLocalChatHistory(deviceId),
    [],
  );
}

export async function inspectLocalChatHistoryRows(): Promise<ChatHistoryLocalStatRow[]> {
  return readWithNativeFallback(
    () => nativeChatStore.inspectLocalChatHistoryRows(),
    [],
  );
}

export async function inspectChatStorageOverview(deviceId: string): Promise<ChatStorageOverview> {
  const did = String(deviceId || "").trim();
  let nativeError = "";
  let nativeSchemaVersion: number | undefined;
  let nativeAvailable = false;
  try {
    if (SumiChatStore.isAndroid()) {
      const status = await SumiChatStore.getStatus();
      nativeAvailable = Boolean(status?.ok);
      nativeSchemaVersion = Number(status?.schemaVersion || 0) || undefined;
    }
  } catch (e: any) {
    nativeError = String(e?.message || e || "");
  }
  if (!nativeAvailable) {
    nativeAvailable = await isNativeChatStoreAvailable();
  }
  const [nativeRows, activeOperations] = await Promise.all([
    nativeAvailable ? nativeChatStore.inspectLocalChatHistoryRows().catch(() => []) : Promise.resolve([]),
    nativeAvailable ? nativeChatStore.listActiveOperations(did).catch(() => []) : Promise.resolve([]),
  ]);
  return {
    deviceId: did,
    backend: nativeAvailable ? "sqlite" : "unavailable",
    nativeAvailable,
    nativeSchemaVersion,
    nativeError,
    nativeRows,
    activeOperations,
    updatedAt: new Date().toISOString(),
  };
}

export async function writeLocalChatHistory(deviceId: string, windowId: string, messages: ChatHistoryMessage[]): Promise<void> {
  await mutateNativeOrThrow(
    "writeLocalChatHistory",
    () => nativeChatStore.writeLocalChatHistory(deviceId, windowId, messages),
    undefined,
  );
}

export async function deleteLocalChatHistoryMessages(deviceId: string, windowId: string, messageIds: string[]): Promise<void> {
  const ids = (Array.isArray(messageIds) ? messageIds : []).map((id) => String(id || "").trim()).filter(Boolean);
  if (!ids.length) return;
  await mutateNativeOrThrow(
    "deleteLocalChatHistoryMessages",
    () => nativeChatStore.deleteLocalChatHistoryMessages(deviceId, windowId, ids),
    undefined,
  );
}

export async function migrateLocalChatHistoryDevice(oldDeviceId: string, newDeviceId: string): Promise<void> {
  await mutateNativeOrThrow(
    "migrateLocalChatHistoryDevice",
    () => nativeChatStore.migrateLocalChatHistoryDevice(oldDeviceId, newDeviceId),
    undefined,
  );
}

export async function migrateLocalChatHistoriesToDevice(deviceId: string): Promise<void> {
  await mutateNativeOrThrow(
    "migrateLocalChatHistoriesToDevice",
    () => nativeChatStore.migrateLocalChatHistoriesToDevice(deviceId),
    undefined,
  );
}

export async function createChatDraftTurn(args: {
  deviceId: string;
  windowId: string;
  userMessage: ChatHistoryMessage;
  userMessages?: ChatHistoryMessage[];
  assistantMessage: ChatHistoryMessage;
  operation: ChatOperation;
}): Promise<ChatOperation | null> {
  return mutateNativeOrThrow(
    "createChatDraftTurn",
    () => nativeChatStore.createDraftTurn(args),
    null,
  );
}

export async function attachChatJobToOperation(operationId: string, jobId: string): Promise<void> {
  await mutateNativeOrThrow(
    "attachChatJobToOperation",
    () => nativeChatStore.attachJob(operationId, jobId),
    undefined,
  );
}

export async function completeChatOperation(operationId: string, assistantMessage: ChatHistoryMessage): Promise<void> {
  await mutateNativeOrThrow(
    "completeChatOperation",
    () => nativeChatStore.completeOperation(operationId, assistantMessage),
    undefined,
  );
}

export async function failChatOperation(operationId: string, error: string, assistantMessage?: ChatHistoryMessage): Promise<void> {
  await mutateNativeOrThrow(
    "failChatOperation",
    () => nativeChatStore.failOperation(operationId, error, assistantMessage),
    undefined,
  );
}

export async function getChatOperation(operationId: string): Promise<ChatOperation | null> {
  return readWithNativeFallback(
    () => nativeChatStore.getOperation(operationId),
    null,
  );
}

export async function listActiveChatOperations(deviceId: string, windowId?: string): Promise<ChatOperation[]> {
  return readWithNativeFallback(
    () => nativeChatStore.listActiveOperations(deviceId, windowId),
    [],
  );
}
