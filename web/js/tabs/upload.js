import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { backendMissing, postJson, fold } from "../ui.js";
import { escapeHtml } from "../format.js";

const POLL_MS = 500;
const PHASES = [
  ["Reading your file", ["Reading the file and the column mapping", "Checking the file can be learned from"]],
  ["Learning from the first 70%", ["Building what was known when each item opened", "Learning on the first 70% of items"]],
  ["Checking the last 30% it never saw", ["Scoring the last 30%, which it never saw", "Shadow mode on the busiest later day"]],
  ["Building your screens", ["Finding recurring problems, then checking them on later items", "Forecasting each team's workload a week ahead"]],
];
const ENGINE_STEPS = PHASES.reduce((n, [, steps]) => n + steps.length, 0);
const PARTS = [
  ["created_at", "Starts (a date, or a date and time)", "time"],
  ["created_time", "Start time, if it is in its own column", "time"],
  ["resolved_at", "Ends at (a date and time)", "time"],
  ["duration_min", "Or: how many minutes it took", "number"],
  ["id", "ID of each item", "any"],
  ["priority", "Priority", "any"],
  ["team", "Team, queue or city", "any"],
  ["category", "Category or type", "any"],
  ["sla_met", "Says if it was on time (yes or no)", "any"],
  ["breached", "Says if it missed (yes or no)", "any"],
  ["due_at", "Due by (a date and time)", "time"],
];
const PART_WORD = { created_at: "starts", created_time: "starts", resolved_at: "ends", duration_min: "ends", sla_met: "miss",
                    breached: "miss", due_at: "due", team: "group", category: "group", priority: "priority", id: "id" };
const MISS_PARTS = ["sla_met", "breached", "due_at"];

let box = null;
let hooks = {};
let file = "";
let peeked = null;
let parts = {};
let target = null;
let typed = false;
let asking = [];
let adjusting = false;
let shown = false;

export function openUpload(container, callbacks) {
  box = container;
  hooks = callbacks || {};
  shown = true;
  if (!box.dataset.wired) {
    box.dataset.wired = "1";
    box.addEventListener("click", onClick);
    box.addEventListener("change", onChange);
  }
  drawDrop();
}

export function closeUpload() {
  shown = false;
  if (box) box.innerHTML = "";
}

function paint(html) {
  if (!shown) return false;
  box.innerHTML = html;
  return true;
}

function onClick(event) {
  const t = event.target;
  if (t.closest("[data-up-close]")) { if (hooks.closed) hooks.closed(); return; }
  if (t.closest("[data-up-other]")) { drawDrop(); return; }
  const answerButton = t.closest("[data-answer]");
  if (answerButton) { answer(answerButton.dataset.role, answerButton.dataset.answer); return; }
  const adjust = t.closest("[data-adjust]");
  if (adjust) toggleAdjust(adjust.dataset.adjust === "learn");
  if (t.closest("#up-run")) run();
}

function onChange(event) {
  const t = event.target;
  if (t.matches("select[data-part]")) setPart(t.dataset.part, t.value);
  else if (t.matches("select[data-end]")) setPart(...t.value.split("|"));
  else if (t.matches("select[data-miss]")) setMiss(t.value);
  else if (t.matches("#up-target")) {
    const minutes = Number(t.value);
    if (minutes > 0) { typed = true; target = minutes; recheck(); }
  } else if (t.matches("[data-learn]")) {
    const name = t.dataset.learn;
    parts.features = (parts.features || []).filter((f) => f !== name).concat(t.checked ? [name] : []);
    recheck();
  }
}

function closeButton() {
  return `<button type="button" class="up-close" data-up-close aria-label="Close the upload card">×</button>`;
}

