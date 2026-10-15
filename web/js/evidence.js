// evidence.js — click any number to see where it came from.
//
// Why: our second moat is trust. Every number on screen is drawn by ev() (or evText() for
// text that contains numbers). ev() reads the value from the JSON itself, so a call site can
// never pass in a made-up number, and it stamps the JSON path on the element. One click
// listener opens a popover with the path, the value, its spread or CI, and a definition.
//
// Example:
//   ev("sim.policies.opslens.kpis.turnaround.breach_pct.mean", "pct")
//   -> <button class="ev" data-path="sim.policies.opslens.kpis.turnaround.breach_pct.mean"
//              data-unit="pct">4.1%</button>
//   Clicking it shows "± 0.3 pts" and "OpsLens − Baseline A: −8.9 pts (95% CI −9.7 to −8.1)".

import { lookup, state, policyLabel } from "./data.js";
import {
  fmt, fmtSigned, spreadUnit, escapeHtml, definitionFor, kpiInfo, prettyKey,
} from "./format.js";

// HTML for one clickable number.
// options.signed shows "+0.8" / "−8.9"; options.bare drops the unit (the header names it).
export function ev(path, unit = "num", options = {}) {
  const value = lookup(path);
  if (value === undefined || value === null) {
    return `<span class="ev-missing" title="Not in the results file: ${escapeHtml(path)}">—</span>`;
  }
  const text = options.signed
    ? fmtSigned(value, unit, options.bare)
    : fmt(value, unit, options.bare);
  return `<button type="button" class="ev" data-path="${escapeHtml(path)}" data-unit="${unit}">${escapeHtml(text)}</button>`;
}

// HTML for a text value from the JSON (titles, ticket texts, times). Also clickable, because
// many of these texts contain numbers ("wait 302 min vs 47 min").
// `display` replaces the shown text (e.g. "Yes" for true); the popover still shows the raw value.
// A <span role="button"> (not a <button>) so long texts wrap inside a sentence like normal
// text; tabindex + the Enter key handler in initEvidence keep it usable from the keyboard.
export function evText(path, display) {
  const value = lookup(path);
  if (value === undefined || value === null || value === "") {
    return "";
  }
  let text = Array.isArray(value) ? value.join(", ") : String(value);
  if (display !== undefined) {
    text = display;
  }
  return `<span class="ev-text" role="button" tabindex="0" data-path="${escapeHtml(path)}" data-unit="text">${escapeHtml(text)}</span>`;
}

function popover() {
  return document.getElementById("evidence-popover");
}

export function isEvidenceOpen() {
  return !popover().hidden;
}

export function closeEvidence() {
  popover().hidden = true;
}

// One listener for the whole page (event delegation), so tabs never wire up their own.
export function initEvidence() {
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-path]");
    if (target) {
      openEvidence(target.dataset.path, target.dataset.unit, target.getBoundingClientRect());
      return;
    }
    // Clicks on charts are handled by the chart itself (charts.js); clicks inside the
    // popover keep it open; anything else closes it.
    if (event.target.closest("canvas") || event.target.closest("#evidence-popover")) {
      if (event.target.closest(".pop-close")) closeEvidence();
      return;
    }
    closeEvidence();
  });
  // Esc closes the popover first. stopImmediatePropagation keeps story mode (which also
  // listens for Esc, and is set up after this) from closing on the same key press.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isEvidenceOpen()) {
      closeEvidence();
      event.stopImmediatePropagation();
    }
    // Text values are spans, so Enter does not "click" them by itself.
    if (event.key === "Enter" && event.target.matches("span[data-path]")) {
      const target = event.target;
      openEvidence(target.dataset.path, target.dataset.unit, target.getBoundingClientRect());
    }
  });
  // The popover is placed once; close it instead of letting it drift away from its number.
  document.getElementById("tab-panels").addEventListener("scroll", closeEvidence);
  window.addEventListener("resize", closeEvidence);
  document.addEventListener("tab-shown", closeEvidence);
}

