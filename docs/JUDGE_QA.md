# Judge Q&A

Questions a sharp industry judge would ask, with model answers under 60 words.
Every number must come from our results or code. "Attack" = a question meant to break us.
Grouped by module; newest milestone at the bottom.

---

## M1 — Privacy and the LLM layer

**Q1. You send customer tickets to Google and Groq. Isn't that a privacy problem?**
Every ticket passes through `mask_pii()` inside the LLM client before any network call.
Phones, emails, UPI IDs, cards (Luhn-checked), Aadhaar, PAN, order IDs, flat numbers and PIN
codes become tags. The cache stores only masked text. A test checks that the mock provider
never receives the raw phone number.

**Q2. (Attack) Regex masking misses things. What about names?**
True — names and free-text street names are not caught today, and we say so. Two things
limit the risk: the LLM only sees the tickets our local model is unsure about, not
all of them; and production would add a named-entity model (e.g. Presidio) before the regex
step. That is in PRODUCTION.md.

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

---

## M2 — Generator, simulator, baselines

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
That is why our paired confidence intervals are narrow: Baseline B vs A is −6.29 points,
95% CI [−7.50, −5.07], with only 5 seeds.

**Q9. Is your baseline a strawman?**
No. Baseline B (priority first) already cuts breaches from 13.1% to 6.8% on the test days. Agents
help other queues when theirs is empty, and shifts follow demand. But B makes the slowest 1% of
customers wait 1,007 minutes instead of 816. OpsLens has to beat B on breaches without that cost.

**Q10. Why did you change decisions to "event-driven"?**
Our first version decided every 2 minutes. The Erlang-C test showed agents then sat idle about a
minute between tickets, which slows every policy and is not how a real floor works. Now every
policy decides the moment a ticket arrives or an agent finishes — the same moments for all.

---

## M3 — Ingest and classification

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

---

## M4 — Patterns

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

---

## M5 — Risk model

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

---

## M6 — Forecast and staffing

**Q23. Your hourly WAPE is 0.305. That sounds bad.**
Hourly counts per category are small, so even a perfect forecast would be off by chance: the
Poisson floor is 0.280. "Same hour last week" scores 0.415. Per team-hour workload, our error is
0.235 vs 0.321. And the ranges are honest: the 80% range covered 79.2% of test hours.

**Q24. (Attack) "Hire more agents" is not a recommendation.**
We never add people. Every move keeps the same people and the same hours per week: shift starts
move 1–2 hours or a day off moves to a quieter day. Example: C05 takes Monday off instead of
Saturday, because Team C is short by up to 5 agents on Saturday nights.

**Q25. Why Erlang C?**
It is the call-centre standard, judges from operations know it, and our simulator reproduces it
(10.97 vs 10.79 minutes average wait). We use it with the upper 80% forecast so plans hold on
busier-than-expected days, and we weight hours with real overload 3×.

---

## M7 — Optimiser and the OpsLens policy

**Q26. What is the headline result?**
On 14 held-out days, 5 seeds, same tickets and luck for every policy: SLA breaches 5.08% with
OpsLens vs 6.82% priority-first and 13.11% FIFO. OpsLens − priority = −1.74 points, 95% CI
[−2.35, −1.13]. P90 resolution 130 vs 198 minutes; the slowest 1% wait 474 vs 1,007 minutes.

**Q27. (Attack) Does OpsLens cut breaches by abandoning tickets that are already late?**
No: the slowest customers do much better. P99 wait falls from 1,007 to 474 minutes vs priority-
first, because every ticket gains value for each hour it waits and a guard serves anything older
than 240 minutes next. Breach % alone would hide starvation; we report P90 and P99 for that reason.

**Q28. Why a min-cost flow and not a simple sorted queue?**
When several agents are free, the best choice for one agent depends on the others: the only
Hindi refund agent should take the Hindi refund, not the English one anyone can take. The flow
optimises all free agents together. It takes 0.08 ms per decision (max 8.8 ms), 0.115 s for
5,000 tickets × 500 agents.

**Q29. (Attack) You tuned the weights until your policy won.**
We tuned on validation days 36–42 only, one weight at a time, and froze the weights before
touching the test days. On validation the result was 3.75% vs 5.94% for priority-first; on the
unseen test days it held: 5.08% vs 6.82%. The tuning log is in eval/parts/tuning.json.

