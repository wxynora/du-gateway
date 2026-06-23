import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type SecretDrawerConfig = {
  configured?: {
    box?: boolean;
    sealed?: boolean;
  };
  updated_at?: string;
};

type SecretDrawerStats = {
  total?: number;
  ordinary?: number;
  sealed?: number;
  pinned?: number;
  needs整理?: number;
  latest_at?: string;
  by_type?: Record<string, number>;
  by_tag?: Record<string, number>;
};

type SecretDrawerMediaRef = {
  kind?: string;
  key?: string;
  url?: string;
  name?: string;
  contentType?: string;
};

type SecretDrawerItem = {
  id: string;
  type?: string;
  title?: string;
  content?: string;
  why?: string;
  tags?: string[];
  pinned?: boolean;
  sealed?: boolean;
  deleted?: boolean;
  media_refs?: SecretDrawerMediaRef[];
  source?: {
    channel?: string;
    url?: string;
    window_id?: string;
  };
  created_at?: string;
  updated_at?: string;
};

type Layer = "drawer" | "alcove";
type FilterKey = "all" | "message" | "photo" | "dream" | "note" | "surf" | "misc" | "pinned" | "needs";

const TYPE_LABELS: Record<string, string> = {
  message: "Dialogue",
  photo: "Photo",
  dream: "Dream",
  note: "Thought",
  surf: "Surf",
  misc: "Note",
};

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: "all", label: "All" },
  { key: "pinned", label: "Pinned" },
  { key: "dream", label: "Dreams" },
  { key: "note", label: "Thoughts" },
  { key: "message", label: "Dialogues" },
  { key: "photo", label: "Photos" },
  { key: "surf", label: "Surf" },
  { key: "needs", label: "Pending" },
];

const serifStyle: React.CSSProperties = { fontFamily: '"Playfair Display", "Times New Roman", serif' };

