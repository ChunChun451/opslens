import { state } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, stat, fold } from "../ui.js";
import { escapeHtml } from "../format.js";
import { planButtons, registerItem } from "../plan.js";

const U = "upload";
const HOT_SHOWN = 8;

const WORDS = {
  road_traffic_density: "traffic", weatherconditions: "weather", weather_conditions: "weather",
  type_of_order: "order type", type_of_vehicle: "vehicle", vehicle_condition: "vehicle condition",
  multiple_deliveries: "multiple deliveries", delivery_person_ratings: "rider rating",
  delivery_person_age: "rider age", assignment_group: "team", first_team: "team",
};

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

function oneIn(r) {
  return evText(`${U}.flag_share_pct`, `1 in ${Math.round(100 / r.flag_share_pct)}`);
}

function missWords(r) {
  const m = r.miss || {};
  if (m.rule === "promise") {
    return m.assumed
      ? `A miss is taking longer than ${ev(`${U}.miss.target_min`, "dur")}: OpsLens's assumption, as your file has no on-time column.`
      : `A miss is taking longer than your promise of ${ev(`${U}.miss.target_min`, "dur")}.`;
  }
  if (m.rule === "due_at") return `A miss is finishing after your file's own ${evText(`${U}.miss.column`)} time.`;
  return `A miss is what your file's own ${evText(`${U}.miss.column`)} column says.`;
}

function needsLine(key, what) {
  return `<p class="needs"><b>${escapeHtml(what)}</b> needs ${evText(`${U}.needs.${key}`) || escapeHtml(`a ${key} column`)}.</p>`;
}

export function stampHtml(stillTrue) {
  return `<span class="stamp ${stillTrue ? "is-yes" : "is-no"}">${stillTrue ? "still true later" : "not confirmed later"}</span>`;
}

function groupName(c, i) {
  return evText(`${U}.cards[${i}].value`, `${readable(c.column)}: ${String(c.value).trim()}`);
}

function noFile(section) {
  section.innerHTML = pageHeader("Your file", "") +
    card({ body: `<p class="muted">No file analysed yet. Press <b>Upload a CSV</b> above.</p>` });
}

export const overview = { render(section) {
  const r = state.upload;
  if (!r) return noFile(section);
  section.innerHTML = `${pageHeader(`Your file: ${r.file}`, `${ev(`${U}.summary.items`, "int")} items from
      ${evText(`${U}.summary.from`)} to ${evText(`${U}.summary.to`)}. ${missWords(r)} OpsLens learned on your first
      ${ev(`${U}.learn.items`, "int")} items and scored the last ${ev(`${U}.test.items`, "int")}, which it never saw.`)}
    ${headline(r)}
    <section class="card stat-card"><div class="grid cols-4">
      ${stat("Items", ev(`${U}.summary.items`, "int"), `over ${ev(`${U}.summary.days`, "int")} days`)}
      ${stat("Missed", ev(`${U}.summary.missed_pct`, "pct"), "of all items")}
      ${stat("Median time", ev(`${U}.summary.median_min`, "dur"), `90% within ${ev(`${U}.summary.p90_min`, "dur")}`)}
      ${stat("Analysed in", ev(`${U}.seconds`, "sec"), "on this laptop")}
    </div></section>
    ${shadowBrief(r)}
    ${topProblems(r)}`;
} };

function headline(r) {
  const rival = r.warning.vs.rival;
  return card({ id: "up-headline", cls: "up-headline", body: `<p class="lead-line">Flagging ${oneIn(r)} items as they opened,
      OpsLens caught <b class="t-ours">${ev(`${U}.warning.caught_pct.opslens`, "pct")}</b> of the real misses on your later items;
      ${rivalWords(r)} caught ${ev(`${U}.warning.caught_pct.${rival}`, "pct")}. Gap ${ev(`${U}.warning.vs.gap_pts`, "pts", { signed: true })},
      95% interval ${ev(`${U}.warning.vs.ci[0]`, "pts", { signed: true, bare: true })} to ${ev(`${U}.warning.vs.ci[1]`, "pts", { signed: true, bare: true })}
      points over days.</p>
      ${rival === "priority" ? "" : needsLine("priority", "The comparison with your priority field")}
      <div class="btn-row"><a class="btn" href="#risks/up-risks">See the items at risk</a><a class="btn" href="#proof/up-proof">How it was tested</a></div>` });
}

