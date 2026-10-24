// tabs/shadow.js — Shadow mode: a real day at a real IT desk, replayed, with OpsLens watching.
//
// Why (issue #16, the owner's addition): Live now shows OpsLens deciding on the simulated food
// floor. The real desk cannot be re-run with different decisions (a log is a log), but it can be
// replayed: incidents arrive at their real times, OpsLens's warning appears one hour after each
// opens (next to the desk's own priority field), and the real outcome appears when it really
// happened. The running tally counts real misses that each one warned about in time. Data:
// results.realdesk.shadow (frozen models, test months only; docs/explain/realdesk.md section 8).
// The running counts are the incident rows counted as the clock passes them; at the end they
// equal the day's summary, which is shown beside them as clickable numbers.
//
// Example (Thu 5 May 2016, 403 incidents): of the 102 deadlines the desk missed, OpsLens's top 20%
// at the 1-hour mark had warned about 53; the priority field's top 20% about 16.

import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, fold } from "../ui.js";
import { escapeHtml } from "../format.js";

const S = "realdesk.shadow";
const DAY_SHARE = 0.72; // share of the replay spent on the day itself; the rest fast-forwards the weeks after
const BASE_MS = 52000; // one full replay at 1× speed
const FEED_MAX = 9;

let timer = null;
let replay = null; // { dayIndex, events, cursor, t, end, playing, speed, counts }
let listening = false;

export function render(section) {
  const sh = state.results.realdesk && state.results.realdesk.shadow;
  if (!sh || !sh.shown_days || !sh.shown_days.length) {
    section.innerHTML = pageHeader("Shadow mode", "") + `<div class="callout warn">No shadow-mode data in this results file.</div>`;
    return;
  }
  const chips = sh.shown_days.map((d, i) => `<button type="button" class="sh-day" data-i="${i}">
      ${escapeHtml(d.weekday)} ${escapeHtml(prettyDate(d.date))}${d.date === sh.showcase ? " · busiest" : ""}</button>`).join("");
  section.innerHTML = `
    ${pageHeader("Shadow mode: a real day, replayed",
      "Real incidents from a real IT desk, at their real times. One hour after each opens, OpsLens gives its warning next to the desk's own priority field; the real outcome appears when it really happened.")}
    <div class="sh-honest"><b>Real incidents and real outcomes.</b> OpsLens only watched (shadow mode): a log cannot replay different decisions.
      Models frozen, test months only. ${evText(`${S}.privacy`)}</div>
    <div class="sh-days">${chips}</div>
    <section class="card sh-stage">
      <div class="sh-top">
        <div class="sh-clock"><span id="sh-date">…</span><b id="sh-time">00:00</b></div>
        <div class="sh-controls">
          <button type="button" class="btn btn-primary" id="sh-play">Pause</button>
          <button type="button" class="btn" id="sh-speed">Speed 1×</button>
          <button type="button" class="btn" id="sh-end">Jump to the end</button>
        </div>
      </div>
      <div class="sh-progress"><i id="sh-bar"></i><span class="sh-midnight" title="End of the day"></span></div>
      <div class="sh-grid">
        <div>
          <div class="sh-tally">
            <div class="sh-t is-miss"><span>Deadlines missed so far</span><b id="sh-missed">0</b></div>
            <div class="sh-t is-ours"><span>OpsLens had warned in time</span><b id="sh-ours">0</b><small id="sh-ours-of"></small></div>
            <div class="sh-t is-theirs"><span>Priority field had warned</span><b id="sh-theirs">0</b><small id="sh-theirs-of"></small></div>
          </div>
          <div class="sh-wall" id="sh-wall" aria-label="Each dot is one incident of the day"></div>
          <ul class="sh-legend">
            <li><i class="d-open"></i>open</li><li><i class="d-flag"></i>OpsLens top 20% at 1 hour</li>
            <li><i class="d-made"></i>met its deadline</li><li><i class="d-miss"></i>missed it</li>
            <li><i class="d-caught"></i>missed, and OpsLens had warned</li></ul>
        </div>
        <div class="sh-feed-box"><div class="sh-feed-title">What is happening</div><ol class="sh-feed" id="sh-feed"></ol></div>
      </div>
      <div class="sh-final" id="sh-final"></div>
    </section>
    ${card({ title: "If the desk had fast-tracked each picker's top 20% that day",
      sub: `<b>Assumption:</b> ${evText(`${S}.assumption`)}`, body: `<div id="sh-fast"></div>
        <p class="small muted">Per-day counts are small and close between pickers; the early-warning tally above is the story.</p>` })}
    ${card({ title: "The other busy days", sub: evText(`${S}.others_why`), body: daysTable(sh) })}
    ${fold("How shadow mode works", `<p>${evText(`${S}.how`)}</p>`)}`;

  section.querySelectorAll(".sh-day").forEach((b) => b.addEventListener("click", () => start(Number(b.dataset.i))));
  section.querySelector("#sh-play").addEventListener("click", togglePlay);
  section.querySelector("#sh-speed").addEventListener("click", cycleSpeed);
  section.querySelector("#sh-end").addEventListener("click", () => { if (replay) { replay.t = replay.end; step(0); } });
  if (!listening) {
    listening = true; // once per page: the view can be drawn again after a world switch
    document.addEventListener("tab-shown", (event) => {
      if (event.detail !== "rd-shadow") pause();
      else if (replay && replay.wasPlaying) play();
    });
  }
  start(0);
}

