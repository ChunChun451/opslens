import { loadResults, state } from "./js/data.js";
import { initEvidence, ev, evText } from "./js/evidence.js";
import { setChartDefaults } from "./js/charts.js";
import { initTabs, setWorld } from "./js/router.js";
import { initPlan } from "./js/plan.js";
import { realPlanItems } from "./js/tabs/realdesk.js";
import { initStory } from "./js/story.js";
import { initAsk } from "./js/ask.js";
import { initMotion, initSliderFill } from "./js/motion.js";
import { initLiveTicker } from "./js/liveticker.js";
import { initThemeSwitch } from "./js/themeswitch.js";
import { initSeason } from "./js/season.js";
import { initBot } from "./js/bot.js";
import { initSource, restoreUpload } from "./js/source.js";
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

  await restoreUpload();
  showStatus(isFixture);
  ["world-changed", "source-changed"].forEach((type) => document.addEventListener(type, () => showStatus(isFixture)));
  initWorldSwitch();

  setChartDefaults();
  initEvidence();
  initMotion();
  initSliderFill();
  initSource();
  initTabs();
  initPlan(realPlanItems());
  initStory();
  initAsk();
  initLiveTicker();
  initThemeSwitch();
  initSeason();
  initBot();
}

function showStatus(isFixture) {
  const meta = state.results.meta;
  const onFile = state.world === "real" && state.realSource === "upload" && state.upload;
  const where = onFile ? `<span>· your file, scored on items it never learned from</span>`
    : state.world === "real" ? `<span>· real public data, scored on later months</span>`
    : `<span>· simulated floor, held-out days ${ev("meta.test_days[0]", "int")}–${ev("meta.test_days[1]", "int")}</span>`;
  document.getElementById("data-source").innerHTML = `
    <span class="status-dot ${isFixture ? "fixture" : ""}"></span>
    <strong>${isFixture ? "Fixture data" : "Live results"}</strong>
    <span>· ${evText("meta.generated_at", fmtDateTime(meta.generated_at))}</span>${where}`;
}

function initWorldSwitch() {
  const buttons = document.querySelectorAll(".world-switch [data-world]");
  const paint = () => buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.world === state.world)));
  buttons.forEach((b) => b.addEventListener("click", () => { setWorld(b.dataset.world); paint(); }));
  paint();
  document.body.dataset.world = state.world;
  document.addEventListener("world-changed", () => { document.body.dataset.world = state.world; paint(); });
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
