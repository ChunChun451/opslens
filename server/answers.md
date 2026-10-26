# OpsLens answers
## Privacy and the LLM layer

**Q1. You send customer tickets to Google and Groq. Isn't that a privacy problem?**
Every ticket passes through `mask_pii()` inside the LLM client before any network call.
Phones, emails, UPI IDs, cards (Luhn-checked), Aadhaar, PAN, order IDs, flat numbers and PIN
codes become tags. The cache stores only masked text. A test checks that the mock provider
never receives the raw phone number.

**Q2. (Attack) Regex masking misses things. What about names?**
True — names and free-text street names are not caught today, and we say so. Two things
limit the risk: the LLM only sees the tickets our local model is unsure about, not
all of them; and production would add a named-entity model (e.g. Presidio) before the regex
step.

**Q3. What happens if Gemini's free tier runs out during your demo?**
Nothing visible. Every reply is cached by a hash of the masked prompt, so the demo replays
from SQLite with Wi-Fi off. Live, the client falls back to Groq, and if both fail the
engine uses the local classifier and a template brief. The LLM is never on the critical path.

**Q4. Why not just call the API directly? Why build a client layer?**
Five jobs every call needs: PII masking, cache, per-minute and per-day limits, fallback
provider, and JSON repair. Doing them once means no module can forget one. It is about 150
lines and fully tested with a mock (outage, broken JSON, budget used up).

**Q5. (Attack) Free tiers change every month. How do you know your model names work?**
We don't trust blogs. `make ping` lists the models our own key can see, sends one real
request to each provider, and warns if the configured model name is missing. Names and
limits live in `config/providers.yaml`, so a change is a config edit, not a code change.

## Generator, simulator, baselines

**Q6. (Attack) Your data is fake. Why should we believe anything?**
The operations layer is generated, and we say so: public data has no timestamps, agents or SLAs.
But it is calibrated (Baseline A: 13.1% breaches, 0.80 utilisation), the roster was searched to
be a reasonable status quo, and the same engine is checked on a real ServiceNow incident log
(24,918 incidents, UCI). Every parameter is in two YAML files.

**Q7. (Attack) You built the simulator, so of course your policy wins in it.**
Three safeguards. Every policy gets the same tickets, the same luck (common random numbers) and
the same decision moments. Policies only see helpdesk fields, never the truth; illegal moves
raise an error. And the simulator matches the Erlang-C formula: 10.97 vs 10.79 minutes average
wait at utilisation 0.8.

**Q8. What are common random numbers and why do they matter?**
All luck is drawn once per seed, by ticket number. Ticket 812 takes the same base time under
FIFO and under OpsLens. So the difference between policies comes from decisions, not luck.
That is why our paired confidence intervals are narrow: OpsLens vs priority-first is −4.72
points, 95% CI [−5.98, −3.46], with only 5 seeds.

**Q9. Is your baseline a strawman?**
No. Baseline B (priority first) already cuts breaches from 13.1% to 6.8% on the test days. Agents
help other queues when theirs is empty, and shifts follow demand. But B makes the slowest 1% of
customers wait 1,007 minutes instead of 816. OpsLens has to beat B on breaches without that cost.

**Q10. Why did you change decisions to "event-driven"?**
Our first version decided every 2 minutes. The Erlang-C test showed agents then sat idle about a
minute between tickets, which slows every policy and is not how a real floor works. Now every
policy decides the moment a ticket arrives or an agent finishes — the same moments for all.

## Ingest and classification

**Q11. Why not send every ticket to the LLM? It's 2026.**
We measured it. On 400 random test tickets Gemini alone was 90.0% right; our local model, which
learns how reliable the customer's menu choice is per channel, was 98.0%. So the LLM only sees
the 1.54% of tickets the local model is unsure about (about 617 requests per million tickets).
There it fixed 57 answers and broke 37.

**Q12. (Attack) 98% accuracy on synthetic text proves nothing.**
Agreed, the text is partly synthetic and real accuracy will be lower. The number that matters
operationally is routing: tickets sent to the wrong team fall from 5.71 to 1.20 per 100, and
on phone tickets from 14.83 to 2.54, because the IVR menu choice is wrong a quarter of the time.

**Q13. How do you choose when to call the LLM?**
On validation days only. We tried confidence thresholds 0.5 to 0.95 with calibrated
(isotonic) probabilities and kept the most accurate one within a 15% LLM budget: 0.6, which
sends 1.6% of validation tickets to the LLM. Test days were never used to choose it.

