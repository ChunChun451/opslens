// tabs/tested.js — every evaluation number in one place, plus our limitations.
//
// Why: a sharp judge will ask "how do you know?". This tab answers with the evaluation from
// CLAUDE.md section 7: recall on planted problems, classification, forecast, risk, ablations,
// sensitivity, stress tests and speed. Each number clicks through to its JSON path.
//
// Example (fixture): ablation "without risk scores" raises breaches by +1.7 pts vs full OpsLens.

import { state, policyLabel } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, policyStyle, INK, SLOTS } from "../charts.js";
import { missing } from "../ui.js";
import { escapeHtml, prettyKey, unitForKey } from "../format.js";

export function render(section) {
  const r = state.results;
  section.innerHTML = `
    <div class="tab-head"><div>
      <h2>How we tested</h2>
      <p>Every claim on this dashboard, how it was measured, and its limits.</p>
    </div></div>
    <div class="grid-2">
      ${setupPanel()}
      ${r.patterns ? recallPanel() : missing("Pattern recall", "M4")}
    </div>
    <div class="grid-2">
      ${r.classification ? classificationPanel() : missing("Classification", "M3")}
      ${r.forecast ? forecastPanel() : missing("Forecast evaluation", "M6")}
    </div>
    ${r.risk ? riskPanel() : missing("Risk model evaluation", "M5")}
    ${r.ablations.length ? ablationsPanel() : missing("Ablations", "M8")}
    ${r.stress.length ? stressPanel() : missing("Stress tests", "M8")}
    <div class="grid-2">
      ${r.sensitivity.length ? genericPanel("Sensitivity", "How results move when one setting changes.", "sensitivity") : missing("Sensitivity", "M8")}
      ${r.speed ? speedPanel() : missing("Speed and scale", "M8")}
    </div>
    ${limitationsPanel()}`;

  if (r.risk && r.risk.calibration.length) drawCalibration();
  if (r.ablations.length) drawAblations();
  if (r.stress.length) drawStress();
}

// A two-column table: label | clickable value. rows = [[label, path, unit], ...]
// unit "text" shows the raw value; unit "range" shows a [first, last] list as "first–last".
function metricTable(rows) {
  const body = rows.map(([label, path, unit]) => {
    let value;
    if (unit === "text") {
      value = evText(path);
    } else if (unit === "range") {
      value = `${ev(path + "[0]", "int")}–${ev(path + "[1]", "int")}`;
    } else {
      value = ev(path, unit);
    }
    return `<tr><td>${escapeHtml(label)}</td><td class="num">${value || "—"}</td></tr>`;
  }).join("");
  return `<table class="metric-table"><tbody>${body}</tbody></table>`;
}

function setupPanel() {
  const rows = [
    ["Train days", "meta.train_days", "range"],
    ["Validation days (choices made here)", "meta.validation_days", "range"],
    ["Test days (report only)", "meta.test_days", "range"],
    ["Generated tickets", "meta.n_tickets", "int"],
    ["Data generator seed", "meta.data_seed", "text"],
    ["Generated at", "meta.generated_at", "text"],
    ["Git commit", "meta.git_commit", "text"],
    ["Evaluation run time", "meta.run_seconds", "sec"],
  ];
  if (state.results.sim) {
    rows.splice(3, 0, ["Simulator seeds (same luck for every policy)", "sim.seeds", "text"]);
  }
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
  if (p.blind_recall) {
    Object.keys(p.blind_recall).forEach((key) => {
      rows.push([`Blind recall: ${prettyKey(key)}`, `patterns.blind_recall.${key}`, unitForKey(key)]);
    });
  }
  rows.push(["Live detection latency (surprise spike)", "patterns.live_detection_latency_min", "min"]);
  const details = p.recall ? p.recall.details.map((d, i) => `
      <span class="chip">${evText(`patterns.recall.details[${i}].id`)}
        ${evText(`patterns.recall.details[${i}].found`, d.found ? "found" : "missed")}</span>`).join("") : "";
  return `<div class="panel"><h3>Finding planted problems</h3>${metricTable(rows)}
      ${details ? `<div class="chips" style="margin-top: 10px">${details}</div>` : ""}
      <p class="panel-note">The engine never reads the plant list; only the evaluation does.</p></div>`;
}

function classificationPanel() {
  return `<div class="panel"><h3>Ticket classification</h3>${metricTable([
    ["Local model accuracy", "classification.accuracy_local", "frac_pct"],
    ["Cascade accuracy (local, then LLM)", "classification.accuracy_cascade", "frac_pct"],
    ["LLM-only accuracy (sample)", "classification.accuracy_llm_sample", "frac_pct"],
    ["Tickets sent to the LLM", "classification.pct_sent_to_llm", "pct"],
    ["LLM cost per million tickets (USD)", "classification.cost_per_million_tickets_usd", "num"],
    ["Transfers avoided per 100 tickets", "classification.transfers_avoided_per_100", "num"],
  ])}</div>`;
}