export function SecretDrawerTab({ onExit }: { onExit?: () => void }) {
  const toast = useToast();
  const randomTimerRef = useRef<number | null>(null);
  const [config, setConfig] = useState<SecretDrawerConfig | null>(null);
  const [stats, setStats] = useState<SecretDrawerStats | null>(null);
  const [items, setItems] = useState<SecretDrawerItem[]>([]);
  const [selected, setSelected] = useState<SecretDrawerItem | null>(null);
  const [layer, setLayer] = useState<Layer>("drawer");
  const [drawerUnlocked, setDrawerUnlocked] = useState(false);
  const [alcoveUnlocked, setAlcoveUnlocked] = useState(false);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [drawingId, setDrawingId] = useState<string | null>(null);

  const activeUnlocked = layer === "drawer" ? drawerUnlocked : alcoveUnlocked;

  useEffect(() => {
    setDrawerUnlocked(false);
    setAlcoveUnlocked(false);
    setSelected(null);
    return () => {
      if (randomTimerRef.current) window.clearTimeout(randomTimerRef.current);
    };
  }, []);

  const loadConfig = useCallback(async () => {
    const res = await apiJson<{ ok?: boolean; configured?: SecretDrawerConfig["configured"]; updated_at?: string }>("/miniapp-api/secret-drawer/config");
    setConfig({ configured: res.configured || {}, updated_at: res.updated_at || "" });
  }, []);

  const loadStats = useCallback(async () => {
    const suffix = layer === "alcove" && alcoveUnlocked ? "?include_sealed_details=1" : "";
    const res = await apiJson<{ ok?: boolean; stats?: SecretDrawerStats }>(`/miniapp-api/secret-drawer/stats${suffix}`);
    setStats(res.stats || {});
  }, [alcoveUnlocked, layer]);

  const loadItems = useCallback(async () => {
    if (!activeUnlocked) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "120");
      if (layer === "alcove") params.set("sealed_only", "1");
      if (query.trim()) params.set("q", query.trim());
      if (filter === "pinned") params.set("pinned", "1");
      else if (filter === "needs") params.set("needs_organize", "1");
      else if (filter !== "all") params.set("type", filter);
      const res = await apiJson<{ ok?: boolean; items?: SecretDrawerItem[] }>(`/miniapp-api/secret-drawer/items?${params.toString()}`);
      const list = Array.isArray(res.items) ? res.items : [];
      setItems(layer === "alcove" ? list.filter((item) => item.sealed) : list.filter((item) => !item.sealed));
    } catch (e: any) {
      toast(`抽屉读取失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [activeUnlocked, filter, layer, query, toast]);

  useEffect(() => {
    void Promise.all([loadConfig(), loadStats()]).catch((e: any) => toast(`秘密抽屉读取失败：${e?.message || e}`));
  }, [loadConfig, loadStats, toast]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  async function unlockPin(pin: string): Promise<boolean> {
    try {
      const res = await apiJson<{ ok?: boolean; unlocked?: boolean }>("/miniapp-api/secret-drawer/unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ layer: layer === "alcove" ? "sealed" : "box", pin }),
      });
      if (!res.unlocked) return false;
      if (layer === "drawer") setDrawerUnlocked(true);
      else setAlcoveUnlocked(true);
      return true;
    } catch {
      return false;
    }
  }

  function openRandomPaper() {
    const pool = items.filter((item) => layer === "alcove" ? item.sealed : !item.sealed);
    if (!pool.length) {
      toast("现在没有可翻的纸条");
      return;
    }
    const picked = pool[Math.floor(Math.random() * pool.length)];
    if (!picked) return;
    setDrawingId(picked.id);
    if (randomTimerRef.current) window.clearTimeout(randomTimerRef.current);
    randomTimerRef.current = window.setTimeout(() => {
      setSelected(picked);
      setDrawingId(null);
    }, 620);
  }

  function switchLayer(next: Layer) {
    setLayer(next);
    setSelected(null);
    setFilter("all");
    setQuery("");
    setDrawingId(null);
  }

  if (!config) {
    return (
      <SecretSurface onExit={onExit}>
        <EmptyVault title="Opening drawer" text="The drawer is waking up." />
      </SecretSurface>
    );
  }

  if (!activeUnlocked) {
    return (
      <PinGate
        layer={layer}
        onExit={onExit}
        onSubmit={(pin) => unlockPin(pin)}
        onSwitchLayer={switchLayer}
      />
    );
  }

  if (selected) {
    return <SecretDrawerDetail item={selected} layer={layer} onBack={() => setSelected(null)} />;
  }

  if (layer === "alcove") {
    return (
      <AlcoveView
        items={items}
        loading={loading}
        onExit={onExit}
        onHome={() => switchLayer("drawer")}
        onSelect={setSelected}
      />
    );
  }

  return (
    <DrawerView
      stats={stats}
      items={items}
      filter={filter}
      query={query}
      loading={loading}
      drawingId={drawingId}
      onExit={onExit}
      onFilter={setFilter}
      onQuery={setQuery}
      onVault={() => switchLayer("alcove")}
      onRandom={openRandomPaper}
      onSelect={setSelected}
    />
  );
}

function SecretSurface({ children, onExit, tone = "paper" }: { children: React.ReactNode; onExit?: () => void; tone?: "paper" | "detail" | "vault" }) {
  const bg = tone === "detail" ? "bg-[#FDFBF7]" : tone === "vault" ? "bg-[#F0EAE3]" : "bg-[#F5F0EB]";
  return (
    <div className={`fixed inset-0 z-40 min-h-dvh overflow-hidden ${bg} text-[#2D2926]`}>
      <style>{`@keyframes secretPinShake{0%,100%{transform:translateX(0)}25%{transform:translateX(-8px)}75%{transform:translateX(8px)}}`}</style>
      <div className="pointer-events-none absolute inset-0 opacity-[0.04]" style={{ backgroundImage: grainBackground() }} />
      {onExit ? <ExitButton onClick={onExit} /> : null}
      {children}
    </div>
  );
}

function ExitButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="absolute left-4 top-[calc(env(safe-area-inset-top,0px)+12px)] z-30 flex h-10 w-10 items-center justify-center rounded-full bg-black/5 text-[#2D2926]/70 active:bg-black/10"
      onClick={onClick}
      aria-label="返回"
    >
      <BackGlyph />
    </button>
  );
}

