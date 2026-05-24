import { useEffect, useState, type ReactNode } from "react";
import { apiJson, getOrCreatePanelDeviceId } from "./api";
import { DEFAULT_GROUP_CHAT_TITLE, getDisplayGroupChatTitle } from "./chatAppearance";
import {
  pickBetterHistory,
  pickLatestDraftPreview,
  sanitizeHistoryMessages,
  type ChatDraftMessage,
} from "./chatMessages";
import { MAIN_SUMITALK_DISPLAY_WINDOW_ID, sumitalkHistoryPath } from "./chatWindowIds";
import { CornerDownIcon } from "./icons";
import { migrateLocalChatHistoriesToDevice, readLocalChatHistory, readLocalChatHistoryRows, writeLocalChatHistory } from "./storage/chatHistoryDb";

function uniqueNonEmptyStrings(values: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const item = String(value || "").trim();
    if (!item || seen.has(item)) continue;
    seen.add(item);
    out.push(item);
  }
  return out;
}

async function readBestLocalHistoryForWindows(windowIds: string[]): Promise<ChatDraftMessage[]> {
  const rows = await readLocalChatHistoryRows(uniqueNonEmptyStrings(windowIds));
  return rows.reduce(
    (best, row) => {
      const messages = sanitizeHistoryMessages((row?.messages || []) as ChatDraftMessage[]);
      return pickBetterHistory(messages, best, []);
    },
    [] as ChatDraftMessage[],
  );
}

function getAnniversaryDayCount() {
  const start = new Date(2026, 2, 4);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const elapsedDays = Math.max(0, Math.floor((today.getTime() - startDay.getTime()) / 86400000));
  return elapsedDays + 1;
}