function drawDrop(problem = "") {
  const drawn = paint(`<section class="card up-card" aria-label="Upload a CSV">${headHtml(true, 1)}
      <div class="up-drop" id="up-drop">
        <svg class="up-drop-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V4.5M7.5 9L12 4.5 16.5 9"/>
          <path d="M4.5 15v3.5a1.5 1.5 0 001.5 1.5h12a1.5 1.5 0 001.5-1.5V15"/></svg>
        <p class="up-drop-title">Drop a CSV of tickets, incidents or orders</p>
        <div class="up-drop-actions"><button type="button" class="btn btn-primary" id="up-choose">Choose file</button>
          <button type="button" class="link-btn" id="up-uci">or try the UCI example</button></div>
        <p class="up-drop-sub">Each row is one ticket, incident or order, with when it started and when it ended or how many minutes it took.
          A team, category, priority or on-time column helps, but is not needed.</p>
        <input type="file" id="up-file" accept=".csv,text/csv,text/plain" hidden>
      </div>
      <p class="up-fine">Read by the OpsLens server on this laptop.</p>
      ${problem ? problemHtml(problem) : ""}
    </section>`);
  if (!drawn) return;
  const zone = box.querySelector("#up-drop");
  const input = box.querySelector("#up-file");
  box.querySelector("#up-choose").addEventListener("click", () => input.click());
  input.addEventListener("change", () => { if (input.files[0]) sendFile(input.files[0]); });
  box.querySelector("#up-uci").addEventListener("click", () => {
    const form = new FormData();
    form.append("example", "uci_incidents");
    send(form, "uci_one_row.csv");
  });
  ["dragenter", "dragover"].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((type) => zone.addEventListener(type, () => zone.classList.remove("is-over")));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    const dropped = event.dataTransfer && event.dataTransfer.files[0];
    if (dropped) sendFile(dropped);
  });
}

function sendFile(chosen) {
  const form = new FormData();
  form.append("file", chosen);
  send(form, chosen.name);
}

async function send(form, name) {
  file = name;
  if (state.staticServer) {
    paint(`<section class="card up-card">${closeButton()}${backendMissing("POST /api/anyfile/peek", "Start the OpsLens server to read your file.")}</section>`);
    return;
  }
  paint(`<section class="card up-card">${headHtml(true, 1)}<div class="wait" role="status"><span class="spinner" aria-hidden="true"></span>
      <span class="wait-text">Reading ${escapeHtml(name)}…</span></div></section>`);
  let data;
  try {
    const response = await fetch("/api/anyfile/peek", { method: "POST", body: form });
    data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The server could not read this file. Try another file.");
  } catch (error) {
    const sentence = /Failed to fetch|NetworkError|Load failed/.test(error.message)
      ? "The OpsLens server is not answering. Start it, then try again." : error.message;
    refuse(sentence);
    drawDrop(sentence);
    return;
  }
  file = data.name || name;
  peeked = data;
  state.uploadpeek = data;
  parts = { ...data.suggested };
  typed = false;
  target = data.plan && data.plan.miss && data.plan.miss.rule === "promise" ? data.plan.miss.target_min : null;
  asking = [...data.ask];
  adjusting = false;
  if (asking.length) drawQuestion();
  else drawConfirm();
}

function noun(one = false) {
  const word = (peeked && peeked.noun) || "items";
  return one ? word.replace(/s$/, "") : word;
}

function usedColumns() {
  return new Set(Object.entries(parts).filter(([key, value]) => key !== "features" && value).map(([, value]) => value));
}

function drawQuestion() {
  const q = asking[0];
  const used = usedColumns();
  const options = q.options.filter((o) => !used.has(o.column));
  if (!options.length) {
    asking = [];
    adjusting = true;
    drawConfirm(q.role === "created_at"
      ? `This file has no column that says when an ${noun(true)} started. Pick the column under Change columns, or try another file.`
      : `This file has no time an ${noun(true)} ended or took. Pick the column under Change columns, or try another file.`);
    return;
  }
  paint(`<section class="card up-card">${headHtml(true, 2)}
      <div class="up-question"><p class="up-q-text">${escapeHtml(q.text)}</p>
        <div class="up-answers">${options.map((o) => `<button type="button" class="btn" data-role="${o.role}"
          data-answer="${escapeHtml(o.column)}">${escapeHtml(o.column)}</button>`).join("")}</div></div>
      ${previewHtml(true)}</section>`);
}

function answer(role, column) {
  parts[role] = column;
  if (role === "resolved_at") delete parts.duration_min;
  if (role === "duration_min") delete parts.resolved_at;
  parts.features = (parts.features || []).filter((f) => f !== column);
  asking.shift();
  if (asking.length) drawQuestion();
  else recheck();
}

async function recheck() {
  try {
    const plan = await postJson("/api/anyfile/check", { token: peeked.token, mapping: cleanParts(), target_min: typed ? target : null });
    state.uploadpeek = { ...state.uploadpeek, plan };
    if (plan.miss && plan.miss.rule === "promise") target = plan.miss.target_min;
    drawConfirm();
  } catch (error) {
    drawConfirm(cleanError(error.message));
  }
}

function cleanParts() {
  const out = {};
  Object.entries(parts).forEach(([key, value]) => { if (key !== "features" && value) out[key] = value; });
  const used = new Set(Object.values(out));
  out.features = (parts.features || []).filter((f) => !used.has(f));
  return out;
}

