import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type DreamArchiveItem = {
  id: string;
  window_id?: string;
  sleep_session_key?: string;
  theme_id?: string;
  sleep_source?: string;
  channel?: string;
  target?: string;
  created_at?: string;
  sent_at?: string;
  preview?: string;
  content?: string;
  content_chars?: number;
  prompt?: string;
  fragments?: string[];
  meta?: Record<string, any>;
  r2_key?: string;
  updated_at?: string;
};

type DreamListResp = {
  ok?: boolean;
  items?: DreamArchiveItem[];
  count?: number;
};

type DreamDetailResp = {
  ok?: boolean;
  item?: DreamArchiveItem;
};

function formatTime(value?: string): string {
  const raw = String(value || "").trim();
  if (!raw) return "--:--";
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (match) return `${match[2]}.${match[3]} ${match[4]}:${match[5]}`;
  return raw.replace("+08:00", "").replace("T", " ").slice(5, 16) || raw;
}

function normalizeItems(input: unknown): DreamArchiveItem[] {
  if (!Array.isArray(input)) return [];
  return input
    .filter((item): item is DreamArchiveItem => !!item && typeof item === "object" && !!String((item as DreamArchiveItem).id || "").trim())
    .map((item) => ({ ...item, id: String(item.id || "").trim() }));
}

function InfoPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex max-w-full items-center rounded-full bg-white/70 px-2.5 py-1 text-[11px] font-medium text-[#766875] shadow-[0_1px_6px_rgba(66,47,70,0.05)]">
      {children}
    </span>
  );
}

export function DreamArchiveTab() {
  const toast = useToast();
  const [items, setItems] = useState<DreamArchiveItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<DreamArchiveItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const selectedSummary = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiJson<DreamListResp>("/miniapp-api/spring-dream-archives?limit=80");
      const next = normalizeItems(res.items);
      setItems(next);
      if (!selectedId && next[0]?.id) setSelectedId(next[0].id);
    } catch (e: any) {
      toast(`读取失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [selectedId, toast]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    let cancelled = false;
    const id = String(selectedId || "").trim();
    if (!id) {
      setSelected(null);
      return;
    }
    setDetailLoading(true);
    apiJson<DreamDetailResp>(`/miniapp-api/spring-dream-archives/${encodeURIComponent(id)}`)
      .then((res) => {
        if (cancelled) return;
        setSelected(res.item || null);
      })
      .catch((e: any) => {
        if (!cancelled) toast(`读取详情失败：${e?.message || e}`);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, toast]);

  const detail = selected || selectedSummary;
  const fragments = Array.isArray(detail?.fragments) ? detail.fragments.filter(Boolean) : [];

  return (
    <div className="min-h-full overflow-x-hidden bg-[#F8F3F7] px-3 pb-8 pt-4 text-[#30272f]">
      <div className="mx-auto flex w-full max-w-[760px] flex-col gap-3">
        <div className="flex items-center justify-between gap-3 px-1">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.28em] text-[#b48ca7]">Dreams</div>
            <div className="mt-1 text-[20px] font-semibold tracking-tight">梦境</div>
          </div>
          <button
            type="button"
            className="h-9 shrink-0 rounded-full bg-white/80 px-4 text-[12px] font-semibold text-[#5f4b5c] shadow-[0_4px_16px_rgba(75,55,77,0.08)] active:scale-[0.98]"
            onClick={() => void loadList()}
            disabled={loading}
          >
            {loading ? "刷新中" : "刷新"}
          </button>
        </div>

        <div className="grid min-h-0 gap-3 md:grid-cols-[minmax(220px,0.86fr)_1.14fr]">
          <section className="min-h-0 rounded-[24px] border border-white/70 bg-white/58 p-2 shadow-[0_12px_32px_rgba(72,47,78,0.08)]">
            <div className="max-h-[40dvh] overflow-y-auto pr-1 md:max-h-[calc(100dvh-150px)]">
              {items.map((item) => {
                const active = item.id === selectedId;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`mb-2 w-full rounded-[20px] px-3 py-3 text-left transition active:scale-[0.99] ${
                      active ? "bg-[#392c38] text-white shadow-[0_10px_22px_rgba(57,44,56,0.18)]" : "bg-white/72 text-[#4a3b48]"
                    }`}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <div className={`mb-1 flex items-center justify-between gap-2 text-[11px] ${active ? "text-white/68" : "text-[#a48c9e]"}`}>
                      <span>{formatTime(item.sent_at)}</span>
                      <span className="truncate">{item.theme_id || "dream"}</span>
                    </div>
                    <div className="line-clamp-3 text-[13px] leading-6">{item.preview || "没有预览"}</div>
                  </button>
                );
              })}
              {!items.length ? (
                <div className="px-4 py-10 text-center text-[13px] text-[#9b8796]">
                  {loading ? "正在读取" : "还没有梦境记录"}
                </div>
              ) : null}
            </div>
          </section>

          <section className="min-h-[56dvh] rounded-[28px] border border-white/75 bg-white/72 p-4 shadow-[0_16px_42px_rgba(72,47,78,0.09)]">
            {detail ? (
              <div className="flex h-full min-h-0 flex-col">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <InfoPill>{formatTime(detail.sent_at)}</InfoPill>
                  <InfoPill>{detail.theme_id || "dream"}</InfoPill>
                  {detail.channel ? <InfoPill>{detail.channel}</InfoPill> : null}
                  {detail.r2_key ? <InfoPill>R2</InfoPill> : null}
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto rounded-[22px] bg-[#fffafc] px-4 py-4 text-[14px] leading-7 text-[#3d313b] shadow-inner shadow-[#eadde7]/60">
                  {detailLoading && !selected?.content ? (
                    <div className="text-[13px] text-[#9b8796]">读取中</div>
                  ) : (
                    <div className="whitespace-pre-wrap break-words">{selected?.content || detail.preview || "没有正文"}</div>
                  )}
                </div>
                {fragments.length || selected?.prompt ? (
                  <details className="mt-3 rounded-[20px] bg-white/62 px-3 py-2 text-[12px] text-[#7b6878]">
                    <summary className="cursor-pointer select-none font-semibold text-[#6b5366]">梦境素材</summary>
                    {fragments.length ? (
                      <div className="mt-2 flex flex-col gap-1.5">
                        {fragments.map((fragment, index) => (
                          <div key={`${fragment}-${index}`} className="rounded-[14px] bg-[#f8f0f6] px-3 py-2 leading-5">
                            {fragment}
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {selected?.prompt ? (
                      <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-[14px] bg-[#f8f0f6] px-3 py-2 font-sans leading-5">
                        {selected.prompt}
                      </pre>
                    ) : null}
                  </details>
                ) : null}
              </div>
            ) : (
              <div className="flex h-full min-h-[48dvh] items-center justify-center text-[13px] text-[#9b8796]">
                {loading ? "正在读取" : "选一条梦境"}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
