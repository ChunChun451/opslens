import { state } from "./data.js";
import { escapeHtml, prettyKey } from "./format.js";

export const TEAM_NAMES = { A: "Live orders", B: "Payments & refunds", C: "Order accuracy", D: "Account & app" };
export const LANGUAGE = { hi: "Hindi", en: "English", other: "Regional" };
export const STATUS_TEXT = {
  busy: "Working", cross: "Rescue for another team", wrong: "Working outside skills", idle: "Free", off: "Off shift",
};

const FRESH_MS = 5000;
const WAIT_MS = 2500;

export function clockNow() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

export async function fetchFloor() {
  if (state.staticServer) return { error: "The live floor needs the OpsLens server." };
  const now = new Date();
  const weekday = (now.getDay() + 6) % 7;
  const minute = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
  try {
    const response = await fetch(`/api/live?weekday=${weekday}&minute=${minute.toFixed(2)}`, { cache: "no-store" });
    return await response.json();
  } catch (error) {
    return { error: "The engine is not answering. Is the server running?" };
  }
}

export function keepFresh(section, viewId, draw) {
  let timer = null;
  const tick = async () => {
    clearTimeout(timer);
    if (!section.isConnected || section.offsetParent === null) return;
    const data = await fetchFloor();
    if (!section.isConnected) return;
    draw(data);
    timer = setTimeout(tick, data && data.ready ? FRESH_MS : WAIT_MS);
  };
  document.addEventListener("tab-shown", (event) => {
    if (event.detail === viewId) tick();
  });
  tick();
}

export function notReady(data) {
  if (data.error) return `<div class="callout warn">${escapeHtml(data.error)}</div>`;
  return `<div class="wait" role="status"><span class="spinner" aria-hidden="true"></span>
    <span class="wait-text">Simulating today on this laptop, every customer and every agent…</span></div>`;
}

export function minutesLeft(m) {
  return m >= 0 ? `${Math.round(m)} min left` : `${Math.round(-m)} min late`;
}

export function ticketLine(t) {
  return `${escapeHtml(t.priority)} · ${escapeHtml(prettyKey(t.category))} · ${escapeHtml(LANGUAGE[t.language] || t.language)}`;
}

export function initialsOf(name) {
  return String(name).split(/\s+/).map((w) => w.charAt(0)).join("").slice(0, 2).toUpperCase();
}
