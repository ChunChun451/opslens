// splash.js — the opening screen: "chaos in, order out". Thousands of glowing particles (tickets)
// swirl like a galaxy in the dark, then rush together and write "OpsLens" in light; the mouse
// scatters them and they flow back; on exit they burst outward like a jump to warp speed.
//
// Why (24 Oct, the owner: the Diwali stage, the dark battle stage and the bright reveal were all
// not right; "make it dark, something different, fascinating"): the picture is the product in
// one sentence. A flood of tickets is chaos; OpsLens turns it into order. It is drawn on one
// canvas with plain 2D drawing (no library, works offline): the letters' points are sampled from
// the word written on a hidden canvas, and every particle eases to one of them. Colours run pink
// #FF0A6C → violet → blue #2D27FF across the word. No result numbers; the countdown to the Deviathon
// 2.0 finale (29 Oct 2026) ticks from this laptop's clock. Once per browser session; any click or
// key skips it; reduced motion: the word is drawn still, briefly. The cold open plays after it.
//
// Example: a 1366×768 screen → about 2,000 particles; 1.6 s of swirl, 1.5 s to form the word.

import { logoSvg, TEAM } from "./logo.js";
import { escapeHtml } from "./format.js";

const SHOW_MS = 5200;
const SWIRL_MS = 1500; // chaos, before the particles head for the letters
const SEEN_KEY = "opslens.splashSeen";
const FINALE = new Date(2026, 9, 29, 9, 0); // 29 Oct 2026, 09:00 (local time)
const FINALE_END = new Date(2026, 9, 31, 23, 59);
// Refined (25 Oct): white into cyan, no pink-violet-indigo.
const PINK = [244, 244, 242], VIOLET = [134, 232, 248], BLUE = [34, 211, 238];

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

// Pink → violet → blue, for a position 0..1 across the word.
function colourAt(t) {
  const [a, b, u] = t < 0.5 ? [PINK, VIOLET, t * 2] : [VIOLET, BLUE, (t - 0.5) * 2];
  return a.map((c, i) => Math.round(c + (b[i] - c) * u));
}

