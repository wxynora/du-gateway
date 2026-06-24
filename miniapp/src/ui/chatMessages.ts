import { firstSystemCard, formatAlarmTime, splitSystemCardSegments, type SumiTalkSystemCard } from "./sumitalkSystemCards";

export const CHAT_FONT_KEYS = ["system", "huninn", "pingfang", "yahei", "serif", "script"] as const;
export type ChatFontKey = typeof CHAT_FONT_KEYS[number];
export type ChatTimeFormat = "hhmm" | "ampm";

export type ChatRole = "user" | "assistant" | "benben";
export type ChatAttachmentKind = "image" | "audio" | "document";
export type ChatAttachment = {
  id: string;
  kind: ChatAttachmentKind;
  name?: string;
  mime?: string;
  remoteKey?: string;
  remoteUrl?: string;
  localUrl?: string;
  thumbUrl?: string;
  previewUrl?: string;
  width?: number;
  height?: number;
  durationMs?: number;
  size?: number;
  transcript?: string;
  textPreview?: string;
  alt?: string;
  createdAt?: string;
};
export type ChatDraftMessage = {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  status?: "pending" | "sent" | "failed";
  clientRequestId?: string;
  operationId?: string;
  jobId?: string;
  reasoning?: string;
  tokenCount?: {
    input?: number;
    output?: number;
  };
  attachments?: ChatAttachment[];
};

