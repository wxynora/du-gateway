import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type ScheduleItem = {
  id?: string;
  title?: string;
  datetime?: string;
  repeat?: string;
  weekly_weekday?: number;
  weekly_time?: string;
  daily_time?: string;
  enabled?: boolean;
  note?: string;
};

type ScheduleResp = {
  ok?: boolean;
  items?: ScheduleItem[];
};

type CalendarCell = {
  key: string;
  day: number;
  inMonth: boolean;
  dayKey: string;
};

function normalizeItems(input: unknown): ScheduleItem[] {
  if (!Array.isArray(input)) return [];
  return input.filter((x): x is ScheduleItem => !!x && typeof x === "object");
}

function dateKey(v: string): string {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dateTimeLabel(v: string): string {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v || "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function hm(v: string): string {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "--:--";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function weekdayLabelMon0(v: number): string {
  return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][v] || "周一";
}

function weekdaySun0Label(v: number): string {
  return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][v] || "周日";
}

function monthLabel(year: number, month: number): string {
  return `${year}年 ${month + 1}月`;
}

function weekdayMon0FromDateKey(k: string): number {
  const d = new Date(`${k}T00:00:00`);
  if (Number.isNaN(d.getTime())) return 0;
  return (d.getDay() + 6) % 7;
}

function occursOnDate(item: ScheduleItem, dayKey: string): boolean {
  const rep = String(item.repeat || "once");
  const anchor = dateKey(String(item.datetime || ""));
  if (!anchor) return false;
  if (dayKey < anchor) return false;
  if (rep === "daily") return true;
  if (rep === "weekly") {
    const wk = Number.isFinite(Number(item.weekly_weekday)) ? Number(item.weekly_weekday) : weekdayMon0FromDateKey(anchor);
    return weekdayMon0FromDateKey(dayKey) === wk;
  }
  return dayKey === anchor;
}

function repeatBadge(item: ScheduleItem): string {
  const rep = String(item.repeat || "once");
  if (rep === "daily") return "每天";
  if (rep === "weekly") {
    const wd = Number.isFinite(Number(item.weekly_weekday)) ? Number(item.weekly_weekday) : 0;
    return `每周 ${weekdayLabelMon0(wd)}`;
  }
  return "仅一次";
}

function repeatSubLabel(item: ScheduleItem): string {
  const rep = String(item.repeat || "once");
  if (rep === "daily") return `每天 ${String(item.daily_time || "").trim() || hm(String(item.datetime || ""))}`;
  if (rep === "weekly") {
    const wd = Number.isFinite(Number(item.weekly_weekday)) ? Number(item.weekly_weekday) : 0;
    const wt = String(item.weekly_time || "").trim() || hm(String(item.datetime || ""));
    return `${wt} · ${weekdayLabelMon0(wd)}`;
  }
  return dateTimeLabel(String(item.datetime || ""));
}

