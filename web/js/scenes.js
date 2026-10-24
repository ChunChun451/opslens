// scenes.js — a small cartoon moment at the top of every screen: Lenny with a prop that fits the
// screen's job, a speech bubble, and a tiny animated stage.
//
// Why (24 Oct, the owner liked the Live now scene and asked for "more in every page according to
// situation"): each screen answers one question, and the scene says that question in one picture.
// Problems: a detective scanning tickets. Risks: an alarm clock ringing. Next 48 hours: binoculars
// and weather. Actions: a checklist. Proof: a race, a stamp, a flask. It is decoration with a job:
// the bubble's lines quote the screen's own top result, read from eval/results.json (never a
// number we did not compute). Clicking Lenny says the next line. After a minute without input he
// falls asleep and wakes on the next mouse move. Pure SVG + CSS (web/neon.css, "Scenes").
//
// Example: Risks → Lenny worried, the alarm rings, the bubble says "T060758 needs help: 7 min left!".

import { mascotHtml, customerHtml, biryaniHtml, setMood, cheer } from "./mascot.js";
import { state } from "./data.js";
import { escapeHtml } from "./format.js";

const LINE_MS = 4800; // how long one bubble line stays
const SLEEP_MS = 60000; // no input for this long → Lenny naps

// Props drawn next to Lenny (24×24-ish SVGs, coloured to match the neon theme).
const PROPS = {
  trophy: `<svg viewBox="0 0 32 32"><path d="M9 4h14v7a7 7 0 01-14 0z" fill="#fbbf24" stroke="#f59e0b"/>
    <path d="M9 7H5a4 4 0 004 5M23 7h4a4 4 0 01-4 5" fill="none" stroke="#f59e0b" stroke-width="2"/>
    <rect x="14" y="17" width="4" height="6" fill="#f59e0b"/><rect x="9" y="23" width="14" height="4" rx="1" fill="#a78bfa"/>
    <path class="shine" d="M12 6v5" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  hat: `<svg viewBox="0 0 40 20"><path d="M4 16q16 -6 32 0q-2 -12 -16 -13q-14 1 -16 13z" fill="#8b5e3c"/>
    <path d="M2 16q18 4 36 0" stroke="#5b3a22" stroke-width="3" fill="none" stroke-linecap="round"/>
    <path d="M10 10q10 -4 20 0" stroke="#c08457" stroke-width="1.4" fill="none"/></svg>`,
  alarm: `<svg viewBox="0 0 32 32"><circle cx="16" cy="18" r="10" fill="#1e293b" stroke="#ff4d8d" stroke-width="2.4"/>
    <path d="M16 12v6l4 3" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>
    <circle cx="7" cy="7" r="4" fill="#ff4d8d"/><circle cx="25" cy="7" r="4" fill="#ff4d8d"/>
    <path d="M9 28l-2 2M23 28l2 2" stroke="#ff4d8d" stroke-width="2" stroke-linecap="round"/></svg>`,
  binoculars: `<svg viewBox="0 0 36 24"><rect x="2" y="6" width="13" height="15" rx="5" fill="#334155" stroke="#22d3ee" stroke-width="1.6"/>
    <rect x="21" y="6" width="13" height="15" rx="5" fill="#334155" stroke="#22d3ee" stroke-width="1.6"/>
    <rect x="13" y="9" width="10" height="6" rx="2" fill="#475569"/>
    <circle class="glint" cx="8.5" cy="16" r="3" fill="#7dd3fc"/><circle class="glint" cx="27.5" cy="16" r="3" fill="#7dd3fc"/></svg>`,
  clipboard: `<svg viewBox="0 0 28 32"><rect x="2" y="4" width="24" height="27" rx="3" fill="#fef3c7" stroke="#f59e0b" stroke-width="1.4"/>
    <rect x="9" y="1" width="10" height="6" rx="2" fill="#a78bfa"/>
    <path class="tick t1" d="M6 13l2 2 4 -4" stroke="#22c55e" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <path class="tick t2" d="M6 21l2 2 4 -4" stroke="#22c55e" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <path d="M15 13h7M15 21h7" stroke="#b45309" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  stopwatch: `<svg viewBox="0 0 32 32"><circle cx="16" cy="18" r="11" fill="#1e293b" stroke="#22d3ee" stroke-width="2.4"/>
    <rect x="13" y="2" width="6" height="4" rx="1" fill="#22d3ee"/>
    <path class="hand" d="M16 18V10" stroke="#ff4d8d" stroke-width="2.2" stroke-linecap="round"/></svg>`,
  dial: `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="12" fill="#1e293b" stroke="#a78bfa" stroke-width="2.4"/>
    <g class="knob"><path d="M16 16V7" stroke="#22d3ee" stroke-width="3" stroke-linecap="round"/></g>
    <circle cx="16" cy="16" r="3" fill="#22d3ee"/></svg>`,
  stamp: `<svg viewBox="0 0 28 32"><rect x="10" y="2" width="8" height="12" rx="3" fill="#a78bfa"/>
    <rect x="4" y="14" width="20" height="6" rx="2" fill="#7c3aed"/><rect x="3" y="20" width="22" height="4" rx="1" fill="#22c55e"/></svg>`,
  flask: `<svg viewBox="0 0 28 32"><path d="M10 3h8M11 3v9L4 26a3 3 0 003 4h14a3 3 0 003 -4L17 12V3" fill="rgba(34,211,238,0.12)" stroke="#22d3ee" stroke-width="1.8"/>
    <path d="M7 22h14l2.5 4.5a2 2 0 01-2 2.5H6.5a2 2 0 01-2-2.5z" fill="#22c55e" opacity="0.8"/>
    <circle class="bub b1" cx="12" cy="24" r="1.6" fill="#fff"/><circle class="bub b2" cx="16" cy="25" r="1.2" fill="#fff"/></svg>`,
  file: `<svg viewBox="0 0 26 32"><path d="M3 2h13l7 7v21H3z" fill="#e2e8f0" stroke="#22d3ee" stroke-width="1.4"/>
    <path d="M16 2v7h7" fill="#cbd5e1"/><text x="5" y="24" font-size="7" font-weight="800" fill="#0d1428">CSV</text></svg>`,
};

