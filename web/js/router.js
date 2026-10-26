// router.js — the five screens, their sub-tabs, the side menu, the world switch and the real source.
//
// Why (Plan v3, 19 Oct): the dashboard follows the questions a manager asks, in the problem
// statement's order — what is happening, why it goes wrong, what will go wrong, what to do, does
// it work — instead of the order we built the engine in. Each screen shows one or more views; the
// existing tab modules are those views, unchanged. The same screens exist in both worlds: "food"
// (the simulated food-delivery floor) and "real" (real data). Real data has two sources (26 Oct):
// the UCI ServiceNow example (the "real" views) and the judge's own uploaded CSV (the "upload"
// views, web/js/tabs/yourfile.js); the bar at the top of every real screen switches between them
// (web/js/source.js). The old "Your data" screen is gone from the side menu: #upload now opens
// Real data with the upload card open.
// The address keeps the screen and view (#risks/forecast), so a reload stays put; old names
// (#patterns, #compare, ...) still work, so story mode and links keep working.
//
// Example: showTab("compare") -> opens Proof, view "Side by side"; with your file shown,
// #overview/rd-shadow opens your file's Shadow mode (up-shadow).

import * as overview from "./tabs/overview.js";
import * as patterns from "./tabs/patterns.js";
import * as forecast from "./tabs/forecast.js";
import * as atrisk from "./tabs/atrisk.js";
import * as recommendations from "./tabs/recommendations.js";
import * as compare from "./tabs/compare.js";
import * as whatif from "./tabs/whatif.js";
import * as tested from "./tabs/tested.js";
import * as ledger from "./tabs/ledger.js";
import * as live from "./tabs/live.js";
import * as realdesk from "./tabs/realdesk.js";
import * as yourfile from "./tabs/yourfile.js";
import * as worlds from "./tabs/worlds.js";
import * as shadow from "./tabs/shadow.js";
import { state, store, storeSession } from "./data.js";

// Simple line icons for the side menu (24×24 grid, drawn with strokes in the text colour).
const ICONS = {
  overview: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  problems: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  risks: '<path d="M12 3.8L21 19.5H3z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  actions: '<path d="M4 7l1.8 1.8L9 5.5M4 14l1.8 1.8L9 12.5"/><path d="M12.5 7.5H20M12.5 14.5H20M4.5 19.5H20"/>',
  proof: '<path d="M12 3.5l7 2.8v5.2c0 4.3-3 7.7-7 9-4-1.3-7-4.7-7-9V6.3z"/><path d="M9 12l2.2 2.2L15.2 10"/>',
};

export const TABS = [
  { id: "overview", label: "Overview", views: {
    food: [{ id: "live", label: "Live now", module: live },
           { id: "overview", label: "Results on the test days", module: overview }],
    real: [{ id: "rd-overview", label: "Overview", module: realdesk.overview },
           { id: "rd-shadow", label: "Shadow mode", module: shadow }],
    upload: [{ id: "up-overview", label: "Overview", module: yourfile.overview },
             { id: "up-shadow", label: "Shadow mode", module: shadow }] } },
  { id: "problems", label: "Problems", views: {
    food: [{ id: "patterns", label: "Why it goes wrong", module: patterns }],
    real: [{ id: "rd-problems", label: "Why it goes wrong", module: realdesk.problems }],
    upload: [{ id: "up-problems", label: "Why it goes wrong", module: yourfile.problems }] } },
  { id: "risks", label: "Risks", views: {
    food: [{ id: "atrisk", label: "Tickets at risk", module: atrisk },
           { id: "forecast", label: "Next 48 hours", module: forecast }],
    real: [{ id: "rd-risks", label: "At risk and next week", module: realdesk.risks }],
    upload: [{ id: "up-risks", label: "At risk and next week", module: yourfile.risks }] } },
  { id: "actions", label: "Actions", views: {
    food: [{ id: "recommendations", label: "What to do", module: recommendations }],
    real: [{ id: "rd-actions", label: "What to do", module: realdesk.actions }],
    upload: [{ id: "up-actions", label: "What to do", module: yourfile.actions }] } },
  { id: "proof", label: "Proof", views: {
    food: [{ id: "compare", label: "Side by side", module: compare },
           { id: "worlds", label: "Beyond our world", module: worlds },
           { id: "whatif", label: "Try a what-if", module: whatif },
           { id: "ledger", label: "Rules we wrote first", module: ledger },
           { id: "tested", label: "How we tested", module: tested }],
    real: [{ id: "rd-proof", label: "Against the real desk", module: realdesk.proof },
           { id: "ledger", label: "Rules we wrote first", module: ledger }],
    upload: [{ id: "up-proof", label: "Does it work on your file?", module: yourfile.proof }] } },
];

