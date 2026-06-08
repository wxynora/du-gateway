import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { getOrCreatePanelDeviceId } from "../api";
import { useToast } from "../toast";
import {
  inspectChatStorageOverview,
  migrateLocalChatHistoriesToDevice,
  type ChatHistoryLocalStatRow,
  type ChatStorageOverview,
} from "../storage/chatHistoryDb";

type RowSummary = {
  windows: number;
  messages: number;
  latestAt: string;
};

export function ChatStorageManagementScreen() {
  const toast = useToast();
  const [overview, setOverview] = useState<ChatStorageOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [migrating, setMigrating] = useState(false);
  const [headerActionsEl, setHeaderActionsEl] = useState<HTMLElement | null>(null);

  const sqliteSummary = useMemo(() => summarizeRows(overview?.nativeRows || []), [overview?.nativeRows]);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const deviceId = await getOrCreatePanelDeviceId();
      const next = await inspectChatStorageOverview(deviceId);
      setOverview(next);
    } catch (e: any) {
      toast(`存储状态读取失败：${e?.message || e}`);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setHeaderActionsEl(document.getElementById("chat-storage-header-actions"));
  }, []);

  async function runMigrationCheck() {
    setMigrating(true);
    try {
      const deviceId = await getOrCreatePanelDeviceId();
      await migrateLocalChatHistoriesToDevice(deviceId);
      await load({ silent: true });
      toast("已重新检查本机聊天记录");
    } catch (e: any) {
      toast(`检查失败：${e?.message || e}`);
    } finally {
      setMigrating(false);
    }
  }

  const backendLabel = overview?.backend === "sqlite" ? "SQLite" : "不可用";
  const activeCount = overview?.activeOperations?.length || 0;

  return (
    <div className="space-y-4 px-4 py-5">
      {headerActionsEl ? createPortal(
        <button
          type="button"
          disabled={loading || migrating}
          aria-label="刷新存储状态"
          title="刷新"
          className="flex h-8 w-8 items-center justify-center rounded-full text-gray-600 transition-colors active:bg-gray-100 disabled:opacity-40"
          onClick={() => void load()}
        >
          <RefreshIcon className={loading ? "animate-spin" : ""} />
        </button>,
        headerActionsEl,
      ) : null}

      <section className="rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_10px_34px_-28px_rgba(0,0,0,0.3)]">
        <div className="flex items-center gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white">
            <StorageIcon />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-semibold text-gray-900">聊天记忆存储</div>
            <div className="mt-1 truncate text-[12px] text-gray-400">{overview?.deviceId || "读取中"}</div>
          </div>
          <span className="shrink-0 rounded-full bg-gray-100 px-3 py-1.5 text-[11px] font-semibold text-gray-600">
            {loading ? "检查中" : backendLabel}
          </span>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <SummaryPill label="当前后端" value={backendLabel} />
          <SummaryPill label="消息数" value={String(sqliteSummary.messages)} />
          <SummaryPill label="待恢复" value={`${activeCount}`} />
        </div>
        <button
          type="button"
          disabled={loading || migrating}
          className="mt-4 h-10 w-full rounded-full bg-gray-900 text-[13px] font-semibold text-white active:bg-gray-700 disabled:opacity-40"
          onClick={() => void runMigrationCheck()}
        >
          {migrating ? "检查中..." : "重新检查"}
        </button>
      </section>

      <section className="grid grid-cols-1 gap-3">
        <BackendCard
          title="SQLite"
          subtitle={overview?.nativeAvailable ? `原生可用${overview?.nativeSchemaVersion ? ` · schema ${overview.nativeSchemaVersion}` : ""}` : "当前不可用"}
          active={overview?.backend === "sqlite"}
          summary={sqliteSummary}
          rows={overview?.nativeRows || []}
          error={overview?.nativeError}
        />
      </section>

      <section className="rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_10px_34px_-28px_rgba(0,0,0,0.3)]">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-[14px] font-semibold text-gray-900">活跃 outbox</div>
            <div className="mt-1 text-[12px] text-gray-400">未完成、可恢复或可重试的发送任务</div>
          </div>
          <span className="rounded-full bg-gray-100 px-3 py-1 text-[11px] font-semibold text-gray-500">{activeCount}</span>
        </div>
        <div className="space-y-2">
          {(overview?.activeOperations || []).slice(0, 20).map((item) => (
            <div key={item.id} className="rounded-[18px] bg-gray-50 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 truncate text-[13px] font-semibold text-gray-800">{item.windowId || "-"}</div>
                <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-gray-500">{item.status}</span>
              </div>
              <div className="mt-1 truncate text-[11px] text-gray-400">{item.clientRequestId}</div>
              <div className="mt-1 text-[11px] text-gray-400">{formatTime(item.updatedAt || item.createdAt)}</div>
            </div>
          ))}
          {!activeCount ? (
            <div className="rounded-[18px] bg-gray-50 px-4 py-6 text-center text-[13px] text-gray-400">没有待恢复任务</div>
          ) : null}
        </div>
      </section>

      <div className="px-1 pb-2 text-[11px] leading-5 text-gray-400">
        这里显示的是本机聊天记忆存储。聊天历史和待恢复发送任务现在都走 Android 原生 SQLite。
      </div>
    </div>
  );
}

