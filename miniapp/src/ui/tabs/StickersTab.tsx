import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";
import { getInitData } from "../tg";

type TagRow = { key: string; label_zh: string };

/**
 * 表情包预览：公网 R2 直链可直接 <img>。
 * 走网关 /stickers/raw 时不能用「initData 塞满 URL」的 img src（Telegram WebView 常截断超长 URL），
 * 须用 fetch + X-Telegram-Init-Data 再 blob: URL。
 */
function StickerPreviewImg({ objectKey, publicBase }: { objectKey: string; publicBase: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    const pb = (publicBase || "").trim().replace(/\/$/, "");
    if (pb) {
      setSrc(`${pb}/${String(objectKey).replace(/^\//, "")}`);
      return;
    }

    setSrc(null);
    let cancelled = false;
    let objectUrl: string | null = null;

    (async () => {
      try {
        const headers = new Headers();
        const initData = getInitData();
        if (initData) headers.set("X-Telegram-Init-Data", initData);
        const q = new URLSearchParams({ key: objectKey });
        const r = await fetch(`${window.location.origin}/miniapp-api/stickers/raw?${q}`, { headers });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        objectUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setSrc(objectUrl);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [objectKey, publicBase]);

  if (failed) {
    return <div className="w-full h-full flex items-center justify-center text-[10px] text-cream-muted px-1 text-center">预览失败</div>;
  }
  if (!src) {
    return <div className="w-full h-full bg-white/30 animate-pulse" aria-hidden />;
  }
  return <img src={src} alt="" className="w-full h-full object-cover" loading="lazy" />;
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
      <div className="rounded-xl2 border border-white/70 bg-white/50 p-2 space-y-2">
        <div className="text-[11px] text-cream-muted">新增分类（网关目录与 [tag] 均为英文代号；下方可填中文仅作本页展示名）</div>
        <div className="flex flex-col gap-1.5">
          <input
            className="rounded-lg border border-white/80 bg-white px-2 py-1.5 text-xs"
            placeholder="英文代号，如 smug"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
          />
          <input
            className="rounded-lg border border-white/80 bg-white px-2 py-1.5 text-xs"
            placeholder="展示名（可选，如 得意）"
            value={newLabelZh}
            onChange={(e) => setNewLabelZh(e.target.value)}
          />
          <Btn kind="dark" onClick={addCategory} disabled={adding}>
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
              "rounded-xl2 px-2.5 py-1 text-[11px] border transition " +
              (activeTag === row.key ? "bg-neutral-900 text-white border-neutral-900" : "bg-white/70 text-cream-text border-white/70")
            }
            onClick={() => setActiveTag(row.key)}
            title={row.key}
          >
            {row.label_zh || row.key}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Btn kind="dark" onClick={load} disabled={loading}>
          {loading ? "刷新中..." : "刷新"}
        </Btn>
        <Btn kind="default" onClick={rebuild}>
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
          <div key={k} className="relative aspect-square rounded-xl2 overflow-hidden border border-white/70 bg-white/40 shadow-soft">
            <StickerPreviewImg objectKey={k} publicBase={publicBase} />
            <button
              type="button"
              className="absolute top-1 right-1 h-6 w-6 rounded-full bg-black/55 text-white text-xs leading-6"
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
        className="fixed bottom-24 right-5 z-30 h-12 w-12 rounded-full bg-neutral-900 text-white text-2xl leading-[48px] shadow-soft2 border border-white/20"
        disabled={uploading || !activeTag}
        onClick={() => fileRef.current?.click()}
        aria-label="上传"
      >
        {uploading ? "…" : "+"}
      </button>
    </div>
  );
}