export function ChatsHome({
  dailyWhisper,
  duAvatarImage,
  benbenAvatarImage,
  groupTitle,
  privateWindowId,
  groupWindowId,
  onOpenDu,
  onOpenGroup,
  onOpenWenyou,
  onRefreshTodayNote,
  todayNoteRefreshing,
}: {
  dailyWhisper: string;
  duAvatarImage: string;
  benbenAvatarImage: string;
  groupTitle: string;
  privateWindowId: string;
  groupWindowId: string;
  onOpenDu: () => void;
  onOpenGroup: () => void;
  onOpenWenyou: () => void;
  onRefreshTodayNote: () => void;
  todayNoteRefreshing: boolean;
}) {
  const groupDisplayTitle = getDisplayGroupChatTitle(groupTitle);
  const [duPreview, setDuPreview] = useState("主会话");
  const [duTime, setDuTime] = useState("主会话");
  const [groupPreview, setGroupPreview] = useState(groupDisplayTitle);
  const [groupTime, setGroupTime] = useState("群聊");
  const [wenyouPreview, setWenyouPreview] = useState("独立文游会话");
  const [wenyouTime, setWenyouTime] = useState("独立会话");
  const anniversaryDayCount = getAnniversaryDayCount();

  useEffect(() => {
    setGroupPreview((prev) => (prev === DEFAULT_GROUP_CHAT_TITLE || !String(prev || "").trim() ? groupDisplayTitle : prev));
  }, [groupDisplayTitle]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const did = await getOrCreatePanelDeviceId();
        await migrateLocalChatHistoriesToDevice(did);
        const mainWindowId = String(privateWindowId || MAIN_SUMITALK_DISPLAY_WINDOW_ID).trim() || MAIN_SUMITALK_DISPLAY_WINDOW_ID;
        const mainLocalMessages = sanitizeHistoryMessages(await readLocalChatHistory(did, mainWindowId));
        const legacyLocalMessages = mainWindowId === "sumitalk-main"
          ? []
          : sanitizeHistoryMessages(await readLocalChatHistory(did, "sumitalk-main"));
        const recoveredMainMessages = await readBestLocalHistoryForWindows([mainWindowId, MAIN_SUMITALK_DISPLAY_WINDOW_ID]);
        const localMessages = pickBetterHistory(recoveredMainMessages, pickBetterHistory(mainLocalMessages, legacyLocalMessages, []), []);
        if (!cancelled && localMessages.length) {
          const pickedLocal = pickLatestDraftPreview(localMessages);
          setDuPreview(pickedLocal.preview);
          setDuTime(pickedLocal.time);
          await writeLocalChatHistory(did, mainWindowId, localMessages);
        }
        const j = await apiJson<{ ok?: boolean; messages?: ChatDraftMessage[] }>(sumitalkHistoryPath(MAIN_SUMITALK_DISPLAY_WINDOW_ID));
        if (cancelled) return;
        const remoteMessages = sanitizeHistoryMessages(Array.isArray(j?.messages) ? j.messages : []);
        const nextMessages = pickBetterHistory(remoteMessages, localMessages, []);
        const picked = pickLatestDraftPreview(nextMessages);
        setDuPreview(picked.preview);
        setDuTime(picked.time);
        if (nextMessages === remoteMessages && remoteMessages.length) {
          await writeLocalChatHistory(did, mainWindowId, remoteMessages);
        }

        const groupCurrentLocalMessages = sanitizeHistoryMessages(await readLocalChatHistory(did, groupWindowId));
        const groupRecoveredMessages = await readBestLocalHistoryForWindows([groupWindowId]);
        const groupLocalMessages = pickBetterHistory(groupRecoveredMessages, groupCurrentLocalMessages, []);
        if (!cancelled && groupLocalMessages.length) {
          const pickedLocalGroup = pickLatestDraftPreview(groupLocalMessages);
          setGroupPreview(pickedLocalGroup.preview);
          setGroupTime(pickedLocalGroup.time);
          await writeLocalChatHistory(did, groupWindowId, groupLocalMessages);
        }
        const groupHistory = await apiJson<{ ok?: boolean; messages?: ChatDraftMessage[] }>(sumitalkHistoryPath(groupWindowId));
        if (cancelled) return;
        const groupRemoteMessages = sanitizeHistoryMessages(Array.isArray(groupHistory?.messages) ? groupHistory.messages : []);
        const groupMessages = pickBetterHistory(groupRemoteMessages, groupLocalMessages, []);
        if (groupMessages.length) {
          const pickedGroup = pickLatestDraftPreview(groupMessages);
          setGroupPreview(pickedGroup.preview);
          setGroupTime(pickedGroup.time);
          if (groupMessages === groupRemoteMessages) {
            await writeLocalChatHistory(did, groupWindowId, groupRemoteMessages);
          }
        }
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, [groupWindowId, privateWindowId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const j = await apiJson<{ ok?: boolean; active?: boolean; session?: { instance_name?: string; startedAt?: string } | null }>("/miniapp-api/wenyou/status");
        if (cancelled) return;
        if (j?.ok && j?.active && j?.session) {
          setWenyouPreview(`当前副本：${String(j.session.instance_name || "系统空间进行中")}`);
          setWenyouTime(String(j.session.startedAt || "").trim() || "进行中");
        }
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div
      className="bg-white pb-8"
      style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 44px)", fontFamily: "'Microsoft YaHei', sans-serif" }}
    >
      <div className="px-4">
        <h1 className="mb-6 text-[22px] font-medium tracking-tight text-gray-900">会话</h1>
        <div className="grid w-full max-w-[600px] grid-cols-2 items-start gap-2 min-[390px]:gap-3">
          <ScaledWidgetFrame baseWidth={320} baseHeight={320}>
            <TodayNoteWidget
              text={todayNoteRefreshing ? "正在刷新..." : dailyWhisper || "今天还没有新的 note。"}
              refreshing={todayNoteRefreshing}
              onClick={onRefreshTodayNote}
            />
          </ScaledWidgetFrame>
          <ScaledWidgetFrame baseWidth={320} baseHeight={320}>
            <AnniversaryWidget dayCount={anniversaryDayCount} />
          </ScaledWidgetFrame>
        </div>
      </div>

      <div className="mt-6 h-2 bg-[#F8F9FA]" />

      <div className="bg-white">
        <ChatEntryRow
          title="渡"
          preview={duPreview}
          time={duTime}
          tone="du"
          avatarImage={duAvatarImage}
          onClick={onOpenDu}
          pinned
        />
        <ChatEntryRow
          title={groupDisplayTitle}
          preview={groupPreview}
          time={groupTime}
          tone="group"
          avatarImage={benbenAvatarImage}
          onClick={onOpenGroup}
        />
        <ChatEntryRow
          title="文游"
          preview={wenyouPreview}
          time={wenyouTime}
          tone="wenyou"
          onClick={onOpenWenyou}
        />
      </div>
    </div>
  );
}

