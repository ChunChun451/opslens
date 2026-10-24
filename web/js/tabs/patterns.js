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
import { pageHeader, card, missing, backendMissing, postJson, showWaiting, fold, onFirstOpen, factLine } from "../ui.js";
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
const CLUSTERS_SHOWN = 6; // shown first inside the clusters fold
const PLANT_TIMEOUT_MS = 120000; // fresh data + detection takes 20-40 s; give up after 2 minutes

export function render(section) {
  const p = state.results.patterns;
  const plantButton = `<button type="button" class="btn btn-primary" id="plant-open">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>Plant a problem</button>`;
  const hasDelay = p && Object.keys(p.delay_decomposition).length;
  section.innerHTML = `
    ${pageHeader("Recurring problems",
      "What keeps going wrong, and why. Strongest first; open a card for its proof.", plantButton)}
    ${p ? summaryStats(p) : ""}
    ${p ? `<div class="finding-grid">${findings(p, false)}</div>` : missing("Patterns", "M4")}
    ${p && p.cards.some((c) => c.cause_type === "other") ? fold("A weaker pattern with no clear cause yet",
      `<div class="finding-grid">${findings(p, true)}</div>`, { hint: "for the team lead to look at" }) : ""}
    ${hasDelay ? fold("Where the time goes, per team", decompositionCard(), { id: "fold-delay", hint: "waiting vs working vs transfers" }) : ""}
    ${clustersCard()}
    ${plantDialog()}`;

  if (hasDelay) onFirstOpen("fold-delay", () => drawDecomposition(p.delay_decomposition));
  wirePlantDialog(section);
  // A card opens its evidence when clicked anywhere (except on a number, which opens its source).
  section.querySelectorAll(".finding-card").forEach((cardEl) => cardEl.addEventListener("click", (event) => {
    if (event.target.closest(".ev, .ev-text, summary, a, button, table")) return;
    const details = cardEl.querySelector("details");
    if (details) details.open = !details.open;
  }));
}

// How well pattern finding works, as one line of facts (details are on the Proof screen).
function summaryStats(p) {
  const b = p.blind_recall;
  return factLine([
    p.recall && [`${ev("patterns.recall.found", "int")} of ${ev("patterns.recall.planted", "int")}`, "hidden problems found"],
    b && [ev("patterns.blind_recall.found_pct", "pct"), "of random problems found in data it never saw"],
    b && typeof b.diagnosed_pct === "number" && [ev("patterns.blind_recall.diagnosed_pct", "pct"), "given the right cause"],
    typeof p.live_detection_latency_min === "number" && [ev("patterns.live_detection_latency_min", "min"), "to catch a sudden surge"],
  ]);
}

// Findings with a named cause lead; "other" (no clear cause) sits in a fold (review #13, item 10).
function findings(p, other) {
  return p.cards
    .map((c, index) => ({ c, index }))
    .filter(({ c }) => (c.cause_type === "other") === other)
    .sort((a, b) => b.c.strength - a.c.strength)
    .map(({ c, index }) => findingCard(c, index))
    .join("");
}

