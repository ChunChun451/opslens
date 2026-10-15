// tabs/whatif.js — the judges' turn: change staffing or volume and re-run the simulator.
//
// Why: moat number three, "touch it". A judge picks a test day, adds or removes agents per
// team, scales the volume and picks a policy. The server (opslens/whatif.py) simulates that
// day for ALL three policies under the same changes and the same luck, so the answer is a fair
// side-by-side comparison, not one number. It takes a while (three full-day simulations), so
// the panel shows a spinner and keeps the button disabled until the answer arrives.
//
// Example request: { "day": 48, "policy": "opslens", "volume_factor": 1.25,
//                    "agents_delta": { "A": 0, "B": 0, "C": 2, "D": 0 } }
// Answer: { "request": {...}, "kpis": {...chosen policy...},
//           "all_policies": { "baseline_a": {...}, "baseline_b": {...}, "opslens": {...} },
//           "agents_on_roster": 42 }

import { state, policyKeys, policyLabel, teamNames } from "../data.js";
import { ev } from "../evidence.js";
import { postJson, policyName } from "../ui.js";
import { escapeHtml, kpiInfo, unitSuffix } from "../format.js";

// Slider ranges. These are input limits for the judge, not results.
const AGENT_DELTA_LIMIT = 5;
const VOLUME_MIN = 0.5;
const VOLUME_MAX = 2;
const TIMEOUT_MS = 180000; // give up after 3 minutes, so a stuck server never freezes the panel

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
  const request = buildRequest(section);
  button.disabled = true;
  result.innerHTML = `<div class="whatif-wait" role="status">
      <span class="spinner" aria-hidden="true"></span>
      Simulating the whole day for all three policies with your changes…
    </div>`;
  try {
    state.whatif = await postJson("/api/whatif", request, TIMEOUT_MS);
    result.innerHTML = answerHtml(state.whatif);
  } catch (error) {
    state.whatif = null;
    if (state.staticServer || /HTTP (404|405|501)/.test(error.message)) {
      // The page is served without the OpsLens API (for example by python -m http.server).
      result.innerHTML = `<div class="notice warn"><strong>What-if needs the OpsLens server.</strong>
        Start it with <code>.venv/Scripts/python.exe -m uvicorn server.app:app --port 8000</code>
        and open <code>http://localhost:8000/web/</code>.</div>`;
    } else {
      result.innerHTML = `<div class="notice warn"><strong>The simulation did not finish.</strong>
        ${escapeHtml(error.message)}. Try again, or check the server window.</div>`;
    }
  } finally {
    button.disabled = false;
  }
}

// The three policies side by side, the chosen one highlighted. Every value is clickable;
// its path starts with "whatif." and the popover names the live simulation as the source.
function answerHtml(answer) {
  if (!answer || !answer.all_policies) {
    return `<div class="notice warn">The server answered, but without "all_policies".</div>`;
  }
  const chosen = answer.request ? answer.request.policy : "opslens";
  const keys = policyKeys().filter((k) => answer.all_policies[k]);
  const kpis = Object.keys(answer.all_policies[keys[0]]);
  const header = keys.map((k) => `<th class="num ${k === chosen ? "chosen" : ""}">${policyName(k)}
      ${k === chosen ? `<div class="small">your choice</div>` : ""}</th>`).join("");
  const rows = kpis.map((kpi) => {
    const info = kpiInfo(kpi);
    const best = bestOf(answer.all_policies, keys, kpi, info.better);
    const suffix = unitSuffix(info.unit);
    const cells = keys.map((k) => `<td class="num ${k === chosen ? "chosen" : ""} ${k === best ? "best" : ""}">
        ${ev(`whatif.all_policies.${k}.${kpi}`, info.unit, { bare: true })}</td>`).join("");
    const label = escapeHtml(info.label) + (suffix ? ` <span class="muted">(${escapeHtml(suffix)})</span>` : "");
    return `<tr><td>${label}</td>${cells}</tr>`;
  }).join("");
  return `<div class="notice ok">Simulated day ${ev("whatif.request.day", "int")},
      volume ×${ev("whatif.request.volume_factor", "num")}, ${ev("whatif.agents_on_roster", "int")} agents
      on the roster. Same tickets and the same luck for every policy.</div>
    <div class="table-wrap"><table class="whatif-table">
      <thead><tr><th>KPI</th>${header}</tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p class="panel-note">Bold = best on that row. Tinted column = the policy you picked.</p>`;
}

// Which policy is best on this KPI (a comparison only; no new number is shown).
function bestOf(allPolicies, keys, kpi, better) {
  if (!better) return null;
  let bestKey = null;
  keys.forEach((k) => {
    const value = allPolicies[k][kpi];
    if (typeof value !== "number") return;
    const current = bestKey === null ? null : allPolicies[bestKey][kpi];
    if (bestKey === null || (better === "lower" ? value < current : value > current)) {
      bestKey = k;
    }
  });
  return bestKey;
}
