import { state, policyLabel, lookup } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, errorBarsPlugin, policyStyle, INK, SLOTS } from "../charts.js";
import { pageHeader, missing, fold, onFirstOpen } from "../ui.js";
import { escapeHtml, prettyKey, unitForKey } from "../format.js";
import { challengeStrip } from "./atrisk.js";
import { alertHitRate } from "./forecast.js";

const SECTIONS = [
  ["what-failed", "What failed"],
  ["t-baselines", "Baselines"],
  ["t-sim", "Simulator"],
  ["t-recall", "Recall"],
  ["t-class", "Classifier"],
  ["t-forecast", "Forecast"],
  ["t-risk", "Risk"],
  ["t-ablations", "Ablations"],
  ["t-stress", "Stress"],
  ["t-sens", "Speed"],
  ["tuning-panel", "Weights"],
  ["limitations", "Limits"],
];

export function render(section) {
  const r = state.results;
  const sections = [
    ["t-setup", "How the test is set up", setupPanel()],
    ["t-recall", "Finding hidden problems", r.patterns ? recallPanel() : missing("Pattern recall", "M4")],
    ["t-class", "Reading the tickets", r.classification ? classificationPanel() : missing("Classification", "M3")],
    ["t-forecast", "Forecasting the next 48 hours", r.forecast ? forecastPanel() : missing("Forecast evaluation", "M6")],
    ["t-risk", "Predicting who will be late", r.risk ? riskPanel() : missing("Risk model evaluation", "M5")],
    ["t-ablate", "Which part does the work (one part removed at a time)", ablationRows().length ? ablationsPanel() : missing("Ablations", "M8")],
    ["t-stress", "Conditions it never saw (stress tests)", r.stress.length ? stressPanel() : missing("Stress tests", "M8")],
    ["t-sens", "Sensitivity, speed and scale", `<div class="grid cols-2">
      ${r.sensitivity.length ? genericPanel("Sensitivity", "How results move when one setting changes.", "sensitivity") : missing("Sensitivity", "M8")}
      ${r.speed ? speedPanel() : missing("Speed and scale", "M8")}</div>`],
    details().tuning && details().tuning.history ? ["t-tuning", "How the weights were chosen (validation days only)", tuningPanel()] : null,
    ["t-limits", "Our limits", limitationsPanel()],
  ].filter(Boolean);
  section.innerHTML = `
    ${pageHeader("How we tested", "What failed, what we beat, and every test behind the numbers. Open any section.")}
    ${r.stress.length || details().v1_record ? honestPanel() : ""}
    ${r.baseline_c && r.baseline_c.test.means ? baselinesPanel() : ""}
    ${r.nlp_bench ? aiPanel() : ""}
    ${sections.map(([id, title, html]) => fold(title, html, { id: `fold-${id}` })).join("")}`;

  const draw = {
    "t-risk": () => {
      if (r.risk && r.risk.calibration.length) drawCalibration();
      if (details().risk && details().risk.feature_gain) drawFeatureGain();
    },
    "t-ablate": () => { if (ablationRows().length) drawAblations(); },
    "t-stress": () => { if (r.stress.length) drawStress(); },
  };
  Object.entries(draw).forEach(([id, fn]) => onFirstOpen(`fold-${id}`, fn));

  section.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.jump);
      const box = target && (target.closest("details") || document.getElementById(`fold-${button.dataset.jump}`));
      if (box) box.open = true;
      if (target) target.scrollIntoView({ block: "start", behavior: "smooth" });
    });
  });
}

