// tabs/tested.js — every evaluation number in one place, what failed, and our limitations.
//
// Why: a sharp judge will ask "how do you know?". This tab answers with the evaluation from
// CLAUDE.md section 7: recall on planted problems (also blind, by type), classification,
// forecast (with its noise floor), risk (with real-data AUC and simple rules to beat),
// ablations with 95% CIs, stress tests, sensitivity, speed, and how the weights were chosen.
// It also shows, on purpose, what failed: policy v1 lost a stress test, and v2 was then
// designed on validation days only. Each number clicks through to its JSON path.
//
// Example (real results, 16 Oct): removing the risk scores raises breaches by +2.8 pts
// (paired 95% CI +1.7 to +3.9) versus full OpsLens.

import { state, policyLabel } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, errorBarsPlugin, policyStyle, INK, SLOTS } from "../charts.js";
import { missing } from "../ui.js";
import { escapeHtml, prettyKey, unitForKey } from "../format.js";

export function render(section) {
  const r = state.results;
  section.innerHTML = `
    <div class="tab-head"><div>
      <h2>How we tested</h2>
      <p>Every claim on this dashboard, how it was measured, what failed, and our limits.</p>
    </div></div>
    ${r.stress.length || details().v1_record ? honestPanel() : ""}
    <div class="grid-2">
      ${setupPanel()}
      ${r.patterns ? recallPanel() : missing("Pattern recall", "M4")}
    </div>
    <div class="grid-2">
      ${r.classification ? classificationPanel() : missing("Classification", "M3")}
      ${r.forecast ? forecastPanel() : missing("Forecast evaluation", "M6")}
    </div>
    ${r.risk ? riskPanel() : missing("Risk model evaluation", "M5")}
    ${ablationRows().length ? ablationsPanel() : missing("Ablations", "M8")}
    ${r.stress.length ? stressPanel() : missing("Stress tests", "M8")}
    <div class="grid-2">
      ${r.sensitivity.length ? genericPanel("Sensitivity", "How results move when one setting changes.", "sensitivity") : missing("Sensitivity", "M8")}
      ${r.speed ? speedPanel() : missing("Speed and scale", "M8")}
    </div>
    ${details().tuning && details().tuning.history ? tuningPanel() : ""}
    ${limitationsPanel()}`;

  if (r.risk && r.risk.calibration.length) drawCalibration();
  if (details().risk && details().risk.feature_gain) drawFeatureGain();
  if (ablationRows().length) drawAblations();
  if (r.stress.length) drawStress();
}

// The free-form `details` object (or an empty one, so `details().x` never crashes).
function details() {
  return state.results.details || {};
}

// A two-column table: label | clickable value. rows = [[label, path, unit, options], ...]
// unit "text" shows the raw value; unit "range" shows a [first, last] list as "first–last".
// Rows whose value is not in the results file are left out.
function metricTable(rows) {
  const body = rows.map(([label, path, unit, options]) => {
    const first = unit === "range" ? path + "[0]" : path;
    if (!hasValue(first)) return "";
    let value;
    if (unit === "text") {
      value = evText(path) || "—";
    } else if (unit === "range") {
      value = `${ev(path + "[0]", "int")}–${ev(path + "[1]", "int")}`;
    } else {
      value = ev(path, unit, options || {});
    }
    return `<tr><td>${escapeHtml(label)}</td><td class="num">${value}</td></tr>`;
  }).join("");
  return `<table class="metric-table"><tbody>${body}</tbody></table>`;
}

function hasValue(path) {
  let node = state.results;
  for (const part of path.replace(/\[(\d+)\]/g, ".$1").split(".")) {
    if (node === null || node === undefined || typeof node !== "object") return false;
    node = node[part];
  }
  return node !== undefined && node !== null;
}

// "OpsLens better" / "OpsLens worse" / "no clear difference", from the sign of a 95% CI of
// (OpsLens − baseline). Lower breach is better. A comparison only: no new number is shown.
function verdict(ciLow, ciHigh) {
  if (ciHigh < 0) return `<span class="verdict good">OpsLens better</span>`;
  if (ciLow > 0) return `<span class="verdict bad">OpsLens worse</span>`;
  return `<span class="verdict">no clear difference</span>`;
}

// ---- What failed, and what we changed ----------------------------------------------------

