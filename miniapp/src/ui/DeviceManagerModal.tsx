import { useEffect, useState } from "react";
import { apiJson, getOrCreatePanelDeviceId } from "./api";
import { FullScreenPane } from "./FullScreenPane";
import { inspectLocalChatHistoryRows, migrateLocalChatHistoriesToDevice, type ChatHistoryLocalStatRow } from "./storage/chatHistoryDb";
import { useToast } from "./toast";

type DeviceItem = {
  id?: string;
  note?: string;
  added_at?: string;
  last_seen?: string;
  revoked?: boolean;
  current?: boolean;
};

type RemoteHistoryStatRow = {
  key?: string;
  device_id?: string;
  window_id?: string;
  count?: number;
  updated_at?: string;
  current?: boolean;
};

type HistoryDiagnostics = {
  deviceId: string;
  localRows: ChatHistoryLocalStatRow[];
  remoteRows: RemoteHistoryStatRow[];
};

export function DeviceManagerModal({ onClose, onLogout }: { onClose: () => void; onLogout?: () => void }) {
  const toast = useToast();
  const [items, setItems] = useState<DeviceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [checkingHistory, setCheckingHistory] = useState(false);
  const [historyDiagnostics, setHistoryDiagnostics] = useState<HistoryDiagnostics | null>(null);

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

  async function checkHistoryStorage(showToast = true) {
    setCheckingHistory(true);
    try {
      const did = await getOrCreatePanelDeviceId();
      await migrateLocalChatHistoriesToDevice(did);
      const localRows = await inspectLocalChatHistoryRows();
      const remote = await apiJson<{ ok?: boolean; rows?: RemoteHistoryStatRow[] }>("/miniapp-api/sumitalk-history/stats");
      const remoteRows = Array.isArray(remote?.rows) ? remote.rows : [];
      setHistoryDiagnostics({ deviceId: did, localRows, remoteRows });
      if (showToast) {
        const localTotal = localRows.reduce((sum, row) => sum + Number(row.count || 0), 0);
        const remoteTotal = remoteRows.reduce((sum, row) => sum + Number(row.count || 0), 0);
        toast(localTotal || remoteTotal ? `查到了：本地 ${localTotal} 条，云端 ${remoteTotal} 条` : "本地和云端都没查到聊天记录");
      }
    } catch (e: any) {
      toast(`检查聊天记录失败：${e?.message || e}`);
    } finally {
      setCheckingHistory(false);
    }
  }

  async function migrateRemoteHistoryFrom(oldDeviceId: string) {
    const from = String(oldDeviceId || "").trim();
    const to = String(historyDiagnostics?.deviceId || "").trim();
    if (!from || !to || from === to) return;
    const ok = window.confirm("把这台旧设备的云端聊天记录合并到当前设备吗？");
    if (!ok) return;
    setBusyId(from);
    try {
      const j = await apiJson<{ ok?: boolean; count?: number; error?: string }>("/miniapp-api/sumitalk-history/migrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_device_id: from, new_device_id: to }),
      });
      if (!j?.ok) throw new Error(j?.error || "迁移失败");
      toast(`已合并云端记录：${Number(j.count || 0)} 条`);
      await checkHistoryStorage(false);
    } catch (e: any) {
      toast(`迁移失败：${e?.message || e}`);
    } finally {
      setBusyId("");
    }
  }

  const currentItem = items.find((it) => !!it.current) || null;
  const otherItems = items.filter((it) => !it.current);
  const localHistoryTotal = (historyDiagnostics?.localRows || []).reduce((sum, row) => sum + Number(row.count || 0), 0);
  const remoteHistoryTotal = (historyDiagnostics?.remoteRows || []).reduce((sum, row) => sum + Number(row.count || 0), 0);
  const remoteOtherHistoryRows = Array.from(
    new Map(
      (historyDiagnostics?.remoteRows || [])
        .filter((row) => String(row.device_id || "").trim() && String(row.device_id || "").trim() !== historyDiagnostics?.deviceId && Number(row.count || 0) > 0)
        .map((row) => [String(row.device_id || "").trim(), row]),
    ).values(),
  );

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
            <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">聊天记录诊断</h2>
            <button
              type="button"
              onClick={() => void checkHistoryStorage(true)}
              disabled={checkingHistory}
              className="rounded-full px-3 py-1.5 text-[12px] font-semibold text-blue-500 transition active:bg-blue-50 disabled:opacity-60"
            >
              {checkingHistory ? "检查中..." : "检查/修复"}
            </button>
          </div>
          <div className="rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
            {historyDiagnostics ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-gray-50 px-4 py-3">
                    <div className="text-[11px] font-bold text-gray-400">本地 IndexedDB</div>
                    <div className="mt-1 text-[22px] font-bold text-gray-800">{localHistoryTotal}</div>
                  </div>
                  <div className="rounded-2xl bg-gray-50 px-4 py-3">
                    <div className="text-[11px] font-bold text-gray-400">云端 R2</div>
                    <div className="mt-1 text-[22px] font-bold text-gray-800">{remoteHistoryTotal}</div>
                  </div>
                </div>
                <div className="mt-4 break-all rounded-2xl bg-blue-50 px-4 py-3 text-[12px] leading-5 text-blue-500">
                  当前设备：{historyDiagnostics.deviceId || "-"}
                </div>
                <div className="mt-4 space-y-2">
                  {[...historyDiagnostics.localRows.slice(0, 4), ...historyDiagnostics.remoteRows.slice(0, 4)].map((row, idx) => {
                    const isLocal = "deviceId" in row;
                    const did = isLocal ? String((row as ChatHistoryLocalStatRow).deviceId || "") : String((row as RemoteHistoryStatRow).device_id || "");
                    const wid = isLocal ? String((row as ChatHistoryLocalStatRow).windowId || "") : String((row as RemoteHistoryStatRow).window_id || "");
                    const count = Number((row as any).count || 0);
                    return (
                      <div key={`${isLocal ? "local" : "remote"}-${idx}-${did}-${wid}`} className="flex items-center justify-between gap-3 rounded-2xl bg-gray-50 px-4 py-3 text-[12px]">
                        <div className="min-w-0">
                          <div className="font-semibold text-gray-700">{isLocal ? "本地" : "云端"} · {wid || "default"}</div>
                          <div className="truncate text-gray-400">{did || "-"}</div>
                        </div>
                        <div className="shrink-0 font-bold text-gray-700">{count} 条</div>
                      </div>
                    );
                  })}
                </div>
                {remoteOtherHistoryRows.length ? (
                  <div className="mt-4 space-y-2">
                    {remoteOtherHistoryRows.slice(0, 3).map((row) => {
                      const did = String(row.device_id || "").trim();
                      return (
                        <button
                          key={`${did}-${row.window_id}`}
                          type="button"
                          onClick={() => void migrateRemoteHistoryFrom(did)}
                          disabled={busyId === did}
                          className="w-full rounded-2xl bg-amber-50 px-4 py-3 text-left text-[12px] font-semibold text-amber-700 transition active:scale-[0.99] disabled:opacity-60"
                        >
                          {busyId === did ? "合并中..." : `合并旧设备 ${did.slice(0, 10)}... 的云端记录`}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="text-[13px] leading-6 text-gray-400">点一下检查，就能看到本机本地库是不是空的，以及云端还有没有旧设备记录。</div>
            )}
          </div>
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
