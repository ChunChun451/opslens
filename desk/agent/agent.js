import {
  $, api, signedIn, logout, initials, esc, agentPill, ticketTable, ticketDetail, toast, onFloorChange,
  CATEGORY, TEAM, prio,
} from "/desk/desk.js";

const VIEWS = [
  { key: "mine", label: "My open tickets", empty: "Nothing assigned to you right now. OpsLens hands you the next ticket when one fits you." },
  { key: "unassigned", label: "Team queue", empty: "Your team's queue is empty." },
  { key: "due_soon", label: "Due in 15 minutes", empty: "Nothing is close to its promise time." },
  { key: "my_solved", label: "Solved by me today", empty: "You have not solved anything yet today." },
];
const DECLINE_REASONS = ["I don't speak this language", "I don't know this topic", "I'm finishing something else"];

const state = { user: null, view: "mine", ticket: null, lists: {}, me: null };

function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  state.view = VIEWS.some(v => v.key === h.get("view")) ? h.get("view") : "mine";
  state.ticket = h.get("t");
}

function go(view, ticket) {
  const h = new URLSearchParams({ view });
  if (ticket) h.set("t", ticket);
  location.hash = h.toString();
}

async function loadLists() {
  const team = state.user.team;
  const results = await Promise.all(VIEWS.map(v =>
    api(`/api/v2/tickets?view=${v.key}${v.key === "unassigned" || v.key === "due_soon" ? `&team=${team}` : ""}&limit=200`)
      .then(r => r.tickets).catch(() => [])));
  VIEWS.forEach((v, i) => { state.lists[v.key] = results[i]; });
}

async function loadMe() {
  try { state.me = (await api("/api/v2/floor/me")).me; } catch { state.me = null; }
}

function renderViews() {
  $("#views").innerHTML = `<h3>Views</h3>` + VIEWS.map(v => `
    <button data-view="${v.key}" class="${v.key === state.view && !state.ticket ? "on" : ""}">
      <span>${esc(v.label)}</span><span class="count">${(state.lists[v.key] || []).length}</span></button>`).join("");
  $("#views").querySelectorAll("button").forEach(b => b.onclick = () => go(b.dataset.view));
}

function renderMe() {
  const me = state.me;
  $("#mystatus").innerHTML = me ? agentPill(me.status) : "";
  const breakBtn = $("#breakbtn");
  breakBtn.hidden = !me || me.status === "off";
  if (me) {
    const onBreak = me.status === "break";
    breakBtn.textContent = onBreak ? "I'm back" : "Take a break";
    breakBtn.onclick = () => act(onBreak ? "back" : "break");
  }
  const box = $("#now");
  if (!me || me.status === "off") {
    box.hidden = false;
    box.innerHTML = `<div><div class="big">You are off shift</div><div class="muted">OpsLens will not give you tickets until your shift starts.</div></div>`;
    return;
  }
  box.hidden = false;
  const cur = me.current;
  const next = me.next;
  const line = j => `${prio(j.priority)} <b>${esc(CATEGORY[j.category] || j.category)}</b> · ${esc(j.ticket_id)} · ${j.minutes_left < 0 ? `<span class="due late">${Math.round(-j.minutes_left)} min late</span>` : `<span class="${j.minutes_left <= 10 ? "due soon" : ""}">${Math.round(j.minutes_left)} min left</span>`}`;
  const left = cur
    ? `<div class="muted" style="font-size:12px">You are working on</div><div class="big">${line(cur)}</div>`
    : me.status === "break" ? `<div class="big">You are on a break</div><div class="muted">Press “I'm back” when you are ready for tickets again.</div>`
    : `<div class="big">You are free</div><div class="muted">OpsLens gives you the next ticket that fits your skills and languages.</div>`;
  const upNext = next ? `<div class="muted" style="margin-top:6px;font-size:13px">Up next: ${line(next)}</div>` : "";
  const buttons = cur
    ? `<button class="btn" data-open="${esc(cur.ticket_id)}">Open</button>
       <button class="btn" data-act="extra_time">Need 10 more min</button>
       <button class="btn primary" data-act="done">Mark solved</button>`
    : next ? `<button class="btn" data-open="${esc(next.ticket_id)}">Open next</button>` : "";
  box.innerHTML = `<div>${left}${upNext}<div class="muted" style="font-size:12px;margin-top:6px">Today: ${me.done} solved, ${me.kept} on time</div></div><div style="display:flex;gap:8px;flex-wrap:wrap">${buttons}</div>`;
  box.querySelectorAll("[data-open]").forEach(b => b.onclick = () => go(state.view, b.dataset.open));
  box.querySelectorAll("[data-act]").forEach(b => b.onclick = () => act(b.dataset.act, { value: b.dataset.act === "extra_time" ? 10 : undefined }));
}

