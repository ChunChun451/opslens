// replay.js — one busy evening, played side by side for every policy.
//
// Why: a table of averages is easy to doubt; watching the same evening unfold is not. Every
// policy gets the same tickets and the same luck, so the only difference is the decisions.
// The replay steps through sim.replay (one point every step_min minutes): the "waiting now"
// counters and queue bars move, the breach counters count up, and both charts grow.
//
// Example (fixture, 21:00): waiting 179 / 169 / 109; breaches so far 57 / 32 / 16.

import { state, policyKeys } from "./data.js";
import { ev, evText } from "./evidence.js";
import { makeChart, policyStyle } from "./charts.js";
import { policyName, policyBorder } from "./ui.js";

let index = 0; // the replay step on screen
let timer = null; // setInterval handle while playing
let charts = {}; // { waiting: Chart, breached: Chart }
let keys = []; // policies that have a replay series
let maxWaiting = 1; // for the queue bar widths

const STEP_MS = 700; // real milliseconds per replay step at 1× speed

export function replayHtml() {
  return `<div class="panel" id="replay">
      <h3>Replay: ${evText("sim.replay.title")}</h3>
      <p class="muted small">Same tickets, same luck, same agents. One point every
         ${ev("sim.replay.step_min", "min")}. Press Play, or drag the slider.</p>
      <div class="replay-controls">
        <button type="button" class="btn btn-primary" id="rp-play">Play</button>
        <div class="replay-clock" id="rp-clock"></div>
        <input type="range" id="rp-scrub" min="0" value="0" aria-label="Replay time">
        <label class="small">Speed
          <select id="rp-speed">
            <option value="1">1×</option><option value="2">2×</option><option value="4">4×</option>
          </select>
        </label>
      </div>
      <div class="grid-3" id="rp-lanes"></div>
      <div class="grid-2" style="margin-top: 16px">
        <div><h3>Tickets waiting</h3><div class="chart-box replay-chart"><canvas id="rp-wait-chart"></canvas></div></div>
        <div><h3>Breaches so far</h3><div class="chart-box replay-chart"><canvas id="rp-breach-chart"></canvas></div></div>
      </div>
    </div>`;
}

// Call after replayHtml() is in the page.
export function initReplay() {
  const replay = state.results.sim.replay;
  keys = policyKeys().filter((k) => replay.series[k]);
  index = 0;
  maxWaiting = 1;
  keys.forEach((k) => replay.series[k].waiting.forEach((w) => { maxWaiting = Math.max(maxWaiting, w); }));

  document.getElementById("rp-lanes").innerHTML = keys.map((k) => `
      <div class="lane" style="${policyBorder(k)}">
        ${policyName(k)}
        <div class="lane-numbers">
          <div><div class="tile-label">Waiting now</div><div class="tile-value" id="rp-w-${k}"></div></div>
          <div><div class="tile-label">Breaches so far</div><div class="tile-value" id="rp-b-${k}"></div></div>
        </div>
        <div class="queue-track"><div class="queue-fill" id="rp-q-${k}" style="background: ${policyStyle(k).color}"></div></div>
      </div>`).join("");

  const scrub = document.getElementById("rp-scrub");
  scrub.max = String(replay.times.length - 1);
  scrub.addEventListener("input", () => showStep(Number(scrub.value)));
  document.getElementById("rp-play").addEventListener("click", () => (timer ? pauseReplay() : startReplay()));
  document.getElementById("rp-speed").addEventListener("change", () => {
    if (timer) {
      pauseReplay();
      startReplay();
    }
  });
  // Stop the animation when the user leaves this tab.
  document.addEventListener("tab-shown", (event) => {
    if (event.detail !== "compare") pauseReplay();
  });

  charts.waiting = lineChart("rp-wait-chart", "waiting", "int");
  charts.breached = lineChart("rp-breach-chart", "breached_cum", "int");
  showStep(0);
}

// A line chart with the full time axis; the lines are revealed step by step.
function lineChart(canvasId, field, unit) {
  const replay = state.results.sim.replay;
  let top = 1;
  keys.forEach((k) => replay.series[k][field].forEach((v) => { top = Math.max(top, v); }));
  return makeChart(document.getElementById(canvasId), {
    type: "line",
    data: {
      labels: replay.times,
      datasets: keys.map((k) => ({
        label: state.results.sim.policies[k].label,
        data: [],
        borderColor: policyStyle(k).color,
        borderDash: policyStyle(k).dash,
        borderWidth: 3,
        pointRadius: 0,
        pointHitRadius: 8,
      })),
    },
    options: {
      animation: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 8, maxRotation: 0 }, grid: { display: false } },
        y: { beginAtZero: true, suggestedMax: top },
      },
      // Legend entries drawn as short lines with each policy's dash, like the chart lines.
      plugins: { legend: { position: "top", labels: { usePointStyle: true, pointStyle: "line" } } },
    },
  }, (datasetIndex, i) => ({ path: `sim.replay.series.${keys[datasetIndex]}.${field}[${i}]`, unit }));
}

function showStep(i) {
  const replay = state.results.sim.replay;
  index = i;
  document.getElementById("rp-scrub").value = String(i);
  document.getElementById("rp-clock").innerHTML = evText(`sim.replay.times[${i}]`);
  keys.forEach((k, d) => {
    const series = replay.series[k];
    document.getElementById("rp-w-" + k).innerHTML = ev(`sim.replay.series.${k}.waiting[${i}]`, "int");
    document.getElementById("rp-b-" + k).innerHTML = ev(`sim.replay.series.${k}.breached_cum[${i}]`, "int");
    document.getElementById("rp-q-" + k).style.width = Math.round((series.waiting[i] / maxWaiting) * 100) + "%";
    charts.waiting.data.datasets[d].data = series.waiting.slice(0, i + 1);
    charts.breached.data.datasets[d].data = series.breached_cum.slice(0, i + 1);
  });
  charts.waiting.update("none");
  charts.breached.update("none");
}

export function startReplay() {
  const last = state.results.sim.replay.times.length - 1;
  if (index >= last) {
    showStep(0); // at the end: start again from the beginning
  }
  const speed = Number(document.getElementById("rp-speed").value);
  pauseReplay();
  timer = setInterval(() => {
    if (index >= last) {
      pauseReplay();
      return;
    }
    showStep(index + 1);
  }, STEP_MS / speed);
  document.getElementById("rp-play").textContent = "Pause";
}

export function pauseReplay() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
  const button = document.getElementById("rp-play");
  if (button) button.textContent = "Play";
}