function setPart(part, column) {
  if (column) parts[part] = column;
  else delete parts[part];
  if (column && part === "resolved_at") delete parts.duration_min;
  if (column && part === "duration_min") delete parts.resolved_at;
  if (column && MISS_PARTS.includes(part)) MISS_PARTS.filter((p) => p !== part).forEach((p) => delete parts[p]);
  parts.features = (parts.features || []).filter((f) => f !== column);
  recheck();
}

function setMiss(value) {
  const [part, column] = value.split("|");
  MISS_PARTS.forEach((p) => delete parts[p]);
  if (column) parts[part] = column;
  else typed = false;
  recheck();
}

function drawConfirm(forced = "") {
  const plan = state.uploadpeek && state.uploadpeek.plan;
  const problem = forced || (plan && plan.problem) || "";
  refuse(problem);
  paint(`<section class="card up-card">${headHtml(true, 2)}
      ${plan ? summaryHtml(plan) : ""}
      ${problem ? problemHtml(problem) : ""}
      ${plan ? `<dl class="up-facts">${facts(plan)}</dl>` : ""}
      <div class="up-go"><button type="button" class="btn btn-primary btn-lg" id="up-run" ${problem || !plan ? "disabled" : ""}>Analyse my file</button>
        <button type="button" class="link-btn" data-adjust aria-expanded="${adjusting}">Change columns</button>
        <button type="button" class="link-btn" data-up-other>Choose another file</button></div>
      <div class="up-adjust" id="up-adjust" ${adjusting ? "" : "hidden"}>${adjustHtml()}</div>
      ${previewHtml(false)}
    </section>`);
}

