// charts.js — shared chart settings, colours and two small drawing plugins.
//
// Why: every chart should look the same and be readable on a projector. Colours are the
// first three slots of a palette checked for colour-blind safety (blue, orange, aqua), and
// each policy also gets its own line style, so colour is never the only clue.
// Every chart point is clickable: makeChart() maps the clicked point to its JSON path and
// opens the same evidence popover as the numbers in the text.
//
// Example:
//   makeChart(canvas, config, (datasetIndex, index) =>
//     ({ path: `sim.replay.series.opslens.waiting[${index}]`, unit: "int" }));

import { openEvidenceAt, closeEvidence } from "./evidence.js";

// Ink colours for text, axes and grid (text never wears a series colour).
export const INK = "#0f172a";
export const INK_SOFT = "#5b6b80";
export const GRID = "#edf1f5";
export const ALERT = "#c22b33"; // used only for the "bottleneck" label on the forecast

// One colour + line style per policy. The colour follows the policy everywhere.
// Design v2: OpsLens is the only vivid colour; baselines step back but stay distinguishable
// (and keep their dash patterns, so colour is never the only cue).
export const POLICY_STYLE = {
  opslens: { color: "#3d5afe", dash: [] },
  baseline_a: { color: "#f08a4b", dash: [10, 6] },
  baseline_b: { color: "#8b95a8", dash: [3, 4] },
  baseline_c: { color: "#a78bfa", dash: [6, 3] },
  baseline_d: { color: "#e0a100", dash: [2, 2] },
};
const OTHER_STYLE = { color: "#6b6e75", dash: [6, 3] };

export function policyStyle(key) {
  return POLICY_STYLE[key] || OTHER_STYLE;
}

// Categorical slots, in fixed order, for charts that are not about policies.
export const SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];

// Calm defaults that match the cards: light grid, no axis borders, muted ticks, round
// legend markers. Chart is the global from vendor/chart.umd.js.
// Neon theme (web/neon.css): light ink on dark glass, neon policy colours. Read once at start;
// the theme switch reloads the page, so every chart is drawn in the right colours.
const NEON = document.documentElement.dataset.theme === "neon";
if (NEON) {
  Object.assign(POLICY_STYLE.opslens, { color: "#22d3ee" });
  Object.assign(POLICY_STYLE.baseline_a, { color: "#fb923c" });
  Object.assign(POLICY_STYLE.baseline_b, { color: "#94a3b8" });
  Object.assign(POLICY_STYLE.baseline_c, { color: "#c9c9cc" });
  Object.assign(POLICY_STYLE.baseline_d, { color: "#ff5a5f" });
}

export function setChartDefaults() {
  Chart.defaults.font.family = '"Inter", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif'; // Inter: web/theme.css
  Chart.defaults.font.size = 14;
  Chart.defaults.color = NEON ? "#8d8d94" : INK_SOFT;
  Chart.defaults.borderColor = NEON ? "#232327" : GRID;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.animation.duration = 300;
  Chart.defaults.scale.border.display = false;
  Chart.defaults.scale.grid.color = NEON ? "#1d1d21" : GRID;
  Chart.defaults.scale.ticks.padding = 8;
  Chart.defaults.plugins.legend.align = "start";
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyle = "circle";
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.boxHeight = 8;
  Chart.defaults.plugins.legend.labels.padding = 16;
  Chart.defaults.plugins.legend.labels.color = NEON ? "#c9c9cc" : INK;
  Chart.defaults.plugins.tooltip.backgroundColor = "#0b1322";
  Chart.defaults.plugins.tooltip.titleFont = { size: 14, weight: "600" };
  Chart.defaults.plugins.tooltip.bodyFont = { size: 14 };
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.usePointStyle = true;
}

