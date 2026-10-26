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

const ICONS = {
  overview: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  problems: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  risks: '<path d="M12 3.8L21 19.5H3z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  actions: '<path d="M4 7l1.8 1.8L9 5.5M4 14l1.8 1.8L9 12.5"/><path d="M12.5 7.5H20M12.5 14.5H20M4.5 19.5H20"/>',
  proof: '<path d="M12 3.5l7 2.8v5.2c0 4.3-3 7.7-7 9-4-1.3-7-4.7-7-9V6.3z"/><path d="M9 12l2.2 2.2L15.2 10"/>',
};

export const TABS = [
  { id: "overview", label: "Overview", views: {
    food: [{ id: "live", label: "Live now", module: live }],
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
    food: [{ id: "results", label: "Results", module: overview },
           { id: "compare", label: "Side by side", module: compare },
           { id: "worlds", label: "Beyond our world", module: worlds },
           { id: "whatif", label: "Try a what-if", module: whatif },
           { id: "ledger", label: "Rules we wrote first", module: ledger },
           { id: "tested", label: "How we tested", module: tested }],
    real: [{ id: "rd-proof", label: "Against the real desk", module: realdesk.proof },
           { id: "ledger", label: "Rules we wrote first", module: ledger }],
    upload: [{ id: "up-proof", label: "Does it work on your file?", module: yourfile.proof }] } },
];

const OTHER_SOURCE_VIEW = { "rd-overview": "up-overview", "rd-shadow": "up-shadow", "rd-problems": "up-problems",
                            "rd-risks": "up-risks", "rd-actions": "up-actions", "rd-proof": "up-proof" };
Object.entries({ ...OTHER_SOURCE_VIEW }).forEach(([uci, file]) => { OTHER_SOURCE_VIEW[file] = uci; });

const ALIAS = { patterns: "problems", atrisk: "risks", forecast: "risks", recommendations: "actions",
                results: "proof", compare: "proof", whatif: "proof", ledger: "proof", tested: "proof", live: "overview",
                worlds: "proof", "rd-shadow": "overview", "up-shadow": "overview", shadow: "overview", next48: "risks" };

const VIEW_ALIAS = { next48: "forecast", "next-48-hours": "forecast", "at-risk": "atrisk", shadow: "rd-shadow",
                     "beyond-our-world": "worlds", rules: "ledger" };

const framed = new Set();
const drawn = new Set();

export function initTabs() {
  const nav = document.getElementById("tab-nav");
  const panels = document.getElementById("tab-panels");
  nav.innerHTML = TABS.map((tab) => `<a href="#${tab.id}" data-tab="${tab.id}">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[tab.id] || ""}</svg>${tab.label}</a>`).join("");
  panels.innerHTML = `<div id="source-bar" class="source-bar" hidden><div class="sb-row" id="sb-row"></div><div id="upload-card"></div></div>`
    + TABS.map((tab) => `<section id="tab-${tab.id}" class="tab-panel" hidden></section>`).join("");
  window.addEventListener("hashchange", () => showTab(...fromHash()));
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-goto-tab]");
    if (!link || event.target.closest("[data-path]")) return;
    showTab(link.dataset.gotoTab);
    const target = link.dataset.gotoId && document.getElementById(link.dataset.gotoId);
    if (target) target.scrollIntoView({ block: "start", behavior: "smooth" });
  });
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

export function setWorld(world) {
  if (world === state.world) return;
  state.world = world;
  store("opslens-world", world);
  clearScreens();
  document.dispatchEvent(new CustomEvent("world-changed", { detail: world }));
  showTab(fromHash()[0]);
}

export function setSource(source, { force = false, screen = "" } = {}) {
  if (source === state.realSource && !force) return;
  const [current, view] = fromHash();
  state.realSource = source;
  storeSession("opslens-real-source", source);
  clearScreens();
  document.dispatchEvent(new CustomEvent("source-changed", { detail: source }));
  if (state.world === "real") showTab(screen || current, screen ? undefined : view);
}

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
  if (viewId && viewId.startsWith("up-") && state.world === "real" && state.upload && state.realSource !== "upload") {
    state.realSource = "upload";
    storeSession("opslens-real-source", "upload");
    clearScreens();
    document.dispatchEvent(new CustomEvent("source-changed", { detail: "upload" }));
  }
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
    } catch (error) {
      container.innerHTML = `<div class="callout warn">This view failed to draw: ${error.message}</div>`;
      console.error(error);
    }
  }
  const hash = "#" + tab.id + (views.length > 1 ? "/" + view.id : "");
  if (location.hash !== hash) {
    history.replaceState(null, "", hash);
  }
  document.getElementById("tab-panels").scrollTop = 0;
  document.body.dataset.screen = tab.id;
  document.dispatchEvent(new CustomEvent("tab-shown", { detail: view.id }));
}
