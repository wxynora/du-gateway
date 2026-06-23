import React, { useCallback, useEffect, useMemo, useState } from "react";
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
  message: "对话",
  photo: "图片",
  dream: "梦境",
  note: "碎碎念",
  surf: "冲浪",
  misc: "其他",
};

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: "all", label: "全部" },
  { key: "message", label: "对话" },
  { key: "photo", label: "图片" },
  { key: "dream", label: "梦境" },
  { key: "note", label: "碎碎念" },
  { key: "surf", label: "冲浪" },
  { key: "pinned", label: "置顶" },
  { key: "needs", label: "待整理" },
];

export function SecretDrawerTab() {
  const toast = useToast();
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

  const activeConfigured = layer === "drawer" ? !!config?.configured?.box : !!config?.configured?.sealed;
  const activeUnlocked = layer === "drawer" ? drawerUnlocked : alcoveUnlocked;

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

  const topTags = useMemo(() => {
    const entries = Object.entries(stats?.by_tag || {});
    return entries.slice(0, 8).map(([tag, count]) => ({ tag, count }));
  }, [stats?.by_tag]);

  async function unlockPin(pin: string) {
    try {
      const res = await apiJson<{ ok?: boolean; unlocked?: boolean }>("/miniapp-api/secret-drawer/unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ layer: layer === "alcove" ? "sealed" : "box", pin }),
      });
      if (!res.unlocked) {
        toast("PIN 不对");
        return;
      }
      if (layer === "drawer") setDrawerUnlocked(true);
      else setAlcoveUnlocked(true);
    } catch (e: any) {
      toast(`解锁失败：${e?.message || e}`);
    }
  }

  async function openRandomPaper() {
    const pool = items.filter((item) => layer === "alcove" ? item.sealed : !item.sealed);
    if (!pool.length) {
      toast("现在没有可翻的纸条");
      return;
    }
    setSelected(pool[Math.floor(Math.random() * pool.length)] || null);
  }

  function switchLayer(next: Layer) {
    setLayer(next);
    setSelected(null);
    setFilter("all");
    setQuery("");
  }

  if (!config) {
    return (
      <div className="min-h-full bg-[#f8f0e6] px-5 pb-7 pt-8 text-[#352b24]">
        <EmptyPaper title="打开抽屉中" text="先看一眼锁和纸条。" />
      </div>
    );
  }

  if (!activeUnlocked) {
    return (
      <PinGate
        layer={layer}
        configured={activeConfigured}
        stats={stats}
        onSubmit={(pin) => void unlockPin(pin)}
        onSwitchLayer={switchLayer}
      />
    );
  }

  if (selected) {
    return (
      <SecretDrawerDetail
        item={selected}
        layer={layer}
        onBack={() => setSelected(null)}
      />
    );
  }

  return (
    <div className="min-h-full overflow-x-hidden bg-[#f8f0e6] text-[#352b24]">
      <div
        className="min-h-full px-5 pb-7 pt-5"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgba(120,91,61,0.12) 1px, transparent 0), linear-gradient(180deg, rgba(255,255,255,0.86), rgba(248,240,230,0.92))",
          backgroundSize: "18px 18px, 100% 100%",
        }}
      >
        <header className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#a37b4e]">{layer === "drawer" ? "private drawer" : "hidden alcove"}</div>
            <h2 className="mt-1 text-[26px] font-semibold tracking-tight text-[#2d241f]">{layer === "drawer" ? "秘密抽屉" : "暗格"}</h2>
            <p className="mt-2 text-[13px] leading-5 text-[#8a7662]">
              {layer === "drawer" ? summarizeStats(stats) : `暗格里有 ${stats?.sealed || 0} 条，只看真正不想被轻易翻到的东西。`}
            </p>
          </div>
          <button
            type="button"
            className="shrink-0 rounded-full border border-[#e7d8c4] bg-[#fffaf1]/90 px-4 py-2 text-[12px] font-semibold text-[#735635] shadow-[0_10px_24px_-20px_rgba(84,55,27,0.7)] active:scale-95"
            onClick={() => switchLayer(layer === "drawer" ? "alcove" : "drawer")}
          >
            {layer === "drawer" ? "进暗格" : "回抽屉"}
          </button>
        </header>

        <section className="mt-5 grid grid-cols-4 gap-2">
          <Metric label="纸条" value={layer === "drawer" ? stats?.ordinary || 0 : stats?.sealed || 0} />
          <Metric label="置顶" value={stats?.pinned || 0} />
          <Metric label="待整理" value={stats?.needs整理 || 0} />
          <Metric label="图片" value={stats?.by_type?.photo || 0} />
        </section>

        <section className="mt-5 rounded-[26px] border border-[#ecdcc7] bg-[#fffaf2]/78 p-3 shadow-[0_18px_42px_-34px_rgba(86,56,31,0.85)] backdrop-blur">
          <div className="flex items-center gap-2">
            <div className="flex-1 rounded-full bg-white/85 px-4 py-2.5 shadow-inner shadow-[#ead8bf]/70">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full bg-transparent text-[13px] text-[#3a3028] outline-none placeholder:text-[#b8a790]"
                placeholder="搜标题、标签、内容..."
              />
            </div>
            <button
              type="button"
              className="h-10 rounded-full bg-[#2f2722] px-4 text-[13px] font-semibold text-[#fff8ed] shadow-[0_12px_26px_-18px_rgba(47,39,34,0.9)] active:scale-95"
              onClick={() => void openRandomPaper()}
            >
              随机
            </button>
          </div>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1 [-webkit-overflow-scrolling:touch]">
            {FILTERS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`shrink-0 rounded-full px-3.5 py-2 text-[12px] font-semibold transition ${
                  filter === item.key ? "bg-[#2f2722] text-[#fff8ed]" : "bg-white/72 text-[#806b56]"
                }`}
                onClick={() => setFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>

        {topTags.length && layer === "drawer" ? (
          <section className="mt-4 flex flex-wrap gap-2">
            {topTags.map((tag) => (
              <span key={tag.tag} className="rounded-full bg-[#efe2cf]/75 px-3 py-1.5 text-[11px] font-semibold text-[#85684a]">
                {tag.tag} · {tag.count}
              </span>
            ))}
          </section>
        ) : null}

        <section className="relative mt-5 min-h-[340px] pb-24">
          {loading ? <EmptyPaper title="翻抽屉中" text="纸条在路上。" /> : null}
          {!loading && !items.length ? (
            <EmptyPaper
              title={layer === "drawer" ? "抽屉还是空的" : "暗格里还空着"}
              text={layer === "drawer" ? "等后端存进第一张纸条，这里会自然堆起来。" : "暗格只显示被标记为私密的条目。"}
            />
          ) : null}
          <div className="space-y-4">
            {items.map((item, index) => (
              <PaperCard key={item.id} item={item} index={index} onClick={() => setSelected(item)} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function PinGate({
  layer,
  configured,
  stats,
  onSubmit,
  onSwitchLayer,
}: {
  layer: Layer;
  configured: boolean;
  stats: SecretDrawerStats | null;
  onSubmit: (pin: string) => void;
  onSwitchLayer: (layer: Layer) => void;
}) {
  const [pin, setPin] = useState("");
  const title = layer === "drawer" ? "秘密抽屉" : "暗格";
  const subtitle = configured ? "输入四位 PIN 偷看一下。" : "默认 PIN 是 0000。";

  function pushDigit(digit: string) {
    setPin((prev) => (prev + digit).slice(0, 4));
  }

  useEffect(() => {
    if (pin.length === 4) {
      onSubmit(pin);
      setPin("");
    }
  }, [onSubmit, pin]);

  return (
    <div className="min-h-full bg-[#f8f0e6] px-7 pb-8 pt-8 text-[#352b24]">
      <div className="mx-auto flex min-h-[calc(100dvh-150px)] max-w-[420px] flex-col justify-center">
        <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#a37b4e]">private drawer</div>
        <h2 className="mt-2 text-[30px] font-semibold tracking-tight">{title}</h2>
        <p className="mt-3 text-[14px] leading-6 text-[#8a7662]">{subtitle}</p>

        <div className="mt-8 rounded-[30px] border border-[#ecdcc7] bg-[#fffaf1]/86 p-6 shadow-[0_24px_58px_-42px_rgba(83,53,30,0.9)]">
          <div className="mb-7 flex justify-center gap-3">
            {[0, 1, 2, 3].map((idx) => (
              <span
                key={idx}
                className={`h-3.5 w-3.5 rounded-full border border-[#9a7858] ${idx < pin.length ? "bg-[#3a3028]" : "bg-transparent"}`}
              />
            ))}
          </div>
          <div className="grid grid-cols-3 gap-3">
            {"123456789".split("").map((digit) => (
              <NumberButton key={digit} label={digit} onClick={() => pushDigit(digit)} />
            ))}
            <button
              type="button"
              className="h-14 rounded-full text-[13px] font-semibold text-[#8a7662] active:bg-[#efe2cf]"
              onClick={() => setPin((prev) => prev.slice(0, -1))}
            >
              删除
            </button>
            <NumberButton label="0" onClick={() => pushDigit("0")} />
            <button
              type="button"
              className="h-14 rounded-full text-[13px] font-semibold text-[#8a7662] active:bg-[#efe2cf]"
              onClick={() => setPin("")}
            >
              清空
            </button>
          </div>
        </div>

        <div className="mt-5 flex items-center justify-between rounded-full bg-[#efe2cf]/65 px-4 py-3 text-[12px] font-semibold text-[#7d6247]">
          <span>{layer === "drawer" ? `${stats?.total || 0} 条记录` : "输入 PIN 后查看暗格"}</span>
          <button
            type="button"
            className="rounded-full bg-white/70 px-3 py-1.5 active:scale-95"
            onClick={() => onSwitchLayer(layer === "drawer" ? "alcove" : "drawer")}
          >
            {layer === "drawer" ? "去暗格" : "回抽屉"}
          </button>
        </div>
      </div>
    </div>
  );
}

function NumberButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      className="h-14 rounded-full bg-white/85 text-[24px] font-semibold text-[#352b24] shadow-[0_10px_20px_-18px_rgba(59,44,31,0.8)] active:scale-95 active:bg-[#f4eadb]"
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[20px] border border-[#ecdcc7] bg-[#fffaf1]/80 px-2 py-3 text-center shadow-[0_14px_30px_-28px_rgba(86,56,31,0.8)]">
      <div className="text-[18px] font-semibold leading-none text-[#3a3028]">{value}</div>
      <div className="mt-1 text-[10px] font-semibold text-[#a0866b]">{label}</div>
    </div>
  );
}

function PaperCard({ item, index, onClick }: { item: SecretDrawerItem; index: number; onClick: () => void }) {
  const rotate = ((index % 5) - 2) * 0.45;
  const type = TYPE_LABELS[item.type || "misc"] || "其他";
  const preview = String(item.content || item.why || "这张纸条还没写内容。").replace(/\s+/g, " ").slice(0, 110);
  return (
    <button
      type="button"
      className="relative w-full rounded-[6px] border border-[#e8d9c6] bg-[#fffdf6] px-5 py-4 text-left shadow-[0_18px_36px_-30px_rgba(67,43,25,0.95)] transition active:scale-[0.985]"
      style={{ transform: `rotate(${rotate}deg)` }}
      onClick={onClick}
    >
      <div className="absolute -top-2 left-8 h-4 w-14 rotate-[-2deg] rounded-sm bg-[#ead8bd]/80 shadow-sm" />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-[#f2e5d3] px-2.5 py-1 text-[10px] font-semibold text-[#86684a]">{type}</span>
            {item.pinned ? <span className="text-[11px] font-semibold text-[#b9803e]">置顶</span> : null}
            {item.sealed ? <span className="text-[11px] font-semibold text-[#7a5140]">暗格</span> : null}
          </div>
          <h3 className="mt-3 line-clamp-2 text-[17px] font-semibold leading-6 text-[#302722]">{item.title || TYPE_LABELS[item.type || "misc"] || "秘密纸条"}</h3>
        </div>
        <span className="shrink-0 text-[11px] font-semibold text-[#b09a82]">{formatShortTime(item.created_at)}</span>
      </div>
      <p className="mt-3 line-clamp-3 text-[13px] leading-6 text-[#6f5f50]">{preview}</p>
      {item.tags?.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {item.tags.slice(0, 4).map((tag) => (
            <span key={tag} className="rounded-full bg-[#f6eee4] px-2 py-1 text-[10px] font-semibold text-[#9a8064]">{tag}</span>
          ))}
        </div>
      ) : null}
    </button>
  );
}

function EmptyPaper({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-[6px] border border-dashed border-[#d9c4aa] bg-[#fffaf1]/72 px-6 py-10 text-center">
      <div className="text-[16px] font-semibold text-[#4a3b31]">{title}</div>
      <div className="mt-2 text-[13px] leading-5 text-[#927a63]">{text}</div>
    </div>
  );
}

function SecretDrawerDetail({ item, layer, onBack }: { item: SecretDrawerItem; layer: Layer; onBack: () => void }) {
  const media = item.media_refs || [];
  return (
    <div className="min-h-full bg-[#f8f0e6] px-5 pb-8 pt-5 text-[#352b24]">
      <button
        type="button"
        className="mb-5 rounded-full bg-[#fffaf1]/85 px-4 py-2 text-[13px] font-semibold text-[#735635] shadow-[0_10px_24px_-20px_rgba(84,55,27,0.7)] active:scale-95"
        onClick={onBack}
      >
        返回纸条堆
      </button>
      <article className="rounded-[8px] border border-[#e8d9c6] bg-[#fffdf6] px-5 py-6 shadow-[0_24px_52px_-38px_rgba(67,43,25,0.95)]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[#f2e5d3] px-2.5 py-1 text-[10px] font-semibold text-[#86684a]">{TYPE_LABELS[item.type || "misc"] || "其他"}</span>
          <span className="text-[11px] font-semibold text-[#b09a82]">{formatFullTime(item.created_at)}</span>
          {layer === "alcove" || item.sealed ? <span className="text-[11px] font-semibold text-[#7a5140]">暗格</span> : null}
        </div>
        <h2 className="mt-4 text-[24px] font-semibold leading-8 tracking-tight text-[#2f2722]">{item.title || "秘密纸条"}</h2>
        {item.why ? <p className="mt-3 rounded-[18px] bg-[#f6eee4] px-4 py-3 text-[13px] leading-6 text-[#745d47]">{item.why}</p> : null}
        {media.length ? (
          <div className="mt-5 grid grid-cols-1 gap-3">
            {media.map((ref, index) => (
              <figure key={`${ref.key || ref.url || index}`} className="rounded-[5px] bg-white p-2 shadow-[0_18px_32px_-28px_rgba(67,43,25,0.95)]">
                <img src={mediaUrl(ref)} alt={ref.name || "secret drawer media"} className="max-h-[420px] w-full rounded-[3px] object-cover" loading="lazy" />
              </figure>
            ))}
          </div>
        ) : null}
        {item.content ? <div className="mt-5 whitespace-pre-wrap text-[15px] leading-8 text-[#4b4037]">{item.content}</div> : null}
        {item.tags?.length ? (
          <div className="mt-6 flex flex-wrap gap-2">
            {item.tags.map((tag) => (
              <span key={tag} className="rounded-full bg-[#f2e5d3] px-3 py-1.5 text-[11px] font-semibold text-[#85684a]">{tag}</span>
            ))}
          </div>
        ) : null}
        {item.source?.channel || item.source?.url ? (
          <div className="mt-6 border-t border-[#eadcc9] pt-4 text-[11px] leading-5 text-[#a18a72]">
            {item.source?.channel ? <div>来源：{item.source.channel}</div> : null}
            {item.source?.url ? <div className="break-all">{item.source.url}</div> : null}
          </div>
        ) : null}
      </article>
    </div>
  );
}

function summarizeStats(stats: SecretDrawerStats | null): string {
  const total = stats?.total || 0;
  if (!total) return "这里还没有纸条。";
  const byType = stats?.by_type || {};
  return `共 ${total} 条，对话 ${byType.message || 0}，图片 ${byType.photo || 0}，梦境 ${byType.dream || 0}，碎碎念 ${byType.note || 0}。`;
}

function formatShortTime(value?: string): string {
  const text = String(value || "");
  const match = text.match(/(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})/);
  return match ? `${match[1]}/${match[2]} ${match[3]}:${match[4]}` : "";
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
