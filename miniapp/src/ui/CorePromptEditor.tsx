import React, { useEffect, useState } from "react";
import { apiJson } from "./api";
import { FullScreenPane } from "./FullScreenPane";
import { useToast } from "./toast";

type PortraitBucket = "xinyue" | "du" | "interaction";
type PortraitCandidate = { id?: string; summary?: string };

export function CorePromptEditor({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [activeKey, setActiveKey] = useState<"a" | "b">("a");
  const [promptA, setPromptA] = useState("");
  const [promptB, setPromptB] = useState("");
  const [loadedPromptA, setLoadedPromptA] = useState("");
  const [loadedPromptB, setLoadedPromptB] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [portrait, setPortrait] = useState<{
    xinyue_candidates?: PortraitCandidate[];
    du_candidates?: PortraitCandidate[];
    interaction_candidates?: PortraitCandidate[];
  } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ bucket: PortraitBucket; id: string } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [j, p] = await Promise.all([
        apiJson<{ ok?: boolean; content?: string; source?: string; error?: string; active_key?: string; prompts?: { a?: string; b?: string } }>("/miniapp-api/core-prompt"),
        apiJson<{ ok?: boolean; xinyue_candidates?: PortraitCandidate[]; du_candidates?: PortraitCandidate[]; interaction_candidates?: PortraitCandidate[] }>("/miniapp-api/portrait-memory"),
      ]);
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setActiveKey(((j.active_key || "a").toString() === "b" ? "b" : "a"));
      const nextA = ((j.prompts?.a ?? j.content) || "").toString();
      const nextB = (j.prompts?.b || "").toString();
      setPromptA(nextA);
      setPromptB(nextB);
      setLoadedPromptA(nextA);
      setLoadedPromptB(nextB);
      if (p?.ok) setPortrait(p);
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

  async function save() {
    const pa = (promptA || "").trim();
    const pb = (promptB || "").trim();
    if (activeKey === "a" && !pa) {
      toast("当前选中的 Prompt A 不能为空");
      return;
    }
    if (activeKey === "b" && !pb) {
      toast("当前选中的 Prompt B 不能为空");
      return;
    }
    const ok = window.confirm("确认保存核心 Prompt 吗？保存后会立即覆盖线上注入内容。");
    if (!ok) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/core-prompt", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_key: activeKey, prompts: { a: promptA, b: promptB } }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      toast("已保存，下一条请求生效");
      setLoadedPromptA(promptA);
      setLoadedPromptB(promptB);
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  function handleCancelEdit() {
    setPromptA(loadedPromptA);
    setPromptB(loadedPromptB);
    onClose();
  }

  async function copyText(text: string) {
    const content = (text || "").trim();
    if (!content) {
      toast("没有可复制的内容");
      return;
    }
    try {
      await navigator.clipboard.writeText(content);
      toast("已复制");
    } catch (e: any) {
      toast(`复制失败：${e?.message || e}`);
    }
  }

  async function deletePortrait(bucket: PortraitBucket, id: string) {
    if (!id) return;
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/portrait-memory/${encodeURIComponent(bucket)}/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      toast("已删除");
      setPendingDelete(null);
      await load();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  const isDirty = promptA !== loadedPromptA || promptB !== loadedPromptB;
  const activePrompt = activeKey === "a" ? promptA : promptB;
  const setActivePrompt = (value: string) => {
    if (activeKey === "a") {
      setPromptA(value);
      return;
    }
    setPromptB(value);
  };

  return (
    <FullScreenPane title="核心 Prompt" accent="neutral" onBack={onClose}>
      <div className="px-2 pb-32 pt-2 text-gray-900">
        <div className="mb-6 flex rounded-2xl bg-gray-100/50 p-1">
          <button
            type="button"
            onClick={() => setActiveKey("a")}
            disabled={loading || saving}
            className={`flex-1 rounded-xl py-2.5 text-[14px] ${
              activeKey === "a"
                ? "border border-gray-100 bg-white font-bold text-gray-800 shadow-sm"
                : "font-medium text-gray-400"
            }`}
          >
            Prompt A
          </button>
          <button
            type="button"
            onClick={() => setActiveKey("b")}
            disabled={loading || saving}
            className={`flex-1 rounded-xl py-2.5 text-[14px] ${
              activeKey === "b"
                ? "border border-gray-100 bg-white font-bold text-gray-800 shadow-sm"
                : "font-medium text-gray-400"
            }`}
          >
            Prompt B
          </button>
        </div>

        <div className="mb-4 rounded-[28px] border border-gray-100/80 bg-white p-6 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[18px] font-bold text-gray-800">Prompt {activeKey.toUpperCase()}</h2>
            {isDirty ? (
              <div className="flex items-center rounded-md border border-amber-100 bg-amber-50 px-2 py-1">
                <span className="mr-2 h-1.5 w-1.5 rounded-full bg-amber-400" />
                <span className="text-[10px] font-bold uppercase text-amber-600">未保存修改</span>
              </div>
            ) : (
              <div className="flex items-center rounded-md border border-green-100 bg-green-50 px-2 py-1">
                <span className="mr-2 h-1.5 w-1.5 rounded-full bg-green-400" />
                <span className="text-[10px] font-bold uppercase text-green-600">已同步</span>
              </div>
            )}
          </div>
          <p className="text-[13px] leading-relaxed text-gray-400">当前正在编辑的是主交互指令，该指令决定了 AI 的基础人格特质和长期记忆提取逻辑。</p>
        </div>

        <div className="mb-8 rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
          <div className="mb-4 px-1">
            <h3 className="mb-1 text-[13px] font-bold uppercase tracking-widest text-gray-400">系统核心指令</h3>
            <p className="text-[11px] text-gray-300">定义角色的回复风格与行为准则</p>
          </div>
          <div className="rounded-[22px] bg-gray-50 p-5">
            <textarea
              className="h-[400px] w-full resize-none border-none bg-transparent text-[15px] leading-relaxed text-gray-700 outline-none"
              value={activePrompt}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setActivePrompt(e.target.value)}
              placeholder={loading ? "加载中..." : "输入核心 Prompt内容..."}
            />
            <div className="mt-4 flex justify-end">
              <span className="text-[11px] font-medium text-gray-300">{activePrompt.length.toLocaleString()} 字符</span>
            </div>
          </div>
        </div>

        <div className="mb-6">
          <PortraitBlock title="辛玥画像候选" bucket="xinyue" items={portrait?.xinyue_candidates || []} onCopy={copyText} onDelete={(bucket, id) => setPendingDelete({ bucket, id })} />
        </div>
        <div className="mb-6">
          <PortraitBlock title="渡画像候选" bucket="du" items={portrait?.du_candidates || []} onCopy={copyText} onDelete={(bucket, id) => setPendingDelete({ bucket, id })} />
        </div>
        <div className="mb-6">
          <PortraitBlock title="相处模式候选" bucket="interaction" items={portrait?.interaction_candidates || []} onCopy={copyText} onDelete={(bucket, id) => setPendingDelete({ bucket, id })} />
        </div>
      </div>

      {isDirty ? (
        <div className="pointer-events-none fixed bottom-[96px] left-5 right-5 z-[60]">
          <div className="flex items-center justify-center rounded-full bg-amber-500 px-4 py-2 text-[12px] font-bold text-white shadow-lg">
            <svg className="mr-2 h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            您有未保存的修改，请确认保存或取消
          </div>
        </div>
      ) : null}

      <div className="safe-bottom fixed bottom-0 left-0 right-0 z-[55] flex gap-4 border-t border-gray-50 bg-white/80 p-5 pb-[calc(env(safe-area-inset-bottom,0px)+20px)] backdrop-blur-lg">
        <button
          type="button"
          onClick={handleCancelEdit}
          disabled={loading || saving}
          className="flex-1 rounded-[20px] py-4 text-[15px] font-bold text-gray-400 transition-all active:bg-gray-50"
        >
          取消编辑
        </button>
        <button
          type="button"
          onClick={save}
          disabled={loading || saving}
          className="flex-1 rounded-[20px] bg-gray-800 py-4 text-[15px] font-bold text-white shadow-[0_10px_24px_rgba(15,23,42,0.18)] transition-all active:scale-95"
        >
          保存修改
        </button>
      </div>

      {pendingDelete ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/10 px-8 backdrop-blur-[2px]">
          <div className="w-full max-w-sm rounded-[32px] bg-white p-8 shadow-2xl">
            <div className="mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-full bg-red-50">
              <svg className="h-6 w-6 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </div>
            <h3 className="mb-3 text-center text-[20px] font-semibold text-gray-900">要删除这个画像候选吗？</h3>
            <p className="mb-8 px-2 text-center text-[15px] font-light leading-relaxed text-gray-500">此操作将永久移除该条目，您将无法再在 Prompt 编辑中快速引用它。</p>
            <div className="flex flex-col space-y-3">
              <button
                type="button"
                onClick={() => void deletePortrait(pendingDelete.bucket, pendingDelete.id)}
                className="w-full rounded-[20px] bg-red-500 py-4 font-bold text-white shadow-lg shadow-red-100 transition-all active:scale-95"
              >
                确认删除
              </button>
              <button
                type="button"
                onClick={() => setPendingDelete(null)}
                className="w-full rounded-[20px] py-4 font-bold text-gray-400 transition-all active:bg-gray-50"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </FullScreenPane>
  );
}

function PortraitBlock({
  title,
  bucket,
  items,
  onCopy,
  onDelete,
}: {
  title: string;
  bucket: PortraitBucket;
  items: PortraitCandidate[];
  onCopy: (text: string) => void;
  onDelete: (bucket: PortraitBucket, id: string) => void;
}) {
  return (
    <>
      <div className="mb-3 flex items-center justify-between px-2">
        <h2 className="text-[12px] font-bold uppercase tracking-widest text-gray-400">{title}</h2>
        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-500">{items.length}</span>
      </div>
      {!items.length ? <div className="rounded-[24px] border border-gray-50 bg-white px-4 py-4 text-[13px] text-gray-400 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">暂无候选</div> : null}
      <div className="space-y-3">
        {items.map((item, idx) => (
          <div key={item.id || `${title}-${idx}`} className="flex items-center gap-4 rounded-[24px] border border-gray-50 bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
            <div className="flex-1">
              <p className="line-clamp-2 text-[13px] leading-snug text-gray-600">{String(item.summary || "")}</p>
            </div>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => onCopy(String(item.summary || ""))}
                className="p-2 text-gray-300 transition-colors active:text-blue-500"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              </button>
              {item.id ? (
                <button
                  type="button"
                  onClick={() => onDelete(bucket, String(item.id || ""))}
                  className="p-2 text-gray-300 transition-colors active:text-red-400"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <line x1="10" y1="11" x2="10" y2="17" />
                    <line x1="14" y1="11" x2="14" y2="17" />
                  </svg>
                </button>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
