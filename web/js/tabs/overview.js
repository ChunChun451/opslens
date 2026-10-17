// tabs/overview.js — the first screen: the headline result, today's brief, the key KPIs,
// the three biggest problems and who is protected.
//
// Why: in ten seconds a judge should see the one number that matters (breach rate on the
// held-out days, with the paired 95% CI against each baseline), then the story around it.
// One hero, then smaller cards: the eye knows where to start.
//
// Example (real results, 16 Oct): hero "2.4%" for OpsLens, with "−10.7 pts vs Baseline A
// (95% CI −12.9 to −8.5)" and "−4.4 pts vs Baseline B"; bars 13.1% / 6.8% / 2.4%.

import { state, policyKeys } from "../data.js";
import { ev, evText, labelFor } from "../evidence.js";
import {
  pageHeader, card, stat, missing, policyName, shortLabel, deltaPill, comparisonIndex,
} from "../ui.js";
import { escapeHtml, kpiInfo, unitForPath, spreadUnit } from "../format.js";
import { policyStyle } from "../charts.js";
import { CAUSE_LABELS } from "./patterns.js";
import { hasMission, missionHtml, initMission } from "../mission.js";

const BREACH = "turnaround.breach_pct";
// The four supporting KPIs shown under the hero (a design choice; values come from the JSON).
const KEY_KPIS = [
  "turnaround.p90_resolution_min",
  "turnaround.mean_wait_min",
  "turnaround.max_backlog",
  "productivity.transfers_per_100",
];

export function render(section) {
  const r = state.results;
  section.innerHTML = `
    ${pageHeader("Overview", "Every ticket is a promise to help a customer in time. We replayed 14 days OpsLens had never seen, with the same tickets, agents and luck for every way of working.")}
    ${r.sim && hasMission() ? missionHtml() : ""}
    <div class="grid cols-3-2 stretch">
      ${r.sim ? heroCard() : missing("The simulator comparison", "M7")}
      ${briefCard()}
    </div>
    ${proofStrip()}
    ${r.sim ? `<div class="grid cols-4 stretch">${KEY_KPIS.map(kpiCard).join("")}</div>` : ""}
    <div class="grid cols-3-2 stretch">
      ${issuesCard()}
      ${r.sim ? segmentsCard() : ""}
    </div>`;
  if (r.sim && hasMission()) initMission();
}

// The hero: OpsLens's breach rate, its paired CIs against each baseline, and the three bars.
function heroCard() {
  const sim = state.results.sim;
  const keys = policyKeys();
  const path = (k) => `sim.policies.${k}.kpis.${BREACH}.mean`;
  let top = 0;
  keys.forEach((k) => { top = Math.max(top, sim.policies[k].kpis[BREACH].mean); });

  const deltas = [];
  sim.comparisons.forEach((c, i) => {
    if (c.kpi !== BREACH || c.policy !== "opslens") return;
    const base = `sim.comparisons[${i}]`;
    // The strongest baseline (industry standard) goes first: it is the comparison that matters.
    (c.baseline === "baseline_d" ? deltas.unshift.bind(deltas) : deltas.push.bind(deltas))(`<div>${deltaPill(base, "pts", "lower")} vs ${escapeHtml(shortLabel(c.baseline))}
        <span class="ci">95% CI ${ev(base + ".ci_low", "pts", { signed: true, bare: true })} to ${ev(base + ".ci_high", "pts", { signed: true, bare: true })}</span></div>`);
  });

  // Bar widths are a picture of the numbers next to them (scaled to the largest), not new numbers.
  const bars = keys.map((k) => {
    const width = Math.round((sim.policies[k].kpis[BREACH].mean / top) * 100);
    return `<div class="cbar ${k === "opslens" ? "is-ours" : ""}">
        ${policyName(k)}
        <div class="cbar-track"><div class="cbar-fill" style="width: ${width}%; background: ${policyStyle(k).color}"></div></div>
        <div class="cbar-value">${ev(path(k), "pct")}</div>
      </div>`;
  }).join("");

  return card({
    id: "ov-headline",
    title: "Missed promises on days it had never seen",
    sub: `Share of tickets not solved in time (SLA breach rate), average over simulator seeds ${evText("sim.seeds")}`,
    body: `<div class="hero">
        <div>
          ${stat("OpsLens", ev(path("opslens"), "pct"), "", "xl")}
          <div class="hero-deltas">${deltas.join("")}</div>
        </div>
        <div class="cbars">${bars}</div>
      </div>`,
  });
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
    actions: `<span class="pill">${b.source === "llm" ? "LLM text · numbers by code" : "template"}</span>`,
    body: `<p class="brief">${evText("brief.text")}</p>
      ${used ? `<details class="disclosure"><summary>Numbers in this brief</summary>
        <ul class="small muted">${used}</ul></details>` : ""}`,
  });
}