function shadowBrief(r) {
  const rival = r.warning.vs.rival;
  return card({ title: "Your busiest later day, replayed", sub: "Shadow mode: each one flags the same number of items as they open. Who caught more of the real misses?",
    body: `<p>On ${evText(`${U}.shadow.weekday`)} ${evText(`${U}.shadow.date`, prettyDate(r.shadow.date))}, ${ev(`${U}.shadow.items`, "int")} items opened and
      ${ev(`${U}.shadow.misses`, "int")} really missed. With ${ev(`${U}.shadow.flags`, "int")} flags each, OpsLens caught
      <b class="t-ours">${ev(`${U}.shadow.caught.opslens`, "int")}</b>; ${rivalWords(r)}, ${ev(`${U}.shadow.caught.${rival}`, "int")}.</p>
      <div class="btn-row"><a class="btn btn-primary" href="#overview/up-shadow">Watch it in Shadow mode</a></div>` });
}

function topProblems(r) {
  if (!r.cards.length) {
    return card({ title: "The biggest problems", body: `<p class="muted">No group in your file misses clearly more often than the rest.</p>` });
  }
  return card({ title: "The biggest problems", sub: "Open Problems for the evidence.",
    body: `<ol class="issues up-issues">${r.cards.slice(0, 3).map((c, i) => `<li class="issue" data-goto-tab="problems" data-goto-id="up-card-${i}">
        <span class="issue-title">${groupName(c, i)}</span>${stampHtml(c.still_true)}
        <span class="issue-text">${ev(`${U}.cards[${i}].learn_pct`, "pct")} missed vs ${ev(`${U}.cards[${i}].learn_rest_pct`, "pct")}
          for the rest, on your first items</span></li>`).join("")}</ol>` });
}