// Open the popover for a chart point clicked at screen position (x, y).
export function openEvidenceAt(path, unit, x, y) {
  openEvidence(path, unit, { left: x, right: x, top: y, bottom: y });
}

export function openEvidence(path, unit, anchorRect) {
  const el = popover();
  el.innerHTML = evidenceHtml(path, unit || "num", lookup(path));
  el.hidden = false;
  place(el, anchorRect);
}

function evidenceHtml(path, unit, value) {
  let valueText;
  if (typeof value === "number") {
    valueText = fmt(value, unit);
  } else if (Array.isArray(value)) {
    valueText = value.join(", ");
  } else {
    valueText = String(value);
  }
  const raw = typeof value === "number" && String(value) !== valueText
    ? `<span class="pop-raw">raw ${escapeHtml(String(value))}</span>`
    : "";
  const lines = spreadLines(path, unit).map((line) => `<li>${line}</li>`).join("");
  const fixtureTag = state.results.meta.fixture ? ' <strong class="pop-fixture">FIXTURE</strong>' : "";
  return `
    <div class="pop-head">
      <span class="pop-title">${escapeHtml(titleFor(path))}</span>
      <button type="button" class="pop-close" aria-label="Close">×</button>
    </div>
    <div class="pop-value ${unit === "text" ? "is-text" : ""}">${escapeHtml(valueText)} ${raw}</div>
    ${lines ? `<ul class="pop-spread">${lines}</ul>` : ""}
    <p class="pop-def">${escapeHtml(definitionFor(path))}</p>
    <div class="pop-path"><span>JSON path</span><code>${escapeHtml(path)}</code></div>
    <div class="pop-source">Source: ${escapeHtml(sourceFor(path))}${fixtureTag}</div>`;
}

// A readable name for a path ("SLA breach rate · OpsLens"), used as the popover title
// and wherever a list of paths is shown (the brief's numbers).
export function labelFor(path) {
  return titleFor(path);
}

function titleFor(path) {
  const kpi = path.match(/^sim\.policies\.([^.]+)\.kpis\.(.+)\.(mean|std)$/);
  if (kpi) {
    const spread = kpi[3] === "std" ? " (spread)" : "";
    return kpiInfo(kpi[2]).label + " · " + policyLabel(kpi[1]) + spread;
  }
  const cmp = path.match(/^sim\.comparisons\[(\d+)\]/);
  if (cmp) {
    const c = state.results.sim.comparisons[Number(cmp[1])];
    return kpiInfo(c.kpi).label + ": " + policyLabel(c.policy) + " − " + policyLabel(c.baseline);
  }
  const whatif = path.match(/^whatif\.all_policies\.([^.]+)\.(.+)$/);
  if (whatif) {
    return kpiInfo(whatif[2]).label + " · " + policyLabel(whatif[1]) + " (What-if)";
  }
  const replay = path.match(/^sim\.replay\.series\.([^.]+)\./);
  if (replay) {
    return policyLabel(replay[1]) + " · replay";
  }
  const parts = path.replace(/\[\d+\]/g, "").split(".").filter((p) => p !== "mean" && p !== "std");
  return prettyKey(parts[parts.length - 1]);
}

function sourceFor(path) {
  if (path.startsWith("whatif.")) {
    return "POST /api/whatif (live simulation)";
  }
  return state.source;
}

