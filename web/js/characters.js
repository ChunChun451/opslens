function face(cx, cy, ink = "#0d1428") {
  return `<g class="mascot-eyes">
      <ellipse class="mascot-eye" cx="${cx - 6}" cy="${cy}" rx="3" ry="3.8" fill="${ink}"/>
      <ellipse class="mascot-eye" cx="${cx + 6}" cy="${cy}" rx="3" ry="3.8" fill="${ink}"/>
      <circle cx="${cx - 5}" cy="${cy - 1.3}" r="1" fill="#fff"/><circle cx="${cx + 7}" cy="${cy - 1.3}" r="1" fill="#fff"/>
    </g>
    <path class="mascot-closed" d="M${cx - 9} ${cy} q3 2.6 6 0 M${cx + 3} ${cy} q3 2.6 6 0" stroke="${ink}" stroke-width="2" fill="none" stroke-linecap="round"/>
    <path class="mascot-happy" d="M${cx - 9} ${cy + 1} q3 -3.6 6 0 M${cx + 3} ${cy + 1} q3 -3.6 6 0" stroke="${ink}" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <circle cx="${cx - 11}" cy="${cy + 5}" r="2.6" fill="#ff4d8d" opacity="0.5"/><circle cx="${cx + 11}" cy="${cy + 5}" r="2.6" fill="#ff4d8d" opacity="0.5"/>
    <path class="mascot-smile" d="M${cx - 5} ${cy + 6} q5 4.6 10 0" stroke="${ink}" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <path class="mascot-frown" d="M${cx - 5} ${cy + 10} q5 -3.6 10 0" stroke="${ink}" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <g class="mascot-sweat">
      <path class="drop d1" d="M${cx - 15} ${cy - 10} q-3 5 0 7 q3 -2 0 -7z" fill="#7dd3fc"/>
      <path class="drop d2" d="M${cx + 15} ${cy - 12} q-3 5 0 7 q3 -2 0 -7z" fill="#7dd3fc"/>
    </g>`;
}

