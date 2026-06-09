import {
  normalizeChatAttachments,
  type ChatAttachment,
} from "../chatMessages";

export type PrivateModelContent = string | Array<Record<string, any>>;

export function contentWithAttachmentHint(content: string, attachments: ChatAttachment[]): string {
  const text = String(content || "").trim();
  const labels = attachments
    .map((item) => {
      if (item.kind === "image") return "[图片]";
      if (item.kind === "audio") {
        const transcript = String(item.transcript || "").trim();
        if (transcript && transcript !== text) return `[语音转写] ${transcript}`;
        return "[语音]";
      }
      return "[附件]";
    })
    .filter(Boolean);
  return [text, ...labels].filter(Boolean).join("\n").trim();
}

export function buildPrivateUserContent(content: string, attachments: ChatAttachment[]): PrivateModelContent {
  const text = String(content || "").trim();
  const imageParts = attachments
    .filter((item) => item.kind === "image" && String(item.remoteUrl || "").trim())
    .map((item) => ({
      type: "image_url",
      image_url: { url: String(item.remoteUrl || "").trim() },
    }));
  if (!imageParts.length) return contentWithAttachmentHint(text, attachments);
  const parts: Array<Record<string, any>> = [];
  if (text) parts.push({ type: "text", text });
  parts.push(...imageParts);
  return parts;
}

export function extractAssistantAttachments(data: any): ChatAttachment[] {
  const content = data?.choices?.[0]?.message?.content || data?.message?.content || data?.content;
  if (!Array.isArray(content)) return [];
  const out: ChatAttachment[] = [];
  for (const part of content) {
    if (!part || typeof part !== "object") continue;
    if (part.type === "image_url") {
      const url = String(part.image_url?.url || "").trim();
      if (!url || /^data:/i.test(url)) continue;
      out.push({
        id: String(part.id || url || `assistant-image-${out.length}`),
        kind: "image",
        remoteUrl: url,
        mime: String(part.mime || ""),
        alt: String(part.alt || "图片"),
      });
    }
  }
  return normalizeChatAttachments(out);
}

export function isVoiceTranscriptEcho(content: string, attachments: ChatAttachment[]): boolean {
  const text = String(content || "").trim().replace(/\s+/g, " ");
  if (!text) return false;
  return attachments.some((item) => {
    const transcript = String(item.transcript || "").trim().replace(/\s+/g, " ");
    return transcript && transcript === text;
  });
}

export function extractSumiTalkVoiceOutput(content: string): { displayText: string; voiceText: string } {
  const raw = String(content || "");
  const voiceTexts: string[] = [];
  const displayText = raw.replace(/<voice>([\s\S]*?)<\/voice>/gi, (_all, inner) => {
    const item = String(inner || "").trim();
    if (item) voiceTexts.push(item);
    return "";
  }).trim();
  return { displayText, voiceText: voiceTexts.join("\n").trim() };
}
