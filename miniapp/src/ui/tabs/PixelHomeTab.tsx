import React, { useEffect, useMemo, useRef, useState } from "react";
import roomImage from "../../assets/pixel-home-room.png";

type Pos = { x: number; y: number };
type DuMode = "follow" | "wander" | "sit" | "garden";
type DecorKind = "lamp" | "plant" | "flower" | "book";
type PlacedDecor = { id: string; kind: DecorKind; x: number; y: number };

const COLS = 24;
const ROWS = 24;
const STORAGE_KEY = "miniapp.pixel-home.v2";

const AREAS = {
  bedroom: { x1: 1, y1: 1, x2: 8, y2: 12 },
  kitchen: { x1: 7, y1: 1, x2: 17, y2: 9 },
  living: { x1: 7, y1: 8, x2: 18, y2: 18 },
  bathroom: { x1: 17, y1: 1, x2: 21, y2: 9 },
  garden: { x1: 0, y1: 18, x2: 23, y2: 23 },
  sidePath: { x1: 19, y1: 8, x2: 23, y2: 23 },
};

const BLOCKED_RECTS = [
  { x1: 1, y1: 1, x2: 6, y2: 7 },
  { x1: 2, y1: 11, x2: 7, y2: 13 },
  { x1: 8, y1: 2, x2: 18, y2: 7 },
  { x1: 12, y1: 7, x2: 17, y2: 11 },
  { x1: 10, y1: 11, x2: 16, y2: 15 },
  { x1: 11, y1: 15, x2: 16, y2: 18 },
  { x1: 18, y1: 2, x2: 21, y2: 7 },
  { x1: 21, y1: 8, x2: 23, y2: 12 },
  { x1: 0, y1: 19, x2: 3, y2: 23 },
  { x1: 20, y1: 19, x2: 23, y2: 23 },
];

const POIS: Record<DuMode, Pos[]> = {
  follow: [],
  wander: [
    { x: 6, y: 9 },
    { x: 10, y: 8 },
    { x: 17, y: 12 },
    { x: 9, y: 18 },
    { x: 19, y: 16 },
  ],
  sit: [
    { x: 9, y: 13 },
    { x: 17, y: 15 },
    { x: 8, y: 10 },
  ],
  garden: [
    { x: 8, y: 21 },
    { x: 14, y: 19 },
    { x: 20, y: 15 },
  ],
};

const DECOR_META: Record<DecorKind, { label: string; mark: string; color: string }> = {
  lamp: { label: "小灯", mark: "◆", color: "#F3CE75" },
  plant: { label: "盆栽", mark: "♣", color: "#6DAA62" },
  flower: { label: "花", mark: "✿", color: "#E99AAF" },
  book: { label: "书", mark: "▣", color: "#9B8A72" },
};

function insideRect(pos: Pos, rect: { x1: number; y1: number; x2: number; y2: number }): boolean {
  return pos.x >= rect.x1 && pos.x <= rect.x2 && pos.y >= rect.y1 && pos.y <= rect.y2;
}

function keyOf(pos: Pos): string {
  return `${pos.x}:${pos.y}`;
}

function clampPos(pos: Pos): Pos {
  return {
    x: Math.max(0, Math.min(COLS - 1, pos.x)),
    y: Math.max(0, Math.min(ROWS - 1, pos.y)),
  };
}

function isInKnownArea(pos: Pos): boolean {
  return Object.values(AREAS).some((area) => insideRect(pos, area));
}

function isWalkable(pos: Pos): boolean {
  const p = clampPos(pos);
  if (p.x !== pos.x || p.y !== pos.y) return false;
  if (!isInKnownArea(p)) return false;
  if (BLOCKED_RECTS.some((rect) => insideRect(p, rect))) return false;
  return true;
}

function neighbors(pos: Pos): Pos[] {
  return [
    { x: pos.x + 1, y: pos.y },
    { x: pos.x - 1, y: pos.y },
    { x: pos.x, y: pos.y + 1 },
    { x: pos.x, y: pos.y - 1 },
  ].filter(isWalkable);
}