// The same view in the other real source: a link to the UCI Shadow mode opens your file's, and back.
const OTHER_SOURCE_VIEW = { "rd-overview": "up-overview", "rd-shadow": "up-shadow", "rd-problems": "up-problems",
                            "rd-risks": "up-risks", "rd-actions": "up-actions", "rd-proof": "up-proof" };
Object.entries({ ...OTHER_SOURCE_VIEW }).forEach(([uci, file]) => { OTHER_SOURCE_VIEW[file] = uci; });

// Old tab names (before Plan v3) → the screen that now holds them.
const ALIAS = { patterns: "problems", atrisk: "risks", forecast: "risks", recommendations: "actions",
                compare: "proof", whatif: "proof", ledger: "proof", tested: "proof", live: "overview",
                worlds: "proof", "rd-shadow": "overview", "up-shadow": "overview", shadow: "overview", next48: "risks" };

// Friendly names for views in links (review #13, item 12): #risks/next48 opens Next 48 hours.
const VIEW_ALIAS = { next48: "forecast", "next-48-hours": "forecast", "at-risk": "atrisk", shadow: "rd-shadow",
                     "beyond-our-world": "worlds", rules: "ledger" };

const framed = new Set(); // screens whose frame (sub-tabs + empty views) is drawn
const drawn = new Set(); // views already drawn (Chart.js needs a visible canvas, so we wait)

// Build the side menu and one empty <section> per screen, then show the screen from the address.
export function initTabs() {
  const nav = document.getElementById("tab-nav");
  const panels = document.getElementById("tab-panels");
  nav.innerHTML = TABS.map((tab) => `<a href="#${tab.id}" data-tab="${tab.id}">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[tab.id] || ""}</svg>${tab.label}</a>`).join("");
  // The Real data source bar sits above every screen and shows only in the real world (source.js).
  panels.innerHTML = `<div id="source-bar" class="source-bar" hidden><div class="sb-row" id="sb-row"></div><div id="upload-card"></div></div>`
    + TABS.map((tab) => `<section id="tab-${tab.id}" class="tab-panel" hidden></section>`).join("");
  window.addEventListener("hashchange", () => showTab(...fromHash()));
  // Any element with data-goto-tab="patterns" (and optionally data-goto-id="card-F1") opens
  // that screen and scrolls to that element. Used by the Overview's "top issues".
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-goto-tab]");
    if (!link || event.target.closest("[data-path]")) return;
    showTab(link.dataset.gotoTab);
    const target = link.dataset.gotoId && document.getElementById(link.dataset.gotoId);
    if (target) target.scrollIntoView({ block: "start", behavior: "smooth" });
  });
  // Sub-tab buttons: <button data-screen="risks" data-view="forecast">.
  document.addEventListener("click", (event) => {
    const sub = event.target.closest("[data-view]");
    if (sub) showTab(sub.dataset.screen, sub.dataset.view);
  });
  showTab(...fromHash());
}

function fromHash() {
  const [screen, view] = location.hash.replace("#", "").split("/");
  return [screen || TABS[0].id, view];
}

// True when the real screens show the uploaded file (and its report is here).
function onFile() {
  return state.world === "real" && state.realSource === "upload" && Boolean(state.upload);
}

function viewsOf(tab) {
  if (onFile() && tab.views.upload) return tab.views.upload;
  return tab.views[state.world] || tab.views.food;
}

function clearScreens() {
  framed.clear();
  drawn.clear();
  TABS.forEach((t) => { document.getElementById("tab-" + t.id).innerHTML = ""; });
}

// Switch between the simulated food-delivery floor and real data: every screen is drawn again
// for the other world, starting on the same screen.
export function setWorld(world) {
  if (world === state.world) return;
  state.world = world;
  store("opslens-world", world);
  clearScreens();
  document.dispatchEvent(new CustomEvent("world-changed", { detail: world }));
  showTab(fromHash()[0]);
}

