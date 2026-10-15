// tabs/patterns.js — recurring problems found in the history, each with its evidence;
// where the time goes per team; ticket clusters; and the "Plant a problem" button.
//
// Why: the problem statement asks us to "identify patterns". A pattern is only useful with
// evidence, so each finding shows the metric against its comparison, the affected volume and
// a suggested action up front; the segment, "why it is not a known event" and three real
// (masked) example tickets sit behind "Show evidence" so the page stays readable.
//
// Example (real results): "phone (IVR) tickets are transferred 5.1× more" — 13.01 vs 2.56
// transfers per 100 tickets, 10,788 tickets (20.2% of all), cause: process.

import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, SLOTS } from "../charts.js";
import { pageHeader, card, stat, missing, backendMissing, postJson } from "../ui.js";
import { escapeHtml, prettyKey, CATEGORIES } from "../format.js";

// Plain-language names for the cause types in the schema.
export const CAUSE_LABELS = {
  capacity: "Capacity",
  skill_gap: "Skill gap",
  volume_spike: "Volume spike",
  partner_issue: "Partner issue",
  process: "Process",
  other: "Other",
};

// How many clusters to show before "Show all" (a layout choice, not a result).
const CLUSTERS_SHOWN = 6;

export function render(section) {
  const p = state.results.patterns;
  const plantButton = `<button type="button" class="btn btn-primary" id="plant-open">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>Plant a problem</button>`;
  section.innerHTML = `
    ${pageHeader("Patterns",
      `Recurring problems found in the history (days ${ev("meta.train_days[0]", "int")}–${ev("meta.validation_days[1]", "int")}), strongest first. Each finding carries its own evidence.`,
      plantButton)}
    ${p ? summaryStats(p) : ""}
    ${p ? findings(p) : missing("Patterns", "M4")}
    <div class="grid cols-2 stretch">
      ${p && Object.keys(p.delay_decomposition).length ? decompositionCard() : ""}
      ${clustersCard()}
    </div>
    ${plantDialog()}`;

  if (p && Object.keys(p.delay_decomposition).length) {
    drawDecomposition(p.delay_decomposition);
  }
  wirePlantDialog(section);
}

// Four headline numbers about how well pattern finding works.
function summaryStats(p) {
  const tiles = [];
  if (p.recall) {
    tiles.push(stat("Planted problems found",
      `${ev("patterns.recall.found", "int")} <span class="muted">of</span> ${ev("patterns.recall.planted", "int")}`,
      `false alarms ${ev("patterns.recall.false_alarms", "int")}`));
  }
  const b = p.blind_recall;
  if (b) {
    const counts = typeof b.planted === "number"
      ? `${ev("patterns.blind_recall.found", "int")} of ${ev("patterns.blind_recall.planted", "int")} random plants, `
      : "";
    tiles.push(stat("Blind recall", ev("patterns.blind_recall.found_pct", "pct"),
      `${counts}${ev("patterns.blind_recall.sets", "int")} sets we never looked at`));
    if (typeof b.diagnosed_pct === "number") {
      tiles.push(stat("Right cause (blind)", ev("patterns.blind_recall.diagnosed_pct", "pct"), "found and given the right cause type"));
    }
  }
  if (typeof p.live_detection_latency_min === "number") {
    tiles.push(stat("Live spike detected after", ev("patterns.live_detection_latency_min", "min"), "an unseen surge on a test day"));
  }
  return `<div class="grid cols-4 stretch">${tiles.map((t) => card({ body: t })).join("")}</div>`;
}

function findings(p) {
  return p.cards
    .map((c, index) => ({ c, index }))
    .sort((a, b) => b.c.strength - a.c.strength)
    .map(({ c, index }) => findingCard(c, index))
    .join("");
}

