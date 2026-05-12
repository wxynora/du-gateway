import React, { useEffect, useState } from "react";
import { apiJson } from "./api";
import {
  DEFAULT_GROUP_CHAT_TITLE,
  GROUP_CHAT_TITLE_MAX_LENGTH,
  TRANSPARENT_BUBBLE_CLASS,
  getBubbleStyleLabel,
  resolveBubbleClass,
  resolveChatFontFamily,
  type BubbleStyleKey,
} from "./chatAppearance";
import { getChatFontLabel, type ChatFontKey, type ChatTimeFormat } from "./chatMessages";
import { ChevronRightIcon } from "./icons";
import { useToast } from "./toast";

type TtsEmotionKey = "" | "happy" | "sad" | "angry" | "fearful" | "disgusted" | "surprised" | "calm" | "fluent" | "whisper";

const TTS_EMOTION_OPTIONS: Array<{ value: TtsEmotionKey; label: string }> = [
  { value: "", label: "默认" },
  { value: "calm", label: "平静" },
  { value: "fluent", label: "流畅" },
  { value: "whisper", label: "低语" },
  { value: "happy", label: "轻快" },
  { value: "sad", label: "低落" },
  { value: "surprised", label: "惊讶" },
  { value: "fearful", label: "紧张" },
  { value: "angry", label: "生气" },
  { value: "disgusted", label: "嫌弃" },
];

function normalizeTtsEmotion(value: unknown): TtsEmotionKey {
  const raw = String(value || "").trim().toLowerCase();
  return TTS_EMOTION_OPTIONS.some((it) => it.value === raw) ? (raw as TtsEmotionKey) : "";
}

function PreviewAvatar({
  image,
  label,
  shellClass,
}: {
  image?: string;
  label: string;
  shellClass: string;
}) {
  if (image) {
    return (
      <div className="h-[44px] w-[44px] overflow-hidden rounded-full">
        <img src={image} alt={label} className="h-full w-full object-cover" />
      </div>
    );
  }
  return <div className={`flex h-[44px] w-[44px] items-center justify-center rounded-full text-[16px] font-semibold ${shellClass}`}>{label}</div>;
}

function PersonalizationRow({
  title,
  subtitle,
  value,
  leading,
  onClick,
  last = false,
}: {
  title: string;
  subtitle?: string;
  value?: string;
  leading?: React.ReactNode;
  onClick?: () => void;
  last?: boolean;
}) {
  return (
    <button
      type="button"
      className={`flex w-full items-center justify-between py-[14px] text-left ${last ? "" : "border-b border-[#F9FAFB]"}`}
      onClick={onClick}
      disabled={!onClick}
    >
      <div className="flex items-center gap-3">
        {leading}
        <div>
          <p className="text-[15px] font-semibold text-gray-800">{title}</p>
          {subtitle ? <p className="mt-0.5 text-[12px] text-gray-400">{subtitle}</p> : null}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {value ? <span className="text-[13px] font-medium text-gray-400">{value}</span> : null}
        <ChevronRightIcon />
      </div>
    </button>
  );
}

