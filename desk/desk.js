export const CATEGORY = {
  late_delivery: "Late delivery", missing_item: "Missing item", wrong_item: "Wrong item", refund: "Refund",
  payment_failure: "Payment failed", app_bug: "App problem", account: "Account", restaurant_partner: "Restaurant partner",
};
export const LANGUAGE = { en: "English", hi: "Hindi", other: "Other language" };
export const TEAM = { A: "Live orders", B: "Payments & refunds", C: "Order issues", D: "Account & app" };
export const STATUS = { open: ["N", "New"], in_progress: ["O", "Open"], solved: ["S", "Solved"] };
export const AGENT_STATUS = {
  idle: ["Free", "green"], busy: ["Working", "blue"], cross: ["Helping another team", "ai"], wrong: ["Working", "blue"],
  break: ["On break", "amber"], off: ["Off shift", ""],
};
export const PRIORITY = { P1: "Urgent", P2: "High", P3: "Normal" };
export const AGENT_NAME = { intake: "Intake", copilot: "Reply copilot", analyst: "Floor analyst", ask: "Ask OpsLens" };
export const ICONS = {
  home: '<path d="M3 11.5 12 4l9 7.5M5.5 9.5V20h13V9.5"/>',
  views: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16M9 9v11"/>',
  problems: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5.5M12 16.2v.3"/>',
  plan: '<path d="M8 6h12M8 12h12M8 18h12"/><path d="m3.5 6 1 1 2-2M3.5 12l1 1 2-2M3.5 18l1 1 2-2"/>',
  team: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.3-5.5 6.5-5.5s5.7 1.9 6.5 5.5M16 4.5a3.5 3.5 0 010 7M18 14.8c1.9.8 3 2.6 3.5 5.2"/>',
  analysis: '<path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/>',
  ai: '<path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z"/><path d="M18 15l.9 2.1 2.1.9-2.1.9L18 21l-.9-2.1-2.1-.9 2.1-.9z"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  out: '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/>',
  download: '<path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.5-4.6L4 8m0-4v4h4M4 13a8 8 0 0 0 14.5 4.6L20 16m0 4v-4h-4"/>',
  inbox: '<path d="M4 13h4l2 3h4l2-3h4M5 5h14l1 8v6H4v-6z"/>',
  sparkle: '<path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z"/>',
  keyboard: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h.01M11 10h.01M15 10h.01M7 14h10"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5"/>',
};

