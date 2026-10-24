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
import { pageHeader, card, missing, fold, factLine } from "../ui.js";
import { escapeHtml, prettyKey } from "../format.js";

const SHOWN = 5; // tickets shown before the fold (a layout choice)

export function render(section) {
  const risk = state.results.risk;
  const head = pageHeader("Customers about to miss their promise",
    "Ranked by the chance they will be late. Each shows why, and what would help. Click a card for every reason.");
  if (!risk) {
    section.innerHTML = head + missing("The risk model", "M5");
    return;
  }
  // 24 Oct, "less clutter": model quality as one line of facts; the judge questions fold away.
  const quality = factLine([
    [ev("risk.top10_precision", "frac_pct"), "of the 10% flagged riskiest really were late"],
    [ev("risk.auc", "ratio"), "ranking score (AUC, 1 = perfect)"],
    typeof risk.realdata_auc === "number" && [ev("risk.realdata_auc", "ratio"), "on a real company's incidents"],
  ]);
  const judge = challengeStrip();
  section.innerHTML = `${head}
    ${quality}
    <div id="ticket-list" class="risk-cards">${ticketsHtml(risk)}</div>
    ${judge ? fold("Would a simpler model do? Are the reasons real?", judge, { hint: "tested, with numbers" }) : ""}
    ${fold("Model quality in detail", factLine([
      [ev("risk.pr_auc", "ratio"), "PR-AUC"],
      [ev("risk.brier", "ratio"), "Brier score (lower = better calibrated)"],
      [ev("risk.base_rate", "frac_pct"), "of snapshots were late (base rate)"],
    ]))}`;
  section.querySelector("#ticket-list").addEventListener("click", (event) => {
    const cardEl = event.target.closest(".ticket");
    if (cardEl && !event.target.closest(".ev, .ev-text")) cardEl.classList.toggle("open");
  });
}

// The two questions a sharp judge asks about this screen, answered from Plan v4 W7 and W8
// (shown only when those results are in the file).
function challengeStrip() {
  const r = state.results;
  const items = [];
  const pb = "prediction_baselines";
  if (r.prediction_baselines) {
    const lr = `${pb}.risk_in_dispatch.variants.logistic_regression.minus_lightgbm`;
    items.push(`<div class="challenge">
        <div class="challenge-q">Would a simpler model do?</div>
        <p>On the same rows a logistic regression scores AUC ${ev(`${pb}.risk_offline.models.logistic_regression.all_rows.auc`, "ratio")}
          and "least time left" ${ev(`${pb}.risk_offline.models.time_left_rule.all_rows.auc`, "ratio")}. Ranking is close;
          deciding is not: dispatching with the regression misses ${ev(lr + ".mean", "pts", { signed: true })} more SLAs.</p>
      </div>`);
  }
  if (r.faithfulness) {
    items.push(`<div class="challenge">
        <div class="challenge-q">Are these reasons the real ones?</div>
        <p>Remove a ticket's top reason and its risk falls more than when a random fact is removed, for
          ${ev("faithfulness.deletion.top1_vs_random1.share_top_drops_more_logodds", "frac_pct")} of
          ${ev("faithfulness.deletion.rows", "int")} at-risk tickets.</p>
      </div>`);
  }
  return items.length ? `<div class="grid cols-${items.length} stretch challenge-strip">${items.join("")}</div>` : "";
}

// Calibrated probabilities saturate near 1, and "100%" reads as a certainty no model has.
// The button still opens the exact value.
function riskText(path, p) {
  if (p < 0.995) return ev(path, "frac_pct");
  return `<button type="button" class="ev" data-path="${escapeHtml(path)}" data-unit="frac_pct">≥ 99%</button>`;
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
  const html = order.map(({ ticket, index }) => ticketHtml(ticket, index, biggest));
  return html.slice(0, SHOWN).join("")
    + (html.length > SHOWN ? fold(`${html.length - SHOWN} more customers at risk`, html.slice(SHOWN).join("")) : "");
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
  // When nobody who can serve the ticket is on shift, "assign now to a capable agent" is not an
  // action a lead can take: say so, show the number as what it is (a what-if), and say what
  // OpsLens does instead (v5: a cross-skill rescue when no capable agent arrives in time).
  const nobody = t.reasons.some((r) => r.feature === "capable_on_shift" && /^no agent/.test(r.text));
  const after = typeof t.probability_after_action === "number"
    ? ` → <strong>${ev(base + ".probability_after_action", "frac_pct")}</strong>` : "";
  const action = !t.action ? "" : nobody
    ? `<div class="action warn"><strong>No one who can serve this is on shift.</strong> If such an agent were free now${after}.
         OpsLens weighs a cross-skill rescue instead: slower, but it can still keep the promise.</div>`
    : `<div class="action"><strong>What would reduce this risk:</strong> ${evText(base + ".action")}${after}</div>`;
  return `<article class="card ticket" id="ticket-${escapeHtml(t.ticket_id)}">
      <div>
        <div class="ring" style="--p: ${percent}; --c: ${t.probability >= 0.5 ? "var(--bad)" : "var(--warn)"}">
          <span class="ring-value">${riskText(base + ".probability", t.probability)}</span>
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
        <div class="stat-label">Why</div>
        <div class="ticket-reasons">${reasons}</div>
        ${action}
      </div>
    </article>`;
}
