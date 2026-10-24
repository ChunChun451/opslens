// bot.js — the OpsLens assistant: an animated AI bot in the side menu that answers whatever the
// jury, a manager or a customer asks.
//
// Why (24 Oct, the owner: "remove the festival layer, it feels festive not professional; put an
// animated AI bot there that resolves customers' queries, so capable that if the jury asks any
// problem we can ask the bot directly"): during Q&A the team should be able to type the judge's
// question and show a tested answer at once. The server (server/bot.py, POST /api/bot) picks one
// of four answers: a customer complaint → triage by our text classifier; a what-if or ticket
// question → the engine (Ask OpsLens); a question about OpsLens → the closest prepared answer
// (docs/JUDGE_QA.md, docs/BOT_QA.md: every number in them is checked against results.json by a
// test); "show me ..." → this file opens the screen. The bot never writes a number of its own.
//
// Example: "Isn't this data leakage?" → Q19 with its tested answer and two related questions;
// "dosa ke jagah biryani de diya" → Wrong item, Hindi / Hinglish, Team C (Order accuracy).

import { characterHtml } from "./characters.js";
import { escapeHtml } from "./format.js";
import { factsTable } from "./ask.js";
import { setWorld } from "./router.js";
import { state } from "./data.js";

const STARTERS = [
  ["Jury favourites", ["Isn't this data leakage?", "Why should we trust a simulator?", "Your data is synthetic, isn't it?",
    "Can it scale to millions of tickets?", "How is this better than our helpdesk tools?"]],
  ["Run the engine", ["What if Team C loses 2 agents on Saturday?", "Why is T060582 at risk?", "What should we fix first?"]],
  ["A customer says", ["dosa ke jagah biryani de diya", "paisa kat gaya but order nahi aaya", "my food is 40 minutes late"]],
  ["Show me", ["Show me Shadow mode", "Show me the 30 random worlds", "Show me the rules we wrote first"]],
];

// "Show me X" → a screen. [pattern, hash, world]
const PLACES = [
  [/shadow/i, "#overview/rd-shadow", "real"],
  [/real (it )?desk|it desk|service desk|servicenow/i, "#overview/rd-overview", "real"],
  [/30|random world|beyond/i, "#proof/worlds", "food"],
  [/rule|ledger|pre-?regist/i, "#proof/ledger", "food"],
  [/what-?if|simulat/i, "#proof/whatif", "food"],
  [/how we tested|tests?\b|banking|earn its place/i, "#proof/tested", "food"],
  [/side by side|compare|baseline/i, "#proof/compare", "food"],
  [/live/i, "#overview/live", "food"],
  [/result|1,?000|journey|ticket.*follow/i, "#overview/overview", "food"],
  [/problem|pattern/i, "#problems", "food"],
  [/forecast|48|next week/i, "#risks/next48", "food"],
  [/risk|late tickets|at risk/i, "#risks/atrisk", "food"],
  [/action|fix|recommend/i, "#actions", "food"],
  [/upload|your data|csv/i, "#upload", "food"],
];
const SHOW = /^\s*(show( me)?|open|go to|take me to|dikhao|dikha do|le chalo)\b/i;

let warmed = false;
let busy = false;

export function initBot() {
  const launch = `<button type="button" class="bot-launch" id="bot-launch" aria-label="Open the OpsLens AI assistant">
      ${characterHtml("bot-mini", "robot", "happy")}
      <span class="bl-text"><b>Ask OpsLens AI</b><small>jury · managers · customers</small></span>
      <i class="bl-ping" aria-hidden="true"></i>
    </button>`;
  const foot = document.querySelector(".sidebar .sidebar-foot");
  if (foot) foot.insertAdjacentHTML("beforebegin", launch);
  else document.body.insertAdjacentHTML("beforeend", launch);
  document.body.insertAdjacentHTML("beforeend", panelHtml());

  document.getElementById("bot-launch").addEventListener("click", open);
  document.getElementById("bot-close").addEventListener("click", close);
  document.getElementById("bot-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("bot-input");
    const q = input.value.trim();
    if (q) { input.value = ""; ask(q); }
  });
  document.getElementById("bot-log").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-q]");
    if (chip) { ask(chip.dataset.q); return; }
    const go = event.target.closest("[data-go]");
    if (go) goTo(go.dataset.go, go.dataset.world || "food", go.dataset.card);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
}

