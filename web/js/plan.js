// plan.js — "Your plan": the recommendations the manager accepted or overrode, and what they change.
//
// Why (Plan v3, 19 Oct): the problem statement asks for "a dashboard showing the expected impact
// of these interventions". A recommendation is only useful if a manager can say yes or no to it
// and see what yes would change. Accept puts it in the plan with its measured effect (every number
// is a path in results.json, so it is clickable); "Simulate" replays a day with every accepted item
// together (food world: POST /api/plan/impact, the simulator). Override records why — a manager's
// "no" is information too. The plan is kept in this browser only (a demo, no accounts).
//
// Example: Accept "Cross-train 2 Hindi-speaking agents" → the plan shows its effect on missed SLAs
// over the two held-out weeks (playbooks.playbooks[1].effect.opslens.vs_without.breaches) → Simulate.

import { state, store } from "./data.js";
import { ev } from "./evidence.js";
import { escapeHtml } from "./format.js";

const items = {}; // id -> {id, world, title, owner, effects: [{label, path, unit}], note, simulable}
const choosing = new Set(); // items whose Override reason is being picked
const REASONS = ["Not now", "We disagree", "Already done"];
const SIM_DAY = 48; // the replay Saturday (sim.replay.day); the API accepts any test day

// Each view registers the recommendations it shows, so the plan panel can describe them.
export function registerItem(item) {
  items[item.id] = item;
}

// The Accept / Override control for one recommendation.
export function planButtons(id) {
  return `<div class="plan-decision" data-plan-item="${escapeHtml(id)}">${decisionHtml(id)}</div>`;
}

function decisionHtml(id) {
  const d = state.plan[id];
  if (choosing.has(id)) {
    return `<span class="small muted">Why not?</span>${REASONS.map((r) =>
      `<button type="button" class="btn btn-sm" data-plan-act="reason" data-reason="${r}">${r}</button>`).join("")}`;
  }
  if (!d) {
    return `<button type="button" class="btn btn-sm btn-primary" data-plan-act="accept">Accept</button>
      <button type="button" class="btn btn-sm" data-plan-act="override">Override</button>`;
  }
  const label = d.status === "accepted" ? `<span class="pill good">In your plan</span>`
    : `<span class="pill">Overridden · ${escapeHtml(d.reason)}</span>`;
  return `${label}<button type="button" class="link-btn" data-plan-act="undo">Undo</button>`;
}

export function initPlan() {
  document.addEventListener("click", onClick);
  document.getElementById("plan-button").addEventListener("click", () => togglePanel());
  document.addEventListener("world-changed", () => { refreshCount(); if (panelOpen()) renderPanel(); });
  refreshCount();
}

function onClick(event) {
  const button = event.target.closest("[data-plan-act]");
  if (!button) return;
  const box = button.closest("[data-plan-item]");
  if (!box) return;
  const id = box.dataset.planItem;
  const act = button.dataset.planAct;
  const item = items[id] || { world: state.world, title: id };
  if (act === "accept") {
    state.plan[id] = { status: "accepted", world: item.world, title: item.title, at: new Date().toISOString() };
  } else if (act === "override") {
    choosing.add(id);
  } else if (act === "reason") {
    choosing.delete(id);
    state.plan[id] = { status: "overridden", reason: button.dataset.reason, world: item.world, title: item.title,
                       at: new Date().toISOString() };
  } else if (act === "undo") {
    delete state.plan[id];
  }
  store("opslens-plan", state.plan);
  document.querySelectorAll(`[data-plan-item="${CSS.escape(id)}"]`).forEach((el) => { el.innerHTML = decisionHtml(id); });
  refreshCount();
  if (panelOpen()) renderPanel();
}

function mine(status) {
  return Object.entries(state.plan).filter(([, d]) => d.world === state.world && d.status === status).map(([id]) => id);
}

function refreshCount() {
  document.getElementById("plan-count").textContent = String(mine("accepted").length);
}

function panelOpen() {
  return !document.getElementById("plan-panel").hidden;
}

function togglePanel(open = !panelOpen()) {
  const panel = document.getElementById("plan-panel");
  panel.hidden = !open;
  if (open) renderPanel();
}

