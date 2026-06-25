import React, { useRef, useState } from "react";
import DOMPurify from "dompurify";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import angryEmojiFaceUrl from "../assets/angry-emoji-face.png?url";
import angryEmojiMarkUrl from "../assets/angry-emoji-mark.png?url";
import peekRabbitStickerUrl from "../assets/peek-rabbit-sticker.png?url";
import softJellyBlueStickerUrl from "../assets/soft-jelly-blue-sticker.png?url";
import softJellyYellowStickerUrl from "../assets/soft-jelly-yellow-sticker.png?url";
import sumikaBubbleStickerUrl from "../assets/sumika-bubble-sticker.png?url";
import type { BubbleSkinKey } from "./chatAppearance";
import { BrushIconMini, FileTextIcon, ImageIconMini, MicIconMini, PhoneIconLarge, RouteIconMini, SmileIconMini } from "./icons";
import type { ChatAttachment, ChatAttachmentKind } from "./chatMessages";

type BubbleStickerAnchor = "top-left" | "top-right" | "bottom-left" | "bottom-right";
type BubbleSticker = {
  id: string;
  anchor: BubbleStickerAnchor;
  offsetX: number;
  offsetY: number;
  size: number;
  rotate: number;
  flipX?: boolean;
} & (
  | { type: "image"; src: string }
  | { type: "text"; text: string }
);

const HEART_RABBIT_BUBBLE_STICKERS = [
  {
    id: "sumika-image",
    type: "image",
    src: sumikaBubbleStickerUrl,
    anchor: "bottom-left",
    offsetX: -21,
    offsetY: -78,
    size: 86,
    rotate: 0,
  },
  {
    id: "sumika-glint",
    type: "text",
    text: "⊹",
    anchor: "top-right",
    offsetX: -7,
    offsetY: -2,
    size: 14,
    rotate: 0,
  },
  {
    id: "sumika-star",
    type: "text",
    text: "★",
    anchor: "top-right",
    offsetX: -16,
    offsetY: -9,
    size: 14,
    rotate: -8,
  },
  {
    id: "sumika-spark",
    type: "text",
    text: "✧",
    anchor: "bottom-right",
    offsetX: -13,
    offsetY: -11,
    size: 14,
    rotate: 14,
  },
] satisfies BubbleSticker[];

const ANGRY_EMOJI_BUBBLE_STICKERS = [
  {
    id: "angry-emoji-face",
    type: "image",
    src: angryEmojiFaceUrl,
    anchor: "bottom-right",
    offsetX: -28,
    offsetY: -17,
    size: 36,
    rotate: 0,
  },
  {
    id: "angry-emoji-mark",
    type: "image",
    src: angryEmojiMarkUrl,
    anchor: "top-left",
    offsetX: -11,
    offsetY: -5,
    size: 24,
    rotate: 0,
  },
] satisfies BubbleSticker[];

const PEEK_RABBIT_BUBBLE_STICKERS = [
  {
    id: "peek-rabbit-sticker",
    type: "image",
    src: peekRabbitStickerUrl,
    anchor: "top-right",
    offsetX: -14,
    offsetY: -2,
    size: 89,
    rotate: 0,
  },
] satisfies BubbleSticker[];

const SOFT_JELLY_YELLOW_BUBBLE_STICKERS = [
  {
    id: "soft-jelly-yellow-sticker",
    type: "image",
    src: softJellyYellowStickerUrl,
    anchor: "bottom-left",
    offsetX: -17,
    offsetY: -13,
    size: 35,
    rotate: 0,
  },
] satisfies BubbleSticker[];

const SOFT_JELLY_BLUE_BUBBLE_STICKERS = [
  {
    id: "soft-jelly-blue-sticker",
    type: "image",
    src: softJellyBlueStickerUrl,
    anchor: "bottom-right",
    offsetX: -16,
    offsetY: -7,
    size: 22,
    rotate: 0,
  },
] satisfies BubbleSticker[];

function getBubbleStickers(skin: BubbleSkinKey): BubbleSticker[] {
  if (skin === "angry-emoji") return ANGRY_EMOJI_BUBBLE_STICKERS;
  if (skin === "peek-rabbit") return PEEK_RABBIT_BUBBLE_STICKERS;
  if (skin === "soft-jelly-yellow") return SOFT_JELLY_YELLOW_BUBBLE_STICKERS;
  if (skin === "soft-jelly-blue") return SOFT_JELLY_BLUE_BUBBLE_STICKERS;
  return HEART_RABBIT_BUBBLE_STICKERS;
}

function resolveBubbleStickerStyle(sticker: BubbleSticker): React.CSSProperties {
  return {
    ...(sticker.anchor.endsWith("left")
      ? { left: `${sticker.offsetX}px` }
      : { left: `calc(100% + ${sticker.offsetX}px)` }),
    ...(sticker.anchor.startsWith("top")
      ? { top: `${sticker.offsetY}px` }
      : { top: `calc(100% + ${sticker.offsetY}px)` }),
    width: `${sticker.size}px`,
    height: `${sticker.size}px`,
    transform: `rotate(${sticker.rotate}deg)${sticker.flipX ? " scaleX(-1)" : ""}`,
    transformOrigin: "50% 50%",
  };
}

