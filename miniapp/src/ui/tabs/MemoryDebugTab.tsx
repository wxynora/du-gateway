import React, { useCallback, useEffect, useState } from "react";
import { apiJson } from "../api";
import { HeaderPortal, HeaderStatusPill } from "../components";
import { useToast } from "../toast";

type RecallScore = {
  id?: string;
  memory_id?: string;
  content?: string;
  retrieval_text?: string;
  total?: number;
  sem_user?: number;
  sem_ctx?: number;
};

type ReferencedMemory = {
  id?: string;
  entry_id?: string;
  source?: string;
  content?: string;
  tag?: string;
  promoted_by?: string;
  promoted_at?: string;
  importance?: number;
  mention_count?: number;
  last_mentioned?: string;
};

type RecalledMemoryItem = ReferencedMemory & {
  label?: string;
  memory_id?: string;
  line?: string;
};

type RecallEvent = {
  timestamp?: string;
  window_id?: string;
  query?: string;
  scene_type?: string;
  target_type?: string;
  time_range?: string;
  reason?: string;
  suspicion_level?: string;
  keywords?: string[];
  keyword_debug?: Array<{ text?: string; is_phrase?: boolean }>;
  retrieval_query?: string;
  source?: string;
  recalled_lines?: Array<
    | string
    | {
        id?: string;
        content?: string;
        emotion_label?: string;
        scene_type?: string;
        target_type?: string;
        semantic_score?: number;
        final_score?: number;
      }
  >;
  recalled_count?: number;
  recalled_items?: RecalledMemoryItem[];
  scores?: RecallScore[];
  referenced_memory_ids?: string[];
  referenced_memories?: ReferencedMemory[];
  assistant_preview?: string;
  citation_timestamp?: string;
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

type MemoryDebugResp = {
  ok?: boolean;
  window_id?: string;
  scope?: "all" | "target" | string;
  summary?: string;
  summary_exists?: boolean;
  recalls?: RecallEvent[];
  search_memory_events?: RecallEvent[];
  citation_events?: RecallEvent[];
  count?: number;
  total_count?: number;
  search_count?: number;
  search_total_count?: number;
  citation_count?: number;
  citation_total_count?: number;
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

function memoryItemId(item: RecalledMemoryItem | RecallScore) {
  return String((item as RecalledMemoryItem).memory_id || item.id || "").trim();
}

export function MemoryDebugTab() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [data, setData] = useState<MemoryDebugResp | null>(null);
  const [scope, setScope] = useState<"all" | "target">("all");
  const [tab, setTab] = useState<"summary" | "dynamic" | "core">("summary");
  const [deletingCoreId, setDeletingCoreId] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const j = await apiJson<MemoryDebugResp>(`/miniapp-api/memory-debug?limit=10&core_limit=180&scope=${scope}`);
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setData(j);
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [toast, scope]);

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

  const recalls = Array.isArray(data?.recalls) ? data!.recalls! : [];
  const searchEvents = Array.isArray(data?.search_memory_events) ? data!.search_memory_events! : [];
  const coreItems = Array.isArray(data?.core_cache?.items) ? data!.core_cache!.items! : [];
  const maintenance = data?.dynamic_stats?.maintenance_report;

  async function runMaintenance() {
    setMaintenanceLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/memory-maintenance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit_candidates: 20 }),
      });
      if (!j?.ok) throw new Error(j?.error || "整理失败");
      toast("离线整理已执行");
      await reload();
    } catch (e: any) {
      toast(`整理失败：${e?.message || e}`);
    } finally {
      setMaintenanceLoading(false);
    }
  }

  async function deleteCoreCacheItem(item: CoreCacheEntry) {
    const entryId = String(item.id || "").trim();
    if (!entryId) {
      toast("这条核心缓存没有可删除的 id");
      return;
    }
    if (deletingCoreId) return;
    const ok = window.confirm("删除这条核心缓存待审记忆？");
    if (!ok) return;
    setDeletingCoreId(entryId);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/core_cache/${encodeURIComponent(entryId)}`, {
        method: "DELETE",
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除核心缓存");
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
        .tab-active { color:#111827; position:relative; }
        .tab-active::after { content:""; position:absolute; left:0; right:0; bottom:-1px; height:2px; background:#111827; border-radius:2px; }
      `}</style>

      <HeaderPortal targetId="memory-debug-header-status">
        <HeaderStatusPill text="实时" dotClassName="bg-green-400" pulse />
      </HeaderPortal>

      <div className="space-y-4 px-5 pb-2 pt-4">
        <div className="flex items-center justify-between">
          <div className="segmented-control flex">
            <button
              className={`segmented-item ${scope === "all" ? "active text-gray-800" : "text-gray-400"}`}
              onClick={() => setScope("all")}
              disabled={loading}
            >
              全部
            </button>
            <button
              className={`segmented-item ${scope === "target" ? "active text-gray-800" : "text-gray-400"}`}
              onClick={() => setScope("target")}
              disabled={loading}
            >
              当前窗口
            </button>
          </div>
          <div className="flex items-center space-x-2">
            <button
              className="flex items-center space-x-2 rounded-xl bg-[#1F2937] px-4 py-2 text-[13px] font-medium text-white transition-all active:scale-95 disabled:opacity-50"
              onClick={runMaintenance}
              disabled={loading || maintenanceLoading}
            >
              <span>{maintenanceLoading ? "整理中..." : "离线整理"}</span>
            </button>
            <button
              className="rounded-xl border border-gray-100 bg-white p-2.5 text-gray-500 shadow-sm transition-colors active:bg-gray-50"
              onClick={reload}
              disabled={loading}
              title="刷新"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          </div>
        </div>

        <div className="flex space-x-8 border-b border-gray-50 px-1">
          <button
            className={`pb-2 text-[15px] font-bold transition-all ${tab === "summary" ? "tab-active" : "text-gray-300"}`}
            onClick={() => setTab("summary")}
          >
            窗口总结
          </button>
          <button
            className={`pb-2 text-[15px] font-bold transition-all ${tab === "dynamic" ? "tab-active" : "text-gray-300"}`}
            onClick={() => setTab("dynamic")}
          >
            动态记忆
          </button>
          <button
            className={`pb-2 text-[15px] font-bold transition-all ${tab === "core" ? "tab-active" : "text-gray-300"}`}
            onClick={() => setTab("core")}
          >
            核心缓存
          </button>
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

            <div className="space-y-3">
              <div className="flex items-center justify-between px-1">
                <h2 className="text-[11px] font-bold uppercase tracking-widest text-gray-400">maintenance</h2>
                <span className="text-[10px] text-gray-400">{String(maintenance?.timestamp || "(暂无)")}</span>
              </div>
              <div className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft">
                <div className="grid grid-cols-3 text-center">
                  <div>
                    <p className="text-[16px] font-bold text-gray-800">{String(maintenance?.backfilled_count ?? 0)}</p>
                    <p className="text-[10px] font-medium text-gray-400">Backfill</p>
                  </div>
                  <div>
                    <p className="text-[16px] font-bold text-gray-800">{String(maintenance?.pruned_count ?? 0)}</p>
                    <p className="text-[10px] font-medium text-gray-400">Pruned</p>
                  </div>
                  <div>
                    <p className="text-[16px] font-bold text-gray-800">{String(maintenance?.duplicate_candidate_count ?? 0)}</p>
                    <p className="text-[10px] font-medium text-gray-400">Duplicate</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between px-1">
                <div className="flex items-baseline space-x-2">
                  <h2 className="text-[11px] font-bold uppercase tracking-widest text-gray-400">自动召回</h2>
                  <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-500">
                    {String(data?.count ?? recalls.length)} / {String(data?.total_count ?? recalls.length)}
                  </span>
                </div>
              </div>
              {recalls.map((it, idx) => {
                const referencedIds = new Set(
                  (it.referenced_memory_ids || []).map((id) => String(id || "").trim()).filter(Boolean)
                );
                const recalledItems = Array.isArray(it.recalled_items) ? it.recalled_items : [];
                const scoreItems = Array.isArray(it.scores) ? it.scores : [];
                return (
                  <details key={`${String(it.timestamp || "")}-${idx}`} className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft">
                    <summary className="cursor-pointer list-none">
                      <div className="mb-2 flex items-start justify-between">
                        <div className="flex flex-wrap gap-1.5">
                          <span className="status-badge bg-gray-50 text-gray-400">source: {String(it.source || "recall")}</span>
                          {referencedIds.size ? <span className="status-badge bg-emerald-50 text-emerald-500">引用 {referencedIds.size}</span> : null}
                        </div>
                        <span className="text-[11px] text-gray-300">{String(it.timestamp || "")}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <h3 className="truncate pr-4 text-[15px] font-bold text-gray-800">{String(it.query || "") || "（空）"}</h3>
                        <svg className="h-4 w-4 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </div>
                    </summary>
                    <div className="mt-4 space-y-3 border-t border-gray-50 pt-4">
                      <div className="text-[12px] text-gray-500 break-words">retrieval_query: {String(it.retrieval_query || "(空)")}</div>
                      <div className="text-[12px] text-gray-500 break-words">
                        keywords: {Array.isArray(it.keywords) && it.keywords.length ? it.keywords.join(" / ") : "(空)"}
                      </div>
                      {it.assistant_preview ? (
                        <div className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-3 text-[12px] leading-relaxed text-emerald-700">
                          渡回复：{firstLinePreview(String(it.assistant_preview || ""), 88)}
                        </div>
                      ) : null}
                      {recalledItems.length > 0 ? (
                        <div className="space-y-2">
                          {recalledItems.map((m, mi) => {
                            const mid = memoryItemId(m);
                            const isReferenced = !!mid && referencedIds.has(mid);
                            return (
                              <div
                                key={`${mid || String(m.label || "")}-${mi}`}
                                className={`rounded-2xl p-4 transition ${
                                  isReferenced
                                    ? "border border-emerald-300 bg-emerald-50/80 shadow-[0_0_0_3px_rgba(16,185,129,.08)]"
                                    : "border border-transparent bg-gray-50"
                                }`}
                              >
                                <div className="mb-2 flex items-center justify-between gap-2">
                                  <div className="flex flex-wrap gap-1.5">
                                    {m.label ? <span className="status-badge bg-white text-gray-400">memory {m.label}</span> : null}
                                    <span className={`status-badge ${m.source === "core_cache" ? "bg-purple-50 text-purple-500" : "bg-blue-50 text-blue-500"}`}>
                                      {m.source === "core_cache" ? "core" : "dynamic"}
                                    </span>
                                    {isReferenced ? <span className="status-badge bg-emerald-500 text-white">已引用</span> : null}
                                  </div>
                                  <span className="truncate text-[10px] text-gray-300">{mid}</span>
                                </div>
                                <p className="text-[12px] leading-relaxed text-gray-600 break-words">{String(m.content || m.line || "(空)")}</p>
                                <div className="mt-3 flex flex-wrap gap-1.5 text-[10px] text-gray-400">
                                  {m.tag ? <span className="rounded bg-white px-2 py-1">{m.tag}</span> : null}
                                  <span className="rounded bg-white px-2 py-1">imp {String(m.importance ?? 0)}</span>
                                  <span className="rounded bg-white px-2 py-1">mention {String(m.mention_count ?? 0)}</span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : scoreItems.length > 0 ? (
                        <div className="space-y-2">
                          {scoreItems.map((s, si) => {
                            const mid = memoryItemId(s);
                            const isReferenced = !!mid && referencedIds.has(mid);
                            return (
                              <div
                                key={`${mid || String(si)}-${si}`}
                                className={`rounded-2xl p-4 transition ${
                                  isReferenced
                                    ? "border border-emerald-300 bg-emerald-50/80 shadow-[0_0_0_3px_rgba(16,185,129,.08)]"
                                    : "border border-transparent bg-gray-50"
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-[12px] font-bold text-gray-700">Result #{si + 1}</span>
                                    {isReferenced ? <span className="status-badge bg-emerald-500 text-white">已引用</span> : null}
                                  </div>
                                  <span className="text-[12px] font-bold text-blue-500">Score: {String(s.total ?? "-")}</span>
                                </div>
                                <p className="mt-2 text-[12px] leading-relaxed text-gray-500 break-words">{String(s.content || s.id || "(空)")}</p>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="py-2 text-center text-[12px] italic text-gray-400">暂无详细召回参数</p>
                      )}
                    </div>
                  </details>
                );
              })}
              {!recalls.length ? <div className="px-1 py-4 text-[12px] text-gray-300">（暂无召回记录）</div> : null}
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between px-1">
                <div className="flex items-baseline space-x-2">
                  <h2 className="text-[11px] font-bold uppercase tracking-widest text-gray-400">Search Memory</h2>
                  <span className="rounded bg-orange-50 px-1.5 py-0.5 text-[10px] font-bold text-orange-500">
                    {String(data?.search_count ?? searchEvents.length)} / {String(data?.search_total_count ?? searchEvents.length)}
                  </span>
                </div>
              </div>
              {searchEvents.map((it, idx) => (
                <details key={`${String(it.timestamp || "")}-search-${idx}`} className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft" open={idx === 0}>
                  <summary className="cursor-pointer list-none">
                    <div className="mb-3 flex items-start justify-between">
                      <div>
                        <span className="status-badge bg-orange-50 text-orange-500">{String(it.suspicion_level || "Info")}</span>
                        <h3 className="mt-2 text-[15px] font-bold text-gray-800">{String(it.query || "（空）")}</h3>
                      </div>
                      <span className="text-[11px] text-gray-300">{String(it.timestamp || "")}</span>
                    </div>
                  </summary>
                  <div className="rounded-2xl bg-gray-50 p-3">
                    <p className="text-[12px] leading-relaxed text-gray-500 break-words">
                      <strong className="text-gray-700">Reason:</strong> {String(it.reason || "(空)")}
                    </p>
                  </div>
                </details>
              ))}
              {!searchEvents.length ? <div className="px-1 py-4 text-[12px] text-gray-300">（暂无 search_memory 记录）</div> : null}
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="reminder-card rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft">
              <div className="mb-4 flex items-start justify-between">
                <div>
                  <h3 className="text-[14px] font-bold text-gray-800">核心缓存待审</h3>
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
                      title="删除核心缓存"
                      aria-label="删除核心缓存"
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
            {!coreItems.length ? <div className="px-1 py-10 text-center text-[12px] text-gray-300">（暂无核心缓存条目）</div> : null}
          </div>
        )}
      </div>
    </div>
  );
}
