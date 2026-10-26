import { state } from "./data.js";

const TEAM_NAMES = { A: "Live orders", B: "Payments & refunds", C: "Order accuracy", D: "Account, app & partners" };
const STATUS_CLASS = { b: "busy", x: "cross", w: "wrong", i: "idle" };
const MAX_DOTS = 36;

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
      <span><i class="dot"></i>waiting, still in time</span>
      <span><i class="dot late"></i>waiting, promise missed</span>
    </div>`;
}

export function drawFloor(keys, time) {
  keys.forEach((key) => drawFloorInto(document.getElementById("rp-f-" + key), key, time));
}

export function drawFloorInto(box, key, time) {
  const f = state.results.sim.replay.floor[key];
  if (!box || !f) return;
  const frame = Math.max(0, f.times.indexOf(time));
  box.innerHTML = Object.keys(TEAM_NAMES).map((team) => teamRow(team, f, frame)).join("");
}

export function drawFrameInto(box, agents, status, queues) {
  if (!box) return;
  const f = { agents, status: [status], queues: [queues] };
  box.innerHTML = Object.keys(TEAM_NAMES).map((team) => teamRow(team, f, 0)).join("");
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