function HeartRabbitBubbleSkin() {
  return (
    <>
      <span
        className="pointer-events-none absolute -inset-[2px] z-0 rounded-[inherit] bg-[#fffdf9]/70 opacity-55 blur-[2px]"
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute inset-0 z-0 rounded-[inherit]"
        style={{
          background:
            "linear-gradient(145deg, rgba(255,255,255,0.34), rgba(255,250,246,0.08) 48%, rgba(244,184,207,0.12))",
          boxShadow:
            "0 2px 2px rgba(70,63,54,0.05), 0 0 18px 0 rgba(244,184,207,0.16), 0 0 32px 2px rgba(209,209,209,0.22), inset 0 1px 0 rgba(255,255,255,0.72)",
        }}
        aria-hidden="true"
      />
    </>
  );
}

function AngryEmojiBubbleSkin() {
  return (
    <>
      <span
        className="pointer-events-none absolute -inset-[2px] z-0 rounded-[inherit] bg-white/80 opacity-55"
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute inset-0 z-0 rounded-[inherit] bg-white/80"
        style={{
          boxShadow:
            "0 2px 2px rgba(70,63,54,0.05), 0 0 15px 6px rgba(209,209,209,0.28), inset 0 1px 0 rgba(255,255,255,0.72)",
        }}
        aria-hidden="true"
      />
    </>
  );
}

function PeekRabbitBubbleSkin() {
  return (
    <>
      <span
        className="pointer-events-none absolute -inset-[2px] z-0 rounded-[inherit] bg-white opacity-55 blur-[1px]"
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute inset-0 z-0 rounded-[inherit] bg-white"
        style={{
          boxShadow:
            "0 0 0 rgba(70,63,54,0), 0 0 0 0 rgba(209,209,209,0), inset 0 1px 0 rgba(255,255,255,0.72)",
        }}
        aria-hidden="true"
      />
    </>
  );
}

function SoftJellyYellowBubbleSkin() {
  return (
    <>
      <span
        className="pointer-events-none absolute -inset-[2px] rounded-[inherit] bg-[rgba(255,250,226,0.38)] opacity-50 blur-[1px]"
        style={{ zIndex: -1 }}
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute inset-0 z-0 rounded-[inherit]"
        style={{
          boxShadow:
            "0 1px 2px rgba(70,63,54,0.08), inset 0 1px 0 rgba(255,255,255,0.72)",
        }}
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute inset-0 z-0 rounded-[inherit] opacity-35"
        style={{
          background:
            "radial-gradient(circle at 22% 18%, rgba(255,255,255,0.82), transparent 32%), radial-gradient(circle at 78% 82%, rgba(255,255,255,0.22), transparent 34%)",
        }}
        aria-hidden="true"
      />
    </>
  );
}

function SoftJellyBlueBubbleSkin() {
  return (
    <>
      <span
        className="pointer-events-none absolute -inset-[2px] rounded-[inherit]"
        style={{
          zIndex: -1,
          boxShadow: "0 2px 9px rgba(224,241,245,0.58)",
        }}
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute inset-0 z-0 rounded-[inherit]"
        style={{
          boxShadow:
            "0 1px 2px rgba(70,63,54,0.08), inset 0 1px 0 rgba(255,255,255,0.72)",
        }}
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute inset-0 z-0 rounded-[inherit] opacity-35"
        style={{
          background:
            "radial-gradient(circle at 22% 18%, rgba(255,255,255,0.82), transparent 32%), radial-gradient(circle at 78% 82%, rgba(255,255,255,0.22), transparent 34%)",
        }}
        aria-hidden="true"
      />
    </>
  );
}

function BubbleSkinLayer({ skin }: { skin: BubbleSkinKey }) {
  if (skin === "angry-emoji") return <AngryEmojiBubbleSkin />;
  if (skin === "peek-rabbit") return <PeekRabbitBubbleSkin />;
  if (skin === "soft-jelly-yellow") return <SoftJellyYellowBubbleSkin />;
  if (skin === "soft-jelly-blue") return <SoftJellyBlueBubbleSkin />;
  return <HeartRabbitBubbleSkin />;
}

export function ChatHeaderStatus({ sending }: { sending: boolean }) {
  if (!sending) {
    return <div className="max-w-full truncate text-[8px] font-medium leading-[1.05] text-gray-500">在线</div>;
  }
  return (
    <div className="flex max-w-full min-w-0 items-center justify-center gap-1 text-[8px] font-medium leading-[1.05] text-[#5F6C7B]" aria-label="正在输入中">
      <span className="min-w-0 truncate">正在输入中</span>
      <span className="inline-flex shrink-0 items-end gap-0.5">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="inline-block h-[2.5px] w-[2.5px] animate-pulse rounded-full bg-[#5F6C7B]"
            style={{
              animationDelay: `${index * 0.18}s`,
              animationDuration: "1s",
            }}
          />
        ))}
      </span>
    </div>
  );
}

