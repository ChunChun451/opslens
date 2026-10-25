// storycards.js — two animated, clickable stories on the Results screen, for people who do not
// read percentages: "Out of 1,000 customers" and "Follow one ticket" (with a delivery rider).
//
// Why (24 Oct, the owner: "add information in animated format which people can interact with and
// relate to"): "2.0% vs 5.5%" is abstract; 20 red dots out of 1,000 next to 55 is not. And one
// real ticket walking through OpsLens ("mera paisa wapas karo please") explains the engine
// better than a diagram. Every number comes from results.json and stays clickable to it; the
// dot counts are the measured rate × 10, rounded. The "your floor" slider is plain arithmetic
// on the measured rates (tickets per day × the gap), labelled as such; it is not a simulation.
// The delivery scene (flat cartoon, after the owner's reference pictures: a rider in a red helmet
// on a red scooter with a burger paper bag, a dashed route between two pins, a stopwatch, a big
// phone with the live map) is decoration; the rider, the route and the map dot move with the
// ticket's steps. No brand marks (CLAUDE.md 1.5).
//
// Example: click "First come, first served" → 131 of the 1,000 dots turn red; click "OpsLens" →
// all but 20 ripple back to green; the slider at 50,000 tickets a day says "about 1,730 more
// promises kept every day than the industry standard".

import { state, policyKeys } from "./data.js";
import { ev } from "./evidence.js";
import { shortLabel } from "./ui.js";
import { escapeHtml, tidyDash } from "./format.js";

const BREACH = "turnaround.breach_pct";
const DOTS = 1000;
const CYCLE_MS = 3200; // the dot wall shows each way of working in turn until someone clicks
const STEP_MS = 2600; // one step of the ticket's journey
const FLOORS = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000]; // the slider's stops
const LANG = { hi: "Hindi", en: "English" };

const pathOf = (k) => `sim.policies.${k}.kpis.${BREACH}.mean`;
const rateOf = (k) => state.results.sim.policies[k].kpis[BREACH].mean;
const perThousand = (k) => Math.round(rateOf(k) * 10);
const nice = (n) => Math.round(n).toLocaleString("en-IN");

// ---------------------------------------------------------------------------------------------
// Out of 1,000 customers
// ---------------------------------------------------------------------------------------------

// A fixed shuffle (same every load), so the same customers turn red as the count grows.
function shuffledRanks() {
  const order = Array.from({ length: DOTS }, (_, i) => i);
  let seed = 7;
  for (let i = DOTS - 1; i > 0; i--) {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    const j = seed % (i + 1);
    [order[i], order[j]] = [order[j], order[i]];
  }
  const rank = new Array(DOTS);
  order.forEach((dot, r) => { rank[dot] = r; });
  return rank;
}

export function thousandHtml() {
  const r = state.results;
  if (!r.sim || !r.sim.policies.opslens) return "";
  const keys = policyKeys();
  const ranks = shuffledRanks();
  // The ripple: each dot's change waits a little by its distance from the top-left corner.
  const dots = ranks.map((rank, i) => `<i style="--r:${rank};--d:${(i % 40) + Math.floor(i / 40)}"></i>`).join("");
  const chips = keys.map((k) => `<button type="button" class="tw-chip${k === "opslens" ? " is-ours" : ""}" data-k="${k}">${escapeHtml(shortLabel(k))}</button>`).join("");
  const counts = keys.map((k) => `<div class="tw-count" data-k="${k}" hidden>
      <div class="tw-big"><b>${perThousand(k)}</b> <span>of 1,000 customers</span></div>
      <div class="tw-sub">waited past their promise with <strong>${escapeHtml(shortLabel(k))}</strong> (${ev(pathOf(k), "pct")} missed)</div>
    </div>`).join("");
  return `<section class="card tale-card" id="ov-thousand">
      <div class="card-head"><div><h2 class="card-title">Out of 1,000 customers</h2>
        <p class="card-sub">Each dot is one customer on the held-out days. Red waited past the promised time. Click a way of working.</p></div></div>
      <div class="tw">
        <div class="tw-wall" aria-hidden="true">${dots}</div>
        <div class="tw-side">
          <div class="tw-chips">${chips}</div>
          ${counts}
          <div class="tw-gap" id="tw-gap"></div>
          <label class="tw-floor">
            <span>Your floor: <b id="tw-n">50,000</b> tickets a day</span>
            <input type="range" id="tw-slider" min="0" max="${FLOORS.length - 1}" step="1" value="4">
          </label>
          <div class="tw-save" id="tw-save"></div>
          <div class="tw-note">Plain arithmetic on the measured rates (tickets × the gap), not a simulation of your floor.</div>
        </div>
      </div>
    </section>`;
}

