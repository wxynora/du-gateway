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
  created_by?: string;
  target_role?: string;
};

type ScheduleResp = {
  ok?: boolean;
  items?: ScheduleItem[];
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

export function DuDayTab() {
  const toast = useToast();
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [title, setTitle] = useState("");
  const [datetime, setDatetime] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

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

  const duItems = useMemo(
    () =>
      normalizeItems(items)
        .filter((it) => String(it.target_role || "wife").toLowerCase() === "du")
        .sort((a, b) => String(a.datetime || "").localeCompare(String(b.datetime || ""))),
    [items]
  );

  async function create() {
    const t = (title || "").trim();
    const dt = (datetime || "").trim();
    if (!t) return toast("先写一件渡想做的事");
    if (!dt) return toast("请选择提醒时间");
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/schedule/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: t,
          datetime: dt,
          repeat: "once",
          note: (note || "").trim(),
          enabled: true,
          created_by: "du",
          target_role: "du",
        }),
      });
      if (!j?.ok) throw new Error(j?.error || "创建失败");
      toast("已加入渡的一天，并联动闹钟/日历");
      setTitle("");
      setDatetime("");
      setNote("");
      await load();
    } catch (e: any) {
      toast(`创建失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="neo-panel p-3 space-y-2">
        <div className="text-xs text-cream-muted">渡的一天：随时新增想做的事，并设置提醒</div>
        <input
          className="neo-input"
          placeholder="例如：写日记 / 整理 Notion / 逛论坛"
          value={title}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTitle(e.target.value)}
          disabled={saving}
        />
        <input
          type="datetime-local"
          className="neo-input"
          value={datetime}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDatetime(e.target.value)}
          disabled={saving}
        />
        <input
          className="neo-input"
          placeholder="备注（可选）"
          value={note}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNote(e.target.value)}
          disabled={saving}
        />
        <Btn kind="pink" onClick={create} disabled={saving}>
          {saving ? "保存中..." : "加入渡的一天"}
        </Btn>
      </div>

      <div className="neo-panel p-3">
        <div className="neo-tag-yellow">
          渡创建的提醒 · {duItems.length}
        </div>
        <div className="mt-3 space-y-2">
          {duItems.map((it) => (
            <div key={String(it.id || "")} className="neo-panel-soft p-3">
              <div className="text-sm font-medium text-cream-text">{it.title || "未命名事项"}</div>
              <div className="mt-1 text-xs text-cream-muted">{fmtDate(String(it.datetime || ""))} · {it.enabled === false ? "已禁用" : "启用中"}</div>
              {it.note ? <div className="mt-1 text-xs text-cream-muted">{it.note}</div> : null}
            </div>
          ))}
          {!duItems.length && !loading ? <div className="text-xs text-cream-muted">还没有渡自己安排的事项。</div> : null}
        </div>
      </div>
    </div>
  );
}