function ScaledWidgetFrame({
  baseWidth,
  baseHeight,
  children,
}: {
  baseWidth: number;
  baseHeight: number;
  children: ReactNode;
}) {
  return (
    <div
      className="relative w-full shrink-0 self-start overflow-visible"
      style={{
        aspectRatio: `${baseWidth} / ${baseHeight}`,
        containerType: "inline-size",
      }}
    >
      <div
        className="absolute left-0 top-0"
        style={{
          width: baseWidth,
          height: baseHeight,
          transform: `scale(min(1, calc(100cqw / ${baseWidth}px)))`,
          transformOrigin: "top left",
        }}
      >
        {children}
      </div>
    </div>
  );
}

function TodayNoteWidget({
  text,
  refreshing,
  onClick,
}: {
  text: string;
  refreshing: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="relative flex h-full w-full flex-col overflow-hidden border border-[#F4B3C1]/60 bg-[#FFF0F5] p-2.5 text-left shadow-[0_10px_30px_rgba(231,84,128,0.14)] transition-transform active:scale-[0.985]"
      style={{
        backgroundImage: "radial-gradient(#FFB7C5 1px, transparent 1px)",
        backgroundSize: "14px 14px",
      }}
      onClick={onClick}
      aria-busy={refreshing}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          backgroundImage: "linear-gradient(rgba(255,255,255,0.14) 50%, transparent 50%)",
          backgroundSize: "100% 2px",
        }}
      />
      <div className="relative z-10 mb-2 flex items-start justify-between">
        <div className="border border-dashed border-[#E75480] bg-white/80 px-1.5 py-0.5 font-mono text-[8px] font-bold uppercase tracking-tight text-[#E75480]">
          ITEM No. 05
        </div>
        <div className="rounded-[2px] bg-[#89CFF0] px-1.5 py-0.5 text-[8px] font-semibold uppercase tracking-[0.12em] text-white">
          New
        </div>
      </div>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col border-2 border-[#E75480] bg-white px-2.5 pb-2.5 pt-4 shadow-[4px_4px_0_#FFB7C5]">
        <div className="absolute -top-1.5 left-[18%] right-[18%] h-3 bg-[radial-gradient(circle,#FFF0F5_4px,transparent_5px)] bg-[length:12px_12px]" />
        <div className="absolute left-1/2 top-[-7px] z-20 h-[15px] w-[56px] -translate-x-1/2 border-x-2 border-white/70 bg-[#89CFF0]/40" />
        <svg className="absolute right-2 top-5 h-4 w-4 rotate-[15deg] fill-[#E75480] opacity-60" viewBox="0 0 32 32" aria-hidden="true">
          <path d="M16 28.5L14.1 26.8C7.1 20.6 2.5 16.4 2.5 11.3C2.5 7.1 5.8 3.8 10 3.8C12.4 3.8 14.6 4.9 16 6.7C17.4 4.9 19.6 3.8 22 3.8C26.2 3.8 29.5 7.1 29.5 11.3C29.5 16.4 24.9 20.6 17.9 26.8L16 28.5Z" />
        </svg>

        <div className="mb-2 text-center">
          <div className="text-[24px] leading-none text-[#E75480]" style={{ fontFamily: '"Brush Script MT", cursive' }}>Strawberry Day</div>
          <div className="-mt-[2px] text-[9px] uppercase tracking-[0.22em] text-[#FFB7C5]">Sweet Memories Memo</div>
        </div>

        <div className="flex min-h-0 flex-1 items-center justify-center border-y border-[#FFF0F5] py-2">
          <p className="line-clamp-4 whitespace-pre-wrap text-center text-[12px] font-medium leading-relaxed text-[#5D4037]">{text}</p>
        </div>

        <div className="mt-1.5 flex items-end">
          <div className="border-t border-gray-100 pt-0.5 text-[8px] text-gray-400">TODAY</div>
        </div>
      </div>

      <div className="absolute bottom-2 left-3 z-10 text-[7px] font-bold uppercase tracking-[0.08em] text-[#E75480]/50">
        Zakkaya Stationery
      </div>
    </button>
  );
}