export function ScheduleTab() {
  const toast = useToast();
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [togglingId, setTogglingId] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const [selectedDate, setSelectedDate] = useState(() => dateKey(new Date().toISOString()));
  const [visibleMonth, setVisibleMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<ScheduleResp>("/miniapp-api/schedule/items");
      setItems(normalizeItems(j?.items));
      setLoadError("");
    } catch (e: any) {
      setItems([]);
      setLoadError(e?.message || String(e));
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allItems = useMemo(
    () => normalizeItems(items).slice().sort((a, b) => String(a.datetime || "").localeCompare(String(b.datetime || ""))),
    [items]
  );
  const enabledItems = useMemo(() => allItems.filter((x) => x.enabled !== false), [allItems]);
  const disabledItems = useMemo(() => allItems.filter((x) => x.enabled === false), [allItems]);

  const calendarCells = useMemo(() => {
    const year = visibleMonth.year;
    const month = visibleMonth.month;
    const first = new Date(year, month, 1);
    const firstWeekday = first.getDay(); // Sun=0
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const daysInPrevMonth = new Date(year, month, 0).getDate();
    const cells: CalendarCell[] = [];
    for (let i = firstWeekday - 1; i >= 0; i -= 1) {
      const day = daysInPrevMonth - i;
      const d = new Date(year, month - 1, day);
      const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      cells.push({ key: `p-${day}`, day, inMonth: false, dayKey: k });
    }
    for (let d = 1; d <= daysInMonth; d += 1) {
      const k = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      cells.push({ key: `m-${d}`, day: d, inMonth: true, dayKey: k });
    }
    while (cells.length % 7 !== 0) {
      const day = cells.length % 7 === 0 ? 1 : cells.length - daysInMonth - firstWeekday + 1;
      const d = new Date(year, month + 1, day);
      const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      cells.push({ key: `n-${day}-${cells.length}`, day: d.getDate(), inMonth: false, dayKey: k });
    }
    return cells;
  }, [visibleMonth]);

  const dateCountMap = useMemo(() => {
    const m: Record<string, number> = {};
    calendarCells.forEach((cell) => {
      let count = 0;
      allItems.forEach((it) => {
        if (occursOnDate(it, cell.dayKey)) count += 1;
      });
      m[cell.dayKey] = count;
    });
    return m;
  }, [calendarCells, allItems]);

  const dayItems = useMemo(() => {
    return allItems.filter((it) => occursOnDate(it, selectedDate));
  }, [allItems, selectedDate]);

  async function setEnabled(id: string, enabled: boolean) {
    if (!id) return;
    setTogglingId(id);
    try {
      const path = enabled
        ? `/miniapp-api/schedule/items/${encodeURIComponent(id)}/enable`
        : `/miniapp-api/schedule/items/${encodeURIComponent(id)}/disable`;
      const j = await apiJson<{ ok?: boolean; error?: string }>(path, { method: "PUT" });
      if (!j?.ok) throw new Error(j?.error || (enabled ? "启用失败" : "停用失败"));
      toast(enabled ? "已启用" : "已停用");
      await load();
    } catch (e: any) {
      toast(`操作失败：${e?.message || e}`);
    } finally {
      setTogglingId("");
    }
  }

  async function deleteItem(id: string) {
    if (!id) return;
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/schedule/items/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除提醒");
      setDeletingId("");
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  function switchMonth(step: number) {
    setVisibleMonth((prev) => {
      const d = new Date(prev.year, prev.month + step, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  }

  return (
    <div className="relative bg-[#FDFDFD]">
      <style>{`
        .shadow-soft { box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.04), 0 8px 10px -6px rgba(0, 0, 0, 0.02); }
        .sch-switch { position: relative; display: inline-block; width: 42px; height: 24px; flex: 0 0 auto; }
        .sch-switch input { opacity: 0; width: 0; height: 0; position: absolute; }
        .sch-slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #E2E8F0; transition: .25s; border-radius: 24px; overflow: hidden; }
        .sch-slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .25s; border-radius: 50%; }
        .sch-switch input:checked + .sch-slider { background-color: #4A5568; }
        .sch-switch input:checked + .sch-slider:before { transform: translateX(18px); }
        .reminder-card { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .reminder-card:active { transform: scale(0.98); }
        .status-badge {
          padding: 2px 8px;
          border-radius: 6px;
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
        }
        .modal-overlay {
          background-color: rgba(0, 0, 0, 0.4);
          backdrop-filter: blur(4px);
        }
        .calendar-dot {
          width: 4px;
          height: 4px;
          background-color: #3B82F6;
          border-radius: 50%;
          margin-top: 2px;
        }
        .date-selected {
          background-color: #1F2937;
          color: white !important;
          border-radius: 14px;
        }
      `}</style>

      <div className="mb-4 flex items-center justify-between px-1">
        <div className="text-[17px] font-semibold text-gray-800">日历</div>
        <div className="flex items-center rounded-full border border-gray-100 bg-gray-50 px-3 py-1">
          <span className={`mr-2 h-1.5 w-1.5 rounded-full ${loadError ? "bg-red-400" : "bg-green-400"}`} />
          <span className="text-[11px] font-medium text-gray-500">{loadError ? "同步异常" : "渡 已同步"}</span>
        </div>
      </div>

      <div className="px-5 pt-2">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-gray-800">{monthLabel(visibleMonth.year, visibleMonth.month)}</h2>
          <div className="flex space-x-2">
            <button className="rounded-full p-2 text-gray-400 transition-colors hover:bg-gray-100" onClick={() => switchMonth(-1)} title="上月">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <button className="rounded-full p-2 text-gray-400 transition-colors hover:bg-gray-100" onClick={() => switchMonth(1)} title="下月">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </div>
        </div>

        <div className="mb-2 grid grid-cols-7 text-center">
          {["日", "一", "二", "三", "四", "五", "六"].map((w) => (
            <span key={w} className="text-[11px] font-bold uppercase tracking-wider text-gray-300">
              {w}
            </span>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-y-2">
          {calendarCells.map((cell) => {
            const selected = selectedDate === cell.dayKey;
            const count = dateCountMap[cell.dayKey] || 0;
            const textCls = cell.inMonth ? "text-gray-800" : "text-gray-200";
            return (
              <button
                key={cell.key}
                className={`h-10 flex flex-col items-center justify-center text-[14px] ${textCls} ${selected ? "date-selected font-bold" : ""}`}
                onClick={() => setSelectedDate(cell.dayKey)}
                title={cell.dayKey}
              >
                {cell.day}
                {count ? <div className={selected ? "mt-0.5 h-1 w-1 rounded-full bg-white" : "calendar-dot"} /> : null}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4 px-5">
        <div className="mb-8">
          <div className="mb-4 flex items-center justify-between px-1">
            <div className="flex items-baseline space-x-2">
              <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">启用中</h2>
              <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-500">{enabledItems.length}</span>
            </div>
          </div>
          <div className="space-y-4">
            {enabledItems.map((it) => {
              const id = String(it.id || "");
              return (
                <div key={id} className="reminder-card group relative overflow-hidden rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-soft">
                  <div className="mb-1 flex justify-between items-start">
                    <div>
                      <span className="status-badge bg-blue-50 text-blue-500">{repeatBadge(it)}</span>
                      <h3 className="mt-2 text-[18px] font-bold text-gray-800">{it.title || "未命名提醒"}</h3>
                      <div className="mt-1 flex items-baseline space-x-1">
                        <span className="text-[24px] font-bold text-gray-800">{hm(String(it.datetime || ""))}</span>
                        <span className="text-[12px] font-medium text-gray-400">{repeatSubLabel(it)}</span>
                      </div>
                    </div>
                    <label className="sch-switch">
                      <input
                        type="checkbox"
                        checked={it.enabled !== false}
                        disabled={!id || togglingId === id}
                        onChange={(e) => setEnabled(id, e.target.checked)}
                      />
                      <span className="sch-slider" />
                    </label>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <p className="text-[13px] font-light text-gray-500">{String(it.note || "").trim() || dateTimeLabel(String(it.datetime || ""))}</p>
                    <button
                      className="p-2 text-gray-300 opacity-0 transition-all group-hover:opacity-100 hover:text-red-400"
                      onClick={() => setDeletingId(id)}
                      title="删除提醒"
                    >
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        <line x1="10" y1="11" x2="10" y2="17" />
                        <line x1="14" y1="11" x2="14" y2="17" />
                      </svg>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mb-8">
          <div className="mb-4 flex items-center justify-between px-1">
            <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">已停用</h2>
          </div>
          <div className="space-y-4">
            {disabledItems.map((it) => {
              const id = String(it.id || "");
              return (
                <div key={id} className="reminder-card group rounded-[28px] border border-gray-100 bg-gray-50/50 p-5">
                  <div className="mb-1 flex justify-between items-start">
                    <div>
                      <span className="status-badge bg-gray-100 text-gray-400">已停用</span>
                      <h3 className="mt-2 text-[18px] font-bold text-gray-400">{it.title || "未命名提醒"}</h3>
                      <div className="mt-1 flex items-baseline space-x-1">
                        <span className="text-[24px] font-bold text-gray-400">{hm(String(it.datetime || ""))}</span>
                        <span className="text-[12px] font-medium text-gray-400">{repeatSubLabel(it)}</span>
                      </div>
                    </div>
                    <label className="sch-switch">
                      <input
                        type="checkbox"
                        checked={it.enabled !== false}
                        disabled={!id || togglingId === id}
                        onChange={(e) => setEnabled(id, e.target.checked)}
                      />
                      <span className="sch-slider" />
                    </label>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <p className="text-[13px] font-light text-gray-400">{String(it.note || "").trim() || dateTimeLabel(String(it.datetime || ""))}</p>
                    <button
                      className="p-2 text-gray-300 opacity-0 transition-all group-hover:opacity-100 hover:text-red-400"
                      onClick={() => setDeletingId(id)}
                      title="删除提醒"
                    >
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        <line x1="10" y1="11" x2="10" y2="17" />
                        <line x1="14" y1="11" x2="14" y2="17" />
                      </svg>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {!loading && !allItems.length ? (
          <div className="py-24 text-center flex flex-col items-center justify-center">
            <div className="mb-6 h-24 w-24 rounded-full bg-orange-50 flex items-center justify-center">
              <svg className="h-10 w-10 text-orange-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                <path d="M18.63 13A17.89 17.89 0 0 1 18 8" />
                <path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14" />
                <path d="M18 8a6 6 0 0 0-9.33-5" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            </div>
            <h3 className="mb-2 text-[18px] font-medium text-gray-800">暂无任何提醒</h3>
            <p className="px-10 text-[14px] leading-relaxed text-gray-400">你可以对渡说：<br />“每天早上八点提醒我喝水”</p>
          </div>
        ) : null}

        {!loading && allItems.length > 0 && !dayItems.length ? (
          <div className="py-20 text-center flex flex-col items-center justify-center">
            <div className="mb-6 h-24 w-24 rounded-full bg-gray-50 flex items-center justify-center">
              <svg className="h-10 w-10 text-gray-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <h3 className="mb-2 text-[18px] font-medium text-gray-800">这一天暂无提醒</h3>
            <p className="px-10 text-[14px] leading-relaxed text-gray-400">休息也是很重要的一部分</p>
          </div>
        ) : null}
      </div>

      {deletingId ? (
        <div className="modal-overlay fixed inset-0 z-[100] flex items-center justify-center px-8">
          <div className="w-full max-w-sm rounded-[32px] bg-white p-8 shadow-2xl">
            <h3 className="mb-3 text-center text-[20px] font-semibold text-gray-900">要删除这个提醒吗？</h3>
            <p className="mb-8 px-2 text-center text-[15px] font-light text-gray-500">删除后将无法恢复，渡也不会再在指定时间提醒你。</p>
            <div className="flex flex-col space-y-3">
              <button
                className="w-full rounded-[20px] bg-red-500 py-4 font-medium text-white shadow-lg shadow-red-100 transition-all active:scale-95"
                onClick={() => deleteItem(deletingId)}
              >
                确认删除
              </button>
              <button
                className="w-full rounded-[20px] py-4 font-medium text-gray-400 transition-all active:bg-gray-50"
                onClick={() => setDeletingId("")}
              >
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="h-8 bg-transparent" />
      <div className="px-5 pb-1 text-[10px] text-gray-300">
        选中日期：{selectedDate || "-"} · 星期{weekdaySun0Label(new Date(`${selectedDate}T00:00:00`).getDay() || 0)}
      </div>
    </div>
  );
}

