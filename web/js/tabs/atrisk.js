// tabs/atrisk.js — open tickets ranked by breach risk, with reasons and a fix.
//
// Why: an agent lead needs to know which tickets will be late before they are late, why
// (TreeSHAP reasons from LightGBM), and what would help ("what would reduce this risk").
// Model quality numbers sit on top so nobody has to trust the ranking blindly.
//
// Example (real results): T060825, P1 app bug, 99.7% risk, 44 min to SLA. Top reason
// "44 min left of 60 min SLA". Assign now to a free agent who handles app bugs -> 8.9%.

import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, stat, missing } from "../ui.js";
import { escapeHtml, prettyKey } from "../format.js";

export function render(section) {
  const risk = state.results.risk;
  const head = pageHeader("At-risk tickets",
    "Open tickets ranked by the chance they breach their SLA, with the top reasons and what would reduce the risk.");
  if (!risk) {
    section.innerHTML = head + missing("The risk model", "M5");
    return;
  }
  const realData = typeof risk.realdata_auc === "number"
    ? `real UCI incidents: ${ev("risk.realdata_auc", "ratio")} on ${ev("risk.realdata_n", "int")}`
    : "held-out days";
  section.innerHTML = `${head}
    <div class="grid cols-4 stretch">
      ${card({ body: stat("AUC", ev("risk.auc", "ratio"), realData) })}
      ${card({ body: stat("PR-AUC", ev("risk.pr_auc", "ratio"), `base rate ${ev("risk.base_rate", "frac_pct")}`) })}
      ${card({ body: stat("Top-10% precision", ev("risk.top10_precision", "frac_pct"), "of the riskiest tenth, share that breached") })}
      ${card({ body: stat("Brier score", ev("risk.brier", "ratio"), "lower = better calibrated") })}
    </div>
    <div id="ticket-list" class="grid">${ticketsHtml(risk)}</div>`;
}

function ticketsHtml(risk) {
  if (!risk.at_risk.length) {
    return card({ body: `<p class="muted">No open tickets at risk.</p>` });
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
  const percent = Math.round(t.probability * 100); // only for the ring's fill, not shown as text
  const reasons = t.reasons.map((r, j) => {
    const width = biggest > 0 ? Math.round((Math.abs(r.contribution) / biggest) * 100) : 0;
    return `<div class="reason">
        <div class="cbar-track"><div class="reason-bar" style="width: ${width}%"></div></div>
        <div>${evText(`${base}.reasons[${j}].text`)}</div>
      </div>`;
  }).join("");
  const action = t.action
    ? `<div class="action"><strong>What would reduce this risk:</strong> ${evText(base + ".action")}
         ${typeof t.probability_after_action === "number" ? ` → <strong>${ev(base + ".probability_after_action", "frac_pct")}</strong>` : ""}</div>`
    : "";
  return `<article class="card ticket" id="ticket-${escapeHtml(t.ticket_id)}">
      <div>
        <div class="ring" style="--p: ${percent}; --c: ${t.probability >= 0.5 ? "var(--bad)" : "var(--warn)"}">
          <span class="ring-value">${ev(base + ".probability", "frac_pct")}</span>
        </div>
        <div class="ring-sub">${ev(base + ".minutes_to_sla", "min")} to SLA</div>
      </div>
      <div>
        <div class="chips">
          <span class="pill ${t.priority === "P1" ? "p1" : ""}">${escapeHtml(t.priority)}</span>
          <span class="pill">${escapeHtml(prettyKey(t.category))}</span>
          <span class="pill">${escapeHtml(t.language)}</span>
        </div>
        <p class="ticket-text">“${evText(base + ".text")}”</p>
        <div class="small muted">${evText(base + ".ticket_id")} · created ${evText(base + ".created_at")}</div>
      </div>
      <div>
        <div class="stat-label">Why (TreeSHAP reasons)</div>
        ${reasons}
        ${action}
      </div>
    </article>`;
}
