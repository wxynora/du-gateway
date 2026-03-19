import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type ScheduleItem = {
  id?: string;
  title?: string;
  datetime?: string;
  repeat?: string;
  enabled?: boolean;
  note?: string;
};

type ScheduleResp = {
  ok?: boolean;
  items?: ScheduleItem[];
  count?: number;
  enabled_count?: number;
};

function normalizeItems(input: unknown): ScheduleItem[] {
  if (!Array.isArray(input)) return [];
  return input.filter((x): x is ScheduleItem => !!x && typeof x === "object");
}

function fmtDate(v: string): string {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v || "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function ScheduleTab() {
  const toast = useToast();
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<ScheduleResp>("/miniapp-api/schedule/items");
      setItems(normalizeItems(j?.items));
      setError("");
    } catch (e: any) {
      setError(e?.message || String(e));
      setItems([]);
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const enabledItems = useMemo(
    () => normalizeItems(items).filter((x) => x.enabled !== false).sort((a, b) => String(a.datetime || "").localeCompare(String(b.datetime || ""))),
    [items]
  );
  const disabledItems = useMemo(
    () => normalizeItems(items).filter((x) => x.enabled === false).sort((a, b) => String(b.datetime || "").localeCompare(String(a.datetime || ""))),
    [items]
  );

  async function disableItem(id: string) {
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/schedule/items/${encodeURIComponent(id)}/disable`, {
        method: "PUT",
      });
      if (!j?.ok) throw new Error(j?.error || "禁用失败");
      toast("已禁用，未来不再触发");
      await load();
    } catch (e: any) {
      toast(`操作失败：${e?.message || e}`);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <div className="text-xs text-cream-muted">日历/提醒（只读 + 禁用）</div>
        <button
          className="h-8 w-8 rounded-full bg-white/58 backdrop-blur-xl border border-white/50 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition disabled:opacity-50"
          onClick={load}
          disabled={loading}
          title="刷新"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M20 6v6h-6" />
            <path d="M20 12a8 8 0 1 1-2.34-5.66L20 8" />
          </svg>
        </button>
      </div>

      {error ? (
        <div className="rounded-xl2 bg-cream-pink/55 px-3 py-2 text-xs text-cream-text shadow-soft2">
          读取失败：{error}
        </div>
      ) : null}

      {!loading && !error && !enabledItems.length && !disabledItems.length ? (
        <div className="rounded-xl2 bg-white/46 border border-white/45 shadow-soft2 px-3 py-2 text-xs text-cream-muted">
          暂无日历/提醒数据（已做兜底，不会白屏）。
        </div>
      ) : null}

      <div className="rounded-xl3 bg-white/42 backdrop-blur-xl border border-white/50 shadow-soft p-3">
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          启用中 · {enabledItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {enabledItems.map((it) => (
            <div key={String(it.id || "")} className="rounded-xl2 bg-white/56 border border-white/50 shadow-soft2 p-3">
              <div className="text-sm font-medium text-cream-text">{it.title || "未命名提醒"}</div>
              <div className="mt-1 text-xs text-cream-muted">{fmtDate(String(it.datetime || ""))} · {it.repeat || "once"}</div>
              {it.note ? <div className="mt-1 text-xs text-cream-muted">{it.note}</div> : null}
              <div className="mt-2">
                <Btn kind="danger" onClick={() => disableItem(String(it.id || ""))} disabled={!it.id}>禁用未来触发</Btn>
              </div>
            </div>
          ))}
          {!enabledItems.length ? <div className="text-xs text-cream-muted">暂无启用中的提醒</div> : null}
        </div>
      </div>

      <div className="rounded-xl3 bg-white/34 backdrop-blur-xl border border-white/45 shadow-soft p-3">
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          已禁用 · {disabledItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {disabledItems.map((it) => (
            <div key={String(it.id || "")} className="rounded-xl2 bg-white/46 border border-white/45 shadow-soft2 p-3">
              <div className="text-sm text-cream-text">{it.title || "未命名提醒"}</div>
              <div className="mt-1 text-xs text-cream-muted">{fmtDate(String(it.datetime || ""))} · {it.repeat || "once"} · 已禁用</div>
            </div>
          ))}
          {!disabledItems.length ? <div className="text-xs text-cream-muted">暂无已禁用提醒</div> : null}
        </div>
      </div>
    </div>
  );
}

