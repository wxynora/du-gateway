declare global {
  interface Window {
    Telegram?: any;
  }
}

export function getTelegramWebApp(): any | null {
  return window.Telegram?.WebApp ?? null;
}

export function getInitData(): string {
  return (getTelegramWebApp()?.initData ?? "") as string;
}

export function tgReady(expand: boolean = false) {
  const tg = getTelegramWebApp();
  if (!tg) return;
  try {
    tg.ready();
    if (expand) {
      // Telegram 在部分机型上首次打开可能仍是半屏，这里做多次拉起兜底。
      const ensureExpanded = () => {
        try {
          tg.expand?.();
        } catch {}
        try {
          tg.requestFullscreen?.();
        } catch {}
      };
      ensureExpanded();
      setTimeout(ensureExpanded, 80);
      setTimeout(ensureExpanded, 260);
      setTimeout(ensureExpanded, 700);
    }
  } catch {}
}

export function applyTelegramThemeToHtmlClass() {
  const tg = getTelegramWebApp();
  const scheme = (tg?.colorScheme ?? "").toString();
  const html = document.documentElement;
  if (scheme === "dark") html.classList.add("dark");
  else html.classList.remove("dark");
}

