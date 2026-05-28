import React, { useCallback, useEffect, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type UpstreamItem = { name: string; url: string };
type UpstreamsResp = { active: number; model?: string; claude_thinking_effort?: string; claude_thinking_efforts?: string[]; items: UpstreamItem[] };
type ProbeItem = {
  index: number;
  isActive: boolean;
  status: "ok" | "degraded" | "fail";
  models_ok: boolean;
  chat_ok: boolean;
  models_status: number;
  chat_status: number;
  model_count: number;
  error?: string;
  note?: string;
};
type ProbeResp = { ok: boolean; status: "ok" | "degraded" | "fail"; results: ProbeItem[]; count: number };
type ActivePutResp = { ok?: boolean; error?: string; active?: number; model?: string; claude_thinking_effort?: string };
type ModelsResp = { ok?: boolean; error?: string; active?: number; index?: number; model?: string; models?: string[] };
type ModelPutResp = { ok?: boolean; error?: string; active?: number; model?: string; claude_thinking_effort?: string };
type ThinkingEffortPutResp = { ok?: boolean; error?: string; active?: number; effort?: string };

const DEFAULT_THINKING_EFFORTS = ["low", "medium", "high", "xhigh", "max"];

function hostFromUrl(url: string): string {
  const raw = String(url || "").trim();
  if (!raw) return "—";
  try {
    const u = new URL(raw.includes("://") ? raw : `https://${raw}`);
    return u.hostname || "—";
  } catch {
    return raw.replace(/^https?:\/\//i, "").split("/")[0] || "—";
  }
}

function pathHint(url: string): string {
  try {
    const u = new URL(String(url || "").trim().includes("://") ? String(url).trim() : `https://${String(url).trim()}`);
    const p = u.pathname || "";
    if (!p || p === "/") return "";
    return p.length > 28 ? `${p.slice(0, 26)}…` : p;
  } catch {
    return "";
  }
}

function probeStatusLabel(p?: ProbeItem): string {
  if (!p) return "未探测";
  if (p.status === "ok") return "探活正常";
  if (p.status === "degraded") return "部分异常";
  return "不可用";
}

function probeStatusBadgeClass(p?: ProbeItem): string {
  if (!p) return "bg-gray-100 text-gray-600";
  if (p.status === "ok") return "bg-green-100 text-green-700";
  if (p.status === "degraded") return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-700";
}

function isClaudeAdaptiveModel(model: string): boolean {
  return /claude-opus-4-(7|8)(\b|-|$)/i.test(String(model || "").trim());
}

export function SettingsUpstream() {
  const toast = useToast();
  const [active, setActive] = useState(0);
  const [items, setItems] = useState<UpstreamItem[]>([]);
  const [probes, setProbes] = useState<Record<number, ProbeItem>>({});
  const [probingAll, setProbingAll] = useState(false);
  const [probingIndex, setProbingIndex] = useState<number | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingIndex, setPendingIndex] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [currentModel, setCurrentModel] = useState("");
  const [pendingModel, setPendingModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelSaving, setModelSaving] = useState(false);
  const [thinkingEffort, setThinkingEffort] = useState("high");
  const [pendingThinkingEffort, setPendingThinkingEffort] = useState("high");
  const [thinkingEffortOptions, setThinkingEffortOptions] = useState<string[]>(DEFAULT_THINKING_EFFORTS);
  const [thinkingEffortSaving, setThinkingEffortSaving] = useState(false);

  const loadModels = useCallback(async (index?: number) => {
    setModelsLoading(true);
    try {
      const q = typeof index === "number" ? `?index=${index}` : "";
      const j = await apiJson<ModelsResp>(`/miniapp-api/upstreams/models${q}`);
      if (!j?.ok) throw new Error(j?.error || "加载模型失败");
      const nextModels = Array.isArray(j.models) ? j.models.filter(Boolean) : [];
      const selected = String(j.model || "").trim();
      setModels(nextModels);
      setCurrentModel(selected);
      setPendingModel(selected || nextModels[0] || "");
    } catch (e: any) {
      setModels([]);
      toast(`模型列表加载失败：${e?.message || e}`);
    } finally {
      setModelsLoading(false);
    }
  }, [toast]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const j = await apiJson<UpstreamsResp>("/miniapp-api/upstreams");
      const nextActive = Number(j.active || 0);
      const nextModel = String(j.model || "").trim();
      const nextItems = Array.isArray(j.items) ? j.items : [];
      const nextEffort = String(j.claude_thinking_effort || "high").trim() || "high";
      setActive(nextActive);
      setItems(nextItems);
      setCurrentModel(nextModel);
      setPendingModel(nextModel);
      setThinkingEffort(nextEffort);
      setPendingThinkingEffort(nextEffort);
      setThinkingEffortOptions(Array.isArray(j.claude_thinking_efforts) && j.claude_thinking_efforts.length ? j.claude_thinking_efforts : DEFAULT_THINKING_EFFORTS);
      if (nextItems.length) {
        await loadModels(nextActive);
      } else {
        setModels([]);
      }
    } catch (e: any) {
      setLoadError(e?.message || String(e));
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [loadModels, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  async function probeAll() {
    if (!items.length) return;
    try {
      setProbingAll(true);
      const r = await apiJson<ProbeResp>("/miniapp-api/upstreams/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ all: true }),
      });
      const next: Record<number, ProbeItem> = {};
      for (const it of r.results || []) next[it.index] = it;
      setProbes(next);
      toast(r.status === "ok" ? "探活完成" : "探活完成（含异常）");
    } catch (e: any) {
      toast(`探活失败：${e?.message || e}`);
    } finally {
      setProbingAll(false);
    }
  }

  async function probeOne(index: number) {
    try {
      setProbingIndex(index);
      const r = await apiJson<ProbeResp>("/miniapp-api/upstreams/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index }),
      });
      const one = (r.results || [])[0];
      if (one) setProbes((prev) => ({ ...prev, [index]: one }));
    } catch (e: any) {
      toast(`探活失败：${e?.message || e}`);
    } finally {
      setProbingIndex(null);
    }
  }

  async function confirmSwitch() {
    if (pendingIndex === null || pendingIndex === active) return;
    setSubmitting(true);
    try {
      const r = await apiJson<ActivePutResp>("/miniapp-api/upstreams/active", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: pendingIndex }),
      });
      if (!r?.ok) throw new Error(r?.error || "切换失败");
      const name = hostFromUrl(items[pendingIndex]?.url || "");
      toast(`已切换到 ${name}`);
      const nextModel = String(r.model || "").trim();
      setCurrentModel(nextModel);
      setPendingModel(nextModel);
      const nextEffort = String(r.claude_thinking_effort || thinkingEffort).trim() || thinkingEffort;
      setThinkingEffort(nextEffort);
      setPendingThinkingEffort(nextEffort);
      setPendingIndex(null);
      await load();
      await probeOne(Number(r.active ?? pendingIndex));
    } catch (e: any) {
      toast(`切换失败：${e?.message || e}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function saveModel() {
    const model = String(pendingModel || "").trim();
    if (!model || model === currentModel) return;
    setModelSaving(true);
    try {
      const r = await apiJson<ModelPutResp>("/miniapp-api/upstreams/model", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model }),
      });
      if (!r?.ok) throw new Error(r?.error || "保存失败");
      const nextModel = String(r.model || model).trim();
      setCurrentModel(nextModel);
      setPendingModel(nextModel);
      const nextEffort = String(r.claude_thinking_effort || thinkingEffort).trim() || thinkingEffort;
      setThinkingEffort(nextEffort);
      setPendingThinkingEffort(nextEffort);
      toast(`已切换模型：${nextModel}`);
    } catch (e: any) {
      toast(`模型保存失败：${e?.message || e}`);
    } finally {
      setModelSaving(false);
    }
  }

  async function saveThinkingEffort() {
    const effort = String(pendingThinkingEffort || "").trim().toLowerCase();
    if (!effort || effort === thinkingEffort) return;
    setThinkingEffortSaving(true);
    try {
      const r = await apiJson<ThinkingEffortPutResp>("/miniapp-api/upstreams/claude-thinking-effort", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ effort }),
      });
      if (!r?.ok) throw new Error(r?.error || "保存失败");
      const nextEffort = String(r.effort || effort).trim() || effort;
      setThinkingEffort(nextEffort);
      setPendingThinkingEffort(nextEffort);
      toast(`已切换 thinking：${nextEffort}`);
    } catch (e: any) {
      toast(`thinking 保存失败：${e?.message || e}`);
    } finally {
      setThinkingEffortSaving(false);
    }
  }

  const activeItem = items[active];
  const activeHost = activeItem ? hostFromUrl(activeItem.url) : "—";
  const activeProbe = probes[active];
  const pendingHost = pendingIndex !== null && items[pendingIndex] ? hostFromUrl(items[pendingIndex].url) : "";
  const canConfirm = pendingIndex !== null && pendingIndex !== active && !submitting && !loading && items.length > 0;
  const canSaveModel = !!pendingModel && pendingModel !== currentModel && !modelSaving && !modelsLoading;
  const modelOptions = pendingModel && !models.includes(pendingModel) ? [pendingModel, ...models] : models;
  const adaptiveThinkingActive = isClaudeAdaptiveModel(pendingModel || currentModel);
  const canSaveThinkingEffort = adaptiveThinkingActive && !!pendingThinkingEffort && pendingThinkingEffort !== thinkingEffort && !thinkingEffortSaving;

  function renderProbeCodes(p?: ProbeItem) {
    if (!p) {
      return <span className="text-[12px] font-medium text-gray-400">未探测 · 可点「一键探活」</span>;
    }
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] font-mono text-gray-700">
        <span>
          models <span className="font-bold">{p.models_status || "—"}</span>
        </span>
        <span className="text-gray-300">·</span>
        <span>
          chat <span className="font-bold">{p.chat_status || "—"}</span>
        </span>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-[#F3F4F6] pb-44 text-gray-900">
      <style>{`
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .glass-footer {
          background: rgba(255,255,255,.88);
          backdrop-filter: blur(12px);
          border-top: 1px solid rgba(229,231,235,.6);
        }
        .card-pick { transition: border-color .2s ease, box-shadow .2s ease, background-color .2s ease; }
        .card-pick-selected {
          box-shadow: 0 0 0 2px #3b82f6, 0 10px 15px -3px rgba(59,130,246,.12);
          border-color: #3b82f6 !important;
          background-color: rgba(239,246,255,.5);
        }
      `}</style>

      <main className="hide-scrollbar space-y-8 overflow-y-auto px-5 pt-2 pb-4">
        <p className="px-1 text-[12px] leading-relaxed text-gray-500">
          切换的是网关<strong>全局默认上游</strong>。列表来自部署环境；手机端不能改 URL/密钥。点选节点后需按底部<strong>确认</strong>才会生效。
        </p>

        {loadError ? (
          <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-4 text-[13px] text-red-600">
            <div className="font-semibold">加载失败</div>
            <div className="mt-1 break-words">{loadError}</div>
            <button
              type="button"
              className="mt-3 rounded-xl bg-red-600 px-4 py-2 text-[13px] font-semibold text-white active:opacity-90"
              onClick={() => void load()}
            >
              重试
            </button>
          </div>
        ) : null}

        {!loading && !loadError && !items.length ? (
          <div className="rounded-2xl border border-dashed border-gray-200 bg-white/80 px-4 py-8 text-center text-[13px] text-gray-500">
            当前没有可用上游（环境未配置）。请联系部署检查上游列表。
          </div>
        ) : null}

        {!loadError && items.length > 0 ? (
          <>
            <section>
              <div className="mb-4 flex items-center justify-between px-1">
                <span className="text-[11px] font-bold uppercase tracking-widest text-gray-400">当前活跃节点</span>
                <span className={`flex items-center gap-1.5 rounded-full px-2 py-1 text-[10px] font-bold ${probeStatusBadgeClass(activeProbe)}`}>
                  {activeProbe ? <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" /> : null}
                  {probeStatusLabel(activeProbe)}
                </span>
              </div>

              <div className="relative overflow-hidden rounded-3xl border border-gray-100 bg-white p-6 shadow-sm">
                <div className="mb-1">
                  <h2 className="text-2xl font-extrabold leading-tight text-gray-900">{activeHost}</h2>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    {activeItem?.name ? (
                      <span className="text-[13px] font-medium text-gray-500">{activeItem.name}</span>
                    ) : null}
                    {activeItem?.name && pathHint(activeItem.url) ? <span className="h-1 w-1 rounded-full bg-gray-300" /> : null}
                    {pathHint(activeItem?.url || "") ? (
                      <code className="rounded bg-blue-50 px-2 py-0.5 text-[12px] font-semibold text-blue-600">{pathHint(activeItem?.url || "")}</code>
                    ) : null}
                  </div>
                </div>
                <div className="mt-5 border-t border-gray-50 pt-5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[11px] font-bold uppercase tracking-widest text-gray-400">运行模型</p>
                      <p className="mt-1 truncate text-[13px] font-semibold text-gray-700">{currentModel || "—"}</p>
                    </div>
                    <button
                      type="button"
                      disabled={!canSaveModel}
                      onClick={() => void saveModel()}
                      className="h-8 shrink-0 rounded-full bg-blue-600 px-3 text-[12px] font-bold text-white shadow-sm shadow-blue-100 active:scale-[0.98] disabled:bg-gray-100 disabled:text-gray-400 disabled:shadow-none"
                    >
                      {modelSaving ? "保存中" : "保存"}
                    </button>
                  </div>
                  <div className="relative mt-3">
                    <select
                      value={pendingModel}
                      disabled={modelsLoading || modelSaving || !models.length}
                      onChange={(e) => setPendingModel(e.target.value)}
                      className="h-11 w-full appearance-none rounded-2xl border border-gray-100 bg-gray-50 px-3 pr-9 text-[13px] font-semibold text-gray-800 outline-none disabled:text-gray-400"
                    >
                      {!modelOptions.length ? <option value="">{modelsLoading ? "加载中…" : "未拉到模型"}</option> : null}
                      {modelOptions.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                    <svg className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                  <div className="mt-4 rounded-2xl border border-gray-100 bg-gray-50 px-3 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[11px] font-bold uppercase tracking-widest text-gray-400">Adaptive Thinking</p>
                        <p className="mt-0.5 text-[12px] font-semibold text-gray-500">{adaptiveThinkingActive ? "Claude 4.8 / 4.7" : "仅 4.8 / 4.7 生效"}</p>
                      </div>
                      <button
                        type="button"
                        disabled={!canSaveThinkingEffort}
                        onClick={() => void saveThinkingEffort()}
                        className="h-8 shrink-0 rounded-full bg-gray-900 px-3 text-[12px] font-bold text-white active:scale-[0.98] disabled:bg-gray-100 disabled:text-gray-400"
                      >
                        {thinkingEffortSaving ? "保存中" : "保存"}
                      </button>
                    </div>
                    <div className="relative mt-3">
                      <select
                        value={pendingThinkingEffort}
                        disabled={!adaptiveThinkingActive || thinkingEffortSaving}
                        onChange={(e) => setPendingThinkingEffort(e.target.value)}
                        className="h-10 w-full appearance-none rounded-xl border border-gray-100 bg-white px-3 pr-9 text-[13px] font-semibold text-gray-800 outline-none disabled:text-gray-400"
                      >
                        {thinkingEffortOptions.map((effort) => (
                          <option key={effort} value={effort}>
                            {effort}
                          </option>
                        ))}
                      </select>
                      <svg className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </div>
                  </div>
                  <p className="mt-5 text-[11px] font-medium text-gray-400">探活（HTTP）</p>
                  <div className="mt-1">{renderProbeCodes(activeProbe)}</div>
                  {activeProbe?.note ? <p className="mt-2 break-words text-[12px] text-amber-700">{activeProbe.note}</p> : null}
                  {activeProbe?.error ? (
                    <p className={"mt-1 break-words text-[12px] " + (activeProbe.status === "degraded" ? "text-amber-700" : "text-red-600")}>{activeProbe.error}</p>
                  ) : null}
                </div>
              </div>
            </section>

            <section>
              <div className="mb-5 flex items-center justify-between px-1">
                <h3 className="text-[11px] font-bold uppercase tracking-widest text-gray-400">可选备选节点</h3>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-bold text-blue-600 active:opacity-80 disabled:opacity-40"
                    onClick={() => void probeAll()}
                    disabled={probingAll || probingIndex !== null}
                  >
                    {probingAll ? "探活中…" : "一键探活"}
                  </button>
                  <span className="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-bold text-gray-600">{items.length} 个</span>
                </div>
              </div>

              <div className="space-y-4">
                {items.map((it, idx) => {
                  const host = hostFromUrl(it.url);
                  const p = probes[idx];
                  const isCurrent = idx === active;
                  const isSelected = pendingIndex === idx;
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => {
                        if (idx === active) setPendingIndex(null);
                        else setPendingIndex(idx);
                      }}
                      className={
                        "card-pick w-full rounded-[24px] border bg-white p-5 text-left shadow-sm " +
                        (isSelected ? "card-pick-selected" : "border-gray-100 hover:border-gray-200")
                      }
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <h4 className="text-lg font-bold text-gray-900">{host}</h4>
                            {isCurrent ? (
                              <span className="rounded-md bg-gray-900 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">当前</span>
                            ) : null}
                          </div>
                          {it.name && it.name !== host ? <p className="mb-2 text-[12px] text-gray-500">{it.name}</p> : null}
                          <div className="mb-3">{renderProbeCodes(p)}</div>
                          {p?.note ? <p className="mb-2 break-words text-[12px] text-gray-600">{p.note}</p> : null}
                          {p?.error ? (
                            <p className={"break-words text-[12px] " + (p.status === "degraded" ? "text-amber-700" : "text-red-600")}>{p.error}</p>
                          ) : null}
                        </div>
                        <div className="shrink-0 pt-0.5">
                          {isSelected ? (
                            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600">
                              <svg className="h-3.5 w-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                                <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            </div>
                          ) : (
                            <div className="h-6 w-6 rounded-full border-2 border-gray-200" />
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>
          </>
        ) : null}

        {loading && !loadError ? (
          <div className="py-16 text-center text-[13px] text-gray-500">加载中…</div>
        ) : null}
      </main>

      {pendingIndex !== null && items.length > 0 ? (
        <footer className="glass-footer fixed bottom-0 left-0 right-0 z-30 px-5 pb-[calc(env(safe-area-inset-bottom,0px)+20px)] pt-4">
          <div className="mx-auto max-w-md space-y-4">
            <div className="flex items-center gap-3 rounded-2xl bg-blue-600 px-4 py-3 text-white shadow-lg shadow-blue-200/50">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/20">
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M8 7h12M8 12h12M8 17h12M4 7h.01M4 12h.01M4 17h.01" strokeLinecap="round" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-bold uppercase tracking-wide text-blue-100 opacity-90">准备切换至</p>
                <p className="truncate text-[15px] font-bold">{pendingHost}</p>
              </div>
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                disabled={!canConfirm}
                onClick={() => void confirmSwitch()}
                className="flex h-14 flex-1 items-center justify-center rounded-2xl bg-gray-900 text-[15px] font-bold text-white shadow-xl active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-gray-300 disabled:shadow-none"
              >
                确认节点切换
              </button>
              <button
                type="button"
                onClick={() => setPendingIndex(null)}
                className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-gray-200 bg-white text-gray-600 active:scale-95"
                aria-label="取消"
              >
                <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          </div>
        </footer>
      ) : null}

      {submitting ? (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-white/90 backdrop-blur-sm">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
          <p className="mt-5 text-[16px] font-bold text-gray-900">切换中…</p>
        </div>
      ) : null}
    </div>
  );
}
