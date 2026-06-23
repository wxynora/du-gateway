import React, { useEffect, useMemo, useState } from "react";

type PlanYear = "year1" | "year2" | "year3";

type PlanMonth = {
  id: string;
  label: string;
  year: PlanYear;
  income: number;
  fixed: number;
  huabei: number;
  daily: number;
  saveTarget: number;
  phase: string;
  note?: string;
};

type MonthRecord = {
  checked?: boolean;
  saved?: number;
  noNewDebt?: boolean;
  note?: string;
  updatedAt?: string;
};

type AnnualRecord = {
  bonus?: number;
  parentPaid?: number;
  done?: boolean;
};

type BudgetState = {
  records: Record<string, MonthRecord>;
  annual: Record<PlanYear, AnnualRecord>;
  reserve?: number;
  selectedMonth?: string;
};

const STORAGE_KEY = "miniapp.budgetCheckIn.v1";

const PLAN_MONTHS: PlanMonth[] = [
  { id: "2026-06", label: "2026.06", year: "year1", income: 2000, fixed: 470, huabei: 1000, daily: 450, saveTarget: 80, phase: "过桥期" },
  { id: "2026-07", label: "2026.07", year: "year1", income: 2000, fixed: 470, huabei: 950, daily: 450, saveTarget: 130, phase: "过桥期" },
  { id: "2026-08", label: "2026.08", year: "year1", income: 2000, fixed: 470, huabei: 750, daily: 550, saveTarget: 230, phase: "过桥期" },
  { id: "2026-09", label: "2026.09", year: "year1", income: 1900, fixed: 370, huabei: 580, daily: 600, saveTarget: 350, phase: "入职后" },
  { id: "2026-10", label: "2026.10", year: "year1", income: 1900, fixed: 370, huabei: 450, daily: 650, saveTarget: 430, phase: "入职后" },
  { id: "2026-11", label: "2026.11", year: "year1", income: 1900, fixed: 370, huabei: 300, daily: 650, saveTarget: 580, phase: "稳住现金" },
  { id: "2026-12", label: "2026.12", year: "year1", income: 1900, fixed: 370, huabei: 300, daily: 700, saveTarget: 530, phase: "稳住现金" },
  { id: "2027-01", label: "2027.01", year: "year1", income: 1900, fixed: 370, huabei: 300, daily: 700, saveTarget: 530, phase: "稳住现金" },
  { id: "2027-02", label: "2027.02", year: "year1", income: 1900, fixed: 370, huabei: 300, daily: 800, saveTarget: 430, phase: "留点年味" },
  { id: "2027-03", label: "2027.03", year: "year1", income: 1900, fixed: 370, huabei: 300, daily: 700, saveTarget: 530, phase: "等绩效" },
  { id: "2027-04", label: "2027.04", year: "year1", income: 1900, fixed: 370, huabei: 300, daily: 700, saveTarget: 530, phase: "绩效月", note: "绩效到账后，第一笔还爸妈 5000。" },
  ...Array.from({ length: 12 }, (_, index): PlanMonth => {
    const monthIndex = index + 4;
    const year = 2027 + Math.floor(monthIndex / 12);
    const month = (monthIndex % 12) + 1;
    return {
      id: `${year}-${String(month).padStart(2, "0")}`,
      label: `${year}.${String(month).padStart(2, "0")}`,
      year: "year2",
      income: 1900,
      fixed: 370,
      huabei: 300,
      daily: 800,
      saveTarget: 430,
      phase: index === 11 ? "绩效月" : "常规月",
      note: index === 11 ? "第二笔目标 20000，备用金慢慢补到 5000。" : undefined,
    };
  }),
  ...Array.from({ length: 12 }, (_, index): PlanMonth => {
    const monthIndex = index + 4;
    const year = 2028 + Math.floor(monthIndex / 12);
    const month = (monthIndex % 12) + 1;
    return {
      id: `${year}-${String(month).padStart(2, "0")}`,
      label: `${year}.${String(month).padStart(2, "0")}`,
      year: "year3",
      income: 1900,
      fixed: 370,
      huabei: 300,
      daily: 850,
      saveTarget: 380,
      phase: index === 11 ? "清账月" : "常规月",
      note: index === 11 ? "第三笔目标 23000，把 48000 还清。" : undefined,
    };
  }),
];

