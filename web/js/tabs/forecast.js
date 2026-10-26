import { state, teamNames } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, shadeRanges, INK, POLICY_STYLE } from "../charts.js";
import { pageHeader, card, missing, fold, factLine } from "../ui.js";
import { escapeHtml } from "../format.js";

let selectedTeam = null;

export function render(section) {
  const f = state.results.forecast;
  const head = pageHeader("The next 48 hours",
    "How much work is coming to each team, hour by hour, against the people on the roster. Shaded hours: a team will be short.");
  if (!f) {
    section.innerHTML = head + missing("The forecast", "M6");
    return;
  }
  const teams = teamNames();
  const flagged = f.bottlenecks.length ? f.bottlenecks[0].team : null;
  selectedTeam = teams.includes(flagged) ? flagged : teams[0];

  const picker = `<div class="segmented" role="group" aria-label="Team">
      ${teams.map((t) => `<button type="button" data-team="${escapeHtml(t)}">Team ${escapeHtml(t)}</button>`).join("")}
    </div>`;
  section.innerHTML = `${head}
    ${factLine([
      [ev("forecast.wape_model", "frac_pct"), "forecast error"],
      [ev("forecast.wape_naive", "frac_pct"), "error of “same hour last week”"],
      [ev("forecast.coverage_80", "frac_pct"), "of hours inside the 80% range"],
    ])}
    ${card({
      id: "fc-panel",
      title: "Demand vs capacity",
      sub: `${evText("forecast.horizon[0].time", hourLabel(f.horizon[0].time))} to
        ${evText(`forecast.horizon[${f.horizon.length - 1}].time`, hourLabel(f.horizon[f.horizon.length - 1].time))}
        · shaded = bottleneck flagged by the engine (Erlang C on the upper band)`,
      actions: picker,
      body: `<div class="chart lg"><canvas id="fc-chart" aria-label="Forecast demand and capacity"></canvas></div>`,
    })}
    ${alertHitRate()}
    ${fold("Every shortage the engine flagged", bottleneckCard(f), { hint: `${f.bottlenecks.length} windows` })}
    ${fold("How good is the forecast?", `<p>${noiseFloor()}</p>${factLine([
      [ev("forecast.coverage_90", "frac_pct"), "of hours inside the 90% range"],
    ])}`)}`;

  section.querySelectorAll("[data-team]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedTeam = button.dataset.team;
      drawChart(section);
    });
  });
  drawChart(section);
}

function noiseFloor() {
  const d = state.results.details;
  if (d && d.forecast && typeof d.forecast.wape_noise_floor === "number") {
    return `noise floor ${ev("details.forecast.wape_noise_floor", "frac_pct")}: random arrivals, no model can beat it`;
  }
  return "lower is better";
}

function hourLabel(iso) {
  const weekday = new Date(iso).toLocaleDateString("en-GB", { weekday: "short" });
  return weekday + " " + iso.slice(11, 16);
}

function drawChart(section) {
  const f = state.results.forecast;
  section.querySelectorAll("[data-team]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.team === selectedTeam));
  });

  const points = [];
  f.horizon.forEach((p, i) => {
    if (p.team === selectedTeam) points.push({ p, i });
  });
  const ranges = bottleneckRanges(points);

  const datasets = [
    { label: "lo80", data: points.map(({ p }) => p.lo80), borderWidth: 0, pointRadius: 0, fill: false },
    {
      label: "80% interval",
      data: points.map(({ p }) => p.hi80),
      borderWidth: 0,
      backgroundColor: "rgba(42, 120, 214, 0.14)",
      fill: "-1",
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
      stepped: "middle",
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

function isNight(b) {
  const startHour = Number(b.start.slice(11, 13));
  const endHour = Number(b.end.slice(11, 13));
  const sameDay = b.start.slice(0, 10) === b.end.slice(0, 10);
  return sameDay && startHour < 7 && endHour <= 7;
}

function bottleneckRanges(points) {
  const ranges = [];
  state.results.forecast.bottlenecks.forEach((b) => {
    if (b.team !== selectedTeam || isNight(b)) return;
    const inside = points.map(({ p }) => p.time >= b.start && p.time < b.end);
    runsOf(inside, "bottleneck").forEach((r) => {
      ranges.push({ ...r, color: "rgba(194, 43, 51, 0.12)" });
    });
  });
  return ranges;
}

function bottleneckCard(f) {
  if (!f.bottlenecks.length) {
    return card({ title: "Bottlenecks", body: `<p class="muted">No bottleneck flagged in the forecast window.</p>` });
  }
  const first = f.horizon.length ? f.horizon[0].time : "";
  const last = f.horizon.length ? f.horizon[f.horizon.length - 1].time : "";
  const hasGap = f.bottlenecks.some((b) => typeof b.peak_gap_agents === "number");
  const hasRho = f.bottlenecks.some((b) => typeof b.peak_rho === "number");
  const night = f.bottlenecks.filter(isNight).length;
  const rows = f.bottlenecks.map((b, i) => (isNight(b) ? "" : (() => {
    const base = `forecast.bottlenecks[${i}]`;
    const inChart = !(b.end <= first || b.start > last);
    return `<tr>
        <td>${evText(base + ".text")}</td>
        <td>${teamCell(base)}</td>
        ${hasGap ? `<td class="num">${ev(base + ".peak_gap_agents", "num")}</td><td class="num">${ev(base + ".agent_hours_short", "num")}</td>` : ""}
        ${hasRho ? `<td class="num">${ev(base + ".peak_rho", "ratio")}</td>` : ""}
        <td>${inChart ? `<span class="pill">in chart</span>` : ""}</td>
      </tr>`;
  })())).join("");
  return card({
    id: "fc-bottlenecks",
    title: "Bottlenecks flagged by the engine",
    sub: "Hours where the forecast's upper band needs more agents than the roster has",
    body: `<div class="table-wrap"><table>
        <thead><tr><th>Where and when</th><th>Team</th>
          ${hasGap ? `<th class="num">Peak gap (agents)</th><th class="num">Agent-hours short</th>` : ""}
          ${hasRho ? `<th class="num">Peak ρ</th>` : ""}<th></th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      ${night ? `<p class="small muted">${night} night ${night === 1 ? "window" : "windows"} (00:00-07:00) not listed:
        three cross-trained night agents cover every team at night, so staffing plans day hours only.</p>` : ""}`,
  });
}

function alertHitRate() {
  const a = state.results.prediction_baselines && state.results.prediction_baselines.alerts;
  if (!a || !a.rules) return "";
  const r = (rule, who, key) => `prediction_baselines.alerts.rules.${rule}.predictors.${who}.workload.${key}`;
  return `<p class="alert-score">Alerts like these, made one to seven days ahead, came true for
    <strong>${ev(r("erlang_gap", "opslens", "precision"), "frac_pct")}</strong> of alert hours
    (a same-hour-last-week forecast: ${ev(r("erlang_gap", "naive_last_week", "precision"), "frac_pct")}) and caught
    ${ev(r("erlang_gap", "opslens", "recall"), "frac_pct")} of the real shortage hours. The simpler test "work above 85% of the
    agents on shift" is right ${ev(r("rho_085", "opslens", "precision"), "frac_pct")} of the time
    (${ev(r("rho_085", "naive_last_week", "precision"), "frac_pct")}). Cautious by design: better to staff an hour that turns out calm.</p>`;
}

function teamCell(base) {
  return `Team ${evText(base + ".team")}`;
}
