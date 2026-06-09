import {
  groupRoleLabel,
  type ChatDraftMessage,
} from "../chatMessages";

export type GroupReplyTargets = {
  du: boolean;
  benben: boolean;
  mentions: string[];
  benbenMode: "daily_chat" | "coding_task";
  codingThreadKey: string;
  freeDiscussion: boolean;
};

export type GroupDiscussionSpeaker = "du" | "benben";

export type GroupDiscussionSnapshot = {
  topic: string;
  replyTarget: string;
  lastSpeaker: GroupDiscussionSpeaker;
  lastContent: string;
  freeRoute: boolean;
  updatedAt: number;
};

export const GROUP_DISCUSSION_MAX_FOLLOWUPS = 3;

const GROUP_DISCUSSION_TRIGGER_RE = /(?:讨论|商量|你俩|你们俩|自由聊|一起聊|一起看看|聊两句|聊几句|互相|碰一下|合计|对一下|头脑风暴)/i;
const GROUP_DISCUSSION_STOP_RE = /(?:先这样|先到这|就先这样|差不多(?:了|就行|可以)|可以收尾|不用继续|别聊了|到这里|我来改|我去改|先按这个)/i;
const GROUP_DISCUSSION_MANUAL_STOP_RE = /(?:停一下|停止|暂停|打断|中断|别聊了|不用继续|先这样|收尾|到这里|算了)/i;
const GROUP_DISCUSSION_CONTINUE_RE = /(?:继续聊|接着聊|再聊|继续讨论|再讨论|你俩继续|你们俩继续|让(?:他们|你俩|你们俩)继续)/i;

function uniqueNonEmptyStrings(values: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const item = String(value || "").trim();
    if (!item || seen.has(item)) continue;
    seen.add(item);
    out.push(item);
  }
  return out;
}

function resolveCodingThreadKey(content: string): string {
  const text = String(content || "").toLowerCase();
  if (/文游|主神|副本|玩家|道具|抽卡|结算|怪物|npc|wenyou/.test(text)) return "wenyou";
  if (/miniapp|小程序|前端|页面|界面|按钮|气泡|样式|ui|tsx|react/.test(text)) return "miniapp";
  if (/studyroom|学习|题库|错题|资料整理/.test(text)) return "studyroom";
  if (/小爱|音箱|migpt|xiaoai/.test(text)) return "xiaoai";
  if (/后端|接口|路由|网关|存储|r2|api|service|route/.test(text)) return "backend";
  if (/文档|方案|markdown|debug_index|索引/.test(text)) return "docs";
  return "general";
}

export function resolveGroupReplyTargets(content: string): GroupReplyTargets {
  const text = String(content || "");
  const hasDuMention = /[@＠]\s*(?:渡|du)(?![a-z0-9_])/i.test(text);
  const hasBenbenMention = /[@＠]\s*(?:笨笨机|笨笨|benben|codex)(?![a-z0-9_])/i.test(text);
  const hasFreeDiscussion = hasDuMention && hasBenbenMention && GROUP_DISCUSSION_TRIGGER_RE.test(text);
  const hasCodingCommand = hasBenbenMention && !hasFreeDiscussion && /(?:改代码|开工|施工|debug|调试|修\s*bug|修一下|实现|落地|加上|做一下)/i.test(text);
  const mentions = uniqueNonEmptyStrings([
    hasDuMention ? "du" : "",
    hasBenbenMention ? "benben" : "",
  ]);
  if (mentions.length) {
    return {
      du: hasDuMention,
      benben: hasBenbenMention,
      mentions,
      benbenMode: hasCodingCommand ? "coding_task" : "daily_chat",
      codingThreadKey: hasCodingCommand ? resolveCodingThreadKey(text) : "",
      freeDiscussion: hasFreeDiscussion,
    };
  }
  return { du: true, benben: false, mentions: [], benbenMode: "daily_chat", codingThreadKey: "", freeDiscussion: false };
}

export function resolveEffectiveGroupReplyTargets(content: string, freeChatEnabled: boolean): GroupReplyTargets {
  const targets = resolveGroupReplyTargets(content);
  if (!freeChatEnabled) return targets;
  if (!targets.mentions.length) {
    return {
      du: true,
      benben: true,
      mentions: ["du", "benben"],
      benbenMode: "daily_chat",
      codingThreadKey: "",
      freeDiscussion: true,
    };
  }
  if (targets.du && targets.benben && targets.benbenMode === "daily_chat") {
    return { ...targets, freeDiscussion: true };
  }
  return targets;
}

export function isBenbenCancelCommand(content: string): boolean {
  const text = String(content || "");
  const hasBenbenMention = /[@＠]\s*(?:笨笨机|笨笨|benben|codex)(?![a-z0-9_])/i.test(text);
  return hasBenbenMention && /(?:停一下|停止|取消|中断|打断|别改了|别施工|别做了|暂停|kill|算了)/i.test(text);
}

export function isGroupDiscussionStopCommand(content: string): boolean {
  return GROUP_DISCUSSION_MANUAL_STOP_RE.test(String(content || ""));
}

export function isGroupDiscussionContinueCommand(content: string): boolean {
  return GROUP_DISCUSSION_CONTINUE_RE.test(String(content || ""));
}

