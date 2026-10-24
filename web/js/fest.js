// fest.js — the festival layer: a rotating "celebrity" banner on the Overview, and a gift button
// that opens coupons, a membership card and a spin wheel.
//
// Why (24 Oct, the owner: "like Myntra: the UI opens with continuously changing products with
// different celebrities, you can apply coupons, add a membership and spin a wheel for rewards"):
// shopping apps teach people their features by making them a game. Here every "product" is a
// feature of OpsLens, every "celebrity" is one of our cartoon characters, every coupon and every
// prize of the wheel takes you to a feature (story mode, the ledger, a what-if, ...), and the
// membership lists the promises behind the numbers. Nothing here shows a result number, and
// nothing costs anything. The countdown to the finale comes from js/splash.js's calendar logic.
//
// Example: spin the wheel → it lands on "Run a what-if" → "Claim" opens Proof → Try a what-if.

import { mascotHtml } from "./mascot.js";
import { characterHtml } from "./characters.js";
import { setSeason } from "./season.js";
import { escapeHtml } from "./format.js";

const SLIDE_MS = 4200;
const MEMBER_KEY = "opslens.member";

// Each "celebrity" endorses one feature; the button goes there.
const SLIDES = [
  { who: () => mascotHtml("fb-lenny", "happy"), name: "Lenny", say: "Watch today's floor live, at 180× speed.", cta: "Open Live now", go: "overview/live",
    bg: "linear-gradient(120deg, #6d28d9, #db2777)" },
  { who: () => characterHtml("fb-box", "box"), name: "Dabba", say: "Follow one ticket from \"paisa kat gaya\" to delivered.", cta: "Follow a ticket", go: "overview/overview", scroll: "ov-journey",
    bg: "linear-gradient(120deg, #be123c, #f97316)" },
  { who: () => characterHtml("fb-gears", "gears"), name: "Gears", say: "Plant a problem. Watch OpsLens find it.", cta: "Find problems", go: "problems",
    bg: "linear-gradient(120deg, #0e7490, #6d28d9)" },
  { who: () => characterHtml("fb-hourglass", "hourglass", "worried"), name: "Ghadi", say: "Customers about to miss their promise, and what saves them.", cta: "See who is at risk", go: "risks/atrisk",
    bg: "linear-gradient(120deg, #9f1239, #7c3aed)" },
  { who: () => characterHtml("fb-robot", "robot"), name: "Robo", say: "Your idea, not ours: try a what-if.", cta: "Run a what-if", go: "proof/whatif",
    bg: "linear-gradient(120deg, #1d4ed8, #0d9488)" },
  { who: () => characterHtml("fb-book", "book"), name: "Bahi-khata", say: "The rules we wrote before the runs. Kept or missed.", cta: "Read the rules", go: "proof/ledger",
    bg: "linear-gradient(120deg, #4c1d95, #b45309)" },
];

// The wheel's prizes: places in the app.
const PRIZES = [
  { label: "Plant a problem", go: "problems", color: "#ff4d8d" },
  { label: "Run a what-if", go: "proof/whatif", color: "#7c3aed" },
  { label: "Ask OpsLens", ask: true, color: "#0891b2" },
  { label: "Story mode", story: true, color: "#f59e0b" },
  { label: "Follow a ticket", go: "overview/overview", scroll: "ov-journey", color: "#16a34a" },
  { label: "Rules we wrote", go: "proof/ledger", color: "#2563eb" },
];

const COUPONS = [
  { code: "JURY", what: "A free two-minute guided tour", story: true },
  { code: "BIRYANI", what: "Dosa ordered, biryani delivered? See it live", go: "overview/live" },
  { code: "PROOF", what: "The rules we wrote before the runs", go: "proof/ledger" },
  { code: "DIWALI", what: "Light up the Diwali logo", season: "diwali" },
  { code: "CRICKET", what: "Put the logo in whites for cricket", season: "cricket" },
];

// ---- going places ----------------------------------------------------------------------------

function goTo(target) {
  closeHub();
  if (target.story) { document.getElementById("story-button")?.click(); return; }
  if (target.ask) {
    const input = document.getElementById("ask-input");
    if (input) { input.focus(); input.select(); }
    return;
  }
  if (target.season) { setSeason(target.season); burst(); return; }
  if (target.go) location.hash = "#" + target.go;
  if (target.scroll) setTimeout(() => document.getElementById(target.scroll)?.scrollIntoView({ behavior: "smooth", block: "start" }), 400);
}

// A burst of confetti from the middle of the screen (decoration).
function burst() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const layer = document.createElement("div");
  layer.className = "fest-burst";
  const colours = ["#ff4d8d", "#22d3ee", "#fde047", "#a78bfa", "#22c55e", "#f97316"];
  layer.innerHTML = Array.from({ length: 40 }, (_, i) => {
    const angle = (i / 40) * Math.PI * 2;
    const dist = 140 + (i % 5) * 40;
    return `<i style="--x:${Math.round(Math.cos(angle) * dist)}px;--y:${Math.round(Math.sin(angle) * dist)}px;background:${colours[i % colours.length]}"></i>`;
  }).join("");
  document.body.appendChild(layer);
  setTimeout(() => layer.remove(), 1600);
}

