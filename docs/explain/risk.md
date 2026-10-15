# features.py and risk.py — which waiting ticket will miss its SLA, and why

## What it does
- Every 30 minutes (in training) or every few minutes (live), takes a **snapshot** of the floor:
  who is waiting, how many are ahead, who is on shift, how busy each team is.
- Builds features for each waiting ticket **only from that snapshot**, so nothing from the
  future can leak in. A test proves it.
- LightGBM predicts P(breach); isotonic calibration makes the probabilities honest.
- TreeSHAP (built into LightGBM) gives the top 3 reasons in plain words.
- "What would reduce this risk": re-score as if a capable agent took the ticket now.

## How it works, step by step
1. Snapshot at time t: tickets created before t and not yet picked up. Already past their SLA?
   Left out — they are certainly breached, and scoring them would only inflate the numbers.
2. Features (15 numbers, 7 categories): age, time left to SLA, priority, predicted category,
   language, tickets ahead in the team queue, capable agents on shift for this language ×
   category, team tickets in work, arrivals in the last hour, hour, weekend…
3. Train on days 1–35 (58,071 snapshot rows), stop early and calibrate on days 36–42, test on
   days 43–56 (26,811 rows). Never tuned on test days.
4. Reasons: each feature's SHAP push in log-odds, shown as its share of all upward pushes.

## Worked example (Saturday 17 Oct, 22:30, test day 48)
Ticket T060582, Hindi customer: "mera paisa wapas karo please" (refund, P2).
P(breach) **0.997**. Reasons: "only 0 agents on shift can serve Hindi refund — 40% of the push",
"113 min left of 240 min SLA — 23%", "Hindi customer — 11%". If a capable agent took it now:
**0.29**. This is planted problem 1 showing up ticket by ticket.

## Results (test days)
| | AUC | PR-AUC | Top-10% precision | Brier |
|---|---|---|---|---|
| OpsLens risk model | **0.976** | 0.955 | 0.996 | 0.055 |
| Rule: least time left | 0.884 | — | — | — |
| Rule: priority | 0.790 | — | — | — |
- At arrival (each ticket's first snapshot, the early warning): AUC **0.966**.
- Calibration: predicted 0.29 → observed 0.32; predicted 0.74 → observed 0.78.
- **Real ServiceNow data (UCI)**, features as of 1 hour after opening, train on the first 70% of
  time, test on the last 30% (7,476 incidents): AUC **0.857** vs **0.552** for the priority rule.

## Weaknesses
- Synthetic data is cleaner than reality, so 0.976 is optimistic; the real-data 0.857 is the
  more honest number for a new company.
- The model learned under Baseline A (FIFO). It predicts "risk if nothing changes" — exactly what
  we want to prevent — but the numbers would shift under a different routing policy.
- Absences are not in the roster export, so "agents on shift" is the plan, not reality.

## How to read the code
`features.py`: `features_for_snapshot()` first, then `snapshots_from_history()`.
`risk.py`: `train()`, `top_reasons()`, `risk_if_assigned_now()`. Experiment: `eval/run_risk.py`.
Leakage test: `tests/test_risk.py::test_features_never_use_the_future`.