export function RichTextBlock({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="m-0 whitespace-pre-wrap">{children}</p>,
        h1: ({ children }) => <h1 className="mb-2 text-[20px] font-semibold leading-tight text-gray-900">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-2 text-[18px] font-semibold leading-tight text-gray-900">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1.5 text-[16px] font-semibold leading-tight text-gray-900">{children}</h3>,
        ul: ({ children }) => <ul className="my-2 list-disc pl-5">{children}</ul>,
        ol: ({ children }) => <ol className="my-2 list-decimal pl-5">{children}</ol>,
        li: ({ children }) => <li className="my-0.5">{children}</li>,
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto">
            <table className="min-w-full border-collapse text-left text-[12px] leading-6 text-gray-800">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="bg-black/5">{children}</thead>,
        tbody: ({ children }) => <tbody>{children}</tbody>,
        tr: ({ children }) => <tr className="border-b border-black/10 last:border-b-0">{children}</tr>,
        th: ({ children }) => <th className="px-2.5 py-2 font-semibold text-gray-900">{children}</th>,
        td: ({ children }) => <td className="px-2.5 py-2 align-top">{children}</td>,
        pre: ({ children }) => <pre className="my-2 overflow-x-auto rounded-[12px] bg-black/5 p-3 text-[13px]">{children}</pre>,
        code: ({ children, ...props }) => {
          const inline = !String(props.className || "").includes("language-");
          return inline ? <code className="rounded bg-black/5 px-1.5 py-0.5 text-[13px]">{children}</code> : <code>{children}</code>;
        },
        blockquote: ({ children }) => <blockquote className="my-2 border-l-2 border-black/10 pl-3 opacity-80">{children}</blockquote>,
        a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" className="underline">{children}</a>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export function HtmlBlock({ content }: { content: string }) {
  const sanitized = DOMPurify.sanitize(content);
  return <div className="w-full" dangerouslySetInnerHTML={{ __html: sanitized }} />;
}

export function PlainTextBlock({ content }: { content: string }) {
  return <span className="whitespace-pre-wrap">{content}</span>;
}

function attachmentSrc(item: ChatAttachment): string {
  return String(item.previewUrl || item.remoteUrl || item.localUrl || item.thumbUrl || "").trim();
}

function attachmentPreviewSrc(item: ChatAttachment): string {
  return String(item.kind === "image" ? item.previewUrl || item.thumbUrl || item.remoteUrl || item.localUrl : item.remoteUrl || item.localUrl || item.thumbUrl).trim();
}

function ImagePreviewOverlay({
  src,
  alt,
  onClose,
}: {
  src: string;
  alt?: string;
  onClose: () => void;
}) {
  const imageSrc = String(src || "").trim();
  if (!imageSrc) return null;
  return (
    <div
      className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/28 px-4 py-8 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="relative max-h-[72vh] max-w-[86vw] overflow-hidden rounded-[18px] bg-white/90 p-2 shadow-[0_18px_60px_rgba(15,23,42,0.28)]"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="absolute right-2 top-2 z-10 flex h-8 w-8 items-center justify-center rounded-full bg-white/86 text-[22px] leading-none text-gray-500 shadow-sm active:scale-95"
          onClick={onClose}
          aria-label="关闭图片预览"
        >
          ×
        </button>
        <img
          src={imageSrc}
          alt={alt || "图片"}
          className="block max-h-[68vh] max-w-[82vw] rounded-[14px] object-contain"
          loading="eager"
          draggable={false}
        />
      </div>
    </div>
  );
}

function formatAudioDuration(ms?: number): string {
  const total = Math.max(0, Math.round(Number(ms || 0) / 1000));
  if (!total) return "";
  if (total < 60) return `${total}"`;
  const mm = Math.floor(total / 60);
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}'${ss}"`;
}

function audioBarWidth(durationMs?: number): number {
  const seconds = Math.max(0, Math.round(Number(durationMs || 0) / 1000));
  if (!seconds) return 92;
  return Math.max(90, Math.min(126, 82 + seconds * 3));
}

function formatAttachmentSize(bytes?: number): string {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "";
  if (value < 1024) return `${Math.round(value)}B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)}KB`;
  return `${(value / 1024 / 1024).toFixed(1)}MB`;
}

