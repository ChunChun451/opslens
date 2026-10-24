// tabs/recommendations.js — what to do: fixes at the source, staffing changes, and the automatic
// ticket-by-ticket dispatch.
//
// Why (Plan v3, 19 Oct): the manager decides the big things and the engine does the small ones.
// Fixes and staffing changes have Accept / Override (web/js/plan.js): accepting puts them in
// "Your plan" with their measured effect and lets the manager simulate the plan. Who takes which
// ticket is automatic (a manager cannot approve 1,100 tickets a day), so it is only explained.
//
// Example (real results): ticket T060574 -> Neha G. (A04), "P2 late delivery, English,
// waiting 12 min; low risk - served in turn". Staffing, days 43-49: six shift changes with the
// same people and hours cut the forecast shortage from 654.2 to 635.9 agent-hours.

import { state, lookup } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, missing, initials, fold } from "../ui.js";
import { escapeHtml, kpiInfo, spreadUnit } from "../format.js";
import { planButtons, registerItem, planIndex, measured } from "../plan.js";

// Assignments shown before "Show all" (a layout choice, not a result).
const ASSIGNMENTS_SHOWN = 8;
const TOP_FIXES = 3; // fixes shown before the fold (a layout choice)

export function render(section) {
  const rec = state.results.recommendations;
  const head = pageHeader("What to do",
    "The changes that pay off most, each tested on 14 days OpsLens never saw. Accept one to add it to Your plan.");
  if (!rec) {
    section.innerHTML = head + missing("Recommendations", "M7");
    return;
  }
  section.innerHTML = `${head}
    ${planLead()}
    ${playbooksCard()}
    ${fold("Staffing changes for the coming weeks", staffingCard(rec), { hint: "same people, same hours" })}
    ${fold("Who takes which ticket (automatic, with a reason each)", assignmentsCard(rec), { hint: "Saturday evening" })}`;
}

// The whole plan in one line: every recommendation accepted together, replayed on the held-out days
// (its own run, not a sum of the single effects).
function planLead() {
  const plan = state.results.plan;
  if (!plan || !plan.all_items) return "";
  return `<p class="lead">Accept all ${plan.items.length} recommendations below and, over the 14 held-out days,
    the customers who miss their SLA change by ${measured("plan.all_items.effect.breaches", "breaches", false)}
    (${ev("plan.base_kpis.breaches.mean", "count")} without any of them). Each one alone is measured the same way, so
    you can see which ones pay off and which do not.</p>`;
}

