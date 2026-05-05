import React, { useEffect, useMemo, useRef, useState } from "react";

type Pos = { x: number; y: number };
type DuMode = "follow" | "wander" | "sit" | "garden";
type DecorKind = "lamp" | "plant" | "rug" | "cups";
type PlacedDecor = { id: string; kind: DecorKind; x: number; y: number };

const COLS = 13;
const ROWS = 15;
const STORAGE_KEY = "miniapp.pixel-home.v1";

const POIS: Record<DuMode, Pos[]> = {
  follow: [],
  wander: [
    { x: 3, y: 6 },
    { x: 8, y: 6 },
    { x: 5, y: 2 },
    { x: 10, y: 11 },
    { x: 2, y: 13 },
  ],
  sit: [
    { x: 3, y: 6 },
    { x: 9, y: 12 },
  ],
  garden: [
    { x: 3, y: 12 },
    { x: 10, y: 12 },
    { x: 6, y: 13 },
  ],
};

const DECOR_META: Record<DecorKind, { label: string; mark: string; color: string }> = {
  lamp: { label: "小夜灯", mark: "◆", color: "#F7D77B" },
  plant: { label: "盆栽", mark: "♣", color: "#79B986" },
  rug: { label: "小地毯", mark: "▰", color: "#D9A9BA" },
  cups: { label: "两只杯子", mark: "◍", color: "#D6EEF1" },
};

const FURNITURE = [
  { id: "bed", label: "床", x: 2, y: 1, w: 3, h: 2, color: "#EBC8C8", text: "bed" },
  { id: "desk", label: "书桌", x: 7, y: 2, w: 2, h: 1, color: "#C7B090", text: "desk" },
  { id: "shelf", label: "书架", x: 10, y: 1, w: 1, h: 3, color: "#9C7A5C", text: "books" },
  { id: "sofa", label: "沙发", x: 2, y: 6, w: 3, h: 1, color: "#B7C7DF", text: "sofa" },
  { id: "table", label: "小桌", x: 5, y: 7, w: 2, h: 1, color: "#D7B88C", text: "tea" },
  { id: "kitchen", label: "厨房", x: 8, y: 7, w: 3, h: 1, color: "#BFD4CC", text: "kitchen" },
  { id: "bench", label: "长椅", x: 8, y: 12, w: 3, h: 1, color: "#A87455", text: "bench" },
];

const BLOCKED = new Set<string>();
for (const item of FURNITURE) {
  for (let dx = 0; dx < item.w; dx += 1) {
    for (let dy = 0; dy < item.h; dy += 1) {
      BLOCKED.add(keyOf({ x: item.x + dx, y: item.y + dy }));
    }
  }
}
BLOCKED.delete(keyOf({ x: 3, y: 6 }));
BLOCKED.delete(keyOf({ x: 9, y: 12 }));

function keyOf(pos: Pos): string {
  return `${pos.x}:${pos.y}`;
}

function clampPos(pos: Pos): Pos {
  return {
    x: Math.max(0, Math.min(COLS - 1, pos.x)),
    y: Math.max(0, Math.min(ROWS - 1, pos.y)),
  };
}

function isInsideHouse(pos: Pos): boolean {
  return pos.y <= 9 && pos.x >= 1 && pos.x <= 11;
}

function isGarden(pos: Pos): boolean {
  return pos.y >= 10;
}

function isWalkable(pos: Pos): boolean {
  const p = clampPos(pos);
  if (p.x !== pos.x || p.y !== pos.y) return false;
  if (!isInsideHouse(p) && !isGarden(p)) return false;
  if (BLOCKED.has(keyOf(p))) return false;
  return true;
}

function stepToward(from: Pos, to: Pos): Pos {
  const options: Pos[] = [];
  const dx = Math.sign(to.x - from.x);
  const dy = Math.sign(to.y - from.y);
  if (Math.abs(to.x - from.x) >= Math.abs(to.y - from.y)) {
    if (dx) options.push({ x: from.x + dx, y: from.y });
    if (dy) options.push({ x: from.x, y: from.y + dy });
  } else {
    if (dy) options.push({ x: from.x, y: from.y + dy });
    if (dx) options.push({ x: from.x + dx, y: from.y });
  }
  options.push({ x: from.x + 1, y: from.y }, { x: from.x - 1, y: from.y }, { x: from.x, y: from.y + 1 }, { x: from.x, y: from.y - 1 });
  return options.find(isWalkable) || from;
}

