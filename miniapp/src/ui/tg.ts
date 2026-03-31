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

export function tgBootstrapEarly() {
  const tg = getTelegramWebApp();
  if (!tg) return;
  try {
    tg.ready?.();
  } catch {}
}

export function tgReady(expand: boolean = false) {
  const tg = getTelegramWebApp();
  if (!tg) return;
  try {
    tg.ready();
    if (expand) {
      const ensureExpanded = () => {
        try {
          tg.expand?.();
        } catch {}
        try {
          tg.disableVerticalSwipes?.();
        } catch {}
      };
      requestAnimationFrame(() => {
        ensureExpanded();
        setTimeout(ensureExpanded, 120);
      });
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
