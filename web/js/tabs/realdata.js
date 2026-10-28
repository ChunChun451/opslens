import { state, lookup } from "../data.js";
import { ev, evText } from "../evidence.js";
import { pageHeader, card, stat, fold, proofLine } from "../ui.js";
import { escapeHtml } from "../format.js";
import { planButtons, registerItem } from "../plan.js";
import { realPlanItems, fastTrackLead, fastTrackProof, alertsCard, impactCard, plantsCard } from "./realdesk.js";
import { filePlanItems, readable, plainReason, rivalWords, stampHtml, missWords, oneIn, groupName, forecastProof } from "./yourfile.js";

const R = "realdesk";
const U = "upload";
const RISKS_SHOWN = 5;
const HOT_SHOWN = 8;

function note(text) {
  return `<p class="needs rd-note">${text}</p>`;
}

function prettyDate(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

function capital(text) {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

function lowerFirst(text) {
  return /^[A-Z]{2}/.test(text) ? text : text.charAt(0).toLowerCase() + text.slice(1);
}

function uciModel() {
  const d = state.results[R];
  if (!d) return null;
  const ew = `${R}.early_warning`;
  const fc = `${R}.forecast`;
  const rep = lookup(`${R}.replication.cards`) || [];
  const showcase = (d.shadow && d.shadow.shown_days || []).find((x) => x.date === d.shadow.showcase);
  const showIdx = showcase ? d.shadow.shown_days.indexOf(showcase) : -1;
  const sh = `${R}.shadow.shown_days[${showIdx}].summary`;
  const shares = Object.entries(d.summary.open_time_share_pct || {});
  const [triage, ...fixes] = realPlanItems();
  return {
    key: "rd", items: "incidents", team: "team", proofHref: "#proof/rd-proof", shadowHref: "#overview/rd-shadow",
    title: "A real service desk",
    sub: `A real company's IT service desk (UCI ServiceNow log, CC BY 4.0). Learned on ${evText(`${R}.summary.learning_period[0]`)} to
      ${evText(`${R}.summary.learning_period[1]`)}; scored on later incidents.`,
    headline: `Flagging the riskiest 1 in 5 incidents one hour after they opened, OpsLens caught
      <b class="t-ours">${ev(`${ew}.caught_top20_opslens_pct`, "pct", { key: true, title: "Misses caught by the riskiest 20%", explain: "Of all incidents in the later months that really missed their SLA, the share that were in OpsLens's riskiest 20% one hour after they opened." })}</b>
      of the real SLA misses on later months; the desk's priority field caught ${ev(`${ew}.caught_top20_priority_pct`, "pct")}.`,
    tiles: [
      ["Items", ev(`${R}.summary.incidents`, "int"), `incidents · ${ev(`${R}.summary.teams`, "int")} teams, ${ev(`${R}.summary.agents`, "int")} agents`],
      ["Missed their promise", ev(`${R}.summary.missed_sla_pct`, "pct"), "the company's own SLA flag"],
      ["Median time to finish", ev(`${R}.summary.median_resolution_h`, "hours"), "from opening to resolved"],
      ["Passed between teams", ev(`${R}.summary.passed_between_teams_pct`, "pct"), "at least once"],
    ],
    shadow: showcase ? `<p>On ${escapeHtml(showcase.weekday)} ${escapeHtml(prettyDate(showcase.date))}, ${ev(`${sh}.benchmark_incidents`, "int")} incidents
        opened and ${ev(`${sh}.actual_misses_benchmark`, "int")} really missed. With ${ev(`${sh}.opslens.flagged`, "int")} flags each, OpsLens caught
        <b class="t-ours">${ev(`${sh}.opslens.caught`, "int")}</b>; the priority field, ${ev(`${sh}.priority.caught`, "int")}.</p>` : "",
    fasttrack: d.fasttrack ? fastTrackLead(d, true) : "",
    openTime: shares.length ? `<div class="share-bar">${shares.map(([k], i) => `<span class="share-seg seg-${i}" style="flex:${d.summary.open_time_share_pct[k]}"
        title="${escapeHtml(k)}"></span>`).join("")}</div><ul class="share-legend">${shares.map(([k], i) => `<li><span class="share-dot seg-${i}"></span>${escapeHtml(k)}
        ${ev(`${R}.summary.open_time_share_pct.${k}`, "pct")}</li>`).join("")}</ul>` : "",
    cards: d.cards.map((c, i) => {
      const b = `${R}.cards[${i}]`;
      const j = rep.findIndex((x) => x.id === c.id);
      const t = `${R}.replication.cards[${j}].test`;
      return {
        id: `rd-card-${c.id}`, tag: c.cause_type, title: evText(`${b}.title`), metric: c.metric.replace(/ \(%\)$/, ""),
        stamp: j < 0 ? null : rep[j].replicates,
        bars: [["This group", c.value, ev(`${b}.value`, "pct")], [capital(c.comparison_text), c.comparison_value, ev(`${b}.comparison_value`, "pct")]],
        later: j < 0 ? "" : `Later months: ${ev(`${t}.value`, "pct")} vs ${ev(`${t}.comparison`, "pct")}.`,
        size: `${ev(`${b}.affected_tickets`, "int")} incidents (${ev(`${b}.affected_share_pct`, "pct")} of the learning period)`,
        todo: evText(`${b}.recommendation`),
        examples: c.examples.map((x, k) => evText(`${b}.examples[${k}].ticket_id`)).join(", "),
      };
    }),
    worst: ["team", "category", "priority"].map((key) => ({ key, word: key, empty: true, body: note("Not available for this source: the cards above come from the event log instead.") })),
    riskProof: `Flagging the riskiest 1 in 5 one hour after opening, OpsLens caught <b>${ev(`${ew}.caught_top20_opslens_pct`, "pct")}</b> of the later SLA misses; the desk's priority field, ${ev(`${ew}.caught_top20_priority_pct`, "pct")}.`,
    riskSub: "Scored one hour after opening. From later months, so you can see if each one missed.",
    atRisk: d.early_warning.at_risk.map((x, i) => ({
      id: evText(`${ew}.at_risk[${i}].ticket_id`), meta: `${evText(`${ew}.at_risk[${i}].priority`)} · ${evText(`${ew}.at_risk[${i}].team_now`)}`,
      reasons: x.reasons.map((r, k) => `${evText(`${ew}.at_risk[${i}].reasons[${k}].text`)} <span class="small muted">${ev(`${ew}.at_risk[${i}].reasons[${k}].share`, "frac_pct")} of the push</span>`),
      risk: ev(`${ew}.at_risk[${i}].risk`, "frac_pct"), missed: x.missed_sla,
    })),
    forecast: { rows: d.forecast.next_week.map((r, i) => ({ over: r.forecast - r.usual_closures,
      cells: [evText(`${fc}.next_week[${i}].team`), evText(`${fc}.next_week[${i}].date`), ev(`${fc}.next_week[${i}].forecast`, "num"),
              ev(`${fc}.next_week[${i}].usual_closures`, "num"), ev(`${fc}.next_week[${i}].actual`, "int")] })) },
    plan: [triage, ...fixes],
    planEvidence: [`flagging the riskiest 1 in 5 one hour after opening caught ${ev(`${ew}.caught_top20_opslens_pct`, "pct")} of the later SLA misses; the desk's priority field, ${ev(`${ew}.caught_top20_priority_pct`, "pct")}`,
      ...d.cards.map((c, i) => `${evText(`${R}.cards[${i}].title`)}`)],
    notOnList: "Not on this list: letting OpsLens pick the team at opening time. It is only right more often than the real desk when it is very sure, and even then the gain is tiny (see Proof).",
    proofRows: [
      ["OpsLens", ev(`${ew}.auc_opslens`, "ratio"), ev(`${ew}.caught_top20_opslens_pct`, "pct"), true],
      ["The desk's priority field", ev(`${ew}.auc_priority`, "ratio"), ev(`${ew}.caught_top20_priority_pct`, "pct"), false],
      ["A rule of thumb (past miss rate)", null, null, false],
    ],
    proofFoot: `Scored on ${ev(`${R}.summary.test_incidents`, "int")} incidents from the later months. Choices (when to stop training, how sure is "sure") were
      made on the last weeks of the learning period, never on the later months.`,
    forecastProof: card({ title: "Workload forecast per team", body: `<p>Forecast error on new incidents per team and day (lower is better): learned
      ${ev(`${fc}.wape_learned`, "ratio")}, same day last week ${ev(`${fc}.wape_same_day_last_week`, "ratio")}. <b>Not better on this desk</b>; three months of
      history is short.</p>` }),
    fasttrackProof: d.fasttrack ? fastTrackProof(d) : "",
    learned: [`Learned on incidents opened ${evText(`${R}.summary.learning_period[0]`)} to ${evText(`${R}.summary.learning_period[1]`)}; scored once on
        ${ev(`${R}.summary.test_incidents`, "int")} incidents from ${evText(`${R}.summary.test_period[0]`)} to ${evText(`${R}.summary.test_period[1]`)}.`,
      "Scored one hour after each incident opened, from what the event log knew at that moment.",
      "Choices were made on the last weeks of the learning period, never on the later months."],
    cannot: [`Right team first time: OpsLens is very sure on ${ev(`${R}.routing.test.sure_share_pct`, "pct")} of incidents, and there it is right
        ${ev(`${R}.routing.test.opslens_sure_right_pct`, "pct")} of the time, vs ${ev(`${R}.routing.test.desk_on_same_right_pct`, "pct")} for the desk. No real gain.`,
      "What would have happened under other decisions: an event log cannot be replayed." + (d.twin ? ` A digital twin of this desk failed its own check
        (${evText(`${R}.twin.status`)}), so no twin number appears anywhere.` : "")],
    extra: [d.alerts ? alertsCard(d) : "", d.impact ? impactCard(d) : "", d.blind_plants ? plantsCard(d) : ""].filter(Boolean),
  };
}

function fileModel() {
  const r = state.upload;
  if (!r) return null;
  const w = `${U}.warning`;
  const rival = r.warning.vs.rival;
  const f = r.forecast || {};
  const fc = `${U}.forecast`;
  const team = readable("team");
  const [warn, ...fixes] = filePlanItems();
  return {
    key: "up", items: "items", team, proofHref: "#proof/up-proof", shadowHref: "#overview/up-shadow",
    title: `Your file: ${r.file}`,
    sub: `${evText(`${U}.summary.from`)} to ${evText(`${U}.summary.to`)}. ${missWords(r)}`,
    headline: `Flagging ${oneIn(r)} items as they opened, OpsLens caught
      <b class="t-ours">${ev(`${w}.caught_pct.opslens`, "pct", { key: true, title: "Real misses caught", explain: "Of the items in the later part of your file that really missed, the share OpsLens had flagged as they opened (the same 1 in 5 of each day's items for every picker)." })}</b>
      of the real misses on your later items; ${rivalWords(r)} caught ${ev(`${w}.caught_pct.${rival}`, "pct")}.`,
    headlineNote: rival === "priority" ? "" : `The comparison with your priority field needs ${evText(`${U}.needs.priority`) || "a priority column"}.`,
    tiles: [
      ["Items", ev(`${U}.summary.items`, "int"), `over ${ev(`${U}.summary.days`, "int")} days`],
      ["Missed their promise", ev(`${U}.summary.missed_pct`, "pct"), "of all items"],
      ["Median time to finish", ev(`${U}.summary.median_min`, "dur"), `90% within ${ev(`${U}.summary.p90_min`, "dur")}`],
      ["Passed between teams", "—", "needs a reassignment column"],
    ],
    shadow: r.shadow ? `<p>On ${evText(`${U}.shadow.weekday`)} ${evText(`${U}.shadow.date`, prettyDate(r.shadow.date))}, ${ev(`${U}.shadow.items`, "int")} items opened and
        ${ev(`${U}.shadow.misses`, "int")} really missed. With ${ev(`${U}.shadow.flags`, "int")} flags each, OpsLens caught
        <b class="t-ours">${ev(`${U}.shadow.caught.opslens`, "int")}</b>; ${rivalWords(r)}, ${ev(`${U}.shadow.caught.${rival}`, "int")}.</p>` : "",
    fasttrack: "",
    openTime: "",
    cards: r.cards.map((c, i) => {
      const b = `${U}.cards[${i}]`;
      return {
        id: `up-card-${i}`, tag: readable(c.column), title: groupName(c, i), metric: "Missed", stamp: c.still_true,
        bars: [["This group", c.learn_pct, ev(`${b}.learn_pct`, "pct")], ["The rest", c.learn_rest_pct, ev(`${b}.learn_rest_pct`, "pct")]],
        later: `Later items: ${ev(`${b}.test_pct`, "pct")} vs ${ev(`${b}.test_rest_pct`, "pct")} for the rest.`,
        size: `${ev(`${b}.learn_items`, "int")} items on your first part`,
        todo: `Look at why ${escapeHtml(readable(c.column))} ${escapeHtml(String(c.value).trim())} misses more often (an item in Actions).`,
        examples: c.examples.map((x, j) => evText(`${b}.examples[${j}]`)).join(", "),
      };
    }),
    worst: ["team", "category", "priority"].map((key) => worstTable(r, key)),
    riskProof: `Flagging ${oneIn(r)} as they opened caught <b>${ev(`${w}.caught_pct.opslens`, "pct")}</b> of real misses; ${rivalWords(r)}, ${ev(`${w}.caught_pct.${rival}`, "pct")}.`,
    riskSub: "Scored the moment each one opened. From later items, so you can see if each one missed.",
    atRisk: r.warning.at_risk.map((x, i) => ({
      id: evText(`${w}.at_risk[${i}].id`), meta: `opened ${evText(`${w}.at_risk[${i}].opened`)}`,
      reasons: x.reasons.map((reason, j) => `${evText(`${w}.at_risk[${i}].reasons[${j}].text`, plainReason(reason.text))} <span class="small muted">${ev(`${w}.at_risk[${i}].reasons[${j}].share`, "frac_pct")} of the push</span>`),
      risk: ev(`${w}.at_risk[${i}].risk`, "frac_pct"), missed: x.missed,
    })),
    forecast: f.needs ? { needs: `This forecast needs ${evText(`${fc}.needs`)}.` } : { rows: (f.first_week || []).map((x, i) => ({ over: x.forecast - x.usual_ends,
      cells: [evText(`${fc}.first_week[${i}].team`), evText(`${fc}.first_week[${i}].date`), ev(`${fc}.first_week[${i}].forecast`, "num"),
              ev(`${fc}.first_week[${i}].usual_ends`, "num"), ev(`${fc}.first_week[${i}].actual`, "int")] })) },
    plan: [warn, ...fixes],
    planEvidence: [`flagging ${oneIn(r)} as they opened caught ${ev(`${w}.caught_pct.opslens`, "pct")} of the real misses on your later items; ${rivalWords(r)}, ${ev(`${w}.caught_pct.${rival}`, "pct")}`,
      ...r.cards.map((c, i) => `${ev(`${U}.cards[${i}].test_pct`, "pct")} missed on your later items vs ${ev(`${U}.cards[${i}].test_rest_pct`, "pct")} for the rest;
        ${ev(`${U}.cards[${i}].test_misses`, "int")} real misses in this group ${stampHtml(c.still_true)}`)],
    notOnList: "Not on this list: Simulate. A log cannot be replayed under different decisions, so every number above is measured in your file.",
    proofRows: ["opslens", "priority", "rule"].map((k) => {
      const name = k === "opslens" ? "OpsLens" : k === "priority" ? "Your priority field"
        : `A rule of thumb${r.rule_column ? ` (past miss rate by ${readable(r.rule_column)})` : " (past miss rate)"}`;
      if (!(k in r.warning.auc)) return [name, null, null, false, `needs ${evText(`${U}.needs.priority`) || "a priority column"}`];
      return [name, ev(`${w}.auc.${k}`, "ratio"), ev(`${w}.caught_pct.${k}`, "pct"), k === "opslens"];
    }),
    proofFoot: `OpsLens minus ${rivalWords(r)}: ${ev(`${w}.vs.gap_pts`, "pts", { signed: true })} of the real misses caught (95% interval
      ${ev(`${w}.vs.ci[0]`, "pts", { signed: true, bare: true })} to ${ev(`${w}.vs.ci[1]`, "pts", { signed: true, bare: true })} points, resampling whole days).
      ${ev(`${w}.misses`, "int")} real misses among ${ev(`${w}.items`, "int")} later items.`,
    forecastProof: f.needs ? "" : forecastProof(r),
    fasttrackProof: "",
    learned: [`Learned on ${ev(`${U}.learn.items`, "int")} items from ${evText(`${U}.learn.from`)} to ${evText(`${U}.learn.to`)} (the most recent of those
        only to decide when to stop learning); scored once on ${ev(`${U}.test.items`, "int")} items from ${evText(`${U}.test.from`)} to ${evText(`${U}.test.to`)}.`,
      `Learned from what was known when each item opened: ${evText(`${U}.features`, r.features.map(readable).join(", "))}.`,
      r.dropped_after_the_fact.length
        ? `Dropped, because each one alone gives the outcome away: ${evText(`${U}.dropped_after_the_fact`, r.dropped_after_the_fact.map(readable).join(", "))}.`
        : "No column gave the outcome away, so none was dropped."],
    cannot: r.cannot.map((n, i) => evText(`${U}.cannot[${i}]`)),
    extra: r.notes.length ? [card({ title: "How to read this", body: `<ul class="list">${r.notes.map((n, i) => `<li>${evText(`${U}.notes[${i}]`)}</li>`).join("")}</ul>` })] : [],
  };
}

function worstTable(r, key) {
  const rows = r.summary[`by_${key}`];
  const word = readable(key);
  if (!rows) return { key, word: key, empty: true, body: note(`Needs ${evText(`${U}.needs.${key}`) || escapeHtml(`a ${key} column`)}.`) };
  if (!rows.length) return { key, word, empty: true, body: note(`No ${escapeHtml(word)} has enough items to compare.`) };
  const p = `${U}.summary.by_${key}`;
  const body = rows.map((x, i) => `<tr><td>${evText(`${p}[${i}].name`)}</td><td class="num">${ev(`${p}[${i}].items`, "int")}</td>
      <td class="num">${ev(`${p}[${i}].missed_pct`, "pct")}</td></tr>`).join("");
  return { key, word, body: `<div class="table-wrap"><table><thead><tr><th>${escapeHtml(capital(word))}</th>
      <th class="num">Items</th><th class="num">Missed</th></tr></thead><tbody>${body}</tbody></table></div>` };
}

function modelFor(section) {
  const fileView = section.id.startsWith("view-up-");
  return fileView ? fileModel() : uciModel();
}

function missing(section) {
  const fileView = section.id.startsWith("view-up-");
  section.innerHTML = pageHeader(fileView ? "Your file" : "A real service desk", "") + card({ body: fileView
    ? `<p class="muted">No file analysed yet. Press <b>Upload a CSV</b> above.</p>`
    : `<p class="muted">No real-data results yet: run <code>eval/run_realdesk.py</code> (part of make eval).</p>` });
}

function slot(title, sub, html, empty) {
  return html ? card({ title, sub, body: html }) : emptyCard(title, empty);
}

function emptyCard(title, text) {
  return card({ cls: "rd-empty", title, body: note(text) });
}

const BIGGEST = ["The biggest problems", "The biggest problem", "The two biggest problems", "The three biggest problems"];

function problemsList(m) {
  if (!m.cards.length) return `<p class="muted">No group misses clearly more often than the rest.</p>`;
  return `<ol class="issues up-issues">${m.cards.slice(0, 3).map((c) => `<li class="issue" data-goto-tab="problems" data-goto-id="${escapeHtml(c.id)}">
      <span class="issue-title">${c.title}</span>${c.stamp === null ? "" : stampHtml(c.stamp)}
      <span class="issue-text">${c.bars[0][2]} ${escapeHtml(lowerFirst(c.metric))} vs ${c.bars[1][2]} for ${escapeHtml(lowerFirst(c.bars[1][0]))}</span></li>`).join("")}</ol>`;
}

export const overview = { render(section) {
  const m = modelFor(section);
  if (!m) return missing(section);
  section.innerHTML = `${pageHeader(m.title, m.sub)}
    ${card({ cls: "up-headline", body: `<p class="lead-line">${m.headline}</p>${m.headlineNote ? `<p class="needs">${m.headlineNote}</p>` : ""}
      <div class="btn-row"><a class="btn" href="#risks/${m.key}-risks">See the ${m.items} at risk</a><a class="btn" href="${m.proofHref}">How it was tested</a></div>` })}
    <section class="card stat-card"><div class="grid cols-4">${m.tiles.map(([label, value, sub]) => stat(label, value, sub)).join("")}</div></section>
    <div class="grid cols-2 rd-pair">
      ${slot("The busiest later day, replayed", "Each picker flags the same number as they open.",
        m.shadow && `${m.shadow}<div class="btn-row"><a class="btn btn-primary" href="${m.shadowHref}">Watch it in Shadow mode</a></div>`,
        "Not available for this source: it needs a later day with enough items.")}
      ${card({ title: BIGGEST[Math.min(m.cards.length, 3)], sub: m.cards.length ? "Open Problems for the evidence." : "", body: problemsList(m) })}
    </div>
    <div class="grid cols-2 rd-pair">
      ${m.fasttrack || slot("If a fifth of each day's items were fast-tracked", "", "",
        "Not available for this source: it needs each item's pickup time after opening, from an event log.")}
      ${slot("Where an item's open time goes", "From every state change in the event log.", m.openTime,
        "Not available for this source: it needs an event log with every state change.")}
    </div>`;
} };

function barsHtml(c) {
  const top = Math.max(...c.bars.map((b) => b[1]), 1);
  return c.bars.map(([label, value, html], k) => `<div class="mini-bar"><span>${escapeHtml(label)}</span><div class="cbar-track"><div class="cbar-fill ${k === 0 ? "is-bad" : "is-normal"}"
      style="width: ${Math.round((value / top) * 100)}%"></div></div><span class="cbar-value">${html}</span></div>`).join("");
}

export const problems = { render(section) {
  const m = modelFor(section);
  if (!m) return missing(section);
  const cards = m.cards.map((c) => `<article class="card finding-card" id="${escapeHtml(c.id)}" tabindex="0">
      <div class="finding-meta"><span class="cause-tag">${escapeHtml(c.tag)}</span>${c.stamp === null ? "" : stampHtml(c.stamp)}</div>
      <h3>${c.title}</h3>
      <div class="finding-bars"><div class="finding-metric">${escapeHtml(c.metric)}</div>${barsHtml(c)}</div>
      <p class="small">${c.later} <span class="muted">${c.size}</span></p>
      <p class="small"><b>What to do:</b> ${c.todo}</p>
      ${c.examples ? `<p class="small muted">Examples: ${c.examples}</p>` : ""}
    </article>`).join("");
  section.innerHTML = `${pageHeader("Why it goes wrong", `Groups that miss far more often than the rest, checked again on later ${m.items}.`)}
    ${m.cards.length ? `<div class="finding-grid rd-findings">${cards}</div>` : card({ body: `<p class="muted">No group misses clearly more often than the rest.</p>` })}
    ${worstCards(m.worst)}`;
} };

function worstCards(worst) {
  const words = worst.map((t) => t.word);
  if (worst.every((t) => t.empty && t.body === worst[0].body)) {
    return `<div class="up-worst">${card({ cls: "rd-empty", title: `Missed most, by ${words.slice(0, -1).join(", ")} or ${words[words.length - 1]}`, body: worst[0].body })}</div>`;
  }
  return `<div class="grid cols-3 up-worst">${worst.map((t) => card({ cls: t.empty ? "rd-empty" : "", title: `Missed most, by ${t.word}`, body: t.body })).join("")}</div>`;
}

export const risks = { render(section) {
  const m = modelFor(section);
  if (!m) return missing(section);
  const rows = m.atRisk.map((x) => `<div class="risk-row">
      <div><strong>${x.id}</strong> <span class="small muted">${x.meta}</span>
        <ul class="reasons">${x.reasons.map((r) => `<li>${r}</li>`).join("")}</ul></div>
      <div class="num"><div class="risk-p">${x.risk}</div><div class="small ${x.missed ? "bad" : "muted"}">${x.missed ? "it did miss" : "it made it"}</div></div></div>`);
  const list = rows.slice(0, RISKS_SHOWN).join("")
    + (rows.length > RISKS_SHOWN ? fold(`${rows.length - RISKS_SHOWN} more ${m.items}`, rows.slice(RISKS_SHOWN).join("")) : "");
  section.innerHTML = `${pageHeader("What will go wrong", `${capital(m.items)} likely to miss, and how much work each ${escapeHtml(m.team)} gets next week.`)}
    ${proofLine(m.riskProof, m.proofHref)}
    ${card({ title: `${capital(m.items)} most likely to miss`, sub: m.riskSub, body: `<div class="risk-list">${list}</div>` })}
    ${forecastCard(m)}`;
} };

function forecastCard(m) {
  const title = `Workload a week ahead, per ${m.team}`;
  if (m.forecast.needs) return emptyCard(title, m.forecast.needs);
  const hot = m.forecast.rows.filter((x) => x.over > 0).sort((a, b) => b.over - a.over);
  const table = (list) => `<div class="table-wrap"><table><thead><tr><th>${escapeHtml(capital(m.team))}</th><th>Day</th>
      <th class="num">Forecast new</th><th class="num">Usually finishes</th><th class="num">Actually came</th></tr></thead><tbody>${list.map((x) =>
      `<tr><td>${x.cells[0]}</td><td>${x.cells[1]}</td><td class="num"><b>${x.cells[2]}</b></td><td class="num">${x.cells[3]}</td><td class="num">${x.cells[4]}</td></tr>`).join("")}
      </tbody></table></div>`;
  return card({ title, sub: `Forecast new ${m.items} vs what the ${escapeHtml(m.team)} usually finishes in a day. Furthest above first.`,
    body: hot.length ? table(hot.slice(0, HOT_SHOWN)) + (hot.length > HOT_SHOWN ? fold(`${hot.length - HOT_SHOWN} more days`, table(hot.slice(HOT_SHOWN))) : "")
      : `<p class="muted">No ${escapeHtml(m.team)} is forecast above what it usually finishes.</p>` });
}

export const actions = { render(section) {
  const m = modelFor(section);
  if (!m) return missing(section);
  m.plan.forEach(registerItem);
  const [first, ...fixes] = m.plan;
  const box = (item, evidence) => `<div class="action-item"><div>
      <div class="action-title">${escapeHtml(item.title)}</div><div class="small muted">${escapeHtml(item.owner)} · ${evidence}</div></div>
      ${planButtons(item.id)}</div>`;
  section.innerHTML = `${pageHeader("What to do", "Accept adds an action to Your plan; Override says why not.")}
    ${card({ title: "Early warning", body: box(first, m.planEvidence[0]) })}
    ${card({ title: "Fix first", sub: "The groups that miss most, biggest first.",
      body: fixes.length ? fixes.map((f, i) => box(f, m.planEvidence[i + 1])).join("")
        : `<p class="muted">No group misses clearly more often than the rest, so nothing needs fixing first.</p>` })}
    <p class="up-oneline">${escapeHtml(m.notOnList)}</p>`;
} };

export const proof = { render(section) {
  const m = modelFor(section);
  if (!m) return missing(section);
  const rows = m.proofRows.map(([who, auc, caught, ours, why]) => auc === null
    ? `<tr><td>${escapeHtml(who)}</td><td colspan="2"><span class="needs">${why || "not available for this source"}</span></td></tr>`
    : `<tr class="${ours ? "is-chosen" : ""}"><td>${escapeHtml(who)}</td><td class="num">${auc}</td><td class="num">${caught}</td></tr>`).join("");
  section.innerHTML = `${pageHeader("Does it work here?", `Each picker flags the same share of each day's ${m.items} as they open, scored once on later ${m.items} OpsLens never saw.`)}
    ${card({ title: `Early warning, scored once on later ${m.items}`, body: `<div class="table-wrap"><table>
        <thead><tr><th>Who flags</th><th class="num">How well it ranks (AUC)</th><th class="num">Real misses caught (1 in 5 flagged)</th></tr></thead>
        <tbody>${rows}</tbody></table></div><p class="small">${m.proofFoot}</p>` })}
    ${m.forecastProof || emptyCard(`Workload forecast per ${m.team}`, m.forecast.needs || "Not available for this source.")}
    ${m.fasttrackProof || emptyCard("Who should be fast-tracked?", "Not available for this source: it needs each item's pickup time after opening, from an event log.")}
    <div class="grid cols-2 rd-pair">
      ${card({ title: "How it learned", body: `<ul class="list">${m.learned.map((x) => `<li>${x}</li>`).join("")}</ul>` })}
      ${card({ title: "What this source cannot tell you", body: `<ul class="list">${m.cannot.map((x) => `<li>${x}</li>`).join("")}</ul>` })}
    </div>
    ${m.extra.join("")}`;
} };
