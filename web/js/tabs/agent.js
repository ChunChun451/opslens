import { state, store } from "../data.js";
import { escapeHtml, prettyKey } from "../format.js";
import {
  TEAM_NAMES, LANGUAGE, STATUS_TEXT, clockNow, keepFresh, notReady, minutesLeft, duration, postAction, effectLines, floorEffect,
} from "../floornow.js";
import { avg, itemHtml } from "./feedback.js";

const CANT = ["Not my skill", "Language", "Needs a callback first", "Other"];
const EXTRA = [5, 10, 20];
const FEEDBACK_EVERY_MS = 60000;
const FEEDBACK_SHOWN = 6;
const PLAIN = [
  [/^already past its SLA - served so no customer is left behind$/, () => "Already late: served so no customer is left behind"],
  [/^breach risk ([\d.]+) -> ([\d.]+) if served now$/, (m) => `Chance of missing the promise: ${pct(m[1])} if it waits, ${pct(m[2])} if you take it now`],
  [/^low risk - served in turn \(fairness by waiting time\)$/, () => "Low risk: next in line by waiting time"],
  [/^cross-skill job .* to rescue a ticket in danger$/, () => "Outside your usual skills: a rescue, it may take you longer"],
  [/^rare-skill agent, no rare work is more urgent$/, () => "You have a rare skill, and no rare-skill work is more urgent"],
  [/^no other free agent could take it now$/, () => "No one else free could take it"],
];

let last = null;
let busy = false;
let problem = "";

function pct(text) {
  return `${Math.round(Number(text) * 100)}%`;
}

function whyLines(reason) {
  const parts = String(reason).split(";").map((p) => p.trim()).filter(Boolean);
  const waited = (parts[0] || "").match(/waiting (\d+) min/);
  const lines = parts.slice(1).map((p) => {
    const rule = PLAIN.find(([re]) => re.test(p));
    return rule ? rule[1](p.match(rule[0])) : p;
  });
  if (waited) lines.unshift(`Waiting ${waited[1]} min`);
  return lines;
}

export function render(section) {
  section.innerHTML = `<div id="ag-body"></div>`;
  section.addEventListener("change", (event) => {
    if (event.target.id !== "ag-pick") return;
    state.agent = event.target.value;
    store("opslens-agent", state.agent);
    problem = "";
    section.querySelector("#ag-body").dataset.agent = "";
    if (last) draw(section, last);
  });
  section.addEventListener("click", (event) => {
    if (event.target.closest("#ag-fb-read")) {
      markRead(section);
      return;
    }
    if (event.target.closest("#ag-fb-badge")) {
      section.querySelector("#ag-fb")?.scrollIntoView({ block: "start", behavior: "smooth" });
      return;
    }
    onClick(section, event);
  });
  document.addEventListener("role-changed", () => { if (last) draw(section, last); });
  keepFresh(section, "agent", (data) => { last = data; draw(section, data); });
  setInterval(() => {
    const body = section.querySelector("#ag-body");
    if (body && body.dataset.agent && !section.closest("[hidden]")) loadFeedback(body, body.dataset.agent);
  }, FEEDBACK_EVERY_MS);
}

function feedbackUrl(code) {
  return state.lockedAgent ? "/api/v2/me/feedback" : `/api/v2/feedback/agent/${encodeURIComponent(code)}`;
}

