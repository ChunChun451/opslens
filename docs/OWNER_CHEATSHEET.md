# OpsLens — the owner's one page (learn this by heart)

Short words on purpose. Every number is in `eval/results.json` (checked by `tests/test_doc_numbers.py`).
The long answers are in `docs/JUDGE_QA.md`; this page is what you say in the first 20 seconds.

## The pitch in 20 seconds
"A support floor gets about a thousand complaints a day and every one has a deadline. OpsLens tells
the team lead why deadlines are missed, which customers will miss theirs next, and what to do — and
every recommendation comes with its own proof, replayed on days it never saw. Same agents, same
customers: 2.0% missed instead of 5.5%."

## How it works, in four parts
1. **Reads** each complaint and finds what it is about (Hinglish too).
2. **Finds patterns and predicts**: next 48 hours per team; each waiting ticket's chance to miss, with reasons.
3. **Decides**: who takes which ticket now — the one that serving now *saves* the most, weighted by
   urgency and business impact; plus fixes at the source and staffing changes.
4. **Proves**: replays held-out days under every way of working, same customers, same luck, 95% intervals.

## The numbers to know
| Say | Means |
|---|---|
| **2.0% vs 5.5%** | Missed deadlines on 14 held-out days: OpsLens vs the industry standard |
| **−3.46, interval −4.77 to −2.15** | The difference, and its 95% interval over seeds |
| **14 of 14 days** | OpsLens lower than the industry standard on every held-out day |
| **2.2% vs 5.8%** | A world generated after we froze the model, run once |
| **29 of 30** | Random worlds we did not design where OpsLens beat the industry standard |
| **19 of 30** | Where it was best of all six methods — we promised 27, we missed it, it is on screen |
| **53 vs 16 of 102** | Real desk, busiest real day: real misses warned about in time, OpsLens vs the desk's priority field |
| **0.857 vs 0.552** | Real desk: early-warning quality (AUC), OpsLens vs the priority field |
| **26.8** | Fewer missed deadlines from cross-training two Hindi-speaking agents, measured alone |
| **98.9%** | Explanations are faithful: removing the top reason changes the risk most |
| **91.0%** | Real public text benchmark (BANKING77) with the LLM cascade; 90.3% without |
| **93.3% vs 61.7%** | Ask OpsLens: the LLM understands the question vs keyword rules |

## The hardest questions (answer, then stop)
1. **"Your data is fake."** — "The food floor is simulated, because no company publishes support data. So
   every screen also runs on a real company's public IT desk, and on a real text benchmark."
2. **"You built the simulator, of course you win."** — "Same customers and same luck for every method,
   days it never saw, a world made after we froze it, and 30 random worlds: 29 of 30 still win."
3. **"Where does it lose?"** — "Under sustained overload, a published rule (least slack first) misses
   fewer deadlines; OpsLens protects gold and late customers there. We wrote the rule first; we show the miss."
4. **"Is the optimiser even needed?"** — "Honestly, at our size a greedy rule ties it. The win is the
   *value*: rescue from the risk model. Without risk scores we lose 2.15 points."
5. **"Is the AI just decoration?"** — "No: the risk model is the win. A logistic regression ranks almost
   as well (0.957 vs 0.977), but inside the dispatcher it misses 3.87% vs 2.05%."
6. **"Did you tune on the test days?"** — "No. Choices on validation days; test days run once; rules
   committed in git before each run — the dates are on the *Rules we wrote first* screen."
7. **"Does the LLM make up numbers?"** — "It cannot. It only picks a tool or writes {{keys}}; any digit it
   writes is rejected. Every number on screen comes from code."
8. **"Real desk: do you beat their routing?"** — "Not on routing — a simple 'still unassigned after 1
   hour' rule ties us on fast-tracking. We beat them on warning early: 53 vs 16 real misses."
9. **"Why not simulate the real desk too?"** — "We built a twin; it could not reproduce reality (27.9%
   vs 22.4% missed), so we show no twin result. Honesty over a nicer chart."
10. **"How would Eternal use it?"** — "Behind the AI first line, on the escalated tickets. Week one in
    shadow mode, like the real-desk screen: it only watches and warns. Then assist, then automatic."

## If you do not know
"I don't know that number by heart — every number on screen clicks through to where it was computed;
let me show you." Then click it.
