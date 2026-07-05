import React, { useCallback, useEffect, useState } from "react";
import { apiJson } from "../api";
import { HeaderPortal } from "../components";
import { useToast } from "../toast";

type DsAuditAttempt = {
  attempt?: number;
  parsed?: boolean;
  action?: string;
  tag?: string;
  issue?: string;
  content?: string;
  raw_preview?: string;
  action_counts?: Record<string, number>;
};

type DsAuditEvent = {
  timestamp?: string;
  source?: string;
  window_id?: string;
  round_index?: number | string;
  batch_size?: number;
  final_status?: string;
  final_action?: string;
  final_tag?: string;
  final_importance?: number;
  final_content?: string;
  final_issue?: string;
  final_fused_with_id?: string;
  attempt_count?: number;
  retry_count?: number;
  action_counts?: Record<string, number>;
  attempts?: DsAuditAttempt[];
};

type CoreCacheEntry = {
  id?: string;
  memory_id?: string;
  content?: string;
  tag?: string;
  promoted_by?: string;
  promoted_at?: string;
  importance?: number;
  mention_count?: number;
  emotion_label?: string;
  scene_type?: string;
  target_type?: string;
};

type DynamicMemoryMirrorKeyword = {
  term?: string;
  normalized_term?: string;
  source?: string;
  weight?: number;
  confidence?: number;
};

type DynamicMemoryMirrorItem = {
  memory_id?: string;
  content?: string;
  retrieval_text?: string;
  tag?: string;
  importance?: number;
  mention_count?: number;
  last_mentioned?: string;
  created_at?: string;
  content_hash?: string;
  keywords?: DynamicMemoryMirrorKeyword[];
};

type DynamicMemoryMirrorStatus = {
  ok?: boolean;
  db_path?: string;
  active_count?: number;
  inactive_count?: number;
  term_count?: number;
  meta?: Record<string, string>;
  last_run?: {
    finished_at?: string;
    memory_count?: number;
    inserted_count?: number;
    updated_count?: number;
    unchanged_count?: number;
    inactive_count?: number;
    keyword_count?: number;
    status?: string;
    error?: string;
  } | null;
  error?: string;
};

type DynamicMemoryMirrorResp = {
  ok?: boolean;
  status?: DynamicMemoryMirrorStatus;
  items?: DynamicMemoryMirrorItem[];
  visible_count?: number;
  keyword_missing_visible_count?: number;
  error?: string;
};

type DynamicMemoryMirrorBackfillResp = {
  ok?: boolean;
  error?: string;
  result?: {
    dry_run?: boolean;
    memory_count?: number;
    inserted_count?: number;
    updated_count?: number;
    unchanged_count?: number;
    inactive_count?: number;
    keyword_count?: number;
    sqlite_write?: boolean;
    r2_write?: boolean;
    source_snapshot_hash?: string;
    ids_hash?: string;
    db_path?: string;
  };
};

type MemoryDebugResp = {
  ok?: boolean;
  window_id?: string;
  scope?: "all" | "target" | string;
  summary?: string;
  summary_exists?: boolean;
  count?: number;
  total_count?: number;
  ds_audit?: {
    events?: DsAuditEvent[];
    total_count?: number;
    action_counts?: Record<string, number>;
    retry_events?: number;
    failed_events?: number;
  };
  core_cache?: {
    count?: number;
    visible_count?: number;
    items?: CoreCacheEntry[];
  };
  dynamic_stats?: {
    memory_count?: number;
    memory_tags?: string[];
    label_complete_count?: number;
    label_missing_count?: number;
    index_tags?: string[];
    vector_min_sim?: number;
    vector_topk?: number;
    vector_topn?: number;
    embedding_backend?: string;
    embedding_model?: string;
    embed_timeout_seconds?: number;
    embed_max_retries?: number;
    embed_retry_backoff_seconds?: number;
    recent_vector_error?: string;
    failed_ids_count?: number;
    failed_ids_preview?: string[];
    maintenance_report?: {
      timestamp?: string;
      dry_run?: boolean;
      memory_count_before?: number;
      memory_count_after?: number;
      backfilled_count?: number;
      pruned_count?: number;
      duplicate_candidate_count?: number;
      duplicate_candidates?: Array<{
        tag?: string;
        retrieval_text?: string;
        count?: number;
        ids?: string[];
      }>;
    };
  };
  error?: string;
};