// One finding as a compact card: what, how much worse than normal, what to do; proof on click.
function findingCard(c, i) {
  const base = `patterns.cards[${i}]`;
  // The two bars are a picture of value vs comparison (scaled to the larger), not new numbers.
  const top = Math.max(Math.abs(c.value), Math.abs(c.comparison_value)) || 1;
  const width = (v) => Math.round((Math.abs(v) / top) * 100);
  const chips = Object.keys(c.segment).map((key) =>
    `<span class="chip"><b>${escapeHtml(prettyKey(key))}</b>${evText(`${base}.segment.${key}`)}</span>`).join("");
  const examples = c.examples.length ? examplesTable(c, base) : "";
  return `<article class="card finding-card cause-${escapeHtml(c.cause_type)}" id="card-${escapeHtml(c.id)}" tabindex="0">
      <div class="finding-meta">
        <span class="cause-tag">${escapeHtml(CAUSE_LABELS[c.cause_type] || c.cause_type)}</span>
        <span class="small muted">${ev(base + ".affected_tickets", "int")} tickets</span>
      </div>
      <h3>${evText(base + ".title")}</h3>
      <div class="finding-bars">
        <div class="mini-bar"><span>This group</span>
          <div class="cbar-track"><div class="cbar-fill is-bad" style="width: ${width(c.value)}%"></div></div>
          <span class="cbar-value">${ev(base + ".value")}</span></div>
        <div class="mini-bar"><span>Normal</span>
          <div class="cbar-track"><div class="cbar-fill is-normal" style="width: ${width(c.comparison_value)}%"></div></div>
          <span class="cbar-value">${ev(base + ".comparison_value")}</span></div>
        <div class="finding-metric">${escapeHtml(c.metric)}</div>
      </div>
      ${c.recommendation ? `<p class="finding-do"><span class="do-tag">Do</span>${evText(base + ".recommendation")}</p>` : ""}
      <details class="disclosure">
        <summary>Proof: example tickets</summary>
        <p class="small">${evText(base + ".comparison_text")}</p>
        <div class="chips">${chips}</div>
        ${c.not_explained_by ? `<p class="small"><strong>Why it is not a known event:</strong> ${evText(base + ".not_explained_by")}</p>` : ""}
        ${examples}
      </details>
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
  return `<p class="small muted">Average minutes per ticket in each stage.</p>
    <div class="chart sm"><canvas id="delay-chart" aria-label="Delay decomposition per team"></canvas></div>`;
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
  return fold("What customers write about: ticket clusters", `<p class="small muted">Similar tickets grouped by their words;
      each group named by the LLM from masked samples.</p>
      <ul class="list">${first}${rest}</ul>`, { id: "clusters-panel", hint: `${order.length} groups` });
}

// ---- Plant a problem (backend arrives in M11) ----------------------------------------------

function plantDialog() {
  const meta = state.results.meta;
  const dayOptions = [];
  for (let day = meta.test_days[0]; day <= meta.test_days[1]; day++) {
    dayOptions.push(`<option value="${day}">Day ${day}</option>`);
  }
  const categoryOptions = CATEGORIES.map((c) => `<option value="${c}">${escapeHtml(prettyKey(c))}</option>`).join("");
  return `<dialog id="plant-dialog" class="wide" aria-labelledby="plant-title">
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

// The live answer from POST /api/plant. It is computed for this request only (not part of
// results.json); it is kept in state.plant so its numbers are clickable ("plant.*" paths).
// Example answer: { planted: { description: "hi x Team B skill gap", cause_type: "skill_gap",
//   fresh_days: 21 }, found: true, diagnosed: true, card: {...}, other_cards: [...], seconds: 16.4 }
function plantAnswerHtml(answer) {
  if (!answer || answer.error) {
    return `<div class="callout warn">${escapeHtml((answer && answer.error) || "No answer from the server.")}</div>`;
  }
  let verdict = `<div class="callout warn"><strong>Missed it.</strong> OpsLens did not flag the planted problem.</div>`;
  if (answer.found) {
    verdict = answer.diagnosed
      ? `<div class="callout good"><strong>Found it, and named the right cause.</strong></div>`
      : `<div class="callout warn"><strong>Found it, but named a different cause.</strong></div>`;
  }
  const c = answer.card;
  const card = c ? `<div class="card" style="margin-top: 14px; box-shadow: none">
      <div class="finding-meta">
        <span class="pill">${escapeHtml(CAUSE_LABELS[c.cause_type] || c.cause_type)}</span>
        <span class="small muted">${ev("plant.card.affected_tickets", "int")} tickets · ${ev("plant.card.affected_share_pct", "pct")} of all</span>
      </div>
      <h3 style="font-size: 1.05rem">${evText("plant.card.title")}</h3>
      <p class="finding-compare">${evText("plant.card.comparison_text")}</p>
      ${c.not_explained_by ? `<p class="small muted" style="margin-top: 6px">${evText("plant.card.not_explained_by")}</p>` : ""}
    </div>` : "";
  const others = (answer.other_cards || []).length
    ? `<p class="small muted" style="margin-top: 12px">Other findings in the fresh data:
        ${answer.other_cards.map((_, i) => evText(`plant.other_cards[${i}]`)).join("; ")}</p>`
    : "";
  return `${verdict}
    <p class="small" style="margin-top: 10px">Planted: <strong>${evText("plant.planted.description")}</strong>
      (${escapeHtml(CAUSE_LABELS[answer.planted.cause_type] || answer.planted.cause_type)}) in
      ${ev("plant.planted.fresh_days", "int")} fresh days · detection took ${ev("plant.seconds", "sec")}</p>
    ${card}${others}`;
}

function wirePlantDialog(section) {
  const dialog = section.querySelector("#plant-dialog");
  const run = section.querySelector("#plant-run");
  section.querySelector("#plant-open").addEventListener("click", () => {
    section.querySelector("#plant-result").innerHTML = "";
    dialog.showModal();
  });
  run.addEventListener("click", async () => {
    const form = dialog.querySelector("form");
    const request = {
      category: form.category.value,
      language: form.language.value,
      effect: form.effect.value,
      day: Number(form.day.value),
    };
    const result = section.querySelector("#plant-result");
    run.disabled = true;
    showWaiting(result, "Generating fresh days with your problem hidden in them, then running detection…");
    try {
      state.plant = await postJson("/api/plant", request, PLANT_TIMEOUT_MS);
      result.innerHTML = plantAnswerHtml(state.plant);
    } catch (error) {
      state.plant = null;
      result.innerHTML = state.staticServer || /HTTP (404|405|501)/.test(error.message)
        ? backendMissing("POST /api/plant",
          "Start it with uvicorn server.app:app. The blind recall test on random plant sets is in How we tested.")
        : `<div class="callout warn"><strong>Detection did not finish.</strong> ${escapeHtml(error.message)}.</div>`;
    } finally {
      run.disabled = false;
    }
  });
}
