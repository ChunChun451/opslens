import { state } from "./data.js";
import { shortLabel } from "./ui.js";
import { ev, evText } from "./evidence.js";
import { showTab, setWorld, setSource } from "./router.js";
import { pauseReplay } from "./replay.js";
import { escapeHtml, prettyKey } from "./format.js";
import { CAUSE_LABELS } from "./tabs/patterns.js";
import { ledgerSummary } from "./tabs/ledger.js";

const BREACH = "turnaround.breach_pct";

const STEPS = [
  { tab: "overview", view: "live", target: () => firstOf(".lv-hero"), title: "The problem, live", body: problemText },
  { tab: "overview", view: "overview", target: () => "ov-thousand", title: "1,000 customers, one picture", body: thousandText },
  { tab: "patterns", target: storyCardId, title: "A pattern, with its evidence", body: patternText },
  { tab: "atrisk", target: storyTicketId, title: "One ticket, before it is late", body: ticketText },
  { tab: "compare", target: () => "kpi-table-panel", title: "What it is worth, with confidence intervals", body: impactText },
  { tab: "worlds", target: () => "wd-chart-card", title: "Beyond the world we built", body: worldsText },
  { tab: "overview", view: "rd-shadow", world: "real", target: () => firstOf(".sh-stage"), title: "A real day at a real desk", body: shadowText },
  { tab: "ledger", target: () => "ledger-tally", title: "What we bet on, and what we lost", body: ledgerText },
  { tab: "whatif", target: () => "whatif-form", title: "Your turn", body: yourTurnText },
];

function firstOf(selector) {
  const el = document.querySelector(`.tab-panel:not([hidden]) .view:not([hidden]) ${selector}`) || document.querySelector(selector);
  if (!el) return "";
  if (!el.id) el.id = "story-" + selector.replace(/[^a-z]/gi, "");
  return el.id;
}

let step = -1;
let highlighted = null;

export function initStory() {
  document.getElementById("story-button").addEventListener("click", () => { setWorld("food"); syncSwitch(); goTo(0); });
  document.getElementById("story-card").addEventListener("click", (event) => {
    if (event.target.closest("#story-next")) next();
    if (event.target.closest("#story-back")) goTo(Math.max(0, step - 1));
    if (event.target.closest("#story-close")) stop();
  });
  document.addEventListener("keydown", (event) => {
    if (step < 0) return;
    if (event.target.matches("input, select, textarea")) return;
    if (event.key === "Escape") stop();
    if (event.key === "ArrowRight") next();
    if (event.key === "ArrowLeft") goTo(Math.max(0, step - 1));
  });
}