function ChatVoiceBar({ item, src, align }: { item: ChatAttachment; src: string; align: "left" | "right" }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [durationMs, setDurationMs] = useState(item.durationMs || 0);
  const duration = formatAudioDuration(durationMs);
  const durationLabel = duration || "0\"";
  const width = audioBarWidth(durationMs);
  const isRight = align === "right";
  const bars = [2, 3, 4, 3, 5, 7, 8, 6, 5, 7, 4, 3, 2];

  function syncMetadata() {
    const durationSeconds = audioRef.current?.duration || 0;
    if (Number.isFinite(durationSeconds) && durationSeconds > 0) {
      setDurationMs(Math.round(durationSeconds * 1000));
    }
  }

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!audio) return;
    if (!audio.paused) {
      audio.pause();
      setPlaying(false);
      return;
    }
    try {
      await audio.play();
      setPlaying(true);
    } catch {
      setPlaying(false);
    }
  }

  return (
    <div className={`flex max-w-full flex-col ${isRight ? "items-end self-end" : "items-start self-start"}`}>
      <button
        type="button"
        className="flex h-5 max-w-full items-center gap-1.5 text-current transition-opacity active:opacity-70"
        style={{ width }}
        onClick={() => void togglePlayback()}
        aria-label={playing ? "暂停语音" : "播放语音"}
      >
        <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-current/10" aria-hidden="true">
          {playing ? (
            <span className="flex h-[7px] items-center gap-[2px]">
              <span className="h-full w-[2px] rounded-full bg-current" />
              <span className="h-full w-[2px] rounded-full bg-current" />
            </span>
          ) : (
            <span
              className="ml-[1px] block h-0 w-0 border-y-[4px] border-l-[6px] border-y-transparent border-l-current"
            />
          )}
        </span>
        <span className="flex flex-1 items-end justify-center gap-[2px]" aria-hidden="true">
          {bars.map((height, index) => (
            <span
              key={index}
              className={`w-[2px] rounded-full bg-current ${playing ? "opacity-90" : "opacity-75"}`}
              style={{ height: `${playing && index % 3 === 1 ? Math.min(10, height + 2) : height}px` }}
            />
          ))}
        </span>
        <span className="shrink-0 text-[12px] font-semibold leading-none tabular-nums">
          {durationLabel}
        </span>
      </button>
      <audio
        ref={audioRef}
        className="hidden"
        preload="metadata"
        src={src}
        onLoadedMetadata={syncMetadata}
        onEnded={() => setPlaying(false)}
        onPause={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
      />
    </div>
  );
}

