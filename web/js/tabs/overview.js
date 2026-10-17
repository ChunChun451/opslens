// tabs/overview.js — the first screen, read top to bottom like a short story.
//
// Why: in ten seconds a judge should get the finding without knowing any jargon. So the page
// opens on the finding as one sentence ("OpsLens missed 2.2% of its promises; the industry
// standard missed 5.5%"), then the Saturday night it happened (the live floor), the three
// proofs, who it protects ("out of 100 customers"), what keeps going wrong (with a real customer
// message each), and today's AI-written brief. Every number clicks through to results.json.
//
// Example (official results, 17 Oct): "On 14 days it had never seen, OpsLens missed 2.2% of its
// promises. The industry standard missed 5.5%." Out of 100 Hindi-speaking customers: 13 vs 3.

import { state } from "../data.js";
import { ev, evText, labelFor } from "../evidence.js";
import { pageHeader, card, missing, shortLabel, comparisonIndex } from "../ui.js";
import { escapeHtml, unitForPath } from "../format.js";
import { CAUSE_LABELS, capitalize } from "./patterns.js";
import { hasMission, missionHtml, initMission } from "../mission.js";

const BREACH = "turnaround.breach_pct";

export function render(section) {
  const r = state.results;
  // Design v4: the Overview reads top to bottom like a short story — the finding as a sentence,
  // the night it happened, the proof, who it protects, what is going wrong, today's brief.
  section.innerHTML = `
    ${r.sim ? headlineHtml() : pageHeader("Overview", "")}
    ${r.sim && hasMission() ? missionHtml() : ""}
    ${proofStrip()}
    ${r.sim ? peopleHtml() : ""}
    <div class="grid cols-3-2 stretch">
      ${issuesCard()}
      ${briefCard()}
    </div>`;
  if (r.sim && hasMission()) initMission();
}

// The finding as one sentence: the type IS the hero. Numbers stay clickable to results.json.
function headlineHtml() {
  const sim = state.results.sim;
  const meta = state.results.meta;
  const best = sim.policies.baseline_d ? "baseline_d" : "baseline_b";
  const days = meta.test_days[1] - meta.test_days[0] + 1; // count of held-out days, from the results
  const i = comparisonIndex("opslens", best, BREACH);
  const ci = i >= 0
    ? `The 95% confidence range of the difference is ${ev(`sim.comparisons[${i}].ci_low`, "pts", { signed: true, bare: true })}
       to ${ev(`sim.comparisons[${i}].ci_high`, "pts", { signed: true, bare: true })} points.` : "";
  return `<header class="headline">
      <p class="headline-kicker">Every ticket is a promise to help a customer in time.</p>
      <h1 class="headline-text">On ${days} days it had never seen, OpsLens missed
        <span class="hl ours">${ev(`sim.policies.opslens.kpis.${BREACH}.mean`, "pct")}</span> of its promises.
        The ${escapeHtml(shortLabel(best).toLowerCase())} missed
        <span class="hl theirs">${ev(`sim.policies.${best}.kpis.${BREACH}.mean`, "pct")}</span>.</h1>
      <p class="headline-sub">Same tickets, same agents, same luck: we replayed each day in a fair simulator,
        once per way of working. ${ci}</p>
    </header>`;
}

// "Out of 100 customers": one dot per customer, red for a missed promise. The dot count is the
// rounded percentage (a picture of the number next to it, like a bar's width).
function peopleHtml() {
  const sim = state.results.sim;
  const best = sim.policies.baseline_d ? "baseline_d" : "baseline_b";
  const groups = [
    ["segment.p1_breach_pct", "live-order customers", "Their food is on its way and something went wrong."],
    ["segment.gold_breach_pct", "gold members", "The customers who order most."],
    ["segment.hindi_breach_pct", "Hindi-speaking customers", "Only a few agents speak Hindi and handle refunds."],
  ].filter(([kpi]) => sim.policies.opslens.kpis[kpi]);
  const grid = (pct, cls) => {
    const missed = Math.round(pct);
    return `<div class="people ${cls}" aria-hidden="true">${Array.from({ length: 100 },
      (_, k) => `<i class="${k < missed ? "m" : ""}"></i>`).join("")}</div>`;
  };
  const blocks = groups.map(([kpi, who, why]) => `
      <figure class="people-block">
        <figcaption><strong>Out of 100 ${escapeHtml(who)}</strong><span>${escapeHtml(why)}</span></figcaption>
        <div class="people-pair">
          <div>${grid(sim.policies[best].kpis[kpi].mean, "theirs")}
            <div class="people-label">${escapeHtml(shortLabel(best))}: ${ev(`sim.policies.${best}.kpis.${kpi}.mean`, "pct")} missed</div></div>
          <div>${grid(sim.policies.opslens.kpis[kpi].mean, "ours")}
            <div class="people-label"><b>OpsLens</b>: ${ev(`sim.policies.opslens.kpis.${kpi}.mean`, "pct")} missed</div></div>
        </div>
      </figure>`).join("");
  return `<section class="people-section" aria-label="Who is protected">
      <h2 class="section-title">Who gets helped in time</h2>
      <div class="people-grid">${blocks}</div>
    </section>`;
}

