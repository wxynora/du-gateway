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
type HealthHistoryRow = { at?: string; heartRate?: string | number; steps?: string | number; source: string };
type DuVitalsHistoryRow = {
  at?: string;
  heart?: number;
  breath?: number;
  focus?: unknown;
  close?: unknown;
  tension?: unknown;
  status?: string;
};
type FlippedCardKind = "sumika" | "du";

const CLOUD_HEALTH_RECORD_DISPLAY_LIMIT = 1;
const HEALTH_REPORT_LOG_DISPLAY_LIMIT = 10;
const ANNIVERSARY_NUMBER_FONT = "'Playfair Display', Georgia, serif";

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
  const [flippedCard, setFlippedCard] = useState<FlippedCardKind | null>(null);
  const isAndroid = Capacitor.getPlatform() === "android";

  const latestLocal = status?.last || {};
  const latestCloud = cloud?.latest || {};
  const cloudHealthRows = useMemo(() => (cloud?.history || []).slice(0, CLOUD_HEALTH_RECORD_DISPLAY_LIMIT), [cloud?.history]);
  const reportLogs = useMemo(() => (status?.logs || []).slice(-HEALTH_REPORT_LOG_DISPLAY_LIMIT).reverse(), [status?.logs]);
  const sumikaHistoryRows = useMemo(
    () => normalizeHealthHistory(cloud?.history || [], latestCloud, latestLocal),
    [cloud?.history, latestCloud, latestLocal],
  );
  const duVitalsHistoryRows = useMemo(
    () => normalizeDuVitalsHistory(cloud?.du_vitals_history || [], cloud?.du_vitals || {}),
    [cloud?.du_vitals_history, cloud?.du_vitals],
  );
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
      <FlipCard
        flipped={flippedCard === "sumika"}
        front={(
          <section
            role="button"
            tabIndex={0}
            aria-label="查看 Sumika 心跳最近十次记录"
            className="relative min-h-[248px] cursor-pointer overflow-hidden rounded-[32px] border border-black/5 bg-white p-6 text-[#111111] shadow-[0_28px_70px_-46px_rgba(0,0,0,0.42)] outline-none transition-transform active:scale-[0.995] focus-visible:ring-2 focus-visible:ring-black/20"
            style={{ fontFamily: "'Inter', sans-serif" }}
            onClick={() => setFlippedCard("sumika")}
            onKeyDown={(e) => handleCardKeyDown(e, () => setFlippedCard("sumika"))}
          >
            <div className="flex items-start justify-between gap-4 border-b border-black/10 pb-4">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-black/45">Sumika Heartbeat</div>
                <div className="mt-1 text-[13px] font-medium text-black/55">Notify for Xiaomi</div>
              </div>
              <span className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-semibold ${status?.listenerEnabled ? "bg-black text-white" : "bg-black/8 text-black/60"}`}>
                {status?.listenerEnabled ? "已授权" : "未授权"}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-5 py-8">
              <BiometricMetric
                label="Heart Rate / 心率"
                value={displayHealth.heartRate || "-"}
                unit={displayHealth.heartRate ? "bpm" : ""}
              />
              <BiometricMetric
                label="Steps / 步数"
                value={displayHealth.steps || "-"}
                unit={displayHealth.steps ? "steps" : ""}
              />
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
        )}
        back={<SumikaHistoryCardBack rows={sumikaHistoryRows} onClose={() => setFlippedCard(null)} />}
      />

      <DuVitalsCard
        vitals={cloud?.du_vitals || {}}
        historyRows={duVitalsHistoryRows}
        flipped={flippedCard === "du"}
        onFlip={() => setFlippedCard("du")}
        onClose={() => setFlippedCard(null)}
      />

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

function DuVitalsCard({
  vitals,
  historyRows,
  flipped,
  onFlip,
  onClose,
}: {
  vitals: Record<string, any>;
  historyRows: DuVitalsHistoryRow[];
  flipped: boolean;
  onFlip: () => void;
  onClose: () => void;
}) {
  const heart = Number(vitals?.heart_bpm || 0);
  const breath = Number(vitals?.breath_rpm || 0);
  const params = typeof vitals?.parameters === "object" && vitals.parameters ? vitals.parameters : {};
  const heartHistory = useMemo(
    () => historyRows
      .slice()
      .reverse()
      .map((item) => ({ at: item.at, value: Number(item.heart || 0) }))
      .filter((item) => Number.isFinite(item.value) && item.value > 0),
    [historyRows],
  );
  const hasVitals = heart > 0 || breath > 0;
  return (
    <FlipCard
      flipped={flipped}
      front={(
        <section
          role="button"
          tabIndex={0}
          aria-label="查看渡心跳最近十次记录"
          className="relative min-h-[360px] cursor-pointer overflow-hidden rounded-[32px] bg-[#111111] p-6 text-white shadow-[0_34px_80px_-48px_rgba(0,0,0,0.85)] outline-none transition-transform active:scale-[0.995] focus-visible:ring-2 focus-visible:ring-white/30"
          style={{ fontFamily: "'Inter', sans-serif" }}
          onClick={onFlip}
          onKeyDown={(e) => handleCardKeyDown(e, onFlip)}
        >
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
          <div className="grid grid-cols-2 gap-5 py-8">
            <BiometricMetric
              label="Du Heart / 渡心率"
              value={heart || "-"}
              unit={heart ? "bpm" : ""}
              tone="dark"
            />
            <BiometricMetric
              label="Du Breath / 渡呼吸"
              value={breath || "-"}
              unit={breath ? "brpm" : ""}
              tone="dark"
            />
          </div>
          <DuHeartCurve points={heartHistory} />
          <div className="mt-4 text-[10px] uppercase tracking-[0.08em] text-white/42">
            Focus {formatParamPercent(params.focus)} · Close {formatParamPercent(params.intimacy_heat)} · Tension {formatParamPercent(params.tension)}
          </div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.08em] text-white/42">Sync {formatTime(vitals?.updatedAt || vitals?.at) || "-"}</div>
        </section>
      )}
      back={<DuHistoryCardBack rows={historyRows} onClose={onClose} />}
    />
  );
}

function handleCardKeyDown(event: React.KeyboardEvent<HTMLElement>, action: () => void) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  action();
}

function normalizeHealthHistory(
  history: Array<{ at?: string; data?: Record<string, any> }>,
  latestCloud: Record<string, any>,
  latestLocal: Record<string, any>,
): HealthHistoryRow[] {
  const rows: HealthHistoryRow[] = [];
  const add = (data: Record<string, any>, at: string | undefined, source: string) => {
    const heartRate = data?.heart_rate ?? data?.heartRate ?? "";
    const steps = data?.steps ?? data?.step_count ?? data?.stepCount ?? "";
    const rowAt = at || data?.updatedAt || data?.status_at || data?.capturedAt || data?.captured_at || data?.at || "";
    if (!hasHistoryValue(heartRate) && !hasHistoryValue(steps)) return;
    const key = `${rowAt}|${heartRate}|${steps}`;
    if (rows.some((item) => `${item.at || ""}|${item.heartRate || ""}|${item.steps || ""}` === key)) return;
    rows.push({ at: String(rowAt || "").trim(), heartRate, steps, source });
  };

  for (const row of Array.isArray(history) ? history : []) {
    add(row.data || {}, row.at, "云端");
  }
  if (Object.keys(latestCloud || {}).length) add(latestCloud, undefined, "云端");
  if (Object.keys(latestLocal || {}).length && !rows.length) add(latestLocal, undefined, "本机");

  return rows.sort((a, b) => recordTime(b.at) - recordTime(a.at)).slice(0, 10);
}

function normalizeDuVitalsHistory(history: Array<Record<string, any>>, latest: Record<string, any>): DuVitalsHistoryRow[] {
  const rows: DuVitalsHistoryRow[] = [];
  const add = (item: Record<string, any>) => {
    const params = typeof item?.parameters === "object" && item.parameters ? item.parameters : {};
    const heart = Number(item?.heart_bpm || item?.heartBpm || 0);
    const breath = Number(item?.breath_rpm || item?.breathRpm || 0);
    const at = String(item?.updatedAt || item?.at || "").trim();
    if (!(heart > 0) && !(breath > 0)) return;
    const key = `${at}|${heart}|${breath}`;
    if (rows.some((row) => `${row.at || ""}|${row.heart || 0}|${row.breath || 0}` === key)) return;
    rows.push({
      at,
      heart: Number.isFinite(heart) && heart > 0 ? heart : undefined,
      breath: Number.isFinite(breath) && breath > 0 ? breath : undefined,
      focus: params.focus ?? item?.focus,
      close: params.intimacy_heat ?? item?.intimacy_heat,
      tension: params.tension ?? item?.tension,
      status: item?.status ? String(item.status) : undefined,
    });
  };

  for (const item of Array.isArray(history) ? history : []) {
    add(item);
  }
  if (Object.keys(latest || {}).length) add(latest);

  return rows.sort((a, b) => recordTime(b.at) - recordTime(a.at)).slice(0, 10);
}

function recordTime(value?: string) {
  const dt = new Date(String(value || ""));
  const time = dt.getTime();
  return Number.isNaN(time) ? 0 : time;
}

function hasHistoryValue(value: unknown) {
  return value !== undefined && value !== null && value !== "";
}

function DuHeartCurve({ points }: { points: DuHeartPoint[] }) {
  const values = points.map((point) => point.value);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const width = 400;
  const height = 80;
  const path = buildStraightLinePath(values, min, max, width, height);

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

function buildStraightLinePath(values: number[], min: number, max: number, width: number, height: number) {
  const padY = 10;
  const span = Math.max(1, max - min);
  const coords = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : (index * width) / (values.length - 1);
    const y = padY + ((max - value) * (height - padY * 2)) / span;
    return { x, y };
  });
  if (!coords.length) return `M 0,${height / 2} L ${width},${height / 2}`;
  if (coords.length === 1) return `M 0,${coords[0].y.toFixed(1)} L ${width},${coords[0].y.toFixed(1)}`;
  return coords
    .map((point, index) => {
      if (index === 0) return `M ${point.x.toFixed(1)},${point.y.toFixed(1)}`;
      return `L ${point.x.toFixed(1)},${point.y.toFixed(1)}`;
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

function FlipCard({ flipped, front, back }: { flipped: boolean; front: React.ReactNode; back: React.ReactNode }) {
  return (
    <div style={{ perspective: "1200px" }}>
      <div
        className="relative transition-transform duration-500"
        style={{
          transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)",
          transformStyle: "preserve-3d",
        }}
      >
        <div style={{ backfaceVisibility: "hidden" }}>{front}</div>
        <div className="absolute inset-0" style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}>{back}</div>
      </div>
    </div>
  );
}

function SumikaHistoryCardBack({ rows, onClose }: { rows: HealthHistoryRow[]; onClose: () => void }) {
  return (
    <section className="relative min-h-[248px] overflow-hidden rounded-[32px] border border-black/5 bg-[#FBFAF8] p-5 text-black shadow-[0_28px_70px_-46px_rgba(0,0,0,0.42)]" style={{ fontFamily: "'Inter', sans-serif" }}>
      <HistoryBackHeader title="Sumika Heartbeat" subtitle={`最近 ${rows.length || 0} 次记录`} tone="light" onClose={onClose} />
      <div className="mt-3 max-h-[164px] space-y-2 overflow-y-auto pr-1">
        {rows.map((row, index) => (
          <div key={`${row.at || ""}-${index}`} className="rounded-[16px] border border-black/5 bg-black/[0.035] px-3 py-2.5">
            <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-[0.1em] text-black/42">
              <span>{formatTime(row.at) || "-"}</span>
              <span>{row.source}</span>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-3">
              <HistoryMetric label="Heart" value={hasHistoryValue(row.heartRate) ? row.heartRate : "-"} unit={hasHistoryValue(row.heartRate) ? "bpm" : ""} />
              <HistoryMetric label="Steps" value={hasHistoryValue(row.steps) ? row.steps : "-"} unit={hasHistoryValue(row.steps) ? "steps" : ""} />
            </div>
          </div>
        ))}
        {!rows.length ? <HistoryEmpty tone="light" /> : null}
      </div>
    </section>
  );
}

function DuHistoryCardBack({ rows, onClose }: { rows: DuVitalsHistoryRow[]; onClose: () => void }) {
  return (
    <section className="relative min-h-[360px] overflow-hidden rounded-[32px] bg-[#111111] p-5 text-white shadow-[0_34px_80px_-48px_rgba(0,0,0,0.85)]" style={{ fontFamily: "'Inter', sans-serif" }}>
      <HistoryBackHeader title="Du Heartbeat" subtitle={`最近 ${rows.length || 0} 次记录`} tone="dark" onClose={onClose} />
      <div className="mt-3 max-h-[276px] space-y-2 overflow-y-auto pr-1">
        {rows.map((row, index) => (
          <div key={`${row.at || ""}-${index}`} className="rounded-[16px] border border-white/10 bg-white/[0.08] px-3 py-2.5">
            <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-[0.1em] text-white/42">
              <span>{formatTime(row.at) || "-"}</span>
              <span>{row.status || "stream"}</span>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-3">
              <HistoryMetric label="Heart" value={row.heart || "-"} unit={row.heart ? "bpm" : ""} tone="dark" />
              <HistoryMetric label="Breath" value={row.breath || "-"} unit={row.breath ? "brpm" : ""} tone="dark" />
            </div>
            <div className="mt-2 truncate text-[9px] uppercase tracking-[0.08em] text-white/42">
              Focus {formatParamPercent(row.focus)} · Close {formatParamPercent(row.close)} · Tension {formatParamPercent(row.tension)}
            </div>
          </div>
        ))}
        {!rows.length ? <HistoryEmpty tone="dark" /> : null}
      </div>
    </section>
  );
}

function HistoryBackHeader({
  title,
  subtitle,
  tone,
  onClose,
}: {
  title: string;
  subtitle: string;
  tone: "light" | "dark";
  onClose: () => void;
}) {
  const dark = tone === "dark";
  return (
    <div className={`flex items-start justify-between gap-4 border-b pb-3 ${dark ? "border-white/10" : "border-black/10"}`}>
      <div>
        <div className={`text-[10px] font-semibold uppercase tracking-[0.22em] ${dark ? "text-white/42" : "text-black/42"}`}>{title}</div>
        <div className={`mt-1 text-[13px] font-medium ${dark ? "text-white/58" : "text-black/55"}`}>{subtitle}</div>
      </div>
      <button
        type="button"
        aria-label="返回"
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[17px] leading-none ${dark ? "bg-white/10 text-white/70 active:bg-white/15" : "bg-black/[0.06] text-black/55 active:bg-black/[0.1]"}`}
        onClick={onClose}
      >
        ↩
      </button>
    </div>
  );
}

