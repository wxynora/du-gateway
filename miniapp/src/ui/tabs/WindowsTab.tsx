import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { Btn, Card, Modal } from "../components";
import { useToast } from "../toast";
import type { ConversationRound, RoundPreview, WindowItem } from "../types";

type WindowsResp = { windows?: WindowItem[] };
type RoundsResp = { rounds?: RoundPreview[]; window_id?: string };
type RoundDetailResp = { ok?: boolean; round?: ConversationRound; error?: string };

export function WindowsTab() {
  const toast = useToast();
  const [windows, setWindows] = useState<WindowItem[]>([]);
  const [activeWindowId, setActiveWindowId] = useState<string | null>(null);
  const [rounds, setRounds] = useState<RoundPreview[]>([]);
  const [roundDetail, setRoundDetail] = useState<ConversationRound | null>(null);

  async function loadWindows() {
    try {
      const j = await apiJson<WindowsResp>("/miniapp-api/windows?limit=60");
      setWindows(j.windows || []);
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    }
  }

  useEffect(() => {
    loadWindows();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const items = useMemo(() => windows.slice(0, 60), [windows]);

  async function openRounds(wid: string) {
    try {
      const j = await apiJson<RoundsResp>(`/miniapp-api/windows/${encodeURIComponent(wid)}/rounds?preview_chars=80`);
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

  async function deleteRound(wid: string, idx: number) {
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(
        `/miniapp-api/windows/${encodeURIComponent(wid)}/rounds/${idx}`,
        { method: "DELETE" },
      );
      if (!j.ok) throw new Error(j?.error || "删除失败");
      toast("已删除该轮");
      await openRounds(wid);
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  return (
    <div className="space-y-3">
      <Card title="最近窗口">
        <div className="space-y-2">
          {items.map((w) => (
            <button
              key={w.id}
              className="w-full neo-panel-soft p-3 text-left"
              onClick={() => openRounds(w.id || "")}
            >
              <div className="text-sm font-medium text-cream-text">{w.id || "(no id)"}</div>
              <div className="mt-1 text-xs text-cream-muted">
                {(w.whitelisted ? "白名单" : "非白") +
                  " · " +
                  (w.blacklisted ? "黑名单" : "非黑") +
                  " · 最近：" +
                  String(w.last_seen || "")}
              </div>
            </button>
          ))}
          {!items.length ? <div className="text-xs text-cream-muted">（暂无）</div> : null}
        </div>
      </Card>

      {activeWindowId ? (
        <Modal title={`轮次 · ${activeWindowId}`} onClose={() => setActiveWindowId(null)}>
          <div className="space-y-2">
            {rounds.map((r) => (
              <div key={r.index} className="neo-panel-soft p-3">
                <div className="text-xs text-cream-muted">#{String(r.index ?? "")}</div>
                <div className="mt-1 text-sm text-cream-text">{String(r.preview || "")}</div>
                <div className="mt-2 flex gap-2">
                  <Btn kind="blue" onClick={() => viewRound(activeWindowId, Number(r.index || 0))} disabled={!r.index}>
                    查看
                  </Btn>
                  <Btn kind="danger" onClick={() => deleteRound(activeWindowId, Number(r.index || 0))} disabled={!r.index}>
                    删除该轮
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
                <div key={i} className="neo-panel-soft p-3">
                  <div className="text-xs text-cream-muted">{role}</div>
                  <div className="mt-1 whitespace-pre-wrap text-sm text-cream-text">{content || ""}</div>
                  {role.toLowerCase() === "assistant" && reasoning?.trim() ? (
                    <details className="mt-2 neo-panel-inset p-2">
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