// Three answers to the first attacks a judge makes, each from results.json (Claude 2 review):
// "you beat strawmen" → the SLA-due sort; "you tuned on test" → a world generated after the
// freeze; "you abandon late customers" → minutes past SLA. Hidden until those sections exist.
function proofStrip() {
  const r = state.results;
  if (!r.baseline_c || !r.baseline_c.test.means) return "";
  const c = "baseline_c.test.means";
  const tiles = [
    // The strongest comparison we have: industry-standard skills routing with AI triage (D) if
    // it was run, else the "SLA due" sort (C).
    (() => {
      const best = r.baseline_c.test.means.baseline_d ? ["baseline_d", "d", "industry-standard skills routing with AI triage"]
        : ["baseline_c", "c", "the SLA-due sort"];
      return `<div class="proof">
        <div class="proof-q">Beats the industry standard</div>
        <div class="proof-a">${ev(`${c}.opslens.${BREACH}`, "pct")} <span class="muted">vs</span> ${ev(`${c}.${best[0]}.${BREACH}`, "pct")}</div>
        <div class="proof-s">Missed promises, OpsLens vs ${best[2]}. 95% CI
          ${ev(`baseline_c.test.opslens_minus_${best[1]}.${BREACH}.ci_low`, "pts", { signed: true, bare: true })} to
          ${ev(`baseline_c.test.opslens_minus_${best[1]}.${BREACH}.ci_high`, "pts", { signed: true, bare: true })} pts</div>
      </div>`;
    })(),
    `<div class="proof">
        <div class="proof-q">Late customers are not abandoned</div>
        <div class="proof-a">${ev(`${c}.opslens.quality.late_minutes_per_100`, "int")} <span class="muted">vs</span>
          ${ev(`${c}.${r.baseline_c.test.means.baseline_d ? "baseline_d" : "baseline_b"}.quality.late_minutes_per_100`, "int")}</div>
        <div class="proof-s">Minutes past the promise per 100 tickets, OpsLens vs ${r.baseline_c.test.means.baseline_d ? "the industry standard" : "urgent first"}</div>
      </div>`,
  ];
  if (r.sealed_world && r.sealed_world.test.means) {
    const s = "sealed_world.test.means";
    tiles.push(`<div class="proof">
        <div class="proof-q">Still wins on data made after we froze it</div>
        <div class="proof-a">${ev(`${s}.opslens.${BREACH}`, "pct")} <span class="muted">vs</span> ${ev(`${s}.baseline_c.${BREACH}`, "pct")}</div>
        <div class="proof-s">Missed promises, OpsLens vs due time first, on a new world (seed ${evText("sealed_world.data_seed")}) tested once</div>
      </div>`);
  }
  return `<div class="grid cols-${tiles.length} stretch proof-strip">${tiles.join("")}</div>`;
}

// Today's brief. The engine fills in the numbers with code (the LLM writes keys, never digits);
// the numbers it used are listed below the text, each clickable.
function briefCard() {
  const b = state.results.brief;
  if (!b) {
    return missing("The daily brief", "M10");
  }
  const used = b.numbers_used.map((path) =>
    `<li>${escapeHtml(labelFor(path))}: <strong>${ev(path, unitForPath(path))}</strong></li>`).join("");
  return card({
    id: "ov-brief",
    title: "Today's brief",
    actions: `<span class="pill ai-pill">${b.source === "llm" ? "Written by AI, every number filled in by code" : "Template text"}</span>`,
    body: `<p class="brief">${evText("brief.text")}</p>
      ${used ? `<details class="disclosure"><summary>Numbers in this brief</summary>
        <ul class="small muted">${used}</ul></details>` : ""}`,
  });
}

// The three strongest evidence cards. Clicking one opens it on the Patterns tab.
function issuesCard() {
  const patterns = state.results.patterns;
  if (!patterns) {
    return missing("Patterns", "M4");
  }
  const order = patterns.cards
    .map((c, index) => ({ c, index }))
    .sort((a, b) => b.c.strength - a.c.strength)
    .slice(0, 3);
  const items = order.map(({ c, index }) => {
    // A real (PII-masked) customer message makes the problem human; prefer one that went late.
    const k = c.examples.findIndex((e) => e.breached === true);
    const quote = c.examples.length
      ? `<span class="issue-quote">“${evText(`patterns.cards[${index}].examples[${Math.max(k, 0)}].text`)}”</span>` : "";
    return `
      <li class="issue" data-goto-tab="patterns" data-goto-id="card-${escapeHtml(c.id)}">
        <span class="issue-title">${evText(`patterns.cards[${index}].title`, capitalize(c.title))}</span>
        <span class="pill cause-${escapeHtml(c.cause_type)}">${escapeHtml(CAUSE_LABELS[c.cause_type] || c.cause_type)}</span>
        ${quote}
        <span class="issue-text">${evText(`patterns.cards[${index}].comparison_text`)}</span>
      </li>`;
  }).join("");
  return card({
    id: "ov-issues",
    title: "What keeps going wrong",
    sub: "Strongest evidence first. Open one to see the tickets behind it.",
    actions: `<a class="btn btn-sm" href="#patterns">All findings</a>`,
    body: `<ul class="list">${items}</ul>`,
  });
}
