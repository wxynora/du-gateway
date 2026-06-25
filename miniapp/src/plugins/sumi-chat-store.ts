import { Capacitor, registerPlugin } from "@capacitor/core";
import type { ChatOperation, ChatHistoryLocalStatRow, ChatHistoryMessage, ChatHistoryRow } from "../ui/chat/chatStore";

export interface SumiChatStorePlugin {
  getStatus(): Promise<{ ok?: boolean; schemaVersion?: number }>;
  upsertMessages(options: { deviceId: string; windowId: string; messages: ChatHistoryMessage[] }): Promise<void>;
  listMessages(options: { deviceId: string; windowId: string; limit?: number; before?: string }): Promise<{ messages?: ChatHistoryMessage[] }>;
  listHistoryRows(options: { windowIds: string[] }): Promise<{ rows?: ChatHistoryRow[] }>;
  inspectRows(): Promise<{ rows?: ChatHistoryLocalStatRow[] }>;
  latestMessages(options: { deviceId: string }): Promise<{ messages?: ChatHistoryMessage[] }>;
  migrateDevice(options: { oldDeviceId: string; newDeviceId: string }): Promise<void>;
  setMeta(options: { key: string; value: string }): Promise<void>;
  getMeta(options: { key: string }): Promise<{ value?: string }>;
  createDraftTurn(options: {
    deviceId: string;
    windowId: string;
    userMessage: ChatHistoryMessage;
    userMessages?: ChatHistoryMessage[];
    assistantMessage: ChatHistoryMessage;
    operation: ChatOperation;
  }): Promise<{ operation?: ChatOperation }>;
  attachJob(options: { operationId: string; jobId: string }): Promise<void>;
  completeOperation(options: { operationId: string; assistantMessage: ChatHistoryMessage }): Promise<void>;
  failOperation(options: { operationId: string; error: string; assistantMessage?: ChatHistoryMessage }): Promise<void>;
  getOperation(options: { operationId: string }): Promise<{ operation?: ChatOperation }>;
  listActiveOperations(options: { deviceId: string; windowId?: string }): Promise<{ operations?: ChatOperation[] }>;
}

const native = registerPlugin<SumiChatStorePlugin>("SumiChatStore");

export const SumiChatStore = {
  isAndroid(): boolean {
    return Capacitor.getPlatform() === "android";
  },

  getStatus(): Promise<{ ok?: boolean; schemaVersion?: number }> {
    return native.getStatus();
  },

  upsertMessages(options: { deviceId: string; windowId: string; messages: ChatHistoryMessage[] }): Promise<void> {
    return native.upsertMessages(options);
  },

  listMessages(options: { deviceId: string; windowId: string; limit?: number; before?: string }): Promise<{ messages?: ChatHistoryMessage[] }> {
    return native.listMessages(options);
  },

  listHistoryRows(options: { windowIds: string[] }): Promise<{ rows?: ChatHistoryRow[] }> {
    return native.listHistoryRows(options);
  },

  inspectRows(): Promise<{ rows?: ChatHistoryLocalStatRow[] }> {
    return native.inspectRows();
  },

  latestMessages(options: { deviceId: string }): Promise<{ messages?: ChatHistoryMessage[] }> {
    return native.latestMessages(options);
  },

  migrateDevice(options: { oldDeviceId: string; newDeviceId: string }): Promise<void> {
    return native.migrateDevice(options);
  },

  setMeta(options: { key: string; value: string }): Promise<void> {
    return native.setMeta(options);
  },

  getMeta(options: { key: string }): Promise<{ value?: string }> {
    return native.getMeta(options);
  },

  createDraftTurn(options: {
    deviceId: string;
    windowId: string;
    userMessage: ChatHistoryMessage;
    userMessages?: ChatHistoryMessage[];
    assistantMessage: ChatHistoryMessage;
    operation: ChatOperation;
  }): Promise<{ operation?: ChatOperation }> {
    return native.createDraftTurn(options);
  },

  attachJob(options: { operationId: string; jobId: string }): Promise<void> {
    return native.attachJob(options);
  },

  completeOperation(options: { operationId: string; assistantMessage: ChatHistoryMessage }): Promise<void> {
    return native.completeOperation(options);
  },

  failOperation(options: { operationId: string; error: string; assistantMessage?: ChatHistoryMessage }): Promise<void> {
    return native.failOperation(options);
  },

  getOperation(options: { operationId: string }): Promise<{ operation?: ChatOperation }> {
    return native.getOperation(options);
  },

  listActiveOperations(options: { deviceId: string; windowId?: string }): Promise<{ operations?: ChatOperation[] }> {
    return native.listActiveOperations(options);
  },
};
