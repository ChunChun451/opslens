// tabs/forecast.js — the forecast horizon (48 h): demand with its 80% band vs capacity.
//
// Why: "predict bottlenecks" means showing WHEN a team will run out of capacity, with honest
// uncertainty. The band is the split-conformal 80% interval. Hours where the top of the band
// (hi80) is above capacity are shaded red; the engine's own bottleneck windows are listed
// below and shaded too when they fall inside the 48 hours.
//
// Example (fixture, Team C, Tue 20:00): demand 4.14 agent-hours, band 3.31–4.96,
// capacity 4.5 -> hi80 above capacity -> shaded "over capacity".

import { state, teamNames } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, shadeRanges, INK, ALERT, POLICY_STYLE } from "../charts.js";
import { missing } from "../ui.js";
import { escapeHtml } from "../format.js";

let selectedTeam = null;

export function render(section) {
  const f = state.results.forecast;
  const head = `<div class="tab-head"><div>
      <h2>Forecast</h2>
      <p>Agent-hours of work arriving per hour over the forecast horizon, with the 80% conformal
         band. Red = the top of the band is above capacity.</p>
    </div></div>`;
  if (!f) {
    section.innerHTML = head + missing("The forecast", "M6");
    return;
  }
  const teams = teamNames();
  // Start on the team the engine flagged first, so the demo opens on the interesting chart.
  const flagged = f.bottlenecks.length ? f.bottlenecks[0].team : null;
  selectedTeam = teams.includes(flagged) ? flagged : teams[0];

  section.innerHTML = `${head}
    <div class="grid-4">
      <div class="panel"><div class="tile-label">WAPE, our model (test days)</div>
        <div class="tile-value">${ev("forecast.wape_model", "frac_pct")}</div>
        <div class="tile-sub">lower is better</div></div>
      <div class="panel"><div class="tile-label">WAPE, seasonal-naive baseline</div>
        <div class="tile-value">${ev("forecast.wape_naive", "frac_pct")}</div>
        <div class="tile-sub">same hour last week</div></div>
      <div class="panel"><div class="tile-label">80% interval coverage</div>
        <div class="tile-value">${ev("forecast.coverage_80", "frac_pct")}</div>
        <div class="tile-sub">should be close to 80%</div></div>
      <div class="panel"><div class="tile-label">90% interval coverage</div>
        <div class="tile-value">${ev("forecast.coverage_90", "frac_pct")}</div>
        <div class="tile-sub">should be close to 90%</div></div>
    </div>
    <div class="panel" id="fc-panel">
      <div class="tab-head">
        <h3 id="fc-title"></h3>
        <div class="btn-row" role="group" aria-label="Team">
          ${teams.map((t) => `<button type="button" class="btn btn-small" data-team="${escapeHtml(t)}">Team ${escapeHtml(t)}</button>`).join("")}
        </div>
      </div>
      <div class="chart-box tall"><canvas id="fc-chart" aria-label="Forecast demand and capacity"></canvas></div>
      <p class="panel-note">Horizon ${evText("forecast.horizon[0].time")} to
        ${evText(`forecast.horizon[${f.horizon.length - 1}].time`)}.
        Click any point to see its numbers and its JSON path.</p>
    </div>
    ${bottleneckPanel(f)}`;

  section.querySelectorAll("[data-team]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedTeam = button.dataset.team;
      drawChart(section);
    });
  });
  drawChart(section);
}

// "2026-10-26T19:00" -> "Mon 19:00"
function hourLabel(iso) {
  const weekday = new Date(iso).toLocaleDateString("en-GB", { weekday: "short" });
  return weekday + " " + iso.slice(11, 16);
}

