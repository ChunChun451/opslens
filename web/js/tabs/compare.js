// tabs/compare.js — Baseline A vs Baseline B vs OpsLens on the held-out test days.
//
// Why: this is moat number one, "proof, not promises". Every KPI is shown under the problem
// statement's three headings (turnaround, productivity, service quality) as mean ± std over
// seeds, with the paired 95% CI wherever the engine computed one. Then the replay.
//
// Example (real results, 16 Oct): SLA breach rate 13.1 ± 2.2 / 6.8 ± 1.3 / 2.4 ± 0.5 (%);
// OpsLens − Baseline A = −10.7 pts, CI [−12.9, −8.5]. A CI that includes zero (P99 wait vs
// Baseline A: −84 [−276, +107]) is shown in grey: no clear difference.

import { state, policyKeys, policyLabel } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, errorBarsPlugin, policyStyle } from "../charts.js";
import { policyName, missing } from "../ui.js";
import { replayHtml, initReplay } from "../replay.js";
import { escapeHtml, kpiInfo, spreadUnit, unitSuffix, KPI_GROUPS } from "../format.js";

export function render(section) {
  const sim = state.results.sim;
  const head = `<div class="tab-head"><div>
      <h2>Baseline vs OpsLens</h2>
      <p>Held-out days ${ev("meta.test_days[0]", "int")}–${ev("meta.test_days[1]", "int")}, seeds ${evText("sim.seeds")}.
         Same tickets, same luck (common random numbers), same decision cadence, same agents and agent-hours.</p>
    </div></div>`;
  if (!sim) {
    section.innerHTML = head + missing("The simulator comparison", "M7");
    return;
  }
  section.innerHTML = `${head}
    <div class="panel" id="kpi-table-panel">
      <h3>Results table</h3>
      ${kpiTable(sim)}
      <p class="panel-note">Bold = best policy on that row. Cells are mean ± standard deviation over seeds.
         The last columns are paired differences with their 95% CI (same seed = same luck); grey = the CI
         includes zero (no clear difference); — means not computed.</p>
    </div>
    <div class="grid-2">
      <div class="panel"><h3>SLA breach rate (%)</h3><div class="chart-box"><canvas id="cmp-breach"></canvas></div></div>
      <div class="panel"><h3>P90 resolution time (min)</h3><div class="chart-box"><canvas id="cmp-p90"></canvas></div></div>
    </div>
    ${sim.replay ? replayHtml() : `<div class="panel muted">No replay in the results file yet.</div>`}`;

  kpiBarChart("cmp-breach", "turnaround.breach_pct");
  kpiBarChart("cmp-p90", "turnaround.p90_resolution_min");
  if (sim.replay) {
    initReplay();
  }
}

function kpiTable(sim) {
  const keys = policyKeys();
  // KPIs in the order the engine wrote them, grouped by the part before the first dot.
  const kpiKeys = Object.keys(sim.policies[keys[0]].kpis);
  const groups = [];
  kpiKeys.forEach((kpi) => {
    const group = kpi.split(".")[0];
    let entry = groups.find((g) => g.name === group);
    if (!entry) {
      entry = { name: group, kpis: [] };
      groups.push(entry);
    }
    entry.kpis.push(kpi);
  });
  // One CI column per (policy, baseline) pair found in the comparisons.
  const pairs = [];
  sim.comparisons.forEach((c) => {
    if (!pairs.some((p) => p.policy === c.policy && p.baseline === c.baseline)) {
      pairs.push({ policy: c.policy, baseline: c.baseline });
    }
  });

  const header = `<tr><th>KPI</th>
      ${keys.map((k) => `<th class="num">${policyName(k)}</th>`).join("")}
      ${pairs.map((p) => `<th class="num">${escapeHtml(policyLabel(p.policy))} − ${escapeHtml(policyLabel(p.baseline))}<div class="small">paired 95% CI</div></th>`).join("")}
    </tr>`;
  const body = groups.map((g) => {
    const title = KPI_GROUPS[g.name] || g.name;
    const span = 1 + keys.length + pairs.length;
    const rows = g.kpis.map((kpi) => kpiRow(sim, kpi, keys, pairs)).join("");
    return `<tr class="group-row"><th colspan="${span}">${escapeHtml(title)}</th></tr>${rows}`;
  }).join("");
  return `<div class="table-wrap"><table class="kpi-table"><thead>${header}</thead><tbody>${body}</tbody></table></div>`;
}

