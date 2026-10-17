// tabs/upload.js — run OpsLens on any helpdesk export: pick a CSV, map its columns.
//
// Why: judges ask "does this only work on your own data?". The answer is the upload path:
// any company's ticket export, with a column mapping, goes through the same engine. The UCI
// ServiceNow incident log is the ready example. The browser only reads the header line to
// fill the mapping form; the file itself goes to the server (POST /api/upload, M10).
//
// Example: a UCI header "number,incident_state,...,opened_at,...,resolved_at" maps to
// ticket_id = number, created_at = opened_at, resolved_at = resolved_at, team = assignment_group.

import { state } from "../data.js";
import { pageHeader, card, stat, backendMissing, postForm, showWaiting } from "../ui.js";
import { ev, evText } from "../evidence.js";
import { CAUSE_LABELS } from "./patterns.js";
import { escapeHtml } from "../format.js";

// The fields OpsLens needs, and column names that usually mean the same thing.
const FIELDS = [
  { key: "ticket_id", label: "Ticket ID", required: true, guesses: ["ticket_id", "id", "number", "case_id", "incident_id"] },
  { key: "created_at", label: "Created at", required: true, guesses: ["created_at", "opened_at", "created", "open_time", "sys_created_at"] },
  { key: "resolved_at", label: "Resolved at", required: true, guesses: ["resolved_at", "closed_at", "resolved", "close_time"] },
  { key: "priority", label: "Priority", required: true, guesses: ["priority", "severity", "urgency"] },
  { key: "category", label: "Category", required: false, guesses: ["category", "type", "issue_type", "subcategory"] },
  { key: "team", label: "Team / queue", required: false, guesses: ["team", "assignment_group", "queue", "group"] },
  { key: "sla_met", label: "SLA met flag", required: false, guesses: ["made_sla", "sla_met", "within_sla"] },
  { key: "reassignments", label: "Reassignment count", required: false, guesses: ["reassignment_count", "transfers", "reassignments"] },
  { key: "text", label: "Ticket text", required: false, guesses: ["text", "description", "short_description", "subject"] },
];

// Column names of the UCI "Incident management process enriched event log" (CC BY 4.0).
const UCI_COLUMNS = [
  "number", "incident_state", "active", "reassignment_count", "reopen_count", "sys_mod_count",
  "made_sla", "caller_id", "opened_by", "opened_at", "sys_created_by", "sys_created_at",
  "sys_updated_by", "sys_updated_at", "contact_type", "location", "category", "subcategory",
  "u_symptom", "cmdb_ci", "impact", "urgency", "priority", "assignment_group", "assigned_to",
  "knowledge", "u_priority_confirmation", "notify", "problem_id", "rfc", "vendor", "caused_by",
  "closed_code", "resolved_by", "resolved_at", "closed_at",
];

let chosenFile = null;
const UPLOAD_TIMEOUT_MS = 180000; // the UCI example takes about 10 s; big files longer

export function render(section) {
  section.innerHTML = `
    ${pageHeader("Upload data", "Run OpsLens on any helpdesk export: pick a CSV, tell us which column is which, and run.")}
    ${card({
      id: "upload-panel",
      body: `<div class="dropzone">
          <div>
            <div class="card-title">Your helpdesk export</div>
            <div class="card-sub" id="up-file-name">A CSV with one row per ticket (or per ticket event)</div>
          </div>
          <div class="btn-row">
            <button type="button" class="btn" id="up-uci">Use the UCI example</button>
            <button type="button" class="btn btn-primary" id="up-choose">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V4.5M7.5 9L12 4.5 16.5 9"/><path d="M4.5 15v3.5a1.5 1.5 0 001.5 1.5h12a1.5 1.5 0 001.5-1.5V15"/></svg>Choose a CSV file</button>
            <input type="file" id="up-file" accept=".csv,text/csv" hidden>
          </div>
        </div>
        <div id="up-mapping"></div>
        <div id="up-result" style="margin-top: 16px"></div>`,
    })}
    <p class="card-foot">The UCI ServiceNow incident log (CC BY 4.0) has a real SLA flag (<code>made_sla</code>),
      priority, assignment group and reassignment count, so it shows the engine on data we did not generate.</p>`;

  // A real button (keyboard-friendly) that opens the hidden file picker.
  section.querySelector("#up-choose").addEventListener("click", () => section.querySelector("#up-file").click());
  section.querySelector("#up-file").addEventListener("change", async (event) => {
    chosenFile = event.target.files[0] || null;
    if (!chosenFile) return;
    section.querySelector("#up-file-name").textContent = chosenFile.name;
    const head = await chosenFile.slice(0, 65536).text(); // the header is in the first bytes
    showMapping(section, parseHeader(head.split(/\r?\n/)[0]));
  });
  section.querySelector("#up-uci").addEventListener("click", () => {
    chosenFile = null;
    section.querySelector("#up-file-name").textContent = "UCI incident event log (preloaded on the server)";
    showMapping(section, UCI_COLUMNS);
  });
}

