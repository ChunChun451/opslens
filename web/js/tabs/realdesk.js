import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, stat, fold, proofLine } from "../ui.js";
import { lookup } from "../data.js";
import { escapeHtml } from "../format.js";
import { planButtons, registerItem } from "../plan.js";

const R = "realdesk";

function missingData(section) {
  section.innerHTML = pageHeader("Real public service desk", "") +
    `<div class="callout warn">No real-data results yet: run <code>eval/run_realdesk.py</code> (part of make eval).</div>`;
}

function shortSource() {
  return "A real company's IT service desk (UCI ServiceNow log, CC BY 4.0).";
}

function sourceLine() {
  return `A real company's IT service desk (UCI ServiceNow log, CC BY 4.0). Learned on
    ${evText(`${R}.summary.learning_period[0]`)} to ${evText(`${R}.summary.learning_period[1]`)};
    every comparison is scored on later incidents (${ev(`${R}.summary.test_incidents`, "int")}).`;
}

export const overview = { render(section) {
  const d = state.results[R];
  if (!d) return missingData(section);
  const shares = Object.entries(d.summary.open_time_share_pct);
  const bar = shares.map(([k], i) => `<span class="share-seg seg-${i}" style="flex:${d.summary.open_time_share_pct[k]}"
      title="${escapeHtml(k)}"></span>`).join("");
  const legend = shares.map(([k], i) => `<li><span class="share-dot seg-${i}"></span>${escapeHtml(k)}
      ${ev(`${R}.summary.open_time_share_pct.${k}`, "pct")}</li>`).join("");
  section.innerHTML = `${pageHeader("A real service desk", shortSource())}
    ${d.fasttrack ? fastTrackLead(d) : ""}
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
`;
} };

export const problems = { render(section) {
  const d = state.results[R];
  if (!d) return missingData(section);
  section.innerHTML = `${pageHeader("Why it goes wrong", "Causes of delay in the real event log. Biggest first.")}
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
      ${replicationLine(c)}
      <p><strong>What to do:</strong> ${evText(`${b}.recommendation`)}</p>
      <details class="disclosure"><summary>Example incidents</summary>
      <div class="table-wrap"><table><thead><tr><th>Example</th><th>Category</th><th>Team</th><th>Priority</th><th>SLA</th><th class="num">Resolved in</th></tr></thead>
        <tbody>${rows}</tbody></table></div></details>` });
}

const RISKS_SHOWN = 5;
const HOT_SHOWN = 8;