const JSON_TEXT_FIELD_RE = /"text"\s*:\s*"((?:\\.|[^"\\])*)"/;
const LEAKED_TEXT_PREFIX_RE = /^\s*\{?\s*"?text"?\s*[:：]\s*"?/i;
const PAUSE_NOTE_RE = /（\s*停顿了约\s*\d+(?:\.\d+)?\s*秒\s*）/g;
const FILLER_ONLY_RE = /^[嗯啊哦呃唔诶哎哼]+$/;

function cleanShortText(value: any, limit = 4000): string {
  const max = Math.max(1, Number(limit) || 4000);
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .slice(0, max);
}

function decodeJsonStringLiteral(value: string): string {
  try {
    return String(JSON.parse(`"${String(value || "")}"`) || "");
  } catch {
    return String(value || "");
  }
}

function extractJsonObjectText(value: string): string {
  let raw = cleanShortText(value);
  if (!raw) return "";
  if (raw.startsWith("```")) {
    raw = raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/g, "").trim();
  }
  const candidates = [raw];
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start >= 0 && end > start) candidates.push(raw.slice(start, end + 1));
  for (const item of candidates) {
    try {
      const parsed = JSON.parse(item);
      if (parsed && typeof parsed === "object" && typeof parsed.text === "string") {
        return String(parsed.text || "");
      }
    } catch {
      // Keep trying loose forms below.
    }
  }
  const match = raw.match(JSON_TEXT_FIELD_RE);
  if (match) return decodeJsonStringLiteral(match[1] || "");
  if (LEAKED_TEXT_PREFIX_RE.test(raw)) {
    let tail = raw.replace(LEAKED_TEXT_PREFIX_RE, "").trim();
    tail = tail.split(/"\s*,\s*"(?:audio_observations|voice_observations|observations|events)"\s*:/i)[0] || tail;
    tail = tail.replace(/\s*"?\s*\}?\s*$/g, "").trim();
    return decodeJsonStringLiteral(tail.replace(/^"+|"+$/g, ""));
  }
  return raw;
}

function compactPauseRepetition(value: string, durationMs = 0): string {
  const raw = cleanShortText(value);
  if (!raw) return "";
  const pauses = raw.match(PAUSE_NOTE_RE) || [];
  const compact = raw
    .replace(PAUSE_NOTE_RE, "")
    .replace(/[\s，,、。.!！？?…"'“”‘’（）()：:；;]+/g, "");
  const duration = Math.max(0, Number(durationMs) || 0);
  if (pauses.length >= 2 && compact && FILLER_ONLY_RE.test(compact)) return compact.slice(0, 1);
  if (duration > 0 && duration <= 2500 && pauses.length >= 1 && raw.length > 48 && compact && FILLER_ONLY_RE.test(compact)) {
    return compact.slice(0, 1);
  }
  return raw;
}

export function sanitizeVoiceTranscriptText(value: any, durationMs = 0): string {
  const extracted = extractJsonObjectText(cleanShortText(value));
  return cleanShortText(compactPauseRepetition(extracted, durationMs));
}

export function sanitizeLeakedVoiceContentText(value: any, durationMs = 0): string {
  const raw = cleanShortText(value);
  if (!raw) return "";
  const cleaned = sanitizeVoiceTranscriptText(raw, durationMs);
  if (!cleaned) return "";
  const looksLikeSttJson =
    /"text"\s*:/i.test(raw)
    && (
      LEAKED_TEXT_PREFIX_RE.test(raw)
      || /"audio_observations"\s*:|"voice_observations"\s*:|"observations"\s*:|"events"\s*:/i.test(raw)
      || PAUSE_NOTE_RE.test(raw)
    );
  PAUSE_NOTE_RE.lastIndex = 0;
  const pauseSpam = (raw.match(PAUSE_NOTE_RE) || []).length >= 2 && cleaned.length < raw.length;
  return looksLikeSttJson || pauseSpam ? cleaned : raw;
}

export function applyAssistantTerminalMessage(
  currentMessages: ChatDraftMessage[],
  clientRequestId: string,
  assistantMessage: ChatDraftMessage,
): ChatDraftMessage[] {
  const cid = String(clientRequestId || "").trim();
  const list = Array.isArray(currentMessages) ? currentMessages : [];
  if (cid && list.some((msg) => msg.role === "assistant" && msg.clientRequestId === cid && msg.status === "sent")) {
    return list;
  }
  let replaced = false;
  const next = list.map((msg) => {
    if (!cid || msg.role !== "assistant" || msg.clientRequestId !== cid || msg.status === "sent") return msg;
    replaced = true;
    return {
      ...assistantMessage,
      id: msg.id,
      createdAt: msg.createdAt,
      clientRequestId: cid,
      jobId: assistantMessage.jobId || msg.jobId,
    };
  });
  if (!replaced) next.push(assistantMessage);
  return next;
}

export function applyMessageById(currentMessages: ChatDraftMessage[], messageId: string, nextMessage: ChatDraftMessage): ChatDraftMessage[] {
  const targetId = String(messageId || "").trim();
  const list = Array.isArray(currentMessages) ? currentMessages : [];
  if (!targetId) return [...list, nextMessage];
  let replaced = false;
  const next = list.map((msg) => {
    if (msg.id !== targetId) return msg;
    replaced = true;
    return { ...nextMessage, id: msg.id, createdAt: msg.createdAt };
  });
  if (!replaced) next.push(nextMessage);
  return next;
}

export function contentToPlainText(content: any): string {
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part.trim();
        if (!part || typeof part !== "object") return "";
        if (part.type === "text" || part.type === "output_text" || part.type === "input_text") {
          if (typeof part.text === "string") return String(part.text || "").trim();
          if (part.text && typeof part.text === "object" && typeof part.text.value === "string") {
            return String(part.text.value || "").trim();
          }
        }
        if (typeof part.content === "string") return String(part.content || "").trim();
        if (part.type === "image_url") return "[图片]";
        if (part.type === "input_audio" || part.type === "audio") return "[语音]";
        if (part.type === "file" || part.type === "document") return "[文档]";
        return "";
      })
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  if (content && typeof content === "object") {
    if (typeof content.text === "string") return String(content.text || "").trim();
    if (content.text && typeof content.text === "object" && typeof content.text.value === "string") {
      return String(content.text.value || "").trim();
    }
    if (typeof content.content === "string") return String(content.content || "").trim();
    if (Array.isArray(content.content)) return contentToPlainText(content.content);
  }
  return "";
}

function sanitizeAttachmentUrl(value: any): string {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/^data:/i.test(raw) || /^blob:/i.test(raw)) return "";
  return raw;
}

