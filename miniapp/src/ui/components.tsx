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
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs shadow-soft2 border border-white/70 " +
        (ok
          ? "bg-[linear-gradient(145deg,rgba(223,246,235,0.92),rgba(191,212,204,0.78))] text-cream-text"
          : "bg-[linear-gradient(145deg,rgba(251,230,236,0.94),rgba(232,198,210,0.82))] text-cream-text")
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
    "text-xs px-3 py-2 rounded-[18px] border border-white/80 shadow-soft2 disabled:opacity-60 disabled:cursor-not-allowed active:scale-[0.99] transition";
  const cls = (() => {
    if (kind === "danger") return base + " bg-[linear-gradient(145deg,rgba(255,243,243,0.94),rgba(242,208,203,0.84))] text-cream-danger";
    if (kind === "blue") return base + " bg-[linear-gradient(145deg,rgba(245,249,255,0.94),rgba(212,226,245,0.84))] text-cream-text";
    if (kind === "pink") return base + " bg-[linear-gradient(145deg,rgba(255,248,251,0.94),rgba(236,206,221,0.84))] text-cream-text";
    if (kind === "yellow") return base + " bg-[linear-gradient(145deg,rgba(255,251,242,0.95),rgba(244,229,189,0.82))] text-cream-text";
    if (kind === "green") return base + " bg-[linear-gradient(145deg,rgba(245,251,248,0.94),rgba(205,227,218,0.84))] text-cream-text";
    if (kind === "dark") return base + " bg-[linear-gradient(145deg,rgba(55,61,73,0.96),rgba(31,39,51,0.94))] text-white border-transparent";
    return base + " bg-[linear-gradient(145deg,rgba(255,255,255,0.86),rgba(239,243,248,0.58))] text-cream-text";
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
      <div className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-xl max-h-[80vh] overflow-auto rounded-t-[34px] border border-white/78 bg-[linear-gradient(160deg,rgba(255,255,255,0.88),rgba(243,244,246,0.72))] p-4 shadow-[0_-8px_22px_rgba(196,201,209,0.14)] backdrop-blur-2xl safe-bottom">
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

