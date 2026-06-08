import { apiFetch, apiJson } from "../api";
import type { ChatAttachment } from "../chatMessages";

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

export function resolveRecorderMimeType(): string {
  if (typeof window === "undefined" || typeof window.MediaRecorder === "undefined") return "";
  const recorderCtor = window.MediaRecorder as typeof MediaRecorder;
  const supported = MIME_CANDIDATES.find((item) => {
    try {
      return typeof recorderCtor.isTypeSupported === "function" ? recorderCtor.isTypeSupported(item) : false;
    } catch {
      return false;
    }
  });
  return supported || "";
}

function audioExt(mimeType: string): string {
  const mime = String(mimeType || "").toLowerCase();
  if (mime.includes("mp4")) return "m4a";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mpeg") || mime.includes("mp3")) return "mp3";
  if (mime.includes("wav")) return "wav";
  return "webm";
}

function normalizeAttachment(value: any, fallbackKind: "image" | "audio"): ChatAttachment {
  const raw = value && typeof value === "object" ? value : {};
  return {
    id: String(raw.id || raw.remoteKey || raw.remoteUrl || `${fallbackKind}-${Date.now()}`),
    kind: raw.kind === "audio" || raw.kind === "image" ? raw.kind : fallbackKind,
    mime: String(raw.mime || ""),
    remoteKey: String(raw.remoteKey || ""),
    remoteUrl: String(raw.remoteUrl || ""),
    size: Number(raw.size || 0) || undefined,
    durationMs: Number(raw.durationMs || 0) || undefined,
    transcript: String(raw.transcript || "").trim() || undefined,
    createdAt: String(raw.createdAt || "").trim() || undefined,
  };
}

export async function uploadChatImage(file: File): Promise<ChatAttachment> {
  const form = new FormData();
  form.append("file", file, file.name || "image.jpg");
  form.append("kind", "image");
  form.append("mime_type", file.type || "image/jpeg");
  const resp = await apiFetch("/miniapp-api/chat-media/upload", { method: "POST", body: form });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
  return normalizeAttachment(data.attachment || data.media, "image");
}

export async function transcribeChatAudio(blob: Blob, mimeType: string): Promise<{
  text: string;
  attachment: ChatAttachment;
  audioObservations?: string;
  sttProvider?: string;
}> {
  const mime = mimeType || blob.type || "audio/webm";
  const form = new FormData();
  form.append("audio", blob, `voice.${audioExt(mime)}`);
  form.append("mime_type", mime);
  const resp = await apiFetch("/miniapp-api/chat-media/transcribe", { method: "POST", body: form });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
  return {
    text: String(data.text || "").trim(),
    attachment: normalizeAttachment(data.attachment || data.media, "audio"),
    audioObservations: String(data.audio_observations || "").trim() || undefined,
    sttProvider: String(data.stt_provider || "").trim() || undefined,
  };
}

export async function createDuReplyAudio(text: string): Promise<ChatAttachment | null> {
  const content = String(text || "").trim();
  if (!content) return null;
  const data = await apiJson<{ ok?: boolean; attachment?: any; media?: any; error?: string }>("/miniapp-api/chat-media/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: content, audio_format: "mp3" }),
  });
  if (!data?.ok) throw new Error(data?.error || "语音生成失败");
  return normalizeAttachment(data.attachment || data.media, "audio");
}