function findingCard(c, i) {
  const base = `patterns.cards[${i}]`;
  // The two bars are a picture of value vs comparison (scaled to the larger), not new numbers.
  const top = Math.max(Math.abs(c.value), Math.abs(c.comparison_value)) || 1;
  const width = (v) => Math.round((Math.abs(v) / top) * 100);
  const chips = Object.keys(c.segment).map((key) =>
    `<span class="chip"><b>${escapeHtml(prettyKey(key))}</b>${evText(`${base}.segment.${key}`)}</span>`).join("");
  const examples = c.examples.length ? examplesTable(c, base) : "";
  return `<article class="card evidence-card" id="card-${escapeHtml(c.id)}">
      <div class="finding">
        <div>
          <div class="finding-meta">
            <span class="pill">${escapeHtml(CAUSE_LABELS[c.cause_type] || c.cause_type)}</span>
            <span class="small muted">${ev(base + ".affected_tickets", "int")} tickets ·
              ${ev(base + ".affected_share_pct", "pct")} of all</span>
          </div>
          <h3>${evText(base + ".title")}</h3>
          <p class="finding-compare">${evText(base + ".comparison_text")}</p>
          ${c.recommendation ? `<div class="callout info finding-action"><strong>Suggested action:</strong> ${evText(base + ".recommendation")}</div>` : ""}
          <details class="disclosure">
            <summary>Show evidence</summary>
            <div class="chips">${chips}</div>
            ${c.not_explained_by ? `<p class="small"><strong>Why it is not a known event:</strong> ${evText(base + ".not_explained_by")}</p>` : ""}
            ${examples}
          </details>
        </div>
        <div class="finding-side">
          <div class="stat-label">${escapeHtml(c.metric)}</div>
          <div class="mini-bars">
            <div class="mini-bar"><span>This segment</span>
              <div class="cbar-track"><div class="cbar-fill" style="width: ${width(c.value)}%; background: var(--ink)"></div></div>
              <span class="cbar-value">${ev(base + ".value")}</span></div>
            <div class="mini-bar"><span>Comparison</span>
              <div class="cbar-track"><div class="cbar-fill" style="width: ${width(c.comparison_value)}%; background: var(--border-strong)"></div></div>
              <span class="cbar-value">${ev(base + ".comparison_value")}</span></div>
          </div>
          <div class="stat-sub">Strength ${ev(base + ".strength")} (robust z or ratio; higher = more unusual)</div>
        </div>
      </div>
    </article>`;
}