const YEAR_META: Record<PlanYear, { title: string; parentTarget: number; reserveTarget: number; bonusRange: string }> = {
  year1: { title: "第一年", parentTarget: 5000, reserveTarget: 3000, bonusRange: "6600-8300" },
  year2: { title: "第二年", parentTarget: 20000, reserveTarget: 5000, bonusRange: "20000-25000" },
  year3: { title: "第三年", parentTarget: 23000, reserveTarget: 5000, bonusRange: "20000-25000" },
};

function readState(): BudgetState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { records: {}, annual: {} as BudgetState["annual"] };
    const parsed = JSON.parse(raw) as Partial<BudgetState>;
    return {
      records: parsed.records && typeof parsed.records === "object" ? parsed.records : {},
      annual: parsed.annual && typeof parsed.annual === "object" ? parsed.annual : ({} as BudgetState["annual"]),
      reserve: finiteNumber(parsed.reserve),
      selectedMonth: typeof parsed.selectedMonth === "string" ? parsed.selectedMonth : undefined,
    };
  } catch {
    return { records: {}, annual: {} as BudgetState["annual"] };
  }
}

function finiteNumber(value: unknown): number | undefined {
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function money(value: number | undefined): string {
  const n = Math.round(Number(value || 0));
  return `¥${n.toLocaleString("zh-CN")}`;
}

function currentMonthId(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function initialMonthId(state: BudgetState): string {
  if (state.selectedMonth && PLAN_MONTHS.some((m) => m.id === state.selectedMonth)) return state.selectedMonth;
  const current = currentMonthId();
  if (PLAN_MONTHS.some((m) => m.id === current)) return current;
  return PLAN_MONTHS.find((m) => !state.records[m.id]?.checked)?.id || PLAN_MONTHS[0].id;
}

function parseAmount(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.round(n)) : undefined;
}

export function BudgetCheckInTab() {
  const [state, setState] = useState<BudgetState>(() => readState());
  const [selectedId, setSelectedId] = useState(() => initialMonthId(readState()));

  useEffect(() => {
    const next = { ...state, selectedMonth: selectedId };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Local storage may be unavailable in restricted WebViews.
    }
  }, [selectedId, state]);

  const selected = PLAN_MONTHS.find((month) => month.id === selectedId) || PLAN_MONTHS[0];
  const record = state.records[selected.id] || {};
  const yearPlan = YEAR_META[selected.year];
  const annual = state.annual[selected.year] || {};

  const totals = useMemo(() => {
    const plannedSaved = PLAN_MONTHS.reduce((sum, month) => sum + month.saveTarget, 0);
    const actualSaved = PLAN_MONTHS.reduce((sum, month) => sum + Number(state.records[month.id]?.saved || 0), 0);
    const checked = PLAN_MONTHS.reduce((sum, month) => sum + (state.records[month.id]?.checked ? 1 : 0), 0);
    const parentPaid = (Object.keys(YEAR_META) as PlanYear[]).reduce((sum, year) => sum + Number(state.annual[year]?.parentPaid || 0), 0);
    return { plannedSaved, actualSaved, checked, parentPaid };
  }, [state.annual, state.records]);

  function updateMonth(id: string, patch: Partial<MonthRecord>) {
    setState((prev) => ({
      ...prev,
      records: {
        ...prev.records,
        [id]: {
          ...prev.records[id],
          ...patch,
          updatedAt: new Date().toISOString(),
        },
      },
    }));
  }

  function updateAnnual(year: PlanYear, patch: Partial<AnnualRecord>) {
    setState((prev) => ({
      ...prev,
      annual: {
        ...prev.annual,
        [year]: {
          ...prev.annual[year],
          ...patch,
        },
      },
    }));
  }

  function resetMonth() {
    setState((prev) => {
      const nextRecords = { ...prev.records };
      delete nextRecords[selected.id];
      return { ...prev, records: nextRecords };
    });
  }

  const yearMonths = PLAN_MONTHS.filter((month) => month.year === selected.year);
  const yearSaved = yearMonths.reduce((sum, month) => sum + Number(state.records[month.id]?.saved || 0), 0);
  const yearTarget = yearMonths.reduce((sum, month) => sum + month.saveTarget, 0);
  const reserve = Number(state.reserve || 0);
  const reserveRatio = Math.min(100, (reserve / yearPlan.reserveTarget) * 100);
  const parentRatio = Math.min(100, (totals.parentPaid / 48000) * 100);
  const monthBalance = selected.income - selected.fixed - selected.huabei - selected.daily;
  const oilFee = selected.id <= "2026-08" ? 200 : 100;

  return (
    <div className="min-h-full bg-[#F8F8F4] pb-8 text-[#24221F]">
      <div className="mx-auto flex w-full max-w-[520px] flex-col gap-4 px-1 py-4">
        <section className="overflow-hidden rounded-[26px] bg-[#1F2924] text-[#F8F3E7] shadow-[0_18px_44px_rgba(31,41,36,0.20)]">
          <div className="relative p-5">
            <div className="absolute right-[-34px] top-[-48px] h-32 w-32 rounded-full bg-[#EAC66A]/25 blur-2xl" />
            <div className="relative">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#EAC66A]">三年还清计划</div>
              <div className="mt-3 flex items-end justify-between gap-3">
                <div>
                  <div className="text-[32px] font-semibold leading-none">{money(48000 - totals.parentPaid)}</div>
                  <div className="mt-2 text-[12px] text-[#D7D0C3]">爸妈剩余</div>
                </div>
                <div className="text-right">
                  <div className="text-[20px] font-semibold">{money(state.reserve)}</div>
                  <div className="mt-2 text-[12px] text-[#D7D0C3]">备用金</div>
                </div>
              </div>
              <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/12">
                <div className="h-full rounded-full bg-[#EAC66A]" style={{ width: `${parentRatio}%` }} />
              </div>
              <div className="mt-2 flex justify-between text-[11px] text-[#D7D0C3]">
                <span>已还 {money(totals.parentPaid)}</span>
                <span>{totals.checked}/{PLAN_MONTHS.length} 月打卡</span>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[22px] border border-[#E7E0D4] bg-[#FFFDF7] p-4 shadow-[0_10px_28px_rgba(42,40,35,0.06)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[12px] font-semibold text-[#8A7661]">{yearPlan.title}</div>
              <div className="mt-1 text-[18px] font-semibold">{selected.label}</div>
            </div>
            <select
              className="h-10 rounded-2xl border border-[#E3D8C6] bg-[#F7F2EA] px-3 text-[13px] font-semibold text-[#3B3028] outline-none"
              value={selectedId}
              onChange={(event) => setSelectedId(event.target.value)}
            >
              {PLAN_MONTHS.map((month) => (
                <option key={month.id} value={month.id}>
                  {month.label}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2">
            <Metric label="到手" value={money(selected.income)} tone="green" />
            <Metric label="固定+油费" value={money(selected.fixed)} tone="stone" />
            <Metric label="花呗" value={money(selected.huabei)} tone="rose" />
            <Metric label="日常可花" value={money(selected.daily)} tone="gold" />
          </div>
          <div className="mt-3 text-[11px] leading-5 text-[#8A8176]">
            固定支出按 170 + 机动 100 + 油费 {oilFee} 算；二手收入先不算进计划。
          </div>

          <div className="mt-4 rounded-[20px] bg-[#F1EEE7] p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[12px] text-[#786D61]">本月建议存</div>
                <div className="mt-1 text-[28px] font-semibold">{money(selected.saveTarget)}</div>
              </div>
              <div className="rounded-full bg-white px-3 py-1 text-[12px] font-semibold text-[#6B5D50]">{selected.phase}</div>
            </div>
            <div className="mt-3 text-[12px] leading-5 text-[#756B60]">
              工资扣完计划项后余量 {money(monthBalance)}。{selected.note || "按这个月跑完就行，先不追求漂亮账面。"}
            </div>
          </div>
        </section>

        <section className="rounded-[22px] border border-[#DDE7DF] bg-[#F9FFFB] p-4 shadow-[0_10px_28px_rgba(31,67,44,0.05)]">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[13px] font-semibold text-[#314C39]">本月打卡</div>
              <div className="mt-1 text-[12px] text-[#748678]">{record.checked ? "已稳住" : "还没打"}</div>
            </div>
            <button
              className={`h-10 rounded-full px-4 text-[13px] font-semibold transition active:scale-[0.98] ${
                record.checked ? "bg-[#314C39] text-white" : "bg-[#E0EFE4] text-[#314C39]"
              }`}
              onClick={() => updateMonth(selected.id, { checked: !record.checked, saved: record.saved ?? selected.saveTarget })}
            >
              {record.checked ? "取消打卡" : "打卡"}
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3">
            <label className="block">
              <span className="text-[12px] font-semibold text-[#5B6E60]">实际存下</span>
              <input
                className="mt-2 h-11 w-full rounded-2xl border border-[#D9E7DD] bg-white px-3 text-[15px] font-semibold text-[#203126] outline-none"
                inputMode="numeric"
                value={record.saved ?? ""}
                placeholder={String(selected.saveTarget)}
                onChange={(event) => updateMonth(selected.id, { saved: parseAmount(event.target.value) })}
              />
            </label>
            <label className="flex items-center justify-between rounded-2xl bg-white px-3 py-3">
              <span className="text-[13px] font-semibold text-[#314C39]">没有新增花呗</span>
              <button
                type="button"
                role="switch"
                aria-checked={Boolean(record.noNewDebt)}
                className={`relative h-7 w-12 rounded-full transition ${record.noNewDebt ? "bg-[#314C39]" : "bg-[#D7DED8]"}`}
                onClick={() => updateMonth(selected.id, { noNewDebt: !record.noNewDebt })}
              >
                <span className={`absolute left-0.5 top-0.5 h-6 w-6 rounded-full bg-white shadow transition ${record.noNewDebt ? "translate-x-[20px]" : ""}`} />
              </button>
            </label>
            <label className="block">
              <span className="text-[12px] font-semibold text-[#5B6E60]">备注</span>
              <textarea
                className="mt-2 min-h-[72px] w-full resize-none rounded-2xl border border-[#D9E7DD] bg-white px-3 py-3 text-[13px] leading-5 text-[#203126] outline-none"
                value={record.note || ""}
                placeholder="比如：买了衣服、送了礼物、这个月比较紧。"
                onChange={(event) => updateMonth(selected.id, { note: event.target.value })}
              />
            </label>
          </div>

          <div className="mt-3 flex gap-2">
            <button className="rounded-full bg-[#314C39] px-4 py-2 text-[12px] font-semibold text-white active:scale-[0.98]" onClick={() => updateMonth(selected.id, { checked: true, saved: selected.saveTarget, noNewDebt: true })}>
              按计划记好
            </button>
            <button className="rounded-full bg-white px-4 py-2 text-[12px] font-semibold text-[#657267] active:scale-[0.98]" onClick={resetMonth}>
              清本月
            </button>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-3">
          <ProgressPanel
            title={`${yearPlan.title}工资存款`}
            current={yearSaved}
            target={yearTarget}
            caption={`计划 ${money(yearTarget)}，绩效估 ${yearPlan.bonusRange}`}
          />
          <ProgressPanel
            title="备用金"
            current={reserve}
            target={yearPlan.reserveTarget}
            caption={`${yearPlan.title}目标 ${money(yearPlan.reserveTarget)}，第一年不用硬凑 5000`}
            ratio={reserveRatio}
          />
        </section>

        <section className="rounded-[22px] border border-[#E7E0D4] bg-white p-4 shadow-[0_10px_28px_rgba(42,40,35,0.05)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[13px] font-semibold text-[#312A23]">{yearPlan.title}绩效后动作</div>
              <div className="mt-1 text-[12px] text-[#7C7268]">目标还爸妈 {money(yearPlan.parentTarget)}</div>
            </div>
            <button
              className={`h-9 rounded-full px-3 text-[12px] font-semibold transition active:scale-[0.98] ${
                annual.done ? "bg-[#2F2923] text-white" : "bg-[#F1EEE7] text-[#4E443A]"
              }`}
              onClick={() => updateAnnual(selected.year, { done: !annual.done, parentPaid: annual.parentPaid ?? yearPlan.parentTarget })}
            >
              {annual.done ? "已完成" : "标记"}
            </button>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[12px] font-semibold text-[#71675F]">绩效到手</span>
              <input
                className="mt-2 h-10 w-full rounded-2xl border border-[#E8DFD1] bg-[#FFFDF7] px-3 text-[14px] font-semibold outline-none"
                inputMode="numeric"
                value={annual.bonus ?? ""}
                placeholder={yearPlan.bonusRange}
                onChange={(event) => updateAnnual(selected.year, { bonus: parseAmount(event.target.value) })}
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-semibold text-[#71675F]">已还爸妈</span>
              <input
                className="mt-2 h-10 w-full rounded-2xl border border-[#E8DFD1] bg-[#FFFDF7] px-3 text-[14px] font-semibold outline-none"
                inputMode="numeric"
                value={annual.parentPaid ?? ""}
                placeholder={String(yearPlan.parentTarget)}
                onChange={(event) => updateAnnual(selected.year, { parentPaid: parseAmount(event.target.value) })}
              />
            </label>
          </div>
          <label className="mt-4 block">
            <span className="text-[12px] font-semibold text-[#71675F]">当前备用金</span>
            <input
              className="mt-2 h-10 w-full rounded-2xl border border-[#E8DFD1] bg-[#FFFDF7] px-3 text-[14px] font-semibold outline-none"
              inputMode="numeric"
              value={state.reserve ?? ""}
              placeholder={String(yearPlan.reserveTarget)}
              onChange={(event) => setState((prev) => ({ ...prev, reserve: parseAmount(event.target.value) }))}
            />
          </label>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: "green" | "stone" | "rose" | "gold" }) {
  const toneClass = {
    green: "bg-[#E7F0E6] text-[#314C39]",
    stone: "bg-[#F1EEE7] text-[#5F554B]",
    rose: "bg-[#F9E6E2] text-[#8A4A43]",
    gold: "bg-[#F6E9BE] text-[#6B5420]",
  }[tone];
  return (
    <div className={`rounded-[18px] px-3 py-3 ${toneClass}`}>
      <div className="text-[11px] font-semibold opacity-70">{label}</div>
      <div className="mt-1 text-[17px] font-semibold">{value}</div>
    </div>
  );
}

function ProgressPanel({
  title,
  current,
  target,
  caption,
  ratio,
}: {
  title: string;
  current: number;
  target: number;
  caption: string;
  ratio?: number;
}) {
  const width = Math.min(100, ratio ?? (target > 0 ? (current / target) * 100 : 0));
  return (
    <div className="rounded-[22px] border border-[#E6E1D8] bg-white p-4">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[13px] font-semibold text-[#332E28]">{title}</div>
        <div className="text-[16px] font-semibold text-[#332E28]">{money(current)}</div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#EEE8DD]">
        <div className="h-full rounded-full bg-[#5F7F64]" style={{ width: `${width}%` }} />
      </div>
      <div className="mt-2 text-[12px] text-[#81766A]">{caption}</div>
    </div>
  );
}
