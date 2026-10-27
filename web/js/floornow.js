import { state } from "./data.js";
import { escapeHtml, prettyKey } from "./format.js";

export const TEAM_NAMES = { A: "Live orders", B: "Payments & refunds", C: "Order accuracy", D: "Account & app" };
export const LANGUAGE = { hi: "Hindi", en: "English", other: "Regional" };
export const STATUS_TEXT = {
  busy: "Working", cross: "Rescue for another team", wrong: "Working outside skills", idle: "Free", off: "Off shift",
  break: "On a break",
};

const FRESH_MS = 5000;
const WAIT_MS = 2500;

export function clockNow() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

export function weekdayNow() {
  return (new Date().getDay() + 6) % 7;
}

export function minuteOfDay() {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
}

export function clockOf(minute) {
  const m = Math.max(0, Math.floor(minute));
  return `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export async function postAction(body) {
  try {
    const response = await fetch("/api/live/action", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weekday: weekdayNow(), minute: Number(minuteOfDay().toFixed(2)), ...body }),
    });
    const data = await response.json();
    if (response.ok) document.dispatchEvent(new CustomEvent("live-changed"));
    return response.ok ? data : { error: data.error || "The engine refused this action." };
  } catch (error) {
    return { error: "The engine is not answering. Is the server running?" };
  }
}

export async function resetDay() {
  try {
    const response = await fetch("/api/live/reset", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ weekday: weekdayNow() }),
    });
    const data = await response.json();
    document.dispatchEvent(new CustomEvent("live-changed"));
    return data;
  } catch (error) {
    return { error: "The engine is not answering. Is the server running?" };
  }
}

function known(value) {
  return value !== null && value !== undefined;
}

function pctText(p) {
  return `${Math.round(p * 100)}%`;
}

function outcomeText(e) {
  const to = e.went_to;
  if (!to || !known(to.deadline)) return "";
  if (e.outcome === "kept") return `made its promise (done ${clockOf(to.resolved)})`;
  if (e.outcome === "missed") return known(to.resolved)
    ? `missed its promise (done ${clockOf(to.resolved)}, due ${clockOf(to.deadline)})` : `missed its promise (due ${clockOf(to.deadline)})`;
  return `is due ${clockOf(to.deadline)}`;
}

function riskChange(was, to) {
  if (!was || !known(was.risk) || !known(to.risk) || (was.risk >= 1 && to.risk >= 1)) return "";
  return `, chance of missing its promise ${pctText(was.risk)} → ${to.risk >= 1 ? "already late" : pctText(to.risk)}`;
}

export function effectLines(e, nameOf) {
  const who = nameOf(e.agent);
  const to = e.went_to;
  const was = e.planned;
  const lines = [];
  if (e.kind === "decline") {
    const head = `${who} could not take ${e.ticket_id}${e.reason ? ` (${e.reason})` : ""}.`;
    if (to && to.agent) {
      lines.push(`${head} Re-routed to ${nameOf(to.agent)} at ${clockOf(to.minute)}${riskChange(was, to)}.`);
    } else {
      lines.push(`${head} ${e.complete ? "Nobody picked it up before midnight." : "Not picked up in the next hour yet; OpsLens keeps trying."}`);
    }
  } else if (e.kind === "take") {
    lines.push(`${who} took ${e.ticket_id}${to && known(to.minute) ? `: starts ${clockOf(to.minute)}` : ""}.`);
  } else if (e.kind === "done") {
    const early = was && to && known(was.resolved) && known(to.resolved) ? Math.round(was.resolved - to.resolved) : null;
    const diff = early === null ? "" : early > 0 ? `, ${early} min earlier than planned` : early < 0 ? `, ${-early} min later than planned` : "";
    lines.push(`${who} finished ${e.ticket_id} at ${clockOf(known(e.value) ? e.value : e.minute)}${diff}.`);
    if (e.next_ticket) lines.push(`Next for ${who}: ${e.next_ticket.ticket_id} at ${clockOf(e.next_ticket.minute)}.`);
  } else if (e.kind === "extra_time") {
    lines.push(`${who} needs ${Math.round(e.value)} more min on ${e.ticket_id}${to && known(to.resolved) ? `: done about ${clockOf(to.resolved)}` : ""}.`);
  } else if (e.kind === "break") {
    lines.push(`${who} went on a break at ${clockOf(e.minute)}. OpsLens gives new work to others.`);
  } else if (e.kind === "back") {
    lines.push(`${who} came back at ${clockOf(e.minute)}.`);
  }
  const outcome = ["decline", "take", "extra_time"].includes(e.kind) ? outcomeText(e) : "";
  if (outcome) lines.push(`The ticket ${outcome}.`);
  return lines;
}

export function floorEffect(e) {
  if (!known(e.missed_before) || !known(e.missed_after)) return e.complete === false ? "Measuring the rest of the day…" : "";
  const d = e.missed_after - e.missed_before;
  return `Promises missed by midnight: ${e.missed_before} → ${e.missed_after}${d === 0 ? " (no change)" : d > 0 ? ` (+${d})` : ` (${d})`}`;
}

export async function fetchFloor() {
  if (state.staticServer) return { error: "The live floor needs the OpsLens server." };
  const weekday = weekdayNow();
  const minute = minuteOfDay();
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
  document.addEventListener("live-changed", () => tick());
  tick();
}

export function notReady(data) {
  if (data.error) return `<div class="callout warn">${escapeHtml(data.error)}</div>`;
  return `<div class="wait" role="status"><span class="spinner" aria-hidden="true"></span>
    <span class="wait-text">Simulating today on this laptop, every customer and every agent…</span></div>`;
}

export function duration(minutes) {
  const m = Math.round(Math.abs(minutes));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
}

export function minutesLeft(m) {
  return m >= 0 ? `${duration(m)} left` : `${duration(m)} late`;
}

export function ticketLine(t) {
  return `${escapeHtml(t.priority)} · ${escapeHtml(prettyKey(t.category))} · ${escapeHtml(LANGUAGE[t.language] || t.language)}`;
}

export function initialsOf(name) {
  return String(name).split(/\s+/).map((w) => w.charAt(0)).join("").slice(0, 2).toUpperCase();
}
