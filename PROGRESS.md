# OpsLens — progress log

Newest entry at the bottom. One entry per milestone (see `CLAUDE.md` section 1.2).

---

## Session 0 — 15 Oct 2026 — Planning (plan v2)

**Built**
- `CLAUDE.md` rewritten as plan v2. Original kept in `docs/CLAUDE_v1.md`.
- `docs/PLAN.md`: 23 changes from v1 with reasons, 2026 research links, risks, team tracks,
  demo outline, attack questions, day-1 checklist.

**Key decisions (all in `docs/PLAN.md` section 2)**
- 56 days of data (train 1–35, validation 36–42, test 43–56).
- 5 planted problems + decoys; blind recall on 20 random plant sets; live Plant-a-problem.
- Real data: UCI ServiceNow incident log (has `made_sla`).
- Classification cascade (local model first, LLM only when unsure).
- Decision tick 2 min for all policies; scarcity cost; starvation guard; Erlang-C staffing.
- LLM never writes digits; What-if tab; UI track in a parallel session from 18 Oct.

**Numbers printed:** none yet (planning only).

**Open issues**
- ~~TrueInk overlap~~ — resolved 15 Oct: OpsLens is the only finale project; all days go to it.
- Free LLM limits to be checked in our own accounts (blogs disagree).
- Project still in OneDrive; M1 moves it to `C:\dev\opslens` with its own git repo.

**Next step:** M1 in a new session at `C:\dev\opslens`.

---

## M1 — 15 Oct 2026 — Repo, LLM layer, privacy, data

**Built**
- Project moved to `C:\dev\opslens` (own git repo, branch `main`), outside OneDrive.
- Python 3.12.15 venv (`.venv`). Versions frozen in `requirements.lock.txt`
  (pandas 3.0.6, numpy 2.5.4, scikit-learn 1.9.1, lightgbm 4.7.0, ortools 9.15, openai 3.31).
- `opslens/config.py`: YAML loader + our own `.env` reader (no python-dotenv).
- `opslens/privacy.py`: 10 ordered regex masks (email, UPI, Luhn-checked card, Aadhaar, PAN,
  order ID, phone, house/flat, PIN, long numbers).
- `opslens/llm/`: `LLMClient.ask_json` = mask → cache → per-provider daily budget →
  per-minute window → send → JSON parse (+1 repair) → fallback → cache. Providers:
  Gemini (`gemini-3.1-flash-lite`), Groq (`openai/gpt-oss-20b`), mock.
- `scripts/download_data.py` + `data/SOURCES.md` (licences, SHA-256).
- `scripts/ping_llm.py` (`mingw32-make ping`): lists visible models, sends one real request.
- `Makefile` (works with `mingw32-make`), `pytest.ini` (temp files inside the project).

**Numbers printed**
- Tests: 31 passed (17 privacy, 14 LLM layer).
- Bitext: 26,872 rows, 27 intents. UCI: 141,712 events, 24,918 incidents, 2016–2017,
  `made_sla` False on 9,215 of 141,712 events (incident-level rate computed in M3).

**Open issues**
- ~~Ping not run yet~~ — done 15 Oct after keys were added: gemini-3.1-flash-lite OK (1.4 s);
  Groq `llama-3.1-8b-instant` is retired and `gpt-oss-20b` had used its 200k tokens/day (shared
  org quota), so the fallback is `qwen/qwen3.8-27b` (OK, 0.2 s; `gpt-oss-120b` also works).
- Bitext has no food intents → `data/text_bank.py` templates (M2).
- pytest needs `--basetemp=.pytest_tmp` on this PC (system temp folder is locked).

**Next step:** M2 — text bank, generator (56 days, 5 plants, decoys), simulator, baselines, CRN.

---

## M2 — 15 Oct 2026 — Generator, simulator, baselines, results contract

**Built**
- `config/generator.yaml` (all assumptions), `config/roster.yaml` (40 named agents; start hours
  and days off from a load-flattening search; planted skill gap + weekend gap in comments).
