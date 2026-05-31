import type { ChatFontKey } from "./chatMessages";

export const BUBBLE_STYLE_KEYS = ["default", "soft", "outline", "decor", "angry", "peek"] as const;
export type BubbleStyleKey = typeof BUBBLE_STYLE_KEYS[number];
export type BubbleSkinKey = "heart-rabbit" | "angry-emoji" | "peek-rabbit";

export const TRANSPARENT_BUBBLE_CLASS =
  "bg-gradient-to-br from-white/40 via-white/20 to-white/5 border border-white/50 text-gray-800 shadow-[inset_0_1px_1px_rgba(255,255,255,0.4),0_4px_20px_rgba(0,0,0,0.05)] backdrop-blur-sm";

export const DEFAULT_GROUP_CHAT_TITLE = "三人群聊";
export const GROUP_CHAT_TITLE_MAX_LENGTH = 24;

export function limitGroupChatTitle(value: string): string {
  return Array.from(String(value || "")).slice(0, GROUP_CHAT_TITLE_MAX_LENGTH).join("");
}

export function getDisplayGroupChatTitle(value?: string): string {
  return limitGroupChatTitle(String(value || "")).trim() || DEFAULT_GROUP_CHAT_TITLE;
}

export function resolveChatFontFamily(fontKey: ChatFontKey): string {
  if (fontKey === "system") return "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
  if (fontKey === "pingfang") return "'PingFang SC', 'Hiragino Sans GB', sans-serif";
  return "'Microsoft YaHei', sans-serif";
}

export function getBubbleStyleLabel(style: BubbleStyleKey, role: "user" | "assistant"): string {
  if (style === "soft") return role === "user" ? "柔和填充" : "浅灰填充";
  if (style === "outline") return "描边";
  if (style === "decor") return "心动兔兔";
  if (style === "angry") return "生气emoji";
  if (style === "peek") return "兔兔探头";
  return "默认";
}

export function resolveBubbleClass(role: "user" | "assistant", style: BubbleStyleKey): string {
  if (role === "user") {
    if (style === "soft") return "bg-[#475569] text-white";
    if (style === "outline") return "border border-[#CBD5E1] bg-white text-gray-900";
    if (style === "decor") return "border-0 bg-[#fffdf9] text-[#56524D] !shadow-none";
    if (style === "angry") return "border-0 bg-white/80 text-[#56524D] !shadow-none";
    if (style === "peek") return "border border-white bg-white text-[#56524D] !shadow-none";
    return "bg-[#2D3748] text-white";
  }
  if (style === "soft") return "bg-[#F4F5F7] text-gray-800";
  if (style === "outline") return "border border-[#CBD5E1] bg-white text-gray-800";
  if (style === "decor") return "border-0 bg-[#fffdf9] text-[#56524D] !shadow-none";
  if (style === "angry") return "border-0 bg-white/80 text-[#56524D] !shadow-none";
  if (style === "peek") return "border border-white bg-white text-[#56524D] !shadow-none";
  return "border border-gray-100/50 bg-white text-gray-800";
}

export function resolveBubbleSkin(style: BubbleStyleKey): BubbleSkinKey | undefined {
  if (style === "decor") return "heart-rabbit";
  if (style === "angry") return "angry-emoji";
  if (style === "peek") return "peek-rabbit";
  return undefined;
}
