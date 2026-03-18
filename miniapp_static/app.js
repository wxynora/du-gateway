const tg = window.Telegram?.WebApp;
if (tg) {
  try {
    tg.ready();
    // 默认不 expand：让 Telegram WebView 以“半屏面板”形式打开
  } catch {}
}

const state = {
  tab: "logs", // logs | windows(思维链)
  initData: tg?.initData || "",
  logPaused: false,
  logLines: [],
  logFilter: "",
  status: null,
  windows: [],
  rounds: [],
  coreCache: null,
  notebook: null,
  upstreams: null,
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

async function loadUpstreams() {
  const r = await apiFetch("/miniapp-api/upstreams");
  const j = await r.json();
  if (!r.ok) throw new Error(j?.message || j?.error || `HTTP ${r.status}`);
  return j;
}

function showUpstreamsModal() {
  // 简化版：直接加载一次并渲染；切换后重新加载即可
  loadUpstreams()
    .then((j) => {
      const overlay = el("div", { class: "fixed inset-0 z-40 bg-black/40" }, []);
      const modal = el(
        "div",
        {
          class:
            "fixed inset-x-0 bottom-0 z-50 max-w-xl mx-auto rounded-t-3xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-4 max-h-[80vh] overflow-auto safe-bottom",
        },
        [],
      );

      const title = el("div", { class: "font-semibold" }, ["上游中转站"]);
      const sub = el(
        "div",
        { class: "mt-1 text-xs text-slate-600 dark:text-slate-300" },
        ["说明：这里切换的是网关的全局默认上游，会影响所有客户端。"],
      );

      const list = el("div", { class: "mt-3 space-y-2" }, []);
      const items = j?.items || [];
      const active = Number(j?.active || 0);

      const closeBtn = el(
        "button",
        {
          class: "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800",
          onclick: () => {
            overlay.remove();
            modal.remove();
          },
        },
        ["关闭"],
      );

      modal.appendChild(el("div", { class: "flex items-center justify-between" }, [title, closeBtn]));
      modal.appendChild(sub);
      modal.appendChild(list);
      document.body.appendChild(overlay);
      document.body.appendChild(modal);

      overlay.addEventListener("click", () => {
        overlay.remove();
        modal.remove();
      });

      items.forEach((it, idx) => {
        const isActive = idx === active;
        const row = el(
          "div",
          {
            class:
              "rounded-xl border border-slate-200 dark:border-slate-800 p-3 " +
              (isActive ? "bg-slate-100 dark:bg-slate-900" : "bg-transparent"),
          },
          [],
        );

        const head = el("div", { class: "flex items-center justify-between gap-2" }, []);
        head.appendChild(el("div", { class: "font-medium text-sm" }, [it.name || `upstream${idx + 1}`]));
        const btn = el(
          "button",
          {
            class: "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800 " + (isActive ? "opacity-50" : ""),
            onclick: async () => {
              if (isActive) return;
              try {
                const rr = await apiFetch("/miniapp-api/upstreams/active", {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ active: idx }),
                });
                const jj = await rr.json();
                if (!rr.ok || !jj?.ok) throw new Error(jj?.error || `HTTP ${rr.status}`);
                toast("已切换并生效");
                overlay.remove();
                modal.remove();
              } catch (e) {
                toast(`切换失败：${e.message || e}`);
              }
            },
          },
          [isActive ? "当前" : "切换到此"],
        );
        head.appendChild(btn);
        row.appendChild(head);
        row.appendChild(el("div", { class: "mt-2 text-xs text-slate-600 dark:text-slate-300 break-all" }, [it.url || ""]));
        list.appendChild(row);
      });
    })
    .catch((e) => {
      toast(`加载上游失败：${e.message || e}`);
    });
}

