# OpsLens on your file (`opslens/anyfile.py`)

## What it does
A judge, or any company, uploads a CSV with one row per work item: a support ticket, an incident, a delivery order.
OpsLens guesses which column is the start, the end (or a duration), what counts as a miss and how items are grouped,
and says each guess as one plain sentence before anything is learned. The person can change any guess.
OpsLens learns on the first 70% of items (by start time) and scores the last 30% once. Since 26 Oct the result is not one
report: every Real data screen (Overview, Shadow mode, Problems, Risks, Actions, Proof) is drawn on the file, exactly like
the UCI example. On the real UCI log (24,918 incidents) it takes about 1.5 s; a 100,000-row file about 2.9 s
(`results.anyfile`).

## Why it does not "replay your floor"
A log records one way of working. To know what would have happened under OpsLens's dispatch, you need how long each item
was actually worked on, who was on shift and who can handle what. An export has none of these, so any replay would be a
guess (our real-desk twin failed its own gate for exactly this reason). The screens say this, and Actions has no Simulate.
What a log CAN answer honestly: which items OpsLens would have warned about in time, where the recurring problems are, and
how much work each team gets next week, scored on items and days it never saw.

## How it works, step by step
1. **Read and guess.** `peek()` reads the file, finds each column's kind (time, number, category, id, text) and suggests a
   role for each: known names first (`opened_at`, `Time_taken(min)`), then a column of the right kind with a telling
   word (`Date Created` is a start, `Closed On` an end, `SLA Breached` says it missed). Dates and times can be one column
   or two (`Order_Date` + `Time_Orderd`); the end can be a time or a duration ("(min) 24" works). It also returns a 3-row
   preview and a question for each needed column it could not guess, with the likely columns as answers.
2. **What is a miss.** From the file's own on-time column (`made_sla`), a "breached" column (`SLA Breached`: yes = missed),
   a due time, or a promised time in minutes. Without any of these, OpsLens assumes a promise: the file's median time
   rounded up to the next round number (`round_promise`: 20 min -> 25, 26 -> 30, 22 h -> 1 day). The screen says it is an
   assumption, and the person can type their own.
3. **Check before learning.** `check_mapping()` builds the items with the current guesses and says what will happen: how
   many items are usable, the dates, what share are misses, how many it learns on and tests on, and how many of the file's
   columns it learns from. The upload card calls it again (`POST /api/anyfile/check`) after every change.
4. **Is the file relevant?** At least 500 usable rows, 7 days, 30 misses and 30 in time; most items must end after they
   start. Otherwise one sentence says what is missing and one fix to try (`relevance_problems()`, `refusal()`).
5. **Features known at the moment an item opens.** Hour, weekday, how many items were open when it arrived (overall and in
   its team), how many arrived in the hour before, its priority, team, category and the columns it learns from.
   `open_counts()` only looks back: an item counts as open at t if it started before t and has not ended yet.
6. **Three guards against leakage.** Column names that describe the outcome (resolved, closed, sla, duration, taken,
   transfer, reopen, rating...) are never suggested; the person can untick any column under Adjust; and `leak_screen()`
   drops any column that alone sorts the learning items almost perfectly (AUC above 0.97): it was written after the fact.
7. **Learn.** LightGBM with fixed settings, trained on the first 56% (by start time), stopped early on the next 14%.
   Nothing is chosen on the last 30%.
8. **Score the last 30%.** Three pickers flag the same share, 1 item in 5 each day, as items open: OpsLens, the file's
   priority field (if there is one) and a rule of thumb (the past miss rate of the one column that ranks best on the
   learning items). We count the real misses each one caught, with a 95% interval over days.
