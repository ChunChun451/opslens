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
    ${pageHeader("Overview", "Held-out test days, replayed in a fair simulator: the same tickets, the same luck and the same agents for every policy.")}
    <div class="grid cols-3-2 stretch">
      ${r.sim ? heroCard() : missing("The simulator comparison", "M7")}
      ${briefCard()}
    </div>
    ${r.sim ? `<div class="grid cols-4 stretch">${KEY_KPIS.map(kpiCard).join("")}</div>` : ""}
    <div class="grid cols-3-2 stretch">
      ${issuesCard()}
      ${r.sim ? segmentsCard() : ""}
    </div>`;
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
    deltas.push(`<div>${deltaPill(base, "pts", "lower")} vs ${escapeHtml(shortLabel(c.baseline))}
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
    title: "SLA breach rate on held-out days",
    sub: `Mean over simulator seeds ${evText("sim.seeds")}`,
    body: `<div class="hero">
        <div>
          ${stat("OpsLens", ev(path("opslens"), "pct"), "", "xl")}
          <div class="hero-deltas">${deltas.join("")}</div>
        </div>
        <div class="cbars">${bars}</div>
      </div>`,
  });
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
    sub: "Strongest evidence first · click one to see its evidence",
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
  return card({ id: "ov-segments", title: "Who is protected", sub: "Breach rate for the customers who matter most", body: blocks });
}
