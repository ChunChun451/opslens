import {
  $, $$, api, signedIn, createShell, route, ticketTable, ticketPage, onFloorChange, tickDue, toast, store, esc, icon,
  tag, prio, agentTag, dueText, fmtMin, CATEGORY, TEAM, LANGUAGE,
} from "/desk/desk.js";

const VIEWS = [
  { key: "mine", label: "My open tickets", empty: "Nothing assigned to you right now. OpsLens hands you the next ticket that fits your skills and languages." },
  { key: "unassigned", label: "Team queue", empty: "Your team's queue is empty." },
  { key: "due_soon", label: "Due in 15 minutes", empty: "Nothing is close to its promise time." },
  { key: "my_solved", label: "Solved by me today", empty: "You have not solved anything yet today." },
];
const DECLINE = ["I don't speak this language", "I don't know this topic", "I'm finishing something else"];

const user = await signedIn("agent");
const state = { me: null, counts: {}, lastCurrent: undefined, sort: store(`opslens.sort.${user.id}`) || {} };
const shell = createShell({
  user, homeTitle: "Home",
  nav: [{ key: "home", label: "Home", icon: "home" }, { key: "views", label: "Views", icon: "views" }],
  shortcuts: [{ key: "b", label: "Take a break, or come back", run: () => toggleBreak() }],
});
shell.menuItems = () => {
  const me = state.me;
  const onBreak = me?.status === "break";
  return [{ html: `<span class="dot" style="color:${onBreak ? "#038153" : "var(--new)"}"></span> ${onBreak ? "I'm back" : "Take a break"} <kbd style="margin-left:auto">b</kbd>`,
            disabled: !me || me.status === "off", run: toggleBreak },
          { html: `${icon("team", 16)} Switch agent`, run: async () => { await api("/api/v2/logout", { body: {} }).catch(() => {}); location.href = "/?as=agent"; } }];
};

async function act(kind, extra = {}, message) {
  const body = { kind };
  for (const [k, v] of Object.entries(extra)) if (v !== undefined && v !== null && v !== "") body[k] = v;
  try {
    await api("/api/v2/actions", { body });
    toast(message, "good");
    setTimeout(refresh, 1500);
    setTimeout(refresh, 6000);
    await refresh();
    return true;
  } catch (e) {
    toast(e.message, true);
    return false;
  }
}

function toggleBreak() {
  const me = state.me;
  if (!me || me.status === "off") { toast("You are off shift right now.", true); return; }
  if (me.status === "break") act("back", {}, "Welcome back. OpsLens will hand you tickets again.");
  else act("break", {}, "Enjoy your break. OpsLens stops giving you tickets until you're back.");
}

async function loadMe() {
  try { state.me = (await api("/api/v2/floor/me")).me; } catch { state.me = null; }
  shell.setPresence(state.me?.status);
  const cur = state.me?.current?.ticket_id || null;
  if (state.lastCurrent !== undefined && cur && cur !== state.lastCurrent) {
    toast(`New ticket for you: ${CATEGORY[state.me.current.category] || ""} · ${cur}`, "", { label: "Open", run: () => { location.hash = `#/t/${cur}`; } });
    document.title = `(1) ${document.title.replace(/^\(\d+\) /, "")}`;
  }
  state.lastCurrent = cur;
}

async function loadCounts() {
  state.counts = await api("/api/v2/counts").catch(() => ({}));
  shell.setBadge("views", state.counts.mine || 0);
}

function jobLine(j) {
  const late = j.minutes_left < 0;
  return `${prio(j.priority)} <b>${esc(CATEGORY[j.category] || j.category)}</b> <span class="muted">#${esc(j.ticket_id)}</span>
    <span class="${late ? "due late" : j.minutes_left <= 10 ? "due soon" : ""}">${late ? `${fmtMin(-j.minutes_left)} late` : `${fmtMin(j.minutes_left)} left`}</span>`;
}

function ring(j) {
  if (!j) return "";
  const total = j.promise_min || 30;
  const left = Math.max(0, j.minutes_left);
  const share = Math.min(1, left / total);
  const color = j.minutes_left < 0 ? "var(--red)" : share < 0.33 ? "var(--amber)" : "var(--green)";
  const c = 2 * Math.PI * 22;
  return `<svg class="ring" viewBox="0 0 52 52"><circle cx="26" cy="26" r="22" fill="none" stroke="var(--line-soft)" stroke-width="5"/>
    <circle cx="26" cy="26" r="22" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${c * share} ${c}" transform="rotate(-90 26 26)"/>
    <text x="26" y="30" text-anchor="middle" font-size="12" font-weight="700" fill="var(--ink)">${Math.round(j.minutes_left)}</text></svg>`;
}

