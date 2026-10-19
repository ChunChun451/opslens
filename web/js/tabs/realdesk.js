// tabs/realdesk.js — the real public service desk (UCI ServiceNow log): the same five questions.
//
// Why (Plan v3, 19 Oct): deliverable 1 asks for "a working prototype using a provided or publicly
// available dataset". This is that prototype on real data nobody generated: a company's IT service
// desk, 24,918 incidents. Every number is read from results.realdesk (eval/run_realdesk.py),
// learned on the first months and scored on later ones. We also show what OpsLens does NOT do
// better on this data (the forecast, picking the team), so the screen stays honest.
//
// Example: the riskiest 20% of incidents by OpsLens's score hold about half of all SLA misses,
// against about a quarter for the desk's own priority field.

import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, stat } from "../ui.js";
import { escapeHtml } from "../format.js";
import { planButtons, registerItem } from "../plan.js";

const R = "realdesk";

function missingData(section) {
  section.innerHTML = pageHeader("Real public service desk", "") +
    `<div class="callout warn">No real-data results yet: run <code>eval/run_realdesk.py</code> (part of make eval).</div>`;
}

function sourceLine() {
  return `A real company's IT service desk (UCI ServiceNow log, CC BY 4.0). Learned on
    ${evText(`${R}.summary.learning_period[0]`)} to ${evText(`${R}.summary.learning_period[1]`)};
    every comparison is scored on later incidents (${ev(`${R}.summary.test_incidents`, "int")}).`;
}

// ---- Overview: what is happening? -------------------------------------------------------------

export const overview = { render(section) {
  const d = state.results[R];
  if (!d) return missingData(section);
  const shares = Object.entries(d.summary.open_time_share_pct);
  const bar = shares.map(([k], i) => `<span class="share-seg seg-${i}" style="flex:${d.summary.open_time_share_pct[k]}"
      title="${escapeHtml(k)}"></span>`).join("");
  const legend = shares.map(([k], i) => `<li><span class="share-dot seg-${i}"></span>${escapeHtml(k)}
      ${ev(`${R}.summary.open_time_share_pct.${k}`, "pct")}</li>`).join("");
  section.innerHTML = `${pageHeader("A real service desk", sourceLine())}
    <section class="card stat-card"><div class="grid cols-4">
      ${stat("Incidents", ev(`${R}.summary.incidents`, "int"), `${ev(`${R}.summary.teams`, "int")} teams, ${ev(`${R}.summary.agents`, "int")} agents`)}
      ${stat("Missed their SLA", ev(`${R}.summary.missed_sla_pct`, "pct"), "the company's own SLA flag")}
      ${stat("Passed between teams", ev(`${R}.summary.passed_between_teams_pct`, "pct"), "at least once")}
      ${stat("Median time to resolve", ev(`${R}.summary.median_resolution_h`, "hours"), "from opening")}
    </div></section>
    ${card({ title: "Where an incident's open time goes", sub: "From every state change in the event log (learning period).",
      body: `<div class="share-bar">${bar}</div><ul class="share-legend">${legend}</ul>` })}
    ${card({ title: "The three biggest problems", sub: "Open Problems for the evidence.",
      body: `<ol class="issues">${d.cards.map((c, i) => `<li class="issue" data-goto-tab="problems" data-goto-id="rd-card-${escapeHtml(c.id)}">
        ${evText(`${R}.cards[${i}].title`)}</li>`).join("")}</ol>` })}
    ${card({ title: "What OpsLens adds here", body: `<p class="lead">One hour after an incident opens, OpsLens says how likely it is
      to miss its SLA, and why. Its riskiest 20% hold ${ev(`${R}.early_warning.caught_top20_opslens_pct`, "pct")} of all SLA misses;
      the desk's own priority field, ${ev(`${R}.early_warning.caught_top20_priority_pct`, "pct")}.</p>
      <button type="button" class="btn" data-goto-tab="risks">See the incidents at risk</button>` })}`;
} };

// ---- Problems: why does it go wrong? ----------------------------------------------------------

export const problems = { render(section) {
  const d = state.results[R];
  if (!d) return missingData(section);
  section.innerHTML = `${pageHeader("Why it goes wrong", "Causes of delay measured in the real event log, each with its evidence and example incidents. " + sourceLine())}
    ${d.cards.map((c, i) => problemCard(c, i)).join("")}`;
} };