async function loadFeedback(body, code) {
  const box = body.querySelector("#ag-fb");
  const badge = body.querySelector("#ag-fb-badge");
  if (!box) return;
  let d;
  try {
    const r = await fetch(feedbackUrl(code), { credentials: "same-origin", cache: "no-store" });
    if (!r.ok) throw new Error(`server answered ${r.status}`);
    d = await r.json();
  } catch (error) {
    box.innerHTML = `<div class="card-head"><h3 class="card-title">Feedback</h3></div>
      <p class="ag-empty">Feedback could not be loaded (${escapeHtml(error.message)}). It needs the database to be running.</p>`;
    return;
  }
  if (body.dataset.agent !== code) return;
  const own = Boolean(state.lockedAgent);
  badge.hidden = !d.unseen;
  badge.textContent = `New feedback (${d.unseen})`;
  const c = d.customer;
  box.innerHTML = `<div class="card-head"><div><h3 class="card-title">${own ? "Your feedback" : `${escapeHtml(nameOf(code))}'s feedback`}</h3>
        <div class="card-sub">${c.count ? `Customers rate ${own ? "you" : "them"} <b>${avg(c.average)} / 5</b> from ${c.count} review${c.count === 1 ? "" : "s"}`
          : "No customer reviews yet"} · admin notes are not in the rating · entered by hand for now</div></div>
      ${d.unseen && own ? `<button type="button" class="btn btn-sm" id="ag-fb-read">Mark ${d.unseen} as read</button>` : ""}</div>
    ${d.items.length ? `<ul class="fb-list">${d.items.slice(0, FEEDBACK_SHOWN).map((f) => itemHtml(f, { showAgent: false, markNew: true })).join("")}</ul>`
      : `<p class="ag-empty">No feedback yet.</p>`}
    ${!own && d.unseen ? `<p class="small muted">${d.unseen} not read yet. Only ${escapeHtml(nameOf(code))} can mark them as read.</p>` : ""}`;
}

async function markRead(section) {
  const body = section.querySelector("#ag-body");
  await fetch("/api/v2/me/feedback/seen", { method: "POST", credentials: "same-origin" }).catch(() => null);
  loadFeedback(body, body.dataset.agent);
}

function nameOf(id) {
  const a = last && last.agents ? last.agents.find((x) => x.id === id) : null;
  return a ? a.name : id;
}

function draw(section, d) {
  const body = section.querySelector("#ag-body");
  if (!d.ready) {
    body.innerHTML = notReady(d);
    body.dataset.agent = "";
    return;
  }
  const ids = d.agents.map((a) => a.id);
  if (state.lockedAgent) state.agent = state.lockedAgent;
  if (!ids.includes(state.agent)) {
    const working = d.floor.find((r) => r.status !== "off");
    state.agent = (working || d.floor[0]).id;
  }
  const agent = d.agents.find((a) => a.id === state.agent);
  const row = d.floor.find((r) => r.id === state.agent);
  if (body.dataset.agent !== agent.id) {
    body.dataset.agent = agent.id;
    body.innerHTML = frame(d, agent);
    loadFeedback(body, agent.id);
  }
  const own = Boolean(state.lockedAgent);
  const mine = (d.actions || []).filter((e) => e.agent === agent.id);
  const taken = new Set(mine.filter((e) => e.kind === "take").map((e) => e.ticket_id));
  const moves = mine.filter((e) => e.kind === "break" || e.kind === "back");
  const away = moves.length > 0 && moves[moves.length - 1].kind === "break";
  body.querySelector("#ag-status").innerHTML = statusHtml(row, agent, away, own);
  body.querySelector("#ag-news").innerHTML = newsHtml(mine[mine.length - 1]);
  const openFold = body.querySelector("#ag-next details[open]");
  if (!openFold || !row.next || openFold.dataset.ticket !== row.next.ticket_id) {
    body.querySelector("#ag-next").innerHTML = row.next
      ? ticketHtml("Next for you", row.next, taken.has(row.next.ticket_id) ? `<p class="ag-done">Yours. OpsLens hands it over the moment you finish.</p>` : own ? nextActions(row.next) : "")
      : `<div class="card-head"><h3 class="card-title">Next for you</h3></div>
        <p class="ag-empty">Nothing lined up for you right now. OpsLens hands you a ticket the moment one fits.</p>`;
  } else {
    const left = body.querySelector("#ag-next .ag-left");
    if (left) left.firstChild.textContent = minutesLeft(row.next.minutes_left);
  }
  body.querySelector("#ag-now").innerHTML = row.current
    ? ticketHtml("Now working on", row.current, own ? nowActions() : "", true)
    : `<div class="card-head"><h3 class="card-title">Now working on</h3></div>
      <p class="ag-empty">${row.status === "off" ? "You are off shift." : row.status === "break" ? "You are on a break." : "Nothing right now."}</p>`;
  body.querySelector("#ag-day").innerHTML = dayTiles(row);
  setBusy(body, busy);
}

function frame(d, agent) {
  const options = Object.keys(TEAM_NAMES).map((team) => `<optgroup label="Team ${team} · ${escapeHtml(TEAM_NAMES[team])}">
      ${d.agents.filter((a) => a.team === team).map((a) => `<option value="${escapeHtml(a.id)}"${a.id === agent.id ? " selected" : ""}>
        ${escapeHtml(a.name)}</option>`).join("")}</optgroup>`).join("");
  const skills = agent.skills.map((s) => `<span class="pill">${escapeHtml(prettyKey(s))}</span>`).join("")
    + (agent.extra_skills.length ? `<span class="muted small">also trained on ${agent.extra_skills.map((s) => escapeHtml(prettyKey(s).toLowerCase())).join(", ")}</span>` : "");
  return `<header class="page-head ag-head">
      <div>
        <h1 class="page-title">${escapeHtml(agent.name)}</h1>
        <p class="page-sub">Team ${escapeHtml(agent.team)} · ${escapeHtml(TEAM_NAMES[agent.team])} · shift ${escapeHtml(agent.shift)} ·
          ${agent.languages.map((l) => escapeHtml(LANGUAGE[l] || l)).join(", ")}</p>
        <div class="chips ag-skills">${skills}</div>
      </div>
      <button type="button" class="fb-badge" id="ag-fb-badge" hidden></button>
      <label class="ag-pick"><span>Viewing</span><select id="ag-pick">${options}</select></label>
    </header>
    ${state.lockedAgent ? "" : `<p class="ag-viewonly">View only. Only ${escapeHtml(agent.name)} can take tickets, finish them or go on a break.</p>`}
    <div id="ag-status" class="ag-status"></div>
    <div id="ag-news" class="ag-news" aria-live="polite"></div>
    <div class="ag-cards">
      <section class="card ag-card ag-next" id="ag-next"></section>
      <section class="card ag-card ag-nowcard" id="ag-now"></section>
    </div>
    <div class="ag-day-title">Your day</div>
    <div class="ag-day" id="ag-day"></div>
    <section class="card ag-card ag-fb" id="ag-fb"></section>`;
}

function statusHtml(row, agent, away, own) {
  const text = row.status === "off" ? `Your shift: ${agent.shift}.`
    : row.status === "idle" ? "Free. The next ticket comes to you the moment it fits."
    : row.status === "break" ? "No new tickets come to you until you are back."
    : away ? "Your break starts when you finish this ticket. No new tickets come to you."
    : `Live at ${clockNow()}`;
  const button = !own ? "" : row.status === "break" || away
    ? `<button type="button" class="btn btn-primary" data-act="back">I'm back</button>`
    : row.status === "off" ? "" : `<button type="button" class="btn" data-act="break">On a break</button>`;
  return `<span class="tm-status is-${row.status}">${escapeHtml(STATUS_TEXT[row.status])}</span>
    <span>${escapeHtml(text)}</span><span class="ag-bar-fill"></span>${button}`;
}

