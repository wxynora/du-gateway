import type { EntryScene, FeedItem, StoryActionOption, StorySegment, WenyouHistoryItem } from "./types";

export function extractEntryScene(text: string): EntryScene {
  const header = text.match(/【无限流\s*·\s*副本(?:\s*([^｜】\n]+))?(?:｜([^】\n]+))?】/);
  const rawCode = String(header?.[1] || "").trim();
  const rawName = String(header?.[2] || "").trim();
  const name = rawName || rawCode || "未知副本";
  const genre = String(text.match(/【副本类型】([^｜\n]+)/)?.[1] || "").trim();
  const difficulty = String(text.match(/【难度】([DCBAS]|新手|普通|困难|噩梦)/)?.[1] || "").trim();
  return {
    name,
    code: rawName && rawCode ? rawCode : undefined,
    genre: genre || undefined,
    difficulty: difficulty || undefined,
  };
}

function storySystemLabel(raw: string): string | null {
  const label = String(raw || "").trim();
  if (!label) return null;
  if (label.startsWith("无限流")) return "副本接入";
  if (/^任务(?:\s*[:：]|$)/.test(label)) return "系统提示";
  if (label === "副本类型") return "副本类型";
  if (label === "难度") return "难度";
  if (label.startsWith("新手副本") || label.startsWith("副本 ")) return "系统提示";
  if (label === "主神提示") return "主神提示";
  if (label === "规则结算") return "规则结算";
  if (label === "状态") return "状态";
  if (label === "状态更新") return "状态更新";
  if (label === "遭遇结算") return "遭遇结算";
  if (label === "道具结算" || label === "系统判定") return "系统判定";
  if (label === "任务更新" || label === "获得物品") return label;
  return null;
}

function cleanStorySystemText(text: string) {
  return String(text || "")
    .replace(/^[\s｜|:：。]+/, "")
    .replace(/[\s｜|]+$/, "")
    .trim();
}

function taskSystemText(rawLabel: string, content = "") {
  const label = String(rawLabel || "").trim();
  if (!/^任务(?:\s*[:：]|$)/.test(label)) return "";
  const inline = label.replace(/^任务\s*[:：]?\s*/, "").trim();
  const body = inline || cleanStorySystemText(content);
  return body ? `任务：${body}` : "任务已更新";
}

function formatStorySystemText(rawLabel: string, content = "") {
  const label = String(rawLabel || "").trim();
  const taskText = taskSystemText(label, content);
  if (taskText) return taskText;
  const text = cleanStorySystemText(content);
  if (label.startsWith("无限流")) return label.replace(/｜/g, " | ");
  if (label === "副本类型") return `副本类型：${text || "未知"}`;
  if (label === "难度") return `难度：${text || "-"}`;
  if (label === "状态") return text ? `状态：${text}` : "状态更新";
  return text || label;
}

function hiddenStorySystemLabel(label: string) {
  return [
    "规则结算",
    "状态",
    "规则状态",
    "后台状态",
    "内部状态",
    "结算缓存",
  ].includes(String(label || "").trim());
}

