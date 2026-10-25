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

import { state, store, lookup } from "./data.js";
import { ev, evText } from "./evidence.js";
import { escapeHtml } from "./format.js";

const items = {}; // id -> {id, world, title, owner, effects: [{label, path, unit}], note, simulable}
const choosing = new Set(); // items whose Override reason is being picked
const REASONS = ["Not now", "We disagree", "Already done"];
// Units of the plan data (opslens/plan.py PLAN_KPIS) -> units of ev(). Counts are means over seeds,
// so they keep one decimal: "−7.6 [−15.0, −0.2]" is clearly below zero, "−8 [−15, 0]" would hide it.
const UNITS = { tickets: "count", "%": "pct", min: "min", h: "hours", "tickets/h": "ratio" };
// What the plan panel shows for each accepted item, one per heading of the problem statement.
const ITEM_KPIS = ["breaches", "busy_agent_hours", "late_minutes_per_100"];
const warmed = new Set(); // days whose "without" runs the server already has
const HEADINGS = { turnaround: "Turnaround", productivity: "Productivity", quality: "Service quality" };
let simDay = null; // the test day picked in the panel; default: the replay Saturday

// Each view registers the recommendations it shows, so the plan panel can describe them.
export function registerItem(item) {
  items[item.id] = item;
}

// Where results.plan measured item `id` on its own (eval/run_plan_items.py), or -1.
export function planIndex(id) {
  const plan = state.results.plan;
  return plan && Array.isArray(plan.items) ? plan.items.findIndex((it) => it.id === id) : -1;
}

function evUnit(key) {
  return UNITS[(state.results.plan.units || {})[key]] || "num";
}

// One measured change with its 95% interval: "−8 [−15, −0]", plus "no clear effect" when the
// interval contains 0 (then the honest answer is "we cannot tell", whatever the sign).
export function measured(base, key, verdict = true) {
  const unit = evUnit(key);
  const diffUnit = unit === "pct" ? "pts" : unit;
  const low = lookup(base + ".ci_low");
  const high = lookup(base + ".ci_high");
  const unclear = typeof low === "number" && low <= 0 && high >= 0;
  return `${ev(base + ".diff", diffUnit, { signed: true })} <span class="small muted">[${ev(base + ".ci_low", diffUnit, { signed: true })},
    ${ev(base + ".ci_high", diffUnit, { signed: true })}]${verdict && unclear ? " · no clear effect" : ""}</span>`;
}

// The item's own measured effect, from results.plan: "customers who missed the SLA −27 [−39, −15]".
export function planEffectHtml(id, keys = ITEM_KPIS) {
  const j = planIndex(id);
  if (j < 0) return "";
  const labels = state.results.plan.labels || {};
  return `<ul class="plan-effects">${keys.map((key) =>
    `<li>${escapeHtml(capital(labels[key] || key))}: ${measured(`plan.items[${j}].effect.${key}`, key)}</li>`).join("")}</ul>`;
}

function capital(text) {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
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

// What the plan knows about item `id`: what a screen registered, else the food plan catalogue
// (results.plan.items), so the panel works whichever screen was opened first.
function itemInfo(id) {
  if (items[id]) return items[id];
  const j = planIndex(id);
  if (j < 0) return null;
  const it = state.results.plan.items[j];
  return { id, world: "food", title: it.title, owner: it.owner, simulable: true };
}

export function initPlan(startItems = []) {
  startItems.forEach(registerItem);
  // Plans saved before 19 Oct used "move-<i>" ids for staffing moves; the server does not know them.
  const stale = Object.keys(state.plan).filter((id) => id.startsWith("move-"));
  stale.forEach((id) => delete state.plan[id]);
  if (stale.length) store("opslens-plan", state.plan);
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
  const item = itemInfo(id) || { world: state.world, title: id };
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
  if (act !== "override") state.planimpact = null; // an old simulation belongs to a different plan
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
  if (item && planIndex(item.id) >= 0) {
    return `<div class="small muted">Alone, over the 14 held-out days (5 seeds), against today's roster with nothing accepted:</div>
      ${planEffectHtml(item.id)}${item.note ? `<div class="small muted">${escapeHtml(item.note)}</div>` : ""}`;
  }
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
  const simulable = state.world === "food" && accepted.some((id) => itemInfo(id) && itemInfo(id).simulable);
  document.getElementById("plan-panel").innerHTML = `
    <div class="plan-head"><h3>Your plan</h3>
      <button type="button" class="link-btn" id="plan-close" aria-label="Close your plan">Close</button></div>
    <p class="small muted">Recommendations you accepted or overrode for ${world}. Accepting shows what each one changes,
      measured on days OpsLens never saw. Kept in this browser only.</p>
    <h4>Accepted (${accepted.length})</h4>
    ${accepted.length ? accepted.map(acceptedHtml).join("")
      : `<p class="small muted">Nothing yet. Open Actions and press Accept on a recommendation.</p>`}
    ${simulable ? `<div class="plan-sim"><label class="small" for="plan-day">Day</label>
        <select id="plan-day">${dayOptions()}</select>
        <button type="button" class="btn btn-primary" id="plan-simulate">Simulate this day with your plan</button></div>
      <div id="plan-result" class="plan-result">${state.planimpact ? impactHtml(state.planimpact) : ""}</div>` : ""}
    ${overridden.length ? `<h4>Overridden (${overridden.length})</h4>${overridden.map((id) =>
      `<div class="plan-item small">${escapeHtml(state.plan[id].title)}: <em>${escapeHtml(state.plan[id].reason)}</em></div>`).join("")}` : ""}`;
  document.getElementById("plan-close").addEventListener("click", () => togglePanel(false));
  const sim = document.getElementById("plan-simulate");
  if (sim) {
    warmUp(currentDay());
    document.getElementById("plan-day").addEventListener("change", (event) => {
      simDay = Number(event.target.value);
      warmUp(simDay);
    });
    sim.addEventListener("click", () => simulate(accepted.filter((id) => itemInfo(id) && itemInfo(id).simulable), currentDay()));
  }
}

// Ask the server for the day's "without" runs in the background (an empty plan): it starts the
// simulation workers and caches those runs, so the real Simulate click takes ~18 s, not ~30 s.
function warmUp(day) {
  if (!day || warmed.has(day)) return;
  warmed.add(day);
  fetch("/api/plan/impact", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day, items: [] }) }).catch(() => warmed.delete(day));
}

