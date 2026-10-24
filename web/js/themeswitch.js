// themeswitch.js — the Neon / Light button in the top bar.
//
// Why: the neon look (web/neon.css) is the default, but a weak projector can wash dark pages out,
// so one click brings back the light design. The choice is remembered in this browser, and the
// page reloads so the charts are drawn again in the matching colours.
//
// Example: on Neon the button reads "Light"; click → light colours, the button reads "Neon".

import { store } from "./data.js";

export function initThemeSwitch() {
  const button = document.getElementById("theme-button");
  if (!button) return;
  const label = document.getElementById("theme-label");
  const neon = () => document.documentElement.dataset.theme === "neon";
  label.textContent = neon() ? "Light" : "Neon";
  button.addEventListener("click", () => {
    store("opslens-theme", neon() ? "light" : "neon");
    location.reload();
  });
}