function newsHtml(e) {
  if (problem) return `<p class="ag-problem" role="alert">${escapeHtml(problem)}</p>`;
  if (busy) return `<p class="ag-update"><span class="spinner" aria-hidden="true"></span> Updating the floor…</p>`;
  if (!e) return "";
  const lines = effectLines(e, nameOf);
  const floor = floorEffect(e);
  return `<div class="ag-update"><b>What changed</b>${lines.map((l) => `<span>${escapeHtml(l)}</span>`).join("")}
    ${floor ? `<span class="muted">${escapeHtml(floor)}</span>` : ""}</div>`;
}

function promiseLeft(t) {
  return t.promise_min ? t.minutes_left < t.promise_min / 4 : t.minutes_left < 15;
}

function ticketHtml(title, t, actions, compact = false) {
  const why = whyLines(t.reason).map((line) => `<li>${escapeHtml(line)}</li>`).join("");
  return `<div class="card-head"><h3 class="card-title">${escapeHtml(title)}</h3>
      <span class="ag-left ${promiseLeft(t) ? "is-urgent" : ""}">${minutesLeft(t.minutes_left)}${t.promise_min
        ? `<small> of a ${duration(t.promise_min)} promise</small>` : ""}</span></div>
    <div class="chips"><span class="pill ${t.priority === "P1" ? "p1" : ""}">${escapeHtml(t.priority)}</span>
      <span class="pill">${escapeHtml(prettyKey(t.category))}</span><span class="pill">${escapeHtml(LANGUAGE[t.language] || t.language)}</span>
      <span class="muted small">${escapeHtml(t.ticket_id)}</span></div>
    <p class="ag-quote">“${escapeHtml(t.text)}”</p>
    ${compact ? "" : `<div class="ag-why"><b>Why you</b><ul>${why}</ul></div>`}
    ${actions}`;
}

