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

type StudyResultSection = {
  title: string;
  body: string;
};

type ParsedChoiceOption = {
  key: string;
  text: string;
};

type ParsedChoiceQuestion = {
  id: string;
  number: string;
  chapterKey: string;
  chapterTitle: string;
  stem: string;
  options: ParsedChoiceOption[];
  answer?: string;
};

type ParsedQuestionChapter = {
  key: string;
  title: string;
  content: string;
};

type ParsedQuestionGroup = {
  id: string;
  label: string;
  chapterKey: string;
  chapterTitle: string;
  questions: ParsedChoiceQuestion[];
};

type QuizResult = {
  answered: number;
  correct: number;
  gradable: number;
  total: number;
  wrong: number;
  collected: number;
  missingAnswer: number;
};

type ReciteCard = {
  id: string;
  question: string;
  answer: string;
};

type ExamLane = {
  id: string;
  title: string;
  subtitle: string;
  modules: string[];
};

type StudyView = "materials" | "questions" | "notes" | "recite" | "wrong";

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
  chunks?: number;
  items?: StudyRoomItem[];
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
  question_bank: "题库PDF",
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
const MAX_CLIENT_IMPORT_CHARS = 120000;
const MAX_CLIENT_PDF_PAGES = 200;
const STUDYROOM_CHUNK_TARGET_CHARS = 9000;
const STUDYROOM_CHUNK_MAX_CHARS = 12000;
const STUDYROOM_MAX_IMPORT_CHUNKS = 10;
const STUDYROOM_QUIZ_GROUP_SIZE = 20;

function clipClientImportText(text: string): string {
  const clean = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  if (clean.length <= MAX_CLIENT_IMPORT_CHARS) return clean;
  return `${clean.slice(0, MAX_CLIENT_IMPORT_CHARS).trimEnd()}\n\n...[导入时已截断，原文件仍可重新拆分导入]`;
}

function fileStem(file: File): string {
  const name = String(file.name || "").trim();
  return name.replace(/\.[^.]+$/, "").trim() || "未命名资料";
}

function isPdfFile(file: File): boolean {
  const name = String(file.name || "").toLowerCase();
  const type = String(file.type || "").toLowerCase();
  return type === "application/pdf" || name.endsWith(".pdf");
}

function pdfTextContentToLines(items: any[]): string {
  const rows = new Map<number, { x: number; text: string }[]>();
  for (const item of items || []) {
    const text = String(item?.str || "").trim();
    if (!text) continue;
    const transform = Array.isArray(item?.transform) ? item.transform : [];
    const y = Math.round(Number(transform[5] || 0));
    const x = Number(transform[4] || 0);
    const row = rows.get(y) || [];
    row.push({ x, text });
    rows.set(y, row);
  }
  if (!rows.size) {
    return (items || []).map((item) => String(item?.str || "").trim()).filter(Boolean).join(" ");
  }
  return Array.from(rows.entries())
    .sort((a, b) => b[0] - a[0])
    .map(([, row]) => row.sort((a, b) => a.x - b.x).map((part) => part.text).join(" ").replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
}

function isStudyRoomHeading(line: string): boolean {
  const clean = String(line || "").trim();
  if (!clean || clean.length > 90) return false;
  if (/^---\s*第\s*\d+\s*页\s*---$/.test(clean)) return false;
  return [
    /^第[一二三四五六七八九十百千\d]+[章节讲课部分单元]\s*[:：、.\s-]?.{0,60}$/,
    /^[一二三四五六七八九十]+[、.．]\s*\S.{0,60}$/,
    /^\d+(?:\.\d+){0,3}[、.．\s]\s*\S.{0,60}$/,
    /^（[一二三四五六七八九十\d]+）\s*\S.{0,60}$/,
  ].some((pattern) => pattern.test(clean));
}

function chunkLabel(label: string, fallback = "正文"): string {
  const clean = String(label || "").replace(/\s+/g, " ").replace(/^---\s*|\s*---$/g, "").trim();
  return (clean || fallback).slice(0, 36);
}

function splitSectionsByHeadings(text: string): Array<{ label: string; content: string }> {
  const sections: Array<{ label: string; content: string }> = [];
  let label = "开头";
  let lines: string[] = [];
  for (const raw of text.split(/\n/)) {
    const line = raw.trimEnd();
    if (isStudyRoomHeading(line) && lines.length) {
      const content = lines.join("\n").trim();
      if (content) sections.push({ label, content });
      label = line.trim();
      lines = [line];
    } else {
      lines.push(line);
      if (isStudyRoomHeading(line)) label = line.trim();
    }
  }
  const content = lines.join("\n").trim();
  if (content) sections.push({ label, content });
  return sections;
}

function splitSectionsByPages(text: string): Array<{ label: string; content: string }> {
  const sections = text
    .split(/(?=^---\s*第\s*\d+\s*页\s*---$)/m)
    .map((part, index) => {
      const content = part.trim();
      if (!content) return null;
      const firstLine = content.split(/\n/)[0]?.trim() || "";
      const label = /^---\s*第\s*\d+\s*页\s*---$/.test(firstLine) ? firstLine : `第 ${index + 1} 段`;
      return { label, content };
    })
    .filter(Boolean) as Array<{ label: string; content: string }>;
  return sections.length ? sections : [{ label: "正文", content: text.trim() }];
}

function splitLongSection(section: { label: string; content: string }): Array<{ label: string; content: string }> {
  const clean = section.content.trim();
  if (clean.length <= STUDYROOM_CHUNK_MAX_CHARS) return clean ? [section] : [];
  const out: Array<{ label: string; content: string }> = [];
  let current: string[] = [];
  for (let part of clean.split(/\n\s*\n/).map((x) => x.trim()).filter(Boolean)) {
    while (part.length > STUDYROOM_CHUNK_MAX_CHARS) {
      if (current.length) {
        out.push({ label: section.label, content: current.join("\n\n").trim() });
        current = [];
      }
      out.push({ label: section.label, content: part.slice(0, STUDYROOM_CHUNK_MAX_CHARS).trimEnd() });
      part = part.slice(STUDYROOM_CHUNK_MAX_CHARS).trimStart();
    }
    const candidate = [...current, part].join("\n\n").trim();
    if (current.length && candidate.length > STUDYROOM_CHUNK_MAX_CHARS) {
      out.push({ label: section.label, content: current.join("\n\n").trim() });
      current = [part];
    } else {
      current.push(part);
    }
  }
  if (current.length) out.push({ label: section.label, content: current.join("\n\n").trim() });
  return out;
}

function splitStudyRoomText(text: string): Array<{ label: string; content: string }> {
  const clean = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  if (!clean) return [];
  if (clean.length <= STUDYROOM_CHUNK_MAX_CHARS) return [{ label: "正文", content: clean }];

  let sections = splitSectionsByHeadings(clean);
  if (sections.length <= 1) sections = splitSectionsByPages(clean);
  const pieces = sections.flatMap(splitLongSection);
  const chunks: Array<{ label: string; content: string }> = [];
  let currentParts: string[] = [];
  let currentLabels: string[] = [];

  for (const piece of pieces) {
    const candidate = [...currentParts, piece.content].join("\n\n").trim();
    if (currentParts.length && candidate.length > STUDYROOM_CHUNK_TARGET_CHARS) {
      chunks.push({ label: chunkLabel(currentLabels[0] || "正文"), content: currentParts.join("\n\n").trim() });
      currentParts = [piece.content];
      currentLabels = [piece.label];
    } else {
      currentParts.push(piece.content);
      if (piece.label && !currentLabels.includes(piece.label)) currentLabels.push(piece.label);
    }
  }
  if (currentParts.length) chunks.push({ label: chunkLabel(currentLabels[0] || "正文"), content: currentParts.join("\n\n").trim() });
  if (chunks.length > STUDYROOM_MAX_IMPORT_CHUNKS) {
    const kept = chunks.slice(0, STUDYROOM_MAX_IMPORT_CHUNKS);
    kept[kept.length - 1] = {
      ...kept[kept.length - 1],
      content: `${kept[kept.length - 1].content.trimEnd()}\n\n...[后续内容超过自动拆分上限，先保留前面重点段落]`,
    };
    return kept;
  }
  return chunks;
}

function chunkedTitle(baseTitle: string, index: number, total: number, label: string): string {
  const cleanTitle = String(baseTitle || "").trim() || "未命名资料";
  if (total <= 1) return cleanTitle;
  return `${cleanTitle}（${index}/${total}：${chunkLabel(label, `第 ${index} 段`)}）`;
}

async function extractPdfTextInBrowser(file: File, onStatus?: (text: string) => void): Promise<string> {
  onStatus?.("读取 PDF...");
  const [{ getDocument, GlobalWorkerOptions }, workerSrc] = await Promise.all([
    import("pdfjs-dist"),
    import("pdfjs-dist/build/pdf.worker.min.mjs?url"),
  ]);
  GlobalWorkerOptions.workerSrc = String(workerSrc.default || "");

  const data = new Uint8Array(await file.arrayBuffer());
  const pdf = await getDocument({ data }).promise;
  try {
    const pageCount = Math.min(Number(pdf.numPages || 0), MAX_CLIENT_PDF_PAGES);
    const parts: string[] = [];
    for (let pageNo = 1; pageNo <= pageCount; pageNo += 1) {
      onStatus?.(`解析第 ${pageNo}/${pageCount} 页`);
      const page = await pdf.getPage(pageNo);
      const textContent = await page.getTextContent();
      const pageText = pdfTextContentToLines(textContent.items as any[]);
      if (pageText) parts.push(`--- 第 ${pageNo} 页 ---\n${pageText}`);
      if (parts.join("\n\n").length >= MAX_CLIENT_IMPORT_CHARS) break;
    }
    return clipClientImportText(parts.join("\n\n"));
  } finally {
    await pdf.destroy().catch(() => undefined);
  }
}

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

function compactText(value?: string, limit: number = 120): string {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, limit).trim()}...`;
}

function itemInitial(value?: string): string {
  const clean = String(value || "").trim();
  return clean ? clean.slice(0, 1) : "学";
}

function matchesStudyView(item: StudyRoomItem, view: StudyView): boolean {
  const source = String(item.source_type || "");
  const moduleId = String(item.module_id || "");
  const title = String(item.title || "");
  const note = String(item.note || "");
  if (view === "wrong") return moduleId === "wrong_questions" || source === "wrong_question" || source === "fenbi";
  if (view === "notes") return source === "note";
  if (view === "questions") return source === "question_bank" || source === "wrong_question" || source === "fenbi" || /题库|题组|试卷|模拟|练习/.test(title);
  if (view === "recite") return /背诵卡|背诵|速记|口诀/.test(`${title}\n${note}`);
  return moduleId !== "wrong_questions" && source !== "question_bank" && source !== "wrong_question" && source !== "fenbi" && source !== "note";
}

function ArrowLeftIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

function ChevronRightIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

function RefreshIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 12a9 9 0 0 1-15.1 6.6" />
      <path d="M3 12A9 9 0 0 1 18.1 5.4" />
      <path d="M18 2v4h-4" />
      <path d="M6 22v-4h4" />
    </svg>
  );
}

function BookIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
      <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </svg>
  );
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

function notePreview(item: StudyRoomItem): string {
  const note = String(item.note || "").trim();
  if (note) {
    const firstUsefulLine = note
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line && !/^(#{1,6}\s*)?(考点笔记|题型落点|高频问法|易错点|应试用法|背诵卡|卡点预测|知识债清单|练习题|5道练习题)\s*[:：]?$/.test(line));
    return compactText(firstUsefulLine || note, 92);
  }
  return compactText(item.content || item.url || "还没整理，点进去可以看原资料和发起整理。", 92);
}

function splitStudyResult(note?: string): StudyResultSection[] {
  const text = String(note || "").trim();
  if (!text) return [];
  const sectionNames = "(考点笔记|题型落点|高频问法|易错点|应试用法|背诵卡|卡点预测|知识债清单|练习题|5道练习题)";
  const headingRe = new RegExp(`^\\s*(?:#{1,6}\\s*)?(?:\\d+[.、)]\\s*)?${sectionNames}\\s*[:：]?\\s*$`);
  const sections: StudyResultSection[] = [];
  let currentTitle = "";
  let currentLines: string[] = [];

  const flush = () => {
    const body = currentLines.join("\n").trim();
    if (currentTitle || body) sections.push({ title: currentTitle || "整理结果", body });
    currentLines = [];
  };

  for (const rawLine of text.split(/\r?\n/)) {
    const match = rawLine.match(headingRe);
    if (match) {
      flush();
      currentTitle = match[1] || rawLine.trim();
      continue;
    }
    currentLines.push(rawLine);
  }
  flush();
  return sections.filter((section) => section.title || section.body);
}

