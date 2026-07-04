import { useEffect, useState } from "react";
import { apiJson, getOrCreatePanelDeviceId } from "./api";
import strawberryScriptFontUrl from "../assets/fonts/cookie-regular.ttf?url";
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
  onRefreshTodayNote,
  todayNoteRefreshing,
  hasAppBackground = false,
  hasDarkAppBackground = false,
}: {
  dailyWhisper: string;
  duAvatarImage: string;
  benbenAvatarImage: string;
  groupTitle: string;
  privateWindowId: string;
  groupWindowId: string;
  onOpenDu: () => void;
  onOpenGroup: () => void;
  onRefreshTodayNote: () => void;
  todayNoteRefreshing: boolean;
  hasAppBackground?: boolean;
  hasDarkAppBackground?: boolean;
}) {
  const groupDisplayTitle = getDisplayGroupChatTitle(groupTitle);
  const [duPreview, setDuPreview] = useState("主会话");
  const [duTime, setDuTime] = useState("主会话");
  const [groupPreview, setGroupPreview] = useState(groupDisplayTitle);
  const [groupTime, setGroupTime] = useState("群聊");
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

  return (
    <div
      className={`${hasAppBackground ? "bg-transparent" : "bg-white"} pb-8`}
      style={{
        paddingTop: "calc(env(safe-area-inset-top, 0px) + 44px)",
        fontFamily: "'Microsoft YaHei', sans-serif",
        "--sumi-main-row-text": hasDarkAppBackground ? "rgba(255,255,255,0.92)" : "#111827",
        "--sumi-main-row-muted": hasDarkAppBackground ? "rgba(255,255,255,0.58)" : "#4b5563",
        "--sumi-main-row-border": hasDarkAppBackground ? "rgba(255,255,255,0.12)" : "#f9fafb",
      } as React.CSSProperties}
    >
      <div className="px-4">
        <h1 className={`mb-6 text-[22px] font-medium tracking-tight ${hasDarkAppBackground ? "text-white drop-shadow-[0_1px_10px_rgba(0,0,0,0.35)]" : "text-gray-900"}`}>会话</h1>
        <div className="w-full max-w-[600px]">
          <AnniversaryTopBar dayCount={anniversaryDayCount} />
          <div className="mt-3 w-full max-w-[375px]">
            <TodayNoteWidget
              text={todayNoteRefreshing ? "正在刷新..." : dailyWhisper || "今天还没有新的 note。"}
              refreshing={todayNoteRefreshing}
              onClick={onRefreshTodayNote}
            />
          </div>
        </div>
      </div>

      <div className={`mt-6 h-2 ${hasAppBackground ? hasDarkAppBackground ? "bg-black/16" : "bg-white/28" : "bg-[#F8F9FA]"}`} />

      <div className={hasAppBackground ? hasDarkAppBackground ? "border-y border-white/16 bg-black/28" : "border-y border-white/55 bg-white/74" : "bg-white"}>
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
      </div>
    </div>
  );
}