function problemCard(c, i) {
  const b = `${R}.cards[${i}]`;
  const rows = c.examples.map((x, j) => `<tr><td>${evText(`${b}.examples[${j}].ticket_id`)}</td><td>${evText(`${b}.examples[${j}].category`)}</td>
      <td>${evText(`${b}.examples[${j}].team`)}</td><td>${evText(`${b}.examples[${j}].priority`)}</td>
      <td>${x.missed_sla ? "missed" : "met"}</td><td class="num">${ev(`${b}.examples[${j}].resolution_h`, "hours")}</td></tr>`).join("");
  return card({ id: `rd-card-${escapeHtml(c.id)}`, title: c.title, sub: `<span class="pill">${escapeHtml(c.cause_type)}</span>`,
    body: `<div class="grid cols-3">
        ${stat(c.metric, ev(`${b}.value`, "pct"), "in this group")}
        ${stat("Compared with", ev(`${b}.comparison_value`, "pct"), evText(`${b}.comparison_text`))}
        ${stat("Incidents affected", ev(`${b}.affected_tickets`, "int"), `${ev(`${b}.affected_share_pct`, "pct")} of the learning period`)}
      </div>
      <p><strong>What to do:</strong> ${evText(`${b}.recommendation`)}</p>
      <div class="table-wrap"><table><thead><tr><th>Example</th><th>Category</th><th>Team</th><th>Priority</th><th>SLA</th><th class="num">Resolved in</th></tr></thead>
        <tbody>${rows}</tbody></table></div>` });
}

// ---- Risks: what will go wrong next? ----------------------------------------------------------

export const risks = { render(section) {
  const d = state.results[R];
  if (!d) return missingData(section);
  const ew = `${R}.early_warning`;
  const list = d.early_warning.at_risk.map((x, i) => `<div class="risk-row">
      <div><strong>${evText(`${ew}.at_risk[${i}].ticket_id`)}</strong> <span class="small muted">${evText(`${ew}.at_risk[${i}].priority`)} ·
        ${evText(`${ew}.at_risk[${i}].team_now`)}</span>
        <ul class="reasons">${x.reasons.map((r, j) => `<li>${evText(`${ew}.at_risk[${i}].reasons[${j}].text`)}
          <span class="small muted">${ev(`${ew}.at_risk[${i}].reasons[${j}].share`, "frac_pct")} of the push</span></li>`).join("")}</ul></div>
      <div class="num"><div class="risk-p">${ev(`${ew}.at_risk[${i}].risk`, "frac_pct")}</div>
        <div class="small muted">${x.missed_sla ? "it did miss" : "it made it"}</div></div></div>`).join("");
  const fc = `${R}.forecast`;
  const week = d.forecast.next_week.filter((r) => r.forecast > r.usual_closures);
  const rows = d.forecast.next_week.map((r, i) => r.forecast > r.usual_closures ? `<tr class="hot"><td>${evText(`${fc}.next_week[${i}].team`)}</td>
      <td>${evText(`${fc}.next_week[${i}].date`)}</td><td class="num">${ev(`${fc}.next_week[${i}].forecast`, "num")}</td>
      <td class="num">${ev(`${fc}.next_week[${i}].usual_closures`, "num")}</td><td class="num">${ev(`${fc}.next_week[${i}].actual`, "int")}</td></tr>` : "").join("");
  section.innerHTML = `${pageHeader("What will go wrong", "Incidents likely to miss their SLA, scored one hour after they open, and teams likely to fall behind next week. " + sourceLine())}
    ${card({ title: "Incidents most likely to miss their SLA", sub: `Scored one hour after opening, with the reasons (TreeSHAP). Shown from the test months, so you can see if each one really missed.`,
      body: `<div class="grid cols-2">
        ${stat("Riskiest 20% hold, of all SLA misses", ev(`${ew}.caught_top20_opslens_pct`, "pct"), `desk's priority field: ${ev(`${ew}.caught_top20_priority_pct`, "pct")}`)}
        ${stat("How well the score ranks (AUC)", ev(`${ew}.auc_opslens`, "ratio"), `priority field: ${ev(`${ew}.auc_priority`, "ratio")} (0.5 = coin flip)`)}
      </div><div class="risk-list">${list}</div>` })}
    ${card({ title: "Teams likely to fall behind next week", sub: `Forecast new incidents per team and day vs what the team usually closes in a day.
      Honest note: on this data our learned forecast (WAPE ${ev(`${fc}.wape_learned`, "ratio")}) is not better than "same day last week"
      (${ev(`${fc}.wape_same_day_last_week`, "ratio")}) — three months of history is short.`,
      body: week.length ? `<div class="table-wrap"><table><thead><tr><th>Team</th><th>Day</th><th class="num">Forecast new</th>
        <th class="num">Usually closes</th><th class="num">Actually came</th></tr></thead><tbody>${rows}</tbody></table></div>`
        : `<p class="muted">No team is forecast above its usual closures next week.</p>` })}`;
} };

// ---- Actions: what should we do? -------------------------------------------------------------