function sanitizeAttachmentPreviewUrl(value: any): string {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/^(?:blob:|data:image\/|https?:\/\/|\/)/i.test(raw)) return raw;
  return "";
}

export function normalizeChatAttachments(value: any): ChatAttachment[] {
  const list = Array.isArray(value) ? value : [];
  const out: ChatAttachment[] = [];
  for (const raw of list) {
    if (!raw || typeof raw !== "object") continue;
    const kind = String(raw.kind || raw.type || "").trim().toLowerCase();
    if (kind !== "image" && kind !== "audio" && kind !== "document") continue;
    const remoteUrl = sanitizeAttachmentUrl(raw.remoteUrl || raw.url || raw.src);
    const localUrl = sanitizeAttachmentUrl(raw.localUrl || raw.localUri);
    const thumbUrl = sanitizeAttachmentUrl(raw.thumbUrl || raw.thumbUri);
    const previewUrl = kind === "image" ? sanitizeAttachmentPreviewUrl(raw.previewUrl || raw.previewUri || raw.localPreviewUrl) : "";
    const remoteKey = String(raw.remoteKey || raw.key || "").trim();
    if (
      !remoteUrl
      && !localUrl
      && !remoteKey
      && !thumbUrl
      && !previewUrl
      && !String(raw.transcript || "").trim()
      && !String(raw.textPreview || raw.text || "").trim()
    ) continue;
    const id = String(raw.id || remoteKey || remoteUrl || localUrl || `${kind}-${out.length}`).trim();
    const durationMs = Number(raw.durationMs ?? raw.duration_ms ?? 0) || 0;
    const transcript = kind === "audio"
      ? sanitizeVoiceTranscriptText(raw.transcript || raw.text || "", durationMs)
      : String(raw.transcript || "").trim();
    out.push({
      id,
      kind,
      ...(String(raw.name || raw.filename || raw.fileName || "").trim() ? { name: String(raw.name || raw.filename || raw.fileName || "").trim() } : {}),
      ...(raw.mime ? { mime: String(raw.mime || "").trim() } : {}),
      ...(remoteKey ? { remoteKey } : {}),
      ...(remoteUrl ? { remoteUrl } : {}),
      ...(localUrl ? { localUrl } : {}),
      ...(thumbUrl ? { thumbUrl } : {}),
      ...(previewUrl ? { previewUrl } : {}),
      ...(Number.isFinite(Number(raw.width)) && Number(raw.width) > 0 ? { width: Number(raw.width) } : {}),
      ...(Number.isFinite(Number(raw.height)) && Number(raw.height) > 0 ? { height: Number(raw.height) } : {}),
      ...(Number.isFinite(durationMs) && durationMs > 0 ? { durationMs } : {}),
      ...(Number.isFinite(Number(raw.size)) && Number(raw.size) > 0 ? { size: Number(raw.size) } : {}),
      ...(transcript ? { transcript } : {}),
      ...(String(raw.textPreview || raw.text || "").trim() ? { textPreview: String(raw.textPreview || raw.text || "").trim() } : {}),
      ...(String(raw.alt || "").trim() ? { alt: String(raw.alt || "").trim() } : {}),
      ...(String(raw.createdAt || "").trim() ? { createdAt: String(raw.createdAt || "").trim() } : {}),
    });
  }
  return out;
}

export function chatAttachmentPreviewLabel(attachments?: ChatAttachment[]): string {
  const list = Array.isArray(attachments) ? attachments : [];
  if (!list.length) return "";
  const images = list.filter((item) => item.kind === "image").length;
  const audios = list.filter((item) => item.kind === "audio").length;
  const documents = list.filter((item) => item.kind === "document").length;
  const parts = [
    images ? `图片${images > 1 ? images : ""}` : "",
    audios ? `语音${audios > 1 ? audios : ""}` : "",
    documents ? `文档${documents > 1 ? documents : ""}` : "",
  ].filter(Boolean);
  if (parts.length > 1) return `[${parts.join(" + ")}]`;
  if (images) return images > 1 ? `[${images}张图片]` : "[图片]";
  if (audios) return audios > 1 ? `[${audios}条语音]` : "[语音]";
  if (documents) return documents > 1 ? `[${documents}个文档]` : "[文档]";
  return "[附件]";
}