function normalizeQuizText(value?: string): string {
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function stripQuestionBankAnswerSection(text: string): { body: string; answers: string } {
  const clean = normalizeQuizText(text);
  const matches = Array.from(clean.matchAll(/(?:^|\n)\s*(?:参考答案|答案速查|参考答案及解析|答案解析|参考答案：|答案：)\s*/g));
  if (!matches.length) return { body: clean, answers: "" };
  const last = matches[matches.length - 1];
  const index = typeof last.index === "number" ? last.index : -1;
  if (index < 0 || index < clean.length * 0.35) return { body: clean, answers: "" };
  return {
    body: clean.slice(0, index).trim(),
    answers: clean.slice(index).trim(),
  };
}

function normalizeChapterTitle(value?: string): string {
  return String(value || "")
    .replace(/^---\s*|\s*---$/g, "")
    .replace(/\s+/g, " ")
    .trim() || "未分章";
}

function chapterKeyForTitle(title: string, index: number): string {
  const clean = normalizeChapterTitle(title)
    .replace(/[^\u4e00-\u9fa5a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return `${index}-${clean || "chapter"}`;
}

function chapterTitlesMatch(a?: string, b?: string): boolean {
  const left = normalizeChapterTitle(a).replace(/\s+/g, "");
  const right = normalizeChapterTitle(b).replace(/\s+/g, "");
  if (!left || !right) return false;
  return left === right || left.includes(right) || right.includes(left);
}

function isQuestionBankChapterHeading(line: string): boolean {
  const clean = normalizeChapterTitle(line);
  if (!clean || clean.length > 80) return false;
  if (/^---\s*第\s*\d+\s*页\s*---$/.test(clean)) return false;
  if (/^\d{1,4}\s*[、.．)]\s*\S/.test(clean)) return false;
  if (/^[A-H]\s*[.．、)]\s*/i.test(clean)) return false;
  if (/^(?:参考答案|答案速查|参考答案及解析|答案解析|答案)\s*[:：]?$/.test(clean)) return true;
  if (/^第[一二三四五六七八九十百千万零〇\d]+[章节编篇部分单元讲]\s*[:：、.\s-]?.{0,50}$/.test(clean)) return true;
  if (/^(?:专题|模块|单元|章节)\s*[一二三四五六七八九十百千万零〇\d]+[：:、.\s-]?.{0,50}$/.test(clean)) return true;
  if (/^(?:法理学|宪法|民法|刑法|行政法|经济法|商法|诉讼法|党建|时政|三农|乡村振兴|基层治理|村务管理|公文写作|计算机)(?:\s|$|[：:、-]).{0,32}$/.test(clean)) return true;
  return false;
}

function splitQuizTextByChapters(text: string, fallbackTitle = "未分章"): ParsedQuestionChapter[] {
  const clean = normalizeQuizText(text);
  if (!clean) return [];
  const segments: ParsedQuestionChapter[] = [];
  let currentTitle = fallbackTitle;
  let currentLines: string[] = [];

  const flush = () => {
    const content = currentLines.join("\n").trim();
    if (!content) return;
    segments.push({
      key: chapterKeyForTitle(currentTitle, segments.length + 1),
      title: normalizeChapterTitle(currentTitle),
      content,
    });
    currentLines = [];
  };

  for (const raw of clean.split(/\n/)) {
    const line = raw.trim();
    if (isQuestionBankChapterHeading(line)) {
      flush();
      currentTitle = line;
      continue;
    }
    currentLines.push(raw);
  }
  flush();
  return segments.length ? segments : [{ key: chapterKeyForTitle(fallbackTitle, 1), title: normalizeChapterTitle(fallbackTitle), content: clean }];
}

function parseAnswerEntries(text: string): Array<{ number: string; answer: string }> {
  const entries: Array<{ number: string; answer: string }> = [];
  const answerText = normalizeQuizText(text);
  if (!answerText) return entries;
  const normalized = answerText
    .replace(/【\s*答案\s*】/g, "答案")
    .replace(/正确答案/g, "答案")
    .replace(/([。；;，,])\s*/g, "$1 ");
  const patterns = [
    /(?:^|[\s。；;，,])(?:第\s*)?(\d{1,4})\s*(?:题)?\s*[.、:：）)]?\s*(?:答案\s*[:：]?)?\s*([A-H]{1,6})(?=$|[\s。；;，,])/gi,
    /(?:^|\n)\s*(\d{1,4})\s*(?:题)?\s*答案\s*[:：]?\s*([A-H]{1,6})/gi,
  ];
  const seen = new Set<string>();
  for (const pattern of patterns) {
    for (const match of normalized.matchAll(pattern)) {
      const number = String(match[1] || "").trim();
      const answer = String(match[2] || "").toUpperCase().replace(/[^A-H]/g, "");
      const key = `${number}:${answer}:${match.index ?? entries.length}`;
      if (number && answer && !seen.has(key)) {
        entries.push({ number, answer });
        seen.add(key);
      }
    }
  }
  return entries;
}