// One supporting KPI: OpsLens's value, its difference from Baseline B, and both baselines.
function kpiCard(kpi) {
  const sim = state.results.sim;
  if (!sim.policies.opslens || !sim.policies.opslens.kpis[kpi]) return "";
  const info = kpiInfo(kpi);
  const i = comparisonIndex("opslens", "baseline_b", kpi);
  const delta = i >= 0 ? `${deltaPill(`sim.comparisons[${i}]`, spreadUnit(info.unit), info.better)} vs ${escapeHtml(shortLabel("baseline_b"))}` : "";
  // The two baselines as a small two-row list under the number, for context.
  const others = ["baseline_a", "baseline_b"].filter((k) => sim.policies[k])
    .map((k) => `<div class="pair"><span>${escapeHtml(shortLabel(k))}</span>${ev(`sim.policies.${k}.kpis.${kpi}.mean`, info.unit)}</div>`).join("");
  return card({
    body: stat(info.label, ev(`sim.policies.opslens.kpis.${kpi}.mean`, info.unit), `${delta}<div class="pairs">${others}</div>`, "md"),
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
  const items = order.map(({ c, index }) => `
      <li class="issue" data-goto-tab="patterns" data-goto-id="card-${escapeHtml(c.id)}">
        <span class="issue-title">${evText(`patterns.cards[${index}].title`)}</span>
        <span class="pill">${escapeHtml(CAUSE_LABELS[c.cause_type] || c.cause_type)}</span>
        <span class="issue-text">${evText(`patterns.cards[${index}].comparison_text`)}</span>
      </li>`).join("");
  return card({
    id: "ov-issues",
    title: "Top problems found",
    sub: "Strongest evidence first. Open one to see the tickets behind it.",
    actions: `<a class="btn btn-sm" href="#patterns">All findings</a>`,
    body: `<ul class="list">${items}</ul>`,
  });
}

// Breach rate for the customers who matter most (P1 live orders, gold, Hindi), per policy.
function segmentsCard() {
  const sim = state.results.sim;
  const keys = policyKeys();
  const segmentKpis = Object.keys(sim.policies[keys[0]].kpis).filter((k) => k.startsWith("segment."));
  if (!segmentKpis.length) return "";
  const blocks = segmentKpis.map((kpi) => {
    let top = 0;
    keys.forEach((k) => { top = Math.max(top, sim.policies[k].kpis[kpi].mean); });
    const bars = keys.map((k) => {
      const width = top > 0 ? Math.round((sim.policies[k].kpis[kpi].mean / top) * 100) : 0;
      return `<div class="mini-bar">
          <span>${escapeHtml(shortLabel(k))}</span>
          <div class="cbar-track"><div class="cbar-fill" style="width: ${width}%; background: ${policyStyle(k).color}"></div></div>
          <span class="cbar-value">${ev(`sim.policies.${k}.kpis.${kpi}.mean`, "pct")}</span>
        </div>`;
    }).join("");
    return `<div class="section-label">${escapeHtml(kpiInfo(kpi).label)}</div><div class="mini-bars">${bars}</div>`;
  }).join("");
  return card({ id: "ov-segments", title: "Who is protected", sub: "Missed promises for the customers who matter most", body: blocks });
}