const NB = "nlp_bench";
function pctCi(path) {
  return `${ev(path + ".pct", "pct")} <span class="ci">[${ev(path + ".ci95[0]", "pct", { bare: true })}, ${ev(path + ".ci95[1]", "pct", { bare: true })}]</span>`;
}
function aiPanel() {
  const nb = state.results.nlp_bench;
  const b = `${NB}.banking77`;
  const pub = (setting, model) => (nb.banking77.published && nb.banking77.published[setting] && nb.banking77.published[setting][model] !== undefined
    ? ev(`${b}.published.${setting}.${model}`, "pct") : "—");
  const bankRow = (setting, label) => `<tr><td>${label}</td>
      <td class="num">${pctCi(`${b}.settings.${setting}.local`)}</td>
      <td class="num"><b>${pctCi(`${b}.settings.${setting}.cascade`)}</b></td>
      <td class="num">${ev(`${b}.settings.${setting}.escalated_pct`, "pct")}</td>
      <td class="num">${pub(setting, "BERT-fixed")} / ${pub(setting, "BERT-tuned")}</td></tr>`;
  const r = `${NB}.routing`;
  const a = `${NB}.attribution`;
  const pill = (ok) => `<span class="pill ${ok ? "good" : ""}">${ok ? "earns its place" : "ties the rules"}</span>`;
  return `<section class="card ai-panel" id="t-ai">
      <div class="card-head"><div><h2 class="card-title">Does the AI earn its place?</h2>
        <p class="card-sub">Three tests, each written down before it ran, each against what we would do without an LLM. The LLM never writes a number.</p></div></div>
      <div class="ai-grid">
        <div class="ai-test">
          <h3>Reading real customer messages ${pill(nb.banking77.settings.full.rule_llm_adds_value)}</h3>
          <p class="small muted">${evText(`${b}.dataset.name`)}: ${ev(`${b}.dataset.test`, "int")} real bank-customer messages,
            ${ev(`${b}.dataset.intents`, "int")} intents (${evText(`${b}.dataset.licence`)}). Our local model first; the LLM only for the unsure ones.</p>
          <div class="table-wrap"><table><thead><tr><th>Training data</th><th class="num">Local model</th><th class="num">+ LLM when unsure</th>
            <th class="num">Sent to the LLM</th><th class="num">Published BERT (fixed / tuned)</th></tr></thead>
            <tbody>${bankRow("full", "All of it")}${bankRow("10-shot", "10 examples per intent")}</tbody></table></div>
          <p class="small muted">Published: ${evText(`${b}.published.source`)}.</p>
        </div>
        <div class="ai-test">
          <h3>Understanding a manager's question ${pill(nb.routing.rule_llm_beats_rules)}</h3>
          <p class="small muted">${ev(`${r}.questions`, "int")} questions labelled before the run, English and Hinglish: does Ask OpsLens pick the right tool with the right settings?</p>
          <div class="ai-vs"><div><b>${ev(`${r}.all.llm_full.pct`, "pct")}</b><span>LLM</span></div>
            <div><b>${ev(`${r}.all.rules_full.pct`, "pct")}</b><span>keyword rules</span></div></div>
          <p class="small">Hinglish: LLM ${ev(`${r}.hinglish.llm_full.correct`, "int")} of ${ev(`${r}.hinglish.llm_full.n`, "int")},
            rules ${ev(`${r}.hinglish.rules_full.correct`, "int")} of ${ev(`${r}.hinglish.rules_full.n`, "int")}.</p>
        </div>
        <div class="ai-test">
          <h3>Naming a problem's cause ${pill(nb.attribution.rule_llm_beats_rules)}</h3>
          <p class="small muted">${ev(`${a}.cards`, "int")} evidence cards with the cause hidden.</p>
          <div class="ai-vs"><div><b>${ev(`${a}.llm.correct`, "int")} of ${ev(`${a}.llm.n`, "int")}</b><span>LLM</span></div>
            <div><b>${ev(`${a}.rules.correct`, "int")} of ${ev(`${a}.rules.n`, "int")}</b><span>our rules</span></div></div>
          <p class="small">The rules already do this, so the LLM only writes the readable sentence; replies with digits: ${ev(`${a}.replies_with_digits`, "int")}.</p>
        </div>
      </div>
    </section>`;
}

