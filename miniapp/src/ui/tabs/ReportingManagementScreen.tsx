import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Capacitor } from "@capacitor/core";
import { apiJson } from "../api";
import { useToast } from "../toast";
import { SumiOverlay, type SenseReportingStatus } from "../../plugins/sumi-overlay";

type ReportingBucketKey = "battery" | "screen" | "foreground" | "location" | "usage";
type ReportingTypeMeta = { key: ReportingBucketKey | string; label: string };
type ReportingHistoryRow = { type?: string; label?: string; at?: string; data?: Record<string, any> };
type ReportingCloudResponse = {
  ok?: boolean;
  device_id?: string;
  latest?: Record<string, Record<string, any>>;
  history?: ReportingHistoryRow[];
  types?: ReportingTypeMeta[];
  error?: string;
};

const DEFAULT_TYPES: ReportingTypeMeta[] = [
  { key: "battery", label: "电量" },
  { key: "screen", label: "屏幕" },
  { key: "foreground", label: "前台应用" },
  { key: "location", label: "位置" },
  { key: "usage", label: "使用统计" },
];

export function ReportingManagementScreen() {
  const toast = useToast();
  const [nativeStatus, setNativeStatus] = useState<SenseReportingStatus | null>(null);
  const [cloud, setCloud] = useState<ReportingCloudResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [headerActionsEl, setHeaderActionsEl] = useState<HTMLElement | null>(null);
  const isAndroid = Capacitor.getPlatform() === "android";

  const types = useMemo(() => {
    const remoteTypes = Array.isArray(cloud?.types) ? cloud.types : [];
    const incoming = remoteTypes.length ? remoteTypes : DEFAULT_TYPES;
    return incoming.filter((item) => String(item?.key || "").trim() !== "health");
  }, [cloud?.types]);

  const history = useMemo(() => (cloud?.history || []).slice(0, 60), [cloud?.history]);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const [nextNative, nextCloud] = await Promise.all([
        SumiOverlay.getSenseReportingStatus().catch(() => null),
        apiJson<ReportingCloudResponse>(`/miniapp-api/device-state/reporting?t=${Date.now()}`, { cache: "no-store" }).catch((e) => ({ ok: false, error: e?.message || String(e) })),
      ]);
      setNativeStatus(nextNative);
      setCloud(nextCloud);
      if (nextCloud && !nextCloud.ok && nextCloud.error && !opts?.silent) {
        toast(`云端状态加载失败：${nextCloud.error}`);
      }
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setHeaderActionsEl(document.getElementById("reporting-header-actions"));
  }, []);

  async function toggleEnabled(next: boolean) {
    const prev = nativeStatus;
    setNativeStatus((s) => ({ ...(s || {}), enabled: next }));
    setSaving(true);
    try {
      const r = await SumiOverlay.setSenseReportingConfig({ enabled: next });
      setNativeStatus((s) => ({ ...(s || {}), enabled: !!r.enabled }));
      toast(r.enabled ? "上报已开启" : "上报已关闭");
      if (r.enabled) void requestSnapshot({ silentToast: true });
    } catch (e: any) {
      setNativeStatus(prev);
      toast(`上报开关保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function requestSnapshot(opts?: { silentToast?: boolean }) {
    setRefreshing(true);
    try {
      const r = await SumiOverlay.requestSenseReportingSnapshot();
      if (!r?.requested && !opts?.silentToast) {
        toast("安卓后台还没接上");
      } else if (!opts?.silentToast) {
        toast("已请求立刻上报");
      }
      await load({ silent: true });
      window.setTimeout(() => void load({ silent: true }), 900);
      window.setTimeout(() => void load({ silent: true }), 2200);
    } catch (e: any) {
      toast(`刷新失败：${e?.message || e}`);
    } finally {
      setRefreshing(false);
    }
  }

  if (!isAndroid) {
    return (
      <div className="px-4 py-5">
        <div className="rounded-[24px] border border-gray-100 bg-white px-5 py-8 text-center shadow-[0_8px_30px_-18px_rgba(0,0,0,0.2)]">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-50 text-gray-700">
            <ReportingIcon />
          </div>
          <div className="text-[15px] font-semibold text-gray-900">上报管理只在 Android 端工作</div>
        </div>
      </div>
    );
  }

  const enabled = !!nativeStatus?.enabled;

  return (
    <div className="space-y-4 px-4 py-5">
      {headerActionsEl ? createPortal(
        <button
          type="button"
          disabled={loading || refreshing || saving || !enabled}
          aria-label={refreshing ? "正在请求上报" : "立刻上报"}
          title={refreshing ? "上报中" : "立刻上报"}
          className="flex h-8 w-8 items-center justify-center rounded-full text-gray-600 transition-colors active:bg-gray-100 disabled:opacity-40"
          onClick={() => void requestSnapshot()}
        >
          <RefreshIcon className={refreshing || loading ? "animate-spin" : ""} />
        </button>,
        headerActionsEl,
      ) : null}

      <section className="rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_10px_34px_-28px_rgba(0,0,0,0.3)]">
        <div className="flex items-center gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white">
            <ReportingIcon />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-semibold text-gray-900">非健康数据上报</div>
            <div className="mt-1 truncate text-[12px] text-gray-400">{nativeStatus?.deviceId || cloud?.device_id || "未识别设备"}</div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            disabled={saving}
            className={`relative h-8 w-[54px] shrink-0 rounded-full transition-colors ${enabled ? "bg-gray-900" : "bg-gray-200"} ${saving ? "opacity-60" : ""}`}
            onClick={() => void toggleEnabled(!enabled)}
          >
            <span className={`absolute left-1 top-1 h-6 w-6 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-[22px]" : "translate-x-0"}`} />
          </button>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <CapabilityBadge label="前台应用" active={!!nativeStatus?.accessibilityEnabled} />
          <CapabilityBadge label="位置权限" active={!!nativeStatus?.locationPermission} />
          <CapabilityBadge label="使用统计" active={!!nativeStatus?.usageStatsAvailable} />
        </div>
      </section>

      <section className="rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_10px_34px_-28px_rgba(0,0,0,0.3)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-[14px] font-semibold text-gray-900">当前数据</div>
            <div className="mt-1 text-[12px] text-gray-400">{loading ? "刷新中" : "服务器已收到的最新快照"}</div>
          </div>
          <button
            type="button"
            disabled={refreshing || !enabled}
            className="h-9 rounded-full bg-gray-100 px-4 text-[12px] font-semibold text-gray-700 active:bg-gray-200 disabled:opacity-40"
            onClick={() => void requestSnapshot()}
          >
            立刻上报
          </button>
        </div>
        <div className="space-y-3">
          {types.map((item) => {
            const key = String(item.key || "") as ReportingBucketKey;
            const data = cloud?.latest?.[key] || {};
            return (
              <ReportCurrentCard key={key} label={item.label || key} type={key} data={data} />
            );
          })}
        </div>
      </section>

      <section className="rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_10px_34px_-28px_rgba(0,0,0,0.3)]">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-[14px] font-semibold text-gray-900">上报日志</div>
            <div className="mt-1 text-[12px] text-gray-400">最近 {history.length || 0} 条</div>
          </div>
          <button type="button" className="text-[12px] font-semibold text-gray-500 active:text-gray-900" onClick={() => void load()}>
            刷新
          </button>
        </div>
        <div className="space-y-2">
          {history.map((row, idx) => (
            <ReportLogRow key={`${row.type || "row"}-${row.at || idx}-${idx}`} row={row} />
          ))}
          {!history.length ? (
            <div className="rounded-[18px] bg-gray-50 px-4 py-6 text-center text-[13px] text-gray-400">还没有非健康上报日志</div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function CapabilityBadge({ label, active }: { label: string; active: boolean }) {
  return (
    <div className={`rounded-[16px] px-3 py-2 text-center text-[11px] font-semibold ${active ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-400"}`}>
      {label}
    </div>
  );
}

function ReportCurrentCard({ label, type, data }: { label: string; type: string; data: Record<string, any> }) {
  const hasData = data && Object.keys(data).length > 0;
  return (
    <div className="rounded-[20px] bg-gray-50 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-gray-900">{label}</div>
          <div className="mt-1 break-words text-[12px] leading-5 text-gray-600">{hasData ? summarizeBucket(type, data) : "暂无数据"}</div>
        </div>
        <div className="shrink-0 text-right text-[11px] leading-5 text-gray-400">
          {formatTime(data?.updatedAt || data?.capturedAt || data?.observedAt || data?.reported_at)}
        </div>
      </div>
    </div>
  );
}

function ReportLogRow({ row }: { row: ReportingHistoryRow }) {
  const data = row.data || {};
  const type = String(row.type || "");
  return (
    <div className="rounded-[18px] border border-gray-100 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-semibold text-gray-700">{row.label || bucketLabel(type)}</span>
        <span className="text-[11px] text-gray-400">{formatTime(row.at || data.updatedAt)}</span>
      </div>
      <div className="mt-2 break-words text-[12px] leading-5 text-gray-600">{summarizeBucket(type, data)}</div>
    </div>
  );
}

function bucketLabel(type: string): string {
  const found = DEFAULT_TYPES.find((item) => item.key === type);
  return found?.label || type || "上报";
}

function summarizeBucket(type: string, data: Record<string, any>): string {
  if (!data || !Object.keys(data).length) return "暂无数据";
  if (type === "battery") {
    const level = valueText(data.level);
    const charging = data.charging ? "充电中" : "未充电";
    return level ? `${level}% · ${charging}` : charging;
  }
  if (type === "screen") {
    const event = screenEventLabel(data.event);
    const interactive = data.interactive === true ? "亮屏" : "息屏";
    const duration = data.screenOffDurationMs ? ` · 息屏 ${formatDuration(Number(data.screenOffDurationMs))}` : "";
    return `${event || "屏幕状态"} · ${interactive}${duration}`;
  }
  if (type === "foreground") {
    const name = valueText(data.appName || data.app_name || data.packageName || data.package_name);
    const pkg = valueText(data.packageName || data.package_name);
    return pkg && pkg !== name ? `${name} · ${pkg}` : name || "暂无前台应用";
  }
  if (type === "location") {
    const lat = formatCoord(data.lat);
    const lng = formatCoord(data.lng);
    const accuracy = data.accuracy || data.accuracy === 0 ? ` · ±${Math.round(Number(data.accuracy))}m` : "";
    const provider = valueText(data.provider);
    const address = valueText(data.address || data.formatted_address);
    return [lat && lng ? `${lat}, ${lng}${accuracy}` : "", provider, address].filter(Boolean).join(" · ") || "暂无位置";
  }
  if (type === "usage") {
    const apps = Array.isArray(data.apps) ? data.apps.slice(0, 3) : [];
    if (!apps.length) return "暂无使用统计";
    return apps.map((app: any) => `${valueText(app.appName || app.packageName) || "App"} ${formatDuration(Number(app.foregroundMs || 0))}`).join(" · ");
  }
  return Object.entries(data)
    .filter(([key]) => !["deviceId", "device_id", "updatedAt"].includes(key))
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${valueText(value)}`)
    .join(" · ") || "已上报";
}

function valueText(value: unknown): string {
  return String(value ?? "").trim();
}

function formatCoord(value: unknown): string {
  const num = Number(value);
  if (!Number.isFinite(num)) return "";
  return num.toFixed(5);
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "0 分钟";
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}小时${rest}分钟` : `${hours}小时`;
}

function screenEventLabel(raw: unknown): string {
  const value = String(raw || "").trim();
  if (value === "screen_on") return "屏幕亮起";
  if (value === "screen_off") return "屏幕关闭";
  if (value === "user_present") return "已解锁";
  if (value === "app_active") return "App 活跃";
  return value;
}

function formatTime(raw: unknown): string {
  const value = String(raw || "").trim();
  if (!value) return "-";
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  return value.replace("T", " ").replace("+08:00", "").replace("Z", "").slice(0, 16);
}

function RefreshIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={`h-[18px] w-[18px] ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 12a9 9 0 0 1-15.5 6.2" />
      <path d="M3 12A9 9 0 0 1 18.5 5.8" />
      <path d="M18 3v4h4" />
      <path d="M6 21v-4H2" />
    </svg>
  );
}

function ReportingIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 15v-4" />
      <path d="M12 15V8" />
      <path d="M16 15v-6" />
      <path d="M20 15v-2" />
    </svg>
  );
}