// Points of the word "OpsLens" written on a hidden canvas, every `gap` pixels.
function wordPoints(w, h, size, centerY) {
  const off = document.createElement("canvas");
  off.width = w; off.height = h;
  const g = off.getContext("2d");
  g.fillStyle = "#fff";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `800 ${size}px Inter, "Segoe UI", system-ui, sans-serif`;
  g.fillText("OpsLens", w / 2, centerY);
  const data = g.getImageData(0, 0, w, h).data;
  const gap = Math.max(3, Math.round(size / 40));
  const points = [];
  let minX = w, maxX = 0;
  for (let y = 0; y < h; y += gap) {
    for (let x = 0; x < w; x += gap) {
      if (data[(y * w + x) * 4 + 3] > 140) {
        points.push([x, y]);
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
      }
    }
  }
  return { points, minX, maxX };
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
  el.innerHTML = `
    <canvas class="sp-canvas" aria-hidden="true"></canvas>
    ${label ? `<div class="sp-pill"><span class="sp-live"></span>${escapeHtml(label)}
      ${before ? ["d", "h", "m", "s"].map((u, i) => `<b data-t="${i}">00</b><small>${u}</small>`).join("") : ""}</div>` : ""}
    <div class="sp-mark">${logoSvg("lg-splash-mark", 64, "lg")}</div>
    <div class="sp-under">
      <span class="sp-by">by ${TEAM}</span>
      <div class="sp-tag">Every ticket is a promise.</div>
    </div>
    <div class="sp-foot"><div class="sp-bar"><i></i></div><div class="sp-skip">Tap anywhere to skip</div></div>`;
  document.body.appendChild(el);

  // ---- the particles ----
  const canvas = el.querySelector(".sp-canvas");
  const ctx = canvas.getContext("2d");
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = window.innerWidth, h = window.innerHeight;
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
  ctx.scale(dpr, dpr);
  const size = Math.round(Math.min(w * 0.17, h * 0.24));
  const centerY = Math.round(h * 0.46);
  const { points, minX, maxX } = wordPoints(w, h, size, centerY);
  // Place the logo above the word and the lines under it.
  el.querySelector(".sp-mark").style.top = `${Math.max(70, centerY - size * 0.62 - 78)}px`;
  el.querySelector(".sp-under").style.top = `${centerY + size * 0.5 + 18}px`;

  const count = Math.min(points.length, Math.round(Math.min(2600, (w * h) / 420)));
  const step = points.length / Math.max(1, count);
  const cx = w / 2, cy = centerY;
  const particles = [];
  for (let i = 0; i < count; i++) {
    const [tx, ty] = points[Math.floor(i * step)];
    const t = (tx - minX) / Math.max(1, maxX - minX);
    const angle = Math.random() * Math.PI * 2;
    const radius = 40 + Math.random() * Math.max(w, h) * 0.55;
    particles.push({ tx, ty, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius * 0.6,
      angle, radius, spin: (0.004 + Math.random() * 0.01) * (Math.random() < 0.85 ? 1 : -1),
      vx: 0, vy: 0, size: 1 + Math.random() * 1.4, col: colourAt(t), phase: Math.random() * Math.PI * 2 });
  }
  // A few dim stars that never join the word.
  const stars = Array.from({ length: Math.round((w * h) / 9000) }, () =>
    ({ x: Math.random() * w, y: Math.random() * h, s: Math.random() * 1.2, tw: Math.random() * Math.PI * 2 }));

  el.particles = particles; // for checks in the browser console (where each particle is vs its letter point)
  const mouse = { x: -9999, y: -9999 };
  el.addEventListener("pointermove", (event) => { mouse.x = event.clientX; mouse.y = event.clientY; });
  el.addEventListener("pointerleave", () => { mouse.x = -9999; mouse.y = -9999; });

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const start = performance.now();
  let burstAt = 0;
  let frame = 0;

  // Time-based motion: `k` is how many 60-fps frames this frame stands for, so a slow laptop or a
  // throttled window still forms the word on time.
  let last = start;
  function draw(now) {
    const t = now - start;
    const k = Math.min(18, Math.max(0.5, (now - last) / 16.7));
    last = now;
    const pull = 1 - Math.pow(1 - 0.12, k); // how far towards the goal, for a frame of this length
    const damp = Math.pow(0.86, k); // how fast a push from the mouse fades
    // Motion trails: paint the dark over the last frame instead of clearing it.
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = burstAt ? "rgba(5, 5, 12, 0.35)" : "rgba(5, 5, 12, 0.28)";
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = "lighter";
    for (const s of stars) {
      const a = 0.25 + 0.25 * Math.sin(t / 700 + s.tw);
      ctx.fillStyle = `rgba(180, 190, 255, ${a})`;
      ctx.fillRect(s.x, s.y, s.s, s.s);
    }
    const forming = reduced ? 1 : Math.min(1, Math.max(0, (t - SWIRL_MS) / 1500));
    for (const p of particles) {
      if (burstAt) {
        // Warp: outward, faster every frame, drawn as a streak.
        const dx = p.x - cx, dy = p.y - cy;
        const d = Math.hypot(dx, dy) || 1;
        p.vx += (dx / d) * 1.6 * k; p.vy += (dy / d) * 1.6 * k;
        const ox = p.x, oy = p.y;
        p.x += p.vx; p.y += p.vy;
        ctx.strokeStyle = `rgba(${p.col[0]}, ${p.col[1]}, ${p.col[2]}, 0.85)`;
        ctx.lineWidth = p.size;
        ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(p.x, p.y); ctx.stroke();
        continue;
      }
      // Swirl: orbit the centre on a flat ellipse, the orbit slowly tightening.
      p.angle += p.spin * (1 - forming * 0.8) * k;
      p.radius *= Math.pow(0.9985, k);
      const sx = cx + Math.cos(p.angle) * p.radius, sy = cy + Math.sin(p.angle) * p.radius * 0.55;
      // Form: ease from the orbit to the letter point; once formed, shimmer in place.
      const ease = forming * forming * (3 - 2 * forming);
      let gx = sx + (p.tx - sx) * ease, gy = sy + (p.ty - sy) * ease;
      if (forming >= 1) { gx += Math.sin(t / 380 + p.phase) * 0.6; gy += Math.cos(t / 420 + p.phase) * 0.6; }
      // The cursor pushes particles away; they spring back.
      const mx = p.x - mouse.x, my = p.y - mouse.y;
      const md = mx * mx + my * my;
      if (md < 9000 && forming > 0.6) { const f = (9000 - md) / 9000 * 6; const d = Math.sqrt(md) || 1; p.vx += (mx / d) * f; p.vy += (my / d) * f; }
      // Ease to the goal (stable at any frame rate); the mouse's push is a velocity that fades.
      p.vx *= damp; p.vy *= damp;
      p.x += (gx - p.x) * pull + p.vx * Math.min(k, 3);
      p.y += (gy - p.y) * pull + p.vy * Math.min(k, 3);
      const glow = forming >= 1 ? 0.75 + 0.25 * Math.sin(t / 300 + p.phase) : 0.85;
      ctx.fillStyle = `rgba(${p.col[0]}, ${p.col[1]}, ${p.col[2]}, ${glow})`;
      ctx.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
    }
    if (forming >= 1 && !el.classList.contains("is-formed")) el.classList.add("is-formed");
    frame = requestAnimationFrame(draw);
  }
  frame = requestAnimationFrame(draw);

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
    burstAt = performance.now();
    el.classList.add("is-leaving");
    window.removeEventListener("keydown", close);
    setTimeout(() => { cancelAnimationFrame(frame); el.remove(); if (done) done(); }, reduced ? 200 : 800);
  };
  el.addEventListener("click", close);
  window.addEventListener("keydown", close);
  setTimeout(close, reduced ? 1600 : SHOW_MS);
}
