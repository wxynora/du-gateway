import React from "react";
import { ChevronRightIcon } from "./icons";

export function PageCardRow({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      className="flex w-full items-center rounded-[22px] border border-gray-100/60 bg-white p-4 text-left shadow-[0_4px_20px_-2px_rgba(0,0,0,0.03)] transition-transform active:scale-[0.98]"
      onClick={onClick}
    >
      <div className="mr-3 flex h-[38px] w-[38px] items-center justify-center rounded-full bg-gray-50 text-gray-600">
        {icon}
      </div>
      <span className="flex-1 text-[15px] font-medium tracking-wide text-gray-800">{label}</span>
      <ChevronRightIcon />
    </button>
  );
}

export function FloatingBallSettingRow({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: (next: boolean) => void;
}) {
  return (
    <div className="flex min-h-[60px] w-full items-center border-b border-gray-50 px-4 py-4">
      <span className="mr-4 text-gray-400">
        <svg className="h-5 w-5 stroke-[1.5]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="12" cy="12" r="8" opacity="0.35" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </span>
      <span className="flex-1 text-[15px] font-medium tracking-wide text-gray-800">显示悬浮球</span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${enabled ? "bg-gray-800" : "bg-gray-200"}`}
        onClick={() => onToggle(!enabled)}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-[22px]" : "translate-x-0"}`}
        />
      </button>
    </div>
  );
}

export function SwitchSettingRow({
  icon,
  label,
  enabled,
  disabled = false,
  onToggle,
  last,
}: {
  icon: React.ReactNode;
  label: string;
  enabled: boolean;
  disabled?: boolean;
  onToggle: (next: boolean) => void;
  last?: boolean;
}) {
  return (
    <div className={`flex min-h-[60px] w-full items-center px-4 py-4 ${last ? "" : "border-b border-gray-50"} ${disabled ? "opacity-60" : ""}`}>
      <span className="mr-4 text-gray-400">{icon}</span>
      <span className="flex-1 text-[15px] font-medium tracking-wide text-gray-800">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${enabled ? "bg-gray-800" : "bg-gray-200"} ${disabled ? "cursor-not-allowed" : ""}`}
        onClick={() => onToggle(!enabled)}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-[22px]" : "translate-x-0"}`}
        />
      </button>
    </div>
  );
}

export function ListRow({
  icon,
  label,
  onClick,
  last,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  last?: boolean;
}) {
  return (
    <button
      className={`flex min-h-[60px] w-full items-center px-4 py-4 text-left transition-colors active:bg-gray-50 ${last ? "" : "border-b border-gray-50"}`}
      onClick={onClick}
    >
      <span className="mr-4 text-gray-400">{icon}</span>
      <span className="flex-1 text-[15px] font-medium tracking-wide text-gray-800">{label}</span>
      <ChevronRightIcon />
    </button>
  );
}