function nowCard() {
  const me = state.me;
  if (!me) return `<div class="card now"><div></div><div><div class="big">Today's floor is still starting</div><div class="muted">Give it a few seconds.</div></div></div>`;
  if (me.status === "off") return `<div class="card now"><div></div><div><div class="big">You are off shift</div><div class="muted">OpsLens gives you tickets once your shift starts.</div></div></div>`;
  const cur = me.current, next = me.next;
  const body = cur ? `<div class="small muted">You are working on</div><div class="big">${jobLine(cur)}</div><div class="small muted" style="margin-top:3px">${esc(cur.text || "")}</div>`
    : me.status === "break" ? `<div class="big">You are on a break</div><div class="muted">Press “I'm back” when you are ready for tickets again.</div>`
    : `<div class="big">You are free</div><div class="muted">OpsLens gives you the next ticket that fits your skills and languages.</div>`;
  const upNext = next ? `<div class="small" style="margin-top:8px">Up next: ${jobLine(next)} <a href="#/t/${esc(next.ticket_id)}">Open</a></div>` : "";
  const buttons = cur ? `<a class="btn quiet" href="#/t/${esc(cur.ticket_id)}">Open ticket</a><button class="btn quiet" data-act="extra_time">+10 min</button><a class="btn primary" href="#/t/${esc(cur.ticket_id)}">Reply and solve</a>`
    : me.status === "break" ? `<button class="btn primary" data-act="back">I'm back</button>` : `<button class="btn quiet" data-act="break">Take a break</button>`;
  return `<div class="card now">${ring(cur) || `<div class="avatar big">${esc(user.name.split(" ").map(w => w[0]).join("").slice(0, 2))}</div>`}<div>${body}${upNext}</div><div style="display:flex;gap:8px;flex-wrap:wrap">${buttons}</div></div>`;
}

function wireNow(root) {
  $$("[data-act]", root).forEach(b => b.onclick = () => {
    const k = b.dataset.act;
    if (k === "extra_time") act("extra_time", { value: 10 }, "10 more minutes added. OpsLens re-planned around it.");
    else if (k === "break" || k === "back") toggleBreak();
  });
}

async function home() {
  shell.setTitle("Home");
  const [stats, mine, queue] = await Promise.all([
    api("/api/v2/me/stats").catch(() => ({})),
    api("/api/v2/tickets?view=mine&limit=5").catch(() => ({ tickets: [] })),
    api("/api/v2/tickets?view=unassigned&limit=5").catch(() => ({ tickets: [] })),
  ]);
  const onTime = stats.solved ? Math.round(100 * stats.on_time / stats.solved) : null;
  const first = user.name.split(" ")[0];
  shell.main.innerHTML = `<div class="page stack">
    <div class="page-head"><div><h1>Hi ${esc(first)}</h1><p>${esc(TEAM[user.team] || user.team)} · ${esc(user.agent_code)} · ${state.me ? agentTag(state.me.status) : ""}</p></div></div>
    <div id="now">${nowCard()}</div>
    <div class="tiles">
      <div class="card tile"><div class="label">Solved today</div><div class="value">${stats.solved ?? 0}</div><div class="note">by you</div></div>
      <div class="card tile ${onTime !== null && onTime >= 90 ? "good" : onTime !== null && onTime < 75 ? "bad" : ""}"><div class="label">On time</div><div class="value">${onTime === null ? "—" : `${onTime}%`}</div><div class="note">${stats.on_time ?? 0} kept their promise</div></div>
      <div class="card tile"><div class="label">Average handle time</div><div class="value">${stats.avg_handle_min ?? "—"}<span class="small muted"> min</span></div><div class="note">from pick-up to solved</div></div>
      <a class="card tile link" href="#/views/unassigned" style="color:inherit;text-decoration:none"><div class="label">Team queue</div><div class="value">${state.counts.unassigned ?? 0}</div><div class="note">waiting for an agent</div></a>
    </div>
    <div class="cols even">
      <div class="card"><div class="head"><h2>My open tickets</h2><a href="#/views/mine" class="small">See all</a></div>${ticketTable(mine.tickets, { showAssignee: false, emptyText: VIEWS[0].empty })}</div>
      <div class="card"><div class="head"><h2>Team queue</h2><a href="#/views/unassigned" class="small">See all</a></div>${ticketTable(queue.tickets, { emptyText: VIEWS[1].empty })}</div>
    </div></div>`;
  wireNow(shell.main);
  $$("tr.row", shell.main).forEach(r => r.onclick = () => { location.hash = `#/t/${r.dataset.id}`; });
  shell.listKeys(".main tr.row", r => { location.hash = `#/t/${r.dataset.id}`; });
}

