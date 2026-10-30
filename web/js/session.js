import { state, store } from "./data.js";
import { escapeHtml } from "./format.js";

export async function whoIsIn() {
  try {
    const r = await fetch("/api/v2/me", { credentials: "same-origin" });
    if (r.status === 401) {
      location.href = "/";
      return { leaving: true };
    }
    return { user: r.ok ? (await r.json()).user : null };
  } catch (error) {
    return { user: null };
  }
}

export function applySession(user) {
  state.user = user;
  if (!user) return;
  document.body.dataset.signed = user.role;
  if (user.role === "agent") {
    state.lockedAgent = user.agent_code;
    state.agent = user.agent_code;
    state.role = "agent";
    store("opslens-agent", user.agent_code);
    store("opslens-role", "agent");
    if (!location.hash.startsWith("#agent")) history.replaceState(null, "", "#agent");
  } else if (!location.hash.startsWith("#agent")) {
    state.role = "lead";
    store("opslens-role", "lead");
  }
  const roleButton = document.querySelector('#role-switch [data-role="lead"]');
  if (roleButton) roleButton.textContent = "Admin";
  const agentButton = document.querySelector('#role-switch [data-role="agent"]');
  if (agentButton) agentButton.textContent = "Agent view";
  const actions = document.querySelector(".topbar-actions");
  const chip = document.createElement("div");
  chip.className = "user-chip";
  const initials = String(user.name || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  chip.innerHTML = `<span class="user-avatar">${escapeHtml(initials)}</span>
    <span class="user-name"><b>${escapeHtml(user.name)}</b><span>${user.role === "admin" ? "Admin" : `Agent · ${escapeHtml(user.agent_code)}`}</span></span>
    ${user.role === "agent" ? `<button type="button" class="btn btn-sm" id="switch-agent">Switch agent</button>` : ""}
    <button type="button" class="btn btn-sm" id="sign-out">Sign out</button>`;
  actions.append(chip);
  const out = async (to) => {
    await fetch("/api/v2/logout", { method: "POST", credentials: "same-origin" }).catch(() => {});
    location.href = to;
  };
  chip.querySelector("#sign-out").addEventListener("click", () => out("/"));
  const sw = chip.querySelector("#switch-agent");
  if (sw) sw.addEventListener("click", () => out("/?as=agent"));
}
