import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type CoreMemory = {
  id?: string;
  memory_id?: string;
  content?: string;
  tag?: string;
  importance?: number;
  mention_count?: number;
  emotion_label?: string;
};

type RecalledLine =
  | string
  | {
      id?: string;
      memory_id?: string;
      content?: string;
      emotion_label?: string;
      scene_type?: string;
      target_type?: string;
      final_score?: number;
    };

type RecallEvent = {
  recalled_lines?: RecalledLine[];
  recalled_items?: Array<{
    id?: string;
    memory_id?: string;
    content?: string;
    tag?: string;
    importance?: number;
    mention_count?: number;
  }>;
  referenced_memories?: Array<{
    id?: string;
    memory_id?: string;
    content?: string;
    tag?: string;
    importance?: number;
    mention_count?: number;
  }>;
};

type MemoryDebugResp = {
  ok?: boolean;
  error?: string;
  recalls?: RecallEvent[];
  search_memory_events?: RecallEvent[];
  citation_events?: RecallEvent[];
  core_cache?: {
    items?: CoreMemory[];
  };
};

type MemoryNode = {
  id: string;
  x: number;
  y: number;
  z: number;
  title: string;
  type: "core" | "dynamic";
  emotion: "positive" | "negative" | "neutral";
  anchor?: string;
  asterism?: string;
  date: string;
  desc: string;
  coord: string;
  connections: string[];
  importance?: number;
};

type ProjectedPoint = {
  x: number;
  y: number;
  z: number;
  depth: number;
};

type AtlasGroup = {
  name: string;
  label: { x: number; y: number };
  stars: Array<{ x: number; y: number; major?: boolean; name?: string }>;
  lines: Array<[number, number]>;
};

const constellationAtlas: AtlasGroup[] = [
  {
    name: "URSA MAJOR",
    label: { x: 118, y: 136 },
    stars: [
      { x: 74, y: 174, major: true },
      { x: 130, y: 204 },
      { x: 195, y: 216 },
      { x: 244, y: 184 },
      { x: 304, y: 174 },
      { x: 356, y: 144, major: true },
      { x: 414, y: 120 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 0], [3, 4], [4, 5], [5, 6]],
  },
  {
    name: "LYRA",
    label: { x: 792, y: 142 },
    stars: [
      { x: 824, y: 108, major: true, name: "Vega" },
      { x: 780, y: 166 },
      { x: 846, y: 178 },
      { x: 803, y: 230 },
    ],
    lines: [[0, 1], [0, 2], [1, 2], [1, 3], [2, 3]],
  },
  {
    name: "ORION",
    label: { x: 662, y: 654 },
    stars: [
      { x: 624, y: 562, major: true, name: "Betelgeuse" },
      { x: 746, y: 552 },
      { x: 660, y: 654 },
      { x: 704, y: 664 },
      { x: 748, y: 676 },
      { x: 602, y: 778 },
      { x: 804, y: 776, major: true, name: "Rigel" },
    ],
    lines: [[0, 2], [1, 4], [2, 3], [3, 4], [2, 5], [4, 6], [5, 6]],
  },
  {
    name: "CASSIOPEIA",
    label: { x: 168, y: 720 },
    stars: [
      { x: 96, y: 682 },
      { x: 160, y: 632, major: true },
      { x: 230, y: 686 },
      { x: 300, y: 640 },
      { x: 364, y: 704 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 4]],
  },
];

function hashText(text: string) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function pickTitle(content: string, tag?: string) {
  const clean = String(content || "").replace(/\s+/g, " ").trim();
  const label = String(tag || "").trim();
  if (label && label !== "default") return label;
  if (!clean) return "Memory";
  return clean.length > 18 ? `${clean.slice(0, 18)}...` : clean;
}

function normalizeEmotion(raw?: string): MemoryNode["emotion"] {
  if (raw === "positive" || raw === "negative") return raw;
  return "neutral";
}