function HistoryMetric({
  label,
  value,
  unit,
  tone = "light",
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  tone?: "light" | "dark";
}) {
  const dark = tone === "dark";
  return (
    <div className="min-w-0">
      <div className={`truncate text-[9px] uppercase tracking-[0.18em] ${dark ? "text-white/38" : "text-black/42"}`}>{label}</div>
      <div className="mt-1 flex min-w-0 items-start gap-1 overflow-hidden">
        <span className={`min-w-0 shrink text-[30px] leading-none ${dark ? "text-white" : "text-black"}`} style={{ fontFamily: ANNIVERSARY_NUMBER_FONT, fontWeight: 500 }}>
          {value}
        </span>
        {unit ? (
          <span className={`shrink-0 translate-y-[16px] text-[10px] italic ${dark ? "text-white/45" : "text-black/45"}`} style={{ fontFamily: ANNIVERSARY_NUMBER_FONT }}>
            {unit}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function HistoryEmpty({ tone }: { tone: "light" | "dark" }) {
  return (
    <div className={`rounded-[18px] px-4 py-8 text-center text-[13px] ${tone === "dark" ? "bg-white/[0.08] text-white/42" : "bg-black/[0.035] text-black/42"}`}>
      还没有最近记录
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
  const valueSize = compact ? "text-[34px]" : "text-[48px]";
  return (
    <div className="min-w-0">
      <div className={`truncate text-[9px] font-semibold uppercase tracking-[0.22em] ${tone === "dark" ? "text-white/38" : "text-black/42"}`}>{label}</div>
      <div className={`${compact ? "mt-2 min-h-[38px]" : "mt-4 min-h-[54px]"} flex min-w-0 items-start gap-1.5 overflow-hidden`}>
        <span
          className={`${valueSize} min-w-0 shrink leading-none tracking-normal ${tone === "dark" ? "text-white" : "text-black"}`}
          style={{ fontFamily: ANNIVERSARY_NUMBER_FONT, fontWeight: 500 }}
        >
          {value}
        </span>
        {unit ? (
          <span
            className={`shrink-0 translate-y-[27px] text-[12px] italic tracking-normal ${tone === "dark" ? "text-white/46" : "text-black/46"}`}
            style={{ fontFamily: ANNIVERSARY_NUMBER_FONT }}
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
