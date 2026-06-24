import { sanitizeVoiceTranscriptText, type ChatAttachment } from "../chatMessages";
import {
  transcribeChatAudio,
  uploadChatDocument,
  uploadChatImage,
} from "./chatMedia";
import { fileToDataUrl } from "../imageDataUrl";
import {
  buildPrivateUserContent,
  type PrivateModelContent,
} from "./privateChatHelpers";

export type PrivateChatSource = "text" | "image" | "document" | "voice" | "travel_form" | "retry";

export type PreparedPrivateChatInput = {
  source: PrivateChatSource;
  content: string;
  displayContent?: string;
  attachments: ChatAttachment[];
  modelContent: PrivateModelContent;
  sttProvider?: string;
};

export function prepareTextPrivateChatInput(content: string): PreparedPrivateChatInput {
  const text = String(content || "").trim();
  return {
    source: "text",
    content: text,
    displayContent: text,
    attachments: [],
    modelContent: buildPrivateUserContent(text, []),
  };
}

function buildPrivateImageDataContent(content: string, imageDataUrls: string[]): PrivateModelContent {
  const text = String(content || "").trim();
  const imageParts = imageDataUrls
    .map((url) => String(url || "").trim())
    .filter((url) => /^data:image\/[^;,]+;base64,/i.test(url))
    .map((url) => ({
      type: "image_url",
      image_url: { url },
    }));
  if (!imageParts.length) return buildPrivateUserContent(text, []);
  const parts: Array<Record<string, any>> = [];
  if (text) parts.push({ type: "text", text });
  parts.push(...imageParts);
  return parts;
}

export async function prepareImagesPrivateChatInput(files: File[], content: string): Promise<PreparedPrivateChatInput> {
  const text = String(content || "").trim();
  const imageFiles = files.filter(Boolean);
  if (!imageFiles.length) {
    return prepareTextPrivateChatInput(text);
  }
  const [attachments, imageDataUrls] = await Promise.all([
    Promise.all(imageFiles.map((file) => uploadChatImage(file))),
    Promise.all(imageFiles.map((file) => fileToDataUrl(file))),
  ]);
  return {
    source: "image",
    content: text,
    displayContent: text,
    attachments,
    modelContent: buildPrivateImageDataContent(text, imageDataUrls),
  };
}

export async function prepareImagePrivateChatInput(file: File, content: string): Promise<PreparedPrivateChatInput> {
  return prepareImagesPrivateChatInput([file], content);
}

export async function prepareDocumentPrivateChatInput(file: File, content: string): Promise<PreparedPrivateChatInput> {
  const text = String(content || "").trim();
  const attachmentWithText = await uploadChatDocument(file);
  const attachment: ChatAttachment = {
    ...attachmentWithText,
    textPreview: undefined,
  };
  const modelAttachments = [attachmentWithText];
  const attachments = [attachment];
  return {
    source: "document",
    content: text,
    displayContent: text,
    attachments,
    modelContent: buildPrivateUserContent(text, modelAttachments),
  };
}

export async function prepareVoicePrivateChatInput(blob: Blob, mimeType: string, durationMs = 0): Promise<PreparedPrivateChatInput> {
  const result = await transcribeChatAudio(blob, mimeType, durationMs);
  const transcript = sanitizeVoiceTranscriptText(result.text || "", durationMs);
  if (!transcript) throw new Error("没识别出内容，再说一遍试试");
  const attachments = [{ ...result.attachment, transcript }];
  return {
    source: "voice",
    content: transcript,
    displayContent: "",
    attachments,
    modelContent: buildPrivateUserContent(transcript, attachments),
    sttProvider: result.sttProvider || "",
  };
}

export function prepareTravelFormPrivateChatInput(content: string, displayContent = "已提交，渡在安排"): PreparedPrivateChatInput {
  const text = String(content || "").trim();
  const shown = String(displayContent || text).trim();
  return {
    source: "travel_form",
    content: text,
    displayContent: shown,
    attachments: [],
    modelContent: buildPrivateUserContent(text, []),
  };
}

export type { PrivateModelContent };
