import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type StayWithDuView = "timeline" | "cinema" | "library";
type StayWithDuEntryType = "node" | "movie" | "book";
type StayTimelineNode = {
  id: string;
  date: string;
  title: string;
  desc: string;
};
type StayMediaItem = {
  id: string;
  title: string;
  note: string;
  date?: string;
};
type StayWithDuData = {
  timeline: StayTimelineNode[];
  moviesTodo: StayMediaItem[];
  moviesDone: StayMediaItem[];
  booksTodo: StayMediaItem[];
  booksDone: StayMediaItem[];
};
type StayWithDuCollection = keyof StayWithDuData;
const STAY_SERIF_FONT = "'Playfair Display', 'Noto Serif SC', 'Songti SC', Georgia, serif";
const STAY_SANS_FONT = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

function emptyStayWithDuData(): StayWithDuData {
  return {
    timeline: [],
    moviesTodo: [],
    moviesDone: [],
    booksTodo: [],
    booksDone: [],
  };
}

function sanitizeStayTimeline(raw: any): StayTimelineNode[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => ({
      id: String(item?.id || `node_${Date.now()}`),
      date: String(item?.date || ""),
      title: String(item?.title || "").trim(),
      desc: String(item?.desc || "").trim(),
    }))
    .filter((item) => item.title);
}

function sanitizeStayMedia(raw: any): StayMediaItem[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => ({
      id: String(item?.id || `item_${Date.now()}`),
      title: String(item?.title || "").trim(),
      note: String(item?.note || "").trim(),
      date: item?.date ? String(item.date) : undefined,
    }))
    .filter((item) => item.title);
}

function normalizeStayWithDuData(raw: any): StayWithDuData {
  return {
    timeline: sanitizeStayTimeline(raw?.timeline),
    moviesTodo: sanitizeStayMedia(raw?.moviesTodo),
    moviesDone: sanitizeStayMedia(raw?.moviesDone),
    booksTodo: sanitizeStayMedia(raw?.booksTodo),
    booksDone: sanitizeStayMedia(raw?.booksDone),
  };
}

