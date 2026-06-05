import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api";
import { VoiceCallScreen } from "./VoiceCallScreen";
import { useToast } from "../toast";
import type { IncomingVoiceCallInvite } from "../voiceCallInvite";

type VoiceConfig = {
  displayName: string;
  subtitle: string;
};

type CallRecordSummary = {
  id: string;
  mode: string;
  started_at: string;
  updated_at: string;
  title: string;
  preview: string;
  turn_count: number;
};

type CallRecordTurn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  kind: string;
  timestamp: string;
};

type CallRecordDetail = CallRecordSummary & {
  turns: CallRecordTurn[];
};

type ViewMode = "home" | "voice" | "records" | "record-detail";
type BackHandler = () => boolean;

const DEFAULT_CONFIG: VoiceConfig = {
  displayName: "渡",
  subtitle: "语音通话中",
};

const surfaceCard =
  "rounded-[28px] border border-gray-100/80 bg-white shadow-[0_8px_30px_-18px_rgba(15,23,42,0.28)]";
const iconButton =
  "flex h-10 w-10 items-center justify-center rounded-full border border-gray-100/80 bg-white text-gray-700 shadow-[0_4px_18px_-12px_rgba(15,23,42,0.35)] transition active:scale-[0.98]";
const softButton =
  "rounded-[16px] border border-gray-100/80 bg-white px-3 py-2 text-[12px] font-medium text-gray-700 shadow-[0_4px_18px_-12px_rgba(15,23,42,0.35)] transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-45";
const dangerButton =
  "rounded-full bg-rose-50 px-3 py-1.5 text-[11px] font-medium text-rose-600 transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-45";

function formatDateTime(value: string): string {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  const normalized = raw.replace("T", " ").replace(/\.\d+/, "").replace(/([+-]\d{2}:\d{2}|Z)$/, "");
  return normalized.slice(0, 16) || raw;
}

function groupByDate(items: CallRecordSummary[]): Array<{ date: string; items: CallRecordSummary[] }> {
  const map = new Map<string, CallRecordSummary[]>();
  for (const item of items || []) {
    const key = formatDateTime(item.started_at).slice(0, 10) || "未知日期";
    map.set(key, [...(map.get(key) || []), item]);
  }
  return Array.from(map.entries()).map(([date, rows]) => ({ date, items: rows }));
}

