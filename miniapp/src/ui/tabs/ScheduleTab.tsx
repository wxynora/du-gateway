import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { Btn } from "../components";
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

function weekdayLabel(v: number): string {
  return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][v] || "周一";
}

function repeatLabel(item: ScheduleItem): string {
  const v = String(item.repeat || "once");
  if (v === "daily") {
    const dt = String(item.daily_time || "").trim();
    return `每天${dt ? ` ${dt}` : ""}`;
  }
  if (v === "weekly") {
    const wd = Number(item.weekly_weekday ?? 0);
    const wt = String(item.weekly_time || "").trim();
    return `每周 ${weekdayLabel(wd)}${wt ? ` ${wt}` : ""}`;
  }
  return "仅一次";
}

function dateKey(v: string): string {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dateLabel(v: string): string {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "未选择日期";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function monthLabel(y: number, m: number): string {
  return `${y}年${String(m + 1).padStart(2, "0")}月`;
}

function weekdayMon0FromDateKey(k: string): number {
  const d = new Date(`${k}T00:00:00`);
  if (Number.isNaN(d.getTime())) return 0;
  // JS: Sun=0..Sat=6 -> Mon=0..Sun=6
  return (d.getDay() + 6) % 7;
}

function occursOnDate(item: ScheduleItem, dayKey: string): boolean {
  const rep = String(item.repeat || "once");
  const anchor = dateKey(String(item.datetime || ""));
  if (!anchor) return false;
  if (dayKey < anchor) return false;
  if (rep === "daily") return true;
  if (rep === "weekly") {
    const wk = Number.isFinite(Number(item.weekly_weekday))
      ? Number(item.weekly_weekday)
      : weekdayMon0FromDateKey(anchor);
    return weekdayMon0FromDateKey(dayKey) === wk;
  }
  return dayKey === anchor;
}

export function ScheduleTab() {
  const toast = useToast();
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formDatetime, setFormDatetime] = useState("");
  const [formRepeat, setFormRepeat] = useState("once");
  const [formDailyTime, setFormDailyTime] = useState("09:00");
  const [formWeeklyWeekdays, setFormWeeklyWeekdays] = useState<number[]>([0]);
  const [formWeeklyTime, setFormWeeklyTime] = useState("09:00");
  const [formNote, setFormNote] = useState("");
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
  const allItems = useMemo(
    () => normalizeItems(items).slice().sort((a, b) => String(a.datetime || "").localeCompare(String(b.datetime || ""))),
    [items]
  );
  const dayItems = useMemo(
    () => allItems.filter((it) => occursOnDate(it, selectedDate)),
    [allItems, selectedDate]
  );
  const calendarCells = useMemo(() => {
    const year = visibleMonth.year;
    const month = visibleMonth.month;
    const firstDay = new Date(year, month, 1);
    const firstWeekday = firstDay.getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prefix: Array<{ key: string; day: number; inMonth: boolean }> = [];
    for (let i = 0; i < firstWeekday; i += 1) {
      prefix.push({ key: `p-${i}`, day: 0, inMonth: false });
    }
    const body: Array<{ key: string; day: number; inMonth: boolean }> = [];
    for (let d = 1; d <= daysInMonth; d += 1) {
      body.push({ key: `d-${d}`, day: d, inMonth: true });
    }
    return [...prefix, ...body];
  }, [visibleMonth]);
  const dateCountMap = useMemo(() => {
    const m: Record<string, number> = {};
    calendarCells.forEach((cell) => {
      if (!cell.inMonth) return;
      const dayKey = `${visibleMonth.year}-${String(visibleMonth.month + 1).padStart(2, "0")}-${String(cell.day).padStart(2, "0")}`;
      let count = 0;
      allItems.forEach((it) => {
        if (occursOnDate(it, dayKey)) count += 1;
      });
      m[dayKey] = count;
    });
    return m;
  }, [allItems, calendarCells, visibleMonth]);

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

  async function enableItem(id: string) {
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/schedule/items/${encodeURIComponent(id)}/enable`, {
        method: "PUT",
      });
      if (!j?.ok) throw new Error(j?.error || "启用失败");
      toast("已启用提醒");
      await load();
    } catch (e: any) {
      toast(`操作失败：${e?.message || e}`);
    }
  }

  async function createItem() {
    const title = (formTitle || "").trim();
    const datetimeLocal = (formDatetime || "").trim();
    if (!title) {
      toast("请填写提醒标题");
      return;
    }
    if (formRepeat === "weekly") {
      if (!(formWeeklyTime || "").trim()) {
        toast("请选择每周提醒时间");
        return;
      }
      if (!formWeeklyWeekdays.length) {
        toast("请至少选择一个周几");
        return;
      }
    } else if (formRepeat === "daily") {
      if (!(formDailyTime || "").trim()) {
        toast("请选择每天提醒时间");
        return;
      }
    } else if (!datetimeLocal) {
      toast("请选择提醒时间");
      return;
    }
    setCreating(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string; item?: ScheduleItem }>("/miniapp-api/schedule/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          datetime: formRepeat === "weekly" || formRepeat === "daily" ? "" : datetimeLocal,
          repeat: formRepeat || "once",
          daily_time: formRepeat === "daily" ? formDailyTime : undefined,
          weekly_weekdays: formRepeat === "weekly" ? formWeeklyWeekdays : undefined,
          weekly_time: formRepeat === "weekly" ? formWeeklyTime : undefined,
          note: (formNote || "").trim(),
          enabled: true,
        }),
      });
      if (!j?.ok) throw new Error(j?.error || "创建失败");
      toast("已创建提醒");
      setFormTitle("");
      setFormDatetime("");
      setFormRepeat("once");
      setFormDailyTime("09:00");
      setFormWeeklyWeekdays([0]);
      setFormWeeklyTime("09:00");
      setFormNote("");
      await load();
    } catch (e: any) {
      toast(`创建失败：${e?.message || e}`);
    } finally {
      setCreating(false);
    }
  }

  async function deleteItem(id: string) {
    if (!id) return;
    const ok = window.confirm("确认删除这条提醒？删除后不可恢复。");
    if (!ok) return;
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/schedule/items/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除提醒");
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

  function toggleWeeklyWeekday(day: number) {
    setFormWeeklyWeekdays((prev) => {
      if (prev.includes(day)) return prev.filter((x) => x !== day);
      return [...prev, day].sort((a, b) => a - b);
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <div className="text-xs text-cream-muted">日历与闹钟 · 轻量管理</div>
        <button
          className="neo-icon-btn h-8 w-8 disabled:opacity-50"
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
        <div className="neo-muted-box bg-[linear-gradient(145deg,rgba(251,230,236,0.95),rgba(236,206,221,0.82))]">
          读取失败：{error}
        </div>
      ) : null}

      <div className="neo-panel p-3 space-y-2">
        <div className="text-xs text-cream-muted">新增提醒（闹钟）</div>
        <input
          className="neo-input"
          placeholder="提醒标题，例如：吃药"
          value={formTitle}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormTitle(e.target.value)}
          disabled={creating}
        />
        {formRepeat === "weekly" ? (
          <div className="space-y-2">
            <div className="grid grid-cols-4 gap-2">
              {["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((w, idx) => {
                const selected = formWeeklyWeekdays.includes(idx);
                return (
                  <button
                    key={w}
                    type="button"
                    className={
                      "neo-segment " +
                      (selected ? "neo-segment-active" : "")
                    }
                    onClick={() => toggleWeeklyWeekday(idx)}
                    disabled={creating}
                  >
                    {w}
                  </button>
                );
              })}
            </div>
            <input
              type="time"
              className="neo-input"
              value={formWeeklyTime}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormWeeklyTime(e.target.value)}
              disabled={creating}
            />
          </div>
        ) : formRepeat === "daily" ? (
          <input
            type="time"
            className="neo-input"
            value={formDailyTime}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormDailyTime(e.target.value)}
            disabled={creating}
          />
        ) : (
          <input
            type="datetime-local"
            className="neo-input"
            value={formDatetime}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormDatetime(e.target.value)}
            disabled={creating}
          />
        )}
        <div className="grid grid-cols-2 gap-2">
          <select
            className="neo-select"
            value={formRepeat}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setFormRepeat(e.target.value)}
            disabled={creating}
          >
            <option value="once">仅一次</option>
            <option value="daily">每天</option>
            <option value="weekly">每周</option>
          </select>
          <Btn kind="green" onClick={createItem} disabled={creating}>
            {creating ? "创建中..." : "创建提醒"}
          </Btn>
        </div>
        <input
          className="neo-input"
          placeholder="备注（可选）"
          value={formNote}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormNote(e.target.value)}
          disabled={creating}
        />
      </div>

      <div className="neo-panel p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-xs text-cream-muted">月视图日历</div>
          <div className="flex items-center gap-1">
            <button
              className="neo-segment h-7 px-2 text-[11px]"
              onClick={() => switchMonth(-1)}
              title="上月"
            >
              上月
            </button>
            <div className="min-w-[84px] text-center text-[11px] text-cream-muted">{monthLabel(visibleMonth.year, visibleMonth.month)}</div>
            <button
              className="neo-segment h-7 px-2 text-[11px]"
              onClick={() => switchMonth(1)}
              title="下月"
            >
              下月
            </button>
          </div>
        </div>
        <div className="grid grid-cols-7 gap-1 text-[11px] text-cream-muted">
          {["日", "一", "二", "三", "四", "五", "六"].map((w) => (
            <div key={w} className="text-center">{w}</div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {calendarCells.map((cell) => {
            if (!cell.inMonth) return <div key={cell.key} className="h-10 rounded-xl2 bg-white/10" />;
            const k = `${visibleMonth.year}-${String(visibleMonth.month + 1).padStart(2, "0")}-${String(cell.day).padStart(2, "0")}`;
            const selected = k === selectedDate;
            const count = dateCountMap[k] || 0;
            return (
              <button
                key={cell.key}
                className={
                  "h-10 rounded-xl2 border text-xs transition " +
                  (selected
                    ? "bg-cream-green/65 border-white/60 text-cream-text shadow-soft2"
                    : "bg-white/55 border-white/45 text-cream-text")
                }
                onClick={() => setSelectedDate(k)}
              >
                <div className="leading-tight">{cell.day}</div>
                <div className="text-[10px] text-cream-muted">{count ? `${count}条` : ""}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="neo-panel p-3">
        <div className="neo-tag-dark">
          当日提醒 · {dateLabel(selectedDate)} · {dayItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {dayItems.map((it) => (
            <div key={`day-${String(it.id || "")}`} className="neo-panel-soft p-3">
              <div className="text-sm font-medium text-cream-text">{it.title || "未命名提醒"}</div>
              <div className="mt-1 text-xs text-cream-muted">
                {fmtDate(String(it.datetime || ""))} · {repeatLabel(it)} · {it.enabled === false ? "已禁用" : "启用中"}
              </div>
              {it.note ? <div className="mt-1 text-xs text-cream-muted">{it.note}</div> : null}
            </div>
          ))}
          {!dayItems.length ? <div className="text-xs text-cream-muted">该日期暂无提醒</div> : null}
        </div>
      </div>

      {!loading && !error && !enabledItems.length && !disabledItems.length ? (
        <div className="neo-muted-box bg-[linear-gradient(145deg,rgba(255,255,255,0.86),rgba(239,243,248,0.62))] text-cream-muted">
          还没有提醒，先创建一条试试。
        </div>
      ) : null}

      <div className="neo-panel p-3">
        <div className="neo-tag-dark">
          启用中 · {enabledItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {enabledItems.map((it) => (
            <div key={String(it.id || "")} className="neo-panel-soft p-3">
              <div className="text-sm font-medium text-cream-text">{it.title || "未命名提醒"}</div>
              <div className="mt-1 text-xs text-cream-muted">{fmtDate(String(it.datetime || ""))} · {repeatLabel(it)}</div>
              {it.note ? <div className="mt-1 text-xs text-cream-muted">{it.note}</div> : null}
              <div className="mt-2 flex items-center gap-2">
                <Btn kind="danger" onClick={() => disableItem(String(it.id || ""))} disabled={!it.id}>禁用未来触发</Btn>
                <Btn kind="pink" onClick={() => deleteItem(String(it.id || ""))} disabled={!it.id}>删除</Btn>
              </div>
            </div>
          ))}
          {!enabledItems.length ? <div className="text-xs text-cream-muted">暂无启用中的提醒</div> : null}
        </div>
      </div>

      <div className="neo-panel p-3">
        <div className="neo-tag-dark">
          已禁用 · {disabledItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {disabledItems.map((it) => (
            <div key={String(it.id || "")} className="neo-panel-soft p-3">
              <div className="text-sm text-cream-text">{it.title || "未命名提醒"}</div>
              <div className="mt-1 text-xs text-cream-muted">{fmtDate(String(it.datetime || ""))} · {repeatLabel(it)} · 已禁用</div>
              <div className="mt-2 flex items-center gap-2">
                <Btn kind="green" onClick={() => enableItem(String(it.id || ""))} disabled={!it.id}>重新启用</Btn>
                <Btn kind="pink" onClick={() => deleteItem(String(it.id || ""))} disabled={!it.id}>删除</Btn>
              </div>
            </div>
          ))}
          {!disabledItems.length ? <div className="text-xs text-cream-muted">暂无已禁用提醒</div> : null}
        </div>
      </div>
    </div>
  );
}

