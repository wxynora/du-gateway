import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { Btn, Card, Modal } from "../components";
import { useToast } from "../toast";
import type { ConversationRound, RoundPreview, WindowItem } from "../types";

type WindowsResp = { windows?: WindowItem[] };
type RoundsResp = { rounds?: RoundPreview[] };
type RoundDetailResp = { ok?: boolean; round?: ConversationRound; error?: string };

function getWindowId(w: any): string {
  return String(w?.id || w?.window_id || w?.windowId || "").trim();
}

export function ReasoningTab() {
  const toast = useToast();
  const [windows, setWindows] = useState<WindowItem[]>([]);
  const [activeWindowId, setActiveWindowId] = useState<string | null>(null);
  const [rounds, setRounds] = useState<RoundPreview[]>([]);
  const [roundDetail, setRoundDetail] = useState<ConversationRound | null>(null);
  const [loadError, setLoadError] = useState("");
  const [roundsError, setRoundsError] = useState("");
  const [detailHasReasoning, setDetailHasReasoning] = useState(true);

  async function loadWindows() {
    try {
      const j = await apiJson<WindowsResp>("/miniapp-api/windows?limit=120");
      const ws = j.windows || [];
      setWindows(ws);
      setLoadError("");
      // 打开思维链面板时，自动预取最近窗口的轮次，避免看起来像“没拉取到”
      const firstWid = ws.length > 0 ? getWindowId(ws[0]) : "";
      if (firstWid) {
        void openRounds(firstWid);
      }
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
      setRoundsError("");
      if (!(j.rounds || []).length) {
        setRoundsError("该窗口暂无轮次，可能还没有归档到 R2。");
      }
    } catch (e: any) {
      setRoundsError(e?.message || String(e));
      toast(`加载轮次失败：${e?.message || e}`);
    }
  }

  async function viewRound(wid: string, idx: number) {
    try {
      const j = await apiJson<RoundDetailResp>(`/miniapp-api/windows/${encodeURIComponent(wid)}/rounds/${idx}`);
      if (!j.ok) throw new Error(j?.error || "未找到该轮");
      const round = j.round || null;
      setRoundDetail(round);
      const has = !!(round?.messages || []).some((m: any) => {
        const role = (m?.role || "").toString().toLowerCase();
        const reasoning = (m?.reasoning || m?.reasoning_content || m?.thinking || "").toString().trim();
        return role === "assistant" && !!reasoning;
      });
      setDetailHasReasoning(has);
    } catch (e: any) {
      toast(`查看失败：${e?.message || e}`);
    }
  }

  return (
    <div className="space-y-3">
      <div className="rounded-xl2 bg-cream-blue/40 px-3 py-2 text-xs text-cream-muted shadow-soft2">
        窗口 ID = 会话标识（如 Telegram 常见为 <span className="font-mono">tg_用户ID</span>）。
      </div>
      {loadError ? (
        <div className="rounded-xl2 bg-cream-pink/65 px-3 py-2 text-xs text-cream-text shadow-soft2">
          窗口加载失败：{loadError}
          <br />
          请从 Telegram 按钮重新打开面板，或稍后重试。
        </div>
      ) : null}

      <Card title="选择窗口（查看轮次里的思维链）">
        <div className="space-y-2">
          {items.map((w, idx) => (
            <button
              key={getWindowId(w) || `w-${idx}`}
              className="w-full rounded-xl2 bg-cream-green/60 shadow-soft2 p-3 text-left active:scale-[0.99] transition"
              onClick={() => openRounds(getWindowId(w))}
            >
              <div className="text-sm font-medium">{getWindowId(w) || "(no id)"}</div>
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
            {roundsError ? (
              <div className="rounded-xl2 bg-cream-pink/65 px-3 py-2 text-xs text-cream-text shadow-soft2">
                轮次加载提示：{roundsError}
              </div>
            ) : null}
            {rounds.map((r) => (
              <div key={r.index} className="rounded-xl2 bg-cream-blue/50 shadow-soft2 p-3">
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
                <div key={i} className="rounded-xl3 bg-cream-card shadow-soft2 p-3">
                  <div className="text-xs text-cream-muted">{role}</div>
                  <div className="mt-1 whitespace-pre-wrap text-sm">{content || ""}</div>
                  {role.toLowerCase() === "assistant" && reasoning?.trim() ? (
                    <details className="mt-2 rounded-xl2 bg-cream-blue/55 p-2 shadow-soft2" open={false}>
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
            {!detailHasReasoning ? (
              <div className="rounded-xl2 bg-cream-pink/55 px-3 py-2 text-xs text-cream-text shadow-soft2">
                该轮有对话内容，但上游未返回 reasoning 字段，所以没有可展示的思维链。
              </div>
            ) : null}
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

