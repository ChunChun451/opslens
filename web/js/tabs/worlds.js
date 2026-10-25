// tabs/worlds.js — Proof → "Beyond our world": does OpsLens still win on floors we did not build?
//
// Why (Plan v4 W1 + W2, issue #16): every other proof runs on the one simulated floor we tuned
// the generator for. Here are 30 random floors drawn from wide, fixed ranges (load, peaks, mix,
// skills), and the same floor with agents holding 2 or 3 chats at once. The pre-registered rule
// for the worlds MISSED (lowest in 19 of 30, the rule needed 27), so the screen says that first;
// then what did hold (beats the industry standard in 29 of 30), where it loses (heavy load, to
// "least slack first") and the analysis made after the result. Every number is a path in
// results.worlds / results.concurrency; the chart is a picture of those numbers.
//
// Example: world 7001, load 1.22× today's: OpsLens 14.5% missed, least slack 11.1% → a loss of
// +3.41 pts, while it still beats the industry standard by −9.34 pts.

import { state, lookup, policyLabel } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, fold, onFirstOpen, factLine } from "../ui.js";
import { escapeHtml } from "../format.js";
import { makeChart } from "../charts.js";

const BREACH = "turnaround.breach_pct";

export function render(section) {
  const w = state.results.worlds;
  if (!w) {
    section.innerHTML = pageHeader("Beyond our world", "") + `<div class="callout warn">No random-world results in this file.</div>`;
    return;
  }
  const verdict = w.rule_passed ? "kept" : "missed";
  section.innerHTML = `
    ${pageHeader("Beyond the world we built",
      `${ev("worlds.n_worlds", "int")} random support floors, drawn from wide ranges fixed before the run. Nothing was tuned per world; the classifier ran without the LLM.`)}
    <section class="card wd-verdict is-${verdict}">
      <div class="wd-said">
        <span class="wd-label">We said, before the run</span>
        <p>OpsLens has the lowest missed-promise rate in at least ${ev("worlds.wins_needed", "int")} of ${ev("worlds.n_worlds", "int")} worlds.</p>
      </div>
      <div class="wd-got">
        <span class="wd-label">We measured</span>
        <p><b>${ev("worlds.wins", "int")} of ${ev("worlds.n_worlds", "int")}</b></p>
      </div>
      <div class="ledger-stamp wd-stamp" aria-label="Verdict: ${verdict}"><span>${verdict}</span></div>
    </section>
    ${factLine([
      [`${ev("worlds.breakdown.beats_industry_standard", "int")} of ${ev("worlds.breakdown.of", "int")}`, "worlds where OpsLens beats the industry standard"],
      [ev("worlds.median_opslens_minus_d", "pts", { signed: true }), "median gap to the industry standard"],
      [`<span class="ci">[${ev("worlds.median_ci[0]", "pts", { signed: true, bare: true })}, ${ev("worlds.median_ci[1]", "pts", { signed: true, bare: true })}]</span>`, "95% interval of that median"],
    ])}
    ${card({ id: "wd-chart-card", title: "Where it wins and where it loses",
      sub: "Each dot is one world: OpsLens minus the best other way of working (below zero = OpsLens is lowest), against how loaded the world is. Click a dot for its numbers.",
      body: `<div class="chart-box wd-chart"><canvas id="wd-chart" aria-label="OpsLens minus the best other policy, by world load"></canvas></div>
        <div class="wd-split">
          <div class="wd-zone is-good"><b>${ev("worlds.breakdown.normal_load.wins", "int")} of ${ev("worlds.breakdown.normal_load.worlds", "int")}</b>
            worlds up to ${ev("worlds.breakdown.normal_load.max_load", "ratio")}× today's load: OpsLens is lowest in every one.</div>
          <div class="wd-zone is-bad"><b>${ev("worlds.breakdown.heavy_load.wins", "int")} of ${ev("worlds.breakdown.heavy_load.worlds", "int")}</b>
            heavier worlds. All ${ev("worlds.breakdown.losses.worlds", "int")} losses go to <i>${escapeHtml(policyLabel((w.breakdown.losses.all_to || [])[0] || ""))}</i>,
            at ${ev("worlds.breakdown.losses.min_load", "ratio")}× load or more, and OpsLens keeps late customers less late in
            ${ev("worlds.breakdown.losses.opslens_less_late", "int")} of them.</div>
        </div>` })}
    ${w.diagnosis ? diagnosisCard(w) : ""}
    ${state.results.concurrency ? concurrencyCard() : ""}
    ${fold("Every world, one row each", worldsTable(w), { id: "wd-table", hint: "load, each way of working, the winner" })}`;
  drawChart(w);
}

// The analysis made after the result: who misses in the worlds OpsLens did not win.
function diagnosisCard(w) {
  const d = "worlds.diagnosis.opslens_lower_than_least_slack";
  const n = ev("worlds.breakdown.losses.worlds", "int"); // the loss worlds, as a clickable number
  return card({ title: "In the worlds it lost, who was let down?",
    sub: `<span class="pill">analysis after the result</span> ${evText("worlds.diagnosis.note")}`,
    body: `<div class="wd-diag">
      <div><b>${ev(d + ".gold", "int")} of ${n}</b><span>fewer gold customers missed than least slack</span></div>
      <div><b>${ev(d + ".mean_minutes_late", "int")} of ${n}</b><span>late customers less late</span></div>
      <div><b>${ev(d + ".hindi", "int")} of ${n}</b><span>fewer Hindi-speaking customers missed</span></div>
      <div><b>${ev(d + ".p1", "int")} of ${n}</b><span>fewer urgent (P1) orders missed</span></div>
    </div>
    <p class="small muted">Under sustained overload "least slack first" saves more promises in total; OpsLens spends its effort on the
      customers its weights protect.${w.diagnosis.all_reproduced ? ` All ${n} loss worlds were rebuilt from their seeds and reproduced exactly.` : ""}</p>` });
}