function findPath(from: Pos, to: Pos): Pos[] | null {
  if (!isWalkable(from) || !isWalkable(to)) return null;
  const startKey = keyOf(from);
  const endKey = keyOf(to);
  const queue: Pos[] = [from];
  const cameFrom = new Map<string, string | null>([[startKey, null]]);
  const byKey = new Map<string, Pos>([[startKey, from]]);
  for (let head = 0; head < queue.length; head += 1) {
    const current = queue[head];
    const currentKey = keyOf(current);
    if (currentKey === endKey) break;
    for (const next of neighbors(current)) {
      const nextKey = keyOf(next);
      if (cameFrom.has(nextKey)) continue;
      cameFrom.set(nextKey, currentKey);
      byKey.set(nextKey, next);
      queue.push(next);
    }
  }
  if (!cameFrom.has(endKey)) return null;
  const path: Pos[] = [];
  let cursor: string | null = endKey;
  while (cursor) {
    const pos = byKey.get(cursor);
    if (pos) path.push(pos);
    cursor = cameFrom.get(cursor) ?? null;
  }
  return path.reverse();
}

function nearestReachableWalkable(from: Pos, target: Pos): Pos | null {
  if (!isWalkable(from)) return null;
  const queue: Pos[] = [from];
  const seen = new Set<string>([keyOf(from)]);
  let best = from;
  let bestScore = distance(from, target);
  for (let head = 0; head < queue.length; head += 1) {
    const current = queue[head];
    const score = distance(current, target);
    if (score < bestScore) {
      best = current;
      bestScore = score;
    }
    for (const next of neighbors(current)) {
      const nextKey = keyOf(next);
      if (seen.has(nextKey)) continue;
      seen.add(nextKey);
      queue.push(next);
    }
  }
  return best;
}

function stepToward(from: Pos, to: Pos): Pos {
  if (distance(from, to) === 0) return from;
  const path = findPath(from, to);
  return path?.[1] || from;
}

function distance(a: Pos, b: Pos): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function loadSaved() {
  const fallback = {
    player: { x: 8, y: 13 },
    du: { x: 9, y: 13 },
    mode: "follow" as DuMode,
    decor: [] as PlacedDecor[],
  };
  try {
    const raw = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    return {
      player: isWalkable(raw.player) ? raw.player as Pos : fallback.player,
      du: isWalkable(raw.du) ? raw.du as Pos : fallback.du,
      mode: ["follow", "wander", "sit", "garden"].includes(raw.mode) ? raw.mode as DuMode : fallback.mode,
      decor: Array.isArray(raw.decor)
        ? raw.decor.filter((item: any) => item && DECOR_META[item.kind as DecorKind] && isWalkable({ x: Number(item.x), y: Number(item.y) })) as PlacedDecor[]
        : fallback.decor,
    };
  } catch {
    return fallback;
  }
}

function describePlace(pos: Pos): string {
  if (insideRect(pos, AREAS.garden) || insideRect(pos, AREAS.sidePath)) return "小花园";
  if (insideRect(pos, AREAS.bedroom)) return "卧室";
  if (insideRect(pos, AREAS.kitchen)) return "厨房";
  if (insideRect(pos, AREAS.bathroom)) return "浴室门口";
  return "客厅";
}

function duLine(mode: DuMode, player: Pos, du: Pos, decor: PlacedDecor[]): string {
  if (distance(player, du) <= 1) return "渡停在你旁边，像素小人轻轻晃了一下。";
  if (mode === "follow") return "渡在往你这边走，路线会绕开家具。";
  if (mode === "sit") return "渡去沙发附近坐一会儿，等你过去。";
  if (mode === "garden") return "渡往花园那边走，像是想看看花。";
  if (decor.length) return `渡在屋里慢慢逛，刚才看了一眼${DECOR_META[decor[decor.length - 1].kind].label}。`;
  return "渡在小家里自由走动，偶尔停在窗边。";
}