const BASELINES = [
  ["baseline_a", "First come, first served", "Each team's oldest ticket first; routed by the customer's menu choice."],
  ["baseline_b", "Urgent first", "P1 before P2 before P3, then oldest; same team queues."],
  ["baseline_c", "SLA due first", "Earliest SLA deadline first; tickets already late go after the savable ones."],
  ["baseline_d", "Industry standard", "Skills-based routing with AI triage (our own classifier), priority then SLA due, any team: what helpdesk suites do out of the box."],
  ["opslens", "OpsLens", "Risk-aware value, optimiser, rare-skill protection, cross-skill rescues."],
];

function baselinesPanel() {
  const r = state.results;
  const m = "baseline_c.test.means";
  const sealed = r.sealed_world && r.sealed_world.test.means;
  const rows = BASELINES.filter(([key]) => r.baseline_c.test.means[key]).map(([key, name, what]) => `
      <tr class="${key === "opslens" ? "is-ours" : ""}">
        <td><strong>${escapeHtml(name)}</strong><div class="small muted">${escapeHtml(what)}</div></td>
        <td class="num">${ev(`${m}.${key}.turnaround.breach_pct`, "pct")}</td>
        <td class="num">${ev(`${m}.${key}.segment.p1_breach_pct`, "pct")}</td>
        <td class="num">${ev(`${m}.${key}.quality.late_minutes_per_100`, "int")}</td>
        <td class="num">${sealed && sealed[key] ? ev(`sealed_world.test.means.${key}.turnaround.breach_pct`, "pct") : '<span class="muted">not run</span>'}</td>
      </tr>`).join("");
  return `<section class="card" id="t-baselines">
      <div class="card-head"><div><h3 class="card-title">Every baseline we beat, weakest to strongest</h3>
        <div class="card-sub">Held-out test days, 5 seeds, same tickets and luck. Baselines have no weights, so nothing
          was tuned: each ran on validation days first, then once on test days. The sealed world was generated after the
          policy freeze and evaluated once (the industry-standard baseline was added after that run).</div></div></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Policy</th><th class="num">SLA breaches</th><th class="num">P1 breaches</th>
          <th class="num">Minutes late / 100 tickets</th><th class="num">Sealed world: breaches</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </section>`;
}

function details() {
  return state.results.details || {};
}

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
  return `<table class="kv"><tbody>${body}</tbody></table>`;
}

function hasValue(path) {
  let node = state.results;
  for (const part of path.replace(/\[(\d+)\]/g, ".$1").split(".")) {
    if (node === null || node === undefined || typeof node !== "object") return false;
    node = node[part];
  }
  return node !== undefined && node !== null;
}

function verdict(ciLow, ciHigh) {
  if (ciHigh < 0) return `<span class="verdict good">OpsLens better</span>`;
  if (ciLow > 0) return `<span class="verdict bad">OpsLens worse</span>`;
  return `<span class="verdict">no clear difference</span>`;
}

function versions() {
  const d = details();
  const kept = [];
  if (d.v1_record && d.v1_record.stress) {
    kept.push({ base: "details.v1_record", title: "Ages tickets per hour", design: null });
  }
  if (d.v2_record && d.v2_record.stress) {
    kept.push({ base: "details.v2_record", title: "Ages tickets in SLA units", design: d.design_v2 ? "details.design_v2" : null });
  }
  const crisis = hasValue("details.weights.aging_lost") && hasValue("details.weights.guard_queue_limit");
  const designKey = `design_v${kept.length + 1}`;
  const current = {
    base: null,
    title: crisis ? "Crisis mode" : "Current policy",
    design: d[designKey] ? `details.${designKey}` : (kept.length === 0 && d.design_v2 ? "details.design_v2" : null),
    current: true,
  };
  return kept.concat([current]).map((v, i) => ({ ...v, name: "v" + (i + 1) }));
}