// Real data: switch every real screen between the UCI example ("uci") and the uploaded file
// ("upload"), staying on the same screen and the matching view (Shadow mode stays Shadow mode).
// `force` redraws even when the source is the same (a new file replaced the old one); `screen`
// opens that screen instead (a finished upload lands on Overview).
export function setSource(source, { force = false, screen = "" } = {}) {
  if (source === state.realSource && !force) return;
  const [current, view] = fromHash();
  state.realSource = source;
  storeSession("opslens-real-source", source);
  clearScreens();
  document.dispatchEvent(new CustomEvent("source-changed", { detail: source }));
  if (state.world === "real") showTab(screen || current, screen ? undefined : view);
}

// The old "Your data" address (#upload, the assistant, old links): Real data, upload card open.
function openUpload() {
  history.replaceState(null, "", "#overview");
  if (state.world !== "real") setWorld("real");
  else showTab("overview");
  document.dispatchEvent(new CustomEvent("upload-open"));
}

export function showTab(id, viewId) {
  if (id === "upload") {
    openUpload();
    return;
  }
  let screenId = id;
  if (ALIAS[id]) {
    screenId = ALIAS[id];
    viewId = viewId || id;
  }
  viewId = VIEW_ALIAS[viewId] || viewId;
  // An up-* address names the file on purpose: when a report is here, show the file, not UCI.
  // (rd-* stays generic: old links and the assistant use it for "the real screen", whichever source.)
  if (viewId && viewId.startsWith("up-") && state.world === "real" && state.upload && state.realSource !== "upload") {
    state.realSource = "upload";
    storeSession("opslens-real-source", "upload");
    clearScreens();
    document.dispatchEvent(new CustomEvent("source-changed", { detail: "upload" }));
  }
  // A real view of the other source (an old link, the assistant, a reload): its twin in this one.
  const twin = OTHER_SOURCE_VIEW[viewId];
  if (twin && (onFile() ? !viewId.startsWith("up-") : viewId.startsWith("up-"))) viewId = twin;
  const tab = TABS.find((t) => t.id === screenId) || TABS[0];
  TABS.forEach((t) => {
    document.getElementById("tab-" + t.id).hidden = t.id !== tab.id;
    const link = document.querySelector(`#tab-nav [data-tab="${t.id}"]`);
    if (t.id === tab.id) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  const section = document.getElementById("tab-" + tab.id);
  const views = viewsOf(tab);
  if (!framed.has(tab.id)) {
    framed.add(tab.id);
    const subnav = views.length > 1
      ? `<nav class="subnav" aria-label="${tab.label} views">${views.map((v) =>
          `<button type="button" data-screen="${tab.id}" data-view="${v.id}">${v.label}</button>`).join("")}</nav>`
      : "";
    section.innerHTML = subnav + views.map((v) => `<div id="view-${v.id}" class="view" hidden></div>`).join("");
  }
  const view = views.find((v) => v.id === viewId) || views[0];
  views.forEach((v) => {
    document.getElementById("view-" + v.id).hidden = v.id !== view.id;
    const button = section.querySelector(`.subnav [data-view="${v.id}"]`);
    if (button) button.setAttribute("aria-current", v.id === view.id ? "true" : "false");
  });
  const container = document.getElementById("view-" + view.id);
  if (!drawn.has(view.id)) {
    drawn.add(view.id);
    try {
      view.module.render(container);
      // (25 Oct, owner: "calm it down": no cartoon strip on the screens; Live now keeps its own scene.)
    } catch (error) {
      // A bug in one view must not take down the whole demo.
      container.innerHTML = `<div class="callout warn">This view failed to draw: ${error.message}</div>`;
      console.error(error);
    }
  }
  const hash = "#" + tab.id + (views.length > 1 ? "/" + view.id : "");
  if (location.hash !== hash) {
    history.replaceState(null, "", hash); // no hashchange event, no double draw
  }
  document.getElementById("tab-panels").scrollTop = 0;
  // The screen id on <body>, for screen-specific styling (25 Oct, owner: no top-bar Ask box on
  // Overview, the side-menu bot answers questions there).
  document.body.dataset.screen = tab.id;
  // Story mode and motion listen for view ids (e.g. "compare", the old tab names), so send that.
  document.dispatchEvent(new CustomEvent("tab-shown", { detail: view.id }));
}
