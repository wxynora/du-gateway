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
      // Telegram 在部分机型上会先半屏再稳定，持续多次拉起并在视口变化时补拉，尽量首屏即全屏。
      const ensureExpanded = () => {
        try {
          tg.expand?.();
        } catch {}
        try {
          tg.requestFullscreen?.();
        } catch {}
        try {
          tg.disableVerticalSwipes?.();
        } catch {}
      };
      ensureExpanded();
      setTimeout(ensureExpanded, 80);
      setTimeout(ensureExpanded, 260);
      setTimeout(ensureExpanded, 700);
      setTimeout(ensureExpanded, 1400);
      setTimeout(ensureExpanded, 2600);
      try {
        tg.onEvent?.("viewportChanged", ensureExpanded);
      } catch {}
      try {
        document.addEventListener("visibilitychange", () => {
          if (!document.hidden) ensureExpanded();
        });
      } catch {}
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