function versionPaths(v) {
  if (v.current) {
    return {
      ours: "sim.policies.opslens.kpis.turnaround.breach_pct.mean",
      baseB: "sim.policies.baseline_b.kpis.turnaround.breach_pct.mean",
      stress: "stress",
    };
  }
  return { ours: `${v.base}.test_breach_pct.opslens`, baseB: `${v.base}.test_breach_pct.baseline_b`, stress: `${v.base}.stress` };
}

function volumeRow(rows) {
  const i = rows.findIndex((row) => /^\+\s*25/.test(String(row.scenario)));
  return i >= 0 ? i : 0;
}

function honestPanel() {
  const list = versions();
  const tiles = list.map((v) => {
    const paths = versionPaths(v);
    const rows = lookup(paths.stress) || [];
    if (!rows.length) return "";
    const i = volumeRow(rows);
    const row = `${paths.stress}[${i}]`;
    return `<div class="version ${v.current ? "is-current" : ""}">
        <div class="stat-label">${v.name} · ${escapeHtml(v.title)}</div>
        <div class="stat-value">${ev(row + ".opslens", "pct")}</div>
        <div class="stat-sub">breaches at ${evText(row + ".scenario")} vs ${ev(row + ".baseline_b", "pct")} for ${escapeHtml(policyLabel("baseline_b"))}</div>
        <div style="margin-top: 8px">${typeof rows[i].ci_low === "number" ? verdict(rows[i].ci_low, rows[i].ci_high) : ""}</div>
      </div>`;
  }).join("");

  const steps = list.map((v) => {
    const paths = versionPaths(v);
    const rows = lookup(paths.stress) || [];
    let why = "";
    if (v.current && hasValue("details.weights.aging_lost")) {
      why = `<p class="small" style="margin-top: 6px">What changed: a ticket that is already lost keeps only
        ${ev("details.weights.aging_lost", "num")} of its waiting value, so it stops crowding out tickets that can
        still be saved; and the fairness guard pauses while more than ${ev("details.weights.guard_queue_limit", "int")}
        tickets wait.</p>`;
    } else if (!v.current && lookup(v.base + ".note")) {
      why = `<p class="small muted" style="margin-top: 6px">Why it changed: ${evText(v.base + ".note")}</p>`;
    }
    const design = v.design
      ? `<details class="disclosure"><summary>Show the designs tried on validation days
          (days ${ev(v.design + ".validation_days[0]", "int")}–${ev(v.design + ".validation_days[1]", "int")})</summary>
          ${designTable(v.design)}</details>`
      : "";
    return `<li>
        <h4>${v.name} · ${escapeHtml(v.title)}${v.current ? ` <span class="pill">current</span>` : ""}</h4>
        <p>Normal test days: OpsLens ${ev(paths.ours, "pct")} vs ${ev(paths.baseB, "pct")} for
          ${escapeHtml(policyLabel("baseline_b"))}. Stress tests:</p>
        ${stressVerdicts(paths.stress, rows)}
        ${why}${design}
      </li>`;
  }).join("");

  const note = hasValue("details.test_runs_note")
    ? `<div class="callout info" style="margin-top: 16px">${evText("details.test_runs_note")}</div>`
    : `<p class="card-foot">Earlier versions appear here once <code>make eval</code> keeps their records
        (<code>details.v1_record</code>, <code>details.v2_record</code>).</p>`;
  return `<section class="card honest" id="what-failed">
      <div class="card-head"><div><h3 class="card-title">What failed, and what we changed</h3>
        <div class="card-sub">Verdicts come from the sign of each 95% CI of (OpsLens − ${escapeHtml(policyLabel("baseline_b"))}),
          so the words stay honest when numbers change</div></div></div>
      ${list.length > 1 ? `<div class="versions">${tiles}</div>` : ""}
      <ol class="steps" style="margin-top: 22px">${steps}</ol>
      ${note}
    </section>`;
}