// Fix-at-source playbooks (added 16 Oct): an upstream action per evidence card, each replayed
// on the test days in the simulator. Every number is a paired difference from results.json.
function playbooksCard() {
  const pbs = state.results.playbooks;
  if (!pbs || !pbs.playbooks.length) return "";
  const diff = (path, unit) => `${ev(path + ".mean_diff", unit, { signed: true })}
    <span class="small muted">[${ev(path + ".ci_low", unit, { signed: true })}, ${ev(path + ".ci_high", unit, { signed: true })}]</span>`;
  const item = (pb, i) => {
    const base = `playbooks.playbooks[${i}]`;
    const fx = (policy, kpi) => `${base}.effect.${policy}.vs_without.${kpi}`;
    // OpsLens column: this fix alone on today's roster (results.plan), the same footing as the
    // priority-first column and the same number Your plan shows. Older results: the playbook run.
    const j = planIndex(pb.id);
    const ops = (kpi, key, unit) => (j >= 0 ? measured(`plan.items[${j}].effect.${key}`, key, false) : diff(fx("opslens", kpi), unit));
    registerItem({ id: pb.id, world: "food", title: pb.title, owner: pb.owner, simulable: true,
      effects: [
        { label: "Missed SLAs over the 14 held-out days, with OpsLens", path: fx("opslens", "breaches") + ".mean_diff", unit: "int", signed: true },
        { label: "Missed SLAs with today's urgent-first routing", path: fx("baseline_b", "breaches") + ".mean_diff", unit: "int", signed: true },
        { label: "Agent-hours of work, with OpsLens", path: fx("opslens", "agent_hours") + ".mean_diff", unit: "hours", signed: true },
      ] });
    const assumptions = pb.assumptions.map((a, k) =>
      `<li class="${a.startsWith("ASSUMPTION") ? "assumption" : ""}">${evText(`${base}.assumptions[${k}]`)}</li>`).join("");
    const effect = j >= 0 ? lookup(`plan.items[${j}].effect.breaches.diff`) : null;
    const low = j >= 0 ? lookup(`plan.items[${j}].effect.breaches.ci_low`) : null;
    const high = j >= 0 ? lookup(`plan.items[${j}].effect.breaches.ci_high`) : null;
    const clear = typeof low === "number" && (high < 0 || low > 0);
    return `<div class="playbook fix-card ${clear && effect < 0 ? "is-win" : "is-unclear"}" id="playbook-${i}">
        <div class="week-head">
          <h4>${evText(base + ".title")}</h4>
          <span class="pill">${evText(base + ".owner")}</span>
        </div>
        <div class="fix-effect">
          <span class="fix-number">${j >= 0 ? ev(`plan.items[${j}].effect.breaches.diff`, "count", { signed: true }) : ev(fx("opslens", "breaches") + ".mean_diff", "count", { signed: true })}</span>
          <span class="fix-label">customers who miss their promise over 14 days, with OpsLens${clear ? "" : " · no clear effect"}</span>
        </div>
        <p class="fix-message">${evText(base + ".message.text")}
          <span class="small muted">(${pb.message.source === "llm" ? "drafted by the LLM, numbers filled in by code" : "template"})</span></p>
        <details class="disclosure"><summary>The numbers</summary>
        <div class="table-wrap"><table>
          <thead><tr><th>Measured on test days</th><th class="num">With OpsLens</th><th class="num">With priority-first</th></tr></thead>
          <tbody>
            <tr><td>Customers who missed the SLA</td><td class="num">${ops("breaches", "breaches", "count")}</td><td class="num">${diff(fx("baseline_b", "breaches"), "count")}</td></tr>
            <tr><td>Tickets</td><td class="num">${ops("tickets", "tickets", "count")}</td><td class="num">${diff(fx("baseline_b", "tickets"), "count")}</td></tr>
            <tr><td>Transfers</td><td class="num">${ops("transfers", "transfers", "count")}</td><td class="num">${diff(fx("baseline_b", "transfers"), "count")}</td></tr>
            <tr><td>Agent-hours of work</td><td class="num">${ops("agent_hours", "busy_agent_hours", "hours")}</td><td class="num">${diff(fx("baseline_b", "agent_hours"), "hours")}</td></tr>
          </tbody></table></div>
        <ul class="small muted">${assumptions}</ul>
        </details>
        ${planButtons(pb.id)}
      </div>`;
  };
  const all = (policy) => `playbooks.all.${policy}.vs_without.breaches`;
  const order = byOpsLensEffect(pbs.playbooks);
  return card({
    id: "rec-playbooks",
    title: "Fix problems at their source",
    sub: "Each fix goes to the team that can remove the problem. Each was replayed alone on 14 held-out days; biggest effect first.",
    body: `<div class="fix-grid">${order.slice(0, TOP_FIXES).map((i) => item(pbs.playbooks[i], i)).join("")}</div>
      ${order.length > TOP_FIXES ? fold(`${order.length - TOP_FIXES} more fixes`, `<div class="fix-grid">${order.slice(TOP_FIXES).map((i) => item(pbs.playbooks[i], i)).join("")}</div>`, { hint: "smaller or unclear effect" }) : ""}
      <p><strong>All six fixes together</strong> under priority-first: ${diff(all("baseline_b"), "count")} customers who missed the SLA.
        OpsLens with every fix and this week's staffing, against priority-first today:
        ${diff("playbooks.opslens_all_vs_baseline_b.breaches", "count")}.</p>`,
  });
}

