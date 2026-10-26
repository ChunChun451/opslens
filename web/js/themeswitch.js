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