function distance(a: Pos, b: Pos): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function loadSaved() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    return {
      player: isWalkable(raw.player) ? raw.player as Pos : { x: 6, y: 8 },
      du: isWalkable(raw.du) ? raw.du as Pos : { x: 7, y: 8 },
      mode: ["follow", "wander", "sit", "garden"].includes(raw.mode) ? raw.mode as DuMode : "follow",
      decor: Array.isArray(raw.decor) ? raw.decor.filter((x: any) => x && DECOR_META[x.kind as DecorKind] && isWalkable({ x: Number(x.x), y: Number(x.y) })) as PlacedDecor[] : [],
    };
  } catch {
    return {
      player: { x: 6, y: 8 },
      du: { x: 7, y: 8 },
      mode: "follow" as DuMode,
      decor: [] as PlacedDecor[],
    };
  }
}

function tileFor(pos: Pos) {
  if (isInsideHouse(pos)) {
    if (pos.y === 4) return { bg: "#D6E2EA", border: "#AEBAC3" };
    if (pos.y <= 4) return { bg: "#F4E5CB", border: "#D9C8AA" };
    return { bg: "#F0DCC0", border: "#D0B998" };
  }
  if (pos.y === 10 || pos.x === 6) return { bg: "#D9C7AA", border: "#B8A080" };
  return { bg: "#BFD8A7", border: "#96B780" };
}

function describePlace(pos: Pos): string {
  if (pos.y <= 4) return "二楼";
  if (pos.y <= 9) return "一楼";
  return "小花园";
}

