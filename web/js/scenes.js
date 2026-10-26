import { customerHtml, biryaniHtml, setMood, cheer } from "./mascot.js";
import { characterHtml } from "./characters.js";
import { state } from "./data.js";
import { escapeHtml } from "./format.js";

const LINE_MS = 4800;
const SLEEP_MS = 60000;

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

function num(value, digits = 1) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : null;
}
function pct(value) {
  return typeof value === "number" ? Math.round(value * 100) : null;
}

function sceneFor(viewId, r) {
  const means = r?.baseline_c?.test?.means;
  const ours = num(means?.opslens?.["turnaround.breach_pct"]);
  const theirs = num(means?.baseline_d?.["turnaround.breach_pct"]);
  const raceLine = ours && theirs ? `OpsLens missed ${ours}% of promises, industry routing ${theirs}%.` : null;
  const rd = r?.realdesk;
  const lines = (list) => list.filter(Boolean);
  switch (viewId) {
    case "overview":
      return { mood: "happy", chr: "trophy", stage: "confetti",
        complaint: "Chicken biryani mein chicken ke kam pieces diye!", lines: lines([
        ours && `Only ${ours}% of promises missed on days OpsLens never saw. Trophy time!`,
        raceLine,
        "Every number here clicks through to its evidence.",
      ]) };
    case "patterns":
      return { mood: "idle", chr: "gears", stage: "scan", lines: lines([
        ...(r?.patterns?.cards || []).slice(0, 4).map((c) => `Found it: ${c.title}`),
        r?.patterns?.recall && `${r.patterns.recall.found} of ${r.patterns.recall.planted} hidden problems found.`,
      ]) };
    case "atrisk":
      return { mood: "worried", chr: "hourglass", stage: "countdown", lines: lines([
        ...(r?.risk?.at_risk || []).slice(0, 3).map((t) => {
          const left = num(t.minutes_to_sla, 0);
          return left !== null ? `${t.ticket_id} needs help: ${left} min left!` : null;
        }),
        "I tell you who to help first, and why.",
      ]) };
    case "forecast":
      return { mood: "idle", chr: "cloud", stage: "weather", lines: lines([
        ...(r?.forecast?.bottlenecks || []).slice(0, 3).map((b) => b.text && `Rush ahead: ${b.text}`),
        pct(r?.forecast?.coverage_80) !== null && `My 80% range caught ${pct(r.forecast.coverage_80)}% of real hours.`,
      ]) };
    case "recommendations":
      return { mood: "happy", chr: "rocket", stage: "checklist", lines: lines([
        ...(r?.playbooks?.playbooks || []).slice(0, 3).map((p) => p.title && `Do this first: ${p.title}`),
        "Accept a fix and I add it to your plan.",
      ]) };
    case "compare":
      return { mood: "idle", chr: "box", stage: "race", lines: lines([
        "Same tickets, same luck, same people. Only the decisions differ.",
        raceLine,
      ]) };
    case "whatif":
      return { mood: "idle", chr: "robot", stage: "slider", lines: [
        "Change a team or the volume, then press Run simulation.",
        "Your idea, not ours: I replay the whole day in seconds.",
      ] };
    case "ledger":
      return { mood: "idle", chr: "book", stage: "ledger", lines: [
        "We wrote the rules before the runs.",
        "Kept or missed, we show both.",
      ] };
    case "tested":
      return { mood: "idle", chr: "flask", stage: "bubbles", lines: [
        "Every test we ran, even the ones we failed.",
        "Click any number to see where it came from.",
      ] };
    case "upload":
      return { mood: "idle", chr: "folder", stage: "drop", lines: [
        "Drop a CSV and I look for its problems.",
        "No file? Use the UCI example.",
      ] };
    case "rd-overview":
      return { mood: "worried", chr: "monitor", stage: "scan", lines: lines([
        num(rd?.summary?.missed_sla_pct, 0) && `${num(rd.summary.missed_sla_pct, 0)}% of real incidents missed their SLA. Let's see why.`,
        "This desk is real: a public ServiceNow log.",
      ]) };
    case "rd-problems":
      return { mood: "idle", chr: "gears", stage: "scan", lines: lines([
        ...(rd?.cards || []).slice(0, 3).map((c) => `Found it: ${c.title}`),
      ]) };
    case "rd-risks":
      return { mood: "worried", chr: "hourglass", stage: "countdown", lines: lines([
        num(rd?.early_warning?.auc_opslens, 2) && num(rd?.early_warning?.auc_priority, 2) &&
          `My early warning scores ${num(rd.early_warning.auc_opslens, 2)}, the desk's own priority ${num(rd.early_warning.auc_priority, 2)}.`,
        "One hour after an incident opens, I know if it is in trouble.",
      ]) };
    case "rd-actions":
      return { mood: "happy", chr: "rocket", stage: "checklist", lines: [
        "Accept a fix and I add it to your plan.",
        "Each fix says who owns it outside the desk.",
      ] };
    case "rd-proof":
      return { mood: "idle", chr: "scale", stage: "race", lines: [
        "Learned on old months, scored on later ones.",
        "Where I do not beat the desk, I say so.",
      ] };
    default:
      return null;
  }
}

const scenes = new Map();

export function addScene(container, viewId) {
  const scene = sceneFor(viewId, state.results);
  if (!scene || !scene.lines.length || container.querySelector(".sc")) return;
  const id = `sc-${viewId}`;
  const customer = scene.complaint
    ? `<div class="sc-customer">${customerHtml(`${id}-customer`)}${biryaniHtml(`${id}-biryani`, true)}
        <div class="sc-say sc-complain">${escapeHtml(scene.complaint)}</div></div>`
    : "";
  const html = `<div class="sc sc-${scene.stage}-scene${customer ? " sc-has-customer" : ""}" data-scene="${viewId}" aria-hidden="true">
      ${customer}
      <div class="sc-cast" title="Click me">${characterHtml(id, scene.chr, scene.mood)}</div>
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
  document.addEventListener("world-changed", () => scenes.clear());
}
