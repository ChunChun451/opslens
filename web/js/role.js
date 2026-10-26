import { state, store } from "./data.js";
import { setWorld, showTab } from "./router.js";

export function initRole() {
  document.querySelectorAll("#role-switch [data-role]").forEach((button) => {
    button.addEventListener("click", () => setRole(button.dataset.role));
  });
  const wantsAgent = state.role === "agent" || location.hash.startsWith("#agent");
  setRole(wantsAgent ? "agent" : "lead", null, true);
}

export function setRole(role, agentId = null, first = false) {
  if (agentId) {
    state.agent = agentId;
    store("opslens-agent", agentId);
  }
  const changed = role !== state.role;
  state.role = role;
  store("opslens-role", role);
  document.body.dataset.role = role;
  document.querySelectorAll("#role-switch [data-role]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.role === role)));
  if (role === "agent") {
    if (state.world !== "food") setWorld("food");
    showTab("agent");
  } else if (location.hash.startsWith("#agent")) {
    showTab("team");
  }
  if (changed || first || agentId) document.dispatchEvent(new CustomEvent("role-changed", { detail: role }));
}
