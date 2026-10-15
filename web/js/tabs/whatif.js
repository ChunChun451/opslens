// tabs/whatif.js — the judges' turn: change staffing or volume and re-run the simulator.
//
// Why: moat number three, "touch it". A judge picks a test day, adds or removes agents per
// team, scales the volume and picks a policy; the server (M10, opslens/whatif.py) simulates
// that day and answers in a few seconds. Until then the panel says clearly that the backend
// is not there, and shows the exact request it would send.
//
// Example request: { "day": 48, "policy": "opslens", "volume_factor": 1.25,
//                    "agents_delta": { "A": 0, "B": 0, "C": 2, "D": -2 } }
// Expected answer (proposed for M10): { "kpis": { "turnaround.breach_pct": 5.2, ... } }

import { state, policyKeys, policyLabel, teamNames } from "../data.js";
import { ev } from "../evidence.js";
import { backendMissing, postJson } from "../ui.js";
import { escapeHtml, kpiInfo } from "../format.js";

// Slider ranges. These are input limits for the judge, not results.
const AGENT_DELTA_LIMIT = 5;
const VOLUME_MIN = 0.5;
const VOLUME_MAX = 2;

export function render(section) {
  const meta = state.results.meta;
  const days = [];
  for (let day = meta.test_days[0]; day <= meta.test_days[1]; day++) {
    days.push(day);
  }
  const replayDay = state.results.sim && state.results.sim.replay ? state.results.sim.replay.day : days[0];
  const teams = teamNames();
  const policies = policyKeys();

  section.innerHTML = `
    <div class="tab-head"><div>
      <h2>What-if</h2>
      <p>Change the staffing or the volume for one held-out day and re-run the fair simulator.</p>
    </div></div>
    <div class="panel" id="whatif-form">
      <div class="form-grid">
        <label>Test day
          <select id="wi-day">${days.map((d) => `<option value="${d}" ${d === replayDay ? "selected" : ""}>Day ${d}</option>`).join("")}</select>
        </label>
        <label>Policy
          <select id="wi-policy">${policies.map((k) => `<option value="${escapeHtml(k)}" ${k === "opslens" ? "selected" : ""}>${escapeHtml(policyLabel(k))}</option>`).join("")}</select>
        </label>
        <label>Volume <span class="slider-value" id="wi-volume-value"></span>
          <input type="range" id="wi-volume" min="${VOLUME_MIN}" max="${VOLUME_MAX}" step="0.05" value="1">
        </label>
      </div>
      <h3 style="margin-top: 18px">Agents per team (change from the normal schedule)</h3>
      <div class="form-grid">
        ${teams.map((t) => `<label>Team ${escapeHtml(t)} <span class="slider-value" id="wi-team-${escapeHtml(t)}-value"></span>
          <input type="range" data-team="${escapeHtml(t)}" min="${-AGENT_DELTA_LIMIT}" max="${AGENT_DELTA_LIMIT}" step="1" value="0">
        </label>`).join("")}
      </div>
      <div class="btn-row" style="margin-top: 18px">
        <button type="button" class="btn btn-primary" id="wi-run">Run simulation</button>
        <button type="button" class="btn" id="wi-reset">Reset</button>
      </div>
      <div id="whatif-result" style="margin-top: 16px"></div>
      <details style="margin-top: 12px">
        <summary class="small">Request sent to the server</summary>
        <pre id="wi-request"></pre>
      </details>
    </div>`;

  section.querySelectorAll("input[type=range]").forEach((input) => {
    input.addEventListener("input", () => updateLabels(section));
  });
  section.querySelector("#wi-run").addEventListener("click", () => run(section));
  section.querySelector("#wi-reset").addEventListener("click", () => {
    section.querySelector("#wi-volume").value = "1";
    section.querySelectorAll("input[data-team]").forEach((input) => { input.value = "0"; });
    section.querySelector("#whatif-result").innerHTML = "";
    updateLabels(section);
  });
  updateLabels(section);
}

function buildRequest(section) {
  const agentsDelta = {};
  section.querySelectorAll("input[data-team]").forEach((input) => {
    agentsDelta[input.dataset.team] = Number(input.value);
  });
  return {
    day: Number(section.querySelector("#wi-day").value),
    policy: section.querySelector("#wi-policy").value,
    volume_factor: Number(section.querySelector("#wi-volume").value),
    agents_delta: agentsDelta,
  };
}

// Show the slider values in words next to each slider, and the request preview.
function updateLabels(section) {
  const request = buildRequest(section);
  section.querySelector("#wi-volume-value").textContent = "×" + request.volume_factor.toFixed(2);
  Object.keys(request.agents_delta).forEach((team) => {
    const delta = request.agents_delta[team];
    const text = delta === 0 ? "no change" : (delta > 0 ? "+" : "−") + Math.abs(delta) + " agents";
    section.querySelector(`#wi-team-${team}-value`).textContent = text;
  });
  section.querySelector("#wi-request").textContent = "POST /api/whatif\n" + JSON.stringify(request, null, 2);
}

async function run(section) {
  const result = section.querySelector("#whatif-result");
  const button = section.querySelector("#wi-run");
  button.disabled = true;
  result.innerHTML = `<p class="muted">Simulating…</p>`;
  try {
    state.whatif = await postJson("/api/whatif", buildRequest(section));
    result.innerHTML = answerHtml(state.whatif);
  } catch (error) {
    state.whatif = null;
    result.innerHTML = backendMissing("POST /api/whatif", "M10",
      "When server/app.py serves this endpoint, the simulated KPIs for your settings appear here in a few seconds.");
  } finally {
    button.disabled = false;
  }
}

// Render whatever KPIs the server returns. Each value is clickable like any other number;
// its path starts with "whatif." and the popover names the live simulation as the source.
function answerHtml(answer) {
  if (!answer || !answer.kpis) {
    return `<div class="notice warn">The server answered, but without a "kpis" object.</div>`;
  }
  const rows = Object.keys(answer.kpis).map((kpi) => {
    const info = kpiInfo(kpi);
    const value = answer.kpis[kpi];
    const path = typeof value === "object" ? `whatif.kpis.${kpi}.mean` : `whatif.kpis.${kpi}`;
    return `<tr><td>${escapeHtml(info.label)}</td><td class="num">${ev(path, info.unit)}</td></tr>`;
  }).join("");
  return `<div class="notice ok">Simulated.</div>
    <div class="table-wrap"><table><thead><tr><th>KPI</th><th class="num">Value</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