export function extractLegacyMessageField(msg: any, keys: string[]): any {
  if (!msg || typeof msg !== "object") return "";
  for (const key of keys) {
    const value = (msg as any)?.[key];
    if (value == null) continue;
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value) && value.length) return value;
    if (value && typeof value === "object") return value;
  }
  return "";
}

export function extractMessageContentSource(msg: any): any {
  if (msg == null) return "";
  if (typeof msg === "string") return msg;
  return extractLegacyMessageField(msg, [
    "content",
    "text",
    "message",
    "body",
    "value",
    "reply",
    "response",
    "markdown",
    "html",
    "parts",
  ]);
}

export function extractMessageReasoningSource(msg: any): any {
  if (!msg || typeof msg !== "object") return "";
  return extractLegacyMessageField(msg, [
    "reasoning",
    "reasoningContent",
    "reasoning_content",
    "thinking",
    "thoughts",
  ]);
}

export function fallbackRawContentText(content: any): string {
  if (content == null) return "";
  if (typeof content === "string") return content.trim();
  if (typeof content === "number" || typeof content === "boolean") return String(content).trim();
  try {
    const raw = JSON.stringify(content);
    return typeof raw === "string" ? raw.trim() : "";
  } catch {
    return "";
  }
}

export function extractAssistantMessage(data: any): any {
  const choice = Array.isArray(data?.choices) ? data.choices[0] : null;
  if (choice?.message) return choice.message;
  if (data?.message && typeof data.message === "object") return data.message;
  return {};
}

export function extractAssistantReplyText(data: any): string {
  const msg = extractAssistantMessage(data);
  return contentToPlainText(msg?.content) || contentToPlainText(data?.content) || "";
}

export function extractAssistantReasoning(data: any): string {
  const msg = extractAssistantMessage(data);
  return contentToPlainText(extractMessageReasoningSource(msg));
}

export function extractTokenCount(data: any): { input?: number; output?: number } | undefined {
  const usage = data?.usage || {};
  const input = Number(usage?.prompt_tokens || usage?.input_tokens || usage?.promptTokens || usage?.inputTokens || 0);
  const output = Number(usage?.completion_tokens || usage?.output_tokens || usage?.completionTokens || usage?.outputTokens || 0);
  const safeInput = Number.isFinite(input) && input > 0 ? input : 0;
  const safeOutput = Number.isFinite(output) && output > 0 ? output : 0;
  if (!safeInput && !safeOutput) return undefined;
  return {
    input: safeInput || undefined,
    output: safeOutput || undefined,
  };
}

export type ChatMessageGroup = {
  id: string;
  role: ChatRole;
  createdAt: string;
  lastCreatedAt: string;
  parts: Array<{
    messageId: string;
    status?: ChatDraftMessage["status"];
    operationId?: string;
    clientRequestId?: string;
    jobId?: string;
    content: string;
    render: "plain" | "rich" | "html";
    reasoning?: string;
    tokenCount?: { input?: number; output?: number };
    systemCard?: SumiTalkSystemCard | null;
    attachments?: ChatAttachment[];
  }>;
};

export type ChatSearchMatch = {
  id: string;
  groupId: string;
  partIndex: number;
};

export function getChatSearchMatchId(groupId: string, partIndex: number): string {
  return `${groupId}::${partIndex}`;
}

