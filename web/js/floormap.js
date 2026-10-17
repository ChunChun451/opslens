// floormap.js — the support floor as a picture, inside each replay lane.
//
// Why: averages are easy to doubt and hard to remember; a floor you can watch is not. Each
// lane shows the same four teams: one tile per agent on shift (blue = working on their own
// skill, amber = a deliberate cross-skill rescue, red = opened a ticket from the wrong queue,
// pale = free) and, next to it, the team's queue as dots (grey = can still make its SLA,
// red = already late). Every frame comes from sim.replay.floor, recorded in the same seed-1
// simulator runs as the counters above (eval/run_opslens.py::floor_frames), so picture and
// numbers always agree.
//
// Example frame: Team B, OpsLens, 21:30 → 9 blue tiles, 1 amber, 2 pale; queue 6 grey, 1 red.

import { state } from "./data.js";

const TEAM_NAMES = { A: "Live orders", B: "Payments & refunds", C: "Order accuracy", D: "Account, app & partners" };
const STATUS_CLASS = { b: "busy", x: "cross", w: "wrong", i: "idle" }; // "o" (off shift) is not drawn
const MAX_DOTS = 36; // beyond this a queue shows "+N" so the lane keeps its height

export function hasFloor() {
  return Boolean(state.results.sim.replay && state.results.sim.replay.floor);
}

export function floorHtml(key) {
  return `<div class="floor" id="rp-f-${key}" aria-label="Support floor"></div>`;
}

export function floorLegend() {
  return `<div class="floor-legend">
      <span><i class="tile busy"></i>working, own skill</span>
      <span><i class="tile cross"></i>cross-skill rescue</span>
      <span><i class="tile wrong"></i>opened a wrong-queue ticket</span>
      <span><i class="tile idle"></i>free</span>
      <span><i class="dot"></i>waiting, can still make SLA</span>
      <span><i class="dot late"></i>waiting, already late</span>
    </div>`;
}

// Draw every lane at replay time `time` ("21:30"). Floor frames are every 5 min, the replay
// every 15 min, so we look the frame up by its clock time.
export function drawFloor(keys, time) {
  keys.forEach((key) => drawFloorInto(document.getElementById("rp-f-" + key), key, time));
}

// Draw one policy's floor at clock time `time` into `box` (also used by the Overview hero).
export function drawFloorInto(box, key, time) {
  const f = state.results.sim.replay.floor[key];
  if (!box || !f) return;
  const frame = Math.max(0, f.times.indexOf(time));
  box.innerHTML = Object.keys(TEAM_NAMES).map((team) => teamRow(team, f, frame)).join("");
}

function teamRow(team, f, frame) {
  const status = f.status[frame];
  const tiles = f.agents
    .map((agent, k) => (agent.team === team && STATUS_CLASS[status[k]]
      ? `<i class="tile ${STATUS_CLASS[status[k]]}" title="${agent.id} · ${agent.languages.join(", ")}"></i>` : ""))
    .join("");
  const [savable, late] = (f.queues[frame] || {})[team] || [0, 0];
  const shownLate = Math.min(late, MAX_DOTS);
  const shownSavable = Math.min(savable, MAX_DOTS - shownLate);
  const extra = savable + late - shownLate - shownSavable;
  const dots = `${'<i class="dot late"></i>'.repeat(shownLate)}${'<i class="dot"></i>'.repeat(shownSavable)}`
    + (extra > 0 ? `<span class="more">+${extra}</span>` : "");
  return `<div class="floor-team">
      <div class="floor-name"><b>${team}</b> ${TEAM_NAMES[team]}</div>
      <div class="floor-agents">${tiles || '<span class="muted">nobody on shift</span>'}</div>
      <div class="floor-queue">${dots}</div>
    </div>`;
}
