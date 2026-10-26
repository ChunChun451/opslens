import { state, policyKeys } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, errorBarsPlugin, policyStyle } from "../charts.js";
import { pageHeader, card, missing, fold, policyName, shortLabel, deltaPill } from "../ui.js";
import { replayHtml, initReplay } from "../replay.js";
import { escapeHtml, kpiInfo, spreadUnit, unitSuffix, KPI_GROUPS } from "../format.js";

export function render(section) {
  const sim = state.results.sim;
  const head = pageHeader("Side by side",
    "The same Saturday evening under each way of working: same customers, same agents, same luck. Press Play.");
  if (!sim) {
    section.innerHTML = head + missing("The simulator comparison", "M7");
    return;
  }
  section.innerHTML = `${head}
    ${sim.replay ? replayHtml() : card({ body: `<p class="muted">No replay in the results file yet.</p>` })}
    <div class="grid cols-2 stretch" style="margin-top: 20px">
      ${card({ title: "SLA breach rate", sub: "Mean over seeds, whiskers = ± one standard deviation", body: `<div class="chart sm"><canvas id="cmp-breach"></canvas></div>` })}
      ${card({ title: "P90 resolution time", sub: "Minutes; 90% of tickets are resolved faster", body: `<div class="chart sm"><canvas id="cmp-p90"></canvas></div>` })}
    </div>
    ${fold("Every number, under turnaround, productivity and service quality", `<p class="small muted">Held-out days
      ${ev("meta.test_days[0]", "int")}–${ev("meta.test_days[1]", "int")}, simulator seeds ${evText("sim.seeds")}. Mean ± standard
      deviation over seeds; differences paired over seeds with their 95% interval: green = clearly better, red = clearly
      worse, grey = we cannot tell.</p>${kpiTable(sim)}`, { id: "kpi-table-panel", hint: "with 95% intervals" })}`;

  kpiBarChart("cmp-breach", "turnaround.breach_pct");
  kpiBarChart("cmp-p90", "turnaround.p90_resolution_min");
  if (sim.replay) {
    initReplay();
  }
}

function kpiTable(sim) {
  const keys = policyKeys();
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
  const pairs = [];
  sim.comparisons.forEach((c) => {
    if (!pairs.some((p) => p.policy === c.policy && p.baseline === c.baseline)) {
      pairs.push({ policy: c.policy, baseline: c.baseline });
    }
  });

  const header = `<tr><th>KPI</th>
      ${keys.map((k) => `<th class="num">${policyName(k, shortLabel(k))}</th>`).join("")}
      ${pairs.map((p) => `<th class="num">${escapeHtml(shortLabel(p.policy))} vs ${escapeHtml(shortLabel(p.baseline))}</th>`).join("")}
    </tr>`;
  const body = groups.map((g) => {
    const title = KPI_GROUPS[g.name] || g.name;
    const span = 1 + keys.length + pairs.length;
    const rows = g.kpis.map((kpi) => kpiRow(sim, kpi, keys, pairs)).join("");
    return `<tr class="group"><th colspan="${span}">${escapeHtml(title)}</th></tr>${rows}`;
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
  const diffCells = pairs.map((p) => {
    const i = sim.comparisons.findIndex((c) => c.policy === p.policy && c.baseline === p.baseline && c.kpi === kpi);
    if (i < 0) {
      return `<td class="num muted">—</td>`;
    }
    const base = `sim.comparisons[${i}]`;
    const unit = spreadUnit(info.unit);
    const c = sim.comparisons[i];
    const unclear = c.ci_low <= 0 && c.ci_high >= 0;
    return `<td class="num ${unclear ? "ci-unclear" : ""}">${deltaPill(base, unit, info.better)}
        <span class="pm">[${ev(base + ".ci_low", unit, { signed: true, bare: true })}, ${ev(base + ".ci_high", unit, { signed: true, bare: true })}]</span></td>`;
  }).join("");
  const arrow = info.better === "lower" ? `<span class="better" title="lower is better">↓</span>`
    : info.better === "higher" ? `<span class="better" title="higher is better">↑</span>` : "";
  return `<tr>
      <td>${escapeHtml(info.label)}${suffix ? ` <span class="muted">(${escapeHtml(suffix)})</span>` : ""}${arrow}</td>
      ${cells}${diffCells}
    </tr>`;
}

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

function kpiBarChart(canvasId, kpi) {
  const sim = state.results.sim;
  const keys = policyKeys().filter((k) => sim.policies[k].kpis[kpi]);
  const unit = kpiInfo(kpi).unit;
  let top = 0;
  keys.forEach((k) => { top = Math.max(top, sim.policies[k].kpis[kpi].mean + sim.policies[k].kpis[kpi].std); });
  makeChart(document.getElementById(canvasId), {
    type: "bar",
    data: {
      labels: keys.map((k) => shortLabel(k)),
      datasets: [{
        label: kpiInfo(kpi).label,
        data: keys.map((k) => sim.policies[k].kpis[kpi].mean),
        errors: keys.map((k) => sim.policies[k].kpis[kpi].std),
        backgroundColor: keys.map((k) => policyStyle(k).color),
        borderRadius: 6,
        maxBarThickness: 72,
      }],
    },
    options: {
      scales: { y: { beginAtZero: true, suggestedMax: top * 1.08 }, x: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
    plugins: [errorBarsPlugin],
  }, (datasetIndex, index) => ({ path: `sim.policies.${keys[index]}.kpis.${kpi}.mean`, unit }));
}
