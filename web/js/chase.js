// chase.js — the "industry wants OpsLens" scene for screens that are empty until you act.
//
// Why (24 Oct, the owner: "in empty pages, industry is happy to have OpsLens and chasing it, and
// throwing the other industry standards in the dustbin"): an empty panel is the moment the
// audience waits, so it gets a little story instead of a blank box. A happy manager throws the
// old ways of working (the baselines' names: First come, first served; Urgent first; Industry
// standard) into a dustbin, one after another, while three happy managers run after the OpsLens
// badge with hearts popping. It carries no numbers and makes no claim; it is a cartoon. Pure
// HTML/SVG + CSS (web/neon.css, "Chase").
//
// Example: What-if before the first run → the scene, then "No simulation yet" under it.

// The old ways thrown away: the same names the baselines carry everywhere else on the dashboard.
const OLD_WAYS = ["First come, first served", "Urgent first", "Industry standard"];

// One cartoon manager (40×72). Legs and arms swing from the hip and shoulders when running.
function person(cls, { suit, skin, hair, tie, bun = false }) {
  return `<svg class="ind ${cls}" viewBox="0 0 40 72" width="40" height="72" aria-hidden="true">
      <g class="leg leg-b"><path d="M22 44 l2 22" stroke="#1e293b" stroke-width="5" stroke-linecap="round"/></g>
      <g class="leg leg-a"><path d="M18 44 l-2 22" stroke="#334155" stroke-width="5" stroke-linecap="round"/></g>
      <g class="arm arm-b"><path d="M25 26 l4 14" stroke="${suit}" stroke-width="4.5" stroke-linecap="round"/></g>
      <rect x="12" y="22" width="16" height="24" rx="5" fill="${suit}"/>
      <path d="M20 23 l-2.6 3 l2.6 12 l2.6 -12z" fill="${tie}"/>
      <g class="arm arm-a"><path d="M15 26 l-4 14" stroke="${suit}" stroke-width="4.5" stroke-linecap="round"/>
        <circle cx="11" cy="40" r="2.6" fill="${skin}"/></g>
      ${bun ? `<circle cx="20" cy="3" r="4" fill="${hair}"/>` : ""}
      <circle cx="20" cy="13" r="9" fill="${skin}"/>
      <path d="M11 12 q1 -10 9 -10 q8 0 9 10 q-4 -5 -9 -5 q-5 0 -9 5z" fill="${hair}"/>
      <path d="M15 13 q2 -2.4 4 0 M21 13 q2 -2.4 4 0" stroke="#1e293b" stroke-width="1.5" fill="none" stroke-linecap="round"/>
      <path d="M16 16.5 q4 4.5 8 0z" fill="#fff" stroke="#1e293b" stroke-width="1.2" stroke-linejoin="round"/>
      <circle cx="13.5" cy="16" r="1.6" fill="#ff4d8d" opacity="0.5"/><circle cx="26.5" cy="16" r="1.6" fill="#ff4d8d" opacity="0.5"/>
    </svg>`;
}

const LENS = `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
    <circle cx="10" cy="10" r="6.5" fill="none" stroke="#22d3ee" stroke-width="2.6"/>
    <path d="M15 15l5 5" stroke="#a78bfa" stroke-width="3" stroke-linecap="round"/>
    <path d="M6.5 10.5h2l1-2.5 1.6 4.5 1-2h1.4" fill="none" stroke="#fff" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

export function chaseHtml() {
  const cards = OLD_WAYS.map((name, i) =>
    `<span class="ch-fly f${i + 1}"><span class="ch-card">${name}</span></span>`).join("");
  return `<div class="chase" aria-hidden="true">
      <div class="ch-old">
        <div class="ch-bin"><b>old ways</b></div>
        ${cards}
        <div class="ch-thrower">${person("thrower", { suit: "#475569", skin: "#f1c27d", hair: "#3b2a20", tie: "#ff4d8d" })}</div>
      </div>
      <div class="ch-run">
        <div class="ch-say"><span>Hamein OpsLens chahiye!</span><span>We want OpsLens!</span></div>
        <div class="ch-crowd">
          ${person("runner r1", { suit: "#6d28d9", skin: "#e0ac69", hair: "#1f2937", tie: "#fbbf24", bun: true })}
          ${person("runner r2", { suit: "#0e7490", skin: "#f6c39a", hair: "#78350f", tie: "#fde047" })}
          ${person("runner r3", { suit: "#be185d", skin: "#c68642", hair: "#111827", tie: "#22d3ee" })}
          <i class="heart h1">♥</i><i class="heart h2">♥</i><i class="heart h3">♥</i>
        </div>
        <div class="ch-badge"><span class="ch-speed"></span>${LENS}<b>OpsLens</b></div>
        <div class="ch-ground"></div>
      </div>
    </div>`;
}