// The real desk's recommendations as plan items (web/js/plan.js). Also registered at start-up
// (app.js), so Your plan can describe them before the Actions screen has been opened.
export function realPlanItems() {
  const d = state.results[R];
  if (!d) return [];
  const ew = `${R}.early_warning`;
  const triage = { id: "rd-triage", world: "real", title: "Look at the riskiest 20% of new incidents first", owner: "Service desk lead",
    effects: [{ label: "Share of all SLA misses in that 20%, OpsLens score", path: `${ew}.caught_top20_opslens_pct`, unit: "pct" },
              { label: "The same with the desk's priority field", path: `${ew}.caught_top20_priority_pct`, unit: "pct" }],
    note: "Measured on later months: this is how much earlier the right incidents get attention." };
  const fixes = d.cards.map((c, i) => ({ id: `rd-fix-${c.id}`, world: "real", title: c.recommendation, owner: "Process owner",
    effects: [{ label: c.metric + " in this group", path: `${R}.cards[${i}].value`, unit: "pct" },
              { label: c.comparison_text, path: `${R}.cards[${i}].comparison_value`, unit: "pct" }],
    note: "Evidence, not a measured effect: an event log cannot replay what would have happened after the change." }));
  return [triage, ...fixes];
}

export const actions = { render(section) {
  const d = state.results[R];
  if (!d) return missingData(section);
  const ew = `${R}.early_warning`;
  const [triage, ...fixes] = realPlanItems();
  [triage, ...fixes].forEach(registerItem);
  const box = (item, evidence) => `<div class="action-item"><div>
      <div class="action-title">${escapeHtml(item.title)}</div><div class="small muted">${escapeHtml(item.owner)} · ${evidence}</div></div>
      ${planButtons(item.id)}</div>`;
  section.innerHTML = `${pageHeader("What to do", "Actions for the real desk, each with the evidence behind it. Accept adds it to Your plan; override says why not.")}
    ${card({ title: "Prioritise by risk, not by the priority field", body: box(triage,
      `riskiest 20% hold ${ev(`${ew}.caught_top20_opslens_pct`, "pct")} of SLA misses vs ${ev(`${ew}.caught_top20_priority_pct`, "pct")}`) })}
    ${card({ title: "Fix the causes of delay", body: fixes.map((f, i) => box(f,
      `${evText(`${R}.cards[${i}].title`)}`)).join("") })}
    <div class="callout">Not recommended on this desk: letting OpsLens pick the team at opening time. It is only right more
      often than the real desk when it is very sure, and even then the gain is tiny (see Proof).</div>`;
} };

// ---- Proof: does it beat what the desk did? --------------------------------------------------

export const proof = { render(section) {
  const d = state.results[R];
  if (!d) return missingData(section);
  const ew = `${R}.early_warning`;
  const fc = `${R}.forecast`;
  const rt = `${R}.routing.test`;
  section.innerHTML = `${pageHeader("Against the real desk", "Each OpsLens prediction against what the desk itself used, on incidents opened after everything OpsLens learned from. " + sourceLine())}
    ${card({ title: "Measured on the later months", body: `<div class="table-wrap"><table>
      <thead><tr><th>Question</th><th class="num">OpsLens</th><th class="num">What the desk used</th><th>Verdict</th></tr></thead><tbody>
      <tr><td>Which incidents will miss their SLA? (ranking quality, AUC)</td><td class="num">${ev(`${ew}.auc_opslens`, "ratio")}</td>
        <td class="num">priority field ${ev(`${ew}.auc_priority`, "ratio")}</td><td><span class="pill good">much better</span></td></tr>
      <tr><td>Share of all SLA misses in the riskiest 20%</td><td class="num">${ev(`${ew}.caught_top20_opslens_pct`, "pct")}</td>
        <td class="num">${ev(`${ew}.caught_top20_priority_pct`, "pct")}</td><td><span class="pill good">about twice</span></td></tr>
      <tr><td>New incidents per team and day (forecast error, lower is better)</td><td class="num">${ev(`${fc}.wape_learned`, "ratio")}</td>
        <td class="num">same day last week ${ev(`${fc}.wape_same_day_last_week`, "ratio")}</td><td><span class="pill">not better</span></td></tr>
      <tr><td>Right team first time, only when OpsLens is sure (${ev(`${rt}.sure_share_pct`, "pct")} of incidents)</td>
        <td class="num">${ev(`${rt}.opslens_sure_right_pct`, "pct")}</td><td class="num">${ev(`${rt}.desk_on_same_right_pct`, "pct")}</td>
        <td><span class="pill">no real gain</span></td></tr>
      </tbody></table></div>
      <p class="small muted">${evText(`${R}.routing.note`)} Choices (when to stop training, how sure is "sure") were made on the last
        weeks of the learning period, never on the later months.</p>` })}`;
} };