export function icon(name, size = 20) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export async function api(path, options = {}) {
  const init = { credentials: "same-origin", ...options };
  if (options.body !== undefined) {
    init.method = options.method || "POST";
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  if (response.status === 401 && location.pathname !== "/") {
    location.href = "/";
    throw new Error("Please sign in again.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || body.detail || `Request failed (${response.status})`);
  return body;
}

export async function signedIn(role) {
  const { user } = await api("/api/v2/me");
  if (user.role !== role) {
    location.href = user.role === "agent" ? "/agent/" : "/admin/";
    throw new Error("wrong screen");
  }
  return user;
}

export async function logout() {
  await api("/api/v2/logout", { body: {} }).catch(() => {});
  location.href = "/";
}

export function initials(name) {
  return String(name || "?").split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

export function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem(key) || "null");
    localStorage.setItem(key, JSON.stringify(value));
  } catch { return null; }
  return value;
}

export function tag(text, color = "") { return `<span class="tag ${color}">${esc(text)}</span>`; }
export function prio(p) { return `<span class="prio ${esc(p)}">${esc(PRIORITY[p] || p)}</span>`; }
export function statusBadge(s) { const [l, w] = STATUS[s] || ["?", s]; return `<span class="st ${esc(s)}" title="${esc(w)}">${l}</span>`; }
export function statusWord(s) { const [, w] = STATUS[s] || ["?", s]; return `<span class="st-word ${esc(s)}">${esc(w)}</span>`; }
export function agentTag(s) { const [t, c] = AGENT_STATUS[s] || [s, ""]; return `<span class="tag ${c}"><span class="dot"></span>${esc(t)}</span>`; }

export function riskCell(risk) {
  if (risk === null || risk === undefined) return `<span class="faint small">—</span>`;
  const pct = Math.round(risk * 100);
  const color = risk >= 0.5 ? "var(--red)" : risk >= 0.25 ? "var(--amber)" : "var(--green)";
  return `<span class="risk" title="${pct}% chance of missing the promise"><span class="meter"><span style="width:${pct}%;background:${color}"></span></span><span class="small num">${pct}%</span></span>`;
}

export function riskTag(risk) {
  if (risk === null || risk === undefined) return tag("Not scored yet");
  const pct = Math.round(risk * 100);
  return tag(`${risk >= 0.5 ? "High" : risk >= 0.25 ? "Medium" : "Low"} · ${pct}%`, risk >= 0.5 ? "red" : risk >= 0.25 ? "amber" : "green");
}

export const minutesUntil = iso => (new Date(iso) - Date.now()) / 60000;

export function dueText(t) {
  if (t.status === "solved") return t.breached ? `<span class="due late">Missed</span>` : `<span class="muted">Kept</span>`;
  const m = minutesUntil(t.sla_due_at);
  if (m < 0) return `<span class="due late num" data-due="${esc(t.sla_due_at)}">${fmtMin(-m)} late</span>`;
  return `<span class="due ${m <= 10 ? "soon" : ""} num" data-due="${esc(t.sla_due_at)}">${m < 1 ? "<1 min" : fmtMin(m)} left</span>`;
}

export function fmtMin(m) {
  m = Math.round(m);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export const clock = iso => iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";

export function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.floor(m / 60)} h ago`;
  return new Date(iso).toLocaleDateString();
}

export function subject(t) {
  const body = String(t.subject || t.body || "").trim();
  return body.length > 90 ? body.slice(0, 88) + "…" : body || "(no message)";
}

export function signed(n, digits = 0) {
  const v = Number(n);
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
}

export function toast(message, kind = "", action = null) {
  let box = $(".toasts");
  if (!box) { box = document.createElement("div"); box.className = "toasts"; document.body.append(box); }
  const el = document.createElement("div");
  el.className = `toast ${kind === true ? "bad" : kind}`;
  el.innerHTML = `<span>${esc(message)}</span>`;
  if (action) {
    const b = document.createElement("button");
    b.textContent = action.label;
    b.onclick = () => { action.run(); el.remove(); };
    el.append(b);
  }
  box.append(el);
  setTimeout(() => el.remove(), action ? 8000 : 4200);
}

export function dialog(title, html) {
  const o = document.createElement("div");
  o.className = "overlay";
  o.innerHTML = `<div class="dialog" role="dialog" aria-label="${esc(title)}"><div class="head"><h2>${esc(title)}</h2>
    <button class="btn quiet small" data-close>${icon("x", 14)}</button></div><div class="body">${html}</div></div>`;
  o.addEventListener("click", e => { if (e.target === o || e.target.closest("[data-close]")) o.remove(); });
  document.body.append(o);
  return o;
}

export function typing(e) {
  const t = e.target;
  return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
}

export function onFloorChange(refresh, everyMs = 15000) {
  let pending;
  const soon = () => { clearTimeout(pending); pending = setTimeout(refresh, 500); };
  try { new EventSource("/api/v2/stream").addEventListener("floor", soon); } catch { }
  setInterval(() => { if (!document.hidden) refresh(); }, everyMs);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) soon(); });
}

export function tickDue() {
  setInterval(() => {
    $$("[data-due]").forEach(el => {
      const m = minutesUntil(el.dataset.due);
      el.textContent = m < 0 ? `${fmtMin(-m)} late` : `${m < 1 ? "<1 min" : fmtMin(m)} left`;
      el.className = `due ${m < 0 ? "late" : m <= 10 ? "soon" : ""} num`;
    });
  }, 20000);
}

export function createShell({ user, nav, homeTitle, shortcuts = [] }) {
  const tabsKey = `opslens.tabs.${user.id}`;
  const state = { tabs: store(tabsKey) || [], selected: -1, listKeys: null, title: homeTitle, current: null };
  document.body.innerHTML = `
    <div class="shell">
      <nav class="nav" aria-label="Main">
        <img class="logo" src="/app/favicon.svg" alt="OpsLens">
        ${nav.filter(n => !n.bottom).map(n => `<a href="#/${n.key}" data-nav="${n.key}" data-tip="${esc(n.label)}" aria-label="${esc(n.label)}">${icon(n.icon, 22)}<span class="badge" data-badge="${n.key}" hidden></span></a>`).join("")}
        <div class="spacer"></div>
        ${nav.filter(n => n.bottom).map(n => `<a href="#/${n.key}" data-nav="${n.key}" data-tip="${esc(n.label)}" aria-label="${esc(n.label)}">${icon(n.icon, 22)}</a>`).join("")}
      </nav>
      <header class="top">
        <div class="title" id="title"></div>
        <div class="tabs" id="tabs" role="tablist"></div>
        <div class="right">
          <div class="search"><span>${icon("search", 16)}</span><input id="q" placeholder="Search tickets" autocomplete="off" aria-label="Search tickets"><kbd>/</kbd><div class="results" id="qres" hidden></div></div>
          <button class="me" id="me" aria-label="Your profile"><span class="avatar">${esc(initials(user.name))}<span class="pres" id="pres"></span></span></button>
        </div>
      </header>
      <main class="main" id="main"></main>
    </div>`;

  const tip = document.createElement("div");
  tip.className = "tip";
  tip.hidden = true;
  document.body.append(tip);
  $$("[data-tip]").forEach(a => {
    a.addEventListener("mouseenter", () => {
      const r = a.getBoundingClientRect();
      tip.textContent = a.dataset.tip;
      tip.hidden = false;
      tip.style.left = `${r.right + 10}px`;
      tip.style.top = `${r.top + r.height / 2 - 12}px`;
    });
    a.addEventListener("mouseleave", () => { tip.hidden = true; });
  });

  const shell = {
    user, main: $("#main"), state,
    setTitle(t) { state.title = t; $("#title").textContent = t; document.title = `${t} · OpsLens`; },
    setNav(key) { $$("[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === key)); },
    setBadge(key, n) { const b = $(`[data-badge="${key}"]`); if (b) { b.hidden = !n; b.textContent = n > 99 ? "99+" : n; } },
    setPresence(status) { $("#pres").className = `pres ${status || ""}`; },
    openTab(t) {
      const i = state.tabs.findIndex(x => x.id === t.id);
      const entry = { id: t.id, label: `${CATEGORY[t.category] || t.category || ""} · ${t.id}`, status: t.status };
      if (i >= 0) state.tabs[i] = entry;
      else state.tabs = [entry, ...state.tabs].slice(0, 8);
      store(tabsKey, state.tabs);
      shell.drawTabs();
    },
    closeTab(id) {
      state.tabs = state.tabs.filter(x => x.id !== id);
      store(tabsKey, state.tabs);
      shell.drawTabs();
    },
    drawTabs() {
      $("#tabs").innerHTML = state.tabs.map(t => `<div class="tab ${state.current === t.id ? "on" : ""}" role="tab" data-tab="${esc(t.id)}">
        ${statusBadge(t.status)}<span class="t">${esc(t.label)}</span><button class="x" data-closetab="${esc(t.id)}" aria-label="Close tab">${icon("x", 12)}</button></div>`).join("");
    },
    listKeys(rowsSel, open) { state.listKeys = { rowsSel, open }; state.selected = -1; },
    back: () => history.length > 1 ? history.back() : (location.hash = "#/home"),
  };

  $("#tabs").addEventListener("click", e => {
    const close = e.target.closest("[data-closetab]");
    if (close) {
      e.stopPropagation();
      const id = close.dataset.closetab;
      shell.closeTab(id);
      if (state.current === id) location.hash = store(`opslens.lastview.${user.id}`) || "#/home";
      return;
    }
    const tab = e.target.closest("[data-tab]");
    if (tab) location.hash = `#/t/${tab.dataset.tab}`;
  });

  let searchTimer, hits = [], hit = -1;
  const q = $("#q"), qres = $("#qres");
  const drawHits = () => {
    qres.hidden = !q.value.trim();
    qres.innerHTML = hits.length ? hits.map((r, i) => `<a href="#/t/${esc(r.id)}" class="${i === hit ? "on" : ""}">${statusBadge(r.status)}
      <span><b>${esc(r.id)}</b> <span class="muted">${esc(CATEGORY[r.category] || r.category || "")}</span><div class="small muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.subject)}</div></span>
      <span class="small faint">${ago(r.created_at)}</span></a>`).join("") : `<div class="empty" style="padding:18px">No tickets match “${esc(q.value.trim())}”</div>`;
  };
  q.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      if (q.value.trim().length < 2) { hits = []; qres.hidden = true; return; }
      hits = (await api(`/api/v2/search?q=${encodeURIComponent(q.value.trim())}`).catch(() => ({ results: [] }))).results;
      hit = hits.length ? 0 : -1;
      drawHits();
    }, 180);
  });
  q.addEventListener("keydown", e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); hit = Math.max(0, Math.min(hits.length - 1, hit + (e.key === "ArrowDown" ? 1 : -1))); drawHits(); }
    if (e.key === "Enter" && hits[hit]) { location.hash = `#/t/${hits[hit].id}`; q.value = ""; qres.hidden = true; q.blur(); }
    if (e.key === "Escape") { q.value = ""; qres.hidden = true; q.blur(); }
  });
  q.addEventListener("blur", () => setTimeout(() => { qres.hidden = true; }, 150));
  qres.addEventListener("click", () => { q.value = ""; qres.hidden = true; });

  $("#me").addEventListener("click", e => {
    e.stopPropagation();
    const old = $(".menu.profile");
    if (old) { old.remove(); return; }
    const r = $("#me").getBoundingClientRect();
    const m = document.createElement("div");
    m.className = "menu profile";
    m.style.right = `${innerWidth - r.right}px`;
    m.style.top = `${r.bottom + 6}px`;
    m.innerHTML = `<div class="head"><b>${esc(user.name)}</b><div class="small muted">${esc(user.email)}</div>
      <div class="small muted">${user.role === "admin" ? "Admin · all teams" : `${esc(TEAM[user.team] || user.team)} · ${esc(user.agent_code)}`}</div></div>
      ${(shell.menuItems ? shell.menuItems() : []).map((it, i) => `<button data-mi="${i}" ${it.disabled ? "disabled" : ""}>${it.html}</button>`).join("")}
      <button data-keys>${icon("keyboard", 16)} Keyboard shortcuts <kbd style="margin-left:auto">?</kbd></button>
      <hr><button data-out>${icon("out", 16)} Sign out</button>`;
    document.body.append(m);
    m.addEventListener("click", ev => {
      const b = ev.target.closest("button");
      if (!b) return;
      if (b.dataset.out !== undefined) logout();
      if (b.dataset.keys !== undefined) showKeys();
      if (b.dataset.mi !== undefined) shell.menuItems()[+b.dataset.mi].run();
      m.remove();
    });
  });
  document.addEventListener("click", e => { if (!e.target.closest(".menu")) $$(".menu").forEach(m => m.remove()); });

  const showKeys = () => dialog("Keyboard shortcuts", `<div class="keys">
    <span><kbd>/</kbd></span><span>Search tickets</span>
    <span><kbd>j</kbd> <kbd>k</kbd></span><span>Move down and up a list</span>
    <span><kbd>Enter</kbd></span><span>Open the selected ticket</span>
    <span><kbd>Esc</kbd></span><span>Close the ticket and go back</span>
    <span><kbd>g</kbd> then <kbd>h</kbd></span><span>Home</span>
    <span><kbd>g</kbd> then <kbd>v</kbd></span><span>Ticket views</span>
    ${shortcuts.map(s => `<span><kbd>${esc(s.key)}</kbd></span><span>${esc(s.label)}</span>`).join("")}
    <span><kbd>?</kbd></span><span>This list</span></div>`);

  let lastG = 0;
  document.addEventListener("keydown", e => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (typing(e)) {
      if (e.key === "Escape") e.target.blur();
      return;
    }
    if ($(".overlay")) { if (e.key === "Escape") $(".overlay").remove(); return; }
    if (e.key === "/") { e.preventDefault(); q.focus(); return; }
    if (e.key === "?") { showKeys(); return; }
    if (e.key === "g") { lastG = Date.now(); return; }
    if (Date.now() - lastG < 900) {
      if (e.key === "h") location.hash = "#/home";
      if (e.key === "v") location.hash = "#/views";
      lastG = 0;
      return;
    }
    const custom = shortcuts.find(s => s.key === e.key);
    if (custom) { custom.run(); return; }
    if (e.key === "Escape" && state.current) {
      const id = state.current;
      shell.closeTab(id);
      location.hash = store(`opslens.lastview.${user.id}`) || "#/home";
      return;
    }
    const lk = state.listKeys;
    if (!lk) return;
    const list = $$(lk.rowsSel);
    if (!list.length) return;
    if (e.key === "j" || e.key === "k") {
      state.selected = Math.max(0, Math.min(list.length - 1, state.selected + (e.key === "j" ? 1 : -1)));
      list.forEach((r, i) => r.classList.toggle("sel", i === state.selected));
      list[state.selected].scrollIntoView({ block: "nearest" });
    }
    if ((e.key === "Enter" || e.key === "o") && state.selected >= 0) lk.open(list[state.selected]);
  });

  shell.drawTabs();
  return shell;
}

