import React from "react";

export function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl3 border border-cream-border bg-cream-card shadow-soft">
      <div className="border-b border-cream-border/70 px-4 py-3">
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
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs " +
        (ok
          ? "border-cream-border bg-cream-accent/25 text-cream-text"
          : "border-cream-border bg-cream-pink/35 text-cream-text")
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
  kind?: "default" | "danger";
  disabled?: boolean;
}) {
  const base =
    "text-xs px-3 py-2 rounded-xl2 border bg-cream-card shadow-soft2 disabled:opacity-60 disabled:cursor-not-allowed active:scale-[0.99] transition";
  const cls =
    kind === "danger"
      ? base + " border-cream-border text-cream-danger"
      : base + " border-cream-border text-cream-text";
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
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-xl max-h-[80vh] overflow-auto rounded-t-[32px] border border-cream-border bg-cream-card p-4 shadow-soft safe-bottom">
        <div className="flex items-center justify-between">
          <div className="font-semibold text-cream-text">{title}</div>
          <button
            className="text-xs px-2 py-1 rounded-xl2 border border-cream-border bg-cream-card shadow-soft2 active:scale-[0.99] transition"
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

