import React from "react";

export function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl3 bg-white/45 backdrop-blur-md border border-white/35 shadow-soft">
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
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs shadow-soft2 " +
        (ok
          ? "bg-cream-green/65 text-cream-text"
          : "bg-cream-pink/60 text-cream-text")
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
  kind?: "default" | "danger" | "blue" | "pink" | "green";
  disabled?: boolean;
}) {
  const base =
    "text-xs px-3 py-2 rounded-xl2 bg-cream-card shadow-soft2 disabled:opacity-60 disabled:cursor-not-allowed active:scale-[0.99] transition";
  const cls = (() => {
    if (kind === "danger") return base + " text-cream-danger";
    if (kind === "blue") return base + " bg-cream-blue/75 text-cream-text";
    if (kind === "pink") return base + " bg-cream-pink/70 text-cream-text";
    if (kind === "green") return base + " bg-cream-green/75 text-cream-text";
    return base + " text-cream-text";
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
      <div className="fixed inset-0 z-40 bg-black/22 backdrop-blur-[1px]" onClick={onClose} />
      <div className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-xl max-h-[80vh] overflow-auto rounded-t-[32px] bg-white/70 backdrop-blur-xl border border-white/45 p-4 shadow-soft safe-bottom">
        <div className="flex items-center justify-between">
          <div className="font-semibold text-cream-text">{title}</div>
          <button
            className="text-xs px-2 py-1 rounded-xl2 bg-white/65 border border-white/45 shadow-soft2 active:scale-[0.99] transition"
            onClick={onClose}
          >
            关闭
          </button>
        </div>
        <div className="mt-3">{children}</div>
      </div>
    </>
  );
}