export function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  return { page: parts[0] || "home", arg: parts[1] || "", rest: parts.slice(2) };
}

export function ticketTable(tickets, { showAssignee = true, emptyText = "Nothing here right now.", sort = "", sortable = false } = {}) {
  if (!tickets.length) return `<div class="empty">${icon("inbox", 44)}${esc(emptyText)}</div>`;
  const th = (key, label, cls = "") => sortable
    ? `<th class="sort ${cls}" data-sort="${key}">${label}${sort === key ? `<span class="arrow">▾</span>` : ""}</th>` : `<th class="${cls}">${label}</th>`;
  const rows = tickets.map(t => `
    <tr class="row" data-id="${esc(t.id)}" tabindex="-1">
      <td style="width:34px">${statusBadge(t.status)}</td>
      <td><div class="subject">${esc(subject(t))}</div><div class="sub">#${esc(t.id)} · ${esc(CATEGORY[t.category] || t.category || "")}${t.ai_category && t.ai_category !== t.category ? ` · <span style="color:var(--ai)">AI reads ${esc(CATEGORY[t.ai_category] || t.ai_category)}</span>` : ""}</div></td>
      <td class="hide-sm nowrap"><span class="small">${esc(t.channel || "")}</span>${t.customer_tier && t.customer_tier !== "normal" ? ` ${tag(t.customer_tier, "blue")}` : ""}<div class="sub">${esc(LANGUAGE[t.language] || t.language || "")}</div></td>
      <td class="hide-sm nowrap small muted">${ago(t.created_at)}</td>
      <td class="nowrap">${prio(t.priority)}</td>
      ${showAssignee ? `<td class="hide-sm nowrap">${t.assignee ? esc(t.assignee) : `<span class="faint">—</span>`}</td>` : ""}
      <td class="nowrap">${dueText(t)}</td>
      <td class="hide-sm">${t.status === "solved" ? "" : riskCell(t.risk)}</td>
    </tr>`).join("");
  return `<table class="grid"><thead><tr><th></th><th>Subject</th><th class="hide-sm">Channel</th>${th("newest", "Requested", "hide-sm")}
    ${th("priority", "Priority")}${showAssignee ? `<th class="hide-sm">Assignee</th>` : ""}${th("due", "Promise")}${th("risk", "Chance of missing", "hide-sm")}</tr></thead><tbody>${rows}</tbody></table>`;
}

