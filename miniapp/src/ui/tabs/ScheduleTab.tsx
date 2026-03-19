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
  if (v === "daily") return "每天";
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

export function ScheduleTab() {
  const toast = useToast();
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formDatetime, setFormDatetime] = useState("");
  const [formRepeat, setFormRepeat] = useState("once");
  const [formWeeklyWeekday, setFormWeeklyWeekday] = useState(0);
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
    () => allItems.filter((it) => dateKey(String(it.datetime || "")) === selectedDate),
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
    allItems.forEach((it) => {
      const k = dateKey(String(it.datetime || ""));
      if (!k) return;
      m[k] = (m[k] || 0) + 1;
    });
    return m;
  }, [allItems]);

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
          datetime: formRepeat === "weekly" ? "" : datetimeLocal,
          repeat: formRepeat || "once",
          weekly_weekday: formRepeat === "weekly" ? formWeeklyWeekday : undefined,
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
      setFormWeeklyWeekday(0);
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

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <div className="text-xs text-cream-muted">日历与闹钟 · 轻量管理</div>
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
        <div className="rounded-xl2 bg-cream-pink/65 px-3 py-2 text-xs text-cream-text shadow-soft2">
          读取失败：{error}
        </div>
      ) : null}

      <div className="rounded-xl3 bg-cream-blue/42 backdrop-blur-xl border border-white/50 shadow-soft p-3 space-y-2">
        <div className="text-xs text-cream-muted">新增提醒（闹钟）</div>
        <input
          className="w-full rounded-xl2 bg-cream-card/90 border border-white/55 px-3 py-2 text-sm text-cream-text shadow-soft2 placeholder:text-cream-muted"
          placeholder="提醒标题，例如：吃药"
          value={formTitle}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormTitle(e.target.value)}
          disabled={creating}
        />
        {formRepeat === "weekly" ? (
          <div className="grid grid-cols-2 gap-2">
            <select
              className="w-full rounded-xl2 bg-cream-card/90 border border-white/55 px-3 py-2 text-sm text-cream-text shadow-soft2"
              value={String(formWeeklyWeekday)}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setFormWeeklyWeekday(Number(e.target.value || 0))}
              disabled={creating}
            >
              <option value="0">周一</option>
              <option value="1">周二</option>
              <option value="2">周三</option>
              <option value="3">周四</option>
              <option value="4">周五</option>
              <option value="5">周六</option>
              <option value="6">周日</option>
            </select>
            <input
              type="time"
              className="w-full rounded-xl2 bg-cream-card/90 border border-white/55 px-3 py-2 text-sm text-cream-text shadow-soft2"
              value={formWeeklyTime}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormWeeklyTime(e.target.value)}
              disabled={creating}
            />
          </div>
        ) : (
          <input
            type="datetime-local"
            className="w-full rounded-xl2 bg-cream-card/90 border border-white/55 px-3 py-2 text-sm text-cream-text shadow-soft2"
            value={formDatetime}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormDatetime(e.target.value)}
            disabled={creating}
          />
        )}
        <div className="grid grid-cols-2 gap-2">
          <select
            className="w-full rounded-xl2 bg-cream-card/90 border border-white/55 px-3 py-2 text-sm text-cream-text shadow-soft2"
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
          className="w-full rounded-xl2 bg-cream-card/90 border border-white/55 px-3 py-2 text-sm text-cream-text shadow-soft2 placeholder:text-cream-muted"
          placeholder="备注（可选）"
          value={formNote}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormNote(e.target.value)}
          disabled={creating}
        />
      </div>

      <div className="rounded-xl3 bg-white/40 backdrop-blur-xl border border-white/50 shadow-soft p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-xs text-cream-muted">月视图日历</div>
          <div className="flex items-center gap-1">
            <button
              className="h-7 rounded-xl2 bg-white/65 border border-white/55 px-2 text-[11px] text-cream-text shadow-soft2"
              onClick={() => switchMonth(-1)}
              title="上月"
            >
              上月
            </button>
            <div className="min-w-[84px] text-center text-[11px] text-cream-muted">{monthLabel(visibleMonth.year, visibleMonth.month)}</div>
            <button
              className="h-7 rounded-xl2 bg-white/65 border border-white/55 px-2 text-[11px] text-cream-text shadow-soft2"
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

      <div className="rounded-xl3 bg-white/38 backdrop-blur-xl border border-white/45 shadow-soft p-3">
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          当日提醒 · {dateLabel(selectedDate)} · {dayItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {dayItems.map((it) => (
            <div key={`day-${String(it.id || "")}`} className="rounded-xl2 bg-white border border-white/70 shadow-soft2 p-3">
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
        <div className="rounded-xl2 bg-white/46 border border-white/45 shadow-soft2 px-3 py-2 text-xs text-cream-muted">
          还没有提醒，先创建一条试试。
        </div>
      ) : null}

      <div className="rounded-xl3 bg-white/42 backdrop-blur-xl border border-white/50 shadow-soft p-3">
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          启用中 · {enabledItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {enabledItems.map((it) => (
            <div key={String(it.id || "")} className="rounded-xl2 bg-white border border-white/70 shadow-soft2 p-3">
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

      <div className="rounded-xl3 bg-white/34 backdrop-blur-xl border border-white/45 shadow-soft p-3">
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          已禁用 · {disabledItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {disabledItems.map((it) => (
            <div key={String(it.id || "")} className="rounded-xl2 bg-white border border-white/70 shadow-soft2 p-3">
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

