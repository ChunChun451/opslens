// tabs/patterns.js — evidence cards for recurring problems, delay breakdown, clusters,
// and the "Plant a problem" button.
//
// Why: the problem statement asks us to "identify patterns". A pattern is only useful with
// evidence, so each card shows the metric, the comparison, the affected volume, why it is not
// a known event, and three real (masked) example tickets.
//
// Example card (fixture): "Hindi payments & refunds wait 6x longer" — 302 vs 47 min mean
// wait, 3,900 tickets affected, strength 9.1, cause: skill gap.

import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { makeChart, SLOTS } from "../charts.js";
import { missing, backendMissing, postJson } from "../ui.js";
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

export function render(section) {
  const p = state.results.patterns;
  section.innerHTML = `
    <div class="tab-head">
      <div>
        <h2>Patterns</h2>
        <p>Recurring problems found in the history (days ${ev("meta.train_days[0]", "int")}–${ev("meta.validation_days[1]", "int")}),
           strongest first. Each card carries its evidence.</p>
      </div>
      <button type="button" class="btn btn-primary" id="plant-open">Plant a problem</button>
    </div>
    ${p ? recallStrip(p) : ""}
    ${p ? cardsHtml(p) : missing("Patterns", "M4")}
    ${p && Object.keys(p.delay_decomposition).length ? decompositionPanel() : ""}
    ${clustersPanel()}
    ${plantDialog()}`;

  if (p && Object.keys(p.delay_decomposition).length) {
    drawDecomposition(p.delay_decomposition);
  }
  wirePlantDialog(section);
}

function recallStrip(p) {
  const parts = [];
  if (p.recall) {
    parts.push(`Planted problems found: <strong>${ev("patterns.recall.found", "int")} of ${ev("patterns.recall.planted", "int")}</strong>,
      false alarms ${ev("patterns.recall.false_alarms", "int")}`);
  }
  if (p.blind_recall) {
    // Older results had false_alarms_mean; the real engine reports found / planted and diagnosed_pct.
    const b = p.blind_recall;
    let extra = "";
    if (typeof b.diagnosed_pct === "number") {
      extra = `, right cause ${ev("patterns.blind_recall.diagnosed_pct", "pct")}`;
    } else if (typeof b.false_alarms_mean === "number") {
      extra = `, false alarms per set ${ev("patterns.blind_recall.false_alarms_mean", "num")}`;
    }
    const counts = typeof b.planted === "number"
      ? ` (${ev("patterns.blind_recall.found", "int")} of ${ev("patterns.blind_recall.planted", "int")})`
      : "";
    parts.push(`Blind recall ${ev("patterns.blind_recall.found_pct", "pct")}${counts} over
      ${ev("patterns.blind_recall.sets", "int")} random plant sets${extra}`);
  }
  if (p.live_detection_latency_min !== null && p.live_detection_latency_min !== undefined) {
    parts.push(`Live spike detected after ${ev("patterns.live_detection_latency_min", "min")}`);
  }
  if (!parts.length) return "";
  return `<div class="panel notice ok">${parts.join(" · ")}</div>`;
}

function cardsHtml(p) {
  const order = p.cards
    .map((card, index) => ({ card, index }))
    .sort((a, b) => b.card.strength - a.card.strength);
  return order.map(({ card, index }) => cardHtml(card, index)).join("");
}

function cardHtml(card, i) {
  const base = `patterns.cards[${i}]`;
  const chips = Object.keys(card.segment).map((key) =>
    `<span class="chip"><b>${escapeHtml(prettyKey(key))}</b>${evText(`${base}.segment.${key}`)}</span>`).join("");
  return `<article class="panel evidence-card" id="card-${escapeHtml(card.id)}">
      <div class="card-top">
        <h3>${evText(base + ".title")}</h3>
        <span class="cause">${escapeHtml(CAUSE_LABELS[card.cause_type] || card.cause_type)}</span>
      </div>
      <p class="card-compare">${evText(base + ".comparison_text")}</p>
      <div class="card-numbers">
        <div>
          <div class="tile-label">${escapeHtml(card.metric)}</div>
          <div class="tile-value">${ev(base + ".value")} <span class="muted small">vs ${ev(base + ".comparison_value")}</span></div>
        </div>
        <div>
          <div class="tile-label">Tickets affected</div>
          <div class="tile-value">${ev(base + ".affected_tickets", "int")}</div>
          <div class="tile-sub">${ev(base + ".affected_share_pct", "pct")} of all tickets</div>
        </div>
        <div>
          <div class="tile-label">Strength</div>
          <div class="tile-value">${ev(base + ".strength")}</div>
          <div class="tile-sub">robust z or ratio</div>
        </div>
      </div>
      <div class="chips">${chips}</div>
      ${card.not_explained_by ? `<p class="small"><strong>Why it is not a known event:</strong> ${evText(base + ".not_explained_by")}</p>` : ""}
      ${card.recommendation ? `<p class="small"><strong>Suggested action:</strong> ${evText(base + ".recommendation")}</p>` : ""}
      ${card.examples.length ? examplesTable(card, base) : ""}
    </article>`;
}

