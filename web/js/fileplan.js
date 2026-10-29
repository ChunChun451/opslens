import { state } from "./data.js";
import { ev } from "./evidence.js";
import { escapeHtml } from "./format.js";
import { itemWord } from "./tabs/yourfile.js";

const SAVE_WORDS = { 0.25: "1 in 4", 0.5: "1 in 2", 0.75: "3 in 4" };
let asked = "";

function token() {
  return state.uploadMeta ? state.uploadMeta.token : "";
}

function acceptedParts() {
  const prefix = `file-${token()}-`;
  const ids = Object.entries(state.plan).filter(([id, d]) => id.startsWith(prefix) && d.status === "accepted").map(([id]) => id);
  return { warn: ids.includes(`${prefix}warn`), groups: ids.filter((id) => id.startsWith(`${prefix}fix-`)).map((id) => Number(id.slice(prefix.length + 4))).sort((a, b) => a - b) };
}

export function fileSave() {
  return state.fileplan ? state.fileplan.save : (state.upload && state.upload.impact ? state.upload.impact.save : 0.5);
}

function base() {
  return state.fileplan && state.fileplan.job === (state.uploadMeta && state.uploadMeta.job) ? "fileplan" : "upload.impact";
}

export async function refreshFileEffect(save = fileSave()) {
  if (!state.upload || !state.upload.impact || !state.uploadMeta) return;
  const parts = acceptedParts();
  const key = JSON.stringify([state.uploadMeta.job, parts, save]);
  if (key === asked && base() === "fileplan") return;
  asked = key;
  try {
    const response = await fetch("/api/anyfile/effect", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job: state.uploadMeta.job, ...parts, save }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    if (key !== asked) return;
    state.fileplan = data;
    state.fileplanError = "";
  } catch (error) {
    asked = "";
    state.fileplanError = error.message;
  }
  document.dispatchEvent(new CustomEvent("fileplan-changed"));
}

function bar(p) {
  const before = p.before || 1;
  return `<div class="fx-bar" aria-hidden="true"><i style="width:${(100 * p.after / before).toFixed(1)}%"></i><s style="width:${(100 * p.fewer / before).toFixed(1)}%"></s></div>`;
}

function beforeAfter(path, p, cls = "") {
  return `<div class="fx-line ${cls}"><span class="fx-nums">${ev(`${path}.before`, "int")} <span class="fx-arrow">→</span> <b>${ev(`${path}.after`, "int")}</b> missed</span>
      <span class="fx-delta ${p.fewer > 0 ? "is-good" : ""}">${p.fewer > 0 ? `−${ev(`${path}.fewer`, "int")} (${ev(`${path}.fewer_pct`, "pct")} fewer)` : "no change"}</span></div>
    ${bar(p)}`;
}

function saveChooser() {
  const now = fileSave();
  return `<span class="fx-save" role="group" aria-label="How many flagged misses looking first saves">${Object.entries(SAVE_WORDS).map(([v, word]) =>
    `<button type="button" data-fx-save="${v}" aria-pressed="${Number(v) === now}">${word}</button>`).join("")}</span>`;
}

export function fileActionEffect(index, groupWord = "") {
  const b = base();
  const source = b === "fileplan" ? state.fileplan : state.upload.impact;
  const path = index === 0 ? `${b}.warn` : `${b}.cards[${index - 1}]`;
  const p = index === 0 ? source.warn : source.cards[index - 1];
  if (!p) return "";
  const items = `on your last ${ev(`${path}.items`, "int")} ${itemWord()}`;
  const how = index === 0
    ? `<b>Measured:</b> ${ev(`${path}.flagged_misses`, "int")} of those misses get flagged as they open. <b>Assumed:</b> looking at them first saves ${saveChooser()} of them.`
    : `<b>Assumed:</b> the fix brings ${escapeHtml(groupWord)} (${ev(`${path}.fixed_items`, "int")} ${itemWord()}) down to the rest's miss rate, ${ev(`${path}.rest_pct`, "pct")}.`;
  return `<div class="fx"><div class="fx-head">If you do this, ${items}</div>${beforeAfter(path, p)}<p class="fx-how">${how}</p></div>`;
}

export function filePlanTotal(compact = false) {
  if (!state.upload || !state.upload.impact) return "";
  const parts = acceptedParts();
  const count = parts.groups.length + (parts.warn ? 1 : 0);
  const w = state.upload.impact.warn;
  if (!count) {
    return `<div class="fx fx-total is-empty"><div class="fx-head">Your plan</div>
      <p class="fx-how">Now: ${ev("upload.impact.warn.before", "int")} missed on your last ${ev("upload.impact.warn.items", "int")} ${itemWord()} (${ev("upload.impact.warn.before_pct", "pct")}).
        Accept actions to see what they save together.</p></div>`;
  }
  const done = state.fileplan && state.fileplan.accepted;
  const fresh = done && base() === "fileplan" && done.warn === parts.warn && done.groups.join() === parts.groups.join();
  if (!fresh) {
    return `<div class="fx fx-total"><div class="fx-head">Your plan, ${count} accepted</div>
      <p class="fx-how">${state.fileplanError ? escapeHtml(state.fileplanError) : `Adding ${count === 1 ? "it" : "them"} up on your last ${w.items.toLocaleString("en-GB")} ${itemWord()}…`}</p></div>`;
  }
  const p = state.fileplan.plan;
  const split = [p.from_fixes ? `${ev("fileplan.plan.from_fixes", "int")} from fixing groups` : "", p.from_warning ? `${ev("fileplan.plan.from_warning", "int")} from looking first` : ""].filter(Boolean).join(", ");
  return `<div class="fx fx-total"><div class="fx-head">Your plan, ${count} accepted, on your last ${ev("fileplan.plan.items", "int")} ${itemWord()}</div>
    ${beforeAfter("fileplan.plan", p, "is-big")}
    <p class="fx-how">${split ? `Fewer misses: ${split}. ` : ""}${parts.groups.length > 1 ? `An ${itemWord(true)} in more than one accepted group gets the bigger of their cuts, once. ` : ""}${parts.warn && !compact ? `Assumes looking first saves ${SAVE_WORDS[state.fileplan.save]} flagged misses.` : ""}</p></div>`;
}

export function initFilePlan() {
  document.addEventListener("click", (event) => {
    const chosen = event.target.closest("[data-fx-save]");
    if (chosen) refreshFileEffect(Number(chosen.dataset.fxSave));
  });
  document.addEventListener("plan-changed", () => { if (state.upload && state.uploadMeta) refreshFileEffect(); });
}