**Q14. Is the LLM given customer data?**
Only masked text, in batches of 25, cached by a hash of the masked prompt. Answers are
validated (known category, every id present); missing ones are asked once more, then the local
answer stays. Cluster names containing digits are rejected.

## Patterns

**Q15. (Attack) You found 5 of 5 problems you planted yourself. Of course you did.**
That is why we ran a blind test: 20 new datasets, each with 3 problems of random type, place and
size drawn by code after the finder was frozen. It found and correctly diagnosed 57 of 60 (95%).
The misses: two small regional-language gaps and one spike on the very last day.

**Q16. How do you avoid "everything looks like a problem"?**
A pair of labels (e.g. Hindi × Team B) is reported only if it is at least 2× worse than BOTH
parents, with z ≥ 6. Spikes compare a day with days of the same type, and known sale days are
explained, not flagged. Unplanted findings must replicate on held-out days: one of two did.

**Q17. How fast would OpsLens notice a bad app release?**
The unseen day-47 app-bug surge was flagged 45 minutes after it began, with one false alert in
two weeks. The alert rule (z ≥ 4.5 on two checks in a row) was chosen on history days 15–42,
where it caught the day-18 payment spike, never on the test days.

**Q18. Can it find problems you did not plant?**
Yes: "regional-language tickets on weekday mornings wait 2.3× longer". We checked the roster: few
regional-language speakers start before 08:00. It replicated on the held-out days (2.0×).
A second unplanted finding did not replicate (1.2×), and we count it as a false alarm.

## Risk model

**Q19. (Attack) An AUC of 0.976 is too good to be true. Leakage?**
Three checks. Features come only from a snapshot of what was known at time t, and a test changes
the future and asserts the features do not move. Tickets already past their SLA are excluded.
And on real ServiceNow data the same method gets 0.857, against 0.552 for the priority rule.

**Q20. Why should a manager trust the probabilities?**
They are calibrated on validation days with isotonic regression. On test days, tickets scored
about 0.29 breached 32% of the time, and those scored about 0.74 breached 78%. The optimiser
multiplies these probabilities, so honesty matters more than a high AUC.

**Q21. The model learned under FIFO. Isn't that biased for your policy?**
It predicts the risk "if nothing changes", which is exactly the risk we act to prevent. The
optimiser uses the difference between waiting and being served now. Whether that helps is
measured in the simulator against both baselines, not assumed.

**Q22. Why LightGBM and not TabPFN or a neural network?**
Milliseconds per score, exact SHAP reasons, free licence, and no GPU. TabPFN-3 (2026) is
stronger on small tables in benchmarks, but its weights are for research use; our optional
challenger arena compares it on the same split before anyone argues from benchmarks.

## Forecast and staffing

**Q23. Your hourly WAPE is 0.305. That sounds bad.**
Hourly counts per category are small, so even a perfect forecast would be off by chance: the
Poisson floor is 0.280. "Same hour last week" scores 0.415. Per team-hour workload, our error is
0.235 vs 0.323. And the ranges are honest: the 80% range covered 79.2% of test hours.

**Q24. (Attack) "Hire more agents" is not a recommendation.**
We never add people. Every move keeps the same people and the same hours per week: shift starts
move 1–2 hours or a day off moves to a quieter day. Example: C05 takes Monday off instead of
Saturday, because Team C is short by up to 5 agents on Saturday nights.

**Q25. Why Erlang C?**
It is the call-centre standard, judges from operations know it, and our simulator reproduces it
(10.97 vs 10.79 minutes average wait). We use it with the upper 80% forecast so plans hold on
busier-than-expected days, and we weight hours with real overload 3×.

## Optimiser and the OpsLens policy

**Q26. What is the headline result?**
On 14 held-out days, 5 seeds, same tickets and luck for every policy: SLA breaches 2.05% with
OpsLens vs 5.51% for industry-standard skills routing (with our AI triage), 5.38% for an "SLA due"
sort, 6.77% priority-first and 13.08% FIFO. OpsLens − industry standard: −3.46 points, 95% CI
[−4.77, −2.15]. On a new world generated after v5 was frozen, run once: 2.20% vs 5.84%.

