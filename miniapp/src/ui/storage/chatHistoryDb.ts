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

async function withNative<T>(nativeAction: () => Promise<T>, fallbackValue: T): Promise<T> {
  if (!(await isNativeChatStoreAvailable())) return fallbackValue;
  try {
    return await nativeAction();
  } catch {
    return fallbackValue;
  }
}

export async function readLocalChatHistory(deviceId: string, windowId: string): Promise<ChatHistoryMessage[]> {
  return withNative(
    () => nativeChatStore.readLocalChatHistory(deviceId, windowId),
    [],
  );
}

export async function readLocalChatHistoryRows(windowIds: string[]): Promise<ChatHistoryRow[]> {
  return withNative(
    () => nativeChatStore.readLocalChatHistoryRows(windowIds),
    [],
  );
}

export async function readLatestLocalChatHistory(deviceId: string): Promise<ChatHistoryMessage[]> {
  return withNative(
    () => nativeChatStore.readLatestLocalChatHistory(deviceId),
    [],
  );
}

export async function inspectLocalChatHistoryRows(): Promise<ChatHistoryLocalStatRow[]> {
  return withNative(
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
  await withNative(
    () => nativeChatStore.writeLocalChatHistory(deviceId, windowId, messages),
    undefined,
  );
}

export async function migrateLocalChatHistoryDevice(oldDeviceId: string, newDeviceId: string): Promise<void> {
  await withNative(
    () => nativeChatStore.migrateLocalChatHistoryDevice(oldDeviceId, newDeviceId),
    undefined,
  );
}

export async function migrateLocalChatHistoriesToDevice(deviceId: string): Promise<void> {
  await withNative(
    () => nativeChatStore.migrateLocalChatHistoriesToDevice(deviceId),
    undefined,
  );
}

export async function createChatDraftTurn(args: {
  deviceId: string;
  windowId: string;
  userMessage: ChatHistoryMessage;
  assistantMessage: ChatHistoryMessage;
  operation: ChatOperation;
}): Promise<ChatOperation | null> {
  return withNative(
    () => nativeChatStore.createDraftTurn(args),
    null,
  );
}

export async function attachChatJobToOperation(operationId: string, jobId: string): Promise<void> {
  await withNative(
    () => nativeChatStore.attachJob(operationId, jobId),
    undefined,
  );
}

export async function completeChatOperation(operationId: string, assistantMessage: ChatHistoryMessage): Promise<void> {
  await withNative(
    () => nativeChatStore.completeOperation(operationId, assistantMessage),
    undefined,
  );
}

export async function failChatOperation(operationId: string, error: string, assistantMessage?: ChatHistoryMessage): Promise<void> {
  await withNative(
    () => nativeChatStore.failOperation(operationId, error, assistantMessage),
    undefined,
  );
}

export async function getChatOperation(operationId: string): Promise<ChatOperation | null> {
  return withNative(
    () => nativeChatStore.getOperation(operationId),
    null,
  );
}

export async function listActiveChatOperations(deviceId: string, windowId?: string): Promise<ChatOperation[]> {
  return withNative(
    () => nativeChatStore.listActiveOperations(deviceId, windowId),
    [],
  );
}
