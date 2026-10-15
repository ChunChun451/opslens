// ui.js — small HTML pieces that several tabs share.
//
// Why: the same "policy name with its colour", "not computed yet" box and "server not ready"
// message appear on many tabs. Writing them once keeps the tabs short and consistent.
//
// Example:
//   policyName("opslens")  -> a line sample in OpsLens blue + the label "OpsLens"
//   missing("Risk", "M5")  -> a box saying the risk section is not in the results yet

import { state, policyLabel } from "./data.js";
import { policyStyle } from "./charts.js";
import { escapeHtml } from "./format.js";

// A short line in the policy's colour and dash pattern, like a chart legend entry.
export function swatch(key) {
  const style = policyStyle(key);
  const lineStyle = style.dash.length === 0 ? "solid" : style.dash[0] > 5 ? "dashed" : "dotted";
  return `<span class="swatch" style="border-top: 4px ${lineStyle} ${style.color}"></span>`;
}

export function policyName(key) {
  return `<span class="policy-name">${swatch(key)}${escapeHtml(policyLabel(key))}</span>`;
}

// The coloured top border of a policy column.
export function policyBorder(key) {
  return `border-top-color: ${policyStyle(key).color}`;
}

// Shown when a results section is missing (milestones fill the JSON one by one).
export function missing(sectionName, milestone) {
  return `<div class="panel notice">
    <strong>${escapeHtml(sectionName)}</strong> is not in the results file yet.
    It is computed in ${escapeHtml(milestone)}.
  </div>`;
}

// Shown when a button calls a server endpoint that is not built yet.
export function backendMissing(endpoint, milestone, detail) {
  return `<div class="notice warn">
    <strong>Backend arrives in ${escapeHtml(milestone)}.</strong>
    <code>${escapeHtml(endpoint)}</code> is not running yet, so nothing was computed.
    ${detail ? escapeHtml(detail) : ""}
  </div>`;
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
