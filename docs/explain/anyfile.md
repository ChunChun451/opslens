# OpsLens on your file (`opslens/anyfile.py`)

## What it does
A judge, or any company, uploads a CSV with one row per work item: a support ticket, an incident, a delivery order.
They say which column is the start, the end (or a duration), and what counts as a miss.
OpsLens learns on the first 70% of items (by start time) and scores the last 30% once.
The report shows which real misses OpsLens would have flagged the moment they opened, against the file's own priority field
and a rule of thumb; shadow mode on the busiest later day; and recurring problems found early and checked again later.
On the real UCI log (24,918 incidents) it takes about 1.5 s; a 100,000-row file about 2.9 s.

## Why it does not "replay your floor"
A log records one way of working. To know what would have happened under OpsLens's dispatch, you need how long each item
was actually worked on, who was on shift and who can handle what. An export has none of these, so any replay would be a
guess (our real-desk twin failed its own gate for exactly this reason). The report says this on screen.
What a log CAN answer honestly: which items OpsLens would have warned about in time, scored on items it never saw.

## How it works, step by step
1. **Read and map.** `peek()` reads the file, guesses each column's kind (time, number, category, id, text) and suggests a
   mapping from the names. Dates and times can be one column or two (`Order_Date` + `Time_Orderd`); the end can be a time or
   a duration ("(min) 24" works).
2. **What is a miss.** From the file's own SLA-met column, a due time, or a promised time in minutes typed in the form.
3. **Is the file relevant?** At least 500 usable rows, 7 days, 30 misses and 30 in time; most items must end after they
   start. Otherwise the screen says exactly what is missing. A file that is not about work items cannot pass.
4. **Features known at the moment an item opens.** Hour, weekday, how many items were open when it arrived (overall and in
   its team), how many arrived in the hour before, its priority, team, category and the columns the person ticked.
   `open_counts()` only looks back: an item counts as open at t if it started before t and has not ended yet.
5. **Three guards against leakage.** Column names that describe the outcome (resolved, closed, sla, duration, taken,
   transfer, reopen, rating...) are never suggested; the person can untick any column; and `leak_screen()` drops any column
   that alone sorts the learning items almost perfectly (AUC above 0.97): it was written after the fact.
6. **Learn.** LightGBM with fixed settings, trained on the first 56% (by start time), stopped early on the next 14%.
   Nothing is chosen on the last 30%.
7. **Score the last 30%.** Three pickers flag the same share, 1 item in 5 each day, as items open: OpsLens, the file's
   priority field (if there is one) and a rule of thumb (the past miss rate of the one column that ranks best on the
   learning items). We count the real misses each one caught, with a 95% interval over days.
8. **Shadow mode** on the busiest later day, with the model's own reasons (TreeSHAP) for its first flags.
9. **Problem cards**: groups that missed at least 1.3× as often as the rest (and 3 points more) on the first 70%, then the
   same gap on the last 30% with a 95% interval over days; "still true later" only if it stays above zero.

## Worked example (the UCI log as a plain CSV, `results.anyfile`)
- 24,918 incidents, Feb 2016 to Feb 2017; a miss is the file's own `made_sla` column.
- Ranking score on the later 30%: OpsLens 0.796, rule of thumb 0.688, the priority field 0.575.
- Flagging 1 in 5 as they opened, OpsLens caught 48.9% of the real misses; the priority field 25.5%.
- Shadow mode, Thu 5 May 2016: 403 incidents, 111 real misses, 81 flags each: OpsLens caught 50, the priority field 22.
  (The real-desk screen, which also uses what happened in the first hour, finds 53 vs 16; at the moment of opening
  OpsLens knows less, so it catches a little less.)

## Weaknesses
- It warns; it does not say what would have happened to a flagged item (the outcomes are the file's own).
- A promised time typed in the form is an assumption; the screen prints it.
- Columns written after the fact but with innocent names, and not strong enough for the screen, could still leak a
  little; the person mapping the file is the last guard (the screen lists every column learned from).
- Very small or very short files are refused rather than analysed badly.

## How to read the code
Open `analyse()` at the bottom of `opslens/anyfile.py`: it calls every step in order. Then `build_items()` (the mapping),
`feature_frame()` and `open_counts()` (what was known at opening), `leak_screen()`, `early_warning()`, `shadow_day()` and
`problem_cards()`. The server side is `server/anyfile_jobs.py` (a background job the screen polls); the screen is
`web/js/tabs/upload.js`. Tests: `tests/test_anyfile.py` (a delivery-order file, junk, leakage) and
`tests/test_anyfile_server.py` (peek, run, poll).
