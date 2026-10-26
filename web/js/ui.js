import { state, policyLabel, lookup } from "./data.js";
import { policyStyle } from "./charts.js";
import { ev } from "./evidence.js";
import { escapeHtml } from "./format.js";

export function pageHeader(title, subtitle, actions = "") {
  return `<header class="page-head">
      <div>
        <h1 class="page-title">${escapeHtml(title)}</h1>
        ${subtitle ? `<p class="page-sub">${subtitle}</p>` : ""}
      </div>
      ${actions ? `<div class="page-actions">${actions}</div>` : ""}
    </header>`;
}

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

export function fold(title, body, { id = "", hint = "", open = false } = {}) {
  return `<details class="fold"${id ? ` id="${id}"` : ""}${open ? " open" : ""}>
      <summary><span class="fold-title">${escapeHtml(title)}</span>${hint ? `<span class="fold-hint">${hint}</span>` : ""}
        <span class="fold-arrow" aria-hidden="true"></span></summary>
      <div class="fold-body">${body}</div>
    </details>`;
}

export function onFirstOpen(id, draw) {
  const box = document.getElementById(id);
  if (!box) return;
  const once = () => {
    if (box.open && !box.dataset.drawn) {
      box.dataset.drawn = "1";
      draw();
    }
  };
  box.addEventListener("toggle", once);
  once();
}

export function factLine(items) {
  return `<div class="facts">${items.filter(Boolean).map(([value, label]) =>
    `<span class="fact"><b>${value}</b><span>${escapeHtml(label)}</span></span>`).join("")}</div>`;
}

export function stat(label, valueHtml, subHtml = "", size = "") {
  return `<div class="stat">
      <div class="stat-label">${escapeHtml(label)}</div>
      <div class="stat-value ${size}">${valueHtml}</div>
      ${subHtml ? `<div class="stat-sub">${subHtml}</div>` : ""}
    </div>`;
}

export function missing(sectionName, milestone) {
  return card({ body: `<p class="muted"><strong>${escapeHtml(sectionName)}</strong> is not in the results file yet.
    It is computed in ${escapeHtml(milestone)}.</p>` });
}

export function backendMissing(endpoint, detail) {
  return `<div class="callout warn">
    <strong>This needs the OpsLens server.</strong>
    <code>${escapeHtml(endpoint)}</code> is not reachable from this page, so nothing was computed.
    ${detail ? escapeHtml(detail) : ""}
  </div>`;
}

export function policyDot(key) {
  return `<span class="dot" style="background: ${policyStyle(key).color}"></span>`;
}

export function policyName(key, label) {
  return `<span class="policy">${policyDot(key)}${escapeHtml(label || policyLabel(key))}</span>`;
}

export function shortLabel(key) {
  return policyLabel(key).replace(/\s*\(.*\)$/, "");
}

export function comparisonIndex(policy, baseline, kpi) {
  const sim = state.results.sim;
  if (!sim) return -1;
  return sim.comparisons.findIndex((c) => c.policy === policy && c.baseline === baseline && c.kpi === kpi);
}

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

export function initials(name) {
  return String(name).split(/\s+/).map((w) => w.charAt(0)).join("").slice(0, 2).toUpperCase();
}

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
        detail = (await response.json()).error || "";
      } catch (error) {
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
