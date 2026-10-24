// season.js — the OpsLens logo dresses up for the season, the way Google's logo does.
//
// Why (24 Oct, the owner: "change the OpsLens logo according to season, like Google does on
// Diwali, cricket and FIFA days"): a logo that knows today's date makes the product feel alive,
// and the finale (29–31 Oct 2026) falls in Diwali season. The season comes from the calendar on
// this laptop; clicking the logo shows the next doodle (for the demo), and ?doodle=cricket in the
// address picks one. The splash screen (js/splash.js) and the festival layer (js/fest.js) read
// currentSeason() too. Pure SVG + CSS (web/neon.css, "Doodles").
//
// Example: 24 Oct 2026 → "diwali": the lens becomes a diya whose flame flickers, with sparkles,
// and the tag line says "Shubh Deepavali · every ticket is a promise".

// The seasons, in priority order. "from"/"to" are month-day; "years" pins festivals that move.
// Diwali 2026 is on 8 Nov (Lakshmi Puja); the window covers the festive shopping weeks.
const SEASONS = [
  { id: "newyear", name: "New Year", tag: "Happy New Year · keep every promise", from: "12-31", to: "01-02" },
  { id: "tricolour", name: "Republic Day", tag: "Happy Republic Day", from: "01-24", to: "01-27" },
  { id: "holi", name: "Holi", tag: "Happy Holi · bura na mano", years: { 2026: ["02-28", "03-05"], 2027: ["03-18", "03-23"] } },
  { id: "cricket", name: "Cricket season", tag: "Cricket season · every ball, every ticket", from: "03-20", to: "05-31" },
  { id: "football", name: "Football World Cup", tag: "World Cup fever · no ticket offside", years: { 2026: ["06-11", "07-19"] } },
  { id: "tricolour", name: "Independence Day", tag: "Happy Independence Day", from: "08-13", to: "08-16" },
  { id: "diwali", name: "Diwali", tag: "Shubh Deepavali · every ticket is a promise", years: { 2026: ["10-17", "11-12"], 2027: ["10-08", "11-02"] } },
  { id: "christmas", name: "Christmas", tag: "Merry Christmas · ho ho ho-lding SLAs", from: "12-20", to: "12-26" },
];
const CLASSIC = { id: "classic", name: "OpsLens", tag: "Every ticket is a promise" };
const DEMO_ORDER = ["diwali", "cricket", "football", "holi", "tricolour", "christmas", "newyear", "classic"];
const PICK_KEY = "opslens.doodle";