**Q27. (Attack) Does OpsLens cut breaches by abandoning tickets that are already late?**
Partly, by design, and we measured the cost. Once a ticket has missed its SLA, OpsLens serves
tickets that can still be saved first; a guard brings a late ticket back 8 hours past its SLA.
Late customers are late by 224 min on average (FIFO 211, priority-first 328). Total minutes past
SLA per 100 tickets: 483 vs 2,256 for priority-first and 1,432 for industry standard.

**Q28. Why a min-cost flow and not a simple sorted queue?**
When several agents are free, the best choice for one agent depends on the others: the only
Hindi refund agent should take the Hindi refund, not the English one anyone can take. The flow
optimises all free agents together in 0.07 ms per decision, 0.06 s for 5,000 tickets × 500
agents. Honestly, greedy with the same values ties it (2.03% vs 2.05%): the values are the engine.

**Q29. (Attack) You tuned the weights until your policy won.**
Weights were chosen on validation days 36–42 only (v3: 2.13% vs 5.94% for priority-first). But
the test days were looked at three times, because v1 and v2 failed a stress test there. So we
generated new worlds afterwards and ran each once; for v5 (seed 6262): OpsLens 2.20% vs "SLA due" 5.55%.

**Q30. What does OpsLens do worse?**
Reopens rise from 3.93% to 4.44% (+0.50 points, CI [+0.41, +0.59]), because OpsLens sometimes asks
an agent to rescue a ticket outside their training (1.6× slower, more reopens), only when the
rescue value is at least 0.5. And late customers wait slightly longer than under FIFO (224 vs
211 min late on average), the price of saving the tickets that can still make it.

## Evaluation, ablations, stress tests

**Q31. (Attack) You changed the policy after seeing test results. Isn't that cheating?**
We say it openly: the test days were run three times. v1 failed the +25% volume stress test
(51.7% vs 29.1% for priority-first), v2 still lost (40.5%), v3 won (10.7%); v5 today: 10.5% vs 28.9% for priority-first. Each new version
was designed and chosen on validation days only, and all three test results are kept in
results.json. The lesson: a stress test is a release gate.

**Q32. Which part of OpsLens actually creates the gain?**
The risk model. Switching it off raises breaches from 2.05% to 4.19% (+2.15, 95% CI [+1.66,
+2.63]). The classifier adds +0.14 [+0.01, +0.27]. Staffing, scarcity and the min-cost flow are
within noise on these days — we report that rather than hide it.

**Q32b. (Attack) Greedy matches your OR-Tools solver (2.03% vs 2.05%). Why keep min-cost flow?**
Because the gain was never the solver: it is the value each pair gets (risk-based rescue +
aging), which greedy also uses. Decisions happen the moment an agent frees up, so usually one
agent is free and there is nothing to coordinate. The flow costs 0.07 ms and guarantees the best
joint choice at shift starts and at scale (5,000 × 500 in 0.06 s).

**Q33. What happens on a really bad day?**
With 25% more tickets (on top of a sale day and an unseen surge), FIFO breaches 53.6%,
priority-first 28.9%, OpsLens 10.5%. With 10% of agents absent: 20.2%, 9.8% and 2.9%. In a
crisis OpsLens pauses its fairness guard to protect what can still be saved.

**Q34. How do I know every number in your deck is real?**
One command (`make eval`, ~20 minutes) regenerates eval/results.json and eval/NUMBERS.md. The dashboard
reads only that file, every number on screen clicks through to its path in it, and `make demo`
refuses to start on fixture data.

## Dashboard and live demos

**Q35. Can I try it myself?**
Yes. What-if re-runs any test day with more or fewer agents per team or more volume, for all
three policies, in about 10–20 seconds. Plant-a-problem hides a problem you choose in 21 fresh
days; OpsLens is not told where, and the same matcher as our blind test checks the answer.

**Q36. (Attack) Your LLM brief could invent numbers.**
It cannot put one on screen. The LLM gets keys, not values, and must write {{key}}; our code
fills each value from results.json. A digit or a number word written by the LLM sends the brief
back to a template. The dashboard labels it "written by LLM, numbers by code".

**Q37. Does it only work on your generated data?**
Upload any export with a column mapping. On the real UCI ServiceNow log (24,918 incidents) it
reports 36.6% breaches, the worst groups and evidence cards in about 10 seconds; the risk model
on the same data scores AUC 0.857 against 0.552 for the priority rule.

