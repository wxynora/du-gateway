export const VOICE_CALL_PENDING_INVITE_KEY = "miniapp.voiceCall.pendingInvite";

export type IncomingVoiceCallInvite = {
  callId: string;
  title: string;
  callerName: string;
  openingLine: string;
  reason: string;
  urgency: "normal" | "important" | "urgent";
  timeoutSeconds: number;
  autoStartRecording: boolean;
  source: string;
};

function cleanText(value: unknown, fallback = ""): string {
  const text = String(value ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  return text || fallback;
}

function cleanUrgency(value: unknown): IncomingVoiceCallInvite["urgency"] {
  const raw = String(value ?? "").trim().toLowerCase();
  return raw === "important" || raw === "urgent" ? raw : "normal";
}

function cleanTimeoutSeconds(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 180;
  return Math.max(30, Math.min(900, Math.floor(n)));
}

function cleanBoolean(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  const raw = String(value ?? "").trim().toLowerCase();
  return raw === "1" || raw === "true" || raw === "yes" || raw === "y";
}

export function normalizeVoiceCallInvite(raw: unknown): IncomingVoiceCallInvite | null {
  const src = typeof raw === "string" ? parseInviteJson(raw) : raw;
  if (!src || typeof src !== "object") return null;
  const item = src as Record<string, unknown>;
  const callId = cleanText(item.callId ?? item.call_id);
  if (!callId) return null;
  return {
    callId,
    title: cleanText(item.title, "渡来电").slice(0, 60),
    callerName: cleanText(item.callerName ?? item.caller_name, "渡").slice(0, 24),
    openingLine: cleanText(item.openingLine ?? item.opening_line ?? item.voice ?? item.message).slice(0, 260),
    reason: cleanText(item.reason).slice(0, 240),
    urgency: cleanUrgency(item.urgency),
    timeoutSeconds: cleanTimeoutSeconds(item.timeoutSeconds ?? item.timeout_seconds),
    autoStartRecording: cleanBoolean(item.autoStartRecording ?? item.auto_start_recording ?? item.autoStart),
    source: cleanText(item.source).slice(0, 60),
  };
}

function parseInviteJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
