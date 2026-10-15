// tabs/recommendations.js — what OpsLens would do now: assignments and staffing moves.
//
// Why: "recommend actions" with a reason for each one, and a human in charge. Accept and
// Override are logged (overrides are a learning signal, CLAUDE.md section 8). Until the
// server has an endpoint for them (proposed: POST /api/decisions) the log goes to the browser
// console and to `decisionLog` below.
//
// Example (real results): ticket T060574 -> Neha G. (A04), "P2 late delivery, English,
// waiting 12 min; low risk - served in turn". Staffing, days 43-49: six shift changes with the
// same people and hours cut the forecast shortage from 654.2 to 635.9 agent-hours.

import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, missing, initials } from "../ui.js";
import { escapeHtml, kpiInfo, spreadUnit } from "../format.js";

// Every Accept / Override click, oldest first, ready to send once the server accepts them.
export const decisionLog = [];

// Assignments shown before "Show all" (a layout choice, not a result).
const ASSIGNMENTS_SHOWN = 8;

export function render(section) {
  const rec = state.results.recommendations;
  const head = pageHeader("Recommendations",
    "Who should take which ticket right now, and staffing moves that keep the same people and the same agent-hours. Accept or override: every click is logged.");
  if (!rec) {
    section.innerHTML = head + missing("Recommendations", "M7");
    return;
  }
  section.innerHTML = `${head}
    ${assignmentsCard(rec)}
    ${staffingCard(rec)}`;

  section.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => logDecision(button));
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
        <td class="decision">${decisionButtons("assignment", i)}</td>
      </tr>`;
  };
  const head = `<thead><tr><th>Ticket</th><th>Agent</th><th>Why this agent</th><th class="num">Value</th><th></th></tr></thead>`;
  const first = rec.assignments.slice(0, ASSIGNMENTS_SHOWN).map((a, i) => row(a, i)).join("");
  const rest = rec.assignments.slice(ASSIGNMENTS_SHOWN).map((a, i) => row(a, i + ASSIGNMENTS_SHOWN)).join("");
  return card({
    id: "rec-assignments",
    title: "Assignments from the optimiser",
    sub: "Min-cost flow over waiting tickets and free agent slots. Value grows with urgency, breach risk and customer impact, minus skill-mismatch and scarcity penalties.",
    body: `<div class="table-wrap"><table>${head}<tbody>${first}</tbody></table></div>
      ${rest ? `<details class="disclosure"><summary>Show all assignments</summary>
        <div class="table-wrap"><table>${head}<tbody>${rest}</tbody></table></div></details>` : ""}`,
  });
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
        ${moveIndexes.map((i) => moveHtml(rec.staffing_moves[i], i)).join("")}
      </div>`).join("")}</div>`;
  } else {
    body = rec.staffing_moves.map((m, i) => moveHtml(m, i)).join("");
  }
  return card({
    id: "rec-staffing",
    title: "Staffing moves (budget-neutral)",
    sub: "Erlang C on the forecast's upper band. Same people, same agent-hours: start a shift earlier or later, or swap a day off.",
    body,
  });
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

function moveHtml(m, i) {
  const base = `recommendations.staffing_moves[${i}]`;
  const effects = Object.keys(m.expected_effect).map((kpi) => {
    const unit = spreadUnit(kpiInfo(kpi).unit);
    return `${escapeHtml(kpiInfo(kpi).label)} ${ev(`${base}.expected_effect.${kpi}`, unit, { signed: true })}`;
  }).join(" · ");
  return `<div class="move" id="move-${i}">
      <div>
        <div class="move-text">${evText(base + ".text")}</div>
        ${effects ? `<div class="small muted">Expected effect (simulated): ${effects}</div>` : ""}
      </div>
      <div class="decision">${decisionButtons("staffing_move", i)}</div>
    </div>`;
}

function decisionButtons(kind, index) {
  return `<div class="btn-row">
      <button type="button" class="btn btn-sm" data-decision="accept" data-kind="${kind}" data-index="${index}">Accept</button>
      <button type="button" class="btn btn-sm" data-decision="override" data-kind="${kind}" data-index="${index}">Override</button>
    </div>`;
}

// Record the click, then replace the buttons with a short status line.
function logDecision(button) {
  const kind = button.dataset.kind;
  const index = Number(button.dataset.index);
  const rec = state.results.recommendations;
  const item = kind === "assignment" ? rec.assignments[index] : rec.staffing_moves[index];
  const entry = {
    kind,
    index,
    decision: button.dataset.decision,
    item,
    at: new Date().toISOString(),
  };
  decisionLog.push(entry);
  console.log("[OpsLens] decision logged (kept in the browser until the server has /api/decisions):", entry);
  const label = entry.decision === "accept" ? "Accepted" : "Overridden";
  button.closest(".decision").innerHTML = `<span class="pill">${label} · logged</span>`;
}
