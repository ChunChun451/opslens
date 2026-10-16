// ui.js — the small building blocks every tab is made of.
//
// Why: a dashboard looks professional when every card, title, number and badge looks the same
// everywhere. So the tabs do not write their own frames: they call these few functions, and
// the look lives in one place (here + styles.css).
//
// Example:
//   card({ title: "Forecast", sub: "Next 48 hours", body: "<canvas ...>" })
//   stat("AUC", ev("risk.auc", "ratio"), "real UCI data: 0.86")
//   deltaPill("sim.comparisons[0]", "pts", "lower")  -> a green "−10.7 pts" pill when the
//                                                      whole 95% CI is below zero

import { state, policyLabel, lookup } from "./data.js";
import { policyStyle } from "./charts.js";
import { ev } from "./evidence.js";
import { escapeHtml } from "./format.js";

// ---- Frames ---------------------------------------------------------------------------------

// The title row at the top of every tab.
export function pageHeader(title, subtitle, actions = "") {
  return `<header class="page-head">
      <div>
        <h1 class="page-title">${escapeHtml(title)}</h1>
        ${subtitle ? `<p class="page-sub">${subtitle}</p>` : ""}
      </div>
      ${actions ? `<div class="page-actions">${actions}</div>` : ""}
    </header>`;
}

// A white card with an optional title, subtitle and actions on the right.
// `title` is plain text; `sub`, `actions` and `body` are HTML.
export function card({ title = "", sub = "", actions = "", body = "", id = "", cls = "" }) {
  const head = title || actions
    ? `<div class="card-head">
        <div>${title ? `<h3 class="card-title">${escapeHtml(title)}</h3>` : ""}
          ${sub ? `<div class="card-sub">${sub}</div>` : ""}</div>
        ${actions ? `<div>${actions}</div>` : ""}
      </div>`
    : "";
  return `<section class="card ${cls}" ${id ? `id="${id}"` : ""}>${head}${body}</section>`;
}

// One headline number with a label above and a short line below.
// size: "" (normal), "md" (smaller) or "xl" (hero).
export function stat(label, valueHtml, subHtml = "", size = "") {
  return `<div class="stat">
      <div class="stat-label">${escapeHtml(label)}</div>
      <div class="stat-value ${size}">${valueHtml}</div>
      ${subHtml ? `<div class="stat-sub">${subHtml}</div>` : ""}
    </div>`;
}

// Shown when a results section is missing (milestones fill the JSON one by one).
export function missing(sectionName, milestone) {
  return card({ body: `<p class="muted"><strong>${escapeHtml(sectionName)}</strong> is not in the results file yet.
    It is computed in ${escapeHtml(milestone)}.</p>` });
}

// Shown when a button needs the OpsLens server but the page is served without it
// (for example by python -m http.server).
export function backendMissing(endpoint, detail) {
  return `<div class="callout warn">
    <strong>This needs the OpsLens server.</strong>
    <code>${escapeHtml(endpoint)}</code> is not reachable from this page, so nothing was computed.
    ${detail ? escapeHtml(detail) : ""}
  </div>`;
}

// ---- Policies -------------------------------------------------------------------------------

// A small dot in the policy's colour (the same colour as its lines and bars in charts).
export function policyDot(key) {
  return `<span class="dot" style="background: ${policyStyle(key).color}"></span>`;
}

// Dot + name, e.g. "● OpsLens". `label` overrides the name (for short labels in tables).
export function policyName(key, label) {
  return `<span class="policy">${policyDot(key)}${escapeHtml(label || policyLabel(key))}</span>`;
}

// "Baseline A (FIFO)" -> "Baseline A", for narrow table headers.
export function shortLabel(key) {
  return policyLabel(key).replace(/\s*\(.*\)$/, "");
}

// ---- Differences with a 95% CI -----------------------------------------------------------------

// Index of the comparison (policy − baseline) for one KPI in sim.comparisons, or -1.
export function comparisonIndex(policy, baseline, kpi) {
  const sim = state.results.sim;
  if (!sim) return -1;
  return sim.comparisons.findIndex((c) => c.policy === policy && c.baseline === baseline && c.kpi === kpi);
}

// A pill with a signed difference. Its colour comes from the whole 95% CI:
// good when the CI is entirely on the better side, bad when entirely on the worse side,
// grey when it includes zero. `base` is the path of an object with mean_diff, ci_low, ci_high.
export function deltaPill(base, unit, better = "lower", valueKey = "mean_diff") {
  const row = lookup(base);
  if (!row) return "";
  let tone = "";
  if (better === "lower" || better === "higher") {
    const sign = better === "lower" ? 1 : -1;
    if (sign * row.ci_high < 0) tone = "good";
    if (sign * row.ci_low > 0) tone = "bad";
  }
  return `<span class="delta ${tone}">${ev(`${base}.${valueKey}`, unit, { signed: true })}</span>`;
}

// ---- Loading states -----------------------------------------------------------------------------

// A spinner with a message and a seconds counter, for server calls that take 10-40 s.
// The counter is the time waited so far (a clock, not a result). It stops by itself when the
// element is replaced by the answer.
export function showWaiting(container, message) {
  container.innerHTML = `<div class="wait" role="status">
      <span class="spinner" aria-hidden="true"></span>
      <span class="wait-text">${message}</span>
      <span class="wait-clock">0 s</span>
    </div>`;
  const clock = container.querySelector(".wait-clock");
  const started = Date.now();
  const timer = setInterval(() => {
    if (!clock.isConnected) {
      clearInterval(timer);
      return;
    }
    clock.textContent = Math.round((Date.now() - started) / 1000) + " s";
  }, 1000);
}

// POST a form (file upload) with a time limit. Same rules as postJson below.
export async function postForm(url, form, timeoutMs = 120000) {
  if (state.staticServer) {
    throw new Error("No API on the static preview server");
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { method: "POST", body: form, signal: controller.signal });
    let answer = null;
    try {
      answer = await response.json();
    } catch (error) {
      // not JSON
    }
    if (!response.ok) {
      throw new Error("HTTP " + response.status + (answer && answer.error ? ": " + answer.error : ""));
    }
    return answer;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("No answer after " + Math.round(timeoutMs / 1000) + " s");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

// ---- Small helpers ----------------------------------------------------------------------------

// "Neha G." -> "NG" (for the round agent badges).
export function initials(name) {
  return String(name).split(/\s+/).map((w) => w.charAt(0)).join("").slice(0, 2).toUpperCase();
}

// POST JSON to the server. Returns the parsed answer, or throws when the server is not
// there, says no, or takes longer than `timeoutMs`. Used by What-if and Plant-a-problem.
// On the static preview server there is no API, so we do not even try (no console errors).
export async function postJson(url, body, timeoutMs = 60000) {
  if (state.staticServer) {
    throw new Error("No API on the static preview server");
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.json()).error || ""; // the server explains a 400 in "error"
      } catch (error) {
        // not JSON: keep the status only
      }
      throw new Error("HTTP " + response.status + (detail ? ": " + detail : ""));
    }
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("No answer after " + Math.round(timeoutMs / 1000) + " s");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
