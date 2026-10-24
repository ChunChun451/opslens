// mascot.js — "Lenny", a minimal cartoon made from the OpsLens lens logo, and the customer it serves.
//
// Why (24 Oct, the owner asked for "cartoon animation, minimal", then for a scene: the AI tired,
// wiping its sweat, while a customer keeps complaining "dosa ke jagah biryani de diya"): a small
// scene gives the live screen a face and says what OpsLens is for: support floors are flooded.
// It never carries information of its own. Lenny looks tired when the live floor is busy, relaxed
// when it is quiet, hops with "+N helped!" when the live gap grows (that change comes from the
// same live answer), and sleeps when nobody is in danger. The customer's lines are one fixed joke
// and the masked text of real tickets in danger. Pure SVG + CSS (web/neon.css, "Mascot").
//
// Example: 110 customers waiting → Lenny sweats and wipes his face; the customer says
// "Dosa ke jagah biryani de diya!", then "paisa kat gaya but order place nahi hua".

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
        <g class="mascot-lids"><path d="M21.5 29 h9 M37.5 29 h9" stroke="#0d1428" stroke-width="5" stroke-linecap="round"/>
          <path d="M22 31 h8 M38 31 h8" stroke="#7dd3fc" stroke-width="1.4" stroke-linecap="round"/></g>
        <path class="mascot-closed" d="M22 32 q4 3 8 0 M38 32 q4 3 8 0" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>
        <path class="mascot-happy" d="M22 32 q4 -4 8 0 M38 32 q4 -4 8 0" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round"/>
        <circle cx="21" cy="40" r="3" fill="#ff4d8d" opacity="0.55"/>
        <circle cx="47" cy="40" r="3" fill="#ff4d8d" opacity="0.55"/>
        <path class="mascot-smile" d="M27 41 q7 6 14 0" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round"/>
        <path class="mascot-frown" d="M27 44 q7 -4 14 0" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round"/>
        <g class="mascot-sweat">
          <path class="drop d1" d="M13 22 q-3 5 0 7 q3 -2 0 -7z" fill="#7dd3fc"/>
          <path class="drop d2" d="M55 18 q-3 5 0 7 q3 -2 0 -7z" fill="#7dd3fc"/>
        </g>
        <g class="mascot-towel">
          <rect x="6" y="12" width="20" height="9" rx="3" fill="#fef3c7" stroke="#f59e0b" stroke-width="1.2"/>
          <path d="M9 14 v5 M13 14 v5 M17 14 v5 M21 14 v5" stroke="#f59e0b" stroke-width="0.8"/>
          <circle cx="4" cy="17" r="4" fill="#a78bfa"/>
        </g>
      </svg>
      <div class="mascot-z"><span>z</span><span>z</span><span>z</span></div>
    </div>`;
}

// The customer: a round face with a phone and cross eyebrows, and a speech bubble.
export function customerHtml(id) {
  return `<div class="customer" id="${id}" aria-hidden="true">
      <svg viewBox="0 0 80 80" width="68" height="68">
        <circle cx="38" cy="40" r="24" fill="#f6c39a"/>
        <path d="M15 34 q6 -22 26 -20 q18 2 21 18 q-10 -9 -22 -9 q-15 0 -25 11z" fill="#3b2a20"/>
        <path class="brow" d="M26 33 l9 3 M51 33 l-9 3" stroke="#3b2a20" stroke-width="2.6" stroke-linecap="round"/>
        <circle cx="31" cy="40" r="2.4" fill="#3b2a20"/>
        <circle cx="46" cy="40" r="2.4" fill="#3b2a20"/>
        <ellipse class="mouth" cx="38" cy="52" rx="5" ry="3.6" fill="#7c2d12"/>
        <g class="phone"><rect x="58" y="34" width="13" height="22" rx="3" fill="#1e293b" stroke="#22d3ee" stroke-width="1.2"/>
          <circle cx="56" cy="50" r="4.5" fill="#f6c39a"/></g>
        <path class="steam s1" d="M14 14 q3 -4 0 -8" stroke="#ff4d8d" stroke-width="2" fill="none" stroke-linecap="round"/>
        <path class="steam s2" d="M60 10 q3 -4 0 -8" stroke="#ff4d8d" stroke-width="2" fill="none" stroke-linecap="round"/>
      </svg>
    </div>`;
}

// The wrong order: a steaming plate of biryani (rice, a chicken leg, mint, lemon), with a thought
// cloud of the crossed-out dosa the customer wanted. Decoration only, like the rest of the scene.
// few = true is the Results screen's complaint ("chicken ke kam pieces"): one tiny piece on the
// plate, a bobbing "?", and a cloud full of the drumsticks the customer expected.
const DRUMSTICK = (x, y) => `<g transform="translate(${x} ${y})"><path d="M0 6 q5 -7 11 -4 q3 5 -3 8 q-6 1 -8 -4z" fill="#92400e"/>
    <path d="M10 2 l4 -4" stroke="#fef3c7" stroke-width="2.4" stroke-linecap="round"/><circle cx="14.5" cy="-2.5" r="1.8" fill="#fef3c7"/></g>`;
export function biryaniHtml(id, few = false) {
  const wish = few
    ? `${DRUMSTICK(6, 10)}${DRUMSTICK(17, 6)}${DRUMSTICK(25, 13)}`
    : `<path class="dosa" d="M11 17 L33 9 L31 18 Z" fill="#f59e0b" stroke="#b45309" stroke-width="1"/>
          <path d="M14 15 l3 -1 M20 13 l3 -1 M26 11 l3 -1" stroke="#b45309" stroke-width="0.8"/>
          <path class="no" d="M12 6 L32 22 M32 6 L12 22" stroke="#ff4d8d" stroke-width="2.4" stroke-linecap="round"/>`;
  const chicken = few
    ? `<g class="leg few"><path d="M34 21 q4 -4 8 -1 q1 3 -3 4 q-4 0 -5 -3z" fill="#92400e"/></g>
        <text class="huh" x="46" y="14" font-size="13" font-weight="900" fill="#ff4d8d">?</text>`
    : `<g class="leg"><path d="M30 22 q8 -9 16 -5 q4 6 -4 10 q-8 2 -12 -5z" fill="#92400e"/>
          <path d="M44 16 l5 -5" stroke="#fef3c7" stroke-width="3" stroke-linecap="round"/>
          <circle cx="50" cy="10" r="2.2" fill="#fef3c7"/></g>`;
  return `<div class="biryani${few ? " is-few" : ""}" id="${id}" aria-hidden="true">
      <div class="biryani-wish">
        <svg viewBox="0 0 44 30" width="58" height="40">
          <path d="M8 22a7 7 0 01-1-14a9 9 0 0116-4a8 8 0 0114 5a6 6 0 01-2 13z" fill="#fff"/>
          ${wish}
        </svg>
        <i></i><i></i>
      </div>
      <svg class="biryani-plate" viewBox="0 0 64 44" width="88" height="60">
        <path class="steam s1" d="M22 12 q-3 -4 0 -8 q3 -4 0 -8" stroke="#cbd5e1" stroke-width="1.8" fill="none" stroke-linecap="round"/>
        <path class="steam s2" d="M32 10 q-3 -4 0 -8 q3 -4 0 -8" stroke="#cbd5e1" stroke-width="1.8" fill="none" stroke-linecap="round"/>
        <path class="steam s3" d="M42 12 q-3 -4 0 -8 q3 -4 0 -8" stroke="#cbd5e1" stroke-width="1.8" fill="none" stroke-linecap="round"/>
        <ellipse cx="32" cy="36" rx="30" ry="7" fill="#e2e8f0" stroke="#22d3ee" stroke-width="1.4"/>
        <path d="M8 34 Q12 14 32 13 Q52 14 56 34 Z" fill="#fbbf24"/>
        <path d="M14 33 Q18 22 30 20 Q22 26 22 33 Z" fill="#fde68a"/>
        <path d="M38 22 Q48 24 50 33 L44 33 Q44 27 38 22 Z" fill="#f97316" opacity="0.75"/>
        <g fill="#fff"><circle cx="20" cy="28" r="1"/><circle cx="27" cy="24" r="1"/><circle cx="34" cy="19" r="1"/>
          <circle cx="40" cy="27" r="1"/><circle cx="46" cy="30" r="1"/><circle cx="31" cy="29" r="1"/><circle cx="24" cy="31" r="1"/></g>
        ${chicken}
        <path d="M17 22 q3 -5 7 -3 q-3 4 -7 3z" fill="#22c55e"/>
        <circle cx="52" cy="35" r="3.4" fill="#facc15" stroke="#a16207" stroke-width="0.8"/>
      </svg>
    </div>`;
}

// Set Lenny's mood: "idle", "tired", "sleep", "worried" or "happy" (keeps a running cheer).
// worried = frown and sweat without the towel (Risks); happy = smiling closed eyes (Results).
export function setMood(id, mood) {
  const el = document.getElementById(id);
  if (!el) return;
  ["idle", "tired", "sleep", "worried", "happy"].forEach((m) => el.classList.toggle(`is-${m}`, m === mood));
}

// A hop and a short speech bubble ("+1 helped!"), then back to its mood.
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
