import { state } from "../data.js";
import { ev } from "../evidence.js";
import { drawFrameInto } from "../floormap.js";
import { escapeHtml, prettyKey, tidyDash } from "../format.js";
import { mascotHtml, customerHtml, biryaniHtml, cheer, setMood } from "../mascot.js";

const BUSY_WAITING = 60;
const POLL_MS = 5000;
const WAIT_MS = 2500;
const LANGUAGE = { hi: "Hindi", en: "English", other: "Regional" };
const TEAMS = { A: "Live orders", B: "Payments & refunds", C: "Order accuracy", D: "Account & app" };
const NORMAL = { agents: { A: 0, B: 0, C: 0, D: 0 }, volume: 100 };
const PRESETS = [
  { id: "normal", label: "Normal day", s: NORMAL },
  { id: "c-2", label: "Team C loses 2 agents", s: { agents: { A: 0, B: 0, C: -2, D: 0 }, volume: 100 } },
  { id: "sale", label: "Sale rush +40%", s: { agents: { A: 0, B: 0, C: 0, D: 0 }, volume: 140 } },
  { id: "storm", label: "Short-staffed rush", s: { agents: { A: 0, B: -1, C: -1, D: 0 }, volume: 130 } },
];

let seed = 1;
let tick = null;
let poll = null;
let speed = 1;
let fastMinute = null;
let listening = false;
let applied = clone(NORMAL);
let draft = clone(NORMAL);
let waitingSince = null;
let seenDecisions = new Set();
let lastGap = null;
const JOKE = "Dosa ke jagah biryani de diya!";
let lines = [JOKE];
let lineIndex = 0;
let talk = null;
let lastRun = "";

