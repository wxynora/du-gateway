const tg = window.Telegram?.WebApp;
if (tg) {
  try {
    tg.ready();
    // 默认不 expand：让 Telegram WebView 以“半屏面板”形式打开
  } catch {}
}

const state = {
  tab: "overview", // overview | logs | memory | windows
  initData: tg?.initData || "",
  logPaused: false,
  logLines: [],
  status: null,
  windows: [],
  rounds: [],
  coreCache: null,
  notebook: null,
};

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, String(v));
  }
  for (const c of children) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return node;
}

function apiFetch(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (state.initData) headers.set("X-Telegram-Init-Data", state.initData);
  return fetch(path, { ...opts, headers });
}

function toast(msg) {
  const box = el(
    "div",
    { class: "fixed left-1/2 top-3 -translate-x-1/2 z-50 max-w-[92vw] rounded-xl bg-slate-900/90 text-white px-3 py-2 text-sm shadow whitespace-pre-wrap" },
    [msg],
  );
  document.body.appendChild(box);
  setTimeout(() => box.remove(), 2200);
}

async function loadStatus() {
  const r = await apiFetch("/miniapp-api/status");
  const j = await r.json();
  if (!r.ok) throw new Error(j?.message || j?.error || `HTTP ${r.status}`);
  state.status = j;
}

async function loadWindows() {
  const r = await apiFetch("/miniapp-api/windows?limit=60");
  const j = await r.json();
  if (!r.ok) throw new Error(j?.message || j?.error || `HTTP ${r.status}`);
  state.windows = j.windows || [];
}

async function loadCoreCache() {
  const r = await apiFetch("/miniapp-api/core_cache");
  const j = await r.json();
  if (!r.ok) throw new Error(j?.message || j?.error || `HTTP ${r.status}`);
  state.coreCache = j;
}

async function loadNotebook() {
  const r = await apiFetch("/miniapp-api/notebook");
  const j = await r.json();
  if (!r.ok) throw new Error(j?.message || j?.error || `HTTP ${r.status}`);
  state.notebook = j;
}

function renderShell() {
  const root = document.getElementById("app");
  root.innerHTML = "";

  const header = el("div", { class: "sticky top-0 z-20 border-b border-slate-200/70 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-950/80 backdrop-blur" }, [
    el("div", { class: "px-4 pt-4 pb-3 flex items-center justify-between" }, [
      el("div", { class: "font-semibold tracking-tight" }, ["渡 · 躺着运维"]),
      el(
        "button",
        {
          class:
            "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/60",
          onClick: async () => {
            try {
              if (state.tab === "overview") await loadStatus();
              if (state.tab === "windows") await loadWindows();
              if (state.tab === "memory") {
                await Promise.all([loadCoreCache(), loadNotebook()]);
              }
              toast("已刷新");
              renderShell();
            } catch (e) {
              toast(`刷新失败：${e.message || e}`);
            }
          },
        },
        ["刷新"],
      ),
    ]),
  ]);

  const content = el("div", { class: "px-4 py-4 pb-24" }, []);
  const nav = renderBottomNav();

  root.appendChild(header);
  root.appendChild(content);
  root.appendChild(nav);

  renderTabContent(content);
}

function tabBtn(id, label) {
  const active = state.tab === id;
  return el(
    "button",
    {
      class:
        "flex-1 py-2 text-xs font-medium " +
        (active ? "text-slate-900 dark:text-white" : "text-slate-500 dark:text-slate-400"),
      onClick: () => {
        state.tab = id;
        renderShell();
        if (id === "overview") {
          loadStatus().then(renderShell).catch((e) => toast(`加载失败：${e.message || e}`));
        } else if (id === "windows") {
          loadWindows().then(renderShell).catch((e) => toast(`加载失败：${e.message || e}`));
        } else if (id === "memory") {
          Promise.all([loadCoreCache(), loadNotebook()]).then(renderShell).catch((e) => toast(`加载失败：${e.message || e}`));
        }
      },
    },
    [label],
  );
}

function renderBottomNav() {
  return el(
    "div",
    { class: "fixed bottom-0 left-0 right-0 z-30 border-t border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-950/90 backdrop-blur safe-bottom" },
    [el("div", { class: "max-w-xl mx-auto flex px-2" }, [tabBtn("overview", "概览"), tabBtn("logs", "日志"), tabBtn("memory", "记忆"), tabBtn("windows", "窗口")])],
  );
}

function renderTabContent(contentRoot) {
  contentRoot.innerHTML = "";
  if (state.tab === "overview") return contentRoot.appendChild(document.createTextNode("..."));
}

async function boot() {
  renderShell();
  try {
    await loadStatus();
  } catch (e) {
    toast(`鉴权/加载失败：${e.message || e}`);
  }
  renderShell();
}

boot();

