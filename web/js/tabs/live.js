// tabs/live.js — "Live now": today's support day, simulated on this laptop, at the real clock.
//
// Why (24 Oct, the owner asked for "everything running live"): the other screens are exam results
// measured on fixed days, so they show fixed dates. This screen is the opposite: it shows TODAY'S
// date and the current time, and asks the engine every few seconds what the floor looks like now
// (GET /api/live). The engine simulated the whole day once when it was first asked (both the
// industry standard and OpsLens, same tickets, same luck), so each answer is instant. The tickets
// are the practice company's tickets for the test day with today's weekday (a day OpsLens never
// studied), and the screen says so. "New luck" simulates the day again with another seed.
// Every number here is a live answer, clickable like the others (path "live.…").
//
// Example (a Saturday, 21:14): industry standard 61 waiting, 23 promises missed so far; OpsLens
// 24 waiting, 6 missed; in danger now T060597, Hindi payment failure, 99.6%.

import { state } from "../data.js";
import { ev } from "../evidence.js";
import { drawFrameInto, floorLegend } from "../floormap.js";
import { escapeHtml, prettyKey } from "../format.js";

const POLL_MS = 5000; // ask the engine for the floor every 5 s; the clock itself ticks every second
const WAIT_MS = 3000; // while the day is still being simulated
const LANGUAGE = { hi: "Hindi", en: "English", other: "regional language" };
let seed = 1;
let tick = null;
let poll = null;
let speed = 1; // 1 = real time; "fast" plays the day at 180x so a judge can watch an evening in minutes
let fastMinute = null;
let listening = false; // the tab-shown listener is added once, however often the view is drawn

export function render(section) {
  section.innerHTML = `
    <section class="mission live-band" aria-label="Live now">
      <div>
        <div class="mission-eyebrow"><span class="live-dot"></span><span id="lv-date">Live</span></div>
        <h2 id="lv-clock" class="live-clock">--:--:--</h2>
        <p class="mission-sub">Today's support day, simulated on this laptop right now: the same customers and the
          same agents under two ways of working. The customers are the practice company's (its test
          <span id="lv-weekday">day</span>, which OpsLens never studied); every number is computed here, live.</p>
        <div class="mission-score">
          <div class="theirs"><div class="k">Promises missed so far today, industry standard</div><div class="v" id="lv-m-theirs">…</div></div>
          <div class="ours"><div class="k">Promises missed so far today, OpsLens</div><div class="v" id="lv-m-ours">…</div></div>
        </div>
        <div class="mission-actions">
          <button type="button" class="btn" id="lv-speed">Play the day fast</button>
          <button type="button" class="btn ghost" id="lv-luck">New luck</button>
        </div>
        <p class="live-status" id="lv-status" role="status"></p>
      </div>
      <div class="mission-floors">
        <div><div class="mission-lane-title">Industry standard<small id="lv-w-theirs"></small></div><div class="floor" id="lv-f-theirs"></div></div>
        <div><div class="mission-lane-title">OpsLens<small id="lv-w-ours"></small></div><div class="floor" id="lv-f-ours"></div></div>
        ${floorLegend()}
      </div>
    </section>
    <div class="grid cols-2 stretch live-panels">
      <section class="card"><div class="card-head"><div><h3 class="card-title">In danger right now</h3>
        <div class="card-sub" id="lv-danger-sub">The waiting customers OpsLens sees as most likely to miss their promise, and why.</div></div></div>
        <div id="lv-danger"></div></section>
      <section class="card"><div class="card-head"><div><h3 class="card-title">What OpsLens just decided</h3>
        <div class="card-sub">The last few minutes of assignments, each with its reason.</div></div></div>
        <div id="lv-decisions"></div></section>
    </div>`;
  section.querySelector("#lv-speed").addEventListener("click", toggleSpeed);
  section.querySelector("#lv-luck").addEventListener("click", () => { seed = (seed % 99) + 1; refresh(); });
  start();
  if (!listening) {
    listening = true;
    document.addEventListener("tab-shown", (event) => (event.detail === "live" ? start() : stop()));
  }
}

// The minute of the day shown: the real clock, or the fast-forward clock.
function minuteNow() {
  if (speed > 1 && fastMinute !== null) return fastMinute;
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
}

function start() {
  stop();
  showClock();
  tick = setInterval(() => {
    if (speed > 1 && fastMinute !== null) fastMinute = Math.min(1439, fastMinute + speed / 60);
    showClock();
  }, 1000);
  refresh();
}

function stop() {
  clearInterval(tick);
  clearTimeout(poll);
  tick = null;
  poll = null;
}

