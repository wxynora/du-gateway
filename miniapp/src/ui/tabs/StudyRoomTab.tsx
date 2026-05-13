import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson } from "../api";
import { useToast } from "../toast";

type StudyRoomModule = {
  id: string;
  label: string;
};

type StudyRoomItem = {
  id?: string;
  title?: string;
  content?: string;
  url?: string;
  module_id?: string;
  source_type?: string;
  status?: "todo" | "sorting" | "done";
  note?: string;
  created_at?: string;
  updated_at?: string;
};

type StudyRoomLog = {
  id?: string;
  content?: string;
  created_at?: string;
};

type KnowledgeDebtItem = {
  id: string;
  text: string;
  title: string;
  module_id?: string;
  updated_at?: string;
};

type ExamLane = {
  id: string;
  title: string;
  subtitle: string;
  modules: string[];
};

type StudyRoomData = {
  profile?: {
    target_name?: string;
    exam_name?: string;
    expected_month?: string;
    goal?: string;
  };
  modules?: StudyRoomModule[];
  items?: StudyRoomItem[];
  study_logs?: StudyRoomLog[];
  updated_at?: string;
};

type StudyRoomResponse = {
  ok?: boolean;
  data?: StudyRoomData;
  item?: StudyRoomItem;
  entry?: StudyRoomLog;
  error?: string;
};

type StudyRoomImportResponse = StudyRoomResponse & {
  chars?: number;
};

type StudyRoomAutoModuleResponse = StudyRoomResponse & {
  module_id?: string;
};

type CodexTask = {
  id?: string;
  status?: "queued" | "running" | "done" | "error" | "cancelled";
  response?: string;
  error?: string;
};

type CodexTaskResponse = {
  ok?: boolean;
  task?: CodexTask | null;
  data?: StudyRoomData;
  error?: string;
};

const SOURCE_LABELS: Record<string, string> = {
  bilibili: "B站视频",
  web: "网页资料",
  pdf: "PDF",
  word: "Word",
  text: "文本文件",
  screenshot: "截图",
  fenbi: "粉笔错题",
  note: "手写备注",
  wrong_question: "错题",
};

const STATUS_LABELS: Record<string, string> = {
  todo: "待整理",
  sorting: "整理中",
  done: "已整理",
};
const EXAM_LANES: ExamLane[] = [
  {
    id: "objective",
    title: "客观题底盘",
    subtitle: "时政、党建、三农、法律、计算机这些先铺熟。",
    modules: ["current_affairs", "party", "rural", "law", "computer"],
  },
  {
    id: "case",
    title: "基层案例",
    subtitle: "群众工作、矛盾调解、村务处理，练答题框架。",
    modules: ["governance", "village_affairs", "rural"],
  },
  {
    id: "writing",
    title: "公文写作",
    subtitle: "通知、请示、报告、简报，重点练格式和语气。",
    modules: ["writing"],
  },
  {
    id: "local",
    title: "本地县情",
    subtitle: "安徽、铜陵、枞阳相关政策和县情做速记。",
    modules: ["local"],
  },
  {
    id: "wrong_questions",
    title: "错题回炉",
    subtitle: "错因、同类题、知识债，形成闭环。",
    modules: ["wrong_questions"],
  },
];
const CODEX_SORT_POLL_MS = 2200;
const CODEX_SORT_TIMEOUT_MS = 8 * 60 * 1000;

function normalizeModules(input: unknown): StudyRoomModule[] {
  if (!Array.isArray(input)) return [];
  return input
    .map((item) => ({
      id: String((item as any)?.id || "").trim(),
      label: String((item as any)?.label || "").trim(),
    }))
    .filter((item) => item.id && item.label);
}

function normalizeItems(input: unknown): StudyRoomItem[] {
  if (!Array.isArray(input)) return [];
  return input.filter((item): item is StudyRoomItem => Boolean(item && typeof item === "object"));
}