// Create a chart (replacing any old one on the same canvas) and make its points clickable.
// `evidenceFor(datasetIndex, index)` returns { path, unit } for the clicked point, or null.
export function makeChart(canvas, config, evidenceFor) {
  const old = Chart.getChart(canvas);
  if (old) {
    old.destroy();
  }
  config.options = config.options || {};
  config.options.onClick = (event, elements, chart) => {
    const hits = chart.getElementsAtEventForMode(event, "nearest", { intersect: false }, true);
    if (!hits.length || !evidenceFor) {
      closeEvidence();
      return;
    }
    const target = evidenceFor(hits[0].datasetIndex, hits[0].index);
    if (target) {
      openEvidenceAt(target.path, target.unit, event.native.clientX, event.native.clientY);
    }
  };
  config.options.onHover = (event, elements) => {
    event.native.target.style.cursor = elements.length ? "pointer" : "default";
  };
  return new Chart(canvas, config);
}

// Plugin: whiskers on bar charts. A dataset opts in with either
//   errors: [std, ...]          -> whisker from mean − std to mean + std
//   ranges: [[low, high], ...]  -> whisker from low to high (a 95% CI)
// Works for vertical bars and for horizontal bars (indexAxis: "y").
export const errorBarsPlugin = {
  id: "errorBars",
  afterDatasetsDraw(chart) {
    const ctx = chart.ctx;
    const horizontal = chart.options.indexAxis === "y";
    const valueScale = horizontal ? chart.scales.x : chart.scales.y;
    chart.data.datasets.forEach((dataset, datasetIndex) => {
      if (!dataset.errors && !dataset.ranges) return;
      chart.getDatasetMeta(datasetIndex).data.forEach((bar, i) => {
        let low;
        let high;
        if (dataset.ranges) {
          if (!dataset.ranges[i]) return;
          [low, high] = dataset.ranges[i];
        } else {
          const mean = dataset.data[i];
          const err = dataset.errors[i];
          if (typeof mean !== "number" || typeof err !== "number") return;
          low = mean - err;
          high = mean + err;
        }
        const a = valueScale.getPixelForValue(low);
        const b = valueScale.getPixelForValue(high);
        ctx.save();
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2;
        ctx.beginPath();
        if (horizontal) {
          ctx.moveTo(a, bar.y);
          ctx.lineTo(b, bar.y);
          ctx.moveTo(a, bar.y - 6);
          ctx.lineTo(a, bar.y + 6);
          ctx.moveTo(b, bar.y - 6);
          ctx.lineTo(b, bar.y + 6);
        } else {
          ctx.moveTo(bar.x, a);
          ctx.lineTo(bar.x, b);
          ctx.moveTo(bar.x - 8, a);
          ctx.lineTo(bar.x + 8, a);
          ctx.moveTo(bar.x - 8, b);
          ctx.lineTo(bar.x + 8, b);
        }
        ctx.stroke();
        ctx.restore();
      });
    });
  },
};

// Plugin maker: shade ranges of x positions behind the data (bottleneck hours on the forecast).
// shadeRanges([{ from: 3, to: 5, label: "over capacity", color: "rgba(...)" }])
// The ranges are passed in directly, not through Chart.js options: Chart.js runs its options
// through a resolver that fills in defaults for known names, which would change our values.
export function shadeRanges(ranges) {
  return {
    id: "shadeRanges",
    beforeDatasetsDraw(chart) {
      if (!ranges.length) return;
      const { ctx, chartArea } = chart;
      const xScale = chart.scales.x;
      const halfStep = (xScale.getPixelForValue(1) - xScale.getPixelForValue(0)) / 2;
      ctx.save();
      ranges.forEach((range) => {
        const left = Math.max(chartArea.left, xScale.getPixelForValue(range.from) - halfStep);
        const right = Math.min(chartArea.right, xScale.getPixelForValue(range.to) + halfStep);
        ctx.fillStyle = range.color || "rgba(194, 43, 51, 0.08)";
        ctx.fillRect(left, chartArea.top, right - left, chartArea.bottom - chartArea.top);
        if (range.label) {
          ctx.fillStyle = ALERT;
          ctx.font = '600 13px "Segoe UI", system-ui, sans-serif';
          ctx.fillText(range.label, left + 4, chartArea.bottom - 8); // bottom: clear of the data points
        }
      });
      ctx.restore();
    },
  };
}
