import React, { useState } from "react";

import { Modal } from "./components";
import { useToast } from "./toast";

const SYSTEM_CARD_PREFIX = "<<<SUMITALK_CARD ";
const SYSTEM_CARD_SUFFIX = ">>>";

export type SystemAlarmCreatedCard = {
  type: "system_alarm_created";
  hour: number;
  minute: number;
  title: string;
};
export type CalendarEventCreatedCard = {
  type: "calendar_event_created";
  title: string;
  startAt: string;
  endAt?: string;
  startMillis?: number;
  endMillis?: number;
  allDay?: boolean;
  location?: string;
  reminderMinutes?: number;
  eventId?: number | string;
};
export type TravelPlanPreference = "auto" | "transit" | "taxi";
export type TravelPlanWalkPreference = "low" | "medium" | "high";
export type TravelPlanFormCard = {
  type: "travel_plan_form";
  title: string;
  prompt?: string;
  city?: string;
  destinations?: string[];
  food?: string;
  prefer?: TravelPlanPreference;
  walk?: TravelPlanWalkPreference;
};
export type TravelPlanRouteSummary = {
  ok?: boolean;
  duration?: string;
  distance?: string;
  walking?: string;
  costYuan?: number;
  taxiCostYuan?: number;
  steps?: string[];
  error?: string;
};
export type TravelPlanResultLeg = {
  from: string;
  to: string;
  mode?: string;
  reason?: string;
  transit?: TravelPlanRouteSummary;
  driving?: TravelPlanRouteSummary;
  links?: {
    navi?: string;
    taxi?: string;
  };
  summary?: string[];
};
export type TravelPlanResultCard = {
  type: "travel_plan_result";
  title: string;
  origin?: string;
  destinations?: string[];
  optimized?: boolean;
  legs?: TravelPlanResultLeg[];
  personalMapUrl?: string;
  note?: string;
};
export type TravelTransportDetailCard = {
  type: "travel_transport_detail";
  title: string;
  planId?: string;
  legId?: string;
  from: string;
  to: string;
  mode?: string;
  reason?: string;
  transit?: TravelPlanRouteSummary;
  driving?: TravelPlanRouteSummary;
  cacheHit?: boolean;
  note?: string;
};
export type TravelFoodItem = {
  name: string;
  type?: string;
  address?: string;
  distanceMeters?: number;
  rating?: string;
  cost?: string;
};
export type TravelFoodDetailCard = {
  type: "travel_food_detail";
  title: string;
  planId?: string;
  placeId?: string;
  placeName?: string;
  keywords?: string;
  items?: TravelFoodItem[];
  cacheHit?: boolean;
  note?: string;
};
export type SumiTalkSystemCard =
  | SystemAlarmCreatedCard
  | CalendarEventCreatedCard
  | TravelPlanFormCard
  | TravelPlanResultCard
  | TravelTransportDetailCard
  | TravelFoodDetailCard;

export function formatAlarmTime(hour: number, minute: number): string {
  const h = Number.isFinite(hour) ? Math.max(0, Math.min(23, Math.floor(hour))) : 0;
  const m = Number.isFinite(minute) ? Math.max(0, Math.min(59, Math.floor(minute))) : 0;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function buildSystemAlarmCreatedCardContent(input: { hour?: number; minute?: number; title?: string }): string {
  const payload: SystemAlarmCreatedCard = {
    type: "system_alarm_created",
    hour: Math.max(0, Math.min(23, Math.floor(Number(input.hour ?? 0) || 0))),
    minute: Math.max(0, Math.min(59, Math.floor(Number(input.minute ?? 0) || 0))),
    title: String(input.title || "渡的提醒").trim() || "渡的提醒",
  };
  return `${SYSTEM_CARD_PREFIX}${JSON.stringify(payload)}${SYSTEM_CARD_SUFFIX}`;
}

export function parseSystemAlarmCreatedCard(content: string): SystemAlarmCreatedCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "system_alarm_created") return null;
    const hour = Number(parsed.hour);
    const minute = Number(parsed.minute);
    if (!Number.isFinite(hour) || hour < 0 || hour > 23) return null;
    if (!Number.isFinite(minute) || minute < 0 || minute > 59) return null;
    return {
      type: "system_alarm_created",
      hour: Math.floor(hour),
      minute: Math.floor(minute),
      title: String(parsed.title || "渡的提醒").trim() || "渡的提醒",
    };
  } catch {
    return null;
  }
}

