// tabs/upload.js — "Your data": OpsLens on any export of work items, with a live report.
//
// Why (25 Oct, the owner: "a judge brings his own CSV and asks what OpsLens would have done"):
// a log records one way of working, so nobody can honestly replay it under another policy. What a
// log CAN answer: learn on the first 70% of items, then show on the last 30% which real misses
// OpsLens would have flagged as they opened, against the file's own priority field and a rule of
// thumb; shadow mode on the busiest later day; problem cards found early and checked later.
// The server does the work (opslens/anyfile.py via server/anyfile_jobs.py); this screen maps the
// columns, follows the steps live and draws the report. Numbers are clickable ("upload.*" paths).
//
// Flow: choose a CSV (or the UCI example) -> POST /api/anyfile/peek returns the columns, their
// kinds and a suggested mapping -> the person fixes the mapping and says what a miss is ->
// POST /api/anyfile/run -> poll GET /api/anyfile/job/<id> every half second until done.
//
// Example (the UCI example, 24,918 incidents, about 2 s): on Thu 5 May 2016, flagging 78 of 388
// incidents as they opened, OpsLens caught 52 of the 111 real misses; the priority field 22.

import { state } from "../data.js";
import { pageHeader, card, stat, backendMissing } from "../ui.js";
import { ev, evText } from "../evidence.js";
import { escapeHtml } from "../format.js";

const POLL_MS = 500;
const STEPS = [
  "Reading the file and the column mapping",
  "Checking the file can be learned from",
  "Building what was known when each item opened",
  "Learning on the first 70% of items",
  "Scoring the last 30%, which it never saw",
  "Shadow mode on the busiest later day",
  "Finding recurring problems, then checking them on later items",
];
const ROLES = [
  { key: "created_at", label: "Start (date or date and time)", need: true },
  { key: "created_time", label: "Start time, if it is a separate column" },
  { key: "resolved_at", label: "End time (resolved, closed, delivered)" },
  { key: "duration_min", label: "or a duration in minutes" },
  { key: "id", label: "ID" },
  { key: "priority", label: "Priority / urgency" },
  { key: "team", label: "Team / queue / city" },
  { key: "category", label: "Category / type" },
];
const PICKERS = { opslens: "OpsLens", priority: "Your priority field", rule: "Rule of thumb" };
let peeked = null;

export function render(section) {
  section.innerHTML = `
    ${pageHeader("Your data", "Run OpsLens on any export of work items: support tickets, incidents, delivery orders. " +
      "It learns on your first 70% and shows what it would have caught on the rest.")}
    ${card({
      id: "upload-panel",
      body: `<div class="dropzone">
          <div><div class="card-title">Your export</div>
            <div class="card-sub" id="up-file-name">A CSV with one row per item: when it started, when it ended (or how long it took), and anything known when it started.</div></div>
          <div class="btn-row">
            <button type="button" class="btn" id="up-uci">Use the UCI example</button>
            <button type="button" class="btn btn-primary" id="up-choose">Choose a CSV file</button>
            <input type="file" id="up-file" accept=".csv,text/csv,text/plain" hidden>
          </div>
        </div>
        <div id="up-mapping"></div>
        <div id="up-result" style="margin-top: 16px"></div>`,
    })}`;
  section.querySelector("#up-choose").addEventListener("click", () => section.querySelector("#up-file").click());
  section.querySelector("#up-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) return;
    section.querySelector("#up-file-name").textContent = file.name;
    const form = new FormData();
    form.append("file", file);
    peek(section, form);
  });
  section.querySelector("#up-uci").addEventListener("click", () => {
    section.querySelector("#up-file-name").textContent = "UCI ServiceNow incident log, one row per incident (CC BY 4.0)";
    const form = new FormData();
    form.append("example", "uci_incidents");
    peek(section, form);
  });
}

async function peek(section, form) {
  const result = section.querySelector("#up-result");
  section.querySelector("#up-mapping").innerHTML = "";
  result.innerHTML = `<div class="wait" role="status"><span class="spinner" aria-hidden="true"></span><span class="wait-text">Reading the columns…</span></div>`;
  try {
    const response = await fetch("/api/anyfile/peek", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `server answered ${response.status}`);
    peeked = data;
    result.innerHTML = "";
    showMapping(section, data);
  } catch (error) {
    result.innerHTML = state.staticServer || /404|405|Failed to fetch/.test(error.message)
      ? backendMissing("POST /api/anyfile/peek", "Start the OpsLens server to read your file.")
      : `<div class="callout warn"><strong>That file could not be read.</strong> ${escapeHtml(error.message)}.</div>`;
  }
}

