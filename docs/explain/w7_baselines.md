# W7 — Predictions against strong baselines (pre-registered design)

Plan v4, item W7 (a) and (b). Owner: Claude 2. **Committed on 22 Oct 2026 before any W7 number was
computed.** Part (c), the real-desk forecast, belongs to the real-desk session (it owns realdesk.py).

Why: AUC 0.976 next to a 0.884 time-left rule invites "your simulator is easy, and a simple model
would do". A harsh ML judge wants the strongest simple rival on the same rows, a reliability
chart, and proof that the bottleneck alerts on the Risks screen come true.

## (a) Breach risk: LightGBM vs logistic regression vs the time-left rule

**Offline, same rows.** The test snapshots of `eval/run_risk.py` (days 43–56, every 30 min, tickets
waiting for first pickup, 26,811 rows), plus each ticket's first snapshot ("at arrival").
- *LightGBM:* the frozen product model (`data/generated/models`), not retrained.
- *Logistic regression:* the same 22 features; numbers standardised (missing → training median),
  categories one-hot; C = 1.0 fixed (no tuning); trained on days 1–35, isotonic calibration on
  days 36–42 — the same split and calibration as the product model.
- *Time-left rule:* rank by least time left to SLA; isotonic-calibrated on days 36–42 so it also
  has probabilities (Brier, reliability).
- Reported for each: AUC, PR-AUC, top-10% precision, Brier, reliability (10 bins by predicted
  value). 95% CIs and paired differences (LightGBM − rival) by cluster bootstrap over tickets
  (a ticket's snapshots move together), 1,000 resamples.

**Inside the dispatcher (what the model is for).** OpsLens uses the model for *rescue* = P(breach if
it waits) − P(breach if served now). We run OpsLens dispatch on test days 43–56, 5 seeds, same
tickets and luck, with: the LightGBM model (product), the logistic regression in its place, and no
risk model (flat rescue; the existing ablation switch). The time-left rule cannot be dropped in:
serving a ticket now does not change its time left, so its rescue is 0 for every ticket — that
is the no-risk variant, and the reason a model of "what serving now changes" is needed.
Paired 95% CI per variant vs the product. This is evaluation only: nothing is adopted from it.

**Rule:** report everything. If logistic regression is within the CI of LightGBM in the
dispatcher, we say so plainly: "a simple model does as well; the value is the rescue estimate,
not the boosting".

## (b) Bottleneck alerts scored (food world, test days 43–56)

- **Alert** = a team-hour (07:00–23:59; nights are covered by the cross-trained night pool, as in
  `opslens/staffing.py`) where agents needed (Erlang C) at the forecast's P80 team band exceed the
  scheduled agents by ≥ 1.5 — the rule behind `forecast.json`'s bottleneck blocks. Blocks (≥ 2
  consecutive alert hours) are scored too.
- **Made in advance:** on day 42 for days 43–49 and on day 49 for days 50–56 (as the staffing
  plans), so the lead time of an alert = hours from that planning moment to the alert hour.
- **Predictors:** the OpsLens forecast (LightGBM + split-conformal band) vs the naive forecast
  (same hour last week) with its own conformal band, fitted the same way on days 36–42.
- **Truth 1 (workload):** the ACTUAL arrivals' Erlang-C need exceeds scheduled agents by ≥ 1.5.
- **Truth 2 (outcome):** in the recorded history (published roster), tickets arriving in that
  team-hour breached at ≥ 2× the team's average test-day breach rate, with ≥ 5 tickets.
- **Reported:** precision, recall, F1 for both predictors × both truths, hour level and block
  level (a block is a hit if any of its hours is a true hour); median lead time of correct alerts.
- **Rule:** report all; the Risks screen shows the alert hit rate (precision) and recall.
- The real desk's overloaded team-days need the real-desk forecast (W7 c) and go to that session.

## Output
`eval/run_w7.py` → `eval/parts/w7.json`; proposed `results.prediction_baselines`.

## Amendments
1. 22 Oct, after the first run: a second alert rule, from Claude 1's brief (issue #8, which I had not
   read when writing this design) and the dashboard's 48-hour view: **P80 work (agent-hours) >
   scheduled agents × 0.85**, scored against the same rule on actual arrivals and against breaches.
   It is reported next to the pre-registered rule, not instead of it; the pre-registered numbers
   did not change.
