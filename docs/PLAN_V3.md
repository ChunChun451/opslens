# Plan v3 — from a strong engine to a product a judge understands (19 Oct 2026)

Written after re-reading the problem statement (DEV_103) word for word, as a hackathon judge and
as the operations manager who would use OpsLens. The owner asked for an unbiased rethink.

## 1. The judge's verdict on what we have
**Strong:** a fair simulator, held-out days, six baselines incl. the best published rules, a risk
model, a forecast, playbooks, a cold open that people remember. Deliverable 4 (baseline vs
proposed) is far beyond what other teams will bring.

**Weak — and these lose hackathons:**
1. **Deliverable 1 says "a working prototype using a provided or publicly available dataset."**
   Our product runs on data we generated. The public data is hidden behind "Use your own data".
2. **The problem statement asks for "a dashboard showing the expected impact of these
   interventions."** Our recommendations have Accept / Override buttons that do nothing.
3. **Nobody can follow it.** Nine tabs, hundreds of numbers. The owner could not explain what each
   screen is for. If the builder cannot, a judge in 7 minutes cannot.

## 2. The manager's verdict
A team lead does not want analytics; they want a loop: *what is going wrong → what will go wrong
→ what should I do → if I do it, what changes?* Our screens follow how we BUILT the engine, not how
a manager WORKS. Small decisions (who takes ticket 812) should run automatically; the manager should
approve the big ones (shift changes, training, process fixes) and see their effect before agreeing.

## 3. Decisions
1. **Public dataset: the UCI ServiceNow incident log** (CC BY 4.0, a real company's IT service desk).
   24,918 incidents, 72 teams, 220 agents, a real SLA flag (36.6% missed). One in three incidents is
   first sent to the wrong team, and those miss their SLA 54% of the time vs 22%. It is the only public
   dataset we found with teams, agents, routing AND an SLA outcome — what "distribute the workload"
   needs. Rejected: CFPB complaints (no teams), Twitter support (no SLA, no teams), BPIC 2013 (no
   SLA flag, vaguer terms), Kaggle food-delivery (no licence, generated data).
2. **Two worlds, one engine.** A switch in the top bar: **Food-delivery support (simulated)** — the
   star, where we can replay decisions — and **IT service desk (real, public)** — the proof it works
   on real data. Same five questions on both.
3. **Accept / Override become real.** Accepting a recommendation adds it to **"Your plan"**; the plan
   shows its **expected impact** on turnaround, productivity and service quality (the problem
   statement's three words). Food world: the simulator replays a day with and without the plan.
   Real world: estimated from held-out months (labelled as an estimate). Override removes it and
   records why. Ticket-level dispatch is automatic and only explained, not clicked.
4. **Six screens, each answering one question, in the problem statement's order:**
   | Screen | Question | Deliverable |
   |---|---|---|
   | Overview | What is happening? | 2 |
   | Problems | Why does it go wrong? (evidence + an LLM summary per card) | 2, "identify patterns" |
   | Risks | What will go wrong next? (at-risk tickets + next 48 h bottlenecks) | 2, "predict bottlenecks" |
   | Actions | What should we do, and what will it change? (plan + expected impact) | 3, "recommend", "measure impact" |
   | Proof | Does it beat today's methods? (comparison, replay, how we tested) | 4 |
   | Your data | Run it on your own export | 1 |
5. **Not now:** the mascot (only after the core works), new models, more baselines, the floor gauge
   (the owner mentions it only if asked).

## 4. What the real-data world will show (all computed in `make eval`, all on held-out months)
- **Problems:** evidence cards on the real log (e.g. categories that bounce between teams).
- **Risks:** incidents likely to miss their SLA, scored at opening time, with reasons
  (AUC 0.857 vs 0.552 for the priority field).
- **Actions:** "send this kind of incident straight to team Y" (routing at opening time), with the
  evidence; escalations for at-risk incidents.
- **Proof (baseline = what the real people did):** routed to the right team first time, OpsLens vs
  the desk; reassignments avoided; SLA misses caught early, OpsLens risk vs the priority field.
- **Honesty:** the final team is not always the "right" one (some hand-offs are by design), and
  "time saved" from fewer hand-offs is an association, not a proven cause. Said on screen.

## 5. Build order (each step leaves a working product)
1. Engine: real-data world (`eval/run_realdesk.py` → `results.realdesk`).
2. Engine + server: the plan and its expected impact (food: simulate; real: held-out estimate).
3. Dashboard: world switch, six screens, plan panel, plain words everywhere.
4. A plain-words guide for the owner; demo script and Q&A updated.
Code freeze: evening of 26 Oct. 27 Oct: rehearsal and backup video.

## 6. Done means
The owner can explain every screen in one sentence; every button does something; deliverable 1
works on public data without uploading anything; every number still comes from `results.json`.
