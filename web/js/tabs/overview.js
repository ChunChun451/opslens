// tabs/overview.js — the first screen: breach rate per policy, backlog, top 3 issues, brief.
//
// Why: in ten seconds a judge should see the headline (breaches on held-out days, with the
// paired 95% CI against each baseline) and the three biggest problems we found.
//
// Example: with the fixture, the big numbers read 13.0% / 6.8% / 4.1% and the line below says
// "OpsLens − Baseline A: −8.9 pts (paired 95% CI −9.7 to −8.1 pts, n = 5 seeds)".

import { state, policyKeys, policyLabel } from "../data.js";
import { ev, evText } from "../evidence.js";
import { policyName, policyBorder, missing } from "../ui.js";
import { escapeHtml, kpiInfo, spreadUnit, unitForPath } from "../format.js";
import { CAUSE_LABELS } from "./patterns.js";

const BREACH = "turnaround.breach_pct";

export function render(section) {
  const r = state.results;
  section.innerHTML = `
    <div class="tab-head">
      <div>
        <h2>Overview</h2>
        <p>Held-out test days ${ev("meta.test_days[0]", "int")}–${ev("meta.test_days[1]", "int")},
           replayed in the simulator on seeds ${evText("sim.seeds")}.
           Generated tickets: ${ev("meta.n_tickets", "int")}.</p>
      </div>
    </div>
    ${r.sim ? headline() : missing("The simulator comparison", "M7")}
    ${r.sim ? `<div class="grid-2">
        ${kpiStrip("turnaround.max_backlog", "Max backlog (tickets waiting at once)")}
        ${kpiStrip("turnaround.p90_resolution_min", "P90 resolution time")}
      </div>` : ""}
    <div class="grid-2">
      ${topIssues()}
      ${brief()}
    </div>`;
}

// The big panel: breach rate per policy + the paired CIs.
function headline() {
  const sim = state.results.sim;
  const cells = policyKeys().map((key) => {
    const path = `sim.policies.${key}.kpis.${BREACH}`;
    return `<div class="policy-cell" style="${policyBorder(key)}">
        ${policyName(key)}
        <div class="tile-value big">${ev(path + ".mean", "pct")}</div>
        <div class="tile-sub">± ${ev(path + ".std", "pts")} across seeds</div>
      </div>`;
  }).join("");
  const lines = [];
  sim.comparisons.forEach((c, i) => {
    if (c.kpi !== BREACH) return;
    const base = `sim.comparisons[${i}]`;
    lines.push(`<li><strong>${escapeHtml(policyLabel(c.policy))} − ${escapeHtml(policyLabel(c.baseline))}:</strong>
      ${ev(base + ".mean_diff", "pts", { signed: true })}
      <span class="muted">(paired 95% CI ${ev(base + ".ci_low", "pts", { signed: true })} to
      ${ev(base + ".ci_high", "pts", { signed: true })}, n = ${ev(base + ".n", "int")} seeds)</span></li>`);
  });
  return `<div class="panel" id="ov-headline">
      <h3>SLA breach rate on held-out test days</h3>
      <div class="policy-row">${cells}</div>
      ${lines.length ? `<ul class="headline">${lines.join("")}</ul>` : ""}
    </div>`;
}

// A smaller panel with one KPI for every policy.
function kpiStrip(kpiKey, title) {
  const unit = kpiInfo(kpiKey).unit;
  const cells = policyKeys().map((key) => {
    const path = `sim.policies.${key}.kpis.${kpiKey}`;
    return `<div class="policy-cell" style="${policyBorder(key)}">
        ${policyName(key)}
        <div class="tile-value">${ev(path + ".mean", unit)}</div>
        <div class="tile-sub">± ${ev(path + ".std", spreadUnit(unit))}</div>
      </div>`;
  }).join("");
  return `<div class="panel strip"><h3>${escapeHtml(title)}</h3><div class="policy-row">${cells}</div></div>`;
}

// The three strongest evidence cards, each linking to the Patterns tab.
function topIssues() {
  const patterns = state.results.patterns;
  if (!patterns) {
    return missing("Patterns", "M4");
  }
  const order = patterns.cards
    .map((card, index) => ({ card, index }))
    .sort((a, b) => b.card.strength - a.card.strength)
    .slice(0, 3);
  const items = order.map(({ card, index }) => `
      <li class="issue">
        <span class="cause">${escapeHtml(CAUSE_LABELS[card.cause_type] || card.cause_type)}</span>
        <div><strong>${evText(`patterns.cards[${index}].title`)}</strong></div>
        <div class="muted small">${evText(`patterns.cards[${index}].comparison_text`)}</div>
      </li>`).join("");
  return `<div class="panel" id="ov-issues">
      <h3>Top 3 issues</h3>
      <ol class="issue-list">${items}</ol>
      <a class="btn btn-small" href="#patterns">All evidence cards →</a>
    </div>`;
}

// Today's brief. The text comes from the engine with numbers already filled in by code
// (the LLM writes keys, never digits); we also list the numbers it used, each clickable.
function brief() {
  const b = state.results.brief;
  if (!b) {
    return missing("The daily brief", "M10");
  }
  const used = b.numbers_used.map((path) => `
      <li><code>${escapeHtml(path)}</code> = ${ev(path, unitForPath(path))}</li>`).join("");
  return `<div class="panel" id="ov-brief">
      <h3>Today's brief <span class="badge">${b.source === "llm" ? "written by LLM, numbers by code" : "template"}</span></h3>
      <p class="brief-text">${evText("brief.text")}</p>
      ${used ? `<div class="small muted">Numbers used:</div><ul class="small">${used}</ul>` : ""}
    </div>`;
}