export const risks = { render(section) {
  const d = state.results[R];
  if (!d) return missingData(section);
  const ew = `${R}.early_warning`;
  const item = (x, i) => `<div class="risk-row">
      <div><strong>${evText(`${ew}.at_risk[${i}].ticket_id`)}</strong> <span class="small muted">${evText(`${ew}.at_risk[${i}].priority`)} ·
        ${evText(`${ew}.at_risk[${i}].team_now`)}</span>
        <ul class="reasons">${x.reasons.map((r, j) => `<li>${evText(`${ew}.at_risk[${i}].reasons[${j}].text`)}
          <span class="small muted">${ev(`${ew}.at_risk[${i}].reasons[${j}].share`, "frac_pct")} of the push</span></li>`).join("")}</ul></div>
      <div class="num"><div class="risk-p">${ev(`${ew}.at_risk[${i}].risk`, "frac_pct")}</div>
        <div class="small muted">${x.missed_sla ? "it did miss" : "it made it"}</div></div></div>`;
  const items = d.early_warning.at_risk.map(item);
  const list = items.slice(0, RISKS_SHOWN).join("")
    + (items.length > RISKS_SHOWN ? fold(`${items.length - RISKS_SHOWN} more incidents`, items.slice(RISKS_SHOWN).join("")) : "");
  const fc = `${R}.forecast`;
  const hot = d.forecast.next_week.map((r, i) => ({ r, i })).filter(({ r }) => r.forecast > r.usual_closures)
    .sort((a, b) => (b.r.forecast - b.r.usual_closures) - (a.r.forecast - a.r.usual_closures));
  const table = (rows) => `<div class="table-wrap"><table><thead><tr><th>Team</th><th>Day</th><th class="num">Forecast new</th>
      <th class="num">Usually closes</th><th class="num">Actually came</th></tr></thead><tbody>${rows.map(({ i }) => `<tr class="hot">
      <td>${evText(`${fc}.next_week[${i}].team`)}</td><td>${evText(`${fc}.next_week[${i}].date`)}</td>
      <td class="num">${ev(`${fc}.next_week[${i}].forecast`, "num")}</td><td class="num">${ev(`${fc}.next_week[${i}].usual_closures`, "num")}</td>
      <td class="num">${ev(`${fc}.next_week[${i}].actual`, "int")}</td></tr>`).join("")}</tbody></table></div>`;
  section.innerHTML = `${pageHeader("What will go wrong", "Incidents likely to miss their SLA, and teams likely to fall behind next week.")}
    ${proofLine(`Its riskiest 20% hold <b>${ev(`${ew}.caught_top20_opslens_pct`, "pct", { key: true, title: "Misses caught by the riskiest 20%", explain: "Of all incidents in the later months that really missed their SLA, the share that were in OpsLens's riskiest 20% one hour after they opened." })}</b> of SLA misses; the desk's priority field, ${ev(`${ew}.caught_top20_priority_pct`, "pct")}.`, "#proof/rd-proof")}
    ${card({ title: "Incidents most likely to miss their SLA", sub: "Scored one hour after opening. From later months, so you can see if each one missed.",
      body: `<div class="risk-list">${list}</div>` })}
    ${card({ title: "Teams likely to fall behind next week", sub: "Forecast new incidents vs what the team usually closes in a day. Furthest above first.",
      body: hot.length ? table(hot.slice(0, HOT_SHOWN))
        + (hot.length > HOT_SHOWN ? fold(`${hot.length - HOT_SHOWN} more team-days`, table(hot.slice(HOT_SHOWN))) : "")
        : `<p class="muted">No team is forecast above its usual closures next week.</p>` })}`;
} };

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
  section.innerHTML = `${pageHeader("What to do", "Accept adds an action to Your plan; Override says why not.")}
    ${card({ title: "Prioritise by risk, not by the priority field", body: box(triage,
      `riskiest 20% hold ${ev(`${ew}.caught_top20_opslens_pct`, "pct")} of SLA misses vs ${ev(`${ew}.caught_top20_priority_pct`, "pct")}`) })}
    ${card({ title: "Fix the causes of delay", body: fixes.map((f, i) => box(f,
      `${evText(`${R}.cards[${i}].title`)}`)).join("") })}
    <div class="callout">Not recommended on this desk: letting OpsLens pick the team at opening time. It is only right more
      often than the real desk when it is very sure, and even then the gain is tiny (see Proof).</div>`;
} };

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
        weeks of the learning period, never on the later months.</p>` })}
    ${d.fasttrack ? fastTrackProof(d) : ""}
    ${d.alerts ? alertsCard(d) : ""}
    ${card({ title: "Team forecast", body: `<p>Forecast error on new incidents per team and day (lower is better): learned
      ${ev(`${R}.forecast.wape_learned`, "ratio")}, same day last week ${ev(`${R}.forecast.wape_same_day_last_week`, "ratio")}.
      Not better on this desk; three months of history is short.</p>` })}
    ${d.impact ? impactCard(d) : ""}
    ${d.blind_plants ? plantsCard(d) : ""}
    ${d.twin ? `<div class="callout">A digital twin of this desk was built to test different decisions. It failed its own check before any
      use (${evText(`${R}.twin.status`)}), so no twin number appears anywhere. See Rules we wrote first.</div>` : ""}`;
} };

const FT = `${R}.fasttrack`;

function tieWords(path) {
  const lo = lookup(path + ".ci_low"), hi = lookup(path + ".ci_high");
  if (typeof lo !== "number" || typeof hi !== "number") return "";
  return lo < 0 && hi > 0 ? "a tie" : hi <= 0 ? "OpsLens behind" : "OpsLens ahead";
}
function ciSpan(path, unit = "int") {
  return `<span class="ci">[${ev(path + ".ci_low", unit, { bare: true })}, ${ev(path + ".ci_high", unit, { bare: true })}]</span>`;
}
function pickerLabel(d, id) {
  const p = d.fasttrack.pickers.find((x) => x.id === id);
  return p ? p.label : id;
}

function fastTrackLead(d) {
  const ft = d.fasttrack;
  const at20 = ft.results["20"];
  const shown = ["priority", "unassigned", "opslens"].filter((id) => at20[id]);
  const top = Math.max(ft.ceiling.saved, ...shown.map((id) => at20[id].saved)) || 1;
  const bar = (label, path, value, cls) => `<div class="ft-row ${cls}"><span>${escapeHtml(label)}</span>
      <div class="ft-track"><i style="width:${Math.round((value / top) * 100)}%"></i></div><b>${ev(path, "int")}</b></div>`;
  const bars = shown.map((id) => bar(pickerLabel(d, id), `${FT}.results.20.${id}.saved`, at20[id].saved, id === "opslens" ? "is-ours" : ""))
    .join("") + bar("Everyone fast-tracked (the ceiling)", `${FT}.ceiling.saved`, ft.ceiling.saved, "is-ceiling");
  return card({ id: "rd-fasttrack", title: "If the desk fast-tracked a fifth of each day's new incidents",
    sub: "Missed deadlines saved on the later months, by who picks the fifth one hour after opening.",
    body: `<div class="ft-bars">${bars}</div>
      <div class="btn-row"><a class="btn btn-primary" href="#overview/rd-shadow">Watch a real day in Shadow mode</a>
        <a class="btn" href="#proof/rd-proof">How we know</a></div>` });
}

function replicationLine(c) {
  const rep = lookup(`${R}.replication.cards`);
  if (!rep) return "";
  const i = rep.findIndex((x) => x.id === c.id);
  if (i < 0) return "";
  const b = `${R}.replication.cards[${i}]`;
  const yes = rep[i].replicates;
  return `<p class="rep-line ${yes ? "is-yes" : "is-no"}"><span class="pill ${yes ? "good" : ""}">${yes ? "still true on later months" : "not confirmed on later months"}</span>
    ${ev(b + ".test.value", "pct")} vs ${ev(b + ".test.comparison", "pct")} on the later months.</p>`;
}

function alertsCard(d) {
  const a = `${R}.alerts`;
  const order = ["learned", "same_day_last_week", "average", "every_weekday"].filter((k) => d.alerts.scores[k]);
  const rows = order.map((k) => `<tr class="${k === d.alerts.chosen_forecast ? "is-chosen" : ""}">
      <td>${evText(`${a}.labels.${k}`)}${k === d.alerts.chosen_forecast ? ' <span class="pill good">chosen before the test</span>' : ""}</td>
      <td class="num">${ev(`${a}.scores.${k}.alerts`, "int")}</td><td class="num"><b>${ev(`${a}.scores.${k}.precision_pct`, "pct")}</b></td>
      <td class="num">${ev(`${a}.scores.${k}.recall_pct`, "pct")}</td></tr>`).join("");
  const c = d.alerts.chosen_forecast;
  return card({ id: "rd-alerts", title: "Overload alerts, a week ahead",
    sub: evText(`${a}.definition`),
    body: `<div class="grid cols-2">
        ${stat("OpsLens alerts that came true", ev(`${a}.scores.${c}.precision_pct`, "pct"), `and they caught ${ev(`${a}.scores.${c}.recall_pct`, "pct")} of overloaded team-days`)}
        ${stat("A calendar rule (alert every weekday)", ev(`${a}.scores.every_weekday.precision_pct`, "pct"), `catches ${ev(`${a}.scores.every_weekday.recall_pct`, "pct")}, by alerting almost always`)}
      </div>
      <div class="table-wrap"><table><thead><tr><th>Forecast</th><th class="num">Alerts</th><th class="num">Came true</th><th class="num">Overloads caught</th></tr></thead>
      <tbody>${rows}</tbody></table></div>` });
}

function fastTrackProof(d) {
  const ft = d.fasttrack;
  const order = ft.pickers.map((x) => x.id);
  const rows = order.map((id) => `<tr class="${id === "opslens" ? "is-chosen" : ""}"><td>${escapeHtml(pickerLabel(d, id))}</td>
      ${ft.budgets.map((b) => `<td class="num">${ev(`${FT}.results.${b}.${id}.saved`, "int")}${String(b) === "20" ? ` ${ciSpan(`${FT}.results.20.${id}`)}` : ""}</td>`).join("")}
      <td class="num">${id === "opslens" ? "" : `${ev(`${FT}.opslens_minus.20.${id}.diff`, "int", { signed: true })} ${ciSpan(`${FT}.opslens_minus.20.${id}`)}`}</td></tr>`).join("");
  const ex = `${FT}.example`;
  const sl = d.fasttrack_second_look;
  const second = sl ? `<div class="second-look"><span class="pill">a second look</span> ${evText(`${R}.fasttrack_second_look.label`)}
      <p>${evText(`${R}.fasttrack_second_look.chosen_label`)} saved ${ev(`${R}.fasttrack_second_look.results.20.${sl.chosen_on_check}.saved`, "int")}
        ${ciSpan(`${R}.fasttrack_second_look.results.20.${sl.chosen_on_check}`)} vs ${ev(`${R}.fasttrack_second_look.results.20.unassigned.saved`, "int")}
        for "still unassigned at 1 hour": ${ev(`${R}.fasttrack_second_look.rule.diff`, "int", { signed: true })} ${ciSpan(`${R}.fasttrack_second_look.rule`)}.
        <span class="pill ${sl.rule.passed ? "good" : "bad"}">rule ${sl.rule.passed ? "kept" : "missed"}</span></p></div>` : "";
  return card({ id: "rd-fasttrack-proof", title: "Who should the desk fast-track?",
    sub: `${evText(`${FT}.question`)} <b>Assumption:</b> ${evText(`${FT}.assumption`)}`,
    actions: `<span class="pill ${ft.rule.passed ? "good" : "bad"}">rule ${ft.rule.passed ? "kept" : "missed"}</span>`,
    body: `<div class="table-wrap"><table><thead><tr><th>Who picks</th>${ft.budgets.map((b) => `<th class="num">${b}% fast-tracked</th>`).join("")}
        <th class="num">OpsLens minus this one (20%)</th></tr></thead><tbody>${rows}
        <tr class="is-ceiling"><td>Everyone fast-tracked (the ceiling)</td><td></td><td class="num">${ev(`${FT}.ceiling.saved`, "int")}</td><td></td><td></td></tr>
      </tbody></table></div>
      <p class="small"><b>The rule, written first:</b> ${evText(`${FT}.rule.text`)} Measured: ${ev(`${FT}.rule.diff`, "int", { signed: true })}
        ${ciSpan(`${FT}.rule`)}, ${tieWords(`${FT}.rule`)}.</p>
      <p class="small muted">One real incident it would save: ${evText(`${ex}.ticket_id`)}, opened ${evText(`${ex}.opened`)}, ${evText(`${ex}.priority`)}
        (limit ${ev(`${ex}.limit_h`, "hours")}). It took ${ev(`${ex}.resolution_h`, "hours")}, of which ${ev(`${ex}.wait_after_1h_h`, "hours")}
        waiting after its first hour; fast-tracked, about ${ev(`${ex}.fast_tracked_h`, "hours")}.</p>
      ${second}` });
}

function impactCard(d) {
  const im = `${R}.impact`;
  return card({ id: "rd-impact", title: "Turnaround, productivity, service quality",
    sub: `At a ${ev(`${im}.budget_pct`, "int")}% fast-track budget. <b>Assumption:</b> ${evText(`${im}.assumption`)}`,
    body: `<div class="grid cols-3">
      ${stat("Turnaround: missed deadlines avoided", ev(`${im}.turnaround.misses_avoided_opslens`, "int"),
        `priority field ${ev(`${im}.turnaround.misses_avoided_priority`, "int")}; ceiling ${ev(`${im}.turnaround.misses_avoided_ceiling`, "int")}`)}
      ${stat("Service quality: deadlines met", ev(`${im}.service_quality.met_deadline_pct_opslens`, "pct"),
        `as it really happened ${ev(`${im}.service_quality.met_deadline_pct_as_it_happened`, "pct")}; priority field ${ev(`${im}.service_quality.met_deadline_pct_priority`, "pct")}`)}
      ${stat("Productivity", "no claim", evText(`${im}.productivity.text`))}
    </div>
    <p class="small muted">Money: ${evText(`${im}.money.why`)}</p>` });
}

function plantsCard(d) {
  const bp = `${R}.blind_plants`;
  const types = Object.keys(d.blind_plants.by_type).map((t) => `<li><b>${escapeHtml(t)}</b>
      ${ev(`${bp}.by_type.${t}.found`, "int")} of ${ev(`${bp}.by_type.${t}.of`, "int")}</li>`).join("");
  const v2 = d.detector_second_look;
  return card({ id: "rd-plants", title: "Problems planted in the real weeks: does OpsLens find them?",
    sub: `${ev(`${bp}.sets`, "int")} random sets fixed before the run, planted in ${ev(`${bp}.days`, "int")} real test days.`,
    actions: `<span class="pill">only reported</span>`,
    body: `<div class="grid cols-2">
        ${stat("Found", `${ev(`${bp}.found`, "int")} of ${ev(`${bp}.plants`, "int")}`, `${ev(`${bp}.recall_pct`, "pct")} of the plants`)}
        ${stat("False alarms on clean weeks", ev(`${bp}.false_alarms_per_30_days`, "num"), "per 30 days")}
      </div>
      <ul class="plant-types">${types}</ul>
      <p class="small">Weak on this real log, and we say so. On the simulated food floor the same kind of blind test finds
        ${ev("patterns.blind_recall.found_pct", "pct")}; three months of real history is short.</p>
      ${v2 ? `<div class="second-look"><span class="pill">a second look</span> ${evText(`${R}.detector_second_look.label`)}
        <p>A retuned detector found ${ev(`${R}.detector_second_look.found_v2`, "int")} of ${ev(`${R}.detector_second_look.test_plants`, "int")} fresh plants,
        the old one ${ev(`${R}.detector_second_look.found_v1`, "int")}.
        <span class="pill ${v2.rule.passed ? "good" : "bad"}">rule ${v2.rule.passed ? "kept" : "missed"}</span></p></div>` : ""}` });
}
