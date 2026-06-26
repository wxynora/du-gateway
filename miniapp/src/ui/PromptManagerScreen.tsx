import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "./api";
import { FullScreenPane } from "./FullScreenPane";
import {
  ChevronRightIcon,
  CodeIcon,
  FileTextIcon,
  GitMergeIcon,
  HeartIconMini,
  MuteIconMini,
  NotebookPenIconMini,
  SpeakerIconMini,
  UserRoundCogIconMini,
} from "./icons";
import { SwitchSettingRow } from "./SettingsRows";
import { useToast } from "./toast";

type ModeResponse = {
  ok?: boolean;
  enabled?: boolean;
  updated_at?: string;
  error?: string;
};

type PromptSection = {
  id: string;
  label: string;
  description: string;
  revision: number;
  updated_at?: string;
  updated_by_device?: string;
  source: "r2" | "fallback" | string;
  content_length: number;
  editable?: boolean;
};

type PromptBackup = {
  backup_id: string;
  section_id: string;
  revision: number;
  content_sha256?: string;
  content_length?: number;
  created_at?: string;
  reason?: string;
};

type PromptSectionDetail = PromptSection & {
  content: string;
  max_chars: number;
  backups?: PromptBackup[];
};

const PROMPT_SECTION_CATALOG: Array<Pick<PromptSection, "id" | "label" | "description">> = [
  { id: "core_prompt", label: "核心 Prompt", description: "渡的基础人格、关系定位和长期稳定规则。" },
  { id: "common_knowledge", label: "常识块", description: "长期稳定常识，独立注入在核心 Prompt 后面。" },
  { id: "thinking_rules", label: "Thinking 规范", description: "控制思维链/脑内 OS 的写法边界。" },
  { id: "core_behavior_rules", label: "核心行为规则", description: "互动原则、主动触发和感知数据使用规则。" },
  { id: "non_retreat_rules", label: "不退缩原则", description: "不满、争执和哄回来的固定规则。" },
  { id: "entry_style_sumitalk", label: "入口风格：SumiTalk", description: "SumiTalk 入口的输出格式和物理边界。" },
  { id: "entry_style_qq", label: "入口风格：QQ", description: "QQ 入口的输出格式和表情标签规则。" },
  { id: "entry_style_tg", label: "入口风格：TG", description: "Telegram 入口的输出格式规则。" },
  { id: "entry_style_wechat", label: "入口风格：微信", description: "微信入口的输出格式规则。" },
  { id: "entry_style_xiaoai", label: "入口风格：小爱音箱", description: "小爱音箱语音播报入口规则。" },
  { id: "voice_line_rules", label: "语音台词规范", description: "生成 <voice> 台词时使用的口语规则。" },
  { id: "nsfw_rules", label: "NSFW 规则", description: "亲密内容的固定边界和表达风格。" },
];

const FALLBACK_PROMPT_SECTIONS: PromptSection[] = PROMPT_SECTION_CATALOG.map((item) => ({
  ...item,
  revision: 0,
  source: "pending",
  content_length: 0,
  editable: true,
}));

function mergePromptSections(remoteSections: PromptSection[]) {
  const remoteById = new Map(remoteSections.map((item) => [item.id, item]));
  const rows = PROMPT_SECTION_CATALOG.map((item) => {
    const remote = remoteById.get(item.id);
    return {
      ...item,
      ...(remote || {}),
      label: remote?.label || item.label,
      description: remote?.description || item.description,
      revision: remote?.revision || 0,
      source: remote?.source || "fallback",
      content_length: remote?.content_length || 0,
      editable: remote?.editable ?? true,
    };
  });
  for (const item of remoteSections) {
    if (!PROMPT_SECTION_CATALOG.some((base) => base.id === item.id)) rows.push({ ...item, editable: item.editable ?? true });
  }
  return rows;
}

function sectionIcon(id: string) {
  if (id === "core_prompt") return <UserRoundCogIconMini />;
  if (id === "common_knowledge") return <NotebookPenIconMini />;
  if (id.includes("voice") || id.includes("xiaoai")) return <SpeakerIconMini />;
  if (id.includes("nsfw")) return <HeartIconMini />;
  if (id.includes("behavior") || id.includes("thinking") || id.includes("retreat")) return <GitMergeIcon />;
  return <FileTextIcon />;
}

function shortTime(value?: string) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.replace("T", " ").replace(/\.\d+/, "").replace(/\+08:00$/, "").slice(0, 16);
}

function sourceLabel(source: string) {
  if (source === "pending") return "";
  return source === "r2" ? "已自定义" : "默认";
}

