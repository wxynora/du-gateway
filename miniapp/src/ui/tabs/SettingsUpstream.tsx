import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { Btn, Modal } from "../components";
import { useToast } from "../toast";

type UpstreamItem = { name: string; url: string };
type UpstreamsResp = { active: number; items: UpstreamItem[]; anthropic_prompt_caching_enabled?: boolean };
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

export function SettingsUpstream({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [active, setActive] = useState(0);
  const [items, setItems] = useState<UpstreamItem[]>([]);
  const [probingAll, setProbingAll] = useState(false);
  const [probingIndex, setProbingIndex] = useState<number | null>(null);
  const [probes, setProbes] = useState<Record<number, ProbeItem>>({});
  const [anthropicPromptCachingEnabled, setAnthropicPromptCachingEnabled] = useState(false);
  const [togglingPromptCaching, setTogglingPromptCaching] = useState(false);

  async function load() {
    try {
      const j = await apiJson<UpstreamsResp>("/miniapp-api/upstreams");
      setActive(Number(j.active || 0));
      setItems(j.items || []);
      setAnthropicPromptCachingEnabled(!!j.anthropic_prompt_caching_enabled);
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function switchActive(nextActive: number) {
    try {
      const r = await apiJson<{ ok?: boolean; error?: string; active?: number }>("/miniapp-api/upstreams/active", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: nextActive }),
      });
      if (!r.ok) throw new Error(r?.error || "保存失败");
      toast("已切换并生效");
      await load();
      // 切换后自动探活一次，立即刷新该上游健康状态。
      await probeOne(nextActive);
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    }
  }

  async function togglePromptCaching(nextEnabled: boolean) {
    try {
      setTogglingPromptCaching(true);
      const r = await apiJson<{ ok?: boolean; error?: string; anthropic_prompt_caching_enabled?: boolean }>("/miniapp-api/upstreams/prompt-caching", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      if (!r.ok) throw new Error(r?.error || "保存失败");
      setAnthropicPromptCachingEnabled(!!r.anthropic_prompt_caching_enabled);
      toast(nextEnabled ? "Claude 缓存已开启" : "Claude 缓存已关闭");
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setTogglingPromptCaching(false);
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
      toast(one?.status === "ok" ? "探活通过" : "探活有异常");
    } catch (e: any) {
      toast(`探活失败：${e?.message || e}`);
    } finally {
      setProbingIndex(null);
    }
  }

  async function probeAll() {
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
      toast(r.status === "ok" ? "全部探活通过" : "探活完成（含异常）");
    } catch (e: any) {
      toast(`探活失败：${e?.message || e}`);
    } finally {
      setProbingAll(false);
    }
  }

  function statusText(p?: ProbeItem): string {
    if (!p) return "未探活";
    if (p.status === "ok") return "正常";
    if (p.status === "degraded") return "部分异常";
    return "不可用";
  }

  return (
    <Modal title="上游中转站" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="text-xs text-cream-muted">
          说明：这里切换的是网关的“全局默认上游”，会影响 RikkaHub/Telegram 等所有客户端。API Key 暂不在手机端维护（更安全）。
        </div>
        <div className="flex justify-end">
          <Btn kind="blue" onClick={probeAll} disabled={probingAll || !items.length}>
            {probingAll ? "探活中..." : "一键探活"}
          </Btn>
        </div>

        <div className="neo-panel p-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-cream-text">Claude 缓存</div>
            <div className="mt-1 text-xs text-cream-muted">
              只对 Claude 请求生效。切换上游后会自动关闭，需要你手动再开。
            </div>
          </div>
          <Btn
            kind={anthropicPromptCachingEnabled ? "blue" : "pink"}
            onClick={() => void togglePromptCaching(!anthropicPromptCachingEnabled)}
            disabled={togglingPromptCaching || !items.length}
          >
            {togglingPromptCaching ? "保存中..." : anthropicPromptCachingEnabled ? "已开启" : "未开启"}
          </Btn>
        </div>

        <div className="space-y-2">
          {items.map((it, idx) => (
            <div
              key={idx}
              className={
                "neo-panel-soft p-3"
              }
            >
              <div className="flex items-center justify-between">
                <div className="font-medium text-cream-text">{it.name || `upstream${idx + 1}`}</div>
                <div className="flex items-center gap-2">
                  <Btn kind="yellow" onClick={() => probeOne(idx)} disabled={probingIndex === idx || probingAll}>
                    {probingIndex === idx ? "检测中..." : "探活"}
                  </Btn>
                  <Btn
                    kind={idx === active ? "blue" : "pink"}
                    onClick={() => {
                      setActive(idx);
                      switchActive(idx);
                    }}
                    disabled={idx === active}
                  >
                    {idx === active ? "当前" : "切换到此"}
                  </Btn>
                </div>
              </div>
              <div className="mt-2 text-xs text-cream-muted break-all">{it.url}</div>
              <div className="mt-2 text-xs text-cream-muted">
                探活：{statusText(probes[idx])}
                {probes[idx]
                  ? ` ｜ models=${probes[idx].models_status} (${probes[idx].model_count}) ｜ chat=${probes[idx].chat_status}`
                  : ""}
              </div>
              {probes[idx]?.note ? <div className="mt-1 text-xs text-amber-600 break-all">{probes[idx]?.note}</div> : null}
              {probes[idx]?.error ? (
                <div className={"mt-1 text-xs break-all " + (probes[idx]?.status === "degraded" ? "text-amber-600" : "text-red-500")}>
                  {probes[idx]?.error}
                </div>
              ) : null}
            </div>
          ))}
          {!items.length ? <div className="text-xs text-cream-muted">（当前没有配置上游）</div> : null}
        </div>
      </div>
    </Modal>
  );
}

