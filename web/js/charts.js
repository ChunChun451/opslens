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
export const INK = "#16181d";
export const INK_SOFT = "#474b53";
export const GRID = "#e4e4df";
export const ALERT = "#b3122a"; // our red accent; used only for "over capacity" marks

// One colour + line style per policy. The colour follows the policy everywhere.
export const POLICY_STYLE = {
  opslens: { color: "#2a78d6", dash: [] },
  baseline_a: { color: "#eb6834", dash: [10, 6] },
  baseline_b: { color: "#1baf7a", dash: [3, 4] },
};
const OTHER_STYLE = { color: "#6b6e75", dash: [6, 3] };

export function policyStyle(key) {
  return POLICY_STYLE[key] || OTHER_STYLE;
}

// Categorical slots, in fixed order, for charts that are not about policies.
export const SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];

// Big, calm defaults for a projector. Chart is the global from vendor/chart.umd.js.
export function setChartDefaults() {
  Chart.defaults.font.family = '"Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif';
  Chart.defaults.font.size = 16;
  Chart.defaults.color = INK_SOFT;
  Chart.defaults.borderColor = GRID;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.animation.duration = 300;
  Chart.defaults.plugins.legend.labels.boxWidth = 28;
  Chart.defaults.plugins.legend.labels.color = INK;
  Chart.defaults.plugins.tooltip.titleFont = { size: 16, weight: "600" };
  Chart.defaults.plugins.tooltip.bodyFont = { size: 16 };
  Chart.defaults.plugins.tooltip.padding = 10;
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

// Plugin: whiskers for mean ± std on bar charts. A dataset opts in with `errors: [std, ...]`.
export const errorBarsPlugin = {
  id: "errorBars",
  afterDatasetsDraw(chart) {
    const ctx = chart.ctx;
    const yScale = chart.scales.y;
    chart.data.datasets.forEach((dataset, datasetIndex) => {
      if (!dataset.errors) return;
      chart.getDatasetMeta(datasetIndex).data.forEach((bar, i) => {
        const mean = dataset.data[i];
        const err = dataset.errors[i];
        if (typeof mean !== "number" || typeof err !== "number") return;
        const top = yScale.getPixelForValue(mean + err);
        const bottom = yScale.getPixelForValue(mean - err);
        ctx.save();
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(bar.x, top);
        ctx.lineTo(bar.x, bottom);
        ctx.moveTo(bar.x - 8, top);
        ctx.lineTo(bar.x + 8, top);
        ctx.moveTo(bar.x - 8, bottom);
        ctx.lineTo(bar.x + 8, bottom);
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
        ctx.fillStyle = range.color || "rgba(179, 18, 42, 0.10)";
        ctx.fillRect(left, chartArea.top, right - left, chartArea.bottom - chartArea.top);
        if (range.label) {
          ctx.fillStyle = ALERT;
          ctx.font = '600 14px "Segoe UI", system-ui, sans-serif';
          ctx.fillText(range.label, left + 4, chartArea.bottom - 8); // bottom: clear of the data points
        }
      });
      ctx.restore();
    },
  };
}
