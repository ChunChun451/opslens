// tabs/forecast.js — the forecast horizon (48 h): demand with its 80% band vs capacity.
//
// Why: "predict bottlenecks" means showing WHEN a team will run out of capacity, with honest
// uncertainty. The band is the split-conformal 80% interval. The engine's bottleneck windows
// (Erlang C on the upper band) are shaded red and listed below.
//
// Example (real results, Team B, Sat 24 Oct 18:00-23:00): shaded "bottleneck", listed as
// "Team B short by up to 5.2 agents", 19.9 agent-hours short in total.

import { state, teamNames } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, shadeRanges, INK, POLICY_STYLE } from "../charts.js";
import { pageHeader, card, stat, missing } from "../ui.js";
import { escapeHtml } from "../format.js";

let selectedTeam = null;

export function render(section) {
  const f = state.results.forecast;
  const head = pageHeader("Forecast",
    "Work arriving per hour for each team, with the 80% conformal band, against the agent-hours on the roster.");
  if (!f) {
    section.innerHTML = head + missing("The forecast", "M6");
    return;
  }
  const teams = teamNames();
  // Start on the team the engine flagged first, so the demo opens on the interesting chart.
  const flagged = f.bottlenecks.length ? f.bottlenecks[0].team : null;
  selectedTeam = teams.includes(flagged) ? flagged : teams[0];

  const picker = `<div class="segmented" role="group" aria-label="Team">
      ${teams.map((t) => `<button type="button" data-team="${escapeHtml(t)}">Team ${escapeHtml(t)}</button>`).join("")}
    </div>`;
  section.innerHTML = `${head}
    <div class="grid cols-4 stretch">
      ${card({ body: stat("Forecast error (WAPE)", ev("forecast.wape_model", "frac_pct"), noiseFloor()) })}
      ${card({ body: stat("Seasonal-naive error", ev("forecast.wape_naive", "frac_pct"), "same hour last week (the baseline to beat)") })}
      ${card({ body: stat("80% band coverage", ev("forecast.coverage_80", "frac_pct"), "should be close to 80%") })}
      ${card({ body: stat("90% band coverage", ev("forecast.coverage_90", "frac_pct"), "should be close to 90%") })}
    </div>
    ${card({
      id: "fc-panel",
      title: "Demand vs capacity",
      sub: `${evText("forecast.horizon[0].time", hourLabel(f.horizon[0].time))} to
        ${evText(`forecast.horizon[${f.horizon.length - 1}].time`, hourLabel(f.horizon[f.horizon.length - 1].time))}
        · shaded = bottleneck flagged by the engine (Erlang C on the upper band)`,
      actions: picker,
      body: `<div class="chart lg"><canvas id="fc-chart" aria-label="Forecast demand and capacity"></canvas></div>`,
    })}
    ${bottleneckCard(f)}`;

  section.querySelectorAll("[data-team]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedTeam = button.dataset.team;
      drawChart(section);
    });
  });
  drawChart(section);
}

// The WAPE no forecast can beat (random arrivals), when the engine reports it.
function noiseFloor() {
  const d = state.results.details;
  if (d && d.forecast && typeof d.forecast.wape_noise_floor === "number") {
    return `noise floor ${ev("details.forecast.wape_noise_floor", "frac_pct")}: random arrivals, no model can beat it`;
  }
  return "lower is better";
}

// "2026-10-26T19:00" -> "Mon 19:00" (the look only; the popover keeps the raw time)
function hourLabel(iso) {
  const weekday = new Date(iso).toLocaleDateString("en-GB", { weekday: "short" });
  return weekday + " " + iso.slice(11, 16);
}

