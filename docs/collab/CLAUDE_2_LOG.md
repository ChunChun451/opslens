# Claude 2 log (Sneha's Claude)

Newest at the bottom. What I checked, decided, changed, and what is next.

## Session 1 — 17 Oct 2026

**Setup notes (Sneha's laptop)**
- Repo cloned with `git -c core.longpaths=true clone` (the default path hit "Filename too long").
- LightGBM's DLL will not load from a very long folder path (WinError 206), so the venv lives at
  `~/.venvs/opslens` (Python 3.12.10), not `.venv`. Commands below use that interpreter.
- No API keys yet → classification run with `--no-llm` (local model only). Claude 1's own numbers
  say the LLM moves accuracy 97.97% → 98.08%, so the simulator comparisons are barely affected.

**Reproduced**
- `make gen`: 71,530 tickets; Baseline A 13.1% breach, utilisation 0.80, Team C ρ 1.40 — exact match.
- Fresh clone: `tests/test_demo.py::test_demo_accepts_the_real_results` fails until `make gen` has
  run (it needs data/generated). The "111 green" claim holds only after gen.

**Changed (branch `claude2/review`)**
- `opslens/policies.py`: Baseline C = "SLA due" sort (deadline first, already-late tickets after).
- `opslens/impact.py` + `simulate.py`: lateness KPIs (minutes past SLA of late tickets).
- `eval/run_baseline_c.py`: A / B / C / OpsLens on validation, then test (writes eval/parts/baseline_c.json).
- `tests/test_baseline_c.py`: 3 hand-computed tests.
- `opslens/optimize.py`: module docstring described policy v1 aging; now describes v3.

**Next**: see REVIEW.md ranked list.
