import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type XiaoAIConfig = {
  enabled?: boolean;
  entry_phrases?: string[];
  exit_phrases?: string[];
  updated_at?: string;
};

type XiaoAIStatus = {
  online?: boolean;
  connected?: boolean;
  last_seen_at?: string;
  runner?: string;
  speaker?: string;
  last_event?: string;
  last_text?: string;
  last_error?: string;
  last_audio_url?: string;
  last_message_at?: string;
};

type XiaoAILog = {
  id?: string;
  at?: string;
  level?: string;
  message?: string;
  event?: string;
  runner?: string;
  speaker?: string;
  text?: string;
  error?: string;
  audio_url?: string;
};

type OverviewResp = {
  ok?: boolean;
  config?: XiaoAIConfig;
  status?: XiaoAIStatus;
  logs?: XiaoAILog[];
  error?: string;
};

function joinPhrases(items: string[] | undefined, fallback: string) {
  const values = Array.isArray(items) ? items.map((x) => String(x || "").trim()).filter(Boolean) : [];
  return (values.length ? values : [fallback]).join("\n");
}

function splitPhrases(text: string, fallback: string) {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of String(text || "").replace(/，/g, ",").split(/[\n,]/)) {
    const item = raw.trim().slice(0, 32);
    if (!item || seen.has(item)) continue;
    seen.add(item);
    out.push(item);
    if (out.length >= 8) break;
  }
  return out.length ? out : [fallback];
}

function formatTime(value: string | undefined) {
  const raw = String(value || "").trim();
  if (!raw) return "暂无";
  const match = raw.match(/(\d{2}:\d{2}:\d{2})/);
  return match?.[1] || raw.replace("T", " ").slice(0, 19);
}

