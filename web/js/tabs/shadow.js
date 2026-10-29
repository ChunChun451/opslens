import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, fold } from "../ui.js";
import { escapeHtml, tidyDash } from "../format.js";
import { plainReason, rivalWords, itemWord } from "./yourfile.js";

const S = "realdesk.shadow";
const F = "upload.shadow";
const DAY_SHARE = 0.72;
const BASE_MS = 52000;
const FEED_MAX = 9;

let timer = null;
let replay = null;
let listening = false;

function onFile() {
  return state.world === "real" && state.realSource === "upload" && Boolean(state.upload && state.upload.shadow);
}

export function render(section) {
  if (onFile()) {
    renderFile(section);
    return;
  }
  const sh = state.results.realdesk && state.results.realdesk.shadow;
  if (!sh || !sh.shown_days || !sh.shown_days.length) {
    section.innerHTML = pageHeader("Shadow mode", "") + `<div class="callout warn">No shadow-mode data in this results file.</div>`;
    return;
  }
  const chips = sh.shown_days.map((d, i) => `<button type="button" class="sh-day" data-i="${i}">
      ${escapeHtml(d.weekday)} ${escapeHtml(prettyDate(d.date))}${d.date === sh.showcase ? " · busiest" : ""}</button>`).join("");
  section.innerHTML = `
    ${pageHeader("Shadow mode: a later day, replayed",
      "Real incidents at their real times. OpsLens only watches and warns; the outcome is what really happened.")}
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
    ${fold("If the desk had fast-tracked each picker's top 20% that day", `<p class="small"><b>Assumption:</b> ${evText(`${S}.assumption`)}</p>
      <div id="sh-fast"></div><p class="small muted">Per-day counts are small and close between pickers; the early-warning tally above is the story.</p>`)}
    ${fold("The other busy days", `<p class="small muted">${evText(`${S}.others_why`)}</p>${daysTable(sh)}`)}
    ${fold("How shadow mode works", `<p>${evText(`${S}.how`)}</p><p class="small muted">Models frozen, test months only. ${evText(`${S}.privacy`)}</p>`)}`;

  section.querySelectorAll(".sh-day").forEach((b) => b.addEventListener("click", () => start(Number(b.dataset.i))));
  wireControls(section);
  start(0);
}

function wireControls(section) {
  section.querySelector("#sh-play").addEventListener("click", togglePlay);
  section.querySelector("#sh-speed").addEventListener("click", cycleSpeed);
  section.querySelector("#sh-end").addEventListener("click", () => { if (replay) { replay.t = replay.end; step(0); } });
  if (!listening) {
    listening = true;
    document.addEventListener("tab-shown", (event) => {
      if (event.detail !== "rd-shadow" && event.detail !== "up-shadow") pause();
      else if (replay && replay.wasPlaying) play();
    });
  }
}

function renderFile(section) {
  const r = state.upload;
  const theirs = r.warning.vs.rival === "priority" ? "Your priority field" : "The rule of thumb";
  const head = pageHeader("Shadow mode: a later day, replayed",
    `Real ${itemWord()} at their real times. OpsLens only watches and warns; the outcome is what really happened.`);
  const honest = "";
  if (!r.shadow.timeline) {
    section.innerHTML = head + honest + card({ body: `<p>${evText(`${F}.timeline_note`)}</p><div class="sh-final">${fileFinal()}</div>` });
    return;
  }
  section.innerHTML = `${head}${honest}
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
            <div class="sh-t is-miss"><span>Real misses so far</span><b id="sh-missed">0</b></div>
            <div class="sh-t is-ours"><span>OpsLens had flagged</span><b id="sh-ours">0</b><small id="sh-ours-of"></small></div>
            <div class="sh-t is-theirs"><span>${escapeHtml(theirs)} had flagged</span><b id="sh-theirs">0</b><small id="sh-theirs-of"></small></div>
          </div>
          <div class="sh-wall" id="sh-wall" aria-label="Each dot is one item of the day"></div>
          <ul class="sh-legend">
            <li><i class="d-open"></i>open</li><li><i class="d-flag"></i>flagged by OpsLens as it opened</li>
            <li><i class="d-made"></i>ended in time</li><li><i class="d-miss"></i>missed</li>
            <li><i class="d-caught"></i>missed, and OpsLens had flagged it</li></ul>
        </div>
        <div class="sh-feed-box"><div class="sh-feed-title">What is happening</div><ol class="sh-feed" id="sh-feed"></ol></div>
      </div>
      <div class="sh-final" id="sh-final"></div>
    </section>
    ${fold("How shadow mode works on your file", `<p>Every item of the day appears at the minute it opened. OpsLens scores it at once,
      from what was known then (the time, how busy it was, and the columns it learned from), and flags the riskiest share of
      the day; ${rivalWords(r)} flags the same number. When the item really ended, its dot turns red if it missed. The tally
      counts the real misses each one had flagged. Nothing is changed: every outcome is your file's own.</p>`)}`;
  wireControls(section);
  start(0);
}

function fileDay() {
  const r = state.upload;
  const rival = r.warning.vs.rival;
  return { date: r.shadow.date, weekday: r.shadow.weekday, incidents: r.shadow.timeline.map((x) => ({
    ticket_id: x.id, opened_at: x.opened_min, resolved_at: x.ended_min, in_benchmark: true, made_sla: !x.missed,
    top20_opslens: x.flagged.includes("opslens"), top20_priority: x.flagged.includes(rival), priority: x.priority || "",
    risk: x.risk, reasons: (x.reasons || []).map((reason) => ({ text: plainReason(reason.text), share: reason.share })) })) };
}

