# OpsLens in production — what changes after the hackathon

OpsLens is built as a prototype on a generated support floor plus one real public dataset.
This page says, plainly, what a real deployment at a company like Eternal would need.

## 1. Where OpsLens sits
- In 2026 an AI first line (such as Eternal's Nugget) resolves most routine chats. The tickets
  that reach people are the escalated, harder, SLA-critical ones. **OpsLens runs that human
  floor**: it decides who takes which escalated ticket, predicts which ones will miss their SLA,
  and plans staffing for the next hours and days.
- The AI first line passes each escalation with its transcript; OpsLens classifies it, scores
  its risk and routes it. The menu choice / IVR choice becomes one input, not the routing key.

## 2. Integration with the helpdesk
- **Read**: a stream of ticket events from the helpdesk API or webhooks (created, assigned,
  transferred, resolved, reopened) — the same fields `opslens/ingest.py` validates today. The
  UCI ServiceNow adapter (`opslens/adapters/uci_incidents.py`) is the template for any other tool.
- **Write**: assignments go back through the helpdesk's assignment API. Agents keep the final say.
- **Agent overrides are a signal**: every Accept / Override in the dashboard is logged with the
  reason. A rising override rate for one rule means the rule is wrong — review it weekly.
- **Shadow mode first**: run OpsLens next to the existing routing for two weeks, log what it
  *would* have done, and compare in the simulator before switching anything on.

## 3. Scale (millions of tickets per day)
- Decisions are local: a free agent only needs the waiting tickets they can serve. Partition the
  floor by **language × skill group**; each partition runs its own decision loop.
- The optimiser solves 5,000 waiting tickets × 500 agents in about a tenth of a second; per
  decision in our runs it takes well under a millisecond. Risk scoring is a LightGBM call on a
  few hundred rows every few minutes.
- The classifier's LLM tier is called for about 1.5% of tickets (≈ 617 requests per million
  tickets with batches of 25). The cache removes repeats.

## 4. Models in production
- **Retrain weekly** (risk, forecast, classifier) on the last 5 weeks; choose thresholds on the
  most recent week; never on the week being reported.
- **Drift checks** before each retrain: category mix, language mix, handle times, breach rate
  and the risk model's calibration on last week (predicted vs observed per decile). Alert when
  any moves beyond its normal weekly range (robust z, the same rule as the pattern finder).
- **Optimiser weights** are re-checked monthly in the simulator on the latest weeks, with the
  stress tests (+25% volume, 10% absenteeism) as a release gate. Our first policy failed the
  volume stress test — that is exactly why the gate exists.

## 5. Privacy
- PII is masked before any text leaves the company (`opslens/privacy.py`): phones, emails, UPI
  IDs, cards (Luhn-checked), Aadhaar, PAN, order IDs, addresses, PIN codes.
- Production adds a named-entity model for names and free-text addresses before the regex step.
- The LLM cache stores only masked text. Retention follows the helpdesk's own policy.
- For the strictest data, the LLM tier can run on a self-hosted open model; the local
  classifier already handles about 98% of tickets without any LLM.

## 6. What we would measure in the first month
- SLA breach % and P90 resolution time vs the same weeks last year and vs shadow-mode Baseline B.
- P99 wait (no customer left behind), reopen rate (cost of cross-skill rescues), transfers per 100.
- Agent-side: load fairness and override rate.

## 7. Week one at a real company: shadow mode (already on screen)
*IT service desk → Shadow mode* is exactly the first week of a deployment: real incidents at their
real times, OpsLens's warning one hour after each opens, next to the desk's own priority field,
and the real outcome when it happens. On the busiest day of the public log, OpsLens flagged 53 of
the 102 real misses in time, the priority field 16. Nothing is switched on until shadow mode has
run for two weeks on the company's own data and the numbers hold.

## 8. Beyond support tickets
The engine works on *work items*: something arrives at a time, has a type, a deadline, and is
handled by someone with the right skill. Support tickets and IT incidents are two such kinds
(both on screen); sales leads with a response-time promise, insurance claims, or internal
approval requests have the same shape, and `Your data` maps any CSV export onto it. We have
tested two kinds, not these others: their first step is the same shadow mode.

## 9. Known limits of the prototype (updated 24 Oct)
- The food-delivery operations data is generated; real floors are messier (breaks, customers who
  give up). The real public desk is the honest guide to what transfers: early warning AUC 0.857
  vs 0.552 for its own priority field.
- Under sustained overload (1.06× today's load or more for weeks) a published rule, least slack
  first, misses fewer deadlines than OpsLens; OpsLens protects gold and late customers there. An
  overload switch was designed and tested (W13) and is reported with its result.
- The value formula is hand-built with weights chosen on validation days, not learned end to end.
- Staffing moves are greedy and weekly; an exact CP-SAT roster was built and did not beat them on
  missed deadlines (it is reported, not shipped).
- A digital twin of the real desk failed its validation gate, so OpsLens's routing gain on real
  data is not claimed; only its warnings (shadow mode) and the fast-track estimate are.
