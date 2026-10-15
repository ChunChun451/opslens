# web/ — the OpsLens dashboard

## What it does
- One web page with nine tabs: Overview, Patterns, Forecast, At-risk tickets,
  Recommendations, Baseline vs OpsLens (with the replay), What-if, How we tested, Upload data.
- It reads **one file**: the results JSON (`/api/results` from the server, or
  `eval/fixture_results.json` until the server exists). It never stores its own numbers.
- **Every number is clickable.** A popover shows its JSON path, value, spread or 95% CI,
  and a one-line definition.
- A red **FIXTURE** banner shows whenever `meta.fixture` is true.
- **Story mode** walks the judges through the demo in 6 steps.
- Plain HTML + vanilla JavaScript + CSS. No framework, no build step. Works with Wi-Fi off
  (Chart.js 4.5.0 is saved in `web/vendor/`, no web fonts).

## How to run it
1. From the repo root: `.venv/Scripts/python.exe -m http.server 8765`
   (or the `dashboard` entry in `.claude/launch.json`).
2. Open `http://localhost:8765/web/`.
3. Opening `index.html` as a file does **not** work: browsers block loading JSON from `file://`.
4. After you edit a file, press **Ctrl+Shift+R**. Python's simple server lets Chrome cache
   files, so a normal reload can show the old version.

## The files
| File | What it does |
|---|---|
| `index.html` | The frame: banner, top bar, side menu, empty content area, popover, story card. |
| `styles.css` | All styles. Light theme, base text 19 px (21 px on Full HD), red accent used sparingly. |
| `app.js` | Start: load the JSON, show the banner, build tabs, popover and story mode. |
| `js/data.js` | `loadResults()`, `state` (the loaded JSON), `getPath()` / `lookup()` to read a value by path. |
| `js/format.js` | Number formats (`13.0%`, `92%`, `−8.9 pts`), KPI names and units, the definitions (from CLAUDE.md section 4). |
| `js/evidence.js` | `ev()` and `evText()` draw clickable values; one click listener opens the popover. |
| `js/charts.js` | Chart.js defaults, policy colours and line styles, `makeChart()` (clickable points), two small plugins (error whiskers, shaded hours). |
| `js/ui.js` | Shared pieces: policy name with colour, "not computed yet" box, "backend arrives in Mx" box, `postJson()`. |
| `js/router.js` | The list of tabs (`TABS`), the side menu, `showTab()`. |
| `js/replay.js` | The side-by-side replay player (play, pause, scrub, speed). |
| `js/story.js` | Story mode: 6 steps, Next / Back / arrow keys / Esc. |
| `js/tabs/*.js` | One file per tab. Each exports `render(section)`. |
| `vendor/chart.umd.js` | Chart.js 4.5.0 from jsDelivr. SHA-256 `b7929ad4d5323b8244f85d79bba0b3d1495e66f79a2f0023be7f4de5ba4fbac8` (matches jsDelivr's published hash). |

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

## Worked example: one number, from JSON to screen
The JSON has
`"sim": {"policies": {"opslens": {"kpis": {"turnaround.breach_pct": {"mean": 4.1, "std": 0.328}}}}}`.

- `overview.js` calls `ev("sim.policies.opslens.kpis.turnaround.breach_pct.mean", "pct")`.
- `getPath()` splits the path. The key `turnaround.breach_pct` itself has a dot, so at each
  level it tries the longest key that exists first. It finds `4.1`.
- `fmt(4.1, "pct")` gives `4.1%`. The screen shows a big **4.1%** with a dotted underline.
- Click it. The popover shows:
  - `4.1%  raw 4.1`
  - `Spread across seeds: ± 0.3 pts` (from the sibling `.std`)
  - `OpsLens − Baseline A (FIFO): −8.9 pts (paired 95% CI −9.7 pts to −8.1 pts, n = 5 seeds)`
    (from `sim.comparisons`)
  - the definition of SLA breach, the JSON path, and `Source: eval/fixture_results.json FIXTURE`.

## How to add a tab
1. Create `web/js/tabs/mytab.js` with `export function render(section) { ... }`.
   Put HTML into `section.innerHTML`. Draw charts after that.
2. In `js/router.js`: add `import * as mytab from "./tabs/mytab.js";` and one line in
   `TABS`: `{ id: "mytab", label: "My tab", module: mytab }`.
3. Every number goes through `ev(path, unit)`. Every text from the JSON that may contain
   numbers goes through `evText(path)`. Never type a number into the HTML.
4. If the results section may be missing, show `missing("Name", "M5")` instead.

## What waits for the server (M9–M11)
| Call | Used by | Request we send | Answer we expect |
|---|---|---|---|
| `GET /api/results` | everything | — | the results JSON (same shape as the fixture) |
| `POST /api/whatif` (M10) | What-if | `{"day": 48, "policy": "opslens", "volume_factor": 1.25, "agents_delta": {"A": 0, "B": 0, "C": 2, "D": 0}}` | `{"kpis": {"turnaround.breach_pct": 5.2, ...}}` (a number or `{mean, std}` per KPI) |
| `POST /api/plant` (M11) | Patterns → Plant a problem | `{"category": "refund", "language": "hi", "effect": "wait", "day": 47}` | shown as JSON for now; M11 decides the shape |
| `POST /api/upload` (M10) | Upload data | form data: `file` (or `example=uci_incidents`) + `mapping` (JSON) | any 2xx = accepted |
| decision log (M9) | Recommendations | `decisionLog` in `recommendations.js` (also printed to the console) | — |

Until then each button shows a clear "Backend arrives in M10/M11" box, and on the static
preview server the page does not even try (so the console stays clean).

## Weaknesses
- The fixture's numbers are invented. The banner says so; `make demo` must refuse them.
- What-if, Plant-a-problem and Upload are forms only until M10/M11.
- Some meanings are assumed because the schema does not say them: the stress table is read as
  breach %, the delay breakdown as minutes per ticket, and the evidence card's value has no unit.
- Chart.js handles clicks on the next animation frame. If the browser is not drawing
  (window hidden), a chart click waits until it draws again.
- Accept / Override is only kept in the browser until the server stores it (M9).

## How to read the code
Open `app.js` first (the start-up steps). Then `js/data.js` (`getPath`),
then `js/evidence.js` (`ev` and the popover), then one tab: `js/tabs/overview.js`.
After that, `js/replay.js` and `js/story.js` read top to bottom.
