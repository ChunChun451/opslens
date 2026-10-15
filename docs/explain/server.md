# server/ — the dashboard's back end and the live demos

## What it does
- `server/app.py` (FastAPI) serves the dashboard (`/web/`) and the results (`GET /api/results`,
  which is `eval/results.json`; the fixture only if that file does not exist).
- Three live endpoints let judges touch the engine, all computed on the laptop, no internet:
  - `POST /api/whatif` — re-run one test day with more/fewer agents or more/less volume
    (`opslens/whatif.py`), for all three policies, in about 10–20 seconds.
  - `POST /api/plant` — hide a problem in 21 fresh days and see if OpsLens finds it
    (`server/plant_demo.py`), about 20–40 seconds.
  - `POST /api/upload` — run the analysis on any CSV export with a column mapping, or on the
    real UCI ServiceNow log (`server/upload.py`), about 10 seconds.
- `server/demo.py` (`mingw32-make demo`) refuses to start on fixture or missing results.

## How a live answer stays honest
- What-if and Plant compute their numbers for that one request; they are never stored or typed.
  They use the same simulator, policies and pattern finder as the evaluation.
- Plant uses a CLEAN floor (the main planted problems removed) and the SAME matcher as the blind
  test, so "found" means exactly what it means in `docs/NUMBERS.md`.
- The brief (`opslens/brief.py`) is written by the LLM but every number in it is filled in by
  code from `results.json`; a digit or a number word written by the LLM → template instead.

## Worked example
Plant request `{"category": "refund", "effect": "volume", "day": 47}` → a 4× refund spike for 5
hours on day 13 of 21 fresh days → the pattern finder (not told anything) returns
"Refund spike on Sat 12 Sep" → matcher: found and diagnosed (volume spike) — 18 seconds.
Upload of the UCI example → 24,918 incidents, 36.6% breached, worst group "Group 15" (98.3% of its
58 incidents breached), cards such as "Category 40: 49 tickets on Mon 07 Mar 2016 vs 6 usual".

## Weaknesses
- A regional-language skill gap in a small team can be missed live, as in the blind test
  (12/14 skill gaps found); a Hindi gap is found.
- The server is single-process; two judges pressing "simulate" at once wait for each other.

## How to read the code
`server/app.py` (all routes in one file), then `opslens/whatif.py`, `server/plant_demo.py`,
`server/upload.py`, `server/demo.py`.