function toggleSpeed() {
  const button = document.getElementById("lv-speed");
  if (speed > 1) {
    speed = 1;
    fastMinute = null;
    button.textContent = "Play the day fast";
  } else {
    speed = 180; // one real second = three simulated minutes: the evening in about 2.5 minutes
    fastMinute = 17 * 60; // start before the dinner rush
    button.textContent = "Back to real time";
  }
  showClock();
  refresh();
}

function showClock() {
  const clock = document.getElementById("lv-clock");
  if (!clock) { stop(); return; }
  const today = new Date();
  const m = minuteNow();
  const hh = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(Math.floor(m % 60)).padStart(2, "0");
  const ss = speed > 1 ? "00" : String(today.getSeconds()).padStart(2, "0");
  clock.textContent = `${hh}:${mm}:${ss}`;
  document.getElementById("lv-date").textContent = (speed > 1 ? "Fast replay · " : "Live · ")
    + today.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  document.getElementById("lv-weekday").textContent = today.toLocaleDateString(undefined, { weekday: "long" });
}

async function refresh() {
  clearTimeout(poll);
  const weekday = (new Date().getDay() + 6) % 7; // JavaScript: 0 = Sunday; the engine: 0 = Monday
  const status = document.getElementById("lv-status");
  if (!status) return;
  if (state.staticServer) {
    status.textContent = "Live now needs the OpsLens server (start it with uvicorn, not a static file server).";
    return;
  }
  let data;
  try {
    const response = await fetch(`/api/live?weekday=${weekday}&minute=${minuteNow().toFixed(2)}&seed=${seed}`, { cache: "no-store" });
    data = await response.json();
  } catch (error) {
    status.textContent = "The engine did not answer. Is the server still running?";
    poll = setTimeout(refresh, POLL_MS * 2);
    return;
  }
  if (!data.ready) {
    status.textContent = `Simulating today's whole day on this laptop (luck ${seed}): two ways of working, about half a minute…`;
    poll = setTimeout(refresh, WAIT_MS);
    return;
  }
  state.live = data;
  status.textContent = `Simulated on this laptop · test day ${data.day} of the practice company · luck ${data.seed}`;
  draw(data);
  poll = setTimeout(refresh, speed > 1 ? 1000 : POLL_MS);
}

function draw(d) {
  const lanes = [["baseline_d", "theirs"], ["opslens", "ours"]];
  lanes.forEach(([key, side]) => {
    const p = d.policies[key];
    if (!p) return;
    document.getElementById(`lv-m-${side}`).innerHTML = ev(`live.policies.${key}.missed`, "int");
    document.getElementById(`lv-w-${side}`).innerHTML = ` ${ev(`live.policies.${key}.waiting`, "int")} waiting now`;
    drawFrameInto(document.getElementById(`lv-f-${side}`), d.agents, p.status, p.queues);
  });
  document.getElementById("lv-danger").innerHTML = d.danger.length ? d.danger.map((t, i) => `
      <div class="live-ticket">
        <div class="live-risk">${ev(`live.danger[${i}].probability`, "frac_pct")}</div>
        <div>
          <div class="live-ticket-head"><strong>${escapeHtml(t.ticket_id)}</strong>
            <span class="pill ${t.priority === "P1" ? "p1" : ""}">${escapeHtml(t.priority)}</span>
            <span class="pill">${escapeHtml(prettyKey(t.category))}</span>
            <span class="pill">${escapeHtml(LANGUAGE[t.language] || t.language)}</span>
            <span class="small muted">${ev(`live.danger[${i}].minutes_left`, "min")} left</span></div>
          <div class="live-text">“${escapeHtml(t.text)}”</div>
          <ul class="live-reasons">${t.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
        </div>
      </div>`).join("")
    : `<p class="muted">Nobody is in danger right now. Quiet hours: try “Play the day fast” for the dinner rush.</p>`;
  document.getElementById("lv-decisions").innerHTML = d.decisions.length ? `<ul class="live-decisions">${d.decisions.map((x) => `
      <li><span class="live-when">${clockOf(x.minute)}</span>
        <strong>${escapeHtml(x.ticket_id)}</strong> → <strong>${escapeHtml(agentName(d.agents, x.agent))}</strong>
        <div class="small muted">${escapeHtml(x.reason)}</div></li>`).join("")}</ul>`
    : `<p class="muted">No assignment in the last 15 minutes.</p>`;
}

function clockOf(minute) {
  const m = Math.floor(minute);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

function agentName(agents, id) {
  const a = agents.find((x) => x.id === id);
  return a && a.name && a.name !== id ? `${a.name} (${id})` : id;
}