function RowArrow() {
  return (
    <svg className="h-4 w-4 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

export function CallHubScreen({
  onClose,
  duAvatarImage,
  backHandlerRef,
  incomingInvite,
  onIncomingInviteConsumed,
}: {
  onClose: () => void;
  duAvatarImage: string;
  backHandlerRef?: React.MutableRefObject<BackHandler | null>;
  incomingInvite?: IncomingVoiceCallInvite | null;
  onIncomingInviteConsumed?: () => void;
}) {
  const toast = useToast();
  const [view, setView] = useState<ViewMode>("home");
  const [config, setConfig] = useState<VoiceConfig>(DEFAULT_CONFIG);
  const [dailyWhisper, setDailyWhisper] = useState("");
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [deletingId, setDeletingId] = useState("");
  const [records, setRecords] = useState<CallRecordSummary[]>([]);
  const [activeRecord, setActiveRecord] = useState<CallRecordDetail | null>(null);
  const grouped = useMemo(() => groupByDate(records), [records]);

  const handleBackIntent = useCallback(() => {
    if (view === "home") return false;
    setView("home");
    return true;
  }, [view]);

  useEffect(() => {
    if (!backHandlerRef) return;
    backHandlerRef.current = handleBackIntent;
    return () => {
      if (backHandlerRef.current === handleBackIntent) {
        backHandlerRef.current = null;
      }
    };
  }, [backHandlerRef, handleBackIntent]);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/miniapp-api/voice-config")
      .then((resp) => resp.json().then((data) => ({ resp, data })))
      .then(({ resp, data }) => {
        if (cancelled) return;
        if (!resp.ok || !data?.ok) return;
        setConfig((prev) => ({
          ...prev,
          ...DEFAULT_CONFIG,
          ...(data.config || {}),
        }));
      })
      .catch(() => {});
    apiFetch("/miniapp-api/daily-whisper")
      .then((resp) => resp.json().then((data) => ({ resp, data })))
      .then(({ resp, data }) => {
        if (cancelled) return;
        if (!resp.ok || !data?.ok) return;
        setDailyWhisper(String(data.text || "").trim());
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!incomingInvite?.callId) return;
    setView("voice");
  }, [incomingInvite?.callId]);

  async function loadRecords() {
    setRecordsLoading(true);
    try {
      const resp = await apiFetch("/miniapp-api/call-records");
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      setRecords(Array.isArray(data.items) ? data.items : []);
    } catch (e: any) {
      toast(e?.message || "通话记录加载失败");
    } finally {
      setRecordsLoading(false);
    }
  }

  async function openRecords() {
    setView("records");
    await loadRecords();
  }

  async function openRecordDetail(id: string) {
    try {
      const resp = await apiFetch(`/miniapp-api/call-records/${encodeURIComponent(id)}`);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      setActiveRecord(data.item || null);
      setView("record-detail");
    } catch (e: any) {
      toast(e?.message || "通话详情加载失败");
    }
  }

  async function deleteRecord(id: string) {
    const cid = String(id || "").trim();
    if (!cid || deletingId) return;
    const ok = window.confirm("确定删除这条通话记录吗？");
    if (!ok) return;
    setDeletingId(cid);
    try {
      const resp = await apiFetch(`/miniapp-api/call-records/${encodeURIComponent(cid)}`, { method: "DELETE" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      setRecords((prev) => prev.filter((item) => item.id !== cid));
      setActiveRecord((prev) => (prev?.id === cid ? null : prev));
      if (view === "record-detail") setView("records");
      toast("已删除");
    } catch (e: any) {
      toast(e?.message || "删除失败");
    } finally {
      setDeletingId("");
    }
  }

  const rowBase =
    "flex w-full items-center gap-3 px-4 py-4 text-left transition active:scale-[0.995]";

  const isVoiceView = view === "voice";

  return (
    <div className={isVoiceView ? "fixed inset-0 z-[80] overflow-auto bg-[#111214] text-white" : "fixed inset-0 z-[80] overflow-auto bg-[#FDFDFD] text-gray-900"}>
      <div
        className={isVoiceView ? "mx-auto min-h-dvh max-w-xl px-0 pb-0 pt-0 safe-bottom" : "mx-auto min-h-dvh w-full max-w-[620px] px-4 pb-8 pt-0 safe-bottom"}
        style={isVoiceView ? undefined : { fontFamily: "'Microsoft YaHei', sans-serif" }}
      >
        {!isVoiceView ? (
        <div className="sticky top-0 z-10 -mx-4 mb-4 flex items-center justify-between border-b border-gray-100/70 bg-[#FDFDFD]/95 px-4 py-3 backdrop-blur">
          <button className={iconButton} onClick={view === "home" ? onClose : () => setView("home")} type="button" aria-label={view === "home" ? "关闭" : "返回"}>
            {view === "home" ? (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 6l12 12M18 6 6 18" /></svg>
            ) : (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m15 6-6 6 6 6" /></svg>
            )}
          </button>
          <div className="text-[16px] font-medium leading-6 tracking-normal text-gray-900">{view === "home" ? "通话" : view === "records" ? "通话记录" : "通话详情"}</div>
          <div className="w-10" />
        </div>
        ) : null}

        {view === "home" ? (
          <div className="flex flex-col gap-4 pb-8">
            <section className={`${surfaceCard} p-4`}>
              <div className="flex items-center gap-4">
                <div className="h-16 w-16 overflow-hidden rounded-full border border-gray-100 bg-gray-50">
                  {duAvatarImage ? (
                    <img src={duAvatarImage} alt={config.displayName} className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center bg-gray-100 text-2xl font-semibold text-gray-700">
                      {(config.displayName || "渡").slice(0, 1)}
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[18px] font-medium leading-6 text-gray-900">{config.displayName || "渡"}</div>
                  <div className="mt-1 text-[12px] leading-5 text-gray-400">{config.subtitle || "语音通话中"}</div>
                  {dailyWhisper ? (
                    <div className="mt-3 rounded-[18px] bg-gray-50 px-3 py-2 text-[12px] leading-5 text-gray-500">
                      {dailyWhisper}
                    </div>
                  ) : null}
                </div>
              </div>
            </section>

            <section className={`${surfaceCard} overflow-hidden`}>
              <button type="button" className={rowBase} onClick={() => setView("voice")}>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-medium text-gray-900">语音通话</span>
                  <span className="mt-1 block text-xs text-gray-400">进入语音通话界面</span>
                </span>
                <RowArrow />
              </button>
              <button type="button" className={rowBase + " border-t border-gray-50"} onClick={openRecords}>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-medium text-gray-900">通话记录</span>
                  <span className="mt-1 block text-xs text-gray-400">查看历史通话文字记录</span>
                </span>
                <RowArrow />
              </button>
            </section>
          </div>
        ) : null}

        {view === "voice" ? (
          <div className="pt-0">
            <VoiceCallScreen
              onClose={() => setView("home")}
              duAvatarImage={duAvatarImage}
              incomingInvite={incomingInvite}
              onIncomingInviteConsumed={onIncomingInviteConsumed}
            />
          </div>
        ) : null}

        {view === "records" ? (
          <div className="pb-8">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-sm font-medium text-gray-800">最近通话</div>
              <button type="button" className={softButton} onClick={loadRecords} disabled={recordsLoading}>
                {recordsLoading ? "刷新中..." : "刷新"}
              </button>
            </div>
            <div className="space-y-4">
              {grouped.length ? (
                grouped.map((group) => (
                  <div key={group.date}>
                    <div className="mb-2 px-1 text-[11px] uppercase tracking-[0.12em] text-gray-400">{group.date}</div>
                    <div className={`${surfaceCard} overflow-hidden`}>
                      {group.items.map((item, idx) => (
                        <div key={item.id} className={idx > 0 ? "border-t border-gray-50" : ""}>
                          <div className="flex items-center gap-3 px-4 py-3">
                            <button type="button" className="min-w-0 flex-1 text-left" onClick={() => openRecordDetail(item.id)}>
                              <div className="truncate text-sm font-medium text-gray-900">{item.title || "语音通话"}</div>
                              <div className="mt-1 text-[11px] text-gray-400">
                                {formatDateTime(item.started_at)} · {item.turn_count} 条
                              </div>
                              <div className="mt-2 truncate text-xs text-gray-400">{item.preview || "暂无文字记录"}</div>
                            </button>
                            <button
                              type="button"
                              className={dangerButton}
                              onClick={() => deleteRecord(item.id)}
                              disabled={deletingId === item.id}
                            >
                              {deletingId === item.id ? "删除中..." : "删除"}
                            </button>
                            <RowArrow />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className={`${surfaceCard} px-4 py-8 text-center text-sm text-gray-400`}>
                  {recordsLoading ? "加载中..." : "还没有通话记录"}
                </div>
              )}
            </div>
          </div>
        ) : null}

        {view === "record-detail" ? (
          <div className="pb-8">
            <div className={`${surfaceCard} px-4 py-4`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[16px] font-semibold tracking-tight text-gray-900">{activeRecord?.title || "通话详情"}</div>
                  <div className="mt-1 text-xs text-gray-400">{formatDateTime(activeRecord?.started_at || "")}</div>
                </div>
                {activeRecord?.id ? (
                  <button
                    type="button"
                    className={dangerButton}
                    onClick={() => deleteRecord(activeRecord.id)}
                    disabled={deletingId === activeRecord.id}
                  >
                    {deletingId === activeRecord.id ? "删除中..." : "删除"}
                  </button>
                ) : null}
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {activeRecord?.turns?.length ? (
                activeRecord.turns.map((turn) => (
                  <div
                    key={turn.id}
                    className={
                      `${surfaceCard} px-4 py-3 ` +
                      (turn.role === "user" ? "ml-10" : "mr-10")
                    }
                  >
                    <div className="mb-1 text-[11px] uppercase tracking-[0.12em] text-gray-400">
                      {turn.role === "user" ? "我的语音" : "他的语音"}
                    </div>
                    <div className="text-sm leading-6 text-gray-700">{turn.text}</div>
                    <div className="mt-2 text-[11px] text-gray-400">{formatDateTime(turn.timestamp)}</div>
                  </div>
                ))
              ) : (
                <div className={`${surfaceCard} px-4 py-8 text-center text-sm text-gray-400`}>这条通话还没有内容</div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
