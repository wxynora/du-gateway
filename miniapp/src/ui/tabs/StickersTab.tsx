import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson, fetchWithInitDataHeaderOnly } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type TagRow = { key: string; label_zh: string };

/**
 * 表情包预览：公网 R2 直链可直接 <img>。
 * 走网关 /stickers/raw：仅用 Header 传 initData（见 fetchWithInitDataHeaderOnly），再 blob:；部分 WebView 对 blob: 支持差，onError 时回退 data URL。
 */
function StickerPreviewImg({ objectKey, publicBase }: { objectKey: string; publicBase: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [dataUrlFallback, setDataUrlFallback] = useState(false);
  const [preferProxy, setPreferProxy] = useState(false);
  const blobRef = React.useRef<Blob | null>(null);
  const objectUrlRef = React.useRef<string | null>(null);

  useEffect(() => {
    setFailed(null);
    setDataUrlFallback(false);
    blobRef.current = null;
    const pb = (publicBase || "").trim().replace(/\/$/, "");
    if (pb && !preferProxy) {
      setSrc(`${pb}/${String(objectKey).replace(/^\//, "")}`);
      return;
    }

    setSrc(null);
    let cancelled = false;

    (async () => {
      try {
        const q = new URLSearchParams({ key: objectKey });
        const r = await fetchWithInitDataHeaderOnly(`/miniapp-api/stickers/raw?${q}`);
        if (!r.ok) {
          const errText = (await r.text().catch(() => "")) || "";
          throw new Error(`HTTP ${r.status} ${errText.slice(0, 80)}`);
        }
        const ct = (r.headers.get("Content-Type") || "").toLowerCase();
        const blob = await r.blob();
        if (!blob || blob.size === 0) throw new Error("空文件");
        if (ct.includes("json") || ct.includes("text/html")) throw new Error("非图片响应");
        blobRef.current = blob;
        const objectUrl = URL.createObjectURL(blob);
        objectUrlRef.current = objectUrl;
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          objectUrlRef.current = null;
          return;
        }
        setSrc(objectUrl);
      } catch (e: any) {
        if (!cancelled) setFailed(e?.message || "加载失败");
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      blobRef.current = null;
    };
  }, [objectKey, publicBase, preferProxy]);

  useEffect(() => {
    setPreferProxy(false);
  }, [objectKey, publicBase]);

  if (failed) {
    return (
      <div className="w-full h-full flex items-center justify-center text-[10px] text-cream-muted px-1 text-center leading-tight" title={failed}>
        预览失败
      </div>
    );
  }
  if (!src) {
    return <div className="w-full h-full bg-[linear-gradient(145deg,rgba(255,255,255,0.64),rgba(236,241,247,0.52))] animate-pulse" aria-hidden />;
  }

  return (
    <img
      src={src}
      alt=""
      className="w-full h-full object-cover"
      loading="lazy"
      onError={() => {
        const pb = (publicBase || "").trim().replace(/\/$/, "");
        if (pb && !preferProxy) {
          setSrc(null);
          setPreferProxy(true);
          return;
        }
        const b = blobRef.current;
        if (!b || dataUrlFallback) return;
        setDataUrlFallback(true);
        try {
          const reader = new FileReader();
          reader.onload = () => {
            const u = reader.result;
            if (typeof u === "string") setSrc(u);
          };
          reader.readAsDataURL(b);
        } catch {
          setFailed("图片无法显示");
        }
      }}
    />
  );
}

const TAG_KEY_RE = /^[a-z][a-z0-9_]{0,63}$/;

export function StickersTab() {
  const toast = useToast();
  const [tagRows, setTagRows] = useState<TagRow[]>([]);
  const [activeTag, setActiveTag] = useState("");
  const [publicBase, setPublicBase] = useState("");
  const [mapping, setMapping] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newLabelZh, setNewLabelZh] = useState("");
  const [adding, setAdding] = useState(false);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const t = await apiJson<{ ok?: boolean; tags?: unknown }>("/miniapp-api/stickers/tags");
      if (t?.ok && Array.isArray(t.tags) && t.tags.length) {
        const rows: TagRow[] = [];
        for (const x of t.tags) {
          if (typeof x === "string") {
            rows.push({ key: x.trim().toLowerCase(), label_zh: x });
          } else if (x && typeof x === "object" && "key" in (x as object)) {
            const o = x as { key?: string; label_zh?: string };
            const k = String(o.key || "").trim().toLowerCase();
            if (!k) continue;
            rows.push({ key: k, label_zh: String(o.label_zh || k).trim() || k });
          }
        }
        if (rows.length) {
          setTagRows(rows);
          setActiveTag((prev) => (prev && rows.some((r) => r.key === prev) ? prev : rows[0].key));
        }
      }
      const m = await apiJson<{ ok?: boolean; mapping?: Record<string, unknown>; public_base?: string }>("/miniapp-api/stickers/mapping");
      if (m?.ok && m.mapping && typeof m.mapping === "object") {
        const out: Record<string, string[]> = {};
        for (const [k, v] of Object.entries(m.mapping)) {
          if (k === "updated_at") continue;
          if (Array.isArray(v)) out[k] = v.filter((x) => typeof x === "string") as string[];
        }
        setMapping(out);
      }
      if (typeof m?.public_base === "string") setPublicBase(m.public_base);
    } catch (e: any) {
      toast(`加载表情包失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const keysForTab = useMemo(() => {
    const k = activeTag || tagRows[0]?.key || "";
    const arr = mapping[k];
    return Array.isArray(arr) ? arr : [];
  }, [activeTag, mapping, tagRows]);

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !activeTag) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("tag", activeTag);
      fd.append("file", f);
      const r = await apiFetch("/miniapp-api/stickers/upload", { method: "POST", body: fd });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j?.ok) throw new Error(j?.error || `HTTP ${r.status}`);
      toast("已上传");
      await load();
    } catch (err: any) {
      toast(`上传失败：${err?.message || err}`);
    } finally {
      setUploading(false);
    }
  }

  async function removeKey(key: string) {
    if (!key) return;
    if (!window.confirm("删除这张图？")) return;
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/stickers/item", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除");
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  async function rebuild() {
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/stickers/rebuild", { method: "POST" });
      if (!j?.ok) throw new Error(j?.error || "重建失败");
      toast("映射已重建");
      await load();
    } catch (e: any) {
      toast(`重建失败：${e?.message || e}`);
    }
  }

  async function addCategory() {
    const key = newKey.trim().toLowerCase();
    if (!key) {
      toast("请填写英文代号");
      return;
    }
    if (!TAG_KEY_RE.test(key)) {
      toast("代号须为小写英文：字母开头，仅 a-z、0-9、下划线，最长 64");
      return;
    }
    setAdding(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/stickers/category", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, label_zh: newLabelZh.trim() }),
      });
      if (!j?.ok) throw new Error(j?.error || "添加失败");
      toast("已添加分类");
      setNewKey("");
      setNewLabelZh("");
      await load();
      setActiveTag(key);
    } catch (e: any) {
      toast(`添加失败：${e?.message || e}`);
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-3 pb-24">
      <div className="text-xs text-cream-muted leading-relaxed">
        渡在 Telegram 回复句末可加 <code className="text-cream-text">[shy]</code> 等<strong>英文</strong>标签，网关会随机发一张该分类下的图。未配置公网时预览走网关代理。
      </div>
      <div className="neo-panel p-3 space-y-2">
        <div className="text-[11px] text-cream-muted">新增分类（网关目录与 [tag] 均为英文代号；下方可填中文仅作本页展示名）</div>
        <div className="flex flex-col gap-1.5">
          <input
            className="neo-input text-xs"
            placeholder="英文代号，如 smug"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
          />
          <input
            className="neo-input text-xs"
            placeholder="展示名（可选，如 得意）"
            value={newLabelZh}
            onChange={(e) => setNewLabelZh(e.target.value)}
          />
          <Btn kind="pink" onClick={addCategory} disabled={adding}>
            {adding ? "添加中…" : "添加分类"}
          </Btn>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tagRows.map((row) => (
          <button
            key={row.key}
            type="button"
            className={
              "neo-segment px-2.5 py-1 text-[11px] " +
              (activeTag === row.key ? "neo-segment-active" : "")
            }
            onClick={() => setActiveTag(row.key)}
            title={row.key}
          >
            {row.label_zh || row.key}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Btn kind="blue" onClick={load} disabled={loading}>
          {loading ? "刷新中..." : "刷新"}
        </Btn>
        <Btn kind="yellow" onClick={rebuild}>
          重建映射
        </Btn>
      </div>
      {publicBase ? (
        <div className="text-[11px] text-cream-muted">公网预览基址：{publicBase}</div>
      ) : (
        <div className="text-[11px] text-cream-muted">未配置 R2_PUBLIC_URL，预览使用网关 /stickers/raw</div>
      )}

      <div className="grid grid-cols-3 gap-2">
        {keysForTab.map((k) => (
          <div key={k} className="relative aspect-square overflow-hidden neo-panel-soft">
            <StickerPreviewImg objectKey={k} publicBase={publicBase} />
            <button
              type="button"
              className="absolute top-1 right-1 neo-icon-btn h-6 w-6 text-xs leading-6"
              onClick={() => removeKey(k)}
              aria-label="删除"
            >
              ×
            </button>
          </div>
        ))}
      </div>
      {!keysForTab.length && !loading ? (
        <div className="text-xs text-cream-muted">当前分类暂无图片，点右下角 + 上传。</div>
      ) : null}

      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={onPickFile} />
      <button
        type="button"
        className="fixed bottom-24 right-5 z-30 h-12 w-12 rounded-full border border-white/85 text-[28px] leading-[46px] text-cream-text shadow-soft2 bg-[linear-gradient(145deg,rgba(255,248,251,0.96),rgba(236,206,221,0.82))]"
        disabled={uploading || !activeTag}
        onClick={() => fileRef.current?.click()}
        aria-label="上传"
      >
        {uploading ? "…" : "+"}
      </button>
    </div>
  );
}
