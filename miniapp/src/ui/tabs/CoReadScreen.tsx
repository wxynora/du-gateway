import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type CoReadTheme = "light" | "dark" | "paper";
type CoReadMarkSource = "user" | "du";
type CoReadMark = {
  id: string;
  source: CoReadMarkSource;
  quote: string;
  note: string;
  du_reply?: string;
  char_start: number;
  char_end: number;
  created_at: string;
  updated_at?: string;
};
type CoReadSection = {
  section_id: string;
  index: number;
  char_start: number;
  char_end: number;
  status: "reading" | "done";
  user_marks: CoReadMark[];
  du_marks: CoReadMark[];
  user_section_note: string;
  du_section_note: string;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
};
type CoReadBook = {
  book_key: string;
  book_title: string;
  content: string;
  sections: CoReadSection[];
  current_section_index: number;
  created_at?: string;
  updated_at?: string;
};
type CoReadBookSummary = {
  book_key: string;
  book_title: string;
  content_chars: number;
  section_count: number;
  done_count: number;
  current_section_index: number;
  created_at?: string;
  updated_at?: string;
};
type CoReadBookCachePayload = {
  book_key: string;
  content_chars: number;
  section_count: number;
  cached_at: string;
  book: CoReadBook;
};
type CoReadSettings = {
  fontSize: number;
  lineHeight: number;
  marginLevel: number;
  theme: CoReadTheme;
};
type CoReadBooksResponse = {
  ok?: boolean;
  books?: CoReadBookSummary[];
  error?: string;
};
type CoReadBookResponse = {
  ok?: boolean;
  book?: CoReadBook;
  book_summary?: CoReadBookSummary;
  section?: CoReadSection;
  error?: string;
};
type CoReadUploadResponse = {
  ok?: boolean;
  upload_id?: string;
  upload?: {
    upload_id?: string;
    total_chunks?: number;
    received_chunks?: number[];
  };
  error?: string;
};
type CoReadSectionCompleteResponse = {
  ok?: boolean;
  book?: CoReadBook;
  book_summary?: CoReadBookSummary;
  section?: CoReadSection;
  du_marks?: CoReadMark[];
  du_section_note?: string;
  error?: string;
};
const CO_READ_SETTINGS_KEY = "miniapp.coRead.settings.v1";
const CO_READ_BOOK_CACHE_KEY = "miniapp.coRead.activeBookCache.v1";
const CO_READ_DIRECT_UPLOAD_MAX_BYTES = 650_000;
const CO_READ_UPLOAD_CHUNK_CHARS = 180_000;

function clampStoredNumber(value: number, min: number, max: number, fallback: number): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(min, Math.min(max, num));
}

function makeCoReadId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function emptyCoReadSettings(): CoReadSettings {
  return {
    fontSize: 18,
    lineHeight: 1.8,
    marginLevel: 2,
    theme: "light",
  };
}

function normalizeCoReadTheme(value: any): CoReadTheme {
  return value === "dark" || value === "paper" || value === "light" ? value : "light";
}

function normalizeCoReadMark(raw: any, source: CoReadMarkSource): CoReadMark | null {
  const quote = String(raw?.quote || "").trim();
  const note = String(raw?.note || "").trim();
  if (!quote && !note) return null;
  return {
    id: String(raw?.id || makeCoReadId(source === "du" ? "du_mark" : "mark")),
    source,
    quote,
    note,
    du_reply: raw?.du_reply ? String(raw.du_reply) : undefined,
    char_start: Number.isFinite(Number(raw?.char_start)) ? Number(raw.char_start) : -1,
    char_end: Number.isFinite(Number(raw?.char_end)) ? Number(raw.char_end) : -1,
    created_at: String(raw?.created_at || new Date().toISOString()),
    updated_at: raw?.updated_at ? String(raw.updated_at) : undefined,
  };
}

function normalizeCoReadMarks(raw: any, source: CoReadMarkSource): CoReadMark[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => normalizeCoReadMark(item, source))
    .filter((item): item is CoReadMark => Boolean(item));
}