function honestPanel() {
  const d = details();
  const v1 = d.v1_record && Object.keys(d.v1_record).length ? d.v1_record : null;
  const v2 = d.design_v2 && Array.isArray(d.design_v2.rows) ? d.design_v2 : null;
  const steps = [];

  if (v1) {
    const b = "details.v1_record.test_breach_pct";
    steps.push(`<li><strong>Our first policy (v1), on the test days.</strong>
        Breach rate ${ev(b + ".opslens", "pct")} against ${ev(b + ".baseline_a", "pct")} for
        ${escapeHtml(policyLabel("baseline_a"))} and ${ev(b + ".baseline_b", "pct")} for
        ${escapeHtml(policyLabel("baseline_b"))}. Then the stress tests:
        ${stressVerdicts("details.v1_record.stress", v1.stress)}
        ${v1.note ? `<div class="small muted">Why: ${evText("details.v1_record.note")}</div>` : ""}</li>`);
  }

  if (v2) {
    steps.push(`<li><strong>What we changed, on validation days only</strong>
        (days ${ev("details.design_v2.validation_days[0]", "int")}–${ev("details.design_v2.validation_days[1]", "int")},
        seeds ${evText("details.design_v2.seeds")}). We tried these designs; the test days were not used to choose.
        ${designTable(v2)}
        ${hasValue("details.weights.aging_per_sla")
          ? `<div class="small">Chosen setting: aging per SLA = ${ev("details.weights.aging_per_sla", "num")}.</div>`
          : ""}</li>`);
  }

  steps.push(`<li><strong>${v1 ? "v2 on the test days, run once after the choice." : "The current policy on the test days."}</strong>
      Breach rate ${ev("sim.policies.opslens.kpis.turnaround.breach_pct.mean", "pct")} on normal days. Stress tests:
      ${stressVerdicts("stress", state.results.stress)}</li>`);

  const pending = !v1 || !v2
    ? `<p class="small muted">The v1 record and the validation-day design table appear here after the next
         <code>make eval</code> (they are in <code>details.v1_record</code> and <code>details.design_v2</code>).</p>`
    : "";
  return `<div class="panel honest" id="what-failed">
      <h3>What failed, and what we changed</h3>
      <ol class="honest-steps">${steps.join("")}</ol>
      ${pending}
    </div>`;
}

// One line per stress scenario: OpsLens − Baseline B with its CI and a plain verdict.
function stressVerdicts(base, rows) {
  if (!Array.isArray(rows) || !rows.length) return "";
  const items = rows.map((row, i) => {
    const path = `${base}[${i}]`;
    if (typeof row.opslens_minus_b !== "number") {
      return `<li>${evText(path + ".scenario")}: OpsLens ${ev(path + ".opslens", "pct")}</li>`;
    }
    return `<li>${evText(path + ".scenario")}: OpsLens − ${escapeHtml(policyLabel("baseline_b"))}
        ${ev(path + ".opslens_minus_b", "pts", { signed: true })}
        <span class="muted">(95% CI ${ev(path + ".ci_low", "pts", { signed: true })} to
        ${ev(path + ".ci_high", "pts", { signed: true })})</span> ${verdict(row.ci_low, row.ci_high)}</li>`;
  }).join("");
  return `<ul class="verdict-list">${items}</ul>`;
}

