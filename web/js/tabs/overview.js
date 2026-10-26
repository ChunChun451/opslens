import { state, policyKeys } from "../data.js";
import { ev, evText, labelFor } from "../evidence.js";
import {
  pageHeader, card, stat, missing, policyName, shortLabel, deltaPill, comparisonIndex, fold, onFirstOpen,
} from "../ui.js";
import { escapeHtml, kpiInfo, unitForPath, spreadUnit } from "../format.js";
import { policyStyle } from "../charts.js";
import { CAUSE_LABELS } from "./patterns.js";
import { hasMission, missionHtml, initMission } from "../mission.js";
import { thousandHtml, journeyHtml, initStoryCards } from "../storycards.js";

const BREACH = "turnaround.breach_pct";
const KEY_KPIS = [
  "turnaround.p90_resolution_min",
  "turnaround.mean_wait_min",
  "turnaround.max_backlog",
  "productivity.transfers_per_100",
];

export function render(section) {
  const r = state.results;
  const strip = proofStrip();
  section.innerHTML = `
    ${pageHeader("Results on days it never saw", "14 held-out days. Same customers, same agents, same luck for every way of working; only the decisions differ.")}
    ${strip || (r.sim ? heroCard() : missing("The simulator comparison", "M7"))}
    ${r.sim ? thousandHtml() : ""}
    ${r.risk ? journeyHtml() : ""}
    ${issuesCard()}
    ${r.sim && strip ? fold("Every way of working, with 95% intervals", heroCard(), { id: "fold-all-ways", hint: "OpsLens against all four" }) : ""}
    ${r.sim && hasMission() ? fold("Replay one Saturday dinner, side by side", missionHtml(), { id: "fold-mission", hint: "the evening in 30 seconds" }) : ""}
    ${r.sim ? fold("More numbers: time to solve, waits, queues, transfers", `<div class="grid cols-4 stretch">${KEY_KPIS.map(kpiCard).join("")}</div>`, { hint: "against the industry standard" }) : ""}
    ${r.sim ? fold("Who is protected: urgent orders, gold and Hindi-speaking customers", segmentsCard()) : ""}
    ${r.brief ? fold("Today's brief, written by the LLM (numbers filled in by code)", briefCard()) : ""}`;
  if (r.sim && hasMission()) onFirstOpen("fold-mission", initMission);
  initStoryCards(section);
}

function heroCard() {
  const sim = state.results.sim;
  const keys = policyKeys();
  const path = (k) => `sim.policies.${k}.kpis.${BREACH}.mean`;
  let top = 0;
  keys.forEach((k) => { top = Math.max(top, sim.policies[k].kpis[BREACH].mean); });

  const deltas = [];
  sim.comparisons.forEach((c, i) => {
    if (c.kpi !== BREACH || c.policy !== "opslens") return;
    const base = `sim.comparisons[${i}]`;
    (c.baseline === "baseline_d" ? deltas.unshift.bind(deltas) : deltas.push.bind(deltas))(`<div>${deltaPill(base, "pts", "lower")} vs ${escapeHtml(shortLabel(c.baseline))}
        <span class="ci">95% CI ${ev(base + ".ci_low", "pts", { signed: true, bare: true })} to ${ev(base + ".ci_high", "pts", { signed: true, bare: true })}</span></div>`);
  });

  const bars = keys.map((k) => {
    const width = Math.round((sim.policies[k].kpis[BREACH].mean / top) * 100);
    return `<div class="cbar ${k === "opslens" ? "is-ours" : ""}">
        ${policyName(k)}
        <div class="cbar-track"><div class="cbar-fill" style="width: ${width}%; background: ${policyStyle(k).color}"></div></div>
        <div class="cbar-value">${ev(path(k), "pct")}</div>
      </div>`;
  }).join("");

  return card({
    id: "ov-headline",
    title: "Missed promises on days it had never seen",
    sub: `Share of tickets not solved in time (SLA breach rate), average over simulator seeds ${evText("sim.seeds")}`,
    body: `<div class="hero">
        <div>
          ${stat("OpsLens", ev(path("opslens"), "pct"), "", "xl")}
          <div class="hero-deltas">${deltas.join("")}</div>
        </div>
        <div class="cbars">${bars}</div>
      </div>`,
  });
}

