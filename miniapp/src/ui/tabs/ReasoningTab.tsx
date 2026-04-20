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
type TranslateResp = { ok?: boolean; translated?: string; error?: string };

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
    <div className="min-h-full bg-[#FDFDFD]">
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

      <header className="header-blur sticky top-0 z-50 flex items-center justify-between border-b border-gray-100 px-5 py-3">
        <div className="flex items-center gap-3">
          <h1 className="text-[18px] font-bold tracking-tight text-gray-900">思维链日志</h1>
        </div>
        <button
          className="flex h-9 w-9 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100"
          onClick={loadLatest}
          disabled={loading}
          title="刷新"
        >
          <svg className={`h-5 w-5 ${loading ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 6v6h-6" />
            <path d="M20 12a8 8 0 1 1-2.34-5.66L20 8" />
          </svg>
        </button>
      </header>

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

      <main className="px-6 pb-8">
        <div className="mb-6">
          <h2 className="mb-6 text-[12px] font-bold uppercase tracking-widest text-gray-400">最近记录</h2>
          <div className="timeline-container">
        {items.map((r, i) => {
          const key = itemKey(r, i);
          const hasReasoning = Boolean(String(r.reasoning || "").trim());
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
                <span className="text-[14px] font-bold text-gray-900">窗口 {String(r.window_id || "-")}</span>
                <span className="ml-2 font-mono text-[12px] text-gray-400">#{String(r.index ?? "")}</span>
              </div>
              <span className="text-[12px] font-medium text-gray-400">{String(r.timestamp || "")}</span>
            </div>
            <div className="content-box shadow-sm">
              {String(r.reasoning || "").trim() ? (
              <p className="mb-4 whitespace-pre-wrap text-[15px] leading-relaxed text-gray-700">
                {String(r.reasoning || "")}
              </p>
              ) : (
                <div className="mb-3 text-[12px] text-gray-400">本轮未返回思维链文本</div>
              )}

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
                  <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-blue-900">{translated[key]}</p>
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

