// intro.js — the cold open: one Saturday night, two support floors, about twelve seconds.
//
// Why: the first moment decides whether a judge leans in. Instead of a dashboard full of
// numbers, the page opens on the thing a non-technical person understands at once: customers
// waiting, and promises being missed. Every dot is a customer waiting in that 5-minute frame of
// the recorded replay (sim.replay.floor: queues per team, "can still be helped in time" vs
// "already late"); the two counters are the replay's own missed-promise series
// (sim.replay.series.*.breached_cum). Nothing here is drawn from invented data.
//
// It plays once per browser session on the Overview, any key or click on "Skip" ends it, and
// "Replay the night" in the side menu plays it again. Reduced-motion users get the end card only.
//
// Example (official results, 17 Oct): industry standard 21 missed promises, OpsLens 7.

import { state } from "./data.js";
import { escapeHtml } from "./format.js";

const FRAME_MS = 95; // 73 five-minute frames ≈ 7 s for the whole evening
const SEEN_KEY = "opslens.introSeen";
const MAX_DOTS = 160;
let timer = null;
let lines = [];

export function initIntro() {
  const replay = state.results.sim && state.results.sim.replay;
  if (!replay || !replay.floor || !replay.floor.opslens) return;
  const button = document.getElementById("intro-replay");
  if (button) {
    button.hidden = false;
    button.addEventListener("click", () => play(true));
  }
  let seen = false;
  try { seen = sessionStorage.getItem(SEEN_KEY) === "1"; } catch { /* private mode: play it */ }
  const onOverview = !location.hash || location.hash === "#overview";
  if (!seen && onOverview) play(false);
}

// The strongest baseline with a recorded floor, and its plain name.
function rival() {
  const floor = state.results.sim.replay.floor;
  const key = ["baseline_d", "baseline_c", "baseline_b", "baseline_a"].find((k) => floor[k]);
  const names = { baseline_d: "The industry standard", baseline_c: "Due time first", baseline_b: "Urgent first", baseline_a: "First come, first served" };
  return [key, names[key]];
}

function play(fromButton) {
  const replay = state.results.sim.replay;
  const [theirs, theirsName] = rival();
  const overlay = document.getElementById("intro");
  const lastIdx = replay.series.opslens.breached_cum.length - 1;
  const theirsEnd = replay.series[theirs].breached_cum[lastIdx];
  const oursEnd = replay.series.opslens.breached_cum[lastIdx];
  const day = escapeHtml(replay.title.split(",")[0]); // "Saturday 17 Oct"

  overlay.innerHTML = `
    <button type="button" class="intro-skip" id="intro-skip">Skip</button>
    <div class="intro-stage">
      <p class="intro-line" id="il-1">${day}. Dinner rush.</p>
      <p class="intro-line" id="il-2">Every ticket is a promise to help a customer in time.</p>
      <div class="intro-skies" id="intro-skies">
        <figure class="sky theirs"><figcaption>${escapeHtml(theirsName)}</figcaption>
          <svg viewBox="0 0 400 260" preserveAspectRatio="xMidYMid meet" id="sky-theirs" aria-hidden="true"></svg>
          <div class="sky-count"><b id="cnt-theirs">0</b> missed promises</div></figure>
        <div class="intro-clock" id="intro-clock">18:00</div>
        <figure class="sky ours"><figcaption>OpsLens</figcaption>
          <svg viewBox="0 0 400 260" preserveAspectRatio="xMidYMid meet" id="sky-ours" aria-hidden="true"></svg>
          <div class="sky-count"><b id="cnt-ours">0</b> missed promises</div></figure>
      </div>
      <div class="intro-end" id="intro-end">
        <p class="intro-big"><span class="t">${theirsEnd}</span><span class="vs">vs</span><span class="o">${oursEnd}</span></p>
        <p class="intro-claim">Same people. Same tickets. Different decisions.</p>
        <p class="intro-small">Missed promises on one held-out Saturday evening: ${escapeHtml(theirsName.toLowerCase())} vs OpsLens.
          A dot is a customer waiting; red means their promise is already missed.</p>
        <div class="intro-actions">
          <button type="button" class="btn intro-go" id="intro-go">See how</button>
          <button type="button" class="btn ghost" id="intro-again">Watch again</button>
        </div>
      </div>
    </div>`;
  overlay.hidden = false;
  document.body.classList.add("intro-open");
  document.getElementById("intro-skip").addEventListener("click", close);
  document.getElementById("intro-go").addEventListener("click", close);
  document.getElementById("intro-again").addEventListener("click", () => play(true));
  document.addEventListener("keydown", keyClose);

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    reveal("intro-end");
    return;
  }
  schedule(() => reveal("il-1"), fromButton ? 100 : 400);
  schedule(() => reveal("il-2"), 1500);
  schedule(() => { reveal("intro-skies"); runNight(theirs); }, 3000);
}