// Extra lines under the value: spread across seeds, paired CIs, forecast interval, action effect.
// Every value here is read from the JSON too.
function spreadLines(path, unit) {
  const lines = [];
  const r = state.results;

  if (path.endsWith(".mean")) {
    const std = lookup(path.slice(0, -".mean".length) + ".std");
    if (typeof std === "number") {
      lines.push(`Spread across seeds: ± ${fmt(std, spreadUnit(unit))} (standard deviation)`);
    }
  }

  const kpi = path.match(/^sim\.policies\.([^.]+)\.kpis\.(.+)\.mean$/);
  if (kpi && r.sim) {
    r.sim.comparisons.forEach((c) => {
      const involved = c.policy === kpi[1] || c.baseline === kpi[1];
      if (c.kpi === kpi[2] && involved) {
        lines.push(ciLine(c, spreadUnit(unit)));
      }
    });
  }

  const cmp = path.match(/^sim\.comparisons\[(\d+)\]/);
  if (cmp && r.sim) {
    const c = r.sim.comparisons[Number(cmp[1])];
    lines.push(ciLine(c, spreadUnit(kpiInfo(c.kpi).unit)));
  }

  const point = path.match(/^forecast\.horizon\[(\d+)\]\./);
  if (point && r.forecast) {
    const p = r.forecast.horizon[Number(point[1])];
    lines.push(`Team ${escapeHtml(p.team)}, ${escapeHtml(p.time)}`);
    lines.push(`80% interval ${fmt(p.lo80, "hours")} to ${fmt(p.hi80, "hours")}; capacity ${fmt(p.capacity_hours, "hours")}`);
  }

  // Stress rows: OpsLens − Baseline B with its 95% CI, from the same row.
  const stress = path.match(/^stress\[(\d+)\]\./);
  if (stress) {
    const row = r.stress[Number(stress[1])];
    if (typeof row.opslens_minus_b === "number") {
      lines.push(`OpsLens − Baseline B: ${fmtSigned(row.opslens_minus_b, "pts")} (95% CI `
        + `${fmtSigned(row.ci_low, "pts")} to ${fmtSigned(row.ci_high, "pts")})`);
    }
  }

  // Ablation rows with CIs (details.ablations): the effect of removing one part.
  const ablation = path.match(/^details\.ablations\[(\d+)\]\./);
  if (ablation && r.details) {
    const row = r.details.ablations[Number(ablation[1])];
    if (typeof row.ci_low === "number") {
      lines.push(`Breach vs full OpsLens: ${fmtSigned(row.delta_breach_vs_full, "pts")} (paired 95% CI `
        + `${fmtSigned(row.ci_low, "pts")} to ${fmtSigned(row.ci_high, "pts")})`);
    }
  }

  const ticket = path.match(/^risk\.at_risk\[(\d+)\]\.probability$/);
  if (ticket && r.risk) {
    const t = r.risk.at_risk[Number(ticket[1])];
    if (typeof t.probability_after_action === "number") {
      lines.push(`If we "${escapeHtml(t.action)}": ${fmt(t.probability_after_action, "frac_pct")}`);
    }
  }
  return lines;
}

function ciLine(c, unit) {
  return `${escapeHtml(policyLabel(c.policy))} − ${escapeHtml(policyLabel(c.baseline))}: `
    + `${fmtSigned(c.mean_diff, unit)} (paired 95% CI ${fmtSigned(c.ci_low, unit)} to `
    + `${fmtSigned(c.ci_high, unit)}, n = ${c.n} seeds)`;
}

// Put the popover under its number, or above it when there is more room there.
// It never goes under the FIXTURE banner (the banner must stay visible) or off screen.
function place(el, rect) {
  const margin = 12;
  const width = el.offsetWidth;
  const height = el.offsetHeight;
  const banner = document.getElementById("fixture-banner");
  const minTop = (banner.hidden ? 0 : banner.getBoundingClientRect().bottom) + margin;

  const spaceBelow = window.innerHeight - rect.bottom;
  const spaceAbove = rect.top - minTop;
  let top = rect.bottom + 8;
  if (spaceBelow < height + 8 && spaceAbove > spaceBelow) {
    top = rect.top - height - 8;
  }
  top = Math.min(top, window.innerHeight - height - margin);
  top = Math.max(top, minTop);

  let left = rect.left;
  if (left + width > window.innerWidth - margin) {
    left = window.innerWidth - width - margin;
  }
  el.style.left = Math.max(margin, left) + "px";
  el.style.top = top + "px";
}