function renderShell() {
  const root = document.getElementById("app");
  root.innerHTML = "";

  const header = el("div", { class: "sticky top-0 z-20 border-b border-slate-200/70 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-950/80 backdrop-blur" }, [
    el("div", { class: "px-4 pt-4 pb-3 flex items-center justify-between" }, [
      el("div", { class: "font-semibold tracking-tight" }, ["渡 · 躺着运维"]),
      el("div", { class: "flex items-center gap-2" }, [
        el(
          "button",
          {
            class:
              "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/60",
            onClick: () => showUpstreamsModal(),
          },
          ["上游"],
        ),
        el(
          "button",
          {
            class:
              "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/60",
            onClick: async () => {
              try {
                // 面板“刷新”只刷新当前 Tab 所需的数据，避免拉取核心缓存/记忆等不在第0版范围内的东西
                if (state.tab === "windows") await loadWindows();
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
        if (id === "windows") {
          loadWindows().then(renderShell).catch((e) => toast(`加载失败：${e.message || e}`));
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
    [el("div", { class: "max-w-xl mx-auto flex px-2" }, [tabBtn("logs", "日志"), tabBtn("windows", "思维链")])],
  );
}

function card(title, bodyEl) {
  return el("div", { class: "rounded-2xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/40 shadow-sm" }, [
    el("div", { class: "px-4 py-3 border-b border-slate-200/70 dark:border-slate-800/70" }, [
      el("div", { class: "text-sm font-semibold" }, [title]),
    ]),
    el("div", { class: "px-4 py-3" }, [bodyEl]),
  ]);
}

function pill(ok, text) {
  return el(
    "span",
    {
      class:
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs border " +
        (ok
          ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-200"
          : "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-900/20 dark:text-rose-200"),
    },
    [text],
  );
}

function renderTabContent(contentRoot) {
  contentRoot.innerHTML = "";
  if (state.tab === "logs") return renderLogs(contentRoot);
  if (state.tab === "windows") return renderWindows(contentRoot);
}

function renderOverview(root) {
  if (!state.status) {
    root.appendChild(el("div", { class: "text-sm text-slate-600 dark:text-slate-300" }, ["加载中…"]));
    return;
  }

  const s = state.status;
  const coreCount = s.core_cache?.pending_count ?? "-";
  root.appendChild(
    card(
      "一眼状态",
      el("div", { class: "grid grid-cols-2 gap-3" }, [
        el("div", { class: "rounded-xl border border-slate-200 dark:border-slate-800 p-3" }, [
          el("div", { class: "text-xs text-slate-500 dark:text-slate-400" }, ["核心缓存待审"]),
          el("div", { class: "text-2xl font-semibold mt-1" }, [String(coreCount)]),
        ]),
        el("div", { class: "rounded-xl border border-slate-200 dark:border-slate-800 p-3" }, [
          el("div", { class: "text-xs text-slate-500 dark:text-slate-400" }, ["动态记忆条数"]),
          el("div", { class: "text-2xl font-semibold mt-1" }, [String(s.dynamic_memory?.count ?? "-")]),
        ]),
        el("div", { class: "rounded-xl border border-slate-200 dark:border-slate-800 p-3" }, [
          el("div", { class: "text-xs text-slate-500 dark:text-slate-400" }, ["小本本条数"]),
          el("div", { class: "text-2xl font-semibold mt-1" }, [String(s.notebook?.count ?? "-")]),
        ]),
        el("div", { class: "rounded-xl border border-slate-200 dark:border-slate-800 p-3" }, [
          el("div", { class: "text-xs text-slate-500 dark:text-slate-400" }, ["R2"]),
          el("div", { class: "mt-2" }, [pill(!!s.r2?.ok, s.r2?.ok ? "可读" : "异常")]),
        ]),
      ]),
    ),
  );
}

let logEs = null;
function renderLogs(root) {
  const keyword = (state.logFilter || "").trim().toLowerCase();
  const visibleLines = keyword
    ? (state.logLines || []).filter((l) => (l || "").toLowerCase().includes(keyword))
    : (state.logLines || []);
  const topRow = el("div", { class: "flex items-center gap-2 mb-3" }, [
    el(
      "button",
      {
        class:
          "text-xs px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/60",
        onClick: async () => {
          try {
            const r = await apiFetch("/miniapp-api/logs?lines=200");
            const j = await r.json();
            if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
            state.logLines = j.lines || [];
            toast("已加载最新日志");
            renderShell();
          } catch (e) {
            toast(`加载失败：${e.message || e}`);
          }
        },
      },
      ["拉取末尾 200 行"],
    ),
    el(
      "button",
      {
        class:
          "text-xs px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/60",
        onClick: () => {
          state.logPaused = !state.logPaused;
          toast(state.logPaused ? "已暂停" : "已继续");
          renderShell();
        },
      },
      [state.logPaused ? "继续" : "暂停"],
    ),
    el(
      "button",
      {
        class:
          "text-xs px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/60",
        onClick: () => {
          if (logEs) {
            logEs.close();
            logEs = null;
            toast("已断开实时");
          } else {
            connectLogStream();
            toast("已连接实时");
          }
          renderShell();
        },
      },
      [logEs ? "断开实时" : "连接实时"],
    ),
  ]);
  root.appendChild(topRow);

  const filterRow = el("div", { class: "flex items-center gap-2 mb-3" }, [
    el("input", {
      class: "flex-1 text-sm px-3 py-2 rounded-xl border border-slate-200 bg-white/80",
      placeholder: "过滤关键字（不区分大小写）",
      value: state.logFilter,
      oninput: (e) => {
        state.logFilter = e.target.value || "";
        renderShell();
      },
    }),
    el(
      "button",
      {
        class: "text-xs px-3 py-2 rounded-xl border border-slate-200 bg-white/80",
        onclick: () => {
          state.logFilter = "";
          renderShell();
        },
        disabled: !state.logFilter.trim(),
      },
      ["清空"],
    ),
    el(
      "button",
      {
        class: "text-xs px-3 py-2 rounded-xl border border-slate-200 bg-white/80",
        onclick: async () => {
          const text = (visibleLines || []).slice(-200).join("\n") || "";
          if (!text) {
            toast("暂无可复制内容");
            return;
          }
          try {
            await navigator.clipboard.writeText(text);
            toast("已复制");
          } catch (e) {
            toast("复制失败");
          }
        },
        disabled: visibleLines.length === 0,
      },
      ["一键复制"],
    ),
  ]);
  root.appendChild(filterRow);

  const box = el(
    "div",
    { class: "rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-900 text-slate-100 p-3 text-xs whitespace-pre-wrap font-mono leading-relaxed min-h-[50vh]" },
    [visibleLines.slice(-800).join("\n") || "（暂无日志）"],
  );
  root.appendChild(box);
}

function connectLogStream() {
  if (logEs) return;
  const url = "/miniapp-api/logs/stream?start_lines=80";
  // EventSource 不能自定义 header，所以后端也支持 query initData；这里用 query
  const qs = state.initData ? `&initData=${encodeURIComponent(state.initData)}` : "";
  logEs = new EventSource(url + qs);
  logEs.onmessage = (ev) => {
    if (state.logPaused) return;
    state.logLines.push(ev.data);
    if (state.logLines.length > 2000) state.logLines.splice(0, state.logLines.length - 2000);
    // 轻量刷新：只在日志页时重绘
    if (state.tab === "logs") renderShell();
  };
  logEs.onerror = () => {
    try {
      logEs?.close();
    } catch {}
    logEs = null;
    toast("实时日志断开");
    if (state.tab === "logs") renderShell();
  };
}

function renderMemory(root) {
  const left = el("div", { class: "space-y-3" }, []);

  left.appendChild(
    card(
      "核心缓存（待审）",
      el("div", { class: "text-sm" }, [
        el("div", { class: "text-slate-600 dark:text-slate-300 mb-2" }, [
          `条数：${state.coreCache?.count ?? "-"}`,
        ]),
        el(
          "button",
          {
            class:
              "text-xs px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/60",
            onClick: async () => {
              try {
                await loadCoreCache();
                toast("已刷新核心缓存");
                renderShell();
              } catch (e) {
                toast(`刷新失败：${e.message || e}`);
              }
            },
          },
          ["刷新列表"],
        ),
        el("div", { class: "mt-3 space-y-2" }, [
          ...(state.coreCache?.pending || []).slice().reverse().slice(0, 30).map((it) =>
            el("div", { class: "rounded-xl border border-slate-200 dark:border-slate-800 p-3" }, [
              el("div", { class: "text-xs text-slate-500 dark:text-slate-400" }, [
                `${it.id || ""} · imp=${it.importance ?? ""} · mention=${it.mention_count ?? ""}`,
              ]),
              el("div", { class: "text-sm mt-1 whitespace-pre-wrap" }, [String(it.content || "")]),
              el(
                "button",
                {
                  class: "mt-2 text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800",
                  onClick: async () => {
                    if (!it.id) return;
                    try {
                      const r = await apiFetch(`/miniapp-api/core_cache/${encodeURIComponent(it.id)}`, { method: "DELETE" });
                      const j = await r.json();
                      if (!r.ok || !j.ok) throw new Error(j?.error || `HTTP ${r.status}`);
                      toast("已删除");
                      await loadCoreCache();
                      renderShell();
                    } catch (e) {
                      toast(`删除失败：${e.message || e}`);
                    }
                  },
                },
                ["删除"],
              ),
            ]),
          ),
        ]),
      ]),
    ),
  );

  left.appendChild(
    card(
      "小本本",
      el("div", { class: "text-sm" }, [
        el("div", { class: "text-slate-600 dark:text-slate-300 mb-2" }, [`条数：${state.notebook?.count ?? "-"}`]),
        el("div", { class: "flex gap-2" }, [
          el("input", {
            id: "nb_input",
            class:
              "flex-1 text-sm px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/40",
            placeholder: "新增一条…",
          }),
          el(
            "button",
            {
              class:
                "text-xs px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/60",
              onClick: async () => {
                const inp = document.getElementById("nb_input");
                const content = (inp?.value || "").trim();
                if (!content) return toast("先写点内容");
                try {
                  const r = await apiFetch("/miniapp-api/notebook", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ content }),
                  });
                  const j = await r.json();
                  if (!r.ok || !j.ok) throw new Error(j?.error || `HTTP ${r.status}`);
                  inp.value = "";
                  toast("已写入");
                  await loadNotebook();
                  renderShell();
                } catch (e) {
                  toast(`写入失败：${e.message || e}`);
                }
              },
            },
            ["添加"],
          ),
        ]),
        el("div", { class: "mt-3 space-y-2" }, [
          ...(state.notebook?.entries || []).slice().reverse().slice(0, 30).map((it) =>
            el("div", { class: "rounded-xl border border-slate-200 dark:border-slate-800 p-3" }, [
              el("div", { class: "text-xs text-slate-500 dark:text-slate-400" }, [String(it.timestamp || "")]),
              el("div", { class: "text-sm mt-1 whitespace-pre-wrap" }, [String(it.content || "")]),
              el(
                "button",
                {
                  class: "mt-2 text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800",
                  onClick: async () => {
                    const ts = it.timestamp;
                    if (!ts) return;
                    try {
                      const r = await apiFetch(`/miniapp-api/notebook/${encodeURIComponent(ts)}`, { method: "DELETE" });
                      const j = await r.json();
                      if (!r.ok || !j.ok) throw new Error(j?.error || `HTTP ${r.status}`);
                      toast("已删除");
                      await loadNotebook();
                      renderShell();
                    } catch (e) {
                      toast(`删除失败：${e.message || e}`);
                    }
                  },
                },
                ["删除"],
              ),
            ]),
          ),
        ]),
      ]),
    ),
  );

  root.appendChild(left);
}

function renderWindows(root) {
  if (!state.windows?.length) {
    root.appendChild(el("div", { class: "text-sm text-slate-600 dark:text-slate-300" }, ["暂无窗口（或加载中）"]));
    return;
  }
  root.appendChild(
    card(
      "最近窗口",
      el("div", { class: "space-y-2" }, [
        ...state.windows.slice(0, 60).map((w) =>
          el(
            "button",
            {
              class: "w-full text-left rounded-xl border border-slate-200 dark:border-slate-800 p-3 bg-white/60 dark:bg-slate-900/30",
              onClick: async () => {
                const wid = w.id || "";
                if (!wid) return;
                try {
                  const r = await apiFetch(`/miniapp-api/windows/${encodeURIComponent(wid)}/rounds?preview_chars=80`);
                  const j = await r.json();
                  if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
                  state.rounds = j.rounds || [];
                  showRoundsModal(wid);
                } catch (e) {
                  toast(`加载轮次失败：${e.message || e}`);
                }
              },
            },
            [
              el("div", { class: "text-sm font-medium" }, [w.id || "(no id)"]),
              el("div", { class: "text-xs text-slate-500 dark:text-slate-400 mt-1" }, [
                `${w.whitelisted ? "白名单" : "非白"} · ${w.blacklisted ? "黑名单" : "非黑"} · 最近：${w.last_seen || ""}`,
              ]),
            ],
          ),
        ),
      ]),
    ),
  );
}

function showRoundsModal(windowId) {
  const overlay = el("div", { class: "fixed inset-0 z-40 bg-black/40" }, []);
  const modal = el("div", { class: "fixed inset-x-0 bottom-0 z-50 max-w-xl mx-auto rounded-t-3xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-4 max-h-[75vh] overflow-auto safe-bottom" }, [
    el("div", { class: "flex items-center justify-between" }, [
      el("div", { class: "font-semibold" }, [`轮次 · ${windowId}`]),
      el(
        "button",
        {
          class: "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800",
          onClick: () => {
            overlay.remove();
            modal.remove();
          },
        },
        ["关闭"],
      ),
    ]),
    el("div", { class: "mt-3 space-y-2" }, [
      ...(state.rounds || []).map((r) =>
        el("div", { class: "rounded-xl border border-slate-200 dark:border-slate-800 p-3" }, [
          el("div", { class: "text-xs text-slate-500 dark:text-slate-400" }, [`#${r.index}`]),
          el("div", { class: "text-sm mt-1" }, [String(r.preview || "")]),
          el("div", { class: "mt-2 flex gap-2" }, [
            el(
              "button",
              {
                class: "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800",
                onClick: async () => {
                  const idx = r.index;
                  if (!idx) return;
                  try {
                    const rr = await apiFetch(`/miniapp-api/windows/${encodeURIComponent(windowId)}/rounds/${idx}`);
                    const jj = await rr.json();
                    if (!rr.ok || !jj.ok) throw new Error(jj?.error || `HTTP ${rr.status}`);
                    showRoundDetailModal(windowId, jj.round);
                  } catch (e) {
                    toast(`查看失败：${e.message || e}`);
                  }
                },
              },
              ["查看"],
            ),
            el(
              "button",
              {
                class: "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800",
                onClick: async () => {
                  const idx = r.index;
                  if (!idx) return;
                  try {
                    const r2 = await apiFetch(`/miniapp-api/windows/${encodeURIComponent(windowId)}/rounds/${idx}`, { method: "DELETE" });
                    const j2 = await r2.json();
                    if (!r2.ok || !j2.ok) throw new Error(j2?.error || `HTTP ${r2.status}`);
                    toast("已删除该轮");
                    // 重新拉取
                    const rr = await apiFetch(`/miniapp-api/windows/${encodeURIComponent(windowId)}/rounds?preview_chars=80`);
                    const jj = await rr.json();
                    state.rounds = jj.rounds || [];
                    overlay.remove();
                    modal.remove();
                    showRoundsModal(windowId);
                  } catch (e) {
                    toast(`删除失败：${e.message || e}`);
                  }
                },
              },
              ["删除该轮"],
            ),
          ]),
        ]),
      ),
    ]),
  ]);

  overlay.addEventListener("click", () => {
    overlay.remove();
    modal.remove();
  });
  document.body.appendChild(overlay);
  document.body.appendChild(modal);
}

function showRoundDetailModal(windowId, round) {
  const overlay = el("div", { class: "fixed inset-0 z-40 bg-black/40" }, []);
  const modal = el("div", { class: "fixed inset-x-0 bottom-0 z-50 max-w-xl mx-auto rounded-t-3xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-4 max-h-[80vh] overflow-auto safe-bottom" }, [
    el("div", { class: "flex items-center justify-between" }, [
      el("div", { class: "font-semibold" }, [`原文 · ${windowId} #${round?.index ?? ""}`]),
      el(
        "button",
        {
          class: "text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800",
          onClick: () => {
            overlay.remove();
            modal.remove();
          },
        },
        ["关闭"],
      ),
    ]),
    el("div", { class: "mt-3 space-y-3" }, [
      ...(round?.messages || []).map((m) => {
        const role = (m?.role || "").toLowerCase() || "unknown";
        const content = typeof m?.content === "string" ? m.content : JSON.stringify(m?.content ?? "", null, 2);
        const reasoning = (m?.reasoning || m?.reasoning_content || m?.thinking || "").trim?.() ? (m.reasoning || m.reasoning_content || m.thinking) : "";
        const box = el("div", { class: "rounded-2xl border border-slate-200 dark:border-slate-800 p-3" }, [
          el("div", { class: "text-xs text-slate-500 dark:text-slate-400" }, [role]),
          el("div", { class: "text-sm mt-1 whitespace-pre-wrap" }, [String(content || "")]),
        ]);
        if (reasoning && role === "assistant") {
          const details = el("details", { class: "mt-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/30 p-2" }, [
            el("summary", { class: "cursor-pointer text-xs text-slate-600 dark:text-slate-300 select-none" }, ["思维链（展开/收起）"]),
            el("div", { class: "mt-2 text-xs whitespace-pre-wrap font-mono text-slate-700 dark:text-slate-200" }, [String(reasoning)]),
          ]);
          box.appendChild(details);
        }
        return box;
      }),
    ]),
  ]);

  overlay.addEventListener("click", () => {
    overlay.remove();
    modal.remove();
  });
  document.body.appendChild(overlay);
  document.body.appendChild(modal);
}

async function boot() {
  renderShell();
  renderShell();
}

boot();