function prettyDate(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

// The day's summary numbers and the fast-track counts, as clickable paths.
function finalHtml(i) {
  const s = `${S}.shown_days[${i}].summary`;
  return `<p>By the end of the log: the desk missed <b>${ev(s + ".actual_misses_benchmark", "int")}</b> deadlines among
    ${ev(s + ".benchmark_incidents", "int")} Moderate/Low incidents. OpsLens's top 20% had warned about
    <b class="t-ours">${ev(s + ".opslens.caught", "int")}</b> of them (${ev(s + ".opslens.recall_pct", "pct")}; ${ev(s + ".opslens.precision_pct", "pct")} of its warnings were right);
    the priority field's top 20% about <b class="t-theirs">${ev(s + ".priority.caught", "int")}</b>
    (${ev(s + ".priority.recall_pct", "pct")}; ${ev(s + ".priority.precision_pct", "pct")} right).</p>`;
}

function fastHtml(i) {
  const f = `${S}.shown_days[${i}].summary.fast_track_saved`;
  return `<div class="sh-fast">
      <div><b>${ev(f + ".opslens", "int")}</b><span>OpsLens's top 20%</span></div>
      <div><b>${ev(f + ".priority", "int")}</b><span>the priority field's top 20%</span></div>
      <div><b>${ev(f + ".unassigned", "int")}</b><span>still unassigned at 1 hour</span></div>
    </div><p class="small muted">Missed deadlines that fast-tracking would have saved, under the assumption above.</p>`;
}

function daysTable(sh) {
  const rows = sh.shown_days.map((d, i) => {
    const s = `${S}.shown_days[${i}].summary`;
    return `<tr><td>${escapeHtml(d.weekday)} ${escapeHtml(prettyDate(d.date))}</td>
      <td class="num">${ev(s + ".incidents", "int")}</td><td class="num">${ev(s + ".actual_misses_benchmark", "int")}</td>
      <td class="num"><b>${ev(s + ".opslens.caught", "int")}</b></td><td class="num">${ev(s + ".priority.caught", "int")}</td>
      <td class="num">${ev(s + ".fast_track_saved.opslens", "int")} / ${ev(s + ".fast_track_saved.priority", "int")} / ${ev(s + ".fast_track_saved.unassigned", "int")}</td></tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr><th>Day</th><th class="num">Incidents</th><th class="num">Missed (Moderate/Low)</th>
    <th class="num">OpsLens warned</th><th class="num">Priority field warned</th><th class="num">Fast-track saved: OpsLens / priority / unassigned</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

// ---- the replay ----------------------------------------------------------------------------------

function start(dayIndex) {
  pause();
  const day = state.results.realdesk.shadow.shown_days[dayIndex];
  const last = Math.max(1440, ...day.incidents.map((x) => (x.resolved_at === null ? 0 : x.resolved_at)));
  const events = [];
  day.incidents.forEach((x, i) => {
    events.push({ t: x.opened_at, kind: "open", i });
    events.push({ t: x.opened_at + 60, kind: "flag", i });
    events.push({ t: x.resolved_at === null ? last : x.resolved_at, kind: "end", i });
  });
  events.sort((a, b) => a.t - b.t || "ofe".indexOf(a.kind[0]) - "ofe".indexOf(b.kind[0]));
  replay = { dayIndex, day, events, cursor: 0, t: 0, p: 0, end: last, playing: false, speed: replay ? replay.speed : 1,
             counts: { missed: 0, ours: 0, theirs: 0 } };
  document.querySelectorAll(".sh-day").forEach((b) => b.setAttribute("aria-pressed", Number(b.dataset.i) === dayIndex ? "true" : "false"));
  const wall = document.getElementById("sh-wall");
  wall.innerHTML = day.incidents.map((x, i) => `<i data-i="${i}" class="${x.in_benchmark ? "" : "is-out"}" title="${escapeHtml(x.ticket_id)}"></i>`).join("");
  document.getElementById("sh-feed").innerHTML = "";
  document.getElementById("sh-final").innerHTML = "";
  document.getElementById("sh-fast").innerHTML = fastHtml(dayIndex);
  document.getElementById("sh-ours-of").textContent = "";
  document.getElementById("sh-theirs-of").textContent = "";
  drawCounts();
  drawClock();
  play();
}

// Progress p (0..1) → minutes: the day runs linearly, the weeks after on a log scale.
function minutesAt(p) {
  if (p <= DAY_SHARE) return (p / DAY_SHARE) * 1440;
  const q = (p - DAY_SHARE) / (1 - DAY_SHARE);
  return 1440 * Math.pow(replay.end / 1440, q);
}

function play() {
  if (!replay) return;
  replay.playing = true;
  replay.wasPlaying = true;
  document.getElementById("sh-play").textContent = "Pause";
  clearInterval(timer);
  timer = setInterval(() => step(100 / BASE_MS), 100);
}
function pause() {
  clearInterval(timer);
  timer = null;
  if (replay) replay.playing = false;
  const b = document.getElementById("sh-play");
  if (b) b.textContent = "Play";
}
function togglePlay() {
  if (!replay) return;
  if (replay.playing) { pause(); replay.wasPlaying = false; return; }
  if (replay.t >= replay.end) { start(replay.dayIndex); return; }
  play();
}
function cycleSpeed() {
  if (!replay) return;
  replay.speed = replay.speed === 1 ? 3 : replay.speed === 3 ? 8 : 1;
  document.getElementById("sh-speed").textContent = `Speed ${replay.speed}×`;
}

function step(dp) {
  if (!replay || !document.getElementById("sh-wall")) { pause(); return; }
  if (dp > 0) {
    replay.p = Math.min(1, replay.p + dp * replay.speed);
    replay.t = minutesAt(replay.p);
  } else {
    replay.p = 1;
  }
  const feed = [];
  while (replay.cursor < replay.events.length && replay.events[replay.cursor].t <= replay.t) {
    const e = replay.events[replay.cursor++];
    const line = apply(e);
    if (line) feed.push(line);
  }
  if (feed.length) pushFeed(feed.slice(-FEED_MAX));
  drawCounts();
  drawClock();
  if (replay.p >= 1 || replay.t >= replay.end) {
    replay.t = replay.end;
    pause();
    replay.wasPlaying = false;
    document.getElementById("sh-final").innerHTML = finalHtml(replay.dayIndex);
  }
}

// One event: update the incident's dot and the tally; return a feed line for the notable ones.
function apply(e) {
  const x = replay.day.incidents[e.i];
  const dot = document.querySelector(`#sh-wall i[data-i="${e.i}"]`);
  const when = clock(e.t);
  if (e.kind === "open") {
    if (dot) dot.classList.add("is-open");
    return x.in_benchmark && replay.t < 1440 && e.i % 6 === 0 // every sixth arrival, so the feed stays readable
      ? `<li><time>${when}</time> ${escapeHtml(x.ticket_id)} opened · ${escapeHtml(x.priority)}</li>` : "";
  }
  if (e.kind === "flag") {
    if (x.top20_opslens && dot) dot.classList.add("is-flag");
    if (!x.top20_opslens) return "";
    const why = x.reasons && x.reasons[0] ? escapeHtml(x.reasons[0].text) : "";
    return `<li class="f-flag"><time>${when}</time> OpsLens warns: <b>${escapeHtml(x.ticket_id)}</b> ${Math.round(x.risk * 100)}% risk${why ? ` · ${why}` : ""}${x.top20_priority ? " · the priority field agrees" : ""}</li>`;
  }
  // The real outcome.
  const missed = x.made_sla === false;
  if (dot) dot.classList.add(missed ? (x.top20_opslens ? "is-caught" : "is-miss") : "is-made");
  if (!x.in_benchmark || !missed) return "";
  replay.counts.missed += 1;
  if (x.top20_opslens) replay.counts.ours += 1;
  if (x.top20_priority) replay.counts.theirs += 1;
  const note = x.top20_opslens ? "OpsLens had warned ✓" : x.top20_priority ? "only the priority field had warned" : "nobody had warned";
  return `<li class="${x.top20_opslens ? "f-caught" : "f-miss"}"><time>${when}</time> ${escapeHtml(x.ticket_id)} missed its deadline · ${note}</li>`;
}

function pushFeed(lines) {
  const feed = document.getElementById("sh-feed");
  feed.insertAdjacentHTML("afterbegin", lines.reverse().join(""));
  while (feed.children.length > FEED_MAX) feed.lastElementChild.remove();
}

function drawCounts() {
  const c = replay.counts;
  document.getElementById("sh-missed").textContent = c.missed;
  document.getElementById("sh-ours").textContent = c.ours;
  document.getElementById("sh-theirs").textContent = c.theirs;
  const pct = (a) => (c.missed ? `${Math.round((a / c.missed) * 100)}% of misses so far` : "");
  document.getElementById("sh-ours-of").textContent = pct(c.ours);
  document.getElementById("sh-theirs-of").textContent = pct(c.theirs);
}

// "Thu 5 May · 14:32" during the day; "+3 days" after it.
function clock(t) {
  if (t < 1440) {
    const h = Math.floor(t / 60), m = Math.floor(t % 60);
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }
  const days = Math.floor(t / 1440);
  return days < 14 ? `+${days} day${days > 1 ? "s" : ""}` : `+${Math.round(days / 7)} weeks`;
}

function drawClock() {
  const d = replay.day;
  document.getElementById("sh-date").textContent = `${d.weekday} ${prettyDate(d.date)}${replay.t >= 1440 ? " · the weeks after" : ""}`;
  document.getElementById("sh-time").textContent = clock(replay.t);
  document.getElementById("sh-bar").style.width = `${(replay.p * 100).toFixed(1)}%`;
  document.querySelector(".sh-midnight").style.left = `${DAY_SHARE * 100}%`;
}
