# W6 — NLP and LLMs on a real benchmark (pre-registered design)

## For the dashboard: exact shape (read this first)
`results.nlp_bench` = `{banking77: <eval/parts/nlp_bench.json>, routing: ..., attribution: ...}`:
```
banking77: {dataset: {name, licence, train, test, intents, source},
    settings: {full | 10-shot: {learn_queries, validation_queries, test_queries, threshold, escalated_pct,
        llm_answered_pct, local: {pct, ci95, ms_per_query}, cascade: {pct, ci95},
        cascade_minus_local: {diff_pts, ci95, excludes_zero}, on_escalated: {n, local_pct, cascade_pct},
        rule_llm_adds_value, threshold_table: [{threshold, escalated_pct, accuracy}]}},
    llm_only: {sample, answered, pct, ci95, note}, published: {source, full: {model: pct}, 10-shot: {...}},
    llm: {provider, models, requests, failed_batches, median_uncached_s_per_batch, price: {...},
          cost: {full | 10-shot: {llm_requests_per_m_tickets, est_tokens_per_m_tickets, usd_per_m_tickets_paid_tier}}}}
routing: {questions, all | english | hinglish: {rules_tool, rules_full, llm_tool, llm_full: {n, correct, pct, ci95},
          llm_minus_rules_full: {diff_pts, ci95, above_zero}}, models, median_uncached_latency_s,
          rule_llm_beats_rules, rows: [{id, lang, want, rules, rules_full, llm, llm_full, llm_args}]}
attribution: {cards, rules, llm: {n, correct, pct, ci95}, llm_minus_rules, rule_llm_beats_rules,
          replies_with_digits, unanswered, models, rows: [{world, plant, truth, rules, llm, root_cause}]}
```

## Results (22 Oct) — LLM adds value where it should, and not where it should not
**(a) BANKING77, official test set (3,080 real customer queries), Gemini 3.1 Flash-Lite**
| | local (product features) | cascade | cascade − local [95% CI] | sent to LLM | paid-tier cost / 1M tickets |
|---|---|---|---|---|---|
| Full (10,003 train) | 90.3% [89.3, 91.3] | **91.0%** [90.1, 92.0] | **+0.71 [+0.16, +1.27]** | 5.6% | $1.41 |
| 10-shot (770 train) | 68.5% [67.0, 70.2] | **78.7%** [77.2, 80.1] | **+10.1 [+8.9, +11.4]** | 25.4% | $6.42 |
- Rule passed in both settings. On the queries the local model was unsure about, the cascade lifts
  accuracy 45% → 58% (full) and 36% → 76% (10-shot).
- LLM alone (zero-shot, intent names only, 500 queries): 79.0% [75.4, 82.8] — below the local model
  with full data, and the cascade matches it in 10-shot while sending only a quarter of the traffic.
- Published (Table 3): Full 87.19 (BERT-fixed) … 93.66 (BERT-tuned); 10-shot 67.55 … 85.19. Our
  TF-IDF model beats frozen BERT in both settings; fine-tuned sentence encoders stay ahead, honestly.
- Speed: local 0.3 ms per query; LLM ~9.7 s per batch of 25 (free tier, outage day).
**(b) Root cause from evidence cards (62 cards: 5 main + 57 blind):** rules 62/62, LLM 61/62
  (−1.6 [−4.8, 0.0]) — no gain, as expected; 0 of 62 replies contained a digit. The LLM's value
  here is the readable one-line root cause, not the label.
**(c) Ask OpsLens routing (60 questions):** LLM 93.3% vs keyword rules 61.7% (+31.7 [+18.3, +45.0]);
  Hinglish 18/18 vs 7/18. Found and fixed a grounding bug ("Two agents", PR #12).

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
  - *LLM only:* the same prompt on a fixed random sample of 500 test queries (seed 77).
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

- **Questions:** `eval/llm_eval/route_questions.json` — 60 questions (42 English, 18 Hinglish)
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
1. 22 Oct, after (c) ran: the design said "40 English, 20 Hinglish"; the committed file has 42 and 18 (a counting slip in the text, not a change to the questions).
2. 22 Oct, before (a) ran with the LLM: Gemini answered 503 "high demand" for several minutes. A batch with no answer would silently stay local and bias (a) against the LLM, so the bench waits and retries (up to ~13 min per batch) and records any batch that still fails.
3. 22 Oct, before LLM-only ran: sample 400 → 500 queries, to match Claude 1's brief (issue #8),
   which I had not read when writing this design.