// The held-out test days (meta.test_days), named by weekday and date from meta.start_date.
function testDays() {
  const meta = state.results.meta || {};
  if (!Array.isArray(meta.test_days) || !meta.start_date) return [];
  const start = new Date(meta.start_date + "T00:00:00");
  const days = [];
  for (let day = meta.test_days[0]; day <= meta.test_days[1]; day++) {
    const date = new Date(start);
    date.setDate(start.getDate() + day - 1);
    days.push({ day, name: date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) });
  }
  return days;
}

function currentDay() {
  if (simDay !== null) return simDay;
  const replay = state.results.sim && state.results.sim.replay;
  return replay && replay.day ? replay.day : (testDays()[0] || { day: null }).day;
}

function dayOptions() {
  const chosen = currentDay();
  return testDays().map((d) => `<option value="${d.day}" ${d.day === chosen ? "selected" : ""}>${escapeHtml(d.name)} (day ${d.day})</option>`).join("");
}

function acceptedHtml(id) {
  const info = itemInfo(id);
  return `<div class="plan-item">
      <div class="plan-item-head"><strong>${escapeHtml(state.plan[id].title)}</strong>
        ${info && info.owner ? `<span class="pill">${escapeHtml(info.owner)}</span>` : ""}</div>
      ${effectsHtml(info)}</div>`;
}

// Replay one day with all accepted items together, with and without them (the simulator).
async function simulate(ids, day) {
  const out = document.getElementById("plan-result");
  const button = document.getElementById("plan-simulate");
  button.disabled = true;
  out.innerHTML = `<p class="small muted">Simulating the whole day with and without your plan, 3 times with different luck: about 20 seconds (a plan simulated before comes back at once)…</p>`;
  try {
    const response = await fetch("/api/plan/impact", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ day, items: ids }),
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
  } finally {
    button.disabled = false;
  }
}

// The answer of POST /api/plan/impact (docs/explain/plan.md): which accepted items change that day,
// then without / with / delta per KPI under turnaround, productivity and quality (means over seeds).
// A change is coloured only when every seed agrees on its direction.
function impactHtml(data) {
  const all = data.items || [];
  const idle = all.filter((it) => !it.in_effect);
  const head = `<p class="small"><strong>${escapeHtml(data.weekday || "")}, day ${ev("planimpact.day", "int")}</strong>:
      ${all.length - idle.length} of ${all.length} accepted items change this day.
      ${idle.length ? `<span class="muted">Not in effect: ${idle.map((it) => `${escapeHtml(it.title)} (${escapeHtml(it.when)})`).join("; ")}.</span>` : ""}</p>`;
  const tables = Object.keys(HEADINGS).filter((h) => data.headings && Array.isArray(data.headings[h])).map((h) => `
    <h5>${HEADINGS[h]}</h5>
    <table class="plan-table"><thead><tr><th></th><th class="num">Without</th><th class="num">With your plan</th><th class="num">Change</th></tr></thead>
    <tbody>${data.headings[h].map((key) => {
      const unit = UNITS[(data.units || {})[key]] || "num";
      return `<tr><td>${escapeHtml(capital((data.labels || {})[key] || key))}</td>
        <td class="num">${ev(`planimpact.without.${key}`, unit)}</td><td class="num">${ev(`planimpact.with.${key}`, unit)}</td>
        <td class="num ${tone((data.better || {})[key], (data.delta_by_seed || {})[key])}">${ev(`planimpact.delta.${key}`, unit === "pct" ? "pts" : unit, { signed: true })}</td></tr>`;
    }).join("")}</tbody></table>`).join("");
  return head + tables + `<p class="small muted">${evText("planimpact.note")} Simulated in ${ev("planimpact.seconds", "sec")}.</p>`;
}

// "good" / "bad" when every seed moved the same way, "" when the seeds disagree or nothing moved.
function tone(better, seeds) {
  if (!better || !Array.isArray(seeds) || !seeds.length) return "";
  const down = seeds.every((d) => d < 0);
  const up = seeds.every((d) => d > 0);
  if (!down && !up) return "";
  return (down === (better === "lower")) ? "delta-good" : "delta-bad";
}