function toggleAdjust(toLearn) {
  adjusting = toLearn ? true : !adjusting;
  const panel = box.querySelector("#up-adjust");
  if (!panel) return;
  panel.hidden = !adjusting;
  box.querySelectorAll("[data-adjust]").forEach((b) => b.setAttribute("aria-expanded", String(adjusting)));
  if (toLearn) box.querySelector("#up-learn").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function day(iso) {
  const d = new Date(String(iso).slice(0, 10) + "T00:00:00Z");
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

function summaryHtml(plan) {
  const P = "uploadpeek.plan";
  const skipped = plan.rows !== plan.items
    ? `<p class="up-sum-note">${ev(`${P}.items`, "int")} of your ${ev(`${P}.rows`, "int")} rows can be read; the rest are left out.</p>` : "";
  return `<div class="up-sum"><p class="up-sum-main"><b>${ev(`${P}.items`, "int")}</b> ${noun()}, ${evText(`${P}.from`, day(plan.from))} to ${evText(`${P}.to`, day(plan.to))}</p>
      ${skipped}<p class="up-sum-how">OpsLens learns on the first ${ev(`${P}.learn_items`, "int")}, then checks itself on the last
        ${ev(`${P}.test_items`, "int")}, which it never sees while learning. Check what it read, then analyse.</p></div>`;
}

function fact(label, value, note = "") {
  return `<div class="up-fact"><dt>${label}</dt><dd><div class="up-fact-v">${value}</div>${note ? `<p class="up-assume">${note}</p>` : ""}</dd></div>`;
}

function facts(plan) {
  const start = `${pick("created_at", ["time"])}${parts.created_time ? `<span class="up-plus">+</span>${pick("created_time", ["time"])}` : ""}`;
  const miss = missFact(plan);
  const groups = ["team", "category"].filter((p) => parts[p]).map((p) => pick(p, ["category", "number"], true));
  return fact("Starts", start)
    + fact("Ends", endSentence())
    + fact("A miss is", miss.value, miss.note)
    + fact("Grouped by", groups.length ? groups.join(`<span class="up-plus">and</span>`) : `<span class="muted">nothing found (see Change columns)</span>`)
    + fact("Priority", pick("priority", ["category", "number"], true))
    + fact("Learns from", learnFact(plan));
}

function freeColumns(part, kinds) {
  const current = parts[part] || "";
  const taken = new Set(Object.entries(parts).filter(([key, value]) => key !== "features" && key !== part && value).map(([, value]) => value));
  return peeked.columns.filter((c) => c.name === current || (kinds.includes(c.kind) && !taken.has(c.name)));
}

function pick(part, kinds, optional = false) {
  const current = parts[part] || "";
  const columns = freeColumns(part, kinds);
  const none = optional ? `<option value="" ${current ? "" : "selected"}>${part === "priority" ? "none in this file" : "none"}</option>` : "";
  return `<select class="pick" data-part="${part}" aria-label="${escapeHtml(partLabel(part))}">${none}${columns.map((c) =>
    `<option value="${escapeHtml(c.name)}" ${c.name === current ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}</select>`;
}

function partLabel(part) {
  const found = PARTS.find(([p]) => p === part);
  return found ? found[1] : part;
}

function endSentence() {
  const current = parts.duration_min ? `duration_min|${parts.duration_min}` : `resolved_at|${parts.resolved_at || ""}`;
  const option = (part, c) => `<option value="${escapeHtml(`${part}|${c.name}`)}" ${`${part}|${c.name}` === current ? "selected" : ""}>${escapeHtml(c.name)}</option>`;
  const times = freeColumns("resolved_at", ["time"]).filter((c) => c.name !== parts.duration_min).map((c) => option("resolved_at", c));
  const minutes = freeColumns("duration_min", ["number"]).filter((c) => c.name !== parts.resolved_at).map((c) => option("duration_min", c));
  const select = `<select class="pick" data-end aria-label="When each item ended">
      ${times.length ? `<optgroup label="Ends at this time">${times.join("")}</optgroup>` : ""}
      ${minutes.length ? `<optgroup label="Took this many minutes">${minutes.join("")}</optgroup>` : ""}</select>`;
  return parts.duration_min ? `${select}<span class="up-plus">minutes after it starts</span>` : `at ${select}`;
}

function missFact(plan) {
  const P = "uploadpeek.plan";
  const rule = plan.miss.rule;
  const share = `<span class="up-share">${ev(`${P}.missed_pct`, "pct")} of your ${noun()}</span>`;
  if (MISS_PARTS.includes(rule)) {
    const kinds = rule === "due_at" ? ["time"] : ["category", "number"];
    const options = freeColumns(rule, kinds).filter((c) => rule === "due_at" || c.unique <= 3 || c.name === parts[rule]);
    const select = `<select class="pick" data-miss aria-label="What counts as a miss">${options.map((c) =>
      `<option value="${rule}|${escapeHtml(c.name)}" ${c.name === parts[rule] ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}
      <option value="promise|">none: use a promised time</option></select>`;
    return { value: `${rule === "due_at" ? `finishing after ${select}` : `what ${select} says`}${share}` };
  }
  const input = `<input type="number" class="pick-num" id="up-target" min="1" step="1" value="${escapeHtml(String(target))}" aria-label="Promised minutes">`;
  return { value: `taking longer than ${input} min${share}`,
    note: plan.miss.assumed ? `OpsLens's guess, as your file has no on-time column: half your ${noun()} take under ${ev(`${P}.median_min`, "dur")}.
      Type your own promise if it is different.` : "" };
}

function learnFact(plan) {
  const P = "uploadpeek.plan";
  return plan.learns_from_count
    ? `${ev(`${P}.learns_from_count`, "int")} columns known when an ${noun(true)} starts, plus the time of day and how busy it was
       <button type="button" class="link-btn" data-adjust="learn">see which</button>`
    : `the time of day and how busy it was (no other column is known when an ${noun(true)} starts)`;
}

function previewHtml(open) {
  const lit = {};
  Object.entries(parts).forEach(([part, column]) => { if (PART_WORD[part] && column && !lit[column]) lit[column] = PART_WORD[part]; });
  const names = peeked.columns.map((c) => c.name);
  const head = names.map((n) => `<th class="${lit[n] ? "is-used" : ""}">${lit[n] ? `<span class="up-role">${lit[n]}</span>` : ""}${escapeHtml(n)}</th>`).join("");
  const rows = peeked.preview.map((row) => `<tr>${names.map((n) =>
    `<td class="${lit[n] ? "is-used" : ""}">${escapeHtml(row[n] === undefined ? "" : row[n])}</td>`).join("")}</tr>`).join("");
  const table = `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
  return `<div class="up-preview">${fold(`The first rows of ${file}`, table, { open, hint: "the columns OpsLens uses are shaded" })}</div>`;
}

const MORE_PARTS = ["id", "sla_met", "breached", "due_at"];
const UNSET_PARTS = ["created_time", "team", "category"];

function adjustHtml() {
  const one = noun(true);
  const shown = PARTS.filter(([part]) => MORE_PARTS.includes(part) || (UNSET_PARTS.includes(part) && !parts[part]));
  const selects = shown.map(([part, label, kind]) => {
    const current = parts[part] || "";
    const columns = freeColumns(part, kind === "any" ? ["time", "number", "category", "id", "text"] : [kind]);
    return `<label class="up-more-field"><span>${escapeHtml(label.replace("item", one))}</span><select data-part="${part}">
        <option value="">not in this file</option>${columns.map((c) =>
          `<option value="${escapeHtml(c.name)}" ${c.name === current ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}</select></label>`;
  }).join("");
  const used = usedColumns();
  const ticks = peeked.columns.filter((c) => ["number", "category"].includes(c.kind) && !used.has(c.name)).map((c) => `
      <label class="up-chip" title="${escapeHtml(c.examples.join(", "))}"><input type="checkbox" data-learn="${escapeHtml(c.name)}" ${(parts.features || []).includes(c.name) ? "checked" : ""}>
        <span class="up-chip-name">${escapeHtml(c.name)}</span><span class="up-chip-eg">${escapeHtml(c.examples.slice(0, 2).join(", "))}</span></label>`).join("");
  return `<div class="up-learn" id="up-learn"><div class="up-more-head">Learns from</div>
      <p class="small muted">Only what is known when an ${escapeHtml(one)} starts. Untick anything written after it ended; a column that gives the outcome away is dropped anyway.</p>
      <div class="up-chips">${ticks || `<p class="small muted">No other column of your file can be learned from.</p>`}</div></div>
    <div class="up-more"><div class="up-more-head">Other columns</div>
      <p class="small muted">Only if your file has them. The rows above already cover the rest.</p>
      <div class="up-more-grid">${selects}</div></div>`;
}

async function run() {
  const plan = state.uploadpeek.plan;
  const promise = plan.miss.rule === "promise";
  const body = { token: peeked.token, mapping: cleanParts(), target_min: promise ? target : null, target_assumed: promise && !typed };
  drawWatch([], "", 0);
  try {
    const started = await postJson("/api/anyfile/run", body);
    const done = await follow(started.job);
    if (hooks.done) hooks.done(done.result, { job: started.job, token: peeked.token, name: file });
  } catch (error) {
    drawConfirm(cleanError(error.message));
  }
}

async function follow(job) {
  for (;;) {
    const response = await fetch(`/api/anyfile/job/${encodeURIComponent(job)}`, { cache: "no-store" });
    const s = await response.json().catch(() => ({}));
    if (s.status === "done") return s;
    if (s.status === "error" || !response.ok) throw new Error(s.error || "OpsLens could not analyse this file. Try another file.");
    drawWatch(s.steps || [], s.step, s.elapsed);
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

function drawWatch(seen, current, elapsed) {
  const finishedSteps = seen.filter((s) => s !== current).length;
  const share = Math.min(1, (finishedSteps + (current ? 0.5 : 0)) / ENGINE_STEPS);
  const rows = PHASES.map(([name, steps]) => {
    const now = steps.includes(current);
    const done = !now && steps.every((s) => seen.includes(s));
    const mark = done ? "✓" : now ? `<span class="spinner" aria-hidden="true"></span>` : "";
    return `<li class="up-step ${done ? "is-done" : ""} ${now ? "is-now" : ""}"><span class="up-mark">${mark}</span>${escapeHtml(name)}</li>`;
  }).join("");
  paint(`<section class="card up-card up-watch" role="status" aria-live="polite">${headHtml(false, 3)}
      <ol class="up-steps">${rows}</ol>
      <div class="up-bar" aria-hidden="true"><i style="width: ${(share * 100).toFixed(0)}%"></i></div>
      <div class="small muted up-clock">${Number(elapsed || 0).toFixed(1)} s</div></section>`);
}

const STEPS = ["Choose a file", "Check what OpsLens read", "Analyse"];

function headHtml(withClose = true, at = 3) {
  const steps = STEPS.map((name, i) => `<li class="${i + 1 === at ? "is-now" : i + 1 < at ? "is-done" : ""}"><span>${i + 1}</span>${name}</li>`).join("");
  return `<header class="up-head"><div class="up-head-main"><span class="up-file">${at > 1 && file ? escapeHtml(file) : "Upload a CSV"}</span>
      <ol class="up-stepper" aria-label="Steps">${steps}</ol></div>${withClose ? closeButton() : ""}</header>`;
}

function problemHtml(sentence) {
  return `<div class="up-problem" role="alert">${escapeHtml(sentence)}</div>`;
}

function cleanError(message) {
  const text = String(message).replace(/^HTTP \d+:?\s*/, "");
  return text || "OpsLens could not analyse this file. Try another file.";
}

function refuse(sentence) {
  if (hooks.refused) hooks.refused(file, sentence);
}