function drawChart(section) {
  const f = state.results.forecast;
  section.querySelectorAll("[data-team]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.team === selectedTeam));
  });

  // Keep each point's index in the full horizon list, so clicks map to the right JSON path.
  const points = [];
  f.horizon.forEach((p, i) => {
    if (p.team === selectedTeam) points.push({ p, i });
  });
  // Only the engine's bottleneck windows are shaded: they use Erlang C (waiting time), which is
  // stricter and more meaningful than "band above capacity" for a single hour.
  const ranges = bottleneckRanges(points);

  const datasets = [
    { label: "lo80", data: points.map(({ p }) => p.lo80), borderWidth: 0, pointRadius: 0, fill: false },
    {
      label: "80% interval",
      data: points.map(({ p }) => p.hi80),
      borderWidth: 0,
      backgroundColor: "rgba(42, 120, 214, 0.14)",
      fill: "-1", // fill down to the lo80 line = the band
      pointRadius: 0,
    },
    {
      label: "Forecast demand",
      data: points.map(({ p }) => p.demand_hours),
      borderColor: POLICY_STYLE.opslens.color,
      borderWidth: 2.5,
      pointRadius: 0,
      tension: 0.3,
    },
    {
      label: "Capacity",
      data: points.map(({ p }) => p.capacity_hours),
      borderColor: INK,
      borderWidth: 1.5,
      borderDash: [6, 4],
      pointRadius: 0,
      stepped: "middle", // capacity changes in whole hours: draw it as steps
    },
  ];
  const fields = ["lo80", "hi80", "demand_hours", "capacity_hours"];
  if (points.some(({ p }) => typeof p.actual_hours === "number")) {
    datasets.push({
      label: "Actual",
      data: points.map(({ p }) => p.actual_hours),
      borderColor: "#eb6834",
      borderWidth: 1.5,
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
        x: { ticks: { maxTicksLimit: 9, maxRotation: 0 }, grid: { display: false } },
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
      ranges.push({ ...r, color: "rgba(194, 43, 51, 0.12)" });
    });
  });
  return ranges;
}

// Every bottleneck the engine flagged, biggest first, with the ones inside the chart marked.
function bottleneckCard(f) {
  if (!f.bottlenecks.length) {
    return card({ title: "Bottlenecks", body: `<p class="muted">No bottleneck flagged in the forecast window.</p>` });
  }
  const first = f.horizon.length ? f.horizon[0].time : "";
  const last = f.horizon.length ? f.horizon[f.horizon.length - 1].time : "";
  // Older results gave peak_rho; the real engine gives the agent gap instead. Show what exists.
  const hasGap = f.bottlenecks.some((b) => typeof b.peak_gap_agents === "number");
  const hasRho = f.bottlenecks.some((b) => typeof b.peak_rho === "number");
  const rows = f.bottlenecks.map((b, i) => {
    const base = `forecast.bottlenecks[${i}]`;
    const inChart = !(b.end <= first || b.start > last);
    return `<tr>
        <td>${evText(base + ".text")}</td>
        <td>${teamCell(base)}</td>
        ${hasGap ? `<td class="num">${ev(base + ".peak_gap_agents", "num")}</td><td class="num">${ev(base + ".agent_hours_short", "num")}</td>` : ""}
        ${hasRho ? `<td class="num">${ev(base + ".peak_rho", "ratio")}</td>` : ""}
        <td>${inChart ? `<span class="pill">in chart</span>` : ""}</td>
      </tr>`;
  }).join("");
  return card({
    id: "fc-bottlenecks",
    title: "Bottlenecks flagged by the engine",
    sub: "Hours where the forecast's upper band needs more agents than the roster has",
    body: `<div class="table-wrap"><table>
        <thead><tr><th>Where and when</th><th>Team</th>
          ${hasGap ? `<th class="num">Peak gap (agents)</th><th class="num">Agent-hours short</th>` : ""}
          ${hasRho ? `<th class="num">Peak ρ</th>` : ""}<th></th></tr></thead>
        <tbody>${rows}</tbody></table></div>`,
  });
}

function teamCell(base) {
  return `Team ${evText(base + ".team")}`;
}
