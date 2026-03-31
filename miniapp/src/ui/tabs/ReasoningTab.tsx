import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type ToolCallItem = { id?: string; name?: string; arguments?: string; result?: string };
type ReasoningItem = {
  window_id?: string;
  index?: number;
  timestamp?: string;
  reasoning?: string;
  tool_calls?: ToolCallItem[];
};
type ReasoningResp = { ok?: boolean; window_id?: string; window_ids?: string[]; items?: ReasoningItem[]; count?: number };

export function ReasoningTab() {
  const toast = useToast();
  const [items, setItems] = useState<ReasoningItem[]>([]);
  const [windowId, setWindowId] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState("");

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

  useEffect(() => {
    loadLatest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <div className="text-xs text-cream-muted">
          最近 10 条 · 最新在上{windowId ? ` · ${windowId}` : ""}{lastRefreshedAt ? ` · 刷新于 ${lastRefreshedAt}` : ""}
        </div>
        <button
          className="neo-icon-btn h-8 w-8"
          onClick={loadLatest}
          disabled={loading}
          title="刷新"
        >
          <svg className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M20 6v6h-6" />
            <path d="M20 12a8 8 0 1 1-2.34-5.66L20 8" />
          </svg>
        </button>
      </div>

      {loadError ? (
        <div className="neo-muted-box bg-[linear-gradient(145deg,rgba(251,230,236,0.95),rgba(236,206,221,0.82))]">
          思维链加载失败：{loadError}
          <br />
          请稍后重试，或从 Telegram 按钮重新打开面板。
        </div>
      ) : null}

      <div className="space-y-2">
        {items.map((r, i) => (
          <div
            key={`${r.index || 0}-${i}`}
            className="neo-panel-soft p-3"
          >
            <div className="neo-tag-dark">
              #{String(r.index ?? "")} {r.timestamp ? `· ${String(r.timestamp)}` : ""} {r.window_id ? `· ${String(r.window_id)}` : ""}
            </div>
            {String(r.reasoning || "").trim() ? (
              <div className="mt-2 whitespace-pre-wrap font-mono text-xs leading-relaxed text-cream-text">
                {String(r.reasoning || "")}
              </div>
            ) : (
              <div className="mt-2 text-[11px] text-cream-muted">本轮未返回思维链文本</div>
            )}
            {Array.isArray(r.tool_calls) && r.tool_calls.length ? (
              <div className="mt-3 space-y-2">
                {r.tool_calls.map((tc, ti) => {
                  const nm = String(tc?.name || "").trim() || "unknown_tool";
                  const args = String(tc?.arguments || "").trim();
                  const result = String(tc?.result || "").trim();
                  return (
                    <div key={`${tc?.id || ""}-${ti}`} className="space-y-1.5">
                      <div className="rounded-[20px] border border-white/75 bg-[linear-gradient(145deg,rgba(255,250,240,0.95),rgba(247,234,193,0.62))] px-3 py-2 shadow-soft2">
                        <div className="text-[11px] text-[#8a6f35] font-medium">工具调用 · {nm}</div>
                        {args ? (
                          <div className="mt-1 whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-[#6f5b31]">
                            {args}
                          </div>
                        ) : null}
                      </div>
                      <div className="rounded-[20px] border border-white/75 bg-[linear-gradient(145deg,rgba(247,251,255,0.95),rgba(213,228,246,0.64))] px-3 py-2 shadow-soft2">
                        <div className="text-[11px] text-[#2f6eb4] font-medium">工具结果 · {nm}</div>
                        <div className="mt-1 whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-[#2a4c77]">
                          {result || "（无返回内容）"}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>
        ))}
        {!items.length && !loadError ? (
          <div className="neo-muted-box bg-[linear-gradient(145deg,rgba(255,247,250,0.92),rgba(240,229,235,0.72))]">
            暂无可展示的思维链（可能上游未返回 reasoning 字段）。
          </div>
        ) : null}
      </div>
    </div>
  );
}

