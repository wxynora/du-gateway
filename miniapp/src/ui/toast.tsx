import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

type ToastItem = { id: string; text: string };
type ToastCtx = { toast: (text: string) => void };

const Ctx = createContext<ToastCtx | null>(null);

function uid() {
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((text: string) => {
    const id = uid();
    setItems((prev) => [...prev, { id, text }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((x) => x.id !== id));
    }, 2200);
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="fixed left-1/2 top-3 z-50 -translate-x-1/2 space-y-2">
        {items.map((it) => (
          <div
            key={it.id}
            className="max-w-[92vw] whitespace-pre-wrap rounded-[18px] border border-cream-border bg-cream-card/95 px-3 py-2 text-sm text-cream-text shadow-soft backdrop-blur"
          >
            {it.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("ToastProvider missing");
  return ctx.toast;
}

