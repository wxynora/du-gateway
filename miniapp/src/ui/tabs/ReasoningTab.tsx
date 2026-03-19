import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type ReasoningItem = { index?: number; timestamp?: string; reasoning?: string };
type ReasoningResp = { ok?: boolean; window_id?: string; items?: ReasoningItem[]; count?: number };

export function ReasoningTab() {
  const toast = useToast();
  const [items, setItems] = useState<ReasoningItem[]>([]);
  const [windowId, setWindowId] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadLatest() {
    setLoading(true);
    try {
      const j = await apiJson<ReasoningResp>("/miniapp-api/reasoning/latest?limit=10");
      setItems(j.items || []);
      setWindowId((j.window_id || "").toString());
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
    <div className="space-y-3">
      {loadError ? (
        <div className="rounded-xl2 bg-cream-pink/65 px-3 py-2 text-xs text-cream-text shadow-soft2">
          思维链加载失败：{loadError}
          <br />
          请稍后重试，或从 Telegram 按钮重新打开面板。
        </div>
      ) : null}

      <div className="rounded-xl3 bg-white/42 backdrop-blur-xl border border-white/50 shadow-soft p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-xs text-cream-muted">
            最近 10 条思维链（最新在上）{windowId ? ` · ${windowId}` : ""}
          </div>
          <Btn kind="blue" onClick={loadLatest} disabled={loading}>刷新</Btn>
        </div>
        <div className="space-y-2">
          {items.map((r, i) => (
            <details key={`${r.index || 0}-${i}`} className="rounded-xl2 bg-white/56 border border-white/50 shadow-soft2 p-2" open={i === 0}>
              <summary className="cursor-pointer select-none text-xs text-cream-muted">
                #{String(r.index ?? "")} {r.timestamp ? `· ${String(r.timestamp)}` : ""}
              </summary>
              <div className="mt-2 whitespace-pre-wrap font-mono text-xs text-cream-text">
                {String(r.reasoning || "")}
              </div>
            </details>
          ))}
          {!items.length && !loadError ? (
            <div className="rounded-xl2 bg-cream-pink/55 px-3 py-2 text-xs text-cream-text shadow-soft2">
              暂无可展示的思维链（可能上游未返回 reasoning 字段）。
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

