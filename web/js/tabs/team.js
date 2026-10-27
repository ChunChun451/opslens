import { pageHeader, card, fold } from "../ui.js";
import { escapeHtml } from "../format.js";
import { setRole } from "../role.js";
import {
  TEAM_NAMES, LANGUAGE, STATUS_TEXT, clockNow, keepFresh, notReady, minutesLeft, ticketLine, initialsOf,
  resetDay, effectLines, floorEffect, clockOf,
} from "../floornow.js";

const FEED_SHOWN = 8;
const MIN_SCALE = 2;
const BUSY_WORDS = ["busy", "wrong", "cross"];

let last = null;

export function render(section) {
  section.innerHTML = `${pageHeader("Team", "Who is doing what right now. Click a person to open their screen.")}
    <div id="tm-body"></div>`;
  section.addEventListener("click", async (event) => {
    const row = event.target.closest("[data-agent]");
    if (row) setRole("agent", row.dataset.agent);
    const reset = event.target.closest("#tm-reset");
    if (reset) {
      reset.disabled = true;
      reset.textContent = "Resetting…";
      await resetDay();
    }
  });
  keepFresh(section, "team", (data) => { last = data; draw(section, data); });
}

function nameOf(id) {
  const a = last && last.agents ? last.agents.find((x) => x.id === id) : null;
  return a ? a.name : id;
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
    ["On shift", floor.length - count(["off"]), count(["break"]) ? `${count(["break"])} on a break` : ""],
    ["Working", count(["busy", "wrong"]), ""],
    ["Rescuing another team", count(["cross"]), ""],
    ["Free", count(["idle"]), ""],
    ["Customers waiting", ours.waiting, `${ours.missed} ${ours.missed === 1 ? "promise" : "promises"} missed today`],
  ];
  const teams = Object.keys(TEAM_NAMES).map((team) => {
    const rows = floor.filter((r) => r.agent.team === team);
    const [savable, late] = ours.queues[team] || [0, 0];
    const on = rows.filter((r) => r.status !== "off");
    const working = rows.filter((r) => BUSY_WORDS.includes(r.status)).length;
    return { team, rows, on, savable, late, load: (working + savable + late) / Math.max(1, on.filter((r) => r.status !== "break").length) };
  });
  const busiest = teams.reduce((a, b) => (b.load > a.load ? b : a), teams[0]);
  const off = floor.filter((r) => r.status === "off");
  const wasOpen = Boolean(body.querySelector("#tm-offs[open]"));
  body.innerHTML = `<p class="proof-line">Live at ${clockNow()} · simulated food floor, test day ${d.day} · routed by OpsLens.</p>
    <div class="tm-tiles">${tiles.map(([label, value, sub]) => `<div class="tm-tile">
      <span>${escapeHtml(label)}</span><b>${value}</b>${sub ? `<small>${escapeHtml(sub)}</small>` : ""}</div>`).join("")}</div>
    <div class="tm-teams">${teams.map((t) => teamCard(t, t === busiest && t.load > 0, Math.max(MIN_SCALE, busiest.load))).join("")}</div>
    ${off.length ? fold(`Off shift now (${off.length})`, `<div class="tm-off">${off.map(offChip).join("")}</div>`, { id: "tm-offs", open: wasOpen }) : ""}
    ${feedCard(d)}`;
}

function teamCard(t, busiest, scale) {
  const list = t.on.length ? t.on.map(agentRow).join("") : `<p class="muted small">Nobody from this team is on shift.</p>`;
  const waiting = t.savable + t.late;
  const share = Math.min(1, t.load / scale);
  return `<section class="card tm-team${busiest ? " is-busiest" : ""}">
      <div class="tm-team-head">
        <h3 class="card-title">Team ${t.team} · ${escapeHtml(TEAM_NAMES[t.team])}</h3>
        ${busiest ? `<span class="tm-flag">Most loaded</span>` : ""}
      </div>
      <div class="tm-counts"><span><b>${waiting}</b> waiting</span><span class="${t.late ? "is-urgent" : ""}"><b>${t.late}</b> already late</span>
        <span><b>${t.on.length}</b> on shift</span></div>
      <div class="tm-load" title="Work in hand and waiting per agent on shift: ${t.load.toFixed(1)}"><i style="width:${Math.round(share * 100)}%"></i></div>
      <div class="tm-rows">${list}</div>
    </section>`;
}

function urgent(t) {
  return t.promise_min ? t.minutes_left < t.promise_min / 4 : t.minutes_left < 15;
}

function agentRow(r) {
  const working = Boolean(r.current);
  const now = working
    ? `<span class="tm-ticket">${ticketLine(r.current)}</span><b class="tm-left ${urgent(r.current) ? "is-urgent" : ""}">${minutesLeft(r.current.minutes_left)}</b>`
    : `<span class="tm-ticket muted">${r.status === "break" ? "On a break" : r.next ? `Next: ${ticketLine(r.next)}` : "Waiting for work"}</span>`;
  const onTime = r.done ? `${r.kept} of ${r.done} on time` : "nothing finished yet";
  return `<button type="button" class="tm-row ${working ? "is-working" : `is-${r.status}`}" data-agent="${escapeHtml(r.id)}">
      <span class="tm-avatar">${escapeHtml(initialsOf(r.agent.name))}</span>
      <span class="tm-name"><b>${escapeHtml(r.agent.name)}</b><small>${r.agent.languages.map((l) => escapeHtml(LANGUAGE[l] || l)).join(", ")}</small></span>
      <span class="tm-status is-${r.status}">${escapeHtml(STATUS_TEXT[r.status])}</span>
      <span class="tm-now">${now}</span>
      <span class="tm-day">${escapeHtml(onTime)}${r.rescues ? ` · ${r.rescues} rescue${r.rescues === 1 ? "" : "s"}` : ""}</span>
    </button>`;
}

function offChip(r) {
  return `<button type="button" class="tm-off-chip" data-agent="${escapeHtml(r.id)}">${escapeHtml(r.agent.name)}
    <small>Team ${escapeHtml(r.agent.team)} · ${escapeHtml(r.agent.shift)}</small></button>`;
}

function feedCard(d) {
  const items = (d.actions || []).slice().reverse();
  const rows = items.slice(0, FEED_SHOWN).map((e) => {
    const lines = effectLines(e, nameOf);
    const floor = floorEffect(e);
    return `<li><span class="tm-feed-time">${escapeHtml(clockOf(e.minute))}</span><div>${lines.map((l) => `<span>${escapeHtml(l)}</span>`).join("")}
      ${floor ? `<span class="muted small">${escapeHtml(floor)}</span>` : ""}</div></li>`;
  }).join("");
  return card({
    cls: "tm-feed",
    title: "Agent actions",
    sub: "What agents reported on their screens, and what it changed. Applied to the OpsLens floor only; the industry standard floor stays as it was, for comparison.",
    actions: items.length ? `<button type="button" class="btn btn-sm" id="tm-reset">Reset the day</button>` : "",
    body: items.length ? `<ul class="tm-feed-list">${rows}</ul>`
      : `<p class="muted small">No actions yet. On the Agent screen, an agent can finish early, ask for more time, take a break or say they can't take a ticket; OpsLens re-plans the floor and the effect shows here.</p>`,
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