export function render(section) {
  section.innerHTML = `
    <section class="lv" aria-label="Live now">
      <header class="lv-hero">
        <div class="lv-when">
          <div class="lv-live"><span class="live-dot"></span><span id="lv-mode">Live</span> · <span id="lv-date"></span></div>
          <div class="lv-clock" id="lv-clock">--:--:--</div>
          <div class="lv-fine" id="lv-status">Starting…</div>
        </div>
        <div class="lv-impact">
          <div class="lv-col-title"><span class="live-dot"></span>Today so far, live</div>
          <div class="lv-big"><span id="lv-saved">…</span></div>
          <div class="lv-big-label" id="lv-saved-label">more customers helped in time today, with the same agents</div>
          <div class="lv-bars">
            <div class="lv-bar theirs"><span class="lv-bar-name">Industry standard</span><span class="lv-bar-track"><i id="lv-bar-theirs"></i></span><b id="lv-m-theirs">…</b><small>missed</small></div>
            <div class="lv-bar ours"><span class="lv-bar-name">OpsLens</span><span class="lv-bar-track"><i id="lv-bar-ours"></i></span><b id="lv-m-ours">…</b><small>missed</small></div>
          </div>
          <div class="lv-midnight" id="lv-midnight"></div>
        </div>
        <div class="lv-actions">
          <button type="button" class="btn btn-primary" id="lv-speed">▶ Play the evening</button>
          <button type="button" class="btn" id="lv-luck">↻ New luck</button>
        </div>
      </header>

      <div class="lv-scene" aria-hidden="true">
        <div class="lv-scene-customer">${customerHtml("lv-customer")}${biryaniHtml("lv-biryani")}<div class="lv-say" id="lv-say">${escapeHtml(JOKE)}</div></div>
        <div class="lv-scene-track"><i class="tk"></i><i class="tk"></i><i class="tk"></i><i class="tk"></i></div>
        <div class="lv-scene-lenny"><div class="lv-scene-status" id="lv-scene-status">Lenny is on shift</div>${mascotHtml("lv-mascot", "tired")}</div>
      </div>

      <div class="lv-floors">
        <div class="lv-lane"><div class="lv-lane-head"><b>Industry standard</b><span id="lv-w-theirs"></span></div><div class="floor" id="lv-f-theirs"></div></div>
        <div class="lv-lane is-ours"><div class="lv-lane-head"><b>OpsLens</b><span id="lv-w-ours"></span></div><div class="floor" id="lv-f-ours"></div></div>
        <div class="lv-wait" id="lv-wait" hidden><div class="lv-wait-box"><div class="spinner"></div>
          <div id="lv-wait-text">Simulating today on this laptop…</div><div class="live-progress"><i id="lv-progress"></i></div></div></div>
      </div>
      <div class="lv-key"><span><i class="tile busy"></i>agent at work</span><span><i class="tile cross"></i>rescue from another team</span>
        <span><i class="tile idle"></i>free</span><span><i class="dot"></i>customer waiting</span><span><i class="dot late"></i>promise missed</span></div>

      <div class="lv-whatif">
        <span class="lv-whatif-q">What if…</span>
        ${PRESETS.map((p) => `<button type="button" class="chip-btn" data-preset="${p.id}">${escapeHtml(p.label)}</button>`).join("")}
        <button type="button" class="chip-btn ghost" id="lv-custom-toggle" aria-expanded="false">Custom…</button>
      </div>
      <div class="lv-custom" id="lv-custom" hidden>
        ${Object.entries(TEAMS).map(([team, name]) => `
          <div class="stepper" data-team="${team}">
            <div class="stepper-label"><b>Team ${team}</b> ${name}</div>
            <div class="stepper-row">
              <button type="button" class="btn btn-sm" data-step="-1" aria-label="One agent fewer in team ${team}">−</button>
              <output id="lv-a-${team}">0</output>
              <button type="button" class="btn btn-sm" data-step="1" aria-label="One agent more in team ${team}">+</button>
            </div>
          </div>`).join("")}
        <label class="live-volume"><span><b>Customers</b> <output id="lv-vol-out">100%</output></span>
          <input type="range" id="lv-volume" min="50" max="200" step="10" value="100" aria-label="Customers today, percent of normal"></label>
        <button type="button" class="btn btn-primary" id="lv-apply">Run today</button>
      </div>

      <div class="lv-feeds">
        <section class="lv-feed"><h3>In danger right now</h3><div id="lv-danger"></div></section>
        <section class="lv-feed"><h3>Just decided by OpsLens</h3><ul class="lv-decisions" id="lv-decisions"></ul></section>
      </div>
    </section>`;

  section.querySelector("#lv-speed").addEventListener("click", toggleSpeed);
  section.querySelector("#lv-luck").addEventListener("click", () => { seed = (seed % 99) + 1; refresh(); });
  section.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    applied = clone(PRESETS.find((p) => p.id === b.dataset.preset).s);
    draft = clone(applied);
    showDraft();
    refresh();
  }));
  section.querySelector("#lv-custom-toggle").addEventListener("click", (event) => {
    const box = document.getElementById("lv-custom");
    box.hidden = !box.hidden;
    event.currentTarget.setAttribute("aria-expanded", String(!box.hidden));
  });
  section.querySelectorAll(".stepper [data-step]").forEach((b) => b.addEventListener("click", () => {
    const team = b.closest(".stepper").dataset.team;
    draft.agents[team] = Math.max(-5, Math.min(5, draft.agents[team] + Number(b.dataset.step)));
    showDraft();
  }));
  section.querySelector("#lv-volume").addEventListener("input", (e) => { draft.volume = Number(e.target.value); showDraft(); });
  section.querySelector("#lv-apply").addEventListener("click", () => { applied = clone(draft); showDraft(); refresh(); });
  section.querySelector("#lv-danger").addEventListener("click", (e) => {
    const card = e.target.closest(".lv-card");
    if (card && !e.target.closest(".ev")) card.classList.toggle("open");
  });
  showDraft();
  start();
  if (!listening) {
    listening = true;
    document.addEventListener("tab-shown", (event) => {
      document.body.classList.toggle("on-live", event.detail === "live");
      if (event.detail === "live") start(); else stop();
    });
  }
  document.body.classList.add("on-live");
}

