# Bot Q&A

Extra model answers for the OpsLens assistant (the bot in the side menu, `server/bot.py`): the
everyday questions a jury or a customer-support manager asks that `JUDGE_QA.md` does not cover.
Same rules as JUDGE_QA: answers under 80 words, and every number must exist in the current
results (checked by `tests/test_doc_numbers.py`).

---

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
LLM only sees the tickets the local model is unsure about. Details in docs/PRODUCTION.md.

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
