import React from "react";

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
    "text-xs px-3 py-2 rounded-[18px] shadow-soft2 disabled:opacity-60 disabled:cursor-not-allowed active:scale-[0.99] transition";
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
      <div className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-xl max-h-[80vh] overflow-auto rounded-t-[34px] bg-[rgba(244,247,251,0.84)] p-4 shadow-[0_-10px_24px_rgba(154,168,186,0.14)] backdrop-blur-2xl safe-bottom">
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