function runNight(theirs) {
  const replay = state.results.sim.replay;
  const frames = replay.floor.opslens.times.length;
  const skyT = makeSky("sky-theirs", 11);
  const skyO = makeSky("sky-ours", 29);
  let i = 0;
  timer = setInterval(() => {
    if (i >= frames) {
      clearInterval(timer);
      timer = null;
      schedule(() => { document.getElementById("intro-skies")?.classList.add("dim"); reveal("intro-end"); }, 700);
      return;
    }
    const s = Math.min(Math.floor((i * 5) / replay.step_min), replay.times.length - 1);
    const clock = document.getElementById("intro-clock");
    if (!clock) { clearInterval(timer); return; }
    clock.textContent = replay.floor.opslens.times[i];
    paint(skyT, replay.floor[theirs].queues[i]);
    paint(skyO, replay.floor.opslens.queues[i]);
    document.getElementById("cnt-theirs").textContent = replay.series[theirs].breached_cum[s];
    document.getElementById("cnt-ours").textContent = replay.series.opslens.breached_cum[s];
    i += 1;
  }, FRAME_MS);
}

// A fixed field of dot positions (same layout every time, so dots appear and fade in place).
function makeSky(id, seed) {
  const svg = document.getElementById(id);
  let x = seed;
  const rand = () => { x = (x * 9301 + 49297) % 233280; return x / 233280; };
  const dots = [];
  for (let k = 0; k < MAX_DOTS; k++) {
    // Fill from the bottom up, like a queue piling up.
    const row = Math.floor(k / 16);
    const cx = 20 + (k % 16) * 24 + (rand() - 0.5) * 10;
    const cy = 240 - row * 22 + (rand() - 0.5) * 10;
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", cx.toFixed(1));
    c.setAttribute("cy", cy.toFixed(1));
    c.setAttribute("r", "5");
    c.setAttribute("class", "d off");
    svg.appendChild(c);
    dots.push(c);
  }
  return dots;
}

// Show one dot per waiting customer: late ones first (chilli), then those still in time.
function paint(dots, queues) {
  let late = 0;
  let inTime = 0;
  Object.values(queues || {}).forEach(([s, l]) => { inTime += s; late += l; });
  dots.forEach((dot, k) => {
    const cls = k < late ? "d late" : k < late + inTime ? "d wait" : "d off";
    if (dot.getAttribute("class") !== cls) dot.setAttribute("class", cls);
  });
}

function reveal(id) {
  document.getElementById(id)?.classList.add("in");
}

function schedule(fn, ms) {
  lines.push(setTimeout(fn, ms));
}

function keyClose(event) {
  if (["Escape", "Enter", " "].includes(event.key)) close();
}

function close() {
  lines.forEach(clearTimeout);
  lines = [];
  if (timer) clearInterval(timer);
  timer = null;
  const overlay = document.getElementById("intro");
  overlay.classList.add("leaving");
  document.removeEventListener("keydown", keyClose);
  try { sessionStorage.setItem(SEEN_KEY, "1"); } catch { /* fine */ }
  setTimeout(() => {
    overlay.hidden = true;
    overlay.classList.remove("leaving");
    overlay.innerHTML = "";
    document.body.classList.remove("intro-open");
  }, 450);
}
