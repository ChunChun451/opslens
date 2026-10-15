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
  nav.innerHTML = TABS.map((tab) => `<a href="#${tab.id}" data-tab="${tab.id}">${tab.label}</a>`).join("");
  panels.innerHTML = TABS.map((tab) => `<section id="tab-${tab.id}" class="tab-panel" hidden></section>`).join("");
  window.addEventListener("hashchange", () => showTab(tabFromHash()));
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
      section.innerHTML = `<div class="panel error">This tab failed to draw: ${error.message}</div>`;
      console.error(error);
    }
  }
  if (location.hash !== "#" + tab.id) {
    history.replaceState(null, "", "#" + tab.id); // no hashchange event, no double draw
  }
  document.getElementById("tab-panels").scrollTop = 0;
  document.dispatchEvent(new CustomEvent("tab-shown", { detail: tab.id }));
}