function proofStrip() {
  const r = state.results;
  if (!r.baseline_c || !r.baseline_c.test.means) return "";
  const c = "baseline_c.test.means";
  const tiles = [
    (() => {
      const best = r.baseline_c.test.means.baseline_d ? ["baseline_d", "d", "industry-standard skills routing with AI triage"]
        : ["baseline_c", "c", "the SLA-due sort"];
      return `<div class="proof is-lead">
        <div class="proof-q">Missed promises: OpsLens vs the industry standard</div>
        <div class="proof-a">${ev(`${c}.opslens.${BREACH}`, "pct")} <span class="muted">vs</span> ${ev(`${c}.${best[0]}.${BREACH}`, "pct")}</div>
        <div class="proof-s">Missed promises, OpsLens vs ${best[2]}. 95% CI
          ${ev(`baseline_c.test.opslens_minus_${best[1]}.${BREACH}.ci_low`, "pts", { signed: true, bare: true })} to
          ${ev(`baseline_c.test.opslens_minus_${best[1]}.${BREACH}.ci_high`, "pts", { signed: true, bare: true })} pts</div>
      </div>`;
    })(),
    `<div class="proof">
        <div class="proof-q">Late customers are not abandoned</div>
        <div class="proof-a">${ev(`${c}.opslens.quality.late_minutes_per_100`, "int")} <span class="muted">vs</span>
          ${ev(`${c}.${r.baseline_c.test.means.baseline_d ? "baseline_d" : "baseline_b"}.quality.late_minutes_per_100`, "int")}</div>
        <div class="proof-s">Minutes past the promise per 100 tickets, OpsLens vs ${r.baseline_c.test.means.baseline_d ? "the industry standard" : "urgent first"}</div>
      </div>`,
  ];
  const sealedNew = r.sealed_world_new && r.sealed_world_new.test && r.sealed_world_new.test.opslens_minus_d;
  if (sealedNew) {
    const s = "sealed_world_new.test";
    tiles.push(`<div class="proof">
        <div class="proof-q">Still wins on data made after we froze it</div>
        <div class="proof-a">${ev(`${s}.means.opslens.${BREACH}`, "pct")} <span class="muted">vs</span> ${ev(`${s}.means.baseline_d.${BREACH}`, "pct")}</div>
        <div class="proof-s">Missed promises, OpsLens vs the industry standard, on a new world (seed ${evText("sealed_world_new.data_seed")}) tested once. 95% CI
          ${ev(`${s}.opslens_minus_d.${BREACH}.ci_low`, "pts", { signed: true, bare: true })} to
          ${ev(`${s}.opslens_minus_d.${BREACH}.ci_high`, "pts", { signed: true, bare: true })} pts</div>
      </div>`);
  } else if (r.sealed_world && r.sealed_world.test.means) {
    const s = "sealed_world.test.means";
    tiles.push(`<div class="proof">
        <div class="proof-q">Still wins on data made after we froze it</div>
        <div class="proof-a">${ev(`${s}.opslens.${BREACH}`, "pct")} <span class="muted">vs</span> ${ev(`${s}.baseline_c.${BREACH}`, "pct")}</div>
        <div class="proof-s">Missed promises, OpsLens vs due time first, on a new world (seed ${evText("sealed_world.data_seed")}) tested once</div>
      </div>`);
  }
  return `<div class="grid cols-${tiles.length} stretch proof-strip">${tiles.join("")}</div>`;
}

