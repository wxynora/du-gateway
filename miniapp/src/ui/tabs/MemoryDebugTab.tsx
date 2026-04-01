import React, { useCallback, useEffect, useState } from "react";
import { apiJson } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type RecallScore = {
  id?: string;
  content?: string;
  total?: number;
  sem_user?: number;
  sem_ctx?: number;
};

type RecallEvent = {
  timestamp?: string;
  window_id?: string;
  query?: string;
  keywords?: string[];
  source?: string;
  recalled_lines?: string[];
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
  count?: number;
  total_count?: number;
  dynamic_stats?: {
    memory_count?: number;
    memory_tags?: string[];
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
  const [data, setData] = useState<MemoryDebugResp | null>(null);
  const [scope, setScope] = useState<"all" | "target">("all");

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

  return (
    <div className="space-y-3">
      <div className="neo-panel p-3 space-y-2 text-cream-text">
        <div className="flex items-center justify-between">
          <div className="neo-tag-blue">
            当前窗口总结
          </div>
          <div className="flex items-center gap-2">
            <Btn kind={scope === "all" ? "blue" : "default"} onClick={() => setScope("all")} disabled={loading}>全部</Btn>
            <Btn kind={scope === "target" ? "pink" : "default"} onClick={() => setScope("target")} disabled={loading}>当前窗口</Btn>
            <Btn kind="yellow" onClick={reload} disabled={loading}>
              刷新
            </Btn>
          </div>
        </div>
        <div className="text-xs text-cream-muted">窗口：{data?.window_id || "(未识别)"}</div>
        <details className="neo-panel-inset p-3">
          <summary className="cursor-pointer select-none text-xs text-cream-muted">
            点击展开窗口总结：{firstLinePreview((data?.summary || "").trim() || "（当前暂无窗口总结）")}
          </summary>
          <div className="mt-2 text-sm text-cream-text whitespace-pre-wrap min-h-[64px]">
            {(data?.summary || "").trim() || "（当前暂无窗口总结）"}
          </div>
        </details>
      </div>

      <div className="neo-panel p-3 space-y-2 text-cream-text">
        <div className="text-xs text-cream-muted">
          动态层状态：
          记忆 {String(data?.dynamic_stats?.memory_count ?? 0)} 条；
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
        <div className="neo-tag-pink">
          动态记忆最近召回 · 最近 {String(data?.count ?? recalls.length)} 次 / 全部 {String(data?.total_count ?? recalls.length)}
        </div>
        <div className="space-y-2">
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
      </div>
    </div>
  );
}

