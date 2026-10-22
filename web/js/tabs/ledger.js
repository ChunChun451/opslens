// tabs/ledger.js — "Rules we wrote first": every pre-registered experiment, the ones we missed too.
//
// Why: rigour is OpsLens's strongest score, but it was invisible: a judge saw only the wins.
// Before each experiment we committed the rule that decides it (git keeps the time), so a result
// cannot be argued into a win afterwards. This view lists every such rule in the order it was
// sealed, with the measured number and a stamp: kept, missed, or only reported (no pass rule).
// The stamp is read from the results file (rule_passed, adopted, ...), never typed here.
// Commit hashes and dates are metadata from git, not results; every number is a clickable path.
//
// Example: "Lowest missed SLAs in at least 27 of 30 random worlds", sealed 19 Oct in 60f359d,
// measured 19 of 30 → stamp "missed", with "beats the industry standard in 29 of 30" beside it.

import { state, lookup } from "../data.js";
import { ev } from "../evidence.js";
import { pageHeader } from "../ui.js";
import { escapeHtml } from "../format.js";

const REPO = "https://github.com/ChunChun451/opslens/commit/";
const BREACH = "turnaround.breach_pct";

// Points with two decimals: these rules are decided right at zero, so "+0.05" must not round
// to "0.0". `ratio` is the formatter's two-decimal unit; the "pts" word is added here.
function pts(path) {
  return `${ev(path, "ratio", { signed: true })} pts`;
}

// "[−5.08, −2.20]" from two paths, each clickable.
function ci(lo, hi, unit = "ratio") {
  return `<span class="ci">[${ev(lo, unit, { signed: true, bare: true })}, ${ev(hi, unit, { signed: true, bare: true })}]</span>`;
}

// Index of the v4 variant the design run chose (its row carries the comparison with v3).
function chosenV4Row() {
  const d = lookup("details.design_v4");
  if (!d) return -1;
  return d.rows.findIndex((row) => row.variant === d.decision.chosen);
}

