import { state, readSession, storeSession } from "./data.js";
import { setSource, setWorld } from "./router.js";
import { openUpload, closeUpload } from "./tabs/upload.js";
import { filePlanItems } from "./tabs/yourfile.js";
import { registerItem } from "./plan.js";
import { escapeHtml } from "./format.js";

const KEY = "opslens-upload";
let note = "";
let cardOpen = false;

export async function restoreUpload() {
  const saved = readSession(KEY, null);
  if (!saved || !saved.job || state.staticServer) {
    state.realSource = "uci";
    return;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(`/api/anyfile/job/${encodeURIComponent(saved.job)}`, { cache: "no-store", signal: controller.signal });
    const s = await response.json();
    if (!response.ok || s.status !== "done") throw new Error(s.error || "not finished");
    useReport(s.result, saved);
  } catch (error) {
    storeSession(KEY, null);
    state.realSource = "uci";
    note = `${saved.name || "Your file"}: its report is gone (the server restarted). Upload it again.`;
  } finally {
    clearTimeout(timer);
  }
}

function useReport(result, meta) {
  state.upload = result;
  state.uploadMeta = meta;
  storeSession(KEY, meta);
  filePlanItems().forEach(registerItem);
}

export function initSource() {
  document.addEventListener("click", onClick);
  ["world-changed", "source-changed", "tab-shown"].forEach((type) => document.addEventListener(type, drawBar));
  document.addEventListener("upload-open", openCard);
}

function onClick(event) {
  const chosen = event.target.closest("#source-bar .sb-row [data-source]");
  if (chosen) {
    if (chosen.dataset.source === "upload" && !state.upload) return;
    setSource(chosen.dataset.source);
    drawBar();
    return;
  }
  if (event.target.closest("#source-bar [data-upload-toggle]")) {
    if (cardOpen) closeCard();
    else openCard();
  }
}

function drawBar() {
  const bar = document.getElementById("source-bar");
  if (!bar) return;
  bar.hidden = state.world !== "real";
  if (bar.hidden) return;
  const name = state.uploadMeta && state.upload ? state.uploadMeta.name : "";
  const onFile = state.realSource === "upload" && Boolean(name);
  const chip = name ? `<span class="sb-file ${onFile ? "is-on" : ""}"><button type="button" data-source="upload" aria-pressed="${onFile}">
      Your file: <b>${escapeHtml(name)}</b></button>${onFile ? `<button type="button" class="sb-x" data-source="uci"
      aria-label="Back to the UCI example" title="Back to the UCI example">×</button>` : ""}</span>` : "";
  document.getElementById("sb-row").innerHTML = `
    <div class="sb-switch" role="group" aria-label="Which real data">
      <button type="button" data-source="uci" aria-pressed="${!onFile}">UCI ServiceNow example</button>${chip}
    </div>
    <button type="button" class="btn btn-sm ${name ? "" : "btn-primary"}" data-upload-toggle aria-expanded="${cardOpen}">Upload a CSV</button>
    ${note && !cardOpen ? `<span class="sb-note" role="status">${escapeHtml(note)}</span>` : ""}`;
}

function openCard() {
  if (state.world !== "real") setWorld("real");
  cardOpen = true;
  openUpload(document.getElementById("upload-card"), { done: onReport, refused: onRefused, closed: closeCard });
  drawBar();
  const panels = document.getElementById("tab-panels");
  if (panels) panels.scrollTop = 0;
}

function closeCard() {
  note = "";
  cardOpen = false;
  closeUpload();
  drawBar();
}

function onReport(result, meta) {
  note = "";
  useReport(result, meta);
  cardOpen = false;
  closeUpload();
  setSource("upload", { force: true, screen: "overview" });
  drawBar();
}

function onRefused(name, sentence) {
  note = sentence ? `${name}: ${sentence}` : "";
  drawBar();
}
