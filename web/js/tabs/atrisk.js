// tabs/atrisk.js — open tickets ranked by breach risk, with reasons and a fix.
//
// Why: an agent lead needs to know which tickets will be late before they are late, why
// (TreeSHAP reasons from LightGBM), and what would help ("what would reduce this risk").
// Model quality numbers sit on top so nobody has to trust the ranking blindly.
//
// Example (fixture): T000003, P1 payment failure in Hindi, 92% risk, 12 min to SLA.
// Top reason "18 tickets ahead in queue (+0.21)". Assign a skilled agent now -> 35%.

import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { missing } from "../ui.js";
import { escapeHtml } from "../format.js";

export function render(section) {
  const risk = state.results.risk;
  const head = `<div class="tab-head"><div>
      <h2>At-risk tickets</h2>
      <p>Open tickets ranked by the chance they breach their SLA, with the top reasons and
         what would reduce the risk.</p>
    </div></div>`;
  if (!risk) {
    section.innerHTML = head + missing("The risk model", "M5");
    return;
  }
  section.innerHTML = `${head}
    <div class="grid-4">
      <div class="panel"><div class="tile-label">AUC (held-out days)</div>
        <div class="tile-value">${ev("risk.auc", "ratio")}</div>
        <div class="tile-sub">real UCI data: ${ev("risk.realdata_auc", "ratio")} on ${ev("risk.realdata_n", "int")} incidents</div></div>
      <div class="panel"><div class="tile-label">PR-AUC</div>
        <div class="tile-value">${ev("risk.pr_auc", "ratio")}</div>
        <div class="tile-sub">base rate ${ev("risk.base_rate", "frac_pct")}</div></div>
      <div class="panel"><div class="tile-label">Top-10% precision</div>
        <div class="tile-value">${ev("risk.top10_precision", "frac_pct")}</div>
        <div class="tile-sub">of the riskiest tenth, share that breached</div></div>
      <div class="panel"><div class="tile-label">Brier score</div>
        <div class="tile-value">${ev("risk.brier", "ratio")}</div>
        <div class="tile-sub">lower = better calibrated</div></div>
    </div>
    <div id="ticket-list">${ticketsHtml(risk)}</div>`;
}

function ticketsHtml(risk) {
  if (!risk.at_risk.length) {
    return `<div class="panel muted">No open tickets at risk.</div>`;
  }
  // Rank by probability, keeping each ticket's index in the JSON for its paths.
  const order = risk.at_risk
    .map((ticket, index) => ({ ticket, index }))
    .sort((a, b) => b.ticket.probability - a.ticket.probability);
  // Reason bars are scaled to the biggest contribution on screen (a picture, not a number).
  let biggest = 0;
  risk.at_risk.forEach((t) => t.reasons.forEach((r) => { biggest = Math.max(biggest, Math.abs(r.contribution)); }));
  return order.map(({ ticket, index }) => ticketHtml(ticket, index, biggest)).join("");
}

function ticketHtml(t, i, biggest) {
  const base = `risk.at_risk[${i}]`;
  const reasons = t.reasons.map((r, j) => {
    const width = biggest > 0 ? Math.round((Math.abs(r.contribution) / biggest) * 100) : 0;
    return `<div class="reason">
        <div class="reason-bar" style="width: ${width}%"></div>
        <div>${evText(`${base}.reasons[${j}].text`)}</div>
      </div>`;
  }).join("");
  const action = t.action
    ? `<div class="action"><strong>What would reduce this risk:</strong> ${evText(base + ".action")}
         ${typeof t.probability_after_action === "number" ? `→ risk falls to ${ev(base + ".probability_after_action", "frac_pct")}` : ""}</div>`
    : "";
  return `<article class="panel ticket" id="ticket-${escapeHtml(t.ticket_id)}">
      <div class="ticket-prob">
        <div class="tile-label">Breach risk</div>
        <div class="tile-value">${ev(base + ".probability", "frac_pct")}</div>
        <div class="prob-bar"><span style="width: ${Math.round(t.probability * 100)}%"></span></div>
        <div class="tile-sub">${ev(base + ".minutes_to_sla", "min")} to SLA</div>
      </div>
      <div>
        <div class="chips">
          <span class="badge ${t.priority === "P1" ? "p1" : ""}">${escapeHtml(t.priority)}</span>
          <span class="badge">${escapeHtml(t.category)}</span>
          <span class="badge">${escapeHtml(t.language)}</span>
        </div>
        <p class="ticket-text">“${evText(base + ".text")}”</p>
        <div class="small muted">${evText(base + ".ticket_id")} · created ${evText(base + ".created_at")}</div>
      </div>
      <div>
        <div class="tile-label">Why (TreeSHAP reasons)</div>
        ${reasons}
        ${action}
      </div>
    </article>`;
}