function assignmentsCard(rec) {
  if (!rec.assignments.length) {
    return card({ title: "Assignments", body: `<p class="muted">No assignments right now.</p>` });
  }
  const row = (a, i) => {
    const base = `recommendations.assignments[${i}]`;
    return `<tr id="assign-${i}">
        <td>${evText(base + ".ticket_id")}</td>
        <td><div class="agent"><span class="avatar">${escapeHtml(initials(a.agent_name))}</span>
          <div><div><strong>${evText(base + ".agent_name")}</strong></div><div class="small muted">${evText(base + ".agent_id")}</div></div></div></td>
        <td>${evText(base + ".reason")}</td>
        <td class="num">${ev(base + ".value", "ratio")}</td>
      </tr>`;
  };
  const head = `<thead><tr><th>Ticket</th><th>Agent</th><th>Why this agent</th><th class="num">Value</th></tr></thead>`;
  const first = rec.assignments.slice(0, ASSIGNMENTS_SHOWN).map((a, i) => row(a, i)).join("");
  const rest = rec.assignments.slice(ASSIGNMENTS_SHOWN).map((a, i) => row(a, i + ASSIGNMENTS_SHOWN)).join("");
  return `<div id="rec-assignments"><p class="small muted">OpsLens hands each waiting ticket to a free agent the moment one is free:
      the tickets most likely to miss their promise first, with the right skills and language. A Saturday evening.</p>
    <div class="table-wrap"><table>${head}<tbody>${first}</tbody></table></div>
      ${rest ? `<details class="disclosure"><summary>Show all assignments</summary>
        <div class="table-wrap"><table>${head}<tbody>${rest}</tbody></table></div></details>` : ""}</div>`;
}

// Playbook indexes, most missed SLAs saved with OpsLens first (results.plan; JSON order if absent).
function byOpsLensEffect(playbooks) {
  const saved = (pb) => {
    const j = planIndex(pb.id);
    const v = j >= 0 ? lookup(`plan.items[${j}].effect.breaches.diff`) : undefined;
    return typeof v === "number" ? v : 0;
  };
  return playbooks.map((pb, i) => i).sort((a, b) => saved(playbooks[a]) - saved(playbooks[b]));
}

// A staffing move whose own replay shows a clear effect (its 95% interval excludes 0).
function moveIsClear(m, i) {
  const id = movePlanId(m, i);
  const j = id ? planIndex(id) : -1;
  if (j < 0) return true; // nothing measured: show it
  const low = lookup(`plan.items[${j}].effect.breaches.ci_low`);
  const high = lookup(`plan.items[${j}].effect.breaches.ci_high`);
  return !(typeof low === "number" && low <= 0 && high >= 0);
}

// Moves listed in full when they have a clear effect; the rest folded under one line, so the
// screen recommends what pays and still shows everything it tried.
function movesHtml(rec, indexes) {
  const clear = indexes.filter((i) => moveIsClear(rec.staffing_moves[i], i));
  const unclear = indexes.filter((i) => !clear.includes(i));
  return clear.map((i) => moveHtml(rec.staffing_moves[i], i)).join("")
    + (unclear.length ? `<details class="disclosure moves-unclear"><summary>${unclear.length} more
        ${unclear.length === 1 ? "move" : "moves"} with no clear effect</summary>
        ${unclear.map((i) => moveHtml(rec.staffing_moves[i], i)).join("")}</details>` : "");
}

// Why staffing is a small lever here, from the CP-SAT experiment (Plan v4 W5), if it is in the file.
function staffingNote() {
  const so = state.results.staffing_opt;
  if (!so || !so.test) return "";
  const p = "staffing_opt.test.candidate_minus_greedy.breach_pct";
  return `<p class="small muted staffing-note">Staffing is a small lever on this floor: the dispatcher's rescues decide most of
    the outcome. We also tried an exact roster optimiser (CP-SAT): it beats these moves on the planning score but not
    on customers (test days ${ev(p + ".mean_diff", "ratio", { signed: true })} pts
    [${ev(p + ".ci95[0]", "ratio", { signed: true, bare: true })}, ${ev(p + ".ci95[1]", "ratio", { signed: true, bare: true })}]), so these simple moves stay.
    <a href="#proof/ledger">See the rule we set first</a>.</p>`;
}

