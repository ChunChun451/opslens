// splash.js — the opening screen: support tickets float in from every side and stream into the
// OpsLens lens, the name rises, four plain lines say what it does, then we enter through the lens.
//
// Why (24 Oct, the owner: "whenever the app starts it shows something"; then: India Gate felt too
// Diwali, the dark battle stage was not liked at all: "try something different"): a clean, bright
// product reveal in 3D, after the owner's references (floating glass cards, a pink-to-blue palette
// #FF0A6C → #2D27FF). The picture is the product in one sentence: every ticket goes through the
// lens. The cards are decoration (category names only, no numbers); the countdown to the Deviathon
// 2.0 finale (29 Oct 2026) ticks from this laptop's clock. Once per browser session; any click or
// key skips it; reduced motion: still, briefly. On exit the screen zooms into the lens and the
// dashboard appears. The cold open (js/intro.js) plays after it.
//
// Example on 24 Oct 2026: "Deviathon 2.0 grand finale in 04 d 11 h 58 m" above the lens,
// "OpsLens by SoyaChaap · Every ticket is a promise." below it.

import { logoSvg, TEAM } from "./logo.js";
import { escapeHtml } from "./format.js";

const SHOW_MS = 4400;
const SEEN_KEY = "opslens.splashSeen";
const FINALE = new Date(2026, 9, 29, 9, 0); // 29 Oct 2026, 09:00 (local time)
const FINALE_END = new Date(2026, 9, 31, 23, 59);

// Decorative tickets: a category and a language or channel; the colour runs pink → blue.
const TICKETS = [
  ["Refund", "Hindi"], ["Late delivery", "Chat"], ["Wrong item", "Hinglish"], ["Payment failed", "UPI"],
  ["Missing item", "Call"], ["App bug", "English"], ["Account", "Email"], ["Restaurant issue", "Chat"],
  ["Refund", "Gold customer"], ["Late delivery", "Hindi"], ["Wrong item", "Call"], ["Payment failed", "Hinglish"],
];
const FEATURES = ["Finds the problems", "Predicts who will be late", "Picks the right agent", "Proves it on days it never saw"];

// "Grand finale in …" while it is ahead, "Live at …" during it, nothing after it.
function countdownLabel(now = new Date()) {
  if (now > FINALE_END) return "";
  return now >= FINALE ? "Live at the Deviathon 2.0 grand finale" : "Deviathon 2.0 grand finale in";
}

function remaining(now = new Date()) {
  let s = Math.max(0, Math.floor((FINALE - now) / 1000));
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60); s -= m * 60;
  return [d, h, m, s].map((n) => String(n).padStart(2, "0"));
}

// Each card starts somewhere around the lens (an angle and a depth) and flies into it.
function cardsHtml() {
  return TICKETS.map(([cat, tag], i) => {
    const angle = (i / TICKETS.length) * Math.PI * 2 + 0.3;
    const x = Math.round(Math.cos(angle) * 46); // vw
    const y = Math.round(Math.sin(angle) * 30); // vh
    const t = (i / (TICKETS.length - 1)).toFixed(3);
    return `<div class="tk-card" style="--x:${x}vw;--y:${y}vh;--z:${-120 - (i % 4) * 90}px;--r:${(i % 2 ? 1 : -1) * (18 + (i % 5) * 7)}deg;--d:${(i * 0.31) % 3.1}s;--t:${t}">
        <i class="tk-stripe"></i><b>${escapeHtml(cat)}</b><span>${escapeHtml(tag)}</span><em></em>
      </div>`;
  }).join("");
}

export function initSplash(done) {
  // Once per browser session (a reload in the middle of a demo should not wait again);
  // ?splash=1 in the address shows it anyway.
  let seen = false;
  try { seen = sessionStorage.getItem(SEEN_KEY) === "1"; sessionStorage.setItem(SEEN_KEY, "1"); } catch { /* show it */ }
  if (seen && !new URLSearchParams(location.search).has("splash")) { if (done) done(); return; }

  const el = document.createElement("div");
  el.className = "splash";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", "OpsLens is opening");
  const label = countdownLabel();
  const before = new Date() < FINALE;
  const units = ["d", "h", "m", "s"];
  const word = "OpsLens".split("").map((ch, i) => `<span style="--i:${i}">${ch}</span>`).join("");
  el.innerHTML = `
    <div class="sp-bg" aria-hidden="true"><i class="blob b1"></i><i class="blob b2"></i><i class="blob b3"></i><i class="sp-grid"></i></div>
    ${label ? `<div class="sp-pill"><span class="sp-live"></span>${escapeHtml(label)}
      ${before ? units.map((u, i) => `<b data-t="${i}">00</b><small>${u}</small>`).join("") : ""}</div>` : ""}
    <div class="sp-stage" aria-hidden="true">
      <div class="sp-cards">${cardsHtml()}</div>
      <div class="sp-core">
        <i class="sp-scan"></i><i class="sp-halo"></i>
        ${logoSvg("lg-splash-core", 150, "sp-lens lg")}
      </div>
    </div>
    <div class="sp-word">${word}</div>
    <div class="sp-by-line"><span class="sp-by">by ${TEAM}</span></div>
    <div class="sp-tag">Every ticket is a promise.</div>
    <div class="sp-features">${FEATURES.map((f, i) => `<span style="--i:${i}">${escapeHtml(f)}</span>`).join("")}</div>
    <div class="sp-bar"><i></i></div>
    <div class="sp-skip">Tap anywhere to skip</div>`;
  document.body.appendChild(el);

  const tick = () => remaining().forEach((v, i) => {
    const cell = el.querySelector(`.sp-pill b[data-t="${i}"]`);
    if (cell) cell.textContent = v;
  });
  tick();
  const clock = setInterval(tick, 1000);

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    clearInterval(clock);
    el.classList.add("is-leaving"); // zoom into the lens
    window.removeEventListener("keydown", close);
    setTimeout(() => { el.remove(); if (done) done(); }, 700);
  };
  el.addEventListener("click", close);
  window.addEventListener("keydown", close);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  setTimeout(close, reduced ? 1600 : SHOW_MS);
}