export function looksLikeInternalPayload(text: string) {
  const value = String(text || "").trim();
  if (!value) return false;
  const compact = value.replace(/\s+/g, " ");
  const hasInternalKey = /['"]?(?:event|risk|targets|tags|action_state|conditions_add|conditions_remove|clock_updates|rule_updates|clue_updates|task_update|state_proposals|id|public_text|leads_to|is_required_for_mainline|runtime_state|rules_state|last_state_patch|threat_clocks|settlement_flags|event_intent|state_patch|gm_state|private_state|npc_private_state|forced_instance|reward_hint)['"]?\s*:/i.test(compact);
  const wrapped = /^[{[]/.test(compact) || /[}\]]$/.test(compact);
  const keyPairs = compact.match(/['"]?[a-zA-Z_][\w-]*['"]?\s*:/g) || [];
  return hasInternalKey && (wrapped || keyPairs.length >= 3);
}

function pushStorySegment(segments: StorySegment[], text: string) {
  const t = String(text || "").trim();
  if (!t || t === "—— 主神系统 ——" || /^━+$/.test(t) || looksLikeInternalPayload(t)) return;
  const last = segments[segments.length - 1];
  if (last?.kind === "story") {
    last.text = `${last.text}\n${t}`;
    return;
  }
  segments.push({ id: `story-${segments.length}`, kind: "story", text: t });
}

function pushSystemSegment(segments: StorySegment[], label: string, text: string) {
  const body = cleanStorySystemText(text);
  if (!body || hiddenStorySystemLabel(label) || looksLikeInternalPayload(body)) return false;
  segments.push({ id: `system-${segments.length}`, kind: "system", label, text: body });
  return true;
}

function pushTaskSystemSegment(segments: StorySegment[], text: string) {
  const body = cleanStorySystemText(text);
  if (!body) return false;
  const last = segments[segments.length - 1];
  if (last?.kind === "system" && ["副本接入", "系统提示"].includes(last.label || "")) {
    last.text = `${last.text}\n${body}`;
    return true;
  }
  segments.push({ id: `system-${segments.length}`, kind: "system", label: "系统提示", text: body });
  return true;
}

function cleanActionOptionText(text: string) {
  return String(text || "")
    .replace(/\*\*/g, "")
    .replace(/^[-*·]\s*/, "")
    .replace(/[“”]/g, "\"")
    .replace(/\s+/g, " ")
    .trim();
}

function actionOptionLine(line: string) {
  const clean = cleanActionOptionText(line);
  return clean.match(/^[（(【[]\s*([A-Ha-hＡ-Ｈａ-ｈ])\s*[）)】\]]\s*(.+)$/)
    || clean.match(/^([A-Ha-hＡ-Ｈａ-ｈ])\s*[.．、:：)）]\s*(.+)$/);
}

function isStandaloneStorySystemLine(line: string) {
  const match = cleanActionOptionText(line).match(/^【([^】]{1,42})】$/);
  return match ? storySystemLabel(match[1]) : null;
}

function extractActionOptions(lines: string[]) {
  const headingIndex = lines.findIndex((line) => /【\s*行动选项\s*】|^行动选项[:：]?$/.test(cleanActionOptionText(line)));
  let startIndex = headingIndex >= 0 ? headingIndex + 1 : -1;
  if (startIndex < 0) {
    const firstOptionIndex = lines.findIndex((line, index) => {
      const current = actionOptionLine(line);
      const next = lines.slice(index + 1).some((it) => actionOptionLine(it));
      return !!current && next;
    });
    if (firstOptionIndex >= 0) startIndex = firstOptionIndex;
  }
  if (startIndex < 0) return null;
  const options: StoryActionOption[] = [];
  let current: StoryActionOption | null = null;
  let stopIndex = lines.length;
  for (let index = startIndex; index < lines.length; index += 1) {
    const rawLine = lines[index];
    const line = cleanActionOptionText(rawLine);
    if (!line) continue;
    if (options.length && isStandaloneStorySystemLine(line)) {
      stopIndex = index;
      break;
    }
    const match = actionOptionLine(line);
    if (match) {
      const key = match[1].normalize("NFKC").toUpperCase();
      const text = cleanActionOptionText(match[2]);
      current = {
        key,
        text,
        free: /^自由行动[。.!！?？]*$/.test(text),
      };
      options.push(current);
      continue;
    }
    if (current) {
      current.text = cleanActionOptionText(`${current.text} ${line}`);
      current.free = /^自由行动[。.!！?？]*$/.test(current.text);
    }
  }
  if (!options.length) return null;
  return {
    before: lines.slice(0, headingIndex >= 0 ? headingIndex : startIndex),
    options,
    after: lines.slice(stopIndex),
  };
}

function pushActionSegment(segments: StorySegment[], options: StoryActionOption[]) {
  if (!options.length) return;
  segments.push({ id: `actions-${segments.length}`, kind: "actions", text: "", options });
}

function appendStorySegments(segments: StorySegment[], nextSegments: StorySegment[]) {
  for (const segment of nextSegments) {
    segments.push({ ...segment, id: `${segment.id}-${segments.length}` });
  }
}

function splitInlineSystemPrompt(segments: StorySegment[], line: string): boolean {
  const text = String(line || "").trim();
  if (!text) return false;
  const re = /(.*?(?:机械女声|冰冷女声|电子音|提示音|系统(?:提示|广播|音)?|主神(?:提示|广播|音)?)[^“”"「」]{0,36}(?:响起|传来|播报|宣告|提示|开口|说道|说|道)?\s*[：:]\s*)[“"「]([^”"」]{6,360}(?:系统|副本|任务|清算|载入|锁定|提示|规则|编号)[^”"」]{0,360})[”"」](.*)/;
  const match = text.match(re);
  if (!match) return false;
  pushStorySegment(segments, match[1].replace(/[：:]\s*$/, "。"));
  pushSystemSegment(segments, "系统提示", match[2]);
  const rest = String(match[3] || "").trim();
  if (rest) splitStoryLine(segments, rest);
  return true;
}

function knownMarkers(line: string) {
  const matches: Array<{ start: number; end: number; raw: string; label: string }> = [];
  const re = /【([^】]{1,42})】/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(line))) {
    const label = storySystemLabel(match[1]);
    if (label) {
      matches.push({ start: match.index, end: match.index + match[0].length, raw: match[1], label });
    }
  }
  return matches;
}

function formatEntryMetadataBlock(block: string) {
  const lines: string[] = [];
  for (const line of block.split("\n").map((it) => it.trim()).filter(Boolean)) {
    const matches = knownMarkers(line);
    for (let i = 0; i < matches.length; i += 1) {
      const marker = matches[i];
      const next = matches[i + 1]?.start ?? line.length;
      lines.push(formatStorySystemText(marker.raw, line.slice(marker.end, next)));
    }
  }
  return lines.filter(Boolean).join("\n");
}

function splitStoryLine(segments: StorySegment[], line: string) {
  if (looksLikeInternalPayload(line)) return;
  if (splitInlineSystemPrompt(segments, line)) return;
  const matches = knownMarkers(line);
  if (!matches.length) {
    pushStorySegment(segments, line);
    return;
  }
  let cursor = 0;
  for (let i = 0; i < matches.length; i += 1) {
    const marker = matches[i];
    const next = matches[i + 1]?.start ?? line.length;
    pushStorySegment(segments, line.slice(cursor, marker.start));
    const taskHasInlineValue = /^任务\s*[:：]\s*\S/.test(String(marker.raw || ""));
    const taskText = taskSystemText(marker.raw, taskHasInlineValue ? "" : line.slice(marker.end, next));
    if (taskText) {
      pushTaskSystemSegment(segments, taskText);
      cursor = taskHasInlineValue ? marker.end : next;
      continue;
    }
    pushSystemSegment(segments, marker.label, formatStorySystemText(marker.raw, line.slice(marker.end, next)));
    cursor = next;
  }
  pushStorySegment(segments, line.slice(cursor));
}

export function parseStorySegments(text: string): StorySegment[] {
  const clean = String(text || "").replace(/\r/g, "").trim();
  if (!clean) return [];
  const segments: StorySegment[] = [];
  let consumedStructuredBlock = false;
  for (const rawBlock of clean.split(/\n{2,}/)) {
    const block = rawBlock.trim();
    if (!block || block === "—— 主神系统 ——") continue;
    if (looksLikeInternalPayload(block)) {
      consumedStructuredBlock = true;
      continue;
    }
    if (/^━+\n?/.test(block) && block.includes("【状态】")) {
      consumedStructuredBlock = true;
      pushSystemSegment(segments, "状态", block.replace(/^━+\n?/, "").replace(/\n?━+$/, ""));
      continue;
    }
    if (block.startsWith("【无限流") || (block.includes("【副本类型】") && block.includes("【难度】"))) {
      consumedStructuredBlock = true;
      pushSystemSegment(segments, "副本接入", formatEntryMetadataBlock(block));
      continue;
    }
    const lines = block.split("\n").map((it) => it.trim()).filter(Boolean);
    const firstInlineMarker = lines[0]?.match(/^【([^】]{1,42})】/);
    const firstInlineLabel = firstInlineMarker ? storySystemLabel(firstInlineMarker[1]) : null;
    if (firstInlineLabel && hiddenStorySystemLabel(firstInlineLabel)) {
      consumedStructuredBlock = true;
      continue;
    }
    const actionOptions = extractActionOptions(lines);
    if (actionOptions) {
      consumedStructuredBlock = true;
      for (const line of actionOptions.before) splitStoryLine(segments, line);
      pushActionSegment(segments, actionOptions.options);
      appendStorySegments(segments, parseStorySegments(actionOptions.after.join("\n")));
      continue;
    }
    const firstOnlyMarker = lines[0]?.match(/^【([^】]{1,42})】$/);
    const firstLabel = firstOnlyMarker ? storySystemLabel(firstOnlyMarker[1]) : null;
    const firstTaskText = firstOnlyMarker ? taskSystemText(firstOnlyMarker[1], "") : "";
    if (firstTaskText) {
      consumedStructuredBlock = true;
      pushTaskSystemSegment(segments, firstTaskText);
      for (const line of lines.slice(1)) splitStoryLine(segments, line);
      continue;
    }
    if (firstOnlyMarker && firstLabel && lines.length > 1) {
      consumedStructuredBlock = true;
      pushSystemSegment(segments, firstLabel, lines.slice(1).join("\n"));
      continue;
    }
    for (const line of lines) splitStoryLine(segments, line);
  }
  return segments.length || consumedStructuredBlock ? segments : [{ id: "story-0", kind: "story", text: clean }];
}

export function feedFromSessionHistory(history?: WenyouHistoryItem[]): FeedItem[] {
  if (!Array.isArray(history)) return [];
  return history
    .map<FeedItem | null>((item, index) => {
      const text = String(item?.content || "").trim();
      if (!text) return null;
      const role = String(item?.role || "").trim().toLowerCase();
      const stamp = String(item?.timestamp || index || "");
      const id = `history-${role || "row"}-${index}-${stamp}`;
      if (role === "player1" || role === "user") {
        return { id, kind: "user" as const, text };
      }
      if (role === "player2" || role === "ai_player") {
        return { id, kind: "ai_player" as const, text };
      }
      return { id, kind: "system" as const, text };
    })
    .filter((item): item is FeedItem => !!item);
}
