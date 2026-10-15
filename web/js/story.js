// story.js — the guided 6-step walkthrough for the demo.
//
// Why: in a five-minute pitch the order matters. Story mode walks the judges through
// problem -> replay -> pattern -> at-risk ticket -> recommendation + impact -> their turn.
// Each step switches tab, outlines the element being discussed in red, and explains it in
// two or three sentences. Numbers in the story text are ev() numbers too: read from the JSON
// and clickable. Next / Back (or the arrow keys) move; Esc closes.
//
// Example step 4 (fixture): "T000003 has a 92% chance of breaching, 12 min before its SLA.
// Top reason: 18 tickets ahead in queue (+0.21). If we assign to a free skilled agent now,
// the risk falls to 35%."

import { state, policyLabel } from "./data.js";
import { ev, evText } from "./evidence.js";
import { showTab } from "./router.js";
import { startReplay, pauseReplay } from "./replay.js";
import { escapeHtml } from "./format.js";
import { CAUSE_LABELS } from "./tabs/patterns.js";

const BREACH = "turnaround.breach_pct";

const STEPS = [
  { tab: "overview", target: "#ov-headline", title: "The problem", body: problemText },
  { tab: "compare", target: "#replay", title: "The same evening, three ways", body: replayText, enter: startReplay },
  { tab: "patterns", target: "#tab-patterns .evidence-card", title: "A pattern, with evidence", body: patternText },
  { tab: "atrisk", target: storyTicketId, title: "One ticket, before it is late", body: ticketText },
  { tab: "recommendations", target: "#rec-staffing", title: "What to do, and what it is worth", body: impactText },
  { tab: "whatif", target: "#whatif-form", title: "Your turn", body: yourTurnText },
];

let step = -1; // -1 = story mode is off
let highlighted = null;

export function initStory() {
  document.getElementById("story-button").addEventListener("click", () => goTo(0));
  document.getElementById("story-card").addEventListener("click", (event) => {
    if (event.target.closest("#story-next")) next();
    if (event.target.closest("#story-back")) goTo(Math.max(0, step - 1));
    if (event.target.closest("#story-close")) stop();
  });
  document.addEventListener("keydown", (event) => {
    if (step < 0) return;
    // Arrow keys on a slider or a dropdown belong to that control, not to the story.
    if (event.target.matches("input, select, textarea")) return;
    if (event.key === "Escape") stop();
    if (event.key === "ArrowRight") next();
    if (event.key === "ArrowLeft") goTo(Math.max(0, step - 1));
  });
}

function next() {
  if (step >= STEPS.length - 1) {
    stop();
  } else {
    goTo(step + 1);
  }
}

function goTo(i) {
  clearHighlight();
  pauseReplay();
  step = i;
  const s = STEPS[step];
  showTab(s.tab);
  // A target is a CSS selector, or a function that returns an element id (chosen from the data).
  const target = typeof s.target === "function"
    ? document.getElementById(s.target())
    : document.querySelector(s.target);
  if (target) {
    target.classList.add("story-target");
    highlighted = target;
    // Scroll it to the top of the screen: the story card sits at the bottom.
    target.scrollIntoView({ block: "start", behavior: "smooth" });
  }
  renderCard();
  if (s.enter) s.enter();
}

function stop() {
  clearHighlight();
  pauseReplay();
  step = -1;
  document.getElementById("story-card").hidden = true;
}

function clearHighlight() {
  if (highlighted) {
    highlighted.classList.remove("story-target");
    highlighted = null;
  }
}

function renderCard() {
  const s = STEPS[step];
  const card = document.getElementById("story-card");
  // Progress dashes: one per step, the ones done so far filled in.
  const dots = STEPS.map((_, i) => `<span class="${i <= step ? "on" : ""}"></span>`).join("");
  card.innerHTML = `
    <div class="story-top">
      <div class="story-dots" aria-hidden="true">${dots}</div>
      <div class="story-step">Story mode · step ${step + 1} of ${STEPS.length}</div>
    </div>
    <h3>${escapeHtml(s.title)}</h3>
    <p>${s.body()}</p>
    <div class="btn-row">
      <button type="button" class="btn btn-primary" id="story-next">${step === STEPS.length - 1 ? "Finish" : "Next"}</button>
      <button type="button" class="btn" id="story-back" ${step === 0 ? "disabled" : ""}>Back</button>
      <button type="button" class="btn" id="story-close" style="margin-left: auto">Close · Esc</button>
    </div>`;
  card.hidden = false;
  card.querySelector("#story-next").focus();
}

// ---- Step texts. Every number is ev() / evText(): read from the JSON, never typed in. -----

function breachPath(policy) {
  return `sim.policies.${policy}.kpis.${BREACH}.mean`;
}