function nodePosition(seed: string, index: number, type: MemoryNode["type"]) {
  if (type === "core") {
    const corePositions = [
      { x: -72, y: -32, z: 138 },
      { x: 74, y: 42, z: 124 },
      { x: -18, y: 8, z: 190 },
      { x: 46, y: -76, z: 96 },
    ];
    return corePositions[index % corePositions.length];
  }
  const h = hashText(seed);
  const angle = ((h % 6283) / 1000) + index * 0.55;
  const radius = 170 + ((h >>> 7) % 260);
  const vertical = -230 + ((h >>> 14) % 470);
  const depth = -220 + ((h >>> 22) % 450);
  return {
    x: Math.cos(angle) * radius + (((h >>> 5) % 88) - 44),
    y: vertical * 0.72 + Math.sin(angle * 1.7) * 72,
    z: depth,
  };
}

function collectNodes(data: MemoryDebugResp | null): MemoryNode[] {
  const nodes: MemoryNode[] = [];
  const seen = new Set<string>();

  const coreItems = data?.core_cache?.items || [];
  coreItems.slice(0, 12).forEach((item, index) => {
    const id = String(item.memory_id || item.id || `core-${index}`).trim();
    const content = String(item.content || "").trim();
    if (!id || !content || seen.has(id)) return;
    seen.add(id);
    const pos = nodePosition(id, index, "core");
    nodes.push({
      id,
      ...pos,
      title: pickTitle(content, item.tag),
      type: "core",
      emotion: normalizeEmotion(item.emotion_label),
      anchor: index === 0 ? "Polaris" : index === 1 ? "Vega" : "Anchor",
      asterism: `${pickTitle(content, item.tag)} Asterism`,
      date: "CORE MEMORY",
      desc: content,
      coord: `imp ${item.importance ?? "-"} | mention ${item.mention_count ?? 0}`,
      connections: [],
      importance: item.importance,
    });
  });

  const events = [
    ...(data?.recalls || []),
    ...(data?.search_memory_events || []),
    ...(data?.citation_events || []),
  ];
  const candidates: Array<{ id: string; content: string; tag?: string; emotion?: string; importance?: number; mention?: number }> = [];
  events.forEach((event, eventIndex) => {
    (event.recalled_items || []).forEach((item, itemIndex) => {
      const content = String(item.content || "").trim();
      const id = String(item.memory_id || item.id || `item-${eventIndex}-${itemIndex}`).trim();
      if (content) candidates.push({ id, content, tag: item.tag, importance: item.importance, mention: item.mention_count });
    });
    (event.referenced_memories || []).forEach((item, itemIndex) => {
      const content = String(item.content || "").trim();
      const id = String(item.memory_id || item.id || `ref-${eventIndex}-${itemIndex}`).trim();
      if (content) candidates.push({ id, content, tag: item.tag, importance: item.importance, mention: item.mention_count });
    });
    (event.recalled_lines || []).forEach((line, lineIndex) => {
      if (typeof line === "string") {
        const content = line.trim();
        if (content) candidates.push({ id: `line-${hashText(content)}`, content });
      } else {
        const content = String(line.content || "").trim();
        const id = String(line.memory_id || line.id || `line-${eventIndex}-${lineIndex}`).trim();
        if (content) candidates.push({ id, content, emotion: line.emotion_label });
      }
    });
  });

  candidates.slice(0, 28).forEach((item, index) => {
    if (!item.id || seen.has(item.id)) return;
    seen.add(item.id);
    const pos = nodePosition(item.id || item.content, index, "dynamic");
    const firstCore = nodes.find((node) => node.type === "core");
    const nearestCore = nodes.filter((node) => node.type === "core")[index % Math.max(1, nodes.filter((node) => node.type === "core").length)];
    const connections = nearestCore ? [nearestCore.id] : firstCore ? [firstCore.id] : [];
    nodes.push({
      id: item.id,
      ...pos,
      title: pickTitle(item.content, item.tag),
      type: "dynamic",
      emotion: normalizeEmotion(item.emotion),
      date: "DYNAMIC MEMORY",
      desc: item.content,
      coord: `imp ${item.importance ?? "-"} | mention ${item.mention ?? 0}`,
      connections,
      importance: item.importance,
    });
  });

  return nodes;
}