async function views(key) {
  const v = VIEWS.find(x => x.key === key) || VIEWS[0];
  store(`opslens.lastview.${user.id}`, `#/views/${v.key}`);
  shell.setTitle("Views");
  const sort = state.sort[v.key] || "";
  const data = await api(`/api/v2/tickets?view=${v.key}&limit=200${sort ? `&sort=${sort}` : ""}`).catch(() => ({ tickets: [] }));
  shell.main.innerHTML = `<div class="split">
    <div class="side-list"><h3>Views <button class="btn quiet small" id="re" title="Refresh">${icon("refresh", 14)}</button></h3>
      ${VIEWS.map(x => `<button data-view="${x.key}" class="${x.key === v.key ? "on" : ""}"><span>${esc(x.label)}</span><span class="count">${state.counts[x.key] ?? ""}</span></button>`).join("")}</div>
    <div class="listing"><div class="list-head"><h1>${esc(v.label)}</h1><span class="muted num">${data.tickets.length} ticket${data.tickets.length === 1 ? "" : "s"}</span><span class="grow"></span>
      <a class="btn quiet small" href="/api/v2/export.csv?view=${v.key}">${icon("download", 14)} Export</a></div>
      ${ticketTable(data.tickets, { showAssignee: !["mine", "my_solved"].includes(v.key), emptyText: v.empty, sortable: true, sort })}</div></div>`;
  $$("[data-view]").forEach(b => b.onclick = () => { location.hash = `#/views/${b.dataset.view}`; });
  $$("th[data-sort]").forEach(th => th.onclick = () => {
    state.sort[v.key] = state.sort[v.key] === th.dataset.sort ? "" : th.dataset.sort;
    store(`opslens.sort.${user.id}`, state.sort);
    views(v.key);
  });
  $("#re").onclick = async () => { await refresh(); toast("Up to date."); };
  $$("tr.row").forEach(r => r.onclick = () => { location.hash = `#/t/${r.dataset.id}`; });
  shell.listKeys(".listing tr.row", r => { location.hash = `#/t/${r.dataset.id}`; });
}

function ticketContext(t) {
  const me = state.me;
  const mineNow = me?.current?.ticket_id === t.id;
  const lined = me?.next?.ticket_id === t.id;
  const canTake = t.status === "open" && t.team === user.team && me && !["off", "break"].includes(me.status);
  const actions = [
    mineNow ? `<span class="small muted">You are working on this.</span><button class="btn quiet small" data-a="extra">+10 min</button>` : "",
    lined ? `<span class="small muted">Lined up for you next.</span><select class="field" id="why" style="height:28px">${DECLINE.map(r => `<option>${esc(r)}</option>`).join("")}</select><button class="btn danger small" data-a="decline">I can't take this</button>` : "",
    canTake && !lined ? `<span class="small muted">Waiting in your team's queue.</span><button class="btn primary small" data-a="take">Take this ticket</button>` : "",
  ].join("");
  return {
    assignee: `<div class="val">${t.assignee ? `<span class="avatar" style="width:22px;height:22px;font-size:9px">${esc(t.assignee)}</span> ${t.assignee === user.agent_code ? "You" : esc(t.assignee)}` : `<span class="muted">Unassigned</span>`}</div>`,
    actions, canReply: t.assignee === user.agent_code && t.status !== "solved", canNote: true, canSolve: mineNow,
    wire() {
      $$("[data-a]").forEach(b => b.onclick = async () => {
        b.disabled = true;
        const a = b.dataset.a;
        const ok = a === "take" ? await act("take", { ticket_id: t.id }, "The ticket is yours. OpsLens re-planned the floor.")
          : a === "decline" ? await act("decline", { ticket_id: t.id, reason: $("#why")?.value }, "Passed back. OpsLens is finding someone else.")
          : await act("extra_time", { value: 10 }, "10 more minutes added.");
        if (ok) setTimeout(() => render(), 1800);
        else b.disabled = false;
      });
    },
  };
}

async function render() {
  const r = route();
  shell.state.current = null;
  shell.listKeys(null, null);
  shell.state.listKeys = null;
  shell.setNav(r.page === "t" ? "views" : r.page);
  if (r.page === "t") {
    await ticketPage(shell, r.arg, { context: ticketContext, after: () => setTimeout(refresh, 1500) });
  } else if (r.page === "views") {
    await views(r.arg);
  } else {
    await home();
  }
  shell.drawTabs();
  if (!document.hidden) document.title = document.title.replace(/^\(\d+\) /, "");
}

async function refresh() {
  await Promise.all([loadMe(), loadCounts()]);
  const r = route();
  if (r.page === "home") { const n = $("#now"); if (n) { n.innerHTML = nowCard(); wireNow(n); } }
  if (r.page === "views" && !document.activeElement?.closest?.(".listing")) await views(r.arg);
}

window.addEventListener("hashchange", render);
await Promise.all([loadMe(), loadCounts()]);
await render();
onFloorChange(refresh);
tickDue();
