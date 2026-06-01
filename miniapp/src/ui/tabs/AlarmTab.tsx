import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { HeaderPortal, HeaderStatusPill } from "../components";
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

function fmtDateTimeParts(v: string): { hm: string; rel: string; full: string } {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) {
    return {
      hm: "--:--",
      rel: "未知",
      full: v || "",
    };
  }
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const full = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${hm}`;
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const targetStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((targetStart - todayStart) / (24 * 60 * 60 * 1000));
  const rel =
    diffDays === 0
      ? "今天"
      : diffDays === 1
        ? "明天"
        : diffDays === -1
          ? "昨天"
          : diffDays > 1
            ? `${diffDays}天后`
            : `${Math.abs(diffDays)}天前`;
  return { hm, rel, full };
}

export function AlarmTab() {
  const toast = useToast();
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [togglingId, setTogglingId] = useState("");
  const [deletingId, setDeletingId] = useState("");

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<ScheduleResp>("/miniapp-api/schedule/items");
      setItems(normalizeItems(j?.items));
      setLoadError("");
    } catch (e: any) {
      setLoadError(e?.message || String(e));
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
  const enabledItems = useMemo(() => alarmItems.filter((it) => it.enabled !== false), [alarmItems]);
  const disabledItems = useMemo(() => alarmItems.filter((it) => it.enabled === false), [alarmItems]);

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
      toast("已删除");
      setDeletingId("");
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  return (
    <div className="relative bg-[#FDFDFD]">
      <style>{`
        .alarm-card { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .alarm-card:active { transform: scale(0.98); }
        .status-badge {
          padding: 2px 8px;
          border-radius: 6px;
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
        }
        .switch { position: relative; display: inline-block; width: 42px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #E2E8F0; transition: .4s; border-radius: 24px; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%; }
        .switch input:checked + .slider { background-color: #4A5568; }
        .switch input:checked + .slider:before { transform: translateX(18px); }
        .modal-overlay { background-color: rgba(0, 0, 0, 0.4); backdrop-filter: blur(4px); }
      `}</style>
      <HeaderPortal targetId="alarm-header-status">
        <HeaderStatusPill text={loadError ? "同步异常" : "渡 已同步"} dotClassName={loadError ? "bg-red-400" : "bg-green-400"} />
      </HeaderPortal>

      {loadError ? (
        <div className="mb-4 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-500">
          数据同步遇到了一点问题：{loadError}
        </div>
      ) : null}

      <div className="space-y-7 px-1">
        <section>
          <div className="mb-4 flex items-center justify-between px-1">
            <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">启用中</h2>
            <span className="rounded-md bg-blue-50 px-2 py-0.5 text-[11px] font-bold text-blue-500">{enabledItems.length}</span>
          </div>
          <div className="space-y-4">
            {enabledItems.map((it) => {
              const id = String(it.id || "");
              const p = fmtDateTimeParts(String(it.datetime || ""));
              return (
                <div key={id} className="alarm-card group relative overflow-hidden rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.04)]">
                  <div className="mb-1 flex items-start justify-between">
                    <div>
                      <span className="status-badge bg-blue-50 text-blue-500">启用中</span>
                      <div className="mt-2 flex items-baseline space-x-2">
                        <span className="text-[32px] font-bold leading-none text-gray-800">{p.hm}</span>
                        <span className="text-[13px] font-medium text-gray-400">{p.rel}</span>
                      </div>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={it.enabled !== false}
                        disabled={!id || togglingId === id}
                        onChange={(e) => setEnabled(id, e.target.checked)}
                      />
                      <span className="slider" />
                    </label>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <div>
                      <p className="text-[14px] font-light text-gray-500">{it.title || "未命名闹钟"}</p>
                      {it.note ? <p className="mt-1 text-[12px] font-light text-gray-400">{it.note}</p> : null}
                      <p className="mt-1 text-[11px] text-gray-400">{p.full}</p>
                    </div>
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
        </section>

        <section>
          <div className="mb-4 flex items-center justify-between px-1">
            <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">已停用</h2>
          </div>
          <div className="space-y-4 opacity-60">
            {disabledItems.map((it) => {
              const id = String(it.id || "");
              const p = fmtDateTimeParts(String(it.datetime || ""));
              return (
                <div key={id} className="alarm-card group rounded-[28px] border border-gray-100 bg-gray-50/50 p-5">
                  <div className="mb-1 flex items-start justify-between">
                    <div>
                      <span className="status-badge bg-gray-100 text-gray-400">已停用</span>
                      <div className="mt-2 flex items-baseline space-x-2">
                        <span className="text-[32px] font-bold leading-none text-gray-400">{p.hm}</span>
                        <span className="text-[13px] font-medium text-gray-400">{p.rel}</span>
                      </div>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={it.enabled !== false}
                        disabled={!id || togglingId === id}
                        onChange={(e) => setEnabled(id, e.target.checked)}
                      />
                      <span className="slider" />
                    </label>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <div>
                      <p className="text-[14px] font-light text-gray-400">{it.title || "未命名闹钟"}</p>
                      {it.note ? <p className="mt-1 text-[12px] font-light text-gray-400">{it.note}</p> : null}
                      <p className="mt-1 text-[11px] text-gray-400">{p.full}</p>
                    </div>
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
        </section>
      </div>

      {!loading && !loadError && !alarmItems.length ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-orange-50">
            <svg className="h-10 w-10 text-orange-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              <path d="M18.63 13A17.89 17.89 0 0 1 18 8" />
              <path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14" />
              <path d="M18 8a6 6 0 0 0-9.33-5" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </svg>
          </div>
          <h3 className="mb-2 text-[18px] font-medium text-gray-800">暂无一次性提醒</h3>
          <p className="px-10 text-[14px] leading-relaxed text-gray-400">
            你可以试着和渡说：
            <br />
            “半小时后提醒我出门”
          </p>
        </div>
      ) : null}

      {deletingId ? (
        <div className="modal-overlay fixed inset-0 z-[100] flex items-center justify-center px-8">
          <div className="w-full max-w-sm rounded-[32px] bg-white p-8 shadow-2xl">
            <h3 className="mb-3 text-center text-[20px] font-semibold text-gray-900">要删除这个提醒吗？</h3>
            <p className="mb-8 px-2 text-center text-[15px] font-light text-gray-500">删除后将无法恢复，渡也不会再在这个时间点提醒你。</p>
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
    </div>
  );
}
