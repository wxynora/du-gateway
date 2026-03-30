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
      <div className="rounded-xl3 bg-white border border-white/70 shadow-soft p-3 space-y-2 text-cream-text">
        <div className="flex items-center justify-between">
          <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
            当前窗口总结
          </div>
          <div className="flex items-center gap-2">
            <Btn kind={scope === "all" ? "dark" : "blue"} onClick={() => setScope("all")} disabled={loading}>全部</Btn>
            <Btn kind={scope === "target" ? "dark" : "blue"} onClick={() => setScope("target")} disabled={loading}>当前窗口</Btn>
            <Btn kind="dark" onClick={reload} disabled={loading}>
            刷新
            </Btn>
          </div>
        </div>
        <div className="text-xs text-[#5f5a52]">窗口：{data?.window_id || "(未识别)"}</div>
        <details className="rounded-xl2 bg-white border border-white/70 shadow-soft2 p-3">
          <summary className="cursor-pointer select-none text-xs text-[#5f5a52]">
            点击展开窗口总结：{firstLinePreview((data?.summary || "").trim() || "（当前暂无窗口总结）")}
          </summary>
          <div className="mt-2 text-sm text-cream-text whitespace-pre-wrap min-h-[64px]">
            {(data?.summary || "").trim() || "（当前暂无窗口总结）"}
          </div>
        </details>
      </div>

      <div className="rounded-xl3 bg-white border border-white/70 shadow-soft p-3 space-y-2 text-cream-text">
        <div className="text-xs text-[#5f5a52]">
          动态层状态：
          记忆 {String(data?.dynamic_stats?.memory_count ?? 0)} 条；
          索引标签 {(data?.dynamic_stats?.index_tags || []).length} 个；
          阈值 {String(data?.dynamic_stats?.vector_min_sim ?? "-")}
          （topK {String(data?.dynamic_stats?.vector_topk ?? "-")} / topN {String(data?.dynamic_stats?.vector_topn ?? "-")}）
        </div>
        <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">
          embedding: {String(data?.dynamic_stats?.embedding_backend || "-")} / {String(data?.dynamic_stats?.embedding_model || "-")}
        </div>
        <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">
          embed_timeout/retries: {String(data?.dynamic_stats?.embed_timeout_seconds ?? "-")}s / {String(data?.dynamic_stats?.embed_max_retries ?? "-")}
          {" "}({String(data?.dynamic_stats?.embed_retry_backoff_seconds ?? "-")}s backoff)
        </div>
        <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">
          memory_tags: {Array.isArray(data?.dynamic_stats?.memory_tags) ? data!.dynamic_stats!.memory_tags!.join(" / ") : ""}
        </div>
        <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">
          index_tags: {Array.isArray(data?.dynamic_stats?.index_tags) ? data!.dynamic_stats!.index_tags!.join(" / ") : ""}
        </div>
        <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">
          recent_vector_error: {String(data?.dynamic_stats?.recent_vector_error || "") || "(空)"}
        </div>
        <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">
          rebuild_failed_ids: {String(data?.dynamic_stats?.failed_ids_count ?? 0)}
          {Array.isArray(data?.dynamic_stats?.failed_ids_preview) && data!.dynamic_stats!.failed_ids_preview!.length
            ? ` ｜ ${data!.dynamic_stats!.failed_ids_preview!.join(" / ")}`
            : ""}
        </div>
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          动态记忆最近召回 · 最近 {String(data?.count ?? recalls.length)} 次 / 全部 {String(data?.total_count ?? recalls.length)}
        </div>
        <div className="space-y-2">
          {recalls.map((it, idx) => (
            <div key={`${String(it.timestamp || "")}-${idx}`} className="rounded-xl2 bg-white border border-white/70 shadow-soft2 p-3 space-y-1">
              <div className="text-xs text-[#5f5a52]">
                {String(it.timestamp || "")} · {String(it.source || "")} · 命中 {String(it.recalled_count ?? (it.recalled_lines || []).length)} 条
              </div>
              <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">query: {String(it.query || "") || "(空)"}</div>
              <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">keywords: {Array.isArray(it.keywords) ? it.keywords.join(" / ") : ""}</div>
              <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">reason: {String((it as any).reason || "")}</div>
              <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">vector_error: {String((it as any).vector_error || "")}</div>
              {Array.isArray(it.scores) && it.scores.length > 0 && (
                <div className="space-y-0.5">
                  {it.scores.map((s, si) => (
                    <div key={si} className="text-xs text-[#5f5a52] flex gap-2 items-baseline">
                      <span className="font-mono font-medium text-neutral-700">{String(s.total ?? "-")}</span>
                      <span className="text-[10px] text-neutral-400">
                        user {String(s.sem_user ?? "-")} · ctx {String(s.sem_ctx ?? "-")}
                      </span>
                      <span className="truncate">{s.content || s.id || ""}</span>
                    </div>
                  ))}
                </div>
              )}
              <details className="rounded-xl border border-white/70 bg-white/70 p-2">
                <summary className="cursor-pointer select-none text-xs text-[#5f5a52]">
                  点击展开召回全文：
                  {firstLinePreview(Array.isArray(it.recalled_lines) && it.recalled_lines.length ? it.recalled_lines.join("\n") : "（本次无内容）")}
                </summary>
                <div className="mt-2 text-sm text-cream-text whitespace-pre-wrap">
                  {Array.isArray(it.recalled_lines) && it.recalled_lines.length ? it.recalled_lines.join("\n") : "（本次无内容）"}
                </div>
              </details>
            </div>
          ))}
          {!recalls.length ? <div className="text-xs text-[#5f5a52]">（暂无召回记录）</div> : null}
        </div>
      </div>
    </div>
  );
}

