import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { apiJson } from "../api";
import { useToast } from "../toast";
import { HeartIconMini } from "../icons";
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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nativeStatus, cloudStatus] = await Promise.all([
        SumiOverlay.getHealthReportingStatus().catch(() => null),
        apiJson<HealthCloudResponse>("/miniapp-api/device-state/health").catch((e) => ({ ok: false, error: e?.message || String(e) })),
      ]);
      setStatus(nativeStatus);
      setCloud(cloudStatus);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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
      window.setTimeout(() => void load(), 700);
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
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500"><HeartIconMini /></div>
          <div className="text-[15px] font-semibold text-gray-900">健康数据只在 Android 端工作</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 px-4 py-5">
      <section className="rounded-[26px] border border-rose-100 bg-[#FFF9F8] p-5 shadow-[0_10px_34px_-22px_rgba(190,55,72,0.45)]">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <div className="text-[12px] font-bold uppercase tracking-[0.18em] text-rose-300">Notify for Xiaomi</div>
            <div className="mt-1 text-[18px] font-semibold tracking-tight text-gray-950">健康数据</div>
          </div>
          <span className={`rounded-full px-3 py-1 text-[12px] font-semibold ${status?.listenerEnabled ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
            {status?.listenerEnabled ? "已授权" : "未授权"}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Metric label="心率" value={displayHealth.heartRate || "-"} unit={displayHealth.heartRate ? "bpm" : ""} />
          <Metric label="步数" value={displayHealth.steps || "-"} unit={displayHealth.steps ? "steps" : ""} />
        </div>

        <div className="mt-4 rounded-[18px] bg-white/70 px-4 py-3 text-[12px] text-gray-500">
          <div className="flex justify-between gap-3">
            <span>最近同步</span>
            <span className="text-right font-medium text-gray-800">{formatTime(displayHealth.at) || "-"}</span>
          </div>
          <div className="mt-2 flex justify-between gap-3">
            <span>数据来源</span>
            <span className="text-right font-medium text-gray-800">{displayHealth.source}</span>
          </div>
          <div className="mt-2 flex justify-between gap-3">
            <span>包名</span>
            <span className="break-all text-right font-medium text-gray-800">{status?.packageName || "com.mc.xiaomi1"}</span>
          </div>
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

      <div className="grid grid-cols-2 gap-2">
        <button type="button" className="h-11 rounded-[16px] bg-gray-900 text-[13px] font-semibold text-white active:scale-[0.98]" onClick={() => void requestSnapshot()}>
          重新读取
        </button>
        <button type="button" className="h-11 rounded-[16px] bg-gray-100 text-[13px] font-semibold text-gray-800 active:scale-[0.98]" onClick={() => void SumiOverlay.openNotificationListenerSettings()}>
          通知权限
        </button>
      </div>

      <section className="rounded-[26px] border border-gray-100 bg-white p-5 shadow-[0_8px_28px_-22px_rgba(0,0,0,0.2)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-[13px] font-semibold tracking-wide text-gray-900">云端记录</div>
            <div className="mt-1 text-[12px] text-gray-400">最新 {cloudHealthRows.length || 0} 条</div>
          </div>
          <button type="button" className="rounded-full bg-gray-50 px-3 py-1.5 text-[12px] font-semibold text-gray-600 active:bg-gray-100" onClick={() => void load()}>
            刷新
          </button>
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
  const heartMs = heart > 0 ? Math.max(420, Math.round(60000 / heart)) : 840;
  const breathSeconds = breath > 0 ? Math.max(2.5, 60 / breath) : 5;
  const params = typeof vitals?.parameters === "object" && vitals.parameters ? vitals.parameters : {};
  const heartHistory = useMemo(() => normalizeDuHeartHistory(history, vitals), [history, vitals]);
  const hasVitals = heart > 0 || breath > 0;
  return (
    <section className="relative overflow-hidden rounded-[26px] border border-rose-100 bg-[#FFF7FA] p-5 shadow-[0_10px_34px_-22px_rgba(190,55,105,0.42)]">
      <style>
        {`
          @keyframes du-heartbeat {
            0%, 100% { transform: scale(1); }
            14% { transform: scale(1.16); }
            24% { transform: scale(0.96); }
            34% { transform: scale(1.08); }
            52% { transform: scale(1); }
          }
          @keyframes du-breathe {
            0%, 100% { transform: scale(0.92); opacity: 0.42; }
            48% { transform: scale(1.12); opacity: 0.78; }
          }
        `}
      </style>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="text-[12px] font-bold uppercase tracking-[0.18em] text-rose-300">Du rhythm</div>
          <div className="mt-1 text-[18px] font-semibold tracking-tight text-gray-950">渡的节律</div>
        </div>
        <span className="rounded-full bg-white/75 px-3 py-1 text-[12px] font-semibold text-rose-600">
          {String(vitals?.status || (hasVitals ? "平稳" : "未同步"))}
        </span>
      </div>
      <div className="flex items-center gap-5">
        <div className="relative flex h-[96px] w-[96px] shrink-0 items-center justify-center">
          <span
            className="absolute h-[84px] w-[84px] rounded-full bg-rose-200/50"
            style={{ animation: `du-breathe ${breathSeconds}s ease-in-out infinite` }}
          />
          <span className="absolute h-[58px] w-[58px] rounded-full bg-white/85 shadow-[0_12px_30px_-18px_rgba(190,55,105,0.8)]" />
          <span
            className="relative flex h-[34px] w-[34px] items-center justify-center rounded-full bg-rose-500 text-white shadow-[0_12px_26px_-14px_rgba(190,55,105,0.9)]"
            style={{ animation: `du-heartbeat ${heartMs}ms ease-in-out infinite` }}
          >
            <HeartIconMini />
          </span>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-3">
          <Metric label="渡心率" value={heart || "-"} unit={heart ? "bpm" : ""} />
          <Metric label="渡呼吸" value={breath || "-"} unit={breath ? "/min" : ""} />
        </div>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[11px] text-gray-500">
        <ParamPill label="专注" value={params.focus} />
        <ParamPill label="靠近" value={params.intimacy_heat} />
        <ParamPill label="绷紧" value={params.tension} />
      </div>
      <DuHeartCurve points={heartHistory} />
      <div className="mt-3 text-[12px] text-gray-400">最近同步：{formatTime(vitals?.updatedAt || vitals?.at) || "-"}</div>
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
  const latest = values.length ? values[values.length - 1] : 0;
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const width = 240;
  const height = 78;
  const padX = 10;
  const padY = 12;
  const span = Math.max(1, max - min);
  const coords = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : padX + (index * (width - padX * 2)) / (values.length - 1);
    const y = padY + ((max - value) * (height - padY * 2)) / span;
    return { x, y, value };
  });
  const path = coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");

  return (
    <div className="mt-4 rounded-[18px] bg-white/75 px-3 py-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-[12px] font-semibold text-gray-800">心率波动</div>
          <div className="mt-0.5 text-[10px] font-medium text-gray-400">最近 {points.length || 0} 次</div>
        </div>
        <div className="text-right">
          <div className="text-[18px] font-semibold leading-none text-rose-600">{latest || "-"}</div>
          <div className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">bpm</div>
        </div>
      </div>
      <div className="relative h-[86px] overflow-hidden rounded-[14px] bg-[#FFF7FA]">
        {values.length ? (
          <svg className="h-full w-full" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
            <line x1={padX} y1={padY} x2={width - padX} y2={padY} stroke="rgba(244, 114, 182, 0.14)" strokeWidth="1" />
            <line x1={padX} y1={height / 2} x2={width - padX} y2={height / 2} stroke="rgba(244, 114, 182, 0.12)" strokeWidth="1" />
            <line x1={padX} y1={height - padY} x2={width - padX} y2={height - padY} stroke="rgba(244, 114, 182, 0.14)" strokeWidth="1" />
            {path ? <path d={path} fill="none" stroke="#E84B77" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" /> : null}
            {coords.map((point, index) => (
              <circle
                key={`${point.x}-${index}`}
                cx={point.x}
                cy={point.y}
                r={index === coords.length - 1 ? 3.6 : 2.6}
                fill={index === coords.length - 1 ? "#E84B77" : "#FDB6CB"}
                stroke="white"
                strokeWidth="1.4"
              />
            ))}
          </svg>
        ) : (
          <div className="flex h-full items-center justify-center text-[12px] font-medium text-rose-200">还没有节律记录</div>
        )}
      </div>
      {values.length ? (
        <div className="mt-2 flex justify-between text-[10px] font-medium text-gray-400">
          <span>低 {min}</span>
          <span>高 {max}</span>
        </div>
      ) : null}
    </div>
  );
}

function ParamPill({ label, value }: { label: string; value: unknown }) {
  const n = Number(value);
  const text = Number.isFinite(n) ? `${Math.round(Math.max(0, Math.min(1, n)) * 100)}%` : "-";
  return (
    <div className="rounded-[14px] bg-white/70 px-2 py-2">
      <div className="font-medium text-gray-400">{label}</div>
      <div className="mt-1 font-semibold text-gray-800">{text}</div>
    </div>
  );
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

function Metric({ label, value, unit }: { label: string; value: React.ReactNode; unit?: string }) {
  return (
    <div className="rounded-[20px] bg-white px-4 py-4">
      <div className="text-[12px] font-medium text-gray-400">{label}</div>
      <div className="mt-2 flex min-h-[34px] items-end gap-1">
        <span className="text-[28px] font-semibold leading-none tracking-tight text-gray-950">{value}</span>
        {unit ? <span className="pb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">{unit}</span> : null}
      </div>
    </div>
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
