import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="neo-panel">
      <div className="px-4 py-3">
        <div className="text-sm font-semibold text-cream-text">{title}</div>
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  );
}

export function Pill({ ok, text }: { ok: boolean; text: string }) {
  return (
    <span
      className={
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs shadow-soft2 " +
        (ok
          ? "bg-[rgba(205,227,218,0.92)] text-cream-text"
          : "bg-[rgba(236,206,221,0.92)] text-cream-text")
      }
    >
      {text}
    </span>
  );
}

export function HeaderStatusPill({
  text,
  dotClassName,
  pulse = false,
}: {
  text: string;
  dotClassName: string;
  pulse?: boolean;
}) {
  return (
    <div className="inline-flex h-8 items-center whitespace-nowrap rounded-full border border-gray-100 bg-gray-50 px-3 text-[11px] font-medium text-gray-500 shadow-[0_4px_14px_rgba(15,23,42,0.04)]">
      <span className={`mr-2 h-1.5 w-1.5 rounded-full ${pulse ? "animate-pulse " : ""}${dotClassName}`} />
      <span>{text}</span>
    </div>
  );
}

export function HeaderPortal({ targetId, children }: { targetId: string; children: React.ReactNode }) {
  const [target, setTarget] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setTarget(document.getElementById(targetId));
  }, [targetId]);

  if (!target) return null;
  return createPortal(children, target);
}

export function Btn({
  children,
  onClick,
  kind = "default",
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  kind?: "default" | "danger" | "blue" | "pink" | "yellow" | "green" | "dark";
  disabled?: boolean;
}) {
  const base =
    "text-xs px-3 py-2 rounded-[18px] shadow-[4px_4px_10px_rgba(173,182,196,0.22),-2px_-2px_5px_rgba(255,255,255,0.44)] disabled:opacity-60 disabled:cursor-not-allowed active:translate-y-[1px] active:shadow-[2px_2px_6px_rgba(173,182,196,0.18),-1px_-1px_3px_rgba(255,255,255,0.34)] transition";
  const cls = (() => {
    if (kind === "danger") return base + " bg-[#E8B9B3] text-[#7C3A33]";
    if (kind === "blue") return base + " bg-[#D6E4F2] text-cream-text";
    if (kind === "pink") return base + " bg-[#EFD5E1] text-cream-text";
    if (kind === "yellow") return base + " bg-[#F2E7BF] text-cream-text";
    if (kind === "green") return base + " bg-[#D4E5DD] text-cream-text";
    if (kind === "dark") return base + " bg-[#7D8697] text-white";
    return base + " bg-[rgba(244,247,251,0.88)] text-cream-text";
  })();
  return (
    <button className={cls} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/10 backdrop-blur-[4px]" onClick={onClose} />
      <div className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-xl max-h-[80vh] overflow-auto rounded-t-[34px] bg-[rgba(244,247,251,0.84)] p-4 shadow-[0_-8px_18px_rgba(173,182,196,0.22)] backdrop-blur-2xl safe-bottom">
        <div className="flex items-center justify-between">
          <div className="neo-chip">{
            title
          }</div>
          <button
            className="neo-icon-btn h-9 w-9 text-xs"
            onClick={onClose}
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </div>
        <div className="mt-3">{children}</div>
      </div>
    </>
  );
}
