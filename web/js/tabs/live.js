// tabs/live.js — "Live now": today's support day, simulated on this laptop, at the real clock.
//
// Why (24 Oct, the owner asked for "everything running live"): the other screens are exam results
// measured on fixed days, so they show fixed dates. This screen is the opposite: it shows TODAY'S
// date and the current time, and asks the engine every few seconds what the floor looks like now
// (GET /api/live). The engine simulated the whole day once when it was first asked (both the
// industry standard and OpsLens, same tickets, same luck), so each answer is instant. The tickets
// are the practice company's tickets for the test day with today's weekday (a day OpsLens never
// studied), and the screen says so.
// Interactive: change today (fewer or more agents per team, more or fewer customers) and the engine
// simulates the day again on this laptop; "New luck" re-runs it with another seed; "Play the day
// fast" runs the clock at 3 minutes per second. Every number is a live answer, clickable ("live.…").
//
// Example (a Saturday, 21:14): industry standard 61 waiting, 23 promises missed so far; OpsLens
// 24 waiting, 6 missed; in danger now T060597, Hindi payment failure, 99.6% (→ 31% if served now).

import { state } from "../data.js";
import { ev } from "../evidence.js";
import { drawFrameInto, floorLegend } from "../floormap.js";
import { escapeHtml, prettyKey } from "../format.js";

const POLL_MS = 5000; // ask the engine for the floor every 5 s; the clock itself ticks every second
const WAIT_MS = 2500; // while the day is still being simulated
const LANGUAGE = { hi: "Hindi", en: "English", other: "regional language" };
const TEAMS = { A: "Live orders", B: "Payments & refunds", C: "Order accuracy", D: "Account, app & partners" };
let seed = 1;
let tick = null;
let poll = null;
let speed = 1; // 1 = real time; "fast" plays the day at 180x so a judge can watch an evening in minutes
let fastMinute = null;
let listening = false; // the tab-shown listener is added once, however often the view is drawn
// Today's change, as chosen in the panel (applied) and as being edited (draft).
let applied = { agents: { A: 0, B: 0, C: 0, D: 0 }, volume: 100 };
let draft = { agents: { ...applied.agents }, volume: 100 };
let waitingSince = null; // when the current simulation was asked for (for the progress line)

