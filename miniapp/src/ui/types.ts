export type MiniappStatus = {
  summary?: { ok?: boolean; has_summary?: boolean; length?: number; error?: string };
  r2?: { ok?: boolean; message?: string; error?: string };
  dynamic_memory?: { ok?: boolean; count?: number; error?: string };
  core_cache?: { ok?: boolean; pending_count?: number; error?: string };
  notebook?: { ok?: boolean; count?: number; error?: string };
  whitelist?: { ok?: boolean; count?: number; error?: string };
  blacklist?: { ok?: boolean; count?: number; error?: string };
  recent_windows?: { ok?: boolean; count?: number; error?: string };
};

export type WindowItem = {
  id?: string;
  last_seen?: string;
  whitelisted?: boolean;
  blacklisted?: boolean;
};

export type RoundPreview = { index?: number; preview?: string };
export type ConversationRound = { index?: number; timestamp?: string; messages?: any[] };

export type CoreCacheEntry = {
  id?: string;
  content?: string;
  importance?: number;
  mention_count?: number;
  promoted_at?: string;
  promoted_by?: string;
  tag?: string;
};

export type CoreCacheResponse = { pending?: CoreCacheEntry[]; count?: number };
export type NotebookEntry = { timestamp?: string; content?: string };
export type NotebookResponse = { entries?: NotebookEntry[]; count?: number };