function problemText() {
  if (!state.results.sim) return "The simulator results are not in the results file yet.";
  return `Helpdesk tools tell you a ticket is already late. On held-out test days a
    first-come-first-served floor (${escapeHtml(policyLabel("baseline_a"))}) breaches
    ${ev(breachPath("baseline_a"), "pct")} of SLAs; priority-first (${escapeHtml(policyLabel("baseline_b"))})
    breaches ${ev(breachPath("baseline_b"), "pct")}. OpsLens: ${ev(breachPath("opslens"), "pct")}.
    Click any number to see where it comes from.`;
}

function replayText() {
  const replay = state.results.sim && state.results.sim.replay;
  if (!replay) return "No replay in the results file yet.";
  const last = replay.times.length - 1;
  return `${evText("sim.replay.title")}. Same tickets and the same luck for every policy;
    only the decisions differ. By the end of the evening:
    ${escapeHtml(policyLabel("baseline_a"))} ${ev(`sim.replay.series.baseline_a.breached_cum[${last}]`, "int")} breaches,
    ${escapeHtml(policyLabel("baseline_b"))} ${ev(`sim.replay.series.baseline_b.breached_cum[${last}]`, "int")},
    OpsLens ${ev(`sim.replay.series.opslens.breached_cum[${last}]`, "int")}.`;
}

function patternText() {
  const p = state.results.patterns;
  if (!p || !p.cards.length) return "Patterns are not in the results file yet.";
  let top = 0;
  p.cards.forEach((card, i) => { if (card.strength > p.cards[top].strength) top = i; });
  const card = p.cards[top];
  return `${evText(`patterns.cards[${top}].title`)} — ${evText(`patterns.cards[${top}].comparison_text`)}.
    Cause: ${escapeHtml(CAUSE_LABELS[card.cause_type] || card.cause_type)}. Each card shows the volume affected,
    why it is not a known event, and real (masked) example tickets.`;
}

// The ticket where acting now helps most (biggest drop from probability to
// probability_after_action); without "after action" numbers, the riskiest ticket.
// A choice made by comparing JSON values; no new number is shown.
function storyTicket() {
  const list = state.results.risk.at_risk;
  const drop = (t) => (typeof t.probability_after_action === "number" ? t.probability - t.probability_after_action : -1);
  let best = 0;
  list.forEach((t, i) => {
    const better = drop(t) > drop(list[best]) || (drop(t) === drop(list[best]) && t.probability > list[best].probability);
    if (better) best = i;
  });
  return { ticket: list[best], index: best };
}

function storyTicketId() {
  const risk = state.results.risk;
  return risk && risk.at_risk.length ? "ticket-" + storyTicket().ticket.ticket_id : "";
}

function ticketText() {
  const risk = state.results.risk;
  if (!risk || !risk.at_risk.length) return "The risk model is not in the results file yet.";
  const { ticket: t, index: top } = storyTicket();
  const base = `risk.at_risk[${top}]`;
  const reason = t.reasons.length ? ` Top reason: ${evText(base + ".reasons[0].text")}.` : "";
  const action = t.action && typeof t.probability_after_action === "number"
    ? ` If we ${evText(base + ".action")}, the risk falls to ${ev(base + ".probability_after_action", "frac_pct")}.`
    : "";
  return `${evText(base + ".ticket_id")} has a ${ev(base + ".probability", "frac_pct")} chance of breaching,
    ${ev(base + ".minutes_to_sla", "min")} before its SLA.${reason}${action}`;
}

function impactText() {
  const r = state.results;
  const parts = [];
  const plans = r.details && r.details.forecast && r.details.forecast.plans;
  if (plans && plans.length) {
    const p = "details.forecast.plans[0]";
    parts.push(`For days ${ev(p + ".first_day", "int")}–${ev(p + ".last_day", "int")} a few shift changes, with the same
      people and the same agent-hours, cut the forecast shortage from ${ev(p + ".shortage_before", "num")} to
      ${ev(p + ".shortage_after", "num")} agent-hours; every assignment comes with its reason.`);
  } else if (r.recommendations && r.recommendations.staffing_moves.length) {
    parts.push(`${evText("recommendations.staffing_moves[0].text")} — same headcount, same agent-hours.`);
  }
  if (r.sim) {
    const i = r.sim.comparisons.findIndex((c) => c.policy === "opslens" && c.baseline === "baseline_a" && c.kpi === BREACH);
    if (i >= 0) {
      const base = `sim.comparisons[${i}]`;
      parts.push(`Over all test days, OpsLens − ${escapeHtml(policyLabel("baseline_a"))} on breaches:
        ${ev(base + ".mean_diff", "pts", { signed: true })} (paired 95% CI
        ${ev(base + ".ci_low", "pts", { signed: true })} to ${ev(base + ".ci_high", "pts", { signed: true })}).`);
    }
  }
  return parts.length ? parts.join(" ") : "Recommendations are not in the results file yet.";
}

function yourTurnText() {
  return `Change the staffing or the volume and re-run the simulator on a held-out day. Or open
    Patterns and press <strong>Plant a problem</strong>: we hide a problem in fresh data and
    OpsLens has to find it without being told where it is.`;
}
