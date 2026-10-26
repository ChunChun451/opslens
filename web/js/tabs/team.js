import { state, store } from "../data.js";
import { pageHeader, card, fold } from "../ui.js";
import { escapeHtml } from "../format.js";
import { setRole } from "../role.js";
import {
  TEAM_NAMES, LANGUAGE, STATUS_TEXT, clockNow, keepFresh, notReady, minutesLeft, ticketLine, initialsOf,
} from "../floornow.js";

const FEEDBACK_SHOWN = 6;

export function render(section) {
  section.innerHTML = `${pageHeader("Team", "Who is doing what right now. Click a person to open their screen.")}
    <div id="tm-body"></div>`;
  section.addEventListener("click", (event) => {
    const row = event.target.closest("[data-agent]");
    if (row) setRole("agent", row.dataset.agent);
    if (event.target.closest("#tm-clear")) {
      state.feedback = [];
      store("opslens-agent-feedback", []);
      section.querySelector("#tm-feedback").innerHTML = feedbackHtml();
    }
  });
  keepFresh(section, "team", (data) => draw(section, data));
}

function draw(section, d) {
  const body = section.querySelector("#tm-body");
  if (!d.ready) {
    body.innerHTML = notReady(d);
    return;
  }
  const ours = d.policies.opslens;
  const byId = new Map(d.agents.map((a) => [a.id, a]));
  const floor = d.floor.map((row) => ({ ...row, agent: byId.get(row.id) }));
  const count = (words) => floor.filter((r) => words.includes(r.status)).length;
  const tiles = [
    ["On shift", floor.length - count(["off"]), ""],
    ["Working", count(["busy", "wrong"]), ""],
    ["Rescuing another team", count(["cross"]), ""],
    ["Free", count(["idle"]), ""],
    ["Customers waiting", ours.waiting, `${ours.missed} ${ours.missed === 1 ? "promise" : "promises"} missed today`],
  ];
  const teams = Object.keys(TEAM_NAMES).map((team) => teamCard(team, floor.filter((r) => r.agent.team === team), ours.queues[team]));
  const off = floor.filter((r) => r.status === "off");
  body.innerHTML = `<p class="proof-line">Live at ${clockNow()} on the simulated floor, test day ${d.day}, routed by OpsLens.</p>
    <div class="brief-tiles tm-tiles">${tiles.map(([label, value, sub]) => `<div class="brief-tile">
      <div class="brief-label">${escapeHtml(label)}</div><div class="brief-value">${value}</div>
      ${sub ? `<div class="brief-sub">${escapeHtml(sub)}</div>` : ""}</div>`).join("")}</div>
    <div class="tm-teams">${teams.join("")}</div>
    ${off.length ? fold(`Off shift now (${off.length})`, `<div class="tm-off">${off.map(offChip).join("")}</div>`) : ""}
    <div id="tm-feedback">${feedbackHtml()}</div>`;
}

function teamCard(team, rows, queue) {
  const [savable, late] = queue || [0, 0];
  const on = rows.filter((r) => r.status !== "off");
  const list = on.length ? on.map(agentRow).join("") : `<p class="muted small">Nobody from this team is on shift.</p>`;
  return card({
    cls: "tm-team",
    title: `Team ${team} · ${TEAM_NAMES[team]}`,
    sub: `${savable + late} waiting${late ? `, ${late} already late` : ""}`,
    body: `<div class="tm-rows">${list}</div>`,
  });
}

function agentRow(r) {
  const now = r.current
    ? `<span class="tm-now">${ticketLine(r.current)} <b class="${r.current.minutes_left < 15 ? "is-urgent" : ""}">${minutesLeft(r.current.minutes_left)}</b></span>`
    : `<span class="tm-now muted">${r.next ? "next ticket lined up" : "—"}</span>`;
  const onTime = r.done ? `${r.kept} of ${r.done} on time` : "nothing finished yet";
  return `<button type="button" class="tm-row" data-agent="${escapeHtml(r.id)}">
      <span class="tm-avatar">${escapeHtml(initialsOf(r.agent.name))}</span>
      <span class="tm-name"><b>${escapeHtml(r.agent.name)}</b><small>${r.agent.languages.map((l) => escapeHtml(LANGUAGE[l] || l)).join(", ")}</small></span>
      <span class="tm-status is-${r.status}">${escapeHtml(STATUS_TEXT[r.status])}</span>
      ${now}
      <span class="tm-day">${escapeHtml(onTime)}${r.rescues ? ` · ${r.rescues} rescue${r.rescues === 1 ? "" : "s"}` : ""}</span>
    </button>`;
}

function offChip(r) {
  return `<button type="button" class="tm-off-chip" data-agent="${escapeHtml(r.id)}">${escapeHtml(r.agent.name)}
    <small>Team ${escapeHtml(r.agent.team)} · ${escapeHtml(r.agent.shift)}</small></button>`;
}

function feedbackHtml() {
  const items = state.feedback.slice(-FEEDBACK_SHOWN).reverse();
  if (!items.length) return "";
  return card({
    title: "From your agents",
    sub: "Tickets an agent said they could not take, with the reason. A signal for routing and training.",
    actions: `<button type="button" class="btn btn-sm" id="tm-clear">Clear</button>`,
    body: `<ul class="list tm-feedback">${items.map((f) => `<li><b>${escapeHtml(f.name)}</b> could not take
      ${escapeHtml(f.ticket_id)} (${escapeHtml(f.ticket)}) · <span class="pill">${escapeHtml(f.reason)}</span>
      <span class="muted small">${escapeHtml(f.at)}</span></li>`).join("")}</ul>`,
  });
}

export const realNote = { render(section) {
  section.innerHTML = `${pageHeader("Team", "")}
    ${card({ body: `<p>Team runs on the simulated food floor: a real event log records past work, not who is free right now.</p>
      <button type="button" class="btn btn-primary" id="tm-to-food">Show the food floor</button>` })}`;
  section.querySelector("#tm-to-food").addEventListener("click", () => {
    document.querySelector('.world-switch [data-world="food"]').click();
  });
} };
