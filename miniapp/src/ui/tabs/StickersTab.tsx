import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson, fetchWithInitDataHeaderOnly } from "../api";
import { useToast } from "../toast";

type TagRow = { key: string; label_zh: string };

const surfaceCard =
  "rounded-[28px] border border-gray-100/80 bg-white shadow-[0_8px_30px_-18px_rgba(15,23,42,0.28)]";
const softButton =
  "rounded-[16px] border border-gray-100/80 bg-white px-3 py-2 text-[12px] font-medium text-gray-700 shadow-[0_4px_18px_-12px_rgba(15,23,42,0.35)] transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-45";
const darkButton =
  "rounded-[16px] bg-gray-900 px-3 py-2 text-[12px] font-medium text-white shadow-[0_8px_20px_-14px_rgba(15,23,42,0.5)] transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-45";
const fieldClass =
  "h-11 w-full rounded-[18px] border border-gray-100/90 bg-[#FAFAFA] px-3 text-[13px] text-gray-800 outline-none transition placeholder:text-gray-300 focus:border-gray-200 focus:bg-white";

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
      <div className="flex h-full w-full items-center justify-center bg-gray-50 px-2 text-center text-[11px] leading-tight text-gray-400" title={failed}>
        预览失败
      </div>
    );
  }
  if (!src) {
    return <div className="h-full w-full animate-pulse bg-gray-50" aria-hidden />;
  }

  return (
    <img
      src={src}
      alt=""
      className="h-full w-full object-contain p-2"
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
  const activeRow = tagRows.find((row) => row.key === (activeTag || tagRows[0]?.key || ""));
  const previewStatus = publicBase ? "公网直链预览" : "网关代理预览";

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
    <div
      className="min-h-full bg-[#FDFDFD] px-4 pb-28 pt-4 text-gray-900"
      style={{ fontFamily: "'Microsoft YaHei', sans-serif" }}
    >
      <div className="mx-auto flex w-full max-w-[620px] flex-col gap-4">
        <section className={`${surfaceCard} p-4`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[18px] font-medium leading-6 tracking-normal text-gray-900">表情包</div>
              <div className="mt-1 truncate text-[12px] leading-5 text-gray-400">
                {activeRow ? `${activeRow.label_zh || activeRow.key} · ${keysForTab.length} 张` : loading ? "加载中" : "暂无分类"}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button type="button" className={softButton} onClick={load} disabled={loading || uploading}>
                {loading ? "刷新中" : "刷新"}
              </button>
              <button type="button" className={softButton} onClick={rebuild} disabled={uploading}>
                重建映射
              </button>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between gap-3 border-t border-gray-50 pt-3">
            <span className="text-[12px] text-gray-400">{previewStatus}</span>
            {activeRow?.key ? (
              <span className="rounded-full bg-gray-50 px-2.5 py-1 text-[11px] font-medium text-gray-500">
                {activeRow.key}
              </span>
            ) : null}
          </div>
        </section>

        {tagRows.length ? (
          <div className="-mx-4 overflow-x-auto px-4">
            <div className="flex min-w-max gap-2 pb-1">
              {tagRows.map((row) => {
                const isActive = row.key === activeTag;
                return (
                  <button
                    key={row.key}
                    type="button"
                    className={[
                      "rounded-full border px-3.5 py-2 text-[12px] font-medium transition active:scale-[0.98]",
                      isActive
                        ? "border-gray-900 bg-gray-900 text-white shadow-[0_10px_22px_-18px_rgba(15,23,42,0.75)]"
                        : "border-gray-100/90 bg-white text-gray-500 shadow-[0_4px_18px_-14px_rgba(15,23,42,0.3)]",
                    ].join(" ")}
                    onClick={() => setActiveTag(row.key)}
                    title={row.key}
                  >
                    {row.label_zh || row.key}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        <section className={`${surfaceCard} p-4`}>
          <div className="mb-3 text-[13px] font-medium text-gray-800">新增分类</div>
          <div className="flex flex-col gap-2">
            <input
              className={fieldClass}
              placeholder="英文代号，如 smug"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value.toLowerCase())}
              inputMode="latin"
            />
            <input
              className={fieldClass}
              placeholder="展示名，如 得意"
              value={newLabelZh}
              onChange={(e) => setNewLabelZh(e.target.value)}
            />
            <button type="button" className={`${darkButton} h-11`} onClick={addCategory} disabled={adding}>
              {adding ? "添加中..." : "添加分类"}
            </button>
          </div>
        </section>

        {keysForTab.length ? (
          <div className="grid grid-cols-3 gap-2.5">
            {keysForTab.map((k) => (
              <div
                key={k}
                className="relative aspect-square overflow-hidden rounded-[24px] border border-gray-100/80 bg-white shadow-[0_4px_18px_-14px_rgba(15,23,42,0.24)]"
              >
                <StickerPreviewImg objectKey={k} publicBase={publicBase} />
                <button
                  type="button"
                  className="absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-full border border-white/80 bg-white/90 text-[15px] leading-none text-gray-400 shadow-[0_4px_12px_-8px_rgba(15,23,42,0.45)] backdrop-blur transition active:scale-95"
                  onClick={() => removeKey(k)}
                  aria-label="删除"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className={`${surfaceCard} flex min-h-32 items-center justify-center px-6 py-8 text-center text-[13px] text-gray-400`}>
            当前分类暂无图片
          </div>
        )}

        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={onPickFile} />
        <button
          type="button"
          className="fixed bottom-24 right-5 z-30 flex h-[52px] w-[52px] items-center justify-center rounded-full border border-gray-100 bg-white text-[28px] font-light leading-none text-gray-800 shadow-[0_16px_30px_-18px_rgba(15,23,42,0.55)] transition active:scale-95 disabled:opacity-45"
          disabled={uploading || !activeTag}
          onClick={() => fileRef.current?.click()}
          aria-label="上传"
        >
          {uploading ? "…" : "+"}
        </button>
      </div>
    </div>
  );
}
