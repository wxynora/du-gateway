import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { ChevronLeftIcon } from "../icons";

type Author = "du" | "xy";

type DiaryComment = {
  id: string;
  author: Author;
  content: string;
  createdAt: string;
  replyToCommentId: string;
};

type DiaryEntry = {
  id: string;
  author: Author;
  title: string;
  createdAt: string;
  updatedAt: string;
  emoji: string;
  content: string;
  comments: DiaryComment[];
};

type EditorDraft = {
  id?: string;
  author: Author;
  title: string;
  emoji: string;
  content: string;
};

type BackHandler = () => boolean;

type ApiDiaryComment = {
  id?: string;
  author?: string;
  content?: string;
  reply_to_comment_id?: string;
  replyToCommentId?: string;
  created_at?: string;
  createdAt?: string;
};

type ApiDiaryEntry = {
  id?: string;
  author?: string;
  title?: string;
  created_at?: string;
  createdAt?: string;
  updated_at?: string;
  updatedAt?: string;
  mood?: string;
  emoji?: string;
  content?: string;
  comments?: ApiDiaryComment[];
};

type ListResp = { ok?: boolean; items?: ApiDiaryEntry[]; next_cursor?: string; nextCursor?: string; error?: string };
type ItemResp = { ok?: boolean; item?: ApiDiaryEntry; error?: string; server_item?: ApiDiaryEntry };

const EXCHANGE_DIARY_API = "/miniapp-api/exchange-diary";
const LIST_PAGE_SIZE = 20;

function makeId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeAuthor(value: unknown): Author {
  return String(value || "").toLowerCase() === "du" ? "du" : "xy";
}

function formatDateTime(value: unknown): string {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const d = new Date(raw);
  if (!Number.isNaN(d.getTime())) {
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).replace(/\//g, ".");
  }
  return raw.replace("T", " ").replace("+08:00", "").slice(0, 16).replace(/-/g, ".");
}

function fromApiComment(raw: ApiDiaryComment): DiaryComment {
  const created = raw.created_at || raw.createdAt || "";
  return {
    id: String(raw.id || makeId("comment")),
    author: normalizeAuthor(raw.author),
    content: String(raw.content || ""),
    createdAt: formatDateTime(created).slice(-5) || String(created || ""),
    replyToCommentId: String(raw.reply_to_comment_id || raw.replyToCommentId || ""),
  };
}

function fromApiEntry(raw: ApiDiaryEntry): DiaryEntry {
  const created = raw.created_at || raw.createdAt || "";
  const updated = raw.updated_at || raw.updatedAt || created;
  return {
    id: String(raw.id || makeId("diary")),
    author: normalizeAuthor(raw.author),
    title: String(raw.title || "没有标题的小纸条"),
    createdAt: formatDateTime(created),
    updatedAt: String(updated || ""),
    emoji: String(raw.emoji || raw.mood || "✦").slice(0, 4) || "✦",
    content: String(raw.content || ""),
    comments: Array.isArray(raw.comments) ? raw.comments.map(fromApiComment) : [],
  };
}

function authorLabel(author: Author): string {
  return author === "du" ? "渡" : "我";
}

function commentPrefix(comment: DiaryComment, comments: DiaryComment[]): string {
  const from = authorLabel(comment.author);
  if (!comment.replyToCommentId) return from;
  const parent = comments.find((item) => item.id === comment.replyToCommentId);
  return parent ? `${from} 回复 ${authorLabel(parent.author)}` : `${from} 回复`;
}

function emptyDraft(author: Author): EditorDraft {
  return { author, title: "", emoji: "✦", content: "" };
}

