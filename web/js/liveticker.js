// liveticker.js — a small live panel in the side menu, on every screen: today's clock and the
// promises missed so far today under the industry standard and under OpsLens.
//
// Why (24 Oct, the owner asked for "everything live on screen"): the Live now view is one click
// deep; this keeps today's live run in sight while a judge looks at any other screen. It reads the
// same GET /api/live answer (a normal day, luck 1) every 10 seconds; clicking it opens Live now.
//
// Example (Saturday 21:14): "● Live 21:14 · missed today: industry standard 23, OpsLens 6".

import { state } from "./data.js";

const EVERY_MS = 10000;
let timer = null;

export function initLiveTicker() {
  const box = document.getElementById("live-ticker");
  if (!box || state.staticServer) return;
  box.hidden = false;
  update(box);
  timer = setInterval(() => update(box), EVERY_MS);
  document.addEventListener("world-changed", () => update(box));
}

async function update(box) {
  const now = new Date();
  const minute = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
  const weekday = (now.getDay() + 6) % 7; // the engine counts Monday as 0
  const clock = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  let data = null;
  try {
    const response = await fetch(`/api/live?weekday=${weekday}&minute=${minute.toFixed(2)}`, { cache: "no-store" });
    data = await response.json();
  } catch (error) {
    data = null;
  }
  if (!data || data.error) {
    box.innerHTML = `<span class="lt-head"><span class="live-dot"></span>Live ${clock}</span><span class="lt-sub">engine not answering</span>`;
    return;
  }
  if (!data.ready) {
    box.innerHTML = `<span class="lt-head"><span class="live-dot"></span>Live ${clock}</span><span class="lt-sub">simulating today…</span>`;
    return;
  }
  const theirs = data.policies.baseline_d.missed;
  const ours = data.policies.opslens.missed;
  box.innerHTML = `<span class="lt-head"><span class="live-dot"></span>Live today ${clock}</span>
    <span class="lt-row"><span>Industry standard</span><b class="lt-theirs">${theirs}</b></span>
    <span class="lt-row"><span>OpsLens</span><b class="lt-ours">${ours}</b></span>
    <span class="lt-sub">promises missed so far, a normal day · open Live now</span>`;
}

export function stopLiveTicker() {
  clearInterval(timer);
  timer = null;
}
