// splash.js — the opening screen: a dark battle-ready stage, our emblem glowing, a big line, a live
// countdown to the finale, then the app.
//
// Why (24 Oct, the owner: "whenever the app starts it shows something, like shopping apps on a
// festival"; then: "India Gate and the diyas feel more Diwali than professional; take the look of
// the Deviathon site, the skull and all, with a 3D touch"): the first seconds set the mood. The
// stage now follows the Deviathon 2.0 look (charcoal, smoke, rising embers, a red glow, carved
// serif letters) without copying its emblem: in the middle is our own mark (OPS inside the lens,
// with eyes) inside two turning red rings, over a twisting 3D ribbon of cards. A faint skull
// watermark breathes in the dark. The words follow the season (js/season.js) and the countdown to
// the Deviathon finale (29 Oct 2026, GLA University) ticks from this laptop's clock. No result
// numbers. Once per browser session; any click or key skips it; reduced motion: still, briefly.
// The cold open (js/intro.js) plays after it.
//
// Example on 24 Oct 2026: "Festive season · The festive rush is here · Deviathon 2.0 grand finale
// in 5 days" with tiles 04 days 11 hours 58 mins 06 secs.

import { currentSeason } from "./season.js";
import { logoSvg, TEAM } from "./logo.js";
import { escapeHtml } from "./format.js";

const SHOW_MS = 4200;
const SEEN_KEY = "opslens.splashSeen";
const FINALE = new Date(2026, 9, 29, 9, 0); // 29 Oct 2026, 09:00 (local time)
const FINALE_END = new Date(2026, 9, 31, 23, 59);
const RIBBON_CARDS = 30;
const EMBERS = 34;

const COPY = {
  diwali: { kicker: "Festive season", big: "The festive rush is here", sub: "Orders spike. Promises shouldn't break." },
  newyear: { kicker: "New Year", big: "Midnight orders incoming", sub: "Start the year with every promise kept." },
  tricolour: { kicker: "Celebrating India", big: "A nation orders dinner", sub: "Every ticket is a promise." },
  cricket: { kicker: "Match night", big: "Every over, a flood of orders", sub: "Keep every promise till the last ball." },
  football: { kicker: "World Cup", big: "Kick-off means order rush", sub: "No ticket left offside." },
  holi: { kicker: "Holi", big: "Colours outside, rush inside", sub: "Every ticket is a promise." },
  christmas: { kicker: "Winter rush", big: "The year-end rush is here", sub: "Every ticket is a promise." },
  classic: { kicker: "OpsLens", big: "Every ticket is a promise", sub: "Let's keep them all." },
};
const MARQUEE = ["Code", "Conquer", "Ascend", "Deviathon 2.0", "GLA University, Mathura", "29–31 Oct 2026", "Every ticket is a promise"];

// "Grand finale in 5 days", "starts tomorrow", "live now", or nothing after it.
function countdown(now = new Date()) {
  if (now > FINALE_END) return "";
  if (now >= FINALE) return "Live at the Deviathon 2.0 grand finale";
  const days = Math.ceil((FINALE - now) / 86400000);
  if (days <= 1) return "Deviathon 2.0 grand finale starts tomorrow";
  return `Deviathon 2.0 grand finale in ${days} days`;
}

// Days, hours, minutes, seconds to the finale (all zero once it has started).
function remaining(now = new Date()) {
  let s = Math.max(0, Math.floor((FINALE - now) / 1000));
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60); s -= m * 60;
  return [d, h, m, s].map((n) => String(n).padStart(2, "0"));
}

// Our emblem: the OpsLens mark in a white disc, a red glow ring, two dashed rings turning apart.
function emblem() {
  return `<div class="sp-emblem" aria-hidden="true">
      <svg class="sp-rings" viewBox="0 0 200 200">
        <g class="ring r1"><circle cx="100" cy="100" r="94" fill="none" stroke="#ff3b30" stroke-width="2.2" stroke-dasharray="34 12 6 12" stroke-linecap="round"/></g>
        <g class="ring r2"><circle cx="100" cy="100" r="80" fill="none" stroke="#ff6b5e" stroke-width="1.4" stroke-dasharray="3 9" stroke-linecap="round"/></g>
        <circle class="glow" cx="100" cy="100" r="66" fill="none" stroke="#ff2d2d" stroke-width="7"/>
        <circle cx="100" cy="100" r="58" fill="#fff7f5"/>
      </svg>
      <div class="sp-mark">${logoSvg("lg-splash-em", 96, "lg")}</div>
    </div>`;
}

