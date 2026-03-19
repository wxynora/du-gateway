import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { Btn, Modal } from "../components";
import { useToast } from "../toast";

type UpstreamItem = { name: string; url: string };
type UpstreamsResp = { active: number; items: UpstreamItem[] };

export function SettingsUpstream({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [active, setActive] = useState(0);
  const [items, setItems] = useState<UpstreamItem[]>([]);

  async function load() {
    try {
      const j = await apiJson<UpstreamsResp>("/miniapp-api/upstreams");
      setActive(Number(j.active || 0));
      setItems(j.items || []);
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
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    }
  }

  return (
    <Modal title="上游中转站" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="text-xs text-cream-muted">
          说明：这里切换的是网关的“全局默认上游”，会影响 RikkaHub/Telegram 等所有客户端。API Key 暂不在手机端维护（更安全）。
        </div>

        <div className="space-y-2">
          {items.map((it, idx) => (
            <div
              key={idx}
              className={
                "rounded-xl3 border p-3 shadow-soft2 " +
                (idx === active ? "border-cream-border bg-cream-green/35" : "border-cream-border bg-cream-blue/18")
              }
            >
              <div className="flex items-center justify-between">
                <div className="font-medium">{it.name || `upstream${idx + 1}`}</div>
                <Btn
                  kind={idx === active ? "green" : "pink"}
                  onClick={() => {
                    setActive(idx);
                    switchActive(idx);
                  }}
                  disabled={idx === active}
                >
                  {idx === active ? "当前" : "切换到此"}
                </Btn>
              </div>
              <div className="mt-2 text-xs text-cream-muted break-all">{it.url}</div>
            </div>
          ))}
          {!items.length ? <div className="text-xs text-cream-muted">（当前没有配置上游）</div> : null}
        </div>
      </div>
    </Modal>
  );
}