function PersonalizationTextInputRow({
  title,
  subtitle,
  value,
  placeholder,
  maxLength,
  onChange,
  last = false,
}: {
  title: string;
  subtitle?: string;
  value: string;
  placeholder?: string;
  maxLength?: number;
  onChange: (next: string) => void;
  last?: boolean;
}) {
  return (
    <label className={`block py-[14px] ${last ? "" : "border-b border-[#F9FAFB]"}`}>
      <div className="mb-3">
        <p className="text-[15px] font-semibold text-gray-800">{title}</p>
        {subtitle ? <p className="mt-0.5 text-[12px] text-gray-400">{subtitle}</p> : null}
      </div>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 w-full rounded-[16px] border border-gray-100 bg-[#F8FAFC] px-4 text-[15px] font-medium text-gray-800 outline-none transition-colors placeholder:text-gray-300 focus:border-gray-200 focus:bg-white"
      />
    </label>
  );
}

function PersonalizationSwitchRow({
  title,
  enabled = false,
  onToggle,
}: {
  title: string;
  enabled?: boolean;
  onToggle?: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between border-b border-[#F9FAFB] py-[14px] last:border-b-0">
      <span className="text-[15px] font-medium text-gray-800">{title}</span>
      <button
        className={`relative h-[24px] w-[42px] rounded-full transition-colors ${enabled ? "bg-[#1F2937]" : "bg-[#E2E8F0]"}`}
        onClick={() => onToggle?.(!enabled)}
        type="button"
      >
        <div className={`absolute bottom-[3px] h-[18px] w-[18px] rounded-full bg-white transition-transform ${enabled ? "left-[21px]" : "left-[3px]"}`} />
      </button>
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

function PersonalizationSelectRow({
  title,
  subtitle,
  value,
  options,
  onChange,
  disabled = false,
  last = false,
}: {
  title: string;
  subtitle?: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (next: string) => void;
  disabled?: boolean;
  last?: boolean;
}) {
  return (
    <label className={`flex items-center justify-between gap-4 py-[14px] ${last ? "" : "border-b border-[#F9FAFB]"}`}>
      <div>
        <p className="text-[15px] font-semibold text-gray-800">{title}</p>
        {subtitle ? <p className="mt-0.5 text-[12px] text-gray-400">{subtitle}</p> : null}
      </div>
      <select
        className="h-10 min-w-[112px] rounded-[14px] border border-gray-100 bg-[#F8FAFC] px-3 text-[14px] font-semibold text-gray-700 outline-none disabled:opacity-60"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((item) => (
          <option key={item.value || "default"} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function PersonalizationScreen({
  transparentBubbleEnabled,
  onToggleTransparentBubble,
  showChatAvatars,
  onToggleShowChatAvatars,
  chatContentFontSize,
  onChangeChatContentFontSize,
  chatTitleFontSize,
  onChangeChatTitleFontSize,
  chatFontKey,
  onCycleChatFont,
  showChatTimestamps,
  onToggleShowChatTimestamps,
  chatTimeFormat,
  onCycleChatTimeFormat,
  showTokenCount,
  onToggleShowTokenCount,
  expandReasoningByDefault,
  onToggleExpandReasoningByDefault,
  chatBackgroundOpacity,
  onChangeChatBackgroundOpacity,
  userBubbleStyle,
  onCycleUserBubbleStyle,
  assistantBubbleStyle,
  onCycleAssistantBubbleStyle,
  myAvatarImage,
  duAvatarImage,
  benbenAvatarImage,
  groupChatTitle,
  chatBackgroundImage,
  onPickMyAvatar,
  onPickDuAvatar,
  onPickBenbenAvatar,
  onChangeGroupChatTitle,
  onPickChatBackground,
}: {
  transparentBubbleEnabled: boolean;
  onToggleTransparentBubble: (next: boolean) => void;
  showChatAvatars: boolean;
  onToggleShowChatAvatars: (next: boolean) => void;
  chatContentFontSize: number;
  onChangeChatContentFontSize: (next: number) => void;
  chatTitleFontSize: number;
  onChangeChatTitleFontSize: (next: number) => void;
  chatFontKey: ChatFontKey;
  onCycleChatFont: () => void;
  showChatTimestamps: boolean;
  onToggleShowChatTimestamps: (next: boolean) => void;
  chatTimeFormat: ChatTimeFormat;
  onCycleChatTimeFormat: () => void;
  showTokenCount: boolean;
  onToggleShowTokenCount: (next: boolean) => void;
  expandReasoningByDefault: boolean;
  onToggleExpandReasoningByDefault: (next: boolean) => void;
  chatBackgroundOpacity: number;
  onChangeChatBackgroundOpacity: (next: number) => void;
  userBubbleStyle: BubbleStyleKey;
  onCycleUserBubbleStyle: () => void;
  assistantBubbleStyle: BubbleStyleKey;
  onCycleAssistantBubbleStyle: () => void;
  myAvatarImage: string;
  duAvatarImage: string;
  benbenAvatarImage: string;
  groupChatTitle: string;
  chatBackgroundImage: string;
  onPickMyAvatar: () => void;
  onPickDuAvatar: () => void;
  onPickBenbenAvatar: () => void;
  onChangeGroupChatTitle: (next: string) => void;
  onPickChatBackground: () => void;
}) {
  const toast = useToast();
  const [ttsEmotion, setTtsEmotion] = useState<TtsEmotionKey>("");
  const [savingTtsEmotion, setSavingTtsEmotion] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiJson<{ ok?: boolean; config?: { ttsEmotion?: string } }>("/miniapp-api/voice-config")
      .then((data) => {
        if (cancelled || !data?.ok) return;
        setTtsEmotion(normalizeTtsEmotion(data.config?.ttsEmotion));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function changeTtsEmotion(nextValue: string) {
    const next = normalizeTtsEmotion(nextValue);
    const previous = ttsEmotion;
    setTtsEmotion(next);
    setSavingTtsEmotion(true);
    try {
      const data = await apiJson<{ ok?: boolean; config?: { ttsEmotion?: string }; error?: string }>("/miniapp-api/voice-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ttsEmotion: next }),
      });
      if (!data?.ok) throw new Error(data?.error || "保存失败");
      setTtsEmotion(normalizeTtsEmotion(data.config?.ttsEmotion));
      toast(next ? "语音情绪已切换" : "语音情绪已改为默认");
    } catch (e: any) {
      setTtsEmotion(previous);
      toast(e?.message || "保存失败");
    } finally {
      setSavingTtsEmotion(false);
    }
  }

  return (
    <div className="bg-[#FDFDFD] px-1 pb-6 pt-4">
      <div className="space-y-6">
        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">群聊设置</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <PersonalizationTextInputRow
              title="群聊名"
              subtitle="会显示在会话列表和群聊顶部"
              value={groupChatTitle}
              placeholder={DEFAULT_GROUP_CHAT_TITLE}
              maxLength={GROUP_CHAT_TITLE_MAX_LENGTH}
              onChange={onChangeGroupChatTitle}
              last
            />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">头像设置</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <PersonalizationRow
              title="我的头像"
              subtitle="自定义我的头像"
              leading={<PreviewAvatar image={myAvatarImage} label="我" shellClass="bg-[#E5E7EB] text-gray-700" />}
              onClick={onPickMyAvatar}
            />
            <PersonalizationRow
              title="渡的头像"
              subtitle="自定义助手的头像"
              leading={<PreviewAvatar image={duAvatarImage} label="渡" shellClass="bg-[#EEF2FF] text-gray-700" />}
              onClick={onPickDuAvatar}
            />
            <PersonalizationRow
              title="笨笨头像"
              subtitle="群聊里笨笨的头像"
              leading={<PreviewAvatar image={benbenAvatarImage} label="笨" shellClass="bg-[#FFF3D7] text-[#8A5A10]" />}
              onClick={onPickBenbenAvatar}
              last
            />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">语音设置</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <PersonalizationSelectRow
              title="MiniMax 情绪"
              subtitle="默认是不传 emotion；保存后下一条语音生效"
              value={ttsEmotion}
              options={TTS_EMOTION_OPTIONS}
              onChange={changeTtsEmotion}
              disabled={savingTtsEmotion}
              last
            />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">聊天背景</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <div className="mb-5 rounded-[20px] bg-[#F8FAFC] p-4">
              <p className="mb-3 text-[12px] font-medium text-gray-400">当前背景预览</p>
              <div
                className="h-[92px] rounded-[18px] bg-[linear-gradient(180deg,#F8FAFC_0%,#EEF2F7_100%)]"
                style={{
                  opacity: Math.max(0.2, Math.min(1, chatBackgroundOpacity / 100)),
                  backgroundImage: chatBackgroundImage ? `url(${chatBackgroundImage})` : "linear-gradient(180deg,#F8FAFC_0%,#EEF2F7_100%)",
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                }}
              />
            </div>
            <PersonalizationRow title="背景图设置" onClick={onPickChatBackground} />
            <PersonalizationSliderRow title="背景透明度" value={`${chatBackgroundOpacity}%`} min={20} max={100} step={1} currentValue={chatBackgroundOpacity} onChange={onChangeChatBackgroundOpacity} />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">气泡样式</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <div className="mb-5 rounded-[20px] bg-[#F8FAFC] p-4">
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  {showChatAvatars ? <div className="flex h-[32px] w-[32px] items-center justify-center rounded-full bg-[#EEF2FF] text-[13px] font-medium text-gray-700">渡</div> : null}
                  <div className={`inline-block w-fit rounded-[16px] px-3 py-2 font-medium leading-normal ${transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("assistant", assistantBubbleStyle)}`} style={{ fontSize: `${chatContentFontSize}px`, fontFamily: resolveChatFontFamily(chatFontKey) }}>
                    这里是助手气泡预览
                  </div>
                </div>
                <div className="flex justify-end gap-3">
                  <div className={`inline-block w-fit rounded-[16px] px-3 py-2 font-medium leading-normal ${transparentBubbleEnabled ? TRANSPARENT_BUBBLE_CLASS : resolveBubbleClass("user", userBubbleStyle)}`} style={{ fontSize: `${chatContentFontSize}px`, fontFamily: resolveChatFontFamily(chatFontKey) }}>
                    这里是用户气泡预览
                  </div>
                  {showChatAvatars ? <div className="flex h-[32px] w-[32px] items-center justify-center rounded-full bg-[#E5E7EB] text-[13px] font-medium text-gray-700">我</div> : null}
                </div>
              </div>
            </div>
            <PersonalizationSliderRow title="气泡圆角" value="18px" min={18} max={18} step={1} currentValue={18} disabled />
            <PersonalizationRow title="用户气泡样式" value={getBubbleStyleLabel(userBubbleStyle, "user")} onClick={onCycleUserBubbleStyle} />
            <PersonalizationRow title="助手气泡样式" value={getBubbleStyleLabel(assistantBubbleStyle, "assistant")} onClick={onCycleAssistantBubbleStyle} />
            <PersonalizationSwitchRow title="显示头像" enabled={showChatAvatars} onToggle={onToggleShowChatAvatars} />
            <PersonalizationSwitchRow
              title="启用（透明模式）"
              enabled={transparentBubbleEnabled}
              onToggle={onToggleTransparentBubble}
            />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">字体与字号</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <div className="mb-5 rounded-[20px] bg-[#F8FAFC] p-4">
              <p className="font-medium text-gray-800" style={{ fontSize: `${chatContentFontSize}px`, fontFamily: resolveChatFontFamily(chatFontKey) }}>这里是聊天文字的预览效果</p>
            </div>
            <PersonalizationSliderRow title="聊天内容字号" value={`${chatContentFontSize}px`} min={12} max={18} step={1} currentValue={chatContentFontSize} onChange={onChangeChatContentFontSize} />
            <PersonalizationSliderRow title="界面标题字号" value={`${chatTitleFontSize}px`} min={14} max={20} step={1} currentValue={chatTitleFontSize} onChange={onChangeChatTitleFontSize} />
            <PersonalizationRow title="聊天字体" value={getChatFontLabel(chatFontKey)} onClick={onCycleChatFont} last />
          </div>
        </section>

        <section>
          <h2 className="mb-3 ml-5 text-[11px] font-extrabold uppercase tracking-[0.15em] text-[#94A3B8]">信息显示</h2>
          <div className="rounded-[32px] border border-gray-100/80 bg-white px-6 py-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.03)]">
            <PersonalizationSwitchRow title="显示时间戳" enabled={showChatTimestamps} onToggle={onToggleShowChatTimestamps} />
            <PersonalizationRow title="时间格式" value={chatTimeFormat === "hhmm" ? "HH:MM" : "上午/下午 HH:MM"} onClick={onCycleChatTimeFormat} />
            <PersonalizationSwitchRow title="显示 token" enabled={showTokenCount} onToggle={onToggleShowTokenCount} />
            <PersonalizationSwitchRow title="默认展开思维链" enabled={expandReasoningByDefault} onToggle={onToggleExpandReasoningByDefault} />
          </div>
        </section>
      </div>
    </div>
  );
}