**Q30. What does OpsLens do worse?**
Reopens rise from 3.93% to 4.35%, because OpsLens sometimes asks an agent to rescue a ticket
outside their training (1.6× slower, more reopens). It only does so when the ticket's rescue
value is at least 0.5; without those jobs, breaches on validation rose to 6.48%.

---

## M8 — Evaluation, ablations, stress tests

**Q31. (Attack) You changed the policy after seeing test results. Isn't that cheating?**
We say it openly: the test days were run three times. v1 failed the +25% volume stress test
(51.7% vs 29.1% for priority-first), v2 still lost (40.5%), v3 wins (10.7%). Each new version
was designed and chosen on validation days only, and all three test results are kept in
results.json. The lesson: a stress test is a release gate.

**Q32. Which part of OpsLens actually creates the gain?**
The risk model. Switching it off raises breaches from 2.20% to 4.21% (+2.01, 95% CI [+1.55,
+2.47]). The classifier adds +0.14 [+0.01, +0.27]. Staffing, scarcity and the min-cost flow are
within noise on these days — we report that rather than hide it.

**Q32b. (Attack) Greedy matches your OR-Tools solver (2.18% vs 2.20%). Why keep min-cost flow?**
Because the gain was never the solver: it is the value each pair gets (risk-based rescue +
aging), which greedy also uses. Decisions happen the moment an agent frees up, so usually one
agent is free and there is nothing to coordinate. The flow costs 0.08 ms and guarantees the best
joint choice at shift starts and at scale (5,000 × 500 in 0.05 s).

**Q33. What happens on a really bad day?**
With 25% more tickets (on top of a sale day and an unseen surge), FIFO breaches 53.6%,
priority-first 29.1%, OpsLens 10.7%. With 10% of agents absent: 20.3%, 9.9% and 3.1%. In a
crisis OpsLens pauses its fairness guard to protect what can still be saved.

**Q34. How do I know every number in your deck is real?**
One command (`make eval`, ~20 minutes) regenerates eval/results.json and NUMBERS.md. The dashboard
reads only that file, every number on screen clicks through to its path in it, and `make demo`
refuses to start on fixture data.

---

## M9–M11 — Dashboard and live demos

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

---

## Challenger arena (16 Oct)

**Q39. Did you try a 2025 foundation model for the forecast?**
Yes, Chronos-2, zero-shot, same test hours and origins. Hourly WAPE 0.304 vs our LightGBM 0.305:
0.4% better, below the 2% bar we wrote down before running it, so LightGBM stays. Its 80% range
covered 76% of hours, ours 79%. Both sit near the Poisson floor (0.280): there is little left to win.

---

## Fix-at-source playbooks (16 Oct)

**Q40. You find that cluster 17 sends 2.5× the wrong items. Do you just route those tickets faster?**
No. Each cause gets an action for the team that can remove it: partner ops gets a kitchen
order-check, product gets a phone-menu fix, a status banner and self-serve refunds, training gets
two named agents to cross-train. Each one was replayed on the 14 held-out days.

**Q41. What do those actions actually save?**
On today's priority-first floor, all six together: 179 fewer breaches in two weeks (95% CI 139 to
219). With OpsLens: 57 fewer (CI 40 to 73). Together, 889 fewer than priority-first today, out of
1,230. The biggest single one: cross-training two Hindi speakers, −83 and −51.

**Q42. (Attack) "Saves 30% of tickets" — you made that number up.**
Some inputs are guesses, and we label them: 30% of customers skip a ticket after a status banner,
60% use self-serve. Each guess is re-run at a low and high value (banner 15% → 50%: 1 to 16
breaches saved). Everything else is measured: which tickets, which agents, which hours.

**Q43. Why do most playbooks barely help under OpsLens?**
Because OpsLens already absorbs those symptoms: its classifier fixes the phone-menu routing, so
the menu fix saves 46 breaches under priority-first but only 3 under OpsLens. Cross-training still
helps (−51) because it adds capacity where no routing can help. We show both columns on purpose.

**Q44. Is the LLM finally doing something?**
It drafts the request to each owner team, from facts it can only cite by key, like the brief. It
never writes a digit; one draft that copied "cluster 17" was rejected and the template was used
until we passed the cluster number as a key too.