export function formatClockTime(value: string, timeFormat: ChatTimeFormat = "hhmm"): string {
  const raw = String(value || "").trim();
  if (!raw) return "最近";
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) {
    const m = raw.match(/(\d{2}):(\d{2})/);
    if (!m) return "最近";
    if (timeFormat === "ampm") {
      const hour = Number(m[1]);
      const period = hour >= 12 ? "下午" : "上午";
      const displayHour = String(hour % 12 || 12).padStart(2, "0");
      return `${period} ${displayHour}:${m[2]}`;
    }
    return `${m[1]}:${m[2]}`;
  }
  const hh = String(dt.getHours()).padStart(2, "0");
  const mm = String(dt.getMinutes()).padStart(2, "0");
  if (timeFormat === "ampm") {
    const hour = dt.getHours();
    const period = hour >= 12 ? "下午" : "上午";
    return `${period} ${String(hour % 12 || 12).padStart(2, "0")}:${mm}`;
  }
  return `${hh}:${mm}`;
}

export function getChatFontLabel(fontKey: ChatFontKey): string {
  if (fontKey === "system") return "系统默认";
  if (fontKey === "huninn") return "文楷";
  if (fontKey === "pingfang") return "苹方";
  if (fontKey === "serif") return "宋体";
  if (fontKey === "script") return "手写感";
  return "微软雅黑";
}

export function shouldShowGroupTime(current: string, previous?: string): boolean {
  const cur = new Date(String(current || ""));
  if (Number.isNaN(cur.getTime())) return !previous;
  if (!previous) return true;
  const prev = new Date(String(previous || ""));
  if (Number.isNaN(prev.getTime())) return true;
  const dayChanged =
    cur.getFullYear() !== prev.getFullYear() ||
    cur.getMonth() !== prev.getMonth() ||
    cur.getDate() !== prev.getDate();
  if (dayChanged) return true;
  return cur.getTime() - prev.getTime() >= 5 * 60 * 1000;
}

