# W8 — Are the explanations faithful? (pre-registered design)

## For the dashboard: exact shape (read this first)
`results.faithfulness` (= `eval/parts/w8.json`):
```
shown_threshold: 0.5, shown_rows,
deletion: {rows, tickets, background_rows, rule_faithful: bool,
    top1_vs_random1 | top3_vs_random3: {share_top_drops_more_logodds, share_top_drops_more_probability,
        mean_drop_top_logodds, mean_drop_random_logodds, mean_drop_top_probability, mean_drop_random_probability,
        top_minus_random_logodds: {mean, ci95}, share_ci95}},
reasons_vs_plant: {planted_hindi_refund_payment | control_team_b_not_hindi:
    {rows, tickets, share_skill_reason_in_top3, ci95}, skill_features, planted_top1_reason_counts},
runner_up: "<where it lives>"
```
Assignment reasons (replay decisions, `decisions[*].reason`) now end with "runner-up B03, value 0.31
lower", "C04 valued it 0.12 higher but took T061200" or "no other free agent could take it now".

## Results (22 Oct) — pre-registered rule PASSED
- Removing a ticket's top reason lowers its risk more than removing a random feature in **98.9%**
  [98.5, 99.2] of 3,000 shown tickets; mean drop 3.18 vs 0.17 log-odds (0.37 vs 0.02 in
  probability). Top 3 vs random 3: 100.0%.
- Planted Hindi refund/payment tickets: language/skill in the top 3 reasons for **98.6%** [98.0, 99.2];
  control (non-Hindi Team B): 63.0% [56.6, 68.5]. The control is not low: "capable agents on shift"
  is a real driver at night for everyone, so the reasons name the mechanism (thin coverage), and for
  Hindi tickets almost always.

Plan v4, item W8. Owner: Claude 2. **Committed on 22 Oct 2026 before any W8 number was computed.**

Why: every risk score on the Risks screen comes with "top 3 reasons" (TreeSHAP shares). Showing
reasons is easy; a harsh judge asks whether the model really *uses* them, whether they point at the
real cause, and why the optimiser picked this agent and not another.

## Rows
Test snapshots (days 43–56, `eval/run_risk.py`), frozen product model. "Shown" tickets = rows with
calibrated P(breach) ≥ 0.5 (the ones a lead would look at); a random sample of 3,000 of them
(seed 8) if there are more.

## (a) Deletion test
- **Removing a feature** = replacing its value with values from 30 random training-day rows
  (seed 8) and averaging the model's output (the "interventional" removal TreeSHAP itself
  assumes). Measured on the model's raw score (log-odds), where SHAP is exact; the calibrated
  probability is also reported.
- For each ticket: drop when its **top reason** is removed vs drop when **one random other
  feature** is removed (uniform over the other 21 features, seed 8). Also top 3 vs 3 random.
- **Reported:** share of tickets where removing the top reason lowers the score more than the
  random feature (ties count as "not more"); mean drop of each, with 95% bootstrap CIs.
- **Rule:** we call the reasons "faithful" only if that share is ≥ 80% AND the mean drop's paired
  95% CI (top − random) is above 0. Otherwise we report the share and say where they fail.

## (b) Do the reasons point at the planted cause?
- Planted problem P1: Hindi refund / payment-failure tickets wait because only 3 agents have the
  skill. Among shown tickets in that segment (language = hi, predicted category refund or
  payment_failure), the share whose top 3 reasons include a language/skill feature:
  `capable_on_shift`, `language` or `queue_team_language` (fixed here, before the run).
- **Control:** the same share for shown Team B tickets that are NOT Hindi (should be much lower;
  if it is not, the model blames language everywhere and the 'hit' means little).
- **Reported:** both shares with 95% CIs (bootstrap over tickets). No pass/fail threshold; the
  gap between segment and control is the evidence.

## (c) "Why this agent and not another"
- `opslens/optimize.py` `with_runner_up` (reason text only; one call in `policies.py`): each assignment's reason line also names the runner-up
  free agent who could have taken the same ticket and its value gap ("runner-up B03, value 0.31
  lower"), or says no other free agent could (language/skill).
- **Regression test:** the same simulation with and without the runner-up text makes exactly the
  same assignments (ticket, agent, minute) — explanation only, no decision change.

## Output
`eval/run_w8.py` → `eval/parts/w8.json`; proposed `results.faithfulness`.

## Amendments
1. 22 Oct: the runner-up helper lives in `opslens/optimize.py` (as Claude 1's brief asks) and is
   called from `policies.py`, where the candidate pairs are built. Same code, same test.
