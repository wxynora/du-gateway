import { useEffect, useState } from "react";
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
import { readLocalChatHistory, readLocalChatHistoryRows, writeLocalChatHistory } from "./storage/chatHistoryDb";
import { SummaryBlock } from "./ChatPresentation";

type DailyReport = {
  report_date?: string;
  rounds?: number;
  keywords?: string[];
  done_count?: number;
  summary_text?: string;
  generated_at?: string;
};

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

export function ChatsHome({
  dailyWhisper,
  dailyReport,
  duAvatarImage,
  benbenAvatarImage,
  groupTitle,
  privateWindowId,
  groupWindowId,
  onOpenDu,
  onOpenGroup,
  onOpenWenyou,
  onRefreshTodayNote,
  onRefreshDailyReport,
  todayNoteRefreshing,
  dailyRefreshing,
}: {
  dailyWhisper: string;
  dailyReport: DailyReport | null;
  duAvatarImage: string;
  benbenAvatarImage: string;
  groupTitle: string;
  privateWindowId: string;
  groupWindowId: string;
  onOpenDu: () => void;
  onOpenGroup: () => void;
  onOpenWenyou: () => void;
  onRefreshTodayNote: () => void;
  onRefreshDailyReport: () => void;
  todayNoteRefreshing: boolean;
  dailyRefreshing: boolean;
}) {
  const groupDisplayTitle = getDisplayGroupChatTitle(groupTitle);
  const [duPreview, setDuPreview] = useState("主会话");
  const [duTime, setDuTime] = useState("主会话");
  const [groupPreview, setGroupPreview] = useState(groupDisplayTitle);
  const [groupTime, setGroupTime] = useState("群聊");
  const [wenyouPreview, setWenyouPreview] = useState("独立文游会话");
  const [wenyouTime, setWenyouTime] = useState("独立会话");

  const reportSummary = dailyReport
    ? `聊了 ${String(dailyReport.rounds || 0)} 轮 · ${Array.isArray(dailyReport.keywords) && dailyReport.keywords.length ? dailyReport.keywords.join(" / ") : "暂无关键词"}`
    : "今天的日报还没生成。";

  useEffect(() => {
    setGroupPreview((prev) => (prev === DEFAULT_GROUP_CHAT_TITLE || !String(prev || "").trim() ? groupDisplayTitle : prev));
  }, [groupDisplayTitle]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const did = await getOrCreatePanelDeviceId();
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
        <div className="space-y-5">
          <SummaryBlock
            label="Today Note"
            text={todayNoteRefreshing ? "正在刷新..." : dailyWhisper || "今天还没有新的 note。"}
            onClick={onRefreshTodayNote}
          />
          <div className="ml-3 h-px w-full bg-gray-50" />
          <SummaryBlock
            label="日报摘要"
            text={dailyRefreshing ? "正在刷新..." : reportSummary}
            onClick={onRefreshDailyReport}
          />
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