- `data/text_bank.py`: Bitext (food-flavoured) + English/Hinglish templates, typos, multi-issue, PII.
- `data/generate_ops.py`: 56 days, 5 planted problems (+ test-period surge) and 3 decoys;
  history by Baseline A; calibration report. `--tickets-only` for quick tuning.
- `opslens/simulate.py`: event-driven discrete-event simulator (FINISH/REOPEN/ARRIVAL/DECIDE),
  transfers, deliberate cross-skill work, reopens, absences, snapshots for the replay.
- `opslens/world.py`: World builder; CRN draws indexed by ticket number.
- `opslens/policies.py`: Baseline A (FIFO, team queue first), Baseline B (priority, then oldest).
- `opslens/impact.py`: KPIs under Turnaround / Productivity / Quality; paired 95% CI.
- `opslens/results_schema.py` + `eval/make_fixture.py` → `eval/fixture_results.json`
  (`meta.fixture = true`) and `eval/results.schema.json`.
- `eval/run_baselines.py`: A vs B on test days, 5 seeds.

**Numbers printed**
- 71,530 tickets. Baseline A history: breach 13.1% (target 12–18), utilisation 0.80
  (0.70–0.80), Team C weekend-dinner ρ 1.40 (1.2–1.5). Sim of 56 days: 11.0 s.
- Planted signals in history: Hindi refund/payment wait 301.7 vs 46.7 min (English);
  cluster 17 = 5.1% of wrong items vs 2.0% of tickets; transfers per 100: call 12.8, chat 2.6.
- Erlang C check: simulated wait 10.97 vs 10.79 min; P(wait) 0.644 vs 0.647.
- Test days 43–56, 5 seeds, 18,032 tickets: Baseline A 13.11% ± 2.23, Baseline B 6.82% ± 1.34,
  B − A = −6.29 [−7.50, −5.07]; P99 wait A 816 vs B 1,007 min.
- Tests: 50 passed.

**Plan changes (CLAUDE.md updated)**
- Decisions are event-driven for all policies (2-min tick only for shift starts): the Erlang-C
  test showed a fixed cadence leaves agents idle ~1 min per ticket.
- 3 Hindi + refund agents instead of 2 (with 2, waits averaged 15 h and never cleared).
- ~1,130 tickets/weekday and sale days ×1.35 (×1.6 created a 2-day backlog of 446 tickets).
- Team C weekend-dinner ρ target 1.2–1.5 (was 1.05–1.2) so the planted problem is visible.
- YAML gotcha: the key `off` is read as boolean false — renamed to `days_off`.

**Open issues**
- Test-day breach % varies a lot by seed (A: ±2.23) because of the day-47 surge and the sale
  day; paired CIs are still tight thanks to CRN.
- U1 dashboard shell is being built in a parallel session on branch `u1-dashboard-shell`.

**Next step:** M3 — ingest (+ UCI adapter), KPIs, classification cascade, LLM-named clusters.

---

## M3 — 15 Oct 2026 — Ingest, UCI adapter, KPIs, classification cascade, clusters

**Built**
- `opslens/ingest.py` (pydantic row check, timing recomputed from timestamps, splits),
  `opslens/adapters/uci_incidents.py` (events → incidents; as-of-time risk features),
  `opslens/kpis.py`, `opslens/classify.py` (local TF-IDF + LR, isotonic, LLM cascade),
  `opslens/clusters.py` (TF-IDF + KMeans per category, LLM names), `eval/run_classification.py`.
