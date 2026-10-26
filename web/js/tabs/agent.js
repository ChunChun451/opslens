import { state, store } from "../data.js";
import { escapeHtml, prettyKey } from "../format.js";
import {
  TEAM_NAMES, LANGUAGE, STATUS_TEXT, clockNow, keepFresh, notReady, minutesLeft,
} from "../floornow.js";

const CANT = ["Not my skill", "Language", "On a break", "Customer needs a callback", "Other"];
const PLAIN = [
  [/^already past its SLA - served so no customer is left behind$/, () => "Already late: served so no customer is left behind"],
  [/^breach risk ([\d.]+) -> ([\d.]+) if served now$/, (m) => `Chance of missing the promise: ${pct(m[1])} if it waits, ${pct(m[2])} if you take it now`],
  [/^low risk - served in turn \(fairness by waiting time\)$/, () => "Low risk: next in line by waiting time"],
  [/^cross-skill job .* to rescue a ticket in danger$/, () => "Outside your usual skills: a rescue, it may take you longer"],
  [/^rare-skill agent, no rare work is more urgent$/, () => "You have a rare skill, and no rare-skill work is more urgent"],
  [/^no other free agent could take it now$/, () => "No one else free could take it"],
];

let taken = new Set();
let shown = { now: "", next: "" };

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
  shown = { now: "", next: "" };
  section.innerHTML = `<div id="ag-body"></div>`;
  section.addEventListener("change", (event) => {
    if (event.target.id !== "ag-pick") return;
    state.agent = event.target.value;
    store("opslens-agent", state.agent);
    shown = { now: "", next: "" };
    section.querySelector("#ag-body").dataset.agent = "";
    keepDrawing(section);
  });
  section.addEventListener("click", (event) => onClick(section, event));
  document.addEventListener("role-changed", () => { shown = { now: "", next: "" }; keepDrawing(section); });
  keepFresh(section, "agent", (data) => { last = data; draw(section, data); });
}

let last = null;

function keepDrawing(section) {
  if (last) draw(section, last);
}