function summarizeRows(rows: ChatHistoryLocalStatRow[]): RowSummary {
  const safeRows = Array.isArray(rows) ? rows : [];
  return safeRows.reduce<RowSummary>((acc, row) => {
    const updatedAt = String(row?.updatedAt || "");
    return {
      windows: acc.windows + 1,
      messages: acc.messages + Number(row?.count || 0),
      latestAt: !acc.latestAt || updatedAt > acc.latestAt ? updatedAt : acc.latestAt,
    };
  }, { windows: 0, messages: 0, latestAt: "" });
}

function BackendCard({
  title,
  subtitle,
  active,
  summary,
  rows,
  error,
}: {
  title: string;
  subtitle: string;
  active: boolean;
  summary: RowSummary;
  rows: ChatHistoryLocalStatRow[];
  error?: string;
}) {
  return (
    <section className={`rounded-[28px] border p-5 shadow-[0_10px_34px_-28px_rgba(0,0,0,0.3)] ${active ? "border-gray-900 bg-white" : "border-gray-100 bg-white"}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <div className="text-[14px] font-semibold text-gray-900">{title}</div>
            {active ? <span className="rounded-full bg-gray-900 px-2 py-0.5 text-[10px] font-semibold text-white">当前</span> : null}
          </div>
          <div className="mt-1 text-[12px] text-gray-400">{subtitle}</div>
          {error ? <div className="mt-1 break-all text-[11px] text-rose-500">{error}</div> : null}
        </div>
        <div className="text-right text-[11px] text-gray-400">{formatTime(summary.latestAt)}</div>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2">
        <SummaryPill label="窗口" value={`${summary.windows}`} />
        <SummaryPill label="消息" value={`${summary.messages}`} />
      </div>
      <div className="space-y-2">
        {rows.slice(0, 8).map((row) => (
          <div key={row.key || `${title}-${row.windowId}`} className="rounded-[16px] bg-gray-50 px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 truncate text-[12px] font-semibold text-gray-700">{row.windowId || "-"}</div>
              <span className="shrink-0 text-[11px] font-semibold text-gray-500">{row.count || 0} 条</span>
            </div>
            <div className="mt-0.5 truncate text-[10px] text-gray-400">{row.deviceId || "-"}</div>
          </div>
        ))}
        {!rows.length ? (
          <div className="rounded-[16px] bg-gray-50 px-4 py-5 text-center text-[12px] text-gray-400">暂无记录</div>
        ) : null}
      </div>
    </section>
  );
}

function SummaryPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[16px] bg-gray-50 px-3 py-2">
      <div className="text-[10px] font-semibold text-gray-400">{label}</div>
      <div className="mt-0.5 truncate text-[12px] font-semibold text-gray-800">{value}</div>
    </div>
  );
}

function formatTime(value: string) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StorageIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6" />
      <path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
    </svg>
  );
}

function RefreshIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={`h-4 w-4 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 11a8 8 0 0 0-14.5-4.6L4 8" />
      <path d="M4 4v4h4" />
      <path d="M4 13a8 8 0 0 0 14.5 4.6L20 16" />
      <path d="M20 20v-4h-4" />
    </svg>
  );
}
