# W6 — NLP and LLMs on a real benchmark (pre-registered design)

Plan v4, item W6. Owner: Claude 2. **This design was committed on 22 Oct 2026 before any of the
three tests below ran.** Results are reported whatever they are; anything changed after a run is
listed under "Amendments" with its reason.

Why: our 98% classifier accuracy is on partly templated text we generated ourselves, and the LLM
only saw 1.5% of tickets. A harsh NLP judge asks: "how good is it on real customer text that you
did not write, and does the LLM add anything?"

## (a) Banking77 — real customer banking queries

- **Data:** BANKING77 (Casanueva et al., 2020, *Efficient Intent Detection with Dual Sentence
  Encoders*, NLP4ConvAI; arXiv 2003.04807). 13,083 real online-banking customer queries, 77
  intents. Official split from github.com/PolyAI-LDN/task-specific-datasets (`banking_data/
  train.csv`, `test.csv`). **Licence: CC BY 4.0** (checked in that repository's LICENSE, 22 Oct).
  Downloaded by `scripts/download_banking77.py` into `data/public/banking77/` (not committed).
- **Models (no tuning on Banking77):**
  - *Local:* exactly the product's text features (word 1–2-grams + character 2–5-grams TF-IDF →
    logistic regression, C = 4, isotonic calibration, 3 folds). No menu/channel features (the
    benchmark has none). Hyperparameters are the product's; none are tuned here.
  - *Cascade:* local first; tickets with calibrated confidence below a threshold go to the LLM
    (the product's main provider, `gemini`, batches of 25, intent names as the label list,
    PII masking and cache as in production). LLM answers outside the 77 intents fall back to local.
  - *LLM only:* the same prompt on a fixed random sample of 400 test queries (seed 77).
- **Threshold:** chosen on a validation split, never on test: candidates 0.30, 0.40, …, 0.90;
  best validation accuracy with at most 30% of queries escalated (the product's rule; ties → the
  lower threshold). Validation = a stratified 20% of the official train set (seed 77); the local
  model used for the threshold is trained on the other 80%; the final local model is then refit on
  the whole training set and scored once on the official test set with that threshold.
- **Two settings:** *Full* (all 10,003 training queries) and *10-shot* (10 per intent, drawn with
  seed 77; the paper's low-data setting, where an LLM should help most). In 10-shot the threshold
  is chosen on 5 further queries per intent (385), which a few-shot user would also have to label —
  stated as a deviation from the paper, which reports no validation set.
- **Reported:** accuracy (with 95% bootstrap CI, 2,000 resamples of test queries) for local,
  cascade and LLM-only; share escalated; LLM requests and tokens per 1M tickets (tokens estimated
  as characters ÷ 4 of the prompts actually sent); cost per 1M tickets at the provider's list
  price on the run date (stated with its source); latency (local ms per query; LLM seconds per
  batch, median of uncached calls). Published results from the paper's Table 3 are shown next to
  ours: Full — BERT-fixed 87.19, BERT-tuned 93.66, USE 92.81, ConveRT 93.01, USE+ConveRT 93.36;
  10-shot — 67.55, 83.42, 84.23, 83.32, 85.19.
- **Rule:** "the LLM adds value" on Banking77 only in a setting where cascade − local accuracy
  on the test set has a paired 95% bootstrap CI that excludes 0 (above 0).

## (b) LLM root-cause attribution on evidence cards

- **Inputs:** every evidence card that matches a planted problem (matcher: `eval/recall.py`) — the
  main world's cards vs `data/planted.json`, and the 20 blind plant sets of `eval/run_blind.py`
  (cards rebuilt by `eval/llm_eval/make_cards.py`, which refuses to write unless every set
  reproduces the published found/diagnosed counts).
- **Blinding:** the LLM sees the card's evidence only — metric, value vs comparison, comparison
  text, segment, affected tickets and share, "not explained by", example tickets. It does NOT see
  the card's cause type, title or recommendation (all three are derived from the rule-based cause
  type), nor the planted truth. Honest limit: the metric itself (e.g. "transfers per 100 tickets",
  "work ÷ agent-time") is evidence and strongly hints at the type, so this tests whether the LLM
  reads the evidence correctly, not whether it discovers the problem.
- **Task:** pick one cause type (capacity, skill_gap, volume_spike, partner_issue, process,
  other — with the definitions used in `opslens/patterns.py`) and write a one-line root cause
  without digits (checked by code; numbers stay with the card).
- **Scored:** share of matched cards where the cause type equals the planted one — LLM vs our
  rule-based cause type, same cards, paired. The one-line root causes are reported for reading;
  they are not scored automatically.
- **Rule:** "the LLM beats the rules on attribution" only if LLM − rules accuracy has a paired 95%
  bootstrap CI above 0. (Before the run we note: the rules already diagnose every card they find
  in the blind sets, 57 of 57, so the LLM can at best tie here.)

## (c) Ask OpsLens routing accuracy

- **Questions:** `eval/llm_eval/route_questions.json` — 60 questions (40 English, 20 Hinglish)
  with the correct tool and arguments, committed with this file before either router ran. Caveat:
  written by Claude 2, who had read both routers' code.
- **Routers:** the LLM route used by the product (`groq_route` provider, same SYSTEM prompt and
  the same grounding check `check_route`); the offline keyword rules (`rules_route` + the same
  check). A route that fails the check counts as "none".
- **Scored:** tool accuracy and full accuracy (tool + labelled arguments), each with a 95% CI;
  paired difference LLM − rules on full accuracy; latency of uncached LLM calls.
- **Rule:** "the LLM beats the rules on routing" only if the paired difference in full accuracy
  has a 95% bootstrap CI above 0.

## Output
`eval/run_nlp_bench.py` → `eval/parts/nlp_bench.json`; `eval/run_llm_eval.py` →
`eval/parts/llm_eval.json`. Proposed for Claude 1 to merge: `results.nlp_bench`,
`results.llm_eval` (one step line each in `eval/run_eval.py`).

## Amendments
(none yet)
