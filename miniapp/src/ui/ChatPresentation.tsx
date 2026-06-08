import React, { useRef, useState } from "react";
import DOMPurify from "dompurify";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import angryEmojiFaceUrl from "../assets/angry-emoji-face.png?url";
import angryEmojiMarkUrl from "../assets/angry-emoji-mark.png?url";
import peekRabbitStickerUrl from "../assets/peek-rabbit-sticker.png?url";
import sumikaBubbleStickerUrl from "../assets/sumika-bubble-sticker.png?url";
import type { BubbleSkinKey } from "./chatAppearance";
import { ImageIconMini, MicIconMini, PhoneIconLarge, RouteIconMini, SmileIconMini } from "./icons";
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

function getBubbleStickers(skin: BubbleSkinKey): BubbleSticker[] {
  if (skin === "angry-emoji") return ANGRY_EMOJI_BUBBLE_STICKERS;
  if (skin === "peek-rabbit") return PEEK_RABBIT_BUBBLE_STICKERS;
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

function BubbleSkinLayer({ skin }: { skin: BubbleSkinKey }) {
  if (skin === "angry-emoji") return <AngryEmojiBubbleSkin />;
  if (skin === "peek-rabbit") return <PeekRabbitBubbleSkin />;
  return <HeartRabbitBubbleSkin />;
}

export function formatTokenCountValue(value?: number): string {
  return value ? `${value}tokens` : "";
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
            className="inline-block h-[2.5px] w-[2.5px] rounded-full bg-[#5F6C7B] animate-pulse"
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
  return String(item.remoteUrl || item.localUrl || item.thumbUrl || "").trim();
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
  if (!seconds) return 112;
  return Math.max(104, Math.min(188, 92 + seconds * 4));
}

function ChatVoiceBar({ item, src, align }: { item: ChatAttachment; src: string; align: "left" | "right" }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [durationMs, setDurationMs] = useState(item.durationMs || 0);
  const duration = formatAudioDuration(durationMs);
  const width = audioBarWidth(durationMs);
  const isRight = align === "right";

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
    <div className={`max-w-full ${isRight ? "self-end" : "self-start"}`}>
      <button
        type="button"
        className={`flex h-[28px] max-w-full items-center gap-2 text-current transition-opacity active:opacity-65 ${isRight ? "flex-row-reverse" : ""}`}
        style={{ width }}
        onClick={() => void togglePlayback()}
        aria-label={playing ? "暂停语音" : "播放语音"}
      >
        <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center" aria-hidden="true">
          {playing ? (
            <span className="flex h-[12px] items-center gap-[3px]">
              <span className="h-full w-[3px] rounded-full bg-current" />
              <span className="h-full w-[3px] rounded-full bg-current" />
            </span>
          ) : (
            <span
              className="block h-0 w-0 border-y-[6px] border-l-[9px] border-y-transparent border-l-current"
              style={isRight ? { transform: "scaleX(-1)" } : undefined}
            />
          )}
        </span>
        <span className={`flex flex-1 items-center gap-[3px] ${isRight ? "justify-end" : "justify-start"}`} aria-hidden="true">
          <span className={`w-[2px] rounded-full bg-current/55 ${playing ? "h-[13px]" : "h-[7px]"}`} />
          <span className={`w-[2px] rounded-full bg-current/70 ${playing ? "h-[17px]" : "h-[12px]"}`} />
          <span className={`w-[2px] rounded-full bg-current/50 ${playing ? "h-[10px]" : "h-[8px]"}`} />
        </span>
        <span className="shrink-0 text-[12px] font-semibold leading-none tabular-nums opacity-75">
          {duration || "语音"}
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

export function ChatAttachmentBlock({
  attachments,
  align = "left",
  kinds,
}: {
  attachments?: ChatAttachment[];
  align?: "left" | "right";
  kinds?: ChatAttachmentKind[];
}) {
  const allowed = kinds?.length ? new Set(kinds) : null;
  const items = Array.isArray(attachments)
    ? attachments.filter((item) => attachmentSrc(item) && (!allowed || allowed.has(item.kind)))
    : [];
  if (!items.length) return null;
  return (
    <div className={`flex max-w-full flex-col gap-1.5 ${align === "right" ? "items-end" : "items-start"}`}>
      {items.map((item) => {
        const src = attachmentSrc(item);
        if (item.kind === "image") {
          return (
            <a key={item.id} href={src} target="_blank" rel="noreferrer" className="block max-w-full overflow-hidden rounded-[14px] active:opacity-80">
              <img
                src={src}
                alt={item.alt || "图片"}
                className="max-h-[260px] max-w-full rounded-[14px] object-cover"
                loading="lazy"
              />
            </a>
          );
        }
        return <ChatVoiceBar key={item.id} item={item} src={src} align={align} />;
      })}
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
  const icon = label === "表情包"
    ? <SmileIconMini />
    : label === "出行规划"
      ? <RouteIconMini />
      : label === "图片"
        ? <ImageIconMini />
        : label === "语音" || label === "发送" || label === "停止"
          ? <MicIconMini />
          : <PhoneIconLarge />;
  return (
    <button className="group flex flex-col items-center" onClick={onClick}>
      <div className="mb-2.5 flex h-[60px] w-[60px] items-center justify-center rounded-[20px] bg-[#F8F9FA] text-gray-600 transition-transform active:scale-95">
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