function panelHtml() {
  const groups = STARTERS.map(([title, qs]) => `<div class="bs-group"><span>${escapeHtml(title)}</span>
      <div class="bs-chips">${qs.map((q) => `<button type="button" class="bot-chip" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join("")}</div></div>`).join("");
  return `<aside class="bot-panel" id="bot-panel" role="dialog" aria-label="OpsLens AI assistant" hidden>
      <header class="bp-head">
        <div class="bp-avatar" id="bp-avatar">${characterHtml("bot-big", "robot", "happy")}</div>
        <div class="bp-title"><b>OpsLens AI</b><span><i class="bp-dot"></i>Answers from tested results. It never makes up a number.</span></div>
        <button type="button" class="bp-close" id="bot-close" aria-label="Close the assistant">✕</button>
      </header>
      <div class="bp-log" id="bot-log" aria-live="polite">
        <div class="bm bm-bot"><div class="bm-bubble">
          <p>Namaste! I'm the OpsLens assistant. Ask me anything a judge would ask about OpsLens, run a what-if on the
            engine, or paste a customer's complaint and I'll triage it. English or Hinglish.</p>
          <div class="bot-starters">${groups}</div>
        </div></div>
      </div>
      <form class="bp-form" id="bot-form" autocomplete="off">
        <input id="bot-input" type="text" maxlength="400" placeholder="Ask anything… e.g. isn't this data leakage?" aria-label="Your question">
        <button type="submit" class="bp-send" aria-label="Send">➤</button>
      </form>
    </aside>`;
}

function open() {
  const panel = document.getElementById("bot-panel");
  panel.hidden = false;
  requestAnimationFrame(() => panel.classList.add("is-open"));
  document.getElementById("bot-input").focus();
  if (!warmed) {
    warmed = true;
    fetch("/api/bot/warm").catch(() => {}); // the classifier loads (or trains once) in the background
  }
}
function close() {
  const panel = document.getElementById("bot-panel");
  if (!panel || panel.hidden) return;
  panel.classList.remove("is-open");
  setTimeout(() => { panel.hidden = true; }, 280);
}

function goTo(hash, world, card) {
  if (state.world !== world) {
    setWorld(world);
    document.querySelectorAll(".world-switch [data-world]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.world === world)));
  }
  location.hash = hash;
  if (card) setTimeout(() => document.getElementById(card)?.scrollIntoView({ behavior: "smooth", block: "start" }), 500);
  if (window.matchMedia("(max-width: 900px)").matches) close();
}

// ---- one question ---------------------------------------------------------------------------------

async function ask(question) {
  if (busy) return;
  addMessage("user", `<p>${escapeHtml(question)}</p>`);
  // "Show me ..." is answered here: open the screen.
  if (SHOW.test(question)) {
    const place = PLACES.find(([re]) => re.test(question));
    if (place) {
      addMessage("bot", `<p>Opening it for you.</p><button type="button" class="bm-go" data-go="${place[1]}" data-world="${place[2]}">Open again</button>`);
      goTo(place[1], place[2]);
      return;
    }
  }
  busy = true;
  const typing = addMessage("bot", `<div class="bm-typing"><i></i><i></i><i></i></div>`, "is-typing");
  setTalking(true);
  let data;
  try {
    const response = await fetch("/api/bot", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
    });
    data = await response.json();
    if (!response.ok) throw new Error(data.error || `server answered ${response.status}`);
  } catch (error) {
    typing.remove();
    addMessage("bot", `<p>I need the OpsLens server to answer (${escapeHtml(error.message)}). Start it with <code>make serve</code>.</p>`);
    busy = false;
    setTalking(false);
    return;
  }
  typing.remove();
  addMessage("bot", render(data));
  busy = false;
  setTimeout(() => setTalking(false), 900);
}

function render(d) {
  if (d.kind === "qa") return renderQa(d);
  if (d.kind === "triage") return renderTriage(d);
  if (d.kind === "engine") return renderEngine(d);
  return `<p>I don't have a tested answer for that, and I won't guess. Did you mean one of these?</p>
    <div class="bs-chips">${(d.suggestions || []).map((s) => `<button type="button" class="bot-chip" data-q="${escapeHtml(s.question)}">${escapeHtml(s.question)}</button>`).join("")}</div>`;
}

// Markdown-light: paragraphs, **bold**, `code`. The text is escaped first.
function formatAnswer(text) {
  return text.split(/\n\s*\n/).map((para) => {
    let html = escapeHtml(para.replace(/\n/g, " "));
    html = html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
    return `<p>${html}</p>`;
  }).join("");
}

function renderQa(d) {
  const related = (d.related || []).length
    ? `<div class="bm-related"><span>Related</span><div class="bs-chips">${d.related.map((r) =>
        `<button type="button" class="bot-chip" data-q="${escapeHtml(r.question)}">${escapeHtml(r.question)}</button>`).join("")}</div></div>` : "";
  return `<div class="bm-qhead"><span class="bm-id">${escapeHtml(d.id)}</span>${d.attack ? '<span class="bm-attack">tough question</span>' : ""}
      <span class="bm-q">${escapeHtml(d.question)}</span></div>
    <div class="bm-answer">${formatAnswer(d.answer)}</div>
    <div class="bm-src">Prepared answer · every number in it is checked against the results file by a test · matched by ${escapeHtml(d.matched_by || "word matching")}</div>
    ${related}`;
}

function renderTriage(d) {
  const pct = Math.round(d.confidence * 100);
  const evidence = d.evidence ? `<div class="bm-evidence"><b>Part of a known problem:</b> ${escapeHtml(d.evidence.title)}
      ${d.evidence.recommendation ? `<br><span>Fix at the source: ${escapeHtml(d.evidence.recommendation)}</span>` : ""}
      <button type="button" class="bm-go" data-go="#problems" data-world="food" data-card="card-${escapeHtml(d.evidence.id)}">See the evidence</button></div>` : "";
  return `<div class="bm-triage">
      <div class="bt-title">Triage, by OpsLens's text classifier</div>
      <div class="bt-tags"><span class="bt-tag is-cat">${escapeHtml(d.category_label)} <small>${pct}% sure</small></span>
        <span class="bt-tag">${escapeHtml(d.language_label)}</span>
        <span class="bt-tag is-team">Team ${escapeHtml(d.team)} · ${escapeHtml(d.team_name)}</span></div>
      <ol class="bt-steps">${d.steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>
      ${evidence}
      <div class="bm-src">Read by the local model trained on the training days only${d.masked ? "; personal data was masked first" : ""}. No LLM involved.</div>
    </div>`;
}

function renderEngine(d) {
  const by = d.route && d.route.understood_by ? d.route.understood_by : "";
  return `<div class="bm-qhead"><span class="bm-id is-engine">engine</span><span class="bm-q">${escapeHtml(d.title || "")}</span></div>
    <div class="bm-answer">${(d.lines || []).map((l) => `<p>${escapeHtml(l)}</p>`).join("")}</div>
    ${factsTable(d.facts)}
    <div class="bm-src">${by.startsWith("LLM") ? "The LLM only chose the tool and copied your numbers;" : "Keyword rules understood the question;"}
      every number above was computed by the engine just now.</div>`;
}

function addMessage(who, html, extra = "") {
  const log = document.getElementById("bot-log");
  const el = document.createElement("div");
  el.className = `bm bm-${who} ${extra}`;
  el.innerHTML = who === "bot"
    ? `<div class="bm-face">${characterHtml("bm-face-" + log.children.length, "robot", "happy")}</div><div class="bm-bubble">${html}</div>`
    : `<div class="bm-bubble">${html}</div>`;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

function setTalking(on) {
  document.getElementById("bp-avatar")?.classList.toggle("is-talking", on);
  document.getElementById("bot-launch")?.classList.toggle("is-talking", on);
}