function duLine(mode: DuMode, player: Pos, du: Pos, decor: PlacedDecor[]): string {
  if (distance(player, du) <= 1) return "渡在你旁边慢半拍停下，像素小人朝你转过来。";
  if (mode === "follow") return "渡正在跟着你，从楼梯边绕过来。";
  if (mode === "sit") return "渡去沙发或花园长椅那边坐一会儿，等你过去。";
  if (mode === "garden") return "渡往花园走，像是想看看花有没有开。";
  if (decor.length) return `渡在屋里慢慢逛，刚才还看了一眼${DECOR_META[decor[decor.length - 1].kind].label}。`;
  return "渡在小洋楼里自由走动，偶尔停下来看看窗外。";
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
  const [target, setTarget] = useState<Pos | null>(null);
  const [decor, setDecor] = useState<PlacedDecor[]>(saved.decor);
  const [decorateMode, setDecorateMode] = useState(false);
  const [selectedDecor, setSelectedDecor] = useState<DecorKind>("lamp");
  const [line, setLine] = useState(() => duLine(saved.mode, saved.player, saved.du, saved.decor));

  const occupied = useMemo(() => new Set(decor.map((item) => keyOf(item))), [decor]);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ player, du, mode, decor }));
    } catch {}
  }, [player, du, mode, decor]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setDu((current) => {
        let nextTarget = target;
        if (mode === "follow") {
          const candidates = [
            { x: player.x + 1, y: player.y },
            { x: player.x - 1, y: player.y },
            { x: player.x, y: player.y + 1 },
            { x: player.x, y: player.y - 1 },
          ].filter(isWalkable);
          nextTarget = candidates.sort((a, b) => distance(current, a) - distance(current, b))[0] || player;
        } else if (!nextTarget || distance(current, nextTarget) === 0) {
          const list = POIS[mode].filter(isWalkable);
          nextTarget = list[Math.floor(Math.random() * list.length)] || current;
          setTarget(nextTarget);
        }
        const next = nextTarget ? stepToward(current, nextTarget) : current;
        setLine(duLine(mode, player, next, decor));
        return next;
      });
    }, 760);
    return () => window.clearInterval(timer);
  }, [decor, mode, player, target]);

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
    setPlayer((current) => {
      const next = { x: current.x + delta.x, y: current.y + delta.y };
      return isWalkable(next) ? next : current;
    });
  }

  function changeMode(nextMode: DuMode) {
    setMode(nextMode);
    setTarget(null);
    setLine(
      nextMode === "follow"
        ? "渡点点头，走到你身边。"
        : nextMode === "wander"
          ? "渡开始自己在小家里慢慢逛。"
          : nextMode === "sit"
            ? "渡往能坐下的地方走。"
            : "渡看向小花园，像是想出去透口气。",
    );
  }

  function decideForDu() {
    const next: DuMode = player.y >= 10 ? "garden" : decor.length >= 2 ? "wander" : distance(player, du) > 4 ? "follow" : "sit";
    changeMode(next);
  }

  function interact() {
    const place = describePlace(player);
    if (distance(player, du) <= 1) {
      setLine(`${place}，渡离你很近。他说：先在这里待一会儿，我跟着你。`);
      return;
    }
    setLine(`${place}。渡抬头看你的位置，正慢慢走过来。`);
    changeMode("follow");
  }

  function handleStageClick(e: React.MouseEvent<HTMLDivElement>) {
    if (!decorateMode || !stageRef.current) return;
    const rect = stageRef.current.getBoundingClientRect();
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * COLS);
    const y = Math.floor(((e.clientY - rect.top) / rect.height) * ROWS);
    const pos = { x, y };
    if (!isWalkable(pos) || occupied.has(keyOf(pos))) {
      setLine("这里放不下，换一格。");
      return;
    }
    setDecor((current) => [...current, makeDecor(selectedDecor, pos)].slice(-18));
    setLine(`你把${DECOR_META[selectedDecor].label}放好了，渡会过去看的。`);
  }

  function clearDecor() {
    setDecor([]);
    setLine("屋子清出来了，可以重新布置。");
  }

  const tiles = [];
  for (let y = 0; y < ROWS; y += 1) {
    for (let x = 0; x < COLS; x += 1) tiles.push({ x, y });
  }

  return (
    <div className="min-h-full bg-[#F7F1E6] px-2 pb-8 pt-4 text-[#3C352B]" style={{ fontFamily: "'Microsoft YaHei', sans-serif" }}>
      <div className="mx-auto flex w-full max-w-[430px] flex-col gap-3">
        <div className="flex items-end justify-between px-1">
          <div>
            <div className="text-[20px] font-semibold tracking-tight">像素小家</div>
            <div className="mt-1 text-[12px] text-[#7B6D5A]">双层小洋楼 · 小花园</div>
          </div>
          <div className="rounded-full border border-[#E0D2BD] bg-[#FFF8EC] px-3 py-1 text-[11px] text-[#7B6D5A]">
            {describePlace(player)}
          </div>
        </div>

        <div
          ref={stageRef}
          className="relative mx-auto w-full overflow-hidden rounded-[18px] border-[3px] border-[#6C5942] bg-[#B9DDF0] shadow-[0_12px_30px_rgba(95,73,48,0.18)]"
          style={{ aspectRatio: `${COLS} / ${ROWS}`, imageRendering: "pixelated" }}
          onClick={handleStageClick}
        >
          <div className="absolute inset-x-[7.7%] top-0 h-[66.7%] bg-[#EAD2B5]" />
          <div className="absolute left-[7.7%] right-[7.7%] top-0 h-[9%] bg-[#9E6A4A]" style={{ clipPath: "polygon(8% 100%, 22% 12%, 50% 100%, 78% 12%, 92% 100%)" }} />
          <div className="absolute left-[7.7%] top-[32.7%] h-[2.4%] w-[84.6%] bg-[#8E785E]" />
          <div className="absolute left-[46.2%] top-[60%] h-[6.7%] w-[7.7%] bg-[#7C5B45]" />

          <div className="grid h-full w-full" style={{ gridTemplateColumns: `repeat(${COLS}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${ROWS}, minmax(0, 1fr))` }}>
            {tiles.map((pos) => {
              const tile = tileFor(pos);
              const outside = !isInsideHouse(pos) && !isGarden(pos);
              return (
                <div
                  key={keyOf(pos)}
                  style={{
                    background: outside ? "transparent" : tile.bg,
                    borderRight: `1px solid ${outside ? "transparent" : tile.border}`,
                    borderBottom: `1px solid ${outside ? "transparent" : tile.border}`,
                    opacity: outside ? 0.1 : 1,
                  }}
                />
              );
            })}
          </div>

          <div className="absolute left-[7.7%] top-[66.6%] h-[1.6%] w-[84.6%] bg-[#7B694D]" />

          {FURNITURE.map((item) => (
            <div
              key={item.id}
              className="absolute flex items-center justify-center border-2 border-[#6B563D] text-[7px] font-bold uppercase leading-none text-[#59452F]"
              style={{
                left: `${(item.x / COLS) * 100}%`,
                top: `${(item.y / ROWS) * 100}%`,
                width: `${(item.w / COLS) * 100}%`,
                height: `${(item.h / ROWS) * 100}%`,
                background: item.color,
                boxShadow: "inset -2px -2px 0 rgba(0,0,0,0.08)",
              }}
            >
              {item.text}
            </div>
          ))}

          <div className="absolute left-[15.4%] top-[78%] h-[8%] w-[23%] border-2 border-[#6B563D] bg-[#EFA6B8]" />
          <div className="absolute left-[69%] top-[78%] h-[7%] w-[15%] border-2 border-[#6B563D] bg-[#F5D87A]" />
          <div className="absolute left-[42%] top-[86%] h-[8%] w-[18%] rounded-full border-2 border-[#6B563D] bg-[#B8D8EC]" />

          {decor.map((item) => {
            const meta = DECOR_META[item.kind];
            return (
              <div
                key={item.id}
                className="absolute flex items-center justify-center border-2 border-[#6B563D] text-[13px] font-black leading-none"
                style={{
                  left: `${(item.x / COLS) * 100}%`,
                  top: `${(item.y / ROWS) * 100}%`,
                  width: `${(1 / COLS) * 100}%`,
                  height: `${(1 / ROWS) * 100}%`,
                  color: "#59452F",
                  background: meta.color,
                }}
                title={meta.label}
              >
                {meta.mark}
              </div>
            );
          })}

          <PixelPerson pos={du} tone="du" label="渡" />
          <PixelPerson pos={player} tone="me" label="我" />
        </div>

        <div className="rounded-[16px] border border-[#E4D2BA] bg-[#FFF9EE] p-3 shadow-[0_6px_18px_rgba(96,72,43,0.08)]">
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
          <button className="rounded-[14px] border border-[#D8C4AA] bg-[#FFF9EE] px-3 py-3 text-[12px] font-semibold text-[#5F4C36] active:translate-y-px" onClick={decideForDu}>
            渡决定
          </button>
          <DPad onMove={movePlayer} />
          <button className="rounded-[14px] border border-[#D8C4AA] bg-[#FFF9EE] px-3 py-3 text-[12px] font-semibold text-[#5F4C36] active:translate-y-px" onClick={interact}>
            互动
          </button>
        </div>

        <div className="rounded-[16px] border border-[#E4D2BA] bg-[#FFF9EE] p-3">
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
            打开布置后，点地图上的空地放摆件。现在先做小家本体，商店和打工后面再接。
          </div>
        </div>
      </div>
    </div>
  );
}

