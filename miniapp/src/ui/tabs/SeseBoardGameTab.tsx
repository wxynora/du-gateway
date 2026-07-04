import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { ChevronLeftIcon, MessageCircleIconMini, SendIconMini } from "../icons";
import { useToast } from "../toast";

type Actor = "xinyue" | "du";

type CellEvent = {
  position?: number;
  kind?: string;
  slot?: string;
  name?: string;
  effect?: Record<string, unknown>;
};

type StatusItem = {
  slot?: string;
  label?: string;
  value?: string;
  duration_type?: string;
  remaining_actions?: number;
  minutes?: number;
  expires_at?: string;
  blocks_action?: boolean;
};

type PrivateBoardState = {
  board_size?: number;
  positions?: Partial<Record<Actor, number>>;
  turn_actor?: Actor;
  statuses?: Partial<Record<Actor, StatusItem[]>>;
  theme_profile?: {
    theme?: string;
    direction?: string;
    direction_label?: string;
  };
  cell_events?: CellEvent[];
  game_over?: boolean;
  winner?: Actor | "";
  result?: string;
  updated_at?: string;
};

type PrivateBoardPayload = {
  ok?: boolean;
  text?: string;
  du_text?: string;
  player_text?: string;
  state?: PrivateBoardState;
  game_over?: boolean;
  winner?: Actor | "";
  result?: string;
  error?: string;
};

type PrivateBoardSyncPayload = {
  ok?: boolean;
  player_text?: string;
  state?: PrivateBoardState;
  reply_text?: string;
  reply_preview?: string;
  channel?: string;
  wakeup?: {
    error?: string;
    reply_text?: string;
    reply_preview?: string;
    channel?: string;
  };
  error?: string;
};

type PrivateBoardSyncMode = "roll_result" | "chat";

type MoveInfo = {
  actor: Actor;
  dice: number;
  from: number;
  to: number;
};

type EventPopup = {
  position: number;
  title: string;
  text: string;
};

type GameChatMessage = {
  id: string;
  speaker: Actor | "system";
  text: string;
};

const ACTORS: Actor[] = ["xinyue", "du"];
const ACTOR_LABEL: Record<Actor, string> = { xinyue: "我", du: "渡" };
const DEFAULT_POSITIONS: Record<Actor, number> = { xinyue: 0, du: 0 };
function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function displayText(value: unknown): string {
  return String(value || "").replace(/小玥/g, "我");
}

function plainText(value: unknown): string {
  return String(value || "");
}

function makeChatId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function clampPosition(value: unknown, boardSize: number): number {
  const n = Math.floor(Number(value || 0));
  return Math.max(1, Math.min(boardSize, n || 1));
}

function progressPosition(value: unknown, boardSize: number): number {
  const n = Math.floor(Number(value || 0));
  return Math.max(0, Math.min(boardSize, n || 0));
}

function snakeOrder(boardSize: number, columns: number): number[] {
  const rows: number[][] = [];
  for (let start = 1; start <= boardSize; start += columns) {
    const row = Array.from({ length: Math.min(columns, boardSize - start + 1) }, (_, idx) => start + idx);
    if (rows.length % 2 === 1) row.reverse();
    rows.push(row);
  }
  return rows.reverse().flat();
}

function eventKind(event: CellEvent | undefined, position: number, boardSize: number): string {
  if (position === 1) return "start";
  if (position === boardSize) return "end";
  if (!event) return "empty";
  const raw = `${event.kind || ""} ${event.slot || ""}`.toLowerCase();
  if (/swap/.test(raw)) return "swap";
  if (/move|back|forward/.test(raw)) return "move";
  if (/lock|pause|item/.test(raw)) return "item";
  if (/clear/.test(raw)) return "clear";
  if (/extend|time/.test(raw)) return "time";
  if (/limit/.test(raw)) return "limit";
  if (/place/.test(raw)) return "place";
  if (/pose/.test(raw)) return "pose";
  if (/theme/.test(raw)) return "theme";
  return "task";
}

function eventIcon(kind: string): string {
  if (kind === "start") return "🚩";
  if (kind === "end") return "🏆";
  if (kind === "place") return "🏫";
  if (kind === "item") return "🎁";
  if (kind === "move") return "⏪";
  if (kind === "swap") return "🔄";
  if (kind === "clear") return "✨";
  if (kind === "time") return "⏳";
  if (kind === "limit") return "🚫";
  if (kind === "pose") return "◇";
  if (kind === "theme") return "🚩";
  if (kind === "task") return "📸";
  return "";
}

function tileName(event: CellEvent | undefined, position: number, boardSize: number): string {
  if (position === 1) return "起点";
  if (position === boardSize) return "终点";
  return displayText(event?.name || "空");
}

function parseMove(text: string): MoveInfo | null {
  const match = displayText(text).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);
  if (!match) return null;
  return {
    actor: match[1] === "渡" ? "du" : "xinyue",
    dice: Number(match[2] || 1),
    from: Number(match[3] || 0),
    to: Number(match[4] || 0),
  };
}

function parseEventPopup(text: string): EventPopup | null {
  const line = displayText(text)
    .split("\n")
    .map((item) => item.trim())
    .find((item) => /^第\s*\d+\s*格：/.test(item));
  if (!line) return null;
  const match = line.match(/^第\s*(\d+)\s*格：([^，。]+)/);
  return {
    position: Number(match?.[1] || 0),
    title: match?.[2] || "格子事件",
    text: line,
  };
}

function statusDuration(item: StatusItem): string {
  const duration = String(item.duration_type || "");
  if (duration === "actions") return `剩余 ${Math.max(0, Number(item.remaining_actions || 0))} 次行动`;
  if (duration === "minutes") return `${Math.max(1, Number(item.minutes || 0))} 分钟`;
  if (duration === "until_finish") return "到终点";
  if (duration === "until_clear") return "待解除";
  return "";
}

function actorPaused(statuses: StatusItem[] | undefined): boolean {
  return (statuses || []).some((item) => item.blocks_action && Number(item.remaining_actions || 0) > 0);
}

