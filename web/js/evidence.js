import { lookup, state, policyLabel, liveSource, LIVE_SOURCES } from "./data.js";
import {
  fmt, fmtSigned, spreadUnit, escapeHtml, definitionFor, kpiInfo, prettyKey, tidyDash,
} from "./format.js";

export function ev(path, unit = "num", options = {}) {
  const value = lookup(path);
  if (value === undefined || value === null) {
    return `<span class="ev-missing" title="Not in the results file: ${escapeHtml(path)}">—</span>`;
  }
  const text = options.signed
    ? fmtSigned(value, unit, options.bare)
    : fmt(value, unit, options.bare);
  const cls = options.key ? "ev key" : "ev";
  const extra = (options.title ? ` data-title="${escapeHtml(options.title)}"` : "")
    + (options.explain ? ` data-explain="${escapeHtml(options.explain)}"` : "");
  return `<button type="button" class="${cls}" data-path="${escapeHtml(path)}" data-unit="${unit}"${extra}>${escapeHtml(text)}</button>`;
}

export function evText(path, display) {
  const value = lookup(path);
  if (value === undefined || value === null || value === "") {
    return "";
  }
  let text = tidyDash(Array.isArray(value) ? value.join(", ") : String(value));
  if (display !== undefined) {
    text = display;
  }
  return escapeHtml(text);
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

export function initEvidence() {
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-path]");
    if (target) {
      openEvidence(target.dataset.path, target.dataset.unit, target.getBoundingClientRect(), target.dataset);
      return;
    }
    if (event.target.closest("canvas") || event.target.closest("#evidence-popover")) {
      if (event.target.closest(".pop-close")) closeEvidence();
      return;
    }
    closeEvidence();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isEvidenceOpen()) {
      closeEvidence();
      event.stopImmediatePropagation();
    }
    if (event.key === "Enter" && event.target.matches("span[data-path]")) {
      const target = event.target;
      openEvidence(target.dataset.path, target.dataset.unit, target.getBoundingClientRect());
    }
  });
  document.getElementById("tab-panels").addEventListener("scroll", closeEvidence);
  window.addEventListener("resize", closeEvidence);
  document.addEventListener("tab-shown", closeEvidence);
}

export function openEvidenceAt(path, unit, x, y) {
  openEvidence(path, unit, { left: x, right: x, top: y, bottom: y });
}

export function openEvidence(path, unit, anchorRect, words = {}) {
  const el = popover();
  el.innerHTML = evidenceHtml(path, unit || "num", lookup(path), words);
  el.hidden = false;
  place(el, anchorRect);
}

function evidenceHtml(path, unit, value, words = {}) {
  let valueText;
  if (typeof value === "number") {
    valueText = fmt(value, unit);
  } else if (Array.isArray(value)) {
    valueText = value.join(", ");
  } else {
    valueText = String(value);
  }
  const lines = spreadLines(path, unit).map((line) => `<li>${line}</li>`).join("");
  const fixtureTag = state.results.meta.fixture ? ' <strong class="pop-fixture">FIXTURE</strong>' : "";
  return `
    <div class="pop-head">
      <span class="pop-title">${escapeHtml(words.title || titleFor(path))}</span>
      <button type="button" class="pop-close" aria-label="Close">×</button>
    </div>
    <div class="pop-value ${unit === "text" ? "is-text" : ""}">${escapeHtml(valueText)}</div>
    ${words.explain || definitionFor(path) ? `<p class="pop-def">${escapeHtml(words.explain || definitionFor(path))}</p>` : ""}
    ${lines ? `<ul class="pop-spread">${lines}</ul>` : ""}
    <div class="pop-source">${escapeHtml(sourceFor(path))}${fixtureTag}
      <code title="${escapeHtml(String(value))}">${escapeHtml(path)}</code></div>`;
}

export function labelFor(path) {
  return titleFor(path);
}

const WHO = { opslens: "OpsLens", priority: "priority field", rule: "rule of thumb", baseline_d: "industry standard",
  baseline_b: "urgent first", baseline_c: "SLA due first", baseline_a: "first come" };

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
  const who = WHO[parts[parts.length - 1]];
  if (who && parts.length > 1) return `${prettyKey(parts[parts.length - 2])} · ${who}`;
  return prettyKey(parts[parts.length - 1]);
}

function sourceFor(path) {
  const live = liveSource(path);
  if (live) {
    return LIVE_SOURCES[live];
  }
  return state.source === "/api/results" ? "From the results file, eval/results.json (make eval)" : state.source;
}

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

  const stress = path.match(/^stress\[(\d+)\]\./);
  if (stress) {
    const row = r.stress[Number(stress[1])];
    if (typeof row.opslens_minus_b === "number") {
      lines.push(`OpsLens − urgent first: ${fmtSigned(row.opslens_minus_b, "pts")} (95% CI `
        + `${fmtSigned(row.ci_low, "pts")} to ${fmtSigned(row.ci_high, "pts")})`);
    }
  }

  const ablation = path.match(/^details\.ablations\[(\d+)\]\./);
  if (ablation && r.details) {
    const row = r.details.ablations[Number(ablation[1])];
    if (typeof row.ci_low === "number") {
      lines.push(`Breach vs full OpsLens: ${fmtSigned(row.delta_breach_vs_full, "pts")} (paired 95% CI `
        + `${fmtSigned(row.ci_low, "pts")} to ${fmtSigned(row.ci_high, "pts")})`);
    }
  }

  const diff = path.match(/^(.*)\.(mean_diff|diff)$/);
  if (diff && !lines.length) {
    const low = lookup(diff[1] + ".ci_low");
    const high = lookup(diff[1] + ".ci_high");
    if (typeof low === "number" && typeof high === "number") {
      lines.push(`95% range: ${fmtSigned(low, unit)} to ${fmtSigned(high, unit)}`);
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