function buildAnswerLookup(answerText: string, questions: ParsedChoiceQuestion[]): Map<string, string> {
  const lookup = new Map<string, string>();
  const answerSegments = splitQuizTextByChapters(answerText, "参考答案");
  const globalBuckets = new Map<string, Set<string>>();
  const allEntries: Array<{ number: string; answer: string }> = [];

  for (const segment of answerSegments) {
    const entries = parseAnswerEntries(segment.content);
    allEntries.push(...entries);
    const hasSpecificChapter = segment.title !== "参考答案" && !/^(?:参考答案|答案速查|参考答案及解析|答案解析|答案)/.test(segment.title);
    if (hasSpecificChapter) {
      const matchedChapter = questions.find((question) => chapterTitlesMatch(question.chapterTitle, segment.title));
      if (matchedChapter) {
        for (const entry of entries) lookup.set(`${matchedChapter.chapterKey}:${entry.number}`, entry.answer);
      }
    }
    for (const entry of entries) {
      const bucket = globalBuckets.get(entry.number) || new Set<string>();
      bucket.add(entry.answer);
      globalBuckets.set(entry.number, bucket);
    }
  }

  for (const [number, bucket] of globalBuckets.entries()) {
    if (bucket.size === 1) lookup.set(`global:${number}`, Array.from(bucket)[0]);
  }

  let cursor = 0;
  for (const question of questions) {
    if (lookup.has(`${question.chapterKey}:${question.number}`) || lookup.has(`global:${question.number}`)) continue;
    const nextIndex = allEntries.findIndex((entry, index) => index >= cursor && entry.number === question.number);
    if (nextIndex >= 0) {
      lookup.set(`question:${question.id}`, allEntries[nextIndex].answer);
      cursor = nextIndex + 1;
    }
  }

  return lookup;
}

function parseChoiceOptions(block: string): { stem: string; options: ParsedChoiceOption[] } {
  const optionReady = normalizeQuizText(block)
    .replace(/([^\n])\s+([A-H])\s*[.．、)]\s*/g, "$1\n$2. ")
    .replace(/([^\n])([A-H])\s*[.．、)]\s*/g, "$1\n$2. ");
  const optionRe = /(?:^|\n)\s*([A-H])\s*[.．、)]\s*([\s\S]*?)(?=\n\s*[A-H]\s*[.．、)]\s*|$)/g;
  const matches = Array.from(optionReady.matchAll(optionRe));
  const options = matches
    .map((match) => ({
      key: String(match[1] || "").toUpperCase(),
      text: compactText(String(match[2] || "").replace(/\n+/g, " "), 220),
    }))
    .filter((option) => option.key && option.text);
  const firstOptionIndex = matches.length && typeof matches[0].index === "number" ? matches[0].index : -1;
  const stem = (firstOptionIndex >= 0 ? optionReady.slice(0, firstOptionIndex) : optionReady)
    .replace(/^\s*\d{1,4}\s*[、.．)]\s*/, "")
    .replace(/\n+/g, " ")
    .trim();
  return { stem, options };
}

function parseChoiceQuestions(text: string, itemKey: string): ParsedChoiceQuestion[] {
  const { body, answers } = stripQuestionBankAnswerSection(text);
  const chapters = splitQuizTextByChapters(body);
  const questions: ParsedChoiceQuestion[] = [];
  for (const chapter of chapters) {
    const markerRe = /(?:^|\n)\s*(\d{1,4})\s*[、.．)]\s*(?=\S)/g;
    const markers = Array.from(chapter.content.matchAll(markerRe));
    for (let index = 0; index < markers.length; index += 1) {
      const marker = markers[index];
      const start = typeof marker.index === "number" ? marker.index : 0;
      const end = index + 1 < markers.length && typeof markers[index + 1].index === "number" ? Number(markers[index + 1].index) : chapter.content.length;
      const rawBlock = chapter.content.slice(start, end).trim();
      const number = String(marker[1] || index + 1);
      const { stem, options } = parseChoiceOptions(rawBlock);
      if (!stem || options.length < 2) continue;
      const inlineAnswer = rawBlock.match(/(?:答案|正确答案)\s*[:：]?\s*([A-H]{1,6})/i)?.[1];
      questions.push({
        id: `${itemKey}-${chapter.key}-${number}-${questions.length}`,
        number,
        chapterKey: chapter.key,
        chapterTitle: chapter.title,
        stem: compactText(stem, 320),
        options: options.slice(0, 8),
        answer: inlineAnswer ? normalizedAnswer(inlineAnswer) : undefined,
      });
    }
  }
  const answerLookup = buildAnswerLookup(answers, questions);
  for (const question of questions) {
    question.answer = question.answer
      || answerLookup.get(`${question.chapterKey}:${question.number}`)
      || answerLookup.get(`question:${question.id}`)
      || answerLookup.get(`global:${question.number}`)
      || undefined;
  }
  return questions.slice(0, 300);
}

function parseReciteCards(note?: string): ReciteCard[] {
  const cardSection = splitStudyResult(note).find((section) => section.title === "背诵卡");
  const body = normalizeQuizText(cardSection?.body || "");
  if (!body) return [];
  const cards: ReciteCard[] = [];
  const oneLineRe = /(?:^|\n)\s*(?:[-*•]\s*)?(?:Q|问|问题)\s*[:：]\s*([\s\S]*?)\s*(?:A|答|答案)\s*[:：]\s*([^\n]+)/gi;
  for (const match of body.matchAll(oneLineRe)) {
    const question = compactText(String(match[1] || ""), 140);
    const answer = compactText(String(match[2] || ""), 220);
    if (question && answer) cards.push({ id: `recite-${cards.length}`, question, answer });
    if (cards.length >= 12) return cards;
  }
  if (cards.length) return cards;

  const lines = body.split(/\n/).map((line) => line.replace(/^\s*[-*•\d.、)]\s*/, "").trim()).filter(Boolean);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const pair = line.match(/^(.+?[？?])\s*(.+)$/);
    if (pair) {
      cards.push({ id: `recite-${cards.length}`, question: compactText(pair[1], 140), answer: compactText(pair[2], 220) });
    } else if (lines[index + 1]) {
      cards.push({ id: `recite-${cards.length}`, question: compactText(line, 140), answer: compactText(lines[index + 1], 220) });
      index += 1;
    }
    if (cards.length >= 12) break;
  }
  return cards;
}