function unescapeCoReadModelText(text: string): string {
  return String(text || "")
    .replace(/<!\[CDATA\[/g, "")
    .replace(/\]\]>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;|&#34;/g, "\"")
    .replace(/&#39;/g, "'")
    .replace(/\\"/g, "\"")
    .replace(/\\n/g, "\n")
    .trim();
}

function extractTagText(text: string, tag: string): string {
  const match = String(text || "").match(new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, "i"));
  return match ? unescapeCoReadModelText(match[1]) : "";
}

function extractCoReadResultArtifact(text: string): { marks: Array<{ quote: string; note: string }>; note: string } | null {
  const raw = String(text || "")
    .trim()
    .replace(/^```(?:json|xml)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
  if (!raw.includes("du_marks") && !raw.includes("du_mark") && !raw.includes("du_section_note")) return null;

  const xmlMarks = Array.from(raw.matchAll(/<du_mark\b[^>]*>([\s\S]*?)<\/du_mark>/gi))
    .map((match) => ({
      quote: extractTagText(match[1], "quote"),
      note: extractTagText(match[1], "note"),
    }))
    .filter((item) => item.quote || item.note);
  const xmlNote = extractTagText(raw, "du_section_note");
  if (xmlMarks.length || xmlNote) return { marks: xmlMarks, note: xmlNote };

  try {
    const start = raw.indexOf("{");
    const end = raw.lastIndexOf("}");
    const parsed = JSON.parse(start >= 0 && end > start ? raw.slice(start, end + 1) : raw);
    const marks = Array.isArray(parsed?.du_marks)
      ? parsed.du_marks.map((item: any) => ({ quote: String(item?.quote || ""), note: String(item?.note || "") })).filter((item: any) => item.quote || item.note)
      : [];
    const note = String(parsed?.du_section_note || "");
    if (marks.length || note) return { marks, note };
  } catch {}

  const marks = Array.from(raw.matchAll(/"quote"\s*:\s*"([\s\S]*?)"\s*,\s*"note"\s*:\s*"([\s\S]*?)"\s*(?:\}|,\s*")/g))
    .map((match) => ({ quote: unescapeCoReadModelText(match[1]), note: unescapeCoReadModelText(match[2]) }))
    .filter((item) => item.quote || item.note);
  const noteMatch = raw.match(/"du_section_note"\s*:\s*"([\s\S]*?)"\s*(?:\}|\n|$)/);
  const note = noteMatch ? unescapeCoReadModelText(noteMatch[1]) : "";
  return marks.length || note ? { marks, note } : null;
}

function normalizeCoReadSection(raw: any, fallbackIndex = 1): CoReadSection | null {
  const charStart = Math.max(0, Number(raw?.char_start || 0));
  const charEnd = Math.max(charStart, Number(raw?.char_end || charStart));
  if (charEnd <= charStart) return null;
  const index = Math.max(1, Number(raw?.index || fallbackIndex));
  return {
    section_id: String(raw?.section_id || `sec_${String(index).padStart(4, "0")}`),
    index,
    char_start: charStart,
    char_end: charEnd,
    status: raw?.status === "done" ? "done" : "reading",
    user_marks: normalizeCoReadMarks(raw?.user_marks, "user"),
    du_marks: normalizeCoReadMarks(raw?.du_marks, "du"),
    user_section_note: String(raw?.user_section_note || ""),
    du_section_note: String(raw?.du_section_note || ""),
    created_at: raw?.created_at ? String(raw.created_at) : undefined,
    updated_at: raw?.updated_at ? String(raw.updated_at) : undefined,
    completed_at: raw?.completed_at ? String(raw.completed_at) : undefined,
  };
}

function repairCoReadSectionArtifact(section: CoReadSection, content: string): CoReadSection {
  if (section.du_marks.length || !section.du_section_note) return section;
  const artifact = extractCoReadResultArtifact(section.du_section_note);
  if (!artifact?.marks.length && !artifact?.note) return section;
  const sectionText = content.slice(section.char_start, section.char_end);
  const now = new Date().toISOString();
  const duMarks = artifact.marks.map((item, index) => {
    const [localStart, localEnd] = locateCoReadQuote(sectionText, item.quote);
    return {
      id: makeCoReadId(`du_recovered_${index}`),
      source: "du" as const,
      quote: item.quote,
      note: item.note,
      char_start: localStart >= 0 ? section.char_start + localStart : -1,
      char_end: localEnd > localStart ? section.char_start + localEnd : -1,
      created_at: section.completed_at || now,
      updated_at: now,
    };
  });
  return {
    ...section,
    du_marks: duMarks,
    du_section_note: artifact.note || "",
  };
}

function normalizeCoReadBook(raw: any): CoReadBook | null {
  const content = String(raw?.content || "");
  const sections = Array.isArray(raw?.sections)
    ? raw.sections
        .map((item: any, index: number) => normalizeCoReadSection(item, index + 1))
        .filter((item: CoReadSection | null): item is CoReadSection => Boolean(item))
        .map((section: CoReadSection) => repairCoReadSectionArtifact(section, content))
    : [];
  const book = {
    book_key: String(raw?.book_key || "").trim(),
    book_title: String(raw?.book_title || raw?.title || "").trim(),
    content,
    sections,
    current_section_index: Math.max(0, Math.min(Math.max(0, sections.length - 1), Number(raw?.current_section_index || 0))),
    created_at: raw?.created_at ? String(raw.created_at) : undefined,
    updated_at: raw?.updated_at ? String(raw.updated_at) : undefined,
  };
  return book.book_key && book.book_title ? book : null;
}

function normalizeCoReadBookSummary(raw: any): CoReadBookSummary | null {
  const bookKey = String(raw?.book_key || "").trim();
  const bookTitle = String(raw?.book_title || "").trim();
  if (!bookKey || !bookTitle) return null;
  return {
    book_key: bookKey,
    book_title: bookTitle,
    content_chars: Math.max(0, Number(raw?.content_chars || 0)),
    section_count: Math.max(0, Number(raw?.section_count || 0)),
    done_count: Math.max(0, Number(raw?.done_count || 0)),
    current_section_index: Math.max(0, Number(raw?.current_section_index || 0)),
    created_at: raw?.created_at ? String(raw.created_at) : undefined,
    updated_at: raw?.updated_at ? String(raw.updated_at) : undefined,
  };
}

function coReadSummaryFromBook(book: CoReadBook): CoReadBookSummary {
  const doneCount = book.sections.filter((section) => section.status === "done").length;
  return {
    book_key: book.book_key,
    book_title: book.book_title,
    content_chars: book.content.length,
    section_count: book.sections.length,
    done_count: doneCount,
    current_section_index: book.current_section_index,
    created_at: book.created_at,
    updated_at: book.updated_at,
  };
}

function mergeCachedCoReadBookWithSummary(book: CoReadBook, summary?: CoReadBookSummary | null): CoReadBook {
  if (!summary) return book;
  const maxIndex = Math.max(0, book.sections.length - 1);
  return {
    ...book,
    book_title: summary.book_title || book.book_title,
    current_section_index: Math.max(0, Math.min(maxIndex, summary.current_section_index)),
    created_at: summary.created_at || book.created_at,
    updated_at: summary.updated_at || book.updated_at,
  };
}

function readCachedCoReadBook(bookKey: string, summary?: CoReadBookSummary | null): CoReadBook | null {
  try {
    const raw = localStorage.getItem(CO_READ_BOOK_CACHE_KEY);
    if (!raw) return null;
    const payload = JSON.parse(raw) as Partial<CoReadBookCachePayload>;
    const book = normalizeCoReadBook(payload?.book);
    if (!book || book.book_key !== bookKey) return null;
    const cachedChars = Math.max(0, Number(payload?.content_chars ?? book.content.length));
    const cachedSections = Math.max(0, Number(payload?.section_count ?? book.sections.length));
    if (cachedChars !== book.content.length || cachedSections !== book.sections.length) return null;
    if (summary) {
      if (summary.book_key !== bookKey) return null;
      if (summary.content_chars > 0 && summary.content_chars !== book.content.length) return null;
      if (summary.section_count > 0 && summary.section_count !== book.sections.length) return null;
    }
    return mergeCachedCoReadBookWithSummary(book, summary);
  } catch {
    return null;
  }
}

function writeCachedCoReadBook(book: CoReadBook | null) {
  if (!book) return;
  try {
    const payload: CoReadBookCachePayload = {
      book_key: book.book_key,
      content_chars: book.content.length,
      section_count: book.sections.length,
      cached_at: new Date().toISOString(),
      book,
    };
    localStorage.setItem(CO_READ_BOOK_CACHE_KEY, JSON.stringify(payload));
  } catch {
    try {
      localStorage.removeItem(CO_READ_BOOK_CACHE_KEY);
    } catch {}
  }
}

function clearCachedCoReadBook(bookKey?: string) {
  try {
    if (!bookKey) {
      localStorage.removeItem(CO_READ_BOOK_CACHE_KEY);
      return;
    }
    const raw = localStorage.getItem(CO_READ_BOOK_CACHE_KEY);
    if (!raw) return;
    const payload = JSON.parse(raw) as Partial<CoReadBookCachePayload>;
    if (payload?.book_key === bookKey) localStorage.removeItem(CO_READ_BOOK_CACHE_KEY);
  } catch {}
}

function patchCoReadBookSection(book: CoReadBook, rawSection: any, rawSummary?: any, fallbackIndex?: number): CoReadBook | null {
  const normalized = normalizeCoReadSection(rawSection, fallbackIndex ?? book.current_section_index + 1);
  if (!normalized) return null;
  const section = repairCoReadSectionArtifact(normalized, book.content);
  const sections = [...book.sections];
  let sectionIndex = sections.findIndex((item) => item.section_id === section.section_id);
  if (sectionIndex < 0) {
    sectionIndex = sections.findIndex((item) => item.index === section.index);
  }
  if (sectionIndex < 0) return null;
  sections[sectionIndex] = section;
  const summary = normalizeCoReadBookSummary(rawSummary);
  const currentIndex = summary
    ? Math.max(0, Math.min(Math.max(0, sections.length - 1), summary.current_section_index))
    : Math.max(0, Math.min(Math.max(0, sections.length - 1), book.current_section_index));
  return {
    ...book,
    book_title: summary?.book_title || book.book_title,
    sections,
    current_section_index: currentIndex,
    created_at: summary?.created_at || book.created_at,
    updated_at: summary?.updated_at || section.updated_at || book.updated_at,
  };
}

function coReadBookFromUpdatePayload(currentBook: CoReadBook, payload: CoReadBookResponse, fallbackIndex?: number): CoReadBook | null {
  const fullBook = normalizeCoReadBook(payload?.book);
  if (fullBook) return fullBook;
  return patchCoReadBookSection(currentBook, payload?.section, payload?.book_summary, fallbackIndex);
}

function readCoReadSettings(): CoReadSettings {
  const fallback = emptyCoReadSettings();
  try {
    const raw = JSON.parse(localStorage.getItem(CO_READ_SETTINGS_KEY) || "{}");
    return {
      fontSize: clampStoredNumber(Number(raw?.fontSize || fallback.fontSize), 15, 24, fallback.fontSize),
      lineHeight: clampStoredNumber(Number(raw?.lineHeight || fallback.lineHeight), 1.4, 2.2, fallback.lineHeight),
      marginLevel: Math.max(1, Math.min(3, Number(raw?.marginLevel || fallback.marginLevel))),
      theme: normalizeCoReadTheme(raw?.theme),
    };
  } catch {
    return fallback;
  }
}

function writeCoReadSettings(settings: CoReadSettings) {
  try {
    localStorage.setItem(CO_READ_SETTINGS_KEY, JSON.stringify(settings));
  } catch {}
}

function stripTxtExtension(filename: string): string {
  return String(filename || "未命名").replace(/\.[^.]+$/, "").trim() || "未命名";
}

function sanitizeDecodedTxt(text: string): string {
  return String(text || "")
    .replace(/^\uFEFF/, "")
    .replace(/\u0000/g, "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
}

function scoreDecodedTxt(text: string): number {
  const value = String(text || "");
  const replacement = (value.match(/\uFFFD/g) || []).length;
  const nul = (value.match(/\u0000/g) || []).length;
  const controls = Array.from(value).filter((ch) => {
    const code = ch.charCodeAt(0);
    return code < 32 && ch !== "\n" && ch !== "\r" && ch !== "\t";
  }).length;
  const mojibake = (value.match(/锟斤拷|ï¿½|Ã.|Â./g) || []).length;
  return replacement * 1000 + nul * 200 + controls * 30 + mojibake * 80;
}

function decodeCoReadTxtBytes(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const startsWith = (...values: number[]) => values.every((value, index) => bytes[index] === value);
  const decode = (label: string, fatal = false) => new TextDecoder(label, { fatal }).decode(bytes);
  if (startsWith(0xef, 0xbb, 0xbf)) return sanitizeDecodedTxt(decode("utf-8"));
  if (startsWith(0xff, 0xfe)) return sanitizeDecodedTxt(decode("utf-16le"));
  if (startsWith(0xfe, 0xff)) return sanitizeDecodedTxt(decode("utf-16be"));
  try {
    const strictUtf8 = decode("utf-8", true);
    if (scoreDecodedTxt(strictUtf8) === 0) return sanitizeDecodedTxt(strictUtf8);
  } catch {}

  const candidates: Array<{ label: string; text: string; score: number }> = [];
  for (const label of ["utf-8", "gb18030", "gbk", "utf-16le", "utf-16be"]) {
    try {
      const text = decode(label);
      candidates.push({ label, text, score: scoreDecodedTxt(text) });
    } catch {}
  }
  candidates.sort((a, b) => a.score - b.score);
  return sanitizeDecodedTxt((candidates[0]?.text || ""));
}

function formatCoReadDate(value: string): string {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "刚刚";
  const month = date.toLocaleString("en-US", { month: "short" }).toUpperCase();
  const day = String(date.getDate()).padStart(2, "0");
  return `${month} ${day}`;
}

function formatCoReadProgress(progress: number): string {
  return `${Math.round(Math.max(0, Math.min(1, progress)) * 1000) / 10}%`;
}

function formatCoReadSectionRange(book: CoReadBook, section: CoReadSection): string {
  const total = Math.max(1, book.content.length);
  const start = section.char_start / total;
  const end = section.char_end / total;
  return `${formatCoReadProgress(start)} - ${formatCoReadProgress(end)}`;
}

function coReadSectionText(book: CoReadBook, section: CoReadSection): string {
  return book.content.slice(section.char_start, section.char_end);
}

function coReadBookProgress(summary: Pick<CoReadBookSummary, "section_count" | "done_count">): number {
  const total = Math.max(1, Number(summary.section_count || 0));
  return Math.max(0, Math.min(1, Number(summary.done_count || 0) / total));
}

function compactCoReadText(text: string, max = 52): string {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (value.length <= max) return value;
  return `${value.slice(0, max)}...`;
}

function locateCoReadQuote(sectionText: string, quote: string): [number, number] {
  const rawQuote = String(quote || "").trim();
  if (!rawQuote) return [-1, -1];
  const exact = sectionText.indexOf(rawQuote);
  if (exact >= 0) return [exact, exact + rawQuote.length];
  const compactChars: string[] = [];
  const mapping: number[] = [];
  Array.from(sectionText).forEach((ch, index) => {
    if (/\s/.test(ch)) return;
    compactChars.push(ch);
    mapping.push(index);
  });
  const compactQuote = Array.from(rawQuote).filter((ch) => !/\s/.test(ch)).join("");
  const compactIndex = compactChars.join("").indexOf(compactQuote);
  if (compactIndex < 0 || compactIndex + compactQuote.length > mapping.length) return [-1, -1];
  return [mapping[compactIndex], mapping[compactIndex + compactQuote.length - 1] + 1];
}

function renderCoReadMarkedText(
  text: string,
  sectionStart: number,
  userMarks: CoReadMark[],
  duMarks: CoReadMark[],
  onOpenMarks?: (marks: CoReadMark[]) => void,
) {
  const marks = [...userMarks, ...duMarks].filter((mark) => (
    mark.char_start >= sectionStart &&
    mark.char_end > mark.char_start &&
    mark.char_start < sectionStart + text.length
  ));
  if (!marks.length) return text;
  const boundaries = new Set<number>([0, text.length]);
  marks.forEach((mark) => {
    boundaries.add(Math.max(0, Math.min(text.length, mark.char_start - sectionStart)));
    boundaries.add(Math.max(0, Math.min(text.length, mark.char_end - sectionStart)));
  });
  const sorted = Array.from(boundaries).sort((a, b) => a - b);
  return sorted.slice(0, -1).map((start, index) => {
    const end = sorted[index + 1];
    const value = text.slice(start, end);
    const active = marks.filter((mark) => mark.char_start - sectionStart < end && mark.char_end - sectionStart > start);
    const hasUser = active.some((mark) => mark.source === "user");
    const hasDu = active.some((mark) => mark.source === "du");
    const title = active.map((mark) => mark.note || mark.quote).filter(Boolean).join("\n");
    const className = hasUser && hasDu
      ? "cursor-pointer rounded-[4px] bg-gradient-to-r from-[#FFE1EC] to-[#DDEBFF] decoration-[#8BA9E8] underline decoration-2 underline-offset-4"
      : hasUser
        ? "cursor-pointer rounded-[4px] bg-[#FFE1EC] decoration-[#F09AB9] underline decoration-2 underline-offset-4"
        : hasDu
          ? "cursor-pointer rounded-[4px] bg-[#DDEBFF] decoration-[#8BA9E8] underline decoration-2 underline-offset-4"
          : "";
    return className
      ? (
          <span
            key={`${start}-${end}`}
            className={className}
            title={title}
            data-co-read-mark-ids={active.map((mark) => mark.id).join(" ")}
            role="button"
            tabIndex={0}
            onClick={(event) => {
              event.stopPropagation();
              onOpenMarks?.(active);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onOpenMarks?.(active);
              }
            }}
          >
            {value}
          </span>
        )
      : <span key={`${start}-${end}`}>{value}</span>;
  });
}

export function CoReadScreen({ onBack, windowId }: { onBack: () => void; windowId: string }) {
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const readerRef = useRef<HTMLDivElement | null>(null);
  const completeInFlightRef = useRef(false);
  const swipeRef = useRef({ tracking: false, startX: 0, startY: 0, latestX: 0, latestY: 0 });
  const [books, setBooks] = useState<CoReadBookSummary[]>([]);
  const [activeBook, setActiveBook] = useState<CoReadBook | null>(null);
  const [settings, setSettings] = useState<CoReadSettings>(() => readCoReadSettings());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [loadingBooks, setLoadingBooks] = useState(true);
  const [loadingBookKey, setLoadingBookKey] = useState("");
  const [refreshingBook, setRefreshingBook] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importStatus, setImportStatus] = useState("");
  const [savingMark, setSavingMark] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [selectedText, setSelectedText] = useState("");
  const [markNote, setMarkNote] = useState("");
  const [sectionNote, setSectionNote] = useState("");
  const [activeMarkPopup, setActiveMarkPopup] = useState<CoReadMark[]>([]);

  const activeSection = useMemo(() => {
    if (!activeBook?.sections.length) return null;
    return activeBook.sections[Math.max(0, Math.min(activeBook.sections.length - 1, activeBook.current_section_index))] || activeBook.sections[0];
  }, [activeBook]);
  const activeSectionText = useMemo(() => (
    activeBook && activeSection ? coReadSectionText(activeBook, activeSection) : ""
  ), [activeBook, activeSection]);

  const theme = settings.theme === "dark"
    ? {
        shell: "bg-[#111111] text-[#F8F8F8]",
        panel: "border-[#2A2A2A] bg-[#171717]",
        soft: "bg-[#1F1F1F] text-[#D8D8D8]",
        muted: "text-[#8C8C8C]",
        input: "border-[#333333] bg-[#181818] text-[#F8F8F8] placeholder:text-[#777777]",
        dock: "border-[#2A2A2A] bg-[#111111]/95",
      }
    : settings.theme === "paper"
      ? {
          shell: "bg-[#F4F1EA] text-[#352D28]",
          panel: "border-[#E1D8CC] bg-[#FBF8F1]",
          soft: "bg-[#ECE4D8] text-[#6E5B4E]",
          muted: "text-[#8A786B]",
          input: "border-[#DED2C2] bg-[#FFFDF8] text-[#352D28] placeholder:text-[#A9998B]",
          dock: "border-[#DED2C2] bg-[#F4F1EA]/95",
        }
      : {
          shell: "bg-white text-[#111111]",
          panel: "border-[#EAEAEA] bg-white",
          soft: "bg-[#F7F7F7] text-[#555555]",
          muted: "text-[#888888]",
          input: "border-[#EAEAEA] bg-white text-[#111111] placeholder:text-[#A0A0A0]",
          dock: "border-[#EAEAEA] bg-white/95",
        };
  const readerPadding = settings.marginLevel === 1 ? "px-5" : settings.marginLevel === 3 ? "px-8" : "px-6";

  useEffect(() => {
    void loadBooks();
  }, []);

  useEffect(() => {
    setSectionNote(activeSection?.user_section_note || "");
    setSelectedText("");
    setMarkNote("");
    setActiveMarkPopup([]);
    requestAnimationFrame(() => readerRef.current?.scrollTo({ top: 0, behavior: "auto" }));
  }, [activeBook?.book_key, activeSection?.section_id]);

  function closeCurrentLevel() {
    if (settingsOpen) {
      setSettingsOpen(false);
      return;
    }
    if (activeBook) {
      setActiveBook(null);
      setSelectedText("");
      setActiveMarkPopup([]);
      return;
    }
    onBack();
  }

  function handleCoReadTouchStart(e: React.TouchEvent<HTMLDivElement>) {
    const touch = e.touches[0];
    if (!touch || touch.clientX > 36) {
      swipeRef.current.tracking = false;
      return;
    }
    swipeRef.current = {
      tracking: true,
      startX: touch.clientX,
      startY: touch.clientY,
      latestX: touch.clientX,
      latestY: touch.clientY,
    };
  }

  function handleCoReadTouchMove(e: React.TouchEvent<HTMLDivElement>) {
    if (!swipeRef.current.tracking) return;
    const touch = e.touches[0];
    if (!touch) return;
    swipeRef.current.latestX = touch.clientX;
    swipeRef.current.latestY = touch.clientY;
  }

  function handleCoReadTouchEnd() {
    const swipe = swipeRef.current;
    swipeRef.current.tracking = false;
    if (!swipe.tracking) return;
    const dx = swipe.latestX - swipe.startX;
    const dy = Math.abs(swipe.latestY - swipe.startY);
    if (dx >= 72 && dx > dy * 1.5) closeCurrentLevel();
  }

  function updateSettings(nextSettings: CoReadSettings | ((prev: CoReadSettings) => CoReadSettings)) {
    setSettings((prev) => {
      const next = typeof nextSettings === "function" ? nextSettings(prev) : nextSettings;
      writeCoReadSettings(next);
      return next;
    });
  }

  function upsertBookSummary(book: CoReadBook) {
    const summary = coReadSummaryFromBook(book);
    setBooks((prev) => [summary, ...prev.filter((item) => item.book_key !== summary.book_key)]);
  }

  async function loadBooks() {
    setLoadingBooks(true);
    try {
      const data = await apiJson<CoReadBooksResponse>("/miniapp-api/co-read/books");
      if (!data?.ok) throw new Error(data?.error || "读取失败");
      setBooks((data.books || []).map(normalizeCoReadBookSummary).filter((item): item is CoReadBookSummary => Boolean(item)));
    } catch (e: any) {
      toast(`共读书架读取失败：${e?.message || e}`);
    } finally {
      setLoadingBooks(false);
    }
  }

  async function openBook(bookKey: string) {
    setLoadingBookKey(bookKey);
    const summary = books.find((book) => book.book_key === bookKey) || null;
    const cachedBook = readCachedCoReadBook(bookKey, summary);
    let openedFromCache = false;
    if (cachedBook) {
      openedFromCache = true;
      setActiveBook(cachedBook);
      setLoadingBookKey("");
    }
    try {
      const data = await apiJson<CoReadBookResponse>(`/miniapp-api/co-read/books/${encodeURIComponent(bookKey)}`);
      const book = normalizeCoReadBook(data.book);
      if (!data?.ok || !book) throw new Error(data?.error || "书籍读取失败");
      setActiveBook(book);
      upsertBookSummary(book);
      writeCachedCoReadBook(book);
    } catch (e: any) {
      toast(openedFromCache ? `已用本地缓存打开，最新状态同步失败：${e?.message || e}` : `打开失败：${e?.message || e}`);
    } finally {
      setLoadingBookKey("");
    }
  }

  async function refreshActiveBook() {
    if (!activeBook || refreshingBook) return;
    const currentSectionId = activeSection?.section_id || "";
    const currentSectionIndex = activeSection?.index || 0;
    setRefreshingBook(true);
    try {
      const data = await apiJson<CoReadBookResponse>(`/miniapp-api/co-read/books/${encodeURIComponent(activeBook.book_key)}`);
      const book = normalizeCoReadBook(data.book);
      if (!data?.ok || !book) throw new Error(data?.error || "刷新失败");
      let nextBook = book;
      const keepIndex = book.sections.findIndex((section) => (
        (currentSectionId && section.section_id === currentSectionId)
        || (currentSectionIndex > 0 && section.index === currentSectionIndex)
      ));
      if (keepIndex >= 0) {
        nextBook = { ...book, current_section_index: keepIndex };
      }
      setActiveBook(nextBook);
      upsertBookSummary(nextBook);
      writeCachedCoReadBook(nextBook);
      setActiveMarkPopup([]);
      toast("已刷新");
    } catch (e: any) {
      toast(`刷新失败：${e?.message || e}`);
    } finally {
      setRefreshingBook(false);
    }
  }

  async function uploadTxtBookInChunks(bookTitle: string, content: string): Promise<CoReadBook> {
    const totalChunks = Math.max(1, Math.ceil(content.length / CO_READ_UPLOAD_CHUNK_CHARS));
    setImportStatus(`准备上传 0/${totalChunks}`);
    const start = await apiJson<CoReadUploadResponse>("/miniapp-api/co-read/uploads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ book_title: bookTitle, total_chunks: totalChunks }),
    });
    const uploadId = String(start.upload_id || start.upload?.upload_id || "");
    if (!start?.ok || !uploadId) throw new Error(start?.error || "创建分片上传失败");
    for (let index = 0; index < totalChunks; index += 1) {
      const chunk = content.slice(index * CO_READ_UPLOAD_CHUNK_CHARS, (index + 1) * CO_READ_UPLOAD_CHUNK_CHARS);
      setImportStatus(`上传 ${index + 1}/${totalChunks}`);
      const part = await apiJson<CoReadUploadResponse>(`/miniapp-api/co-read/uploads/${encodeURIComponent(uploadId)}/chunks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index, chunk }),
      });
      if (!part?.ok) throw new Error(part?.error || `第 ${index + 1} 片上传失败`);
    }
    setImportStatus("正在切分");
    const finished = await apiJson<CoReadBookResponse>(`/miniapp-api/co-read/uploads/${encodeURIComponent(uploadId)}/finish`, {
      method: "POST",
    });
    const book = normalizeCoReadBook(finished.book);
    if (!finished?.ok || !book) throw new Error(finished?.error || "导入失败");
    return book;
  }

  async function importTxtFile(file?: File | null) {
    if (!file || importing) return;
    if (!file.name.toLowerCase().endsWith(".txt") && file.type && file.type !== "text/plain") {
      toast("只能导入 TXT");
      return;
    }
    setImporting(true);
    setImportStatus("");
    try {
      const content = decodeCoReadTxtBytes(await file.arrayBuffer()).trim();
      if (!content) throw new Error("文件里没有可读内容");
      const bookTitle = stripTxtExtension(file.name);
      const useChunkUpload = new Blob([content]).size > CO_READ_DIRECT_UPLOAD_MAX_BYTES;
      let book: CoReadBook | null = null;
      if (useChunkUpload) {
        book = await uploadTxtBookInChunks(bookTitle, content);
      } else {
        const data = await apiJson<CoReadBookResponse>("/miniapp-api/co-read/books", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ book_title: bookTitle, content }),
        });
        book = normalizeCoReadBook(data.book);
        if (!data?.ok || !book) throw new Error(data?.error || "导入失败");
      }
      setActiveBook(book);
      upsertBookSummary(book);
      writeCachedCoReadBook(book);
      toast(`已切成 ${book.sections.length} 个共读小节`);
    } catch (e: any) {
      toast(`导入失败：${e?.message || e}`);
    } finally {
      setImporting(false);
      setImportStatus("");
    }
  }

  async function deleteBook(bookKey: string) {
    const target = books.find((book) => book.book_key === bookKey);
    if (!target) return;
    if (!window.confirm(`删除《${target.book_title}》？`)) return;
    try {
      const data = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/co-read/books/${encodeURIComponent(bookKey)}`, { method: "DELETE" });
      if (!data?.ok) throw new Error(data?.error || "删除失败");
      setBooks((prev) => prev.filter((book) => book.book_key !== bookKey));
      if (activeBook?.book_key === bookKey) setActiveBook(null);
      clearCachedCoReadBook(bookKey);
      toast("已删除");
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  function captureSelection() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount < 1) return;
    const anchor = selection.anchorNode;
    if (anchor && readerRef.current && !readerRef.current.contains(anchor)) return;
    const text = String(selection.toString() || "").trim();
    if (text.length < 2) return;
    setSelectedText(text.slice(0, 800));
    setMarkNote("");
    setActiveMarkPopup([]);
  }

  function clearCoReadSelection() {
    setSelectedText("");
    setMarkNote("");
    window.getSelection()?.removeAllRanges();
  }

  async function persistSection(nextMarks: CoReadMark[], nextNote: string, silent = false) {
    if (!activeBook || !activeSection) return null;
    const data = await apiJson<CoReadBookResponse>(`/miniapp-api/co-read/books/${encodeURIComponent(activeBook.book_key)}/sections/${encodeURIComponent(activeSection.section_id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_marks: nextMarks, user_section_note: nextNote, include_book: false }),
    });
    const book = coReadBookFromUpdatePayload(activeBook, data, activeSection.index);
    if (!data?.ok || !book) throw new Error(data?.error || "保存失败");
    setActiveBook(book);
    upsertBookSummary(book);
    writeCachedCoReadBook(book);
    if (!silent) toast("已保存");
    return book;
  }

  async function saveUserMark() {
    if (!activeBook || !activeSection || !selectedText || savingMark) return;
    setSavingMark(true);
    try {
      const [localStart, localEnd] = locateCoReadQuote(activeSectionText, selectedText);
      const now = new Date().toISOString();
      const mark: CoReadMark = {
        id: makeCoReadId("mark"),
        source: "user",
        quote: selectedText,
        note: markNote.trim(),
        du_reply: "",
        char_start: localStart >= 0 ? activeSection.char_start + localStart : -1,
        char_end: localEnd > localStart ? activeSection.char_start + localEnd : -1,
        created_at: now,
        updated_at: now,
      };
      await persistSection([...activeSection.user_marks, mark], sectionNote, true);
      clearCoReadSelection();
      toast("粉色标记已保存");
    } catch (e: any) {
      toast(`保存标记失败：${e?.message || e}`);
    } finally {
      setSavingMark(false);
    }
  }

  async function deleteUserMark(markId: string) {
    if (!activeSection) return;
    try {
      await persistSection(activeSection.user_marks.filter((mark) => mark.id !== markId), sectionNote, true);
      toast("标记已删除");
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  async function saveSectionNote(silent = false) {
    if (!activeSection || savingNote) return;
    setSavingNote(true);
    try {
      await persistSection(activeSection.user_marks, sectionNote, silent);
    } catch (e: any) {
      toast(`保存感想失败：${e?.message || e}`);
    } finally {
      setSavingNote(false);
    }
  }

  async function completeSection() {
    if (!activeBook || !activeSection || completing || completeInFlightRef.current) return;
    const cleanWindowId = String(windowId || "").trim();
    if (!cleanWindowId) {
      toast("当前还没拿到聊天窗口 ID");
      return;
    }
    completeInFlightRef.current = true;
    setCompleting(true);
    try {
      const data = await apiJson<CoReadSectionCompleteResponse>(`/miniapp-api/co-read/books/${encodeURIComponent(activeBook.book_key)}/sections/${encodeURIComponent(activeSection.section_id)}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          window_id: cleanWindowId,
          user_marks: activeSection.user_marks,
          user_section_note: sectionNote,
          include_book: false,
          defer_card_update: true,
        }),
      });
      const book = coReadBookFromUpdatePayload(activeBook, data, activeSection.index);
      if (!data?.ok || !book) throw new Error(data?.error || "读完提交失败");
      setActiveBook(book);
      upsertBookSummary(book);
      writeCachedCoReadBook(book);
      toast("这一节已和渡读完");
    } catch (e: any) {
      toast(`提交失败：${e?.message || e}`);
    } finally {
      completeInFlightRef.current = false;
      setCompleting(false);
    }
  }

  function goToSection(index: number) {
    if (!activeBook) return;
    const nextIndex = Math.max(0, Math.min(activeBook.sections.length - 1, index));
    const nextSection = activeBook.sections[nextIndex];
    const nextBook = { ...activeBook, current_section_index: nextIndex };
    setActiveBook(nextBook);
    writeCachedCoReadBook(nextBook);
    setSelectedText("");
    setMarkNote("");
    setActiveMarkPopup([]);
    requestAnimationFrame(() => readerRef.current?.scrollTo({ top: 0, behavior: "auto" }));
    void apiJson<CoReadBookResponse>(`/miniapp-api/co-read/books/${encodeURIComponent(activeBook.book_key)}/sections/${encodeURIComponent(nextSection.section_id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include_book: false }),
    }).then((data) => {
      const book = coReadBookFromUpdatePayload(nextBook, data, nextSection.index);
      if (data?.ok && book) {
        setActiveBook(book);
        upsertBookSummary(book);
        writeCachedCoReadBook(book);
      }
    }).catch(() => {});
  }

  function scrollToCoReadMark(mark: CoReadMark) {
    const root = readerRef.current;
    if (!root || !mark.id) return;
    const escapedId = typeof CSS !== "undefined" && CSS.escape
      ? CSS.escape(mark.id)
      : mark.id.replace(/["\\]/g, "\\$&");
    const target = root.querySelector<HTMLElement>(`[data-co-read-mark-ids~="${escapedId}"]`);
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function openUserMarkCard(mark: CoReadMark) {
    setActiveMarkPopup([mark]);
    requestAnimationFrame(() => scrollToCoReadMark(mark));
  }

  if (activeBook && activeSection) {
    const sectionIndex = Math.max(0, activeBook.current_section_index);
    const canGoPrev = sectionIndex > 0;
    const canGoNext = sectionIndex < activeBook.sections.length - 1;
    return (
      <div
        className={`absolute inset-0 z-30 flex flex-col overflow-hidden ${theme.shell}`}
        onTouchStart={handleCoReadTouchStart}
        onTouchMove={handleCoReadTouchMove}
        onTouchEnd={handleCoReadTouchEnd}
        onTouchCancel={() => {
          swipeRef.current.tracking = false;
        }}
      >
        <header className={`z-20 flex items-center border-b px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)] ${theme.dock}`}>
          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-full transition-colors active:bg-black/5"
            onClick={closeCurrentLevel}
            aria-label="返回书架"
          >
            <ChevronLeftIcon />
          </button>
          <div className="min-w-0 flex-1 text-center">
            <div className="truncate text-[13px] font-semibold">{activeBook.book_title}</div>
            <div className={`mt-0.5 text-[11px] font-mono ${theme.muted}`}>第 {activeSection.index}/{activeBook.sections.length} 小节 · {formatCoReadSectionRange(activeBook, activeSection)}</div>
          </div>
          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-full transition-colors active:bg-black/5"
            onClick={() => setSettingsOpen(true)}
            aria-label="阅读设置"
          >
            <SettingsIconMini />
          </button>
        </header>

        <div className={`z-20 border-b px-4 py-2 ${theme.dock}`}>
          <div className="mx-auto flex max-w-[760px] items-center gap-2 overflow-x-auto pb-1">
            {activeBook.sections.map((section, index) => (
              <button
                key={section.section_id}
                type="button"
                className={`h-8 shrink-0 rounded-full border px-3 font-mono text-[11px] font-semibold ${index === sectionIndex ? "border-[#111111] bg-[#111111] text-white" : `${theme.panel} ${theme.muted}`}`}
                onClick={() => goToSection(index)}
              >
                {section.index}{section.status === "done" ? " ✓" : ""}
              </button>
            ))}
          </div>
        </div>

        {selectedText ? (
          <div className={`z-20 border-b px-4 py-3 ${theme.dock}`}>
            <div className="mx-auto max-w-[760px] space-y-2">
              <div className={`truncate text-[12px] font-medium ${theme.muted}`}>粉色标记：{compactCoReadText(selectedText, 58)}</div>
              <div className="flex items-center gap-2">
                <input
                  className={`h-10 min-w-0 flex-1 rounded-full border px-4 text-[13px] outline-none ${theme.input}`}
                  value={markNote}
                  onChange={(e) => setMarkNote(e.target.value)}
                  placeholder="写一点感想"
                />
                <button
                  type="button"
                  className="h-10 shrink-0 rounded-full bg-[#111111] px-4 text-[13px] font-semibold text-white disabled:opacity-40"
                  onClick={saveUserMark}
                  disabled={savingMark}
                >
                  保存
                </button>
                <button
                  type="button"
                  className={`h-10 shrink-0 rounded-full px-3 text-[13px] font-semibold ${theme.muted}`}
                  onClick={clearCoReadSelection}
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        ) : null}

        <div
          ref={readerRef}
          className={`min-h-0 max-w-full flex-1 overflow-x-hidden overflow-y-auto ${readerPadding} pb-[calc(env(safe-area-inset-bottom,0px)+34px)] pt-5`}
          onMouseUp={captureSelection}
          onTouchEnd={() => window.setTimeout(captureSelection, 80)}
          onContextMenu={(event) => event.preventDefault()}
          style={{ fontSize: `${settings.fontSize}px`, lineHeight: settings.lineHeight, WebkitTouchCallout: "none" } as React.CSSProperties}
        >
          <article className="mx-auto max-w-[760px]">
            <div
              className="select-text whitespace-pre-wrap break-words [overflow-wrap:anywhere]"
              onContextMenu={(event) => event.preventDefault()}
              style={{ WebkitTouchCallout: "none" } as React.CSSProperties}
            >
              {renderCoReadMarkedText(
                activeSectionText,
                activeSection.char_start,
                activeSection.user_marks,
                activeSection.du_marks,
                (marks) => setActiveMarkPopup(marks),
              )}
            </div>

            <section className={`mt-10 rounded-[18px] border p-4 ${theme.panel}`}>
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="text-[14px] font-semibold">我的粉色标记</div>
                <div className={`font-mono text-[11px] ${theme.muted}`}>{activeSection.user_marks.length}</div>
              </div>
              {activeSection.user_marks.length ? (
                <div className="space-y-2">
                  {activeSection.user_marks.map((mark) => (
                    <div
                      key={mark.id}
                      className="cursor-pointer rounded-[14px] bg-[#FFEAF1] px-3 py-2 text-[#5D2A3A]"
                      role="button"
                      tabIndex={0}
                      onClick={() => openUserMarkCard(mark)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openUserMarkCard(mark);
                        }
                      }}
                    >
                      <div className="text-[12px] leading-5">「{compactCoReadText(mark.quote, 80)}」</div>
                      {mark.note ? <div className="mt-1 text-[13px] leading-5 text-[#7A3A4D]">{mark.note}</div> : null}
                      {mark.du_reply ? (
                        <div className="mt-2 rounded-[12px] bg-[#E6F0FF] px-3 py-2 text-[#263D66]">
                          <div className="text-[11px] font-semibold">渡的回复</div>
                          <div className="mt-1 text-[13px] leading-5">{mark.du_reply}</div>
                        </div>
                      ) : null}
                      <button
                        type="button"
                        className="mt-1 text-[12px] font-semibold text-[#B85673]"
                        onClick={(event) => {
                          event.stopPropagation();
                          void deleteUserMark(mark.id);
                        }}
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className={`text-[13px] ${theme.muted}`}>选中原文后可以留下粉色标记。</div>
              )}
            </section>

            <section className={`mt-4 rounded-[18px] border p-4 ${theme.panel}`}>
              <div className="mb-3 text-[14px] font-semibold">我的小节感想</div>
              <textarea
                className={`min-h-[96px] w-full resize-none rounded-[16px] border px-3 py-3 text-[14px] leading-6 outline-none ${theme.input}`}
                value={sectionNote}
                onChange={(e) => setSectionNote(e.target.value)}
                placeholder="读完这一节时想留下的话"
              />
              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  className={`h-10 rounded-full border px-4 text-[13px] font-semibold disabled:opacity-40 ${theme.panel}`}
                  onClick={() => void saveSectionNote(false)}
                  disabled={savingNote}
                >
                  保存感想
                </button>
                <button
                  type="button"
                  className="h-10 flex-1 rounded-full bg-[#111111] px-4 text-[13px] font-semibold text-white disabled:opacity-40"
                  onClick={completeSection}
                  disabled={completing}
                >
                  {completing ? "渡在读这一节..." : activeSection.status === "done" ? "重新读完这一节" : "读完这一节"}
                </button>
              </div>
            </section>

            {activeSection.du_marks.length || activeSection.du_section_note ? (
              <section className={`mt-4 rounded-[18px] border p-4 ${theme.panel}`}>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="text-[14px] font-semibold">渡的蓝色标记</div>
                  <div className={`font-mono text-[11px] ${theme.muted}`}>{activeSection.du_marks.length}</div>
                </div>
                {activeSection.du_marks.length ? (
                  <div className="mb-4 space-y-2">
                    {activeSection.du_marks.map((mark) => (
                      <div key={mark.id} className="rounded-[14px] bg-[#E6F0FF] px-3 py-2 text-[#263D66]">
                        <div className="text-[12px] leading-5">「{compactCoReadText(mark.quote, 80)}」</div>
                        {mark.note ? <div className="mt-1 text-[13px] leading-5 text-[#36598F]">{mark.note}</div> : null}
                      </div>
                    ))}
                  </div>
                ) : null}
                {activeSection.du_section_note ? (
                  <div className={`rounded-[14px] px-3 py-3 text-[14px] leading-7 ${theme.soft}`}>{activeSection.du_section_note}</div>
                ) : null}
              </section>
            ) : null}

            <div className="mt-5 flex items-center justify-between gap-3">
              <button
                type="button"
                className={`h-11 rounded-full border px-5 text-[13px] font-semibold disabled:opacity-30 ${theme.panel}`}
                onClick={() => goToSection(sectionIndex - 1)}
                disabled={!canGoPrev}
              >
                上一节
              </button>
              <button
                type="button"
                className={`h-11 rounded-full border px-5 text-[13px] font-semibold disabled:opacity-30 ${theme.panel}`}
                onClick={() => goToSection(sectionIndex + 1)}
                disabled={!canGoNext}
              >
                下一节
              </button>
            </div>
          </article>
        </div>

        {activeMarkPopup.length ? (
          <div className="pointer-events-none fixed inset-x-4 bottom-[calc(env(safe-area-inset-bottom,0px)+18px)] z-50 flex justify-center">
            <div className={`pointer-events-auto max-h-[46vh] w-full max-w-[520px] overflow-y-auto rounded-[18px] border p-4 shadow-[0_18px_46px_rgba(0,0,0,0.18)] ${theme.panel}`}>
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className={`font-mono text-[11px] font-semibold uppercase tracking-[0.12em] ${theme.muted}`}>mark</div>
                <button
                  type="button"
                  className={`rounded-full px-3 py-1 text-[12px] font-semibold ${theme.muted}`}
                  onClick={() => setActiveMarkPopup([])}
                >
                  关闭
                </button>
              </div>
              <div className="space-y-3">
                {activeMarkPopup.map((mark) => (
                  <div key={mark.id} className={mark.source === "du" ? "text-[#263D66]" : "text-[#5D2A3A]"}>
                    <div className={`mb-1 inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${mark.source === "du" ? "bg-[#E6F0FF]" : "bg-[#FFEAF1]"}`}>
                      {mark.source === "du" ? "渡的蓝色标记" : "我的粉色标记"}
                    </div>
                    {mark.source === "user" ? (
                      <div className="space-y-3">
                        <div>
                          <div className="text-[11px] font-semibold text-[#B85673]">我的内容</div>
                          <div className="mt-1 text-[14px] leading-6">{mark.note || "只标记了这一段"}</div>
                        </div>
                        {mark.du_reply ? (
                          <div className="rounded-[14px] bg-[#E6F0FF] px-3 py-2 text-[#263D66]">
                            <div className="text-[11px] font-semibold">渡的回复</div>
                            <div className="mt-1 text-[14px] leading-6">{mark.du_reply}</div>
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      mark.note ? <div className="mt-1 text-[14px] leading-6">{mark.note}</div> : null
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        {settingsOpen ? (
          <div className="fixed inset-0 z-50 flex items-end bg-black/10" onClick={() => setSettingsOpen(false)}>
            <div
              className={`w-full rounded-t-[28px] border px-6 pb-[calc(env(safe-area-inset-bottom,0px)+26px)] pt-6 shadow-[0_-16px_42px_rgba(0,0,0,0.12)] ${theme.panel}`}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-5 flex items-center justify-between">
                <div className="text-[15px] font-semibold">阅读设置</div>
                <button type="button" className={`rounded-full px-3 py-1.5 text-[13px] ${theme.muted}`} onClick={() => setSettingsOpen(false)}>完成</button>
              </div>
              <div className="space-y-6">
                <section>
                  <button
                    type="button"
                    className={`h-11 w-full rounded-full border text-[13px] font-semibold disabled:opacity-40 ${theme.panel}`}
                    onClick={() => void refreshActiveBook()}
                    disabled={refreshingBook}
                  >
                    {refreshingBook ? "刷新中..." : "刷新当前书"}
                  </button>
                </section>
                <section>
                  <div className={`mb-3 font-mono text-[11px] uppercase tracking-[0.12em] ${theme.muted}`}>typography</div>
                  <div className="grid grid-cols-2 gap-3">
                    <button type="button" className={`h-11 rounded-full border text-[13px] font-semibold ${theme.panel}`} onClick={() => updateSettings((prev) => ({ ...prev, fontSize: Math.max(15, prev.fontSize - 1) }))}>- A</button>
                    <button type="button" className={`h-11 rounded-full border text-[13px] font-semibold ${theme.panel}`} onClick={() => updateSettings((prev) => ({ ...prev, fontSize: Math.min(24, prev.fontSize + 1) }))}>A +</button>
                  </div>
                </section>
                <section>
                  <div className={`mb-3 font-mono text-[11px] uppercase tracking-[0.12em] ${theme.muted}`}>theme</div>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { id: "light" as const, label: "LIGHT", cls: "bg-white text-black" },
                      { id: "dark" as const, label: "DARK", cls: "bg-[#111] text-white" },
                      { id: "paper" as const, label: "PAPER", cls: "bg-[#F4F1EA] text-[#433]" },
                    ].map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={`h-12 rounded-[14px] border font-mono text-[11px] ${item.cls} ${settings.theme === item.id ? "ring-2 ring-[#111111]" : ""}`}
                        onClick={() => updateSettings((prev) => ({ ...prev, theme: item.id }))}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </section>
                <section>
                  <div className={`mb-3 font-mono text-[11px] uppercase tracking-[0.12em] ${theme.muted}`}>spacing</div>
                  <PersonalizationSliderRow
                    title="行距"
                    value={String(settings.lineHeight.toFixed(1))}
                    min={1.4}
                    max={2.2}
                    step={0.1}
                    currentValue={settings.lineHeight}
                    onChange={(next) => updateSettings((prev) => ({ ...prev, lineHeight: next }))}
                  />
                  <div className="mt-4 grid grid-cols-3 gap-2">
                    {[1, 2, 3].map((level) => (
                      <button
                        key={level}
                        type="button"
                        className={`h-9 rounded-full border text-[12px] font-semibold ${settings.marginLevel === level ? "bg-[#111111] text-white" : theme.panel}`}
                        onClick={() => updateSettings((prev) => ({ ...prev, marginLevel: level }))}
                      >
                        边距 {level}
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className="absolute inset-0 z-30 flex flex-col overflow-hidden bg-white text-[#111111]"
      onTouchStart={handleCoReadTouchStart}
      onTouchMove={handleCoReadTouchMove}
      onTouchEnd={handleCoReadTouchEnd}
      onTouchCancel={() => {
        swipeRef.current.tracking = false;
      }}
    >
      <header className="z-20 flex items-center gap-2 border-b border-[#F1F1F1] bg-white px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)]">
        <button type="button" className="flex h-11 w-11 items-center justify-center rounded-full transition-colors active:bg-gray-50" onClick={closeCurrentLevel} aria-label="返回">
          <ChevronLeftIcon />
        </button>
        <div className="min-w-0 flex-1 truncate text-[15px] font-medium">和渡一起读</div>
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-full bg-[#111111] text-white transition-transform active:scale-95 disabled:opacity-40"
          onClick={() => fileInputRef.current?.click()}
          aria-label="导入 TXT"
          disabled={importing}
        >
          <PlusIcon open={importing} />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-[112px] pt-5">
        {loadingBooks ? (
          <div className="flex min-h-[58vh] items-center justify-center font-mono text-[12px] text-[#999999]">loading...</div>
        ) : books.length ? (
          <div className="mx-auto max-w-xl space-y-4">
            {books.map((book) => (
              <button
                key={book.book_key}
                type="button"
                className="w-full rounded-[22px] border border-[#EAEAEA] bg-white p-5 text-left shadow-[0_8px_24px_rgba(0,0,0,0.025)] transition-transform active:scale-[0.99]"
                onClick={() => void openBook(book.book_key)}
              >
                <div className="mb-5 flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 text-[15px] font-semibold leading-5">{book.book_title}</div>
                  <div className="font-mono text-[11px] lowercase text-[#AAAAAA]">txt</div>
                </div>
                <div className="mb-5 flex items-center gap-6">
                  <div>
                    <div className="mb-1 font-mono text-[11px] lowercase tracking-[0.05em] text-[#AAAAAA]">sections</div>
                    <div className="font-mono text-[14px] font-medium">{book.done_count}/{book.section_count}</div>
                  </div>
                  <div className="h-8 w-px bg-black/10" />
                  <div>
                    <div className="mb-1 font-mono text-[11px] lowercase tracking-[0.05em] text-[#AAAAAA]">progress</div>
                    <div className="font-mono text-[14px] font-medium">{formatCoReadProgress(coReadBookProgress(book))}</div>
                  </div>
                  <button
                    type="button"
                    className="ml-auto flex h-9 w-9 items-center justify-center rounded-full text-[#9A9A9A] transition-colors active:bg-gray-50"
                    onClick={(e) => {
                      e.stopPropagation();
                      void deleteBook(book.book_key);
                    }}
                    aria-label="删除"
                  >
                    <TrashIconMini />
                  </button>
                </div>
                <div className="flex items-center justify-between gap-3 text-[12px] leading-5 text-[#777777]">
                  <span>当前第 {Math.min(book.section_count, book.current_section_index + 1)} 小节</span>
                  <span>{loadingBookKey === book.book_key ? "打开中..." : formatCoReadDate(book.updated_at || book.created_at || "")}</span>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="flex min-h-[58vh] flex-col items-center justify-center text-center">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-[#F7F7F7] text-[#777777]">
              <BookOpenIcon />
            </div>
            <div className="text-[16px] font-semibold text-[#111111]">还没有导入的书</div>
            <div className="mt-2 max-w-[240px] text-[13px] leading-5 text-[#888888]">先放一本 TXT 进来，再和渡按小节一起读。</div>
          </div>
        )}
      </div>

      <button
        type="button"
        className="fixed inset-x-5 bottom-[calc(env(safe-area-inset-bottom,0px)+20px)] z-40 h-14 rounded-full bg-[#111111] font-mono text-[12px] font-semibold uppercase tracking-[0.08em] text-white shadow-[0_12px_26px_rgba(0,0,0,0.18)] active:scale-[0.99] disabled:opacity-40"
        onClick={() => fileInputRef.current?.click()}
        disabled={importing}
      >
        {importing ? (importStatus || "正在导入...") : "导入 TXT 资料"}
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".txt,text/plain"
        className="hidden"
        onChange={(e) => {
          void importTxtFile(e.target.files?.[0]);
          e.currentTarget.value = "";
        }}
      />
    </div>
  );
}

function PersonalizationSliderRow({
  title,
  value,
  min,
  max,
  step,
  currentValue,
  onChange,
  disabled = false,
}: {
  title: string;
  value: string;
  min: number;
  max: number;
  step: number;
  currentValue: number;
  onChange?: (next: number) => void;
  disabled?: boolean;
}) {
  const percent = max === min ? 100 : ((currentValue - min) / (max - min)) * 100;
  return (
    <div className="border-b border-[#F9FAFB] py-[14px] last:border-b-0">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[15px] font-medium text-gray-800">{title}</span>
        <span className="text-[13px] font-medium text-gray-400">{value}</span>
      </div>
      <div className={`relative h-[4px] rounded-full bg-[#E2E8F0] ${disabled ? "opacity-50" : ""}`}>
        <div className="absolute left-0 top-0 h-[4px] rounded-full bg-[#1F2937]" style={{ width: `${percent}%` }} />
        <div className="absolute top-1/2 h-[18px] w-[18px] -translate-y-1/2 rounded-full border-2 border-white bg-[#1F2937] shadow-[0_2px_4px_rgba(0,0,0,0.1)]" style={{ left: `calc(${percent}% - 9px)` }} />
        {!disabled ? (
          <input
            type="range"
            className="absolute inset-0 h-[18px] w-full cursor-pointer opacity-0"
            min={min}
            max={max}
            step={step}
            value={currentValue}
            onChange={(e) => onChange?.(Number(e.target.value))}
          />
        ) : null}
      </div>
    </div>
  );
}

function ChevronLeftIcon() {
  return <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>;
}

function PlusIcon({ open }: { open: boolean }) {
  return (
    <svg className={`h-[22px] w-[22px] transition-transform duration-200 ${open ? "rotate-45" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function SettingsIconMini() {
  return <svg className="h-[18px] w-[18px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51c.6.25 1.29.11 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82c.25.6.85 1 1.51 1H21a2 2 0 0 1 0 4h-.09c-.66 0-1.26.4-1.51 1z" /></svg>;
}

function TrashIconMini() {
  return <svg className="h-[15px] w-[15px] stroke-[1.8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v5M14 11v5" /></svg>;
}

function BookOpenIcon() {
  return <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" /></svg>;
}
