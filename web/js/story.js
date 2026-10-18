// story.js — the guided 6-step walkthrough for the demo, on the real numbers.
//
// Why: in a five-minute pitch the order matters. Story mode walks the judges through
// problem -> Saturday replay -> one pattern with evidence -> one at-risk ticket -> impact with
// CIs -> their turn. Each step switches tab, outlines the element being discussed in red, and
// explains it in two or three sentences. Every number in the story text is ev()/evText():
// read from the results file and clickable. The pattern and the ticket are CHOSEN from the
// data (rules below), so the story stays correct when the results change.
// Next / Back (or the arrow keys) move; Esc closes.
//
// Example step 4 (real results): "T060582, a P2 refund ticket, has a 99.7% chance of
// breaching ... If we assign now to a free agent who handles refund in Hindi, the risk falls
// to 29%."

import { state } from "./data.js";
import { shortLabel } from "./ui.js";
import { ev, evText } from "./evidence.js";
import { showTab } from "./router.js";
import { startReplay, pauseReplay } from "./replay.js";
import { escapeHtml, prettyKey } from "./format.js";
import { CAUSE_LABELS } from "./tabs/patterns.js";

const BREACH = "turnaround.breach_pct";

// Each step: the tab to open, a function returning the id of the element to outline, a title,
// a function writing the text, and optionally something to start (the replay).
const STEPS = [
  { tab: "overview", target: () => (document.getElementById("ov-mission") ? "ov-mission" : "ov-headline"), title: "The problem", body: problemText },
  { tab: "compare", target: () => "replay", title: "One busy Saturday, three ways", body: replayText, enter: startReplay },
  { tab: "patterns", target: storyCardId, title: "A pattern, with its evidence", body: patternText },
  { tab: "atrisk", target: storyTicketId, title: "One ticket, before it is late", body: ticketText },
  { tab: "compare", target: () => "kpi-table-panel", title: "What it is worth, with confidence intervals", body: impactText },
  { tab: "whatif", target: () => "whatif-form", title: "Your turn", body: yourTurnText },
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
  const target = document.getElementById(s.target());
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

// The paired difference (OpsLens − baseline) for one KPI: "−4.6 pts (95% CI −5.8 to −3.4)".
function diffText(baseline, kpi, unit) {
  const i = state.results.sim.comparisons.findIndex((c) => c.policy === "opslens" && c.baseline === baseline && c.kpi === kpi);
  if (i < 0) return "";
  const base = `sim.comparisons[${i}]`;
  return `${ev(base + ".mean_diff", unit, { signed: true })} (95% CI ${ev(base + ".ci_low", unit, { signed: true })} to
    ${ev(base + ".ci_high", unit, { signed: true })})`;
}

function problemText() {
  if (!state.results.sim) return "The simulator results are not in the results file yet.";
  // Lead with the strongest baseline: industry-standard skills routing if it was run.
  const best = state.results.sim.policies.baseline_d ? "baseline_d" : "baseline_b";
  return `Helpdesk tools tell you a ticket is already late. Here is a held-out Saturday dinner peak,
    replayed with the same tickets, agents and luck. On all held-out days the industry standard
    (${escapeHtml(shortLabel(best))}: skills-based routing with AI triage) misses
    ${ev(breachPath(best), "pct")} of SLAs. OpsLens: ${ev(breachPath("opslens"), "pct")}.
    Only the decisions differ. Click any number to see where it comes from.`;
}

function replayText() {
  const replay = state.results.sim && state.results.sim.replay;
  if (!replay) return "No replay in the results file yet.";
  const last = replay.times.length - 1;
  const lanes = Object.keys(replay.series).map((k) =>
    `${escapeHtml(shortLabel(k))} ${ev(`sim.replay.series.${k}.breached_cum[${last}]`, "int")}`).join(", ");
  return `${evText("sim.replay.title")}: the same tickets and the same luck for every policy;
    only the decisions differ. Breaches by the end of the evening: ${lanes}.`;
}

// The pattern the story shows: the strongest skill-gap card (Hindi refunds wait for the few
// agents who speak Hindi and know refunds), or simply the strongest card if there is none.
function storyCard() {
  const cards = state.results.patterns.cards;
  let best = -1;
  cards.forEach((c, i) => {
    if (c.cause_type === "skill_gap" && (best < 0 || c.strength > cards[best].strength)) best = i;
  });
  if (best < 0) {
    best = 0;
    cards.forEach((c, i) => { if (c.strength > cards[best].strength) best = i; });
  }
  return { card: cards[best], index: best };
}

function storyCardId() {
  const p = state.results.patterns;
  return p && p.cards.length ? "card-" + storyCard().card.id : "";
}

function patternText() {
  const p = state.results.patterns;
  if (!p || !p.cards.length) return "Patterns are not in the results file yet.";
  const { card, index } = storyCard();
  const base = `patterns.cards[${index}]`;
  const why = card.not_explained_by ? ` (${evText(base + ".not_explained_by")})` : "";
  const action = card.recommendation ? ` Suggested action: ${evText(base + ".recommendation")}.` : "";
  return `${evText(base + ".title")}: ${evText(base + ".comparison_text")}.
    Cause: ${escapeHtml(CAUSE_LABELS[card.cause_type] || card.cause_type)}${why}.${action}`;
}

// The ticket the story shows: among tickets in the story pattern's language (if it has one),
// the one where acting now helps most (biggest drop from probability to
// probability_after_action); otherwise the same rule over all tickets.
// A choice made by comparing JSON values; no new number is shown.
function storyTicket() {
  const list = state.results.risk.at_risk;
  const p = state.results.patterns;
  const language = p && p.cards.length ? storyCard().card.segment.language : null;
  const drop = (t) => (typeof t.probability_after_action === "number" ? t.probability - t.probability_after_action : -1);
  const pick = (allowed) => {
    let best = -1;
    list.forEach((t, i) => {
      if (!allowed(t)) return;
      const better = best < 0 || drop(t) > drop(list[best])
        || (drop(t) === drop(list[best]) && t.probability > list[best].probability);
      if (better) best = i;
    });
    return best;
  };
  let best = typeof language === "string" ? pick((t) => t.language === language) : -1;
  if (best < 0) best = pick(() => true);
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
  const reasons = t.reasons.slice(0, 2).map((_, j) => evText(`${base}.reasons[${j}].text`)).join("; ");
  const action = t.action && typeof t.probability_after_action === "number"
    ? ` If we ${evText(base + ".action")}, the risk falls to ${ev(base + ".probability_after_action", "frac_pct")}.`
    : "";
  return `${evText(base + ".ticket_id")}, a ${escapeHtml(t.priority)} ${escapeHtml(prettyKey(t.category).toLowerCase())}
    ticket, has a ${ev(base + ".probability", "frac_pct")} chance of breaching, ${ev(base + ".minutes_to_sla", "min")}
    before its SLA. Why: ${reasons}.${action}`;
}

function impactText() {
  const r = state.results;
  if (!r.sim) return "The simulator results are not in the results file yet.";
  const best = r.sim.policies.baseline_d ? "baseline_d" : "baseline_b";
  const hindi = r.sim.policies.opslens.kpis["segment.hindi_breach_pct"]
    ? ` Hindi tickets: ${diffText(best, "segment.hindi_breach_pct", "pts")}.` : "";
  return `Doing this for every waiting ticket, all day, over all held-out days: breaches
    ${diffText(best, BREACH, "pts")} against ${escapeHtml(shortLabel(best))}, and
    ${diffText("baseline_a", BREACH, "pts")} against ${escapeHtml(shortLabel("baseline_a"))}.${hindi}
    Every row of this table is a paired comparison over the same seeds.`;
}

function yourTurnText() {
  return `Your turn. Type a question in <strong>Ask OpsLens</strong> at the top, in English or Hinglish
    ("What if Team C loses 2 agents on Saturday?"): the LLM only understands the question, the simulator
    answers it. Or change the staffing here, or open Patterns and press <strong>Plant a problem</strong>:
    we hide a problem in fresh data and OpsLens has to find it without being told where it is.`;
}