const BODIES = {
  trophy: () => `
    <g class="arm al"><path d="M17 30 q-9 -5 -8 -17" stroke="#f59e0b" stroke-width="4" fill="none" stroke-linecap="round"/><circle cx="9" cy="12" r="3.6" fill="#fbbf24"/></g>
    <g class="arm ar"><path d="M63 30 q9 -5 8 -17" stroke="#f59e0b" stroke-width="4" fill="none" stroke-linecap="round"/><circle cx="71" cy="12" r="3.6" fill="#fbbf24"/></g>
    <path d="M18 10 h44 v20 a22 22 0 0 1 -44 0z" fill="#fbbf24" stroke="#f59e0b" stroke-width="2"/>
    <rect x="35" y="51" width="10" height="9" fill="#f59e0b"/><rect x="23" y="60" width="34" height="10" rx="2.5" fill="#a78bfa"/>
    <path class="shine" d="M24 15 v12" stroke="#fff" stroke-width="2.6" stroke-linecap="round" opacity="0.8"/>
    <path class="sparkle" d="M68 42 l2 5 l5 2 l-5 2 l-2 5 l-2 -5 l-5 -2 l5 -2z" fill="#fff"/>
    ${face(40, 27)}`,
  gears: () => `
    <g class="g-small"><circle cx="62" cy="17" r="9" fill="none" stroke="#a78bfa" stroke-width="6" stroke-dasharray="4 3.07"/>
      <circle cx="62" cy="17" r="6.5" fill="#a78bfa"/><circle cx="62" cy="17" r="2.4" fill="#0d1428"/></g>
    <g class="g-big"><circle cx="36" cy="44" r="27" fill="none" stroke="#22d3ee" stroke-width="7" stroke-dasharray="6 4.6"/></g>
    <circle cx="36" cy="44" r="22.5" fill="#67e8f9"/>
    ${face(36, 42)}
    <g class="wrench"><path d="M74 74 l-13 -13" stroke="#b45309" stroke-width="4.5" stroke-linecap="round"/>
      <rect x="51" y="53" width="18" height="9" rx="2" transform="rotate(-45 60 57.5)" fill="#94a3b8" stroke="#cbd5e1" stroke-width="1.2"/></g>`,
  hourglass: () => `
    <rect x="16" y="5" width="48" height="7" rx="3" fill="#a78bfa"/><rect x="16" y="68" width="48" height="7" rx="3" fill="#a78bfa"/>
    <path d="M22 12 h36 q0 17 -14 25 v6 q14 8 14 25 h-36 q0 -17 14 -25 v-6 q-14 -8 -14 -25z" fill="rgba(186,230,253,0.18)" stroke="#7dd3fc" stroke-width="2"/>
    <path class="sand-top" d="M26 16 h28 q-2 11 -14 19 q-12 -8 -14 -19z" fill="#fbbf24"/>
    <path class="sand-stream" d="M40 36 v30" stroke="#fbbf24" stroke-width="2.2" stroke-dasharray="3 3"/>
    <path class="sand-bot" d="M24 67 q3 -15 16 -17 q13 2 16 17z" fill="#fbbf24"/>
    ${face(40, 57)}`,
  cloud: () => `
    <g class="sun"><circle cx="58" cy="22" r="11" fill="#fbbf24"/>
      <path d="M58 4v5M58 35v5M40 22h5M71 22h5M45 9l3.5 3.5M67.5 31.5l3.5 3.5M45 35l3.5 -3.5M67.5 12.5l3.5 -3.5" stroke="#fbbf24" stroke-width="2.4" stroke-linecap="round"/></g>
    <path d="M17 58 a12 12 0 0 1 1 -24 a16 16 0 0 1 30 -6 a13 13 0 0 1 15 18 a10 10 0 0 1 -5 12z" fill="#e2e8f0"/>
    ${face(38, 43)}
    <g class="rain"><path class="r1" d="M24 63 l-2 7" stroke="#22d3ee" stroke-width="2.4" stroke-linecap="round"/>
      <path class="r2" d="M38 63 l-2 7" stroke="#22d3ee" stroke-width="2.4" stroke-linecap="round"/>
      <path class="r3" d="M52 63 l-2 7" stroke="#22d3ee" stroke-width="2.4" stroke-linecap="round"/></g>`,
  rocket: () => `
    <g class="flame"><path d="M31 60 q9 20 18 0 q-9 6 -18 0z" fill="#f97316"/><path d="M35 61 q5 11 10 0z" fill="#fde047"/></g>
    <g class="smoke"><circle class="p1" cx="26" cy="72" r="4" fill="#94a3b8"/><circle class="p2" cx="54" cy="72" r="3.5" fill="#94a3b8"/></g>
    <path d="M28 46 l-11 12 v-15 l11 -9z" fill="#ff4d8d"/><path d="M52 46 l11 12 v-15 l-11 -9z" fill="#ff4d8d"/>
    <path d="M40 3 q17 14 15 57 h-30 q-2 -43 15 -57z" fill="#e2e8f0" stroke="#a78bfa" stroke-width="2"/>
    <circle cx="40" cy="31" r="12.5" fill="#7dd3fc" stroke="#a78bfa" stroke-width="2"/>
    ${face(40, 30)}`,
  box: () => `
    <g class="speed"><path d="M1 28 h11 M0 40 h13 M3 52 h9" stroke="#22d3ee" stroke-width="2.6" stroke-linecap="round"/></g>
    <g class="cart"><rect x="17" y="12" width="46" height="42" rx="6" fill="#ff4d8d"/>
      <rect x="17" y="12" width="46" height="9" rx="4" fill="#be185d"/>
      <path d="M33 12 v9 M47 12 v9" stroke="#fda4af" stroke-width="1.6"/>
      ${face(40, 35)}
      <path d="M13 57 h56" stroke="#a78bfa" stroke-width="4" stroke-linecap="round"/></g>
    <g class="wheel"><circle cx="25" cy="66" r="8" fill="#1e293b" stroke="#cbd5e1" stroke-width="3"/><path d="M25 59v14M18 66h14" stroke="#cbd5e1" stroke-width="1.6"/></g>
    <g class="wheel"><circle cx="57" cy="66" r="8" fill="#1e293b" stroke="#cbd5e1" stroke-width="3"/><path d="M57 59v14M50 66h14" stroke="#cbd5e1" stroke-width="1.6"/></g>`,
  robot: () => `
    <path d="M40 6 v9" stroke="#a78bfa" stroke-width="2.6"/><circle class="bulb" cx="40" cy="5" r="4" fill="#ff4d8d"/>
    <circle cx="11" cy="34" r="4.5" fill="#a78bfa"/><circle cx="69" cy="34" r="4.5" fill="#a78bfa"/>
    <rect x="14" y="14" width="52" height="40" rx="10" fill="#cbd5e1" stroke="#a78bfa" stroke-width="2"/>
    <rect x="20" y="20" width="40" height="28" rx="6" fill="#0d1428"/>
    ${face(40, 31, "#22d3ee")}
    <rect x="24" y="56" width="32" height="19" rx="5" fill="#94a3b8"/>
    <g class="knob"><circle cx="40" cy="65.5" r="6" fill="#1e293b"/><path d="M40 65.5 v-5" stroke="#22d3ee" stroke-width="2.4" stroke-linecap="round"/></g>`,
  book: () => `
    <rect x="15" y="8" width="50" height="62" rx="5" fill="#6d28d9"/>
    <rect x="19" y="8" width="46" height="58" rx="4" fill="#a78bfa"/>
    <path d="M61 11 v53" stroke="#fef3c7" stroke-width="3"/>
    <rect x="25" y="14" width="30" height="8" rx="2" fill="#ede9fe"/>
    ${face(40, 38)}
    <g class="ribbon"><path d="M50 66 v10 l3 -3 l3 3 v-10" fill="#ff4d8d"/></g>
    <g class="tick"><circle cx="58" cy="56" r="8" fill="#22c55e"/><path d="M54 56 l3 3 l5 -6" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round"/></g>`,
  flask: () => `
    <path d="M30 5 h20 M33 5 v20 L14 61 a7 7 0 0 0 6 11 h40 a7 7 0 0 0 6 -11 L47 25 V5" fill="rgba(34,211,238,0.12)" stroke="#22d3ee" stroke-width="2.4" stroke-linejoin="round"/>
    <path d="M21 47 h38 l8 14 a6 6 0 0 1 -5 10 H18 a6 6 0 0 1 -5 -10z" fill="#22c55e"/>
    <g class="bubbles"><circle class="bub b1" cx="33" cy="44" r="2.6" fill="#bbf7d0"/>
      <circle class="bub b2" cx="45" cy="42" r="2" fill="#bbf7d0"/><circle class="bub b3" cx="39" cy="38" r="1.6" fill="#bbf7d0"/></g>
    ${face(40, 58)}`,
  folder: () => `
    <path d="M9 22 h22 l5 6 h35 v42 a4 4 0 0 1 -4 4 h-54 a4 4 0 0 1 -4 -4z" fill="#f59e0b"/>
    <g class="paper"><rect x="25" y="2" width="30" height="36" rx="2" fill="#fff" stroke="#22d3ee" stroke-width="1.6"/>
      <path d="M30 12h20M30 18h20M30 24h13" stroke="#94a3b8" stroke-width="2"/></g>
    <path d="M9 36 h62 v34 a4 4 0 0 1 -4 4 h-54 a4 4 0 0 1 -4 -4z" fill="#fcd34d"/>
    ${face(40, 53)}`,
  monitor: () => `
    <path d="M34 54 l-4 12 h20 l-4 -12z" fill="#475569"/><rect x="23" y="66" width="34" height="6" rx="2" fill="#a78bfa"/>
    <rect x="7" y="8" width="66" height="47" rx="6" fill="#1e293b" stroke="#a78bfa" stroke-width="2.4"/>
    <rect x="12" y="13" width="56" height="37" rx="3" fill="#0d1428"/>
    ${face(40, 29, "#22d3ee")}
    <rect class="cursor" x="57" y="42" width="6" height="2.6" fill="#22d3ee"/>
    <g class="alert"><circle cx="69" cy="10" r="7" fill="#ff4d8d"/><path d="M69 6.5 v4 M69 13.5 v.1" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/></g>`,
  scale: () => `
    <path d="M40 16 v51" stroke="#a78bfa" stroke-width="4"/><rect x="23" y="67" width="34" height="7" rx="3" fill="#a78bfa"/>
    <g class="beam"><path d="M9 20 h62" stroke="#cbd5e1" stroke-width="3.5" stroke-linecap="round"/>
      <path d="M14 20 l-7 18 M14 20 l7 18 M66 20 l-7 18 M66 20 l7 18" stroke="#cbd5e1" stroke-width="1.2"/>
      <path d="M5 38 h18 a9 5 0 0 1 -18 0z" fill="#94a3b8"/><path d="M57 38 h18 a9 5 0 0 1 -18 0z" fill="#22d3ee"/></g>
    <circle cx="40" cy="17" r="13" fill="#fde68a"/>
    ${face(40, 16)}`,
};

export function characterHtml(id, kind, mood = "idle") {
  const body = BODIES[kind] || BODIES.trophy;
  return `<div class="mascot chr chr-${kind} is-${mood}" id="${id}" aria-hidden="true">
      <div class="mascot-bubble"></div>
      <svg viewBox="0 0 80 80" width="64" height="64">${body()}</svg>
      <div class="mascot-z"><span>z</span><span>z</span><span>z</span></div>
    </div>`;
}