function actionsFor(t) {
  const me = state.me;
  if (!me) return "";
  if (me.current && me.current.ticket_id === t.id) {
    return `<button class="btn primary" data-act="done">Mark solved</button><button class="btn" data-act="extra_time" data-value="10">Need 10 more min</button>`;
  }
  if (me.next && me.next.ticket_id === t.id) {
    return `<span class="muted">This is lined up for you next.</span>
      <select class="field" id="why">${DECLINE_REASONS.map(r => `<option>${esc(r)}</option>`).join("")}</select>
      <button class="btn danger" data-act="decline">I can't take this</button>`;
  }
  if (t.status === "open" && t.team === state.user.team && me.status !== "off" && me.status !== "break") {
    return `<button class="btn primary" data-act="take">Take this ticket</button>`;
  }
  return "";
}

async function renderTicket(id) {
  const content = $("#content");
  let data;
  try { data = await api(`/api/v2/tickets/${encodeURIComponent(id)}`); }
  catch (e) { content.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  content.innerHTML = `<div style="padding:10px 16px;border-bottom:1px solid var(--line);background:var(--panel)"><button class="btn small ghost" id="back">← Back to ${esc(VIEWS.find(v => v.key === state.view).label)}</button></div>`
    + ticketDetail(data, { user: state.user, extraActions: actionsFor(data.ticket) });
  $("#back").onclick = () => go(state.view);
  content.querySelectorAll("[data-act]").forEach(b => b.onclick = () => act(b.dataset.act, {
    ticket_id: id, value: b.dataset.value ? Number(b.dataset.value) : undefined,
    reason: b.dataset.act === "decline" ? $("#why")?.value : undefined,
  }));
}

function renderList() {
  const v = VIEWS.find(x => x.key === state.view);
  const list = state.lists[v.key] || [];
  $("#content").innerHTML = `<div style="padding:14px 16px;display:flex;justify-content:space-between;align-items:center;background:var(--panel);border-bottom:1px solid var(--line)">
      <h2>${esc(v.label)}</h2><span class="muted num">${list.length} ticket${list.length === 1 ? "" : "s"}</span></div>`
    + ticketTable(list, { showAssignee: v.key !== "mine" && v.key !== "my_solved", emptyText: v.empty });
  $("#content").querySelectorAll("tr.row").forEach(r => r.onclick = () => go(state.view, r.dataset.id));
}

async function render() {
  readHash();
  renderViews();
  renderMe();
  if (state.ticket) await renderTicket(state.ticket);
  else renderList();
}

async function refresh(redrawTicket = false) {
  await Promise.all([loadLists(), loadMe()]);
  if (redrawTicket || !state.ticket) await render();
  else { renderViews(); renderMe(); }
}

async function act(kind, extra = {}) {
  const body = { kind };
  for (const [k, v] of Object.entries(extra)) if (v !== undefined && v !== null && v !== "") body[k] = v;
  document.querySelectorAll("[data-act], #breakbtn").forEach(b => { b.disabled = true; });
  try {
    await api("/api/v2/actions", { body });
    toast({ done: "Marked solved.", extra_time: "10 more minutes added.", take: "The ticket is yours.", decline: "Passed back. OpsLens is finding someone else.", break: "Enjoy your break.", back: "Welcome back." }[kind]);
    setTimeout(() => refresh(true), 1500);
    setTimeout(() => refresh(true), 6000);
    await refresh(true);
  } catch (e) {
    toast(e.message, true);
    await render();
  }
}

state.user = await signedIn(["agent"]);
$("#avatar").textContent = initials(state.user.name);
$("#myname").textContent = state.user.name;
$("#myteam").textContent = `${TEAM[state.user.team] || state.user.team} · ${state.user.agent_code}`;
$("#logout").onclick = logout;
window.addEventListener("hashchange", render);
await refresh(true);
onFloorChange(() => refresh());