function mmdd(date) {
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function inWindow(day, from, to) {
  return from <= to ? day >= from && day <= to : day >= from || day <= to; // New Year wraps
}

// The season for a date (today by default), or the classic logo.
export function seasonFor(date = new Date()) {
  const day = mmdd(date);
  for (const s of SEASONS) {
    const range = s.years ? s.years[date.getFullYear()] : [s.from, s.to];
    if (range && inWindow(day, range[0], range[1])) return s;
  }
  return CLASSIC;
}

function byId(id) {
  return SEASONS.find((s) => s.id === id) || CLASSIC;
}

// The season shown now: the address (?doodle=), then a click-picked one, then the calendar.
export function currentSeason() {
  const asked = new URLSearchParams(location.search).get("doodle");
  if (asked) return byId(asked);
  try {
    const picked = sessionStorage.getItem(PICK_KEY);
    if (picked) return byId(picked);
  } catch { /* private mode: the calendar decides */ }
  return seasonFor();
}

const GRAD = `<defs><linearGradient id="lens-g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/></linearGradient></defs>`;
const LENS = `<circle cx="18" cy="18" r="13" fill="none" stroke="url(#lens-g)" stroke-width="3.2"/>
    <path d="M8 19h5l2.5-5 4 9 3-6h5" fill="none" stroke="url(#lens-g)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M28 28l7 7" stroke="url(#lens-g)" stroke-width="3.6" stroke-linecap="round"/>`;
const SPARK = (x, y, c, cls = "") => `<path class="spark ${cls}" d="M${x} ${y - 4} l1 3 l3 1 l-3 1 l-1 3 l-1 -3 l-3 -1 l3 -1z" fill="${c}"/>`;

// One SVG body (40×40) per doodle. Each keeps the lens idea: a ring and a handle.
const DOODLES = {
  classic: () => LENS,
  diwali: () => `
    <circle cx="18" cy="18" r="14" fill="none" stroke="#fbbf24" stroke-width="1.2" stroke-dasharray="2 3" opacity="0.7"/>
    <path d="M28 28l7 7" stroke="url(#lens-g)" stroke-width="3.6" stroke-linecap="round"/>
    <path d="M6 22 q12 14 24 0z" fill="#f97316"/><path d="M6 22 q12 4 24 0" fill="#fdba74"/>
    <path d="M10 26 h16" stroke="#9a3412" stroke-width="1.2" stroke-dasharray="1.5 2"/>
    <g class="flame"><path d="M18 21 q-6 -7 0 -16 q6 9 0 16z" fill="#fde047"/><path d="M18 20 q-3 -4 0 -9 q3 5 0 9z" fill="#f97316"/></g>
    ${SPARK(5, 8, "#fde047", "s1")}${SPARK(32, 6, "#f472b6", "s2")}${SPARK(34, 18, "#22d3ee", "s3")}`,
  cricket: () => `
    <g class="bat"><path d="M27 27 l9 9" stroke="#d6a46b" stroke-width="5" stroke-linecap="round"/>
      <path d="M25 25 l3 3" stroke="#1e293b" stroke-width="3" stroke-linecap="round"/></g>
    <g class="ball"><circle cx="16" cy="16" r="11" fill="#dc2626"/>
      <path d="M9 8 q7 8 0 16 M23 8 q-7 8 0 16" fill="none" stroke="#fff" stroke-width="1.3" stroke-dasharray="1.6 1.4"/>
      <circle cx="12" cy="12" r="2.4" fill="#fff" opacity="0.35"/></g>`,
  football: () => `
    <path d="M28 28l7 7" stroke="url(#lens-g)" stroke-width="3.6" stroke-linecap="round"/>
    <g class="ball"><circle cx="17" cy="17" r="12.5" fill="#f8fafc" stroke="#0f172a" stroke-width="1.4"/>
      <path d="M17 12 l4.6 3.4 l-1.8 5.4 h-5.6 l-1.8 -5.4z" fill="#0f172a"/>
      <path d="M17 12 v-6.5 M21.6 15.4 l6 -2 M19.8 20.8 l3.8 5 M14.2 20.8 l-3.8 5 M12.4 15.4 l-6 -2" stroke="#0f172a" stroke-width="1.2"/></g>`,
  holi: () => `
    <circle class="blob b1" cx="7" cy="9" r="5" fill="#f472b6"/><circle class="blob b2" cx="31" cy="8" r="4" fill="#facc15"/>
    <circle class="blob b3" cx="6" cy="30" r="4" fill="#22c55e"/><circle class="blob b4" cx="33" cy="20" r="3.5" fill="#38bdf8"/>
    <g class="rainbow">${LENS}</g>`,
  tricolour: () => `
    <circle cx="18" cy="18" r="13" fill="none" stroke="#ff9933" stroke-width="3.2" stroke-dasharray="27.2 54.5"/>
    <circle cx="18" cy="18" r="13" fill="none" stroke="#f8fafc" stroke-width="3.2" stroke-dasharray="27.2 54.5" stroke-dashoffset="-27.2"/>
    <circle cx="18" cy="18" r="13" fill="none" stroke="#138808" stroke-width="3.2" stroke-dasharray="27.2 54.5" stroke-dashoffset="-54.5"/>
    <g class="chakra"><circle cx="18" cy="18" r="6.5" fill="none" stroke="#1e3a8a" stroke-width="1.4"/>
      <path d="M18 11.5v13M11.5 18h13M13.4 13.4l9.2 9.2M22.6 13.4l-9.2 9.2" stroke="#1e3a8a" stroke-width="0.9"/></g>
    <path d="M28 28l7 7" stroke="url(#lens-g)" stroke-width="3.6" stroke-linecap="round"/>`,
  christmas: () => `${LENS}
    <g class="hat"><path d="M5 12 q4 -11 15 -9 q-3 2 -1 8z" fill="#dc2626"/><path d="M4 12 q8 -3 16 -1" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
      <circle cx="20" cy="3" r="2.4" fill="#fff"/></g>
    <circle class="snow n1" cx="30" cy="4" r="1.2" fill="#fff"/><circle class="snow n2" cx="36" cy="12" r="1" fill="#fff"/><circle class="snow n3" cx="3" cy="22" r="1" fill="#fff"/>`,
  newyear: () => `${LENS}
    <g class="burst b1"><path d="M33 6 v-4 M33 6 h4 M33 6 v4 M33 6 h-4 M33 6 l3 -3 M33 6 l-3 3 M33 6 l3 3 M33 6 l-3 -3" stroke="#fde047" stroke-width="1.2" stroke-linecap="round"/></g>
    <g class="burst b2"><path d="M5 31 v-3 M5 31 h3 M5 31 v3 M5 31 h-3 M5 31 l2 -2 M5 31 l-2 2 M5 31 l2 2 M5 31 l-2 -2" stroke="#f472b6" stroke-width="1.2" stroke-linecap="round"/></g>`,
};

export function doodleSvg(id) {
  return GRAD + (DOODLES[id] || DOODLES.classic)();
}

function apply(season) {
  const brand = document.querySelector(".sidebar .brand");
  if (!brand) return;
  const logo = brand.querySelector(".brand-logo");
  logo.innerHTML = doodleSvg(season.id);
  [...brand.classList].filter((c) => c.startsWith("doodle-")).forEach((c) => brand.classList.remove(c));
  brand.classList.add(`doodle-${season.id}`);
  brand.querySelector(".brand-tag").textContent = season.tag;
  brand.title = `${season.name} doodle. Click the logo for the next one.`;
  document.documentElement.dataset.season = season.id;
}

// Show the next doodle (demo): Diwali → Cricket → Football → … → classic.
function next() {
  const now = currentSeason().id;
  const id = DEMO_ORDER[(DEMO_ORDER.indexOf(now) + 1) % DEMO_ORDER.length];
  try { sessionStorage.setItem(PICK_KEY, id); } catch { /* ignore */ }
  const season = byId(id);
  apply(season);
  const brand = document.querySelector(".sidebar .brand");
  brand.classList.remove("doodle-pop");
  void brand.offsetWidth;
  brand.classList.add("doodle-pop");
  document.dispatchEvent(new CustomEvent("season-changed", { detail: season }));
}

export function setSeason(id) {
  try { sessionStorage.setItem(PICK_KEY, id); } catch { /* ignore */ }
  apply(byId(id));
  document.dispatchEvent(new CustomEvent("season-changed", { detail: byId(id) }));
}

export function initSeason() {
  apply(currentSeason());
  const logo = document.querySelector(".sidebar .brand-logo");
  if (logo) {
    logo.style.cursor = "pointer";
    logo.addEventListener("click", next);
  }
}
