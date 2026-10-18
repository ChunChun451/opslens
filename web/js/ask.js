// ask.js — "Ask OpsLens": the command bar in the top bar.
//
// What happens: the manager types a question in plain words ("What if Team C loses 2 agents
// on Saturday?"). The server (POST /api/ask, opslens/ask.py) lets the LLM pick ONE engine tool,
// checks it, runs the real engine and returns the answer lines. This file only shows them.
//
// Why the "How I answered" list: judges should see that the LLM understood the question and
// the simulator produced the numbers — the LLM never writes a number (CLAUDE.md rule 1.5).
// Numbers here are computed live at request time, so they are not clickable to results.json;
// the panel says so.

import { escapeHtml } from "./format.js";

const EXAMPLES = [
  "What if Team C loses 2 agents on Saturday and volume goes up 20%?",
  "Why is T060582 at risk?",
  "Plant a refund spike and see if you find it",
  "What should we fix first?",
];

export function initAsk() {
  const form = document.getElementById("ask-form");
  const input = document.getElementById("ask-input");
  const panel = document.getElementById("ask-panel");
  if (!form || !input || !panel) return;
  input.addEventListener("focus", () => { if (!panel.innerHTML) showExamples(panel, input); });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (question) await ask(question, panel);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { panel.hidden = true; }
    // "/" focuses the bar from anywhere (like many search boxes), unless already typing.
    if (event.key === "/" && document.activeElement?.tagName !== "INPUT") {
      event.preventDefault();
      input.focus();
    }
  });
}

function showExamples(panel, input) {
  panel.innerHTML = `<div class="ask-head">Try asking</div>
    ${EXAMPLES.map((q) => `<button type="button" class="ask-example">${escapeHtml(q)}</button>`).join("")}`;
  panel.hidden = false;
  panel.querySelectorAll(".ask-example").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.textContent;
      document.getElementById("ask-form").requestSubmit();
    });
  });
}

async function ask(question, panel) {
  panel.hidden = false;
  panel.innerHTML = `<div class="ask-head">Working…</div>
    <p class="ask-wait">Understanding the question, then running the engine. A simulation takes a few seconds.</p>`;
  const started = performance.now();
  let data;
  try {
    const response = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
    });
    data = await response.json();
    if (!response.ok) throw new Error(data.error || `server answered ${response.status}`);
  } catch (error) {
    panel.innerHTML = `<div class="ask-head">Could not answer</div><p>${escapeHtml(error.message)}</p>`;
    return;
  }
  const seconds = ((performance.now() - started) / 1000).toFixed(1);
  panel.innerHTML = `
    <div class="ask-head">${escapeHtml(data.title)}<button type="button" class="ask-close" aria-label="Close">×</button></div>
    <div class="ask-lines">${data.lines.map((l) => `<p>${escapeHtml(l)}</p>`).join("")}</div>
    ${factsTable(data.facts)}
    <details class="ask-trace" open>
      <summary>How I answered (${seconds} s)</summary>
      <ol>${data.trace.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ol>
      <p class="ask-note">${data.route.understood_by.startsWith("LLM")
        ? "The LLM only chose the tool and copied your numbers;"
        : "Keyword rules understood the question (no LLM needed);"} every number above was computed by the engine just now.</p>
    </details>`;
  panel.querySelector(".ask-close").addEventListener("click", () => { panel.hidden = true; });
}

function factsTable(facts) {
  if (!facts || !facts.length) return "";
  const rows = facts.map((f) => `<tr><td>${escapeHtml(f.label)}</td>
      <td class="num">${f.breach_pct.toFixed(1)}%</td><td class="num">${f.p90_min.toFixed(0)}</td>
      <td class="num">${f.max_backlog.toFixed(0)}</td>
      <td class="num">${f.late_per_100 == null ? "–" : Math.round(f.late_per_100).toLocaleString("en-IN")}</td></tr>`).join("");
  return `<table class="ask-table"><thead><tr><th>Policy</th><th class="num">SLA breaches</th>
    <th class="num">P90 min</th><th class="num">Peak queue</th><th class="num">Min late / 100</th></tr></thead><tbody>${rows}</tbody></table>`;
}
