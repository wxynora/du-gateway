import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type RecallEvent = {
  timestamp?: string;
  window_id?: string;
  query?: string;
  keywords?: string[];
  source?: string;
  recalled_lines?: string[];
  recalled_count?: number;
};

type MemoryDebugResp = {
  ok?: boolean;
  window_id?: string;
  summary?: string;
  summary_exists?: boolean;
  recalls?: RecallEvent[];
  count?: number;
  error?: string;
};

export function MemoryDebugTab() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<MemoryDebugResp | null>(null);

  async function reload() {
    setLoading(true);
    try {
      const j = await apiJson<MemoryDebugResp>("/miniapp-api/memory-debug?limit=30");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setData(j);
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const recalls = Array.isArray(data?.recalls) ? data!.recalls! : [];

  return (
    <div className="space-y-3">
      <div className="rounded-xl3 bg-white border border-white/70 shadow-soft p-3 space-y-2 text-cream-text">
        <div className="flex items-center justify-between">
          <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
            当前窗口总结
          </div>
          <Btn kind="dark" onClick={reload} disabled={loading}>
            刷新
          </Btn>
        </div>
        <div className="text-xs text-[#5f5a52]">窗口：{data?.window_id || "(未识别)"}</div>
        <div className="rounded-xl2 bg-white border border-white/70 shadow-soft2 p-3 text-sm text-cream-text whitespace-pre-wrap min-h-[64px]">
          {(data?.summary || "").trim() || "（当前暂无窗口总结）"}
        </div>
      </div>

      <div className="rounded-xl3 bg-white border border-white/70 shadow-soft p-3 space-y-2 text-cream-text">
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          动态记忆最近召回 · {String(data?.count ?? recalls.length)}
        </div>
        <div className="space-y-2">
          {recalls.map((it, idx) => (
            <div key={`${String(it.timestamp || "")}-${idx}`} className="rounded-xl2 bg-white border border-white/70 shadow-soft2 p-3 space-y-1">
              <div className="text-xs text-[#5f5a52]">
                {String(it.timestamp || "")} · {String(it.source || "")} · 命中 {String(it.recalled_count ?? (it.recalled_lines || []).length)} 条
              </div>
              <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">query: {String(it.query || "") || "(空)"}</div>
              <div className="text-xs text-[#5f5a52] whitespace-pre-wrap">keywords: {Array.isArray(it.keywords) ? it.keywords.join(" / ") : ""}</div>
              <div className="text-sm text-cream-text whitespace-pre-wrap">{Array.isArray(it.recalled_lines) && it.recalled_lines.length ? it.recalled_lines.join("\n") : "（本次无内容）"}</div>
            </div>
          ))}
          {!recalls.length ? <div className="text-xs text-[#5f5a52]">（暂无召回记录）</div> : null}
        </div>
      </div>
    </div>
  );
}