function staffingCard(rec) {
  if (!rec.staffing_moves.length) {
    return card({ title: "Staffing moves", body: `<p class="muted">No staffing change needed.</p>` });
  }
  const plans = weeklyPlans(rec);
  let body;
  if (plans) {
    // One block per week: the week's shortage before and after, then that week's moves.
    body = `<div class="grid cols-2">${plans.map(({ p, moveIndexes }) => `
      <div class="week">
        <div class="week-head">
          <h4>Days ${ev(`details.forecast.plans[${p}].first_day`, "int")}–${ev(`details.forecast.plans[${p}].last_day`, "int")}</h4>
          <span class="small muted">agent-hours short
            <strong>${ev(`details.forecast.plans[${p}].shortage_before`, "num")}</strong> →
            <strong>${ev(`details.forecast.plans[${p}].shortage_after`, "num")}</strong></span>
        </div>
        ${movesHtml(rec, moveIndexes)}
      </div>`).join("")}</div>${staffingNote()}`;
  } else {
    body = movesHtml(rec, rec.staffing_moves.map((m, i) => i)) + staffingNote();
  }
  return `<div id="rec-staffing"><p class="small muted">From the forecast: the same people and the same hours, but a shift starts
    earlier or later, or a day off moves to a quieter day.</p>${body}</div>`;
}

// Group the moves by week using details.forecast.plans (the engine lists the moves in plan
// order). Returns null when the plans are missing or do not line up, and we show a flat list.
function weeklyPlans(rec) {
  const d = state.results.details;
  if (!d || !d.forecast || !Array.isArray(d.forecast.plans)) return null;
  const groups = [];
  let k = 0;
  for (let p = 0; p < d.forecast.plans.length; p++) {
    const plan = d.forecast.plans[p];
    const moveIndexes = [];
    for (const move of plan.moves) {
      const listed = rec.staffing_moves[k];
      if (!listed || listed.agents[0] !== move.agent_id) return null;
      moveIndexes.push(k);
      k++;
    }
    groups.push({ plan, p, moveIndexes });
  }
  return k === rec.staffing_moves.length ? groups : null;
}

// results.plan lists the staffing moves first, in the same order as staffing_moves (same agent, same
// week); the server only knows those ids ("staff_43_C02"), so a move without one cannot be planned.
function movePlanId(m, i) {
  const plan = state.results.plan;
  const it = plan && plan.items && plan.items[i];
  return it && it.kind === "staffing" && it.change.agent_id === m.agents[0] ? it.id : null;
}

function moveHtml(m, i) {
  const base = `recommendations.staffing_moves[${i}]`;
  const id = movePlanId(m, i);
  if (id) registerItem({ id, world: "food", title: m.text, owner: "Team lead", simulable: true });
  const j = id ? planIndex(id) : -1;
  const effects = Object.keys(m.expected_effect).map((kpi) => {
    const unit = spreadUnit(kpiInfo(kpi).unit);
    return `${escapeHtml(kpiInfo(kpi).label)} ${ev(`${base}.expected_effect.${kpi}`, unit, { signed: true })}`;
  }).join(" · ");
  return `<div class="move" id="move-${i}">
      <div>
        <div class="move-text">${evText(base + ".text")}</div>
        ${effects ? `<div class="small muted">Expected effect (simulated): ${effects}</div>` : ""}
        ${j >= 0 ? `<div class="small">Alone, customers who miss the SLA over the 14 held-out days: ${measured(`plan.items[${j}].effect.breaches`, "breaches")}</div>` : ""}
      </div>
      ${id ? planButtons(id) : ""}
    </div>`;
}
