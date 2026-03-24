import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";
import { getInitData } from "../tg";

function stickerPreviewUrl(key: string, publicBase: string): string {
  const pb = (publicBase || "").trim().replace(/\/$/, "");
  if (pb) {
    return `${pb}/${String(key).replace(/^\//, "")}`;
  }
  const u = new URL("/miniapp-api/stickers/raw", window.location.origin);
  u.searchParams.set("key", key);
  const init = getInitData();
  if (init) u.searchParams.set("initData", init);
  return u.toString();
}

export function StickersTab() {
  const toast = useToast();
  const [tags, setTags] = useState<string[]>([]);
  const [activeTag, setActiveTag] = useState("");
  const [publicBase, setPublicBase] = useState("");
  const [mapping, setMapping] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const t = await apiJson<{ ok?: boolean; tags?: string[] }>("/miniapp-api/stickers/tags");
      if (t?.ok && Array.isArray(t.tags) && t.tags.length) {
        setTags(t.tags);
        setActiveTag((prev) => (prev && t.tags!.includes(prev) ? prev : t.tags![0]));
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
    const k = activeTag || tags[0] || "";
    const arr = mapping[k];
    return Array.isArray(arr) ? arr : [];
  }, [activeTag, mapping, tags]);

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

  return (
    <div className="space-y-3 pb-24">
      <div className="text-xs text-cream-muted leading-relaxed">
        渡在 Telegram 回复句末可加 <code className="text-cream-text">[shy]</code> 等标签，网关会随机发一张该分类下的图。未配置公网时预览走网关代理。
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t) => (
          <button
            key={t}
            type="button"
            className={
              "rounded-xl2 px-2.5 py-1 text-[11px] border transition " +
              (activeTag === t ? "bg-neutral-900 text-white border-neutral-900" : "bg-white/70 text-cream-text border-white/70")
            }
            onClick={() => setActiveTag(t)}
          >
            {t}
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
            <img src={stickerPreviewUrl(k, publicBase)} alt="" className="w-full h-full object-cover" loading="lazy" />
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