function stressVerdicts(base, rows) {
  if (!Array.isArray(rows) || !rows.length) return "";
  const items = rows.map((row, i) => {
    const path = `${base}[${i}]`;
    if (typeof row.opslens_minus_b !== "number") {
      return `<li><strong>${evText(path + ".scenario")}</strong> OpsLens ${ev(path + ".opslens", "pct")}</li>`;
    }
    return `<li>${verdict(row.ci_low, row.ci_high)} <strong>${evText(path + ".scenario")}</strong>
        <span>OpsLens ${ev(path + ".opslens", "pct")} vs ${ev(path + ".baseline_b", "pct")}:
          ${ev(path + ".opslens_minus_b", "pts", { signed: true })}</span>
        <span class="muted">95% CI ${ev(path + ".ci_low", "pts", { signed: true })} to ${ev(path + ".ci_high", "pts", { signed: true })}</span></li>`;
  }).join("");
  return `<ul class="verdicts">${items}</ul>`;
}

function designTable(base) {
  const design = lookup(base);
  const columns = Object.keys(design.rows[0]).filter((k) => k !== "variant" && /breach_pct$/.test(k));
  const header = columns.map((c) => `<th class="num">${escapeHtml(designHeader(c))}</th>`).join("");
  const body = design.rows.map((row, i) => `<tr>
      <td>${evText(`${base}.rows[${i}].variant`)}</td>
      ${columns.map((c) => `<td class="num">${ev(`${base}.rows[${i}].${c}`, "pct", { bare: true })}</td>`).join("")}
    </tr>`).join("");
  return `<div class="table-wrap"><table>
      <thead><tr><th>Design</th>${header}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function designHeader(key) {
  const space = key.lastIndexOf(" ");
  const scenario = key.slice(0, space);
  const metric = key.slice(space + 1).replace(/^p1_/, "P1 ").replace(/_pct$/, " %").replace(/_/g, " ");
  return `${scenario}: ${metric}`;
}

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
  return `<section class="card" id="t-sim"><div class="card-head"><div><h3 class="card-title">Data and fair simulator</h3>
      <div class="card-sub">All model, threshold and weight choices use validation days only</div></div></div>${metricTable(rows)}</section>`;
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
  return `<section class="card" id="t-recall"><div class="card-head"><div><h3 class="card-title">Finding planted problems</h3>
      <div class="card-sub">The engine never reads the plant list; only the evaluation does</div></div></div>${metricTable(rows)}
      ${p.blind_recall ? blindTable() : ""}
      ${p.recall ? `<details class="disclosure"><summary>Show each planted problem</summary>${recallDetails(p.recall)}</details>` : ""}
    </section>`;
}

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
  return `<div class="table-wrap"><table>
      <thead><tr><th>Planted problem</th><th>Found</th><th>Right cause</th><th>Card</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

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
    typeTable = `<details class="disclosure"><summary>Show blind recall by cause type</summary><div class="table-wrap"><table>
        <thead><tr><th>Blind recall by cause type</th><th class="num">Planted</th><th class="num">Found</th>
        <th class="num">Right cause</th></tr></thead><tbody>${body}</tbody></table></div></details>`;
  }
  return metricTable(rows) + typeTable;
}

function classificationPanel() {
  return `<section class="card" id="t-class"><div class="card-head"><div><h3 class="card-title">Ticket classification</h3>
      <div class="card-sub">Local model first, the LLM only for tickets it is unsure about</div></div></div>${metricTable([
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
  ])}</section>`;
}

