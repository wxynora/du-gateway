import React, { useCallback, useEffect, useState } from "react";
import { apiJson } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type RecallScore = {
  id?: string;
  content?: string;
  retrieval_text?: string;
  total?: number;
  sem_user?: number;
  sem_ctx?: number;
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
  scores?: RecallScore[];
};

type MemoryDebugResp = {
  ok?: boolean;
  window_id?: string;
  scope?: "all" | "target" | string;
  summary?: string;
  summary_exists?: boolean;
  recalls?: RecallEvent[];
  search_memory_events?: RecallEvent[];
  count?: number;
  total_count?: number;
  search_count?: number;
  search_total_count?: number;
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

function recallBoxClass(tone: "blue" | "neutral" = "neutral") {
  if (tone === "blue") {
    return "rounded-[22px] bg-[#dfeaf6] shadow-[4px_4px_10px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.42)]";
  }
  return "rounded-[22px] bg-[#f5f7fa] shadow-[4px_4px_10px_rgba(173,182,196,0.2),-2px_-2px_5px_rgba(255,255,255,0.4)]";
}

export function MemoryDebugTab() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [data, setData] = useState<MemoryDebugResp | null>(null);
  const [scope, setScope] = useState<"all" | "target">("all");
  const [tab, setTab] = useState<"summary" | "dynamic">("summary");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const j = await apiJson<MemoryDebugResp>(`/miniapp-api/memory-debug?limit=10&scope=${scope}`);
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

  return (
    <div className="space-y-3">
      <div className="neo-panel p-3 space-y-2 text-cream-text">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Btn kind={scope === "all" ? "blue" : "default"} onClick={() => setScope("all")} disabled={loading}>全部</Btn>
            <Btn kind={scope === "target" ? "pink" : "default"} onClick={() => setScope("target")} disabled={loading}>当前窗口</Btn>
            <Btn kind="default" onClick={runMaintenance} disabled={loading || maintenanceLoading}>
              {maintenanceLoading ? "整理中" : "离线整理"}
            </Btn>
            <Btn kind="yellow" onClick={reload} disabled={loading}>
              刷新
            </Btn>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Btn kind={tab === "summary" ? "blue" : "default"} onClick={() => setTab("summary")} disabled={loading}>窗口总结</Btn>
          <Btn kind={tab === "dynamic" ? "pink" : "default"} onClick={() => setTab("dynamic")} disabled={loading}>动态记忆</Btn>
        </div>
      </div>

      {tab === "summary" ? (
        <div className="neo-panel p-3 space-y-2 text-cream-text">
          <details className="neo-panel-inset p-3" open>
            <summary className="cursor-pointer select-none text-xs text-cream-muted">
              窗口总结：{firstLinePreview((data?.summary || "").trim() || "（当前暂无窗口总结）")}
            </summary>
            <div className="mt-2 text-sm text-cream-text whitespace-pre-wrap min-h-[64px]">
              {(data?.summary || "").trim() || "（当前暂无窗口总结）"}
            </div>
          </details>
        </div>
      ) : (
        <div className="neo-panel p-3 space-y-2 text-cream-text">
          <div className="text-xs text-cream-muted">
            动态层状态：
            记忆 {String(data?.dynamic_stats?.memory_count ?? 0)} 条；
            标签完整 {String(data?.dynamic_stats?.label_complete_count ?? 0)} 条；
            缺失 {String(data?.dynamic_stats?.label_missing_count ?? 0)} 条；
            索引标签 {(data?.dynamic_stats?.index_tags || []).length} 个；
            阈值 {String(data?.dynamic_stats?.vector_min_sim ?? "-")}
            （topK {String(data?.dynamic_stats?.vector_topk ?? "-")} / topN {String(data?.dynamic_stats?.vector_topn ?? "-")}）
          </div>
          <div className="text-xs text-cream-muted whitespace-pre-wrap">
            embedding: {String(data?.dynamic_stats?.embedding_backend || "-")} / {String(data?.dynamic_stats?.embedding_model || "-")}
          </div>
          <div className="text-xs text-cream-muted whitespace-pre-wrap">
            embed_timeout/retries: {String(data?.dynamic_stats?.embed_timeout_seconds ?? "-")}s / {String(data?.dynamic_stats?.embed_max_retries ?? "-")}
            {" "}({String(data?.dynamic_stats?.embed_retry_backoff_seconds ?? "-")}s backoff)
          </div>
          <div className="text-xs text-cream-muted whitespace-pre-wrap">
            memory_tags: {Array.isArray(data?.dynamic_stats?.memory_tags) ? data!.dynamic_stats!.memory_tags!.join(" / ") : ""}
          </div>
          <div className="text-xs text-cream-muted whitespace-pre-wrap">
            index_tags: {Array.isArray(data?.dynamic_stats?.index_tags) ? data!.dynamic_stats!.index_tags!.join(" / ") : ""}
          </div>
          <div className="text-xs text-cream-muted whitespace-pre-wrap">
            recent_vector_error: {String(data?.dynamic_stats?.recent_vector_error || "") || "(空)"}
          </div>
          <div className="text-xs text-cream-muted whitespace-pre-wrap">
            rebuild_failed_ids: {String(data?.dynamic_stats?.failed_ids_count ?? 0)}
            {Array.isArray(data?.dynamic_stats?.failed_ids_preview) && data!.dynamic_stats!.failed_ids_preview!.length
              ? ` ｜ ${data!.dynamic_stats!.failed_ids_preview!.join(" / ")}`
              : ""}
          </div>
          <div className="text-xs text-cream-muted whitespace-pre-wrap">
            maintenance: {String(maintenance?.timestamp || "") || "(暂无)"} ｜ backfill {String(maintenance?.backfilled_count ?? 0)} ｜ prune {String(maintenance?.pruned_count ?? 0)} ｜ dup {String(maintenance?.duplicate_candidate_count ?? 0)}
          </div>
          {Array.isArray(maintenance?.duplicate_candidates) && maintenance!.duplicate_candidates!.length > 0 && (
            <details className="neo-panel-inset p-3">
              <summary className="cursor-pointer select-none text-xs text-cream-muted">
                最近慢整理候选：{maintenance!.duplicate_candidates!.length} 组
              </summary>
              <div className="mt-2 space-y-2">
                {maintenance!.duplicate_candidates!.map((it, idx) => (
                  <div key={idx} className="text-xs text-cream-muted break-words">
                    [{String(it.tag || "-")}] {String(it.retrieval_text || "(空)")} · {String(it.count || 0)} 条
                  </div>
                ))}
              </div>
            </details>
          )}

          <details className="neo-panel-inset p-3" open>
            <summary className="cursor-pointer select-none text-xs text-cream-muted">
              自动召回 · 最近 {String(data?.count ?? recalls.length)} 次 / 全部 {String(data?.total_count ?? recalls.length)}
            </summary>
            <div className="mt-3 space-y-2">
              {recalls.map((it, idx) => (
                <details key={`${String(it.timestamp || "")}-${idx}`} className="neo-panel-soft p-3 shadow-[5px_5px_11px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.38)]">
                  <summary className="cursor-pointer select-none list-none">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="neo-tag-dark px-2.5 py-1 text-[10px]">
                        {String(it.source || "recall")}
                      </span>
                      <span className="text-[11px] text-cream-muted">{String(it.timestamp || "")}</span>
                    </div>
                    <div className="mt-2 text-sm text-cream-text break-words">
                      {String(it.query || "") || "（空）"}
                    </div>
                  </summary>
                  <div className="mt-3 space-y-2.5">
                    <div className="text-xs text-cream-muted break-words">
                      retrieval_query: {String(it.retrieval_query || "") || "(空)"}
                    </div>
                    <div className="text-xs text-cream-muted break-words">
                      keywords: {Array.isArray(it.keywords) && it.keywords.length ? it.keywords.join(" / ") : "(空)"}
                    </div>
                    {Array.isArray(it.keyword_debug) && it.keyword_debug.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {it.keyword_debug.map((kw, ki) => (
                          <span
                            key={`${String(kw.text || "")}-${ki}`}
                            className={kw.is_phrase ? "neo-tag-pink px-2 py-1 text-[10px]" : "neo-tag-blue px-2 py-1 text-[10px]"}
                            title={kw.is_phrase ? "收敛短语" : "散词回退"}
                          >
                            {kw.is_phrase ? "phrase" : "raw"} · {String(kw.text || "")}
                          </span>
                        ))}
                      </div>
                    )}
                    {Array.isArray(it.scores) && it.scores.length > 0 && (
                      <details className={`${recallBoxClass("blue")} p-2.5`}>
                        <summary className="cursor-pointer select-none text-[10px] font-medium uppercase tracking-[0.14em] text-cream-muted">
                          召回条目 · {it.scores.length} 条
                        </summary>
                        <div className="mt-2 space-y-2">
                          {it.scores.map((s, si) => (
                            <div key={si} className={`${recallBoxClass("neutral")} p-2.5`}>
                              <div className="flex items-center justify-between gap-3">
                                <div className="font-mono text-sm font-semibold text-cream-text">{String(s.total ?? "-")}</div>
                                <div className="text-[11px] text-cream-muted">
                                  user {String(s.sem_user ?? "-")} · ctx {String(s.sem_ctx ?? "-")}
                                </div>
                              </div>
                              <div className="mt-1 text-xs text-cream-muted break-words">
                                {s.retrieval_text ? `检索短语：${s.retrieval_text}` : ""}
                              </div>
                              <div className="mt-1 text-sm text-cream-text break-words">
                                {s.content || s.id || "(空)"}
                              </div>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                </details>
              ))}
              {!recalls.length ? <div className="text-xs text-cream-muted">（暂无召回记录）</div> : null}
            </div>
          </details>

          <details className="neo-panel-inset p-3">
            <summary className="cursor-pointer select-none text-xs text-cream-muted">
              search_memory · 最近 {String(data?.search_count ?? searchEvents.length)} 次 / 全部 {String(data?.search_total_count ?? searchEvents.length)}
            </summary>
            <div className="mt-3 space-y-2">
              {searchEvents.map((it, idx) => (
                <details key={`${String(it.timestamp || "")}-search-${idx}`} className="neo-panel-soft p-3 shadow-[5px_5px_11px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.38)]">
                  <summary className="cursor-pointer select-none list-none">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="neo-tag-dark px-2.5 py-1 text-[10px]">search_memory</span>
                      <span className="text-[11px] text-cream-muted">{String(it.timestamp || "")}</span>
                    </div>
                    <div className="mt-2 text-sm text-cream-text break-words">
                      {String(it.query || "") || "（空）"}
                    </div>
                  </summary>
                  <div className="mt-3 space-y-2.5">
                    <div className="text-xs text-cream-muted break-words">
                      scene_type: {String(it.scene_type || "") || "(空)"} ｜ target_type: {String(it.target_type || "") || "(空)"}
                    </div>
                    <div className="text-xs text-cream-muted break-words">
                      time_range: {String(it.time_range || "") || "(空)"} ｜ suspicion_level: {String(it.suspicion_level || "") || "(空)"}
                    </div>
                    <div className="text-xs text-cream-muted break-words">
                      reason: {String(it.reason || "") || "(空)"}
                    </div>
                    {Array.isArray(it.recalled_lines) && it.recalled_lines.length > 0 && (
                      <details className={`${recallBoxClass("blue")} p-2.5`}>
                        <summary className="cursor-pointer select-none text-[10px] font-medium uppercase tracking-[0.14em] text-cream-muted">
                          命中结果 · {it.recalled_lines.length} 条
                        </summary>
                        <div className="mt-2 space-y-2">
                          {it.recalled_lines.map((row, ri) => {
                            if (typeof row === "string") {
                              return (
                                <div key={ri} className={`${recallBoxClass("neutral")} p-2.5 text-sm text-cream-text break-words`}>
                                  {row}
                                </div>
                              );
                            }
                            return (
                              <div key={ri} className={`${recallBoxClass("neutral")} p-2.5`}>
                                <div className="flex items-center justify-between gap-3">
                                  <div className="font-mono text-sm font-semibold text-cream-text">{String(row.final_score ?? "-")}</div>
                                  <div className="text-[11px] text-cream-muted">
                                    semantic {String(row.semantic_score ?? "-")}
                                  </div>
                                </div>
                                <div className="mt-1 text-xs text-cream-muted break-words">
                                  {String(row.emotion_label || "") || "(空)"} ｜ {String(row.scene_type || "") || "(空)"} ｜ {String(row.target_type || "") || "(空)"}
                                </div>
                                <div className="mt-1 text-sm text-cream-text break-words">
                                  {String(row.content || row.id || "(空)")}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </details>
                    )}
                  </div>
                </details>
              ))}
              {!searchEvents.length ? <div className="text-xs text-cream-muted">（暂无 search_memory 记录）</div> : null}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