export function ExchangeDiaryTab({
  onBack,
  backHandlerRef,
}: {
  onBack: () => void;
  backHandlerRef?: React.MutableRefObject<BackHandler | null>;
}) {
  const [activeAuthor, setActiveAuthor] = useState<Author>("du");
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditorDraft | null>(null);
  const [commentDraft, setCommentDraft] = useState("");
  const [commentRequestId, setCommentRequestId] = useState("");
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [loadMoreError, setLoadMoreError] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const listRequestSeqRef = useRef(0);
  const detailRequestSeqRef = useRef(0);

  const visibleEntries = entries;
  const selected = useMemo(
    () => entries.find((entry) => entry.id === selectedId) || null,
    [entries, selectedId],
  );

  async function loadEntries(author: Author = activeAuthor, cursor = "") {
    const seq = listRequestSeqRef.current + 1;
    listRequestSeqRef.current = seq;
    const isLoadMore = Boolean(cursor);
    if (isLoadMore) {
      setLoadingMore(true);
      setLoadMoreError("");
    } else {
      setLoading(true);
      setNextCursor("");
      setLoadMoreError("");
    }
    if (!isLoadMore) setError("");
    try {
      const params = new URLSearchParams({ author, limit: String(LIST_PAGE_SIZE) });
      if (cursor) params.set("cursor", cursor);
      const data = await apiJson<ListResp>(`${EXCHANGE_DIARY_API}?${params.toString()}`);
      if (seq !== listRequestSeqRef.current) return;
      const next = (data.items || []).map(fromApiEntry);
      setNextCursor(String(data.next_cursor || data.nextCursor || ""));
      if (isLoadMore) {
        setEntries((prev) => {
          const seen = new Set(prev.map((entry) => entry.id));
          return [...prev, ...next.filter((entry) => !seen.has(entry.id))];
        });
      } else {
        setEntries(next);
      }
    } catch (err) {
      if (seq !== listRequestSeqRef.current) return;
      const message = err instanceof Error ? err.message : String(err);
      if (isLoadMore) {
        setLoadMoreError(message);
      } else {
        setError(message);
      }
      if (!isLoadMore) setEntries([]);
    } finally {
      if (seq === listRequestSeqRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }

  async function openEntry(id: string) {
    const seq = detailRequestSeqRef.current + 1;
    detailRequestSeqRef.current = seq;
    setSelectedId(id);
    setCommentDraft("");
    setCommentRequestId("");
    setDetailLoading(true);
    setDetailError("");
    try {
      const data = await apiJson<ItemResp>(`${EXCHANGE_DIARY_API}/${encodeURIComponent(id)}`);
      if (seq !== detailRequestSeqRef.current) return;
      const item = data.item ? fromApiEntry(data.item) : null;
      if (item) {
        setEntries((prev) => prev.map((entry) => (entry.id === item.id ? item : entry)));
      }
    } catch (err) {
      if (seq !== detailRequestSeqRef.current) return;
      setDetailError(err instanceof Error ? err.message : String(err));
      if (err && typeof err === "object" && "status" in err && (err as { status?: number }).status === 404) {
        setEntries((prev) => prev.filter((entry) => entry.id !== id));
        setSelectedId(null);
      }
    } finally {
      if (seq === detailRequestSeqRef.current) setDetailLoading(false);
    }
  }

  function closeTopLayer(): boolean {
    if (draft) {
      setDraft(null);
      return true;
    }
    if (selectedId) {
      detailRequestSeqRef.current += 1;
      setSelectedId(null);
      setCommentDraft("");
      setCommentRequestId("");
      setDetailLoading(false);
      setDetailError("");
      return true;
    }
    return false;
  }

  useEffect(() => {
    if (!backHandlerRef) return;
    backHandlerRef.current = closeTopLayer;
    return () => {
      if (backHandlerRef.current === closeTopLayer) backHandlerRef.current = null;
    };
  }, [backHandlerRef, draft, selectedId]);

  useEffect(() => {
    setEntries([]);
    setNextCursor("");
    setLoadMoreError("");
    setError("");
    void loadEntries(activeAuthor);
  }, [activeAuthor]);

  function handleBack() {
    if (closeTopLayer()) return;
    onBack();
  }

  function openEdit(entry: DiaryEntry) {
    setDraft({
      id: entry.id,
      author: entry.author,
      title: entry.title,
      emoji: entry.emoji,
      content: entry.content,
    });
  }

  async function saveDraft() {
    if (!draft || saving) return;
    const title = draft.title.trim() || "没有标题的小纸条";
    const emoji = draft.emoji.trim() || "✦";
    const content = draft.content.trim();
    if (!content) return;
    setSaving(true);
    setError("");
    try {
      let item: DiaryEntry | null = null;
      if (draft.id) {
        const current = entries.find((entry) => entry.id === draft.id);
        const data = await apiJson<ItemResp>(`${EXCHANGE_DIARY_API}/${encodeURIComponent(draft.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            author: draft.author,
            title,
            mood: emoji,
            content,
            base_updated_at: current?.updatedAt || "",
          }),
        });
        item = data.item ? fromApiEntry(data.item) : null;
        if (item) {
          if (item.author !== activeAuthor) {
            setActiveAuthor(item.author);
            setEntries([item]);
          } else {
            setEntries((prev) => prev.map((entry) => (entry.id === item!.id ? item! : entry)));
          }
        }
      } else {
        const data = await apiJson<ItemResp>(EXCHANGE_DIARY_API, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            author: "xy",
            title,
            mood: emoji,
            content,
            client_request_id: makeId("exchange_diary"),
          }),
        });
        item = data.item ? fromApiEntry(data.item) : null;
        if (item) {
          setActiveAuthor(item.author);
          setEntries((prev) => [item!, ...prev.filter((entry) => entry.id !== item!.id)]);
          setSelectedId(item.id);
        }
      }
      setDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function deleteEntry(id: string) {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await apiJson<ItemResp>(`${EXCHANGE_DIARY_API}/${encodeURIComponent(id)}`, { method: "DELETE" });
      setEntries((prev) => prev.filter((entry) => entry.id !== id));
      setSelectedId(null);
      setDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function addComment(entry: DiaryEntry) {
    if (saving) return;
    const content = commentDraft.trim();
    if (!content) return;
    const requestId = commentRequestId || makeId("exchange_diary_comment");
    if (!commentRequestId) setCommentRequestId(requestId);
    setSaving(true);
    setError("");
    try {
      const data = await apiJson<ItemResp>(`${EXCHANGE_DIARY_API}/${encodeURIComponent(entry.id)}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ author: "xy", content, client_request_id: requestId }),
      });
      const item = data.item ? fromApiEntry(data.item) : null;
      if (item) {
        setEntries((prev) => prev.map((old) => (old.id === item.id ? item : old)));
      }
      setCommentDraft("");
      setCommentRequestId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="exchange-diary-page">
      <ExchangeDiaryStyles />
      <header className="exchange-diary-header-lace">
        <button className="exchange-diary-back" type="button" onClick={handleBack} aria-label="返回">
          <ChevronLeftIcon />
        </button>
        <div className="exchange-diary-toggle" role="tablist" aria-label="交换日记">
          <button
            className={`exchange-diary-toggle-btn ${activeAuthor === "du" ? "active" : ""}`}
            type="button"
            onClick={() => setActiveAuthor("du")}
            role="tab"
            aria-selected={activeAuthor === "du"}
          >
            <HeartGlyph />
            渡的Diary
          </button>
          <button
            className={`exchange-diary-toggle-btn ${activeAuthor === "xy" ? "active" : ""}`}
            type="button"
            onClick={() => setActiveAuthor("xy")}
            role="tab"
            aria-selected={activeAuthor === "xy"}
          >
            我的Diary
          </button>
        </div>
      </header>

      <main className="exchange-diary-timeline-container">
        <div className="exchange-diary-timeline-line" />
        {error ? <div className="exchange-diary-status error">{error}</div> : null}
        {loading ? <div className="exchange-diary-status">翻日记中...</div> : null}
        {!loading && !error && visibleEntries.length === 0 ? (
          <div className="exchange-diary-status">还没有日记</div>
        ) : null}
        {visibleEntries.map((entry, index) => (
          <article
            key={entry.id}
            className={`exchange-diary-entry ${index % 2 === 0 ? "side-left" : "side-right"} author-${entry.author}`}
          >
            {index < 2 ? (
              <div
                className="exchange-diary-star-ornament"
                style={index % 2 === 0 ? { top: "-20px", left: "10%" } : { top: "0", right: "5%" }}
              >
                ★
              </div>
            ) : null}
            <button className="exchange-diary-sticky-note" type="button" onClick={() => void openEntry(entry.id)}>
              <div className="exchange-diary-entry-header compact">
                <div className="exchange-diary-card-title-line">
                  <span className="exchange-diary-entry-title compact">{entry.title}</span>
                  <span className="exchange-diary-entry-emoji compact">{entry.emoji}</span>
                </div>
                <span className="exchange-diary-entry-time compact">{entry.createdAt}</span>
              </div>
            </button>
          </article>
        ))}
        {loadMoreError ? <div className="exchange-diary-status inline error">{loadMoreError}</div> : null}
        {!loading && nextCursor ? (
          <button
            className="exchange-diary-load-more"
            type="button"
            onClick={() => void loadEntries(activeAuthor, nextCursor)}
            disabled={loadingMore}
          >
            {loadingMore ? "翻页中..." : "继续翻"}
          </button>
        ) : null}
      </main>

      <button
        className="exchange-diary-add-entry-btn"
        type="button"
        onClick={() => {
          setActiveAuthor("xy");
          setDraft(emptyDraft("xy"));
        }}
        aria-label="写一条日记"
      >
        <PlusGlyph />
      </button>

      {selected ? (
        <div
          className="exchange-diary-overlay active"
          onClick={() => {
            setSelectedId(null);
            setCommentDraft("");
            setCommentRequestId("");
          }}
        >
          <div className="exchange-diary-detail-card" onClick={(event) => event.stopPropagation()}>
            <div className="exchange-diary-entry-header">
              <span className="exchange-diary-entry-title">{selected.title}</span>
              <span className="exchange-diary-entry-time">{selected.createdAt}</span>
            </div>
            {detailLoading ? <div className="exchange-diary-status inline">翻这一页中...</div> : null}
            {detailError ? <div className="exchange-diary-status inline error">{detailError}</div> : null}
            <div className="exchange-diary-entry-content detail">{selected.content}</div>
            <div className="exchange-diary-entry-footer detail-footer">
              <span className="exchange-diary-entry-emoji">{selected.emoji}</span>
              <span className="exchange-diary-comment-count">{authorLabel(selected.author)}写的</span>
            </div>

            <div className="exchange-diary-comments-section">
              <p className="exchange-diary-comments-title">Comments ({selected.comments.length})</p>
              {selected.comments.map((comment) => (
                <div
                  key={comment.id}
                  className={`exchange-diary-comment-row ${comment.replyToCommentId ? "reply" : ""}`}
                >
                  <div className="exchange-diary-comment-meta">
                    <strong>{commentPrefix(comment, selected.comments)}</strong>
                    {comment.createdAt ? <span>{comment.createdAt}</span> : null}
                  </div>
                  <div className="exchange-diary-comment-content">{comment.content}</div>
                </div>
              ))}
              <div className="exchange-diary-comment-box">
                <textarea
                  value={commentDraft}
                  onChange={(event) => {
                    setCommentDraft(event.target.value);
                    setCommentRequestId("");
                  }}
                  placeholder="写一句评论..."
                  rows={2}
                  disabled={saving}
                />
                <button type="button" onClick={() => addComment(selected)} disabled={saving || !commentDraft.trim()}>保存评论</button>
              </div>
            </div>

            <div className="exchange-diary-actions">
              <button className="exchange-diary-action-link" type="button" onClick={() => openEdit(selected)}>Edit</button>
              <button className="exchange-diary-action-link" type="button" onClick={() => deleteEntry(selected.id)} disabled={saving}>Delete</button>
              <button className="exchange-diary-action-link push-right" type="button" onClick={() => setSelectedId(null)}>Close</button>
            </div>
          </div>
        </div>
      ) : null}

      {draft ? (
        <div className="exchange-diary-overlay active" onClick={() => setDraft(null)}>
          <div className="exchange-diary-detail-card editor" onClick={(event) => event.stopPropagation()}>
            <div className="exchange-diary-editor-row">
              <input
                className="title-input"
                value={draft.title}
                onChange={(event) => setDraft((prev) => prev ? { ...prev, title: event.target.value } : prev)}
                placeholder="标题"
              />
              <label className="exchange-diary-emoji-field">
                <span>emoji</span>
                <input
                  className="emoji-input"
                  value={draft.emoji}
                  onChange={(event) => setDraft((prev) => prev ? { ...prev, emoji: event.target.value.slice(0, 4) } : prev)}
                  placeholder="✦"
                  aria-label="emoji"
                />
              </label>
            </div>
            {draft.id ? (
              <div className="exchange-diary-author-switch">
                <button
                  type="button"
                  className={draft.author === "du" ? "active" : ""}
                  onClick={() => setDraft((prev) => prev ? { ...prev, author: "du" } : prev)}
                >
                  渡
                </button>
                <button
                  type="button"
                  className={draft.author === "xy" ? "active" : ""}
                  onClick={() => setDraft((prev) => prev ? { ...prev, author: "xy" } : prev)}
                >
                  我
                </button>
              </div>
            ) : null}
            <textarea
              className="exchange-diary-editor-content"
              value={draft.content}
              onChange={(event) => setDraft((prev) => prev ? { ...prev, content: event.target.value } : prev)}
              placeholder="把今天想留下的事写在这里..."
              rows={8}
            />
            <div className="exchange-diary-actions">
              <button className="exchange-diary-action-link" type="button" onClick={() => setDraft(null)}>Cancel</button>
              <button className="exchange-diary-action-link push-right" type="button" onClick={saveDraft} disabled={saving}>Save</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function HeartGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
    </svg>
  );
}

function PlusGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function ExchangeDiaryStyles() {
  return (
    <style>{`
      .exchange-diary-page {
        --bg-cream: #FDF9F8;
        --soft-pink: #F7E9EB;
        --soft-blue: #E8EEF4;
        --soft-yellow: #FFF8E6;
        --accent-pink: #EBD5D8;
        --text-main: #7A7272;
        --text-light: #A8A1A1;
        --border-color: #E2D6D8;
        --serif-font: "Georgia", "Times New Roman", "Songti SC", serif;
        --mono-font: "Courier New", Courier, monospace;
        position: fixed;
        inset: 0;
        z-index: 40;
        min-height: 100dvh;
        overflow-y: auto;
        overflow-x: hidden;
        background-color: var(--bg-cream);
        background-image:
          radial-gradient(circle, rgba(235, 213, 216, 0.22) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(255,255,255,0.8), rgba(255,255,255,0.8));
        background-size: 20px 20px, 100% 100%;
        color: var(--text-main);
        font-family: var(--serif-font);
        -webkit-font-smoothing: antialiased;
      }

      .exchange-diary-page button,
      .exchange-diary-page input,
      .exchange-diary-page textarea {
        font-family: inherit;
      }

      .exchange-diary-header-lace {
        width: 100%;
        height: calc(env(safe-area-inset-top, 0px) + 60px);
        padding-top: env(safe-area-inset-top, 0px);
        background-color: white;
        position: sticky;
        top: 0;
        z-index: 100;
        display: flex;
        justify-content: center;
        align-items: center;
        border-bottom: 1px dashed var(--border-color);
        box-shadow: 0 2px 10px rgba(0,0,0,0.02);
      }

      .exchange-diary-header-lace::before {
        content: "";
        position: absolute;
        bottom: -12px;
        left: 0;
        right: 0;
        height: 12px;
        background-image: radial-gradient(circle at 6px 0, transparent 6px, white 6px);
        background-size: 12px 12px;
      }

      .exchange-diary-back {
        position: absolute;
        left: 12px;
        top: calc(env(safe-area-inset-top, 0px) + 10px);
        z-index: 2;
        width: 40px;
        height: 40px;
        border: none;
        border-radius: 999px;
        background: transparent;
        color: var(--text-main);
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .exchange-diary-toggle {
        display: flex;
        background: var(--soft-pink);
        padding: 4px;
        border-radius: 20px;
        gap: 4px;
        position: relative;
      }

      .exchange-diary-toggle-btn {
        padding: 6px 24px;
        border-radius: 16px;
        border: none;
        cursor: pointer;
        font-size: 14px;
        transition: all 0.3s ease;
        background: transparent;
        color: var(--text-light);
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .exchange-diary-toggle-btn.active {
        background: white;
        color: var(--text-main);
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
      }

      .exchange-diary-toggle-btn svg {
        width: 12px;
        height: 12px;
        fill: currentColor;
      }

      .exchange-diary-timeline-container {
        width: 100%;
        max-width: 700px;
        margin: 0 auto;
        padding: 60px 20px 120px;
        position: relative;
      }

      .exchange-diary-timeline-line {
        position: absolute;
        left: 50%;
        top: 0;
        bottom: 0;
        width: 1px;
        border-left: 1.5px dashed var(--border-color);
        z-index: 0;
      }

      .exchange-diary-status {
        position: relative;
        z-index: 2;
        width: fit-content;
        max-width: min(420px, calc(100vw - 56px));
        margin: 20px auto 34px;
        padding: 12px 18px;
        border: 1px dashed var(--border-color);
        background: rgba(255, 255, 255, 0.78);
        color: var(--text-light);
        font-size: 13px;
        text-align: center;
      }

      .exchange-diary-status.error {
        color: #9a5f66;
        background: rgba(255, 248, 248, 0.86);
      }

      .exchange-diary-status.inline {
        margin: 0 0 14px;
        width: 100%;
        max-width: none;
      }

      .exchange-diary-load-more {
        position: relative;
        z-index: 2;
        display: block;
        margin: -8px auto 40px;
        padding: 8px 20px;
        border: 1px solid rgba(213, 168, 176, 0.38);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.72);
        color: var(--text-light);
        font-size: 13px;
        letter-spacing: 0;
      }

      .exchange-diary-load-more:disabled {
        opacity: 0.55;
      }

      .exchange-diary-entry {
        width: 100%;
        margin-bottom: 52px;
        position: relative;
        z-index: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
      }

      .exchange-diary-sticky-note {
        width: 420px;
        padding: 30px;
        position: relative;
        text-align: left;
        color: var(--text-main);
        box-shadow: 0 4px 15px rgba(0,0,0,0.03);
        border: 1px solid rgba(235, 213, 216, 0.4);
        transition: transform 0.2s ease;
        cursor: pointer;
      }

      .exchange-diary-sticky-note:active {
        transform: translateY(-2px);
      }

      .exchange-diary-sticky-note::before {
        content: "♥";
        position: absolute;
        top: -15px;
        left: 50%;
        transform: translateX(-50%);
        font-size: 16px;
        color: var(--accent-pink);
        background: var(--bg-cream);
        padding: 0 10px;
      }

      .exchange-diary-entry.author-du .exchange-diary-sticky-note {
        background-color: var(--soft-blue);
      }

      .exchange-diary-entry.author-xy .exchange-diary-sticky-note {
        background-color: var(--soft-yellow);
      }

      .exchange-diary-entry.side-left .exchange-diary-sticky-note {
        align-self: flex-start;
        margin-left: 20px;
      }

      .exchange-diary-entry.side-right .exchange-diary-sticky-note {
        align-self: flex-end;
        margin-right: 20px;
      }

      .exchange-diary-entry-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 16px;
        margin-bottom: 15px;
        border-bottom: 1px solid rgba(0,0,0,0.05);
        padding-bottom: 10px;
      }

      .exchange-diary-entry-header.compact {
        flex-direction: column;
        justify-content: center;
        align-items: center;
        gap: 6px;
        margin-bottom: 0;
        border-bottom: none;
        padding-bottom: 0;
      }

      .exchange-diary-card-title-line {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 6px;
        width: 100%;
      }

      .exchange-diary-entry-title {
        min-width: 0;
        font-size: 18px;
        font-weight: 500;
        color: var(--text-main);
      }

      .exchange-diary-entry-title.compact {
        font-size: 15px;
        line-height: 1.35;
        text-align: center;
      }

      .exchange-diary-entry-time {
        flex-shrink: 0;
        font-family: var(--mono-font);
        font-size: 11px;
        color: var(--text-light);
        text-transform: uppercase;
      }

      .exchange-diary-entry-time.compact {
        font-size: 10px;
        letter-spacing: 0.04em;
      }

      .exchange-diary-entry-content {
        font-size: 14px;
        line-height: 1.8;
        color: var(--text-main);
        margin-bottom: 20px;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }

      .exchange-diary-entry-content.detail {
        display: block;
        overflow: visible;
        -webkit-line-clamp: initial;
        white-space: pre-wrap;
      }

      .exchange-diary-entry-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        font-size: 12px;
      }

      .exchange-diary-entry-footer.compact {
        justify-content: center;
      }

      .exchange-diary-entry-footer.detail-footer {
        border-bottom: 1px solid var(--soft-pink);
        padding-bottom: 15px;
        margin-bottom: 20px;
      }

      .exchange-diary-entry-emoji {
        font-size: 16px;
      }

      .exchange-diary-entry-emoji.compact {
        flex-shrink: 0;
        font-size: 15px;
        line-height: 1;
      }

      .exchange-diary-comment-count {
        color: var(--text-light);
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .exchange-diary-add-entry-btn {
        position: fixed;
        bottom: calc(env(safe-area-inset-bottom, 0px) + 32px);
        right: 28px;
        z-index: 90;
        width: 50px;
        height: 50px;
        background: white;
        border: 1px solid var(--accent-pink);
        border-radius: 50%;
        display: flex;
        justify-content: center;
        align-items: center;
        cursor: pointer;
        box-shadow: 0 4px 10px rgba(235, 213, 216, 0.4);
        transition: all 0.3s ease;
        color: var(--accent-pink);
      }

      .exchange-diary-add-entry-btn:active {
        transform: scale(1.1) rotate(90deg);
        background: var(--soft-pink);
      }

      .exchange-diary-add-entry-btn svg {
        width: 20px;
        height: 20px;
      }

      .exchange-diary-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(253, 249, 248, 0.95);
        z-index: 1000;
        display: none;
        justify-content: center;
        padding: calc(env(safe-area-inset-top, 0px) + 80px) 20px calc(env(safe-area-inset-bottom, 0px) + 40px);
        overflow-y: auto;
      }

      .exchange-diary-overlay.active {
        display: flex;
      }

      .exchange-diary-detail-card {
        width: 100%;
        max-width: 600px;
        background: white;
        padding: 40px;
        height: fit-content;
        border: 1px solid var(--border-color);
        box-shadow: 0 10px 40px rgba(0,0,0,0.05);
      }

      .exchange-diary-detail-card.editor {
        background: var(--soft-pink);
      }

      .exchange-diary-comments-section {
        font-size: 13px;
      }

      .exchange-diary-comments-title {
        color: var(--text-light);
        margin-bottom: 10px;
      }

      .exchange-diary-comment-row {
        margin-bottom: 10px;
        background: var(--bg-cream);
        padding: 10px;
      }

      .exchange-diary-comment-row.reply {
        border-left: 2px solid rgba(203, 161, 145, 0.42);
      }

      .exchange-diary-comment-meta {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 4px;
        color: var(--text-main);
      }

      .exchange-diary-comment-meta strong {
        font-weight: 600;
      }

      .exchange-diary-comment-meta span {
        flex: 0 0 auto;
        color: var(--text-light);
        font-size: 11px;
      }

      .exchange-diary-comment-content {
        line-height: 1.7;
      }

      .exchange-diary-comment-box {
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }

      .exchange-diary-comment-box textarea,
      .exchange-diary-editor-row input,
      .exchange-diary-editor-content {
        width: 100%;
        border: 1px dashed var(--border-color);
        background: rgba(255,255,255,0.72);
        color: var(--text-main);
        outline: none;
        padding: 10px 12px;
        font-size: 14px;
        line-height: 1.7;
      }

      .exchange-diary-comment-box button {
        justify-self: end;
        border: 1px solid var(--accent-pink);
        background: white;
        color: var(--text-main);
        padding: 7px 14px;
        font-size: 12px;
      }

      .exchange-diary-actions {
        margin-top: 30px;
        padding-top: 20px;
        border-top: 1px dashed var(--border-color);
        display: flex;
        gap: 20px;
      }

      .exchange-diary-action-link {
        border: none;
        background: transparent;
        padding: 0;
        font-size: 12px;
        color: var(--text-light);
        text-decoration: none;
        cursor: pointer;
      }

      .exchange-diary-action-link:active {
        color: var(--text-main);
      }

      .exchange-diary-action-link.push-right {
        margin-left: auto;
      }

      .exchange-diary-editor-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 86px;
        align-items: end;
        gap: 10px;
        margin-bottom: 12px;
      }

      .exchange-diary-emoji-field {
        display: grid;
        grid-template-rows: auto 1fr;
        gap: 3px;
      }

      .exchange-diary-emoji-field span {
        font-family: var(--mono-font);
        font-size: 9px;
        line-height: 1;
        letter-spacing: 0.08em;
        text-align: center;
        text-transform: uppercase;
        color: var(--text-light);
      }

      .exchange-diary-editor-row .emoji-input {
        text-align: center;
      }

      .exchange-diary-author-switch {
        display: flex;
        width: fit-content;
        margin-bottom: 14px;
        padding: 4px;
        background: rgba(255,255,255,0.45);
        border-radius: 999px;
        gap: 4px;
      }

      .exchange-diary-author-switch button {
        border: none;
        background: transparent;
        color: var(--text-light);
        border-radius: 999px;
        padding: 5px 18px;
        font-size: 13px;
      }

      .exchange-diary-author-switch button.active {
        background: white;
        color: var(--text-main);
      }

      .exchange-diary-editor-content {
        resize: vertical;
        min-height: 170px;
      }

      .exchange-diary-star-ornament {
        position: absolute;
        color: var(--accent-pink);
        font-size: 10px;
        opacity: 0.6;
      }

      @media (max-width: 600px) {
        .exchange-diary-back {
          left: 8px;
        }

        .exchange-diary-toggle-btn {
          padding: 6px 18px;
          font-size: 13px;
        }

        .exchange-diary-timeline-container {
          padding: 52px 12px 118px;
        }

        .exchange-diary-sticky-note {
          width: min(74vw, 292px);
          padding: 24px 22px;
        }

        .exchange-diary-entry {
          margin-bottom: 34px;
        }

        .exchange-diary-entry.side-left .exchange-diary-sticky-note {
          align-self: flex-start;
          margin-left: 10px;
          margin-right: 0;
        }

        .exchange-diary-entry.side-right .exchange-diary-sticky-note {
          align-self: flex-end;
          margin-right: 10px;
          margin-left: 0;
        }

        .exchange-diary-entry-header {
          flex-direction: column;
          align-items: flex-start;
          gap: 4px;
        }

        .exchange-diary-detail-card {
          padding: 30px 24px;
        }

        .exchange-diary-add-entry-btn {
          right: 22px;
          bottom: calc(env(safe-area-inset-bottom, 0px) + 28px);
        }
      }

      @media (max-width: 360px) {
        .exchange-diary-sticky-note {
          width: min(76vw, 272px);
        }

        .exchange-diary-toggle-btn {
          padding-left: 14px;
          padding-right: 14px;
        }
      }
    `}</style>
  );
}
