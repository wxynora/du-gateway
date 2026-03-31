import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type WenyouView = "archives" | "hub";

type WenyouArchiveItem = {
  gameId?: string;
  endedAt?: string;
  instance_code?: string;
  instance_name?: string;
  instance_genre?: string;
  difficulty?: string;
  points?: number;
  player1_name?: string;
  player2_name?: string;
  player1_level?: number;
  player2_level?: number;
  history_count?: number;
};

type WenyouArchiveDetail = {
  gameId?: string;
  endedAt?: string;
  framework?: {
    instance_code?: string;
    instance_name?: string;
    instance_genre?: string;
    difficulty?: string;
    world?: string;
    conflict?: string;
    failure_hint?: string;
    reward_hint?: string;
  };
  history_count?: number;
};

type WenyouStatus = {
  active?: boolean;
  session?: {
    gameId?: string;
    startedAt?: string;
    instance_code?: string;
    instance_name?: string;
    instance_genre?: string;
    difficulty?: string;
  } | null;
};

export function WenyouTab({ initialView = "archives" }: { initialView?: WenyouView }) {
  const toast = useToast();
  const [view, setView] = useState<WenyouView>(initialView);

  const [archivesLoading, setArchivesLoading] = useState(false);
  const [archives, setArchives] = useState<WenyouArchiveItem[]>([]);
  const [openGameId, setOpenGameId] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [archiveDetails, setArchiveDetails] = useState<Record<string, WenyouArchiveDetail>>({});

  const [statusLoading, setStatusLoading] = useState(false);
  const [status, setStatus] = useState<WenyouStatus>({ active: false, session: null });
  const [mode, setMode] = useState<"random" | "custom">("random");
  const [keywords, setKeywords] = useState("");
  const [starting, setStarting] = useState(false);
  const [lastResult, setLastResult] = useState("");

  const loadArchives = useCallback(async () => {
    setArchivesLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; items?: WenyouArchiveItem[]; error?: string }>("/miniapp-api/wenyou/archives?limit=30");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setArchives(Array.isArray(j?.items) ? j.items : []);
    } catch (e: any) {
      toast(`加载已通关副本失败：${e?.message || e}`);
    } finally {
      setArchivesLoading(false);
    }
  }, [toast]);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; active?: boolean; session?: WenyouStatus["session"]; error?: string }>("/miniapp-api/wenyou/status");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setStatus({ active: !!j.active, session: j.session || null });
    } catch (e: any) {
      toast(`加载系统空间状态失败：${e?.message || e}`);
    } finally {
      setStatusLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (view === "archives") loadArchives();
    if (view === "hub") loadStatus();
  }, [view, loadArchives, loadStatus]);

  const sortedArchives = useMemo(
    () => (archives || []).slice().sort((a, b) => String(b.endedAt || "").localeCompare(String(a.endedAt || ""))),
    [archives]
  );

  async function toggleArchive(gameId: string) {
    if (!gameId) return;
    if (openGameId === gameId) {
      setOpenGameId("");
      return;
    }
    setOpenGameId(gameId);
    if (archiveDetails[gameId]) return;
    setDetailLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; archive?: WenyouArchiveDetail; error?: string }>(`/miniapp-api/wenyou/archive/${encodeURIComponent(gameId)}`);
      if (!j?.ok || !j.archive) throw new Error(j?.error || "加载详情失败");
      setArchiveDetails((prev) => ({ ...prev, [gameId]: j.archive as WenyouArchiveDetail }));
    } catch (e: any) {
      toast(`加载副本详情失败：${e?.message || e}`);
    } finally {
      setDetailLoading(false);
    }
  }

  async function startStory() {
    if (mode === "custom" && !keywords.trim()) {
      toast("请填写任务描述");
      return;
    }
    setStarting(true);
    try {
      const j = await apiJson<{ ok?: boolean; text?: string; need_confirm_new_game?: boolean; error?: string }>("/miniapp-api/wenyou/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          keywords: mode === "custom" ? keywords : "",
        }),
      });
      if (!j?.ok) throw new Error(j?.error || "开局失败");
      const text = String(j?.text || "");
      setLastResult(text);
      if (j.need_confirm_new_game) {
        toast("检测到已有进行中副本，请再点一次以确认开新局");
      } else {
        toast("已提交开局请求");
      }
      await loadStatus();
      await loadArchives();
    } catch (e: any) {
      toast(`开局失败：${e?.message || e}`);
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="neo-panel p-2 flex items-center gap-2">
        <button
          className={
            "neo-segment flex-1 text-sm " +
            (view === "archives" ? "neo-segment-active" : "")
          }
          onClick={() => setView("archives")}
        >
          已完成副本
        </button>
        <button
          className={
            "neo-segment flex-1 text-sm " +
            (view === "hub" ? "neo-segment-active" : "")
          }
          onClick={() => setView("hub")}
        >
          系统空间
        </button>
      </div>

      {view === "archives" ? (
        <div className="space-y-2">
          <div className="neo-panel p-3 flex items-center justify-between">
            <div className="text-xs text-cream-muted">按完成时间倒序展示</div>
            <Btn kind="blue" onClick={loadArchives} disabled={archivesLoading}>
              {archivesLoading ? "刷新中..." : "刷新列表"}
            </Btn>
          </div>
          {sortedArchives.map((it, idx) => (
            <div key={`${it.gameId || "g"}-${idx}`} className="neo-panel-soft p-3 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold text-cream-text">
                  {(it.instance_code || "").trim() ? `${it.instance_code}｜` : ""}
                  {it.instance_name || "未命名副本"}
                </div>
                <button
                  className="neo-chip px-2.5 py-1 text-[11px] tracking-normal normal-case"
                  onClick={() => toggleArchive(String(it.gameId || ""))}
                >
                  {openGameId === String(it.gameId || "") ? "收起" : "展开"}
                </button>
              </div>
              <div className="text-xs text-cream-muted">
                {it.instance_genre || "未知类型"} · 难度 {it.difficulty || "-"} · 结束于 {it.endedAt || "-"}
              </div>
              <div className="text-xs text-cream-muted">
                积分 {Number(it.points || 0)} · {it.player1_name || "玩家一"} Lv{Number(it.player1_level || 1)} · {it.player2_name || "渡"} Lv{Number(it.player2_level || 1)} · 历史 {Number(it.history_count || 0)} 条
              </div>
              {openGameId === String(it.gameId || "") ? (
                <div className="mt-2 neo-panel-inset p-2.5 text-xs space-y-1.5">
                  {detailLoading && !archiveDetails[String(it.gameId || "")] ? <div className="text-cream-muted">详情加载中...</div> : null}
                  {archiveDetails[String(it.gameId || "")] ? (
                    <>
                      <div className="text-cream-text"><span className="text-cream-muted">副本类型：</span>{archiveDetails[String(it.gameId || "")]?.framework?.instance_genre || "-"}</div>
                      <div className="text-cream-text"><span className="text-cream-muted">难度：</span>{archiveDetails[String(it.gameId || "")]?.framework?.difficulty || "-"}</div>
                      <div className="text-cream-text whitespace-pre-wrap"><span className="text-cream-muted">副本场景：</span>{archiveDetails[String(it.gameId || "")]?.framework?.world || "-"}</div>
                      <div className="text-cream-text whitespace-pre-wrap"><span className="text-cream-muted">主神任务：</span>{archiveDetails[String(it.gameId || "")]?.framework?.conflict || "-"}</div>
                      <div className="text-cream-text whitespace-pre-wrap"><span className="text-cream-muted">失败倾向：</span>{archiveDetails[String(it.gameId || "")]?.framework?.failure_hint || "-"}</div>
                      <div className="text-cream-text whitespace-pre-wrap"><span className="text-cream-muted">回报风味：</span>{archiveDetails[String(it.gameId || "")]?.framework?.reward_hint || "-"}</div>
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
          ))}
          {!sortedArchives.length && !archivesLoading ? <div className="text-xs text-cream-muted">还没有已完成副本归档。</div> : null}
        </div>
      ) : null}

      {view === "hub" ? (
        <div className="space-y-2">
          <div className="neo-panel p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div className="neo-tag-blue">
                系统空间
              </div>
              <Btn kind="blue" onClick={loadStatus} disabled={statusLoading}>
                {statusLoading ? "刷新中..." : "刷新状态"}
              </Btn>
            </div>
            {status.active ? (
              <div className="text-xs text-cream-muted leading-relaxed">
                当前有进行中副本：{status.session?.instance_name || "未命名"}（{status.session?.instance_genre || "-"} / {status.session?.difficulty || "-"}）。
                若开新局，需二次确认。
              </div>
            ) : (
              <div className="text-xs text-cream-muted">当前无进行中副本，可直接开新局。</div>
            )}
          </div>

          <div className="neo-panel p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Btn kind={mode === "random" ? "blue" : "default"} onClick={() => setMode("random")} disabled={starting}>
                随机任务
              </Btn>
              <Btn kind={mode === "custom" ? "pink" : "default"} onClick={() => setMode("custom")} disabled={starting}>
                自定义任务
              </Btn>
            </div>
            {mode === "custom" ? (
              <textarea
                className="neo-textarea min-h-[110px]"
                placeholder="输入较长任务描述（世界观、风格、禁忌、期望节奏等）"
                value={keywords}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setKeywords(e.target.value)}
                disabled={starting}
              />
            ) : (
              <div className="text-xs text-cream-muted">将由系统随机生成下一场任务副本。</div>
            )}
            <Btn kind={mode === "random" ? "blue" : "pink"} onClick={startStory} disabled={starting}>
              {starting ? "提交中..." : mode === "random" ? "开始随机任务" : "开始自定义任务"}
            </Btn>
          </div>

          {lastResult ? (
            <div className="neo-panel-soft p-3">
              <div className="text-xs text-cream-muted mb-1">系统反馈</div>
              <div className="text-xs leading-relaxed whitespace-pre-wrap text-cream-text">{lastResult}</div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
