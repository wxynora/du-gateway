import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type ToolCallItem = { id?: string; name?: string; arguments?: string; result?: string };
type PromptCacheDebugEntry = {
  request?: Record<string, unknown>;
  usage?: Record<string, unknown>;
  response?: Record<string, unknown>;
};
type PromptCacheBreakdownItem = {
  label?: string;
  chars?: number;
  est_tokens?: number;
};
type OutputStats = {
  source?: string;
  output_tokens?: number;
  usage_output_tokens?: number;
  estimated_output_tokens?: number;
  visible_tokens_est?: number;
  thinking_tokens_est?: number;
  thinking_tokens_source?: string;
  thinking_ratio?: number;
  reasoning_omitted?: boolean;
};
type CostStats = {
  provider?: string;
  currency?: string;
  cache_ttl?: string;
  pricing_per_million?: Record<string, number>;
  input_tokens?: number;
  cache_creation_input_tokens?: number;
  cache_read_input_tokens?: number;
  output_tokens?: number;
  input_usd?: number;
  cache_creation_usd?: number;
  cache_read_usd?: number;
  output_usd?: number;
  total_usd?: number;
  usage_entries?: number;
  models?: string[];
};
type ReasoningItem = {
  window_id?: string;
  index?: number;
  timestamp?: string;
  reasoning?: string;
  cache_debug?: PromptCacheDebugEntry[];
  output_stats?: OutputStats;
  cost?: CostStats;
  tool_calls?: ToolCallItem[];
};
type ReasoningResp = { ok?: boolean; window_id?: string; window_ids?: string[]; items?: ReasoningItem[]; count?: number };
type TranslateResp = { ok?: boolean; translated?: string; error?: string };

function debugValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "未返回";
  return String(value);
}

function tokenValue(value: unknown) {
  const raw = debugValue(value);
  return raw === "未返回" ? raw : `≈${raw}`;
}

function tokenCountValue(value: unknown) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return "0";
  return String(Math.round(n));
}

function firstUsageValue(usage: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = usage[key];
    if (value !== null && value !== undefined && value !== "") return value;
  }
  return undefined;
}

function stringValue(value: unknown) {
  return value === null || value === undefined ? "" : String(value).trim();
}

function truthyDebugFlag(value: unknown) {
  return value === true || value === "true" || value === 1 || value === "1";
}

function tokenNumber(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function formatTokenNumber(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0";
  return Math.round(value).toLocaleString("en-US");
}

function formatUsd(value: unknown) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return "$0";
  return `$${n < 0.0001 ? n.toFixed(6) : n.toFixed(4)}`;
}

function promptCacheBreakdown(value: unknown): PromptCacheBreakdownItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((item) => ({
      label: String(item.label || "system"),
      chars: typeof item.chars === "number" ? item.chars : Number(item.chars || 0),
      est_tokens: typeof item.est_tokens === "number" ? item.est_tokens : Number(item.est_tokens || 0),
    }))
    .filter((item) => item.chars || item.est_tokens);
}

function outputStatsLine(stats?: OutputStats) {
  if (!stats || typeof stats !== "object") return "";
  const outputTokens = Number(stats.output_tokens || 0);
  const thinkingTokens = Number(stats.thinking_tokens_est || 0);
  if (!outputTokens && !thinkingTokens) return "";
  const outputPrefix = stats.source === "usage" ? "=" : "≈";
  if (stats.thinking_tokens_source === "usage_output_tokens_details") {
    return `output${outputPrefix}${tokenCountValue(outputTokens)}（thinking ${tokenCountValue(thinkingTokens)}）`;
  }
  if (stats.reasoning_omitted) {
    return `output${outputPrefix}${tokenCountValue(outputTokens)}（thinking 未返回）`;
  }
  return `output${outputPrefix}${tokenCountValue(outputTokens)}`;
}

