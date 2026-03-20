import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { Btn } from "../components";
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

export function DuNotebookTab() {
  const toast = useToast();
  const [items, setItems] = useState<DuNote[]>([]);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [editingText, setEditingText] = useState("");

  async function load() {
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
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rows = useMemo(
    () =>
      normalize(items).slice().sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""))),
    [items]
  );

  async function add() {
    const c = (text || "").trim();
    if (!c) return toast("先写一条记事");
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/du-notebook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: c }),
      });
      if (!j?.ok) throw new Error(j?.error || "新增失败");
      setText("");
      toast("已写入渡的记事本");
      await load();
    } catch (e: any) {
      toast(`新增失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function saveEdit(id: string) {
    const c = (editingText || "").trim();
    if (!id || !c) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/du-notebook/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: c }),
      });
      if (!j?.ok) throw new Error(j?.error || "更新失败");
      setEditingId("");
      setEditingText("");
      toast("已更新");
      await load();
    } catch (e: any) {
      toast(`更新失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    if (!id) return;
    if (!window.confirm("确认删除这条记事？")) return;
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/du-notebook/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除");
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  return (
    <div className="space-y-3">
      <div className="rounded-xl3 bg-white border border-white/70 shadow-soft p-3 space-y-2">
        <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">
          新增记事
        </div>
        <textarea
          className="w-full min-h-[84px] rounded-xl2 bg-white border border-white/70 px-3 py-2 text-sm text-cream-text shadow-soft2"
          placeholder="写一条固定注入的记事..."
          value={text}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value)}
          disabled={saving}
        />
        <Btn kind="dark" onClick={add} disabled={saving}>
          {saving ? "保存中..." : "写入记事本"}
        </Btn>
      </div>

      <div className="space-y-2">
        {rows.map((it) => (
          <div key={String(it.id || "")} className="rounded-xl3 bg-white border border-white/70 shadow-soft p-3 space-y-2">
            <div className="text-xs text-[#5f5a52]">{String(it.updated_at || it.created_at || "")}</div>
            {editingId === String(it.id || "") ? (
              <>
                <textarea
                  className="w-full min-h-[84px] rounded-xl2 bg-white border border-white/70 px-3 py-2 text-sm text-cream-text shadow-soft2"
                  value={editingText}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setEditingText(e.target.value)}
                  disabled={saving}
                />
                <div className="flex items-center gap-2">
                  <Btn kind="dark" onClick={() => saveEdit(String(it.id || ""))} disabled={saving}>保存</Btn>
                  <Btn
                    kind="blue"
                    onClick={() => {
                      setEditingId("");
                      setEditingText("");
                    }}
                    disabled={saving}
                  >
                    取消
                  </Btn>
                </div>
              </>
            ) : (
              <>
                <div className="text-sm text-cream-text whitespace-pre-wrap">{String(it.content || "")}</div>
                <div className="flex items-center gap-2">
                  <Btn
                    kind="dark"
                    onClick={() => {
                      setEditingId(String(it.id || ""));
                      setEditingText(String(it.content || ""));
                    }}
                  >
                    修改
                  </Btn>
                  <Btn kind="pink" onClick={() => remove(String(it.id || ""))}>删除</Btn>
                </div>
              </>
            )}
          </div>
        ))}
        {!rows.length && !loading ? <div className="text-xs text-cream-muted">还没有记事。</div> : null}
      </div>
    </div>
  );
}