// W2: agents holding 2 or 3 chats at once, at equal load (the pre-registered setting).
function concurrencyCard() {
  const settings = lookup("concurrency.settings") || [];
  const rows = settings.map((s, i) => ({ s, i })).filter(({ s }) => s.load === "equal_load").map(({ s, i }) => {
    const p = `concurrency.settings[${i}].opslens_vs.baseline_d.${BREACH}`;
    return `<tr><td>${ev(`concurrency.settings[${i}].k`, "int")} chats</td>
      <td class="num">${ev(`concurrency.settings[${i}].s`, "num")}</td>
      <td class="num">${ev(`concurrency.settings[${i}].volume_factor`, "ratio")}×</td>
      <td class="num"><b>${ev(p + ".mean_diff", "pts", { signed: true })}</b></td>
      <td class="num"><span class="ci">[${ev(p + ".ci_low", "pts", { signed: true, bare: true })}, ${ev(p + ".ci_high", "pts", { signed: true, bare: true })}]</span></td></tr>`;
  }).join("");
  const verdict = lookup("concurrency.rule_passed") ? "kept" : "missed";
  const allBelow = settings.filter((s) => s.load === "equal_load")
    .every((s) => s.opslens_vs.baseline_d[BREACH].ci_high < 0);
  return card({ title: "When agents hold 2 or 3 chats at once",
    sub: `Each extra open chat slows an agent down (an assumption: ${evText("concurrency.assumption")}). More tickets arrive so the load stays equal.`,
    actions: `<span class="pill ${verdict === "kept" ? "good" : ""}">rule ${verdict}</span>`,
    body: `<div class="table-wrap"><table><thead><tr><th>Chats per agent</th><th class="num">Slowdown per extra chat</th>
      <th class="num">Volume</th><th class="num">OpsLens − industry standard</th><th class="num">95% interval</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <p class="small muted">Missed promises in points; below zero = OpsLens misses fewer.${allBelow ? " Every setting has its whole interval below zero." : ""}</p>` });
}

function worldsTable(w) {
  const rows = w.worlds.map((x, i) => {
    const b = `worlds.worlds[${i}]`;
    return `<tr class="${x.wins ? "" : "hot"}"><td>${ev(b + ".seed", "int")}</td>
      <td class="num">${ev(b + ".params.load", "ratio")}×</td>
      <td class="num">${ev(b + ".breach_pct.opslens", "pct")}</td>
      <td class="num">${ev(b + ".breach_pct.baseline_d", "pct")}</td>
      <td>${escapeHtml(policyLabel(x.best_other))} ${ev(b + `.breach_pct.${x.best_other}`, "pct")}</td>
      <td class="num">${ev(b + ".opslens_minus_best_other", "pts", { signed: true })}</td>
      <td>${x.wins ? "OpsLens" : escapeHtml(policyLabel(x.best_other))}</td></tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr><th>World</th><th class="num">Load</th><th class="num">OpsLens</th>
    <th class="num">Industry standard</th><th>Best other</th><th class="num">OpsLens − best other</th><th>Lowest</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

// The scatter: x = the world's load, y = OpsLens minus the best other policy. Pictures only.
function drawChart(w) {
  const canvas = document.getElementById("wd-chart");
  if (!canvas || typeof Chart === "undefined") return;
  const point = (x) => ({ x: x.params.load, y: x.opslens_minus_best_other });
  const wins = [], losses = [], winIdx = [], lossIdx = [];
  w.worlds.forEach((x, i) => {
    (x.wins ? wins : losses).push(point(x));
    (x.wins ? winIdx : lossIdx).push(i);
  });
  const limit = w.breakdown && w.breakdown.normal_load ? w.breakdown.normal_load.max_load : null;
  makeChart(canvas, {
    type: "scatter",
    data: { datasets: [
      { label: "OpsLens lowest", data: wins, backgroundColor: "#22d3ee", pointRadius: 6, pointHoverRadius: 8 },
      { label: "Another way is lower", data: losses, backgroundColor: "#ff5a5f", pointRadius: 6, pointHoverRadius: 8, pointStyle: "rectRot" },
    ] },
    options: {
      scales: {
        x: { title: { display: true, text: "World load (× today's)" } },
        y: { title: { display: true, text: "OpsLens − best other (pts)" } },
      },
      plugins: { tooltip: { callbacks: { label: (c) => `load ${c.parsed.x.toFixed(2)}×, ${c.parsed.y > 0 ? "+" : ""}${c.parsed.y.toFixed(2)} pts` } } },
    },
    plugins: [{
      id: "wdLines",
      afterDatasetsDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        ctx.save();
        ctx.strokeStyle = "rgba(255,255,255,0.35)";
        ctx.setLineDash([5, 4]);
        const y0 = scales.y.getPixelForValue(0);
        ctx.beginPath(); ctx.moveTo(chartArea.left, y0); ctx.lineTo(chartArea.right, y0); ctx.stroke();
        if (limit) {
          const x = scales.x.getPixelForValue(limit);
          ctx.strokeStyle = "rgba(141,141,148,0.6)";
          ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
        }
        ctx.restore();
      },
    }],
  }, (dataset, index) => {
    const i = (dataset === 0 ? winIdx : lossIdx)[index];
    return { path: `worlds.worlds[${i}].opslens_minus_best_other`, unit: "pts" };
  });
}
