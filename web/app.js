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
import { initTabs, setWorld } from "./js/router.js";
import { initPlan } from "./js/plan.js";
import { realPlanItems } from "./js/tabs/realdesk.js";
import { initStory } from "./js/story.js";
import { initAsk } from "./js/ask.js";
import { initMotion, initSliderFill } from "./js/motion.js";
import { initIntro } from "./js/intro.js";
import { initLiveTicker } from "./js/liveticker.js";
import { initThemeSwitch } from "./js/themeswitch.js";
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

  showStatus(isFixture);
  document.addEventListener("world-changed", () => showStatus(isFixture));
  initWorldSwitch();

  setChartDefaults();
  initEvidence(); // before story mode, so Esc closes the popover first
  initMotion(); // before the first tab is shown, so its numbers count up too
  initSliderFill();
  initTabs();
  initPlan(realPlanItems());
  initStory();
  initAsk();
  initLiveTicker(); // today's live run in the side menu, on every screen
  initThemeSwitch(); // Neon / Light
  initIntro(); // the cold open plays last, over the ready dashboard
}

// The status line: what this world's numbers are, and how they were tested.
function showStatus(isFixture) {
  const meta = state.results.meta;
  const where = state.world === "real"
    ? `<span>· real public data, scored on later months</span>`
    : `<span>· simulated floor, held-out days ${ev("meta.test_days[0]", "int")}–${ev("meta.test_days[1]", "int")}</span>`;
  document.getElementById("data-source").innerHTML = `
    <span class="status-dot ${isFixture ? "fixture" : ""}"></span>
    <strong>${isFixture ? "Fixture data" : "Live results"}</strong>
    <span>· ${evText("meta.generated_at", fmtDateTime(meta.generated_at))}</span>${where}`;
}

// The two-button switch in the top bar. The cold open and its replay button belong to the food world.
function initWorldSwitch() {
  const buttons = document.querySelectorAll(".world-switch [data-world]");
  const paint = () => buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.world === state.world)));
  buttons.forEach((b) => b.addEventListener("click", () => { setWorld(b.dataset.world); paint(); }));
  paint();
  document.body.dataset.world = state.world;
  document.addEventListener("world-changed", () => { document.body.dataset.world = state.world; });
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
