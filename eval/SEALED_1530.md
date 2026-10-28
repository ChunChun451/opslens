# Sealed world for the 15/30/60 floor

Written before the run. OpsLens S2 was frozen at commit 8f5fe6f: code, weights and the four estimates in
`config/optimizer.yaml`.

- Seed **9393**. It has never been used in this repository (checked on every branch before this commit).
- Command, run once: `python eval/run_sealed_world.py --new --seed 9393 --no-llm`.
- A fresh copy of the repo generates the world. It retrains the classifier (local model only, no LLM keys on this
  machine), the risk model and the forecast and staffing plan, as routine retraining would. Then it runs Baseline C,
  the best baselines (least slack + rescue with the threshold chosen on the main world's validation days) and the
  physical floor on the test days.
- Nothing is tuned on this world. Whatever happens is reported in `eval/parts/sealed_world_new.json`. The earlier
  sealed world (seed 6262, earlier floor) stays in `earlier_floor.sealed_world_new`.