// Every sealed rule, oldest first. `show` says whether the results file has the section;
// `verdict` reads the rule's outcome from the file; `measured` is the evidence line.
const ENTRIES = [
  {
    when: "18 Oct 19:50", commit: "7f42f68", owner: "Claude 1",
    claim: "Pricing cross-skill work in breach-probability units (policy v4) beats v3",
    rule: "Adopt only if the gain over v3 on validation days has a 95% interval entirely below zero.",
    show: () => chosenV4Row() >= 0,
    verdict: () => (lookup("details.design_v4.decision.adopt_v4") ? "kept" : "missed"),
    measured: () => {
      const p = `details.design_v4.rows[${chosenV4Row()}].normal breach_vs_v3`;
      return `Missed SLAs vs v3: ${pts(p + ".mean_diff")} ${ci(p + ".ci_low", p + ".ci_high")}. Not shipped.`;
    },
  },
  {
    when: "18 Oct 21:50", commit: "7871e05", owner: "Claude 1",
    claim: "Roster-aware rescue (policy v5) beats v3 on 20 seeds it had never used",
    rule: "One candidate fixed in advance; adopt only if its 95% interval vs v3 is entirely below zero.",
    show: () => lookup("details.confirm_v5.v5_minus_v3") !== undefined,
    verdict: () => (lookup(`details.confirm_v5.v5_minus_v3.normal.${BREACH}.ci_high`) < 0 ? "kept" : "missed"),
    measured: () => {
      const p = `details.confirm_v5.v5_minus_v3.normal.${BREACH}`;
      return `Missed SLAs vs v3: ${pts(p + ".mean_diff")} ${ci(p + ".ci_low", p + ".ci_high")}. Shipped.`;
    },
  },
  {
    when: "18 Oct 23:19", commit: "eede459", owner: "Claude 1",
    claim: "A world generated after the freeze, run once",
    rule: "New seed, routine retraining, frozen weights, every baseline; report whatever happens.",
    show: () => lookup(`sealed_world_new.test.opslens_minus_d.${BREACH}`) !== undefined,
    verdict: () => "reported",
    measured: () => {
      const p = `sealed_world_new.test.opslens_minus_d.${BREACH}`;
      return `OpsLens vs the industry standard: ${pts(p + ".mean_diff")} ${ci(p + ".ci_low", p + ".ci_high")}.`;
    },
  },
  {
    when: "19 Oct 15:08", commit: "60f359d", owner: "Claude 1",
    claim: "OpsLens has the lowest missed-SLA rate in at least 27 of 30 random worlds",
    rule: "30 worlds drawn from wide, fixed ranges; nothing tuned per world.",
    show: () => lookup("worlds.rule_passed") !== undefined,
    verdict: () => (lookup("worlds.rule_passed") ? "kept" : "missed"),
    measured: () => `Lowest in ${ev("worlds.wins", "int")} of ${ev("worlds.n_worlds", "int")}; every loss is a floor in
      sustained overload. Beats the industry standard in ${ev("worlds.breakdown.beats_industry_standard", "int")} of
      ${ev("worlds.breakdown.of", "int")}.`,
  },
  {
    when: "19 Oct 15:08", commit: "60f359d", owner: "Claude 1",
    claim: "OpsLens still beats the industry standard when agents hold 2 or 3 chats at once",
    rule: "All four settings, at equal load, each with a 95% interval below zero.",
    show: () => lookup("concurrency.rule_passed") !== undefined,
    verdict: () => (lookup("concurrency.rule_passed") ? "kept" : "missed"),
    measured: () => {
      const i = hardestConcurrency();
      const p = `concurrency.settings[${i}].opslens_vs.baseline_d.${BREACH}`;
      return `Hardest setting (${ev(`concurrency.settings[${i}].k`, "int")} chats, slowdown ${ev(`concurrency.settings[${i}].s`, "num")}):
        ${pts(p + ".mean_diff")} ${ci(p + ".ci_low", p + ".ci_high")}.`;
    },
  },
  {
    when: "19 Oct 15:28", commit: "4706f8f", owner: "real-desk session",
    claim: "On the real desk, OpsLens's fast-track pick saves more missed SLAs than the best other pick",
    rule: "At a 20% fast-track budget, against the best other picker, with an interval excluding zero.",
    show: () => lookup("realdesk.fasttrack.rule.passed") !== undefined,
    verdict: () => (lookup("realdesk.fasttrack.rule.passed") ? "kept" : "missed"),
    measured: () => `Misses saved, OpsLens minus the best other picker: ${ev("realdesk.fasttrack.rule.diff", "int")}
      ${ci("realdesk.fasttrack.rule.ci_low", "realdesk.fasttrack.rule.ci_high", "num")}. A tie.`,
  },
  {
    when: "19 Oct 15:28", commit: "4706f8f", owner: "real-desk session",
    claim: "Problems found on the real desk's early months still hold on its later months",
    rule: "A finding replicates only if its gap keeps the same sign with an interval excluding zero.",
    show: () => lookup("realdesk.replication.replicated") !== undefined,
    verdict: () => (lookup("realdesk.replication.replicated") === lookup("realdesk.replication.of") ? "kept" : "missed"),
    measured: () => `${ev("realdesk.replication.replicated", "int")} of ${ev("realdesk.replication.of", "int")} findings replicate.`,
  },
  {
    when: "22 Oct 21:20", commit: "b2e1b97", owner: "Claude 2",
    claim: "On real bank-customer text, the LLM cascade beats our local model",
    rule: "In each setting, cascade minus local on the official test set with a 95% interval above zero.",
    show: () => lookup("nlp_bench.banking77.settings") !== undefined,
    verdict: () => (lookup("nlp_bench.banking77.settings.full.rule_llm_adds_value")
      && lookup("nlp_bench.banking77.settings.10-shot.rule_llm_adds_value") ? "kept" : "missed"),
    measured: () => {
      const f = "nlp_bench.banking77.settings.full", t = "nlp_bench.banking77.settings.10-shot";
      return `Full data ${pts(f + ".cascade_minus_local.diff_pts")}
        (${ev(f + ".escalated_pct", "pct")} sent to the LLM); 10 examples per intent
        ${pts(t + ".cascade_minus_local.diff_pts")}.`;
    },
  },
  {
    when: "22 Oct 21:20", commit: "b2e1b97", owner: "Claude 2",
    claim: "The LLM understands managers' questions better than keyword rules",
    rule: "60 questions labelled before the run; full-answer accuracy gap with a 95% interval above zero.",
    show: () => lookup("nlp_bench.routing.rule_llm_beats_rules") !== undefined,
    verdict: () => (lookup("nlp_bench.routing.rule_llm_beats_rules") ? "kept" : "missed"),
    measured: () => `${ev("nlp_bench.routing.all.llm_full.pct", "pct")} vs ${ev("nlp_bench.routing.all.rules_full.pct", "pct")};
      Hinglish ${ev("nlp_bench.routing.hinglish.llm_full.correct", "int")} of ${ev("nlp_bench.routing.hinglish.llm_full.n", "int")}
      vs ${ev("nlp_bench.routing.hinglish.rules_full.correct", "int")}.`,
  },
  {
    when: "22 Oct 21:20", commit: "b2e1b97", owner: "Claude 2",
    claim: "The LLM names a problem's cause better than our rules",
    rule: "Same evidence cards, cause hidden; LLM minus rules with a 95% interval above zero.",
    show: () => lookup("nlp_bench.attribution.rule_llm_beats_rules") !== undefined,
    verdict: () => (lookup("nlp_bench.attribution.rule_llm_beats_rules") ? "kept" : "missed"),
    measured: () => `LLM ${ev("nlp_bench.attribution.llm.correct", "int")} of ${ev("nlp_bench.attribution.cards", "int")},
      rules ${ev("nlp_bench.attribution.rules.correct", "int")}. We keep the LLM for the readable sentence only.`,
  },
  {
    when: "22 Oct 21:34", commit: "f51c5a8", owner: "Claude 2",
    claim: "Does a simple model rank risk as well as ours?",
    rule: "Logistic regression and a time-left rule on the same rows, and inside the dispatcher; report all.",
    show: () => lookup("prediction_baselines.risk_in_dispatch") !== undefined,
    verdict: () => "reported",
    measured: () => {
      const p = "prediction_baselines.risk_in_dispatch.variants.logistic_regression.minus_lightgbm";
      return `Ranks almost as well, but dispatching with it misses ${pts(p + ".mean")}
        ${ci(p + ".ci95[0]", p + ".ci95[1]")} more SLAs.`;
    },
  },
  {
    when: "22 Oct 21:37", commit: "da4a9a1", owner: "Claude 2",
    claim: "The reasons we show are the reasons the model uses",
    rule: "Removing the top reason lowers the risk more than a random feature in at least 80% of tickets.",
    show: () => lookup("faithfulness.deletion.rule_faithful") !== undefined,
    verdict: () => (lookup("faithfulness.deletion.rule_faithful") ? "kept" : "missed"),
    measured: () => `True for ${ev("faithfulness.deletion.top1_vs_random1.share_top_drops_more_logodds", "frac_pct")}
      of ${ev("faithfulness.deletion.rows", "int")} at-risk tickets.`,
  },
  {
    when: "22 Oct 21:53", commit: "56ab3f5", owner: "Claude 2",
    claim: "An exact roster optimiser (CP-SAT) beats our greedy staffing moves",
    rule: "Adopt only if better with a 95% interval below zero on validation and again on 20 fresh seeds.",
    show: () => lookup("staffing_opt.confirm.adopted") !== undefined,
    verdict: () => (lookup("staffing_opt.confirm.adopted") ? "kept" : "missed"),
    measured: () => {
      const p = "staffing_opt.test.candidate_minus_greedy.breach_pct";
      return `Wins on its own planning score, not on customers: test days ${pts(p + ".mean_diff")}
        ${ci(p + ".ci95[0]", p + ".ci95[1]")}. Greedy stays.`;
    },
  },
];