function firstLinePreview(text: string, maxChars = 96) {
  const raw = (text || "").replace(/\r/g, "");
  const first = raw.split("\n").find((x) => x.trim()) || raw.trim();
  if (!first) return "（空）";
  if (first.length <= maxChars) return first;
  return `${first.slice(0, maxChars)}...`;
}

export function MemoryDebugTab() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [mirrorSyncLoading, setMirrorSyncLoading] = useState(false);
  const [data, setData] = useState<MemoryDebugResp | null>(null);
  const [mirrorData, setMirrorData] = useState<DynamicMemoryMirrorResp | null>(null);
  const [tab, setTab] = useState<"summary" | "dynamic" | "core">("summary");
  const [deletingCoreId, setDeletingCoreId] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [j, mirror] = await Promise.all([
        apiJson<MemoryDebugResp>(`/miniapp-api/memory-debug?limit=10&core_limit=180&scope=all`),
        apiJson<DynamicMemoryMirrorResp>(`/miniapp-api/dynamic-memory-mirror?limit=8`).catch((e: any) => ({
          ok: false,
          error: String(e?.message || e),
          items: [],
        })),
      ]);
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setData(j);
      setMirrorData(mirror);
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      reload();
    }, 5000);
    const onVisible = () => {
      if (document.visibilityState === "visible") reload();
    };
    const onFocus = () => reload();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onFocus);
    };
  }, [reload]);

  const dsAuditEvents = Array.isArray(data?.ds_audit?.events) ? data!.ds_audit!.events! : [];
  const dsActionCounts = data?.ds_audit?.action_counts || {};
  const coreItems = Array.isArray(data?.core_cache?.items) ? data!.core_cache!.items! : [];
  const mirrorStatus = mirrorData?.status || {};
  const mirrorMeta = mirrorStatus.meta || {};
  const mirrorItems = Array.isArray(mirrorData?.items) ? mirrorData!.items! : [];
  const mirrorConsistent = Number(mirrorStatus.active_count ?? 0) === Number(data?.dynamic_stats?.memory_count ?? -1);

  async function syncMirrorKeywords() {
    setMirrorSyncLoading(true);
    try {
      const j = await apiJson<DynamicMemoryMirrorBackfillResp>(`/miniapp-api/dynamic-memory-mirror/backfill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ write: true, max_terms: 32 }),
      });
      if (!j?.ok) throw new Error(j?.error || "同步失败");
      const result = j.result || {};
      toast(`关键词已同步：${String(result.memory_count ?? 0)} 条 / ${String(result.keyword_count ?? 0)} 词`);
      await reload();
    } catch (e: any) {
      toast(`同步失败：${e?.message || e}`);
    } finally {
      setMirrorSyncLoading(false);
    }
  }

  async function deleteCoreCacheItem(item: CoreCacheEntry) {
    const entryId = String(item.id || "").trim();
    if (!entryId) {
      toast("这条核心记忆没有可删除的 id");
      return;
    }
    if (deletingCoreId) return;
    const ok = window.confirm("删除这条核心记忆？");
    if (!ok) return;
    setDeletingCoreId(entryId);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/core_cache/${encodeURIComponent(entryId)}`, {
        method: "DELETE",
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除核心记忆");
      await reload();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    } finally {
      setDeletingCoreId("");
    }
  }

  return (
    <div className="flex min-h-full flex-col overflow-hidden bg-[#FDFDFD]" style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" }}>
      <style>{`
        .shadow-soft { box-shadow: 0 10px 25px -5px rgba(0,0,0,.04), 0 8px 10px -6px rgba(0,0,0,.02); }
        .reminder-card { transition: all .3s cubic-bezier(0.4, 0, 0.2, 1); }
        .reminder-card:active { transform: scale(.98); }
        .status-badge { padding: 2px 8px; border-radius: 6px; font-size: 10px; font-weight: 600; text-transform: uppercase; }
        .segmented-control { background:#f3f4f6; border-radius:14px; padding:2px; }
        .segmented-item { border-radius:12px; padding:7px 14px; font-size:13px; font-weight:600; transition:.2s; }
        .segmented-item.active { background:#fff; color:#111827; box-shadow:0 1px 2px rgba(0,0,0,.06); }
      `}</style>

      <HeaderPortal targetId="memory-debug-header-status">
        <button
          className="flex h-8 w-8 items-center justify-center rounded-full border border-gray-100/70 bg-white/80 text-gray-500 shadow-[0_3px_10px_rgba(15,23,42,0.04)] transition-colors active:bg-gray-50 disabled:opacity-50"
          onClick={reload}
          disabled={loading}
          title="刷新"
          aria-label="刷新记忆调试"
        >
          <svg className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>
      </HeaderPortal>

      <div className="relative z-10 space-y-4 px-5 pb-3 pt-7">
        <div className="flex items-center">
          <div className="segmented-control flex">
            <button
              className={`segmented-item ${tab === "summary" ? "active text-gray-800" : "text-gray-400"}`}
              onClick={() => setTab("summary")}
              disabled={loading}
            >
              近期
            </button>
            <button
              className={`segmented-item ${tab === "dynamic" ? "active text-gray-800" : "text-gray-400"}`}
              onClick={() => setTab("dynamic")}
              disabled={loading}
            >
              动态
            </button>
            <button
              className={`segmented-item ${tab === "core" ? "active text-gray-800" : "text-gray-400"}`}
              onClick={() => setTab("core")}
              disabled={loading}
            >
              核心
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 pb-20 pt-4">
        {tab === "summary" ? (
          <div className="space-y-4">
            <details className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft" open>
              <summary className="flex cursor-pointer list-none items-center justify-between">
                <h3 className="text-[14px] font-bold text-gray-800">当前窗口总结</h3>
                <svg className="h-4 w-4 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </summary>
              <div className="mt-4 border-t border-gray-50 pt-4">
                <p className="whitespace-pre-wrap text-[13px] font-light leading-relaxed text-gray-500">
                  {(data?.summary || "").trim() || "（当前暂无窗口总结）"}
                </p>
              </div>
            </details>
            {!((data?.summary || "").trim()) ? (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-gray-50">
                  <svg className="h-8 w-8 text-gray-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                </div>
                <h3 className="mb-1 text-[15px] font-medium text-gray-800">当前暂无窗口总结</h3>
                <p className="text-[12px] text-gray-400">稍后再来看看吧</p>
              </div>
            ) : null}
          </div>
        ) : tab === "dynamic" ? (
          <div className="space-y-6">
            <details className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft" open>
              <summary className="flex cursor-pointer list-none items-center justify-between">
                <div className="flex items-center space-x-2">
                  <h3 className="text-[14px] font-bold text-gray-800">动态层状态概览</h3>
                  <span className="status-badge bg-blue-50 text-blue-500">active</span>
                </div>
                <svg className="h-4 w-4 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </summary>
              <div className="mt-4 space-y-4 border-t border-gray-100 pt-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-gray-400">记忆条数</p>
                    <p className="text-[18px] font-bold text-gray-800">{String(data?.dynamic_stats?.memory_count ?? 0)}</p>
                  </div>
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-gray-400">索引标签</p>
                    <p className="text-[18px] font-bold text-gray-800">{String((data?.dynamic_stats?.index_tags || []).length)}</p>
                  </div>
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-gray-400">检索阈值</p>
                    <p className="text-[13px] font-bold text-gray-800">
                      {String(data?.dynamic_stats?.vector_min_sim ?? "-")} / top {String(data?.dynamic_stats?.vector_topn ?? "-")}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-gray-400">模型</p>
                    <p className="truncate text-[13px] font-bold text-gray-800">{String(data?.dynamic_stats?.embedding_model || "-")}</p>
                  </div>
                </div>
                <div className="flex items-center justify-between border-t border-gray-100 pt-4">
                  <span className="text-[12px] text-gray-400">Failed IDs</span>
                  <span className="text-[12px] font-bold text-gray-800">{String(data?.dynamic_stats?.failed_ids_count ?? 0)}</span>
                </div>
                <div className="whitespace-pre-wrap text-[12px] text-gray-500">
                  embedding: {String(data?.dynamic_stats?.embedding_backend || "-")} / {String(data?.dynamic_stats?.embedding_model || "-")}
                </div>
                <div className="whitespace-pre-wrap text-[12px] text-gray-500">
                  recent_vector_error: {String(data?.dynamic_stats?.recent_vector_error || "") || "(空)"}
                </div>
              </div>
            </details>

            <details className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft" open>
              <summary className="flex cursor-pointer list-none items-center justify-between">
                <div className="flex items-center space-x-2">
                  <h3 className="text-[14px] font-bold text-gray-800">SQLite mirror</h3>
                  <span className={`status-badge ${mirrorData?.ok && mirrorConsistent ? "bg-emerald-50 text-emerald-500" : "bg-amber-50 text-amber-500"}`}>
                    {mirrorData?.ok ? (mirrorConsistent ? "synced" : "diff") : "offline"}
                  </span>
                </div>
                <svg className="h-4 w-4 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </summary>
              <div className="mt-4 space-y-4 border-t border-gray-100 pt-4">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="text-[16px] font-bold text-gray-800">{String(mirrorStatus.active_count ?? 0)}</p>
                    <p className="mt-1 text-[10px] text-gray-400">Mirror</p>
                  </div>
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="text-[16px] font-bold text-gray-800">{String(data?.dynamic_stats?.memory_count ?? 0)}</p>
                    <p className="mt-1 text-[10px] text-gray-400">R2</p>
                  </div>
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="text-[16px] font-bold text-gray-800">{String(mirrorStatus.term_count ?? 0)}</p>
                    <p className="mt-1 text-[10px] text-gray-400">Terms</p>
                  </div>
                </div>
                <div className="rounded-2xl bg-gray-50 p-3 text-[11px] leading-relaxed text-gray-500">
                  <div className="flex items-center justify-between gap-3">
                    <span>last_sync</span>
                    <span className="truncate font-medium text-gray-700">{String(mirrorMeta.last_synced_at || mirrorStatus.last_run?.finished_at || "-")}</span>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-3">
                    <span>snapshot</span>
                    <span className="truncate font-mono text-gray-400">{String(mirrorMeta.source_snapshot_hash || "").slice(0, 12) || "-"}</span>
                  </div>
                  {mirrorData?.error ? <div className="mt-2 break-words text-amber-500">{mirrorData.error}</div> : null}
                </div>
                <button
                  className="w-full rounded-2xl bg-[#111827] px-4 py-3 text-[13px] font-bold text-white transition active:scale-[.99] disabled:opacity-50"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    syncMirrorKeywords();
                  }}
                  disabled={loading || mirrorSyncLoading}
                >
                  {mirrorSyncLoading ? "同步中..." : "同步关键词 mirror"}
                </button>
                {mirrorItems.length ? (
                  <div className="space-y-2">
                    {mirrorItems.slice(0, 5).map((item, idx) => {
                      const keywords = Array.isArray(item.keywords) ? item.keywords : [];
                      return (
                        <div key={`${String(item.memory_id || "")}-${idx}`} className="rounded-2xl bg-gray-50 p-3">
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <span className="truncate text-[11px] font-bold text-gray-700">{firstLinePreview(String(item.content || ""), 42)}</span>
                            <span className="shrink-0 rounded bg-white px-2 py-1 text-[10px] text-gray-400">{String(item.tag || "-")}</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {keywords.slice(0, 8).map((kw, ki) => (
                              <span key={`${String(kw.normalized_term || kw.term || "")}-${ki}`} className="rounded bg-white px-2 py-1 text-[10px] font-medium text-gray-500">
                                {String(kw.term || kw.normalized_term || "")}
                              </span>
                            ))}
                            {!keywords.length ? <span className="rounded bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-500">缺关键词</span> : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-2xl bg-gray-50 p-4 text-center text-[12px] text-gray-400">mirror 还没有同步内容</div>
                )}
              </div>
            </details>

            <details className="space-y-4">
              <summary className="reminder-card flex cursor-pointer list-none items-center justify-between rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft">
                <div className="flex items-baseline space-x-2">
                  <h2 className="text-[11px] font-bold uppercase tracking-widest text-gray-400">DS 写入审计</h2>
                  <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-bold text-violet-500">
                    {String(dsAuditEvents.length)} / {String(data?.ds_audit?.total_count ?? dsAuditEvents.length)}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[11px] font-medium text-gray-300">
                  <span>点击展开</span>
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </summary>
              <div className="space-y-4 pt-1">
              <div className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft">
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div className="rounded-2xl bg-emerald-50 p-3">
                    <p className="text-[16px] font-bold text-emerald-600">{String(dsActionCounts.new ?? 0)}</p>
                    <p className="mt-1 text-[10px] font-medium text-emerald-500">New</p>
                  </div>
                  <div className="rounded-2xl bg-blue-50 p-3">
                    <p className="text-[16px] font-bold text-blue-600">{String(dsActionCounts.merge ?? 0)}</p>
                    <p className="mt-1 text-[10px] font-medium text-blue-500">Merge</p>
                  </div>
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="text-[16px] font-bold text-gray-700">{String(dsActionCounts.skip ?? 0)}</p>
                    <p className="mt-1 text-[10px] font-medium text-gray-400">Skip</p>
                  </div>
                  <div className="rounded-2xl bg-amber-50 p-3">
                    <p className="text-[16px] font-bold text-amber-600">{String(data?.ds_audit?.retry_events ?? 0)}</p>
                    <p className="mt-1 text-[10px] font-medium text-amber-500">Retry</p>
                  </div>
                </div>
              </div>
              {dsAuditEvents.map((it, idx) => {
                const counts = it.action_counts || {};
                const attempts = Array.isArray(it.attempts) ? it.attempts : [];
                const action = String(it.final_action || "");
                const status = String(it.final_status || "");
                const actionTone =
                  action === "new" ? "bg-emerald-50 text-emerald-500" :
                  action === "merge" ? "bg-blue-50 text-blue-500" :
                  status === "ok" ? "bg-violet-50 text-violet-500" :
                  status === "skip" || action === "skip" ? "bg-gray-50 text-gray-400" :
                  "bg-red-50 text-red-500";
                return (
                  <details key={`${String(it.timestamp || "")}-ds-${idx}`} className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft" open={idx === 0}>
                    <summary className="cursor-pointer list-none">
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <div className="flex min-w-0 flex-wrap gap-1.5">
                          <span className={`status-badge ${actionTone}`}>{action || status || "unknown"}</span>
                          <span className="status-badge bg-gray-50 text-gray-400">{String(it.source || "-")}</span>
                          {Number(it.retry_count || 0) > 0 ? <span className="status-badge bg-amber-50 text-amber-500">retry {String(it.retry_count)}</span> : null}
                          {it.batch_size ? <span className="status-badge bg-violet-50 text-violet-500">batch {String(it.batch_size)}</span> : null}
                        </div>
                        <span className="shrink-0 text-[11px] text-gray-300">{String(it.timestamp || "")}</span>
                      </div>
                      <h3 className="text-[14px] font-bold leading-snug text-gray-800 break-words">
                        {String(it.final_content || it.final_issue || JSON.stringify(counts) || "（空）")}
                      </h3>
                    </summary>
                    <div className="mt-4 space-y-3 border-t border-gray-50 pt-4">
                      <div className="grid grid-cols-2 gap-2 text-[11px] text-gray-400">
                        <div className="rounded-2xl bg-gray-50 p-3">window: {String(it.window_id || "-")}</div>
                        <div className="rounded-2xl bg-gray-50 p-3">round: {String(it.round_index || "-")}</div>
                        <div className="rounded-2xl bg-gray-50 p-3">status: {status || "-"}</div>
                        <div className="rounded-2xl bg-gray-50 p-3">attempts: {String(it.attempt_count ?? attempts.length)}</div>
                      </div>
                      {it.final_issue ? <div className="rounded-2xl bg-red-50 p-3 text-[12px] text-red-500">issue: {String(it.final_issue)}</div> : null}
                      {attempts.length ? (
                        <div className="space-y-2">
                          {attempts.map((attempt, ai) => (
                            <div key={`${String(attempt.attempt || ai)}-${ai}`} className="rounded-2xl bg-gray-50 p-3 text-[11px] leading-relaxed text-gray-500">
                              <div className="mb-1 flex items-center justify-between">
                                <span className="font-bold text-gray-700">attempt {String(attempt.attempt ?? ai + 1)}</span>
                                <span>{attempt.parsed ? "parsed" : "unparsed"}</span>
                              </div>
                              <div>action: {String(attempt.action || JSON.stringify(attempt.action_counts || {}) || "-")}</div>
                              <div>issue: {String(attempt.issue || "(无)")}</div>
                              {attempt.content || attempt.raw_preview ? (
                                <div className="mt-1 break-words">content: {firstLinePreview(String(attempt.content || attempt.raw_preview || ""), 120)}</div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </details>
                );
              })}
              {!dsAuditEvents.length ? <div className="px-1 py-4 text-[12px] text-gray-300">（暂无 DS 写入审计）</div> : null}
              </div>
            </details>

          </div>
        ) : (
          <div className="space-y-5">
            <div className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft">
              <div className="mb-4 flex items-start justify-between">
                <div>
                  <h3 className="text-[14px] font-bold text-gray-800">核心记忆</h3>
                  <p className="mt-1 text-[12px] text-gray-400">按提拔时间倒序显示</p>
                </div>
                <span className="status-badge bg-purple-50 text-purple-500">
                  {String(data?.core_cache?.visible_count ?? coreItems.length)} / {String(data?.core_cache?.count ?? coreItems.length)}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-2xl bg-gray-50 p-3">
                  <p className="text-[16px] font-bold text-gray-800">{String(data?.core_cache?.count ?? 0)}</p>
                  <p className="mt-1 text-[10px] text-gray-400">Total</p>
                </div>
                <div className="rounded-2xl bg-gray-50 p-3">
                  <p className="text-[16px] font-bold text-gray-800">{String(coreItems.filter((x) => x.promoted_by === "importance").length)}</p>
                  <p className="mt-1 text-[10px] text-gray-400">Importance</p>
                </div>
                <div className="rounded-2xl bg-gray-50 p-3">
                  <p className="text-[16px] font-bold text-gray-800">{String(coreItems.filter((x) => x.promoted_by === "mention_count").length)}</p>
                  <p className="mt-1 text-[10px] text-gray-400">Mention</p>
                </div>
              </div>
            </div>

            {coreItems.map((item, idx) => (
              <details key={`${String(item.id || "")}-${idx}`} className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft" open={idx < 3}>
                <summary className="cursor-pointer list-none">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        <span className="status-badge bg-purple-50 text-purple-500">{String(item.tag || "core")}</span>
                        <span className="status-badge bg-gray-50 text-gray-400">{String(item.promoted_by || "-")}</span>
                      </div>
                      <h3 className="text-[14px] font-bold leading-snug text-gray-800 break-words">{firstLinePreview(String(item.content || ""), 58)}</h3>
                    </div>
                    <svg className="mt-1 h-4 w-4 shrink-0 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </div>
                </summary>
                <div className="mt-4 space-y-3 border-t border-gray-50 pt-4">
                  <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-gray-600 break-words">{String(item.content || "(空)")}</p>
                  <div className="flex flex-wrap gap-1.5 text-[10px] text-gray-400">
                    <span className="rounded bg-gray-50 px-2 py-1">imp {String(item.importance ?? 0)}</span>
                    <span className="rounded bg-gray-50 px-2 py-1">mention {String(item.mention_count ?? 0)}</span>
                    {item.scene_type ? <span className="rounded bg-gray-50 px-2 py-1">{item.scene_type}</span> : null}
                    {item.target_type ? <span className="rounded bg-gray-50 px-2 py-1">{item.target_type}</span> : null}
                  </div>
                  <div className="flex items-end justify-between gap-3">
                    <div className="min-w-0 break-all text-[10px] leading-relaxed text-gray-300">
                      id: {String(item.memory_id || item.id || "")}
                      <br />
                      promoted_at: {String(item.promoted_at || "")}
                    </div>
                    <button
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-red-100 bg-red-50 text-red-400 transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        deleteCoreCacheItem(item);
                      }}
                      disabled={deletingCoreId === String(item.id || "")}
                      title="删除核心记忆"
                      aria-label="删除核心记忆"
                    >
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M3 6h18" />
                        <path d="M8 6V4h8v2" />
                        <path d="M19 6l-1 14H6L5 6" />
                        <path d="M10 11v5" />
                        <path d="M14 11v5" />
                      </svg>
                    </button>
                  </div>
                </div>
              </details>
            ))}
            {!coreItems.length ? <div className="px-1 py-10 text-center text-[12px] text-gray-300">（暂无核心记忆条目）</div> : null}
          </div>
        )}
      </div>
    </div>
  );
}
