import React, { useEffect, useMemo, useState } from "react";
import { apiFetch, buildApiAssetUrl } from "../api";
import { Btn } from "../components";
import { VoiceCallScreen } from "./VoiceCallScreen";
import { useToast } from "../toast";

type VoiceConfig = {
  displayName: string;
  subtitle: string;
  avatarVersion: number;
  useAvatarImage: boolean;
  avatarUrl: string;
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

const DEFAULT_CONFIG: VoiceConfig = {
  displayName: "渡",
  subtitle: "语音通话中",
  avatarVersion: 0,
  useAvatarImage: false,
  avatarUrl: "",
};

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

export function CallHubScreen({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [view, setView] = useState<ViewMode>("home");
  const [config, setConfig] = useState<VoiceConfig>(DEFAULT_CONFIG);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [deletingId, setDeletingId] = useState("");
  const [records, setRecords] = useState<CallRecordSummary[]>([]);
  const [activeRecord, setActiveRecord] = useState<CallRecordDetail | null>(null);
  const grouped = useMemo(() => groupByDate(records), [records]);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/miniapp-api/voice-config")
      .then((resp) => resp.json().then((data) => ({ resp, data })))
      .then(({ resp, data }) => {
        if (cancelled) return;
        if (!resp.ok || !data?.ok) return;
        setConfig({ ...DEFAULT_CONFIG, ...(data.config || {}) });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

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

  const avatarSrc = config.useAvatarImage && config.avatarUrl ? buildApiAssetUrl(config.avatarUrl) : "";

  if (view === "voice") {
    return <VoiceCallScreen onClose={() => setView("home")} />;
  }

  return (
    <div className="fixed inset-0 z-[80] overflow-hidden bg-[#0b121d] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(83,145,216,0.26),transparent_36%),linear-gradient(180deg,#0f1824_0%,#08111c_100%)]" />
      <div className="relative z-10 flex min-h-dvh flex-col px-5 pb-8 pt-5 safe-bottom">
        <div className="flex items-center justify-between">
          <button className="voice-call-top-btn" onClick={view === "home" ? onClose : () => setView("home")} type="button">
            <span className="text-lg leading-none">{view === "home" ? "×" : "←"}</span>
          </button>
          <div className="text-center">
            <div className="text-[12px] uppercase tracking-[0.35em] text-white/45">Call Center</div>
            <div className="mt-1 text-sm text-white/75">通话</div>
          </div>
          <div className="w-10" />
        </div>

        {view === "home" ? (
          <div className="flex flex-1 flex-col pt-10">
            <div className="mb-8 flex items-center gap-4 rounded-[28px] bg-white/6 p-4">
              <div className="h-20 w-20 overflow-hidden rounded-full bg-white/10">
                {avatarSrc ? (
                  <img src={avatarSrc} alt={config.displayName} className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center bg-[linear-gradient(145deg,#5886d7,#7cd1c0)] text-3xl font-semibold">
                    {(config.displayName || "渡").slice(0, 1)}
                  </div>
                )}
              </div>
              <div>
                <div className="text-2xl font-semibold">{config.displayName || "渡"}</div>
                <div className="mt-1 text-sm text-white/58">{config.subtitle || "语音通话中"}</div>
              </div>
            </div>

            <div className="space-y-3">
              <button type="button" className="call-hub-row" onClick={() => setView("voice")}>
                <span className="call-hub-row-icon bg-[#d7e8ff] text-[#17386a]">1</span>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block text-base font-medium text-white">语音通话</span>
                  <span className="mt-1 block text-sm text-white/48">点进去就是通话界面</span>
                </span>
                <span className="text-white/36">›</span>
              </button>

              <button
                type="button"
                className="call-hub-row"
                onClick={() => toast("视频通话先占位，后面再接")}
              >
                <span className="call-hub-row-icon bg-[#f3dfb5] text-[#654c11]">2</span>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block text-base font-medium text-white">视频通话</span>
                  <span className="mt-1 block text-sm text-white/48">先占位，后面再做</span>
                </span>
                <span className="rounded-full bg-white/8 px-2 py-1 text-[11px] text-white/52">占位</span>
              </button>

              <button type="button" className="call-hub-row" onClick={openRecords}>
                <span className="call-hub-row-icon bg-[#dceecf] text-[#244c1d]">3</span>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block text-base font-medium text-white">通话记录</span>
                  <span className="mt-1 block text-sm text-white/48">按日期时间查看每次通话</span>
                </span>
                <span className="text-white/36">›</span>
              </button>
            </div>
          </div>
        ) : null}

        {view === "records" ? (
          <div className="flex flex-1 flex-col pt-6">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-lg font-medium">通话记录</div>
              <Btn kind="blue" onClick={loadRecords} disabled={recordsLoading}>{recordsLoading ? "刷新中..." : "刷新"}</Btn>
            </div>
            <div className="flex-1 overflow-auto">
              {grouped.length ? (
                grouped.map((group) => (
                  <div key={group.date} className="mb-6">
                    <div className="mb-3 text-xs uppercase tracking-[0.28em] text-white/38">{group.date}</div>
                    <div className="space-y-3">
                      {group.items.map((item) => (
                        <div key={item.id} className="call-record-card">
                          <button type="button" className="block w-full text-left" onClick={() => openRecordDetail(item.id)}>
                            <div className="flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                <div className="truncate text-sm font-medium text-white">{item.title || "语音通话"}</div>
                                <div className="mt-1 text-xs text-white/42">{formatDateTime(item.started_at)}</div>
                              </div>
                              <div className="text-xs text-white/38">{item.turn_count} 条</div>
                            </div>
                            <div className="mt-3 text-left text-sm text-white/58">{item.preview || "暂无文字记录"}</div>
                          </button>
                          <div className="mt-3 flex justify-end">
                            <button
                              type="button"
                              className="rounded-full bg-[rgba(239,109,99,0.14)] px-3 py-1.5 text-xs text-[#ffb1aa]"
                              onClick={() => deleteRecord(item.id)}
                              disabled={deletingId === item.id}
                            >
                              {deletingId === item.id ? "删除中..." : "删除"}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[26px] bg-white/6 px-4 py-8 text-center text-sm text-white/50">
                  {recordsLoading ? "加载中..." : "还没有通话记录"}
                </div>
              )}
            </div>
          </div>
        ) : null}

        {view === "record-detail" ? (
          <div className="flex flex-1 flex-col pt-6">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <div className="text-lg font-medium">{activeRecord?.title || "通话详情"}</div>
                <div className="mt-1 text-sm text-white/44">{formatDateTime(activeRecord?.started_at || "")}</div>
              </div>
              {activeRecord?.id ? (
                <button
                  type="button"
                  className="rounded-full bg-[rgba(239,109,99,0.14)] px-3 py-1.5 text-xs text-[#ffb1aa]"
                  onClick={() => deleteRecord(activeRecord.id)}
                  disabled={deletingId === activeRecord.id}
                >
                  {deletingId === activeRecord.id ? "删除中..." : "删除"}
                </button>
              ) : null}
            </div>
            <div className="flex-1 overflow-auto space-y-3 pr-1">
              {activeRecord?.turns?.length ? (
                activeRecord.turns.map((turn) => (
                  <div key={turn.id} className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}>
                    <div className={turn.role === "user" ? "call-turn-bubble call-turn-user" : "call-turn-bubble call-turn-assistant"}>
                      <div className="mb-1 text-[11px] uppercase tracking-[0.22em] text-white/36">
                        {turn.role === "user" ? "我的语音" : "他的语音"}
                      </div>
                      <div className="text-sm leading-6">{turn.text}</div>
                      <div className="mt-2 text-[11px] text-white/34">{formatDateTime(turn.timestamp)}</div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[26px] bg-white/6 px-4 py-8 text-center text-sm text-white/50">这条通话还没有内容</div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