function AnniversaryTopBar({ dayCount }: { dayCount: number }) {
  return (
    <div
      className="relative flex h-[72px] w-full max-w-[375px] items-center justify-between overflow-hidden border-b border-[#1A1A1A]/[0.08] bg-[#F9F8F6] px-5 shadow-[0_4px_20px_rgba(0,0,0,0.03)] active:bg-[#F2F1EF]"
      style={{
        fontFamily: "'Inter', 'Microsoft YaHei', sans-serif",
      }}
    >
      <div className="pointer-events-none absolute bottom-[-10px] left-5 h-[60px] w-10 rounded-t-full border border-[#C4A484]/20" />

      <div className="relative z-10 flex flex-col">
        <div className="flex items-baseline gap-1 text-[15px] tracking-[-0.01em] text-[#1A1A1A]" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>
          <span>わたり</span>
          <span className="text-[11px] italic font-normal text-[#C4A484]">with</span>
          <span>すみか</span>
        </div>
        <div className="mt-0.5 text-[8px] font-medium uppercase tracking-[0.15em] text-[#8C8C8C]">Commemoration</div>
      </div>

      <div className="pointer-events-none absolute left-[60%] flex h-full w-[100px] -translate-x-1/2 items-center justify-center">
        <svg className="h-6 w-full fill-none stroke-[#D92B2B]" viewBox="0 0 100 24" aria-hidden="true">
          <path
            className="animate-[anniversary-pulse-draw_3s_ease-in-out_infinite]"
            d="M0,12 L35,12 L40,4 L45,20 L50,8 L55,12 L100,12"
            strokeWidth="0.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="200"
            strokeDashoffset="200"
          />
        </svg>
      </div>

      <div className="relative z-10 text-right">
        <div className="flex items-start justify-end">
          <span className="text-[26px] font-medium leading-none text-[#1A1A1A]" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>
            {dayCount}
          </span>
          <span className="ml-0.5 mt-1 text-[10px] font-normal text-[#1A1A1A]">天</span>
          <span className="ml-1 mt-1.5 h-[3px] w-[3px] self-start rounded-full bg-[#D92B2B]" />
        </div>
        <div className="mt-0.5 text-[8px] font-medium uppercase tracking-[0.15em] text-[#8C8C8C]">Together</div>
      </div>

      <style>
        {`@keyframes anniversary-pulse-draw {
          0% { stroke-dashoffset: 200; opacity: 0; }
          30% { opacity: 0.6; }
          70% { opacity: 0.6; }
          100% { stroke-dashoffset: 0; opacity: 0; }
        }`}
      </style>
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
  const textWeight = Array.from(text.trim()).reduce((sum, char) => {
    if (/\s/.test(char)) return sum;
    return sum + (char.charCodeAt(0) > 255 ? 1 : 0.55);
  }, 0);
  const estimatedLineCount = Math.min(5, Math.max(1, Math.ceil(textWeight / 23)));
  const adaptiveHeight = 150 + estimatedLineCount * 18;

  return (
    <button
      className="relative flex w-full flex-col overflow-hidden border border-[#F4B3C1]/60 bg-[#FFF0F5] p-2.5 text-left shadow-[0_10px_30px_rgba(231,84,128,0.14)] transition-transform active:scale-[0.985]"
      style={{
        height: adaptiveHeight,
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
          <div className="text-[30px] leading-none text-[#E75480]" style={{ fontFamily: "'TodayNoteScript', 'Brush Script MT', cursive" }}>Du want to say</div>
          <div className="-mt-[2px] text-[9px] uppercase tracking-[0.22em] text-[#FFB7C5]">Sweet Memories Memo</div>
        </div>

        <div className="flex min-h-0 flex-1 items-center justify-center border-y border-[#FFF0F5] py-2">
          <p className="line-clamp-5 whitespace-pre-wrap text-center text-[13px] font-medium leading-relaxed text-[#5D4037]">{text}</p>
        </div>

        <div className="mt-1.5 flex items-end">
          <div className="border-t border-gray-100 pt-0.5 text-[8px] text-gray-400">TODAY</div>
        </div>
      </div>

      <div className="absolute bottom-2 left-3 z-10 text-[7px] font-bold uppercase tracking-[0.08em] text-[#E75480]/50">
        Zakkaya Stationery
      </div>

      <style>
        {`@font-face {
          font-family: 'TodayNoteScript';
          src: url("${strawberryScriptFontUrl}") format("truetype");
          font-style: normal;
          font-weight: 400;
          font-display: block;
        }`}
      </style>
    </button>
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
  tone: "du" | "group";
  avatarImage?: string;
  pinned?: boolean;
  onClick: () => void;
}) {
  const palette = tone === "group"
    ? { shell: "bg-[#FFF3D7] text-[#8A5A10]" }
    : { shell: "bg-[#F0F4F8] text-[#4A5568]" };
  return (
    <button className="flex w-full items-center px-4 py-3.5 text-left transition-colors active:bg-white/12" onClick={onClick}>
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
      <div className={`ml-3 min-w-0 flex-1 pt-0.5 ${pinned ? "border-b border-gray-50 pb-3.5" : ""}`} style={pinned ? { borderBottomColor: "var(--sumi-main-row-border, #f9fafb)" } : undefined}>
        <div className="mb-1 flex items-baseline justify-between">
          <span className="text-[16px] font-medium text-gray-900" style={{ color: "var(--sumi-main-row-text, #111827)" }}>{title}</span>
          <span className="text-[11px] font-normal text-gray-900" style={{ color: "var(--sumi-main-row-muted, #111827)" }}>{time}</span>
        </div>
        <p className="truncate text-[13px] font-normal text-gray-600" style={{ color: "var(--sumi-main-row-muted, #4b5563)" }}>{preview}</p>
      </div>
    </button>
  );
}
