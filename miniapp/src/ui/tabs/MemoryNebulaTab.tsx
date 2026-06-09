import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type CoreMemory = {
  id?: string;
  memory_id?: string;
  content?: string;
  tag?: string;
  promoted_at?: string;
  importance?: number;
  mention_count?: number;
  emotion_label?: string;
};

type DynamicMemory = {
  id?: string;
  memory_id?: string;
  content?: string;
  tag?: string;
  importance?: number;
  mention_count?: number;
  emotion_label?: string;
  scene_type?: string;
  target_type?: string;
  created_at?: string;
  last_mentioned?: string;
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
    final_score?: number;
  }>;
  referenced_memories?: Array<{
    id?: string;
    memory_id?: string;
    content?: string;
    tag?: string;
    importance?: number;
    mention_count?: number;
    final_score?: number;
  }>;
  timestamp?: string;
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

type DynamicMemoryResp = {
  ok?: boolean;
  error?: string;
  count?: number;
  memories?: DynamicMemory[];
};

type MemoryNode = {
  id: string;
  x: number;
  y: number;
  z: number;
  title: string;
  contentTitle: string;
  type: "core" | "dynamic";
  emotion: "positive" | "negative" | "neutral";
  desc: string;
  connections: string[];
};

type EventMemoryIndex = {
  connections: Map<string, Set<string>>;
  scores: Map<string, number>;
  timestamps: Map<string, string>;
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

function pickTitle(content: string) {
  const clean = String(content || "").replace(/\s+/g, " ").trim();
  if (!clean) return "Memory";
  return clean.length > 18 ? `${clean.slice(0, 18)}...` : clean;
}

function buildMemoryVerse(content: string) {
  const clean = String(content || "").replace(/\s+/g, " ").trim();
  if (!clean) return ["Memory"];

  const pieces: string[] = [];
  clean
    .split(/[，。！？；：、\n]+/)
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach((part) => {
      if (part.length <= 18) {
        pieces.push(part);
        return;
      }
      for (let index = 0; index < part.length; index += 18) {
        pieces.push(part.slice(index, index + 18));
      }
    });

  return (pieces.length ? pieces : [clean]).slice(0, 5);
}

function memoryVerseClass(line: string, index: number, total: number) {
  if (index === 0 && line.length <= 8) return "memory-phrase-title";
  if (line.length >= 12 || index === Math.floor(total / 2)) return "memory-phrase-loud";
  if (index === total - 1) return "memory-phrase-soft";
  return "memory-phrase-mid";
}

function asNumber(value: unknown): number | null {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function formatTimeCoord(raw?: string) {
  const text = String(raw || "").trim();
  if (!text) return "T--";
  const date = new Date(text);
  if (!Number.isFinite(date.getTime())) return "T--";
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `T${month}.${day}`;
}

function formatScoreCoord(score: number | null, mentionCount?: number) {
  if (score !== null) {
    return score <= 1 ? `S${score.toFixed(2)}` : `S${Math.round(score)}`;
  }
  const mentions = Math.max(0, Math.min(99, Math.round(Number(mentionCount) || 0)));
  return `S${String(mentions).padStart(2, "0")}`;
}

function formatMemoryCoord({
  time,
  importance,
  score,
  mentionCount,
}: {
  time?: string;
  importance?: number;
  score?: number | null;
  mentionCount?: number;
}) {
  const weight = Math.max(0, Math.min(9, Math.round(Number(importance) || 0)));
  return `${formatTimeCoord(time)} / W${weight} / ${formatScoreCoord(score ?? null, mentionCount)}`;
}

function contentKey(content: string) {
  return String(content || "").replace(/\s+/g, "").trim();
}

function normalizeEmotion(raw?: string): MemoryNode["emotion"] {
  if (raw === "positive" || raw === "negative") return raw;
  return "neutral";
}

function memoryId(item: { id?: string; memory_id?: string } | null | undefined, fallback: string) {
  return String(item?.memory_id || item?.id || fallback).trim();
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

function eventMemoryIds(event: RecallEvent, eventIndex: number) {
  const ids: string[] = [];
  (event.recalled_items || []).forEach((item, itemIndex) => {
    const id = memoryId(item, `item-${eventIndex}-${itemIndex}`);
    if (id) ids.push(id);
  });
  (event.referenced_memories || []).forEach((item, itemIndex) => {
    const id = memoryId(item, `ref-${eventIndex}-${itemIndex}`);
    if (id) ids.push(id);
  });
  (event.recalled_lines || []).forEach((line, lineIndex) => {
    if (typeof line === "string") return;
    const id = memoryId(line, `line-${eventIndex}-${lineIndex}`);
    if (id) ids.push(id);
  });
  return Array.from(new Set(ids));
}

function buildEventIndex(data: MemoryDebugResp | null): EventMemoryIndex {
  const connections = new Map<string, Set<string>>();
  const scores = new Map<string, number>();
  const timestamps = new Map<string, string>();
  const events = [
    ...(data?.recalls || []),
    ...(data?.search_memory_events || []),
    ...(data?.citation_events || []),
  ];
  const rememberMeta = (id: string, score?: number, timestamp?: string) => {
    if (!id) return;
    const numericScore = asNumber(score);
    if (numericScore !== null && numericScore > (scores.get(id) ?? -Infinity)) {
      scores.set(id, numericScore);
    }
    if (timestamp && !timestamps.has(id)) timestamps.set(id, timestamp);
  };
  events.forEach((event, eventIndex) => {
    const ids = eventMemoryIds(event, eventIndex).slice(0, 8);
    ids.forEach((id, index) => {
      const related = connections.get(id) || new Set<string>();
      ids.forEach((other, otherIndex) => {
        if (other !== id && Math.abs(otherIndex - index) <= 2) related.add(other);
      });
      connections.set(id, related);
      rememberMeta(id, undefined, event.timestamp);
    });
    (event.recalled_lines || []).forEach((line, lineIndex) => {
      if (typeof line === "string") return;
      rememberMeta(memoryId(line, `line-${eventIndex}-${lineIndex}`), line.final_score, event.timestamp);
    });
    (event.recalled_items || []).forEach((item, itemIndex) => {
      rememberMeta(memoryId(item, `item-${eventIndex}-${itemIndex}`), item.final_score, event.timestamp);
    });
    (event.referenced_memories || []).forEach((item, itemIndex) => {
      rememberMeta(memoryId(item, `ref-${eventIndex}-${itemIndex}`), item.final_score, event.timestamp);
    });
  });
  return { connections, scores, timestamps };
}

function collectNodes(data: MemoryDebugResp | null, dynamicData: DynamicMemoryResp | null): MemoryNode[] {
  const nodes: MemoryNode[] = [];
  const seen = new Set<string>();
  const seenContents = new Set<string>();
  const eventIndex = buildEventIndex(data);

  const coreItems = data?.core_cache?.items || [];
  coreItems.slice(0, 12).forEach((item, index) => {
    const id = memoryId(item, `core-${index}`);
    const content = String(item.content || "").trim();
    if (!id || !content || seen.has(id)) return;
    const key = contentKey(content);
    seen.add(id);
    if (key) seenContents.add(key);
    const pos = nodePosition(id, index, "core");
    nodes.push({
      id,
      ...pos,
      title: formatMemoryCoord({
        time: item.promoted_at || eventIndex.timestamps.get(id),
        importance: item.importance,
        score: eventIndex.scores.get(id) ?? null,
        mentionCount: item.mention_count,
      }),
      contentTitle: pickTitle(content),
      type: "core",
      emotion: normalizeEmotion(item.emotion_label),
      desc: content,
      connections: [],
    });
  });

  const dynamicMemories = dynamicData?.memories || [];
  dynamicMemories.forEach((item, index) => {
    const id = memoryId(item, `dynamic-${index}`);
    const content = String(item.content || "").trim();
    if (!id || !content || seen.has(id)) return;
    const key = contentKey(content);
    if (key && seenContents.has(key)) return;
    seen.add(id);
    if (key) seenContents.add(key);
    const pos = nodePosition(id || content, index, "dynamic");
    nodes.push({
      id,
      ...pos,
      title: formatMemoryCoord({
        time: item.last_mentioned || item.created_at || eventIndex.timestamps.get(id),
        importance: item.importance,
        score: eventIndex.scores.get(id) ?? null,
        mentionCount: item.mention_count,
      }),
      contentTitle: pickTitle(content),
      type: "dynamic",
      emotion: normalizeEmotion(item.emotion_label),
      desc: content,
      connections: Array.from(eventIndex.connections.get(id) || []),
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
  const [dynamicData, setDynamicData] = useState<DynamicMemoryResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [activeId, setActiveId] = useState("");
  const [viewMode, setViewMode] = useState<"" | "anchor" | "mood">("");
  const [atlasVisible, setAtlasVisible] = useState(true);
  const [rotation, setRotation] = useState({ x: 0.18, y: -0.16 });
  const dragRef = useRef({ active: false, moved: false, sx: 0, sy: 0, lx: 0, ly: 0 });
  const rotationRef = useRef(rotation);
  const frameRef = useRef<number | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [debugResult, dynamicResult] = await Promise.allSettled([
        apiJson<MemoryDebugResp>("/miniapp-api/memory-debug?limit=16&core_limit=48&scope=all"),
        apiJson<DynamicMemoryResp>("/miniapp-api/dynamic-memory"),
      ]);
      const errors: string[] = [];
      if (debugResult.status === "fulfilled" && debugResult.value?.ok) {
        setData(debugResult.value);
      } else {
        const reason = debugResult.status === "rejected" ? debugResult.reason : debugResult.value?.error;
        errors.push(`核心记忆 ${reason?.message || reason || "加载失败"}`);
        setData(null);
      }
      if (dynamicResult.status === "fulfilled" && dynamicResult.value?.ok) {
        setDynamicData(dynamicResult.value);
      } else {
        const reason = dynamicResult.status === "rejected" ? dynamicResult.reason : dynamicResult.value?.error;
        errors.push(`动态记忆 ${reason?.message || reason || "加载失败"}`);
        setDynamicData(null);
      }
      setLoadError("");
      if (errors.length === 2) throw new Error(errors.join("；"));
      if (errors.length === 1) toast(`记忆星云部分加载失败：${errors[0]}`);
    } catch (e: any) {
      const message = e?.message || String(e);
      setLoadError(message);
      toast(`记忆星云加载失败：${message}`);
      setData(null);
      setDynamicData(null);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    rotationRef.current = rotation;
  }, [rotation]);

  useEffect(() => {
    return () => {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
    };
  }, []);

  const nodes = useMemo(() => collectNodes(data, dynamicData), [data, dynamicData]);
  const activeNode = nodes.find((node) => node.id === activeId) || null;
  const activeVerse = useMemo(() => (activeNode ? buildMemoryVerse(activeNode.desc) : []), [activeNode]);

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
    rotationRef.current = {
      x: Math.max(-1.15, Math.min(1.15, rotationRef.current.x - dy * 0.004)),
      y: rotationRef.current.y + dx * 0.006,
    };
    if (frameRef.current !== null) return;
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      setRotation(rotationRef.current);
    });
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
      className={`memory-nebula-root h-full min-h-full overflow-hidden ${activeNode ? "is-focused" : ""} ${viewMode === "anchor" ? "mode-anchor" : ""} ${viewMode === "mood" ? "mode-mood" : ""} ${atlasVisible ? "" : "atlas-off"}`}
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
              aria-label={`${node.title} ${node.contentTitle}`}
            >
              <span className="star-label">{node.title}</span>
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
        <div className="memory-verse-layer" aria-live="polite">
          <div className="memory-observation memory-observation-left">
            MEMORY {activeNode.type.toUpperCase()} // {activeNode.title}
          </div>
          <div className="memory-observation memory-observation-right">
            EMOTION: {activeNode.emotion.toUpperCase()} // INDEX: {activeNode.id.slice(0, 8)}
          </div>
          <div className="memory-verse" aria-label={activeNode.desc}>
            {activeVerse.map((line, index) => (
              <div key={`${activeNode.id}-${index}`} className={`memory-phrase ${memoryVerseClass(line, index, activeVerse.length)}`}>
                {line}
              </div>
            ))}
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
  font-family: "Playfair Display", Georgia, "Times New Roman", serif;
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
  will-change: transform, opacity;
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
  opacity: 0.34;
}
.star-core::before,
.star.active::before {
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
  box-shadow: 0 0 7px rgba(255, 255, 255, 0.46);
}
.star-label {
  position: absolute;
  top: 13px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  color: rgba(232, 236, 255, 0.62);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 8px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-shadow: 0 0 14px rgba(4, 5, 26, 0.9);
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
.mode-anchor .star-core .star-label { opacity: 0.92; transform: translateX(-50%) translateY(2px); }
.mode-mood .star-core { opacity: 0.38 !important; filter: grayscale(0.7); }
.mode-mood .star-dynamic { width: 6px; height: 6px; }
.mode-mood .star-dynamic[data-emotion="positive"] { background: #f2e3b6; box-shadow: 0 0 14px rgba(242, 227, 182, 0.72), 0 0 28px rgba(242, 227, 182, 0.28); }
.mode-mood .star-dynamic[data-emotion="negative"] { background: #c5a3ff; box-shadow: 0 0 14px rgba(197, 163, 255, 0.72), 0 0 28px rgba(98, 76, 170, 0.34); }
.mode-mood .star-dynamic[data-emotion="neutral"] { background: #dfe7ff; box-shadow: 0 0 12px rgba(223, 231, 255, 0.56); }
.star.active { filter: none; }
.star.active .star-label,
.star.related .star-label { opacity: 0.82; transform: translateX(-50%) translateY(2px); }
.memory-verse-layer {
  position: absolute;
  inset: 0;
  z-index: 32;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 88px 48px 92px;
  pointer-events: none;
}
.memory-verse {
  width: min(560px, calc(100vw - 96px));
  transform: translateY(-2vh);
  text-align: center;
  animation: memoryVerseIn 0.48s cubic-bezier(0.16, 1, 0.3, 1);
}
.memory-phrase {
  margin: 8px 0;
  color: rgba(238, 244, 255, 0.78);
  font-family: "Inter", "PingFang SC", "Microsoft YaHei UI", sans-serif;
  letter-spacing: 0;
  line-height: 1.25;
  text-shadow: 0 0 18px rgba(126, 183, 255, 0.28), 0 0 34px rgba(41, 96, 176, 0.24);
}
.memory-phrase-title {
  color: #9fdcff;
  font-size: clamp(28px, 8.5vw, 52px);
  font-weight: 800;
  line-height: 1.05;
  text-shadow: 0 0 16px rgba(95, 190, 255, 0.68), 0 0 42px rgba(38, 104, 190, 0.48);
}
.memory-phrase-loud {
  color: rgba(245, 249, 255, 0.96);
  font-size: clamp(22px, 6vw, 34px);
  font-weight: 800;
  text-shadow: 0 0 16px rgba(196, 224, 255, 0.72), 0 0 40px rgba(73, 129, 216, 0.4);
}
.memory-phrase-mid {
  color: rgba(226, 234, 250, 0.78);
  font-size: clamp(16px, 4.3vw, 23px);
  font-weight: 650;
}
.memory-phrase-soft {
  color: rgba(209, 217, 236, 0.54);
  font-size: clamp(13px, 3.4vw, 18px);
  font-weight: 500;
  font-style: italic;
}
.memory-observation {
  position: absolute;
  max-height: min(72vh, 520px);
  overflow: hidden;
  color: rgba(168, 178, 210, 0.58);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9px;
  letter-spacing: 0.18em;
  line-height: 1.6;
  text-transform: uppercase;
  text-shadow: 0 0 18px rgba(4, 5, 26, 0.95);
  white-space: nowrap;
  writing-mode: vertical-rl;
}
.memory-observation-left {
  left: 20px;
  bottom: calc(env(safe-area-inset-bottom, 0px) + 24px);
  transform: rotate(180deg);
}
.memory-observation-right {
  right: 18px;
  top: calc(env(safe-area-inset-top, 0px) + 24px);
}
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
  font-family: "Playfair Display", Georgia, "Times New Roman", serif;
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
@media (max-width: 460px) {
  .memory-verse-layer { padding-left: 34px; padding-right: 34px; }
  .memory-verse { width: min(330px, calc(100vw - 84px)); }
  .memory-observation {
    font-size: 8px;
    letter-spacing: 0.14em;
    opacity: 0.72;
  }
  .memory-observation-left { left: 10px; }
  .memory-observation-right { right: 9px; }
}
@keyframes memoryVerseIn {
  0% { opacity: 0; transform: translateY(1vh) scale(0.98); filter: blur(6px); }
  100% { opacity: 1; transform: translateY(-2vh) scale(1); filter: blur(0); }
}
@keyframes nebulaPulse {
  0%, 100% { opacity: 0.4; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.8; transform: translate(-50%, -50%) scale(1.3); }
}
`;