function PromptCacheDebugCard({ entries, outputStats, cost }: { entries?: PromptCacheDebugEntry[]; outputStats?: OutputStats; cost?: CostStats }) {
  const items = Array.isArray(entries) ? entries.filter(Boolean).slice(-4) : [];
  if (!items.length) return null;
  const outputLine = outputStatsLine(outputStats);
  const costTotal = Number(cost?.total_usd || 0);
  const latestUsage = items[items.length - 1]?.usage || {};
  const totalInputTokens =
    tokenNumber(cost?.input_tokens) || tokenNumber(firstUsageValue(latestUsage, ["input_tokens", "prompt_tokens"]));
  const cacheReadTokens =
    tokenNumber(cost?.cache_read_input_tokens) ||
    tokenNumber(latestUsage.cache_read_input_tokens) ||
    tokenNumber(firstUsageValue(latestUsage, ["cached_tokens", "prompt_cached_tokens", "input_cached_tokens"]));
  const cacheCreateTokens = tokenNumber(cost?.cache_creation_input_tokens) || tokenNumber(latestUsage.cache_creation_input_tokens);
  const outputTokens =
    tokenNumber(cost?.output_tokens) ||
    tokenNumber(outputStats?.output_tokens) ||
    tokenNumber(outputStats?.usage_output_tokens) ||
    tokenNumber(outputStats?.estimated_output_tokens) ||
    tokenNumber(firstUsageValue(latestUsage, ["output_tokens", "completion_tokens"]));

  return (
    <details className="group mt-3 rounded-lg border border-[#f4c7d2] bg-[#fff4f7] px-3 py-2.5 text-[#7a2d45]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 [&::-webkit-details-marker]:hidden">
        <div className="min-w-0">
          <div className="mb-1 text-[11px] font-bold">Prompt Cache</div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] leading-4 text-[#8a4055]">
            <span>input={formatTokenNumber(totalInputTokens)}</span>
            <span>read={formatTokenNumber(cacheReadTokens)}</span>
            <span>create={formatTokenNumber(cacheCreateTokens)}</span>
            <span>output={formatTokenNumber(outputTokens)}</span>
            {costTotal > 0 ? <span>cost={formatUsd(costTotal)}</span> : null}
          </div>
        </div>
        <span className="shrink-0 text-[10px] text-[#a05a70]">
          <span className="group-open:hidden">展开</span>
          <span className="hidden group-open:inline">收起</span>
        </span>
      </summary>
      <div className="mt-2.5 space-y-2.5 border-t border-[#f6d7df] pt-2.5">
        {costTotal > 0 ? (
          <div className="rounded-md border border-[#f6d7df] bg-white/45 px-2 py-1.5 text-[10px] leading-4 text-[#8a4055]">
            <span className="font-semibold text-[#7a2d45]">Claude cost</span>
            <span> · {formatUsd(costTotal)}</span>
          </div>
        ) : null}
        {items.map((entry, idx) => {
          const req = entry?.request || {};
          const usage = entry?.usage || {};
          const resp = entry?.response || {};
          const openaiCached = firstUsageValue(usage, ["cached_tokens", "prompt_cached_tokens", "input_cached_tokens"]);
          const anthropicRead = usage.cache_read_input_tokens;
          const anthropicCreated = usage.cache_creation_input_tokens;
          const inputTokens = firstUsageValue(usage, ["input_tokens", "prompt_tokens"]);
          const thinkingTokens = firstUsageValue(usage, ["thinking_tokens"]);
          const fallbackCount = tokenNumber(usage.fallback_message_count);
          const fallbackModel = stringValue(usage.fallback_model);
          const iterations = Array.isArray(usage.iterations) ? usage.iterations.length : 0;
          const requestedModel = stringValue(resp.requested_model) || stringValue(req.model);
          const actualModel = stringValue(resp.actual_model);
          const modelRoute =
            requestedModel && actualModel && requestedModel !== actualModel
              ? `${requestedModel} -> ${actualModel}`
              : actualModel || requestedModel;
          const servedByFallback = truthyDebugFlag(resp.served_by_fallback) || fallbackCount > 0 || !!fallbackModel;
          const cacheKey = req.prompt_cache_key ? "已设置" : "未设置";
          const staticBreakdown = promptCacheBreakdown(req.static_breakdown);
          const dynamicBreakdown = promptCacheBreakdown(req.dynamic_breakdown);
          return (
            <div key={idx} className="space-y-1.5 text-[11px] leading-4">
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <span className="font-semibold">第{idx + 1}次</span>
                <span>openai_cached={debugValue(openaiCached)}</span>
                <span>anthropic_read={debugValue(anthropicRead)}</span>
                <span>anthropic_created={debugValue(anthropicCreated)}</span>
                <span>input={debugValue(inputTokens)}</span>
                {outputLine && idx === items.length - 1 ? <span>{outputLine}</span> : null}
                {thinkingTokens !== undefined ? <span>thinking_exact={debugValue(thinkingTokens)}</span> : null}
                {servedByFallback ? <span>fallback=是</span> : null}
                {iterations ? <span>attempts={iterations}</span> : null}
              </div>
              <div className="grid grid-cols-2 gap-x-2.5 gap-y-1 text-[#8a4055]">
                <span>static {tokenValue(req.static_prefix_est_tokens)}</span>
                <span>dynamic {tokenValue(req.dynamic_system_est_tokens)}</span>
              </div>
              {staticBreakdown.length ? (
                <div className="rounded-md border border-[#f6d7df] bg-white/45 px-2 py-1.5 text-[10px] leading-4 text-[#8a4055]">
                  <div className="mb-0.5 font-semibold text-[#7a2d45]">static breakdown</div>
                  <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
                    {staticBreakdown.map((part, partIdx) => (
                      <span key={`${part.label || "system"}-${partIdx}`} className="min-w-0 truncate">
                        {part.label || "system"} {tokenValue(part.est_tokens)}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              {dynamicBreakdown.length ? (
                <div className="rounded-md border border-[#f6d7df] bg-white/45 px-2 py-1.5 text-[10px] leading-4 text-[#8a4055]">
                  <div className="mb-0.5 font-semibold text-[#7a2d45]">dynamic breakdown</div>
                  <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
                    {dynamicBreakdown.map((part, partIdx) => (
                      <span key={`${part.label || "dynamic"}-${partIdx}`} className="min-w-0 truncate">
                        {part.label || "dynamic"} {tokenValue(part.est_tokens)}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="break-words text-[#9b5368]">
                model={debugValue(modelRoute)} · host={debugValue(req.upstream_host)} · prompt_cache_key={cacheKey}
                {fallbackModel ? ` · fallback_model=${fallbackModel}` : ""}
              </div>
              {usage.usage_returned === false ? (
                <div className="text-[#9b5368]">usage 未返回，需要看本地代理/上游是否透传。</div>
              ) : null}
            </div>
          );
        })}
      </div>
    </details>
  );
}

export function ReasoningTab() {
  const toast = useToast();
  const [items, setItems] = useState<ReasoningItem[]>([]);
  const [windowId, setWindowId] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState("");
  const [translating, setTranslating] = useState<Record<string, boolean>>({});
  const [translated, setTranslated] = useState<Record<string, string>>({});
  const [translationOpen, setTranslationOpen] = useState<Record<string, boolean>>({});

  function itemKey(r: ReasoningItem, i: number) {
    return `${r.window_id || ""}::${r.index || 0}::${i}`;
  }

  function formatTimelineTime(raw: string) {
    const input = String(raw || "").trim();
    if (!input) return "";
    const d = new Date(input);
    if (Number.isNaN(d.getTime())) return input;
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }

  async function loadLatest() {
    setLoading(true);
    try {
      // 带时间戳做强刷，避免命中缓存导致“按刷新没反应”。
      const j = await apiJson<ReasoningResp>(`/miniapp-api/reasoning/latest?limit=10&_ts=${Date.now()}`);
      setItems(j.items || []);
      setWindowId((j.window_id || "").toString());
      setLastRefreshedAt(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
      setLoadError("");
    } catch (e: any) {
      setLoadError(e?.message || String(e));
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  async function translateReasoning(key: string, text: string) {
    if (!String(text || "").trim()) {
      toast("这一条没有可翻译的思维链");
      return;
    }
    if (translated[key]) {
      setTranslationOpen((prev) => ({ ...prev, [key]: !prev[key] }));
      return;
    }
    setTranslating((prev) => ({ ...prev, [key]: true }));
    try {
      const j = await apiJson<TranslateResp>("/miniapp-api/reasoning/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const zh = String(j.translated || "").trim();
      setTranslated((prev) => ({ ...prev, [key]: zh }));
      setTranslationOpen((prev) => ({ ...prev, [key]: true }));
      toast("已翻译成中文");
    } catch (e: any) {
      toast(`翻译失败：${e?.message || e}`);
    } finally {
      setTranslating((prev) => ({ ...prev, [key]: false }));
    }
  }

  useEffect(() => {
    loadLatest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-full w-full max-w-full overflow-x-hidden bg-[#FDFDFD]">
      <style>{`
        .header-blur { background: rgba(255,255,255,.9); backdrop-filter: blur(8px); }
        .timeline-container { position: relative; }
        .timeline-container::before {
          content:"";
          position:absolute;
          left:9px;
          top:20px;
          bottom:0;
          width:2px;
          background: linear-gradient(180deg,#e5e7eb 0%, transparent 100%);
        }
        .timeline-item { position: relative; margin-left: 28px; margin-bottom: 20px; }
        .timeline-dot {
          position:absolute;
          left:-28px;
          top:7px;
          width:10px;
          height:10px;
          border-radius:50%;
          background:#374151;
          border:2px solid #fff;
          box-shadow:0 0 0 2px #e5e7eb;
        }
        .content-box {
          border-radius:18px;
          background:#fff;
          border:1px solid #f3f4f6;
          padding:14px;
        }
      `}</style>

      <button
        className="fixed right-4 z-[35] flex h-9 w-9 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100"
        style={{ top: "calc(env(safe-area-inset-top, 0px) + 10px)" }}
        onClick={loadLatest}
        disabled={loading}
        title="刷新"
      >
        <svg className={`h-5 w-5 ${loading ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M20 6v6h-6" />
          <path d="M20 12a8 8 0 1 1-2.34-5.66L20 8" />
        </svg>
      </button>

      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-gray-900">{items.length} 条记录</span>
          <span className="text-[13px] text-gray-400">·</span>
          <span className="text-[13px] text-gray-400">{windowId ? `窗口: ${windowId}` : "窗口: 全部"}</span>
        </div>
        <span className="text-[12px] font-medium text-gray-400">{lastRefreshedAt ? `${lastRefreshedAt} 刷新` : ""}</span>
      </div>

      {loadError ? (
        <div className="mx-6 mb-4 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-[12px] text-red-500">
          思维链加载失败：{loadError}
        </div>
      ) : null}

      <main className="w-full max-w-full overflow-x-hidden px-6 pb-8">
        <div className="mb-6 w-full max-w-full overflow-x-hidden">
          <div className="timeline-container">
        {items.map((r, i) => {
          const key = itemKey(r, i);
          const hasReasoning = Boolean(String(r.reasoning || "").trim());
          const hasCacheDebug = Array.isArray(r.cache_debug) && r.cache_debug.length > 0;
          const hasTranslated = Boolean(String(translated[key] || "").trim());
          const open = Boolean(translationOpen[key]);
          return (
          <div
            key={key}
            className="timeline-item"
          >
            <div className="timeline-dot" />
            <div className="mb-1 flex items-start justify-between">
              <div>
                <span className="text-[14px] font-bold text-gray-900">{String(r.window_id || "-")}</span>
                <span className="ml-2 font-mono text-[12px] text-gray-400">#{String(r.index ?? "")}</span>
              </div>
              <span className="text-[12px] font-medium text-gray-400">{formatTimelineTime(String(r.timestamp || ""))}</span>
            </div>
            <div className="content-box shadow-sm">
              {hasReasoning ? (
                <p className="mb-4 whitespace-pre-wrap break-words text-[13px] leading-relaxed text-gray-700">
                  {String(r.reasoning || "")}
                </p>
              ) : (
                <div className="mb-3 text-[12px] text-gray-400">本轮未返回思维链文本</div>
              )}

              {hasCacheDebug ? <PromptCacheDebugCard entries={r.cache_debug} outputStats={r.output_stats} cost={r.cost} /> : null}

              {Array.isArray(r.tool_calls) && r.tool_calls.length ? (
                <div className="space-y-3">
                  {r.tool_calls.map((tc, ti) => {
                    const nm = String(tc?.name || "").trim() || "unknown_tool";
                    const args = String(tc?.arguments || "").trim();
                    const result = String(tc?.result || "").trim();
                    return (
                      <div key={`${tc?.id || ""}-${ti}`} className="space-y-3">
                        <div>
                          <div className="mb-1 flex items-center gap-2">
                            <span className="text-[11px] font-bold uppercase text-amber-700">Call: {nm}</span>
                          </div>
                          <div className="rounded-lg border border-amber-100/50 bg-amber-50/50 p-3">
                            <code className="font-mono text-[12px] text-amber-900 break-all">{args || "(空参数)"}</code>
                          </div>
                        </div>

                        <div>
                          <div className="mb-1 flex items-center gap-2">
                            <span className="text-[11px] font-bold uppercase text-blue-700">Result</span>
                          </div>
                          <div className="rounded-lg border border-blue-100/50 bg-blue-50/50 p-3">
                            <code className="font-mono text-[12px] text-blue-900 break-all">{result || "（无返回内容）"}</code>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}

              {hasReasoning ? (
                <div className="mt-4 flex justify-end border-t border-gray-50 pt-3">
                  <button
                    className="flex items-center gap-1 text-[12px] font-bold text-blue-600"
                    onClick={() => translateReasoning(key, String(r.reasoning || ""))}
                    disabled={Boolean(translating[key])}
                  >
                    {translating[key] ? "翻译中..." : hasTranslated ? (open ? "收起译文" : "查看译文") : "翻译原文"}
                  </button>
                </div>
              ) : null}

              {hasTranslated && open ? (
                <div className="mt-3 rounded-lg border border-blue-100/50 bg-blue-50/50 p-3">
                  <div className="mb-1 text-[11px] font-bold uppercase text-blue-700">中文翻译</div>
                  <p className="whitespace-pre-wrap break-words text-[13px] leading-relaxed text-blue-900">{translated[key]}</p>
                </div>
              ) : null}
              </div>
          </div>
        )})}
        {!items.length && !loadError ? (
          <div className="rounded-2xl border border-gray-100 bg-white px-4 py-6 text-[12px] text-gray-400">
            暂无可展示的思维链（可能上游未返回 reasoning 字段）。
          </div>
        ) : null}
          </div>
        </div>
      </main>
      </div>
  );
}