function buildQuestionGroups(questions: ParsedChoiceQuestion[], size = STUDYROOM_QUIZ_GROUP_SIZE): ParsedQuestionGroup[] {
  const groups: ParsedQuestionGroup[] = [];
  const chapters: Array<{ key: string; title: string; questions: ParsedChoiceQuestion[] }> = [];
  for (const question of questions) {
    let chapter = chapters.find((item) => item.key === question.chapterKey);
    if (!chapter) {
      chapter = { key: question.chapterKey, title: question.chapterTitle, questions: [] };
      chapters.push(chapter);
    }
    chapter.questions.push(question);
  }
  for (const chapter of chapters) {
    const chunkCount = Math.ceil(chapter.questions.length / size) || 1;
    for (let index = 0; index < chapter.questions.length; index += size) {
      const chunkIndex = Math.floor(index / size);
      const chunk = chapter.questions.slice(index, index + size);
      const chapterLabel = chapter.title === "未分章" ? `第 ${groups.length + 1} 组` : chapter.title;
      groups.push({
        id: `${chapter.key}-${chunkIndex}`,
        label: chunkCount > 1 && chapter.title !== "未分章" ? `${chapterLabel} ${chunkIndex + 1}/${chunkCount}` : chapterLabel,
        chapterKey: chapter.key,
        chapterTitle: chapter.title,
        questions: chunk,
      });
    }
  }
  return groups;
}

function uploadSourceTypeForFile(file: File, selectedSourceType: string): string {
  const selected = String(selectedSourceType || "").trim();
  if (isPdfFile(file)) {
    if (["question_bank", "wrong_question", "fenbi", "note"].includes(selected)) return selected;
    return "pdf";
  }
  if (["question_bank", "wrong_question", "fenbi", "note"].includes(selected)) return selected;
  return "";
}

function quizGroupKey(item: StudyRoomItem, groupId: string | number): string {
  return `${item.id || item.title || "item"}::group::${groupId}`;
}