function forecastPanel() {
  return `<section class="card" id="t-forecast"><div class="card-head"><div><h3 class="card-title">Forecast</h3>
      <div class="card-sub">Test days; WAPE = total absolute error ÷ total actual</div></div></div>${metricTable([
    ["WAPE, our LightGBM model", "forecast.wape_model", "frac_pct"],
    ["WAPE, seasonal-naive baseline", "forecast.wape_naive", "frac_pct"],
    ["WAPE noise floor (no model can beat it)", "details.forecast.wape_noise_floor", "frac_pct"],
    ["Team-hour workload WAPE, our model", "details.forecast.wape_team_hour_workload_model", "frac_pct"],
    ["Team-hour workload WAPE, naive", "details.forecast.wape_team_hour_workload_naive", "frac_pct"],
    ["Error on the known sale day", "details.forecast.sale_day_error_pct", "pct", { signed: true }],
    ["80% interval coverage", "forecast.coverage_80", "frac_pct"],
    ["90% interval coverage", "forecast.coverage_90", "frac_pct"],
  ])}${alertHitRate()}</section>`;
}

function riskPanel() {
  return `<section class="card" id="t-risk"><div class="card-head"><div><h3 class="card-title">Breach-risk model</h3>
      <div class="card-sub">Test days, and the same code on real UCI ServiceNow incidents</div></div></div>
      <div class="grid cols-2">
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
          <div class="section-label">Real data: UCI ServiceNow incidents</div>
          ${metricTable([
            ["AUC on real incidents (made_sla)", "risk.realdata_auc", "ratio"],
            ["Rule to beat: rank by priority", "details.risk.realdata.priority_rule_auc", "ratio"],
            ["PR-AUC on real incidents", "details.risk.realdata.pr_auc", "ratio"],
            ["Real incidents scored", "risk.realdata_n", "int"],
          ])}
        </div>
        <div>
          <div class="section-label">Calibration: predicted vs observed</div>
          <div class="chart sm"><canvas id="calibration-chart"></canvas></div>
          ${details().risk && details().risk.feature_gain ? `<div class="section-label" style="margin-top: 18px">What the model looks at (share of gain, top 8)</div>
          <div class="chart sm"><canvas id="gain-chart"></canvas></div>` : ""}
        </div>
      </div>${challengeStrip()}</section>`;
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
      scales: { x: { beginAtZero: true }, y: { grid: { display: false }, ticks: { autoSkip: false } } },
      plugins: { legend: { display: false } },
    },
  }, (datasetIndex, index) => ({ path: `details.risk.feature_gain.${top[index]}`, unit: "frac_pct" }));
}

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
  return `<section class="card" id="t-ablations"><div class="card-head"><div><h3 class="card-title">Ablations: take one part away at a time</h3>
      <div class="card-sub">Test days; how many more breaches without each part, with a paired 95% CI</div></div></div>
      <div class="grid cols-3-2">
        <div class="table-wrap"><table>
          <thead><tr><th>Variant</th><th class="num">Breach (%)</th><th class="num">P90 resolution (min)</th>
            <th class="num">Breach vs full (pts)${hasCi ? "<div class=\"small\">paired 95% CI</div>" : ""}</th></tr></thead>
          <tbody>${body}</tbody>
        </table></div>
        <div><div class="section-label">Extra breaches without each part (pts)${hasCi ? ", whiskers = 95% CI" : ""}</div>
          <div class="chart sm"><canvas id="ablation-chart"></canvas></div></div>
      </div></section>`;
}

function drawAblations() {
  const rows = ablationRows().filter(({ row }) => row.key !== "full");
  const hasCi = rows.length && typeof rows[0].row.ci_low === "number";
  makeChart(document.getElementById("ablation-chart"), {
    type: "bar",
    data: {
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
      scales: { x: { beginAtZero: true }, y: { grid: { display: false }, ticks: { autoSkip: false } } },
      plugins: { legend: { display: false } },
    },
    plugins: [errorBarsPlugin],
  }, (datasetIndex, index) => ({ path: `${rows[index].path}.delta_breach_vs_full`, unit: "pts" }));
}