// The concurrency setting with the most chats and the largest slowdown, at equal load.
function hardestConcurrency() {
  const settings = lookup("concurrency.settings") || [];
  let best = 0;
  settings.forEach((s, i) => {
    const b = settings[best];
    if (s.load === "equal_load" && (b.load !== "equal_load" || s.k * 10 + s.s > b.k * 10 + b.s)) best = i;
  });
  return best;
}

const STAMP = { kept: "kept", missed: "missed", reported: "reported" };

// The rules present in the results file, each with its verdict.
function sealedRows() {
  return ENTRIES.filter((e) => { try { return e.show(); } catch (error) { return false; } })
    .map((e) => ({ ...e, v: e.verdict() }));
}

// Counts of the stamps (used by story mode).
export function ledgerSummary() {
  const rows = state.results ? sealedRows() : [];
  const count = (v) => rows.filter((r) => r.v === v).length;
  return { total: rows.length, kept: count("kept"), missed: count("missed"), reported: count("reported") };
}

export function render(section) {
  const rows = sealedRows();
  const count = (v) => rows.filter((r) => r.v === v).length;
  section.innerHTML = `
    ${pageHeader("Rules we wrote first",
      "Before each experiment we committed the rule that decides it, and git keeps the time. Here is every one, including the ones we missed.")}
    <div class="ledger-tally" id="ledger-tally" aria-label="Summary of the rules below">
      <p class="ledger-tally-line">${rows.length} rules, sealed before their run.</p>
      <p class="ledger-tally-split">
        <span class="t-kept">${count("kept")} kept.</span>
        <span class="t-missed">${count("missed")} missed.</span>
        <span class="t-reported">${count("reported")} only reported.</span>
      </p>
      <p class="ledger-tally-note">A team that never misses is not testing hard enough. These counts are the stamps below; each stamp is read from the results file.</p>
    </div>
    <ol class="ledger">
      ${rows.map(entryHtml).join("")}
    </ol>`;
  pressStamps(section);
}

function entryHtml(e) {
  return `<li class="ledger-entry is-${e.v}">
      <div class="ledger-when">
        <time>${escapeHtml(e.when)}</time>
        <a href="${REPO}${e.commit}" target="_blank" rel="noopener">sealed in ${escapeHtml(e.commit)}</a>
        <span class="ledger-owner">${escapeHtml(e.owner)}</span>
      </div>
      <div class="ledger-body">
        <h3 class="ledger-claim">${escapeHtml(e.claim)}</h3>
        <p class="ledger-rule">${escapeHtml(e.rule)}</p>
        <p class="ledger-measured">${e.measured()}</p>
      </div>
      <div class="ledger-stamp" aria-label="Verdict: ${STAMP[e.v]}"><span>${STAMP[e.v]}</span></div>
    </li>`;
}

// The one orchestrated moment on this view: the stamps press down in order, once, when the
// view is first drawn. Skipped when the viewer asked for reduced motion.
function pressStamps(section) {
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  section.querySelectorAll(".ledger-stamp").forEach((stamp, i) => {
    stamp.style.animationDelay = `${180 + i * 110}ms`;
    stamp.classList.add("press");
  });
}
