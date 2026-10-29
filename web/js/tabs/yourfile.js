import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { card, fold } from "../ui.js";
import { escapeHtml } from "../format.js";

const U = "upload";

const WORDS = {
  road_traffic_density: "traffic", weatherconditions: "weather", weather_conditions: "weather",
  type_of_order: "order type", type_of_vehicle: "vehicle", vehicle_condition: "vehicle condition",
  multiple_deliveries: "multiple deliveries", delivery_person_ratings: "rider rating",
  delivery_person_age: "rider age", assignment_group: "team", first_team: "team",
};

export function itemWord(one = false) {
  const noun = (state.upload && state.upload.noun) || "items";
  return one ? noun.replace(/s$/, "") : noun;
}

export function nounText(text) {
  return String(text).replace(/\bitems\b/g, itemWord()).replace(/\bitem\b/g, itemWord(true));
}

export function readable(column) {
  const name = String(column);
  const mapped = state.upload && state.upload.mapping ? state.upload.mapping[name] : "";
  if (["team", "category", "priority"].includes(name) && mapped && mapped !== name) return readable(mapped);
  const key = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return WORDS[key] || name.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_\s]+/g, " ").trim().toLowerCase();
}

export function plainReason(text) {
  const t = String(text).trim();
  const names = ((state.upload && state.upload.features) || []).slice().sort((a, b) => b.length - a.length);
  const name = names.find((n) => t.startsWith(n + ":") || t.startsWith(n + " "));
  const words = name ? readable(name) + t.slice(name.length) : t;
  return words.replace(/ in its team$/, ` in its ${readable("team")}`);
}

const capital = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text);

export function rivalWords(r) {
  if (r.warning.vs.rival === "priority") return "your priority field";
  return escapeHtml(r.rule_column ? `a rule of thumb (past miss rate by ${readable(r.rule_column)})` : "a rule of thumb (the past miss rate)");
}

export function oneIn(r) {
  return evText(`${U}.flag_share_pct`, `1 in ${Math.round(100 / r.flag_share_pct)}`);
}

export function missWords(r) {
  const m = r.miss || {};
  if (m.rule === "promise") {
    return m.assumed
      ? `A miss is taking longer than ${ev(`${U}.miss.target_min`, "dur")}: OpsLens's assumption, as your file has no on-time column.`
      : `A miss is taking longer than your promise of ${ev(`${U}.miss.target_min`, "dur")}.`;
  }
  if (m.rule === "due_at") return `A miss is finishing after your file's own ${evText(`${U}.miss.column`)} time.`;
  return `A miss is what your file's own ${evText(`${U}.miss.column`)} column says.`;
}

export function stampHtml(stillTrue) {
  return `<span class="stamp ${stillTrue ? "is-yes" : "is-no"}">${stillTrue ? "still true later" : "not confirmed later"}</span>`;
}

export function groupName(c, i) {
  return evText(`${U}.cards[${i}].value`, `${readable(c.column)}: ${String(c.value).trim()}`);
}

export function forecastProof(r) {
  const f = r.forecast;
  if (!f || f.needs) return "";
  const fc = `${U}.forecast`;
  const word = readable("team");
  const better = f.wape_learned < f.wape_same_weekday_last_week;
  const teams = f.by_team.map((t, i) => `<tr><td>${evText(`${fc}.by_team[${i}].team`)}</td><td class="num">${ev(`${fc}.by_team[${i}].items`, "int")}</td>
      <td class="num">${ev(`${fc}.by_team[${i}].wape_learned`, "ratio")}</td><td class="num">${ev(`${fc}.by_team[${i}].wape_same_weekday_last_week`, "ratio")}</td></tr>`).join("");
  return card({ title: `Workload forecast per ${word}`,
    sub: `Learned on ${evText(`${fc}.learned_days[0]`)} to ${evText(`${fc}.learned_days[1]`)}; scored on ${evText(`${fc}.scored_days[0]`)} to
      ${evText(`${fc}.scored_days[1]`)}, days it never saw.`,
    body: `<p>Forecast error (lower is better): learned ${ev(`${fc}.wape_learned`, "ratio")}, same weekday last week
        ${ev(`${fc}.wape_same_weekday_last_week`, "ratio")}. <b>${better ? "On your file the learned forecast is better."
          : "On your file the learned forecast is not better than same weekday last week."}</b>
        The days just before had picked ${f.chosen_on_check === "learned" ? "the learned one" : "same weekday last week"}.</p>
      ${fold(`Forecast error per ${word}`, `<div class="table-wrap"><table><thead><tr><th>${escapeHtml(capital(word))}</th><th class="num">New ${escapeHtml(itemWord())}</th>
        <th class="num">Learned</th><th class="num">Same weekday last week</th></tr></thead><tbody>${teams}</tbody></table></div>`)}` });
}

export function filePlanItems() {
  const r = state.upload;
  const meta = state.uploadMeta;
  if (!r || !meta) return [];
  const source = `upload:${meta.token}`;
  const w = `${U}.warning`;
  const rival = r.warning.vs.rival;
  const warn = { id: `file-${meta.token}-warn`, world: "real", source, owner: "Team lead", fileIndex: 0,
    title: `Flag the riskiest 1 in ${Math.round(100 / r.flag_share_pct)} new ${itemWord()} as they open, and look at them first`,
    effects: [{ label: `Real misses caught on your later ${itemWord()}, OpsLens`, path: `${w}.caught_pct.opslens`, unit: "pct" },
              { label: `The same, ${r.warning.vs.rival === "priority" ? "your priority field" : "a rule of thumb"}`, path: `${w}.caught_pct.${rival}`, unit: "pct" }],
    note: `Measured on your later ${itemWord()}, which OpsLens never learned from.` };
  const fixes = r.cards.map((c, i) => ({ id: `file-${meta.token}-fix-${i}`, world: "real", source, owner: "Process owner",
    fileIndex: i + 1, groupWord: `${readable(c.column)} = ${String(c.value).trim()}`,
    title: `Look at ${readable(c.column)} = ${String(c.value).trim()}`,
    effects: [{ label: `Real misses in this group, on your later ${itemWord()}`, path: `${U}.cards[${i}].test_misses`, unit: "int" },
              { label: "Missed in this group, later", path: `${U}.cards[${i}].test_pct`, unit: "pct" },
              { label: "Missed in the rest, later", path: `${U}.cards[${i}].test_rest_pct`, unit: "pct" }],
    note: "Measured in your file. A log cannot say what fixing it would have saved." }));
  return [warn, ...fixes];
}