function normalizeLogs(input: unknown): StudyRoomLog[] {
  if (!Array.isArray(input)) return [];
  return input.filter((item): item is StudyRoomLog => Boolean(item && typeof item === "object"));
}

function formatShortTime(value?: string): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function sourceLabel(value?: string): string {
  return SOURCE_LABELS[String(value || "")] || "资料";
}

function statusLabel(value?: string): string {
  return STATUS_LABELS[String(value || "")] || "待整理";
}

function moduleLabel(value?: string, modules: StudyRoomModule[] = []): string {
  const id = String(value || "inbox");
  return modules.find((m) => m.id === id)?.label || "待整理";
}

function nextStatus(value?: string): "todo" | "sorting" | "done" {
  if (value === "todo") return "sorting";
  if (value === "sorting") return "done";
  return "todo";
}

function cleanDebtLine(line: string): string {
  return String(line || "")
    .replace(/^\s*[-*•]\s*/, "")
    .replace(/^\s*\d+[.、)]\s*/, "")
    .replace(/^\s*\[[ xX]\]\s*/, "")
    .trim();
}

function extractKnowledgeDebts(item: StudyRoomItem): KnowledgeDebtItem[] {
  const note = String(item.note || "");
  if (!note.trim()) return [];
  const lines = note.split(/\r?\n/);
  const out: KnowledgeDebtItem[] = [];
  let active = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    if (/^(#{1,6}\s*)?知识债(清单)?\s*[:：]?\s*$/.test(line)) {
      active = true;
      continue;
    }
    if (active && /^(#{1,6}\s*)?(考点笔记|高频问法|易错点|背诵卡|卡点预测|练习题)\s*[:：]?\s*$/.test(line)) {
      break;
    }
    if (!active) continue;
    const text = cleanDebtLine(line);
    if (!text || /^(无|暂无|没有|无明显)/.test(text)) continue;
    out.push({
      id: `${item.id || item.title || "debt"}-${out.length}`,
      text,
      title: String(item.title || "未命名资料"),
      module_id: item.module_id,
      updated_at: item.updated_at || item.created_at,
    });
    if (out.length >= 4) break;
  }
  return out;
}

function buildSortPrompt(item: StudyRoomItem, modules: StudyRoomModule[], profile?: StudyRoomData["profile"]): string {
  const moduleLabel = modules.find((m) => m.id === item.module_id)?.label || "待整理";
  return [
    "请帮我把这份学习资料整理成当前目标可用材料。",
    "",
    `当前目标：${profile?.target_name || profile?.exam_name || "安徽省铜陵市枞阳县村级后备干部考试"}`,
    `模块：${moduleLabel}`,
    `来源：${sourceLabel(item.source_type)}`,
    item.url ? `链接：${item.url}` : "",
    `标题：${item.title || "未命名资料"}`,
    "",
    "请输出：",
    "1. 考点笔记",
    "2. 题型落点",
    "3. 高频问法",
    "4. 易错点",
    "5. 应试用法",
    "6. 背诵卡",
    "7. 卡点预测",
    "8. 知识债清单",
    "9. 5道练习题",
    "",
    "资料内容：",
    item.content || item.note || item.url || "",
  ]
    .filter(Boolean)
    .join("\n");
}

function waitMs(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function waitForCodexTask(taskId: string): Promise<CodexTask> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < CODEX_SORT_TIMEOUT_MS) {
    await waitMs(CODEX_SORT_POLL_MS);
    const j = await apiJson<CodexTaskResponse>(`/miniapp-api/codex-group-chat-tasks/${encodeURIComponent(taskId)}`);
    const task = j.task || {};
    if (task.status === "done") return task;
    if (task.status === "error" || task.status === "cancelled") {
      throw new Error(task.error || j.error || "整理失败");
    }
  }
  throw new Error("整理超时，稍后再看任务结果");
}

