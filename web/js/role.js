import { state, store } from "./data.js";
import { setWorld, showTab } from "./router.js";

export function initRole() {
  const role = state.lockedAgent ? "agent" : "lead";
  state.role = role;
  store("opslens-role", role);
  document.body.dataset.role = role;
  if (role === "agent") {
    if (state.world !== "food") setWorld("food");
    showTab("agent");
  }
  document.dispatchEvent(new CustomEvent("role-changed", { detail: role }));
}

export function openAgent(agentId) {
  state.agent = agentId;
  store("opslens-agent", agentId);
  if (state.world !== "food") setWorld("food");
  showTab("agent");
  document.dispatchEvent(new CustomEvent("role-changed", { detail: state.role }));
}