function prettyDate(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export const problems = { render(section) {
  const r = state.upload;
  if (!r) return noFile(section);
  section.innerHTML = `${pageHeader("Why it goes wrong", `Groups of your items that missed far more often than the rest on
      your first ${ev(`${U}.learn.items`, "int")} items, each measured again on the last ${ev(`${U}.test.items`, "int")}, which the search never saw.`)}
    ${r.cards.length ? `<div class="finding-grid">${r.cards.map(findingCard).join("")}</div>`
      : card({ body: `<p class="muted">No group in your file misses clearly more often than the rest.</p>` })}
    <div class="grid cols-3 up-worst">${["team", "category", "priority"].map((key) => worstTable(r, key)).join("")}</div>`;
} };

function findingCard(c, i) {
  const b = `${U}.cards[${i}]`;
  const top = Math.max(c.learn_pct, c.learn_rest_pct, c.test_pct, c.test_rest_pct) || 1;
  const bar = (label, key, cls) => `<div class="mini-bar"><span>${label}</span><div class="cbar-track"><div class="cbar-fill ${cls}"
      style="width: ${Math.round((c[key] / top) * 100)}%"></div></div><span class="cbar-value">${ev(`${b}.${key}`, "pct")}</span></div>`;
  const examples = c.examples.map((x, j) => evText(`${b}.examples[${j}]`)).join(", ");
  return `<article class="card finding-card" id="up-card-${i}" tabindex="0">
      <div class="finding-meta"><span class="cause-tag">${escapeHtml(readable(c.column))}</span>${stampHtml(c.still_true)}</div>
      <h3>${groupName(c, i)}</h3>
      <div class="finding-bars">
        <div class="finding-metric">Missed, on your first ${ev(`${U}.learn.items`, "int")} items</div>
        ${bar("This group", "learn_pct", "is-bad")}${bar("The rest", "learn_rest_pct", "is-normal")}
        <div class="finding-metric">Missed, on the later ${ev(`${U}.test.items`, "int")} it never saw</div>
        ${bar("This group", "test_pct", "is-bad")}${bar("The rest", "test_rest_pct", "is-normal")}
      </div>
      <p class="small">Later, this group misses ${ev(`${b}.gap_ci[0]`, "pts", { signed: true, bare: true })} to
        ${ev(`${b}.gap_ci[1]`, "pts", { signed: true, bare: true })} points more often than the rest (95% interval over days).
        ${ev(`${b}.learn_items`, "int")} items in the first part, ${ev(`${b}.test_items`, "int")} later.</p>
      ${examples ? `<p class="small muted">Items that missed: ${examples}</p>` : ""}
    </article>`;
}

function worstTable(r, key) {
  const rows = r.summary[`by_${key}`];
  const word = readable(key);
  if (!rows) return card({ title: `Missed most, by ${key}`, body: needsLine(key, "This table") });
  if (!rows.length) return card({ title: `Missed most, by ${word}`, body: `<p class="muted">No ${escapeHtml(word)} has enough items to compare.</p>` });
  const p = `${U}.summary.by_${key}`;
  const body = rows.map((x, i) => `<tr><td>${evText(`${p}[${i}].name`)}</td><td class="num">${ev(`${p}[${i}].items`, "int")}</td>
      <td class="num">${ev(`${p}[${i}].missed_pct`, "pct")}</td></tr>`).join("");
  return card({ title: `Missed most, by ${word}`, body: `<div class="table-wrap"><table><thead><tr><th>${escapeHtml(capital(word))}</th>
      <th class="num">Items</th><th class="num">Missed</th></tr></thead><tbody>${body}</tbody></table></div>` });
}

export const risks = { render(section) {
  const r = state.upload;
  if (!r) return noFile(section);
  const w = `${U}.warning`;
  const rival = r.warning.vs.rival;
  const list = r.warning.at_risk.map((x, i) => `<div class="risk-row">
      <div><strong>${evText(`${w}.at_risk[${i}].id`)}</strong> <span class="small muted">opened ${evText(`${w}.at_risk[${i}].opened`)}</span>
        <ul class="reasons">${x.reasons.map((reason, j) => `<li>${evText(`${w}.at_risk[${i}].reasons[${j}].text`, plainReason(reason.text))}
          <span class="small muted">${ev(`${w}.at_risk[${i}].reasons[${j}].share`, "frac_pct")} of the push</span></li>`).join("")}</ul></div>
      <div class="num"><div class="risk-p">${ev(`${w}.at_risk[${i}].risk`, "frac_pct")}</div>
        <div class="small ${x.missed ? "bad" : "muted"}">${x.missed ? "it did miss" : "it made it"}</div></div></div>`).join("");
  section.innerHTML = `${pageHeader("What will go wrong", `Items likely to miss, scored the moment they opened, and how much work
      each ${escapeHtml(readable("team"))} gets a week ahead. From your later items, which OpsLens never learned from.`)}
    ${card({ title: "Items most likely to miss", sub: "Scored the moment each one opened, with the model's own reasons. You can see if each one really missed.",
      body: `<div class="grid cols-2">
        ${stat("Real misses OpsLens caught", ev(`${w}.caught_pct.opslens`, "pct"),
          `flagging ${oneIn(r)} as they opened; ${rivalWords(r)}: ${ev(`${w}.caught_pct.${rival}`, "pct")}`)}
        ${stat("How well the score ranks (AUC)", ev(`${w}.auc.opslens`, "ratio"), `${rivalWords(r)}: ${ev(`${w}.auc.${rival}`, "ratio")}; higher is better`)}
      </div><div class="risk-list">${list}</div>` })}
    ${forecastCard(r)}`;
} };

function forecastCard(r) {
  const f = r.forecast;
  const word = readable("team");
  const title = `Workload a week ahead, per ${word}`;
  if (f.needs) return card({ id: "up-forecast", title, body: `<p class="needs"><b>This forecast</b> needs ${evText(`${U}.forecast.needs`)}.</p>` });
  const fc = `${U}.forecast`;
  const better = f.wape_learned < f.wape_same_weekday_last_week;
  const hot = f.first_week.map((x, i) => ({ x, i })).filter(({ x }) => x.forecast > x.usual_ends)
    .sort((a, b) => (b.x.forecast - b.x.usual_ends) - (a.x.forecast - a.x.usual_ends));
  const table = (list) => `<div class="table-wrap"><table><thead><tr><th>${escapeHtml(capital(word))}</th><th>Day</th>
      <th class="num">Forecast new</th><th class="num">Usually finishes</th><th class="num">Actually came</th></tr></thead><tbody>${list.map(({ i }) =>
      `<tr><td>${evText(`${fc}.first_week[${i}].team`)}</td><td>${evText(`${fc}.first_week[${i}].date`)}</td>
      <td class="num"><b>${ev(`${fc}.first_week[${i}].forecast`, "num")}</b></td><td class="num">${ev(`${fc}.first_week[${i}].usual_ends`, "num")}</td>
      <td class="num">${ev(`${fc}.first_week[${i}].actual`, "int")}</td></tr>`).join("")}</tbody></table></div>`;
  const teams = f.by_team.map((t, i) => `<tr><td>${evText(`${fc}.by_team[${i}].team`)}</td><td class="num">${ev(`${fc}.by_team[${i}].items`, "int")}</td>
      <td class="num">${ev(`${fc}.by_team[${i}].wape_learned`, "ratio")}</td><td class="num">${ev(`${fc}.by_team[${i}].wape_same_weekday_last_week`, "ratio")}</td></tr>`).join("");
  return card({ id: "up-forecast", title,
    sub: `New items per ${escapeHtml(word)} and day, forecast a week ahead. Learned on ${evText(`${fc}.learned_days[0]`)} to
      ${evText(`${fc}.learned_days[1]`)}; scored on ${evText(`${fc}.scored_days[0]`)} to ${evText(`${fc}.scored_days[1]`)}, days it never saw.`,
    body: `<p>Forecast error (lower is better): learned ${ev(`${fc}.wape_learned`, "ratio")}, same weekday last week
        ${ev(`${fc}.wape_same_weekday_last_week`, "ratio")}. <b>${better ? "On your file the learned forecast is better."
          : "On your file the learned forecast is not better than same weekday last week."}</b>
        The days just before had picked ${f.chosen_on_check === "learned" ? "the learned one" : "same weekday last week"}.</p>
      ${hot.length ? `<div class="section-label">The busiest days of the first scored week</div>${table(hot.slice(0, HOT_SHOWN))}
          <p class="small muted">Forecast more new items than the ${escapeHtml(word)} usually finishes in a day, furthest above first.</p>
          ${hot.length > HOT_SHOWN ? fold("Every such day in the first scored week", table(hot)) : ""}`
        : `<p class="muted">In the first scored week, no ${escapeHtml(word)} was forecast more than it usually finishes in a day.</p>`}
      ${fold(`Forecast error per ${word}`, `<div class="table-wrap"><table><thead><tr><th>${escapeHtml(capital(word))}</th><th class="num">New items</th>
        <th class="num">Learned</th><th class="num">Same weekday last week</th></tr></thead><tbody>${teams}</tbody></table></div>`)}` });
}

export function filePlanItems() {
  const r = state.upload;
  const meta = state.uploadMeta;
  if (!r || !meta) return [];
  const source = `upload:${meta.token}`;
  const w = `${U}.warning`;
  const rival = r.warning.vs.rival;
  const warn = { id: `file-${meta.token}-warn`, world: "real", source, owner: "Team lead",
    title: `Flag the riskiest 1 in ${Math.round(100 / r.flag_share_pct)} new items as they open, and look at them first`,
    effects: [{ label: "Real misses caught on your later items, OpsLens", path: `${w}.caught_pct.opslens`, unit: "pct" },
              { label: `The same, ${r.warning.vs.rival === "priority" ? "your priority field" : "a rule of thumb"}`, path: `${w}.caught_pct.${rival}`, unit: "pct" }],
    note: "Measured on your later items, which OpsLens never learned from." };
  const fixes = r.cards.map((c, i) => ({ id: `file-${meta.token}-fix-${i}`, world: "real", source, owner: "Process owner",
    title: `Look at ${readable(c.column)} = ${String(c.value).trim()}`,
    effects: [{ label: "Real misses in this group, on your later items", path: `${U}.cards[${i}].test_misses`, unit: "int" },
              { label: "Missed in this group, later", path: `${U}.cards[${i}].test_pct`, unit: "pct" },
              { label: "Missed in the rest, later", path: `${U}.cards[${i}].test_rest_pct`, unit: "pct" }],
    note: "Measured in your file. A log cannot say what fixing it would have saved." }));
  return [warn, ...fixes];
}

export const actions = { render(section) {
  const r = state.upload;
  if (!r) return noFile(section);
  const [warn, ...fixes] = filePlanItems();
  [warn, ...fixes].forEach(registerItem);
  const w = `${U}.warning`;
  const box = (item, evidence) => `<div class="action-item"><div>
      <div class="action-title">${escapeHtml(item.title)}</div><div class="small muted">${escapeHtml(item.owner)} · ${evidence}</div></div>
      ${planButtons(item.id)}</div>`;
  const fixList = fixes.map((f, i) => box(f, `${ev(`${U}.cards[${i}].test_pct`, "pct")} missed on your later items vs
      ${ev(`${U}.cards[${i}].test_rest_pct`, "pct")} for the rest; ${ev(`${U}.cards[${i}].test_misses`, "int")} real misses in this group
      ${stampHtml(r.cards[i].still_true)}`)).join("");
  section.innerHTML = `${pageHeader("What to do", "Actions for your file, each with the evidence behind it. Accept adds it to Your plan; Override says why not.")}
    ${card({ title: "Early warning", body: box(warn, `flagging ${oneIn(r)} as they opened caught
      ${ev(`${w}.caught_pct.opslens`, "pct")} of the real misses on your later items; ${rivalWords(r)}, ${ev(`${w}.caught_pct.${r.warning.vs.rival}`, "pct")}`) })}
    ${card({ title: "Fix first", sub: "Ranked by how many extra misses each group had on your first items.",
      body: fixList || `<p class="muted">No group misses clearly more often than the rest, so nothing needs fixing first.</p>` })}
    <p class="up-oneline">No Simulate here: a log cannot be replayed under different decisions. Every number above is measured in your file.</p>`;
} };

export const proof = { render(section) {
  const r = state.upload;
  if (!r) return noFile(section);
  const w = `${U}.warning`;
  const rows = ["opslens", "priority", "rule"].map((k) => pickerRow(r, k)).join("");
  const learned = r.features.map(readable).join(", ");
  const dropped = r.dropped_after_the_fact.length
    ? `Dropped, because each one alone gives the outcome away (written after the fact): ${evText(`${U}.dropped_after_the_fact`, r.dropped_after_the_fact.map(readable).join(", "))}.`
    : "No column gave the outcome away, so none was dropped.";
  section.innerHTML = `${pageHeader("Does it work on your file?", `Each picker flags the same share of each day's items as they open. Scored once on
      your last ${ev(`${U}.test.items`, "int")} items, which OpsLens never saw.`)}
    ${card({ title: "Scored once, on items it never saw", body: `<div class="table-wrap"><table>
        <thead><tr><th>Who flags</th><th class="num">How well it ranks (AUC)</th><th class="num">Real misses caught</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <p class="small">OpsLens minus ${rivalWords(r)}: ${ev(`${w}.vs.gap_pts`, "pts", { signed: true })} of the real misses caught
        (95% interval ${ev(`${w}.vs.ci[0]`, "pts", { signed: true, bare: true })} to ${ev(`${w}.vs.ci[1]`, "pts", { signed: true, bare: true })} points,
        resampling whole days). ${ev(`${w}.misses`, "int")} real misses among ${ev(`${w}.items`, "int")} later items.</p>` })}
    ${card({ title: "How it learned", body: `<ul class="list">
        <li>Learned on ${ev(`${U}.learn.items`, "int")} items from ${evText(`${U}.learn.from`)} to ${evText(`${U}.learn.to`)} (the most recent
          of those only to decide when to stop learning); scored once on ${ev(`${U}.test.items`, "int")} items from ${evText(`${U}.test.from`)}
          to ${evText(`${U}.test.to`)}. Nothing was chosen on the scored items.</li>
        <li>Learned from what was known when each item opened: ${evText(`${U}.features`, learned)}.</li>
        <li>${dropped}</li></ul>` })}
    ${card({ title: "How to read this", body: `<ul class="list">${r.notes.map((n, i) => `<li>${evText(`${U}.notes[${i}]`)}</li>`).join("")}</ul>` })}
    ${card({ title: "What this file cannot tell you", body: `<ul class="list">${r.cannot.map((n, i) => `<li>${evText(`${U}.cannot[${i}]`)}</li>`).join("")}</ul>` })}`;
} };

function pickerRow(r, k) {
  const w = `${U}.warning`;
  const name = k === "opslens" ? "OpsLens" : k === "priority" ? "Your priority field"
    : escapeHtml(`A rule of thumb${r.rule_column ? ` (past miss rate by ${readable(r.rule_column)})` : ""}`);
  if (!(k in r.warning.auc)) {
    return `<tr><td>${name}</td><td colspan="2"><span class="needs">needs ${evText(`${U}.needs.priority`) || "a priority column"}</span></td></tr>`;
  }
  return `<tr class="${k === "opslens" ? "is-chosen" : ""}"><td>${name}</td><td class="num">${ev(`${w}.auc.${k}`, "ratio")}</td>
    <td class="num">${ev(`${w}.caught_pct.${k}`, "pct")}</td></tr>`;
}
