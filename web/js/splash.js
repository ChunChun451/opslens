// splash.js — the opening screen, the way shopping apps open on a festival: a night sky, a
// monument lighting up, a big line, a countdown, then the app.
//
// Why (24 Oct, the owner: "whenever the app starts it shows something, like Myntra shows 'sale
// ends tomorrow, big fashion festival' with a monument animation, and then the UI opens"): the
// first three seconds set the mood. The brand line is the OpsLens mark, "by SoyaChaap". The splash follows the season of js/season.js (Diwali:
// fireworks over India Gate while a row of diyas lights up one by one) and counts down to the
// Deviathon finale (29 Oct 2026, GLA University) from this laptop's clock. It carries no result
// numbers. It shows once per browser session; any click or key skips it; reduced-motion users see it still, briefly. The cold open
// (js/intro.js) plays after it.
//
// Example on 24 Oct 2026: "Festive season · The festive rush is here · Grand finale in 5 days".

import { currentSeason } from "./season.js";
import { logoSvg, TEAM } from "./logo.js";
import { escapeHtml } from "./format.js";

const SHOW_MS = 3600;
const SEEN_KEY = "opslens.splashSeen";
const FINALE = new Date(2026, 9, 29, 9, 0); // 29 Oct 2026, 09:00 (local time)
const FINALE_END = new Date(2026, 9, 31, 23, 59);

const COPY = {
  diwali: { kicker: "Festive season", big: "The festive rush is here", sub: "Orders spike. Promises shouldn't break.", sky: "fireworks" },
  newyear: { kicker: "New Year", big: "Midnight orders incoming", sub: "Start the year with every promise kept.", sky: "fireworks" },
  tricolour: { kicker: "Celebrating India", big: "A nation orders dinner", sub: "Every ticket is a promise.", sky: "fireworks" },
  cricket: { kicker: "Match night", big: "Every over, a flood of orders", sub: "Keep every promise till the last ball.", sky: "confetti" },
  football: { kicker: "World Cup", big: "Kick-off means order rush", sub: "No ticket left offside.", sky: "confetti" },
  holi: { kicker: "Holi", big: "Colours outside, rush inside", sub: "Every ticket is a promise.", sky: "colours" },
  christmas: { kicker: "Winter rush", big: "The year-end rush is here", sub: "Every ticket is a promise.", sky: "snow" },
  classic: { kicker: "OpsLens", big: "Every ticket is a promise", sub: "Let's keep them all.", sky: "confetti" },
};

// "Grand finale in 5 days", "starts tomorrow", "live now", or nothing after it.
function countdown(now = new Date()) {
  if (now > FINALE_END) return "";
  if (now >= FINALE) return "Live at the Deviathon 2.0 grand finale";
  const days = Math.ceil((FINALE - now) / 86400000);
  if (days <= 1) return "Deviathon 2.0 grand finale starts tomorrow";
  return `Deviathon 2.0 grand finale in ${days} days`;
}

// India Gate in silhouette, with diyas along its base that light up one by one.
function monument() {
  const diyas = Array.from({ length: 9 }, (_, i) => {
    const x = 22 + i * 19.5;
    return `<g class="diya" style="--i:${i}"><path d="M${x - 6} 141 q6 7 12 0z" fill="#f97316"/>
      <path class="fl" d="M${x} 140 q-3 -4 0 -9 q3 5 0 9z" fill="#fde047"/></g>`;
  }).join("");
  return `<svg class="sp-gate" viewBox="0 0 200 150" aria-hidden="true">
      <path d="M90 18 q10 -12 20 0z M62 26 h76 v-8 h-76z" fill="#1e1b4b"/>
      <path fill-rule="evenodd" fill="#1e1b4b" d="M44 136 h112 v-6 h-8 V40 h6 v-10 h-6 v-4 H52 v4 h-6 v10 h6 v90 h-8z M80 130 V80 a20 20 0 0 1 40 0 v50z"/>
      <path d="M52 40 h96" stroke="#fbbf24" stroke-width="1" opacity="0.6"/>
      <path class="gate-glow" d="M80 130 V80 a20 20 0 0 1 40 0 v50" fill="none" stroke="#fbbf24" stroke-width="1.6"/>
      <rect x="10" y="136" width="180" height="5" rx="2" fill="#312e81"/>
      ${diyas}
    </svg>`;
}

function skyHtml(kind) {
  if (kind === "fireworks") return Array.from({ length: 6 }, (_, i) => `<i class="fw f${i + 1}"></i>`).join("");
  if (kind === "snow") return Array.from({ length: 24 }, (_, i) => `<i class="sn" style="--x:${(i * 41) % 100};--d:${(i % 6) * 0.4}"></i>`).join("");
  if (kind === "colours") return Array.from({ length: 8 }, (_, i) => `<i class="puff" style="--x:${(i * 13 + 6) % 100};--d:${i * 0.3}"></i>`).join("");
  return Array.from({ length: 26 }, (_, i) => `<i class="cf" style="--x:${(i * 37) % 100};--d:${(i % 7) * 0.3}"></i>`).join("");
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
  el.className = `splash sky-${copy.sky}`;
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", "OpsLens is opening");
  const count = countdown();
  el.innerHTML = `
    <div class="sp-sky" aria-hidden="true">${skyHtml(copy.sky)}</div>
    <div class="sp-top">
      <div class="sp-kicker">${escapeHtml(copy.kicker)}</div>
      <div class="sp-big">${escapeHtml(copy.big)}</div>
      <div class="sp-sub">${escapeHtml(copy.sub)}</div>
      ${count ? `<div class="sp-count"><span class="sp-dot"></span>${escapeHtml(count)}</div>` : ""}
    </div>
    ${monument()}
    <div class="sp-brand">${logoSvg("lg-splash", 72, "sp-logo lg")}
      <div><b>OpsLens</b><span class="sp-by">by ${TEAM}</span></div></div>
    <div class="sp-bar"><i></i></div>
    <div class="sp-skip">Tap anywhere to skip</div>`;
  document.body.appendChild(el);

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    el.classList.add("is-leaving");
    window.removeEventListener("keydown", close);
    setTimeout(() => { el.remove(); if (done) done(); }, 550);
  };
  el.addEventListener("click", close);
  window.addEventListener("keydown", close);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  setTimeout(close, reduced ? 1600 : SHOW_MS);
}