9. **Shadow mode** on the busiest later day. `shadow_day()` keeps the counts, and `day_timeline()` lists the day item by
   item (minute opened, minute ended, missed or not, who flagged it as it opened, OpsLens's risk and its TreeSHAP reasons)
   so the screen replays it like the UCI day. The replay's running tally ends exactly on the day's counts.
10. **Problem cards**: groups that missed at least 1.3× as often as the rest (and 3 points more) on the first 70%, then the
    same gap on the last 30% with a 95% interval over days; "still true later" only if it stays above zero. Each card also
    counts the real misses in the group later (`test_misses`), which Actions shows.
11. **Workload a week ahead** (`team_forecast()`), when the file has a team column and 8 weeks: new items per team and day,
    learned (LightGBM, Poisson) on the days before the later 30% began, scored on the first 4 weeks after, against "same
    weekday last week". Each day's forecast reads only counts from a week or more before it (`lag_features()`); the last
    days before the later part pick which forecast to trust. The busy days are the ones forecast above what the team
    usually finishes in a day (median of the 4 weeks before).
12. **What the file lacks** (`missing_columns()`): a short "needs a priority column" (or team, category, 8 weeks...) for every
    part of the report the file cannot support, so no screen is blank.

## The screens (web/)
- `web/js/source.js`: the bar at the top of every Real data screen: `[UCI ServiceNow example] [Your file: orders.csv ×]
  [Upload a CSV]`. The UCI example draws from `results.realdesk`, exactly as before. The job id stays in sessionStorage,
  so a reload fetches the finished report again from the server.
- `web/js/tabs/upload.js`: the upload card in three moments: drop, confirm (the sentences, the preview, Adjust), watch.
- `web/js/tabs/yourfile.js`: Overview, Problems, Risks, Actions and Proof on the file; `web/js/tabs/shadow.js` replays
  the file's day. Every number is read from the job result (`upload.*` paths) through `ev()`, so it is clickable.
- The old "Your data" screen is gone from the side menu; `#upload` opens Real data with the card open.

## Worked example (the UCI log as a plain CSV, `results.anyfile`)
- 24,918 incidents, Feb 2016 to Feb 2017; a miss is the file's own `made_sla` column; nothing to ask.
- Ranking score on the later 30%: OpsLens 0.796, rule of thumb 0.688, the priority field 0.575.
- Flagging 1 in 5 as they opened, OpsLens caught 48.9% of the real misses; the priority field 25.5%.
- Shadow mode, Thu 5 May 2016: 403 incidents, 111 real misses, 81 flags each: OpsLens caught 50, the priority field 22.
  (The real-desk screen, which also uses what happened in the first hour, finds 53 vs 16; at the moment of opening
  OpsLens knows less, so it catches a little less.)
- Workload a week ahead (computed by the current engine on 26 Oct; not yet in `results.anyfile`): the 8 busiest teams,
  scored 2 to 29 May 2016: learned 0.378 against 0.356 for same weekday last week, so not better, as on the real-desk
  screen (0.365 vs 0.341). On a 90-day file of generated delivery orders (tests), it is better: 0.122 vs 0.176.

## Weaknesses
- It warns; it does not say what would have happened to a flagged item (the outcomes are the file's own).
- A promised time is an assumption when the file has none; the screen says so and prints it.
- Columns written after the fact but with innocent names, and not strong enough for the screen, could still leak a
  little; the person mapping the file is the last guard (Proof lists every column learned from).
- Guessing by names can be wrong for unusual exports; the sentences show every guess, and Adjust changes it.
- The forecast is daily and short (4 scored weeks); a thin or very seasonal file can make it worse than last week's count,
  and the screen then says so.
- Very small or very short files are refused rather than analysed badly.

## How to read the code
Open `analyse()` at the bottom of `opslens/anyfile.py`: it calls every step in order. Then `peek()`, `suggest_mapping()` and
`check_mapping()` (the guesses and the sentences), `build_items()` (the mapping), `feature_frame()` and `open_counts()` (what
was known at opening), `leak_screen()`, `early_warning()`, `shadow_day()` with `day_timeline()`, `problem_cards()` and
`team_forecast()`. The server side is `server/anyfile_jobs.py` (a background job the screen polls; `check` for the card).
Tests: `tests/test_anyfile.py` (a delivery-order file, a helpdesk export, junk, leakage, the replay and the forecast) and
`tests/test_anyfile_server.py` (peek, check, run, poll, a junk file).
