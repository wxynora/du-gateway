import { useEffect, useState } from "react";
import { apiJson } from "./api";
import { FullScreenPane } from "./FullScreenPane";
import { useToast } from "./toast";

type DeviceItem = {
  id?: string;
  note?: string;
  added_at?: string;
  last_seen?: string;
  revoked?: boolean;
  current?: boolean;
};

export function DeviceManagerModal({ onClose, onLogout }: { onClose: () => void; onLogout?: () => void }) {
  const toast = useToast();
  const [items, setItems] = useState<DeviceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; items?: DeviceItem[] }>("/miniapp-api/panel-auth/list");
      const next = Array.isArray(j?.items) ? j.items.filter((it) => !it?.revoked) : [];
      setItems(next);
    } catch (e: any) {
      toast(`加载设备失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function revoke(deviceId: string, current: boolean) {
    if (!deviceId) return;
    const ok = window.confirm(current ? "撤销当前浏览器后会立刻退出，继续吗？" : "确认撤销这个浏览器的访问权限吗？");
    if (!ok) return;
    setBusyId(deviceId);
    try {
      const j = await apiJson<{ ok?: boolean; revoked_current?: boolean }>("/miniapp-api/panel-auth/revoke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: deviceId }),
      });
      if (!j?.ok) throw new Error("撤销失败");
      if (j.revoked_current) {
        toast("当前浏览器已被撤销");
        onClose();
        onLogout?.();
        return;
      }
      toast("设备已删除");
      setItems((prev) => prev.filter((it) => String(it.id || "") !== deviceId));
    } catch (e: any) {
      toast(`撤销失败：${e?.message || e}`);
    } finally {
      setBusyId("");
    }
  }

  const currentItem = items.find((it) => !!it.current) || null;
  const otherItems = items.filter((it) => !it.current);

  function getDeviceIcon(item: DeviceItem): "phone" | "tablet" | "desktop" {
    const note = String(item.note || "").toLowerCase();
    if (note.includes("ipad") || note.includes("tablet")) return "tablet";
    if (note.includes("iphone") || note.includes("android") || note.includes("mobile")) return "phone";
    return "desktop";
  }

  function getDeviceTitle(item: DeviceItem): string {
    return String(item.note || "设备").replace(/\s*@\s*.+$/, "").trim() || "设备";
  }

  function getDeviceSubtitle(item: DeviceItem): string {
    const note = String(item.note || "").trim();
    const m = note.match(/@\s*(.+)$/);
    return m?.[1]?.trim() || "SumiTalk";
  }

  function renderDeviceIcon(kind: "phone" | "tablet" | "desktop", active = false) {
    const cls = active ? "text-blue-500" : "text-gray-400";
    if (kind === "phone") {
      return (
        <svg className={`h-6 w-6 ${cls}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="5" y="2" width="14" height="20" rx="2" ry="2" />
          <line x1="12" y1="18" x2="12.01" y2="18" />
        </svg>
      );
    }
    if (kind === "tablet") {
      return (
        <svg className={`h-6 w-6 ${cls}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4" y="2" width="16" height="20" rx="2" ry="2" />
          <line x1="12" y1="18" x2="12.01" y2="18" />
        </svg>
      );
    }
    return (
      <svg className={`h-6 w-6 ${cls}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
    );
  }

  return (
    <FullScreenPane title="设备管理" accent="neutral" onBack={onClose} edgeSwipeBack>
      <div className="px-2 pb-8 pt-2">
        <div className="px-1 pt-4">
          <div className="mb-4 flex items-center justify-between px-1">
            <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">当前使用的设备</h2>
          </div>

          {currentItem ? (
            <div className="relative overflow-hidden rounded-[28px] border border-gray-100/80 border-l-4 border-l-blue-500 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
              <div className="flex items-start">
                <div className="mr-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50">
                  {renderDeviceIcon(getDeviceIcon(currentItem), true)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-bold text-blue-500">正在使用</span>
                    <span className="text-[12px] font-medium text-gray-400">{currentItem.last_seen || "刚刚"}</span>
                  </div>
                  <h3 className="mt-1 text-[18px] font-bold text-gray-800">{getDeviceTitle(currentItem)}</h3>
                  <p className="mt-1 text-[13px] font-light text-gray-500">{getDeviceSubtitle(currentItem)}</p>
                </div>
              </div>
            </div>
          ) : !loading ? (
            <div className="rounded-[24px] border border-gray-100 bg-white px-5 py-4 text-[13px] text-gray-400 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
              当前没有可识别设备。
            </div>
          ) : null}
        </div>

        <div className="mt-8 px-1">
          <div className="mb-4 flex items-center justify-between px-1">
            <div className="flex items-baseline gap-2">
              <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">其他授信设备</h2>
              <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-500">{otherItems.length}</span>
            </div>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="rounded-full px-3 py-1.5 text-[12px] font-semibold text-gray-400 transition active:bg-gray-50"
            >
              {loading ? "刷新中..." : "刷新"}
            </button>
          </div>

          {otherItems.length ? (
            <div className="space-y-4">
              {otherItems.map((item) => {
                const id = String(item.id || "");
                return (
                  <div key={id} className="group rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
                    <div className="flex items-start">
                      <div className="mr-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gray-50">
                        {renderDeviceIcon(getDeviceIcon(item))}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <span className="rounded-full bg-green-50 px-2.5 py-1 text-[10px] font-bold text-green-500">正常</span>
                          <span className="text-[12px] font-medium text-gray-400">{item.last_seen || "-"}</span>
                        </div>
                        <h3 className="mt-1 text-[17px] font-bold text-gray-800">{getDeviceTitle(item)}</h3>
                        <div className="mt-3 flex items-center justify-between gap-3">
                          <p className="text-[13px] font-light text-gray-500">{getDeviceSubtitle(item)}</p>
                          <button
                            type="button"
                            onClick={() => void revoke(id, false)}
                            disabled={busyId === id}
                            className="rounded-full bg-red-50 px-3 py-1 text-[13px] font-semibold text-red-400 transition active:scale-95 disabled:opacity-60"
                          >
                            {busyId === id ? "处理中..." : "撤销"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : !loading ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-blue-50">
                <svg className="h-10 w-10 text-blue-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <h3 className="mb-2 text-[18px] font-medium text-gray-800">暂无其他设备</h3>
              <p className="px-10 text-[14px] leading-relaxed text-gray-400">当前仅有这一台设备连接到你的 SumiTalk 账号</p>
            </div>
          ) : null}
        </div>
      </div>
    </FullScreenPane>
  );
}