function columnSelect(role, columns, chosen) {
  const options = [`<option value="">(not in this file)</option>`].concat(columns.map((c) =>
    `<option value="${escapeHtml(c.name)}" ${c.name === chosen ? "selected" : ""}>${escapeHtml(c.name)}</option>`));
  return `<label class="field"><span class="field-label">${escapeHtml(role.label)}${role.need ? " *" : ""}</span>
      <select data-role="${role.key}">${options.join("")}</select></label>`;
}

function showMapping(section, data) {
  const s = data.suggested || {};
  const missRule = s.sla_met ? "sla_met" : s.due_at ? "due_at" : "target";
  const featureBoxes = data.columns.filter((c) => ["number", "category"].includes(c.kind)).map((c) => `
      <label class="up-check"><input type="checkbox" data-feature="${escapeHtml(c.name)}" ${c.feature ? "checked" : ""}>
        <span>${escapeHtml(c.name)}</span><small>${escapeHtml(c.examples.slice(0, 2).join(", "))}</small></label>`).join("");
  section.querySelector("#up-mapping").innerHTML = `
    <div class="section-label" style="margin-top: 22px">${Number(data.rows).toLocaleString("en-IN")} rows, ${data.columns.length} columns. Which column is which?</div>
    <p class="small muted">Guessed from the names; fix any that are wrong. * = needed. An end time or a duration is needed too.</p>
    <div class="form-grid">${ROLES.map((r) => columnSelect(r, data.columns, s[r.key])).join("")}</div>
    <div class="section-label" style="margin-top: 20px">What counts as a miss?</div>
    <div class="up-miss">
      <label><input type="radio" name="up-miss" value="sla_met" ${missRule === "sla_met" ? "checked" : ""}> A column that says it met the SLA:
        ${columnSelect({ key: "sla_met", label: "" }, data.columns, s.sla_met).replace('<label class="field">', '<span class="field">').replace("</label>", "</span>")}</label>
      <label><input type="radio" name="up-miss" value="due_at" ${missRule === "due_at" ? "checked" : ""}> A due time:
        ${columnSelect({ key: "due_at", label: "" }, data.columns, s.due_at).replace('<label class="field">', '<span class="field">').replace("</label>", "</span>")}</label>
      <label><input type="radio" name="up-miss" value="target" ${missRule === "target" ? "checked" : ""}> Taking longer than
        <input type="number" id="up-target" min="1" step="1" value="30" style="width: 90px"> minutes (the promise)</label>
    </div>
    <div class="section-label" style="margin-top: 20px">Known when an item starts</div>
    <p class="small muted">OpsLens learns only from these. Untick anything written after an item ended; a column that gives the outcome away is dropped anyway.</p>
    <div class="up-checks">${featureBoxes}</div>
    <div class="btn-row" style="margin-top: 20px"><button type="button" class="btn btn-primary" id="up-run">Run OpsLens on this file</button></div>`;
  section.querySelector("#up-run").addEventListener("click", () => run(section));
}

function readMapping(section) {
  const mapping = {};
  section.querySelectorAll("#up-mapping select[data-role]").forEach((sel) => { if (sel.value) mapping[sel.dataset.role] = sel.value; });
  const rule = section.querySelector('input[name="up-miss"]:checked').value;
  if (rule !== "sla_met") delete mapping.sla_met;
  if (rule !== "due_at") delete mapping.due_at;
  const used = new Set(Object.values(mapping));
  mapping.features = [...section.querySelectorAll("[data-feature]:checked")].map((b) => b.dataset.feature).filter((f) => !used.has(f));
  const target = rule === "target" ? Number(section.querySelector("#up-target").value) : null;
  return { mapping, target };
}

async function run(section) {
  const result = section.querySelector("#up-result");
  const button = section.querySelector("#up-run");
  const { mapping, target } = readMapping(section);
  button.disabled = true;
  result.innerHTML = progressHtml([], "", 0);
  try {
    const response = await fetch("/api/anyfile/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: peeked.token, mapping, target_min: target }),
    });
    const start = await response.json();
    if (!response.ok) throw new Error(start.error || `server answered ${response.status}`);
    const done = await follow(start.job, result);
    state.upload = done.result;
    result.innerHTML = reportHtml(done.result);
  } catch (error) {
    state.upload = null;
    result.innerHTML = `<div class="callout warn"><strong>OpsLens could not analyse this file.</strong> ${escapeHtml(error.message)}</div>`;
  } finally {
    button.disabled = false;
  }
}