function initThousand(section) {
  const box = section.querySelector("#ov-thousand");
  if (!box) return;
  const keys = policyKeys();
  const lead = keys.includes("baseline_d") ? "baseline_d" : keys.find((k) => k !== "opslens");
  let current = null;
  let cycling = true;
  let cycleIndex = 0;

  const draw = (k) => {
    current = k;
    box.style.setProperty("--red", perThousand(k));
    box.querySelectorAll(".tw-chip").forEach((c) => c.setAttribute("aria-pressed", c.dataset.k === k ? "true" : "false"));
    box.querySelectorAll(".tw-count").forEach((c) => { c.hidden = c.dataset.k !== k; });
    box.dataset.policy = k;
    const gap = box.querySelector("#tw-gap");
    if (k === "opslens") {
      gap.innerHTML = `<b>${perThousand(lead) - perThousand("opslens")}</b> more promises kept than ${escapeHtml(shortLabel(lead))}. Same customers, same agents, same luck.`;
    } else {
      gap.innerHTML = `OpsLens would bring these <b>${perThousand(k)}</b> down to <b>${perThousand("opslens")}</b>.`;
    }
    drawSaving();
  };
  const drawSaving = () => {
    const n = FLOORS[Number(box.querySelector("#tw-slider").value)];
    const versus = current && current !== "opslens" ? current : lead;
    const saved = (n * (rateOf(versus) - rateOf("opslens"))) / 100;
    box.querySelector("#tw-n").textContent = nice(n);
    box.querySelector("#tw-save").innerHTML = `≈ <b>${nice(saved)}</b> more promises kept every day than ${escapeHtml(shortLabel(versus))}`;
  };

  // The dots: red when their rank is below the count (CSS reads --red and each dot's --r).
  box.querySelectorAll(".tw-chip").forEach((chip) => chip.addEventListener("click", () => {
    cycling = false;
    draw(chip.dataset.k);
  }));
  box.querySelector("#tw-slider").addEventListener("input", drawSaving);
  draw(keys[0]);
  const timer = setInterval(() => {
    if (!document.body.contains(box)) { clearInterval(timer); return; }
    if (!cycling || box.offsetParent === null) return;
    cycleIndex = (cycleIndex + 1) % keys.length;
    draw(keys[cycleIndex]);
  }, CYCLE_MS);
}

// ---------------------------------------------------------------------------------------------
// Follow one ticket (with the rider)
// ---------------------------------------------------------------------------------------------

