// mission.js — the Overview's "mission control" band: the Saturday dinner peak plays on its own.
//
// Why: the first ten seconds decide whether a judge leans in. A moving floor (agents working,
// queues filling, late tickets turning red) says "same people, better decisions" faster than
// any number. It plays the recorded seed-1 replay (sim.replay.floor, 5-minute frames) for the
// best baseline that has a floor and for OpsLens, side by side; the breach counters are the
// replay's own series (sim.replay.series, 15-minute points), clickable to results.json.
//
// Example at 21:30 (official results, 17 Oct): urgent-first 13 breaches so far, OpsLens 2.

import { state, policyLabel } from "./data.js";
import { ev, evText } from "./evidence.js";
import { drawFloorInto, floorLegend } from "./floormap.js";
import { escapeHtml } from "./format.js";

const FRAME_MS = 420; // one 5-minute frame; the whole evening plays in about 30 seconds
const HOLD_MS = 2500; // pause on the last frame before looping
let timer = null;
let frame = 0;
let theirs = "";

export function hasMission() {
  const replay = state.results.sim && state.results.sim.replay;
  return Boolean(replay && replay.floor && replay.floor.opslens);
}

export function missionHtml() {
  const floor = state.results.sim.replay.floor;
  // The strongest baseline with a recorded floor: industry standard if present, else urgent-first.
  theirs = ["baseline_d", "baseline_b", "baseline_a"].find((k) => floor[k]) || "";
  const theirsLabel = policyLabel(theirs);
  return `<section class="mission" id="ov-mission" aria-label="Live replay of a Saturday evening">
      <div>
        <div class="mission-eyebrow"><span class="live-dot"></span>Replay · ${evText("sim.replay.title", "a Saturday OpsLens never saw, 18:00–24:00")}</div>
        <h2>Same agents. Same tickets.<br>Only the decisions differ.</h2>
        <p class="mission-sub">The dinner rush on a Saturday OpsLens had never seen, replayed with identical luck.
          Tiles are agents at work; red dots are customers whose promise is already missed.</p>
        <div class="mission-clock" id="ms-clock">18:00</div>
        <div class="mission-score">
          <div class="theirs"><div class="k">Missed promises so far, ${escapeHtml(theirsLabel.toLowerCase())}</div><div class="v" id="ms-b-theirs">0</div></div>
          <div class="ours"><div class="k">Missed promises so far, OpsLens</div><div class="v" id="ms-b-ours">0</div></div>
        </div>
        <div class="mission-actions">
          <button type="button" class="btn" id="ms-play">Pause</button>
          <a class="btn ghost" href="#compare">See the full comparison</a>
        </div>
      </div>
      <div class="mission-floors">
        <div><div class="mission-lane-title">${escapeHtml(theirsLabel)}<small id="ms-w-theirs"></small></div><div class="floor" id="ms-f-theirs"></div></div>
        <div><div class="mission-lane-title">OpsLens<small id="ms-w-ours"></small></div><div class="floor" id="ms-f-ours"></div></div>
        ${floorLegend()}
        <div class="mission-progress"><i id="ms-progress"></i></div>
      </div>
    </section>`;
}

export function initMission() {
  if (!hasMission()) return;
  stop();
  frame = 0;
  show(0);
  play();
  document.getElementById("ms-play").addEventListener("click", () => (timer ? stop() : play()));
  document.addEventListener("tab-shown", (event) => {
    if (event.detail !== "overview") stop();
  });
}

function play() {
  const last = state.results.sim.replay.floor.opslens.times.length - 1;
  stop();
  timer = setInterval(() => {
    if (frame >= last) {
      stop();
      setTimeout(() => { if (document.getElementById("ms-clock")) { frame = 0; show(0); play(); } }, HOLD_MS);
      return;
    }
    frame += 1;
    show(frame);
  }, FRAME_MS);
  const button = document.getElementById("ms-play");
  if (button) button.textContent = "Pause";
}

function stop() {
  if (timer) clearInterval(timer);
  timer = null;
  const button = document.getElementById("ms-play");
  if (button) button.textContent = "Play";
}

function show(i) {
  const replay = state.results.sim.replay;
  const time = replay.floor.opslens.times[i];
  const clock = document.getElementById("ms-clock");
  if (!clock) { stop(); return; }
  clock.textContent = time;
  // Breach counters move on the replay's 15-minute points. Both series start at the same
  // minute, so 5-minute frame i falls on 15-minute point floor(i / 3).
  const s = Math.min(Math.floor((i * 5) / replay.step_min), replay.times.length - 1);
  document.getElementById("ms-b-theirs").innerHTML = ev(`sim.replay.series.${theirs}.breached_cum[${s}]`, "int");
  document.getElementById("ms-b-ours").innerHTML = ev(`sim.replay.series.opslens.breached_cum[${s}]`, "int");
  drawFloorInto(document.getElementById("ms-f-theirs"), theirs, time);
  drawFloorInto(document.getElementById("ms-f-ours"), "opslens", time);
  document.getElementById("ms-w-theirs").textContent = `${waiting(replay.floor[theirs], i)} waiting`;
  document.getElementById("ms-w-ours").textContent = `${waiting(replay.floor.opslens, i)} waiting`;
  document.getElementById("ms-progress").style.width = `${(100 * i) / (replay.floor.opslens.times.length - 1)}%`;
}

// Tickets waiting in this frame: the sum of the recorded team queues (picture of the data).
function waiting(f, i) {
  return Object.values(f.queues[i] || {}).reduce((sum, [savable, late]) => sum + savable + late, 0);
}