function PinGate({
  layer,
  onSubmit,
  onSwitchLayer,
  onExit,
}: {
  layer: Layer;
  onSubmit: (pin: string) => Promise<boolean>;
  onSwitchLayer: (layer: Layer) => void;
  onExit?: () => void;
}) {
  const [pin, setPin] = useState("");
  const [shaking, setShaking] = useState(false);
  const isAlcove = layer === "alcove";

  function pushDigit(digit: string) {
    setPin((prev) => (prev + digit).slice(0, 4));
  }

  useEffect(() => {
    if (pin.length !== 4) return;
    let cancelled = false;
    void onSubmit(pin).then((ok) => {
      if (cancelled) return;
      if (ok) {
        setPin("");
        return;
      }
      setShaking(true);
      window.setTimeout(() => {
        setShaking(false);
        setPin("");
      }, isAlcove ? 300 : 420);
    });
    return () => {
      cancelled = true;
    };
  }, [isAlcove, onSubmit, pin]);

  return (
    <SecretSurface onExit={onExit}>
      <div className="relative flex h-full flex-col items-center justify-center p-8">
        <div className="mb-12 text-center">
          {isAlcove ? (
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-amber-200/50 text-amber-700">
              <LockKeyGlyph />
            </div>
          ) : (
            <CabinetGlyph />
          )}
          <h1 className={`${isAlcove ? "text-2xl" : "text-4xl"} mb-2 font-medium tracking-tight`} style={serifStyle}>
            {isAlcove ? "The Inner Vault" : "Secret Drawer"}
          </h1>
          <p className={`${isAlcove ? "text-xs opacity-40" : "text-sm opacity-60"} font-light italic`}>
            {isAlcove ? "Enter your second signature." : "A quiet place for stray thoughts."}
          </p>
        </div>

        <div className={`mb-12 flex gap-4 ${shaking ? "animate-[secretPinShake_0.32s_ease-in-out]" : ""}`}>
          {[0, 1, 2, 3].map((idx) => (
            <span
              key={idx}
              className={`h-3 w-3 rounded-full border-[1.5px] border-amber-700/50 transition-colors ${
                idx < pin.length ? (isAlcove ? "bg-amber-500" : "bg-[#2D2926]") : "bg-transparent"
              }`}
            />
          ))}
        </div>

        <div className="grid w-full max-w-[240px] grid-cols-3 gap-6">
          {"123456789".split("").map((digit) => (
            <NumberButton key={digit} label={digit} onClick={() => pushDigit(digit)} />
          ))}
          {isAlcove ? (
            <button
              type="button"
              className="flex h-16 w-16 items-center justify-center rounded-full text-sm text-gray-500 hover:bg-white/5 active:bg-white/10"
              onClick={() => onSwitchLayer("drawer")}
            >
              Cancel
            </button>
          ) : (
            <div />
          )}
          <NumberButton label="0" onClick={() => pushDigit("0")} />
          <button
            type="button"
            className="flex h-16 w-16 items-center justify-center rounded-full text-sm font-medium uppercase tracking-widest text-amber-500/60 hover:bg-white/5 active:bg-white/10"
            onClick={() => setPin("")}
          >
            Clear
          </button>
        </div>
      </div>
    </SecretSurface>
  );
}

function NumberButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      className="flex h-16 w-16 items-center justify-center rounded-full text-xl font-medium text-[#2D2926] transition-colors hover:bg-white/5 active:bg-white/10"
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function DrawerView({
  stats,
  items,
  filter,
  query,
  loading,
  drawingId,
  onExit,
  onFilter,
  onQuery,
  onVault,
  onRandom,
  onSelect,
}: {
  stats: SecretDrawerStats | null;
  items: SecretDrawerItem[];
  filter: FilterKey;
  query: string;
  loading: boolean;
  drawingId: string | null;
  onExit?: () => void;
  onFilter: (filter: FilterKey) => void;
  onQuery: (query: string) => void;
  onVault: () => void;
  onRandom: () => void;
  onSelect: (item: SecretDrawerItem) => void;
}) {
  const total = stats?.ordinary || items.length || 0;
  const pending = stats?.needs整理 || 0;
  return (
    <SecretSurface onExit={onExit}>
      <div className="relative flex h-full min-h-0 flex-col">
        <div className="px-6 pb-4 pt-[calc(env(safe-area-inset-top,0px)+48px)]">
          <div className="mb-6 flex items-end justify-between">
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-amber-800/60">Archive Collections</p>
              <h2 className="text-3xl font-medium text-[#2D2926]" style={serifStyle}>Your Drawer</h2>
            </div>
            <button
              type="button"
              className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 shadow-[0_0_20px_rgba(217,119,6,0.10)] transition-colors active:bg-amber-200"
              onClick={onVault}
              aria-label="Open inner vault"
            >
              <LockClosedGlyph />
            </button>
          </div>

          <div className="mb-6 flex items-center gap-4">
            <div className="flex flex-col">
              <span className="text-lg font-medium text-[#2D2926]">{total}</span>
              <span className="text-[10px] uppercase tracking-tighter text-gray-400">Total</span>
            </div>
            <div className="h-6 w-px bg-gray-200" />
            <div className="flex flex-col">
              <span className="text-lg font-medium text-[#2D2926]">{pending}</span>
              <span className="text-[10px] uppercase tracking-tighter text-gray-400">Pending</span>
            </div>
            <div className="relative ml-auto w-full max-w-[200px]">
              <input
                value={query}
                onChange={(e) => onQuery(e.target.value)}
                className="w-full rounded-full border border-black/5 bg-white/50 px-4 py-2 pr-9 text-xs text-[#2D2926] outline-none focus:border-amber-200"
                placeholder="Search memories..."
              />
              <span className="absolute right-3 top-2.5 text-gray-400"><SearchGlyph /></span>
            </div>
          </div>

          <div className="flex gap-2 overflow-x-auto pb-2 [-webkit-overflow-scrolling:touch]">
            {FILTERS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`shrink-0 whitespace-nowrap rounded-full px-4 py-1.5 text-[11px] font-medium ${
                  filter === item.key ? "bg-amber-700 text-white shadow-sm" : "border border-black/5 bg-white text-[#2D2926]"
                }`}
                onClick={() => onFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="relative mt-4 min-h-0 flex-1 overflow-hidden" id="stack-container">
          {loading ? <EmptyVault title="Shuffling papers" text="The drawer is turning over." /> : null}
          {!loading && !items.length ? <EmptyVault title="No papers yet" text="Stray thoughts will stack here when they arrive." /> : null}
          {!loading && items.length ? <PaperStack items={items} drawingId={drawingId} onSelect={onSelect} /> : null}
        </div>

        <div className="pointer-events-none absolute bottom-[calc(env(safe-area-inset-bottom,0px)+40px)] left-0 right-0 flex justify-center">
          <button
            type="button"
            className="pointer-events-auto flex items-center gap-3 rounded-full bg-[#2D2926] px-8 py-4 text-white shadow-xl transition-all active:scale-95"
            onClick={onRandom}
          >
            <HandGlyph />
            <span className="text-sm font-medium tracking-tight">Draw Random Paper</span>
          </button>
        </div>
      </div>
    </SecretSurface>
  );
}

function AlcoveView({
  items,
  loading,
  onExit,
  onHome,
  onSelect,
}: {
  items: SecretDrawerItem[];
  loading: boolean;
  onExit?: () => void;
  onHome: () => void;
  onSelect: (item: SecretDrawerItem) => void;
}) {
  return (
    <SecretSurface tone="vault" onExit={onExit}>
      <div className="relative flex h-full min-h-0 flex-col overflow-hidden">
        <div className="px-6 pb-4 pt-[calc(env(safe-area-inset-top,0px)+48px)]">
          <div className="mb-6 flex items-end justify-between text-[#2D2926]/90">
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-amber-700/50">Confidential Compartment</p>
              <h2 className="text-3xl font-medium" style={serifStyle}>Deep Vault</h2>
            </div>
            <button
              type="button"
              className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-200/50 text-amber-700 transition-colors active:bg-amber-300/60"
              onClick={onHome}
              aria-label="Back to drawer"
            >
              <HomeGlyph />
            </button>
          </div>
        </div>

        <div className="relative mt-4 min-h-0 flex-1 overflow-hidden">
          {loading ? <EmptyVault title="Opening vault" text="The chamber is still settling." /> : null}
          {!loading && !items.length ? (
            <EmptyVault
              title=""
              text="No stray thoughts here yet. This chamber is for the things you only say to the dark."
              icon={<FeatherGlyph />}
            />
          ) : null}
          {!loading && items.length ? <PaperStack items={items} onSelect={onSelect} compact /> : null}
        </div>
      </div>
    </SecretSurface>
  );
}

function PaperStack({
  items,
  drawingId,
  compact = false,
  onSelect,
}: {
  items: SecretDrawerItem[];
  drawingId?: string | null;
  compact?: boolean;
  onSelect: (item: SecretDrawerItem) => void;
}) {
  const visible = items.slice(0, compact ? 8 : 12);
  return (
    <div className="relative h-full min-h-[420px]">
      {visible.map((item, index) => (
        <PaperCard
          key={item.id}
          item={item}
          index={index}
          drawing={drawingId === item.id}
          muted={!!drawingId && drawingId !== item.id}
          onClick={() => onSelect(item)}
        />
      ))}
    </div>
  );
}

function PaperCard({
  item,
  index,
  drawing,
  muted,
  onClick,
}: {
  item: SecretDrawerItem;
  index: number;
  drawing?: boolean;
  muted?: boolean;
  onClick: () => void;
}) {
  const type = TYPE_LABELS[item.type || "misc"] || "Note";
  const preview = String(item.content || item.why || "This paper is still blank.").replace(/\s+/g, " ").slice(0, 120);
  const colors = ["bg-white/90", "bg-[#FFFBF2]/95", "bg-[#FDF7EA]/95", "bg-[#F8F1E8]/95"];
  const rotate = [-1.2, 0.9, -0.45, 1.35, -0.8][index % 5] || 0;
  return (
    <button
      type="button"
      className={`paper-card absolute left-8 right-8 rounded-sm border border-black/5 p-6 text-left shadow-md transition-all duration-500 ${
        colors[index % colors.length]
      } ${drawing ? "scale-[1.04] opacity-100 shadow-xl" : ""} ${muted ? "opacity-30" : "opacity-100"}`}
      style={{
        top: `${index * 25 + 20}px`,
        transform: `rotate(${rotate}deg) ${drawing ? "translateY(-24px)" : ""}`,
        zIndex: drawing ? 80 : index + 10,
      }}
      onClick={onClick}
    >
      <div className="mb-4 flex items-start justify-between">
        <span className="text-[9px] font-bold uppercase tracking-widest text-amber-800/50">{type}</span>
        <span className="text-[9px] font-medium text-gray-400">{formatShortTime(item.created_at)}</span>
      </div>
      <h3 className="mb-2 text-xl font-medium leading-tight text-[#2D2926]" style={serifStyle}>{item.title || "Untitled Paper"}</h3>
      <p className="line-clamp-2 text-xs font-light text-gray-500">{preview}</p>
      {item.pinned ? <div className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-amber-500" /> : null}
      <div className="mt-4 flex gap-2">
        <div className="h-1.5 w-1.5 rounded-full bg-gray-100" />
        <div className="h-1.5 w-1.5 rounded-full bg-gray-100" />
      </div>
    </button>
  );
}

function SecretDrawerDetail({ item, layer, onBack }: { item: SecretDrawerItem; layer: Layer; onBack: () => void }) {
  const media = item.media_refs || [];
  const type = TYPE_LABELS[item.type || "misc"] || "Note";
  return (
    <SecretSurface tone="detail">
      <div className="flex h-full min-h-0 flex-col bg-[#FDFBF7]">
        <div className="flex items-center justify-between px-6 pb-4 pt-[calc(env(safe-area-inset-top,0px)+48px)]">
          <button type="button" className="flex h-10 w-10 items-center justify-center rounded-full bg-black/5 active:bg-black/10" onClick={onBack} aria-label="Back">
            <BackGlyph />
          </button>
          <div className="flex gap-4 text-gray-400">
            <ShareGlyph />
            <DotsGlyph />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-8 pb-12 [-webkit-overflow-scrolling:touch]">
          <div className="mb-8 mt-4">
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-amber-800">{layer === "alcove" || item.sealed ? "Vault" : type}</span>
              <span className="text-[10px] text-gray-400">{formatDetailDate(item.created_at)}</span>
            </div>
            <h1 className="text-4xl font-medium leading-tight text-[#2D2926]" style={serifStyle}>{item.title || "Untitled Paper"}</h1>
          </div>

          <div className="space-y-6 text-lg font-light leading-relaxed text-[#2D2926]/80" style={serifStyle}>
            {item.why ? <p>{item.why}</p> : null}
            {media.map((ref, index) => (
              <figure key={`${ref.key || ref.url || index}`} className="mx-2 my-8 rotate-[-1deg] bg-white p-2 pb-6 shadow-md">
                <div className="mb-4 flex aspect-[4/3] items-center justify-center overflow-hidden rounded-sm bg-gray-200">
                  <img src={mediaUrl(ref)} alt={ref.name || "secret drawer media"} className="h-full w-full object-cover" loading="lazy" />
                </div>
                <figcaption className="text-center font-mono text-xs tracking-tighter text-gray-400">{ref.name || ref.kind || "SAVED_IMAGE"}</figcaption>
              </figure>
            ))}
            {item.content ? <p className="whitespace-pre-wrap">{item.content}</p> : null}
            {!item.why && !item.content && !media.length ? <p>This paper is quiet for now.</p> : null}
          </div>

          <div className="mt-12 border-t border-black/5 pt-8">
            {item.tags?.length ? (
              <div className="mb-6 flex flex-wrap gap-2">
                {item.tags.map((tag) => <span key={tag} className="text-[11px] font-medium text-gray-500">#{tag}</span>)}
              </div>
            ) : null}
            <div className="space-y-1 text-[10px] text-gray-400">
              <p>Saved: {formatFullTime(item.created_at) || "Unknown"}</p>
              {item.updated_at ? <p>Updated: {formatFullTime(item.updated_at)}</p> : null}
              {item.source?.channel ? <p>Source: {item.source.channel}</p> : null}
            </div>
          </div>
        </div>
      </div>
    </SecretSurface>
  );
}

function EmptyVault({ title, text, icon }: { title?: string; text: string; icon?: React.ReactNode }) {
  return (
    <div className="flex h-full min-h-[300px] flex-col items-center justify-center px-10 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-black/5 text-gray-600">
        {icon || <FeatherGlyph />}
      </div>
      {title ? <div className="mb-2 text-sm font-medium text-[#2D2926]/60">{title}</div> : null}
      <p className="text-sm font-light italic text-[#2D2926]/40">{text}</p>
    </div>
  );
}

function CabinetGlyph() {
  return (
    <svg className="mx-auto mb-6 h-12 w-12 text-amber-700 opacity-80" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path d="M9 11h30v26H9z" fill="currentColor" opacity="0.14" />
      <path d="M10 11h28v26H10zM10 20h28M10 28.5h28" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M22 15.5h4M22 24.2h4M22 32.7h4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function LockKeyGlyph() {
  return (
    <svg className="h-10 w-10" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path d="M14.5 22.5h19v16h-19z" fill="currentColor" opacity="0.14" />
      <path d="M14.5 22.5h19v16h-19z" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
      <path d="M18 22.5v-6.2C18 12.1 20.7 9 24.8 9c3.4 0 5.8 2 6.5 5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M24 28.5v4" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

function LockClosedGlyph() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M17 9h-1V7a4 4 0 0 0-8 0v2H7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2Zm-7-2a2 2 0 0 1 4 0v2h-4V7Z" />
    </svg>
  );
}

function HomeGlyph() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M3 11.4 12 4l9 7.4-1.3 1.5L18 11.5V20H6v-8.5l-1.7 1.4L3 11.4Z" />
    </svg>
  );
}

function BackGlyph() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

function SearchGlyph() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function HandGlyph() {
  return (
    <svg className="h-5 w-5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12" />
      <path d="M11 11V4.5a1.5 1.5 0 0 1 3 0V12" />
      <path d="M14 11V6.5a1.5 1.5 0 0 1 3 0V13" />
      <path d="M8 13c-1.5-1.5-3-2-3.8-1.2-.8.8-.2 2.1 1.2 3.8L8 19c1 1.3 2.4 2 4 2h2.5A4.5 4.5 0 0 0 19 16.5V11" />
    </svg>
  );
}

function FeatherGlyph() {
  return (
    <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20.24 3.76a6 6 0 0 0-8.48 0L4 11.52V20h8.48l7.76-7.76a6 6 0 0 0 0-8.48Z" />
      <path d="M16 8 2 22" />
      <path d="M17.5 15H9" />
    </svg>
  );
}

function ShareGlyph() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4" />
    </svg>
  );
}

function DotsGlyph() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="5" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="19" cy="12" r="1.8" />
    </svg>
  );
}

function grainBackground(): string {
  return "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E\")";
}

function formatShortTime(value?: string): string {
  const text = String(value || "");
  const match = text.match(/(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})/);
  return match ? `${match[1]}/${match[2]}` : "";
}

function formatDetailDate(value?: string): string {
  const text = String(value || "");
  const match = text.match(/(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[1]}.${match[2]}.${match[3]}` : "";
}

function formatFullTime(value?: string): string {
  const text = String(value || "");
  return text.replace("T", " ").replace(/\+\d{2}:?\d{2}$/, "");
}

function mediaUrl(ref: SecretDrawerMediaRef): string {
  const raw = String(ref.url || "").trim();
  if (raw) return raw;
  const key = String(ref.key || "").trim();
  return key ? `/miniapp-api/chat-media/raw-public?key=${encodeURIComponent(key)}` : "";
}
