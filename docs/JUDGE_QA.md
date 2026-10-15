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