function formatStayDate(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function makeStayItemId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function StayWithDuScreen() {
  const toast = useToast();
  const [activeView, setActiveView] = useState<StayWithDuView>("timeline");
  const [data, setData] = useState<StayWithDuData>(() => emptyStayWithDuData());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);
  const [entryType, setEntryType] = useState<StayWithDuEntryType>("node");
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [date, setDate] = useState(() => formatStayDate());

  const load = useCallback(async (showSpinner = false) => {
    if (saving) return;
    if (showSpinner) setLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; data?: StayWithDuData; error?: string }>("/miniapp-api/stay-with-du");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setData(normalizeStayWithDuData(j.data));
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [saving, toast]);

  useEffect(() => {
    void load(true);
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => void load(false), 5000);
    const onVisible = () => {
      if (document.visibilityState === "visible") void load(false);
    };
    const onFocus = () => void load(false);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  const timeline = useMemo(
    () => [...data.timeline].sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))),
    [data.timeline],
  );

  const resetForm = (nextType: StayWithDuEntryType = entryType) => {
    setEntryType(nextType);
    setTitle("");
    setDesc("");
    setDate(formatStayDate());
  };

  const openAddSheet = (nextType?: StayWithDuEntryType) => {
    resetForm(nextType || (activeView === "cinema" ? "movie" : activeView === "library" ? "book" : "node"));
    setAdding(true);
  };

  const entryTypeOptions: Array<{ id: StayWithDuEntryType; label: string }> = [
    { id: "node", label: "Important node" },
    { id: "movie", label: "Movie" },
    { id: "book", label: "Book" },
  ];

  async function saveData(next: StayWithDuData, successText?: string) {
    const prev = data;
    setData(next);
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; data?: StayWithDuData; error?: string }>("/miniapp-api/stay-with-du", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: next }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      setData(normalizeStayWithDuData(j.data || next));
      if (successText) toast(successText);
      return true;
    } catch (e: any) {
      setData(prev);
      toast(`保存失败：${e?.message || e}`);
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function addEntry() {
    const cleanTitle = title.trim();
    if (!cleanTitle || saving) return;
    const cleanDesc = desc.trim();
    const cleanDate = date.trim() || formatStayDate();
    let next: StayWithDuData;
    if (entryType === "movie") {
      next = {
        ...data,
        moviesTodo: [{ id: makeStayItemId("movie"), title: cleanTitle, note: cleanDesc }, ...data.moviesTodo],
      };
    } else if (entryType === "book") {
      next = {
        ...data,
        booksTodo: [{ id: makeStayItemId("book"), title: cleanTitle, note: cleanDesc }, ...data.booksTodo],
      };
    } else {
      next = {
        ...data,
        timeline: [
          { id: makeStayItemId("node"), date: cleanDate, title: cleanTitle, desc: cleanDesc },
          ...data.timeline,
        ],
      };
    }
    const ok = await saveData(next, "已保存");
    if (!ok) return;
    setAdding(false);
    resetForm(entryType);
  }

  async function completeMovie(id: string) {
    if (saving) return;
    const item = data.moviesTodo.find((it) => it.id === id);
    if (!item) return;
    await saveData(
      {
        ...data,
        moviesTodo: data.moviesTodo.filter((it) => it.id !== id),
        moviesDone: [{ ...item, date: formatStayDate() }, ...data.moviesDone],
      },
      "已移到一起看过",
    );
  }

  async function completeBook(id: string) {
    if (saving) return;
    const item = data.booksTodo.find((it) => it.id === id);
    if (!item) return;
    await saveData(
      {
        ...data,
        booksTodo: data.booksTodo.filter((it) => it.id !== id),
        booksDone: [{ ...item, date: formatStayDate() }, ...data.booksDone],
      },
      "已移到一起读过",
    );
  }

  async function deleteStayItem(section: StayWithDuCollection, id: string) {
    if (saving || !id) return;
    await saveData(
      {
        ...data,
        [section]: data[section].filter((item) => item.id !== id),
      } as StayWithDuData,
      "已删除",
    );
  }

  return (
    <div className="-mx-3.5 min-h-full bg-[#FBF8F6] px-5 pb-[126px] pt-5 text-[#3D2B29]" style={{ fontFamily: STAY_SANS_FONT }}>
      <div className="mx-auto max-w-xl">
        <div className="mb-7 flex items-end justify-between gap-4">
          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#C87D60]">stay with du</div>
            <h2 className="text-[30px] font-normal leading-none" style={{ fontFamily: STAY_SERIF_FONT }}>
              our little archive
            </h2>
          </div>
          <div className="rounded-full border border-[#E8D8D0] bg-white/[0.55] px-3 py-1.5 text-[12px] font-medium text-[#8B6F68]">
            {timeline.length} nodes
          </div>
        </div>

        {loading ? <StayEmptyState text="加载中..." /> : null}

        {activeView === "timeline" ? (
          <div className="relative pl-8">
            <div className="absolute bottom-2 left-[11px] top-2 w-px bg-[#E6D2CA]" />
            {timeline.length ? (
              <div className="space-y-7">
                {timeline.map((item) => (
                  <div key={item.id} className="relative pr-10">
                    <div className="absolute -left-[31px] top-1.5 h-[16px] w-[16px] rounded-full border-[3px] border-[#FBF8F6] bg-[#C87D60] shadow-[0_0_0_1px_rgba(200,125,96,0.22)]" />
                    <div className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#C87D60]">{item.date || "Today"}</div>
                    <div className="mt-1 text-[22px] font-normal leading-7 text-[#3D2B29]" style={{ fontFamily: STAY_SERIF_FONT }}>{item.title}</div>
                    {item.desc ? <div className="mt-2 text-[14px] leading-6 text-[#7A625D]">{item.desc}</div> : null}
                    <button
                      type="button"
                      className="absolute right-0 top-0 flex h-8 w-8 items-center justify-center rounded-full text-[#A68B84] transition-colors active:bg-[#EDE1DC] disabled:opacity-40"
                      onClick={() => void deleteStayItem("timeline", item.id)}
                      disabled={saving}
                      aria-label="删除时间线节点"
                      title="删除"
                    >
                      <TrashIconMini />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <StayEmptyState text="重要节点会放在这里。" />
            )}
          </div>
        ) : null}

        {activeView === "cinema" ? (
          <div className="space-y-8">
            <StayMediaSection
              title="Want to watch"
              items={data.moviesTodo}
              emptyText="想看的电影先空着。"
              onComplete={completeMovie}
              onDelete={(id) => void deleteStayItem("moviesTodo", id)}
              disabled={saving}
            />
            <StayMediaSection
              title="Watched together"
              items={data.moviesDone}
              emptyText="一起看过的电影会出现在这里。"
              onDelete={(id) => void deleteStayItem("moviesDone", id)}
              disabled={saving}
              done
            />
          </div>
        ) : null}

        {activeView === "library" ? (
          <div className="space-y-8">
            <StayMediaSection
              title="Want to read"
              items={data.booksTodo}
              emptyText="想一起读的书先空着。"
              onComplete={completeBook}
              onDelete={(id) => void deleteStayItem("booksTodo", id)}
              disabled={saving}
            />
            <StayMediaSection
              title="Read together"
              items={data.booksDone}
              emptyText="一起读完的书会出现在这里。"
              onDelete={(id) => void deleteStayItem("booksDone", id)}
              disabled={saving}
              done
            />
          </div>
        ) : null}
      </div>

      <button
        type="button"
        className="fixed right-5 z-40 flex h-[54px] w-[54px] items-center justify-center rounded-full bg-[#C87D60] text-white shadow-[0_12px_26px_rgba(200,125,96,0.35)] active:scale-95"
        style={{ bottom: "calc(env(safe-area-inset-bottom, 0px) + 88px)" }}
        onClick={() => openAddSheet()}
        disabled={saving}
        aria-label="新增"
      >
        <PlusIcon open={adding} />
      </button>

      <nav
        className="fixed inset-x-0 bottom-0 z-30 border-t border-[#E8D8D0] bg-[#FBF8F6]/95 px-4 pt-2 backdrop-blur-md"
        style={{ paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 10px)" }}
      >
        <div className="mx-auto grid max-w-xl grid-cols-3 gap-2">
          {[
            { id: "timeline" as const, label: "timeline" },
            { id: "cinema" as const, label: "cinema" },
            { id: "library" as const, label: "library" },
          ].map((item) => {
            const active = activeView === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={`rounded-full px-3 py-2.5 text-[12px] font-semibold uppercase tracking-[0.12em] transition-colors ${
                  active ? "bg-[#3D2B29] text-[#FBF8F6]" : "text-[#8B6F68] active:bg-[#EDE1DC]"
                }`}
                onClick={() => setActiveView(item.id)}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </nav>

      {adding ? (
        <div className="fixed inset-0 z-50 flex items-end bg-[#3D2B29]/20 px-4 pt-12 backdrop-blur-sm">
          <form
            className="mx-auto w-full max-w-xl rounded-t-[24px] border border-[#E8D8D0] bg-[#FBF8F6] px-5 pb-[calc(env(safe-area-inset-bottom,0px)+18px)] pt-5 shadow-[0_-16px_42px_rgba(61,43,41,0.18)]"
            onSubmit={(e) => {
              e.preventDefault();
              void addEntry();
            }}
          >
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[15px] font-semibold text-[#3D2B29]">Record memory</div>
              <button
                type="button"
                className="rounded-full px-3 py-1.5 text-[13px] font-medium text-[#8B6F68] active:bg-[#EDE1DC]"
                onClick={() => setAdding(false)}
                disabled={saving}
              >
                取消
              </button>
            </div>
            <div className="mb-4 grid grid-cols-3 gap-2">
              {entryTypeOptions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`rounded-full border px-3 py-2 text-[12px] font-semibold transition-colors ${
                    entryType === item.id
                      ? "border-[#C87D60] bg-[#C87D60] text-white"
                      : "border-[#E8D8D0] bg-white/60 text-[#7A625D]"
                  }`}
                  onClick={() => setEntryType(item.id)}
                  disabled={saving}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="space-y-3">
              <input
                className="h-12 w-full rounded-[16px] border border-[#E8D8D0] bg-white/70 px-4 text-[15px] font-medium text-[#3D2B29] outline-none placeholder:text-[#B59B93] focus:border-[#C87D60]"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={entryType === "node" ? "重要节点" : entryType === "movie" ? "片名" : "书名"}
                disabled={saving}
                style={{ fontFamily: STAY_SERIF_FONT }}
              />
              {entryType === "node" ? (
                <input
                  type="date"
                  className="h-12 w-full rounded-[16px] border border-[#E8D8D0] bg-white/70 px-4 text-[15px] font-medium text-[#3D2B29] outline-none focus:border-[#C87D60]"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  disabled={saving}
                  style={{ fontFamily: STAY_SANS_FONT }}
                />
              ) : null}
              <textarea
                className="min-h-[96px] w-full resize-none rounded-[16px] border border-[#E8D8D0] bg-white/70 px-4 py-3 text-[14px] leading-6 text-[#3D2B29] outline-none placeholder:text-[#B59B93] focus:border-[#C87D60]"
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder="备注"
                disabled={saving}
                style={{ fontFamily: STAY_SERIF_FONT }}
              />
            </div>
            <button
              type="submit"
              className="mt-4 h-12 w-full rounded-full bg-[#3D2B29] text-[14px] font-semibold text-[#FBF8F6] disabled:opacity-40"
              disabled={saving || !title.trim()}
            >
              {saving ? "Saving..." : "Record Memory"}
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}


function StayMediaSection({
  title,
  items,
  emptyText,
  done = false,
  onComplete,
  onDelete,
  disabled = false,
}: {
  title: string;
  items: StayMediaItem[];
  emptyText: string;
  done?: boolean;
  onComplete?: (id: string) => void;
  onDelete?: (id: string) => void;
  disabled?: boolean;
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[13px] font-semibold uppercase tracking-[0.18em] text-[#C87D60]">{title}</h3>
        <span className="text-[12px] font-medium text-[#A68B84]">{items.length}</span>
      </div>
      {items.length ? (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex min-h-[74px] items-start gap-3 rounded-[18px] border border-[#E8D8D0] bg-white/[0.62] px-4 py-3 shadow-[0_8px_22px_rgba(61,43,41,0.04)]"
            >
              <input
                type="checkbox"
                className="mt-1 h-5 w-5 shrink-0 accent-[#C87D60]"
                checked={done}
                readOnly={done}
                disabled={disabled}
                onChange={() => {
                  if (!done) onComplete?.(item.id);
                }}
              />
              <span className="min-w-0 flex-1">
                <span
                  className={`block text-[18px] font-normal leading-6 ${done ? "text-[#7A625D] line-through decoration-[#A68B84] decoration-1" : "text-[#3D2B29]"}`}
                  style={{ fontFamily: STAY_SERIF_FONT }}
                >
                  {item.title}
                </span>
                {item.note ? <span className="mt-1 block text-[13px] leading-5 text-[#8B6F68]">{item.note}</span> : null}
                {item.date ? <span className="mt-2 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[#C87D60]">{item.date}</span> : null}
              </span>
              <button
                type="button"
                className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#A68B84] transition-colors active:bg-[#EDE1DC] disabled:opacity-40"
                onClick={() => onDelete?.(item.id)}
                disabled={disabled}
                aria-label={`删除 ${item.title}`}
                title="删除"
              >
                <TrashIconMini />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <StayEmptyState text={emptyText} />
      )}
    </section>
  );
}

function StayEmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[18px] border border-dashed border-[#E8D8D0] px-4 py-5 text-[13px] leading-6 text-[#8B6F68]">
      {text}
    </div>
  );
}