function PromptSectionRow({ item, onClick }: { item: PromptSection; onClick: () => void }) {
  return (
    <button
      type="button"
      className="flex w-full items-center gap-3 border-b border-gray-50 px-4 py-4 text-left transition-colors active:bg-gray-50"
      onClick={onClick}
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gray-50 text-gray-400">{sectionIcon(item.id)}</span>
      <span className="min-w-0 flex-1">
        <span className="mb-1 flex items-center gap-2">
          <span className="truncate text-[15px] font-semibold tracking-wide text-gray-800">{item.label}</span>
          {sourceLabel(item.source) ? (
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${item.source === "r2" ? "bg-green-50 text-green-600" : "bg-gray-100 text-gray-400"}`}>
              {sourceLabel(item.source)}
            </span>
          ) : null}
        </span>
        <span className="line-clamp-2 text-[12px] leading-relaxed text-gray-400">{item.description}</span>
      </span>
      <span className="shrink-0 text-right text-[11px] text-gray-300">
        {item.source === "pending" ? "状态同步中" : item.content_length ? `${item.content_length.toLocaleString()} 字` : "默认内容"}
        <ChevronRightIcon />
      </span>
    </button>
  );
}

export function PromptManagerScreen({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [sections, setSections] = useState<PromptSection[]>(FALLBACK_PROMPT_SECTIONS);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<PromptSectionDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [silenceEnabled, setSilenceEnabled] = useState(false);
  const [silenceSaving, setSilenceSaving] = useState(false);
  const [millionEnabled, setMillionEnabled] = useState(false);
  const [millionSaving, setMillionSaving] = useState(false);

  const isDirty = !!detail && draft !== detail.content;
  const selectedTitle = detail?.label || "Prompt 管理";

  async function loadList() {
    setLoading(true);
    try {
      const [list, silence, million] = await Promise.all([
        apiJson<{ ok?: boolean; sections?: PromptSection[]; error?: string }>("/miniapp-api/prompt-manager"),
        apiJson<ModeResponse>("/miniapp-api/silence-mode"),
        apiJson<ModeResponse>("/miniapp-api/million-plan-mode"),
      ]);
      if (!list?.ok) throw new Error(list?.error || "加载失败");
      setSections(mergePromptSections(list.sections || []));
      if (silence?.ok) setSilenceEnabled(!!silence.enabled);
      if (million?.ok) setMillionEnabled(!!million.enabled);
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(id: string) {
    setLoading(true);
    try {
      const j = await apiJson<PromptSectionDetail & { ok?: boolean; error?: string }>(`/miniapp-api/prompt-manager/sections/${encodeURIComponent(id)}`);
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setDetail(j);
      setDraft(j.content || "");
      setSelectedId(id);
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveMode(kind: "silence" | "million", next: boolean) {
    const isSilence = kind === "silence";
    const prev = isSilence ? silenceEnabled : millionEnabled;
    const setEnabled = isSilence ? setSilenceEnabled : setMillionEnabled;
    const setBusy = isSilence ? setSilenceSaving : setMillionSaving;
    const path = isSilence ? "/miniapp-api/silence-mode" : "/miniapp-api/million-plan-mode";
    setEnabled(next);
    setBusy(true);
    try {
      const j = await apiJson<ModeResponse>(path, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      setEnabled(!!j.enabled);
      toast(isSilence ? (j.enabled ? "禁言模式已开启" : "禁言模式已关闭") : (j.enabled ? "百万计划游戏模式已开启" : "百万计划游戏模式已关闭"));
    } catch (e: any) {
      setEnabled(prev);
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setBusy(false);
    }
  }

  async function savePrompt() {
    if (!detail) return;
    const content = draft.trim();
    if (!content) {
      toast("内容不能为空");
      return;
    }
    if (detail.max_chars && content.length > detail.max_chars) {
      toast(`内容太长了，最多 ${detail.max_chars.toLocaleString()} 字`);
      return;
    }
    const ok = window.confirm("保存后会覆盖线上生效提示词，并自动备份当前版本。确认保存吗？");
    if (!ok) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string; section?: PromptSectionDetail; warning?: string }>(`/miniapp-api/prompt-manager/sections/${encodeURIComponent(detail.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: draft, base_revision: detail.revision }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      toast(j.warning || "已保存，下一条请求生效");
      await loadDetail(detail.id);
      await loadList();
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function rollback(backup: PromptBackup) {
    if (!detail) return;
    const ok = window.confirm(`回滚到 ${shortTime(backup.created_at) || "这个"} 版本吗？当前版本也会先自动备份。`);
    if (!ok) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string; warning?: string }>(`/miniapp-api/prompt-manager/sections/${encodeURIComponent(detail.id)}/rollback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backup_id: backup.backup_id }),
      });
      if (!j?.ok) throw new Error(j?.error || "回滚失败");
      toast(j.warning || "已回滚，下一条请求生效");
      await loadDetail(detail.id);
      await loadList();
    } catch (e: any) {
      toast(`回滚失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  function handleBack() {
    if (selectedId) {
      if (isDirty && !window.confirm("有未保存修改，确认返回列表吗？")) return;
      setSelectedId("");
      setDetail(null);
      setDraft("");
      return;
    }
    onClose();
  }

  const backups = useMemo(() => detail?.backups || [], [detail]);

  return (
    <FullScreenPane title={selectedId ? selectedTitle : "Prompt 管理"} accent="neutral" headerMode="simple" onBack={handleBack}>
      {!selectedId ? (
        <div className="px-1 pb-8 pt-4 text-gray-900">
          <div className="mb-5 overflow-hidden rounded-[28px] border border-gray-100/60 bg-white shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <SwitchSettingRow
              icon={<MuteIconMini />}
              label="禁言模式"
              enabled={silenceEnabled}
              disabled={silenceSaving}
              onToggle={(v) => void saveMode("silence", v)}
            />
            <SwitchSettingRow
              icon={<CodeIcon />}
              label="百万计划游戏模式"
              enabled={millionEnabled}
              disabled={millionSaving}
              onToggle={(v) => void saveMode("million", v)}
              last
            />
          </div>

          <div className="mb-2 px-2 text-[12px] font-bold tracking-[0.18em] text-gray-300">PROMPTS</div>
          <div className="overflow-hidden rounded-[28px] border border-gray-100/60 bg-white shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            {sections.map((item) => (
              <PromptSectionRow key={item.id} item={item} onClick={() => void loadDetail(item.id)} />
            ))}
            {!sections.length ? (
              <div className="px-5 py-10 text-center text-[13px] text-gray-400">{loading ? "加载中..." : "还没有可管理的提示词"}</div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="px-1 pb-36 pt-4 text-gray-900">
          <div className="mb-4 rounded-[28px] border border-gray-100/70 bg-white p-5 shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-[18px] font-bold text-gray-800">{detail?.label || "Prompt"}</div>
                <div className="mt-1 text-[12px] leading-relaxed text-gray-400">{detail?.description || ""}</div>
              </div>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${detail?.source === "r2" ? "bg-green-50 text-green-600" : "bg-gray-100 text-gray-400"}`}>
                {sourceLabel(detail?.source || "fallback")}
              </span>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-gray-400">
              <span className="rounded-full bg-gray-50 px-2.5 py-1">rev {detail?.revision || 0}</span>
              <span className="rounded-full bg-gray-50 px-2.5 py-1">{draft.length.toLocaleString()} 字</span>
              {detail?.updated_at ? <span className="rounded-full bg-gray-50 px-2.5 py-1">{shortTime(detail.updated_at)}</span> : null}
              {isDirty ? <span className="rounded-full bg-amber-50 px-2.5 py-1 font-bold text-amber-600">未保存</span> : null}
            </div>
          </div>

          <div className="mb-5 rounded-[28px] border border-gray-100/70 bg-white p-4 shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            <textarea
              className="h-[48vh] w-full resize-none rounded-[22px] bg-gray-50 px-4 py-4 text-[14px] leading-relaxed text-gray-700 outline-none"
              value={draft}
              disabled={loading || saving || !detail}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={loading ? "加载中..." : "编辑提示词..."}
            />
          </div>

          <div className="mb-2 px-2 text-[12px] font-bold tracking-[0.18em] text-gray-300">BACKUPS</div>
          <div className="overflow-hidden rounded-[28px] border border-gray-100/60 bg-white shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)]">
            {backups.map((item) => (
              <div key={item.backup_id} className="flex items-center gap-3 border-b border-gray-50 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-semibold text-gray-700">{shortTime(item.created_at) || item.backup_id}</div>
                  <div className="mt-1 text-[11px] text-gray-300">rev {item.revision || 0} · {(item.content_length || 0).toLocaleString()} 字</div>
                </div>
                <button
                  type="button"
                  className="rounded-full bg-gray-900 px-3 py-1.5 text-[12px] font-bold text-white active:scale-95 disabled:opacity-50"
                  disabled={saving}
                  onClick={() => void rollback(item)}
                >
                  回滚
                </button>
              </div>
            ))}
            {!backups.length ? <div className="px-5 py-8 text-center text-[13px] text-gray-400">暂无备份；第一次保存后会自动生成。</div> : null}
          </div>

          <div className="safe-bottom fixed bottom-0 left-0 right-0 z-[55] flex gap-4 border-t border-gray-50 bg-white/85 p-5 pb-[calc(env(safe-area-inset-bottom,0px)+20px)] backdrop-blur-lg">
            <button
              type="button"
              onClick={handleBack}
              disabled={saving}
              className="flex-1 rounded-[20px] py-4 text-[15px] font-bold text-gray-400 transition-all active:bg-gray-50"
            >
              返回列表
            </button>
            <button
              type="button"
              onClick={() => void savePrompt()}
              disabled={saving || loading || !isDirty}
              className="flex-1 rounded-[20px] bg-gray-800 py-4 text-[15px] font-bold text-white shadow-[0_10px_24px_rgba(15,23,42,0.18)] transition-all active:scale-95 disabled:bg-gray-300 disabled:shadow-none"
            >
              {saving ? "保存中..." : "保存修改"}
            </button>
          </div>
        </div>
      )}
    </FullScreenPane>
  );
}
