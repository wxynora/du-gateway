import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type DuPageItem = {
  id: string;
  title?: string;
  emoji?: string;
  description?: string;
  html?: string;
  tags?: string[];
  url?: string;
  created_at?: string;
  updated_at?: string;
};

type ViewState = "list" | "detail" | "edit" | "preview";

function pageTime(item: DuPageItem): number {
  const raw = item.updated_at || item.created_at || "";
  const n = raw ? new Date(raw).getTime() : 0;
  return Number.isFinite(n) ? n : 0;
}

function sortPages(items: DuPageItem[]) {
  return items.slice().sort((a, b) => pageTime(b) - pageTime(a));
}

function normalizePages(input: unknown): DuPageItem[] {
  if (!Array.isArray(input)) return [];
  return input
    .filter((item): item is DuPageItem => !!item && typeof item === "object" && typeof (item as DuPageItem).id === "string")
    .map((item) => ({
      ...item,
      tags: Array.isArray(item.tags) ? item.tags.map((tag) => String(tag || "").trim()).filter(Boolean) : [],
    }));
}

function text(value: unknown): string {
  return String(value || "").trim();
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildSimpleHtml(title: string, body: string): string {
  const safeTitle = escapeHtml(title || "页笺");
  const safeBody = escapeHtml(body || "").replace(/\n/g, "<br>");
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${safeTitle}</title>
  <style>
    body{margin:0;min-height:100vh;background:#FAF7F0;color:#2D2926;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.7;padding:32px}
    main{max-width:680px;margin:0 auto;background:white;padding:32px;box-shadow:0 10px 40px rgba(0,0,0,.08)}
    h1{font-family:Georgia,"Times New Roman",serif;font-size:32px;margin:0 0 20px}
    p{white-space:pre-wrap}
  </style>
</head>
<body><main><h1>${safeTitle}</h1><p>${safeBody}</p></main></body>
</html>`;
}

function cardTransform(item: DuPageItem, index: number) {
  const seed = Array.from(String(item.id || index)).reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  const rot = ((seed * 13) % 8 - 4) / 2;
  return `rotate(${rot}deg)`;
}

function Ladybug({ index }: { index: number }) {
  const positions = [
    { top: "16.1972%", left: "46.766%" },
    { top: "68.583%", left: "15.0092%" },
    { top: "10.46%", left: "7.20462%" },
  ];
  const pos = positions[index % positions.length] || positions[0];
  return (
    <div className="ladybug" style={pos}>
      <svg viewBox="0 0 24 24" fill="var(--red)">
        <circle cx="12" cy="12" r="8" />
        <circle cx="12" cy="8" r="2" fill="black" />
        <circle cx="9" cy="12" r="1" fill="black" />
        <circle cx="15" cy="12" r="1" fill="black" />
        <circle cx="12" cy="16" r="1" fill="black" />
      </svg>
    </div>
  );
}

function ChevronLeftSmall() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function PlusSmall() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

export function DuPagesTab({
  onExit,
  backHandlerRef,
}: {
  onExit?: () => void;
  backHandlerRef?: React.MutableRefObject<(() => boolean) | null>;
}) {
  const toast = useToast();
  const [view, setView] = useState<ViewState>("list");
  const [pages, setPages] = useState<DuPageItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");

  const sourcePages = useMemo(() => pages, [pages]);

  const selected = useMemo(
    () => sourcePages.find((item) => item.id === selectedId) || null,
    [selectedId, sourcePages],
  );

  const visiblePages = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? sourcePages.filter((item) => {
          const haystack = [
            item.title,
            item.description,
            ...(Array.isArray(item.tags) ? item.tags : []),
          ]
            .map((part) => String(part || "").toLowerCase())
            .join("\n");
          return haystack.includes(q);
        })
      : sourcePages;
    return sortPages(list);
  }, [query, sourcePages]);

  const displayPages = visiblePages;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiJson<{ ok?: boolean; pages?: DuPageItem[]; error?: string }>("/miniapp-api/du-pages?limit=160");
      if (!res?.ok) throw new Error(res?.error || "加载失败");
      setPages(sortPages(normalizePages(res.pages)));
    } catch (e: any) {
      console.warn("du pages preview fallback:", e?.message || e);
      toast(`页笺加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleBack = useCallback(() => {
    if (view === "preview") {
      setView("detail");
      return true;
    }
    if (view === "edit") {
      if (selectedId) setView("detail");
      else setView("list");
      return true;
    }
    if (view === "detail") {
      setView("list");
      return true;
    }
    return false;
  }, [selectedId, view]);

  useEffect(() => {
    if (!backHandlerRef) return;
    backHandlerRef.current = handleBack;
    return () => {
      if (backHandlerRef.current === handleBack) backHandlerRef.current = null;
    };
  }, [backHandlerRef, handleBack]);

  function showList() {
    setView("list");
    setSelectedId("");
    setDraftTitle("");
    setDraftTags("");
    setDraftDescription("");
    setPreviewHtml("");
    setPreviewUrl("");
  }

  async function openDetail(id: string) {
    setSelectedId(id);
    setView("detail");
    try {
      const res = await apiJson<{ ok?: boolean; item?: DuPageItem; error?: string }>(`/miniapp-api/du-pages/${encodeURIComponent(id)}?include_html=1`);
      const item = res?.item;
      if (res?.ok && item?.id) {
        setPages((prev) => {
          const next = normalizePages(prev);
          const idx = next.findIndex((existing) => existing.id === item.id);
          if (idx >= 0) next[idx] = { ...next[idx], ...item };
          else next.unshift(item);
          return sortPages(next);
        });
      }
    } catch {}
  }

  function beginCreate() {
    setSelectedId("");
    setDraftTitle("");
    setDraftTags("");
    setDraftDescription("");
    setView("edit");
  }

  function beginEdit() {
    if (!selected) return;
    setDraftTitle(text(selected.title));
    setDraftTags((selected.tags || []).join(", "));
    setDraftDescription(text(selected.description));
    setView("edit");
  }

  async function saveNote() {
    const title = draftTitle.trim();
    const description = draftDescription.trim();
    const tags = draftTags.split(",").map((tag) => tag.trim()).filter(Boolean);
    if (!title) {
      toast("Please add a title");
      return;
    }
    setSaving(true);
    try {
      const body = selectedId
        ? { title, description, tags }
        : { title, description, tags, html: buildSimpleHtml(title, description), source: "miniapp", created_by: "xy" };
      const res = await apiJson<{ ok?: boolean; item?: DuPageItem; error?: string }>(
        selectedId ? `/miniapp-api/du-pages/${encodeURIComponent(selectedId)}` : "/miniapp-api/du-pages",
        {
          method: selectedId ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (!res?.ok || !res.item) throw new Error(res?.error || "保存失败");
      const item = res.item;
      setPages((prev) => {
        const next = normalizePages(prev);
        const idx = next.findIndex((existing) => existing.id === item.id);
        if (idx >= 0) next[idx] = { ...next[idx], ...item };
        else next.unshift(item);
        return sortPages(next);
      });
      setSelectedId(item.id);
      setView("detail");
      toast("页笺已保存");
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function deleteCurrent() {
    if (!selected) return;
    if (!window.confirm("Delete this page note?")) return;
    setSaving(true);
    try {
      const res = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/du-pages/${encodeURIComponent(selected.id)}`, {
        method: "DELETE",
      });
      if (!res?.ok) throw new Error(res?.error || "删除失败");
      setPages((prev) => prev.filter((item) => item.id !== selected.id));
      showList();
      toast("页笺已删除");
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  function openPage() {
    if (!selected) return;
    if (selected.url) {
      setPreviewUrl(selected.url);
      setPreviewHtml("");
      setView("preview");
      return;
    }
    const html = text(selected.html) || buildSimpleHtml(text(selected.title) || "页笺", text(selected.description));
    if (html) {
      setPreviewHtml(html);
      setPreviewUrl("");
      setView("preview");
      return;
    }
    {
      toast("这张页笺还没有打开地址");
      return;
    }
  }

  const pageForDetail = selected;

  return (
    <div className="du-pages-shell">
      <style>{`
        .du-pages-shell {
          --paper-bg: #FAF7F0;
          --graph-line: #E8E2D2;
          --ink: #2D2926;
          --red: #D23636;
          --green: #8BA341;
          --blue: #4A6D8C;
          --shadow: rgba(0,0,0,0.08);
          --gloss: linear-gradient(180deg, rgba(255,255,255,0.8) 0%, rgba(255,255,255,0) 50%, rgba(0,0,0,0.05) 100%);
          position: absolute;
          inset: 0;
          z-index: 30;
          overflow-x: hidden;
          overflow-y: auto;
          background-color: var(--paper-bg);
          background-image:
            linear-gradient(var(--graph-line) 1px, transparent 1px),
            linear-gradient(90deg, var(--graph-line) 1px, transparent 1px);
          background-size: 20px 20px;
          color: var(--ink);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          -webkit-tap-highlight-color: transparent;
        }
        .du-pages-shell * { box-sizing: border-box; }
        .du-pages-app-container {
          max-width: 500px;
          margin: 0 auto;
          min-height: 100%;
          position: relative;
          padding-bottom: 100px;
        }
        .du-pages-header {
          padding: calc(env(safe-area-inset-top, 0px) + 40px) 20px 20px;
          text-align: center;
          position: relative;
        }
        .du-pages-exit {
          position: absolute;
          left: 20px;
          top: calc(env(safe-area-inset-top, 0px) + 36px);
        }
        .du-pages-logo {
          font-family: 'Playfair Display', Georgia, serif;
          font-size: 32px;
          font-style: italic;
          color: var(--red);
          letter-spacing: -1px;
          position: relative;
          display: inline-block;
        }
        .du-pages-logo::after {
          content: '';
          position: absolute;
          bottom: -5px;
          left: 0;
          width: 100%;
          height: 8px;
          background: rgba(139, 163, 65, 0.2);
          z-index: -1;
        }
        .du-pages-search-tray {
          padding: 0 20px;
          margin-bottom: 30px;
        }
        .du-pages-search-input-wrapper {
          background: white;
          border: 1px solid #DCD5C5;
          padding: 8px 15px;
          border-radius: 4px;
          box-shadow: inset 0 2px 4px var(--shadow);
          display: flex;
          align-items: center;
        }
        .du-pages-search-input {
          border: none;
          background: transparent;
          width: 100%;
          font-family: 'Courier New', Courier, monospace;
          font-size: 14px;
          outline: none;
          color: var(--ink);
        }
        .du-pages-view {
          padding: 20px;
          animation: duPagesFadeIn 0.4s ease;
        }
        @keyframes duPagesFadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .du-pages-list-view { padding: 0; }
        .du-pages-collage-list {
          position: relative;
          padding: 20px;
          min-height: 400px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 10px;
        }
        .du-pages-note-card {
          position: relative;
          background: white;
          padding: 16px 18px;
          box-shadow: 2px 5px 15px var(--shadow);
          width: min(82vw, 340px);
          min-height: 96px;
          transition: transform 0.3s ease, z-index 0.3s ease;
          cursor: pointer;
          word-wrap: break-word;
          border: 0;
          color: inherit;
          text-align: left;
          display: block;
        }
        .du-pages-note-card:nth-child(odd) { background-color: #FFF9E5; }
        .du-pages-note-card:nth-child(3n) { background-color: #F6E4E4; width: min(84vw, 352px); }
        .du-pages-note-card:nth-child(4n) { background-color: #E7F0DC; }
        .du-pages-note-card .tape {
          position: absolute;
          top: -10px;
          left: 50%;
          transform: translateX(-50%) rotate(-2deg);
          width: 60px;
          height: 20px;
          background: rgba(255, 255, 255, 0.4);
          backdrop-filter: blur(1px);
          border: 1px solid rgba(0,0,0,0.05);
          z-index: 2;
        }
        .du-pages-note-card h3 {
          font-size: 14px;
          margin: 0 0 8px;
          line-height: 1.2;
          font-family: 'Playfair Display', Georgia, serif;
        }
        .du-pages-note-card p {
          font-size: 11px;
          color: #666;
          line-height: 1.4;
          font-family: 'Courier New', monospace;
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
          margin: 0;
        }
        .du-pages-tag-pill {
          display: inline-block;
          font-size: 9px;
          text-transform: uppercase;
          padding: 2px 6px;
          border: 0.5px solid currentColor;
          margin-top: 10px;
          letter-spacing: 1px;
        }
        .du-pages-floating-action {
          position: fixed;
          bottom: 30px;
          left: 50%;
          transform: translateX(-50%);
          display: flex;
          gap: 10px;
          z-index: 100;
        }
        .du-pages-btn-capsule {
          background: #fff;
          border-radius: 50px;
          padding: 10px 20px;
          border: 1px solid #ddd;
          box-shadow: 0 4px 10px rgba(0,0,0,0.1), inset 0 2px 2px white;
          font-size: 13px;
          font-weight: 600;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          background-image: var(--gloss);
          cursor: pointer;
          color: var(--ink);
          white-space: nowrap;
        }
        .du-pages-btn-capsule:active {
          transform: translateY(2px);
          box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .du-pages-btn-icon-round {
          width: 32px;
          height: 32px;
          background: #fff;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          border: 1px solid #ddd;
          box-shadow: 0 4px 10px rgba(0,0,0,0.1), inset 0 2px 2px white;
          background-image: var(--gloss);
          color: var(--ink);
        }
        .du-pages-detail-back { margin-bottom: 30px; }
        .du-pages-preview-view {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          background: #FAF7F0;
        }
        .du-pages-preview-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: calc(env(safe-area-inset-top, 0px) + 14px) 16px 12px;
          border-bottom: 1px solid rgba(45,41,38,0.08);
          background: rgba(250,247,240,0.92);
          backdrop-filter: blur(10px);
          z-index: 2;
        }
        .du-pages-preview-title {
          min-width: 0;
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-family: 'Playfair Display', Georgia, serif;
          font-size: 17px;
          font-weight: 700;
        }
        .du-pages-preview-frame {
          width: 100%;
          min-height: 0;
          flex: 1;
          border: 0;
          background: white;
        }
        .du-pages-detail-sheet {
          background: white;
          padding: 40px 30px;
          box-shadow: 0 10px 40px rgba(0,0,0,0.1);
          min-height: 60vh;
          position: relative;
        }
        .du-pages-detail-sheet::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 10px;
          background-image: radial-gradient(circle at 10px 10px, transparent 10px, white 10px);
          background-size: 20px 20px;
          transform: translateY(-10px);
        }
        .du-pages-detail-title {
          font-family: 'Playfair Display', Georgia, serif;
          font-size: 28px;
          margin: 0 0 20px;
          border-bottom: 1px solid #eee;
          padding-bottom: 10px;
          line-height: 1.16;
        }
        .du-pages-detail-content {
          font-family: 'Courier New', monospace;
          line-height: 1.6;
          color: #444;
          white-space: pre-wrap;
        }
        .du-pages-form-field { margin-bottom: 25px; }
        .du-pages-form-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 2px;
          color: #999;
          margin-bottom: 8px;
          display: block;
        }
        .du-pages-form-input,
        .du-pages-form-textarea {
          width: 100%;
          border: none;
          border-bottom: 1px dashed #ccc;
          background: transparent;
          padding: 10px 0;
          font-family: inherit;
          font-size: 16px;
          outline: none;
          color: var(--ink);
        }
        .du-pages-form-textarea {
          min-height: 150px;
          resize: none;
        }
        .ladybug {
          position: absolute;
          width: 24px;
          height: 24px;
          pointer-events: none;
          z-index: 50;
        }
        .du-pages-empty-state {
          text-align: center;
          padding: 100px 20px;
          color: #BDB7AB;
        }
        .du-pages-empty-icon {
          font-size: 40px;
          margin-bottom: 20px;
          filter: grayscale(1);
          opacity: 0.5;
        }
        .du-pages-muted {
          margin-top: 10px;
        }
      `}</style>
      <div className="du-pages-app-container">
        {view === "list" ? (
          <div className="du-pages-view du-pages-list-view">
            <header className="du-pages-header">
              <button className="du-pages-btn-icon-round du-pages-exit" onClick={onExit} aria-label="返回">
                <ChevronLeftSmall />
              </button>
              <div className="du-pages-logo">页笺</div>
            </header>

            <div className="du-pages-search-tray">
              <div className="du-pages-search-input-wrapper">
                <input
                  type="text"
                  className="du-pages-search-input"
                  placeholder="SEARCH NOTES..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            </div>

            <div className="du-pages-collage-list">
              {loading && !displayPages.length ? (
                <div className="du-pages-empty-state">
                  <div className="du-pages-empty-icon">🍂</div>
                  <h2>页笺加载中</h2>
                  <p className="du-pages-muted">The drawer is waking up.</p>
                </div>
              ) : displayPages.length ? (
                <>
                  {displayPages.map((item, index) => (
                    <button
                      key={item.id}
                      type="button"
                      className="du-pages-note-card"
                      style={{ transform: cardTransform(item, index), zIndex: index }}
                      onClick={() => void openDetail(item.id)}
                    >
                      <div className="tape" />
                      <h3>{text(item.title) || "Untitled Page"}</h3>
                      <p>{text(item.description) || "No description yet."}</p>
                      {(item.tags || []).map((tag) => (
                        <span key={tag} className="du-pages-tag-pill">{tag}</span>
                      ))}
                    </button>
                  ))}
                  <Ladybug index={0} />
                  <Ladybug index={1} />
                  <Ladybug index={2} />
                </>
              ) : (
                <div className="du-pages-empty-state">
                  <div className="du-pages-empty-icon">🍂</div>
                  <h2>这里还没有页笺</h2>
                  <p className="du-pages-muted">Tap "New Note" to start your collection.</p>
                </div>
              )}
            </div>

            <div className="du-pages-floating-action">
              <button className="du-pages-btn-capsule" onClick={beginCreate}>
                <PlusSmall />
                NEW NOTE
              </button>
            </div>
          </div>
        ) : null}

        {view === "detail" && pageForDetail ? (
          <div className="du-pages-view">
            <div className="du-pages-detail-back">
              <button className="du-pages-btn-icon-round" onClick={showList} aria-label="返回列表">
                <ChevronLeftSmall />
              </button>
            </div>
            <div className="du-pages-detail-sheet">
              <h1 className="du-pages-detail-title">
                {text(pageForDetail.emoji) ? `${text(pageForDetail.emoji)} ` : ""}
                {text(pageForDetail.title) || "Untitled Page"}
              </h1>
              <div style={{ marginBottom: 20 }}>
                {(pageForDetail.tags || []).map((tag) => (
                  <span key={tag} className="du-pages-tag-pill">{tag}</span>
                ))}
              </div>
              <div className="du-pages-detail-content">
                {text(pageForDetail.description) || "No description yet."}
              </div>
            </div>
            <div className="du-pages-floating-action">
              <button className="du-pages-btn-capsule" onClick={openPage}>OPEN</button>
              <button className="du-pages-btn-capsule" onClick={beginEdit}>EDIT</button>
              <button className="du-pages-btn-capsule" style={{ color: "var(--red)" }} disabled={saving} onClick={() => void deleteCurrent()}>DELETE</button>
            </div>
          </div>
        ) : null}

        {view === "edit" ? (
          <div className="du-pages-view">
            <div className="du-pages-detail-sheet" style={{ paddingTop: 20 }}>
              <div className="du-pages-form-field">
                <label className="du-pages-form-label">TITLE</label>
                <input
                  type="text"
                  className="du-pages-form-input"
                  placeholder="What's on your mind?"
                  value={draftTitle}
                  onChange={(e) => setDraftTitle(e.target.value)}
                />
              </div>
              <div className="du-pages-form-field">
                <label className="du-pages-form-label">TAGS (COMMA SEPARATED)</label>
                <input
                  type="text"
                  className="du-pages-form-input"
                  placeholder="design, thoughts, links"
                  value={draftTags}
                  onChange={(e) => setDraftTags(e.target.value)}
                />
              </div>
              <div className="du-pages-form-field">
                <label className="du-pages-form-label">DESCRIPTION</label>
                <textarea
                  className="du-pages-form-textarea"
                  placeholder="Paste link or write note here..."
                  value={draftDescription}
                  onChange={(e) => setDraftDescription(e.target.value)}
                />
              </div>
            </div>
            <div className="du-pages-floating-action">
              <button className="du-pages-btn-capsule" disabled={saving} onClick={() => void saveNote()}>
                {saving ? "SAVING..." : "SAVE NOTE"}
              </button>
              <button className="du-pages-btn-capsule" onClick={selectedId ? () => setView("detail") : showList}>CANCEL</button>
            </div>
          </div>
        ) : null}

        {view === "preview" && pageForDetail ? (
          <div className="du-pages-preview-view">
            <div className="du-pages-preview-header">
              <button className="du-pages-btn-icon-round" onClick={() => setView("detail")} aria-label="返回页笺">
                <ChevronLeftSmall />
              </button>
              <div className="du-pages-preview-title">
                {text(pageForDetail.emoji) ? `${text(pageForDetail.emoji)} ` : ""}
                {text(pageForDetail.title) || "Untitled Page"}
              </div>
            </div>
            <iframe
              className="du-pages-preview-frame"
              title={text(pageForDetail.title) || "页笺预览"}
              src={previewUrl || undefined}
              srcDoc={previewUrl ? undefined : previewHtml}
              sandbox="allow-scripts allow-forms allow-popups allow-modals"
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