// ---- the banner ------------------------------------------------------------------------------

function bannerHtml() {
  const slides = SLIDES.map((s, i) => `<div class="fb-slide${i === 0 ? " is-on" : ""}" style="background:${s.bg}" data-i="${i}">
      <div class="fb-star"><div class="fb-spot"></div>${s.who()}</div>
      <div class="fb-text">
        <span class="fb-sticker">Festive Ops Fest</span>
        <p class="fb-say">“${escapeHtml(s.say)}”</p>
        <span class="fb-by">${escapeHtml(s.name)} recommends</span>
      </div>
      <button type="button" class="fb-cta" data-i="${i}">${escapeHtml(s.cta)}</button>
    </div>`).join("");
  const dots = SLIDES.map((_, i) => `<button type="button" class="fb-dot${i === 0 ? " is-on" : ""}" data-i="${i}" aria-label="Show offer ${i + 1}"></button>`).join("");
  return `<div class="fest-banner" aria-label="Festive offers">${slides}<div class="fb-dots">${dots}</div></div>`;
}

let slide = 0;
let paused = false;

function showSlide(i) {
  slide = (i + SLIDES.length) % SLIDES.length;
  document.querySelectorAll(".fest-banner .fb-slide").forEach((s) => s.classList.toggle("is-on", Number(s.dataset.i) === slide));
  document.querySelectorAll(".fest-banner .fb-dot").forEach((d) => d.classList.toggle("is-on", Number(d.dataset.i) === slide));
}

function ensureBanner() {
  const section = document.getElementById("tab-overview");
  if (!section || section.hidden || section.querySelector(".fest-banner")) return;
  section.insertAdjacentHTML("afterbegin", bannerHtml());
  const banner = section.querySelector(".fest-banner");
  slide = 0;
  banner.addEventListener("mouseenter", () => { paused = true; });
  banner.addEventListener("mouseleave", () => { paused = false; });
  banner.addEventListener("click", (event) => {
    const dot = event.target.closest(".fb-dot");
    if (dot) { showSlide(Number(dot.dataset.i)); return; }
    const cta = event.target.closest(".fb-cta");
    if (cta) goTo(SLIDES[Number(cta.dataset.i)]);
  });
}

// ---- the hub: spin wheel, coupons, membership ------------------------------------------------

function wheelSvg() {
  const r = 110;
  const segs = PRIZES.map((p, i) => {
    const a0 = ((i * 60 - 90) * Math.PI) / 180;
    const a1 = (((i + 1) * 60 - 90) * Math.PI) / 180;
    const x0 = 120 + r * Math.cos(a0), y0 = 120 + r * Math.sin(a0);
    const x1 = 120 + r * Math.cos(a1), y1 = 120 + r * Math.sin(a1);
    const mid = i * 60 + 30;
    return `<path d="M120 120 L${x0.toFixed(1)} ${y0.toFixed(1)} A${r} ${r} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)} Z" fill="${p.color}"/>
      <text transform="rotate(${mid} 120 120)" x="120" y="48" text-anchor="middle" font-size="9.5" font-weight="800" fill="#fff">${escapeHtml(p.label)}</text>`;
  }).join("");
  const bulbs = Array.from({ length: 18 }, (_, i) => {
    const a = (i * 20 * Math.PI) / 180;
    return `<circle class="bulb" style="--i:${i}" cx="${(120 + 116 * Math.cos(a)).toFixed(1)}" cy="${(120 + 116 * Math.sin(a)).toFixed(1)}" r="3" fill="#fde047"/>`;
  }).join("");
  return `<div class="fw-wrap">
      <svg class="fw-wheel" viewBox="0 0 240 240"><circle cx="120" cy="120" r="119" fill="#1e1b4b"/>${segs}
        <circle cx="120" cy="120" r="20" fill="#0d1428" stroke="#fde047" stroke-width="3"/></svg>
      <svg class="fw-bulbs" viewBox="0 0 240 240">${bulbs}</svg>
      <div class="fw-pointer"></div>
      <button type="button" class="fw-spin" id="fw-spin">Spin</button>
    </div>
    <div class="fw-result" id="fw-result" hidden></div>`;
}