function recentLines(text: string): string[] {
  const allowed = [
    /^(我|渡)掷出\s*\d+/,
    /^第\s*\d+\s*格：/,
    /^下一次行动：/,
    /行动权/,
    /到达终点/,
    /^新局已开始。?$/,
    /^本局已结束。?$/,
  ];
  return displayText(text)
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => item && allowed.some((pattern) => pattern.test(item)))
    .slice(0, 4);
}

function duWantsRoll(text: string): boolean {
  const firstLine = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  return firstLine === "【掷骰】";
}

async function executePrivateBoard(command: string): Promise<PrivateBoardPayload> {
  const payload = await apiJson<PrivateBoardPayload>("/miniapp-api/game-tools/private_board", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, save_id: "default" }),
  });
  if (!payload?.ok) throw new Error(payload?.error || "走格棋命令失败");
  return payload;
}

async function sendPrivateBoardToDu(options: {
  mode: PrivateBoardSyncMode;
  message?: string;
  rollText?: string;
}): Promise<PrivateBoardSyncPayload> {
  const payload = await apiJson<PrivateBoardSyncPayload>("/miniapp-api/game-tools/private_board/sync-du", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      save_id: "default",
      mode: options.mode,
      message: options.message || "",
      roll_text: options.rollText || "",
    }),
  });
  if (!payload?.ok) throw new Error(payload?.error || payload?.wakeup?.error || "游戏内交流失败");
  return payload;
}

function isDuTurnState(state: PrivateBoardState | undefined): boolean {
  return Boolean(state && state.turn_actor === "du" && !state.game_over);
}