// The little animated stage beside the bubble.
const STAGES = {
  confetti: () => `<div class="sc-confetti">${"<i></i>".repeat(12)}</div>`,
  scan: () => `<div class="sc-scan">${'<i class="chip"></i>'.repeat(7)}<b class="beam"></b></div>`,
  countdown: () => `<div class="sc-countdown"><i></i></div>`,
  weather: () => `<div class="sc-weather"><i class="cloud c1"></i><i class="cloud c2"></i>
      <svg viewBox="0 0 120 30" preserveAspectRatio="none"><path class="wave" d="M0 24 Q15 20 30 22 T60 12 T90 6 T120 18" fill="none" stroke="#22d3ee" stroke-width="2.4"/>
      <path d="M0 14 H120" stroke="#ff4d8d" stroke-width="1.2" stroke-dasharray="4 3"/></svg></div>`,
  checklist: () => `<div class="sc-checklist">${[1, 2, 3].map((n) => `<span class="row r${n}"><i></i><b></b></span>`).join("")}</div>`,
  race: () => `<div class="sc-race"><span class="lane"><i class="runner them"></i></span>
      <span class="lane ours"><i class="runner us"></i></span><b class="flag"></b></div>`,
  slider: () => `<div class="sc-slider">${[1, 2, 3].map((n) => `<span class="sl s${n}"><i></i></span>`).join("")}</div>`,
  ledger: () => `<div class="sc-ledger">${[1, 2, 3].map((n) => `<span class="rule l${n}"><b></b><em>${n === 2 ? "missed" : "kept"}</em></span>`).join("")}</div>`,
  bubbles: () => `<div class="sc-bubbles">${"<i></i>".repeat(8)}</div>`,
  drop: () => `<div class="sc-drop"><i class="doc"></i><b class="tray"></b></div>`,
};

// Small number helpers: values come straight from the results; we only round them.
function num(value, digits = 1) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : null;
}
function pct(value) {
  return typeof value === "number" ? Math.round(value * 100) : null;
}