function forecastPanel() {
  return `<div class="panel"><h3>Forecast (test days)</h3>${metricTable([
    ["WAPE, our LightGBM model", "forecast.wape_model", "frac_pct"],
    ["WAPE, seasonal-naive baseline", "forecast.wape_naive", "frac_pct"],
    ["80% interval coverage", "forecast.coverage_80", "frac_pct"],
    ["90% interval coverage", "forecast.coverage_90", "frac_pct"],
  ])}</div>`;
}

function riskPanel() {
  return `<div class="panel"><h3>Breach-risk model (test days)</h3>
      <div class="grid-2">
        ${metricTable([
          ["AUC", "risk.auc", "ratio"],
          ["PR-AUC", "risk.pr_auc", "ratio"],
          ["Top-10% precision", "risk.top10_precision", "frac_pct"],
          ["Brier score", "risk.brier", "ratio"],
          ["Base rate (share that breached)", "risk.base_rate", "frac_pct"],
          ["AUC on real UCI incidents", "risk.realdata_auc", "ratio"],
          ["Real UCI incidents scored", "risk.realdata_n", "int"],
        ])}
        <div><div class="tile-label">Calibration: predicted vs observed</div>
          <div class="chart-box short"><canvas id="calibration-chart"></canvas></div></div>
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

function ablationsPanel() {
  const rows = state.results.ablations.map((a, i) => {
    const base = `ablations[${i}]`;
    return `<tr>
        <td>${evText(base + ".label")}</td>
        <td class="num">${ev(base + ".breach_pct.mean", "pct", { bare: true })} <span class="pm">± ${ev(base + ".breach_pct.std", "pts", { bare: true })}</span></td>
        <td class="num">${ev(base + ".p90_resolution_min.mean", "min", { bare: true })} <span class="pm">± ${ev(base + ".p90_resolution_min.std", "min", { bare: true })}</span></td>
        <td class="num">${ev(base + ".delta_breach_vs_full", "pts", { signed: true })}</td>
      </tr>`;
  }).join("");
  return `<div class="panel"><h3>Ablations: take one part away at a time</h3>
      <div class="split-wide">
        <div class="table-wrap"><table>
          <thead><tr><th>Variant</th><th class="num">Breach (%)</th><th class="num">P90 resolution (min)</th><th class="num">Breach vs full</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
        <div><div class="tile-label">Extra breaches without each part (pts)</div>
          <div class="chart-box short"><canvas id="ablation-chart"></canvas></div></div>
      </div></div>`;
}

function drawAblations() {
  const rows = state.results.ablations;
  makeChart(document.getElementById("ablation-chart"), {
    type: "bar",
    data: {
      labels: rows.map((a) => a.label),
      datasets: [{
        label: "Breach vs full (pts)",
        data: rows.map((a) => a.delta_breach_vs_full),
        backgroundColor: SLOTS[0],
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y",
      scales: { x: { beginAtZero: true }, y: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
  }, (datasetIndex, index) => ({ path: `ablations[${index}].delta_breach_vs_full`, unit: "pts" }));
}

// A table for a list of flat rows (sensitivity, stress). Columns = keys of the first row.
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

// Stress rows name a scenario and a value per policy. The schema does not name the metric
// yet; CLAUDE.md section 7.8 asks "does OpsLens still beat both baselines?" on breaches.
function stressPanel() {
  return `<div class="panel"><h3>Stress tests (never seen in training)</h3>
      <p class="muted small">Breach rate (%) per policy under each condition.</p>
      <div class="split-wide">
        ${genericTable("stress")}
        <div class="chart-box short"><canvas id="stress-chart"></canvas></div>
      </div></div>`;
}

function drawStress() {
  const rows = state.results.stress;
  const policies = state.results.sim
    ? Object.keys(state.results.sim.policies).filter((k) => typeof rows[0][k] === "number")
    : [];
  if (!policies.length) return;
  const labelKey = Object.keys(rows[0]).find((k) => typeof rows[0][k] === "string");
  makeChart(document.getElementById("stress-chart"), {
    type: "bar",
    data: {
      labels: rows.map((row) => (labelKey ? row[labelKey] : "")),
      datasets: policies.map((k) => ({
        label: policyLabel(k),
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
  }, (datasetIndex, index) => ({ path: `stress[${index}].${policies[datasetIndex]}`, unit: unitForKey(policies[datasetIndex]) }));
}

function speedPanel() {
  const s = state.results.speed;
  const rows = [
    ["Full pipeline", "speed.pipeline_seconds", "sec"],
    ["Optimiser per decision step (median)", "speed.optimizer_ms_median", "ms"],
    ["Optimiser per decision step (slowest)", "speed.optimizer_ms_max", "ms"],
  ];
  Object.keys(s.scale_test).forEach((key) => {
    rows.push([`Scale test: ${prettyKey(key)}`, `speed.scale_test.${key}`, unitForKey(key)]);
  });
  return `<div class="panel"><h3>Speed and scale</h3>${metricTable(rows)}</div>`;
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
        <li>LLM text (cluster names, the brief) never contains digits; our code fills in every number.</li>
      </ul></div>`;
}