function draw(section, d) {
  const body = section.querySelector("#ag-body");
  if (!d.ready) {
    body.innerHTML = notReady(d);
    return;
  }
  const ids = d.agents.map((a) => a.id);
  if (!ids.includes(state.agent)) {
    const working = d.floor.find((r) => r.status !== "off");
    state.agent = (working || d.floor[0]).id;
  }
  const agent = d.agents.find((a) => a.id === state.agent);
  const row = d.floor.find((r) => r.id === state.agent);
  if (body.dataset.agent !== agent.id) {
    body.dataset.agent = agent.id;
    body.innerHTML = frame(d, agent);
  }
  body.querySelector("#ag-status").innerHTML = statusHtml(row, agent);
  body.querySelector("#ag-now").innerHTML = row.current
    ? ticketHtml("Now working on", row.current, "")
    : `<h3 class="card-title">Now working on</h3><p class="muted">${row.status === "off" ? "You are off shift." : "Nothing right now."}</p>`;
  if (row.next && shown.next === row.next.ticket_id) {
    const left = body.querySelector("#ag-next .ag-left");
    if (left) left.textContent = minutesLeft(row.next.minutes_left);
  } else {
    shown.next = row.next ? row.next.ticket_id : "";
    body.querySelector("#ag-next").innerHTML = row.next
      ? ticketHtml("Next for you", row.next, nextActions(row.next))
      : `<h3 class="card-title">Next for you</h3><p class="muted">Nothing is lined up for you yet. OpsLens hands you a ticket the moment you are free.</p>`;
  }
  body.querySelector("#ag-day").innerHTML = dayTiles(row);
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
      <label class="ag-pick"><span>You are</span><select id="ag-pick">${options}</select></label>
    </header>
    <div id="ag-status" class="ag-status"></div>
    <div class="ag-cards">
      <section class="card ag-card" id="ag-next"></section>
      <section class="card ag-card" id="ag-now"></section>
    </div>
    <div class="brief-tiles" id="ag-day"></div>`;
}

function statusHtml(row, agent) {
  const text = row.status === "off" ? `Off shift. Your shift: ${agent.shift}.`
    : row.status === "idle" ? "Free. The next ticket comes to you the moment it fits."
    : STATUS_TEXT[row.status];
  return `<span class="tm-status is-${row.status}">${escapeHtml(STATUS_TEXT[row.status])}</span>
    <span>${escapeHtml(text === STATUS_TEXT[row.status] ? `Live at ${clockNow()}` : text)}</span>`;
}

function ticketHtml(title, t, actions) {
  const why = whyLines(t.reason).map((line) => `<li>${escapeHtml(line)}</li>`).join("");
  return `<div class="card-head"><h3 class="card-title">${escapeHtml(title)}</h3>
      <span class="ag-left ${t.minutes_left < 15 ? "is-urgent" : ""}">${minutesLeft(t.minutes_left)}</span></div>
    <div class="chips"><span class="pill ${t.priority === "P1" ? "p1" : ""}">${escapeHtml(t.priority)}</span>
      <span class="pill">${escapeHtml(prettyKey(t.category))}</span><span class="pill">${escapeHtml(LANGUAGE[t.language] || t.language)}</span>
      <span class="muted small">${escapeHtml(t.ticket_id)}</span></div>
    <p class="ag-quote">“${escapeHtml(t.text)}”</p>
    <div class="ag-why"><b>Why you</b><ul>${why}</ul></div>
    ${actions}`;
}

function nextActions(t) {
  if (taken.has(t.ticket_id)) {
    return `<p class="ag-done">Yours. OpsLens hands it over the moment you finish.</p>`;
  }
  return `<div class="ag-actions">
      <button type="button" class="btn btn-primary" data-take="${escapeHtml(t.ticket_id)}">Take it</button>
      <details class="ag-cant"><summary class="btn">Can't take it</summary>
        <div class="ag-reasons">${CANT.map((r) => `<button type="button" class="chip-btn" data-cant="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join("")}</div>
      </details>
    </div>`;
}

function dayTiles(row) {
  const onTime = row.done ? `${Math.round((100 * row.kept) / row.done)}%` : "—";
  return [
    ["Handled today", row.done, ""],
    ["On time", onTime, row.done ? `${row.kept} of ${row.done}` : ""],
    ["Rescues for other teams", row.rescues, ""],
  ].map(([label, value, sub]) => `<div class="brief-tile"><div class="brief-label">${escapeHtml(label)}</div>
      <div class="brief-value">${escapeHtml(String(value))}</div>${sub ? `<div class="brief-sub">${escapeHtml(sub)}</div>` : ""}</div>`).join("");
}

function onClick(section, event) {
  const take = event.target.closest("[data-take]");
  const cant = event.target.closest("[data-cant]");
  const box = section.querySelector("#ag-next");
  if (take) {
    taken.add(take.dataset.take);
    box.querySelector(".ag-actions").outerHTML = `<p class="ag-done">Yours. OpsLens hands it over the moment you finish.</p>`;
  }
  if (cant) {
    const agent = last.agents.find((a) => a.id === state.agent);
    const t = last.floor.find((r) => r.id === state.agent).next;
    state.feedback = [...state.feedback, {
      agent: agent.id, name: agent.name, ticket_id: t.ticket_id,
      ticket: `${t.priority} ${prettyKey(t.category)}, ${LANGUAGE[t.language] || t.language}`,
      reason: cant.dataset.cant, at: clockNow(),
    }].slice(-50);
    store("opslens-agent-feedback", state.feedback);
    box.querySelector(".ag-actions").outerHTML = `<p class="ag-done">Logged: “${escapeHtml(cant.dataset.cant)}”. Your team lead sees it on Team.</p>`;
  }
}