export function parseCalendarEventCreatedCard(content: string): CalendarEventCreatedCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "calendar_event_created") return null;
    const title = String(parsed.title || "渡的行程").trim() || "渡的行程";
    const startAt = String(parsed.startAt || parsed.start_at || "").trim();
    const startMillis = Number(parsed.startMillis || 0);
    if (!startAt && (!Number.isFinite(startMillis) || startMillis <= 0)) return null;
    const card: CalendarEventCreatedCard = {
      type: "calendar_event_created",
      title,
      startAt,
      endAt: String(parsed.endAt || parsed.end_at || "").trim() || undefined,
      startMillis: Number.isFinite(startMillis) && startMillis > 0 ? Math.floor(startMillis) : undefined,
      allDay: Boolean(parsed.allDay || parsed.all_day),
    };
    const endMillis = Number(parsed.endMillis || 0);
    if (Number.isFinite(endMillis) && endMillis > 0) card.endMillis = Math.floor(endMillis);
    const location = String(parsed.location || "").trim();
    if (location) card.location = location;
    const reminder = Number(parsed.reminderMinutes ?? parsed.reminder_minutes);
    if (Number.isFinite(reminder)) card.reminderMinutes = Math.floor(reminder);
    const eventId = String(parsed.eventId || "").trim();
    if (eventId) card.eventId = eventId;
    return card;
  } catch {
    return null;
  }
}

export function normalizeTravelPrefer(value: unknown): TravelPlanPreference {
  const raw = String(value || "").trim();
  if (raw === "transit" || raw === "taxi") return raw;
  return "auto";
}

export function normalizeTravelWalk(value: unknown): TravelPlanWalkPreference {
  const raw = String(value || "").trim();
  if (raw === "low" || raw === "high") return raw;
  return "medium";
}

export function parseTravelPlanFormCard(content: string): TravelPlanFormCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "travel_plan_form") return null;
    const destinations = Array.isArray(parsed.destinations)
      ? parsed.destinations.map((item: unknown) => String(item || "").trim()).filter(Boolean).slice(0, 6)
      : [];
    return {
      type: "travel_plan_form",
      title: String(parsed.title || "出行规划").trim() || "出行规划",
      prompt: String(parsed.prompt || "").trim() || undefined,
      city: String(parsed.city || "").trim() || undefined,
      destinations,
      food: String(parsed.food || "").trim() || undefined,
      prefer: normalizeTravelPrefer(parsed.prefer),
      walk: normalizeTravelWalk(parsed.walk),
    };
  } catch {
    return null;
  }
}

export function parseStringList(value: unknown, limit = 8): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || "").trim()).filter(Boolean).slice(0, limit);
}

export function parseTravelRouteSummary(value: unknown): TravelPlanRouteSummary {
  if (!value || typeof value !== "object") return {};
  const raw = value as Record<string, unknown>;
  const costYuan = Number(raw.costYuan ?? raw.cost_yuan);
  const taxiCostYuan = Number(raw.taxiCostYuan ?? raw.taxi_cost_yuan);
  const out: TravelPlanRouteSummary = {
    ok: Boolean(raw.ok),
    duration: String(raw.duration || "").trim() || undefined,
    distance: String(raw.distance || "").trim() || undefined,
    walking: String(raw.walking || raw.walking_distance || "").trim() || undefined,
    steps: parseStringList(raw.steps, 6),
    error: String(raw.error || "").trim() || undefined,
  };
  if (Number.isFinite(costYuan) && costYuan > 0) out.costYuan = costYuan;
  if (Number.isFinite(taxiCostYuan) && taxiCostYuan > 0) out.taxiCostYuan = taxiCostYuan;
  return out;
}