export function pickLatestDraftPreview(messages: ChatDraftMessage[]): { preview: string; time: string } {
  const list = Array.isArray(messages) ? messages : [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const msg = list[i];
    if (msg?.role === "assistant" && String(msg?.status || "").trim().toLowerCase() === "pending") continue;
    const text = String(msg?.content || "").trim();
    const attachmentPreview = chatAttachmentPreviewLabel(normalizeChatAttachments(msg?.attachments));
    if (!text && !attachmentPreview) continue;
    const systemCard = firstSystemCard(text);
    if (systemCard?.type === "system_alarm_created") {
      return {
        preview: `已创建 ${formatAlarmTime(systemCard.hour, systemCard.minute)} 系统闹钟`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "calendar_event_created") {
      return {
        preview: `已创建系统行程：${systemCard.title}`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "travel_plan_form") {
      return {
        preview: `填写${systemCard.title || "出行规划"}表单`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "travel_plan_result") {
      return {
        preview: `${systemCard.title || "渡安排好了"}：${(systemCard.destinations || []).join("、") || "路线"}`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "travel_transport_detail") {
      return {
        preview: `${systemCard.title || "这段怎么走"}：${systemCard.from} 到 ${systemCard.to}`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    if (systemCard?.type === "travel_food_detail") {
      return {
        preview: `${systemCard.title || "附近吃这些"}：${systemCard.placeName || systemCard.keywords || "吃喝"}`,
        time: formatClockTime(String(msg?.createdAt || "").trim()),
      };
    }
    return {
      preview: text || attachmentPreview,
      time: formatClockTime(String(msg?.createdAt || "").trim()),
    };
  }
  return { preview: "主会话", time: "主会话" };
}

export function isHtmlBlock(content: string): boolean {
  const raw = String(content || "").trim();
  if (!raw) return false;
  return /<\/?[a-z][\s\S]*>/i.test(raw);
}

export function isCodeBlock(content: string): boolean {
  const raw = String(content || "").trim();
  if (!raw) return false;
  return /```[\s\S]*```/.test(raw) || /^( {4}|\t).+/m.test(raw);
}

export function hasMarkdownSyntax(content: string): boolean {
  const raw = String(content || "").trim();
  if (!raw) return false;
  // Only treat as markdown when explicit syntax appears.
  return /(^|\n)\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|>\s)|```|`[^`\n]+`|\[.+?\]\(.+?\)|\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|\|.+\|/.test(raw);
}

export function detectMessageRender(role: ChatRole, content: string): "plain" | "rich" | "html" {
  const raw = String(content || "").replace(/\r/g, "").trim();
  if (!raw) return "plain";
  if (role === "user") return "plain";
  if (isHtmlBlock(raw)) return "html";
  if (isCodeBlock(raw)) return "rich";
  if (hasMarkdownSyntax(raw)) return "rich";
  return "plain";
}

function splitLineBubbleSegments(role: ChatRole, content: string): Array<{ content: string; systemCard: null }> {
  const raw = String(content || "").replace(/\r/g, "").trim();
  if (!raw) return [{ content: "", systemCard: null }];
  if (detectMessageRender(role, raw) === "html") return [{ content: raw, systemCard: null }];
  const lines = raw
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  return (lines.length ? lines : [raw]).map((line) => ({ content: line, systemCard: null }));
}

export function stripInlineBase64Images(content: string): string {
  const raw = String(content || "");
  if (!raw) return "";
  return raw.replace(/data:image\/[a-zA-Z0-9.+-]+;base64,[a-zA-Z0-9+/=\s]+/g, "[图片base64已省略，请改用图片URL]");
}

export function historyRenderableScore(messages: ChatDraftMessage[]): number {
  const list = Array.isArray(messages) ? messages : [];
  return list.reduce((score, msg) => {
    const content = String(msg?.content || "").trim();
    const reasoning = String(msg?.reasoning || "").trim();
    const attachments = normalizeChatAttachments(msg?.attachments);
    if (content) return score + 2;
    if (attachments.length) return score + 2;
    if (reasoning) return score + 1;
    return score;
  }, 0);
}

export function parseChatMessageTime(value: string): number {
  const raw = String(value || "").trim();
  if (!raw) return 0;
  const ts = Date.parse(raw);
  if (Number.isFinite(ts)) return ts;
  const m = raw.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?([+-]\d{2}:?\d{2})?$/);
  if (!m) return 0;
  const normalized = `${m[1]}T${m[2]}${m[3] || "+08:00"}`;
  const next = Date.parse(normalized);
  return Number.isFinite(next) ? next : 0;
}

export function latestHistoryTimestamp(messages: ChatDraftMessage[]): number {
  const list = Array.isArray(messages) ? messages : [];
  return list.reduce((latest, msg) => {
    if (msg?.role === "assistant" && String(msg?.status || "").trim().toLowerCase() === "pending") {
      return latest;
    }
    const ts = parseChatMessageTime(String(msg?.createdAt || ""));
    return ts > latest ? ts : latest;
  }, 0);
}

export function sortHistoryMessages(messages: ChatDraftMessage[]): ChatDraftMessage[] {
  const list = Array.isArray(messages) ? [...messages] : [];
  list.sort((a, b) => {
    const diff = parseChatMessageTime(String(a?.createdAt || "")) - parseChatMessageTime(String(b?.createdAt || ""));
    if (diff !== 0) return diff;
    const roleA = String(a?.role || "").trim().toLowerCase();
    const roleB = String(b?.role || "").trim().toLowerCase();
    if (roleA !== roleB) {
      if (roleA === "user") return -1;
      if (roleB === "user") return 1;
    }
    return String(a?.id || "").localeCompare(String(b?.id || ""));
  });
  return list;
}

export function pickBetterHistory(primary: ChatDraftMessage[], fallback: ChatDraftMessage[], seed: ChatDraftMessage[]): ChatDraftMessage[] {
  const primaryScore = historyRenderableScore(primary);
  const fallbackScore = historyRenderableScore(fallback);
  const primaryLatest = latestHistoryTimestamp(primary);
  const fallbackLatest = latestHistoryTimestamp(fallback);
  if (primaryScore <= 0 && fallbackScore <= 0) return seed;
  if (fallbackLatest > primaryLatest) return fallback.length ? fallback : (primary.length ? primary : seed);
  if (primaryLatest > fallbackLatest) return primary.length ? primary : (fallback.length ? fallback : seed);
  if (fallbackScore > primaryScore) return fallback.length ? fallback : (primary.length ? primary : seed);
  return primary.length ? primary : (fallback.length ? fallback : seed);
}

export function sanitizeHistoryMessages(messages: ChatDraftMessage[]): ChatDraftMessage[] {
  const list = Array.isArray(messages) ? messages : [];
  return sortHistoryMessages(list.filter((msg) => {
      const id = String((msg as any)?.id || "").trim();
      const role = String((msg as any)?.role || "").trim().toLowerCase();
      const content = contentToPlainText(extractMessageContentSource(msg)) || fallbackRawContentText(extractMessageContentSource(msg));
      const attachments = normalizeChatAttachments((msg as any)?.attachments);
      const isSeedId = id.startsWith("seed-");
      const isDefaultGreeting = role === "assistant" && (
        content === "我在。你直接说就好。" ||
        /开着。你直接说就好。$/.test(content)
      );
      return attachments.length || !(isSeedId || isDefaultGreeting);
    }).map((msg) => {
      const rawContent = extractMessageContentSource(msg);
      const rawReasoning = extractMessageReasoningSource(msg);
      const normalizedRole = String(msg?.role || "").trim().toLowerCase();
      const role: ChatRole = normalizedRole === "user" || normalizedRole === "assistant" || normalizedRole === "benben"
        ? normalizedRole
        : "assistant";
      const reasoning = contentToPlainText(rawReasoning) || fallbackRawContentText(rawReasoning);
      const rawStatus = String((msg as any)?.status || "").trim().toLowerCase();
      const status = rawStatus === "pending" || rawStatus === "sent" || rawStatus === "failed"
        ? rawStatus as ChatDraftMessage["status"]
        : undefined;
      const rawContentText = contentToPlainText(rawContent) || fallbackRawContentText(rawContent);
      const cleanedContent = sanitizeLeakedVoiceContentText(rawContentText);
      const content = status === "pending" && role === "assistant"
        ? ""
        : stripInlineBase64Images(cleanedContent);
      const attachments = normalizeChatAttachments((msg as any)?.attachments);
      let tokenCount: { input?: number; output?: number } | undefined;
      if (msg?.tokenCount && typeof msg.tokenCount === "object") {
        const input = Number(msg.tokenCount.input || 0);
        const output = Number(msg.tokenCount.output || 0);
        tokenCount = {
          input: Number.isFinite(input) && input > 0 ? input : undefined,
          output: Number.isFinite(output) && output > 0 ? output : undefined,
        };
      } else {
        const legacyCount = Number((msg as any)?.tokenCount || 0);
        if (Number.isFinite(legacyCount) && legacyCount > 0) {
          tokenCount = { output: legacyCount };
        }
      }
      return {
        ...msg,
        role,
        content,
        status,
        clientRequestId: String((msg as any)?.clientRequestId || "").trim() || undefined,
        operationId: String((msg as any)?.operationId || "").trim() || undefined,
        jobId: String((msg as any)?.jobId || "").trim() || undefined,
        reasoning: reasoning || undefined,
        tokenCount,
        ...(attachments.length ? { attachments } : {}),
      };
    }));
}

export function groupChatMessages(messages: ChatDraftMessage[]): ChatMessageGroup[] {
  const groups: ChatMessageGroup[] = [];
  for (const msg of messages) {
    if (msg?.role === "assistant" && String(msg?.status || "").trim().toLowerCase() === "pending") continue;
    const normalizedContent = String(msg?.content || "").trim();
    const normalizedReasoning = String(msg?.reasoning || "").trim();
    const attachments = normalizeChatAttachments(msg?.attachments);
    if (!normalizedContent && !normalizedReasoning && !attachments.length) continue;
    const rawSegments = msg.role === "assistant"
      ? splitSystemCardSegments(normalizedContent)
      : [{ content: normalizedContent, systemCard: null }];
    const segments = rawSegments.flatMap((segment) => (
      segment.systemCard
        ? [segment]
        : splitLineBubbleSegments(msg.role, segment.content)
    ));
    const safeParts = (segments.length ? segments : [{ content: normalizedContent, systemCard: null }])
      .filter((segment, index) => String(segment.content || "").trim() || segment.systemCard || normalizedReasoning || (index === 0 && attachments.length))
      .map((segment, index) => ({
        messageId: msg.id,
        status: msg.status,
        operationId: msg.operationId,
        clientRequestId: msg.clientRequestId,
        jobId: msg.jobId,
        content: String(segment.content || "").trim(),
        render: segment.systemCard ? "plain" as const : detectMessageRender(msg.role, String(segment.content || "").trim()),
        reasoning: index === 0 ? normalizedReasoning || undefined : undefined,
        tokenCount: index === 0 ? msg.tokenCount : undefined,
        systemCard: segment.systemCard,
        attachments: index === 0 ? attachments : undefined,
      }));
    const last = groups[groups.length - 1];
    if (last && last.role === msg.role && !shouldShowGroupTime(msg.createdAt, last.lastCreatedAt)) {
      last.parts.push(...safeParts);
      last.lastCreatedAt = msg.createdAt;
      continue;
    }
    groups.push({
      id: msg.id,
      role: msg.role,
      createdAt: msg.createdAt,
      lastCreatedAt: msg.createdAt,
      parts: [...safeParts],
    });
  }
  return groups;
}

export function groupRoleLabel(role: ChatRole): string {
  if (role === "user") return "辛玥";
  if (role === "benben") return "笨笨";
  return "渡";
}

export function buildBenbenGroupContext(messages: ChatDraftMessage[], force = false): string {
  const lines = (Array.isArray(messages) ? messages : [])
    .filter((msg) => msg.status !== "pending" && msg.status !== "failed")
    .filter((msg) => String(msg.content || "").trim())
    .slice(-12)
    .map((msg) => `${groupRoleLabel(msg.role)}：${String(msg.content || "").trim()}`);
  if (!force && !lines.some((line) => line.startsWith("笨笨："))) return "";
  return [
    "【三人群聊上下文】",
    "这是辛玥、渡、笨笨的日常群聊。笨笨的话来自第三个群成员，不是辛玥说的；回复时可以自然看见笨笨刚才说过什么，但不要把笨笨当成辛玥。",
    ...lines,
    "【以上为群聊上下文】",
  ].join("\n");
}

export function buildGroupTurnUserContent(messages: ChatDraftMessage[], fallbackUserContent: string): string {
  const list = Array.isArray(messages) ? messages : [];
  let lastAssistantIndex = -1;
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const msg = list[i];
    if (msg?.role === "assistant" && msg.status !== "pending" && msg.status !== "failed") {
      lastAssistantIndex = i;
      break;
    }
  }
  const turnLines = list
    .slice(lastAssistantIndex + 1)
    .filter((msg) => msg?.role === "user" || msg?.role === "benben")
    .filter((msg) => msg.status !== "pending" && msg.status !== "failed")
    .map((msg) => `${groupRoleLabel(msg.role)}：${String(msg.content || "").trim()}`)
    .filter((line) => !line.endsWith("："));
  const fallback = String(fallbackUserContent || "").trim();
  if (!turnLines.length && fallback) {
    turnLines.push(`辛玥：${fallback}`);
  }
  if (!turnLines.length) return fallback;
  return ["【三人群聊当前轮】", ...turnLines].join("\n");
}

export function buildCodexGroupRecentMessages(messages: ChatDraftMessage[]): Array<{ role: ChatRole; content: string; createdAt?: string }> {
  return (Array.isArray(messages) ? messages : [])
    .filter((msg) => msg.status !== "pending" && msg.status !== "failed")
    .filter((msg) => String(msg.content || "").trim())
    .slice(-14)
    .map((msg) => ({
      role: msg.role,
      content: String(msg.content || "").trim(),
      createdAt: msg.createdAt,
    }));
}