function useMeasuredSize(ref: React.RefObject<HTMLDivElement | null>) {
  const [size, setSize] = useState({ width: 390, height: 720 });
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const update = () => {
      const rect = node.getBoundingClientRect();
      setSize({ width: Math.max(320, rect.width), height: Math.max(520, rect.height) });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}

export function MemoryNebulaTab() {
  const toast = useToast();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const size = useMeasuredSize(rootRef);
  const [data, setData] = useState<MemoryDebugResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [activeId, setActiveId] = useState("");
  const [viewMode, setViewMode] = useState<"" | "anchor" | "mood">("");
  const [atlasVisible, setAtlasVisible] = useState(true);
  const [rotation, setRotation] = useState({ x: 0.18, y: -0.16 });
  const dragRef = useRef({ active: false, moved: false, sx: 0, sy: 0, lx: 0, ly: 0 });

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiJson<MemoryDebugResp>("/miniapp-api/memory-debug?limit=16&core_limit=48&scope=all");
      if (!resp?.ok) throw new Error(resp?.error || "加载失败");
      setLoadError("");
      setData(resp);
    } catch (e: any) {
      const message = e?.message || String(e);
      setLoadError(message);
      toast(`记忆星云加载失败：${message}`);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const nodes = useMemo(() => collectNodes(data), [data]);
  const coreNodes = useMemo(() => nodes.filter((node) => node.type === "core"), [nodes]);
  const activeNode = nodes.find((node) => node.id === activeId) || null;

  const projected = useMemo(() => {
    const points = new Map<string, ProjectedPoint>();
    const cosY = Math.cos(rotation.y);
    const sinY = Math.sin(rotation.y);
    const cosX = Math.cos(rotation.x);
    const sinX = Math.sin(rotation.x);
    nodes.forEach((node) => {
      const x1 = node.x * cosY + node.z * sinY;
      const z1 = -node.x * sinY + node.z * cosY;
      const y1 = node.y * cosX - z1 * sinX;
      const z2 = node.y * sinX + z1 * cosX;
      const perspective = 760;
      const depth = Math.max(0.48, Math.min(1.7, perspective / (perspective - z2)));
      points.set(node.id, {
        x: size.width / 2 + x1 * depth,
        y: size.height / 2 + y1 * depth,
        z: z2,
        depth,
      });
    });
    return points;
  }, [nodes, rotation.x, rotation.y, size.height, size.width]);

  const relatedIds = useMemo(() => {
    const related = new Set<string>();
    if (!activeNode) return related;
    activeNode.connections.forEach((id) => related.add(id));
    nodes.forEach((node) => {
      if (node.connections.includes(activeNode.id)) related.add(node.id);
    });
    return related;
  }, [activeNode, nodes]);

  function pointerStart(clientX: number, clientY: number) {
    dragRef.current = { active: true, moved: false, sx: clientX, sy: clientY, lx: clientX, ly: clientY };
  }

  function pointerMove(clientX: number, clientY: number) {
    const drag = dragRef.current;
    if (!drag.active) return;
    const dx = clientX - drag.lx;
    const dy = clientY - drag.ly;
    if (Math.abs(clientX - drag.sx) + Math.abs(clientY - drag.sy) > 4) drag.moved = true;
    drag.lx = clientX;
    drag.ly = clientY;
    setRotation((prev) => ({
      x: Math.max(-1.15, Math.min(1.15, prev.x - dy * 0.004)),
      y: prev.y + dx * 0.006,
    }));
  }

  function pointerEnd() {
    window.setTimeout(() => {
      dragRef.current.active = false;
      dragRef.current.moved = false;
    }, 0);
  }

  function selectNode(node: MemoryNode) {
    if (dragRef.current.moved) return;
    setActiveId(node.id);
  }

  function toggleMode(mode: "anchor" | "atlas" | "mood") {
    if (mode === "atlas") {
      setAtlasVisible((prev) => !prev);
      return;
    }
    setViewMode((prev) => (prev === mode ? "" : mode));
  }

  return (
    <div
      ref={rootRef}
      className={`memory-nebula-root -mx-3.5 min-h-[calc(100dvh-74px)] overflow-hidden ${activeNode ? "is-focused" : ""} ${viewMode === "anchor" ? "mode-anchor" : ""} ${viewMode === "mood" ? "mode-mood" : ""} ${atlasVisible ? "" : "atlas-off"}`}
      onMouseDown={(e) => pointerStart(e.clientX, e.clientY)}
      onMouseMove={(e) => pointerMove(e.clientX, e.clientY)}
      onMouseUp={pointerEnd}
      onMouseLeave={pointerEnd}
      onTouchStart={(e) => {
        const touch = e.touches[0];
        if (touch) pointerStart(touch.clientX, touch.clientY);
      }}
      onTouchMove={(e) => {
        const touch = e.touches[0];
        if (touch) pointerMove(touch.clientX, touch.clientY);
      }}
      onTouchEnd={pointerEnd}
      onClick={() => {
        if (!dragRef.current.moved) setActiveId("");
      }}
    >
      <style>{memoryNebulaCss}</style>
      <div className="nebula" />
      <div className="sky-atlas" aria-hidden>
        <svg viewBox="0 0 1000 1000" preserveAspectRatio="none">
          {constellationAtlas.map((group) => (
            <g key={group.name}>
              {group.lines.map(([a, b]) => {
                const from = group.stars[a];
                const to = group.stars[b];
                return <line key={`${a}-${b}`} className="sky-atlas-line" x1={from.x} y1={from.y} x2={to.x} y2={to.y} />;
              })}
              {group.stars.map((star, index) => (
                <React.Fragment key={`${group.name}-${index}`}>
                  <circle className={`sky-atlas-star ${star.major ? "major" : ""}`} cx={star.x} cy={star.y} r={star.major ? 2.4 : 1.25} />
                  {star.name ? <text className="sky-atlas-star-label" x={star.x + 9} y={star.y - 7}>{star.name}</text> : null}
                </React.Fragment>
              ))}
              <text className="sky-atlas-label" x={group.label.x} y={group.label.y}>{group.name}</text>
            </g>
          ))}
        </svg>
      </div>

      <div className="hud">
        <div className="hud-top">
          <button type="button" className="crescent-btn" onClick={(e) => { e.stopPropagation(); void reload(); }} aria-label="刷新记忆星云">
            <svg className="crescent-svg" width="24" height="24" viewBox="0 0 24 24">
              <path d="M12 3a9 9 0 1 0 9 9 9.011 9.011 0 0 1-9-9Z" />
            </svg>
          </button>
          <h1 className="app-title">MNEMOSYNE</h1>
          <div className="memory-count">{loading ? "..." : nodes.length ? `${nodes.length} stars` : "NO DATA"}</div>
        </div>
        <div className="hud-side">
          <button type="button" className={`filter-btn ${viewMode === "anchor" ? "active" : ""}`} onClick={(e) => { e.stopPropagation(); toggleMode("anchor"); }}>ANCHOR</button>
          <button type="button" className={`filter-btn ${atlasVisible ? "active" : ""}`} onClick={(e) => { e.stopPropagation(); toggleMode("atlas"); }}>ATLAS</button>
          <button type="button" className={`filter-btn ${viewMode === "mood" ? "active" : ""}`} onClick={(e) => { e.stopPropagation(); toggleMode("mood"); }}>MOOD</button>
        </div>
      </div>

      <div className="constellation-canvas">
        {nodes.map((node) => {
          const p = projected.get(node.id);
          if (!p) return null;
          const active = activeNode?.id === node.id;
          const related = relatedIds.has(node.id);
          const base = node.type === "core" ? 1.08 : 0.92;
          const focus = active ? 1.72 : related ? 1.18 : 1;
          return (
            <button
              key={node.id}
              type="button"
              className={`star star-${node.type} ${active ? "active" : ""} ${related ? "related" : ""}`}
              data-emotion={node.emotion}
              style={{
                left: p.x,
                top: p.y,
                opacity: Math.max(0.22, Math.min(1, 0.42 + p.depth * 0.42)),
                transform: `translate(-50%, -50%) scale(${base * focus * p.depth})`,
                zIndex: Math.round(50 + p.z),
              }}
              onClick={(e) => {
                e.stopPropagation();
                selectNode(node);
              }}
              aria-label={node.title}
            >
              <span className="star-label">{node.title}</span>
              {node.anchor ? <span className="anchor-name">{node.anchor}</span> : null}
            </button>
          );
        })}
        {activeNode
          ? activeNode.connections.map((toId) => {
              const from = projected.get(activeNode.id);
              const to = projected.get(toId);
              if (!from || !to) return null;
              const dx = to.x - from.x;
              const dy = to.y - from.y;
              const dist = Math.sqrt(dx * dx + dy * dy);
              const angle = Math.atan2(dy, dx) * 180 / Math.PI;
              return (
                <div
                  key={`${activeNode.id}-${toId}`}
                  className="constellation-line active"
                  style={{ left: from.x, top: from.y, width: dist, transform: `rotate(${angle}deg)` }}
                />
              );
            })
          : null}
      </div>

      {!nodes.length ? (
        <div className="memory-empty-state" onClick={(e) => e.stopPropagation()}>
          <p className="memory-empty-kicker">NO SAMPLE MEMORY</p>
          <h2>{loading ? "正在读取真实记忆" : loadError ? "没有拿到真实记忆" : "还没有可显示的记忆"}</h2>
          <p>
            {loading
              ? "星云只会从网关返回的记忆内容生成。"
              : loadError
                ? "接口没有返回可用数据，所以这里不再展示样例卡片。"
                : "等核心记忆或动态召回出现后，这里会生成真实星点。"}
          </p>
          <button type="button" onClick={(e) => { e.stopPropagation(); void reload(); }}>重新读取</button>
        </div>
      ) : null}

      {activeNode ? (
        <div
          className="private-asterism active"
          style={{
            left: projected.get(activeNode.id)?.x || size.width / 2,
            top: Math.max(64, (projected.get(activeNode.id)?.y || size.height / 2) - 54),
          }}
        >
          {activeNode.asterism || `${activeNode.title} Asterism`}
        </div>
      ) : null}

      {activeNode ? (
        <div className="logbook active" onClick={(e) => e.stopPropagation()}>
          <div className="logbook-header">
            <div>
              <p className="memory-date">{activeNode.date}</p>
              <h2 className="memory-title">{activeNode.title}</h2>
            </div>
            <button type="button" className="close-btn" onClick={() => setActiveId("")} aria-label="关闭记忆卡片">×</button>
          </div>
          <div className="memory-body">{activeNode.desc}</div>
          <div className="metadata-grid">
            <div className="meta-item">
              <label>Coordinates</label>
              <span>{activeNode.coord}</span>
            </div>
            <div className="meta-item">
              <label>Intensity</label>
              <span>{activeNode.anchor ? `${activeNode.anchor} Anchor` : "Temporal Flicker"}</span>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const memoryNebulaCss = `
.memory-nebula-root {
  position: relative;
  width: 100%;
  background: radial-gradient(circle at 50% 50%, #101435 0%, #04051a 100%);
  color: #f0f0d0;
  cursor: grab;
  touch-action: none;
  user-select: none;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.memory-nebula-root:active { cursor: grabbing; }
.nebula {
  position: absolute;
  width: 150%;
  height: 150%;
  top: -25%;
  left: -25%;
  background: radial-gradient(circle at 20% 30%, rgba(65, 48, 122, 0.15) 0%, transparent 40%),
    radial-gradient(circle at 80% 70%, rgba(30, 58, 138, 0.1) 0%, transparent 50%);
  filter: blur(60px);
  pointer-events: none;
}
.sky-atlas {
  position: absolute;
  inset: 0;
  opacity: 0.32;
  mix-blend-mode: screen;
  pointer-events: none;
  transition: opacity 0.4s ease;
}
.atlas-off .sky-atlas { opacity: 0; }
.sky-atlas svg { width: 100%; height: 100%; display: block; }
.sky-atlas-line { stroke: rgba(178, 184, 216, 0.16); stroke-width: 0.72; vector-effect: non-scaling-stroke; }
.sky-atlas-star { fill: rgba(223, 229, 255, 0.42); }
.sky-atlas-star.major { fill: rgba(242, 227, 182, 0.66); filter: drop-shadow(0 0 4px rgba(242, 227, 182, 0.38)); }
.sky-atlas-label,
.sky-atlas-star-label {
  fill: rgba(189, 195, 224, 0.28);
  font-size: 8px;
  letter-spacing: 0.26em;
  text-transform: uppercase;
}
.sky-atlas-star-label { fill: rgba(242, 227, 182, 0.4); font-size: 7px; letter-spacing: 0.22em; }
.hud { position: absolute; inset: 0; z-index: 20; pointer-events: none; }
.hud-top {
  position: absolute;
  top: 18px;
  left: 18px;
  right: 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  pointer-events: auto;
}
.app-title {
  font-family: "Times New Roman", Georgia, serif;
  font-size: 18px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-style: italic;
}
.memory-count {
  min-width: 42px;
  text-align: right;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(142, 148, 175, 0.76);
}
.crescent-btn {
  display: flex;
  width: 40px;
  height: 40px;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  color: #f2e3b6;
}
.crescent-svg { fill: none; stroke: #f2e3b6; stroke-width: 1.5; filter: drop-shadow(0 0 5px rgba(242, 227, 182, 0.8)); }
.hud-side {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 20px;
  pointer-events: auto;
}
.filter-btn {
  appearance: none;
  border: 0;
  border-right: 1px solid rgba(142, 148, 175, 0.2);
  border-radius: 999px;
  background: transparent;
  writing-mode: vertical-rl;
  padding: 11px 7px;
  color: #8e94af;
  font: inherit;
  font-size: 9px;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  opacity: 0.62;
  transition: color 0.24s ease, opacity 0.24s ease, border-color 0.24s ease, text-shadow 0.24s ease, background 0.24s ease, box-shadow 0.24s ease, transform 0.24s ease;
}
.filter-btn.active {
  color: #f2e3b6;
  opacity: 1;
  border-right-color: rgba(242, 227, 182, 0.48);
  background: rgba(242, 227, 182, 0.06);
  box-shadow: inset -2px 0 0 rgba(242, 227, 182, 0.48), 0 0 22px rgba(242, 227, 182, 0.12);
  text-shadow: 0 0 12px rgba(242, 227, 182, 0.32);
  transform: translateX(-4px);
}
.constellation-canvas { position: absolute; inset: 0; z-index: 5; }
.star {
  position: absolute;
  border: 0;
  border-radius: 50%;
  padding: 0;
  cursor: pointer;
  transition: opacity 0.26s ease, filter 0.26s ease, box-shadow 0.3s ease;
}
.star::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: 300%;
  height: 300%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  filter: blur(4px);
  opacity: 0.6;
  animation: nebulaPulse 4s infinite ease-in-out;
}
.star-core {
  width: 8px;
  height: 8px;
  background: #f2e3b6;
  box-shadow: 0 0 15px rgba(242, 227, 182, 0.8), 0 0 30px rgba(242, 227, 182, 0.8);
}
.star-dynamic {
  width: 4px;
  height: 4px;
  background: #fff;
  box-shadow: 0 0 10px rgba(255, 255, 255, 0.6);
}
.star-label {
  position: absolute;
  top: 15px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  font-family: Georgia, "Songti SC", serif;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  text-shadow: 0 0 14px rgba(4, 5, 26, 0.9);
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.anchor-name {
  position: absolute;
  bottom: 15px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  color: rgba(242, 227, 182, 0.46);
  opacity: 0.52;
  pointer-events: none;
  font-size: 7px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  text-shadow: 0 0 12px rgba(4, 5, 26, 0.95);
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.constellation-line {
  position: absolute;
  height: 0.5px;
  transform-origin: 0 50%;
  pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(242, 227, 182, 0.8), transparent);
  opacity: 0.78;
  filter: drop-shadow(0 0 10px rgba(242, 227, 182, 0.35));
}
.is-focused .star:not(.active):not(.related) { opacity: 0.15 !important; filter: grayscale(1); }
.mode-anchor .sky-atlas { opacity: 0.18; }
.mode-anchor .star-dynamic { opacity: 0.12 !important; filter: grayscale(1); }
.mode-anchor .star-core { filter: brightness(1.18) drop-shadow(0 0 16px rgba(242, 227, 182, 0.55)); }
.mode-anchor .star-core .star-label,
.mode-anchor .star-core .anchor-name { opacity: 0.92; transform: translateX(-50%) translateY(2px); }
.mode-mood .star-core { opacity: 0.38 !important; filter: grayscale(0.7); }
.mode-mood .star-dynamic { width: 6px; height: 6px; }
.mode-mood .star-dynamic[data-emotion="positive"] { background: #f2e3b6; box-shadow: 0 0 14px rgba(242, 227, 182, 0.72), 0 0 28px rgba(242, 227, 182, 0.28); }
.mode-mood .star-dynamic[data-emotion="negative"] { background: #c5a3ff; box-shadow: 0 0 14px rgba(197, 163, 255, 0.72), 0 0 28px rgba(98, 76, 170, 0.34); }
.mode-mood .star-dynamic[data-emotion="neutral"] { background: #dfe7ff; box-shadow: 0 0 12px rgba(223, 231, 255, 0.56); }
.star.active { filter: none; }
.star.active .star-label,
.star.related .star-label { opacity: 0.82; transform: translateX(-50%) translateY(2px); }
.star.active .anchor-name,
.star.related .anchor-name { opacity: 0.86; transform: translateX(-50%) translateY(-2px); }
.private-asterism {
  position: absolute;
  z-index: 16;
  transform: translate(-50%, -50%);
  color: rgba(242, 227, 182, 0.42);
  font-size: 8px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  pointer-events: none;
  opacity: 0;
  text-shadow: 0 0 18px rgba(4, 5, 26, 0.96);
}
.private-asterism.active { opacity: 0.72; }
.logbook {
  position: absolute;
  left: 50%;
  bottom: calc(env(safe-area-inset-bottom, 0px) + 22px);
  z-index: 30;
  width: min(292px, calc(100% - 44px));
  transform: translateX(-50%);
  border: 1px solid rgba(242, 227, 182, 0.045);
  border-radius: 18px;
  background: rgba(6, 8, 30, 0.34);
  padding: 14px 15px 13px;
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.035);
  backdrop-filter: blur(18px) saturate(1.18);
}
.logbook-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
.memory-date { margin-bottom: 4px; color: #8e94af; opacity: 0.76; font-size: 8px; letter-spacing: 0.16em; text-transform: uppercase; }
.memory-title { color: #f0f0d0; font-family: Georgia, "Songti SC", serif; font-size: 18px; font-style: italic; line-height: 1.04; }
.close-btn { border: 0; background: transparent; color: rgba(142, 148, 175, 0.9); font-size: 22px; line-height: 1; }
.memory-body {
  max-height: 78px;
  overflow-y: auto;
  color: #8e94af;
  font-size: 12px;
  line-height: 1.45;
  -webkit-mask-image: linear-gradient(to bottom, black 86%, transparent 100%);
  mask-image: linear-gradient(to bottom, black 86%, transparent 100%);
}
.metadata-grid {
  margin-top: 13px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  border-top: 0.5px solid rgba(142, 148, 175, 0.14);
  padding-top: 10px;
}
.meta-item label { display: block; margin-bottom: 3px; color: #f2e3b6; opacity: 0.72; font-size: 7px; letter-spacing: 0.18em; text-transform: uppercase; }
.meta-item span { color: rgba(240, 240, 208, 0.68); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; }
.memory-empty-state {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 18;
  width: min(286px, calc(100% - 68px));
  transform: translate(-50%, -50%);
  color: rgba(240, 240, 208, 0.72);
  text-align: center;
  pointer-events: auto;
}
.memory-empty-kicker {
  margin-bottom: 9px;
  color: rgba(242, 227, 182, 0.58);
  font-size: 8px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
}
.memory-empty-state h2 {
  margin-bottom: 9px;
  color: #f0f0d0;
  font-family: Georgia, "Songti SC", serif;
  font-size: 20px;
  font-style: italic;
  line-height: 1.15;
}
.memory-empty-state p {
  color: rgba(142, 148, 175, 0.86);
  font-size: 12px;
  line-height: 1.55;
}
.memory-empty-state button {
  margin-top: 18px;
  border: 1px solid rgba(242, 227, 182, 0.16);
  border-radius: 999px;
  background: rgba(242, 227, 182, 0.06);
  padding: 9px 18px;
  color: rgba(240, 240, 208, 0.82);
  font: inherit;
  font-size: 11px;
  letter-spacing: 0.08em;
}
@keyframes nebulaPulse {
  0%, 100% { opacity: 0.4; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.8; transform: translate(-50%, -50%) scale(1.3); }
}
`;
