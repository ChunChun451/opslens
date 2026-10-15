# web/ — the OpsLens dashboard

## What it does
- One web page with nine tabs: Overview, Patterns, Forecast, At-risk tickets,
  Recommendations, Baseline vs OpsLens (with the replay), What-if, How we tested, Upload data.
- It reads **one file**: the results JSON. The server gives it at `/api/results`
  (`eval/results.json`). Without the server it falls back to `eval/fixture_results.json`.
  The page never stores its own numbers.
- **Every number is clickable.** A popover shows its JSON path, value, spread or 95% CI,
  and a one-line definition.
- A red **FIXTURE** banner shows only when `meta.fixture` is true (real results: no banner).
- **What-if is live**: it asks the server to simulate one test day for all three policies.
- **Story mode** walks the judges through the demo in 6 steps.
- Plain HTML + vanilla JavaScript + CSS. No framework, no build step. Works with Wi-Fi off
  (Chart.js 4.5.0 is saved in `web/vendor/`, no web fonts).

## How to run it
1. From the repo root: `.venv/Scripts/python.exe -m uvicorn server.app:app --port 8000`
   (or `mingw32-make serve`).
2. Open `http://localhost:8000/web/`.
3. Without the server, `.venv/Scripts/python.exe -m http.server 8765` (the `dashboard`
   entry in `.claude/launch.json`) still shows every tab, on the fixture, with the banner.
   What-if then says it needs the server.
4. Opening `index.html` as a file does **not** work: browsers block loading JSON from `file://`.
5. After you edit a file, press **Ctrl+Shift+R**. Neither server tells Chrome not to cache
   the JS files, so a normal reload can show the old version for a while.