function stressPanel() {
  const rows = state.results.stress;
  const policies = ["baseline_a", "baseline_b", "opslens"].filter((k) => typeof rows[0][k] === "number");
  const hasWait = policies.some((k) => typeof rows[0][k + "_p99_wait"] === "number");
  const hasCi = typeof rows[0].opslens_minus_b === "number";
  const groupHeader = `<tr><th></th>
      <th class="num" colspan="${policies.length}">Breach rate (%)</th>
      ${hasWait ? `<th class="num" colspan="${policies.length}">P99 wait (min)</th>` : ""}
      ${hasCi ? `<th class="num" colspan="2">OpsLens − ${escapeHtml(policyLabel("baseline_b"))}</th>` : ""}</tr>`;
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
  return `<section class="card" id="t-stress"><div class="card-head"><div><h3 class="card-title">Stress tests</h3>
      <div class="card-sub">Conditions never seen in training, on the test days</div></div></div>
      <div class="table-wrap"><table><thead>${groupHeader}${header}</thead><tbody>${body}</tbody></table></div>
      <div class="chart sm" style="margin-top: 16px"><canvas id="stress-chart"></canvas></div></section>`;
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
        borderWidth: 2,
        borderRadius: 4,
      })),
    },
    options: {
      scales: { y: { beginAtZero: true }, x: { grid: { display: false } } },
      plugins: { legend: { position: "top" } },
    },
  }, (datasetIndex, index) => ({ path: `stress[${index}].${policies[datasetIndex]}`, unit: "pct" }));
}

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
  return `<section class="card"><div class="card-head"><div><h3 class="card-title">${escapeHtml(title)}</h3>
      <div class="card-sub">${escapeHtml(note)}</div></div></div>${genericTable(listName)}</section>`;
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
  return `<section class="card"><div class="card-head"><div><h3 class="card-title">Speed and scale</h3>
      <div class="card-sub">Optimiser time per decision, and one big scale test</div></div></div>${metricTable(rows)}</section>`;
}

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
  return `<section class="card" id="tuning-panel"><div class="card-head"><div><h3 class="card-title">How the weights were chosen</h3>
      <div class="card-sub">Validation days only, one weight at a time</div></div></div>
      <p class="small muted" style="margin-bottom: 10px">Days ${ev("details.tuning.validation_days[0]", "int")}–${ev("details.tuning.validation_days[1]", "int")},
        seeds ${evText("details.tuning.seeds")}. ${escapeHtml(policyLabel("baseline_b"))} on the same days:
        breach ${ev("details.tuning.baseline_b.breach_pct", "pct")}, P99 wait ${ev("details.tuning.baseline_b.p99_wait_min", "min")}.</p>
      ${chosen ? `<div class="chips">${chosen}</div>` : ""}
      <details class="disclosure"><summary>Show every setting we tried</summary>
        <div class="table-wrap"><table>
          <thead><tr><th>Weight</th><th class="num">Value</th><th class="num">Breach (%)</th><th class="num">P99 wait (min)</th></tr></thead>
          <tbody>${rows}</tbody></table></div>
      </details></section>`;
}

function limitationsPanel() {
  return `<section class="card" id="limitations"><div class="card-head"><div><h3 class="card-title">Limitations</h3>
      <div class="card-sub">What we say out loud in the pitch</div></div></div>
      <ul class="small" style="margin: 0; padding-left: 20px; line-height: 1.8">
        <li>The operations layer (timestamps, agents, skills, shifts, SLAs) is generated, not real. We say so openly.</li>
        <li>Ticket text is partly synthetic: food-specific intents come from templates with typos and Hinglish.</li>
        <li>We designed the planted problems. Blind recall on random plant sets and the real UCI log guard against "you only found what you planted".</li>
        <li>The real-data check uses the public UCI ServiceNow log: IT incidents, not food delivery.</li>
        <li>The simulator is a model of a support floor. It is checked against Erlang C, but real agents behave in ways it does not capture.</li>
        <li>Stress tests are shown with their verdicts above, including the ones OpsLens does not win.</li>
        <li>LLM text (cluster names, the brief) never contains digits; our code fills in every number.</li>
      </ul></section>`;
}