// One entry per view id: Lenny's mood, his prop, the stage, the place of the prop, and the lines.
function sceneFor(viewId, r) {
  const means = r?.baseline_c?.test?.means;
  const ours = num(means?.opslens?.["turnaround.breach_pct"]);
  const theirs = num(means?.baseline_d?.["turnaround.breach_pct"]);
  const raceLine = ours && theirs ? `OpsLens missed ${ours}% of promises, industry routing ${theirs}%.` : null;
  const rd = r?.realdesk;
  const lines = (list) => list.filter(Boolean);
  switch (viewId) {
    case "overview":
      return { mood: "happy", prop: "trophy", at: "side", stage: "confetti",
        complaint: "Chicken biryani mein chicken ke kam pieces diye!", lines: lines([
        ours && `Only ${ours}% of promises missed on days I never saw. Trophy time!`,
        raceLine,
        "Every number here clicks through to its evidence.",
      ]) };
    case "patterns":
      return { mood: "idle", prop: "hat", at: "top", stage: "scan", lines: lines([
        ...(r?.patterns?.cards || []).slice(0, 4).map((c) => `Found it: ${c.title}`),
        r?.patterns?.recall && `${r.patterns.recall.found} of ${r.patterns.recall.planted} hidden problems found.`,
      ]) };
    case "atrisk":
      return { mood: "worried", prop: "alarm", at: "side", stage: "countdown", lines: lines([
        ...(r?.risk?.at_risk || []).slice(0, 3).map((t) => {
          const left = num(t.minutes_to_sla, 0);
          return left !== null ? `${t.ticket_id} needs help: ${left} min left!` : null;
        }),
        "I tell you who to help first, and why.",
      ]) };
    case "forecast":
      return { mood: "idle", prop: "binoculars", at: "front", stage: "weather", lines: lines([
        ...(r?.forecast?.bottlenecks || []).slice(0, 3).map((b) => b.text && `Rush ahead: ${b.text}`),
        pct(r?.forecast?.coverage_80) !== null && `My 80% range caught ${pct(r.forecast.coverage_80)}% of real hours.`,
      ]) };
    case "recommendations":
      return { mood: "happy", prop: "clipboard", at: "side", stage: "checklist", lines: lines([
        ...(r?.playbooks?.playbooks || []).slice(0, 3).map((p) => p.title && `Do this first: ${p.title}`),
        "Accept a fix and I add it to your plan.",
      ]) };
    case "compare":
      return { mood: "idle", prop: "stopwatch", at: "side", stage: "race", lines: lines([
        "Same tickets, same luck, same people. Only the decisions differ.",
        raceLine,
      ]) };
    case "whatif":
      return { mood: "idle", prop: "dial", at: "side", stage: "slider", lines: [
        "Change a team or the volume, then press Run simulation.",
        "Your idea, not ours: I replay the whole day in seconds.",
      ] };
    case "ledger":
      return { mood: "idle", prop: "stamp", at: "side", stage: "ledger", lines: [
        "We wrote the rules before the runs.",
        "Kept or missed, we show both.",
      ] };
    case "tested":
      return { mood: "idle", prop: "flask", at: "side", stage: "bubbles", lines: [
        "Every test we ran, even the ones we failed.",
        "Click any number to see where it came from.",
      ] };
    case "upload":
      return { mood: "idle", prop: "file", at: "side", stage: "drop", lines: [
        "Drop a CSV and I look for its problems.",
        "No file? Use the UCI example.",
      ] };
    case "rd-overview":
      return { mood: "worried", prop: "hat", at: "top", stage: "scan", lines: lines([
        num(rd?.summary?.missed_sla_pct, 0) && `${num(rd.summary.missed_sla_pct, 0)}% of real incidents missed their SLA. Let's see why.`,
        "This desk is real: a public ServiceNow log.",
      ]) };
    case "rd-problems":
      return { mood: "idle", prop: "hat", at: "top", stage: "scan", lines: lines([
        ...(rd?.cards || []).slice(0, 3).map((c) => `Found it: ${c.title}`),
      ]) };
    case "rd-risks":
      return { mood: "worried", prop: "alarm", at: "side", stage: "countdown", lines: lines([
        num(rd?.early_warning?.auc_opslens, 2) && num(rd?.early_warning?.auc_priority, 2) &&
          `My early warning scores ${num(rd.early_warning.auc_opslens, 2)}, the desk's own priority ${num(rd.early_warning.auc_priority, 2)}.`,
        "One hour after an incident opens, I know if it is in trouble.",
      ]) };
    case "rd-actions":
      return { mood: "happy", prop: "clipboard", at: "side", stage: "checklist", lines: [
        "Accept a fix and I add it to your plan.",
        "Each fix says who owns it outside the desk.",
      ] };
    case "rd-proof":
      return { mood: "idle", prop: "stopwatch", at: "side", stage: "race", lines: [
        "Learned on old months, scored on later ones.",
        "Where I do not beat the desk, I say so.",
      ] };
    default:
      return null;
  }
}