function clone(s) {
  return { agents: { ...s.agents }, volume: s.volume };
}

function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function showDraft() {
  Object.keys(TEAMS).forEach((team) => {
    const out = document.getElementById(`lv-a-${team}`);
    if (!out) return;
    const k = draft.agents[team];
    out.textContent = k > 0 ? `+${k}` : String(k);
    out.className = k < 0 ? "minus" : k > 0 ? "plus" : "";
  });
  const vol = document.getElementById("lv-volume");
  if (vol) vol.value = draft.volume;
  const out = document.getElementById("lv-vol-out");
  if (out) out.textContent = `${draft.volume}%`;
  const preset = PRESETS.find((p) => same(p.s, applied));
  document.querySelectorAll("[data-preset]").forEach((b) => b.setAttribute("aria-pressed", String(preset && b.dataset.preset === preset.id)));
  const custom = document.getElementById("lv-custom-toggle");
  if (custom) custom.classList.toggle("is-on", !preset);
}

function describe(s) {
  const parts = Object.entries(s.agents).filter(([, k]) => k).map(([t, k]) => `Team ${t} ${k > 0 ? "+" : "−"}${Math.abs(k)}`);
  if (s.volume !== 100) parts.push(`${s.volume > 100 ? "+" : "−"}${Math.abs(s.volume - 100)}% customers`);
  return parts.length ? parts.join(", ") : "a normal day";
}

function query() {
  const agents = Object.entries(applied.agents).filter(([, k]) => k).map(([t, k]) => `${t}:${k}`).join(",");
  return `seed=${seed}&agents=${encodeURIComponent(agents)}&volume=${(applied.volume / 100).toFixed(2)}`;
}

function minuteNow() {
  if (speed > 1 && fastMinute !== null) return fastMinute;
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
}

function start() {
  stop();
  talk = setInterval(nextLine, 3600);
  showClock();
  tick = setInterval(() => {
    if (speed > 1 && fastMinute !== null) fastMinute = Math.min(1439, fastMinute + speed / 60);
    showClock();
    showProgress();
  }, 1000);
  refresh();
}

