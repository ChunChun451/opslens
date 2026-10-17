// app.js — the start of the dashboard.
//
// What happens when the page opens:
//   1. Load the results JSON (the real server first, else the fixture file).
//   2. If it is fixture data, show the red FIXTURE banner.
//   3. Build the tabs, the click-to-evidence popover and story mode.
// Every other file is in web/js/. Tabs live in web/js/tabs/, one file per tab.

import { loadResults, state } from "./js/data.js";
import { initEvidence, ev, evText } from "./js/evidence.js";
import { setChartDefaults } from "./js/charts.js";
import { initTabs } from "./js/router.js";
import { initStory } from "./js/story.js";
import { initAsk } from "./js/ask.js";
import { initMotion, initSliderFill } from "./js/motion.js";
import { escapeHtml, fmtDateTime } from "./js/format.js";

async function start() {
  let loaded;
  try {
    loaded = await loadResults();
  } catch (error) {
    showLoadError(error);
    return;
  }
  if (!loaded.data || !loaded.data.meta) {
    showLoadError(new Error("The results file has no 'meta' section."));
    return;
  }
  state.results = loaded.data;
  state.source = loaded.source;

  const isFixture = state.results.meta.fixture === true;
  document.getElementById("fixture-banner").hidden = !isFixture;
  document.body.classList.toggle("has-fixture", isFixture);

  // The status line: live or fixture, when the results were made, which days are held out.
  const meta = state.results.meta;
  document.getElementById("data-source").innerHTML = `
    <span class="status-dot ${isFixture ? "fixture" : ""}"></span>
    <strong>${isFixture ? "Fixture data" : "Live results"}</strong>
    <span>· generated ${evText("meta.generated_at", fmtDateTime(meta.generated_at))}</span>
    <span>· held-out days ${ev("meta.test_days[0]", "int")}–${ev("meta.test_days[1]", "int")}</span>
    <span title="${escapeHtml(state.source)}">· from <code>${escapeHtml(state.source)}</code></span>`;

  setChartDefaults();
  initEvidence(); // before story mode, so Esc closes the popover first
  initMotion(); // before the first tab is shown, so its numbers count up too
  initSliderFill();
  initTabs();
  initStory();
  initAsk();
}

function showLoadError(error) {
  document.getElementById("load-message").innerHTML = `
    <h2 class="card-title">Could not load the results</h2>
    <p>${escapeHtml(error.message)}</p>
    <p>Serve the repository root and open the dashboard from there:</p>
    <pre>.venv/Scripts/python.exe -m http.server 8765</pre>
    <p>then open <code>http://localhost:8765/web/</code>.
       Opening <code>index.html</code> as a file does not work, because browsers block
       loading JSON from <code>file://</code>.</p>`;
}

start();
