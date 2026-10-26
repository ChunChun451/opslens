# OpsLens in plain words

Read this first. It explains what OpsLens is, what every screen does, what every button does,
and what to say. No jargon. (Numbers: `docs/NUMBERS.md`. Hard questions: `docs/JUDGE_QA.md`.)

## The one sentence
**A support team gets about 1,100 complaints a day and every complaint has a deadline. OpsLens
tells the team lead why deadlines are missed, which complaints will miss next, and what to do —
and shows what each action would change, tested on days and data it never saw.**

## Why it exists (the problem statement in one line)
Eternal asked for an engine that finds recurring problems, predicts bottlenecks, recommends how to
prioritise and share the work, explains why, and measures the impact — on a public dataset, with a
comparison against today's way of working.

## Two worlds, one engine (the switch at the top)
| | Food delivery (simulated) | IT service desk (real, public) |
|---|---|---|
| What it is | A support floor we built: 40 agents, 8 weeks of complaints, problems hidden on purpose | A real company's IT service desk (public UCI data): 24,918 incidents, 70 teams |
| Why we have it | We know the truth there, so we can replay decisions and prove they help | It is real, so nobody can say "you made it up" — deliverable 1 |
| What it proves | OpsLens's decisions beat today's methods on days it never saw | OpsLens's warnings and findings hold on real data |

Same screens in both. Food is the star; the real desk is the proof that it works outside our world.

## The six screens — each answers one question
1. **Overview — "What is happening?"**
   Food: Saturday night replayed twice — same agents, same complaints, only the decisions differ.
   Real: the size of the desk and where an incident's time goes.
2. **Problems — "Why does it go wrong?"**
   Each card is one recurring problem with proof: a number, a comparison, and example tickets.
   Food example: Hindi refunds wait 5× longer (only 3 agents can handle them, none at night).
   Real example: incidents that wait on the customer miss their deadline far more often.
3. **Risks — "What will go wrong next?"**
   The tickets most likely to miss their deadline, with the reasons, and the hours or days when a
   team will be short of people.
4. **Actions — "What should we do?"**
   Recommendations, each with its evidence and its measured effect alone (replayed on 14 days
   OpsLens never saw). "No clear effect" means the 95% range includes zero: we cannot tell.
   **Accept** adds it to *Your plan*. **Override** says no and records why. Who takes which ticket is decided
   automatically (nobody approves 1,100 tickets a day) — the screen only explains it.
5. **Proof — "Does it actually work?"**
   OpsLens against today's methods, on days or months it never learned from. Includes the replay,
   "try a what-if", and everything we tested — including what failed.
6. **Your own file — "Will it work on my company?"**
   In Real data, press **Upload a CSV** and drop any export of tickets, incidents or orders. OpsLens says in five
   sentences what it will do with it; press **Analyse my file**, and every real screen (Overview, Shadow mode,
   Problems, Risks, Actions, Proof) runs on that file. What the file does not have, the screen names.

## What every button does
| Button | What happens |
|---|---|
| Food delivery / Real data | Switches every screen to that world |
| UCI ServiceNow example / Your file (bar on top, Real data) | Which real data the screens show; × goes back to the example |
| Accept | The recommendation goes into *Your plan*, with its measured effect |
| Override → a reason | The recommendation is refused, and the reason is kept |
| Your plan | Opens the plan: what you accepted, what each changes, what you refused |
| Simulate (in Your plan, food world) | Pick a held-out day; it replays that day with your plan and without it, three times with different luck (about 20 s), and shows the difference under turnaround, productivity and service quality. Green or red only when all three agree |
| Any number | Shows where it comes from — every number on screen is computed, none typed in |
| Ask OpsLens (top bar) | Ask in plain words or Hinglish ("what if Team C loses 2 agents on Saturday?") — the engine answers |
| Story mode | A guided tour for the demo |
| Replay the night | Plays the Saturday opening again |

## What OpsLens is — in 4 parts (if a judge asks "how does it work?")
1. **It reads the complaints** and works out what each is about (also in Hinglish).
2. **It finds patterns** in the history: which kinds of complaints wait longest, and why.
3. **It predicts**: for every open complaint, the chance it misses its deadline, and the reasons.
4. **It decides and checks**: who should take which complaint now (the most at-risk first), and
   what bigger changes would help — then replays days it never saw to prove the decisions are better.

## What we do NOT claim (say it before they ask)
- The food-delivery data is generated (no company publishes its support data). That is why we
  added the real public service desk.
- On the real desk, OpsLens does not pick the right team better than the real people did, and its
  workload forecast is not better than "same day last week". We show this on the Proof screen.
- The effect of a process fix on the real desk is evidence, not a measured result — a log cannot
  replay what would have happened.