**Q38. Does the demo need the internet?**
No. Results, LLM answers (cached), data and Chart.js are local; What-if, Plant and Upload run
on the laptop. `make demo` checks that real results exist before it starts.

## Challenger arena

**Q39. Did you try a 2025 foundation model for the forecast?**
Yes, Chronos-2, zero-shot, same test hours and origins. Hourly WAPE 0.304 vs our LightGBM 0.305:
0.4% better, below the 2% bar we wrote down before running it, so LightGBM stays. Its 80% range
covered 76% of hours, ours 79%. Both sit near the Poisson floor (0.280): there is little left to win.

## Fix-at-source playbooks

**Q40. You find that cluster 17 sends 2.5× the wrong items. Do you just route those tickets faster?**
No. Each cause gets an action for the team that can remove it: partner ops gets a kitchen
order-check, product gets a phone-menu fix, a status banner and self-serve refunds, training gets
two named agents to cross-train. Each one was replayed on the 14 held-out days.

**Q41. What do those actions actually save?**
On today's priority-first floor, all six together: 163 fewer breaches in two weeks (95% CI 125 to
201). OpsLens with every fix and the staffing changes: 889 fewer than priority-first today, out of
1,220. The biggest single one: cross-training two Hindi speakers, −79.0 under priority-first and
−26.8 under OpsLens (alone, today's roster, CI −39.0 to −14.6).

**Q42. (Attack) "Saves 30% of tickets" — you made that number up.**
Some inputs are guesses, and we label them: 30% of customers skip a ticket after a status banner,
60% use self-serve. Each guess is re-run at a low and high value (banner 15% → 50%: 1 to 16
breaches saved). Everything else is measured: which tickets, which agents, which hours.

**Q43. Why do most playbooks barely help under OpsLens?**
Because OpsLens already absorbs those symptoms: its classifier fixes the phone-menu routing, so
the menu fix saves 39.0 breaches under priority-first but only 2.0 under OpsLens (no clear effect).
Cross-training still helps (−26.8) because it adds capacity where no routing can help. We show both
columns on purpose.

**Q44. Is the LLM finally doing something?**
It drafts the request to each owner team, from facts it can only cite by key, like the brief. It
never writes a digit; one draft that copied "cluster 17" was rejected and the template was used
until we passed the cluster number as a key too.

## How close to perfect

**Q45. Is OpsLens the best possible? How would you even know?**
We computed the physical floor: tickets that breach even with unlimited agents and perfect routing
(their own work outlasts the SLA, or nobody on shift speaks their language). On the test days it is
1.31%. OpsLens (2.05%) captures 83% ± 4 of everything possible over industry routing; on a new
world generated after v5 was frozen, 81% ± 4.

**Q46. (Attack) Your "floor" is just another simulation you can tune.**
It is not a simulation: it is computed exactly per ticket, and a proof shows no legal policy can beat
it. We attacked the proof: ten policies, including random legal ones, on 25 random worlds, never
beat it. It is a bound, not a choice, so nothing is tuned on it.

**Q47. Is 1.31% true for any company?**
No. The method is general; the number belongs to this data. It depends on the tickets, the SLAs,
the roster and luck (1.23–1.38% across our five seeds). On your export we would compute it again.

**Q48. Did you find anything wrong while building it?**
Yes, in our own simulator: a transfer used to change a ticket's work-time draw, so policies with
many transfers did not see exactly the same luck. We fixed it and regenerated every number (OpsLens
v3 moved by only 0.01 points). A promising v4 then lost its significance, so our rule rejected it.

**Q49. What is v5, and how do you know it is not luck?**
The floor showed tickets nobody trained can reach before their deadline (Hindi refunds at night).
v5 lets an untrained agent who speaks the language rescue them. The first test (5 seeds) could not
separate it from luck, so we did not ship it; a new pre-registered test on 20 fresh seeds did:
−0.17 points [−0.20, −0.13]. Test days: 2.21% → 2.05%.

**Q50. (Attack) What does v5 cost?**
Cross-skill work is 1.6× slower and reopens more (4.44% vs 3.93% for the baselines). Under +25%
volume on validation days, already-late customers got later and the slowest 1% waited longer. On
the test days the slowest 1% did not wait longer (728 min, as before). We report it rather than hide it.

## Real public data and your plan

**Q51. Why the UCI ServiceNow log as your public dataset?**
It is the only public dataset we found with real teams, real agents, real hand-offs and a real SLA
flag — what "distribute the workload" needs. A real company's service desk: 24,918 incidents, 70
teams, 36.6% missed their SLA. Licence CC BY 4.0.

**Q52. What does OpsLens do better than the real desk?**
It warns which incidents will miss their SLA, one hour after they open: AUC 0.857 vs 0.552 for the
desk's own priority field. Its riskiest 20% hold 49.9% of all misses; the priority field's, 24.6%.
Learned on the first months, scored on later ones.

**Q53. (Attack) Does it route incidents to the right team better than the real people?**
No, and we say so. Overall the desk is right more often. Even when OpsLens is sure, it is right
78.2% of the time vs 77.8% for the desk — no real gain. So we do not recommend it on that desk.

**Q54. (Attack) Your forecast loses on the real data.**
Yes: 0.365 vs 0.341 for "same day last week". Three months of history is too short for the learned
forecast; on our food floor it wins clearly. We show the real result on the Proof screen.

**Q55. What do Accept and Override actually do?**
Accept puts a recommendation in Your plan with its measured effect, and Simulate replays a day with
the whole plan, live. Example: cross-training two Hindi agents, 26.8 fewer missed SLAs over 14
held-out days with OpsLens. Override records why the manager said no.

**Q56. (Attack) Most of your staffing moves say "no clear effect". Why recommend them?**
Because one move is one person for one week: small. Each is measured alone, so we show it: only
Arjun N.'s day-off swap is clearly helpful (−7.6, CI −15.0 to −0.2). All 18 recommendations
together: −48.8 (CI −63.1 to −34.5) of 379.8 missed SLAs. The manager can override the rest.

**Q57. (Attack) Isn't "all together" just the single effects added up?**
No. It is its own replay with every item in place: same 14 days, same 5 seeds, same luck. It is
smaller than the sum because fixes overlap — cross-training and a Hindi-heavy staffing move help
the same tickets. That is why Your plan simulates the plan instead of adding numbers.

**Q58. How long does Simulate take, and is it the real engine?**
The same simulator and OpsLens policy as every result: one test day, three seeds, without and
with the plan, in parallel worker processes. About 20 seconds for a new plan; a plan simulated
before comes back at once. It runs only on held-out days 43 to 56.

**Q59. On the real desk, do you show an outcome or only an AUC?**
An outcome, under one stated assumption: a fast-tracked incident is picked up at its 1-hour mark and
everything else happens as it really did. Fast-tracking 20% of each day's incidents, OpsLens's pick saves
108 missed deadlines [86.5, 136.9] on the test months; the desk's priority field saves 29; the ceiling is 223.

**Q60. (Attack) Beating the priority field is a strawman — 94% of incidents share one value.**
Agreed, so we pre-registered a harder rule: beat the BEST other picker. It failed. "Still unassigned
at 1 hour" saves 115, OpsLens 108: −7 [−30.5, +29.1]. Fast-track only helps incidents still waiting;
risk is not rescue. We show this on the Proof screen.

**Q61. Are your real-log findings just stories fitted to the data?**
Each card was found on the learning months and re-measured on later months it never saw. All 3 still
hold with CIs excluding 0: waits on outsiders 45.8 points [39.5, 50.8], slow pickup 37.7 [34.5, 41.5],
Category 26 bouncing 37.6 [26.5, 54.5].

**Q62. (Attack) Can your detectors find problems in real data, or only in your simulator?**
Partly. We planted 60 random problems into the real test weeks, ranges fixed before the run. We found
9: spikes 6 of 20 (same evening), team slowdowns 0 of 20, bouncing categories 3 of 20, with 7.7 false
alarms per 30 clean days. We report this instead of re-tuning on test weeks.

**Q63. Are the real desk's bottleneck alerts any good?**
Week-ahead "more new incidents than the team usually closes": precision 77.6%, recall 92.8% on 240
team-days, vs 54.0% / 97.9% for alerting every weekday. The forecast choice was honest too: the check
weeks picked the learned model, which then did worst on test (0.365 vs 0.326 for the average).

**Q64. Does OpsLens only win in the world you built?**
No. We drew 30 random worlds from ranges fixed before running: volume, skills, deadlines, absences,
chats per agent. OpsLens beats the industry standard in 29 of 30 (median −8.19 points, CI −12.20 to
−3.28), and is the best of six policies in all 13 worlds up to today's load.

**Q65. (Attack) Your own pre-registered rule failed: lowest in only 19 of 30 worlds.**
Yes, and we show it. All 11 losses are floors in sustained overload (1.06× today's load or more, the
backlog growing for weeks), all to least-slack-first. In 10 of the 11 OpsLens keeps late customers
less late: least slack wins the count by letting the already-late wait much longer.

**Q66. (Attack) A logistic regression would do just as well as your LightGBM.**
On ranking it nearly does: AUC 0.957 vs 0.977 on the same 26,811 test snapshots. But dispatch does not use the ranking, it uses the *rescue*: how much serving a ticket now lowers its risk. Swapped into the dispatcher, the logistic regression misses 3.87% of SLAs vs 2.05% (+1.83 points [+1.66, +2.00], test days, 5 seeds), almost as bad as no model (4.19%).

**Q67. Isn't "least time left" all you need?**
It ranks well (AUC 0.884) but cannot tell what serving now changes: time left is the same whether the ticket waits or not, so its rescue is zero for every ticket. That is our "no risk model" ablation: 4.19% vs 2.05%.

**Q68. Are your probabilities honest?**
Brier 0.055 (LR 0.080, rule 0.131). The reliability bins per model are in `results.prediction_baselines` (predicted vs observed per decile).

**Q69. (Attack) Do your bottleneck alerts come true?**
Made 1–7 days ahead from the P80 forecast: 58% of alert hours really were over 85% load (naive forecast 56%) and we caught 98% of those hours (naive 91%). Most overloaded hours do not turn into a breach cluster (precision 15–18% against that), because the floor absorbs them with cross-skill help. So the alerts are cautious by design: better than naive, not a crystal ball.

**Q70. (Attack) SHAP reasons are decoration: you never checked the model uses them.**
We did. Remove a ticket's top reason and its risk falls more than when a random feature is removed in 98.9% of 3,000 at-risk test tickets (3.18 vs 0.17 log-odds). Rule fixed before the run: ≥ 80%.

**Q71. Do the reasons point at the real cause?**
For the Hindi refund problem we planted, 98.6% of at-risk Hindi refund/payment tickets name language or skill coverage in their top 3 reasons. For other Team B tickets it is 63%: at night, few capable agents on shift is a real cause for everyone.

**Q72. Why did the optimiser give this ticket to this agent?**
Every assignment names the runner-up: "runner-up B03, value 0.31 lower", or "C04 valued it more but took T061200": the optimiser maximises the whole floor, not each pair. A test proves the text never changes a decision.

**Q73. (Attack) Your staffing "optimiser" is a greedy search. Did you try a real one?**
Yes: an exact CP-SAT tour scheduler (start hours and days off for every agent at once). It beats greedy on the planning score every week, but missed SLAs did not follow: −0.03 points on 20 fresh seeds (CI crosses 0) and +0.21 [+0.05, +0.37] on the test days. Our rule, fixed before the run, said keep greedy, so we did.

**Q74. Then why does staffing matter at all?**
The staffing plan is a small lever here (removing it costs +0.06 points); the dispatcher's risk-based rescues decide most of the outcome. A better roster objective would be measured in simulated breaches, not in Erlang-C shortfall: that is the next step, not a claim.

**Q75. Is CP-SAT fast enough?**
N ≤ 2 changes per team: proven optimal in about 17 s per week; N = 4 gives its best roster within 30 s. Rosters are weekly, so seconds are fine.

**Q76. (Attack) 98% on text you generated yourselves proves nothing.**
Agreed, so we ran the same classifier on BANKING77, 3,080 real bank-customer queries we never saw: 90.3% alone, 91.0% with the LLM cascade (+0.71 [+0.16, +1.27]). Published: frozen BERT 87.2%, fine-tuned BERT 93.7%.

**Q77. Does the LLM earn its cost?**
Where data is scarce, a lot: with 10 examples per intent the cascade goes 68.5% → 78.7% (+10.1 points) sending 25% of queries, about $6 per million tickets at list price. With full data it adds +0.7 points for 5.6% of traffic, $1.41 per million.

**Q78. Why not send everything to the LLM?**
Zero-shot it scored 79.0%, below our local model (90.3%) on full data, and slower (~10 s per batch vs 0.3 ms per query). The cascade uses each where it is strong.

**Q79. Does the LLM diagnose root causes better than your rules?**
No: 61 of 62 cards vs 62 of 62. We use it for the readable one-line cause, never for numbers (0 of 62 replies contained a digit).

**Q80. If risk ties a simple rule, is OpsLens's idea of 'rescue' any better on the real desk?**
We wrote three rescue pickers down first and let the check weeks choose. The rescue model saved the most
at every budget: 160 vs 115 at 20%, but +45 [0.0, 100.5] does not exclude zero, so we do not claim it.
At 10% the gap is +46 [30.8, 66.7].

**Q81. (Attack) Did a second, better-tuned detector find more planted problems?**
No. Detector v2 was designed on the check weeks with a limit of 10 false alarms per 30 days fixed first. No setting met it, so the fallback rule kept v1: on 60 fresh test plants both found 11. We report it as missed.

**Q82. (Attack) Why not just simulate the real desk with OpsLens's routing and show fewer misses?**
We tried, the honest way: a digital twin of the desk, with a validation gate fixed before any run. Running the desk's own policy, the twin had to reproduce reality on months it was not fitted to. It missed 27.9% vs 22.4% real, so it failed and we show no twin result. A log does not record real work time; a twin that cannot reproduce reality would only show our assumptions. What we do show on real data: the warnings (shadow mode) and the fast-track estimate.

**Q83. When least slack beats you under overload, who pays for OpsLens's extra misses?**
We rebuilt the 11 worlds and looked (analysis after the result, labelled as such). OpsLens misses fewer gold customers in 11 of 11 and keeps late customers less late in 11 of 11: it follows its business-impact weights and never abandons the late. It does not protect P1 better (4 of 11). Least slack wins the raw count by letting the already-late wait much longer.

**Q84. (Attack) You lose overloaded worlds to least slack. Why not switch strategy when overload is predicted?**
We tried, with the rule written first. Round 1's best mode (value per minute of work) was no worse on a normal
week (−0.006 points) but was lowest in only 18 of 30 new worlds — we needed 27. Switching to least slack fired too
often on normal weeks. v5 stays; it still beat the industry standard in 30 of 30 new worlds.

**Q85. Can I upload my own CSV and see what OpsLens would have done?**
Yes. Map start, end or duration, and what a miss is. OpsLens learns on your first 70% and scores the rest once. On the UCI log
as a plain CSV it took 1.5 s: flagging 1 item in 5 as they opened, it caught 48.9% of the real misses; the priority field 25.5%.

**Q86. (Attack) Then tell me how many SLA breaches I would have had with OpsLens.**
Not from a log, honestly. Replaying your floor needs how long each item was worked on, who was on shift and who can handle
what; an export has none of these. We show what a log can answer: which misses OpsLens would have flagged in time. In shadow
mode, the busiest later day of the UCI log: 50 of 111 real misses flagged, the priority field 22.

**Q87. (Attack) Couldn't a column in my file leak the answer?**
Three guards: outcome-like names (resolved, closed, sla, duration, taken...) are never suggested; you can untick any column;
and any column that alone sorts the learning items almost perfectly is dropped as written after the fact. A test plants
such a column and checks it is dropped; the screen lists every column it learned from.

**Q88. What if my file is junk or too small?**
It is refused, with the reason: it needs at least 500 rows, 7 days, 30 misses and 30 in time, and items that end after they
start. A 100,000-row file takes 2.9 s.

**Q89. I uploaded my own CSV. Is every screen really about my file?**
Yes. Real data has two sources: the UCI example and your file. After *Analyse my file*, Overview, Shadow mode, Problems,
Risks, Actions and Proof are all drawn from the report on your file, learned on your first 70% and scored once on the rest,
and every number clicks to its source. On the UCI log as a plain CSV: OpsLens caught 48.9% of real misses, the priority field 25.5%.

**Q90. (Attack) My file has no priority or SLA column. Then you just make something up?**
No. Without an on-time column, a miss is taking longer than your file's median time rounded up, labelled as OpsLens's
assumption, and you can type your real promise. Without a priority field, OpsLens is compared with a rule of thumb (the past
miss rate of your best column). Anything that needs a missing column says so by name: "needs a priority column".

**Q91. (Attack) You forecast my teams' workload too. Isn't that fitting noise?**
Each day's forecast reads only counts from a week or more before it; it learns on the days before your later 30% and is
scored on the four weeks after, against "same weekday last week", and the screen says which wins. On the real desk the
learned team forecast does not win: 0.365 against 0.341 for same day last week, and we show that.

## The basics

**B1. What is OpsLens, in one sentence?**
A decision engine for a support floor: it tells you which tickets will be late, why, and what to
do about it, and it proves the plan works by replaying days it has never seen against the
industry-standard routing. Every number on screen clicks through to its evidence.

**B2. How does OpsLens work, step by step?**
It reads each ticket's text (not the menu the customer clicked), finds recurring problems with
evidence, forecasts the next 48 hours, scores every waiting ticket's risk of missing its promise,
and assigns work with an optimiser that protects rare skills and rescues tickets about to be late.
Then a fair simulator replays held-out days to measure it against every baseline.

**B3. (Attack) Can it scale to millions of tickets a day?**
Decisions are local: a free agent only needs the tickets it can serve, so the floor splits by
language × skill group and each part runs its own loop. Our scale test assigned 5,000 waiting
tickets to 500 agents in 0.04 seconds. Risk scoring is one LightGBM call every few minutes, and the
LLM only sees the tickets the local model is unsure about.

**B4. How would it plug into our helpdesk (Zendesk, Freshdesk, ServiceNow)?**
It reads the helpdesk's ticket events (created, assigned, transferred, resolved) through its API or
webhooks and writes assignments back through the assignment API; agents keep the final say. The
ServiceNow adapter we built for the real public desk is the template. We would start in shadow
mode: OpsLens watches for two weeks and only then is anything switched on.

**B5. What does it cost to run?**
No GPU and no paid licences: free libraries (LightGBM, OR-Tools, scikit-learn, FastAPI) and free LLM
tiers. The LLM is called only when the local model is unsure, every reply is cached, and the whole
demo runs with Wi-Fi off.

**B6. (Attack) What is the business impact in rupees?**
We do not invent a cost per missed promise. OpsLens measures what a manager can verify: missed
promises, minutes late, waiting times and agent-hours, each against the industry standard on days
it never saw. A company multiplies by its own cost per breach; on the real desk we show no money at
all, because no such cost exists for it.

**B7. Who built OpsLens?**
Team SoyaChaap, for the Deviathon 2.0 finale (problem DEV_103). The engine, the simulator, the
evaluation and this dashboard are our own; the public data sources and their licences are listed in
data/SOURCES.md.

**B8. What would you do in the first month at a real company?**
Run it in shadow mode next to the current routing, log what it would have done, and compare in the
simulator before switching anything on. Then measure missed promises, P90 resolution time, P99 wait,
reopens and agent overrides weekly, retrain weekly with drift checks, and keep the stress tests as a
release gate.

**B9. (Attack) What can't OpsLens do?**
The operations data of the food floor is generated, so the real public desk is the honest guide.
On that real log OpsLens can only watch (a log cannot replay new decisions), its planted-problem
detector is weak, and its forecast does not beat "same day last week". In random worlds under heavy
overload, "least slack first" saves more promises in total. Every one of these is on screen.

**B10. Isn't an AI chatbot enough for customer support now?**
An AI first line resolves the routine chats. What still reaches people are the escalated,
harder, deadline-critical tickets, and that human floor is what OpsLens runs: who takes which ticket,
which ones will be late, and what to fix at the source.

**B11. How does this bot work? Can it make up numbers?**
No. It never writes a number itself. A customer complaint goes to our text classifier; a
what-if or a ticket question goes to the engine, which computes the answer; a question about
OpsLens gets the closest prepared answer, and every number in those answers is checked against the
results file by a test. The LLM only helps pick which prepared answer fits.

**B12. What is shadow mode?**
A real day at a real company's IT desk, replayed: incidents arrive at their real times, OpsLens
warns one hour after each opens, and the real outcome appears when it really happened. On the
busiest day, of 102 missed deadlines OpsLens had warned about 53; the desk's own priority field
about 16. Open it under IT service desk → Overview → Shadow mode.

**B13. How is OpsLens different from the helpdesk tools we already have?**
Helpdesk tools tell you a ticket is already late. OpsLens tells you which tickets will be late, why,
and what to do, and it shows the effect before you act: on the held-out days the industry
standard missed 5.51% of promises and OpsLens 2.05%, with the same tickets, agents and luck.