function syncSwitch() {
  document.querySelectorAll(".world-switch [data-world]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.world === state.world)));
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
  const world = s.world || "food";
  if (world === "real" && state.realSource !== "uci") setSource("uci");
  if (state.world !== world) { setWorld(world); syncSwitch(); }
  showTab(s.tab, s.view);
  const target = document.getElementById(s.target());
  if (target && target.tagName === "DETAILS") target.open = true;
  if (target) {
    target.classList.add("story-target");
    highlighted = target;
    target.scrollIntoView({ block: "start", behavior: "smooth" });
  }
  renderCard();
  if (s.enter) s.enter();
}

function stop() {
  clearHighlight();
  pauseReplay();
  if (step >= 0 && state.world !== "food") { setWorld("food"); syncSwitch(); }
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

function breachPath(policy) {
  return `sim.policies.${policy}.kpis.${BREACH}.mean`;
}

function diffText(baseline, kpi, unit) {
  const i = state.results.sim.comparisons.findIndex((c) => c.policy === "opslens" && c.baseline === baseline && c.kpi === kpi);
  if (i < 0) return "";
  const base = `sim.comparisons[${i}]`;
  return `${ev(base + ".mean_diff", unit, { signed: true })} (95% CI ${ev(base + ".ci_low", unit, { signed: true })} to
    ${ev(base + ".ci_high", unit, { signed: true })})`;
}

function problemText() {
  if (!state.results.sim) return "The simulator results are not in the results file yet.";
  const best = state.results.sim.policies.baseline_d ? "baseline_d" : "baseline_b";
  return `Helpdesk tools tell you a ticket is already late. This is today's floor, simulated live on this
    laptop: the same customers and agents run two ways at once. On all held-out days the industry standard
    (${escapeHtml(shortLabel(best))}: skills-based routing with AI triage) misses
    ${ev(breachPath(best), "pct")} of SLAs. OpsLens: ${ev(breachPath("opslens"), "pct")}.
    Only the decisions differ. Click any number to see where it comes from.`;
}

function thousandText() {
  if (!state.results.sim) return "The simulator results are not in the results file yet.";
  const best = state.results.sim.policies.baseline_d ? "baseline_d" : "baseline_b";
  return `Each dot is one customer on the held-out days; red waited past the promised time. Click
    <strong>${escapeHtml(shortLabel(best))}</strong> (${ev(breachPath(best), "pct")}), then <strong>OpsLens</strong>
    (${ev(breachPath("opslens"), "pct")}) and watch the red ripple away. Below it, one real ticket walks through
    OpsLens step by step.`;
}

function worldsText() {
  const w = state.results.worlds;
  if (!w) return "The random-world test is not in the results file yet.";
  return `Everything so far ran on the one floor we built. So we drew ${ev("worlds.n_worlds", "int")} random floors.
    We had promised OpsLens would be the lowest in ${ev("worlds.wins_needed", "int")}; it was lowest in
    ${ev("worlds.wins", "int")}, so that rule is <strong>missed</strong>. It still beats the industry standard in
    ${ev("worlds.breakdown.beats_industry_standard", "int")} of ${ev("worlds.breakdown.of", "int")}, wins every world up to
    ${ev("worlds.breakdown.normal_load.max_load", "ratio")}× today's load, and loses only under heavy overload.`;
}

function shadowText() {
  const sh = state.results.realdesk && state.results.realdesk.shadow;
  if (!sh || !sh.shown_days.length) return "Shadow mode is not in the results file yet.";
  const s = "realdesk.shadow.shown_days[0].summary";
  return `A real company's IT desk, a real day, replayed: incidents arrive at their real times and the real outcome
    appears when it happened. OpsLens only watched. Of the ${ev(s + ".actual_misses_benchmark", "int")} deadlines the desk
    missed that day, OpsLens had warned about ${ev(s + ".opslens.caught", "int")} one hour after they opened; the
    desk's own priority field, ${ev(s + ".priority.caught", "int")}.`;
}

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
  const nobody = t.reasons.some((r) => r.feature === "capable_on_shift" && /^no agent/.test(r.text));
  const after = typeof t.probability_after_action === "number" ? ev(base + ".probability_after_action", "frac_pct") : "";
  const action = !t.action || !after ? ""
    : nobody
      ? ` Nobody who can serve it is on shift; if one were free now the risk would be ${after}. So OpsLens weighs a
        cross-skill rescue: slower, but it can still keep the promise.`
      : ` If we ${evText(base + ".action")}, the risk falls to ${after}.`;
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

function ledgerText() {
  const n = ledgerSummary();
  if (!n.total) return "The pre-registered rules are not in the results file yet.";
  return `Before every experiment we wrote down the rule that decides it, and git keeps the time. Of
    ${n.total} rules, ${n.kept} were kept and ${n.missed} were missed, and the misses stay on screen: an exact roster
    optimiser lost to our simple one, and OpsLens is not the best policy in every random world. A team that only
    shows wins is not testing hard enough.`;
}

function yourTurnText() {
  return `Your turn. Open <strong>Ask OpsLens AI</strong> in the side menu and ask it anything, in English or
    Hinglish: a tough question about our method, a what-if ("What if Team C loses 2 agents on Saturday?") or a
    customer's complaint to triage. It answers from tested results and never makes up a number. Or change the
    staffing here, or open Problems and press <strong>Plant a problem</strong>: we hide a problem in fresh data
    and OpsLens has to find it without being told where it is.`;
}