// A twisting 3D ribbon of cards (pink-red #FF0A6C to blue #2D27FF), each turning a little later.
function ribbon() {
  const cards = Array.from({ length: RIBBON_CARDS }, (_, i) => `<i style="--i:${i};--t:${(i / (RIBBON_CARDS - 1)).toFixed(3)}"></i>`).join("");
  return `<div class="sp-ribbon" aria-hidden="true"><div class="rb-track">${cards}</div></div>`;
}

// A faint skull, drawn in thin red lines, breathing behind everything.
function skull() {
  return `<svg class="sp-skull" viewBox="0 0 200 220" aria-hidden="true">
      <path d="M100 12 C52 12 22 46 22 92 c0 28 12 46 28 58 v26 c0 8 6 12 14 12 h72 c8 0 14-4 14-12 v-26 c16-12 28-30 28-58 C178 46 148 12 100 12z"
        fill="none" stroke="currentColor" stroke-width="3"/>
      <path d="M58 96 c0-16 12-26 26-24 c10 2 14 12 12 24 c-2 12-12 18-22 18 c-10 0-16-8-16-18z M142 96 c0-16-12-26-26-24 c-10 2-14 12-12 24
        c2 12 12 18 22 18 c10 0 16-8 16-18z" fill="currentColor" opacity="0.55"/>
      <path d="M100 118 l-10 22 h20z" fill="currentColor" opacity="0.6"/>
      <path d="M68 166 v22 M84 168 v24 M100 168 v24 M116 168 v24 M132 166 v22" stroke="currentColor" stroke-width="3"/>
      <path d="M70 40 q30-14 60 0 M40 78 q-6 18 0 34 M160 78 q6 18 0 34" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.6"/>
    </svg>`;
}

export function initSplash(done) {
  // Once per browser session (a reload in the middle of a demo should not wait again);
  // ?splash=1 in the address shows it anyway.
  let seen = false;
  try { seen = sessionStorage.getItem(SEEN_KEY) === "1"; sessionStorage.setItem(SEEN_KEY, "1"); } catch { /* show it */ }
  if (seen && !new URLSearchParams(location.search).has("splash")) { if (done) done(); return; }
  const season = currentSeason();
  const copy = COPY[season.id] || COPY.classic;
  const el = document.createElement("div");
  el.className = "splash";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", "OpsLens is opening");
  const count = countdown();
  const embers = Array.from({ length: EMBERS }, (_, i) =>
    `<i style="--x:${(i * 29) % 100};--d:${((i * 7) % 10) * 0.35};--s:${0.6 + ((i * 13) % 10) / 10}"></i>`).join("");
  const marquee = MARQUEE.map((w) => `<span>${escapeHtml(w)}</span><b>✦</b>`).join("");
  const tiles = ["Days", "Hours", "Mins", "Secs"].map((label, i) =>
    `<div class="sp-tile"><b data-t="${i}">00</b><span>${label}</span></div>`).join("");
  el.innerHTML = `
    <div class="sp-bg" aria-hidden="true"><i class="fog f1"></i><i class="fog f2"></i>${skull()}<div class="sp-embers">${embers}</div></div>
    <div class="sp-top">
      <div class="sp-kicker">${escapeHtml(copy.kicker)}</div>
      <div class="sp-big">${escapeHtml(copy.big)}</div>
      <div class="sp-sub">${escapeHtml(copy.sub)}</div>
    </div>
    <div class="sp-stage">${ribbon()}${emblem()}</div>
    ${count ? `<div class="sp-countdown">
      <div class="sp-count"><span class="sp-dot"></span>${escapeHtml(count)}</div>
      ${new Date() < FINALE ? `<div class="sp-tiles">${tiles}</div>` : ""}
    </div>` : ""}
    <div class="sp-marquee" aria-hidden="true"><div class="mq-track">${marquee}${marquee}</div></div>
    <div class="sp-brand">${logoSvg("lg-splash", 72, "sp-logo lg")}
      <div><b>OpsLens</b><span class="sp-by">by ${TEAM}</span></div></div>
    <div class="sp-bar"><i></i></div>
    <div class="sp-skip">Tap anywhere to skip</div>`;
  document.body.appendChild(el);

  const tick = () => remaining().forEach((v, i) => {
    const cell = el.querySelector(`.sp-tile b[data-t="${i}"]`);
    if (cell) cell.textContent = v;
  });
  tick();
  const clock = setInterval(tick, 1000);

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    clearInterval(clock);
    el.classList.add("is-leaving");
    window.removeEventListener("keydown", close);
    setTimeout(() => { el.remove(); if (done) done(); }, 550);
  };
  el.addEventListener("click", close);
  window.addEventListener("keydown", close);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  setTimeout(close, reduced ? 1600 : SHOW_MS);
}