- Text realism: 12% vague first messages, 15% multi-issue (30% with the main issue second),
  and ~600 LLM-written message patterns (`data/llm_templates.json`, Groq Qwen — a different
  model from the classifier's Gemini). With hand templates only, accuracy was 99.9% (memorised).
- `config/calendar.yaml`: calendar facts split from `generator.yaml`, so the engine never reads
  the file that describes the planted problems (guard test added).
- LLM client: waits and retries once on "try again in Ns" (≤ 90 s); Groq paced to 1 request/min
  (its free tier allows 1,000 output tokens per minute) and capped at 900 output tokens; batches
  of 25.

**Numbers printed (test days 43-56, 18,032 tickets)**
- Menu choice 90.9% (calls 75.8%) → local 97.97% → cascade 98.08% (calls 95.7%, Hinglish 97.3%).
- Threshold 0.6 (chosen on validation); 1.54% sent to LLM (≈ 617 requests per 1M tickets);
  LLM fixed 57, broke 37. LLM alone on 400 random tickets: 90.0%.
- Wrong-team routing per 100: 5.71 → 1.20 (calls 14.83 → 2.54).
- UCI: 24,918 incidents; breach 36.6%; breach by reassignments 0/1/2/4+: 21.6/42.9/60.1/81.0%.

**Open issues**: cluster names sometimes repeat; synthetic text is cleaner than real tickets.

---

## M4 — 15 Oct 2026 — Patterns, live alerts, blind recall

**Built**: `opslens/patterns.py` (capacity, interaction, transfer, partner, spike scans; cause
rules; evidence cards; live alerts), `eval/recall.py`, `eval/run_patterns.py`, `data/plant.py`,
`eval/run_blind.py`; generator accepts generic plants (`extra_lifts`, `extra_partners`,
`extra_misrouting`) — main data verified identical.

**Numbers printed**
- Main data: 5/5 planted problems found and diagnosed (cause type correct). 2 unplanted findings:
  regional-language × weekday morning replicates on test days (2.0×); Team B × weekday night
  does not (1.2×) → 1 false alarm.
- Live alerts (rule z ≥ 4.5 twice in a row, chosen on days 15-42): day-47 surge flagged after
  45 min; 1 false alert in 2 weeks; sale-day alerts explained.
- **Blind test: 57/60 random plants found and diagnosed (95%)** over 20 datasets
  (capacity 10/10, partner 14/14, process 10/10, spike 11/12, skill gap 12/14); clean dataset 3 cards;
  2.35 unplanted cards per set.

**Open issues**: small groups with modest effects can be missed (regional-language × Team C).

---

## M5 — 15 Oct 2026 — Leak-proof features, risk model, reasons, UCI check

**Built**: `opslens/features.py` (QueueSnapshot → features; the same code will run inside the
simulator), `opslens/risk.py` (LightGBM + isotonic, TreeSHAP shares, counterfactual, save/load),
`eval/run_risk.py`, `tests/test_risk.py` (leakage test: change the future, features unchanged).

**Numbers printed (test days, still-savable waiting tickets, 26,811 snapshot rows)**
- AUC 0.976 (time-left rule 0.884, priority rule 0.790), PR-AUC 0.955, top-10% precision 0.996,
  Brier 0.055; at arrival AUC 0.966. Calibration 0.29 → 0.32, 0.74 → 0.78.
- UCI real data (7,476 test incidents): AUC 0.857 vs priority rule 0.552.

**Decision**: tickets already past SLA are excluded (with them the AUC was a misleading 0.992).

---

## M6 — 15 Oct 2026 — Forecast, conformal ranges, bottlenecks, staffing

**Built**: `opslens/forecast.py`, `opslens/staffing.py` (Erlang C, numpy coverage, greedy
budget-neutral moves, overload hours 3×, day hours only), `eval/run_forecast.py`, weekly plans
saved to `data/generated/staffing_plan.json`; simulator agents accept week-specific shift
overrides (`world.apply_staffing_plan`).

**Numbers printed (test days)**
- WAPE 0.305 vs naive 0.415 (Poisson floor 0.280); team-hour workload 0.235 vs 0.321.
- Conformal coverage 79.2% (80% range), 90.0% (90% range); sale day −16.6%.
- Plan days 43-49: C05 Monday off instead of Saturday, B02 Monday instead of Friday, C06 Friday
  instead of Tuesday, 3 starts 08:00 → 07:00; shortage 654 → 636 agent-hours.

**Next step:** M7 — OpsLens policy (rescue value, scarcity, starvation guard, min-cost flow),
weights chosen on validation days, OpsLens vs A/B on test days with paired CIs.

---

## M7 — 15 Oct 2026 — Optimiser and the OpsLens policy

**Built**: `opslens/optimize.py` (ticket value, min-cost flow with OR-Tools, greedy fallback),
`OpsLensPolicy` in `opslens/policies.py` (classifier routing, rescue value = P(breach if waiting) −
P(breach if served now), fairness aging, starvation guard, cross-skill rescue jobs, scarcity
preference that never causes idling, decision log with reasons, ablation switches),
`config/optimizer.yaml`, `eval/run_opslens.py` (`--tune` on validation, parallel seeds,
replay series), `tests/test_optimize.py`. Fast risk scoring path (numpy codes, ~10× faster).

**First attempt failed and was fixed (on validation days only)**: untuned, OpsLens breached 25.9%
on a trial run (cross-skill jobs everywhere, scarcity made rare agents idle). Fixes: cross-skill
only for rescue ≥ 0.5 with penalty 2.0; scarcity floored so no agent idles; stronger aging.

**Numbers printed**
- Validation tuning (days 36-42, seeds 1-3): OpsLens 3.75% vs Baseline B 5.94%; chosen
  aging 1.0/h, cross-skill rescue ≥ 0.5, mismatch penalty 2.0, scarcity 0.3, rescue floor 0.2.
- **Test days 43-56, 5 seeds**: breach A 13.11%, B 6.82%, **OpsLens 5.08%**; OpsLens − B −1.74
  [−2.35, −1.13], OpsLens − A −8.02 [−9.01, −7.04]. P90 130 vs 185/198 min; P99 wait 474 vs 816/1,007;
  transfers 0.97 vs 4.66/4.59 per 100; reopens 4.35% vs 3.93% (the cost of cross-skill rescues).
- Replay, Saturday 17 Oct 18:00-24:00: breaches 7 (OpsLens) vs 83 (A) vs 26 (B); peak queue 79 vs 132/141.
- Solver: median 0.08 ms, max 8.8 ms, 0 fallbacks; 5,000 × 500 scale test 0.115 s.

**Next step:** M8 — ablations, sensitivity, stress, `make eval` → results.json + NUMBERS.md.

---

## M8 — 16 Oct 2026 — make eval, ablations, sensitivity, stress; policy v2 → v3

**Built**: `eval/run_eval.py` (all steps, schema validation, NUMBERS.md), `eval/run_ablations.py`,
`eval/run_design_v2.py`, `eval/run_design_v3.py`, stress inputs (+25% volume by copying tickets,
10% absenteeism), segment KPIs (P1, gold, Hindi), single-thread LightGBM scoring for parallel runs,
`docs/explain/evaluation.md`, `docs/PRODUCTION.md`.

**The three policy versions (all test results kept in results.json → details)**
- v1 (aging per hour): test 5.08%; **failed** +25% volume: 51.7% vs B 29.1%.
- v2 (aging in SLA units; chosen on validation 36-42 at normal and +25%): test 2.38%; still lost
  +25% on test days: 40.5% vs 29.1% (there +25% lands on a sale day and an unseen surge).
- v3 (lost ticket → small fixed value; guard after 480 min late; guard pauses while > 150 wait;
  chosen on validation at normal, +25%, +40%: 2.13% / 6.17% / 15.07% vs B 5.94% / 16.55% / 32.23%).

**Final numbers (v3, test days 43-56, 5 seeds)**
- Breach: A 13.11%, B 6.82%, **OpsLens 2.20%**; OpsLens − B −4.62 [−6.01, −3.23]; − A −10.91.
- P90 141 vs 185/198 min; P99 wait 728 vs 816/1,007; P1 breach 4.89% vs 27.34/9.13;
  Hindi customers 3.46% vs 22.11/16.18; gold 1.83% vs 12.40/6.71; transfers 0.97 vs 4.66/4.59;
  reopens 4.40% vs 3.93% (cost of cross-skill rescues).
- Ablations: risk +2.01 [+1.55, +2.47]; classifier +0.14 [+0.01, +0.27]; staffing +0.05,
  scarcity +0.03, optimiser −0.02 (all within noise).
- Gold weight ×1 / ×1.5 / ×2: gold breach 2.08% / 1.83% / 1.85%, overall 2.20 / 2.20 / 2.25%.
- Stress: +25% volume A 53.55%, B 29.06%, OpsLens 10.71%; 10% absenteeism 20.32 / 9.89 / 3.09%.
- Speed: pipeline ~20 min; optimiser median 0.08 ms, max 5.9 ms; 5,000 × 500 in 0.047 s.

---

## M9 — 16 Oct 2026 — Server + dashboard wired to real results

**Built**: `server/app.py` (FastAPI: /api/results, /api/health, /api/whatif, /api/plant,
/api/upload, static /web and /eval). Dashboard wired to the real results by the parallel UI
session (branch m9-wire-real-results, merged as 9ab294c): every tab renders, What-if live,
"What failed" box, ablation CIs. Checked in the browser: no console errors.

## M10 — 16 Oct 2026 — What-if, brief, Upload CSV

**Built**: `opslens/whatif.py` (volume ×k, agents ± per team, all three policies),
`opslens/brief.py` (LLM writes {{keys}}; digits and number words rejected → template; Gemini
brief now in results.json), `server/upload.py` (column mapping, priority ranking, ISO/day-first
dates, SLA flag; UCI example: 24,918 incidents, 36.6% breach, ~10 s), `patterns.find_patterns_basic`
(same scans on any export; spikes compared with nearby days for uneven exports).
Dependency added: `python-multipart` (FastAPI's own form/file extra).

## M11 — 16 Oct 2026 — Plant-a-problem live, make demo

**Built**: `server/plant_demo.py` (fresh 21 days, clean floor, judge's problem, same matcher as
the blind test): refund spike found+diagnosed in 18 s; app-bug mislabels in 16 s; Hindi skill
gaps found; a regional-language gap in a small team can be missed (as in the blind test).
`server/demo.py` (`make demo` refuses fixture or missing results). Tests: 104 passing.

**Open issues**
- UI polish (What-failed timeline v1→v2→v3, story mode on real numbers, loading states) is with
  the parallel UI session (branch m10-polish), not merged yet.
- DEMO_SCRIPT.md and rehearsal (M12).

---

## P1 — Fix-at-source playbooks + challenger arena (16 Oct 2026)

**Why:** an outside AI review (16 Oct) said OpsLens treats symptoms (routing) and not causes.
Owner decision (docs/PLAN.md section 9): build playbooks, measured in the simulator; keep the
other review points as Q&A answers. The UI session's redesign + M10 polish (branch m10-polish)
was reviewed (only web/ and docs/explain/web.md, no hard-coded numbers) and merged.

**Built**
- `opslens/playbooks.py`: one upstream action per evidence card (process → phone-menu fix,
  partner → kitchen order-check, skill gap → cross-train named agents, spike → status banner on
  live alerts, capacity → self-serve instant refund in the overloaded window). `apply_scenario()`
  changes tickets or roster; assumptions in `config/playbooks.yaml`, labelled.
- `eval/run_playbooks.py` (122 runs, 18 min; `--messages` re-drafts only the LLM text);
  scenario hook in `eval/run_opslens.py::run_one`; `playbooks` section in results.json and
  NUMBERS.md; "Fix at the source" card on the Recommendations tab; 7 new tests; all 111 tests pass.
- Challenger arena: `.venv-challengers` (torch CPU, chronos-forecasting, tabpfn),
  `eval/challengers/run_forecast_arena.py`, `run_risk_arena.py`, rules written before running.

**Key numbers (test days 43-56, 5 seeds)**
- All six playbooks: breaches −179 [−219, −139] under priority-first, −57 [−73, −40] under
  OpsLens; OpsLens + playbooks vs priority-first today −889 [−1,127, −652] of 1,230.
- Cross-train A09 + D11 (Hindi, nights): −83 [−131, −35] / −51 [−71, −30]. Phone-menu fix:
  −46 / −3 (OpsLens already fixes routing). Others within noise under OpsLens.
- Chronos-2 zero-shot WAPE 0.304 vs LightGBM 0.305 (+0.4% < 2%), coverage 76.2% vs 79.2%,
  1.7 s per refresh → keep LightGBM.

**Open issues**
- TabPFN-3 arena needs the owner's licence key (TABPFN_TOKEN in .env), then
  `.venv-challengers/Scripts/python.exe eval/challengers/run_risk_arena.py` and
  `.venv/Scripts/python.exe eval/run_eval.py --assemble`.
- DEMO_SCRIPT: decide where the playbooks appear in the 7 minutes. M12 rehearsal.

---

## C2 — Claude 2's review merged (PR #1, 16–18 Oct 2026)

**Who:** Claude 2 (Sneha's Claude Code) worked on branch `claude2/review` in the private repo
ChunChun451/opslens; Claude 1 reviewed (PR comment), the owner approved, merged as `cbca9fa`.

**Built by Claude 2** (full findings: `docs/collab/REVIEW.md`, log: `docs/collab/CLAUDE_2_LOG.md`)
- Baseline C ("SLA due") and Baseline D (industry-standard skills routing with our AI triage);
  no weights, validation first, then test once. D is now the lead comparison.
- Lateness KPIs (minutes past SLA): the measured answer to "do you abandon late tickets?".
- Ask OpsLens (`opslens/ask.py`, `POST /api/ask`): LLM routes, engine answers, grounding check,
  offline keyword rules. Owner approved it on 18 Oct (amends the CLAUDE.md non-goal).
- Floor map in the replay; design v3 with a cold open ("21 vs 7 missed promises").
- Sealed second world (seed 4242, generated after the freeze, run once).
- Official `make eval` on Sneha's laptop: 0 of 3,744 existing numbers moved (Claude 1 checked).

**Key numbers (test days 43-56, 5 seeds)**
- Breach %: OpsLens 2.20 vs D 5.51 (−3.31 [−4.79, −1.84]), C 5.40 (−3.20 [−3.93, −2.46]),
  B 6.82, A 13.11.
- Minutes past SLA per 100 tickets: OpsLens 529, D 1,477, B 2,282, A 2,820, C 4,189.
- Sealed world: OpsLens 3.07% vs C 6.13% (−3.06 [−3.67, −2.45]); retrained risk AUC 0.970.
- Saturday replay 18-24h, missed promises: D 21, OpsLens 7 (A 83, B 26).

**Fixed by Claude 1 after the merge (18 Oct)**
- JUDGE_QA Q26–Q30 quoted policy v1 (5.08%, P99 474, a 240-min guard): rewritten from v3
  results. Also 53.6% → 53.5% (double rounding), 0.321 → 0.323 (stale), and a B-vs-A interval
  that results.json never contained.
- New `tests/test_doc_numbers.py`: numbers in JUDGE_QA and DEMO_SCRIPT must exist in the
  current results (measured limit: about 45% of random one-decimal numbers match by chance).
- CLAUDE.md updated (baselines, ask.py, lateness, sealed world, cold open, non-goal amended).
- DEMO_SCRIPT rewritten around the cold open.

**Open issues** (also posted on PR #1)
- Sealed world lacks Baseline D (re-run with D; OpsLens stays frozen).
- Ask OpsLens sends the question to Groq without `mask_pii()`.
- Confirm `gemini-3.8-flash` in `make ping`.
- TabPFN-3 still waits for the licence key. M12 rehearsal.

---

## P2 — Can OpsLens do better? Diagnosis, v4, a proven floor, a simulator fix (18 Oct 2026)

**Asked:** make OpsLens better than 2.2%; then "prove the floor".

**Diagnosis (validation days 36-42 only).** Of v3's breaches, most happen even with unlimited
agents and perfect routing. The biggest avoidable group: Hindi / regional-language P2s at night,
never given to an untrained agent who speaks the language, because the flat cross-skill penalty
(2.0, tuned for v1's scale) cost a P2 more than it could ever be worth.

**v4 (cross-skill cost in breach-probability units) — tested, NOT adopted.** Pre-registered rule in
`eval/run_design_v4.py`. Under the old simulator it passed (2.07% → 1.92%). Under the corrected
simulator: 2.03% → 1.95%, CI [−0.21, +0.05], so v3 stays. (The first re-run compared v4 with
itself after `mismatch_cost` entered the config — caught because both rows were identical; fixed.)

**Proven floor (`opslens/floor.py`).** Exact per-ticket lower bound with a proof; attacked by
`tests/test_floor.py` (10 policies incl. random legal ones, 25 random worlds, no counterexample,
tight in 3). Test days: 1.31% (1.23-1.38 by seed). The number belongs to the data.

**Found while proving it:** the simulator drew a ticket's work time per attempt, and a transfer
counted as an attempt (unequal luck for policies with many transfers; a re-roll loophole). Fixed:
the k-th piece of real work uses draw k. Off-shift starts now raise. Every number regenerated.

**Key numbers (corrected simulator, test days 43-56, 5 seeds)**
- OpsLens 2.21%, industry standard 5.51% (−3.29 [−4.60, −1.98]), SLA due 5.38%, least slack 3.94%,
  least slack + rescue 2.98%, c-mu 5.27%, priority-first 6.77%, FIFO 13.08%.
- Floor 1.31% → OpsLens captures 78% ± 4 of the possible improvement over industry routing.
- New sealed world (seed 5151, run once): OpsLens 2.50% vs industry 6.56%, least slack + rescue
  3.52%, floor 1.30%, captured 77% ± 2. Cold-open replay: industry 24 vs OpsLens 6.

**Open:** UI copy that says "21 vs 7" is read from results (now 24 vs 6) — check the cold open.
TabPFN-3 still waits for its licence key. M12 rehearsal with the updated DEMO_SCRIPT.

**P2 update — v5 shipped (18 Oct, evening).** v5 (roster-aware cross-skill rescue) failed to separate
from luck in its 5-seed design run, so it was NOT shipped then; a new pre-registered confirmation on
20 fresh seeds (validation days) passed: −0.17 [−0.20, −0.13]. Test days, run once: **2.05%**
(v3 2.21%), −3.46 [−4.77, −2.15] vs industry; floor 1.31% → **83% ± 4 captured**. Hindi 3.53% →
2.72%. New sealed world (seed 6262, after the v5 freeze, run once, local classifier because the
Gemini daily quota ran out): OpsLens 2.20% vs industry 5.84%, least slack + rescue 3.11%, floor 1.31%,
81% ± 4. Cost: under +25% volume (validation) late customers get later; reopens 4.44%. Not below 2.0%
on test, and we did not tune to get there.

---

## V3 — Plan v3: from engine to product (19 Oct 2026)

**Why:** the owner could not explain what each screen was for; Accept/Override did nothing; the
public dataset (deliverable 1) was hidden behind Upload. Re-read the problem statement verbatim:
it asks for "a dashboard showing the expected impact of these interventions". Plan: docs/PLAN_V3.md.

**Built**
- Public dataset chosen with evidence: UCI ServiceNow (real teams, agents, hand-offs, SLA flag).
  Checked first, then built: OpsLens does NOT route to the right team better than the real desk
  (61.8% vs 66.2% overall; when sure 78.2% vs 77.8%) and its forecast does not beat "same day last
  week" (0.365 vs 0.341) — both shown as such. It DOES warn early: AUC 0.857 vs 0.552; riskiest 20%
  hold 49.9% of SLA misses vs 24.6% for the priority field.
- `opslens/realdesk.py`, `eval/run_realdesk.py` → `results.realdesk` (a STEP in make eval).
- Dashboard: world switch, six question-shaped screens (old names still work), Your plan
  (web/js/plan.js): Accept with measured effect, Override with a reason, Simulate (calls
  POST /api/plan/impact, built by the parallel "Make Accept/Override real" session).
- docs/OPSLENS_IN_PLAIN_WORDS.md for the owner; DEMO_SCRIPT rewritten; JUDGE_QA Q51–Q55.

**Open:** merge the plan-impact session's branch (API + per-item effects for staffing moves) and
wire its ids; story mode tour through the new screens; projector check at 1366×768.