function stop() {
  clearInterval(talk);
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
    button.textContent = "▶ Play the evening";
  } else {
    speed = 180;
    fastMinute = 17 * 60;
    button.textContent = "■ Back to real time";
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
  document.getElementById("lv-mode").textContent = speed > 1 ? "Fast replay" : "Live";
  document.getElementById("lv-date").textContent = today.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function showProgress() {
  const wait = document.getElementById("lv-wait");
  if (!wait) return;
  wait.hidden = waitingSince === null;
  if (waitingSince !== null) {
    const done = Math.min(0.95, (Date.now() - waitingSince) / 30000);
    document.getElementById("lv-progress").style.width = `${Math.round(done * 100)}%`;
  }
}

async function refresh() {
  clearTimeout(poll);
  const weekday = (new Date().getDay() + 6) % 7;
  const status = document.getElementById("lv-status");
  if (!status) return;
  if (state.staticServer) {
    status.textContent = "Live now needs the OpsLens server.";
    return;
  }
  let data;
  try {
    const response = await fetch(`/api/live?weekday=${weekday}&minute=${minuteNow().toFixed(2)}&${query()}`, { cache: "no-store" });
    data = await response.json();
  } catch (error) {
    status.textContent = "The engine is not answering. Is the server running?";
    poll = setTimeout(refresh, POLL_MS * 2);
    return;
  }
  if (data.error) {
    status.textContent = data.error;
    return;
  }
  if (!data.ready) {
    if (waitingSince === null) waitingSince = Date.now();
    document.getElementById("lv-wait-text").textContent = `Simulating today on this laptop: ${describe(applied)}, every customer, every minute…`;
    showProgress();
    poll = setTimeout(refresh, WAIT_MS);
    return;
  }
  waitingSince = null;
  showProgress();
  state.live = data;
  loadMidnight();
  status.textContent = `Running on this laptop · ${describe(applied)} · practice customers, test day ${data.day} · luck ${data.seed}`;
  draw(data);
  poll = setTimeout(refresh, speed > 1 ? 1000 : POLL_MS);
}

function draw(d) {
  const theirs = d.policies.baseline_d;
  const ours = d.policies.opslens;
  if (!theirs || !ours) return;
  const top = Math.max(theirs.missed, ours.missed, 1);
  bump("lv-m-theirs", ev("live.policies.baseline_d.missed", "int"));
  bump("lv-m-ours", ev("live.policies.opslens.missed", "int"));
  document.getElementById("lv-bar-theirs").style.width = `${(100 * theirs.missed) / top}%`;
  document.getElementById("lv-bar-ours").style.width = `${(100 * ours.missed) / top}%`;
  const diff = theirs.missed - ours.missed;
  const runKey = query();
  if (lastGap !== null && lastRun === runKey && diff > lastGap) cheer("lv-mascot", `+${diff - lastGap} helped!`);
  lastGap = diff;
  lastRun = runKey;
  const waiting = ours.waiting;
  setMood("lv-mascot", waiting >= BUSY_WAITING ? "tired" : "idle");
  const status = document.getElementById("lv-scene-status");
  if (status) status.textContent = waiting >= BUSY_WAITING ? `${waiting} customers waiting… phew!` : `${waiting} waiting, all calm`;
  lines = [JOKE, ...d.danger.slice(0, 4).map((t) => t.text).filter(Boolean)];
  bump("lv-saved", String(Math.abs(diff)));
  document.getElementById("lv-saved-label").textContent = diff >= 0
    ? `more customer${diff === 1 ? "" : "s"} helped in time today, with the same agents`
    : `fewer helped in time so far today: the industry standard is ahead`;
  document.getElementById("lv-w-theirs").innerHTML = `${ev("live.policies.baseline_d.waiting", "int")} waiting`;
  document.getElementById("lv-w-ours").innerHTML = `${ev("live.policies.opslens.waiting", "int")} waiting`;
  drawFrameInto(document.getElementById("lv-f-theirs"), d.agents, theirs.status, theirs.queues);
  drawFrameInto(document.getElementById("lv-f-ours"), d.agents, ours.status, ours.queues);
  drawDanger(d);
  drawDecisions(d);
}

let midnightKey = "";
async function loadMidnight() {
  const key = query();
  const box = document.getElementById("lv-midnight");
  if (!box || key === midnightKey) return;
  midnightKey = key;
  const weekday = (new Date().getDay() + 6) % 7;
  try {
    const response = await fetch(`/api/live?weekday=${weekday}&minute=1439.9&${key}`, { cache: "no-store" });
    const d = await response.json();
    if (!d.ready) { midnightKey = ""; return; }
    const theirs = d.policies.baseline_d.missed;
    const ours = d.policies.opslens.missed;
    box.innerHTML = `By midnight (the whole day, already simulated): <b class="t">${theirs}</b> vs <b class="o">${ours}</b>
      missed, <b class="o">${theirs - ours}</b> more customers helped.`;
  } catch (error) {
    midnightKey = "";
  }
}

function drawDanger(d) {
  const box = document.getElementById("lv-danger");
  const open = new Set([...box.querySelectorAll(".lv-card.open")].map((c) => c.dataset.id));
  box.innerHTML = d.danger.length ? d.danger.slice(0, 3).map((t, i) => `
      <article class="lv-card ${open.has(t.ticket_id) ? "open" : ""}" data-id="${escapeHtml(t.ticket_id)}" tabindex="0">
        <div class="lv-risk">${ev(`live.danger[${i}].probability`, "frac_pct")}</div>
        <div class="lv-card-main">
          <div class="lv-card-head"><span class="pill ${t.priority === "P1" ? "p1" : ""}">${escapeHtml(t.priority)}</span>
            <b>${escapeHtml(prettyKey(t.category))}</b><span class="muted">${escapeHtml(LANGUAGE[t.language] || t.language)}</span>
            <span class="muted lv-left">${ev(`live.danger[${i}].minutes_left`, "min")} left</span></div>
          <div class="lv-quote">“${escapeHtml(t.text)}”</div>
          <div class="lv-why">${escapeHtml(tidyDash(t.reasons[0] || ""))}</div>
          <ul class="lv-more">${t.reasons.slice(1).map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
        </div>
        <div class="lv-fix">${t.nobody_capable ? `<span class="lv-fix-no">nobody capable on shift → rescue</span>`
          : `<span>if served now</span>${ev(`live.danger[${i}].if_served_now`, "frac_pct")}`}</div>
      </article>`).join("")
    : `<div class="lv-empty lv-sleep">${mascotHtml("lv-mascot-sleep", "sleep")}<p class="muted">Nobody in danger right now.
        Press “Play the evening” for the dinner rush.</p></div>`;
}

function drawDecisions(d) {
  const list = document.getElementById("lv-decisions");
  list.innerHTML = d.decisions.length ? d.decisions.slice(0, 5).map((x) => {
    const key = `${x.ticket_id}|${x.minute}`;
    const fresh = !seenDecisions.has(key);
    seenDecisions.add(key);
    const [tagClass, tagText] = tagOf(x.reason);
    return `<li class="${fresh ? "fresh" : ""}" title="${escapeHtml(x.reason)}">
        <span class="lv-time">${clockOf(x.minute)}</span>
        <span class="lv-who"><b>${escapeHtml(x.ticket_id)}</b> → ${escapeHtml(agentName(d.agents, x.agent))}</span>
        <span class="lv-tag ${tagClass}">${escapeHtml(tagText)}</span></li>`;
  }).join("") : `<li class="muted lv-empty">No assignment in the last 15 minutes.</li>`;
  if (seenDecisions.size > 400) seenDecisions = new Set([...seenDecisions].slice(-200));
}

function tagOf(reason) {
  const risk = reason.match(/breach risk ([\d.]+) -> ([\d.]+)/);
  if (/cross-skill/.test(reason)) return ["rescue", "cross-team rescue"];
  if (/past its SLA/.test(reason)) return ["late", "late: not forgotten"];
  if (risk) return ["save", `risk ${Math.round(risk[1] * 100)}% → ${Math.round(risk[2] * 100)}%`];
  return ["turn", "in turn"];
}

function bump(id, html) {
  const el = document.getElementById(id);
  if (!el) return;
  const before = el.textContent;
  el.innerHTML = html;
  if (before === "…") {
    countUp(el, "0", el.textContent);
    return;
  }
  if (before !== el.textContent) {
    countUp(el, before, el.textContent);
    el.classList.remove("bumped");
    void el.offsetWidth;
    el.classList.add("bumped");
  }
}

function nextLine() {
  const say = document.getElementById("lv-say");
  if (!say || !lines.length) return;
  lineIndex = (lineIndex + 1) % lines.length;
  const text = lines[lineIndex];
  say.textContent = text.length > 60 ? text.slice(0, 58) + "…" : text;
  say.classList.remove("pop");
  void say.offsetWidth;
  say.classList.add("pop");
}

function countUp(el, beforeText, afterText) {
  const from = parseInt(beforeText.replace(/[^\d-]/g, ""), 10);
  const to = parseInt(afterText.replace(/[^\d-]/g, ""), 10);
  if (!Number.isFinite(from) || !Number.isFinite(to) || from === to) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const holder = el.querySelector(".ev") || el;
  const finalText = holder.textContent;
  const started = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - started) / 700);
    const eased = 1 - Math.pow(1 - k, 3);
    holder.textContent = k < 1 ? String(Math.round(from + (to - from) * eased)) : finalText;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function clockOf(minute) {
  const m = Math.floor(minute);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

function agentName(agents, id) {
  const a = agents.find((x) => x.id === id);
  return a && a.name && a.name !== id ? a.name : id;
}