function hubHtml() {
  let member = false;
  try { member = localStorage.getItem(MEMBER_KEY) === "1"; } catch { /* ignore */ }
  const coupons = COUPONS.map((c, i) => `<div class="cp">
      <div class="cp-code">${c.code}</div><div class="cp-what">${escapeHtml(c.what)}</div>
      <button type="button" class="cp-apply" data-i="${i}">Apply</button></div>`).join("");
  return `<div class="fest-hub" id="fest-hub" role="dialog" aria-label="Festive Ops Fest" hidden>
      <div class="fh-head"><div><b>Festive Ops Fest</b><span>Spin, apply a coupon, join the club</span></div>
        <button type="button" class="fh-close" id="fh-close" aria-label="Close">✕</button></div>
      <section class="fh-sec"><h3>Spin and win a tour</h3>${wheelSvg()}</section>
      <section class="fh-sec"><h3>Coupons</h3>
        <form class="cp-form" id="cp-form"><input id="cp-input" placeholder="Have a code? Try JURY" autocomplete="off"><button type="submit">Apply</button></form>
        <div class="cp-msg" id="cp-msg"></div>
        <div class="cp-list">${coupons}</div></section>
      <section class="fh-sec"><h3>Membership</h3>
        <div class="mb-card${member ? " is-member" : ""}" id="mb-card">
          <div class="mb-front"><b>OpsLens Promise Keeper</b><span>Free for every judge</span>
            <ul><li>Every number clicks through to its evidence</li><li>Tested on days the model never saw</li><li>The AI never writes a number</li></ul>
            <button type="button" class="mb-join" id="mb-join">Join free</button></div>
          <div class="mb-back"><b>Member ✓</b><span>Promise Keeper since today</span><p>Welcome to the club. Every ticket is a promise.</p></div>
        </div></section>
    </div>`;
}

let spun = 0;

function openHub() {
  const hub = document.getElementById("fest-hub");
  hub.hidden = false;
  requestAnimationFrame(() => hub.classList.add("is-open"));
}
function closeHub() {
  const hub = document.getElementById("fest-hub");
  if (!hub || hub.hidden) return;
  hub.classList.remove("is-open");
  setTimeout(() => { hub.hidden = true; }, 300);
}

function spin() {
  const wheel = document.querySelector(".fw-wheel");
  const result = document.getElementById("fw-result");
  const button = document.getElementById("fw-spin");
  const prize = Math.floor(Math.random() * PRIZES.length);
  // Five turns, then stop with the prize's middle under the pointer at the top.
  const target = spun - (spun % 360) + 360 * 5 + (360 - (prize * 60 + 30));
  spun = target;
  button.disabled = true;
  result.hidden = true;
  wheel.style.transform = `rotate(${target}deg)`;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  setTimeout(() => {
    button.disabled = false;
    result.hidden = false;
    result.innerHTML = `<span>You won: <b>${escapeHtml(PRIZES[prize].label)}</b></span><button type="button" class="fw-claim">Claim</button>`;
    result.querySelector(".fw-claim").addEventListener("click", () => goTo(PRIZES[prize]));
    burst();
  }, reduced ? 50 : 4300);
}

function applyCoupon(code) {
  const msg = document.getElementById("cp-msg");
  const coupon = COUPONS.find((c) => c.code === code.trim().toUpperCase());
  if (!coupon) {
    msg.className = "cp-msg is-bad";
    msg.textContent = "That code is not valid. Try JURY.";
    return;
  }
  msg.className = "cp-msg is-good";
  msg.textContent = `Coupon ${coupon.code} applied ✓`;
  burst();
  setTimeout(() => goTo(coupon), 900);
}

function initHub() {
  document.body.insertAdjacentHTML("beforeend", `<button type="button" class="fest-fab" id="fest-fab" aria-label="Open Festive Ops Fest: spin, coupons, membership">
      <span class="ff-gift">🎁</span><span class="ff-text">Fest</span><span class="ff-crown" hidden>👑</span></button>${hubHtml()}`);
  const fab = document.getElementById("fest-fab");
  const crown = fab.querySelector(".ff-crown");
  try { crown.hidden = localStorage.getItem(MEMBER_KEY) !== "1"; } catch { /* ignore */ }
  fab.addEventListener("click", openHub);
  document.getElementById("fh-close").addEventListener("click", closeHub);
  document.getElementById("fw-spin").addEventListener("click", spin);
  document.getElementById("cp-form").addEventListener("submit", (event) => {
    event.preventDefault();
    applyCoupon(document.getElementById("cp-input").value);
  });
  document.querySelectorAll(".cp-apply").forEach((b) => b.addEventListener("click", () => applyCoupon(COUPONS[Number(b.dataset.i)].code)));
  document.getElementById("mb-join").addEventListener("click", () => {
    document.getElementById("mb-card").classList.add("is-member");
    try { localStorage.setItem(MEMBER_KEY, "1"); } catch { /* ignore */ }
    crown.hidden = false;
    burst();
  });
  window.addEventListener("keydown", (event) => { if (event.key === "Escape") closeHub(); });
}

export function initFest() {
  initHub();
  document.addEventListener("tab-shown", ensureBanner);
  ensureBanner();
  setInterval(() => {
    const banner = document.querySelector(".fest-banner");
    if (!banner || paused || banner.offsetParent === null) return;
    showSlide(slide + 1);
  }, SLIDE_MS);
}