export function render(section) {
  section.innerHTML = `
    <section class="mission live-band" aria-label="Live now">
      <div>
        <div class="mission-eyebrow"><span class="live-dot"></span><span id="lv-date">Live</span></div>
        <h2 id="lv-clock" class="live-clock">--:--:--</h2>
        <p class="mission-sub">Today's support day, running on this laptop now: the same customers and the same agents
          under two ways of working. The customers are the practice company's (its test
          <span id="lv-weekday">day</span>, which OpsLens never studied); every number is computed here, live.</p>
        <div class="mission-score">
          <div class="theirs"><div class="k">Promises missed so far today, industry standard</div><div class="v" id="lv-m-theirs">…</div></div>
          <div class="ours"><div class="k">Promises missed so far today, OpsLens</div><div class="v" id="lv-m-ours">…</div></div>
        </div>
        <div class="live-saved" id="lv-saved"></div>
        <div class="mission-actions">
          <button type="button" class="btn" id="lv-speed">Play the day fast</button>
          <button type="button" class="btn ghost" id="lv-luck">New luck</button>
        </div>
        <p class="live-status" id="lv-status" role="status"></p>
        <div class="live-progress" id="lv-progress" hidden><i></i></div>
      </div>
      <div class="mission-floors">
        <div><div class="mission-lane-title">Industry standard<small id="lv-w-theirs"></small></div><div class="floor" id="lv-f-theirs"></div></div>
        <div><div class="mission-lane-title">OpsLens<small id="lv-w-ours"></small></div><div class="floor" id="lv-f-ours"></div></div>
        ${floorLegend()}
      </div>
    </section>
    <section class="card live-controls" aria-label="Change today">
      <div class="card-head"><div><h3 class="card-title">Change today, and watch it run</h3>
        <div class="card-sub">Take agents away or bring more customers: the engine simulates today again on this laptop
          (about half a minute) and both floors above follow your change.</div></div></div>
      <div class="live-controls-grid">
        ${Object.entries(TEAMS).map(([team, name]) => `
          <div class="stepper" data-team="${team}">
            <div class="stepper-label"><b>Team ${team}</b> ${name}</div>
            <div class="stepper-row">
              <button type="button" class="btn btn-sm" data-step="-1" aria-label="One agent fewer in team ${team}">−</button>
              <output id="lv-a-${team}">0</output>
              <button type="button" class="btn btn-sm" data-step="1" aria-label="One agent more in team ${team}">+</button>
            </div>
          </div>`).join("")}
        <label class="live-volume">
          <span><b>Customers today</b> <output id="lv-vol-out">100%</output></span>
          <input type="range" id="lv-volume" min="50" max="200" step="10" value="100" aria-label="Customers today, percent of normal">
        </label>
      </div>
      <div class="live-controls-actions">
        <button type="button" class="btn btn-primary" id="lv-apply">Run today with my change</button>
        <button type="button" class="btn ghost" id="lv-reset">Back to a normal day</button>
        <span class="small muted" id="lv-scenario">A normal day.</span>
      </div>
    </section>
    <div class="grid cols-2 stretch live-panels">
      <section class="card"><div class="card-head"><div><h3 class="card-title">In danger right now</h3>
        <div class="card-sub">The waiting customers OpsLens sees as most likely to miss their promise, why, and what serving them now would change.</div></div></div>
        <div id="lv-danger"></div></section>
      <section class="card"><div class="card-head"><div><h3 class="card-title">What OpsLens just decided</h3>
        <div class="card-sub">The last few minutes of assignments, each with its reason.</div></div></div>
        <div id="lv-decisions"></div></section>
    </div>`;
  section.querySelector("#lv-speed").addEventListener("click", toggleSpeed);
  section.querySelector("#lv-luck").addEventListener("click", () => { seed = (seed % 99) + 1; refresh(); });
  section.querySelectorAll(".stepper [data-step]").forEach((button) => button.addEventListener("click", () => {
    const team = button.closest(".stepper").dataset.team;
    draft.agents[team] = Math.max(-5, Math.min(5, draft.agents[team] + Number(button.dataset.step)));
    showDraft();
  }));
  section.querySelector("#lv-volume").addEventListener("input", (event) => { draft.volume = Number(event.target.value); showDraft(); });
  section.querySelector("#lv-apply").addEventListener("click", () => { applied = clone(draft); showDraft(); refresh(); });
  section.querySelector("#lv-reset").addEventListener("click", () => {
    applied = { agents: { A: 0, B: 0, C: 0, D: 0 }, volume: 100 };
    draft = clone(applied);
    showDraft();
    refresh();
  });
  showDraft();
  start();
  if (!listening) {
    listening = true;
    document.addEventListener("tab-shown", (event) => (event.detail === "live" ? start() : stop()));
  }
}

function clone(s) {
  return { agents: { ...s.agents }, volume: s.volume };
}

// The panel shows the draft; the button lights up when the draft differs from what is running.
function showDraft() {
  Object.keys(TEAMS).forEach((team) => {
    const out = document.getElementById(`lv-a-${team}`);
    if (!out) return;
    const k = draft.agents[team];
    out.textContent = k > 0 ? `+${k}` : String(k);
    out.className = k < 0 ? "minus" : k > 0 ? "plus" : "";
  });
  document.getElementById("lv-volume").value = draft.volume;
  document.getElementById("lv-vol-out").textContent = `${draft.volume}%`;
  const changed = JSON.stringify(draft) !== JSON.stringify(applied);
  document.getElementById("lv-apply").classList.toggle("is-ready", changed);
  document.getElementById("lv-scenario").textContent = describe(applied);
}

function describe(s) {
  const parts = Object.entries(s.agents).filter(([, k]) => k).map(([t, k]) => `Team ${t} ${k > 0 ? "+" : "−"}${Math.abs(k)} agent${Math.abs(k) === 1 ? "" : "s"}`);
  if (s.volume !== 100) parts.push(`${s.volume > 100 ? "+" : "−"}${Math.abs(s.volume - 100)}% customers`);
  return parts.length ? `Running now: ${parts.join(", ")}.` : "Running now: a normal day.";
}