export function SeseBoardGameTab({ onBack }: { onBack: () => void }) {
  const toast = useToast();
  const gameRef = useRef<HTMLDivElement | null>(null);
  const chatOpenRef = useRef(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const rollOnceRef = useRef<((options?: { notifyAfterUserRoll?: boolean }) => Promise<void>) | null>(null);
  const [payload, setPayload] = useState<PrivateBoardPayload | null>(null);
  const [displayPositions, setDisplayPositions] = useState<Partial<Record<Actor, number>>>(DEFAULT_POSITIONS);
  const [dice, setDice] = useState(1);
  const [busy, setBusy] = useState(false);
  const [rolling, setRolling] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [activeTile, setActiveTile] = useState<number | null>(null);
  const [popup, setPopup] = useState<EventPopup | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatUnread, setChatUnread] = useState(0);
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);
  const [chatMessages, setChatMessages] = useState<GameChatMessage[]>([
    {
      id: "system-ready",
      speaker: "system",
      text: "游戏内交流在这里。渡的第一行是【掷骰】时，棋盘才会执行他的行动。",
    },
  ]);

  const state = payload?.state || {};
  const boardSize = Math.max(12, Math.min(80, Number(state.board_size || 36)));
  const columns = boardSize <= 36 ? 6 : 8;
  const currentActor = state.turn_actor === "du" ? "du" : "xinyue";
  const isGameOver = Boolean(state.game_over || payload?.game_over);
  const isDuTurn = currentActor === "du" && !isGameOver;

  useLayoutEffect(() => {
    if (gameRef.current) gameRef.current.scrollTop = 0;
  }, []);

  useEffect(() => {
    chatOpenRef.current = chatOpen;
    if (chatOpen) setChatUnread(0);
  }, [chatOpen]);

  useEffect(() => {
    if (!chatOpen) return;
    window.setTimeout(() => chatEndRef.current?.scrollIntoView({ block: "end" }), 40);
  }, [chatMessages.length, chatOpen, chatSending]);

  const appendChat = useCallback((message: GameChatMessage, unread = false) => {
    setChatMessages((items) => [...items, message]);
    if (unread && !chatOpenRef.current) {
      setChatUnread((count) => Math.min(9, count + 1));
    }
  }, []);

  const eventMap = useMemo(() => {
    const map = new Map<number, CellEvent>();
    for (const item of state.cell_events || []) {
      const position = Number(item?.position || 0);
      if (position > 0) map.set(position, item);
    }
    return map;
  }, [state.cell_events]);

  const boardTiles = useMemo(() => {
    return snakeOrder(boardSize, columns).map((position) => {
      const event = eventMap.get(position);
      const kind = eventKind(event, position, boardSize);
      return {
        position,
        event,
        kind,
        icon: eventIcon(kind),
        name: tileName(event, position, boardSize),
      };
    });
  }, [boardSize, columns, eventMap]);

  const applyPayload = useCallback((next: PrivateBoardPayload) => {
    setPayload(next);
    setDisplayPositions({
      xinyue: Number(next.state?.positions?.xinyue || 0),
      du: Number(next.state?.positions?.du || 0),
    });
  }, []);

  const loadStatus = useCallback(async () => {
    setBusy(true);
    try {
      const next = await executePrivateBoard("status");
      applyPayload(next);
    } catch (e: any) {
      toast(`加载涩涩走格棋失败：${e?.message || e}`);
    } finally {
      setBusy(false);
    }
  }, [applyPayload, toast]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const animateDice = useCallback(async (finalDice: number) => {
    setRolling(true);
    for (let i = 0; i < 12; i += 1) {
      setDice(Math.floor(Math.random() * 6) + 1);
      await wait(58);
    }
    setDice(Math.max(1, Math.min(6, finalDice || 1)));
    setRolling(false);
  }, []);

  const animateActor = useCallback(async (
    positions: Partial<Record<Actor, number>>,
    actor: Actor,
    from: number,
    to: number,
  ) => {
    const start = Number(from || 0);
    const end = Number(to || 0);
    if (start === end) {
      positions[actor] = end;
      setDisplayPositions({ ...positions });
      setActiveTile(clampPosition(end, boardSize));
      await wait(120);
      return;
    }
    const step = end > start ? 1 : -1;
    for (let pos = start + step; step > 0 ? pos <= end : pos >= end; pos += step) {
      positions[actor] = pos;
      setDisplayPositions({ ...positions });
      setActiveTile(clampPosition(pos, boardSize));
      await wait(145);
    }
  }, [boardSize]);

  const startNewGame = useCallback(async () => {
    if (busy || animating) return;
    setBusy(true);
    setPopup(null);
    try {
      const next = await executePrivateBoard("new_game");
      setDice(1);
      applyPayload(next);
    } catch (e: any) {
      toast(`开新局失败：${e?.message || e}`);
    } finally {
      setBusy(false);
    }
  }, [animating, applyPayload, busy, toast]);

  const endGame = useCallback(async () => {
    if (busy || animating) return;
    setBusy(true);
    try {
      const next = await executePrivateBoard("end_game");
      applyPayload(next);
    } catch (e: any) {
      toast(`结束本局失败：${e?.message || e}`);
    } finally {
      setBusy(false);
    }
  }, [animating, applyPayload, busy, toast]);

  const processDuReply = useCallback(async (reply: string, nextState: PrivateBoardState | undefined) => {
    const duReply = reply.trim() || "我看到了。";
    appendChat({ id: makeChatId("du"), speaker: "du", text: duReply }, true);
    if (isDuTurnState(nextState) && duWantsRoll(duReply)) {
      await wait(260);
      appendChat({ id: makeChatId("system"), speaker: "system", text: "渡第一行发出【掷骰】，已执行他的行动。" }, true);
      await rollOnceRef.current?.({ notifyAfterUserRoll: false });
    }
  }, [appendChat]);

  const notifyRollResultToDu = useCallback(async (rolled: PrivateBoardPayload) => {
    const rollText = plainText(rolled.text || rolled.du_text || rolled.player_text || "").trim();
    appendChat({ id: makeChatId("system"), speaker: "system", text: "已把这次掷骰结果和当前棋局发给渡。" }, true);
    setChatSending(true);
    try {
      const next = await sendPrivateBoardToDu({
        mode: "roll_result",
        message: "小玥刚掷完骰子。",
        rollText,
      });
      if (next.state) {
        applyPayload({
          ok: true,
          state: next.state,
          player_text: next.player_text || rolled.player_text || "",
        });
      }
      const reply = plainText(next.reply_text || next.wakeup?.reply_text || next.reply_preview || next.wakeup?.reply_preview || "").trim();
      await processDuReply(reply, next.state || rolled.state);
    } catch (e: any) {
      const message = String(e?.message || e || "同步失败");
      appendChat({ id: makeChatId("system"), speaker: "system", text: `自动同步失败：${message}` }, true);
      toast(`自动同步给渡失败：${message}`);
    } finally {
      setChatSending(false);
    }
  }, [appendChat, applyPayload, processDuReply, toast]);

  const rollOnce = useCallback(async (options: { notifyAfterUserRoll?: boolean } = {}) => {
    if (busy || animating || isGameOver) return;
    let notifyPayload: PrivateBoardPayload | null = null;
    setBusy(true);
    setAnimating(true);
    setPopup(null);
    const beforePositions: Partial<Record<Actor, number>> = {
      xinyue: Number(state.positions?.xinyue || 0),
      du: Number(state.positions?.du || 0),
    };
    const visualPositions = { ...beforePositions };
    try {
      const next = await executePrivateBoard("roll");
      const move = parseMove(next.player_text || "");
      await animateDice(move?.dice || Math.floor(Math.random() * 6) + 1);
      if (move) {
        await animateActor(visualPositions, move.actor, move.from, move.to);
      }
      const finalPositions: Partial<Record<Actor, number>> = {
        xinyue: Number(next.state?.positions?.xinyue || 0),
        du: Number(next.state?.positions?.du || 0),
      };
      for (const actor of ACTORS) {
        const current = Number(visualPositions[actor] || 0);
        const target = Number(finalPositions[actor] || 0);
        if (current !== target) {
          await animateActor(visualPositions, actor, current, target);
        }
      }
      applyPayload(next);
      const nextPopup = parseEventPopup(next.player_text || "");
      if (nextPopup) setPopup(nextPopup);
      if (options.notifyAfterUserRoll !== false && move?.actor === "xinyue" && !next.state?.game_over) {
        notifyPayload = next;
      }
    } catch (e: any) {
      toast(`掷骰失败：${e?.message || e}`);
    } finally {
      setBusy(false);
      setAnimating(false);
      window.setTimeout(() => setActiveTile(null), 260);
    }
    if (notifyPayload) {
      await notifyRollResultToDu(notifyPayload);
    }
  }, [animateActor, animateDice, animating, applyPayload, busy, isGameOver, notifyRollResultToDu, state.positions, toast]);

  useEffect(() => {
    rollOnceRef.current = rollOnce;
  }, [rollOnce]);

  const sendGameChat = useCallback(async () => {
    if (chatSending || busy || animating || !payload?.state) return;
    const message = chatInput.trim();
    if (!message) return;
    const userChatMessage: GameChatMessage = { id: makeChatId("me"), speaker: "xinyue", text: message };
    setChatInput("");
    appendChat(userChatMessage);
    setChatSending(true);
    try {
      const next = await sendPrivateBoardToDu({
        mode: "chat",
        message,
      });
      if (next.state) {
        applyPayload({
          ok: true,
          state: next.state,
          player_text: next.player_text || payload.player_text || "",
        });
      }
      const reply = plainText(next.reply_text || next.wakeup?.reply_text || next.reply_preview || next.wakeup?.reply_preview || "").trim();
      await processDuReply(reply, next.state || payload.state);
    } catch (e: any) {
      const message = String(e?.message || e || "同步失败");
      appendChat({ id: makeChatId("system"), speaker: "system", text: `交流失败：${message}` });
      toast(`游戏内交流失败：${message}`);
    } finally {
      setChatSending(false);
    }
  }, [animating, appendChat, applyPayload, busy, chatInput, chatSending, payload, processDuReply, toast]);

  const themeName = displayText(state.theme_profile?.theme || "未触发");
  const directionLabel = displayText(state.theme_profile?.direction_label || "待定");
  const meProgress = progressPosition(state.positions?.xinyue, boardSize);
  const duProgress = progressPosition(state.positions?.du, boardSize);
  const winnerLabel = state.winner ? ACTOR_LABEL[state.winner] : "";
  const lines = recentLines(payload?.player_text || "");
  const rollDisabled = busy || animating || chatSending || !payload?.state || isDuTurn;
  const chatDisabled = chatSending || busy || animating || !payload?.state;
  const pausedByActor: Record<Actor, boolean> = {
    xinyue: actorPaused(state.statuses?.xinyue),
    du: actorPaused(state.statuses?.du),
  };

  return (
    <div className="sese-game" ref={gameRef}>
      <div className="sese-header">
        <button className="sese-back" type="button" onClick={onBack} aria-label="返回游戏">
          <ChevronLeftIcon />
        </button>
        <button className="sese-chat-entry" type="button" onClick={() => setChatOpen(true)} aria-label="游戏内交流">
          <MessageCircleIconMini />
          {chatUnread ? <span>{chatUnread}</span> : null}
        </button>
        <div className="sese-header-title">涩涩走格棋</div>
        <div className="sese-game-status-bar">
          <StatusPill label="主题" value={themeName} />
          <StatusPill label="主导方" value={directionLabel} />
          <StatusPill label="我 进度" value={`${String(meProgress).padStart(2, "0")} / ${boardSize}`} />
          <StatusPill label="渡 进度" value={`${String(duProgress).padStart(2, "0")} / ${boardSize}`} />
          <div className="sese-turn-indicator">
            {isGameOver && winnerLabel ? `${winnerLabel} 到达终点` : isDuTurn ? "等待 渡 行动..." : "轮到 我 行动"}
          </div>
        </div>
      </div>

      <section className="sese-board-container" aria-label="走格棋盘">
        <div className="sese-board" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
          {boardTiles.map((tile) => {
            const pieces = ACTORS.filter((actor) => clampPosition(displayPositions[actor], boardSize) === tile.position);
            return (
              <div
                key={tile.position}
                className={`sese-tile sese-tile-${tile.kind} ${activeTile === tile.position ? "is-active" : ""}`}
              >
                <div className="sese-tile-number">{tile.position}</div>
                <div className="sese-tile-icon">{tile.icon}</div>
                <div className="sese-tile-name">{tile.name}</div>
                <div className="sese-piece-stack">
                  {pieces.map((actor) => (
                    <span
                      key={actor}
                      className={`sese-piece ${actor === "xinyue" ? "sese-piece-me" : "sese-piece-du"} ${pausedByActor[actor] ? "paused" : ""}`}
                    >
                      {ACTOR_LABEL[actor]}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="sese-controls">
        <div className="sese-player-states">
          <PlayerStateCard actor="xinyue" statuses={state.statuses?.xinyue || []} active={currentActor === "xinyue"} />
          <PlayerStateCard actor="du" statuses={state.statuses?.du || []} active={currentActor === "du"} />
        </div>

        <div className="sese-action-area">
          <div className={`sese-dice ${rolling ? "rolling" : ""}`} aria-label={`骰子 ${dice}`}>
            {dice}
          </div>
          <button
            className="sese-roll-button"
            type="button"
            disabled={rollDisabled}
            onClick={isGameOver ? startNewGame : () => void rollOnce({ notifyAfterUserRoll: true })}
          >
            {isGameOver ? "开新局" : isDuTurn ? "等渡掷骰" : busy || animating ? "移动中" : chatSending ? "等渡回应" : "掷骰子"}
          </button>
        </div>

        <div className="sese-history">
          {lines.length ? `最近：${lines[0]}` : "最近：等待第一次掷骰"}
        </div>
      </section>

      {chatOpen ? (
        <div className="sese-chat-mask" role="dialog" aria-modal="true" aria-label="游戏内交流" onClick={() => setChatOpen(false)}>
          <div className="sese-chat-panel" onClick={(event) => event.stopPropagation()}>
            <div className="sese-chat-head">
              <div>
                <strong>游戏内交流</strong>
                <span>{isDuTurn ? "渡第一行【掷骰】才算指令" : "当前轮到我行动"}</span>
              </div>
              <button type="button" onClick={() => setChatOpen(false)} aria-label="关闭交流">×</button>
            </div>
            <div className="sese-chat-list">
              {chatMessages.map((message) => (
                <div key={message.id} className={`sese-chat-message ${message.speaker}`}>
                  <span>{message.speaker === "xinyue" ? "我" : message.speaker === "du" ? "渡" : "系统"}</span>
                  <p>{plainText(message.text)}</p>
                </div>
              ))}
              {chatSending ? (
                <div className="sese-chat-message du pending">
                  <span>渡</span>
                  <p>正在回复...</p>
                </div>
              ) : null}
              <div ref={chatEndRef} />
            </div>
            <form className="sese-chat-form" onSubmit={(event) => {
              event.preventDefault();
              void sendGameChat();
            }}>
              <input
                value={chatInput}
                disabled={chatDisabled}
                placeholder="和渡说一句游戏内的话"
                onChange={(event) => setChatInput(event.target.value)}
              />
              <button type="submit" disabled={chatDisabled || !chatInput.trim()} aria-label={chatSending ? "发送中" : "发送"}>
                <SendIconMini />
              </button>
            </form>
          </div>
        </div>
      ) : null}

      {popup ? (
        <div className="sese-popup-mask" role="dialog" aria-modal="true">
          <div className="sese-popup">
            <div className="sese-popup-kicker">第 {popup.position} 格</div>
            <h2>{displayText(popup.title)}</h2>
            <p>{displayText(popup.text)}</p>
            <button type="button" onClick={() => setPopup(null)}>确 认</button>
          </div>
        </div>
      ) : null}

      <style>
        {`
        .sese-game {
          --primary-pink: #f8bbd0;
          --soft-lavender: #f3e5f5;
          --accent-yellow: #fff9c4;
          --accent-mint: #e0f2f1;
          --accent-blue: #e1f5fe;
          --text-main: #884d8a;
          --text-light: #ba68c8;
          --bg-page: #fce4ec;
          --card-white: rgba(255, 255, 255, 0.86);
          position: absolute;
          inset: 0;
          z-index: 34;
          min-height: 100dvh;
          overflow-y: auto;
          background:
            linear-gradient(180deg, rgba(255,255,255,0.62) 0, rgba(255,255,255,0) 210px),
            var(--bg-page);
          color: var(--text-main);
          font-family: "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          padding: calc(env(safe-area-inset-top, 0px) + 10px) 14px calc(env(safe-area-inset-bottom, 0px) + 22px);
        }
        .sese-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin: 0 auto 12px;
          max-width: 720px;
        }
        .sese-back,
        .sese-header-button,
        .sese-quiet-button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border: 0;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.82);
          color: var(--text-main);
          box-shadow: 0 8px 18px rgba(136, 77, 138, 0.14);
          transition: transform 140ms ease, opacity 140ms ease;
        }
        .sese-back {
          width: 42px;
          height: 42px;
          flex: 0 0 42px;
        }
        .sese-header-button {
          min-width: 58px;
          height: 36px;
          padding: 0 14px;
          font-size: 13px;
          font-weight: 800;
        }
        .sese-back:active,
        .sese-header-button:active,
        .sese-roll-button:active,
        .sese-quiet-button:active {
          transform: scale(0.96);
        }
        .sese-header-button:disabled,
        .sese-roll-button:disabled,
        .sese-quiet-button:disabled {
          opacity: 0.54;
        }
        .sese-title-block {
          min-width: 0;
          flex: 1;
          text-align: center;
        }
        .sese-title-block h1 {
          margin: 0;
          color: var(--text-main);
          font-size: 24px;
          font-weight: 900;
          line-height: 1.12;
          text-shadow: 0 2px 0 rgba(255, 255, 255, 0.82);
        }
        .sese-title-block p {
          margin: 4px 0 0;
          color: var(--text-light);
          font-size: 12px;
          font-weight: 800;
          line-height: 1.2;
        }
        .sese-status-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
          margin: 0 auto 12px;
          max-width: 720px;
        }
        .sese-pill {
          min-height: 54px;
          overflow: hidden;
          border: 1px solid rgba(255, 255, 255, 0.72);
          border-radius: 18px;
          background: var(--card-white);
          padding: 8px 10px;
          box-shadow: 0 10px 22px rgba(136, 77, 138, 0.1);
        }
        .sese-pill span {
          display: block;
          color: var(--text-light);
          font-size: 10px;
          font-weight: 900;
          line-height: 1.1;
        }
        .sese-pill strong {
          display: block;
          margin-top: 4px;
          overflow: hidden;
          color: var(--text-main);
          font-size: 13px;
          font-weight: 900;
          line-height: 1.18;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sese-board-wrap {
          margin: 0 auto;
          max-width: 720px;
          border: 6px solid rgba(255, 255, 255, 0.84);
          border-radius: 26px;
          background: rgba(255, 255, 255, 0.62);
          padding: 8px;
          box-shadow: 0 18px 38px rgba(136, 77, 138, 0.16);
        }
        .sese-board {
          display: grid;
          gap: 6px;
          width: 100%;
        }
        .sese-tile {
          position: relative;
          display: flex;
          aspect-ratio: 1;
          min-width: 0;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          border: 1px solid rgba(255, 255, 255, 0.8);
          border-radius: 14px;
          background: rgba(255, 255, 255, 0.8);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), 0 5px 10px rgba(136, 77, 138, 0.08);
          transition: transform 170ms ease, box-shadow 170ms ease;
        }
        .sese-tile.is-active {
          transform: translateY(-2px) scale(1.03);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.96), 0 10px 20px rgba(136, 77, 138, 0.2);
        }
        .sese-tile-start { background: #e0f2f1; }
        .sese-tile-end { background: #fff9c4; }
        .sese-tile-place { background: #e1f5fe; }
        .sese-tile-item { background: #f3e5f5; }
        .sese-tile-task { background: #f8bbd0; }
        .sese-tile-move { background: #fff9c4; }
        .sese-tile-swap { background: #e0f2f1; }
        .sese-tile-clear { background: #ffffff; }
        .sese-tile-time { background: #fff7dd; }
        .sese-tile-limit { background: #ffe3ea; }
        .sese-tile-pose { background: #edf7ff; }
        .sese-tile-theme { background: #f6e9ff; }
        .sese-tile-number {
          position: absolute;
          left: 6px;
          top: 5px;
          color: rgba(136, 77, 138, 0.46);
          font-size: 9px;
          font-weight: 900;
          line-height: 1;
        }
        .sese-tile-icon {
          height: 18px;
          color: var(--text-main);
          font-size: 15px;
          font-weight: 900;
          line-height: 18px;
        }
        .sese-tile-name {
          display: -webkit-box;
          width: calc(100% - 8px);
          min-height: 20px;
          overflow: hidden;
          -webkit-box-orient: vertical;
          -webkit-line-clamp: 2;
          color: var(--text-main);
          font-size: 9px;
          font-weight: 900;
          line-height: 10px;
          text-align: center;
        }
        .sese-piece-stack {
          position: absolute;
          inset: auto 4px 4px;
          display: flex;
          justify-content: center;
          gap: 3px;
          min-height: 17px;
          pointer-events: none;
        }
        .sese-piece {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 16px;
          border: 2px solid #ffffff;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 900;
          line-height: 1;
          box-shadow: 0 5px 10px rgba(68, 42, 77, 0.18);
          animation: sesePiecePop 180ms ease both;
        }
        .sese-piece-xinyue {
          background: #ff6f91;
          color: #ffffff;
        }
        .sese-piece-du {
          background: #7bc9ff;
          color: #ffffff;
        }
        .sese-control-panel {
          margin: 12px auto 0;
          max-width: 720px;
          border: 1px solid rgba(255, 255, 255, 0.78);
          border-radius: 26px;
          background: var(--card-white);
          padding: 12px;
          box-shadow: 0 16px 36px rgba(136, 77, 138, 0.12);
        }
        .sese-player-row {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
        }
        .sese-player-card {
          min-height: 98px;
          border-radius: 20px;
          padding: 10px;
          background: rgba(255, 255, 255, 0.74);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.78);
        }
        .sese-player-card h2 {
          margin: 0 0 7px;
          color: var(--text-main);
          font-size: 14px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-status-list {
          display: flex;
          flex-direction: column;
          gap: 5px;
        }
        .sese-status-item,
        .sese-status-empty {
          border-radius: 12px;
          background: rgba(248, 187, 208, 0.22);
          padding: 6px 7px;
          color: #7c4a80;
          font-size: 11px;
          font-weight: 800;
          line-height: 1.25;
        }
        .sese-status-item span {
          display: block;
          margin-top: 2px;
          color: rgba(124, 74, 128, 0.62);
          font-size: 10px;
          font-weight: 800;
        }
        .sese-roll-row {
          display: grid;
          grid-template-columns: 70px minmax(0, 1fr) 68px;
          gap: 10px;
          align-items: center;
          margin-top: 12px;
        }
        .sese-dice {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 70px;
          height: 70px;
          border: 3px solid #ffffff;
          border-radius: 20px;
          background: #ffffff;
          color: var(--text-main);
          font-size: 42px;
          line-height: 1;
          box-shadow: 0 12px 24px rgba(136, 77, 138, 0.16);
        }
        .sese-dice.rolling {
          animation: seseDiceRoll 120ms linear infinite;
        }
        .sese-roll-button {
          min-width: 0;
          height: 54px;
          border: 0;
          border-radius: 18px;
          background: linear-gradient(135deg, #f48fb1, #ba68c8);
          color: #ffffff;
          font-size: 16px;
          font-weight: 900;
          box-shadow: 0 12px 24px rgba(186, 104, 200, 0.24);
          transition: transform 140ms ease, opacity 140ms ease;
        }
        .sese-quiet-button {
          height: 48px;
          padding: 0 10px;
          font-size: 13px;
          font-weight: 900;
        }
        .sese-log {
          display: flex;
          flex-direction: column;
          gap: 5px;
          margin-top: 12px;
          border-radius: 18px;
          background: rgba(255, 255, 255, 0.62);
          padding: 10px;
        }
        .sese-log p {
          margin: 0;
          color: #7b5a7f;
          font-size: 12px;
          font-weight: 700;
          line-height: 1.35;
        }
        .sese-popup-mask {
          position: fixed;
          inset: 0;
          z-index: 60;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(73, 34, 81, 0.28);
          padding: 24px;
          backdrop-filter: blur(8px);
        }
        .sese-popup {
          width: min(340px, 100%);
          border: 1px solid rgba(255, 255, 255, 0.82);
          border-radius: 28px;
          background: rgba(255, 255, 255, 0.95);
          padding: 20px;
          text-align: center;
          box-shadow: 0 22px 48px rgba(73, 34, 81, 0.24);
        }
        .sese-popup-kicker {
          display: inline-flex;
          border-radius: 999px;
          background: #f3e5f5;
          padding: 5px 10px;
          color: var(--text-light);
          font-size: 11px;
          font-weight: 900;
          line-height: 1;
        }
        .sese-popup h2 {
          margin: 12px 0 8px;
          color: var(--text-main);
          font-size: 20px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-popup p {
          margin: 0;
          color: #7b5a7f;
          font-size: 13px;
          font-weight: 700;
          line-height: 1.55;
          text-align: left;
        }
        .sese-popup button {
          width: 100%;
          height: 44px;
          margin-top: 16px;
          border: 0;
          border-radius: 16px;
          background: linear-gradient(135deg, #f48fb1, #ba68c8);
          color: #ffffff;
          font-size: 14px;
          font-weight: 900;
        }
        @keyframes seseDiceRoll {
          0% { transform: rotate(-8deg) scale(1); }
          50% { transform: rotate(8deg) scale(1.06); }
          100% { transform: rotate(-8deg) scale(1); }
        }
        @keyframes sesePiecePop {
          from { transform: translateY(4px) scale(0.82); opacity: 0.6; }
          to { transform: translateY(0) scale(1); opacity: 1; }
        }
        @media (max-width: 380px) {
          .sese-game {
            padding-left: 10px;
            padding-right: 10px;
          }
          .sese-board {
            gap: 4px;
          }
          .sese-board-wrap {
            border-width: 5px;
            padding: 6px;
          }
          .sese-tile {
            border-radius: 11px;
          }
          .sese-piece {
            width: 21px;
            height: 15px;
          }
          .sese-roll-row {
            grid-template-columns: 62px minmax(0, 1fr) 58px;
          }
          .sese-dice {
            width: 62px;
            height: 62px;
          }
        }
        .sese-game {
          --card-white: rgba(255, 255, 255, 0.85);
          --radius-lg: 24px;
          --radius-md: 16px;
          --shadow-soft: 0 4px 12px rgba(233, 30, 99, 0.1);
          --wavy-border: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 120' preserveAspectRatio='none'%3E%3Cpath d='M0,0V46.29c47.79,22.2,103.59,32.17,158,28,70.36-5.37,136.33-33.31,206.8-37.5C438.64,32.43,512.34,53.67,583,72.05c69.27,18,138.3,24.88,209.4,13.08,36.15-6,69.85-17.84,104.45-29.34C989.49,25,1113-14.29,1200,52.47V0Z' fill='%23f8bbd0'/%3E%3C/svg%3E");
          display: flex;
          flex-direction: column;
          min-height: 100dvh;
          overflow-x: hidden;
          overflow-y: auto;
          padding: 0;
          background: var(--bg-page);
          color: var(--text-main);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }
        .sese-header {
          position: relative;
          z-index: 10;
          display: block;
          max-width: none;
          margin: 0;
          background-color: var(--primary-pink);
          padding: 12px 16px 18px;
        }
        .sese-header::after {
          content: "";
          position: absolute;
          bottom: -24px;
          left: 0;
          width: 100%;
          height: 28px;
          background-image: var(--wavy-border);
          background-size: cover;
          transform: rotate(180deg);
        }
        .sese-back {
          position: absolute;
          left: 10px;
          top: 12px;
          z-index: 12;
          width: 34px;
          height: 34px;
          border: 0;
          border-radius: 50%;
          background: rgba(255,255,255,0.22);
          color: #fff;
          box-shadow: none;
        }
        .sese-chat-entry {
          position: absolute;
          right: 10px;
          top: 12px;
          z-index: 12;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 34px;
          height: 34px;
          border: 0;
          border-radius: 17px;
          background: rgba(255,255,255,0.24);
          color: #fff;
          padding: 0;
          box-shadow: none;
        }
        .sese-chat-entry span {
          position: absolute;
          right: -4px;
          top: -4px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 16px;
          height: 16px;
          border-radius: 8px;
          background: #fff9c4;
          color: var(--text-main);
          font-size: 10px;
          line-height: 1;
        }
        .sese-header-title {
          margin-bottom: 8px;
          color: #fff;
          font-size: 18px;
          font-weight: 900;
          line-height: 1.15;
          text-align: center;
          text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
        }
        .sese-game-status-bar {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 5px 8px;
          border-radius: 14px;
          background: var(--card-white);
          padding: 7px 10px;
          backdrop-filter: blur(5px);
        }
        .sese-pill {
          min-height: 0;
          overflow: hidden;
          border: 0;
          border-radius: 0;
          background: transparent;
          padding: 0;
          box-shadow: none;
          font-size: 11px;
        }
        .sese-pill span {
          display: block;
          color: var(--text-light);
          font-size: 9px;
          font-weight: bold;
          line-height: 1.2;
        }
        .sese-pill strong {
          display: block;
          margin-top: 1px;
          overflow: hidden;
          color: var(--text-main);
          font-size: 11px;
          font-weight: 800;
          line-height: 1.2;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sese-turn-indicator {
          grid-column: span 2;
          margin-top: 1px;
          border-radius: 20px;
          background: var(--accent-yellow);
          padding: 3px;
          font-size: 10px;
          font-weight: bold;
          text-align: center;
        }
        .sese-board-container {
          flex: 0 0 auto;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: visible;
          padding: 30px 12px 20px;
        }
        .sese-board {
          display: grid;
          grid-template-rows: repeat(6, 1fr);
          gap: 4px;
          width: 100%;
          max-width: 400px;
          aspect-ratio: 1 / 1;
          border-radius: var(--radius-lg);
          background: var(--card-white);
          padding: 6px;
          box-shadow: var(--shadow-soft);
          position: relative;
        }
        .sese-tile {
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          aspect-ratio: 1;
          overflow: hidden;
          border: 1px solid rgba(255,255,255,0.5);
          border-radius: 8px;
          background: var(--soft-lavender);
          box-shadow: none;
          transition: all 0.3s;
        }
        .sese-tile.is-active {
          z-index: 5;
          background: var(--accent-yellow) !important;
          transform: scale(1.05);
          box-shadow: 0 0 15px var(--accent-yellow);
        }
        .sese-tile-start,
        .sese-tile-theme { background: #ffecb3; font-weight: bold; }
        .sese-tile-end { background: #b2dfdb; font-weight: bold; }
        .sese-tile-task { background: #f8bbd0; }
        .sese-tile-place { background: #e1f5fe; }
        .sese-tile-pose { background: #d1c4e9; }
        .sese-tile-number {
          position: absolute;
          top: 2px;
          left: 3px;
          color: var(--text-main);
          font-size: 9px;
          font-weight: 400;
          line-height: 1;
          opacity: 0.6;
        }
        .sese-tile-icon {
          height: auto;
          margin-bottom: 2px;
          color: var(--text-main);
          font-size: 14px;
          font-weight: 400;
          line-height: 1;
        }
        .sese-tile-name {
          display: block;
          width: auto;
          min-height: 0;
          max-width: calc(100% - 4px);
          overflow: hidden;
          color: var(--text-main);
          font-size: 8px;
          font-weight: 400;
          line-height: 1.1;
          text-align: center;
          text-overflow: ellipsis;
          transform: scale(0.9);
          white-space: nowrap;
        }
        .sese-piece-stack {
          position: absolute;
          inset: 0;
          min-height: 0;
          pointer-events: none;
        }
        .sese-piece {
          position: absolute;
          z-index: 10;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 20px;
          height: 20px;
          border: 2px solid #fff;
          border-radius: 50%;
          color: #fff;
          font-size: 10px;
          font-weight: bold;
          line-height: 1;
          box-shadow: 0 2px 4px rgba(0,0,0,0.2);
          transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        .sese-piece-me { left: 10%; bottom: 10%; background: #ec407a; }
        .sese-piece-du { right: 10%; bottom: 10%; background: #7e57c2; }
        .sese-piece.paused { filter: grayscale(1); opacity: 0.7; }
        .sese-piece.paused::after {
          content: "🔒";
          position: absolute;
          top: -5px;
          right: -5px;
          font-size: 8px;
        }
        .sese-controls {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 0 16px calc(env(safe-area-inset-bottom, 0px) + 20px);
        }
        .sese-player-states {
          display: flex;
          gap: 10px;
        }
        .sese-player-card {
          flex: 1;
          min-height: 80px;
          border-radius: var(--radius-md);
          background: var(--card-white);
          padding: 8px;
          font-size: 11px;
          box-shadow: none;
        }
        .sese-player-card.active { border: 2px solid var(--primary-pink); }
        .sese-player-card h2 {
          margin: 0 0 4px;
          color: var(--text-main);
          font-size: 11px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-status-list {
          display: block;
        }
        .sese-status-item,
        .sese-status-empty {
          display: inline-block;
          margin: 2px;
          border: 1px solid rgba(0,0,0,0.05);
          border-radius: 4px;
          background: var(--soft-lavender);
          padding: 2px 6px;
          color: var(--text-main);
          font-size: 9px;
          font-weight: 400;
          line-height: 1.2;
        }
        .sese-status-item span {
          display: inline;
          margin: 0 0 0 4px;
          color: var(--text-light);
          font-size: 9px;
          font-weight: 400;
        }
        .sese-action-area {
          display: flex;
          align-items: center;
          gap: 16px;
          border-radius: 40px;
          background: var(--card-white);
          padding: 12px;
        }
        .sese-dice {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 50px;
          height: 50px;
          border: 0;
          border-radius: 12px;
          background: white;
          color: var(--text-main);
          font-size: 24px;
          font-weight: 900;
          line-height: 1;
          box-shadow: inset 0 -4px 0 rgba(0,0,0,0.1), 0 4px 8px rgba(0,0,0,0.1);
        }
        .sese-dice.rolling { animation: seseDiceRoll 0.1s infinite; }
        .sese-roll-button {
          flex: 1;
          height: 50px;
          border: none;
          border-radius: 25px;
          background: var(--primary-pink);
          color: white;
          font-size: 18px;
          font-weight: 900;
          box-shadow: 0 4px 0 #d81b60;
          transition: all 0.1s;
        }
        .sese-roll-button:active {
          transform: translateY(2px);
          box-shadow: 0 2px 0 #d81b60;
        }
        .sese-roll-button:disabled {
          background: #ce93d8;
          box-shadow: 0 4px 0 #ab47bc;
          opacity: 0.7;
        }
        .sese-history {
          padding: 0 10px;
          color: var(--text-light);
          font-size: 10px;
          text-align: center;
        }
        .sese-chat-mask {
          position: fixed;
          inset: 0;
          z-index: 110;
          display: flex;
          align-items: flex-start;
          justify-content: flex-end;
          background: rgba(136, 77, 138, 0.18);
          padding: calc(env(safe-area-inset-top, 0px) + 54px) 14px 14px;
          backdrop-filter: blur(2px);
        }
        .sese-chat-panel {
          display: flex;
          flex-direction: column;
          width: min(360px, calc(100vw - 28px));
          max-height: min(70dvh, 560px);
          overflow: hidden;
          border: 2px solid rgba(248, 187, 208, 0.9);
          border-radius: 18px;
          background: #fff6fb;
          box-shadow: 0 18px 42px rgba(136, 77, 138, 0.22);
        }
        .sese-chat-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          border-bottom: 1px solid rgba(186, 104, 200, 0.16);
          background: #f8bbd0;
          padding: 9px 10px;
          color: #fff;
        }
        .sese-chat-head strong,
        .sese-chat-head span {
          display: block;
          line-height: 1.2;
        }
        .sese-chat-head strong {
          font-size: 13px;
          font-weight: 900;
        }
        .sese-chat-head span {
          margin-top: 2px;
          font-size: 10px;
          font-weight: 700;
          opacity: 0.9;
        }
        .sese-chat-head button {
          flex: 0 0 28px;
          width: 28px;
          height: 28px;
          border: 0;
          border-radius: 50%;
          background: rgba(255,255,255,0.24);
          color: #fff;
          font-size: 20px;
          font-weight: 700;
          line-height: 1;
        }
        .sese-chat-list {
          display: flex;
          flex: 1;
          min-height: 180px;
          flex-direction: column;
          gap: 8px;
          overflow-y: auto;
          padding: 10px;
        }
        .sese-chat-message {
          max-width: 86%;
          border-radius: 12px;
          padding: 7px 9px;
          color: var(--text-main);
          font-size: 12px;
          line-height: 1.45;
        }
        .sese-chat-message span {
          display: block;
          margin-bottom: 2px;
          font-size: 9px;
          font-weight: 900;
          opacity: 0.72;
        }
        .sese-chat-message p {
          margin: 0;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .sese-chat-message.xinyue {
          align-self: flex-end;
          background: #ffe0ec;
        }
        .sese-chat-message.du {
          align-self: flex-start;
          background: #efe7f6;
        }
        .sese-chat-message.system {
          align-self: center;
          max-width: 100%;
          background: #fff9c4;
          color: #8a6d3b;
          font-size: 10px;
          text-align: center;
        }
        .sese-chat-message.pending {
          opacity: 0.72;
        }
        .sese-chat-form {
          display: flex;
          gap: 6px;
          border-top: 1px solid rgba(186, 104, 200, 0.16);
          background: rgba(255,255,255,0.74);
          padding: 8px;
        }
        .sese-chat-form input {
          flex: 1;
          min-width: 0;
          height: 36px;
          border: 1px solid rgba(186, 104, 200, 0.22);
          border-radius: 18px;
          background: #fff;
          color: var(--text-main);
          padding: 0 12px;
          font-size: 12px;
          outline: none;
        }
        .sese-chat-form input:disabled {
          opacity: 0.6;
        }
        .sese-chat-form button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          flex: 0 0 44px;
          width: 44px;
          height: 36px;
          border: 0;
          border-radius: 18px;
          background: #f06292;
          color: #fff;
          font-size: 13px;
          font-weight: 900;
          box-shadow: 0 3px 0 #d81b60;
        }
        .sese-chat-form button svg {
          color: currentColor;
        }
        .sese-chat-form button:disabled {
          opacity: 0.5;
        }
        .sese-popup-mask {
          position: fixed;
          inset: 0;
          z-index: 100;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(136, 77, 138, 0.4);
          padding: 0;
          backdrop-filter: blur(4px);
        }
        .sese-popup {
          width: 80%;
          border: 4px solid var(--primary-pink);
          border-radius: var(--radius-lg);
          background: white;
          padding: 24px;
          text-align: center;
          box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }
        .sese-popup-kicker { display: none; }
        .sese-popup h2 {
          margin: 0 0 12px;
          color: var(--text-main);
          font-size: 20px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-popup p {
          margin: 0 0 20px;
          color: #666;
          font-size: 14px;
          font-weight: 400;
          line-height: 1.6;
          text-align: center;
        }
        .sese-popup button {
          width: auto;
          height: auto;
          margin: 0;
          border: none;
          border-radius: 20px;
          background: var(--primary-pink);
          color: white;
          padding: 12px 30px;
          font-size: 14px;
          font-weight: bold;
          box-shadow: none;
        }
        @keyframes seseDiceRoll {
          0% { transform: rotate(0deg) scale(1); }
          50% { transform: rotate(10deg) scale(1.1); }
          100% { transform: rotate(-10deg) scale(1); }
        }
        `}
      </style>
    </div>
  );
}

function StatusPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="sese-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PlayerStateCard({ actor, statuses, active }: { actor: Actor; statuses: StatusItem[]; active: boolean }) {
  const shown = statuses.slice(-3).reverse();
  return (
    <div className={`sese-player-card sese-player-card-${actor} ${active ? "active" : ""}`}>
      <h2>{actor === "xinyue" ? "我的状态" : "渡的状态"}</h2>
      <div className="sese-status-list">
        {shown.length ? shown.map((item, index) => {
          const label = displayText(item.label || item.slot || "状态");
          const value = displayText(item.value || "");
          const duration = statusDuration(item);
          return (
            <div className="sese-status-item" key={`${label}-${value}-${index}`}>
              {label}{value ? `：${value}` : ""}
              {duration ? <span>{duration}</span> : null}
            </div>
          );
        }) : <div className="sese-status-empty">无状态</div>}
      </div>
    </div>
  );
}