// The validation-day design table: one row per candidate, breach columns only (to fit).
function designTable(v2) {
  const columns = Object.keys(v2.rows[0]).filter((k) => k !== "variant" && /breach_pct$/.test(k));
  const header = columns.map((c) => `<th class="num">${escapeHtml(designHeader(c))}</th>`).join("");
  const body = v2.rows.map((row, i) => `<tr>
      <td>${evText(`details.design_v2.rows[${i}].variant`)}</td>
      ${columns.map((c) => `<td class="num">${ev(`details.design_v2.rows[${i}].${c}`, "pct", { bare: true })}</td>`).join("")}
    </tr>`).join("");
  return `<div class="table-wrap"><table class="design-table">
      <thead><tr><th>Design</th>${header}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// "+25% volume p1_breach_pct" -> "+25% volume: P1 breach %"
function designHeader(key) {
  const space = key.lastIndexOf(" ");
  const scenario = key.slice(0, space);
  const metric = key.slice(space + 1).replace(/^p1_/, "P1 ").replace(/_pct$/, " %").replace(/_/g, " ");
  return `${scenario}: ${metric}`;
}

// ---- Data, recall, classification, forecast, risk -----------------------------------------

function setupPanel() {
  const rows = [
    ["Train days", "meta.train_days", "range"],
    ["Validation days (choices made here)", "meta.validation_days", "range"],
    ["Test days (report only)", "meta.test_days", "range"],
    ["Simulator seeds (same luck for every policy)", "sim.seeds", "text"],
    ["Generated tickets", "meta.n_tickets", "int"],
    ["Data generator seed", "meta.data_seed", "text"],
    ["Generated at", "meta.generated_at", "text"],
    ["Git commit", "meta.git_commit", "text"],
    ["Evaluation run time", "meta.run_seconds", "sec"],
  ];
  return `<div class="panel"><h3>Data and fair simulator</h3>${metricTable(rows)}
      <p class="panel-note">All model, threshold and weight choices use validation days only.</p></div>`;
}

function recallPanel() {
  const p = state.results.patterns;
  const rows = [];
  if (p.recall) {
    rows.push(["Planted problems", "patterns.recall.planted", "int"]);
    rows.push(["Found", "patterns.recall.found", "int"]);
    rows.push(["False alarms (incl. decoys)", "patterns.recall.false_alarms", "int"]);
  }
  rows.push(["Live spike detected after", "patterns.live_detection_latency_min", "min"]);
  rows.push(["Live false alerts per week", "details.patterns.live_false_alerts_per_week", "num"]);
  return `<div class="panel"><h3>Finding planted problems</h3>${metricTable(rows)}
      ${p.recall ? recallDetails(p.recall) : ""}
      ${p.blind_recall ? blindTable() : ""}
      <p class="panel-note">The engine never reads the plant list; only the evaluation does.</p></div>`;
}

// Each planted problem: found? right cause? which evidence card?
function recallDetails(recall) {
  const rows = recall.details.map((item, i) => {
    const base = `patterns.recall.details[${i}]`;
    const yesNo = (key) => (typeof item[key] === "boolean" ? evText(`${base}.${key}`, item[key] ? "yes" : "no") : "—");
    return `<tr>
        <td>${evText(base + ".id")}${item.name ? ` · ${evText(base + ".name")}` : ""}</td>
        <td>${yesNo("found")}</td><td>${yesNo("diagnosed")}</td>
        <td>${item.card ? evText(base + ".card") : "—"}</td>
      </tr>`;
  }).join("");
  return `<div class="table-wrap"><table class="small">
      <thead><tr><th>Planted problem</th><th>Found</th><th>Right cause</th><th>Card</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

// Blind recall: random plants the team never saw, plus the same numbers per cause type.
function blindTable() {
  const labels = {
    sets: ["Random plant sets", "int"],
    planted: ["Problems planted", "int"],
    found: ["Found", "int"],
    found_pct: ["Found", "pct"],
    diagnosed_pct: ["Found with the right cause", "pct"],
    unplanted_cards_per_set: ["Extra cards per set (match no plant)", "num"],
    clean_set_cards: ["Cards on a clean set (nothing planted)", "int"],
    false_alarms_mean: ["False alarms per set", "num"],
  };
  const rows = Object.keys(state.results.patterns.blind_recall).map((key) => {
    const [label, unit] = labels[key] || [prettyKey(key), unitForKey(key)];
    return [`Blind recall: ${label}`, `patterns.blind_recall.${key}`, unit];
  });
  const byType = details().blind && details().blind.by_type;
  let typeTable = "";
  if (byType) {
    const body = Object.keys(byType).map((type) => {
      const base = `details.blind.by_type.${type}`;
      return `<tr><td>${escapeHtml(prettyKey(type))}</td>
          <td class="num">${ev(base + ".planted", "int")}</td>
          <td class="num">${ev(base + ".found", "int")}</td>
          <td class="num">${ev(base + ".diagnosed", "int")}</td></tr>`;
    }).join("");
    typeTable = `<div class="table-wrap"><table class="small">
        <thead><tr><th>Blind recall by cause type</th><th class="num">Planted</th><th class="num">Found</th>
        <th class="num">Right cause</th></tr></thead><tbody>${body}</tbody></table></div>`;
  }
  return metricTable(rows) + typeTable;
}

function classificationPanel() {
  return `<div class="panel"><h3>Ticket classification</h3>${metricTable([
    ["Customer's own menu choice was right", "details.classification.menu_choice_accuracy", "frac_pct"],
    ["Local model accuracy", "classification.accuracy_local", "frac_pct"],
    ["Cascade accuracy (local, then LLM)", "classification.accuracy_cascade", "frac_pct"],
    ["Cascade accuracy on Hinglish tickets", "details.classification.accuracy_cascade_hinglish", "frac_pct"],
    ["LLM-only accuracy (sample)", "classification.accuracy_llm_sample", "frac_pct"],
    ["Tickets sent to the LLM", "classification.pct_sent_to_llm", "pct"],
    ["LLM requests per million tickets", "details.classification.llm_requests_per_million_tickets", "int"],
    ["LLM cost per million tickets (USD)", "classification.cost_per_million_tickets_usd", "num"],
    ["Wrong team per 100, routing by menu choice", "details.classification.misrouted_per_100_menu", "num"],
    ["Wrong team per 100, routing by OpsLens", "details.classification.misrouted_per_100_opslens", "num"],
    ["Transfers avoided per 100 tickets", "classification.transfers_avoided_per_100", "num"],
  ])}</div>`;
}

function forecastPanel() {
  return `<div class="panel"><h3>Forecast (test days)</h3>${metricTable([
    ["WAPE, our LightGBM model", "forecast.wape_model", "frac_pct"],
    ["WAPE, seasonal-naive baseline", "forecast.wape_naive", "frac_pct"],
    ["WAPE noise floor (no model can beat it)", "details.forecast.wape_noise_floor", "frac_pct"],
    ["Team-hour workload WAPE, our model", "details.forecast.wape_team_hour_workload_model", "frac_pct"],
    ["Team-hour workload WAPE, naive", "details.forecast.wape_team_hour_workload_naive", "frac_pct"],
    ["Error on the known sale day", "details.forecast.sale_day_error_pct", "pct", { signed: true }],
    ["80% interval coverage", "forecast.coverage_80", "frac_pct"],
    ["90% interval coverage", "forecast.coverage_90", "frac_pct"],
  ])}</div>`;
}

function riskPanel() {
  return `<div class="panel"><h3>Breach-risk model (test days)</h3>
      <div class="grid-2">
        <div>
          ${metricTable([
            ["AUC (open tickets, every snapshot)", "risk.auc", "ratio"],
            ["AUC at arrival only (harder)", "details.risk.at_arrival.auc", "ratio"],
            ["Rule to beat: rank by time left to SLA", "details.risk.rules.time_left_auc", "ratio"],
            ["Rule to beat: rank by priority", "details.risk.rules.priority_auc", "ratio"],
            ["PR-AUC", "risk.pr_auc", "ratio"],
            ["Top-10% precision", "risk.top10_precision", "frac_pct"],
            ["Brier score", "risk.brier", "ratio"],
            ["Base rate (share that breached)", "risk.base_rate", "frac_pct"],
          ])}
          <h4>Real data: UCI ServiceNow incidents</h4>
          ${metricTable([
            ["AUC on real incidents (made_sla)", "risk.realdata_auc", "ratio"],
            ["Rule to beat: rank by priority", "details.risk.realdata.priority_rule_auc", "ratio"],
            ["PR-AUC on real incidents", "details.risk.realdata.pr_auc", "ratio"],
            ["Real incidents scored", "risk.realdata_n", "int"],
          ])}
        </div>
        <div>
          <div class="tile-label">Calibration: predicted vs observed</div>
          <div class="chart-box short"><canvas id="calibration-chart"></canvas></div>
          ${details().risk && details().risk.feature_gain ? `<div class="tile-label" style="margin-top: 12px">What the model looks at (share of gain, top 8)</div>
          <div class="chart-box short"><canvas id="gain-chart"></canvas></div>` : ""}
        </div>
      </div></div>`;
}

function drawCalibration() {
  const bins = state.results.risk.calibration;
  makeChart(document.getElementById("calibration-chart"), {
    type: "line",
    data: {
      datasets: [
        {
          label: "Our model",
          data: bins.map((b) => ({ x: b.predicted, y: b.observed })),
          borderColor: SLOTS[0],
          backgroundColor: SLOTS[0],
          borderWidth: 2,
          pointRadius: 6,
        },
        {
          label: "Perfect calibration",
          data: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
          borderColor: INK,
          borderDash: [6, 4],
          borderWidth: 1.5,
          pointRadius: 0,
        },
      ],
    },
    options: {
      scales: {
        x: { type: "linear", min: 0, max: 1, title: { display: true, text: "predicted probability" } },
        y: { min: 0, max: 1, title: { display: true, text: "observed breach rate" } },
      },
      plugins: { legend: { position: "top" } },
    },
  }, (datasetIndex, index) => (datasetIndex === 0 ? { path: `risk.calibration[${index}].observed`, unit: "frac_pct" } : null));
}

// The 8 features with the most LightGBM gain: what the risk model mostly relies on.
function drawFeatureGain() {
  const gain = details().risk.feature_gain;
  const top = Object.keys(gain).sort((a, b) => gain[b] - gain[a]).slice(0, 8);
  makeChart(document.getElementById("gain-chart"), {
    type: "bar",
    data: {
      labels: top.map((f) => prettyKey(f)),
      datasets: [{ label: "share of gain", data: top.map((f) => gain[f]), backgroundColor: SLOTS[0], borderRadius: 4 }],
    },
    options: {
      indexAxis: "y",
      scales: { x: { beginAtZero: true }, y: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
  }, (datasetIndex, index) => ({ path: `details.risk.feature_gain.${top[index]}`, unit: "frac_pct" }));
}

// ---- Ablations, stress, sensitivity, speed, tuning ---------------------------------------

// Ablation rows with CIs (details.ablations) when present, else the plain rows.
function ablationRows() {
  const d = details();
  if (Array.isArray(d.ablations) && d.ablations.length) {
    return d.ablations.map((row, i) => ({ row, path: `details.ablations[${i}]` }));
  }
  return state.results.ablations.map((row, i) => ({ row, path: `ablations[${i}]` }));
}

function ablationsPanel() {
  const rows = ablationRows();
  const hasCi = typeof rows[0].row.ci_low === "number";
  const body = rows.map(({ row, path }) => {
    const ci = hasCi && row.key !== "full"
      ? ` <span class="pm">[${ev(path + ".ci_low", "pts", { signed: true, bare: true })}, ${ev(path + ".ci_high", "pts", { signed: true, bare: true })}]</span>`
      : "";
    return `<tr>
        <td>${evText(path + ".label")}</td>
        <td class="num">${ev(path + ".breach_pct.mean", "pct", { bare: true })} <span class="pm">± ${ev(path + ".breach_pct.std", "pts", { bare: true })}</span></td>
        <td class="num">${ev(path + ".p90_resolution_min.mean", "min", { bare: true })} <span class="pm">± ${ev(path + ".p90_resolution_min.std", "min", { bare: true })}</span></td>
        <td class="num">${ev(path + ".delta_breach_vs_full", "pts", { signed: true, bare: true })}${ci}</td>
      </tr>`;
  }).join("");
  return `<div class="panel"><h3>Ablations: take one part away at a time (test days)</h3>
      <div class="split-wide">
        <div class="table-wrap"><table>
          <thead><tr><th>Variant</th><th class="num">Breach (%)</th><th class="num">P90 resolution (min)</th>
            <th class="num">Breach vs full (pts)${hasCi ? "<div class=\"small\">paired 95% CI</div>" : ""}</th></tr></thead>
          <tbody>${body}</tbody>
        </table></div>
        <div><div class="tile-label">Extra breaches without each part (pts)${hasCi ? ", whiskers = 95% CI" : ""}</div>
          <div class="chart-box short"><canvas id="ablation-chart"></canvas></div></div>
      </div></div>`;
}

function drawAblations() {
  // Leave out the full system itself (its difference is zero by definition).
  const rows = ablationRows().filter(({ row }) => row.key !== "full");
  const hasCi = rows.length && typeof rows[0].row.ci_low === "number";
  makeChart(document.getElementById("ablation-chart"), {
    type: "bar",
    data: {
      // "without classifier (menu choice routing)" -> two lines, so the axis label is not cut off
      labels: rows.map(({ row }) => row.label.replace(" (", "\n(").split("\n")),
      datasets: [{
        label: "Breach vs full (pts)",
        data: rows.map(({ row }) => row.delta_breach_vs_full),
        ranges: hasCi ? rows.map(({ row }) => [row.ci_low, row.ci_high]) : undefined,
        backgroundColor: SLOTS[0],
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y",
      scales: { x: { beginAtZero: true }, y: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
    plugins: [errorBarsPlugin],
  }, (datasetIndex, index) => ({ path: `${rows[index].path}.delta_breach_vs_full`, unit: "pts" }));
}

// Stress rows: breach % and P99 wait per policy, then OpsLens − Baseline B with its CI.
function stressPanel() {
  const rows = state.results.stress;
  const policies = ["baseline_a", "baseline_b", "opslens"].filter((k) => typeof rows[0][k] === "number");
  const hasWait = policies.some((k) => typeof rows[0][k + "_p99_wait"] === "number");
  const hasCi = typeof rows[0].opslens_minus_b === "number";
  const groupHeader = `<tr><th></th>
      <th class="num" colspan="${policies.length}">Breach rate (%)</th>
      ${hasWait ? `<th class="num" colspan="${policies.length}">P99 wait (min)</th>` : ""}
      ${hasCi ? `<th class="num" colspan="2">OpsLens − ${escapeHtml(policyLabel("baseline_b"))}</th>` : ""}</tr>`;
  // Short names ("Baseline A") so nine columns fit on a 1366-px screen.
  const short = (k) => escapeHtml(policyLabel(k).replace(/\s*\(.*\)$/, ""));
  const header = `<tr><th>Scenario</th>
      ${policies.map((k) => `<th class="num">${short(k)}</th>`).join("")}
      ${hasWait ? policies.map((k) => `<th class="num">${short(k)}</th>`).join("") : ""}
      ${hasCi ? `<th class="num">pts, 95% CI</th><th>Verdict</th>` : ""}</tr>`;
  const body = rows.map((row, i) => {
    const base = `stress[${i}]`;
    return `<tr>
        <td>${evText(base + ".scenario")}</td>
        ${policies.map((k) => `<td class="num">${ev(`${base}.${k}`, "pct", { bare: true })}</td>`).join("")}
        ${hasWait ? policies.map((k) => `<td class="num">${ev(`${base}.${k}_p99_wait`, "min", { bare: true })}</td>`).join("") : ""}
        ${hasCi ? `<td class="num">${ev(base + ".opslens_minus_b", "pts", { signed: true, bare: true })}
            <span class="pm">[${ev(base + ".ci_low", "pts", { signed: true, bare: true })}, ${ev(base + ".ci_high", "pts", { signed: true, bare: true })}]</span></td>
          <td>${verdict(row.ci_low, row.ci_high)}</td>` : ""}
      </tr>`;
  }).join("");
  return `<div class="panel"><h3>Stress tests (conditions never seen in training)</h3>
      <div class="table-wrap"><table class="stress-table"><thead>${groupHeader}${header}</thead><tbody>${body}</tbody></table></div>
      <div class="chart-box short" style="margin-top: 12px"><canvas id="stress-chart"></canvas></div></div>`;
}

function drawStress() {
  const rows = state.results.stress;
  const policies = ["baseline_a", "baseline_b", "opslens"].filter((k) => typeof rows[0][k] === "number");
  if (!policies.length) return;
  makeChart(document.getElementById("stress-chart"), {
    type: "bar",
    data: {
      labels: rows.map((row) => row.scenario),
      datasets: policies.map((k) => ({
        label: policyLabel(k) + " (breach %)",
        data: rows.map((row) => row[k]),
        backgroundColor: policyStyle(k).color,
        borderColor: "#ffffff",
        borderWidth: 2, // white gap between neighbouring bars
        borderRadius: 4,
      })),
    },
    options: {
      scales: { y: { beginAtZero: true }, x: { grid: { display: false } } },
      plugins: { legend: { position: "top" } },
    },
  }, (datasetIndex, index) => ({ path: `stress[${index}].${policies[datasetIndex]}`, unit: "pct" }));
}

// A table for a list of flat rows (sensitivity). Columns = keys of the first row.
// Policy keys get their policy label as the header.
function genericTable(listName) {
  const list = state.results[listName];
  const columns = Object.keys(list[0]);
  const header = columns.map((c) => {
    const label = state.results.sim && state.results.sim.policies[c] ? policyLabel(c) : prettyKey(c);
    return `<th class="${typeof list[0][c] === "number" ? "num" : ""}">${escapeHtml(label)}</th>`;
  }).join("");
  const body = list.map((row, i) => `<tr>${columns.map((c) => {
    const path = `${listName}[${i}].${c}`;
    return typeof row[c] === "number"
      ? `<td class="num">${ev(path, unitForKey(c))}</td>`
      : `<td>${evText(path)}</td>`;
  }).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function genericPanel(title, note, listName) {
  return `<div class="panel"><h3>${escapeHtml(title)}</h3><p class="muted small">${escapeHtml(note)}</p>${genericTable(listName)}</div>`;
}

function speedPanel() {
  const s = state.results.speed;
  const rows = [
    ["Full pipeline", "speed.pipeline_seconds", "sec"],
    ["Optimiser per decision step (median)", "speed.optimizer_ms_median", "ms"],
    ["Optimiser per decision step (slowest)", "speed.optimizer_ms_max", "ms"],
  ];
  Object.keys(s.scale_test).forEach((key) => {
    rows.push([`Scale test: ${prettyKey(key)}`, `speed.scale_test.${key}`, key === "seconds" ? "sec" : "int"]);
  });
  return `<div class="panel"><h3>Speed and scale</h3>${metricTable(rows)}</div>`;
}

// How the optimiser weights were chosen: one weight at a time, on validation days only.
function tuningPanel() {
  const t = details().tuning;
  const chosen = t.chosen ? Object.keys(t.chosen).map((key) =>
    `<span class="chip"><b>${escapeHtml(prettyKey(key))}</b>${ev(`details.tuning.chosen.${key}`, "num")}</span>`).join("") : "";
  const rows = t.history.map((h, i) => {
    const base = `details.tuning.history[${i}]`;
    return `<tr><td>${evText(base + ".weight")}</td><td class="num">${ev(base + ".value", "num")}</td>
        <td class="num">${ev(base + ".breach_pct", "pct", { bare: true })}</td>
        <td class="num">${ev(base + ".p99_wait_min", "min", { bare: true })}</td></tr>`;
  }).join("");
  return `<div class="panel" id="tuning-panel"><h3>How the weights were chosen (validation days only)</h3>
      <p class="small muted">Days ${ev("details.tuning.validation_days[0]", "int")}–${ev("details.tuning.validation_days[1]", "int")},
        seeds ${evText("details.tuning.seeds")}. ${escapeHtml(policyLabel("baseline_b"))} on the same days:
        breach ${ev("details.tuning.baseline_b.breach_pct", "pct")}, P99 wait ${ev("details.tuning.baseline_b.p99_wait_min", "min")}.</p>
      ${chosen ? `<div class="chips">${chosen}</div>` : ""}
      <details style="margin-top: 10px"><summary class="small">Every setting we tried</summary>
        <div class="table-wrap"><table class="small">
          <thead><tr><th>Weight</th><th class="num">Value</th><th class="num">Breach (%)</th><th class="num">P99 wait (min)</th></tr></thead>
          <tbody>${rows}</tbody></table></div>
      </details></div>`;
}

// Written by us, in words only. These are the honest limits we say out loud in the pitch.
function limitationsPanel() {
  return `<div class="panel" id="limitations"><h3>Limitations</h3>
      <ul>
        <li>The operations layer (timestamps, agents, skills, shifts, SLAs) is generated, not real. We say so openly.</li>
        <li>Ticket text is partly synthetic: food-specific intents come from templates with typos and Hinglish.</li>
        <li>We designed the planted problems. Blind recall on random plant sets and the real UCI log guard against "you only found what you planted".</li>
        <li>The real-data check uses the public UCI ServiceNow log: IT incidents, not food delivery.</li>
        <li>The simulator is a model of a support floor. It is checked against Erlang C, but real agents behave in ways it does not capture.</li>
        <li>Stress tests are shown with their verdicts above, including the ones OpsLens does not win.</li>
        <li>LLM text (cluster names, the brief) never contains digits; our code fills in every number.</li>
      </ul></div>`;
}
