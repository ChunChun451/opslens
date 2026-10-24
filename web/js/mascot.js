// mascot.js — "Lenny", a minimal cartoon made from the OpsLens lens logo.
//
// Why (24 Oct, the owner asked for "cartoon animation, minimal"): a small friendly character gives
// the live screen a face. It never carries information of its own: it floats and blinks while
// idle, hops and says "+N helped!" when the live gap between OpsLens and the industry standard
// grows (the number it shows is the change in that gap, from the same live answer), and sleeps
// when nobody is in danger. Pure SVG + CSS (web/neon.css, "Mascot"); still for reduced motion.
//
// Example: the gap goes from 2 to 3 → Lenny hops and says "+1 helped!".

export function mascotHtml(id, mood = "idle") {
  return `<div class="mascot is-${mood}" id="${id}" aria-hidden="true">
      <div class="mascot-bubble"></div>
      <svg viewBox="0 0 80 80" width="72" height="72">
        <defs>
          <linearGradient id="${id}-ring" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/>
          </linearGradient>
        </defs>
        <g class="mascot-handle"><path d="M52 52 L68 68" stroke="url(#${id}-ring)" stroke-width="8" stroke-linecap="round"/></g>
        <circle cx="34" cy="34" r="26" fill="#0d1428" stroke="url(#${id}-ring)" stroke-width="6"/>
        <circle cx="34" cy="34" r="20" fill="rgba(34, 211, 238, 0.08)"/>
        <g class="mascot-eyes">
          <ellipse class="mascot-eye" cx="26" cy="31" rx="3.6" ry="4.6" fill="#fff"/>
          <ellipse class="mascot-eye" cx="42" cy="31" rx="3.6" ry="4.6" fill="#fff"/>
          <circle cx="27" cy="30" r="1.4" fill="#0d1428"/>
          <circle cx="43" cy="30" r="1.4" fill="#0d1428"/>
        </g>
        <path class="mascot-closed" d="M22 32 q4 3 8 0 M38 32 q4 3 8 0" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>
        <circle cx="21" cy="40" r="3" fill="#ff4d8d" opacity="0.55"/>
        <circle cx="47" cy="40" r="3" fill="#ff4d8d" opacity="0.55"/>
        <path class="mascot-smile" d="M27 41 q7 6 14 0" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round"/>
      </svg>
      <div class="mascot-z"><span>z</span><span>z</span><span>z</span></div>
    </div>`;
}

// A hop and a short speech bubble ("+1 helped!"), then back to idle.
export function cheer(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.querySelector(".mascot-bubble").textContent = text;
  el.classList.remove("cheer");
  void el.offsetWidth; // restart the animation
  el.classList.add("cheer");
  clearTimeout(el._cheerTimer);
  el._cheerTimer = setTimeout(() => el.classList.remove("cheer"), 2200);
}
