// router.js — the list of tabs, the side menu, and switching between tabs.
//
// Why: one list (TABS) is the whole table of contents. Adding a tab = write a module with a
// render(section) function and add one line here. Each tab is drawn the first time it is
// shown, because Chart.js needs a visible canvas to measure its size.
// The tab id is kept in the address (#forecast), so a reload stays on the same tab.
//
// Example: showTab("forecast") -> draws the Forecast tab once, then just shows it.

import * as overview from "./tabs/overview.js";
import * as patterns from "./tabs/patterns.js";
import * as forecast from "./tabs/forecast.js";
import * as atrisk from "./tabs/atrisk.js";
import * as recommendations from "./tabs/recommendations.js";
import * as compare from "./tabs/compare.js";
import * as whatif from "./tabs/whatif.js";
import * as tested from "./tabs/tested.js";
import * as upload from "./tabs/upload.js";

// Simple line icons for the side menu (24×24 grid, drawn with strokes in the text colour).
const ICONS = {
  overview: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  patterns: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  forecast: '<path d="M3.5 17l5-5 4 3.5 7.5-8"/><path d="M15 7.5h5v5"/>',
  atrisk: '<path d="M12 3.8L21 19.5H3z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  recommendations: '<path d="M4 7l1.8 1.8L9 5.5M4 14l1.8 1.8L9 12.5"/><path d="M12.5 7.5H20M12.5 14.5H20M4.5 19.5H20"/>',
  compare: '<path d="M5 20V11M12 20V4.5M19 20v-6"/>',
  whatif: '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
  tested: '<path d="M12 3.5l7 2.8v5.2c0 4.3-3 7.7-7 9-4-1.3-7-4.7-7-9V6.3z"/><path d="M9 12l2.2 2.2L15.2 10"/>',
  upload: '<path d="M12 15V4.5M7.5 9L12 4.5 16.5 9"/><path d="M4.5 15v3.5a1.5 1.5 0 001.5 1.5h12a1.5 1.5 0 001.5-1.5V15"/>',
};

export const TABS = [
  { id: "overview", label: "Overview", module: overview },
  { id: "patterns", label: "Patterns", module: patterns },
  { id: "forecast", label: "Forecast", module: forecast },
  { id: "atrisk", label: "At-risk tickets", module: atrisk },
  { id: "recommendations", label: "Recommendations", module: recommendations },
  { id: "compare", label: "Baseline vs OpsLens", module: compare },
  { id: "whatif", label: "What-if", module: whatif },
  { id: "tested", label: "How we tested", module: tested },
  { id: "upload", label: "Upload data", module: upload },
];

const rendered = new Set();

// Build the side menu and one empty <section> per tab, then show the tab from the address.
export function initTabs() {
  const nav = document.getElementById("tab-nav");
  const panels = document.getElementById("tab-panels");
  nav.innerHTML = TABS.map((tab) => `<a href="#${tab.id}" data-tab="${tab.id}">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[tab.id] || ""}</svg>${tab.label}</a>`).join("");
  panels.innerHTML = TABS.map((tab) => `<section id="tab-${tab.id}" class="tab-panel" hidden></section>`).join("");
  window.addEventListener("hashchange", () => showTab(tabFromHash()));
  // Any element with data-goto-tab="patterns" (and optionally data-goto-id="card-F1") opens
  // that tab and scrolls to that element. Used by the Overview's "top issues".
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-goto-tab]");
    if (!link || event.target.closest("[data-path]")) return;
    showTab(link.dataset.gotoTab);
    const target = link.dataset.gotoId && document.getElementById(link.dataset.gotoId);
    if (target) target.scrollIntoView({ block: "start", behavior: "smooth" });
  });
  showTab(tabFromHash());
}

function tabFromHash() {
  return location.hash.replace("#", "") || TABS[0].id;
}

export function showTab(id) {
  const tab = TABS.find((t) => t.id === id) || TABS[0];
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
  if (!rendered.has(tab.id)) {
    rendered.add(tab.id);
    try {
      tab.module.render(section);
    } catch (error) {
      // A bug in one tab must not take down the whole demo.
      section.innerHTML = `<div class="callout warn">This tab failed to draw: ${error.message}</div>`;
      console.error(error);
    }
  }
  if (location.hash !== "#" + tab.id) {
    history.replaceState(null, "", "#" + tab.id); // no hashchange event, no double draw
  }
  document.getElementById("tab-panels").scrollTop = 0;
  document.dispatchEvent(new CustomEvent("tab-shown", { detail: tab.id }));
}