function nextActions(t) {
  return `<div class="ag-actions">
      <button type="button" class="btn btn-primary" data-act="take" data-ticket="${escapeHtml(t.ticket_id)}">Take it</button>
      <details class="ag-cant" data-ticket="${escapeHtml(t.ticket_id)}"><summary class="btn">Can't take it</summary>
        <div class="ag-reasons"><span class="muted small">Why not?</span>${CANT.map((r) => `<button type="button" class="btn btn-sm" data-act="decline"
          data-ticket="${escapeHtml(t.ticket_id)}" data-reason="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join("")}</div>
      </details>
    </div>`;
}

function nowActions() {
  return `<div class="ag-actions">
      <button type="button" class="btn btn-primary" data-act="done">Done</button>
      <span class="ag-more"><span class="muted small">Need more time</span>${EXTRA.map((m) =>
        `<button type="button" class="btn btn-sm" data-act="extra_time" data-value="${m}">+${m} min</button>`).join("")}</span>
    </div>`;
}

function dayTiles(row) {
  const onTime = row.done ? `${Math.round((100 * row.kept) / row.done)}%` : "—";
  return [
    ["Handled today", row.done, ""],
    ["On time", onTime, row.done ? `${row.kept} of ${row.done}` : ""],
    ["Rescues for other teams", row.rescues, ""],
  ].map(([label, value, sub]) => `<div class="ag-tile"><span>${escapeHtml(label)}</span>
      <b>${escapeHtml(String(value))}</b>${sub ? `<small>${escapeHtml(sub)}</small>` : ""}</div>`).join("");
}

function setBusy(body, on) {
  body.querySelectorAll("[data-act]").forEach((b) => { b.disabled = on; });
}

async function onClick(section, event) {
  const button = event.target.closest("[data-act]");
  if (!button || busy || !last || !state.lockedAgent) return;
  const body = section.querySelector("#ag-body");
  const act = button.dataset.act;
  const request = { kind: act, agent: state.agent };
  if (button.dataset.ticket) request.ticket_id = button.dataset.ticket;
  if (button.dataset.reason) request.reason = button.dataset.reason;
  if (button.dataset.value) request.value = Number(button.dataset.value);
  busy = true;
  problem = "";
  setBusy(body, true);
  body.querySelector("#ag-news").innerHTML = newsHtml(null);
  const result = await postAction(request);
  busy = false;
  problem = result.error || "";
  if (problem) {
    body.querySelector("#ag-news").innerHTML = newsHtml(null);
    setBusy(body, false);
  }
}
