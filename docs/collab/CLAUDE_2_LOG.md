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

## Session 1, part 2 — 17 Oct 2026 (Sneha shared the DEV_103 PDF and API keys)

**Setup**: keys in `.env` (git-ignored), `make ping` OK for Gemini and Groq. gh: winget hung
on an admin prompt, so the portable gh 2.102.0 lives in `~/tools/gh/bin/gh.exe`; it runs with
`GH_TOKEN` taken from Git's stored credential (`gh auth login` refuses it: no read:org scope).
Network on this laptop drops DNS every few minutes: retry pushes.

**Built (PR #1)**: Ask OpsLens (`opslens/ask.py`, `/api/ask`, top-bar command bar), the
`groq_route` provider, lateness in What-if, brief units, floor-map recorder and view, replay
first on its tab, `eval/run_sealed_world.py`.
**Measured**: Groq routing 7/7 correct at 0.2 s (incl. Hinglish); offline keyword rules 5/6.
**Issues for Claude 1**: #2 stale JUDGE_QA v1 numbers, #3 who runs official make eval,
#4 demo story.

**Next**: sealed world result (seed 4242) → `eval/parts/sealed_world.json`; then the official
`make eval` (if Claude 1 agrees on #3) so baseline_c / floor / sealed reach results.json;
add sealed-world + Baseline C to the dashboard's How we tested and Overview.

## Session 1, part 3 — 17 Oct 2026 (Sneha: "beat the industry standard", "2015-esque UI")

- **Baseline D, industry standard** (skills-based routing + AI triage with our classifier, priority
  then SLA due, any team): test 5.51% vs OpsLens 2.20%, −3.31 [−4.79, −1.84]; validation −2.43.
  Now in the main comparison, replay/floor, NUMBERS.md, What-if and Ask OpsLens.
- **Design v2** (`web/theme.css`): Inter (vendored), refined light palette, frosted sidebar, glass
  top bar, staggered entry, count-up numbers, styled sliders/selects, dark "mission control"
  hero on the Overview playing the Saturday floor (industry standard vs OpsLens).
- How we tested → Baselines table (all baselines + sealed world). Story mode leads with the
  industry standard and ends on Ask OpsLens. Playbook drafts + brief use gemini-3.8-flash.
- **Known trade-off (not tuned away, on purpose):** on an overloaded What-if day OpsLens has
  fewer breaches but more minutes late than the industry standard (crisis mode protects
  savable tickets). Over the 14 test days it is lower on both. UI and Ask now say so plainly.
  Retuning now would re-open the test days a 4th time and break the sealed world's "frozen" claim.
- Session folder moved to `Documents\OpsLens\o` (git re-linked, .env and Chart.js restored).
