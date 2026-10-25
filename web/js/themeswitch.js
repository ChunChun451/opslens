// themeswitch.js — the Dark / Light button in the top bar.
//
// Why: the graphite dark look (web/clean.css) is the default, but a weak projector can wash dark
// pages out, so one click brings the light theme. The choice is remembered in this browser, and
// the page reloads so the charts are drawn again in the matching colours.
//
// Example: on Dark the button reads "Light"; click → light colours, the button reads "Dark".

import { store } from "./data.js";

export function initThemeSwitch() {
  const button = document.getElementById("theme-button");
  if (!button) return;
  const label = document.getElementById("theme-label");
  const dark = () => document.documentElement.dataset.theme !== "light";
  label.textContent = dark() ? "Light" : "Dark";
  button.setAttribute("aria-label", dark() ? "Switch to the light theme" : "Switch to the dark theme");
  button.addEventListener("click", () => {
    store("opslens-theme", dark() ? "light" : "dark");
    location.reload();
  });
}
