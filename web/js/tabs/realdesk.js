import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { card, stat } from "../ui.js";
import { lookup } from "../data.js";
import { escapeHtml } from "../format.js";

const R = "realdesk";

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

export function fastTrackLead(d) {
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

export function alertsCard(d) {
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

export function fastTrackProof(d) {
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

export function impactCard(d) {
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

export function plantsCard(d) {
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