## The files
| File | What it does |
|---|---|
| `index.html` | The frame: banner, top bar, side menu, empty content area, popover, story card. |
| `styles.css` | All styles: the design system (colours, card, stat, pill, table, button, chart, popover). Base text 18 px (20 px on Full HD). |
| `app.js` | Start: load the JSON, show the banner, build tabs, popover and story mode. |
| `js/data.js` | `loadResults()`, `state` (the loaded JSON), `getPath()` / `lookup()` to read a value by path. |
| `js/format.js` | Number formats (`13.1%`, `92%`, `−10.7 pts`), KPI names and units, the definitions (from CLAUDE.md section 4). |
| `js/evidence.js` | `ev()` and `evText()` draw clickable values; one click listener opens the popover. |
| `js/charts.js` | Chart.js defaults, policy colours and line styles, `makeChart()` (clickable points), two small plugins (whiskers for ± std or a 95% CI, shaded hours). |
| `js/ui.js` | The building blocks every tab uses: `pageHeader()`, `card()`, `stat()`, `deltaPill()` (a difference coloured by its 95% CI), `policyName()`, `postJson()` (with a time limit). |
| `js/router.js` | The list of tabs (`TABS`), the side menu, `showTab()`. |
| `js/replay.js` | The side-by-side replay player (play, pause, scrub, speed). |
| `js/story.js` | Story mode: 6 steps, Next / Back / arrow keys / Esc. |
| `js/tabs/*.js` | One file per tab. Each exports `render(section)`. |
| `vendor/chart.umd.js` | Chart.js 4.5.0 from jsDelivr. SHA-256 `b7929ad4d5323b8244f85d79bba0b3d1495e66f79a2f0023be7f4de5ba4fbac8` (matches jsDelivr's published hash). |

## How it looks, and why (the design rules)
- **Frame**: dark navy side menu with icons; a slim top bar (live/fixture status, "click any
  number" hint, Story mode); a light grey page with white cards. Every tab starts with the same
  page header (title + one sentence).
- **One hero per tab**: the number that matters is big (e.g. OpsLens's breach rate on the
  Overview); everything else is smaller. Long evidence (example tickets, every tuning step,
  every design we tried) sits behind a "Show …" disclosure, so the first view stays calm.
- **Same pieces everywhere**: tabs never write their own frames. They call `card()`, `stat()`,
  `pageHeader()` and `deltaPill()` from `ui.js`, so a change to the look is one change.
- **Quiet numbers**: numbers are clickable but have no underline; they get a soft blue
  highlight under the mouse. The top bar says once: "Click any number to see its source".
- **Colour means something**: policy colours (blue OpsLens, orange Baseline A, green Baseline B)
  are the same in dots, bars and lines. Green/red pills only repeat what the sign and the 95% CI
  already say (green = CI entirely on the better side, red = entirely on the worse side, grey =
  CI includes zero). Red is otherwise kept for the brand dot, the active menu item and FIXTURE.
- **Projector**: 18 px base text, 20 px on Full HD, high contrast, tabular numbers.

## How the data flows, step by step
1. `app.js` calls `loadResults()`.
2. `loadResults()` asks the server for `/api/results`. If the page is served by Python's
   static server (no API), it skips that call and loads `../eval/fixture_results.json`.
3. The JSON goes into `state.results`. Nothing else keeps a copy.
4. `initTabs()` builds the side menu. A tab is drawn the first time it is shown
   (Chart.js needs a visible canvas to measure its size).
5. A tab never writes a number itself. It calls `ev(path, unit)`. `ev()` reads the value
   at that path from `state.results`, formats it, and returns a button with `data-path`.
6. One click listener on the page (in `evidence.js`) opens the popover for any element
   with `data-path`. Chart points do the same through `makeChart()`.
7. What-if answers are kept in `state.whatif`; their paths start with `whatif.`, so they are
   clickable too and the popover says "POST /api/whatif (live simulation)".

## Worked example: one number, from JSON to screen
The JSON (real results, 16 Oct) has
`"sim": {"policies": {"opslens": {"kpis": {"turnaround.breach_pct": {"mean": 2.379, "std": 0.536}}}}}`.

- `overview.js` calls `ev("sim.policies.opslens.kpis.turnaround.breach_pct.mean", "pct")`.
- `getPath()` splits the path. The key `turnaround.breach_pct` itself has a dot, so at each
  level it tries the longest key that exists first. It finds `2.379`.
- `fmt(2.379, "pct")` gives `2.4%`. The screen shows a big **2.4%** with a dotted underline.
- Click it. The popover shows:
  - `2.4%  raw 2.379…`
  - `Spread across seeds: ± 0.5 pts` (from the sibling `.std`)
  - `OpsLens − Baseline A (FIFO): −10.7 pts (paired 95% CI −12.9 pts to −8.5 pts, n = 5 seeds)`
    and the same against Baseline B (from `sim.comparisons`)
  - the definition of SLA breach, the JSON path, and `Source: /api/results`.

## Where each tab reads its numbers
| Tab | Main paths |
|---|---|
| Overview | `sim.policies.*.kpis` (breach, backlog, P90, `segment.*`), `sim.comparisons`, `brief`, `patterns.cards` |
| Patterns | `patterns.cards`, `patterns.recall`, `patterns.blind_recall`, `patterns.delay_decomposition`, `classification.clusters` |
| Forecast | `forecast.horizon`, `forecast.bottlenecks` (`peak_gap_agents`, `agent_hours_short`), `details.forecast.wape_noise_floor` |
| At-risk tickets | `risk.*`, `risk.at_risk` |
| Recommendations | `recommendations.assignments`, `recommendations.staffing_moves`, grouped by week with `details.forecast.plans` |
| Baseline vs OpsLens | `sim.policies`, `sim.comparisons` (grey = CI includes zero), `sim.replay` |
| What-if | live `POST /api/whatif` → `all_policies`, `agents_on_roster`, `request` |
| How we tested | `details.v1_record` + `details.design_v2` + `stress` (the "What failed" box), `details.ablations` (CIs), `details.blind.by_type`, `details.risk`, `details.forecast`, `details.classification`, `details.tuning`, `sensitivity`, `speed` |

The "What failed, and what we changed" box gives each stress test a verdict from the sign of
its 95% CI of (OpsLens − Baseline B): above zero = "OpsLens worse", below zero = "OpsLens
better", across zero = "no clear difference". The words come from the data, so the box stays
honest when the numbers change.

## How to add a tab
1. Create `web/js/tabs/mytab.js` with `export function render(section) { ... }`.
   Put HTML into `section.innerHTML`: start with `pageHeader(...)`, then `card({...})` blocks.
   Draw charts after that.
2. In `js/router.js`: add `import * as mytab from "./tabs/mytab.js";`, one line in
   `TABS`: `{ id: "mytab", label: "My tab", module: mytab }`, and an icon in `ICONS`.
3. Every number goes through `ev(path, unit)`. Every text from the JSON that may contain
   numbers goes through `evText(path)`. Never type a number into the HTML.
4. If the results section may be missing, show `missing("Name", "M5")` instead.

## Server calls
| Call | Used by | Request we send | Answer we use |
|---|---|---|---|
| `GET /api/results` | everything | — | the results JSON |
| `POST /api/whatif` (live) | What-if | `{"day": 48, "policy": "opslens", "volume_factor": 1.25, "agents_delta": {"A": 0, "B": 0, "C": 2, "D": 0}}` | `request`, `all_policies` (three policies side by side), `agents_on_roster`; takes about 25 s, spinner meanwhile, gives up after 3 minutes |
| `POST /api/plant` (M11) | Patterns → Plant a problem | `{"category": "refund", "language": "hi", "effect": "wait", "day": 47}` | shown as JSON for now; M11 decides the shape |
| `POST /api/upload` (M10) | Upload data | form data: `file` (or `example=uci_incidents`) + `mapping` (JSON) | any 2xx = accepted |
| decision log | Recommendations | `decisionLog` in `recommendations.js` (also printed to the console) | — (no endpoint yet; proposed `POST /api/decisions`) |

On the static preview server the page does not even try these calls (so the console stays clean).

## Weaknesses
- Plant-a-problem and Upload are forms only until their endpoints exist.
- Some meanings are assumed because the schema does not say them: the evidence card's value
  has no unit, and the delay breakdown is read as minutes per ticket.
- Chart.js handles clicks on the next animation frame. If the browser is not drawing
  (window hidden), a chart click waits until it draws again.
- Accept / Override is only kept in the browser until the server stores it.
- Browser caching (see "How to run it"): after editing web files, hard-reload.

## How to read the code
Open `app.js` first (the start-up steps). Then `js/data.js` (`getPath`),
then `js/evidence.js` (`ev` and the popover), then one tab: `js/tabs/overview.js`.
After that, `js/tabs/tested.js` (the "What failed" box), `js/tabs/whatif.js`,
`js/replay.js` and `js/story.js` read top to bottom.
