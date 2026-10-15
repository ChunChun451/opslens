// tabs/recommendations.js — what OpsLens would do now: assignments and staffing moves.
//
// Why: "recommend actions" with a reason for each one, and a human in charge. Accept and
// Override are logged (overrides are a learning signal, CLAUDE.md section 8). Until the
// server exists (M9) the log goes to the browser console and to `decisionLog` below.
//
// Example (fixture): ticket T000003 -> Kavita D. (B01), "Hindi refund, 91% breach risk,
// Kavita is one of 3 agents with both skills"; staffing: move 3 Team D agents to Team C,
// Sat-Sun 19:00-23:00, expected breach change −1.2 pts.

import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { missing } from "../ui.js";
import { escapeHtml, kpiInfo, spreadUnit } from "../format.js";

// Every Accept / Override click, oldest first. M9 will send these to the server.
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
  const moves = rec.staffing_moves.map((m, i) => {
    const base = `recommendations.staffing_moves[${i}]`;
    const effects = Object.keys(m.expected_effect).map((kpi) => {
      const unit = spreadUnit(kpiInfo(kpi).unit);
      return `<li>${escapeHtml(kpiInfo(kpi).label)}: <strong>${ev(`${base}.expected_effect.${kpi}`, unit, { signed: true })}</strong></li>`;
    }).join("");
    return `<article class="move" id="move-${i}">
        <p class="move-text"><strong>${evText(base + ".text")}</strong></p>
        <div class="chips">
          <span class="chip"><b>From</b>Team ${evText(base + ".team_from")}</span>
          <span class="chip"><b>To</b>Team ${evText(base + ".team_to")}</span>
          <span class="chip"><b>Agents</b>${evText(base + ".agents")}</span>
          <span class="chip"><b>When</b>${evText(base + ".when")}</span>
        </div>
        <div class="small"><strong>Expected effect (measured in the simulator):</strong><ul>${effects}</ul></div>
        <div class="decision">${decisionButtons("staffing_move", i)}</div>
      </article>`;
  }).join("");
  return `<div class="panel" id="rec-staffing">
      <h3>Staffing moves (budget-neutral)</h3>
      <p class="muted small">Erlang C on the forecast's upper band; only moves that keep headcount and agent-hours the same.</p>
      ${moves}
    </div>`;
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
  console.log("[OpsLens] decision logged (server log arrives in M9):", entry);
  const label = entry.decision === "accept" ? "Accepted" : "Overridden";
  button.closest(".decision").innerHTML = `<span class="badge">${label} — logged</span>`;
}
