import type { ChatDraftMessage } from "./chatMessages";

export function buildGroupDisplayWindowId(_primaryWindowId?: string): string {
  return "sumitalk-group";
}

export function sumitalkHistoryPath(displayWindowId?: string): string {
  const wid = String(displayWindowId || "").trim();
  return wid ? `/miniapp-api/sumitalk-history?window_id=${encodeURIComponent(wid)}` : "/miniapp-api/sumitalk-history";
}

export function sumitalkHistoryPayload(messages: ChatDraftMessage[], displayWindowId?: string): Record<string, unknown> {
  const wid = String(displayWindowId || "").trim();
  return wid ? { messages, window_id: wid } : { messages };
}
