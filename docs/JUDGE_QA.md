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
