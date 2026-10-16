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
import { policyName } from "./ui.js";
import { hasFloor, floorHtml, floorLegend, drawFloor } from "./floormap.js";

let index = 0; // the replay step on screen
let timer = null; // setInterval handle while playing
let charts = {}; // { waiting: Chart, breached: Chart }
let keys = []; // policies that have a replay series
let maxWaiting = 1; // for the queue bar widths
let speed = 1; // 1×, 2× or 4×

const STEP_MS = 700; // real milliseconds per replay step at 1× speed

export function replayHtml() {
  return `<section class="card" id="replay">
      <div class="card-head">
        <div>
          <h3 class="card-title">Replay · ${evText("sim.replay.title")}</h3>
          <div class="card-sub">Same tickets, same luck, same agents; one point every ${ev("sim.replay.step_min", "min")}.
            Press Play, or drag the slider.</div>
        </div>
      </div>
      <div class="replay-controls">
        <button type="button" class="btn btn-primary" id="rp-play">Play</button>
        <div class="clock" id="rp-clock"></div>
        <input type="range" id="rp-scrub" min="0" value="0" aria-label="Replay time">
        <div class="segmented" role="group" aria-label="Speed">
          <button type="button" data-speed="1" aria-pressed="true">1×</button>
          <button type="button" data-speed="2" aria-pressed="false">2×</button>
          <button type="button" data-speed="4" aria-pressed="false">4×</button>
        </div>
      </div>
      <div class="grid cols-3" id="rp-lanes"></div>
      <div id="rp-legend"></div>
      <div class="grid cols-2" style="margin-top: 20px">
        <div><div class="section-label">Tickets waiting</div><div class="chart sm"><canvas id="rp-wait-chart"></canvas></div></div>
        <div><div class="section-label">Breaches so far</div><div class="chart sm"><canvas id="rp-breach-chart"></canvas></div></div>
      </div>
    </section>`;
}

// Call after replayHtml() is in the page.
export function initReplay() {
  const replay = state.results.sim.replay;
  keys = policyKeys().filter((k) => replay.series[k]);
  index = 0;
  maxWaiting = 1;
  keys.forEach((k) => replay.series[k].waiting.forEach((w) => { maxWaiting = Math.max(maxWaiting, w); }));

  document.getElementById("rp-lanes").innerHTML = keys.map((k) => `
      <div class="lane">
        ${policyName(k)}
        <div class="lane-numbers">
          <div><div class="stat-label">Waiting now</div><div class="stat-value md" id="rp-w-${k}"></div></div>
          <div><div class="stat-label">Breaches so far</div><div class="stat-value md" id="rp-b-${k}"></div></div>
        </div>
        <div class="queue-track"><div class="queue-fill" id="rp-q-${k}" style="background: ${policyStyle(k).color}"></div></div>
        ${hasFloor() ? floorHtml(k) : ""}
      </div>`).join("");
  document.getElementById("rp-legend").innerHTML = hasFloor() ? floorLegend() : "";

  const scrub = document.getElementById("rp-scrub");
  scrub.max = String(replay.times.length - 1);
  scrub.addEventListener("input", () => showStep(Number(scrub.value)));
  document.getElementById("rp-play").addEventListener("click", () => (timer ? pauseReplay() : startReplay()));
  // Speed buttons: press one, and restart the timer at the new speed if it is playing.
  document.querySelectorAll("#replay [data-speed]").forEach((button) => {
    button.addEventListener("click", () => {
      speed = Number(button.dataset.speed);
      document.querySelectorAll("#replay [data-speed]").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      if (timer) {
        pauseReplay();
        startReplay();
      }
    });
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
        borderWidth: 2.5,
        pointRadius: 0,
        tension: 0.3,
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
      // No legend: the three lanes above name the policies in the same colours.
      plugins: { legend: { display: false } },
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
  if (hasFloor()) drawFloor(keys, replay.times[i]);
}

export function startReplay() {
  const last = state.results.sim.replay.times.length - 1;
  if (index >= last) {
    showStep(0); // at the end: start again from the beginning
  }
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
