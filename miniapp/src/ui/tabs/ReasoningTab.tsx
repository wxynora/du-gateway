import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { Btn, Card, Modal } from "../components";
import { useToast } from "../toast";
import type { ConversationRound, RoundPreview, WindowItem } from "../types";

type WindowsResp = { windows?: WindowItem[] };
type RoundsResp = { rounds?: RoundPreview[] };
type RoundDetailResp = { ok?: boolean; round?: ConversationRound; error?: string };

export function ReasoningTab() {
  const toast = useToast();
  const [windows, setWindows] = useState<WindowItem[]>([]);
  const [activeWindowId, setActiveWindowId] = useState<string | null>(null);
  const [rounds, setRounds] = useState<RoundPreview[]>([]);
  const [roundDetail, setRoundDetail] = useState<ConversationRound | null>(null);
  const [loadError, setLoadError] = useState("");

  async function loadWindows() {
    try {
      const j = await apiJson<WindowsResp>("/miniapp-api/windows?limit=30");
      setWindows(j.windows || []);
      setLoadError("");
    } catch (e: any) {
      setLoadError(e?.message || String(e));
      toast(`加载失败：${e?.message || e}`);
    }
  }

  useEffect(() => {
    loadWindows();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const items = useMemo(() => windows.slice(0, 30), [windows]);

  async function openRounds(wid: string) {
    try {
      const j = await apiJson<RoundsResp>(`/miniapp-api/windows/${encodeURIComponent(wid)}/rounds?preview_chars=60`);
      setActiveWindowId(wid);
      setRounds(j.rounds || []);
    } catch (e: any) {
      toast(`加载轮次失败：${e?.message || e}`);
    }
  }

  async function viewRound(wid: string, idx: number) {
    try {
      const j = await apiJson<RoundDetailResp>(`/miniapp-api/windows/${encodeURIComponent(wid)}/rounds/${idx}`);
      if (!j.ok) throw new Error(j?.error || "未找到该轮");
      setRoundDetail(j.round || null);
    } catch (e: any) {
      toast(`查看失败：${e?.message || e}`);
    }
  }

  return (
    <div className="space-y-3">
      {loadError ? (
        <div className="rounded-xl2 border border-cream-border bg-cream-pink/35 px-3 py-2 text-xs text-cream-text">
          窗口加载失败：{loadError}
          <br />
          请从 Telegram 按钮重新打开面板，或稍后重试。
        </div>
      ) : null}

      <Card title="选择窗口（查看轮次里的思维链）">
        <div className="space-y-2">
          {items.map((w) => (
            <button
              key={w.id}
              className="w-full rounded-xl2 border border-cream-border bg-cream-green/30 shadow-soft2 p-3 text-left active:scale-[0.99] transition"
              onClick={() => openRounds(w.id || "")}
            >
              <div className="text-sm font-medium">{w.id || "(no id)"}</div>
              <div className="mt-1 text-xs text-cream-muted">
                最近：{String(w.last_seen || "")}
              </div>
            </button>
          ))}
          {!items.length ? <div className="text-xs text-cream-muted">（暂无窗口）</div> : null}
        </div>
        <div className="mt-3">
          <Btn kind="blue" onClick={loadWindows}>刷新窗口列表</Btn>
        </div>
      </Card>

      {activeWindowId ? (
        <Modal title={`轮次 · ${activeWindowId}`} onClose={() => setActiveWindowId(null)}>
          <div className="space-y-2">
            {rounds.map((r) => (
              <div key={r.index} className="rounded-xl2 border border-cream-border bg-cream-blue/22 shadow-soft2 p-3">
                <div className="text-xs text-cream-muted">#{String(r.index ?? "")}</div>
                <div className="mt-1 text-sm">{String(r.preview || "")}</div>
                <div className="mt-2">
                  <Btn kind="pink" onClick={() => viewRound(activeWindowId, Number(r.index || 0))} disabled={!r.index}>
                    查看原文 + 思维链
                  </Btn>
                </div>
              </div>
            ))}
            {!rounds.length ? <div className="text-xs text-cream-muted">（暂无轮次）</div> : null}
          </div>
        </Modal>
      ) : null}

      {roundDetail && activeWindowId ? (
        <Modal title={`原文 · ${activeWindowId} #${roundDetail.index ?? ""}`} onClose={() => setRoundDetail(null)}>
          <div className="space-y-3">
            {(roundDetail.messages || []).map((m: any, i: number) => {
              const role = (m?.role || "unknown").toString();
              const content =
                typeof m?.content === "string" ? (m.content as string) : JSON.stringify(m?.content ?? "", null, 2);
              const reasoning = (m?.reasoning || m?.reasoning_content || m?.thinking || "") as string;
              return (
                <div key={i} className="rounded-xl3 border border-cream-border bg-cream-card shadow-soft2 p-3">
                  <div className="text-xs text-cream-muted">{role}</div>
                  <div className="mt-1 whitespace-pre-wrap text-sm">{content || ""}</div>
                  {role.toLowerCase() === "assistant" && reasoning?.trim() ? (
                    <details className="mt-2 rounded-xl2 border border-cream-border bg-cream-blue/35 p-2" open={false}>
                      <summary className="cursor-pointer select-none text-xs text-cream-muted">
                        思维链（展开/收起）
                      </summary>
                      <div className="mt-2 whitespace-pre-wrap font-mono text-xs text-cream-text">
                        {reasoning}
                      </div>
                    </details>
                  ) : null}
                </div>
              );
            })}
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