function fileFinal() {
  const rival = state.upload.warning.vs.rival;
  return `<p>Once every item of that day had ended: <b>${ev(F + ".misses", "int")}</b> of its ${ev(F + ".items", "int")} ${itemWord()} really missed.
    OpsLens's ${ev(F + ".flags", "int")} flags had caught <b class="t-ours">${ev(F + ".caught.opslens", "int")}</b> of them;
    the ${ev(F + ".flags", "int")} flags of ${rivalWords(state.upload)} caught <b class="t-theirs">${ev(`${F}.caught.${rival}`, "int")}</b>.</p>`;
}

function prettyDate(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

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

function start(dayIndex) {
  pause();
  const file = onFile();
  const day = file ? fileDay() : state.results.realdesk.shadow.shown_days[dayIndex];
  const flagAt = file ? 0 : 60;
  const last = Math.max(1440, ...day.incidents.map((x) => (x.resolved_at === null ? 0 : x.resolved_at)));
  const events = [];
  day.incidents.forEach((x, i) => {
    events.push({ t: x.opened_at, kind: "open", i });
    events.push({ t: x.opened_at + flagAt, kind: "flag", i });
    events.push({ t: x.resolved_at === null ? last : x.resolved_at, kind: "end", i });
  });
  events.sort((a, b) => a.t - b.t || "ofe".indexOf(a.kind[0]) - "ofe".indexOf(b.kind[0]));
  replay = { dayIndex, day, events, cursor: 0, t: 0, p: 0, end: last, playing: false, speed: replay ? replay.speed : 1,
             counts: { missed: 0, ours: 0, theirs: 0 }, file, dayShare: file && last <= 1500 ? 1 : DAY_SHARE,
             theirs: file ? rivalWords(state.upload) : "the priority field" };
  document.querySelectorAll(".sh-day").forEach((b) => b.setAttribute("aria-pressed", Number(b.dataset.i) === dayIndex ? "true" : "false"));
  const wall = document.getElementById("sh-wall");
  wall.innerHTML = day.incidents.map((x, i) => `<i data-i="${i}" class="${x.in_benchmark ? "" : "is-out"}" title="${escapeHtml(x.ticket_id)}"></i>`).join("");
  document.getElementById("sh-feed").innerHTML = "";
  document.getElementById("sh-final").innerHTML = "";
  if (!file) document.getElementById("sh-fast").innerHTML = fastHtml(dayIndex);
  document.getElementById("sh-ours-of").textContent = "";
  document.getElementById("sh-theirs-of").textContent = "";
  drawCounts();
  drawClock();
  play();
}

function minutesAt(p) {
  const share = replay.dayShare;
  if (p <= share) return (p / share) * 1440;
  const q = (p - share) / (1 - share);
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
    document.getElementById("sh-final").innerHTML = replay.file ? fileFinal() : finalHtml(replay.dayIndex);
  }
}

function apply(e) {
  const x = replay.day.incidents[e.i];
  const dot = document.querySelector(`#sh-wall i[data-i="${e.i}"]`);
  const when = clock(e.t);
  if (e.kind === "open") {
    if (dot) dot.classList.add("is-open");
    return x.in_benchmark && replay.t < 1440 && e.i % 6 === 0
      ? `<li><time>${when}</time> ${escapeHtml(x.ticket_id)} opened${x.priority ? ` · ${escapeHtml(x.priority)}` : ""}</li>` : "";
  }
  if (e.kind === "flag") {
    if (x.top20_opslens && dot) dot.classList.add("is-flag");
    if (!x.top20_opslens) return "";
    const why = x.reasons && x.reasons[0] ? escapeHtml(tidyDash(x.reasons[0].text)) : "";
    return `<li class="f-flag"><time>${when}</time> ${replay.file ? "OpsLens flags" : "OpsLens warns"}: <b>${escapeHtml(x.ticket_id)}</b> ${Math.round(x.risk * 100)}% risk${why ? ` · ${why}` : ""}${x.top20_priority ? ` · ${replay.theirs} agrees` : ""}</li>`;
  }
  const missed = x.made_sla === false;
  if (dot) dot.classList.add(missed ? (x.top20_opslens ? "is-caught" : "is-miss") : "is-made");
  if (!x.in_benchmark || !missed) return "";
  replay.counts.missed += 1;
  if (x.top20_opslens) replay.counts.ours += 1;
  if (x.top20_priority) replay.counts.theirs += 1;
  const verb = replay.file ? "flagged it" : "warned";
  const note = x.top20_opslens ? `OpsLens had ${verb} ✓` : x.top20_priority ? `only ${replay.theirs} had ${verb}` : `nobody had ${verb}`;
  return `<li class="${x.top20_opslens ? "f-caught" : "f-miss"}"><time>${when}</time> ${escapeHtml(x.ticket_id)} ${replay.file ? "missed" : "missed its deadline"} · ${note}</li>`;
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
  const after = replay.file ? " · after that day" : " · the weeks after";
  document.getElementById("sh-date").textContent = `${d.weekday} ${prettyDate(d.date)}${replay.t >= 1440 ? after : ""}`;
  document.getElementById("sh-time").textContent = clock(replay.t);
  document.getElementById("sh-bar").style.width = `${(replay.p * 100).toFixed(1)}%`;
  document.querySelector(".sh-midnight").style.left = `${replay.dayShare * 100}%`;
}