function AnniversaryWidget({ dayCount }: { dayCount: number }) {
  const serialDay = String(dayCount).padStart(4, "0");

  return (
    <>
      <div
        className="relative flex aspect-square min-h-[172px] w-full flex-col items-center justify-between overflow-hidden rounded-[36px] border-2 border-[#8E7075] bg-[#FFF8FA] px-3.5 py-4 text-[#8E7075] shadow-[0_10px_28px_rgba(142,112,117,0.12)]"
        style={{ filter: "url(#anniversary-pencil-texture)" }}
      >
        <div
          className="absolute inset-0 opacity-30"
          style={{
            backgroundImage: "radial-gradient(#FFD3E0 1px, transparent 1px)",
            backgroundSize: "16px 16px",
          }}
        />
        <div className="pointer-events-none absolute inset-2 rounded-[28px] border border-dashed border-[#F4B5C6]" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 z-[1] h-[130px] w-[130px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#FFD3E0] after:absolute after:inset-[-8px] after:rounded-full after:border-[6px] after:border-dotted after:border-[#FFD3E0]" />

        <div className="relative z-10 flex w-full items-center justify-between text-[8px] font-semibold uppercase tracking-[0.1em]">
          <div className="font-serif italic">MEM-ID: {serialDay}-W/S</div>
          <div>記念日</div>
        </div>

        <svg className="pointer-events-none absolute right-5 top-7 z-10 h-10 w-10 drop-shadow-[2px_2px_0_#FFFFFF]" viewBox="0 0 100 100" aria-hidden="true">
          <path d="M50 95 C 20 80, 5 60, 15 30 C 20 10, 80 10, 85 30 C 95 60, 80 80, 50 95" fill="#F4B5C6" stroke="#8E7075" strokeWidth="3" />
          <path d="M40 15 C 45 5, 55 5, 60 15 L 50 25 Z" fill="#C5E1A5" stroke="#8E7075" strokeWidth="2" />
          <circle cx="40" cy="45" r="2" fill="#8E7075" />
          <circle cx="60" cy="40" r="2" fill="#8E7075" />
          <circle cx="50" cy="60" r="2" fill="#8E7075" />
          <circle cx="35" cy="70" r="2" fill="#8E7075" />
          <circle cx="65" cy="70" r="2" fill="#8E7075" />
        </svg>

        <div className="relative z-10 flex flex-1 flex-col items-center justify-center pt-3">
          <div className="relative -mb-1">
            <div className="font-serif text-[64px] font-extrabold leading-none tracking-tight">{dayCount}</div>
            <div className="absolute bottom-2 right-[-26px] rotate-[5deg] rounded-[10px] border-[1.5px] border-[#8E7075] bg-white px-1.5 py-0.5 text-[10px] font-bold leading-none text-[#F4B5C6]">
              days
            </div>
          </div>
          <div className="mt-3 flex items-center gap-1.5 text-[13px] font-semibold">
            わたり <span className="text-[#F4B5C6]">❤︎</span> すみか
          </div>
        </div>

        <svg
          className="pointer-events-none absolute bottom-11 left-3 z-10 h-12 w-[76px] -rotate-[15deg] animate-[anniversary-bow-float_4s_ease-in-out_infinite]"
          viewBox="0 0 200 100"
          aria-hidden="true"
        >
          <path d="M100 50 Q 130 10, 180 30 Q 190 50, 160 70 Q 130 90, 100 50" fill="white" stroke="#8E7075" strokeWidth="3" />
          <path d="M100 50 Q 70 10, 20 30 Q 10 50, 40 70 Q 70 90, 100 50" fill="white" stroke="#8E7075" strokeWidth="3" />
          <circle cx="100" cy="50" r="12" fill="white" stroke="#8E7075" strokeWidth="3" />
          <path d="M90 60 L 70 95" stroke="#8E7075" strokeWidth="3" strokeLinecap="round" />
          <path d="M110 60 L 130 95" stroke="#8E7075" strokeWidth="3" strokeLinecap="round" />
        </svg>

        <div className="relative z-10 w-full border-t border-[#FFD3E0] pt-2.5 text-center text-[8px] uppercase tracking-[0.06em] opacity-70">
          SINCE 2026.03.04 - ALWAYS TOGETHER
        </div>
      </div>

      <svg className="hidden" aria-hidden="true">
        <defs>
          <filter id="anniversary-pencil-texture">
            <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="3" result="noise" />
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.5" />
            <feColorMatrix
              type="matrix"
              values="
                1 0 0 0 0
                0 0.98 0 0 0
                0 0 0.98 0 0
                0 0 0 1 0"
            />
          </filter>
        </defs>
      </svg>

      <style>
        {`@keyframes anniversary-bow-float {
          0%, 100% { transform: translateY(0) rotate(-15deg); }
          50% { transform: translateY(-5px) rotate(-10deg); }
        }`}
      </style>
    </>
  );
}

function ChatEntryRow({
  title,
  preview,
  time,
  tone,
  avatarImage,
  pinned,
  onClick,
}: {
  title: string;
  preview: string;
  time: string;
  tone: "du" | "group" | "wenyou";
  avatarImage?: string;
  pinned?: boolean;
  onClick: () => void;
}) {
  const palette = tone === "wenyou"
    ? { shell: "bg-[#F8F0F4] text-[#704A5D]" }
    : tone === "group"
      ? { shell: "bg-[#FFF3D7] text-[#8A5A10]" }
      : { shell: "bg-[#F0F4F8] text-[#4A5568]" };
  return (
    <button className="flex w-full items-center px-4 py-3.5 text-left transition-colors active:bg-gray-50" onClick={onClick}>
      <div className="relative shrink-0">
        {avatarImage ? (
          <div className="h-[48px] w-[48px] overflow-hidden rounded-2xl shadow-sm">
            <img src={avatarImage} alt={title} className="h-full w-full object-cover" />
          </div>
        ) : (
          <div className={`flex h-[48px] w-[48px] items-center justify-center rounded-2xl text-[18px] font-medium shadow-sm ${palette.shell}`}>
            {title.slice(0, 1)}
          </div>
        )}
        {pinned ? (
          <div className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-gray-100 bg-white shadow-sm">
            <CornerDownIcon />
          </div>
        ) : null}
      </div>
      <div className={`ml-3 min-w-0 flex-1 pt-0.5 ${pinned ? "border-b border-gray-50 pb-3.5" : ""}`}>
        <div className="mb-1 flex items-baseline justify-between">
          <span className="text-[16px] font-medium text-gray-900">{title}</span>
          <span className="text-[11px] font-normal text-gray-900">{time}</span>
        </div>
        <p className="truncate text-[13px] font-normal text-gray-600">{preview}</p>
      </div>
    </button>
  );
}