function effectsHtml(item) {
  if (!item || !item.effects || !item.effects.length) {
    return `<div class="small muted">${escapeHtml(item && item.note ? item.note : "No measured effect for this action alone.")}</div>`;
  }
  return `<ul class="plan-effects">${item.effects.map((e) =>
    `<li>${escapeHtml(e.label)}: ${ev(e.path, e.unit, { signed: e.signed })}${e.after ? ` <span class="small muted">${escapeHtml(e.after)}</span>` : ""}</li>`).join("")}</ul>
    ${item.note ? `<div class="small muted">${escapeHtml(item.note)}</div>` : ""}`;
}

function renderPanel() {
  const accepted = mine("accepted");
  const overridden = mine("overridden");
  const world = state.world === "real" ? "the real public service desk" : "the food-delivery floor";
  const simulable = state.world === "food" && accepted.some((id) => items[id] && items[id].simulable);
  document.getElementById("plan-panel").innerHTML = `
    <div class="plan-head"><h3>Your plan</h3>
      <button type="button" class="link-btn" id="plan-close" aria-label="Close your plan">Close</button></div>
    <p class="small muted">Recommendations you accepted or overrode for ${world}. Accepting shows what each one changes,
      measured on days OpsLens never saw. Kept in this browser only.</p>
    <h4>Accepted (${accepted.length})</h4>
    ${accepted.length ? accepted.map((id) => `<div class="plan-item">
        <div class="plan-item-head"><strong>${escapeHtml(state.plan[id].title)}</strong>
          ${items[id] && items[id].owner ? `<span class="pill">${escapeHtml(items[id].owner)}</span>` : ""}</div>
        ${effectsHtml(items[id])}</div>`).join("")
      : `<p class="small muted">Nothing yet. Open Actions and press Accept on a recommendation.</p>`}
    ${simulable ? `<button type="button" class="btn btn-primary" id="plan-simulate">Simulate Saturday 17 Oct with this plan</button>
      <div id="plan-result" class="plan-result"></div>` : ""}
    ${overridden.length ? `<h4>Overridden (${overridden.length})</h4>${overridden.map((id) =>
      `<div class="plan-item small">${escapeHtml(state.plan[id].title)} — <em>${escapeHtml(state.plan[id].reason)}</em></div>`).join("")}` : ""}`;
  document.getElementById("plan-close").addEventListener("click", () => togglePanel(false));
  const sim = document.getElementById("plan-simulate");
  if (sim) sim.addEventListener("click", () => simulate(accepted.filter((id) => items[id] && items[id].simulable)));
}

// Replay one day with all accepted items together, with and without them (the simulator).
async function simulate(ids) {
  const out = document.getElementById("plan-result");
  out.innerHTML = `<p class="small muted">Simulating the whole day with and without your plan…</p>`;
  try {
    const response = await fetch("/api/plan/impact", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ day: SIM_DAY, items: ids }),
    });
    if (response.status === 404) {
      out.innerHTML = `<p class="small muted">The live plan simulator is not on this server yet. Each action's own measured effect is shown above.</p>`;
      return;
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || "HTTP " + response.status);
    state.planimpact = data;
    out.innerHTML = impactHtml(data);
  } catch (error) {
    out.innerHTML = `<p class="small muted">Could not simulate: ${escapeHtml(error.message)}</p>`;
  }
}

// Expected response: {headings: {turnaround: [kpi...], productivity: [...], quality: [...]},
// labels: {kpi: "..."}, without: {kpi: v}, with: {kpi: v}, delta: {kpi: v}, seconds}.
function impactHtml(data) {
  const headings = data.headings || { results: Object.keys(data.delta || {}) };
  return Object.entries(headings).map(([heading, kpis]) => `
    <h5>${escapeHtml(heading[0].toUpperCase() + heading.slice(1))}</h5>
    <table class="plan-table"><thead><tr><th></th><th class="num">Without</th><th class="num">With your plan</th><th class="num">Change</th></tr></thead>
    <tbody>${kpis.map((k) => `<tr><td>${escapeHtml((data.labels && data.labels[k]) || k)}</td>
      <td class="num">${ev(`planimpact.without.${k}`, "num")}</td><td class="num">${ev(`planimpact.with.${k}`, "num")}</td>
      <td class="num">${ev(`planimpact.delta.${k}`, "num", { signed: true })}</td></tr>`).join("")}</tbody></table>`).join("")
    + (data.seconds ? `<p class="small muted">Simulated live in ${ev("planimpact.seconds", "sec")}.</p>` : "");
}
