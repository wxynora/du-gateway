import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Capacitor } from "@capacitor/core";
import { apiJson } from "../api";
import { useToast } from "../toast";
import { SumiOverlay, type HealthReportingLog, type HealthReportingStatus } from "../../plugins/sumi-overlay";

type HealthCloudResponse = {
  ok?: boolean;
  latest?: Record<string, any>;
  history?: Array<{ at?: string; data?: Record<string, any> }>;
  du_vitals?: Record<string, any>;
  du_vitals_history?: Array<Record<string, any>>;
  error?: string;
};

type DuHeartPoint = { at?: string; value: number };

const CLOUD_HEALTH_RECORD_DISPLAY_LIMIT = 1;
const HEALTH_REPORT_LOG_DISPLAY_LIMIT = 10;

const FREQUENCY_OPTIONS = [
  { label: "30 秒", seconds: 30 },
  { label: "1 分钟", seconds: 60 },
  { label: "5 分钟", seconds: 300 },
  { label: "15 分钟", seconds: 900 },
];

export function HealthDataScreen() {
  const toast = useToast();
  const [status, setStatus] = useState<HealthReportingStatus | null>(null);
  const [cloud, setCloud] = useState<HealthCloudResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [headerActionsEl, setHeaderActionsEl] = useState<HTMLElement | null>(null);
  const [savingSeconds, setSavingSeconds] = useState<number | null>(null);
  const isAndroid = Capacitor.getPlatform() === "android";

  const latestLocal = status?.last || {};
  const latestCloud = cloud?.latest || {};
  const cloudHealthRows = useMemo(() => (cloud?.history || []).slice(0, CLOUD_HEALTH_RECORD_DISPLAY_LIMIT), [cloud?.history]);
  const reportLogs = useMemo(() => (status?.logs || []).slice(-HEALTH_REPORT_LOG_DISPLAY_LIMIT).reverse(), [status?.logs]);
  const displayHealth = useMemo(() => {
    const src = Object.keys(latestCloud).length ? latestCloud : latestLocal;
    return {
      heartRate: src?.heart_rate ?? src?.heartRate ?? "",
      steps: src?.steps ?? src?.step_count ?? "",
      at: src?.updatedAt || src?.status_at || src?.capturedAt || src?.captured_at || "",
      source: Object.keys(latestCloud).length ? "云端" : "本机",
    };
  }, [latestCloud, latestLocal]);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const [nativeStatus, cloudStatus] = await Promise.all([
        SumiOverlay.getHealthReportingStatus().catch(() => null),
        apiJson<HealthCloudResponse>(`/miniapp-api/device-state/health?t=${Date.now()}`, { cache: "no-store" }).catch((e) => ({ ok: false, error: e?.message || String(e) })),
      ]);
      setStatus(nativeStatus);
      setCloud(cloudStatus);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setHeaderActionsEl(document.getElementById("health-data-header-actions"));
  }, []);

  async function saveInterval(seconds: number) {
    const prev = status;
    setSavingSeconds(seconds);
    setStatus((s) => ({ ...(s || {}), intervalSeconds: seconds }));
    try {
      const r = await SumiOverlay.setHealthReportingConfig({ intervalSeconds: seconds });
      setStatus((s) => ({ ...(s || {}), intervalSeconds: r.intervalSeconds || seconds }));
      toast("健康数据频率已更新");
    } catch (e: any) {
      setStatus(prev);
      toast(`频率保存失败：${e?.message || e}`);
    } finally {
      setSavingSeconds(null);
    }
  }

  async function requestSnapshot() {
    try {
      const r = await SumiOverlay.requestHealthReportingSnapshot();
      if (!r?.requested) {
        toast("通知监听还没连上");
      }
      await load();
      window.setTimeout(() => void load({ silent: true }), 900);
      window.setTimeout(() => void load({ silent: true }), 2200);
    } catch (e: any) {
      toast(`刷新失败：${e?.message || e}`);
    }
  }

  async function clearLogs() {
    try {
      await SumiOverlay.clearHealthReportingLogs();
      setStatus((s) => ({ ...(s || {}), logs: [] }));
    } catch (e: any) {
      toast(`清空失败：${e?.message || e}`);
    }
  }

  if (!isAndroid) {
    return (
      <div className="px-4 py-5">
        <div className="rounded-[24px] border border-gray-100 bg-white px-5 py-8 text-center shadow-[0_8px_30px_-18px_rgba(0,0,0,0.2)]">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-50 text-gray-700"><BiometricSignalIcon /></div>
          <div className="text-[15px] font-semibold text-gray-900">健康数据只在 Android 端工作</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 px-4 py-5">
      {headerActionsEl ? createPortal(
        <button
          type="button"
          disabled={loading}
          aria-label={loading ? "健康数据刷新中" : "刷新健康数据"}
          title={loading ? "刷新中" : "刷新"}
          className="flex h-8 w-8 items-center justify-center rounded-full text-gray-600 transition-colors active:bg-gray-100 disabled:opacity-60"
          onClick={() => void requestSnapshot()}
        >
          <RefreshIconMini className={loading ? "animate-spin" : ""} />
        </button>,
        headerActionsEl,
      ) : null}
      <section className="relative overflow-hidden rounded-[32px] border border-black/5 bg-white p-6 text-[#111111] shadow-[0_28px_70px_-46px_rgba(0,0,0,0.42)]">
        <div className="flex items-start justify-between gap-4 border-b border-black/10 pb-4">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-black/45">Sumika Heartbeat</div>
            <div className="mt-1 text-[13px] font-medium text-black/55">Notify for Xiaomi</div>
          </div>
          <span className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-semibold ${status?.listenerEnabled ? "bg-black text-white" : "bg-black/8 text-black/60"}`}>
            {status?.listenerEnabled ? "已授权" : "未授权"}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4 py-7">
          <BiometricMetric label="Heart Rate / 心率" value={displayHealth.heartRate || "-"} unit={displayHealth.heartRate ? "bpm" : ""} />
          <BiometricMetric label="Steps / 步数" value={displayHealth.steps || "-"} unit={displayHealth.steps ? "steps" : ""} />
        </div>

        <div className="flex items-end justify-between gap-4 border-t border-black/10 pt-4">
          <div className="min-w-0 space-y-1 text-[10px] uppercase tracking-[0.08em] text-black/45">
            <div className="flex gap-2">
              <span>Sync</span>
              <span className="font-medium text-black/70">{formatTime(displayHealth.at) || "-"}</span>
            </div>
            <div className="flex gap-2">
              <span>Source</span>
              <span className="font-medium text-black/70">{displayHealth.source}</span>
            </div>
          </div>
          <div className="h-8 w-8 shrink-0 opacity-70 [background-image:radial-gradient(#111_1px,transparent_1px)] [background-size:4px_4px]" aria-hidden="true" />
        </div>
      </section>

      <DuVitalsCard vitals={cloud?.du_vitals || {}} history={cloud?.du_vitals_history || []} />

      <section className="rounded-[26px] border border-gray-100 bg-white p-5 shadow-[0_8px_28px_-22px_rgba(0,0,0,0.2)]">
        <div className="mb-3 text-[13px] font-semibold tracking-wide text-gray-900">上报频率</div>
        <div className="grid grid-cols-2 gap-2">
          {FREQUENCY_OPTIONS.map((item) => {
            const active = Number(status?.intervalSeconds || 60) === item.seconds;
            return (
              <button
                key={item.seconds}
                type="button"
                disabled={savingSeconds !== null}
                className={`h-11 rounded-[16px] text-[13px] font-semibold transition-colors ${active ? "bg-gray-900 text-white" : "bg-gray-50 text-gray-700 active:bg-gray-100"} ${savingSeconds === item.seconds ? "opacity-60" : ""}`}
                onClick={() => void saveInterval(item.seconds)}
              >
                {item.label}
              </button>
            );
          })}
        </div>
        <div className="mt-3 text-[12px] leading-5 text-gray-500">同一条通知内容在间隔内不会重复上传。</div>
      </section>

      <div>
        <button type="button" className="h-11 w-full rounded-[16px] bg-gray-100 text-[13px] font-semibold text-gray-800 active:scale-[0.98]" onClick={() => void SumiOverlay.openNotificationListenerSettings()}>
          通知权限
        </button>
      </div>

      <section className="rounded-[26px] border border-gray-100 bg-white p-5 shadow-[0_8px_28px_-22px_rgba(0,0,0,0.2)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-[13px] font-semibold tracking-wide text-gray-900">云端记录</div>
            <div className="mt-1 text-[12px] text-gray-400">最新 {cloudHealthRows.length || 0} 条</div>
          </div>
        </div>
        <div className="space-y-2">
          {cloudHealthRows.map((row, idx) => (
            <CloudRow key={`${row.at || ""}-${idx}`} row={row} />
          ))}
          {!cloudHealthRows.length ? (
            <div className="rounded-[18px] bg-gray-50 px-4 py-6 text-center text-[13px] text-gray-400">云端还没有健康记录</div>
          ) : null}
        </div>
      </section>

      <section className="rounded-[26px] border border-gray-100 bg-white p-5 shadow-[0_8px_28px_-22px_rgba(0,0,0,0.2)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-[13px] font-semibold tracking-wide text-gray-900">上报日志</div>
            <div className="mt-1 text-[12px] text-gray-400">{loading ? "刷新中" : `最近 ${reportLogs.length || 0} 条`}</div>
          </div>
          <button type="button" className="rounded-full bg-gray-50 px-3 py-1.5 text-[12px] font-semibold text-gray-600 active:bg-gray-100" onClick={() => void clearLogs()}>
            清空
          </button>
        </div>
        <div className="space-y-2">
          {reportLogs.map((row, idx) => (
            <LogRow key={`${row.at || ""}-${idx}`} row={row} />
          ))}
          {!reportLogs.length ? (
            <div className="rounded-[18px] bg-gray-50 px-4 py-6 text-center text-[13px] text-gray-400">还没有健康数据日志</div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function DuVitalsCard({ vitals, history }: { vitals: Record<string, any>; history: Array<Record<string, any>> }) {
  const heart = Number(vitals?.heart_bpm || 0);
  const breath = Number(vitals?.breath_rpm || 0);
  const params = typeof vitals?.parameters === "object" && vitals.parameters ? vitals.parameters : {};
  const heartHistory = useMemo(() => normalizeDuHeartHistory(history, vitals), [history, vitals]);
  const hasVitals = heart > 0 || breath > 0;
  return (
    <section className="relative overflow-hidden rounded-[32px] bg-[#111111] p-6 text-white shadow-[0_34px_80px_-48px_rgba(0,0,0,0.85)]" style={{ fontFamily: "'Inter', sans-serif" }}>
      <style>
        {`
          @keyframes biometric-line-draw {
            from { stroke-dashoffset: 1000; }
            to { stroke-dashoffset: 0; }
          }
        `}
      </style>
      <div className="mb-6 flex items-start justify-between gap-4 border-b border-white/15 pb-4">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/42">Du Heartbeat</div>
          <div className="mt-1 text-[13px] font-medium text-white/42">Biometric stream</div>
        </div>
        <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-black">
          {String(vitals?.status || (hasVitals ? "平稳" : "未同步"))}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4 py-7">
        <BiometricMetric label="Du Heart / 渡心率" value={heart || "-"} unit={heart ? "bpm" : ""} tone="dark" />
        <BiometricMetric label="Du Breath / 渡呼吸" value={breath || "-"} unit={breath ? "brpm" : ""} tone="dark" />
      </div>
      <DuHeartCurve points={heartHistory} />
      <div className="mt-4 text-[10px] uppercase tracking-[0.08em] text-white/42">
        Focus {formatParamPercent(params.focus)} · Close {formatParamPercent(params.intimacy_heat)} · Tension {formatParamPercent(params.tension)}
      </div>
      <div className="mt-1 text-[10px] uppercase tracking-[0.08em] text-white/42">Sync {formatTime(vitals?.updatedAt || vitals?.at) || "-"}</div>
    </section>
  );
}

function normalizeDuHeartHistory(history: Array<Record<string, any>>, latest: Record<string, any>): DuHeartPoint[] {
  const rows = (Array.isArray(history) ? history : [])
    .map((item) => ({
      at: String(item?.updatedAt || item?.at || "").trim(),
      value: Number(item?.heart_bpm || item?.heartBpm || 0),
    }))
    .filter((item) => Number.isFinite(item.value) && item.value > 0);

  const latestAt = String(latest?.updatedAt || latest?.at || "").trim();
  const latestValue = Number(latest?.heart_bpm || latest?.heartBpm || 0);
  if (
    Number.isFinite(latestValue) &&
    latestValue > 0 &&
    !rows.some((item) => item.at === latestAt && item.value === latestValue)
  ) {
    rows.push({ at: latestAt, value: latestValue });
  }

  return rows.slice(-10);
}

function DuHeartCurve({ points }: { points: DuHeartPoint[] }) {
  const values = points.map((point) => point.value);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const width = 400;
  const height = 80;
  const path = values.length >= 2 ? buildSmoothCurvePath(values, min, max, width, height) : BIOMETRIC_WAVE_PATH;

  return (
    <div className="mt-5">
      <div className="relative h-[92px] overflow-hidden">
        <svg className="h-full w-full" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
          <g>
            <line x1="0" y1="20" x2={width} y2="20" stroke="rgba(245,245,245,0.15)" strokeWidth="0.5" />
            <line x1="0" y1="40" x2={width} y2="40" stroke="rgba(245,245,245,0.15)" strokeWidth="0.5" />
            <line x1="0" y1="60" x2={width} y2="60" stroke="rgba(245,245,245,0.15)" strokeWidth="0.5" />
          </g>
          <path
            d={path}
            fill="none"
            stroke="#F5F5F5"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.25"
            strokeDasharray="1000"
            style={{ animation: "biometric-line-draw 4s cubic-bezier(0.4,0,0.2,1) forwards" }}
          />
        </svg>
      </div>
    </div>
  );
}

const BIOMETRIC_WAVE_PATH = `
  M 0,40
  C 10,40 15,10 20,40
  C 25,70 35,70 40,40
  C 45,10 55,10 60,40
  C 65,70 75,70 80,40
  C 85,10 95,10 100,40
  C 105,70 115,70 120,40
  C 125,10 135,10 140,40
  C 145,70 155,70 160,40
  C 165,10 175,10 180,40
  C 185,70 195,70 200,40
  C 205,10 215,10 220,40
  C 225,70 235,70 240,40
  C 245,10 255,10 260,40
  C 265,70 275,70 280,40
  C 285,10 295,10 300,40
  C 305,70 315,70 320,40
  C 325,10 335,10 340,40
  C 345,70 355,70 360,40
  C 365,10 375,10 380,40
  C 385,70 395,70 400,40
`;

function buildSmoothCurvePath(values: number[], min: number, max: number, width: number, height: number) {
  const padY = 10;
  const span = Math.max(1, max - min);
  const coords = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : (index * width) / (values.length - 1);
    const y = padY + ((max - value) * (height - padY * 2)) / span;
    return { x, y };
  });
  if (!coords.length) return BIOMETRIC_WAVE_PATH;
  if (coords.length === 1) return `M 0,${coords[0].y.toFixed(1)} C 120,${coords[0].y.toFixed(1)} 280,${coords[0].y.toFixed(1)} ${width},${coords[0].y.toFixed(1)}`;
  return coords
    .map((point, index) => {
      if (index === 0) return `M ${point.x.toFixed(1)},${point.y.toFixed(1)}`;
      const prev = coords[index - 1];
      const cp1x = prev.x + (point.x - prev.x) / 2;
      const cp2x = point.x - (point.x - prev.x) / 2;
      return `C ${cp1x.toFixed(1)},${prev.y.toFixed(1)} ${cp2x.toFixed(1)},${point.y.toFixed(1)} ${point.x.toFixed(1)},${point.y.toFixed(1)}`;
    })
    .join(" ");
}

function formatParamPercent(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(Math.max(0, Math.min(1, n)) * 100)}%` : "-";
}

function CloudRow({ row }: { row: { at?: string; data?: Record<string, any> } }) {
  const data = row.data || {};
  return (
    <div className="flex items-center justify-between gap-3 rounded-[18px] bg-gray-50 px-4 py-3">
      <div className="min-w-0">
        <div className="text-[13px] font-semibold text-gray-800">
          心率 {data.heart_rate ?? "-"} · 步数 {data.steps ?? "-"}
        </div>
        <div className="mt-1 truncate text-[11px] text-gray-400">{formatTime(row.at || data.updatedAt || data.capturedAt)}</div>
      </div>
      <span className="shrink-0 rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-gray-500">R2</span>
    </div>
  );
}

function BiometricMetric({
  label,
  value,
  unit,
  compact = false,
  tone = "light",
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  compact?: boolean;
  tone?: "light" | "dark";
}) {
  return (
    <div className="min-w-0">
      <div className={`text-[9px] font-semibold uppercase tracking-[0.16em] ${tone === "dark" ? "text-white/38" : "text-black/42"}`}>{label}</div>
      <div className={`${compact ? "mt-2 min-h-[42px]" : "mt-3 min-h-[56px]"} flex min-w-0 items-end gap-1 overflow-hidden`}>
        <span
          className={`${compact ? "text-[clamp(32px,9vw,48px)]" : "text-[clamp(42px,14vw,64px)]"} min-w-0 shrink leading-none tracking-tight ${tone === "dark" ? "text-white" : "text-black"}`}
          style={{ fontFamily: "'Playfair Display', Georgia, 'Times New Roman', serif" }}
        >
          {value}
        </span>
        {unit ? (
          <span
            className={`shrink-0 pb-1 text-[12px] italic tracking-wide ${tone === "dark" ? "text-white/42" : "text-black/42"}`}
            style={{ fontFamily: "'Playfair Display', Georgia, 'Times New Roman', serif" }}
          >
            {unit}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function RefreshIconMini({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12a9 9 0 0 1-15.1 6.6" />
      <path d="M3 12A9 9 0 0 1 18.1 5.4" />
      <path d="M18 2v4h-4" />
      <path d="M6 22v-4h4" />
    </svg>
  );
}

function BiometricSignalIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 12h3l2.4-6 4.2 12 2.2-6H21" />
    </svg>
  );
}

function LogRow({ row }: { row: HealthReportingLog }) {
  return (
    <div className="rounded-[18px] bg-gray-50 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${levelClass(row.level)}`}>{levelText(row.level)}</span>
        <span className="shrink-0 text-[11px] text-gray-400">{formatTime(row.at)}</span>
      </div>
      <div className="mt-2 text-[13px] font-medium leading-5 text-gray-800">{row.message || "-"}</div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500">
        {row.heart_rate ? <span>心率 {row.heart_rate}</span> : null}
        {row.steps ? <span>步数 {row.steps}</span> : null}
        {row.http_code ? <span>HTTP {row.http_code}</span> : null}
      </div>
      {row.raw_text ? <div className="mt-2 break-words text-[11px] leading-4 text-gray-400">{row.raw_text}</div> : null}
    </div>
  );
}

function levelText(level?: string) {
  if (level === "ok") return "OK";
  if (level === "error") return "ERROR";
  if (level === "skip") return "SKIP";
  return "LOG";
}

function levelClass(level?: string) {
  if (level === "ok") return "bg-emerald-100 text-emerald-700";
  if (level === "error") return "bg-rose-100 text-rose-700";
  if (level === "skip") return "bg-amber-100 text-amber-700";
  return "bg-gray-200 text-gray-600";
}

function formatTime(value?: string) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return raw;
  return dt.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