export function stepText(step) {
  const words = {
    read_ticket: "Read the ticket", search_policies: "Searched the policies", similar_tickets: "Looked for similar solved tickets",
    review_against_policy: "Checked the draft against the policy", embed: "Stored the message's meaning for search",
    floor_summary: "Read today's numbers", at_risk: "Listed tickets likely to miss", people_now: "Counted who is working",
    free_agents: "Found who is free", category_mix: "Compared categories with usual", tickets_per_hour: "Read tickets per hour",
    check_proposals: "Dropped actions that failed checks", check_numbers: "Checked every number against the data",
  };
  const tool = words[step.tool] || step.tool || "";
  if (step.kind === "tool_call") return tool;
  if (step.kind === "tool_result") {
    const p = step.payload;
    if (Array.isArray(p)) return `${tool}: ${p.length} found`;
    if (p && p.unsupported) return `${tool}: ${p.unsupported.length ? `${p.unsupported.length} claim(s) not backed by policy` : "every claim backed"}`;
    return `${tool}: done`;
  }
  if (step.kind === "answer") return "Wrote the answer";
  if (step.kind === "error") return `${tool || "Step"} refused: ${JSON.stringify(step.payload).slice(0, 110)}`;
  return step.kind;
}

export const seconds = run => run.finished_at ? `${((new Date(run.finished_at) - new Date(run.started_at)) / 1000).toFixed(1)} s` : "";