function normalizedAnswer(value?: string): string {
  return String(value || "").toUpperCase().replace(/[^A-H]/g, "");
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
  const [uploadStatus, setUploadStatus] = useState("");
  const [moduleFilter, setModuleFilter] = useState("all");
  const [studyView, setStudyView] = useState<StudyView>("materials");
  const [sourceType, setSourceType] = useState("bilibili");
  const [moduleId, setModuleId] = useState("inbox");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [studyLog, setStudyLog] = useState("");
  const [sortingItemId, setSortingItemId] = useState("");
  const [classifyingItemId, setClassifyingItemId] = useState("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [quizGroupIndex, setQuizGroupIndex] = useState(0);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>({});
  const [quizResults, setQuizResults] = useState<Record<string, QuizResult>>({});
  const [recitedCards, setRecitedCards] = useState<Record<string, boolean>>({});

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
    const list = items
      .slice()
      .sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")))
      .filter((item) => matchesStudyView(item, studyView));
    if (moduleFilter === "all") return list;
    return list.filter((item) => String(item.module_id || "inbox") === moduleFilter);
  }, [items, moduleFilter, studyView]);

  const selectedItem = useMemo(
    () => items.find((item) => String(item.id || "") === selectedItemId) || null,
    [items, selectedItemId],
  );

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

  const viewCounts = useMemo(() => {
    const out: Record<StudyView, number> = {
      materials: 0,
      questions: 0,
      notes: 0,
      recite: 0,
      wrong: 0,
    };
    const scopedItems = moduleFilter === "all" ? items : items.filter((item) => String(item.module_id || "inbox") === moduleFilter);
    (Object.keys(out) as StudyView[]).forEach((view) => {
      out[view] = scopedItems.filter((item) => matchesStudyView(item, view)).length;
    });
    return out;
  }, [items, moduleFilter]);

  const pendingItems = useMemo(
    () => items.filter((item) => item.status !== "done").sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""))),
    [items],
  );

  const doneItemsCount = useMemo(() => items.filter((item) => item.status === "done").length, [items]);

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

  useEffect(() => {
    setQuizGroupIndex(0);
  }, [selectedItemId]);

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
    setUploadStatus("");
    try {
      const uploadSourceType = uploadSourceTypeForFile(file, sourceType);
      if (isPdfFile(file)) {
        const text = await extractPdfTextInBrowser(file, setUploadStatus);
        if (!text) throw new Error("没有抽到文字；扫描版 PDF/图片需要 OCR，当前还没接。");
        const chunks = splitStudyRoomText(text);
        if (!chunks.length) throw new Error("没有抽到可保存的文字");
        const baseTitle = title.trim() || fileStem(file);
        const createdItems: StudyRoomItem[] = [];
        for (let index = 0; index < chunks.length; index += 1) {
          const chunk = chunks[index];
          setUploadStatus(chunks.length > 1 ? `保存第 ${index + 1}/${chunks.length} 段...` : "保存中...");
          const j = await apiJson<StudyRoomResponse>("/miniapp-api/studyroom/items", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              title: chunkedTitle(baseTitle, index + 1, chunks.length, chunk.label),
              content: chunk.content,
              module_id: moduleId,
              source_type: uploadSourceType || "pdf",
              status: "todo",
              note: chunks.length > 1
                ? `本地解析 PDF：${file.name || "资料.pdf"}\n自动拆分：第 ${index + 1}/${chunks.length} 段 · ${chunkLabel(chunk.label, `第 ${index + 1} 段`)}`
                : `本地解析 PDF：${file.name || "资料.pdf"}`,
            }),
          });
          if (!j?.ok) throw new Error(j?.error || "保存失败");
          if (j.item) createdItems.push(j.item);
          setData(j.data || {});
        }
        setTitle("");
        setContent("");
        setUrl("");
        if (uploadSourceType === "question_bank") {
          setStudyView("questions");
          toast(chunks.length > 1 ? `题库已拆成 ${chunks.length} 段，可按题组练` : `题库已导入，解析到 ${parseChoiceQuestions(text, fileStem(file)).length} 道选择题`);
        } else {
          toast(chunks.length > 1 ? `已拆成 ${chunks.length} 段，开始逐段整理` : `已导入 ${text.length || 0} 字，开始整理`);
          if (createdItems.length) void sortItemsSequentially(createdItems);
        }
        return;
      }
      setUploadStatus("上传中...");
      const form = new FormData();
      form.append("file", file);
      form.append("module_id", moduleId);
      if (uploadSourceType) form.append("source_type", uploadSourceType);
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
      const importedItems = Array.isArray(j.items) && j.items.length ? j.items : (j.item ? [j.item] : []);
      if (uploadSourceType === "question_bank") {
        setStudyView("questions");
        toast((j.chunks || importedItems.length || 1) > 1 ? `题库已拆成 ${j.chunks || importedItems.length} 段` : `题库已导入 ${j.chars || 0} 字`);
      } else {
        toast((j.chunks || importedItems.length || 1) > 1 ? `已拆成 ${j.chunks || importedItems.length} 段，开始逐段整理` : `已导入 ${j.chars || 0} 字，开始整理`);
        if (importedItems.length) void sortItemsSequentially(importedItems);
      }
    } catch (e: any) {
      toast(`导入失败：${e?.message || e}`);
    } finally {
      setUploading(false);
      setUploadStatus("");
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

  async function copyText(text: string, label: string = "内容") {
    try {
      await navigator.clipboard.writeText(text);
      toast(`${label}已复制`);
    } catch {
      toast("复制失败，可以长按内容手动复制");
    }
  }

  async function submitQuestionGroup(item: StudyRoomItem, questions: ParsedChoiceQuestion[], groupId: string | number) {
    if (!questions.length || saving) return;
    const groupKey = quizGroupKey(item, groupId);
    const answered = questions.filter((question) => quizAnswers[question.id]);
    const gradable = questions.filter((question) => normalizedAnswer(question.answer));
    const wrongQuestions = questions.filter((question) => {
      const answer = normalizedAnswer(question.answer);
      const chosen = normalizedAnswer(quizAnswers[question.id]);
      return answer && chosen && chosen !== answer;
    });
    const correct = questions.filter((question) => {
      const answer = normalizedAnswer(question.answer);
      const chosen = normalizedAnswer(quizAnswers[question.id]);
      return answer && chosen && chosen === answer;
    }).length;
    let collected = 0;
    setSaving(true);
    try {
      const existingTitles = new Set(items.map((row) => String(row.title || "").trim()));
      for (const question of wrongQuestions) {
        const chapterPart = question.chapterTitle && question.chapterTitle !== "未分章" ? ` · ${question.chapterTitle}` : "";
        const wrongTitle = `错题：${item.title || "题库"}${chapterPart} · 第${question.number}题`;
        if (existingTitles.has(wrongTitle)) continue;
        const optionsText = question.options.map((option) => `${option.key}. ${option.text}`).join("\n");
        const chosen = normalizedAnswer(quizAnswers[question.id]) || "未选";
        const answer = normalizedAnswer(question.answer) || "未匹配";
        const j = await apiJson<StudyRoomResponse>("/miniapp-api/studyroom/items", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: wrongTitle,
            content: `${question.stem}\n${optionsText}`,
            module_id: "wrong_questions",
            source_type: "wrong_question",
            status: "todo",
            note: `来源：${item.title || "题库"}\n章节：${question.chapterTitle || "未分章"}\n题号：${question.number}\n我的答案：${chosen}\n正确答案：${answer}\n复盘方向：回到原题库对应章节，把这题涉及的概念重新背一遍。`,
          }),
        });
        if (!j?.ok) throw new Error(j?.error || "错题收录失败");
        existingTitles.add(wrongTitle);
        collected += 1;
        if (j.data) setData(j.data);
      }
      setQuizResults((prev) => ({
        ...prev,
        [groupKey]: {
          answered: answered.length,
          correct,
          gradable: gradable.length,
          total: questions.length,
          wrong: wrongQuestions.length,
          collected,
          missingAnswer: questions.length - gradable.length,
        },
      }));
      toast(`本组 ${correct}/${gradable.length || questions.length}，错题收录 ${collected} 道`);
    } catch (e: any) {
      toast(`提交失败：${e?.message || e}`);
    } finally {
      setSaving(false);
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

  async function runCodexSortItem(item: StudyRoomItem): Promise<void> {
    const id = String(item.id || "");
    if (!id) throw new Error("资料 ID 为空");
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
      const task = await waitForCodexTask(taskId);
      const response = String(task.response || "").trim();
      if (!response) throw new Error("整理结果为空");
      const updated = await apiJson<StudyRoomResponse>(`/miniapp-api/studyroom/items/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: response, status: "done" }),
      });
      if (updated.data) setData(updated.data);
    } catch (e: any) {
      try {
        const reverted = await apiJson<StudyRoomResponse>(`/miniapp-api/studyroom/items/${encodeURIComponent(id)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "todo" }),
        });
        if (reverted.data) setData(reverted.data);
      } catch {}
      throw e;
    } finally {
      setSortingItemId("");
    }
  }

  async function runCodexSort(item: StudyRoomItem) {
    if (sortingItemId) return;
    try {
      toast("笨笨开始整理了");
      await runCodexSortItem(item);
      toast("整理好了，结果写回来了");
    } catch (e: any) {
      toast(`整理失败：${e?.message || e}`);
    }
  }

  async function sortItemsSequentially(targetItems: StudyRoomItem[]) {
    if (sortingItemId) return;
    const queue = targetItems.filter((item) => String(item.id || "").trim());
    if (!queue.length) return;
    let done = 0;
    for (let index = 0; index < queue.length; index += 1) {
      try {
        if (queue.length > 1) toast(`整理第 ${index + 1}/${queue.length} 段`);
        await runCodexSortItem(queue[index]);
        done += 1;
      } catch (e: any) {
        toast(`第 ${index + 1} 段整理失败：${e?.message || e}`);
        break;
      }
    }
    if (queue.length > 1 && done) toast(`已整理 ${done}/${queue.length} 段`);
  }

  if (selectedItem) {
    const resultSections = splitStudyResult(selectedItem.note);
    const sourceText = String(selectedItem.content || selectedItem.url || "").trim();
    const selectedId = String(selectedItem.id || "");
    const shouldParseQuiz = matchesStudyView(selectedItem, "questions") || /题库|题组|试卷|模拟/.test(String(selectedItem.title || ""));
    const parsedQuestions = shouldParseQuiz ? parseChoiceQuestions(`${selectedItem.content || ""}\n\n${selectedItem.note || ""}`, selectedId || selectedItem.title || "studyroom") : [];
    const questionGroups = buildQuestionGroups(parsedQuestions);
    const safeQuizGroupIndex = questionGroups.length ? Math.min(quizGroupIndex, questionGroups.length - 1) : 0;
    const activeQuestionGroupMeta = questionGroups[safeQuizGroupIndex] || null;
    const activeQuestionGroup = activeQuestionGroupMeta?.questions || [];
    const activeQuizResult = activeQuestionGroupMeta ? quizResults[quizGroupKey(selectedItem, activeQuestionGroupMeta.id)] : undefined;
    const reciteCards = parseReciteCards(selectedItem.note);
    return (
      <div className="min-h-full bg-white pb-8 text-black">
        <header className="sticky top-0 z-20 bg-white px-5 pt-[calc(env(safe-area-inset-top,0px)+0px)]">
          <nav className="flex h-16 items-center justify-between">
            <button
              type="button"
              className="-ml-2 flex h-10 w-10 items-center justify-center rounded-lg text-black active:bg-[#F7F7F7]"
              aria-label="返回模块"
              onClick={() => setSelectedItemId("")}
            >
              <ArrowLeftIcon />
            </button>
            <div className="text-[11px] font-bold uppercase text-[#707070]">资料详情</div>
            <div className="h-10 w-10" />
          </nav>
        </header>

        <main className="px-5">
          <h1 className="mt-6 text-[28px] font-bold leading-9">{selectedItem.title || "未命名资料"}</h1>
          <p className="mt-2 text-[13px] text-[#707070]">{formatShortTime(selectedItem.updated_at || selectedItem.created_at) || "还没有时间记录"}</p>

          <section className="mt-6 divide-y divide-[#F0F0F0] border-y border-[#F0F0F0]">
            {[
              ["资料来源", sourceLabel(selectedItem.source_type)],
              ["归属模块", moduleLabel(selectedItem.module_id, modules)],
              ["整理状态", statusLabel(selectedItem.status)],
            ].map(([label, value]) => (
              <div key={label} className="flex min-h-[56px] items-center gap-4 py-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#F7F7F7] text-[12px] font-bold text-black">
                  {String(value || label).slice(0, 1)}
                </div>
                <div className="flex-1 text-[14px] font-semibold">{label}</div>
                <div className="max-w-[150px] truncate text-right text-[12px] text-[#707070]">{value}</div>
              </div>
            ))}
          </section>

          <button
            type="button"
            className="mt-8 w-full rounded-2xl border-0 bg-black px-5 py-5 text-left text-white shadow-[0_16px_34px_rgba(0,0,0,0.16)] active:scale-[0.995] disabled:opacity-60"
            disabled={Boolean(sortingItemId)}
            onClick={() => void runCodexSort(selectedItem)}
          >
            <div className="text-[11px] font-bold uppercase text-white/55">Study Action</div>
            <h2 className="mt-1 text-[20px] font-semibold">{sortingItemId === selectedId ? "正在整理这份资料" : selectedItem.note ? "重新生成学习方向" : "生成学习方向"}</h2>
            <p className="mt-2 text-[13px] leading-5 text-white/55">考点笔记、背诵卡、知识债和练习题会写回这个页面。</p>
          </button>

          {parsedQuestions.length ? (
            <section className="mt-8">
              <div className="mb-4 flex items-end justify-between">
                <h2 className="text-[20px] font-semibold">题组训练</h2>
                <span className="text-[11px] font-bold uppercase text-[#707070]">{parsedQuestions.length} 题</span>
              </div>
              <div className="-mx-5 flex overflow-x-auto px-5 pb-2 no-scrollbar">
                {questionGroups.map((group, index) => (
                  <button
                    key={group.id}
                    type="button"
                    className={`mr-2 shrink-0 rounded-lg px-3 py-2 text-[12px] font-semibold ${
                      safeQuizGroupIndex === index ? "bg-black text-white" : "bg-[#F7F7F7] text-black"
                    }`}
                    onClick={() => setQuizGroupIndex(index)}
                  >
                    {group.label} · {group.questions.length}题
                  </button>
                ))}
              </div>
              <div className="mt-3 space-y-4">
                {activeQuestionGroup.map((question, index) => {
                  const chosen = normalizedAnswer(quizAnswers[question.id]);
                  const answer = normalizedAnswer(question.answer);
                  const submitted = Boolean(activeQuizResult);
                  return (
                    <div key={question.id} className="rounded-xl border border-[#EEEEEE] p-4">
                      <div className="mb-3 text-[11px] font-bold uppercase text-[#707070]">
                        {question.chapterTitle && question.chapterTitle !== "未分章" ? `${question.chapterTitle} · ` : ""}第 {question.number || index + 1} 题
                      </div>
                      <div className="text-[15px] font-semibold leading-7">{question.stem}</div>
                      <div className="mt-4 space-y-2">
                        {question.options.map((option) => {
                          const optionKey = normalizedAnswer(option.key);
                          const isChosen = chosen === optionKey;
                          const isCorrect = submitted && answer && answer === optionKey;
                          const isWrongChoice = submitted && isChosen && answer && answer !== optionKey;
                          return (
                            <button
                              key={`${question.id}-${option.key}`}
                              type="button"
                              className={`flex w-full items-start gap-3 rounded-xl border px-3 py-3 text-left text-[13px] leading-6 ${
                                isCorrect
                                  ? "border-[#22C55E] bg-[#DCFCE7] text-[#166534]"
                                  : isWrongChoice
                                    ? "border-[#EF4444] bg-[#FEE2E2] text-[#991B1B]"
                                    : isChosen
                                      ? "border-[#E67E22] bg-[#FFF4E8] text-[#7C3D0A]"
                                      : "border-[#EEEEEE] bg-[#F7F7F7] text-[#333333]"
                              }`}
                              onClick={() => {
                                if (submitted) return;
                                setQuizAnswers((prev) => ({ ...prev, [question.id]: optionKey }));
                              }}
                            >
                              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current text-[11px] font-bold">{option.key}</span>
                              <span>{option.text}</span>
                            </button>
                          );
                        })}
                      </div>
                      {submitted ? (
                        <div className="mt-3 rounded-lg bg-[#F7F7F7] px-3 py-2 text-[12px] leading-5 text-[#707070]">
                          {answer ? `正确答案：${answer}${chosen ? ` · 你选：${chosen}` : " · 你未作答"}` : "这题没匹配到答案，先不计分。"}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
              <button
                type="button"
                className="mt-4 w-full rounded-lg bg-black px-4 py-4 text-[13px] font-semibold text-white active:scale-[0.99] disabled:opacity-60"
                disabled={saving || Boolean(activeQuizResult)}
                onClick={() => void submitQuestionGroup(selectedItem, activeQuestionGroup, activeQuestionGroupMeta?.id || safeQuizGroupIndex)}
              >
                {activeQuizResult ? `已提交：${activeQuizResult.correct}/${activeQuizResult.gradable || activeQuizResult.total}` : "提交本组并收录错题"}
              </button>
              {activeQuizResult ? (
                <div className="mt-3 rounded-xl bg-[#FFF4E8] px-4 py-3 text-[12px] leading-6 text-[#7C3D0A]">
                  本组已答 {activeQuizResult.answered}/{activeQuizResult.total}，可评分 {activeQuizResult.gradable} 题，错 {activeQuizResult.wrong} 题，已收录 {activeQuizResult.collected} 道。
                  {activeQuizResult.missingAnswer ? ` 还有 ${activeQuizResult.missingAnswer} 题没匹配到参考答案。` : ""}
                </div>
              ) : null}
            </section>
          ) : selectedItem.source_type === "question_bank" ? (
            <section className="mt-8 rounded-xl bg-[#FFF4E8] px-4 py-4 text-[13px] leading-6 text-[#7C3D0A]">
              这份题库还没识别出标准选择题。常见原因是扫描版 PDF、选项被排成图片，或者答案区格式太散；这种先让笨笨整理，别硬刷。
            </section>
          ) : null}

          {reciteCards.length ? (
            <section className="mt-8">
              <div className="mb-4 flex items-end justify-between">
                <h2 className="text-[20px] font-semibold">背诵卡</h2>
                <span className="text-[11px] font-bold uppercase text-[#707070]">{reciteCards.filter((card) => recitedCards[`${selectedId}-${card.id}`]).length}/{reciteCards.length}</span>
              </div>
              <div className="space-y-3">
                {reciteCards.map((card) => {
                  const cardKey = `${selectedId}-${card.id}`;
                  const remembered = Boolean(recitedCards[cardKey]);
                  return (
                    <button
                      key={card.id}
                      type="button"
                      className={`w-full rounded-xl p-4 text-left active:scale-[0.995] ${remembered ? "bg-[#DCFCE7]" : "bg-[#F7F7F7]"}`}
                      onClick={() => setRecitedCards((prev) => ({ ...prev, [cardKey]: !prev[cardKey] }))}
                    >
                      <div className="text-[11px] font-bold uppercase text-[#707070]">{remembered ? "已背" : "待背"}</div>
                      <div className="mt-2 text-[14px] font-semibold leading-6">{card.question}</div>
                      <div className="mt-2 text-[13px] leading-6 text-[#707070]">{card.answer}</div>
                    </button>
                  );
                })}
              </div>
            </section>
          ) : null}

          <section className="mt-8">
            <div className="mb-4 flex items-end justify-between">
              <h2 className="text-[20px] font-semibold">整理结果</h2>
              <span className="text-[11px] font-bold uppercase text-[#707070]">{resultSections.length ? `${resultSections.length} 段` : "未生成"}</span>
            </div>
            {resultSections.length ? (
              <div className="space-y-3">
                {resultSections.map((section, index) => (
                  <div key={`${section.title}-${index}`} className="border-l-4 border-[#E67E22] bg-[#F7F7F7] py-4 pl-4 pr-3">
                    <div className="mb-2 text-[13px] font-bold text-black">{section.title}</div>
                    <div className="whitespace-pre-wrap text-[13px] leading-6 text-[#333333]">{section.body || "（这一段暂时为空）"}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl bg-[#F7F7F7] px-4 py-5 text-[13px] leading-6 text-[#707070]">
                这份资料还没有整理结果。点上面的“生成学习方向”，这里只保留整理后的东西，不把 PDF 原文塞满屏幕。
              </div>
            )}
          </section>

          {sourceText ? (
            <section className="mt-8">
              <div className="mb-4 flex items-end justify-between">
                <h2 className="text-[20px] font-semibold">原资料预览</h2>
                <button className="rounded-lg bg-[#F7F7F7] px-3 py-2 text-[12px] font-semibold text-black" onClick={() => void copyText(sourceText, "原资料")}>
                  复制
                </button>
              </div>
              <div className="max-h-[280px] overflow-auto rounded-xl bg-[#F7F7F7] px-4 py-4 whitespace-pre-wrap text-[12px] leading-6 text-[#707070]">
                {sourceText}
              </div>
            </section>
          ) : null}

          <section className="mt-8">
            <div className="mb-4 flex items-end justify-between">
              <h2 className="text-[20px] font-semibold">操作</h2>
              <span className="text-[11px] font-bold uppercase text-[#707070]">Manage</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button className="rounded-xl bg-[#F7F7F7] px-3 py-3 text-[12px] font-semibold text-black" onClick={() => void updateItem(selectedItem, { status: nextStatus(selectedItem.status) })}>
                切状态
              </button>
              <button
                className="rounded-xl bg-[#F7F7F7] px-3 py-3 text-[12px] font-semibold text-black disabled:opacity-60"
                disabled={Boolean(classifyingItemId)}
                onClick={() => void autoModuleItem(selectedItem)}
              >
                {classifyingItemId === selectedId ? "归类中..." : "自动归类"}
              </button>
              <button className="rounded-xl bg-[#F7F7F7] px-3 py-3 text-[12px] font-semibold text-black" onClick={() => void copySortPrompt(selectedItem)}>
                复制整理请求
              </button>
              <button className="rounded-xl bg-[#FFF4E8] px-3 py-3 text-[12px] font-semibold text-[#B95E0D]" onClick={() => void updateItem(selectedItem, { module_id: "wrong_questions" })}>
                归到错题
              </button>
              <button
                className="col-span-2 rounded-xl bg-[#FEE2E2] px-3 py-3 text-[12px] font-semibold text-[#B91C1C]"
                onClick={() => {
                  setSelectedItemId("");
                  void deleteItem(selectedItem);
                }}
              >
                删除
              </button>
            </div>
          </section>
        </main>
      </div>
    );
  }

  const activeModuleName = moduleFilter === "all" ? "全部资料" : moduleLabel(moduleFilter, modules);
  const overallProgress = items.length ? Math.round((doneItemsCount / items.length) * 100) : 0;
  const studyTabs: Array<{ id: StudyView; label: string; count: number }> = [
    { id: "materials", label: "资料", count: viewCounts.materials },
    { id: "questions", label: "题库", count: viewCounts.questions },
    { id: "notes", label: "笔记", count: viewCounts.notes },
    { id: "recite", label: "背诵", count: viewCounts.recite },
    { id: "wrong", label: "错题", count: viewCounts.wrong },
  ];

  return (
    <div className="min-h-full bg-white pb-8 text-black">
      <header className="sticky top-0 z-20 bg-white px-5 pt-[calc(env(safe-area-inset-top,0px)+0px)]">
        <nav className="flex h-16 items-center justify-between">
          <div className="text-[11px] font-bold uppercase text-[#707070]">StudyRoom</div>
          <div className="flex gap-1">
            <button
              type="button"
              className="flex h-10 w-10 items-center justify-center rounded-lg text-black active:bg-[#F7F7F7]"
              aria-label="看全部资料"
              onClick={() => {
                setModuleFilter("all");
                setStudyView("materials");
              }}
            >
              <BookIcon />
            </button>
            <button
              type="button"
              className="flex h-10 w-10 items-center justify-center rounded-lg text-black active:bg-[#F7F7F7]"
              aria-label="刷新 StudyRoom"
              onClick={() => void load()}
            >
              <RefreshIcon />
            </button>
          </div>
        </nav>
      </header>

      <main className="px-5">
        <section className="mt-3 rounded-xl bg-[#F7F7F7] p-4">
          <div className="text-[11px] font-bold uppercase text-[#707070]">Current Goal</div>
          <h1 className="mt-2 text-[24px] font-bold leading-8">
            {data.profile?.target_name || data.profile?.exam_name || "安徽省铜陵市枞阳县村级后备干部考试"}
          </h1>
          <div className="mt-4 grid grid-cols-3 gap-2">
            {[
              ["资料", items.length],
              ["已整理", doneItemsCount],
              ["记录", logs.length],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg bg-white px-3 py-3">
                <div className="text-[18px] font-bold">{value}</div>
                <div className="mt-1 text-[11px] text-[#707070]">{label}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-8">
          <div className="mb-4 flex items-end justify-between">
            <h2 className="text-[20px] font-semibold">学习模块</h2>
            <button className="text-[11px] font-bold uppercase text-[#707070]" onClick={() => setModuleFilter("all")}>全部</button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {modules.map((module) => {
              const itemCount = counts.get(module.id) || 0;
              const doneCount = items.filter((item) => String(item.module_id || "inbox") === module.id && item.status === "done").length;
              const progress = itemCount ? Math.round((doneCount / itemCount) * 100) : 0;
              return (
                <button
                  key={module.id}
                  type="button"
                  className={`rounded-xl p-5 text-left active:scale-[0.995] ${
                    moduleFilter === module.id ? "bg-black text-white" : "bg-[#F7F7F7] text-black"
                  }`}
                  onClick={() => setModuleFilter(module.id)}
                >
                  <div className={`mb-3 text-[11px] font-bold uppercase ${moduleFilter === module.id ? "text-white/55" : "text-[#707070]"}`}>
                    Module
                  </div>
                  <h3 className="text-[16px] font-semibold leading-6">{module.label}</h3>
                  <div className={`mt-1 text-[12px] ${moduleFilter === module.id ? "text-white/55" : "text-[#707070]"}`}>{itemCount} 份资料</div>
                  <div className={`mt-4 h-1 overflow-hidden rounded-full ${moduleFilter === module.id ? "bg-white/20" : "bg-[#E8E8E8]"}`}>
                    <div className="h-full rounded-full bg-[#E67E22]" style={{ width: `${progress}%` }} />
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="mt-8">
          <div className="mb-4 flex items-end justify-between">
            <h2 className="text-[20px] font-semibold">继续学习</h2>
            <span className="text-[11px] font-bold uppercase text-[#707070]">{overallProgress}%</span>
          </div>
          <div className="space-y-1">
            {examLaneStats.slice(0, 4).map((lane) => {
              const progress = lane.itemCount ? Math.round((lane.doneCount / lane.itemCount) * 100) : 0;
              return (
                <div key={lane.id} className="flex items-center border-b border-[#F0F0F0] py-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-black text-[12px] font-bold text-white">
                    {itemInitial(lane.title)}
                  </div>
                  <div className="ml-3 min-w-0 flex-1">
                    <div className="truncate text-[14px] font-semibold">{lane.title}</div>
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-[#EEEEEE]">
                      <div className="h-full rounded-full bg-[#E67E22]" style={{ width: `${progress}%` }} />
                    </div>
                  </div>
                  <div className="ml-3 text-[11px] font-bold uppercase text-[#707070]">{progress}%</div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="mt-8">
          <div className="mb-4 flex items-end justify-between">
            <h2 className="text-[20px] font-semibold">待处理</h2>
            <span className="text-[11px] font-bold uppercase text-[#707070]">{pendingItems.length} 项</span>
          </div>
          {pendingItems[0] ? (
            <button
              type="button"
              className="flex w-full items-center justify-between rounded-xl bg-[#F7F7F7] p-4 text-left active:scale-[0.995]"
              onClick={() => setSelectedItemId(String(pendingItems[0].id || ""))}
            >
              <div className="min-w-0">
                <div className="mb-2 inline-flex rounded bg-[#FFF4E8] px-2 py-1 text-[11px] font-bold text-[#E67E22]">
                  {statusLabel(pendingItems[0].status)}
                </div>
                <div className="truncate text-[14px] font-semibold">{pendingItems[0].title || "未命名资料"}</div>
              </div>
              <ChevronRightIcon className="ml-3 shrink-0 text-[#707070]" />
            </button>
          ) : (
            <div className="rounded-xl bg-[#F7F7F7] px-4 py-5 text-[13px] text-[#707070]">暂时没有待处理资料。</div>
          )}
        </section>

        <section className="mt-8 rounded-xl bg-[#F7F7F7] p-4">
          <div className="mb-4 flex items-end justify-between">
            <h2 className="text-[20px] font-semibold">丢进 StudyRoom</h2>
            <span className="text-[11px] font-bold uppercase text-[#707070]">{loading ? "加载中" : "Import"}</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select className="rounded-lg bg-white px-3 py-3 text-[13px] outline-none" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
              {Object.entries(SOURCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <select className="rounded-lg bg-white px-3 py-3 text-[13px] outline-none" value={moduleId} onChange={(e) => setModuleId(e.target.value)}>
              {modules.map((module) => <option key={module.id} value={module.id}>{module.label}</option>)}
            </select>
          </div>
          <label
            className={`relative mt-2 flex w-full items-center justify-center overflow-hidden rounded-lg border border-[#E8E8E8] bg-white px-4 py-3 text-[13px] font-semibold text-black ${
              uploading ? "cursor-not-allowed opacity-60" : "cursor-pointer active:scale-[0.99]"
            }`}
          >
            <span>{uploading ? (uploadStatus || "正在导入...") : "上传 PDF / Word / TXT"}</span>
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
          <div className="mt-2 text-[11px] leading-5 text-[#707070]">支持文字版 PDF、docx、txt、md；长资料会按章节/页码拆段，扫描版 PDF 先不做 OCR。</div>
          <input
            className="mt-2 w-full rounded-lg bg-white px-3 py-3 text-[13px] outline-none placeholder:text-[#A0A0A0]"
            placeholder="标题，例如：B站公文写作第一课"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input
            className="mt-2 w-full rounded-lg bg-white px-3 py-3 text-[13px] outline-none placeholder:text-[#A0A0A0]"
            placeholder="链接，可空"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <textarea
            className="mt-2 min-h-[112px] w-full resize-none rounded-lg bg-white px-3 py-3 text-[13px] leading-6 outline-none placeholder:text-[#A0A0A0]"
            placeholder="贴视频简介、网页摘要、错题、自己的备注都行。"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <button
            type="button"
            className="mt-3 w-full rounded-lg bg-black px-4 py-4 text-[13px] font-semibold text-white active:scale-[0.99] disabled:opacity-60"
            disabled={saving}
            onClick={addItem}
          >
            放进 StudyRoom
          </button>
        </section>

        <section className="mt-8">
          <div className="mb-4 flex items-end justify-between">
            <h2 className="text-[20px] font-semibold">{activeModuleName}</h2>
            <button
              className="text-[11px] font-bold uppercase text-[#707070]"
              onClick={() => {
                setModuleFilter("all");
                setStudyView("materials");
              }}
            >
              看全部
            </button>
          </div>
          <div className="no-scrollbar -mx-5 flex overflow-x-auto border-b border-[#F0F0F0] px-5">
            {studyTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`mr-6 shrink-0 border-b-2 py-3 text-[15px] ${
                  studyView === tab.id ? "border-black font-bold text-black" : "border-transparent font-medium text-[#707070]"
                }`}
                onClick={() => {
                  setStudyView(tab.id);
                  if (tab.id === "questions") setSourceType("question_bank");
                  if (tab.id === "notes") setSourceType("note");
                  if (tab.id === "wrong") setSourceType("wrong_question");
                  if (tab.id === "materials" && ["question_bank", "wrong_question"].includes(sourceType)) setSourceType("pdf");
                }}
              >
                {tab.label} {tab.count}
              </button>
            ))}
          </div>

          <div className="mt-5 space-y-3">
            {visibleItems.map((item) => (
              <article key={String(item.id || "")} className="rounded-xl border border-[#EEEEEE] bg-white p-4">
                <button
                  type="button"
                  className="flex w-full items-start gap-3 text-left"
                  onClick={() => setSelectedItemId(String(item.id || ""))}
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-black text-[12px] font-bold text-white">
                    {itemInitial(moduleLabel(item.module_id, modules))}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap gap-1.5">
                      <span className="rounded bg-[#F7F7F7] px-2 py-1 text-[11px] font-semibold text-[#707070]">{sourceLabel(item.source_type)}</span>
                      <span className="rounded bg-[#FFF4E8] px-2 py-1 text-[11px] font-semibold text-[#E67E22]">{statusLabel(item.status)}</span>
                    </div>
                    <h3 className="text-[15px] font-semibold leading-6">{item.title || "未命名资料"}</h3>
                    <p className="mt-2 line-clamp-2 text-[13px] leading-6 text-[#707070]">{notePreview(item)}</p>
                  </div>
                  <ChevronRightIcon className="mt-2 shrink-0 text-[#B0B0B0]" />
                </button>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <button className="rounded-lg bg-black px-3 py-3 text-[12px] font-semibold text-white" onClick={() => setSelectedItemId(String(item.id || ""))}>
                    查看
                  </button>
                  <button
                    className="rounded-lg bg-[#FFF4E8] px-3 py-3 text-[12px] font-semibold text-[#B95E0D] disabled:opacity-60"
                    disabled={Boolean(sortingItemId)}
                    onClick={() => void runCodexSort(item)}
                  >
                    {sortingItemId === String(item.id || "") ? "整理中" : item.note ? "重整" : "整理"}
                  </button>
                  <button
                    className="rounded-lg bg-[#F7F7F7] px-3 py-3 text-[12px] font-semibold text-black"
                    onClick={() => void updateItem(item, { status: nextStatus(item.status) })}
                  >
                    状态
                  </button>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <button className="rounded-lg bg-[#F7F7F7] px-3 py-3 text-[12px] font-semibold text-black" onClick={() => copySortPrompt(item)}>复制</button>
                  <button
                    className="rounded-lg bg-[#F7F7F7] px-3 py-3 text-[12px] font-semibold text-black disabled:opacity-60"
                    disabled={Boolean(classifyingItemId)}
                    onClick={() => void autoModuleItem(item)}
                  >
                    {classifyingItemId === String(item.id || "") ? "归类中" : "归类"}
                  </button>
                  <button className="rounded-lg bg-[#FEE2E2] px-3 py-3 text-[12px] font-semibold text-[#B91C1C]" onClick={() => deleteItem(item)}>删除</button>
                </div>
              </article>
            ))}
            {!visibleItems.length ? (
              <div className="rounded-xl border border-dashed border-[#DADADA] px-4 py-8 text-center text-[13px] leading-6 text-[#707070]">
                这里还空着。看到 B站课、网页、错题就先扔进来。
              </div>
            ) : null}
          </div>
        </section>

        <section className="mt-8">
          <div className="mb-4 flex items-end justify-between">
            <h2 className="text-[20px] font-semibold">学习记录</h2>
            <span className="text-[11px] font-bold uppercase text-[#707070]">Notes</span>
          </div>
          <textarea
            className="min-h-[96px] w-full resize-none rounded-xl bg-[#F7F7F7] px-4 py-4 text-[13px] leading-6 outline-none placeholder:text-[#A0A0A0]"
            placeholder="今天看了什么、哪里卡住、下次从哪里继续。"
            value={studyLog}
            onChange={(e) => setStudyLog(e.target.value)}
          />
          <button
            type="button"
            className="mt-3 w-full rounded-lg bg-[#E67E22] px-4 py-4 text-[13px] font-semibold text-white active:scale-[0.99] disabled:opacity-60"
            disabled={saving}
            onClick={addStudyLog}
          >
            记一笔
          </button>
          <div className="mt-4 space-y-2">
            {logs.slice(0, 5).map((log) => (
              <div key={String(log.id || "")} className="rounded-xl bg-[#F7F7F7] px-4 py-4">
                <div className="mb-1 text-[11px] text-[#707070]">{formatShortTime(log.created_at)}</div>
                <p className="whitespace-pre-wrap text-[13px] leading-6 text-[#333333]">{log.content}</p>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
