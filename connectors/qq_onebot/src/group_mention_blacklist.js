export const DEFAULT_QQ_GROUP_MENTION_BLACKLIST = Object.freeze([
  "3299553137",
  "190689686",
]);

export function parseQqGroupMentionBlacklist(raw) {
  const configured = String(raw || "").trim();
  const values = configured
    ? configured.split(/[,\s]+/)
    : DEFAULT_QQ_GROUP_MENTION_BLACKLIST;
  return new Set(
    values
      .map((value) => String(value || "").trim())
      .filter((value) => /^\d+$/.test(value))
  );
}

export function shouldIgnoreQqGroupMention(event, mentionsSelf, blacklist) {
  if (!mentionsSelf) return false;
  const senderId = String(event?.user_id || event?.sender?.user_id || "").trim();
  return !!senderId && blacklist instanceof Set && blacklist.has(senderId);
}