export function parseGroupDiscussionContinueTurns(content: string): number {
  const text = String(content || "");
  if (/[一1]/.test(text)) return 1;
  if (/[三3]/.test(text)) return 3;
  return 2;
}

export function codexGroupTaskStatusText(task: Pick<{ mode?: string; status?: string }, "mode" | "status">): string {
  const mode = String(task.mode || "").trim();
  const status = String(task.status || "").trim();
  const isCoding = mode === "coding_task";
  if (isCoding) {
    if (status === "running") return "笨笨施工中，正在改代码 / debug...";
    if (status === "queued") return "笨笨已接单，等待施工...";
    if (status === "cancelled") return "笨笨施工已取消。";
    return "笨笨收到开工指令，正在接单...";
  }
  if (status === "cancelled") return "笨笨任务已取消。";
  if (status === "running") return "笨笨正在看群聊...";
  if (status === "queued") return "笨笨任务已创建，等我一下...";
  return "笨笨正在看群聊...";
}

export function groupDiscussionShouldStop(content: string): boolean {
  return GROUP_DISCUSSION_STOP_RE.test(String(content || ""));
}

export function mentionedGroupSpeaker(content: string, speaker: GroupDiscussionSpeaker): boolean {
  const text = String(content || "");
  if (speaker === "du") return /[@＠]\s*(?:渡|du)(?![a-z0-9_])/i.test(text);
  return /[@＠]\s*(?:笨笨机|笨笨|benben|codex)(?![a-z0-9_])/i.test(text);
}

export function resolveNextGroupDiscussionSpeaker(lastSpeaker: GroupDiscussionSpeaker, lastContent: string): GroupDiscussionSpeaker {
  const mentionsDu = mentionedGroupSpeaker(lastContent, "du");
  const mentionsBenben = mentionedGroupSpeaker(lastContent, "benben");
  if (mentionsDu && !mentionsBenben) return "du";
  if (mentionsBenben && !mentionsDu) return "benben";
  return lastSpeaker === "du" ? "benben" : "du";
}

export function resolveNextFreeDiscussionSpeaker(lastSpeaker: GroupDiscussionSpeaker, lastContent: string): GroupDiscussionSpeaker | null {
  const mentionsDu = mentionedGroupSpeaker(lastContent, "du");
  const mentionsBenben = mentionedGroupSpeaker(lastContent, "benben");
  if (mentionsDu && !mentionsBenben) return "du";
  if (mentionsBenben && !mentionsDu) return "benben";
  if (mentionsDu && mentionsBenben) return lastSpeaker === "du" ? "benben" : "du";
  return null;
}

export function buildGroupFreeDiscussionOpeningContent(messages: ChatDraftMessage[], topic: string): string {
  const lines = (Array.isArray(messages) ? messages : [])
    .filter((msg) => msg.status !== "pending" && msg.status !== "failed")
    .filter((msg) => String(msg.content || "").trim())
    .slice(-10)
    .map((msg) => `${groupRoleLabel(msg.role)}：${String(msg.content || "").trim()}`);
  const fallbackTopic = String(topic || "").trim();
  if (!lines.length && fallbackTopic) lines.push(`辛玥：${fallbackTopic}`);
  return [
    "【三人群聊自由讨论开场】",
    "辛玥在自由聊模式里发了一条群聊广播，这句话同时发给你和笨笨，是想让你们俩围绕这个话题自由聊几句。",
    "你先发一条自然的群聊开场；想让笨笨接，就在正文里明确 @笨笨，不 @ 就自然停。不要把历史里笨笨之前对辛玥的回复当成对你的私聊。",
    "只输出渡要发到群里的正文，不要写“渡：”前缀，不要解释规则。",
    `原话题：${fallbackTopic || "（无）"}`,
    "最近群聊：",
    ...lines,
  ].join("\n");
}

export function buildGroupDiscussionUserContent(
  messages: ChatDraftMessage[],
  topic: string,
  turnIndex: number,
  maxTurns: number,
): string {
  const lines = (Array.isArray(messages) ? messages : [])
    .filter((msg) => msg.status !== "pending" && msg.status !== "failed")
    .filter((msg) => String(msg.content || "").trim())
    .slice(-12)
    .map((msg) => `${groupRoleLabel(msg.role)}：${String(msg.content || "").trim()}`);
  const fallbackTopic = String(topic || "").trim();
  if (!lines.length && fallbackTopic) lines.push(`辛玥：${fallbackTopic}`);
  return [
    "【三人群聊自由讨论接力】",
    `原话题：${fallbackTopic || "（无）"}`,
    `这是自动接力第 ${turnIndex}/${maxTurns} 条。你是渡，接着最近一条自然回复一小段。`,
    "规则：这是辛玥、渡、笨笨都能看见的公共群聊；辛玥在自由聊模式里的发言默认同时发给你和笨笨。不要把笨笨上一句默认理解成对你的私聊，除非它明确 @ 了你。想让笨笨继续就明确 @笨笨，不 @ 就自然停。只发群聊正文，不要写“渡：”前缀；不要替辛玥决定；不要进入施工、调工具或汇报流程；如果结论已经差不多，就自然收尾。",
    "最近群聊：",
    ...lines,
  ].join("\n");
}
