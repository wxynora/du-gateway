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
};

function normalizeItems(input: unknown): ScheduleItem[] {
  if (!Array.isArray(input)) return [];
  return input.filter((x): x is ScheduleItem => !!x && typeof x === "object");
}

function toDateTimeLocalString(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day}T${hh}:${mm}`;
}

function fmtDate(v: string): string {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v || "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function AlarmTab() {
  const toast = useToast();
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [label, setLabel] = useState("闹钟");
  const [customTime, setCustomTime] = useState("");

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<ScheduleResp>("/miniapp-api/schedule/items");
      setItems(normalizeItems(j?.items));
    } catch (e: any) {
      toast(`读取失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const alarmItems = useMemo(() => {
    return normalizeItems(items)
      .filter((it) => String(it.repeat || "once") === "once")
      .sort((a, b) => String(a.datetime || "").localeCompare(String(b.datetime || "")));
  }, [items]);

  async function createAt(datetimeLocal: string, titleOverride?: string) {
    if (!datetimeLocal) {
      toast("请先选择时间");
      return;
    }
    setCreating(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/schedule/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: (titleOverride || label || "闹钟").trim() || "闹钟",
          datetime: datetimeLocal,
          repeat: "once",
          note: "from_alarm_tab",
          enabled: true,
        }),
      });
      if (!j?.ok) throw new Error(j?.error || "创建失败");
      toast("闹钟已创建");
      await load();
    } catch (e: any) {
      toast(`创建失败：${e?.message || e}`);
    } finally {
      setCreating(false);
    }
  }

  async function createQuick(minutes: number) {
    const d = new Date();
    d.setMinutes(d.getMinutes() + minutes);
    await createAt(toDateTimeLocalString(d), `${minutes}分钟后闹钟`);
  }

  async function disableItem(id: string) {
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/schedule/items/${encodeURIComponent(id)}/disable`, { method: "PUT" });
      if (!j?.ok) throw new Error(j?.error || "禁用失败");
      toast("已禁用");
      await load();
    } catch (e: any) {
      toast(`操作失败：${e?.message || e}`);
    }
  }

  async function deleteItem(id: string) {
    if (!window.confirm("确认删除该闹钟？")) return;
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/schedule/items/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除");
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  return (
    <div className="space-y-3">
      <div className="rounded-xl3 bg-cream-blue/42 backdrop-blur-xl border border-white/50 shadow-soft p-3 space-y-2">
        <div className="text-xs text-cream-muted">快速闹钟</div>
        <div className="grid grid-cols-3 gap-2">
          <Btn kind="dark" onClick={() => createQuick(10)} disabled={creating}>+10 分钟</Btn>
          <Btn kind="dark" onClick={() => createQuick(30)} disabled={creating}>+30 分钟</Btn>
          <Btn kind="dark" onClick={() => createQuick(60)} disabled={creating}>+60 分钟</Btn>
        </div>
        <input
          className="w-full rounded-xl2 bg-cream-card/90 border border-white/55 px-3 py-2 text-sm text-cream-text shadow-soft2 placeholder:text-cream-muted"
          placeholder="闹钟名称（可选）"
          value={label}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLabel(e.target.value)}
          disabled={creating}
        />
        <div className="grid grid-cols-2 gap-2">
          <input
            type="datetime-local"
            className="w-full rounded-xl2 bg-cream-card/90 border border-white/55 px-3 py-2 text-sm text-cream-text shadow-soft2"
            value={customTime}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCustomTime(e.target.value)}
            disabled={creating}
          />
          <Btn kind="dark" onClick={() => createAt(customTime)} disabled={creating || !customTime}>
            自定义时间创建
          </Btn>
        </div>
      </div>

      <div className="rounded-xl3 bg-white/40 backdrop-blur-xl border border-white/50 shadow-soft p-3">
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          闹钟列表 · {alarmItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {alarmItems.map((it) => (
            <div key={String(it.id || "")} className="rounded-xl2 bg-white border border-white/70 shadow-soft2 p-3">
              <div className="text-sm font-medium text-cream-text">{it.title || "未命名闹钟"}</div>
              <div className="mt-1 text-xs text-cream-muted">{fmtDate(String(it.datetime || ""))} · {it.enabled === false ? "已禁用" : "启用中"}</div>
              <div className="mt-2 flex items-center gap-2">
                <Btn kind="danger" onClick={() => disableItem(String(it.id || ""))} disabled={!it.id || it.enabled === false}>禁用</Btn>
                <Btn kind="pink" onClick={() => deleteItem(String(it.id || ""))} disabled={!it.id}>删除</Btn>
              </div>
            </div>
          ))}
          {!alarmItems.length && !loading ? <div className="text-xs text-cream-muted">暂无闹钟，先创建一个。</div> : null}
        </div>
      </div>
    </div>
  );
}

