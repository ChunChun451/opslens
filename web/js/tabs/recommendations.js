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
import { missing } from "../ui.js";
import { escapeHtml, kpiInfo, spreadUnit } from "../format.js";

// Every Accept / Override click, oldest first, ready to send once the server accepts them.
export const decisionLog = [];

export function render(section) {
  const rec = state.results.recommendations;
  const head = `<div class="tab-head"><div>
      <h2>Recommendations</h2>
      <p>Who should take which ticket, and staffing moves that keep the same headcount and
         agent-hours. Accept or override — every click is logged.</p>
    </div></div>`;
  if (!rec) {
    section.innerHTML = head + missing("Recommendations", "M7");
    return;
  }
  section.innerHTML = `${head}
    ${assignmentsPanel(rec)}
    ${staffingPanel(rec)}`;

  section.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => logDecision(button));
  });
}

function assignmentsPanel(rec) {
  if (!rec.assignments.length) {
    return `<div class="panel"><h3>Assignments</h3><p class="muted">No assignments right now.</p></div>`;
  }
  const rows = rec.assignments.map((a, i) => {
    const base = `recommendations.assignments[${i}]`;
    return `<tr id="assign-${i}">
        <td>${evText(base + ".ticket_id")}</td>
        <td><strong>${evText(base + ".agent_name")}</strong><div class="small muted">${evText(base + ".agent_id")}</div></td>
        <td>${evText(base + ".reason")}</td>
        <td class="num">${ev(base + ".value", "num")}</td>
        <td class="decision">${decisionButtons("assignment", i)}</td>
      </tr>`;
  }).join("");
  return `<div class="panel" id="rec-assignments">
      <h3>Assignments from the optimiser</h3>
      <p class="muted small">Min-cost flow over tickets and free agent slots. Value grows with urgency, breach risk and customer impact, minus skill-mismatch and scarcity penalties.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Ticket</th><th>Agent</th><th>Why</th><th class="num">Value</th><th>Decision</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>`;
}

function staffingPanel(rec) {
  if (!rec.staffing_moves.length) {
    return `<div class="panel"><h3>Staffing moves</h3><p class="muted">No staffing change needed.</p></div>`;
  }
  const plans = weeklyPlans(rec);
  let body;
  if (plans) {
    // One block per week: the week's shortage before and after, then that week's moves.
    body = plans.map(({ plan, p, moveIndexes }) => `
      <div class="week">
        <h4>Days ${ev(`details.forecast.plans[${p}].first_day`, "int")}–${ev(`details.forecast.plans[${p}].last_day`, "int")}:
          agent-hours short ${ev(`details.forecast.plans[${p}].shortage_before`, "num")} →
          ${ev(`details.forecast.plans[${p}].shortage_after`, "num")}</h4>
        ${moveIndexes.map((i) => moveHtml(rec.staffing_moves[i], i)).join("")}
      </div>`).join("");
  } else {
    body = rec.staffing_moves.map((m, i) => moveHtml(m, i)).join("");
  }
  return `<div class="panel" id="rec-staffing">
      <h3>Staffing moves (budget-neutral)</h3>
      <p class="muted small">Erlang C on the forecast's upper band. Only moves that keep the same people and the
         same agent-hours: start a shift earlier or later, or swap a day off.</p>
      ${body}
    </div>`;
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
  const effectKeys = Object.keys(m.expected_effect);
  const effects = effectKeys.map((kpi) => {
    const unit = spreadUnit(kpiInfo(kpi).unit);
    return `<li>${escapeHtml(kpiInfo(kpi).label)}: <strong>${ev(`${base}.expected_effect.${kpi}`, unit, { signed: true })}</strong></li>`;
  }).join("");
  const teams = m.team_from === m.team_to
    ? `<span class="chip"><b>Team</b>${evText(base + ".team_from")}</span>`
    : `<span class="chip"><b>From</b>Team ${evText(base + ".team_from")}</span>
       <span class="chip"><b>To</b>Team ${evText(base + ".team_to")}</span>`;
  return `<article class="move" id="move-${i}">
      <div class="move-row">
        <div>
          <p class="move-text"><strong>${evText(base + ".text")}</strong></p>
          <div class="chips">
            ${teams}
            <span class="chip"><b>Agents</b>${evText(base + ".agents")}</span>
            <span class="chip"><b>When</b>${evText(base + ".when")}</span>
          </div>
          ${effects ? `<div class="small"><strong>Expected effect (measured in the simulator):</strong><ul>${effects}</ul></div>` : ""}
        </div>
        <div class="decision">${decisionButtons("staffing_move", i)}</div>
      </div>
    </article>`;
}

function decisionButtons(kind, index) {
  return `<div class="btn-row">
      <button type="button" class="btn btn-small" data-decision="accept" data-kind="${kind}" data-index="${index}">Accept</button>
      <button type="button" class="btn btn-small" data-decision="override" data-kind="${kind}" data-index="${index}">Override</button>
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
  button.closest(".decision").innerHTML = `<span class="badge">${label} — logged</span>`;
}