const scenes = new Map(); // view id → { lines, index, mood }

// Add the scene to a freshly drawn view (below its title). Live now has its own scene.
export function addScene(container, viewId) {
  const scene = sceneFor(viewId, state.results);
  if (!scene || !scene.lines.length || container.querySelector(".sc")) return;
  const id = `sc-${viewId}`;
  // A complaining customer with the plate they got, on screens that have one (Results).
  const customer = scene.complaint
    ? `<div class="sc-customer">${customerHtml(`${id}-customer`)}${biryaniHtml(`${id}-biryani`, true)}
        <div class="sc-say sc-complain">${escapeHtml(scene.complaint)}</div></div>`
    : "";
  const html = `<div class="sc sc-${scene.stage}-scene${customer ? " sc-has-customer" : ""}" data-scene="${viewId}" aria-hidden="true">
      ${customer}
      <div class="sc-cast sc-at-${scene.at}" title="Click me">
        ${mascotHtml(id, scene.mood)}
        <span class="sc-prop sc-prop-${scene.prop}">${PROPS[scene.prop]}</span>
      </div>
      <div class="sc-say" id="${id}-say">${escapeHtml(scene.lines[0])}</div>
      <div class="sc-stage">${STAGES[scene.stage]()}</div>
    </div>`;
  const head = container.querySelector(".page-head, .ov-hero, header");
  if (head && head.parentElement === container) {
    head.insertAdjacentHTML("afterend", html);
  } else {
    container.insertAdjacentHTML("afterbegin", html);
  }
  scenes.set(viewId, { lines: scene.lines, index: 0, mood: scene.mood, id });
  container.querySelector(".sc-cast").addEventListener("click", () => {
    nextLine(viewId);
    cheer(id, scene.mood === "worried" ? "On it!" : "Hi!");
  });
}

// The next line in the visible scene's bubble, with a little pop.
function nextLine(viewId) {
  const s = scenes.get(viewId);
  const say = s && document.getElementById(`${s.id}-say`);
  if (!say || s.lines.length < 2) return;
  s.index = (s.index + 1) % s.lines.length;
  say.textContent = s.lines[s.index];
  say.classList.remove("pop");
  void say.offsetWidth;
  say.classList.add("pop");
}

function visibleScene() {
  for (const [viewId, s] of scenes) {
    const el = document.getElementById(s.id);
    if (el && el.offsetParent !== null) return viewId;
  }
  return null;
}

// One timer for all scenes (only the visible one talks), and the nap after a quiet minute.
export function initScenes() {
  setInterval(() => {
    const viewId = visibleScene();
    if (viewId) nextLine(viewId);
  }, LINE_MS);
  let napTimer = null;
  let napping = false;
  const wake = () => {
    if (napping) {
      napping = false;
      scenes.forEach((s) => setMood(s.id, s.mood));
    }
    clearTimeout(napTimer);
    napTimer = setTimeout(() => {
      napping = true;
      scenes.forEach((s) => setMood(s.id, "sleep"));
    }, SLEEP_MS);
  };
  ["pointermove", "keydown", "wheel", "touchstart"].forEach((type) =>
    window.addEventListener(type, wake, { passive: true }));
  wake();
  // A new world draws every view again.
  document.addEventListener("world-changed", () => scenes.clear());
}