function briefCard() {
  const b = state.results.brief;
  if (!b) {
    return missing("The daily brief", "M10");
  }
  const used = b.numbers_used.map((path) =>
    `<li>${escapeHtml(labelFor(path))}: <strong>${ev(path, unitForPath(path))}</strong></li>`).join("");
  return card({
    id: "ov-brief",
    title: "Today's brief",
    actions: `<span class="pill">${b.source === "llm" ? "LLM text · numbers by code" : "template"}</span>`,
    body: `<p class="brief">${evText("brief.text")}</p>
      ${used ? `<details class="disclosure"><summary>Numbers in this brief</summary>
        <ul class="small muted">${used}</ul></details>` : ""}`,
  });
}

function kpiCard(kpi) {
  const sim = state.results.sim;
  if (!sim.policies.opslens || !sim.policies.opslens.kpis[kpi]) return "";
  const info = kpiInfo(kpi);
  const lead = sim.policies.baseline_d ? "baseline_d" : "baseline_b";
  const i = comparisonIndex("opslens", lead, kpi);
  const delta = i >= 0 ? `${deltaPill(`sim.comparisons[${i}]`, spreadUnit(info.unit), info.better)} vs ${escapeHtml(shortLabel(lead))}` : "";
  const others = ["baseline_a", "baseline_b", "baseline_d"].filter((k) => sim.policies[k])
    .map((k) => `<div class="pair"><span>${escapeHtml(shortLabel(k))}</span>${ev(`sim.policies.${k}.kpis.${kpi}.mean`, info.unit)}</div>`).join("");
  return card({
    body: stat(info.label, ev(`sim.policies.opslens.kpis.${kpi}.mean`, info.unit), `${delta}<div class="pairs">${others}</div>`, "md"),
  });
}

function issuesCard() {
  const patterns = state.results.patterns;
  if (!patterns) {
    return missing("Patterns", "M4");
  }
  const order = patterns.cards
    .map((c, index) => ({ c, index }))
    .sort((a, b) => b.c.strength - a.c.strength)
    .slice(0, 3);
  const items = order.map(({ c, index }) => `
      <li class="issue" data-goto-tab="patterns" data-goto-id="card-${escapeHtml(c.id)}">
        <span class="issue-title">${evText(`patterns.cards[${index}].title`)}</span>
        <span class="pill">${escapeHtml(CAUSE_LABELS[c.cause_type] || c.cause_type)}</span>
        <span class="issue-text">${evText(`patterns.cards[${index}].comparison_text`)}</span>
      </li>`).join("");
  return card({
    id: "ov-issues",
    title: "Top problems found",
    sub: "Strongest evidence first. Open one to see the tickets behind it.",
    actions: `<a class="btn btn-sm" href="#patterns">All findings</a>`,
    body: `<ul class="list">${items}</ul>`,
  });
}

function segmentsCard() {
  const sim = state.results.sim;
  const keys = policyKeys();
  const segmentKpis = Object.keys(sim.policies[keys[0]].kpis).filter((k) => k.startsWith("segment."));
  if (!segmentKpis.length) return "";
  const blocks = segmentKpis.map((kpi) => {
    let top = 0;
    keys.forEach((k) => { top = Math.max(top, sim.policies[k].kpis[kpi].mean); });
    const bars = keys.map((k) => {
      const width = top > 0 ? Math.round((sim.policies[k].kpis[kpi].mean / top) * 100) : 0;
      return `<div class="mini-bar">
          <span>${escapeHtml(shortLabel(k))}</span>
          <div class="cbar-track"><div class="cbar-fill" style="width: ${width}%; background: ${policyStyle(k).color}"></div></div>
          <span class="cbar-value">${ev(`sim.policies.${k}.kpis.${kpi}.mean`, "pct")}</span>
        </div>`;
    }).join("");
    return `<div class="section-label">${escapeHtml(kpiInfo(kpi).label)}</div><div class="mini-bars">${bars}</div>`;
  }).join("");
  return `<div id="ov-segments" class="segments-grid">${blocks}</div>`;
}
