import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type DuNote = {
  id?: string;
  content?: string;
  created_at?: string;
  updated_at?: string;
};

type DuNoteResp = {
  ok?: boolean;
  items?: DuNote[];
  count?: number;
  error?: string;
};

function normalize(input: unknown): DuNote[] {
  if (!Array.isArray(input)) return [];
  return input.filter((x): x is DuNote => !!x && typeof x === "object");
}

function formatTopDate(value?: string) {
  const date = value ? new Date(value) : new Date();
  const month = date.toLocaleString("en-US", { month: "short" });
  const day = String(date.getDate()).padStart(2, "0");
  return `${month} ${day}`;
}

function formatClock(value?: string) {
  if (!value) return "--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--";
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export function DuNotebookTab() {
  const toast = useToast();
  const [items, setItems] = useState<DuNote[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draftOpen, setDraftOpen] = useState(false);
  const [draftText, setDraftText] = useState("");
  const [editingId, setEditingId] = useState("");
  const [deletingId, setDeletingId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const j = await apiJson<DuNoteResp>("/miniapp-api/du-notebook");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setItems(normalize(j.items));
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(load, 5000);
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    const onFocus = () => load();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  const rows = useMemo(
    () =>
      normalize(items)
        .slice()
        .sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""))),
    [items]
  );

  const pageDate = formatTopDate(rows[0]?.updated_at || rows[0]?.created_at);
  const activeNote = editingId ? rows.find((it) => String(it.id || "") === editingId) : null;

  async function add() {
    const content = draftText.trim();
    if (!content) return toast("先写一条记事");
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/du-notebook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!j?.ok) throw new Error(j?.error || "新增失败");
      setDraftText("");
      setDraftOpen(false);
      toast("已写入渡的记事本");
      await load();
    } catch (e: any) {
      toast(`新增失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function saveEdit() {
    const id = editingId;
    const content = draftText.trim();
    if (!id || !content) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/du-notebook/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!j?.ok) throw new Error(j?.error || "更新失败");
      setEditingId("");
      setDraftText("");
      setDraftOpen(false);
      toast("已更新");
      await load();
    } catch (e: any) {
      toast(`更新失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    const id = deletingId;
    if (!id) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/du-notebook/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      setDeletingId("");
      toast("已删除");
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  function openCreate() {
    setEditingId("");
    setDraftText("");
    setDraftOpen(true);
  }

  function openEdit(note: DuNote) {
    setEditingId(String(note.id || ""));
    setDraftText(String(note.content || ""));
    setDraftOpen(true);
  }

  return (
    <div
      className="relative min-h-full overflow-x-hidden bg-[#FAF9F6] pb-24 text-[#5A524D]"
      style={{ fontFamily: "'Noto Serif SC', serif" }}
    >
      <div className="flex justify-end px-3 pb-4 pt-2">
        <div className="text-[10px] font-light uppercase tracking-[0.2em] text-stone-400">{pageDate}</div>
      </div>

      <div className="pointer-events-none absolute bottom-0 left-7 top-0 w-px bg-[#EBE5DB]" />

      <div className="relative z-10 flex flex-col gap-12 px-1 pb-8">
        {rows.map((it) => (
          <div key={String(it.id || "")} className="flex">
            <div className="w-16 flex-shrink-0 pt-2">
              <div className="flex flex-col items-center">
                <div className="mb-3 h-2 w-2 rounded-full border-4 border-[#FAF9F6] bg-[#D6C7B7] ring-1 ring-[#E8E2D9]" />
                <span className="text-[11px] font-light tracking-wider text-stone-400">
                  {formatClock(it.updated_at || it.created_at)}
                </span>
              </div>
            </div>

            <div className="flex-1 pr-2">
              <div className="relative rounded-sm bg-white p-6 shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
                <div
                  className="pointer-events-none absolute -top-[10px] left-[10px] h-[15px] w-[40px]"
                  style={{ background: "rgba(224, 214, 203, 0.3)", transform: "rotate(-3deg)" }}
                />

                <div className="relative">
                  <span className="absolute -left-4 top-0 text-3xl text-[#E8E2D9]">“</span>
                  <p className="px-2 text-[15px] font-light leading-relaxed text-stone-600 whitespace-pre-wrap">
                    {String(it.content || "")}
                  </p>
                  <span className="absolute -bottom-1 -right-1 text-3xl text-[#E8E2D9]">”</span>
                </div>

                <div className="mt-8 flex items-center border-t border-stone-50 pt-4">
                  <div className="flex gap-4">
                    <button
                      className="text-[12px] text-stone-400 transition-colors active:text-stone-600"
                      onClick={() => openEdit(it)}
                    >
                      编辑
                    </button>
                    <button
                      className="text-[12px] text-stone-300 transition-colors active:text-stone-500"
                      onClick={() => setDeletingId(String(it.id || ""))}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}

        {!rows.length && !loading ? (
          <div className="pl-16 pr-4 text-[13px] font-light leading-7 text-stone-400">还没有记事。</div>
        ) : null}
      </div>

      <div className="fixed bottom-10 right-6 z-30">
        <button
          className="flex h-14 w-14 items-center justify-center rounded-full bg-[#D6C7B7] text-white shadow-lg transition-transform active:scale-95"
          onClick={openCreate}
          aria-label="新增记事"
        >
          <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>

      {draftOpen ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#FAF9F6]/80 p-8 backdrop-blur-md">
          <div className="w-full max-w-xs rounded-sm bg-white p-6 shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <textarea
              className="min-h-[180px] w-full resize-none bg-transparent text-[15px] font-light leading-relaxed text-stone-600 outline-none placeholder:text-stone-300"
              placeholder="写下一段想留下的记事..."
              value={draftText}
              onChange={(e) => setDraftText(e.target.value)}
              disabled={saving}
            />
            <div className="mt-6 flex items-center justify-end gap-4">
              <button
                className="text-sm tracking-widest text-stone-400"
                onClick={() => {
                  setDraftOpen(false);
                  setEditingId("");
                  setDraftText("");
                }}
                disabled={saving}
              >
                取消
              </button>
              <button
                className="rounded-sm bg-[#D6C7B7] px-5 py-3 text-sm font-medium tracking-widest text-white"
                onClick={() => void (editingId ? saveEdit() : add())}
                disabled={saving}
              >
                {saving ? "保存中" : editingId ? "保存" : "新增"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deletingId ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#FAF9F6]/80 p-8 backdrop-blur-md">
          <div className="max-w-xs rounded-sm bg-white p-8 text-center shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <div
              className="mb-4 text-2xl italic text-stone-500"
              style={{ fontFamily: "'Dancing Script', cursive" }}
            >
              Let it go?
            </div>
            <p className="mb-8 text-sm font-light leading-relaxed text-stone-500">
              这段记忆要从记事本里抹去吗？
              <br />
              被删除的心情可能无法找回哦。
            </p>
            <div className="flex flex-col gap-3">
              <button
                className="rounded-sm bg-[#D6C7B7] px-6 py-3 text-sm font-medium tracking-widest text-white"
                onClick={() => void remove()}
                disabled={saving}
              >
                确认删除
              </button>
              <button
                className="px-6 py-3 text-sm tracking-widest text-stone-400"
                onClick={() => setDeletingId("")}
                disabled={saving}
              >
                再想想
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div
        className={`pointer-events-none fixed bottom-24 left-0 right-0 z-30 flex justify-center transition-opacity ${loading || saving ? "opacity-100" : "opacity-0"}`}
      >
        <div className="rounded-full border border-stone-100 bg-white/90 px-4 py-2 text-[11px] tracking-wider text-stone-400 shadow-sm">
          正在同步笔记...
        </div>
      </div>
    </div>
  );
}