function examplesTable(card, base) {
  const rows = card.examples.map((t, j) => {
    const path = `${base}.examples[${j}]`;
    let breached = "—";
    if (t.breached === true || t.breached === false) {
      breached = evText(path + ".breached", t.breached ? "Yes" : "No");
    }
    return `<tr>
        <td>${evText(path + ".ticket_id")}</td>
        <td>${evText(path + ".created_at")}</td>
        <td>${evText(path + ".text")}</td>
        <td class="num">${ev(path + ".wait_min", "min")}</td>
        <td>${breached}</td>
      </tr>`;
  }).join("");
  return `<div class="table-wrap"><table class="examples">
      <thead><tr><th>Ticket</th><th>Created</th><th>Text (PII-masked)</th><th class="num">Wait</th><th>Breached</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

function decompositionPanel() {
  return `<div class="panel" id="delay-panel">
      <h3>Where the time goes, per team</h3>
      <p class="muted small">Average minutes per ticket in each stage. Click a bar for its number.</p>
      <div class="chart-box short"><canvas id="delay-chart" aria-label="Delay decomposition per team"></canvas></div>
    </div>`;
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

function clustersPanel() {
  const c = state.results.classification;
  if (!c || !c.clusters.length) {
    return "";
  }
  const items = c.clusters.map((cluster, i) => {
    const base = `classification.clusters[${i}]`;
    const examples = cluster.examples.map((_, j) => `<li>${evText(`${base}.examples[${j}]`)}</li>`).join("");
    return `<li class="cluster">
        <div><strong>${evText(base + ".name")}</strong> <span class="badge">${escapeHtml(cluster.category)}</span>
          <span class="muted small">${ev(base + ".size", "int")} tickets</span></div>
        <div class="small">Root cause: ${evText(base + ".root_cause")}</div>
        <ul class="small muted">${examples}</ul>
      </li>`;
  }).join("");
  return `<div class="panel" id="clusters-panel">
      <h3>Ticket clusters</h3>
      <p class="muted small">Grouped by TF-IDF + KMeans; each cluster named by the LLM from masked sample tickets.</p>
      <ul class="cluster-list">${items}</ul>
    </div>`;
}

// ---- Plant a problem (backend arrives in M11) ----------------------------------------------

function plantDialog() {
  const meta = state.results.meta;
  const dayOptions = [];
  for (let day = meta.test_days[0]; day <= meta.test_days[1]; day++) {
    dayOptions.push(`<option value="${day}">Day ${day}</option>`);
  }
  const categoryOptions = CATEGORIES.map((c) => `<option value="${c}">${c}</option>`).join("");
  return `<dialog id="plant-dialog" aria-labelledby="plant-title">
      <form method="dialog">
        <h2 id="plant-title">Plant a problem</h2>
        <p>Pick a segment and an effect. OpsLens gets fresh data with the problem hidden in it,
           is <strong>not</strong> told where it is, and runs pattern detection. Then we check if it found it.</p>
        <div class="form-grid">
          <label>Category<select name="category">${categoryOptions}</select></label>
          <label>Language<select name="language">
            <option value="">any</option><option value="en">en</option><option value="hi">hi</option><option value="other">other</option>
          </select></label>
          <label>Effect<select name="effect">
            <option value="volume">Volume spike</option>
            <option value="wait">Long waits (skill gap)</option>
            <option value="transfers">Many transfers (process)</option>
          </select></label>
          <label>Day<select name="day">${dayOptions.join("")}</select></label>
        </div>
        <div id="plant-result" class="plant-result"></div>
        <div class="btn-row">
          <button type="button" class="btn btn-primary" id="plant-run">Plant and detect</button>
          <button type="submit" class="btn" value="close">Close</button>
        </div>
      </form>
    </dialog>`;
}

// The live answer is computed by the server for this request only, so its numbers are shown
// as the server sent them (they are not part of results.json).
function plantAnswerHtml(answer) {
  if (!answer || answer.error) {
    return `<div class="notice warn">${escapeHtml((answer && answer.error) || "No answer")}</div>`;
  }
  const verdict = answer.found
    ? (answer.diagnosed ? "Found it, and named the right cause." : "Found it, but named a different cause.")
    : "Missed it.";
  const card = answer.card
    ? `<div class="card"><strong>${escapeHtml(answer.card.title)}</strong>
         <p>${escapeHtml(answer.card.comparison_text)}</p>
         <p class="muted">Cause: ${escapeHtml(answer.card.cause_type)}${answer.card.not_explained_by ? " · " + escapeHtml(answer.card.not_explained_by) : ""}</p></div>`
    : "";
  const others = (answer.other_cards || []).length
    ? `<p class="muted">Other findings in the fresh data: ${answer.other_cards.map(escapeHtml).join("; ")}</p>` : "";
  return `<div class="notice ${answer.found ? "ok" : "warn"}"><strong>${verdict}</strong>
      Planted: ${escapeHtml(answer.planted.description)} (${escapeHtml(answer.planted.cause_type)}),
      in ${escapeHtml(String(answer.planted.fresh_days))} fresh days. Took ${escapeHtml(String(answer.seconds))} s.</div>
    ${card}${others}`;
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
    result.innerHTML = `<p class="muted">Generating 21 fresh days with your problem hidden in them, then detecting… (about 20–40 seconds)</p>`;
    try {
      const answer = await postJson("/api/plant", request);
      result.innerHTML = plantAnswerHtml(answer);
    } catch (error) {
      result.innerHTML = backendMissing("POST /api/plant", "M11",
        "The blind recall test on random plant sets is already in How we tested.");
    }
  });
}