function PixelPerson({ pos, tone, label }: { pos: Pos; tone: "me" | "du"; label: string }) {
  const colors = tone === "du"
    ? { body: "#F3CF94", hair: "#5A4637", shirt: "#F8E2B8", outline: "#6B563D" }
    : { body: "#F6CFC8", hair: "#2F2830", shirt: "#F1B8C8", outline: "#6B563D" };
  return (
    <div
      className="absolute z-20"
      style={{
        left: `${(pos.x / COLS) * 100}%`,
        top: `${(pos.y / ROWS) * 100}%`,
        width: `${(1 / COLS) * 100}%`,
        height: `${(1 / ROWS) * 100}%`,
        transition: "left 180ms linear, top 180ms linear",
      }}
      aria-label={label}
    >
      <div className="relative h-full w-full">
        <div className="absolute left-[18%] top-[8%] h-[78%] w-[64%] border-2" style={{ background: colors.body, borderColor: colors.outline }} />
        <div className="absolute left-[18%] top-[8%] h-[22%] w-[64%] border-x-2 border-t-2" style={{ background: colors.hair, borderColor: colors.outline }} />
        <div className="absolute left-[30%] top-[38%] h-[9%] w-[9%] bg-[#2F2A26]" />
        <div className="absolute right-[30%] top-[38%] h-[9%] w-[9%] bg-[#2F2A26]" />
        <div className="absolute left-[26%] bottom-[8%] h-[26%] w-[48%] border-x-2 border-b-2" style={{ background: colors.shirt, borderColor: colors.outline }} />
      </div>
    </div>
  );
}

function DPad({ onMove }: { onMove: (delta: Pos) => void }) {
  const btn = "flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#D8C4AA] bg-[#FFF9EE] text-[16px] font-black text-[#5F4C36] active:translate-y-px";
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
        active ? "border-[#6C5942] bg-[#6C5942] text-white" : "border-[#D8C4AA] bg-[#FFF9EE] text-[#5F4C36]"
      }`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