export function StudyRoomTab() {
  const toast = useToast();
  const [data, setData] = useState<StudyRoomData>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [moduleFilter, setModuleFilter] = useState("all");
  const [sourceType, setSourceType] = useState("bilibili");
  const [moduleId, setModuleId] = useState("inbox");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [studyLog, setStudyLog] = useState("");
  const [sortingItemId, setSortingItemId] = useState("");
  const [classifyingItemId, setClassifyingItemId] = useState("");

  const modules = useMemo(() => normalizeModules(data.modules), [data.modules]);
  const items = useMemo(() => normalizeItems(data.items), [data.items]);
  const logs = useMemo(() => normalizeLogs(data.study_logs), [data.study_logs]);

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const item of items) {
      const key = String(item.module_id || "inbox");
      map.set(key, (map.get(key) || 0) + 1);
    }
    return map;
  }, [items]);

  const visibleItems = useMemo(() => {
    const list = items.slice().sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")));
    if (moduleFilter === "all") return list;
    return list.filter((item) => String(item.module_id || "inbox") === moduleFilter);
  }, [items, moduleFilter]);

  const knowledgeDebts = useMemo(() => {
    const seen = new Set<string>();
    const debts: KnowledgeDebtItem[] = [];
    const sorted = items.slice().sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")));
    for (const item of sorted) {
      for (const debt of extractKnowledgeDebts(item)) {
        const key = debt.text.replace(/\s+/g, "");
        if (!key || seen.has(key)) continue;
        seen.add(key);
        debts.push(debt);
        if (debts.length >= 8) return debts;
      }
    }
    return debts;
  }, [items]);

  const examLaneStats = useMemo(() => {
    return EXAM_LANES.map((lane) => {
      const laneItems = items.filter((item) => lane.modules.includes(String(item.module_id || "inbox")));
      const laneDebts = knowledgeDebts.filter((debt) => lane.modules.includes(String(debt.module_id || "inbox")));
      return {
        ...lane,
        itemCount: laneItems.length,
        doneCount: laneItems.filter((item) => item.status === "done").length,
        debtCount: laneDebts.length,
      };
    });
  }, [items, knowledgeDebts]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const j = await apiJson<StudyRoomResponse>("/miniapp-api/studyroom");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setData(j.data || {});
    } catch (e: any) {
      toast(`StudyRoom 加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  async function addItem() {
    const cleanTitle = title.trim();
    const cleanContent = content.trim();
    const cleanUrl = url.trim();
    if (!cleanTitle && !cleanContent && !cleanUrl) {
      toast("先贴一点资料");
      return;
    }
    setSaving(true);
    try {
      const j = await apiJson<StudyRoomResponse>("/miniapp-api/studyroom/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: cleanTitle || cleanUrl || "未命名资料",
          content: cleanContent,
          url: cleanUrl,
          module_id: moduleId,
          source_type: sourceType,
          status: "todo",
        }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      setData(j.data || {});
      setTitle("");
      setContent("");
      setUrl("");
      toast(`已放进 ${moduleLabel(j.item?.module_id, modules)}`);
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function importFile(file: File | null) {
    if (!file || uploading) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("module_id", moduleId);
      if (title.trim()) form.append("title", title.trim());
      const r = await apiFetch("/miniapp-api/studyroom/import", {
        method: "POST",
        body: form,
      });
      const j = (await r.json().catch(() => ({}))) as StudyRoomImportResponse;
      if (!r.ok || !j?.ok) throw new Error(j?.error || `HTTP ${r.status}`);
      setData(j.data || {});
      setTitle("");
      setContent("");
      setUrl("");
      toast(`已导入 ${j.chars || 0} 字，归到 ${moduleLabel(j.item?.module_id, modules)}`);
    } catch (e: any) {
      toast(`导入失败：${e?.message || e}`);
    } finally {
      setUploading(false);
    }
  }

  async function updateItem(item: StudyRoomItem, patch: Partial<StudyRoomItem>) {
    const id = String(item.id || "");
    if (!id) return;
    setSaving(true);
    try {
      const j = await apiJson<StudyRoomResponse>(`/miniapp-api/studyroom/items/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!j?.ok) throw new Error(j?.error || "更新失败");
      setData(j.data || {});
    } catch (e: any) {
      toast(`更新失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function deleteItem(item: StudyRoomItem) {
    const id = String(item.id || "");
    if (!id) return;
    setSaving(true);
    try {
      const j = await apiJson<StudyRoomResponse>(`/miniapp-api/studyroom/items/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (!j?.ok) throw new Error(j?.error || "删除失败");
      setData(j.data || {});
      toast("已删除");
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function addStudyLog() {
    const text = studyLog.trim();
    if (!text) {
      toast("先写今天学了什么");
      return;
    }
    setSaving(true);
    try {
      const j = await apiJson<StudyRoomResponse>("/miniapp-api/studyroom/study-logs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      setData(j.data || {});
      setStudyLog("");
      toast("学习记录已存");
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function copySortPrompt(item: StudyRoomItem) {
    const prompt = buildSortPrompt(item, modules, data.profile);
    try {
      await navigator.clipboard.writeText(prompt);
      toast("整理请求已复制");
    } catch {
      toast("复制失败，可以长按资料内容手动复制");
    }
  }

  async function autoModuleItem(item: StudyRoomItem) {
    const id = String(item.id || "");
    if (!id || classifyingItemId) return;
    setClassifyingItemId(id);
    try {
      const j = await apiJson<StudyRoomAutoModuleResponse>(`/miniapp-api/studyroom/items/${encodeURIComponent(id)}/auto-module`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!j?.ok) throw new Error(j?.error || "归类失败");
      setData(j.data || {});
      toast(`已归到 ${moduleLabel(j.item?.module_id || j.module_id, j.data?.modules || modules)}`);
    } catch (e: any) {
      toast(`归类失败：${e?.message || e}`);
    } finally {
      setClassifyingItemId("");
    }
  }

  async function runCodexSort(item: StudyRoomItem) {
    const id = String(item.id || "");
    if (!id || sortingItemId) return;
    setSortingItemId(id);
    try {
      const created = await apiJson<CodexTaskResponse>(`/miniapp-api/studyroom/items/${encodeURIComponent(id)}/codex-sort`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (created.data) setData(created.data);
      const taskId = String(created.task?.id || "").trim();
      if (!taskId) throw new Error(created.error || "没有拿到整理任务 ID");
      toast("笨笨开始整理了");
      const task = await waitForCodexTask(taskId);
      const response = String(task.response || "").trim();
      if (!response) throw new Error("整理结果为空");
      await updateItem(item, { note: response, status: "done" });
      toast("整理好了，结果写回来了");
    } catch (e: any) {
      toast(`整理失败：${e?.message || e}`);
      try {
        await updateItem(item, { status: "todo" });
      } catch {}
    } finally {
      setSortingItemId("");
    }
  }

  return (
    <div className="min-h-full bg-[#FBFAF4] px-4 pb-8 pt-[calc(env(safe-area-inset-top,0px)+34px)] text-[#342F2A]">
      <section className="relative overflow-hidden rounded-[32px] bg-[#EEE3CD] px-5 py-6 shadow-[0_18px_40px_rgba(94,73,47,0.12)]">
        <div className="absolute -right-8 -top-10 h-36 w-36 rounded-full bg-[#D7B889]/50" />
        <div className="absolute bottom-4 right-5 h-16 w-16 rotate-6 rounded-[18px] border border-[#C79A5A]/30 bg-[#F9F2DF]/70" />
        <div className="relative">
          <div className="text-[11px] font-semibold tracking-[0.24em] text-[#8C6A3D]">STUDYROOM</div>
          <h1 className="mt-2 text-[26px] font-semibold tracking-tight">StudyRoom</h1>
          <p className="mt-3 max-w-[260px] text-[13px] leading-6 text-[#745E43]">
            {data.profile?.target_name || data.profile?.exam_name || "安徽省铜陵市枞阳县村级后备干部考试"}
          </p>
          <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-[#6B5538]">
            <span className="rounded-full bg-white/55 px-3 py-1.5">预计 {data.profile?.expected_month || "2026年7月左右"}</span>
            <span className="rounded-full bg-white/55 px-3 py-1.5">{items.length} 份资料</span>
            <span className="rounded-full bg-white/55 px-3 py-1.5">{logs.length} 条记录</span>
          </div>
        </div>
      </section>

      <section className="mt-5 overflow-hidden rounded-[30px] bg-[#3F392F] p-4 text-[#FFF8EA] shadow-[0_18px_40px_rgba(63,57,47,0.18)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold tracking-[0.22em] text-[#D9C19A]">KNOWLEDGE DEBT</div>
            <h2 className="mt-1 text-[17px] font-semibold">知识债清单</h2>
          </div>
          <span className="rounded-full bg-[#FFF8EA]/12 px-3 py-1.5 text-[11px] text-[#E8D6B8]">{knowledgeDebts.length || "未生成"} 条</span>
        </div>
        {knowledgeDebts.length ? (
          <div className="mt-4 space-y-2">
            {knowledgeDebts.slice(0, 5).map((debt) => (
              <div key={debt.id} className="rounded-2xl bg-[#FFF8EA]/10 px-3 py-3">
                <div className="mb-1 flex flex-wrap gap-1.5 text-[10px] text-[#D9C19A]">
                  <span>{moduleLabel(debt.module_id, modules)}</span>
                  <span>·</span>
                  <span className="line-clamp-1">{debt.title}</span>
                </div>
                <p className="text-[13px] leading-6 text-[#FFF8EA]">{debt.text}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 rounded-2xl bg-[#FFF8EA]/10 px-3 py-3 text-[13px] leading-6 text-[#E8D6B8]">
            让笨笨整理几份资料后，这里会自动收集“还没补齐的坑”。
          </p>
        )}
      </section>

      <section className="mt-5 rounded-[30px] border border-[#EFE2CB] bg-white/90 p-4 shadow-[0_12px_30px_rgba(94,73,47,0.08)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold tracking-[0.22em] text-[#8C6A3D]">EXAM ROUTE</div>
            <h2 className="mt-1 text-[17px] font-semibold">备考路线</h2>
          </div>
          <span className="rounded-full bg-[#F7F0E3] px-3 py-1.5 text-[11px] text-[#6B5538]">按能力拆</span>
        </div>
        <div className="mt-4 space-y-2">
          {examLaneStats.map((lane) => (
            <div key={lane.id} className="rounded-2xl bg-[#FAF5EA] px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[13px] font-semibold text-[#3F392F]">{lane.title}</div>
                  <p className="mt-1 text-[11px] leading-5 text-[#7A6648]">{lane.subtitle}</p>
                </div>
                <div className="shrink-0 text-right text-[11px] leading-5 text-[#8C6A3D]">
                  <div>{lane.itemCount} 份</div>
                  <div>{lane.debtCount} 债</div>
                </div>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#E9D8BC]">
                <div
                  className="h-full rounded-full bg-[#C89B5E]"
                  style={{ width: `${lane.itemCount ? Math.max(12, Math.min(100, Math.round((lane.doneCount / lane.itemCount) * 100))) : 0}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-5 rounded-[28px] border border-[#EFE2CB] bg-white/85 p-4 shadow-[0_10px_28px_rgba(94,73,47,0.07)]">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-[16px] font-semibold">丢进 StudyRoom</h2>
          <span className="text-[11px] text-stone-400">{loading ? "加载中" : "先收，自动归类"}</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <select className="rounded-2xl bg-[#F7F0E3] px-3 py-2 text-[13px] outline-none" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            {Object.entries(SOURCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <select className="rounded-2xl bg-[#F7F0E3] px-3 py-2 text-[13px] outline-none" value={moduleId} onChange={(e) => setModuleId(e.target.value)}>
            {modules.map((module) => <option key={module.id} value={module.id}>{module.label}</option>)}
          </select>
        </div>
        <label
          className={`relative mt-2 flex w-full items-center justify-center overflow-hidden rounded-2xl border border-[#D8C4A5] bg-[#FFFCF5] px-4 py-3 text-[13px] font-semibold text-[#6B5538] transition ${
            uploading ? "cursor-not-allowed opacity-60" : "cursor-pointer active:scale-[0.99]"
          }`}
        >
          <span>{uploading ? "正在导入..." : "上传 PDF / Word / TXT"}</span>
          <input
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
            type="file"
            accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
            disabled={uploading}
            onChange={(e) => {
              const file = e.currentTarget.files?.[0] || null;
              e.currentTarget.value = "";
              void importFile(file);
            }}
          />
        </label>
        <div className="mt-2 text-[11px] leading-5 text-stone-400">支持文字版 PDF、docx、txt、md；选“待整理”时会自动猜模块，扫描版 PDF 先不做 OCR。</div>
        <input
          className="mt-2 w-full rounded-2xl bg-[#F7F0E3] px-3 py-2 text-[13px] outline-none placeholder:text-stone-400"
          placeholder="标题，例如：B站公文写作第一课"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <input
          className="mt-2 w-full rounded-2xl bg-[#F7F0E3] px-3 py-2 text-[13px] outline-none placeholder:text-stone-400"
          placeholder="链接，可空"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <textarea
          className="mt-2 min-h-[112px] w-full resize-none rounded-2xl bg-[#F7F0E3] px-3 py-3 text-[13px] leading-6 outline-none placeholder:text-stone-400"
          placeholder="贴视频简介、网页摘要、错题、自己的备注都行。"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <button
          type="button"
          className="mt-3 w-full rounded-2xl bg-[#3F392F] px-4 py-3 text-[13px] font-semibold text-white transition active:scale-[0.99] disabled:opacity-60"
          disabled={saving}
          onClick={addItem}
        >
          放进 StudyRoom
        </button>
      </section>

      <section className="mt-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-[16px] font-semibold">模块</h2>
          <button className="text-[12px] text-[#8C6A3D]" onClick={() => setModuleFilter("all")}>看全部</button>
        </div>
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
          <button
            className={`shrink-0 rounded-full px-4 py-2 text-[12px] ${moduleFilter === "all" ? "bg-[#3F392F] text-white" : "bg-white text-stone-500"}`}
            onClick={() => setModuleFilter("all")}
          >
            全部 {items.length}
          </button>
          {modules.map((module) => (
            <button
              key={module.id}
              className={`shrink-0 rounded-full px-4 py-2 text-[12px] ${moduleFilter === module.id ? "bg-[#3F392F] text-white" : "bg-white text-stone-500"}`}
              onClick={() => setModuleFilter(module.id)}
            >
              {module.label} {counts.get(module.id) || 0}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-5 space-y-3">
        {visibleItems.map((item) => (
          <article key={String(item.id || "")} className="rounded-[26px] border border-[#EFE2CB] bg-white p-4 shadow-[0_10px_24px_rgba(94,73,47,0.06)]">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="mb-2 flex flex-wrap gap-1.5">
                  <span className="rounded-full bg-[#F4E8D4] px-2.5 py-1 text-[10px] text-[#765C35]">{sourceLabel(item.source_type)}</span>
                  <span className="rounded-full bg-[#EEF0E8] px-2.5 py-1 text-[10px] text-[#697052]">{moduleLabel(item.module_id, modules)}</span>
                  <span className="rounded-full bg-[#E7EFE6] px-2.5 py-1 text-[10px] text-[#4F684F]">{statusLabel(item.status)}</span>
                </div>
                <h3 className="text-[15px] font-semibold leading-6">{item.title || "未命名资料"}</h3>
                <div className="mt-1 text-[11px] text-stone-400">{formatShortTime(item.updated_at || item.created_at)}</div>
              </div>
              <button className="rounded-full bg-[#F7F0E3] px-3 py-1.5 text-[11px] text-[#6B5538]" onClick={() => updateItem(item, { status: nextStatus(item.status) })}>
                切状态
              </button>
            </div>
            {item.url ? <div className="mb-2 break-all rounded-2xl bg-[#FAF5EA] px-3 py-2 text-[12px] leading-5 text-[#765C35]">{item.url}</div> : null}
            {item.content ? <p className="line-clamp-5 whitespace-pre-wrap text-[13px] leading-6 text-stone-600">{item.content}</p> : null}
            {item.note ? (
              <div className="mt-3 max-h-80 overflow-auto rounded-2xl bg-[#F7F0E3] px-3 py-3">
                <div className="mb-2 text-[11px] font-semibold tracking-[0.18em] text-[#8C6A3D]">整理结果</div>
                <div className="whitespace-pre-wrap text-[13px] leading-6 text-stone-700">{item.note}</div>
              </div>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className="rounded-full bg-[#C89B5E] px-3 py-2 text-[12px] font-semibold text-white disabled:opacity-60"
                disabled={Boolean(sortingItemId)}
                onClick={() => void runCodexSort(item)}
              >
                {sortingItemId === String(item.id || "") ? "整理中..." : "让笨笨整理"}
              </button>
              <button className="rounded-full bg-[#3F392F] px-3 py-2 text-[12px] font-semibold text-white" onClick={() => copySortPrompt(item)}>复制整理请求</button>
              <button
                className="rounded-full bg-[#F7F0E3] px-3 py-2 text-[12px] text-[#6B5538] disabled:opacity-60"
                disabled={Boolean(classifyingItemId)}
                onClick={() => void autoModuleItem(item)}
              >
                {classifyingItemId === String(item.id || "") ? "归类中..." : "自动归类"}
              </button>
              <button className="rounded-full bg-[#F7F0E3] px-3 py-2 text-[12px] text-[#6B5538]" onClick={() => updateItem(item, { module_id: "wrong_questions" })}>归到错题</button>
              <button className="rounded-full bg-[#FAE7E2] px-3 py-2 text-[12px] text-[#8A4A3B]" onClick={() => deleteItem(item)}>删除</button>
            </div>
          </article>
        ))}
        {!visibleItems.length ? (
          <div className="rounded-[26px] border border-dashed border-[#E5D5BC] bg-white/60 px-4 py-8 text-center text-[13px] leading-6 text-stone-400">
            这里还空着。看到 B站课、网页、错题就先扔进来。
          </div>
        ) : null}
      </section>

      <section className="mt-5 rounded-[28px] border border-[#EFE2CB] bg-white/85 p-4 shadow-[0_10px_28px_rgba(94,73,47,0.07)]">
        <h2 className="text-[16px] font-semibold">学习记录</h2>
        <textarea
          className="mt-3 min-h-[96px] w-full resize-none rounded-2xl bg-[#F7F0E3] px-3 py-3 text-[13px] leading-6 outline-none placeholder:text-stone-400"
          placeholder="今天看了什么、哪里卡住、下次从哪里继续。"
          value={studyLog}
          onChange={(e) => setStudyLog(e.target.value)}
        />
        <button
          type="button"
          className="mt-3 w-full rounded-2xl bg-[#C89B5E] px-4 py-3 text-[13px] font-semibold text-white transition active:scale-[0.99] disabled:opacity-60"
          disabled={saving}
          onClick={addStudyLog}
        >
          记一笔
        </button>
        <div className="mt-4 space-y-2">
          {logs.slice(0, 5).map((log) => (
            <div key={String(log.id || "")} className="rounded-2xl bg-[#FAF5EA] px-3 py-3">
              <div className="mb-1 text-[11px] text-stone-400">{formatShortTime(log.created_at)}</div>
              <p className="whitespace-pre-wrap text-[13px] leading-6 text-stone-600">{log.content}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
