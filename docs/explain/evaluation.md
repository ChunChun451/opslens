# eval/ — how every number is produced (`mingw32-make eval`)

## What it does
- One command re-runs every experiment and writes `eval/results.json` (the only source of numbers
  for the dashboard, the brief and the pitch) and `docs/NUMBERS.md` (generated, never typed).
- Each step writes a part file in `eval/parts/`; `eval/run_eval.py` checks them against the
  schema (`opslens/results_schema.py`, pydantic) and assembles them.
- The full run takes about 20 minutes on a laptop; LLM answers come from the cache, so no network.

## The steps
| Step | Script | What it measures |
|---|---|---|
| classification | `run_classification.py` | accuracy local / cascade / LLM, wrong-team routing |
| patterns | `run_patterns.py` | planted recall, unplanted findings that replicate, live alert latency |
| risk | `run_risk.py` | AUC, PR-AUC, calibration on test days; AUC on real ServiceNow data |
| forecast | `run_forecast.py` | WAPE vs naive and vs the noise floor, interval coverage, staffing plans |
| opslens | `run_opslens.py` | OpsLens vs both baselines, 14 test days × 5 seeds, paired 95% CI, replay |
| ablations | `run_ablations.py` | each part switched off; gold-weight sensitivity; stress tests |
| blind (optional, 35 min) | `run_blind.py` | 20 random plant sets, 60 problems |

## The rules that make the comparison fair
1. **Same tickets, same luck**: every policy and seed uses the same tickets and the same random
   draws (common random numbers), so differences come from decisions only.
2. **No tuning on test days**: models, thresholds and weights are chosen on days 1–42; days 43–56
   are only reported.
3. **Same people, same hours**: OpsLens's staffing plan only moves start times and days off.
4. **Paired confidence intervals**: the difference per seed, then a t-interval over 5 seeds.

## The honest record: three versions of the policy
| Version | What changed | Test days, normal | Test days, +25% volume |
|---|---|---|---|
| v1 | aging per hour; guard after 240 min waiting | 5.08% | **51.7%** (lost to priority-first 29.1%) |
| v2 | aging in SLA units (chosen on validation days) | 2.38% | **40.5%** (still lost) |
| v3 | a lost ticket drops to a small value; guard pauses while > 150 tickets wait (chosen on validation days at normal, +25% and +40% volume) | **2.20%** | **10.7%** (priority-first 29.1%) |
Each version was designed and chosen on validation days only; the test days were run three times
in total and all three results are kept in `results.json → details` (`v1_record`, `v2_record`).
This is the main lesson for production: a stress test is a release gate, not a decoration.

## Worked example: reading one ablation row
"without risk scores: 4.21% (+2.01 [+1.55, +2.47])". Turning the risk model off (every ticket gets
the same rescue value) raises breaches from 2.20% to 4.21% on the same tickets and luck; over the 5
paired seeds the increase is 2.01 points, and the 95% interval does not include 0. So the risk
model is the main source of the gain. "without optimiser: 2.18% (−0.02 [−0.11, +0.06])" includes
0: with instant decisions the joint solve rarely beats a per-agent greedy choice.

## Weaknesses
- 5 seeds give tight paired intervals for the main result, but some small effects (staffing,
  scarcity) stay within noise.
- The simulator is our model of a floor; the real-data checks (UCI) cover risk and patterns, not
  the routing policy itself — that would need a shadow-mode trial (docs/PRODUCTION.md).

## How to read the code
`eval/run_eval.py` → `run_steps()`, `assemble()`, `numbers_md()`. Every other script prints its
numbers and writes one part file. The schema is `opslens/results_schema.py`.
