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
import { pageHeader, card, missing } from "../ui.js";
import { escapeHtml, prettyKey } from "../format.js";

export function render(section) {
  const risk = state.results.risk;
  const head = pageHeader("Customers about to be let down",
    "OpsLens watches every open ticket and spots the ones that will miss their promise before it happens, says why in plain words, and what would save them.");
  if (!risk) {
    section.innerHTML = head + missing("The risk model", "M5");
    return;
  }
  section.innerHTML = `${head}
    ${trustHtml(risk)}
    <h2 class="section-title">Who you can still save, biggest difference first</h2>
    <div id="ticket-list" class="save-list">${ticketsHtml(risk)}</div>`;
}

// "Can you trust it?" in one paragraph, every number clickable.
function trustHtml(risk) {
  const rd = state.results.details && state.results.details.risk && state.results.details.risk.realdata;
  const real = typeof risk.realdata_auc === "number"
    ? ` On a real incident log from another company (ServiceNow, ${ev("risk.realdata_n", "int")} incidents) it still ranks a
       ticket that will go late above one that won't ${ev("risk.realdata_auc", "frac_pct")} of the time${rd && typeof rd.priority_rule_auc === "number"
        ? `, against ${ev("details.risk.realdata.priority_rule_auc", "frac_pct")} for "sort by priority"` : ""} (AUC).` : "";
  return `<section class="trust-strip"><h2>Can you trust it?</h2>
      <p>Of the tenth of tickets it worried about most on unseen days, ${ev("risk.top10_precision", "frac_pct")} really did
        miss their promise.${real}</p></section>`;
}

function ticketsHtml(risk) {
  if (!risk.at_risk.length) {
    return card({ body: `<p class="muted">No open tickets at risk.</p>` });
  }
  // Customers we can still save come first: rank by how much acting now lowers the risk (then by
  // risk). A manager's question is "who can I still help?", not "who is already lost?".
  const gain = (t) => (typeof t.probability_after_action === "number" ? t.probability - t.probability_after_action : 0);
  const order = risk.at_risk
    .map((ticket, index) => ({ ticket, index }))
    .sort((a, b) => gain(b.ticket) - gain(a.ticket) || b.ticket.probability - a.ticket.probability);
  // Reason bars are scaled to the biggest contribution on screen (a picture, not a number).
  let biggest = 0;
  risk.at_risk.forEach((t) => t.reasons.forEach((r) => { biggest = Math.max(biggest, Math.abs(r.contribution)); }));
  return order.map(({ ticket, index }) => ticketHtml(ticket, index, biggest)).join("");
}

// Colour the "if you act" gauge by how much acting helps, so a 100% → 99.6% case is never shown
// as good news. Thresholds are display choices: a drop of 20+ points = good, under 5 = bad.
function helpClass(before, after) {
  if (after === null) return "";
  const drop = before - after;
  return drop >= 20 ? "good" : drop < 5 ? "bad" : "meh";
}

const LANGS = { hi: "Hindi", en: "English", other: "Regional language" };
const PRIORITY_WORDS = { P1: "Live order", P2: "Recent order", P3: "General" };

function ticketHtml(t, i, biggest) {
  const base = `risk.at_risk[${i}]`;
  const before = Math.round(t.probability * 100); // only for the gauge's fill
  const after = typeof t.probability_after_action === "number" ? Math.round(t.probability_after_action * 100) : null;
  const reasons = t.reasons.map((r, j) => {
    const width = biggest > 0 ? Math.round((Math.abs(r.contribution) / biggest) * 100) : 0;
    return `<li><span class="why-bar" style="--w: ${width}%"></span>${evText(`${base}.reasons[${j}].text`)}</li>`;
  }).join("");
  return `<article class="save ${t.priority === "P1" ? "p1" : ""}" id="ticket-${escapeHtml(t.ticket_id)}">
      <div class="save-who">
        <div class="save-tags">
          <span class="tag-live">${escapeHtml(PRIORITY_WORDS[t.priority] || t.priority)}</span>
          <span>${escapeHtml(prettyKey(t.category))}</span><span>${escapeHtml(LANGS[t.language] || t.language)}</span>
        </div>
        <div class="bubble big"><p>${evText(base + ".text")}</p>
          <span class="bubble-meta">${evText(base + ".ticket_id")} · ${evText(base + ".created_at")}</span></div>
        <div class="save-clock"><b>${ev(base + ".minutes_to_sla", "min")}</b> left on this customer's promise</div>
      </div>
      <div class="save-why">
        <div class="save-h">Why OpsLens is worried</div>
        <ul class="why">${reasons}</ul>
      </div>
      <div class="save-fix">
        <div class="save-h">Chance we miss it</div>
        <div class="gauge-row">
          <div class="gauge bad" style="--p: ${before}"><span>${ev(base + ".probability", "frac_pct")}</span><small>now</small></div>
          ${after === null ? "" : `<div class="gauge-arrow" aria-hidden="true"></div>
          <div class="gauge ${helpClass(before, after)}" style="--p: ${after}"><span>${ev(base + ".probability_after_action", "frac_pct")}</span><small>if you act</small></div>`}
        </div>
        ${t.action ? `<div class="save-action ${helpClass(before, after)}"><b>Do this:</b> ${evText(base + ".action")}
          ${after !== null && helpClass(before, after) === "bad" ? `<span class="save-note">Acting now barely changes the odds: this customer
            will probably be late, so tell them now and escalate.</span>` : ""}</div>` : ""}
      </div>
    </article>`;
}