const STEPS = [
  { label: "A customer writes", icon: '<path d="M4 6h16v10H8l-4 4z"/>' },
  { label: "OpsLens reads it", icon: '<path d="M4 7h10l6 5-6 5H4z"/><circle cx="8" cy="12" r="1.5"/>' },
  { label: "It sees the danger", icon: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.1"/>' },
  { label: "It picks the right agent", icon: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1-4 4-6 7-6s6 2 7 6"/>' },
  { label: "The risk drops", icon: '<path d="M4 6l6 6 4-4 6 8"/><path d="M15 16h5v-5"/>' },
];

// Tickets worth following: the riskiest ones where serving now really helps (from the model).
function journeyTickets() {
  const list = (state.results.risk && state.results.risk.at_risk) || [];
  return list.map((t, i) => ({ t, i }))
    .filter(({ t }) => typeof t.probability_after_action === "number" && t.probability - t.probability_after_action >= 0.5)
    .slice(0, 3);
}

function pretty(category) {
  return String(category || "").replace(/_/g, " ");
}

// The rider, flat cartoon style: red helmet and jacket, a red scooter, a burger paper bag on
// the back carrier. Drawn on a 200×150 grid; wheels spin, the body bobs, exhaust puffs.
function riderSvg() {
  const wheel = (x) => `<g class="wheel"><circle cx="${x}" cy="126" r="19" fill="#111827"/>
      <circle cx="${x}" cy="126" r="10.5" fill="#f8fafc"/><circle cx="${x}" cy="126" r="4" fill="#334155"/>
      <path d="M${x} 116.5 v19 M${x - 9.5} 126 h19" stroke="#94a3b8" stroke-width="1.6"/></g>`;
  return `<svg class="rider" viewBox="0 0 200 150" width="200" height="150" aria-hidden="true">
      <g class="exhaust"><circle cx="8" cy="122" r="6" fill="#e2e8f0"/><circle cx="16" cy="114" r="4" fill="#e2e8f0"/></g>
      <g class="speed"><path d="M2 70 h18 M0 86 h14 M6 100 h16" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity="0.7"/></g>
      <g class="ride">
        <g class="bag">
          <path d="M18 80 h46" stroke="#1f2937" stroke-width="4" stroke-linecap="round"/>
          <path d="M22 36 h40 l-3 44 h-34z" fill="#c8a272"/>
          <path d="M22 36 l4 -7 l4 4 l4 -4 l4 4 l4 -4 l4 4 l4 -4 l4 4 l4 -4 l4 7z" fill="#b08b5a"/>
          <path d="M31 56 q11 -12 22 0z" fill="#f59e0b"/><circle cx="38" cy="51" r="0.9" fill="#fff"/><circle cx="45" cy="50" r="0.9" fill="#fff"/>
          <path d="M30 57 q3.5 3 7.5 0 q3.5 3 7.5 0 q3.5 3 8 0" stroke="#22c55e" stroke-width="2.4" fill="none" stroke-linecap="round"/>
          <rect x="31" y="59.5" width="22" height="4.5" rx="2" fill="#7c2d12"/>
          <path d="M31 66 h22 q0 5 -11 5 q-11 0 -11 -5z" fill="#f59e0b"/>
        </g>
        <path d="M22 116 q0 -30 40 -31 h34 q8 0 12 8 l9 23 h30 l12 -40 h12 l-11 46 q-3 10 -14 10 h-110 q-14 0 -14 -16z" fill="#ef4444"/>
        <path d="M30 112 q4 -16 28 -18" stroke="#fca5a5" stroke-width="3" fill="none" stroke-linecap="round" opacity="0.8"/>
        <path d="M144 66 h13 l15 52 h-14z" fill="#dc2626"/>
        <path d="M58 86 q22 -9 50 -2 l-2 7 h-46z" fill="#111827"/>
        <path d="M138 62 l20 -5" stroke="#111827" stroke-width="5" stroke-linecap="round"/>
        <circle cx="163" cy="70" r="5" fill="#fde047"/>
        <path class="beam" d="M168 66 l30 -8 v24z" fill="rgba(253, 224, 71, 0.35)"/>
        <path d="M80 84 l32 0 l10 24" stroke="#1e40af" stroke-width="11" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M118 110 h12" stroke="#f8fafc" stroke-width="6" stroke-linecap="round"/>
        <path d="M70 88 q-6 -30 14 -46 q14 -6 20 6 l-6 40z" fill="#ef4444"/>
        <path d="M74 60 q8 -4 22 -2" stroke="#b91c1c" stroke-width="2" fill="none"/>
        <path d="M94 52 q22 2 44 9" stroke="#bfdbfe" stroke-width="9" fill="none" stroke-linecap="round"/>
        <circle cx="140" cy="61" r="4.4" fill="#e0ac69"/>
        <ellipse cx="108" cy="36" rx="6" ry="7" fill="#e0ac69"/>
        <circle cx="97" cy="28" r="16" fill="#ef4444"/>
        <path d="M86 20 a14 14 0 0 1 20 -6" stroke="#fecaca" stroke-width="3" fill="none" stroke-linecap="round"/>
        <path d="M100 22 h12 a5 5 0 0 1 0 10 h-11z" fill="#1e293b"/><path d="M103 25 h7" stroke="#7dd3fc" stroke-width="1.6" stroke-linecap="round"/>
      </g>
      ${wheel(46)}${wheel(158)}
    </svg>`;
}

// The big phone on the right: a yellow map with streets, the route, both pins and the rider's dot.
function phoneHtml() {
  return `<div class="dl-phone" aria-hidden="true">
      <div class="dl-screen">
        <svg viewBox="0 0 100 180" preserveAspectRatio="none">
          <path d="M18 157 V108 H62 V63 H82 V27" fill="none" stroke="#dc2626" stroke-width="3" stroke-dasharray="5 4"/>
          <path class="dl-done" d="M18 157 V108 H62 V63 H82 V27" fill="none" stroke="#2563eb" stroke-width="4" pathLength="100"/>
        </svg>
        <i class="dl-pin dl-pin-a"></i><i class="dl-pin dl-pin-b"></i><i class="dl-dot"></i>
        <div class="dl-delivered">Delivered ✓</div>
      </div>
    </div>`;
}

export function journeyHtml() {
  const picks = journeyTickets();
  if (!picks.length) return "";
  const chips = picks.map(({ t }, n) => `<button type="button" class="jr-chip" data-n="${n}">${escapeHtml(LANG[t.language] || t.language)} ${escapeHtml(pretty(t.category))}</button>`).join("");
  const steps = STEPS.map((s, n) => `<button type="button" class="jr-step" data-step="${n}">
      <svg viewBox="0 0 24 24" aria-hidden="true">${s.icon}</svg><span>${s.label}</span></button>`).join("");
  return `<section class="card tale-card" id="ov-journey">
      <div class="card-head"><div><h2 class="card-title">Follow one ticket</h2>
        <p class="card-sub">A real ticket from the test days, step by step: what OpsLens sees and what it does. Click a step, or pick another ticket.</p></div>
        <div class="jr-chips">${chips}</div></div>
      <div class="jr-road" aria-hidden="true">
        <i class="dl-cloud c1"></i><i class="dl-cloud c2"></i><i class="dl-cloud c3"></i>
        <div class="jr-city"></div>
        <svg class="dl-route" viewBox="0 0 1000 220" preserveAspectRatio="none">
          <path d="M60 78 H260 V34 H480 V92 H640" fill="none" stroke="#fff" stroke-width="3" stroke-dasharray="12 9" vector-effect="non-scaling-stroke" opacity="0.8"/>
          <path class="dl-done" d="M60 78 H260 V34 H480 V92 H640" fill="none" stroke="#22d3ee" stroke-width="4" pathLength="100" vector-effect="non-scaling-stroke"/>
        </svg>
        <i class="dl-pin dl-start"></i><i class="dl-pin dl-end"></i>
        <div class="dl-watch"><i></i></div>
        <div class="jr-lane"></div>
        ${riderSvg()}
        ${phoneHtml()}
        <div class="jr-ontime">On time!</div>
      </div>
      <div class="jr-track"><div class="jr-line"><i></i></div>${steps}</div>
      <div class="jr-panel" id="jr-panel"></div>
    </section>`;
}

// The panel for one step of one ticket. Values are clickable to results.json.
function stepPanel(n, t, i) {
  const at = `risk.at_risk[${i}]`;
  const meter = (value, extra = "") => `<div class="jr-meter ${extra}"><i style="width:${Math.round(value * 100)}%"></i></div>`;
  switch (n) {
    case 0:
      return `<div class="jr-msg">“${escapeHtml(t.text)}”</div>
        <div class="jr-facts">${escapeHtml(t.priority)} ticket · ${ev(`${at}.minutes_to_sla`, "min")} left of its promise</div>`;
    case 1:
      return `<div class="jr-tags"><span>${escapeHtml(pretty(t.category))}</span><span>${escapeHtml(LANG[t.language] || t.language)}</span><span>${escapeHtml(t.priority)}</span></div>
        <div class="jr-facts">Read from the text by the classifier, not from the menu the customer clicked.</div>`;
    case 2:
      return `${meter(t.probability, "is-hot")}
        <div class="jr-facts">Chance it misses its promise: <strong>${ev(`${at}.probability`, "frac_pct")}</strong></div>
        <ul class="jr-why">${(t.reasons || []).slice(0, 2).map((x) => `<li>${escapeHtml(tidyDash(x.text))}</li>`).join("")}</ul>`;
    case 3:
      return `<div class="jr-agent"><span class="jr-avatar"></span><div><strong>OpsLens:</strong> ${escapeHtml(t.action)}</div></div>
        <div class="jr-facts">The optimiser checks every free agent's skills and languages, every few minutes.</div>`;
    default:
      return `${meter(t.probability_after_action, "is-cool")}
        <div class="jr-facts">If served now: <strong>${ev(`${at}.probability`, "frac_pct")}</strong> → <strong>${ev(`${at}.probability_after_action`, "frac_pct")}</strong> chance of a missed promise (the risk model's own estimate).</div>`;
  }
}

function initJourney(section) {
  const box = section.querySelector("#ov-journey");
  if (!box) return;
  const picks = journeyTickets();
  let ticket = 0;
  let step = 0;
  let playing = true;

  const draw = () => {
    const { t, i } = picks[ticket];
    box.style.setProperty("--step", step);
    box.dataset.step = step;
    box.querySelectorAll(".jr-step").forEach((b) => {
      const n = Number(b.dataset.step);
      b.classList.toggle("is-done", n < step);
      b.setAttribute("aria-current", n === step ? "step" : "false");
    });
    box.querySelectorAll(".jr-chip").forEach((c) => c.setAttribute("aria-pressed", Number(c.dataset.n) === ticket ? "true" : "false"));
    const panel = box.querySelector("#jr-panel");
    panel.innerHTML = stepPanel(step, t, i);
    panel.classList.remove("pop");
    void panel.offsetWidth;
    panel.classList.add("pop");
  };
  box.querySelectorAll(".jr-step").forEach((b) => b.addEventListener("click", () => {
    playing = false;
    step = Number(b.dataset.step);
    draw();
  }));
  box.querySelectorAll(".jr-chip").forEach((c) => c.addEventListener("click", () => {
    playing = true;
    ticket = Number(c.dataset.n);
    step = 0;
    draw();
  }));
  draw();
  const timer = setInterval(() => {
    if (!document.body.contains(box)) { clearInterval(timer); return; }
    if (!playing || box.offsetParent === null) return;
    step = (step + 1) % STEPS.length;
    if (step === 0) ticket = (ticket + 1) % picks.length; // the next ticket after each finish
    draw();
  }, STEP_MS);
}

export function initStoryCards(section) {
  initThousand(section);
  initJourney(section);
}