// Poll the job and redraw the step list until it finishes.
async function follow(job, result) {
  for (;;) {
    const response = await fetch(`/api/anyfile/job/${encodeURIComponent(job)}`);
    const s = await response.json();
    if (s.status === "done") return s;
    if (s.status === "error" || !response.ok) throw new Error(s.error || "the job stopped");
    result.innerHTML = progressHtml(s.steps || [], s.step, s.elapsed);
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

function progressHtml(seen, current, elapsed) {
  const rows = STEPS.map((name) => {
    const isNow = name === current;
    const isDone = seen.includes(name) && !isNow;
    const mark = isDone ? "✓" : isNow ? `<span class="spinner" aria-hidden="true"></span>` : "·";
    return `<li class="up-step ${isDone ? "is-done" : ""} ${isNow ? "is-now" : ""}"><span class="up-mark">${mark}</span>${escapeHtml(name)}</li>`;
  }).join("");
  return `<div class="card up-progress" role="status" aria-live="polite"><div class="card-head"><h3 class="card-title">OpsLens is working on your file</h3>
      <span class="muted">${Number(elapsed || 0).toFixed(1)} s</span></div><ol class="up-steps">${rows}</ol></div>`;
}

// ---- The report ----------------------------------------------------------------------------

function reportHtml(r) {
  const w = r.warning;
  const rival = w.vs.rival;
  const head = `<div class="callout good"><strong>Flagging 1 item in 5 as they opened, OpsLens caught
      ${ev("upload.warning.caught_pct.opslens", "pct")} of the real misses on your later items;
      ${escapeHtml(PICKERS[rival].toLowerCase())} caught ${ev(`upload.warning.caught_pct.${rival}`, "pct")}</strong>
      (gap ${ev("upload.warning.vs.gap_pts", "pts", { signed: true })}, 95% interval ${ev("upload.warning.vs.ci[0]", "pts", { bare: true })} to
      ${ev("upload.warning.vs.ci[1]", "pts", { bare: true })} points over days). Learned on ${ev("upload.learn.items", "int")} items
      (${evText("upload.learn.from")} to ${evText("upload.learn.to")}), scored on ${ev("upload.test.items", "int")} it never saw.</div>`;
  const stats = `<div class="grid cols-4 stretch" style="margin-top: 14px">
      ${card({ body: stat("Items", ev("upload.summary.items", "int"), `${evText("upload.summary.from")} to ${evText("upload.summary.to")}`) })}
      ${card({ body: stat("Missed", ev("upload.summary.missed_pct", "pct"), "of all items") })}
      ${card({ body: stat("Median time", ev("upload.summary.median_min", "dur"), `90% within ${ev("upload.summary.p90_min", "dur")}`) })}
      ${card({ body: stat("Analysed in", ev("upload.seconds", "sec"), "on this laptop") })}
    </div>`;
  return `${head}${stats}
    <div class="grid cols-2" style="margin-top: 18px">${shadowHtml(r)}${warningHtml(r)}</div>
    <div style="margin-top: 18px">${cardsHtml(r)}</div>
    <div class="grid cols-2" style="margin-top: 18px">${worstHtml(r, "team", "Worst teams")}${worstHtml(r, "category", "Worst categories")}</div>
    <div style="margin-top: 18px">${honestHtml(r)}</div>`;
}

function shadowHtml(r) {
  const sh = r.shadow;
  const most = Math.max(1, sh.misses);
  const bars = Object.keys(sh.caught).map((k) => `<div class="ft-row ${k === "opslens" ? "is-ours" : ""}">
      <span>${escapeHtml(PICKERS[k])}${k === "rule" && r.rule_column ? ` (by ${escapeHtml(r.rule_column)})` : ""}</span>
      <span class="ft-track"><i style="width: ${(100 * sh.caught[k]) / most}%"></i></span>
      <b>${ev(`upload.shadow.caught.${k}`, "int")}</b></div>`).join("");
  const examples = sh.examples.map((x, i) => `<li><span class="mono">${escapeHtml(x.opened)}</span> ${evText(`upload.shadow.examples[${i}].id`)}
      · ${ev(`upload.shadow.examples[${i}].risk`, "frac_pct")} risk · ${x.missed ? `<strong class="bad">missed</strong>` : "in time"}
      <div class="small muted">${x.reasons.map((reason) => escapeHtml(reason.text)).join(" · ")}</div></li>`).join("");
  return card({
    title: `Shadow mode: ${sh.weekday} ${sh.date}, your busiest later day`,
    sub: `${ev("upload.shadow.items", "int")} items opened, ${ev("upload.shadow.misses", "int")} really missed. Each one flags the same ${ev("upload.shadow.flags", "int")} as they open: how many real misses did it catch?`,
    body: `<div class="ft-bars">${bars}</div><div class="section-label" style="margin-top: 12px">OpsLens's first flags that day</div><ul class="list">${examples}</ul>`,
  });
}

function warningHtml(r) {
  const w = r.warning;
  const rows = Object.keys(w.auc).map((k) => `<tr><td>${escapeHtml(PICKERS[k])}</td><td class="num">${ev(`upload.warning.auc.${k}`, "ratio")}</td>
      <td class="num">${ev(`upload.warning.caught_pct.${k}`, "pct")}</td></tr>`).join("");
  const top = w.at_risk.slice(0, 4).map((x, i) => `<li>${evText(`upload.warning.at_risk[${i}].id`)} · ${ev(`upload.warning.at_risk[${i}].risk`, "frac_pct")}
      · ${x.missed ? `<strong class="bad">missed</strong>` : "in time"}<div class="small muted">${x.reasons.map((reason) =>
        `${escapeHtml(reason.text)} (${Math.round(100 * reason.share)}%)`).join(" · ")}</div></li>`).join("");
  return card({
    title: "Early warning, the moment an item opens",
    sub: `On your later ${ev("upload.warning.items", "int")} items (${ev("upload.warning.misses", "int")} misses). Ranking score: 0.5 is a coin toss, 1 is perfect.`,
    body: `<div class="table-wrap"><table><thead><tr><th>Who flags</th><th class="num">Ranking score</th><th class="num">Misses caught (1 in 5 flagged)</th></tr></thead>
      <tbody>${rows}</tbody></table></div><div class="section-label" style="margin-top: 12px">Riskiest later items, with the model's own reasons</div><ul class="list">${top}</ul>`,
  });
}

function cardsHtml(r) {
  if (!r.cards.length) return card({ title: "Recurring problems", body: `<p class="muted">No group misses clearly more often than the rest.</p>` });
  const items = r.cards.map((c, i) => `<li><div class="issue">
      <span class="issue-title">${escapeHtml(c.column)} = ${evText(`upload.cards[${i}].value`)}</span>
      <span class="pill ${c.still_true ? "good" : ""}">${c.still_true ? "still true later" : "not confirmed later"}</span>
      <span class="issue-text">First 70%: ${ev(`upload.cards[${i}].learn_pct`, "pct")} missed vs ${ev(`upload.cards[${i}].learn_rest_pct`, "pct")} for the rest
        (${ev(`upload.cards[${i}].learn_items`, "int")} items). Later: ${ev(`upload.cards[${i}].test_pct`, "pct")} vs ${ev(`upload.cards[${i}].test_rest_pct`, "pct")},
        gap ${ev(`upload.cards[${i}].gap_ci[0]`, "pts", { bare: true })} to ${ev(`upload.cards[${i}].gap_ci[1]`, "pts", { bare: true })} points (95%).</span>
    </div></li>`).join("");
  return card({ title: "Recurring problems", sub: "Found on your first 70%, then measured again on the last 30%.", body: `<ul class="list">${items}</ul>` });
}

function worstHtml(r, key, title) {
  const rows = r.summary[`by_${key}`] || [];
  if (!rows.length) return "";
  const body = rows.map((x, i) => `<tr><td>${evText(`upload.summary.by_${key}[${i}].name`)}</td>
      <td class="num">${ev(`upload.summary.by_${key}[${i}].items`, "int")}</td><td class="num">${ev(`upload.summary.by_${key}[${i}].missed_pct`, "pct")}</td></tr>`).join("");
  return card({ title, body: `<div class="table-wrap"><table><thead><tr><th>Name</th><th class="num">Items</th><th class="num">Missed</th></tr></thead><tbody>${body}</tbody></table></div>` });
}

function honestHtml(r) {
  const notes = r.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("");
  const dropped = r.dropped_after_the_fact.length
    ? `<li>Dropped because they give the outcome away (written after the fact): ${escapeHtml(r.dropped_after_the_fact.join(", "))}.</li>` : "";
  const cannot = r.cannot.map((n) => `<li>${escapeHtml(n)}</li>`).join("");
  return card({
    title: "How to read this",
    body: `<ul class="list">${notes}${dropped}<li>Learned from: ${escapeHtml(r.features.join(", "))}.</li></ul>
      <div class="section-label" style="margin-top: 12px">What this file cannot tell you</div><ul class="list">${cannot}</ul>`,
  });
}