export function traceList(steps) {
  const shown = steps.filter(s => s.kind !== "tool_call");
  return `<ol class="trace">${shown.map(s => `<li class="${s.kind}">${esc(stepText(s))}</li>`).join("") || `<li>Starting on the local model…</li>`}</ol>`;
}

export async function runAgent(path, body, onProgress) {
  const { run_id } = await api(path, { body });
  for (let i = 0; i < 300; i++) {
    const data = await api(`/api/v2/runs/${run_id}`);
    onProgress(data);
    if (data.run.status !== "running") return data;
    await new Promise(r => setTimeout(r, 700));
  }
  throw new Error("The local model is taking too long. Is Ollama running?");
}

export function eventText(e) {
  if (e.kind === "created") return "Customer wrote in";
  if (e.kind === "assigned") return `Given to ${e.actor || "an agent"}`;
  if (e.kind === "solved") return `Solved by ${e.actor || "the agent"}`;
  if (e.kind === "breached") return "Promise time passed";
  return e.kind;
}

export async function ticketPage(shell, id, opts) {
  const main = shell.main;
  main.innerHTML = `<div class="page"><div class="skeleton" style="width:40%;height:22px"></div><div class="skeleton" style="width:70%;margin-top:14px"></div></div>`;
  let data;
  try { data = await api(`/api/v2/tickets/${encodeURIComponent(id)}`); }
  catch (e) {
    main.innerHTML = `<div class="empty">${icon("inbox", 44)}${esc(e.message)}<div style="margin-top:12px"><button class="btn quiet" id="gone">Back</button></div></div>`;
    $("#gone").onclick = () => { shell.closeTab(id); shell.back(); };
    return;
  }
  const t = data.ticket;
  shell.state.current = id;
  shell.openTab(t);
  shell.setTitle(`#${t.id}`);
  const reasons = Array.isArray(t.risk_reasons) ? t.risk_reasons : [];
  const decided = data.decisions.at(-1);
  const ctx = await opts.context(t);
  const messages = [
    { kind: "customer", name: `Customer${t.customer_tier && t.customer_tier !== "normal" ? ` · ${t.customer_tier}` : ""}`, at: t.created_at, body: t.body },
    ...(decided ? [{ kind: "system", name: "OpsLens", at: decided.at, body: `Assigned to ${decided.agent_code}. ${decided.reason}` }] : []),
    ...data.messages.map(m => ({ kind: m.kind === "internal" ? "internal" : "reply", name: m.author_name, role: m.author_role, at: m.at, body: m.body })),
  ].sort((a, b) => new Date(a.at) - new Date(b.at));
  const draftKey = `opslens.draft.${shell.user.id}.${id}`;
  const saved = store(draftKey) || { kind: "public", body: "" };

  main.innerHTML = `<div class="ticket">
    <aside class="props">
      <label>Requester</label><div class="val"><span class="avatar cust" style="width:24px;height:24px;font-size:10px">C</span> Customer${t.customer_tier && t.customer_tier !== "normal" ? ` ${tag(t.customer_tier, "blue")}` : ""}</div>
      <label>Assignee</label>${ctx.assignee}
      <label>Team</label><div class="val">${esc(TEAM[t.team] || t.team || "—")}</div>
      <label>Type</label><div class="val">${esc(CATEGORY[t.category] || t.category)}${t.ai_category ? (t.ai_category === t.category ? ` ${tag("AI agrees", "green")}` : ` ${tag(`AI: ${CATEGORY[t.ai_category] || t.ai_category}`, "ai")}`) : ""}</div>
      <label>Priority</label><div class="val">${prio(t.priority)}</div>
      <label>Promise</label><div class="val">${clock(t.sla_due_at)} · ${dueText(t)}</div>
      <label>Channel and language</label><div class="val">${esc(t.channel || "—")} · ${esc(LANGUAGE[t.language] || t.language)}</div>
      ${t.order_value_inr ? `<label>Order value</label><div class="val">Rs ${Math.round(t.order_value_inr).toLocaleString()}</div>` : ""}
      ${t.restaurant ? `<label>Restaurant</label><div class="val">${esc(t.restaurant)}</div>` : ""}
      <label>Tags</label><div class="tags">${[t.ai_urgency === "high" ? tag("urgent", "red") : "", t.breached ? tag("missed promise", "red") : "", t.risk >= 0.5 && t.status !== "solved" ? tag("likely to miss", "amber") : "", tag(t.category), tag(t.channel || "")].join("")}</div>
    </aside>
    <section class="conv">
      <div class="conv-head"><h1 style="font-size:19px">${esc(subject(t))}</h1>
        <div class="meta">${statusWord(t.status)}<span>#${esc(t.id)}</span><span>·</span><span>${ago(t.created_at)} via ${esc(t.channel || "chat")}</span>${t.solved_at ? `<span>·</span><span>solved ${clock(t.solved_at)}</span>` : ""}</div></div>
      <div class="thread" id="thread">${messages.map(m => `
        <div class="msg ${m.kind === "internal" ? "internal" : m.kind === "system" ? "system" : ""}">
          <span class="avatar ${m.kind === "customer" ? "cust" : m.kind === "system" ? "ops" : ""}">${m.kind === "system" ? icon("sparkle", 16) : esc(initials(m.name))}</span>
          <div><div class="who"><b>${esc(m.name)}</b>${m.kind === "internal" ? tag("Internal note", "amber") : m.kind === "system" ? tag("OpsLens", "ai") : ""}<span class="small faint">${clock(m.at)}</span></div>
          <div class="${m.kind === "internal" || m.kind === "system" ? "bubble" : ""}"><div class="text">${esc(m.body)}</div></div></div>
        </div>`).join("")}</div>
      ${ctx.actions ? `<div class="act-bar">${ctx.actions}</div>` : ""}
      ${t.status === "solved" && !ctx.canNote ? "" : `
      <div class="composer ${saved.kind === "internal" ? "internal" : ""}" id="composer">
        <div class="modes">${ctx.canReply ? `<button data-mode="public" class="${saved.kind !== "internal" ? "on" : ""}">Public reply</button>` : ""}
          <button data-mode="internal" class="internal ${saved.kind === "internal" || !ctx.canReply ? "on" : ""}">Internal note</button></div>
        <textarea id="reply" placeholder="${ctx.canReply && saved.kind !== "internal" ? "Write your reply to the customer…" : "Write a note only your team can see…"}">${esc(saved.body)}</textarea>
        <div class="row">
          ${ctx.canReply ? `<button class="btn ai small" id="draft">${icon("sparkle", 14)} Draft with AI</button>` : ""}
          <span class="small faint" id="draftinfo"></span><span class="grow"></span>
          ${ctx.canSolve ? `<div class="btn-group"><button class="btn quiet" id="send">Submit</button><button class="btn primary" id="solve">Submit as Solved</button></div>`
            : `<button class="btn primary" id="send">Submit</button>`}
        </div><div id="draftsteps"></div>
      </div>`}
    </section>
    <aside class="context">
      <div class="box ai"><h3>${icon("sparkle", 14)} OpsLens<span></span></h3>
        ${t.status === "solved" ? `<div class="small">Closed. ${t.breached ? "The promise was missed." : "The promise was kept."}</div>`
          : `<div class="small">Chance of missing the promise</div><div style="margin-top:4px">${riskTag(t.risk)}</div>`}
        ${reasons.length ? `<ul class="reasons">${reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
        ${t.assign_reason ? `<div class="small" style="margin-top:10px"><b>Why ${esc(t.assignee || decided?.agent_code || "this agent")}:</b> ${esc(t.assign_reason)}</div>` : ""}
      </div>
      ${t.ai_summary ? `<div class="box"><h3>AI read</h3><div class="small">${esc(t.ai_summary)}</div>
        <div style="margin-top:6px">${t.ai_category && t.ai_category !== t.category ? tag(`Reads as ${CATEGORY[t.ai_category] || t.ai_category}, routed as ${CATEGORY[t.category] || t.category}`, "ai") : tag("Category confirmed", "green")} ${t.ai_urgency ? tag(`${t.ai_urgency} urgency`, t.ai_urgency === "high" ? "red" : "") : ""}</div></div>` : ""}
      <div class="box"><h3>Similar solved tickets</h3><div id="similar"><div class="skeleton"></div></div></div>
      <div class="box"><h3>History</h3><ul class="timeline">${data.events.map(e => `<li><span class="faint num">${clock(e.at)}</span><span>${esc(eventText(e))}</span></li>`).join("") || `<li><span></span><span class="muted">No events yet</span></li>`}</ul></div>
    </aside>
  </div>`;

  const thread = $("#thread");
  thread.scrollTop = thread.scrollHeight;
  const composer = $("#composer");
  if (composer) {
    const box = $("#reply");
    let mode = ctx.canReply ? saved.kind : "internal";
    const persist = () => store(draftKey, { kind: mode, body: box.value });
    box.addEventListener("input", persist);
    $$("[data-mode]", composer).forEach(b => b.onclick = () => {
      mode = b.dataset.mode;
      $$("[data-mode]", composer).forEach(x => x.classList.toggle("on", x === b));
      composer.classList.toggle("internal", mode === "internal");
      box.placeholder = mode === "internal" ? "Write a note only your team can see…" : "Write your reply to the customer…";
      persist();
      box.focus();
    });
    const submit = async solve => {
      const body = box.value.trim();
      if (!body) { toast("Write something first.", true); box.focus(); return; }
      $$("button", composer).forEach(b => { b.disabled = true; });
      try {
        await api(`/api/v2/tickets/${encodeURIComponent(id)}/messages`, { body: { kind: mode, body, solve } });
        store(draftKey, null);
        toast(solve ? "Sent and marked solved. OpsLens is lining up your next ticket." : mode === "internal" ? "Note added." : "Reply sent.", "good");
        if (opts.after) opts.after(solve);
        await ticketPage(shell, id, opts);
      } catch (e) {
        toast(e.message, true);
        $$("button", composer).forEach(b => { b.disabled = false; });
      }
    };
    $("#send").onclick = () => submit(false);
    if ($("#solve")) $("#solve").onclick = () => submit(true);
    box.addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(false); } });
    const draft = $("#draft");
    if (draft) draft.onclick = async () => {
      draft.disabled = true;
      draft.innerHTML = `${icon("sparkle", 14)} Drafting…`;
      const steps = $("#draftsteps");
      try {
        const done = await runAgent("/api/v2/copilot", { ticket_id: id }, d => { steps.innerHTML = traceList(d.steps); });
        const o = done.run.output || {};
        if (done.run.status !== "done" || !o.reply) throw new Error(done.run.summary || "No draft this time.");
        mode = "public";
        $$("[data-mode]", composer).forEach(x => x.classList.toggle("on", x.dataset.mode === "public"));
        composer.classList.remove("internal");
        box.value = o.reply;
        persist();
        $("#draftinfo").innerHTML = `Drafted from <b>${esc(o.policy || "policy")}</b> in ${seconds(done.run)}${o.fixed ? ` · ${o.problems.length} unsupported claim(s) removed` : ""}${o.check ? ` · Check: ${esc(o.check)}` : ""}`;
        steps.innerHTML = "";
        box.focus();
      } catch (e) {
        steps.innerHTML = `<div class="small muted" style="margin-top:6px">${esc(e.message)}</div>`;
      }
      draft.disabled = false;
      draft.innerHTML = `${icon("sparkle", 14)} Draft again`;
    };
  }
  if (ctx.wire) ctx.wire(t);
  api(`/api/v2/tickets/${encodeURIComponent(id)}/similar`).then(s => {
    $("#similar").innerHTML = s.similar.length ? s.similar.map(x => `<a href="#/t/${esc(x.ticket_id)}" style="display:block;padding:6px 0;border-bottom:1px solid var(--line-soft);color:inherit;text-decoration:none">
      <div class="small"><b>#${esc(x.ticket_id)}</b> · ${esc(CATEGORY[x.category] || x.category)} ${x.kept_promise ? tag("kept", "green") : tag("missed", "red")}</div>
      <div class="small muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(x.message)}</div></a>`).join("") + `<div class="small faint" style="margin-top:6px">Matched ${esc(s.how)}</div>`
      : `<div class="small muted">None yet.</div>`;
  }).catch(() => { $("#similar").innerHTML = `<div class="small muted">Not available.</div>`; });
}
