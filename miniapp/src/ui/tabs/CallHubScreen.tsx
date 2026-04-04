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

function RowArrow() {
  return (
    <svg className="h-4 w-4 text-cream-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

export function CallHubScreen({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [view, setView] = useState<ViewMode>("home");
  const [config, setConfig] = useState<VoiceConfig>(DEFAULT_CONFIG);
  const [dailyWhisper, setDailyWhisper] = useState("");
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [avatarStamp, setAvatarStamp] = useState(0);
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
        setConfig((prev) => ({
          ...prev,
          ...DEFAULT_CONFIG,
          ...(data.config || {}),
          avatarVersion: Math.max(Number(prev.avatarVersion || 0), Number(data?.config?.avatarVersion || 0)),
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

  async function uploadAvatar(file: File | null) {
    if (!file || uploadingAvatar) return;
    setUploadingAvatar(true);
    try {
      const toDataUrl = (blob: Blob) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ""));
          reader.onerror = () => reject(new Error("读取图片失败"));
          reader.readAsDataURL(blob);
        });
      const loadImage = (src: string) =>
        new Promise<HTMLImageElement>((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.onerror = () => reject(new Error("图片解码失败"));
          img.src = src;
        });
      const canvasToBlob = (canvas: HTMLCanvasElement, quality: number) =>
        new Promise<Blob>((resolve, reject) => {
          canvas.toBlob(
            (blob) => {
              if (blob) resolve(blob);
              else reject(new Error("图片编码失败"));
            },
            "image/jpeg",
            quality,
          );
        });
      const maxUploadBytes = 1200 * 1024;
      const maxSide = 1200;
      let uploadBlob: Blob = file;
      if (file.size > maxUploadBytes || file.type !== "image/jpeg") {
        const src = await toDataUrl(file);
        const img = await loadImage(src);
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("浏览器不支持图片处理");
        ctx.drawImage(img, 0, 0, w, h);
        let q = 0.9;
        let out = await canvasToBlob(canvas, q);
        while (out.size > maxUploadBytes && q > 0.55) {
          q -= 0.08;
          out = await canvasToBlob(canvas, q);
        }
        uploadBlob = out;
      }
      const form = new FormData();
      form.append("file", uploadBlob, "voice-avatar.jpg");
      const resp = await apiFetch("/miniapp-api/voice-avatar", { method: "POST", body: form });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      setConfig((prev) => ({
        ...prev,
        avatarVersion: Number(data.avatarVersion || prev.avatarVersion || 0),
        useAvatarImage: true,
      }));
      setAvatarStamp(Date.now());
      toast("头像已更新");
    } catch (e: any) {
      toast(e?.message || "头像上传失败");
    } finally {
      setUploadingAvatar(false);
    }
  }

  const avatarSrc = config.useAvatarImage && config.avatarVersion > 0
    ? buildApiAssetUrl(`/miniapp-api/voice-avatar/${config.avatarVersion}?s=${avatarStamp || 0}`)
    : "";
  const rowBase =
    "flex w-full items-center gap-3 px-4 py-4 text-left transition active:scale-[0.995]";

  return (
    <div className="fixed inset-0 z-[80] overflow-auto bg-[rgba(238,241,245,0.96)] text-cream-text backdrop-blur-xl">
      <div className="mx-auto min-h-dvh max-w-xl px-4 pb-8 pt-4 safe-bottom">
        <div className="flex items-center justify-between">
          <button className="neo-icon-btn h-10 w-10 text-sm" onClick={view === "home" ? onClose : () => setView("home")} type="button">
            {view === "home" ? (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 6l12 12M18 6 6 18" /></svg>
            ) : (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m15 6-6 6 6 6" /></svg>
            )}
          </button>
          <div className="neo-chip">{view === "home" ? "通话" : view === "voice" ? "语音通话" : view === "records" ? "通话记录" : "通话详情"}</div>
          <div className="w-10" />
        </div>

        {view === "home" ? (
          <div className="pt-4">
            <div className="neo-panel-soft flex items-center gap-4 px-4 py-4">
              <label className="relative block cursor-pointer">
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  className="hidden"
                  onChange={(e) => uploadAvatar(e.target.files?.[0] || null)}
                  disabled={uploadingAvatar}
                />
                <div className="h-16 w-16 overflow-hidden rounded-full bg-[rgba(255,255,255,0.52)] shadow-[4px_4px_9px_rgba(173,182,196,0.18),-2px_-2px_4px_rgba(255,255,255,0.5)]">
                  {avatarSrc ? (
                    <img src={avatarSrc} alt={config.displayName} className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center bg-[#D6E4F2] text-2xl font-semibold text-cream-text">
                      {(config.displayName || "渡").slice(0, 1)}
                    </div>
                  )}
                </div>
                <span className="absolute -bottom-1 -right-1 rounded-full bg-[#EFD5E1] px-2 py-0.5 text-[10px] text-cream-text shadow-[3px_3px_8px_rgba(173,182,196,0.2),-1px_-1px_3px_rgba(255,255,255,0.5)]">
                  {uploadingAvatar ? "上传中" : "换头像"}
                </span>
              </label>
              <div className="min-w-0">
                <div className="rounded-[22px] bg-[rgba(255,255,255,0.38)] px-3 py-2 text-[12px] leading-5 text-cream-text shadow-[inset_2px_2px_5px_rgba(173,182,196,0.18),inset_-1px_-1px_3px_rgba(255,255,255,0.55)]">
                  {dailyWhisper || "今天也可以来和渡说说话。"}
                </div>
              </div>
            </div>

            <div className="mt-4 overflow-hidden rounded-[28px] bg-[rgba(244,247,251,0.74)] shadow-[6px_6px_13px_rgba(170,180,194,0.22),-3px_-3px_7px_rgba(255,255,255,0.5)] backdrop-blur-xl">
              <button type="button" className={rowBase} onClick={() => setView("voice")}>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-medium">语音通话</span>
                  <span className="mt-1 block text-xs text-cream-muted">点进去就是通话界面</span>
                </span>
                <RowArrow />
              </button>
              <button type="button" className={rowBase + " border-t border-white/40"} onClick={() => toast("视频通话先占位，后面再接")}>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-medium">视频通话</span>
                  <span className="mt-1 block text-xs text-cream-muted">先占位，后面再做</span>
                </span>
                <span className="neo-tag-yellow">占位</span>
              </button>
              <button type="button" className={rowBase + " border-t border-white/40"} onClick={openRecords}>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-medium">通话记录</span>
                  <span className="mt-1 block text-xs text-cream-muted">按日期时间查看每次通话</span>
                </span>
                <RowArrow />
              </button>
            </div>
          </div>
        ) : null}

        {view === "voice" ? (
          <div className="pt-4">
            <VoiceCallScreen onClose={() => setView("home")} />
          </div>
        ) : null}

        {view === "records" ? (
          <div className="pt-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-sm font-medium text-cream-text">最近通话</div>
              <Btn kind="blue" onClick={loadRecords} disabled={recordsLoading}>{recordsLoading ? "刷新中..." : "刷新"}</Btn>
            </div>
            <div className="space-y-4">
              {grouped.length ? (
                grouped.map((group) => (
                  <div key={group.date}>
                    <div className="mb-2 px-1 text-[11px] uppercase tracking-[0.18em] text-cream-muted">{group.date}</div>
                    <div className="overflow-hidden rounded-[26px] bg-[rgba(244,247,251,0.72)] shadow-[6px_6px_13px_rgba(170,180,194,0.22),-3px_-3px_7px_rgba(255,255,255,0.48)] backdrop-blur-xl">
                      {group.items.map((item, idx) => (
                        <div key={item.id} className={idx > 0 ? "border-t border-white/40" : ""}>
                          <div className="flex items-center gap-3 px-4 py-3">
                            <button type="button" className="min-w-0 flex-1 text-left" onClick={() => openRecordDetail(item.id)}>
                              <div className="truncate text-sm font-medium text-cream-text">{item.title || "语音通话"}</div>
                              <div className="mt-1 text-[11px] text-cream-muted">
                                {formatDateTime(item.started_at)} · {item.turn_count} 条
                              </div>
                              <div className="mt-2 truncate text-xs text-cream-muted">{item.preview || "暂无文字记录"}</div>
                            </button>
                            <button
                              type="button"
                              className="rounded-full bg-[rgba(232,185,179,0.42)] px-3 py-1.5 text-[11px] text-[#8a4a43]"
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
                <div className="neo-panel-soft px-4 py-8 text-center text-sm text-cream-muted">
                  {recordsLoading ? "加载中..." : "还没有通话记录"}
                </div>
              )}
            </div>
          </div>
        ) : null}

        {view === "record-detail" ? (
          <div className="pt-4">
            <div className="neo-panel-soft px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[16px] font-semibold tracking-tight">{activeRecord?.title || "通话详情"}</div>
                  <div className="mt-1 text-xs text-cream-muted">{formatDateTime(activeRecord?.started_at || "")}</div>
                </div>
                {activeRecord?.id ? (
                  <button
                    type="button"
                    className="rounded-full bg-[rgba(232,185,179,0.42)] px-3 py-1.5 text-[11px] text-[#8a4a43]"
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
                      "neo-panel-soft px-4 py-3 " +
                      (turn.role === "user" ? "ml-10" : "mr-10")
                    }
                  >
                    <div className="mb-1 text-[11px] uppercase tracking-[0.16em] text-cream-muted">
                      {turn.role === "user" ? "我的语音" : "他的语音"}
                    </div>
                    <div className="text-sm leading-6 text-cream-text">{turn.text}</div>
                    <div className="mt-2 text-[11px] text-cream-muted">{formatDateTime(turn.timestamp)}</div>
                  </div>
                ))
              ) : (
                <div className="neo-panel-soft px-4 py-8 text-center text-sm text-cream-muted">这条通话还没有内容</div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