function query() {
  const agents = Object.entries(applied.agents).filter(([, k]) => k).map(([t, k]) => `${t}:${k}`).join(",");
  return `seed=${seed}&agents=${encodeURIComponent(agents)}&volume=${(applied.volume / 100).toFixed(2)}`;
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
    showProgress();
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

// While the engine simulates, a bar fills over ~30 s so the wait feels like work, not a freeze.
function showProgress() {
  const bar = document.getElementById("lv-progress");
  if (!bar) return;
  bar.hidden = waitingSince === null;
  if (waitingSince !== null) {
    const done = Math.min(0.95, (Date.now() - waitingSince) / 30000);
    bar.firstElementChild.style.width = `${Math.round(done * 100)}%`;
  }
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
    const response = await fetch(`/api/live?weekday=${weekday}&minute=${minuteNow().toFixed(2)}&${query()}`, { cache: "no-store" });
    data = await response.json();
  } catch (error) {
    status.textContent = "The engine did not answer. Is the server still running?";
    poll = setTimeout(refresh, POLL_MS * 2);
    return;
  }
  if (data.error) {
    status.textContent = data.error;
    return;
  }
  if (!data.ready) {
    if (waitingSince === null) waitingSince = Date.now();
    status.textContent = `Simulating today on this laptop (${describe(applied).replace("Running now: ", "").replace(".", "")}, luck ${seed}): two ways of working, every customer, every minute…`;
    showProgress();
    poll = setTimeout(refresh, WAIT_MS);
    return;
  }
  waitingSince = null;
  showProgress();
  state.live = data;
  status.textContent = `Simulated on this laptop · the practice company's test day ${data.day} · luck ${data.seed}`;
  draw(data);
  poll = setTimeout(refresh, speed > 1 ? 1000 : POLL_MS);
}

function draw(d) {
  const lanes = [["baseline_d", "theirs"], ["opslens", "ours"]];
  lanes.forEach(([key, side]) => {
    const p = d.policies[key];
    if (!p) return;
    bump(`lv-m-${side}`, ev(`live.policies.${key}.missed`, "int"));
    document.getElementById(`lv-w-${side}`).innerHTML = ` ${ev(`live.policies.${key}.waiting`, "int")} waiting now`;
    drawFrameInto(document.getElementById(`lv-f-${side}`), d.agents, p.status, p.queues);
  });
  const theirs = d.policies.baseline_d ? d.policies.baseline_d.missed : 0;
  const ours = d.policies.opslens ? d.policies.opslens.missed : 0;
  document.getElementById("lv-saved").innerHTML = theirs > ours
    ? `<b>${theirs - ours}</b> more customer${theirs - ours === 1 ? "" : "s"} helped in time today, so far, with the same agents.`
    : theirs === ours ? "Even so far today." : `OpsLens is behind by ${ours - theirs} so far today.`;
  document.getElementById("lv-danger").innerHTML = d.danger.length ? d.danger.map((t, i) => `
      <div class="live-ticket">
        <div class="live-risk">${ev(`live.danger[${i}].probability`, "frac_pct")}
          <div class="live-after">${t.nobody_capable ? "nobody capable on shift"
            : `→ ${ev(`live.danger[${i}].if_served_now`, "frac_pct")} if served now`}</div></div>
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
    : `<p class="muted">Nobody is in danger right now. Quiet hours: press “Play the day fast” for the dinner rush.</p>`;
  document.getElementById("lv-decisions").innerHTML = d.decisions.length ? `<ul class="live-decisions">${d.decisions.map((x) => `
      <li><span class="live-when">${clockOf(x.minute)}</span>
        <strong>${escapeHtml(x.ticket_id)}</strong> → <strong>${escapeHtml(agentName(d.agents, x.agent))}</strong>
        <div class="small muted">${escapeHtml(x.reason)}</div></li>`).join("")}</ul>`
    : `<p class="muted">No assignment in the last 15 minutes.</p>`;
}

// Replace a counter and flash it when its value changed (motion that answers a change in the data).
function bump(id, html) {
  const el = document.getElementById(id);
  if (!el) return;
  const before = el.textContent;
  el.innerHTML = html;
  if (before !== el.textContent && before !== "…") {
    el.classList.remove("bumped");
    void el.offsetWidth; // restart the animation
    el.classList.add("bumped");
  }
}

function clockOf(minute) {
  const m = Math.floor(minute);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

function agentName(agents, id) {
  const a = agents.find((x) => x.id === id);
  return a && a.name && a.name !== id ? `${a.name} (${id})` : id;
}