function kpiRow(sim, kpi, keys, pairs) {
  const info = kpiInfo(kpi);
  const suffix = unitSuffix(info.unit);
  const best = bestPolicy(sim, kpi, keys, info.better);
  const cells = keys.map((k) => {
    const path = `sim.policies.${k}.kpis.${kpi}`;
    return `<td class="num ${k === best ? "best" : ""}">${ev(path + ".mean", info.unit, { bare: true })}
        <span class="pm">± ${ev(path + ".std", spreadUnit(info.unit), { bare: true })}</span></td>`;
  }).join("");
  const ciCells = pairs.map((p) => {
    const i = sim.comparisons.findIndex((c) => c.policy === p.policy && c.baseline === p.baseline && c.kpi === kpi);
    if (i < 0) {
      return `<td class="num muted">—</td>`;
    }
    const base = `sim.comparisons[${i}]`;
    const unit = spreadUnit(info.unit);
    // A CI that includes zero means "no clear difference": shown in grey, not hidden.
    const c = sim.comparisons[i];
    const unclear = c.ci_low <= 0 && c.ci_high >= 0;
    return `<td class="num ${unclear ? "ci-unclear" : ""}">${ev(base + ".mean_diff", unit, { signed: true, bare: true })}
        <span class="pm">[${ev(base + ".ci_low", unit, { signed: true, bare: true })},
        ${ev(base + ".ci_high", unit, { signed: true, bare: true })}]</span></td>`;
  }).join("");
  const direction = info.better === "lower" ? "lower is better" : info.better === "higher" ? "higher is better" : "";
  return `<tr>
      <td>${escapeHtml(info.label)}${suffix ? ` <span class="muted">(${escapeHtml(suffix)})</span>` : ""}
        ${direction ? `<div class="small muted">${direction}</div>` : ""}</td>
      ${cells}${ciCells}
    </tr>`;
}

// Which policy has the best mean on this KPI (a comparison only; no new number is shown).
function bestPolicy(sim, kpi, keys, better) {
  if (!better) return null;
  let bestKey = null;
  keys.forEach((k) => {
    const entry = sim.policies[k].kpis[kpi];
    if (!entry) return;
    const current = bestKey ? sim.policies[bestKey].kpis[kpi].mean : null;
    if (bestKey === null || (better === "lower" ? entry.mean < current : entry.mean > current)) {
      bestKey = k;
    }
  });
  return bestKey;
}

// Bars = mean per policy, whiskers = ± std over seeds.
function kpiBarChart(canvasId, kpi) {
  const sim = state.results.sim;
  const keys = policyKeys().filter((k) => sim.policies[k].kpis[kpi]);
  const unit = kpiInfo(kpi).unit;
  makeChart(document.getElementById(canvasId), {
    type: "bar",
    data: {
      labels: keys.map((k) => policyLabel(k)),
      datasets: [{
        label: kpiInfo(kpi).label,
        data: keys.map((k) => sim.policies[k].kpis[kpi].mean),
        errors: keys.map((k) => sim.policies[k].kpis[kpi].std),
        backgroundColor: keys.map((k) => policyStyle(k).color),
        borderRadius: 4,
        maxBarThickness: 110,
      }],
    },
    options: {
      scales: { y: { beginAtZero: true }, x: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
    plugins: [errorBarsPlugin],
  }, (datasetIndex, index) => ({ path: `sim.policies.${keys[index]}.kpis.${kpi}.mean`, unit }));
}