// Split one CSV line into column names. Handles "quoted, names" — enough for a header.
function parseHeader(line) {
  const columns = [];
  let current = "";
  let quoted = false;
  for (const ch of line.replace(/^﻿/, "")) {
    if (ch === '"') {
      quoted = !quoted;
    } else if (ch === "," && !quoted) {
      columns.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  columns.push(current.trim());
  return columns.filter((c) => c !== "");
}

// First column whose lower-case name is in the field's guess list.
function guessColumn(field, columns) {
  const lower = columns.map((c) => c.toLowerCase());
  for (const guess of field.guesses) {
    const i = lower.indexOf(guess);
    if (i >= 0) return columns[i];
  }
  return "";
}

function showMapping(section, columns) {
  const selects = FIELDS.map((field) => {
    const guess = guessColumn(field, columns);
    const options = [`<option value="">${field.required ? "— choose —" : "— not in file —"}</option>`]
      .concat(columns.map((c) => `<option value="${escapeHtml(c)}" ${c === guess ? "selected" : ""}>${escapeHtml(c)}</option>`));
    return `<label class="field"><span class="field-label">${escapeHtml(field.label)}${field.required ? " *" : ""}</span>
        <select data-field="${field.key}">${options.join("")}</select></label>`;
  }).join("");
  section.querySelector("#up-mapping").innerHTML = `
    <div class="section-label" style="margin-top: 24px">Column mapping</div>
    <p class="small muted" style="margin-bottom: 14px">We guessed from the column names; fix any that are wrong. * = required.</p>
    <div class="form-grid">${selects}</div>
    <div class="btn-row" style="margin-top: 20px">
      <button type="button" class="btn btn-primary" id="up-run">Run OpsLens on this data</button>
    </div>`;
  section.querySelector("#up-result").innerHTML = "";
  section.querySelector("#up-run").addEventListener("click", () => run(section));
}

// The live answer from POST /api/upload: the same analysis as the main engine, run on the
// uploaded file only. Not part of results.json; kept in state.upload so its numbers are
// clickable ("upload.*" paths).
// Example (UCI example): 24,918 incidents, 2016-02-29 to 2017-02-16, breach 36.6%,
// worst teams and categories, and 4 evidence cards.
function uploadAnswerHtml(a) {
  const range = Array.isArray(a.date_range)
    ? `${evText("upload.date_range[0]")} to ${evText("upload.date_range[1]")}` : "";
  const stats = `<div class="grid cols-4 stretch" style="margin-top: 4px">
      ${card({ body: stat("Tickets", ev("upload.rows", "int"), range) })}
      ${card({ body: stat("SLA breach rate", ev("upload.breach_pct", "pct"), "share that missed its SLA") })}
      ${card({ body: stat("Mean resolution", ev("upload.mean_resolution_min", "dur"), "created to resolved") })}
      ${card({ body: stat("P90 resolution", ev("upload.p90_resolution_min", "dur"), `analysed in ${ev("upload.seconds", "sec")}`) })}
    </div>`;
  const table = (title, key) => {
    const rows = a[key] || [];
    if (!rows.length) return "";
    const body = rows.map((r, i) => `<tr><td>${evText(`upload.${key}[${i}].name`)}</td>
        <td class="num">${ev(`upload.${key}[${i}].tickets`, "int")}</td>
        <td class="num">${ev(`upload.${key}[${i}].breach_pct`, "pct")}</td>
        <td class="num">${ev(`upload.${key}[${i}].mean_resolution_min`, "dur")}</td></tr>`).join("");
    return card({
      title,
      body: `<div class="table-wrap"><table><thead><tr><th>Name</th><th class="num">Tickets</th>
        <th class="num">Breach</th><th class="num">Mean resolution</th></tr></thead><tbody>${body}</tbody></table></div>`,
    });
  };
  const cards = (a.cards || []).map((c, i) => `<li>
      <div class="issue">
        <span class="issue-title">${evText(`upload.cards[${i}].title`)}</span>
        <span class="pill">${escapeHtml(CAUSE_LABELS[c.cause_type] || c.cause_type)}</span>
        <span class="issue-text">${evText(`upload.cards[${i}].comparison_text`)} · ${ev(`upload.cards[${i}].affected_tickets`, "int")} tickets</span>
      </div></li>`).join("");
  return `<div class="callout good"><strong>${evText("upload.source")}</strong>: analysed with the same pattern scans as the main engine.</div>
    ${stats}
    <div class="grid cols-2" style="margin-top: 20px">${table("Worst teams by breach rate", "by_team")}${table("Worst categories by breach rate", "by_category")}</div>
    <div style="margin-top: 20px">${card({
      title: "Findings in your data",
      body: cards ? `<ul class="list">${cards}</ul>` : `<p class="muted">No finding passed the thresholds.</p>`,
    })}</div>`;
}

async function run(section) {
  const result = section.querySelector("#up-result");
  const button = section.querySelector("#up-run");
  const mapping = {};
  section.querySelectorAll("[data-field]").forEach((select) => {
    mapping[select.dataset.field] = select.value;
  });
  const missingFields = FIELDS.filter((f) => f.required && !mapping[f.key]).map((f) => f.label);
  if (missingFields.length) {
    result.innerHTML = `<div class="callout warn">Please choose a column for: ${escapeHtml(missingFields.join(", "))}.</div>`;
    return;
  }
  const form = new FormData();
  form.append("mapping", JSON.stringify(mapping));
  if (chosenFile) {
    form.append("file", chosenFile);
  } else {
    form.append("example", "uci_incidents");
  }
  button.disabled = true;
  showWaiting(result, "Reading the file and running the engine's pattern scans on it…");
  try {
    state.upload = await postForm("/api/upload", form, UPLOAD_TIMEOUT_MS);
    result.innerHTML = uploadAnswerHtml(state.upload);
  } catch (error) {
    state.upload = null;
    result.innerHTML = state.staticServer || /HTTP (404|405|501)/.test(error.message)
      ? backendMissing("POST /api/upload", "Your column mapping is ready; start the server to run the engine on it.")
      : `<div class="callout warn"><strong>The analysis did not finish.</strong> ${escapeHtml(error.message)}.</div>`;
  } finally {
    button.disabled = false;
  }
}