function drawChart(section) {
  const f = state.results.forecast;
  section.querySelector("#fc-title").textContent = "Team " + selectedTeam + ": demand vs capacity";
  section.querySelectorAll("[data-team]").forEach((button) => {
    const active = button.dataset.team === selectedTeam;
    button.classList.toggle("btn-primary", active);
    button.setAttribute("aria-pressed", String(active));
  });

  // Keep each point's index in the full horizon list, so clicks map to the right JSON path.
  const points = [];
  f.horizon.forEach((p, i) => {
    if (p.team === selectedTeam) points.push({ p, i });
  });
  const over = points.map(({ p }) => p.hi80 > p.capacity_hours);
  const ranges = runsOf(over, "over capacity").concat(bottleneckRanges(points));

  const datasets = [
    { label: "lo80", data: points.map(({ p }) => p.lo80), borderWidth: 0, pointRadius: 0, fill: false },
    {
      label: "80% interval",
      data: points.map(({ p }) => p.hi80),
      borderWidth: 0,
      backgroundColor: "rgba(42, 120, 214, 0.18)",
      fill: "-1", // fill down to the lo80 line = the band
      pointRadius: over.map((isOver) => (isOver ? 6 : 0)),
      pointBackgroundColor: ALERT,
    },
    {
      label: "Forecast demand",
      data: points.map(({ p }) => p.demand_hours),
      borderColor: POLICY_STYLE.opslens.color,
      borderWidth: 2,
      pointRadius: 0,
    },
    {
      label: "Capacity",
      data: points.map(({ p }) => p.capacity_hours),
      borderColor: INK,
      borderWidth: 2,
      borderDash: [8, 5],
      pointRadius: 0,
    },
  ];
  const fields = ["lo80", "hi80", "demand_hours", "capacity_hours"];
  if (points.some(({ p }) => typeof p.actual_hours === "number")) {
    datasets.push({
      label: "Actual",
      data: points.map(({ p }) => p.actual_hours),
      borderColor: "#eb6834",
      borderWidth: 2,
      pointRadius: 0,
    });
    fields.push("actual_hours");
  }

  makeChart(section.querySelector("#fc-chart"), {
    type: "line",
    data: { labels: points.map(({ p }) => hourLabel(p.time)), datasets },
    options: {
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 12, maxRotation: 0 }, grid: { display: false } },
        y: { beginAtZero: true, title: { display: true, text: "agent-hours per hour" } },
      },
      plugins: {
        legend: { labels: { filter: (item) => item.text !== "lo80" } },
        tooltip: { filter: (item) => item.dataset.label !== "lo80" },
      },
    },
    plugins: [shadeRanges(ranges)],
  }, (datasetIndex, index) => ({
    path: `forecast.horizon[${points[index].i}].${fields[datasetIndex]}`,
    unit: "hours",
  }));
}

// [false, true, true, false] -> [{ from: 1, to: 2, label }]
function runsOf(flags, label) {
  const ranges = [];
  let start = -1;
  flags.forEach((flag, i) => {
    if (flag && start < 0) start = i;
    if (!flag && start >= 0) {
      ranges.push({ from: start, to: i - 1, label });
      start = -1;
    }
  });
  if (start >= 0) ranges.push({ from: start, to: flags.length - 1, label });
  return ranges;
}

// The engine's bottleneck windows for this team that fall inside the chart.
// ISO strings of the same format compare correctly as text.
function bottleneckRanges(points) {
  const ranges = [];
  state.results.forecast.bottlenecks.forEach((b) => {
    if (b.team !== selectedTeam) return;
    const inside = points.map(({ p }) => p.time >= b.start && p.time < b.end);
    runsOf(inside, "bottleneck").forEach((r) => {
      ranges.push({ ...r, color: "rgba(179, 18, 42, 0.18)" });
    });
  });
  return ranges;
}

function bottleneckPanel(f) {
  if (!f.bottlenecks.length) {
    return `<div class="panel"><h3>Bottlenecks</h3><p class="muted">No bottleneck flagged in the forecast window.</p></div>`;
  }
  const first = f.horizon.length ? f.horizon[0].time : "";
  const last = f.horizon.length ? f.horizon[f.horizon.length - 1].time : "";
  const items = f.bottlenecks.map((b, i) => {
    const base = `forecast.bottlenecks[${i}]`;
    const outside = b.end <= first || b.start > last;
    return `<li>
        <strong>${evText(base + ".text")}</strong>
        <div class="small muted">Team ${evText(base + ".team")} · ${evText(base + ".start")} to ${evText(base + ".end")}
          · peak ρ ${ev(base + ".peak_rho", "ratio")}
          ${outside ? " · outside the chart window" : ""}</div>
      </li>`;
  }).join("");
  return `<div class="panel" id="fc-bottlenecks"><h3>Bottlenecks flagged by the engine</h3><ul class="plain-list">${items}</ul></div>`;
}