function examplesTable(c, base) {
  const rows = c.examples.map((t, j) => {
    const path = `${base}.examples[${j}]`;
    let breached = "—";
    if (t.breached === true || t.breached === false) {
      breached = evText(path + ".breached", t.breached ? "Yes" : "No");
    }
    return `<tr>
        <td>${evText(path + ".ticket_id")}</td>
        <td class="muted">${evText(path + ".created_at")}</td>
        <td>${evText(path + ".text")}</td>
        <td class="num">${ev(path + ".wait_min", "min")}</td>
        <td>${breached}</td>
      </tr>`;
  }).join("");
  return `<div class="table-wrap"><table>
      <thead><tr><th>Ticket</th><th>Created</th><th>Text (PII-masked)</th><th class="num">Wait</th><th>Breached</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

function decompositionCard() {
  return card({
    id: "delay-panel",
    title: "Where the time goes, per team",
    sub: "Average minutes per ticket in each stage",
    body: `<div class="chart sm"><canvas id="delay-chart" aria-label="Delay decomposition per team"></canvas></div>`,
  });
}

// Horizontal stacked bars: one bar per team, one segment per stage.
function drawDecomposition(decomposition) {
  const teams = Object.keys(decomposition).sort();
  const stages = Object.keys(decomposition[teams[0]]);
  const datasets = stages.map((stage, s) => ({
    label: prettyKey(stage),
    data: teams.map((team) => decomposition[team][stage]),
    backgroundColor: SLOTS[s % SLOTS.length],
    borderColor: "#ffffff",
    borderWidth: 2, // a thin white gap between stacked segments
    borderRadius: 4,
    barThickness: 22,
  }));
  makeChart(document.getElementById("delay-chart"), {
    type: "bar",
    data: { labels: teams.map((t) => "Team " + t), datasets },
    options: {
      indexAxis: "y",
      scales: {
        x: { stacked: true, title: { display: true, text: "minutes per ticket" } },
        y: { stacked: true, grid: { display: false } },
      },
      plugins: { legend: { position: "top" } },
    },
  }, (datasetIndex, index) => ({
    path: `patterns.delay_decomposition.${teams[index]}.${stages[datasetIndex]}`,
    unit: "min",
  }));
}

// The biggest ticket clusters (named by the LLM); the rest behind "Show all clusters".
function clustersCard() {
  const c = state.results.classification;
  if (!c || !c.clusters.length) {
    return "";
  }
  const order = c.clusters.map((cluster, i) => ({ cluster, i })).sort((a, b) => b.cluster.size - a.cluster.size);
  const item = ({ cluster, i }) => {
    const base = `classification.clusters[${i}]`;
    return `<li>
        <div class="issue">
          <span class="issue-title">${evText(base + ".name")}</span>
          <span class="pill">${escapeHtml(prettyKey(cluster.category))}</span>
          <span class="issue-text">${ev(base + ".size", "int")} tickets · ${evText(base + ".root_cause")}</span>
        </div>
      </li>`;
  };
  const first = order.slice(0, CLUSTERS_SHOWN).map(item).join("");
  const rest = order.slice(CLUSTERS_SHOWN).map(item).join("");
  return card({
    id: "clusters-panel",
    title: "Ticket clusters",
    sub: "TF-IDF + KMeans; each cluster named by the LLM from masked sample tickets",
    body: `<ul class="list">${first}</ul>
      ${rest ? `<details class="disclosure"><summary>Show all clusters</summary><ul class="list">${rest}</ul></details>` : ""}`,
  });
}

// ---- Plant a problem (backend arrives in M11) ----------------------------------------------

function plantDialog() {
  const meta = state.results.meta;
  const dayOptions = [];
  for (let day = meta.test_days[0]; day <= meta.test_days[1]; day++) {
    dayOptions.push(`<option value="${day}">Day ${day}</option>`);
  }
  const categoryOptions = CATEGORIES.map((c) => `<option value="${c}">${escapeHtml(prettyKey(c))}</option>`).join("");
  return `<dialog id="plant-dialog" aria-labelledby="plant-title">
      <form method="dialog">
        <h2 id="plant-title">Plant a problem</h2>
        <p class="muted small" style="margin-bottom: 18px">Pick a segment and an effect. OpsLens gets fresh data with the
          problem hidden in it, is <strong>not</strong> told where it is, and runs pattern detection.
          Then we check whether it found it.</p>
        <div class="form-grid">
          <label class="field"><span class="field-label">Category</span><select name="category">${categoryOptions}</select></label>
          <label class="field"><span class="field-label">Language</span><select name="language">
            <option value="">Any</option><option value="en">English</option><option value="hi">Hindi</option><option value="other">Other</option>
          </select></label>
          <label class="field"><span class="field-label">Effect</span><select name="effect">
            <option value="volume">Volume spike</option>
            <option value="wait">Long waits (skill gap)</option>
            <option value="transfers">Many transfers (process)</option>
          </select></label>
          <label class="field"><span class="field-label">Day</span><select name="day">${dayOptions.join("")}</select></label>
        </div>
        <div id="plant-result" style="margin-top: 16px"></div>
        <div class="btn-row" style="margin-top: 20px; justify-content: flex-end">
          <button type="submit" class="btn" value="close">Close</button>
          <button type="button" class="btn btn-primary" id="plant-run">Plant and detect</button>
        </div>
      </form>
    </dialog>`;
}

function wirePlantDialog(section) {
  const dialog = section.querySelector("#plant-dialog");
  section.querySelector("#plant-open").addEventListener("click", () => {
    section.querySelector("#plant-result").innerHTML = "";
    dialog.showModal();
  });
  section.querySelector("#plant-run").addEventListener("click", async () => {
    const form = dialog.querySelector("form");
    const request = {
      category: form.category.value,
      language: form.language.value,
      effect: form.effect.value,
      day: Number(form.day.value),
    };
    const result = section.querySelector("#plant-result");
    result.innerHTML = `<div class="wait"><span class="spinner" aria-hidden="true"></span>Planting and detecting…</div>`;
    try {
      const answer = await postJson("/api/plant", request);
      result.innerHTML = `<div class="callout good">Server answered:</div><pre>${escapeHtml(JSON.stringify(answer, null, 2))}</pre>`;
    } catch (error) {
      result.innerHTML = backendMissing("POST /api/plant", "M11",
        "The blind recall test on random plant sets is already in How we tested.");
    }
  });
}