export function ChatVoiceTranscriptBlock({
  attachments,
  align = "left",
  openTranscriptId,
  onTranscriptToggle,
  showToggle = true,
}: {
  attachments?: ChatAttachment[];
  align?: "left" | "right";
  openTranscriptId?: string;
  onTranscriptToggle: (item: ChatAttachment) => void;
  showToggle?: boolean;
}) {
  const items = Array.isArray(attachments)
    ? attachments.filter((item) => item.kind === "audio" && String(item.transcript || "").trim())
    : [];
  if (!items.length) return null;
  const isRight = align === "right";
  return (
    <div className={`flex max-w-full flex-col gap-1 px-1 ${isRight ? "items-end self-end" : "items-start self-start"}`}>
      {items.map((item) => {
        const id = String(item.id || item.remoteKey || item.remoteUrl || "").trim();
        const open = Boolean(id && openTranscriptId === id);
        const transcript = String(item.transcript || "").trim();
        const showTranscriptToggle = showToggle || open;
        return (
          <div key={id || item.remoteUrl || transcript} className={`flex max-w-[260px] flex-col gap-0.5 ${isRight ? "items-end" : "items-start"}`}>
            {showTranscriptToggle ? (
              <button
                type="button"
                className={`text-[10px] font-medium leading-4 transition-colors active:opacity-70 ${
                  open ? "text-gray-700" : "text-gray-400"
                }`}
                onClick={() => onTranscriptToggle(item)}
              >
                {open ? "收起文字" : "转文字"}
              </button>
            ) : null}
            {open ? (
              <div className="whitespace-pre-wrap text-left text-[12px] font-medium leading-5 text-gray-500">
                {transcript}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function ImageAttachmentGallery({ items, align }: { items: ChatAttachment[]; align: "left" | "right" }) {
  type StackMotion = {
    phase: "dragging" | "settling";
    baseIndex: number;
    direction: 1 | -1;
    targetIndex: number | null;
    progress: number;
    accepted: boolean;
  };
  type CardPose = {
    x: number;
    y: number;
    scale: number;
    rotate: number;
    opacity: number;
  };

  const [activeIndex, setActiveIndex] = useState(0);
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null);
  const [motion, setMotion] = useState<StackMotion | null>(null);
  const motionRef = useRef<StackMotion | null>(null);
  const dragStartX = useRef<number | null>(null);
  const dragBaseIndexRef = useRef(0);
  const dragDirectionRef = useRef<1 | -1 | null>(null);
  const settleTimerRef = useRef<number | null>(null);
  const suppressClickRef = useRef(false);
  const isRight = align === "right";
  const imageItems = items.filter((item) => attachmentSrc(item));
  const swipeDistance = 136;
  const dragActivationDistance = 14;
  const commitDistance = 42;

  if (imageItems.length < 2) return null;

  const normalizedIndex = Math.max(0, Math.min(activeIndex, imageItems.length - 1));
  const baseIndex = Math.max(0, Math.min(motion?.baseIndex ?? normalizedIndex, imageItems.length - 1));
  const currentItem = imageItems[baseIndex];
  const targetItem = motion?.targetIndex != null ? imageItems[motion.targetIndex] : null;
  const activePreviewSrc = attachmentPreviewSrc(currentItem);
  const activePreviewAlt = currentItem.alt || "图片";
  const motionProgress = motion
    ? (motion.phase === "dragging" ? Math.pow(motion.progress, 0.92) : motion.progress)
    : 0;
  const movingTransition = motion?.phase === "settling"
    ? "transform 240ms cubic-bezier(0.22, 1, 0.36, 1), opacity 180ms ease-out"
    : "none";

  function setStackMotion(next: StackMotion | null) {
    motionRef.current = next;
    setMotion(next);
  }

  function clearSettleTimer() {
    if (settleTimerRef.current != null) {
      window.clearTimeout(settleTimerRef.current);
      settleTimerRef.current = null;
    }
  }

  function finishSettling() {
    const current = motionRef.current;
    if (!current || current.phase !== "settling") return;
    clearSettleTimer();
    if (current.accepted && current.targetIndex != null) {
      setActiveIndex(Math.max(0, Math.min(current.targetIndex, imageItems.length - 1)));
    }
    setStackMotion(null);
  }

  function queueSettleFallback() {
    clearSettleTimer();
    settleTimerRef.current = window.setTimeout(finishSettling, 320);
  }

  function canSwipeFrom(index: number, direction: 1 | -1) {
    const nextIndex = index + direction;
    return nextIndex >= 0 && nextIndex < imageItems.length;
  }

  function stackPose(offset: number): CardPose & { zIndex: number } {
    const rawDepth = Math.abs(offset);
    if (rawDepth < 0.001) {
      return { x: 0, y: 0, scale: 1, rotate: 0, opacity: 1, zIndex: 20 };
    }
    const side = offset > 0 ? 1 : -1;
    const towardAvatar = side === (isRight ? 1 : -1);
    const depth = Math.min(rawDepth, 3);
    const firstLayer = Math.min(depth, 1);
    const extraDepth = Math.max(depth - 1, 0);
    const xSpread = towardAvatar
      ? (8 * firstLayer + extraDepth * 4)
      : (18 * firstLayer + extraDepth * 12);
    const y = 6 * firstLayer + extraDepth * 5;
    const scale = 1 - depth * 0.04;
    const rotateSpread = towardAvatar
      ? (0.45 * firstLayer + extraDepth * 0.2)
      : (1.15 * firstLayer + extraDepth * 0.5);
    const opacity = Math.max(towardAvatar ? 0.34 : 0.44, 1 - depth * (towardAvatar ? 0.22 : 0.18));
    const zIndex = Math.max(1, 10 - Math.ceil(depth));
    return { x: side * xSpread, y, scale, rotate: side * rotateSpread, opacity, zIndex };
  }

  function mixPose(from: CardPose, to: CardPose, progress: number): CardPose {
    const p = Math.max(0, Math.min(progress, 1));
    return {
      x: from.x + (to.x - from.x) * p,
      y: from.y + (to.y - from.y) * p,
      scale: from.scale + (to.scale - from.scale) * p,
      rotate: from.rotate + (to.rotate - from.rotate) * p,
      opacity: from.opacity + (to.opacity - from.opacity) * p,
    };
  }

  function cardLayerStyle(pose: CardPose, zIndex: number, transition = "none"): React.CSSProperties {
    return {
      transform: `translate3d(${pose.x}px, ${pose.y}px, 0) scale(${pose.scale}) rotate(${pose.rotate}deg)`,
      opacity: pose.opacity,
      zIndex,
      transition,
    };
  }

  const stackShift = motion?.targetIndex != null ? motion.direction * motionProgress : 0;
  const stackAnchorIndex = baseIndex + stackShift;
  const backgroundTransition = motion?.phase === "settling"
    ? "transform 240ms cubic-bezier(0.22, 1, 0.36, 1), opacity 180ms ease-out"
    : "none";
  const backgroundEntries = imageItems
    .map((item, index) => ({ item, index, offset: index - stackAnchorIndex }))
    .filter(({ index, offset }) => (
      index !== baseIndex
      && index !== motion?.targetIndex
      && Math.abs(offset) <= 3.2
    ))
    .sort((a, b) => {
      const depthDelta = Math.abs(b.offset) - Math.abs(a.offset);
      if (Math.abs(depthDelta) > 0.01) return depthDelta;
      return a.index - b.index;
    });

  const frontPose: CardPose = { x: 0, y: 0, scale: 1, rotate: 0, opacity: 1 };
  const targetStartPose = motion?.targetIndex != null ? stackPose(motion.direction) : null;
  const currentRestPose = motion?.targetIndex != null ? stackPose(-motion.direction) : null;
  const currentExitPose: CardPose = motion?.targetIndex != null
    ? currentRestPose || frontPose
    : {
        x: motion ? -motion.direction * 14 : 0,
        y: motion ? 2 : 0,
        scale: motion ? 0.98 : 1,
        rotate: motion ? -motion.direction * 0.7 : 0,
        opacity: 1,
      };
  const currentPose = motion ? mixPose(frontPose, currentExitPose, motionProgress) : frontPose;
  const targetPose = motion && targetItem
    ? mixPose(targetStartPose || frontPose, frontPose, motionProgress)
    : frontPose;
  const layerFlipProgress = 0.48;
  const targetLayerZIndex = targetStartPose && motionProgress < layerFlipProgress
    ? targetStartPose.zIndex
    : 24;
  const currentLayerZIndex = currentRestPose && motionProgress >= layerFlipProgress
    ? currentRestPose.zIndex
    : 24;

  function stopBubbleGesture(event: React.SyntheticEvent) {
    event.stopPropagation();
  }

  function handlePointerDown(event: React.PointerEvent<HTMLButtonElement>) {
    if (motionRef.current?.phase === "settling") return;
    event.stopPropagation();
    dragStartX.current = event.clientX;
    dragBaseIndexRef.current = normalizedIndex;
    dragDirectionRef.current = null;
    suppressClickRef.current = false;
    clearSettleTimer();
    setStackMotion(null);
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Some embedded WebViews do not expose pointer capture consistently.
    }
  }

  function handlePointerMove(event: React.PointerEvent<HTMLButtonElement>) {
    event.stopPropagation();
    const startX = dragStartX.current;
    if (startX == null) return;
    const deltaX = event.clientX - startX;
    if (Math.abs(deltaX) > 6) suppressClickRef.current = true;
    if (Math.abs(deltaX) <= dragActivationDistance) {
      return;
    }
    const direction = dragDirectionRef.current ?? (deltaX < 0 ? 1 : -1);
    dragDirectionRef.current = direction;
    const base = dragBaseIndexRef.current;
    const directionalDelta = direction === 1 ? -deltaX : deltaX;
    const effectiveDistance = Math.max(0, directionalDelta - dragActivationDistance);
    const nextIndex = base + direction;
    const hasTarget = nextIndex >= 0 && nextIndex < imageItems.length;
    const progress = hasTarget
      ? Math.min(effectiveDistance / swipeDistance, 1)
      : Math.min(effectiveDistance / swipeDistance, 0.18);
    setStackMotion({
      phase: "dragging",
      baseIndex: base,
      direction,
      targetIndex: hasTarget ? nextIndex : null,
      progress,
      accepted: false,
    });
  }

  function handlePointerUp(event: React.PointerEvent<HTMLButtonElement>) {
    event.stopPropagation();
    const startX = dragStartX.current;
    dragStartX.current = null;
    const lockedDirection = dragDirectionRef.current;
    dragDirectionRef.current = null;
    if (startX == null) return;
    const deltaX = event.clientX - startX;
    if (!lockedDirection && Math.abs(deltaX) <= 6) {
      return;
    }
    const direction: 1 | -1 = lockedDirection ?? (deltaX < 0 ? 1 : -1);
    const base = dragBaseIndexRef.current;
    const directionalDelta = direction === 1 ? -deltaX : deltaX;
    if (directionalDelta <= dragActivationDistance) {
      suppressClickRef.current = true;
      setStackMotion(null);
      return;
    }
    const effectiveDistance = directionalDelta - dragActivationDistance;
    const accepted = effectiveDistance >= commitDistance && canSwipeFrom(base, direction);
    const nextIndex = base + direction;
    suppressClickRef.current = true;
    setStackMotion({
      phase: "settling",
      baseIndex: base,
      direction,
      targetIndex: canSwipeFrom(base, direction) ? nextIndex : null,
      progress: accepted ? 1 : 0,
      accepted,
    });
    queueSettleFallback();
  }

  function handleSwipeTransitionEnd(event: React.TransitionEvent<HTMLSpanElement>) {
    if (event.target !== event.currentTarget || event.propertyName !== "transform") return;
    finishSettling();
  }

  function handleClick() {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    setPreviewImage({ src: activePreviewSrc, alt: activePreviewAlt });
  }

  return (
    <>
      <button
        type="button"
        className={`group relative block h-[216px] w-[162px] touch-pan-y overflow-visible text-left ${
          isRight ? "self-end" : "self-start"
        }`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={(event) => {
          event.stopPropagation();
          dragStartX.current = null;
          dragDirectionRef.current = null;
          setStackMotion(null);
        }}
        onTouchStart={stopBubbleGesture}
        onTouchMove={stopBubbleGesture}
        onTouchEnd={stopBubbleGesture}
        onTouchCancel={stopBubbleGesture}
        onClick={handleClick}
        onDragStart={(event) => event.preventDefault()}
        aria-label={`${imageItems.length} 张图片，滑动切换，点击查看当前第 ${normalizedIndex + 1} 张`}
        style={{ perspective: 800, transformStyle: "preserve-3d" }}
      >
        {backgroundEntries.map(({ item, offset, index }) => {
          const src = attachmentPreviewSrc(item);
          const nearFront = Math.abs(offset) < 1;
          const pose = stackPose(offset);
          return (
            <span
              key={`${item.id}-back-${index}`}
              data-image-index={index}
              className={`pointer-events-none absolute inset-0 overflow-hidden rounded-[14px] bg-gray-100 ${
                nearFront
                  ? "shadow-[0_6px_18px_rgba(15,23,42,0.11)]"
                  : "shadow-[0_4px_14px_rgba(15,23,42,0.10)]"
              }`}
              style={cardLayerStyle(pose, pose.zIndex, backgroundTransition)}
              aria-hidden="true"
            >
              <img
                src={src}
                alt=""
                className="h-full w-full object-cover"
                loading={nearFront ? "eager" : "lazy"}
                draggable={false}
              />
            </span>
          );
        })}
        {targetItem && motion ? (
          <span
            key={`${targetItem.id}-target-${motion.targetIndex}`}
            className="pointer-events-none absolute inset-0 overflow-hidden rounded-[14px] bg-gray-100 shadow-[0_7px_20px_rgba(15,23,42,0.12)]"
            style={cardLayerStyle(targetPose, targetLayerZIndex, movingTransition)}
            aria-hidden="true"
          >
            <img
              src={attachmentPreviewSrc(targetItem)}
              alt=""
              className="h-full w-full object-cover"
              loading="eager"
              draggable={false}
            />
          </span>
        ) : null}
        <span
          key={`${currentItem.id}-current-${baseIndex}`}
          className="pointer-events-none absolute inset-0 overflow-hidden rounded-[14px] bg-gray-100 shadow-[0_7px_20px_rgba(15,23,42,0.12)]"
          style={cardLayerStyle(currentPose, targetItem && motion ? currentLayerZIndex : 24, movingTransition)}
          onTransitionEnd={handleSwipeTransitionEnd}
        >
          <img
            src={attachmentPreviewSrc(currentItem)}
            alt={currentItem.alt || "图片"}
            className="h-full w-full object-cover"
            loading="eager"
            draggable={false}
          />
        </span>
      </button>
      {previewImage ? (
        <ImagePreviewOverlay
          src={previewImage.src}
          alt={previewImage.alt || activePreviewAlt}
          onClose={() => setPreviewImage(null)}
        />
      ) : null}
    </>
  );
}

export function ChatAttachmentBlock({
  attachments,
  align = "left",
  kinds,
}: {
  attachments?: ChatAttachment[];
  align?: "left" | "right";
  kinds?: ChatAttachmentKind[];
}) {
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null);
  const allowed = kinds?.length ? new Set(kinds) : null;
  const items = Array.isArray(attachments)
    ? attachments.filter((item) => attachmentSrc(item) && (!allowed || allowed.has(item.kind)))
    : [];
  if (!items.length) return null;
  const imageItems = items.filter((item) => item.kind === "image");
  const nonImageItems = items.filter((item) => item.kind !== "image");
  return (
    <div className={`flex max-w-full flex-col gap-1.5 ${align === "right" ? "items-end" : "items-start"}`}>
      {imageItems.length >= 2 ? <ImageAttachmentGallery items={imageItems} align={align} /> : null}
      {(imageItems.length >= 2 ? nonImageItems : items).map((item) => {
        const src = attachmentSrc(item);
        if (item.kind === "image") {
          const previewSrc = attachmentPreviewSrc(item);
          return (
            <button
              key={item.id}
              type="button"
              className="block max-w-full overflow-hidden rounded-[14px] text-left active:opacity-80"
              onClick={(event) => {
                event.stopPropagation();
                setPreviewImage({ src: previewSrc, alt: item.alt || "图片" });
              }}
              aria-label="预览图片"
            >
              <img
                src={previewSrc}
                alt={item.alt || "图片"}
                className="max-h-[260px] max-w-full rounded-[14px] object-cover"
                loading="lazy"
              />
            </button>
          );
        }
        if (item.kind === "document") {
          const size = formatAttachmentSize(item.size);
          const name = String(item.name || item.alt || "文档").trim();
          return (
            <a
              key={item.id}
              href={src}
              target="_blank"
              rel="noreferrer"
              className={`flex max-w-[236px] items-center gap-2 rounded-[14px] border border-gray-200/80 bg-white/88 px-3 py-2 text-gray-700 shadow-sm backdrop-blur active:opacity-80 ${
                align === "right" ? "self-end" : "self-start"
              }`}
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-gray-100 text-gray-500">
                <FileTextIcon />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-semibold leading-4">{name}</span>
                <span className="block truncate text-[11px] font-medium leading-4 text-gray-400">{size || item.mime || "文本附件"}</span>
              </span>
            </a>
          );
        }
        return <ChatVoiceBar key={item.id} item={item} src={src} align={align} />;
      })}
      {previewImage ? (
        <ImagePreviewOverlay
          src={previewImage.src}
          alt={previewImage.alt}
          onClose={() => setPreviewImage(null)}
        />
      ) : null}
    </div>
  );
}

type ChatBubbleFrameProps = {
  children: React.ReactNode;
  className: string;
  style?: React.CSSProperties;
  decorated?: boolean;
  skin?: BubbleSkinKey;
  align?: "left" | "right";
};

export const ChatBubbleFrame = React.forwardRef<HTMLDivElement, ChatBubbleFrameProps>(function ChatBubbleFrame({
  children,
  className,
  style,
  decorated = false,
  skin,
  align = "left",
}, ref) {
  const resolvedSkin = skin || (decorated ? "heart-rabbit" : undefined);
  if (!resolvedSkin) {
    return (
      <div ref={ref} className={className} style={style}>
        {children}
      </div>
    );
  }
  return (
    <div
      ref={ref}
      className={`relative isolate overflow-visible ${className} ${align === "right" ? "self-end" : ""}`}
      style={style}
    >
      <BubbleSkinLayer skin={resolvedSkin} />
      <div className="relative z-10">
        {children}
      </div>
      <span className="pointer-events-none absolute inset-0 z-20 overflow-visible" aria-hidden="true">
        {getBubbleStickers(resolvedSkin).map((sticker) => (
          <span
            key={sticker.id}
            className="absolute grid select-none place-items-center leading-none"
            style={resolveBubbleStickerStyle(sticker)}
          >
            {sticker.type === "image" ? (
              <img
                src={sticker.src}
                alt=""
                className="h-full w-full object-contain"
                draggable={false}
              />
            ) : (
              <span
                className="whitespace-pre"
                style={{
                  color: "rgba(107,107,107,1)",
                  fontSize: `${sticker.size}px`,
                  fontWeight: 800,
                  textShadow: "0 1px 8px rgba(70,63,54,0.08)",
                }}
              >
                {sticker.text}
              </span>
            )}
          </span>
        ))}
      </span>
    </div>
  );
});

export function copyText(text: string, toast: (msg: string) => void) {
  const value = String(text || "").trim();
  if (!value) return;
  navigator.clipboard.writeText(value).then(
    () => toast("已复制"),
    () => toast("复制失败"),
  );
}

export function SummaryBlock({
  label,
  text,
  onClick,
}: {
  label: string;
  text: string;
  onClick?: () => void;
}) {
  return (
    <button
      className="block w-full text-left active:opacity-80"
      onClick={onClick}
    >
      <div className="mb-2.5 flex items-center">
        <div className="mr-2 h-3 w-1 rounded-full bg-gray-200" />
        <h2 className="text-[10px] font-semibold uppercase tracking-widest text-gray-900">{label}</h2>
      </div>
      <p className="whitespace-pre-wrap pl-3 text-[13px] font-normal leading-relaxed text-gray-800">{text}</p>
    </button>
  );
}

export function ChatActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  const actionIconClass = "h-[22px] w-[22px] stroke-[1.6]";
  const icon = label === "表情包"
    ? <SmileIconMini className={actionIconClass} />
    : label === "出行规划"
      ? <RouteIconMini className={actionIconClass} />
      : label === "画画"
        ? <BrushIconMini className={actionIconClass} />
      : label === "图片"
        ? <ImageIconMini className={actionIconClass} />
        : label === "文档"
          ? <FileTextIcon className={actionIconClass} />
        : label === "语音" || label === "发送" || label === "停止"
          ? <MicIconMini className={actionIconClass} />
          : <PhoneIconLarge className={actionIconClass} />;
  return (
    <button className="group flex flex-col items-center" onClick={onClick}>
      <div className="mb-2 flex h-[52px] w-[52px] items-center justify-center rounded-[18px] bg-[#F8F9FA] text-gray-600 transition-transform active:scale-95">
        {icon}
      </div>
      <span className="text-[11px] font-medium tracking-wide text-gray-500">{label}</span>
    </button>
  );
}

export function AvatarBubble({
  image,
  label,
  className,
}: {
  image?: string;
  label: string;
  className: string;
}) {
  if (image) {
    return (
      <div className="h-[32px] w-[32px] shrink-0 overflow-hidden rounded-full shadow-sm">
        <img src={image} alt={label} className="h-full w-full object-cover" />
      </div>
    );
  }
  return <div className={`flex h-[32px] w-[32px] shrink-0 items-center justify-center rounded-full text-[12px] font-medium shadow-sm ${className}`}>{label}</div>;
}
