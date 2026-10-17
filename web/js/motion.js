// motion.js — headline numbers count up when a page opens.
//
// Why: a number that arrives draws the eye to it, and the projector audience sees which number
// matters. The animation only changes how the text gets there: it ends on exactly the text the
// page rendered from results.json (same digits, same unit), so nothing new is ever shown.
//
// Example: "2.2%" counts 0.0% → 2.2% in 0.9 s; "−4.6 pts" counts −0.0 → −4.6 pts; "10,788" keeps its comma.

const SELECTOR = ".stat-value .ev, .proof-a .ev, .cbar-value .ev";
const DURATION_MS = 900;
const NUMBER = /[−-]?\d[\d,]*(?:\.\d+)?/;

export function initMotion() {
  document.addEventListener("tab-shown", (event) => {
    const panel = document.getElementById("tab-" + event.detail);
    if (panel) countUp(panel);
  });
}

export function countUp(root) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  root.querySelectorAll(SELECTOR).forEach((el) => {
    const final = el.textContent;
    const match = final.match(NUMBER);
    if (!match) return;
    const raw = match[0];
    const negative = /^[−-]/.test(raw);
    const digits = raw.replace(/^[−-]/, "");
    const target = Number(digits.replace(/,/g, ""));
    const decimals = (digits.split(".")[1] || "").length;
    const commas = digits.includes(",");
    const sign = negative ? raw[0] : "";
    const [before, after] = [final.slice(0, match.index), final.slice(match.index + raw.length)];
    const started = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - started) / DURATION_MS);
      const eased = 1 - Math.pow(1 - t, 3);
      let text = (target * eased).toFixed(decimals);
      if (commas) text = Number(text).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      el.textContent = t < 1 ? `${before}${sign}${text}${after}` : final;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}