function makeDecor(kind: DecorKind, pos: Pos): PlacedDecor {
  return {
    id: `${kind}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    kind,
    x: pos.x,
    y: pos.y,
  };
}

export function PixelHomeTab() {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const saved = useMemo(loadSaved, []);
  const [player, setPlayer] = useState<Pos>(saved.player);
  const [du, setDu] = useState<Pos>(saved.du);
  const [mode, setMode] = useState<DuMode>(saved.mode);
  const [duTarget, setDuTarget] = useState<Pos | null>(null);
  const [playerTarget, setPlayerTarget] = useState<Pos | null>(null);
  const [decor, setDecor] = useState<PlacedDecor[]>(saved.decor);
  const [decorateMode, setDecorateMode] = useState(false);
  const [selectedDecor, setSelectedDecor] = useState<DecorKind>("plant");
  const [line, setLine] = useState(() => duLine(saved.mode, saved.player, saved.du, saved.decor));

  const occupied = useMemo(() => new Set(decor.map((item) => keyOf(item))), [decor]);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ player, du, mode, decor }));
    } catch {}
  }, [player, du, mode, decor]);

  useEffect(() => {
    if (!playerTarget) return;
    const timer = window.setInterval(() => {
      setPlayer((current) => {
        if (distance(current, playerTarget) === 0) {
          setPlayerTarget(null);
          return current;
        }
        const next = stepToward(current, playerTarget);
        if (keyOf(next) === keyOf(current)) setPlayerTarget(null);
        return next;
      });
    }, 140);
    return () => window.clearInterval(timer);
  }, [playerTarget]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setDu((current) => {
        let nextTarget = duTarget;
        if (mode === "follow") {
          const candidates = [
            { x: player.x + 1, y: player.y },
            { x: player.x - 1, y: player.y },
            { x: player.x, y: player.y + 1 },
            { x: player.x, y: player.y - 1 },
          ]
            .filter(isWalkable)
            .map((candidate) => ({ candidate, path: findPath(current, candidate) }))
            .filter((item): item is { candidate: Pos; path: Pos[] } => Boolean(item.path))
            .sort((a, b) => a.path.length - b.path.length);
          nextTarget = candidates[0]?.candidate || nearestReachableWalkable(current, player) || current;
        } else if (!nextTarget || distance(current, nextTarget) === 0) {
          const list = POIS[mode]
            .map((poi) => nearestReachableWalkable(current, poi))
            .filter((poi): poi is Pos => Boolean(poi));
          nextTarget = list[Math.floor(Math.random() * list.length)] || current;
          setDuTarget(nextTarget);
        }
        const next = nextTarget ? stepToward(current, nextTarget) : current;
        setLine(duLine(mode, player, next, decor));
        return next;
      });
    }, 720);
    return () => window.clearInterval(timer);
  }, [decor, mode, player, duTarget]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const map: Record<string, Pos> = {
        ArrowUp: { x: 0, y: -1 },
        ArrowDown: { x: 0, y: 1 },
        ArrowLeft: { x: -1, y: 0 },
        ArrowRight: { x: 1, y: 0 },
        w: { x: 0, y: -1 },
        s: { x: 0, y: 1 },
        a: { x: -1, y: 0 },
        d: { x: 1, y: 0 },
      };
      const delta = map[e.key];
      if (!delta) return;
      e.preventDefault();
      movePlayer(delta);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  function movePlayer(delta: Pos) {
    setPlayerTarget(null);
    setPlayer((current) => {
      const next = { x: current.x + delta.x, y: current.y + delta.y };
      return isWalkable(next) ? next : current;
    });
  }

  function changeMode(nextMode: DuMode) {
    setMode(nextMode);
    setDuTarget(null);
    setLine(
      nextMode === "follow"
        ? "渡点点头，走到你身边。"
        : nextMode === "wander"
          ? "渡开始自己在小家里慢慢逛。"
          : nextMode === "sit"
            ? "渡往沙发那边走。"
            : "渡看向小花园，像是想出去透口气。",
    );
  }

  function decideForDu() {
    const next: DuMode = player.y >= 18 ? "garden" : decor.length >= 2 ? "wander" : distance(player, du) > 5 ? "follow" : "sit";
    changeMode(next);
  }

  function interact() {
    const place = describePlace(player);
    if (distance(player, du) <= 1) {
      setLine(`${place}。渡离你很近，说：先在这里待一会儿，我跟着你。`);
      return;
    }
    setLine(`${place}。渡抬头看你的位置，正慢慢走过来。`);
    changeMode("follow");
  }

  function handleStageClick(e: React.MouseEvent<HTMLDivElement>) {
    if (!stageRef.current) return;
    const rect = stageRef.current.getBoundingClientRect();
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * COLS);
    const y = Math.floor(((e.clientY - rect.top) / rect.height) * ROWS);
    const clicked = { x, y };
    const pos = nearestReachableWalkable(player, clicked) || player;
    if (decorateMode) {
      if (occupied.has(keyOf(pos))) {
        setLine("这里放不下，换一格。");
        return;
      }
      setDecor((current) => [...current, makeDecor(selectedDecor, pos)].slice(-18));
      setLine(`你把${DECOR_META[selectedDecor].label}放好了，渡会过去看的。`);
      return;
    }
    setPlayerTarget(pos);
    setLine(`你往${describePlace(pos)}走。`);
  }

  function clearDecor() {
    setDecor([]);
    setLine("叠加摆件清掉了，房间底图还在。");
  }

  return (
    <div className="min-h-full bg-[#EEE6D2] px-2 pb-8 pt-4 text-[#3C352B]" style={{ fontFamily: "'Microsoft YaHei', sans-serif" }}>
      <div className="mx-auto flex w-full max-w-[520px] flex-col gap-3">
        <div className="flex items-end justify-between px-1">
          <div>
            <div className="text-[20px] font-semibold tracking-tight">像素小家</div>
            <div className="mt-1 text-[12px] text-[#7B6D5A]">小房子 · 花园 · 点地图移动</div>
          </div>
          <div className="rounded-full border border-[#D6C4A7] bg-[#FFF7E8] px-3 py-1 text-[11px] text-[#7B6D5A]">
            {describePlace(player)}
          </div>
        </div>

        <div
          ref={stageRef}
          className="relative mx-auto w-full overflow-hidden rounded-[18px] border-[3px] border-[#7B654C] bg-[#B4C7A4] shadow-[0_14px_34px_rgba(85,64,38,0.20)]"
          style={{ aspectRatio: "1 / 1", imageRendering: "pixelated" }}
          onClick={handleStageClick}
        >
          <img
            src={roomImage}
            alt="像素小家"
            className="absolute inset-0 h-full w-full select-none object-cover"
            draggable={false}
            style={{ imageRendering: "pixelated" }}
          />
          <WalkHint pos={playerTarget} />
          {decor.map((item) => (
            <DecorItem key={item.id} item={item} />
          ))}
          <PixelPerson pos={du} tone="du" label="渡" />
          <PixelPerson pos={player} tone="me" label="我" />
        </div>

        <div className="rounded-[16px] border border-[#DCC8A8] bg-[#FFF8EA] p-3 shadow-[0_6px_18px_rgba(96,72,43,0.08)]">
          <div className="mb-1 text-[11px] font-semibold tracking-[0.18em] text-[#A17855]">DU</div>
          <div className="text-[14px] leading-relaxed text-[#3C352B]">{line}</div>
        </div>

        <div className="grid grid-cols-4 gap-2">
          <ModeButton active={mode === "follow"} label="跟着我" onClick={() => changeMode("follow")} />
          <ModeButton active={mode === "wander"} label="自由走" onClick={() => changeMode("wander")} />
          <ModeButton active={mode === "sit"} label="坐一会" onClick={() => changeMode("sit")} />
          <ModeButton active={mode === "garden"} label="看花园" onClick={() => changeMode("garden")} />
        </div>

        <div className="grid grid-cols-[84px_1fr_84px] items-center gap-3">
          <button className="rounded-[14px] border border-[#D6C4A7] bg-[#FFF8EA] px-3 py-3 text-[12px] font-semibold text-[#5F4C36] active:translate-y-px" onClick={decideForDu}>
            渡决定
          </button>
          <DPad onMove={movePlayer} />
          <button className="rounded-[14px] border border-[#D6C4A7] bg-[#FFF8EA] px-3 py-3 text-[12px] font-semibold text-[#5F4C36] active:translate-y-px" onClick={interact}>
            互动
          </button>
        </div>

        <div className="rounded-[16px] border border-[#DCC8A8] bg-[#FFF8EA] p-3">
          <div className="mb-3 flex items-center justify-between">
            <button
              className={`rounded-full px-3 py-1.5 text-[12px] font-semibold ${decorateMode ? "bg-[#6C5942] text-white" : "bg-[#EFE0CB] text-[#5F4C36]"}`}
              onClick={() => setDecorateMode((v) => !v)}
            >
              {decorateMode ? "布置中" : "布置"}
            </button>
            <button className="text-[12px] text-[#9A6B52]" onClick={clearDecor}>清空摆件</button>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {(Object.keys(DECOR_META) as DecorKind[]).map((kind) => {
              const meta = DECOR_META[kind];
              const active = selectedDecor === kind;
              return (
                <button
                  key={kind}
                  className={`rounded-[12px] border px-2 py-2 text-[11px] ${active ? "border-[#6C5942] bg-[#F4E0B8]" : "border-[#E4D2BA] bg-[#FFFDF8]"}`}
                  onClick={() => {
                    setSelectedDecor(kind);
                    setDecorateMode(true);
                  }}
                >
                  <span className="mr-1 font-black" style={{ color: meta.color }}>{meta.mark}</span>
                  {meta.label}
                </button>
              );
            })}
          </div>
          <div className="mt-2 text-[11px] leading-relaxed text-[#8B7B65]">
            普通模式点地图移动；布置模式点地图叠加小摆件。
          </div>
        </div>
      </div>
    </div>
  );
}

function DecorItem({ item }: { item: PlacedDecor }) {
  const meta = DECOR_META[item.kind];
  return (
    <div
      className="absolute z-10 flex items-center justify-center rounded-[4px] border border-[#6B563D] bg-[#FFF8EA] text-[13px] font-black leading-none shadow-[0_2px_0_rgba(80,55,28,0.22)]"
      style={{
        left: `${(item.x / COLS) * 100}%`,
        top: `${(item.y / ROWS) * 100}%`,
        width: `${(1 / COLS) * 100}%`,
        height: `${(1 / ROWS) * 100}%`,
        color: meta.color,
      }}
      title={meta.label}
    >
      {meta.mark}
    </div>
  );
}

function WalkHint({ pos }: { pos: Pos | null }) {
  if (!pos) return null;
  return (
    <div
      className="absolute z-10 rounded-full border-2 border-[#FFF4BE] bg-[#F5CE69]/70 shadow-[0_0_0_2px_rgba(99,73,38,0.28)]"
      style={{
        left: `${((pos.x + 0.22) / COLS) * 100}%`,
        top: `${((pos.y + 0.22) / ROWS) * 100}%`,
        width: `${(0.56 / COLS) * 100}%`,
        height: `${(0.56 / ROWS) * 100}%`,
      }}
    />
  );
}

function PixelPerson({ pos, tone, label }: { pos: Pos; tone: "me" | "du"; label: string }) {
  const colors = tone === "du"
    ? { skin: "#F0C98F", hair: "#5A3E2D", shirt: "#F6D17C", pants: "#6E563A", accent: "#FFF0BD", outline: "#4D3526" }
    : { skin: "#F1B9A7", hair: "#2D2430", shirt: "#F3A7B6", pants: "#8B5F5A", accent: "#F86F8C", outline: "#4D3526" };
  return (
    <div
      className="absolute z-20"
      style={{
        left: `${((pos.x + 0.02) / COLS) * 100}%`,
        top: `${((pos.y - 0.08) / ROWS) * 100}%`,
        width: `${(0.78 / COLS) * 100}%`,
        height: `${(1.08 / ROWS) * 100}%`,
        transition: "left 180ms linear, top 180ms linear",
        filter: "drop-shadow(0 2px 0 rgba(83,58,32,0.26))",
      }}
      aria-label={label}
    >
      <div className="relative h-full w-full">
        <div className="absolute bottom-0 left-[18%] h-[12%] w-[64%] rounded-full bg-black/20" />
        <div className="absolute left-[18%] top-[6%] h-[45%] w-[64%] border-2" style={{ background: colors.skin, borderColor: colors.outline }} />
        <div className="absolute left-[10%] top-[2%] h-[22%] w-[80%] border-2" style={{ background: colors.hair, borderColor: colors.outline }} />
        <div className="absolute left-[13%] top-[23%] h-[18%] w-[13%]" style={{ background: colors.hair }} />
        <div className="absolute right-[13%] top-[23%] h-[18%] w-[13%]" style={{ background: colors.hair }} />
        {tone === "me" ? (
          <>
            <div className="absolute left-[5%] top-[4%] h-[12%] w-[14%]" style={{ background: colors.accent }} />
            <div className="absolute right-[5%] top-[4%] h-[12%] w-[14%]" style={{ background: colors.accent }} />
          </>
        ) : null}
        <div className="absolute left-[32%] top-[28%] h-[8%] w-[8%] bg-[#1F1A18]" />
        <div className="absolute right-[32%] top-[28%] h-[8%] w-[8%] bg-[#1F1A18]" />
        <div className="absolute left-[29%] top-[43%] h-[7%] w-[42%]" style={{ background: colors.accent }} />
        <div className="absolute left-[22%] top-[50%] h-[30%] w-[56%] border-2" style={{ background: colors.shirt, borderColor: colors.outline }} />
        <div className="absolute left-[4%] top-[54%] h-[24%] w-[18%] border-2" style={{ background: colors.skin, borderColor: colors.outline }} />
        <div className="absolute right-[4%] top-[54%] h-[24%] w-[18%] border-2" style={{ background: colors.skin, borderColor: colors.outline }} />
        <div className="absolute left-[27%] bottom-[7%] h-[18%] w-[18%] border-2" style={{ background: colors.pants, borderColor: colors.outline }} />
        <div className="absolute right-[27%] bottom-[7%] h-[18%] w-[18%] border-2" style={{ background: colors.pants, borderColor: colors.outline }} />
      </div>
    </div>
  );
}

function DPad({ onMove }: { onMove: (delta: Pos) => void }) {
  const btn = "flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#D6C4A7] bg-[#FFF8EA] text-[16px] font-black text-[#5F4C36] active:translate-y-px";
  return (
    <div className="mx-auto grid w-[124px] grid-cols-3 gap-1">
      <div />
      <button className={btn} onClick={() => onMove({ x: 0, y: -1 })}>↑</button>
      <div />
      <button className={btn} onClick={() => onMove({ x: -1, y: 0 })}>←</button>
      <div className="h-10 w-10 rounded-[12px] border border-[#EADDC9] bg-[#EFE0CB]" />
      <button className={btn} onClick={() => onMove({ x: 1, y: 0 })}>→</button>
      <div />
      <button className={btn} onClick={() => onMove({ x: 0, y: 1 })}>↓</button>
      <div />
    </div>
  );
}

function ModeButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className={`rounded-[14px] border px-2 py-2 text-[12px] font-semibold active:translate-y-px ${
        active ? "border-[#6C5942] bg-[#6C5942] text-white" : "border-[#D6C4A7] bg-[#FFF8EA] text-[#5F4C36]"
      }`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
