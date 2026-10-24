// router.js — the six screens, their sub-tabs, the side menu, and the world switch.
//
// Why (Plan v3, 19 Oct): the dashboard follows the questions a manager asks, in the problem
// statement's order — what is happening, why it goes wrong, what will go wrong, what to do, does
// it work — instead of the order we built the engine in. Each screen shows one or more views; the
// existing tab modules are those views, unchanged. The same six screens exist in both worlds:
// "food" (the simulated food-delivery floor) and "real" (the public UCI service desk).
// The address keeps the screen and view (#risks/forecast), so a reload stays put; old names
// (#patterns, #compare, ...) still work, so story mode and links keep working.
//
// Example: showTab("compare") -> opens Proof, view "Side by side".

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
import * as upload from "./tabs/upload.js";
import * as realdesk from "./tabs/realdesk.js";
import { state, store } from "./data.js";

// Simple line icons for the side menu (24×24 grid, drawn with strokes in the text colour).
const ICONS = {
  overview: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  problems: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  risks: '<path d="M12 3.8L21 19.5H3z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  actions: '<path d="M4 7l1.8 1.8L9 5.5M4 14l1.8 1.8L9 12.5"/><path d="M12.5 7.5H20M12.5 14.5H20M4.5 19.5H20"/>',
  proof: '<path d="M12 3.5l7 2.8v5.2c0 4.3-3 7.7-7 9-4-1.3-7-4.7-7-9V6.3z"/><path d="M9 12l2.2 2.2L15.2 10"/>',
  upload: '<path d="M12 15V4.5M7.5 9L12 4.5 16.5 9"/><path d="M4.5 15v3.5a1.5 1.5 0 001.5 1.5h12a1.5 1.5 0 001.5-1.5V15"/>',
};

export const TABS = [
  { id: "overview", label: "Overview", views: {
    food: [{ id: "overview", label: "Overview", module: overview },
           { id: "live", label: "Live now", module: live }],
    real: [{ id: "rd-overview", label: "Overview", module: realdesk.overview }] } },
  { id: "problems", label: "Problems", views: {
    food: [{ id: "patterns", label: "Why it goes wrong", module: patterns }],
    real: [{ id: "rd-problems", label: "Why it goes wrong", module: realdesk.problems }] } },
  { id: "risks", label: "Risks", views: {
    food: [{ id: "atrisk", label: "Tickets at risk", module: atrisk },
           { id: "forecast", label: "Next 48 hours", module: forecast }],
    real: [{ id: "rd-risks", label: "At risk and next week", module: realdesk.risks }] } },
  { id: "actions", label: "Actions", views: {
    food: [{ id: "recommendations", label: "What to do", module: recommendations }],
    real: [{ id: "rd-actions", label: "What to do", module: realdesk.actions }] } },
  { id: "proof", label: "Proof", views: {
    food: [{ id: "compare", label: "Side by side", module: compare },
           { id: "whatif", label: "Try a what-if", module: whatif },
           { id: "ledger", label: "Rules we wrote first", module: ledger },
           { id: "tested", label: "How we tested", module: tested }],
    real: [{ id: "rd-proof", label: "Against the real desk", module: realdesk.proof },
           { id: "ledger", label: "Rules we wrote first", module: ledger }] } },
  { id: "upload", label: "Your data", views: {
    food: [{ id: "upload", label: "Use your own data", module: upload }],
    real: [{ id: "upload", label: "Use your own data", module: upload }] } },
];

// Old tab names (before Plan v3) → the screen that now holds them.
const ALIAS = { patterns: "problems", atrisk: "risks", forecast: "risks", recommendations: "actions",
                compare: "proof", whatif: "proof", ledger: "proof", tested: "proof", live: "overview" };

const framed = new Set(); // screens whose frame (sub-tabs + empty views) is drawn
const drawn = new Set(); // views already drawn (Chart.js needs a visible canvas, so we wait)

// Build the side menu and one empty <section> per screen, then show the screen from the address.
export function initTabs() {
  const nav = document.getElementById("tab-nav");
  const panels = document.getElementById("tab-panels");
  nav.innerHTML = TABS.map((tab) => `<a href="#${tab.id}" data-tab="${tab.id}">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[tab.id] || ""}</svg>${tab.label}</a>`).join("");
  panels.innerHTML = TABS.map((tab) => `<section id="tab-${tab.id}" class="tab-panel" hidden></section>`).join("");
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

function viewsOf(tab) {
  return tab.views[state.world] || tab.views.food;
}

// Switch between the simulated food-delivery floor and the real public service desk: every
// screen is drawn again for the other world, starting on the same screen.
export function setWorld(world) {
  if (world === state.world) return;
  state.world = world;
  store("opslens-world", world);
  framed.clear();
  drawn.clear();
  TABS.forEach((t) => { document.getElementById("tab-" + t.id).innerHTML = ""; });
  document.dispatchEvent(new CustomEvent("world-changed", { detail: world }));
  showTab(fromHash()[0]);
}

export function showTab(id, viewId) {
  let screenId = id;
  if (ALIAS[id]) {
    screenId = ALIAS[id];
    viewId = viewId || id;
  }
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
  // Story mode and motion listen for view ids (e.g. "compare", the old tab names), so send that.
  document.dispatchEvent(new CustomEvent("tab-shown", { detail: view.id }));
}