function levelClass(level: string | undefined) {
  const lv = String(level || "info").toLowerCase();
  if (lv === "error") return "border-red-200 bg-red-50 text-red-700";
  if (lv === "warn" || lv === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

export function XiaoAISettingsTab() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [entryText, setEntryText] = useState("请求连接渡");
  const [exitText, setExitText] = useState("退出渡");
  const [status, setStatus] = useState<XiaoAIStatus>({});
  const [logs, setLogs] = useState<XiaoAILog[]>([]);
  const [loadError, setLoadError] = useState("");

  async function loadOverview(silent = false) {
    try {
      if (!silent) setLoading(true);
      const data = await apiJson<OverviewResp>("/miniapp-api/xiaoai/overview?limit=120");
      if (!data?.ok) throw new Error(data?.error || "加载失败");
      const cfg = data.config || {};
      setEnabled(!!cfg.enabled);
      setEntryText(joinPhrases(cfg.entry_phrases, "请求连接渡"));
      setExitText(joinPhrases(cfg.exit_phrases, "退出渡"));
      setStatus(data.status || {});
      setLogs(Array.isArray(data.logs) ? data.logs : []);
      setLoadError("");
      if (!silent) toast("小爱音箱状态已刷新");
    } catch (e: any) {
      const msg = e?.message || String(e);
      setLoadError(msg);
      if (!silent) toast(`小爱音箱加载失败：${msg}`);
    } finally {
      setLoading(false);
    }
  }

  async function saveConfig(nextEnabled = enabled) {
    const payload = {
      enabled: nextEnabled,
      entry_phrases: splitPhrases(entryText, "请求连接渡"),
      exit_phrases: splitPhrases(exitText, "退出渡"),
    };
    const prevEnabled = enabled;
    setEnabled(nextEnabled);
    setSaving(true);
    try {
      const data = await apiJson<{ ok?: boolean; config?: XiaoAIConfig; error?: string }>("/miniapp-api/xiaoai/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!data?.ok) throw new Error(data?.error || "保存失败");
      const cfg = data.config || {};
      setEnabled(!!cfg.enabled);
      setEntryText(joinPhrases(cfg.entry_phrases, "请求连接渡"));
      setExitText(joinPhrases(cfg.exit_phrases, "退出渡"));
      toast(cfg.enabled ? "小爱入口已启用" : "小爱入口已关闭");
    } catch (e: any) {
      setEnabled(prevEnabled);
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    void loadOverview(true);
    const timer = window.setInterval(() => {
      void loadOverview(true);
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const online = !!status.online;

  return (
    <div className="min-h-full bg-[#FDFDFD] pb-8">
      <div className="space-y-4 px-1 pt-2">
        <section className="overflow-hidden rounded-[30px] border border-[#ece7dc] bg-[#fffaf0] shadow-[0_18px_45px_-28px_rgba(120,80,30,0.42)]">
          <div className="relative p-5">
            <div className="absolute right-4 top-4 h-16 w-16 rounded-full bg-[#f6d57a]/40 blur-2xl" />
            <div className="relative flex items-start justify-between gap-4">
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-[#b7772d]">XiaoAI Bridge</div>
                <h2 className="mt-2 text-[24px] font-semibold tracking-tight text-[#2f2a1f]">小爱音箱</h2>
                <p className="mt-1 text-[13px] leading-5 text-[#8a7354]">让小爱只当入口，渡负责思考和说话。</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={enabled}
                disabled={saving}
                className={`relative mt-1 h-8 w-[56px] shrink-0 rounded-full transition-colors ${enabled ? "bg-[#2f2a1f]" : "bg-[#e6dccb]"} ${saving ? "opacity-60" : ""}`}
                onClick={() => void saveConfig(!enabled)}
              >
                <span className={`absolute left-1 top-1 h-6 w-6 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-6" : "translate-x-0"}`} />
              </button>
            </div>
            <div className="relative mt-5 grid grid-cols-2 gap-2">
              <div className="rounded-2xl bg-white/70 p-3">
                <div className={`mb-1 h-2 w-2 rounded-full ${online ? "bg-emerald-500" : "bg-slate-300"}`} />
                <div className="text-[12px] font-semibold text-[#3d3528]">{online ? "在线" : "未连接"}</div>
                <div className="mt-1 text-[11px] text-[#9a8463]">最近：{formatTime(status.last_seen_at)}</div>
              </div>
              <div className="rounded-2xl bg-white/70 p-3">
                <div className="text-[11px] text-[#9a8463]">入口音箱</div>
                <div className="mt-1 truncate text-[13px] font-semibold text-[#3d3528]">{status.speaker || "未上报"}</div>
                <div className="mt-1 truncate text-[11px] text-[#9a8463]">{status.runner || "MiGPT Next"}</div>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_12px_28px_-24px_rgba(0,0,0,0.24)]">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-[15px] font-bold text-gray-900">启动指令</h3>
              <p className="mt-1 text-[12px] text-gray-400">一行一个，也可以用逗号隔开。</p>
            </div>
            <button
              type="button"
              className="rounded-full bg-gray-900 px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-50"
              disabled={saving}
              onClick={() => void saveConfig(enabled)}
            >
              保存
            </button>
          </div>
          <label className="block">
            <span className="mb-2 block text-[12px] font-semibold text-gray-500">入口词</span>
            <textarea
              className="min-h-[92px] w-full resize-none rounded-2xl border border-gray-100 bg-gray-50 px-4 py-3 text-[14px] font-medium text-gray-800 outline-none transition focus:border-gray-300 focus:bg-white"
              value={entryText}
              onChange={(e) => setEntryText(e.target.value)}
              placeholder="请求连接渡"
            />
          </label>
          <label className="mt-4 block">
            <span className="mb-2 block text-[12px] font-semibold text-gray-500">退出词</span>
            <textarea
              className="min-h-[72px] w-full resize-none rounded-2xl border border-gray-100 bg-gray-50 px-4 py-3 text-[14px] font-medium text-gray-800 outline-none transition focus:border-gray-300 focus:bg-white"
              value={exitText}
              onChange={(e) => setExitText(e.target.value)}
              placeholder="退出渡"
            />
          </label>
        </section>

        <section className="rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_12px_28px_-24px_rgba(0,0,0,0.24)]">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-[15px] font-bold text-gray-900">连接状态</h3>
              <p className="mt-1 text-[12px] text-gray-400">{loading ? "正在读取..." : loadError || "由 MiGPT Next 上报"}</p>
            </div>
            <button type="button" className="rounded-full bg-gray-100 px-4 py-2 text-[12px] font-semibold text-gray-600" onClick={() => void loadOverview(false)}>
              刷新
            </button>
          </div>
          <div className="grid gap-2 text-[13px]">
            <StatusLine label="最近事件" value={status.last_event || "暂无"} />
            <StatusLine label="最近文本" value={status.last_text || "暂无"} />
            <StatusLine label="最近错误" value={status.last_error || "暂无"} danger={!!status.last_error} />
            <StatusLine label="最近音频" value={status.last_audio_url || "暂无"} />
          </div>
        </section>

        <section className="rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_12px_28px_-24px_rgba(0,0,0,0.24)]">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-[15px] font-bold text-gray-900">小爱日志</h3>
              <p className="mt-1 text-[12px] text-gray-400">最近 {logs.length} 条，最新在上。</p>
            </div>
          </div>
          {logs.length ? (
            <div className="space-y-2">
              {logs.map((item, idx) => (
                <div key={item.id || `${item.at}-${idx}`} className={`rounded-2xl border px-3 py-3 ${levelClass(item.level)}`}>
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <span className="text-[11px] font-bold uppercase tracking-[0.12em]">{item.level || "info"}</span>
                    <span className="shrink-0 text-[11px] opacity-70">{formatTime(item.at)}</span>
                  </div>
                  <div className="text-[13px] font-semibold leading-5">{item.message || item.event || "日志"}</div>
                  {item.text ? <div className="mt-1 line-clamp-2 text-[12px] opacity-80">{item.text}</div> : null}
                  {item.error ? <div className="mt-1 line-clamp-2 text-[12px] font-semibold text-red-700">{item.error}</div> : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl bg-gray-50 px-4 py-6 text-center text-[13px] text-gray-400">还没有小爱日志。等 MiGPT Next 上报第一声。</div>
          )}
        </section>
      </div>
    </div>
  );
}

function StatusLine({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-2xl bg-gray-50 px-4 py-3">
      <div className="mb-1 text-[11px] font-semibold text-gray-400">{label}</div>
      <div className={`break-words text-[13px] font-medium leading-5 ${danger ? "text-red-600" : "text-gray-800"}`}>{value}</div>
    </div>
  );
}