export function parseTravelPlanResultCard(content: string): TravelPlanResultCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "travel_plan_result") return null;
    const legs = Array.isArray(parsed.legs)
      ? parsed.legs.map((item: unknown) => {
        const leg = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
        const links = (leg.links && typeof leg.links === "object" ? leg.links : {}) as Record<string, unknown>;
        return {
          from: String(leg.from || "起点").trim() || "起点",
          to: String(leg.to || "终点").trim() || "终点",
          mode: String(leg.mode || "").trim() || undefined,
          reason: String(leg.reason || "").trim() || undefined,
          transit: parseTravelRouteSummary(leg.transit),
          driving: parseTravelRouteSummary(leg.driving),
          links: {
            navi: String(links.navi || "").trim() || undefined,
            taxi: String(links.taxi || "").trim() || undefined,
          },
          summary: parseStringList(leg.summary, 5),
        };
      }).slice(0, 6)
      : [];
    return {
      type: "travel_plan_result",
      title: String(parsed.title || "渡安排好了").trim() || "渡安排好了",
      origin: String(parsed.origin || "").trim() || undefined,
      destinations: parseStringList(parsed.destinations, 8),
      optimized: Boolean(parsed.optimized),
      legs,
      personalMapUrl: String(parsed.personalMapUrl || parsed.personal_map_url || "").trim() || undefined,
      note: String(parsed.note || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

export function parseTravelTransportDetailCard(content: string): TravelTransportDetailCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "travel_transport_detail") return null;
    return {
      type: "travel_transport_detail",
      title: String(parsed.title || "这段怎么走").trim() || "这段怎么走",
      planId: String(parsed.planId || parsed.plan_id || "").trim() || undefined,
      legId: String(parsed.legId || parsed.leg_id || "").trim() || undefined,
      from: String(parsed.from || "起点").trim() || "起点",
      to: String(parsed.to || "终点").trim() || "终点",
      mode: String(parsed.mode || "").trim() || undefined,
      reason: String(parsed.reason || "").trim() || undefined,
      transit: parseTravelRouteSummary(parsed.transit),
      driving: parseTravelRouteSummary(parsed.driving),
      cacheHit: Boolean(parsed.cacheHit ?? parsed.cache_hit),
      note: String(parsed.note || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

export function parseTravelFoodDetailCard(content: string): TravelFoodDetailCard | null {
  const raw = String(content || "").trim();
  if (!raw.startsWith(SYSTEM_CARD_PREFIX) || !raw.endsWith(SYSTEM_CARD_SUFFIX)) return null;
  const jsonText = raw.slice(SYSTEM_CARD_PREFIX.length, raw.length - SYSTEM_CARD_SUFFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonText);
    if (!parsed || parsed.type !== "travel_food_detail") return null;
    const items = Array.isArray(parsed.items)
      ? parsed.items.map((item: unknown) => {
        const rawItem = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
        const distanceMeters = Number(rawItem.distanceMeters ?? rawItem.distance_meters);
        const out: TravelFoodItem = {
          name: String(rawItem.name || "").trim(),
          type: String(rawItem.type || "").trim() || undefined,
          address: String(rawItem.address || "").trim() || undefined,
          rating: String(rawItem.rating || "").trim() || undefined,
          cost: String(rawItem.cost || "").trim() || undefined,
        };
        if (Number.isFinite(distanceMeters) && distanceMeters > 0) out.distanceMeters = distanceMeters;
        return out;
      }).filter((item: TravelFoodItem) => item.name).slice(0, 8)
      : [];
    return {
      type: "travel_food_detail",
      title: String(parsed.title || "附近吃这些").trim() || "附近吃这些",
      planId: String(parsed.planId || parsed.plan_id || "").trim() || undefined,
      placeId: String(parsed.placeId || parsed.place_id || "").trim() || undefined,
      placeName: String(parsed.placeName || parsed.place_name || "").trim() || undefined,
      keywords: String(parsed.keywords || "").trim() || undefined,
      items,
      cacheHit: Boolean(parsed.cacheHit ?? parsed.cache_hit),
      note: String(parsed.note || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

export function parseSumiTalkSystemCard(content: string): SumiTalkSystemCard | null {
  return (
    parseSystemAlarmCreatedCard(content)
    || parseCalendarEventCreatedCard(content)
    || parseTravelPlanFormCard(content)
    || parseTravelPlanResultCard(content)
    || parseTravelTransportDetailCard(content)
    || parseTravelFoodDetailCard(content)
  );
}

export function splitSystemCardSegments(content: string): Array<{ content: string; systemCard: SumiTalkSystemCard | null }> {
  const raw = String(content || "");
  const out: Array<{ content: string; systemCard: SumiTalkSystemCard | null }> = [];
  let cursor = 0;
  while (cursor < raw.length) {
    const start = raw.indexOf(SYSTEM_CARD_PREFIX, cursor);
    if (start < 0) {
      const rest = raw.slice(cursor).trim();
      if (rest) out.push({ content: rest, systemCard: null });
      break;
    }
    const before = raw.slice(cursor, start).trim();
    if (before) out.push({ content: before, systemCard: null });
    const end = raw.indexOf(SYSTEM_CARD_SUFFIX, start + SYSTEM_CARD_PREFIX.length);
    if (end < 0) {
      const rest = raw.slice(start).trim();
      if (rest) out.push({ content: rest, systemCard: null });
      break;
    }
    const marker = raw.slice(start, end + SYSTEM_CARD_SUFFIX.length).trim();
    const systemCard = parseSumiTalkSystemCard(marker);
    if (systemCard) {
      out.push({ content: marker, systemCard });
    } else {
      out.push({ content: marker, systemCard: null });
    }
    cursor = end + SYSTEM_CARD_SUFFIX.length;
  }
  return out;
}

export function firstSystemCard(content: string): SumiTalkSystemCard | null {
  for (const segment of splitSystemCardSegments(content)) {
    if (segment.systemCard) return segment.systemCard;
  }
  return null;
}

export function SystemAlarmCreatedBubble({ card, onOpen }: { card: SystemAlarmCreatedCard; onOpen: () => void }) {
  return (
    <button
      className="block w-full max-w-[260px] rounded-[20px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-semibold text-amber-800">系统闹钟</span>
        <span className="text-[11px] font-medium text-amber-700">点击查看</span>
      </div>
      <div className="text-[30px] font-bold leading-none text-gray-900">{formatAlarmTime(card.hour, card.minute)}</div>
      <div className="mt-2 text-[13px] font-medium leading-5 text-gray-700">{card.title}</div>
    </button>
  );
}

export function formatCalendarCardTime(value?: string, millis?: number, allDay?: boolean): string {
  const ts = Number.isFinite(Number(millis || 0)) && Number(millis || 0) > 0
    ? Number(millis)
    : Date.parse(String(value || ""));
  if (!Number.isFinite(ts)) return allDay ? "全天" : "时间待确认";
  const date = new Date(ts);
  if (allDay) {
    return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", weekday: "short" }).format(date);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function CalendarEventCreatedBubble({ card, onOpen }: { card: CalendarEventCreatedCard; onOpen: () => void }) {
  const start = formatCalendarCardTime(card.startAt, card.startMillis, card.allDay);
  const end = card.endAt || card.endMillis ? formatCalendarCardTime(card.endAt, card.endMillis, card.allDay) : "";
  return (
    <button
      className="block w-full max-w-[290px] rounded-[22px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-semibold text-emerald-800">系统行程</span>
        <span className="text-[11px] font-medium text-emerald-700">点击查看</span>
      </div>
      <div className="text-[15px] font-bold leading-5 text-gray-900">{card.title}</div>
      <div className="mt-2 text-[13px] font-medium leading-5 text-gray-700">{end ? `${start} - ${end}` : start}</div>
      {card.location ? <div className="mt-1 text-[12px] leading-5 text-gray-500">{card.location}</div> : null}
      {typeof card.reminderMinutes === "number" && card.reminderMinutes >= 0 ? (
        <div className="mt-2 text-[11px] font-medium text-emerald-700">提前 {card.reminderMinutes} 分钟提醒</div>
      ) : null}
    </button>
  );
}

export function TravelPlanFormBubble({ card, onOpen }: { card: TravelPlanFormCard; onOpen: () => void }) {
  const placeText = card.destinations?.length ? card.destinations.join("、") : "填写想去的地方";
  return (
    <button
      className="block w-full max-w-[300px] rounded-[22px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-semibold text-sky-800">{card.title || "出行规划"}</span>
        <span className="text-[11px] font-medium text-sky-700">点击填写</span>
      </div>
      <div className="text-[15px] font-bold leading-5 text-gray-900">{placeText}</div>
      <div className="mt-2 text-[12px] leading-5 text-gray-500">
        {card.prompt || "填完后渡会综合位置、交通、吃饭和步行接受度来规划。"}
      </div>
    </button>
  );
}

export function splitTravelFormText(value: string): string[] {
  return String(value || "")
    .split(/[\n,，、;；]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 8);
}

export function travelPreferLabel(value: TravelPlanPreference): string {
  if (value === "transit") return "地铁公交优先";
  if (value === "taxi") return "打车优先";
  return "自动比较";
}

export function travelWalkLabel(value: TravelPlanWalkPreference): string {
  if (value === "low") return "少走路";
  if (value === "high") return "可以多走";
  return "可以走一点";
}

export function TravelPlanFormModal({
  card,
  sending,
  onClose,
  onSubmit,
}: {
  card: TravelPlanFormCard;
  sending: boolean;
  onClose: () => void;
  onSubmit: (content: string) => void;
}) {
  const toast = useToast();
  const [useCurrentLocation, setUseCurrentLocation] = useState(true);
  const [origin, setOrigin] = useState("");
  const [city, setCity] = useState(card.city || "");
  const [destinations, setDestinations] = useState((card.destinations || []).join("\n"));
  const [walk, setWalk] = useState<TravelPlanWalkPreference>(card.walk || "medium");
  const [prefer, setPrefer] = useState<TravelPlanPreference>(card.prefer || "auto");
  const [note, setNote] = useState(card.food ? `想吃：${card.food}` : "");

  const inputClass = "w-full rounded-xl border border-[#FFECDA] bg-white px-4 py-3 text-[14px] font-medium leading-5 text-[#5C4D3E] outline-none placeholder:text-[#B8A998] focus:border-[#FF8C42] focus:shadow-[0_0_0_2px_rgba(255,140,66,0.10)]";
  const pillClass = (active: boolean, extra = "") =>
    `${extra} rounded-full border px-4 py-2 text-[14px] font-medium leading-5 transition-colors active:scale-[0.98] ${
      active ? "border-[#FF8C42] bg-[#FF8C42] text-white" : "border-[#FFECDA] bg-white text-[#8D7B68]"
    }`;
  const sectionTitleClass = "mb-3 flex items-center gap-1.5 text-[15px] font-bold text-[#5C4D3E]";
  const renderSection = (icon: string, title: string, children: React.ReactNode) => (
    <div className="mb-8">
      <div className={sectionTitleClass}>
        <span className="text-[16px] leading-none" aria-hidden="true">
          {icon}
        </span>
        {title}
      </div>
      {children}
    </div>
  );

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const places = splitTravelFormText(destinations);
    if (!places.length) {
      toast("先填想去的地方");
      return;
    }
    if (!useCurrentLocation && !origin.trim()) {
      toast("填一下出发地，或者选用最近定位");
      return;
    }
    const lines = [
      "帮我做一个轻量出行规划，信息如下：",
      `出发地：${useCurrentLocation ? "用我最近定位/当前位置" : origin.trim()}`,
      city.trim() ? `城市：${city.trim()}` : "",
      `想去的地方：${places.join("、")}`,
      `步行接受度：${travelWalkLabel(walk)}`,
      `交通偏好：${travelPreferLabel(prefer)}`,
      note.trim() ? `补充：${note.trim()}` : "",
      "请只做第一轮轻量总规划：综合位置距离安排游玩顺序，每段只给推荐交通方式、大致耗时/步行/打车参考即可，不用逐站逐步写得很细；吃饭只简单提醒，不要展开查店。",
    ].filter(Boolean);
    onSubmit(lines.join("\n"));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/20" role="dialog" aria-modal="true">
      <button type="button" className="absolute inset-0 h-full w-full cursor-default" aria-label="关闭出行规划表单" onClick={onClose} />
      <form
        className="relative z-10 flex h-[92vh] max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-t-[32px] bg-[#FFF9F2] shadow-[0_-10px_25px_rgba(0,0,0,0.10)]"
        onSubmit={handleSubmit}
      >
        <div className="flex justify-center py-3">
          <div className="h-1.5 w-10 rounded-full bg-[#E5D5C5]" />
        </div>

        <div className="flex items-start justify-between px-6 pb-4">
          <div>
            <h1 className="text-2xl font-bold text-[#5C4D3E]">想去哪玩？</h1>
            <p className="mt-1 text-sm text-[#A89A8B]">先填最关键的，细节后面再聊</p>
          </div>
          <button
            type="button"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#F3E9DD] text-lg font-semibold leading-none text-[#8D7B68] active:scale-[0.96]"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 pb-36 [scrollbar-color:#E5D5C5_transparent]">
          {renderSection(
            "📍",
            "出发地",
            <>
              <div className="mb-3 flex gap-3">
                <button type="button" className={pillClass(useCurrentLocation)} onClick={() => setUseCurrentLocation(true)}>
                  用当前位置
                </button>
                <button type="button" className={pillClass(!useCurrentLocation)} onClick={() => setUseCurrentLocation(false)}>
                  手动填写
                </button>
              </div>
              {!useCurrentLocation ? (
                <input className={inputClass} value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="酒店 / 车站 / 地址" />
              ) : null}
            </>,
          )}

          {renderSection(
            "🏙️",
            "城市",
            <input className={inputClass} value={city} onChange={(e) => setCity(e.target.value)} placeholder="比如 上海" />,
          )}

          {renderSection(
            "⭐",
            "想去的地方",
            <textarea
              className={`${inputClass} h-24 resize-none`}
              value={destinations}
              onChange={(e) => setDestinations(e.target.value)}
              placeholder="一行一个地点，比如：上海迪士尼、武康路、咖啡店"
            />,
          )}

          {renderSection(
            "👟",
            "步行接受度",
            <div className="flex gap-2">
              {(["low", "medium", "high"] as TravelPlanWalkPreference[]).map((item) => (
                <button key={item} type="button" className={pillClass(walk === item, "flex-1 px-2")} onClick={() => setWalk(item)}>
                  {travelWalkLabel(item)}
                </button>
              ))}
            </div>,
          )}

          {renderSection(
            "🚇",
            "交通偏好",
            <div className="flex gap-2">
              {(["auto", "transit", "taxi"] as TravelPlanPreference[]).map((item) => (
                <button key={item} type="button" className={pillClass(prefer === item, "flex-1 px-2")} onClick={() => setPrefer(item)}>
                  {travelPreferLabel(item)}
                </button>
              ))}
            </div>,
          )}

          {renderSection(
            "📝",
            "补充",
            <textarea
              className={`${inputClass} h-24 resize-none`}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="比如 想吃甜品 / 不想太赶 / 预算控制一下"
            />,
          )}
        </div>

        <div className="absolute bottom-0 left-0 right-0 flex flex-col gap-3 border-t border-[#FFECDA] bg-[#FFF9F2] p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
          <p className="text-center text-xs text-[#A89A8B]">提交后只显示：已提交，渡在安排</p>
          <button
            type="submit"
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#FF8C42] py-4 text-lg font-bold text-white shadow-lg shadow-orange-200 transition-all active:scale-[0.98] disabled:opacity-50"
            disabled={sending}
          >
            ✨ 让渡安排
          </button>
        </div>
      </form>
    </div>
  );
}

export function travelModeLabel(value?: string): string {
  const raw = String(value || "").trim();
  if (raw === "taxi") return "打车";
  if (raw === "transit") return "地铁公交";
  if (raw === "walking") return "步行";
  return raw || "建议";
}

export function formatYuan(value?: number): string {
  if (!Number.isFinite(Number(value || 0)) || Number(value || 0) <= 0) return "";
  return `${Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 1)}元`;
}

export function TravelPlanResultBubble({ card, onOpen }: { card: TravelPlanResultCard; onOpen: () => void }) {
  const legs = card.legs || [];
  const order = card.destinations?.length ? card.destinations : legs.map((leg) => leg.to).filter(Boolean);
  return (
    <button
      className="relative block w-full max-w-[345px] text-left transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="absolute -left-[8px] top-5 h-0 w-0 border-y-[8px] border-r-[12px] border-y-transparent border-r-[#FFF9F2]" />
      <div className="flex flex-col gap-4 overflow-hidden rounded-[28px] border border-[#FFEEDB] bg-[#FFF9F2] p-5 shadow-[0_10px_25px_-5px_rgba(255,180,100,0.10),0_8px_10px_-6px_rgba(255,180,100,0.10)]">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-orange-100 text-[16px]">✨</div>
            <span className="truncate text-[18px] font-bold text-[#5C4D3E]">{card.title || "渡安排好了"}</span>
          </div>
          <span className="shrink-0 text-[18px] leading-none text-[#A89A8B]">•••</span>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-1.5 text-[#8D7B68]">
            <span className="shrink-0 text-[15px] text-orange-400">📍</span>
            <span className="truncate text-[14px]">
              {card.origin ? (
                <>
                  从 <span className="font-medium text-[#5C4D3E]">{card.origin}</span> 出发
                </>
              ) : (
                "路线已规划"
              )}
            </span>
          </div>
          {card.optimized ? (
            <div className="flex shrink-0 items-center gap-1 rounded-full border border-[#D0E7D2] bg-[#E8F5E9] px-2 py-0.5">
              <span className="text-[10px] text-[#4CAF50]">✨</span>
              <span className="text-[11px] font-bold text-[#4CAF50]">已顺路排序</span>
            </div>
          ) : null}
        </div>

        {order.length ? (
          <div className="flex flex-wrap gap-2">
            {order.slice(0, 4).map((name, index) => (
              <div key={`${name}-${index}`} className="flex max-w-full items-center gap-2 rounded-xl border border-[#FFECDA] bg-white px-3 py-1.5 shadow-sm">
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white ${index % 2 === 0 ? "bg-orange-400" : "bg-blue-300"}`}>
                  {index + 1}
                </span>
                <span className="truncate text-[14px] font-medium text-[#5C4D3E]">{name}</span>
              </div>
            ))}
            {order.length > 4 ? (
              <div className="flex items-center rounded-xl border border-[#FFECDA] bg-white px-3 py-1.5 text-[12px] font-bold text-[#A89A8B] shadow-sm">
                +{order.length - 4}
              </div>
            ) : null}
          </div>
        ) : null}

        {legs.length ? (
          <div className="relative py-1 pl-6">
            <div className="absolute bottom-0 left-1.5 top-0 border-l-2 border-dashed border-orange-200" />
            <div className="space-y-4">
              {legs.slice(0, 3).map((leg, index) => {
                const preferred = leg.mode === "taxi" ? leg.driving : leg.transit;
                const brief = [
                  travelModeLabel(leg.mode),
                  preferred?.duration,
                  leg.mode === "taxi" ? preferred?.distance : preferred?.walking ? `步行${preferred.walking}` : "",
                ].filter(Boolean);
                return (
                  <div key={`${leg.from}-${leg.to}-${index}`} className="relative">
                    <div className="absolute -left-[22px] top-1.5 h-2 w-2 rounded-full border-2 border-white bg-orange-400" />
                    <div className="flex min-w-0 flex-col">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-[14px] font-bold text-[#5C4D3E]">{leg.from}</span>
                        <span className="shrink-0 text-[12px] text-[#A89A8B]">→</span>
                        <span className="truncate text-[14px] font-bold text-[#5C4D3E]">{leg.to}</span>
                      </div>
                      <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2 text-[12px] text-[#A89A8B]">
                        <span>{leg.mode === "taxi" ? "🚗" : "🚇"}</span>
                        <span>{brief.join(" · ") || leg.reason || "路线详情见卡片"}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        <div className="flex items-center justify-center gap-1 border-t border-[#FFF1E0] pt-2">
          <span className="text-[12px] text-[#A89A8B]">点击查看详情</span>
          <span className="text-[12px] text-[#A89A8B]">›</span>
        </div>
      </div>
    </button>
  );
}

export function TravelPlanResultModal({ card, onClose }: { card: TravelPlanResultCard; onClose: () => void }) {
  const legs = card.legs || [];
  const order = card.destinations?.length ? card.destinations : legs.map((leg) => leg.to).filter(Boolean);
  return (
    <Modal title={card.title || "渡安排好了"} onClose={onClose}>
      <div className="space-y-3">
        <div className="rounded-[18px] bg-white px-3 py-3">
          <div className="text-[12px] font-semibold text-gray-500">顺序</div>
          <div className="mt-2 space-y-1.5">
            {card.origin ? <div className="text-[13px] font-semibold text-gray-900">0. {card.origin}</div> : null}
            {order.map((name, index) => (
              <div key={`${name}-${index}`} className="text-[13px] font-semibold text-gray-900">{index + 1}. {name}</div>
            ))}
          </div>
          {card.optimized ? <div className="mt-2 text-[11px] text-indigo-700">已按位置做顺路排序</div> : null}
        </div>
        {legs.map((leg, index) => {
          const transitCost = formatYuan(leg.transit?.costYuan);
          const taxiCost = formatYuan(leg.transit?.taxiCostYuan);
          return (
            <div key={`${leg.from}-${leg.to}-${index}`} className="rounded-[18px] bg-white px-3 py-3">
              <div className="text-[12px] font-semibold text-gray-500">第 {index + 1} 段</div>
              <div className="mt-1 text-[15px] font-bold leading-5 text-gray-900">{leg.from}{" -> "}{leg.to}</div>
              <div className="mt-2 rounded-[14px] bg-indigo-50 px-3 py-2 text-[12px] font-semibold leading-5 text-indigo-800">
                推荐：{travelModeLabel(leg.mode)}{leg.reason ? `，${leg.reason}` : ""}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <div className="rounded-[14px] bg-gray-50 px-3 py-2">
                  <div className="text-[11px] font-semibold text-gray-500">地铁公交</div>
                  <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-800">
                    {leg.transit?.ok ? [leg.transit.duration, leg.transit.walking ? `步行${leg.transit.walking}` : "", transitCost].filter(Boolean).join(" · ") : (leg.transit?.error || "无结果")}
                  </div>
                </div>
                <div className="rounded-[14px] bg-gray-50 px-3 py-2">
                  <div className="text-[11px] font-semibold text-gray-500">打车/驾车</div>
                  <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-800">
                    {leg.driving?.ok ? [leg.driving.duration, leg.driving.distance, taxiCost ? `预估${taxiCost}` : ""].filter(Boolean).join(" · ") : (leg.driving?.error || "无结果")}
                  </div>
                </div>
              </div>
              {leg.transit?.steps?.length ? (
                <div className="mt-2 space-y-1">
                  {leg.transit.steps.map((step, stepIndex) => (
                    <div key={`${step}-${stepIndex}`} className="text-[12px] leading-5 text-gray-600">{stepIndex + 1}. {step}</div>
                  ))}
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {leg.links?.navi ? (
                  <a className="rounded-full bg-gray-900 px-3 py-2 text-[12px] font-semibold text-white" href={leg.links.navi} target="_blank" rel="noreferrer">打开导航</a>
                ) : null}
                {leg.links?.taxi ? (
                  <a className="rounded-full bg-gray-100 px-3 py-2 text-[12px] font-semibold text-gray-800" href={leg.links.taxi} target="_blank" rel="noreferrer">打开打车</a>
                ) : null}
              </div>
            </div>
          );
        })}
        {card.personalMapUrl ? (
          <a className="block rounded-[18px] bg-gray-900 px-4 py-3 text-center text-[13px] font-semibold text-white" href={card.personalMapUrl} target="_blank" rel="noreferrer">打开高德专属地图</a>
        ) : null}
        {card.note ? <div className="px-1 text-[11px] leading-5 text-gray-500">{card.note}</div> : null}
      </div>
    </Modal>
  );
}

export function formatMeters(value?: number): string {
  const meters = Number(value || 0);
  if (!Number.isFinite(meters) || meters <= 0) return "";
  if (meters < 1000) return `${Math.round(meters)}米`;
  return `${(meters / 1000).toFixed(1)}公里`;
}

export function TravelTransportDetailBubble({ card, onOpen }: { card: TravelTransportDetailCard; onOpen: () => void }) {
  const preferred = card.mode === "taxi" ? card.driving : card.transit;
  const brief = [
    travelModeLabel(card.mode),
    preferred?.duration,
    card.mode === "taxi" ? preferred?.distance : preferred?.walking ? `步行${preferred.walking}` : "",
  ].filter(Boolean).join(" · ");
  return (
    <button
      className="block w-full max-w-[320px] rounded-[22px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[12px] font-semibold text-gray-500">{card.title || "这段怎么走"}</span>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">{card.cacheHit ? "已缓存" : "刚查到"}</span>
      </div>
      <div className="text-[15px] font-bold leading-5 text-gray-900">{card.from} → {card.to}</div>
      <div className="mt-2 text-[12px] leading-5 text-gray-600">{brief || card.reason || "点击查看这一段路线"}</div>
    </button>
  );
}

export function TravelTransportDetailModal({ card, onClose }: { card: TravelTransportDetailCard; onClose: () => void }) {
  const transitCost = formatYuan(card.transit?.costYuan);
  const taxiCost = formatYuan(card.transit?.taxiCostYuan);
  return (
    <Modal title={card.title || "这段怎么走"} onClose={onClose}>
      <div className="space-y-3">
        <div className="rounded-[18px] bg-white px-3 py-3">
          <div className="text-[12px] font-semibold text-gray-500">路线</div>
          <div className="mt-1 text-[15px] font-bold leading-5 text-gray-900">{card.from}{" -> "}{card.to}</div>
          <div className="mt-2 rounded-[14px] bg-gray-50 px-3 py-2 text-[12px] font-semibold leading-5 text-gray-800">
            推荐：{travelModeLabel(card.mode)}{card.reason ? `，${card.reason}` : ""}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-[18px] bg-white px-3 py-3">
            <div className="text-[11px] font-semibold text-gray-500">地铁公交</div>
            <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-800">
              {card.transit?.ok ? [card.transit.duration, card.transit.walking ? `步行${card.transit.walking}` : "", transitCost].filter(Boolean).join(" · ") : (card.transit?.error || "无结果")}
            </div>
          </div>
          <div className="rounded-[18px] bg-white px-3 py-3">
            <div className="text-[11px] font-semibold text-gray-500">打车/驾车</div>
            <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-800">
              {card.driving?.ok ? [card.driving.duration, card.driving.distance, taxiCost ? `预估${taxiCost}` : ""].filter(Boolean).join(" · ") : (card.driving?.error || "无结果")}
            </div>
          </div>
        </div>
        {card.transit?.steps?.length ? (
          <div className="rounded-[18px] bg-white px-3 py-3">
            <div className="text-[12px] font-semibold text-gray-500">换乘步骤</div>
            <div className="mt-2 space-y-1">
              {card.transit.steps.map((step, index) => (
                <div key={`${step}-${index}`} className="text-[12px] leading-5 text-gray-600">{index + 1}. {step}</div>
              ))}
            </div>
          </div>
        ) : null}
        {card.note ? <div className="px-1 text-[11px] leading-5 text-gray-500">{card.note}</div> : null}
      </div>
    </Modal>
  );
}

export function TravelFoodDetailBubble({ card, onOpen }: { card: TravelFoodDetailCard; onOpen: () => void }) {
  const first = card.items?.[0]?.name;
  return (
    <button
      className="block w-full max-w-[320px] rounded-[22px] border border-gray-200 bg-white px-4 py-3 text-left shadow-[0_6px_18px_rgba(15,23,42,0.06)] transition-transform active:scale-[0.98]"
      onClick={onOpen}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[12px] font-semibold text-gray-500">{card.title || "附近吃这些"}</span>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">{card.cacheHit ? "已缓存" : "刚查到"}</span>
      </div>
      <div className="text-[15px] font-bold leading-5 text-gray-900">{card.placeName || card.keywords || "附近"}</div>
      <div className="mt-2 text-[12px] leading-5 text-gray-600">{first ? `比如 ${first}` : "点击查看候选"}</div>
    </button>
  );
}

export function TravelFoodDetailModal({ card, onClose }: { card: TravelFoodDetailCard; onClose: () => void }) {
  return (
    <Modal title={card.title || "附近吃这些"} onClose={onClose}>
      <div className="space-y-3">
        <div className="rounded-[18px] bg-white px-3 py-3">
          <div className="text-[12px] font-semibold text-gray-500">位置</div>
          <div className="mt-1 text-[15px] font-bold leading-5 text-gray-900">{card.placeName || "附近"}</div>
          {card.keywords ? <div className="mt-1 text-[12px] leading-5 text-gray-500">关键词：{card.keywords}</div> : null}
        </div>
        {(card.items || []).map((item, index) => {
          const distance = formatMeters(item.distanceMeters);
          const meta = [distance, item.rating ? `评分${item.rating}` : "", item.cost ? `人均${item.cost}` : ""].filter(Boolean).join(" · ");
          return (
            <div key={`${item.name}-${index}`} className="rounded-[18px] bg-white px-3 py-3">
              <div className="text-[14px] font-bold leading-5 text-gray-900">{item.name}</div>
              {meta ? <div className="mt-1 text-[12px] font-semibold leading-5 text-gray-700">{meta}</div> : null}
              {item.address ? <div className="mt-1 text-[12px] leading-5 text-gray-500">{item.address}</div> : null}
            </div>
          );
        })}
        {!(card.items || []).length ? <div className="rounded-[18px] bg-white px-3 py-3 text-[13px] text-gray-500">这次没查到稳定候选。</div> : null}
        {card.note ? <div className="px-1 text-[11px] leading-5 text-gray-500">{card.note}</div> : null}
      </div>
    </Modal>
  );
}

