import { state, store, lookup } from "./data.js";
import { ev, evText } from "./evidence.js";
import { escapeHtml } from "./format.js";

const items = {};
const choosing = new Set();
const REASONS = ["Not now", "We disagree", "Already done"];
const UNITS = { tickets: "count", "%": "pct", min: "min", h: "hours", "tickets/h": "ratio" };
const ITEM_KPIS = ["breaches", "busy_agent_hours", "late_minutes_per_100"];
const warmed = new Set();
const HEADINGS = { turnaround: "Turnaround", productivity: "Productivity", quality: "Service quality" };
let simDay = null;

export function registerItem(item) {
  items[item.id] = item;
}

export function planIndex(id) {
  const plan = state.results.plan;
  return plan && Array.isArray(plan.items) ? plan.items.findIndex((it) => it.id === id) : -1;
}

function evUnit(key) {
  return UNITS[(state.results.plan.units || {})[key]] || "num";
}

export function measured(base, key, verdict = true) {
  const unit = evUnit(key);
  const diffUnit = unit === "pct" ? "pts" : unit;
  const low = lookup(base + ".ci_low");
  const high = lookup(base + ".ci_high");
  const unclear = typeof low === "number" && low <= 0 && high >= 0;
  return `${ev(base + ".diff", diffUnit, { signed: true })} <span class="small muted">[${ev(base + ".ci_low", diffUnit, { signed: true })},
    ${ev(base + ".ci_high", diffUnit, { signed: true })}]${verdict && unclear ? " · no clear effect" : ""}</span>`;
}

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

function itemInfo(id) {
  if (items[id]) return items[id];
  const j = planIndex(id);
  if (j < 0) return null;
  const it = state.results.plan.items[j];
  return { id, world: "food", title: it.title, owner: it.owner, simulable: true };
}

export function initPlan(startItems = []) {
  startItems.forEach(registerItem);
  const stale = Object.keys(state.plan).filter((id) => id.startsWith("move-"));
  stale.forEach((id) => delete state.plan[id]);
  if (stale.length) store("opslens-plan", state.plan);
  document.addEventListener("click", onClick);
  document.getElementById("plan-button").addEventListener("click", () => togglePanel());
  ["world-changed", "source-changed"].forEach((type) => document.addEventListener(type, () => { refreshCount(); if (panelOpen()) renderPanel(); }));
  refreshCount();
}

function sourceKey() {
  const meta = state.uploadMeta;
  return state.world === "real" && state.realSource === "upload" && state.upload && meta ? `upload:${meta.token}` : "";
}

function onClick(event) {
  const button = event.target.closest("[data-plan-act]");
  if (!button) return;
  const box = button.closest("[data-plan-item]");
  if (!box) return;
  const id = box.dataset.planItem;
  const act = button.dataset.planAct;
  const item = itemInfo(id) || { world: state.world, title: id };
  const source = item.source || "";
  if (act === "accept") {
    state.plan[id] = { status: "accepted", world: item.world, source, title: item.title, at: new Date().toISOString() };
  } else if (act === "override") {
    choosing.add(id);
  } else if (act === "reason") {
    choosing.delete(id);
    state.plan[id] = { status: "overridden", reason: button.dataset.reason, world: item.world, source, title: item.title,
                       at: new Date().toISOString() };
  } else if (act === "undo") {
    delete state.plan[id];
  }
  store("opslens-plan", state.plan);
  if (act !== "override") state.planimpact = null;
  document.querySelectorAll(`[data-plan-item="${CSS.escape(id)}"]`).forEach((el) => { el.innerHTML = decisionHtml(id); });
  refreshCount();
  if (panelOpen()) renderPanel();
}

function mine(status) {
  return Object.entries(state.plan)
    .filter(([, d]) => d.world === state.world && (d.source || "") === sourceKey() && d.status === status).map(([id]) => id);
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
  const onFile = sourceKey() !== "";
  const world = onFile ? `your file ${escapeHtml(state.uploadMeta.name)}` : state.world === "real" ? "the real public service desk" : "the food-delivery floor";
  const simulable = state.world === "food" && accepted.some((id) => itemInfo(id) && itemInfo(id).simulable);
  document.getElementById("plan-panel").innerHTML = `
    <div class="plan-head"><h3>Your plan</h3>
      <button type="button" class="link-btn" id="plan-close" aria-label="Close your plan">Close</button></div>
    <p class="small muted">Recommendations you accepted or overrode for ${world}. ${onFile
      ? "Each one keeps the facts measured in your file." : "Accepting shows what each one changes, measured on days OpsLens never saw."}
      Kept in this browser only.</p>
    <h4>Accepted (${accepted.length})</h4>
    ${accepted.length ? accepted.map(acceptedHtml).join("")
      : `<p class="small muted">Nothing yet. Open Actions and press Accept on a recommendation.</p>`}
    ${onFile ? `<p class="small muted">No Simulate for a file: a log cannot be replayed under different decisions.</p>` : ""}
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

function warmUp(day) {
  if (!day || warmed.has(day)) return;
  warmed.add(day);
  fetch("/api/plan/impact", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day, items: [] }) }).catch(() => warmed.delete(day));
}

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

function tone(better, seeds) {
  if (!better || !Array.isArray(seeds) || !seeds.length) return "";
  const down = seeds.every((d) => d < 0);
  const up = seeds.every((d) => d > 0);
  if (!down && !up) return "";
  return (down === (better === "lower")) ? "delta-good" : "delta-bad";
}
