# ingest.py, adapters/uci_incidents.py, kpis.py, classify.py, clusters.py

## What they do
- `ingest.py` turns any ticket CSV into one clean table: checked row by row (pydantic), timing
  recomputed from timestamps (wait, resolution, breach), and each day labelled train /
  validation / test.
- `adapters/uci_incidents.py` turns the real ServiceNow event log (141,712 events) into one row
  per incident (24,918), plus "as of time t" features for the risk model.
- `kpis.py` is the single definition of every KPI table (volume, breach %, waits, transfers, reopens).
- `classify.py` decides each ticket's category: a cheap local model first, the LLM only when the
  local model is unsure.
- `clusters.py` finds sub-issues inside each category and lets the LLM name them.

## How the classifier works, step by step
1. Input = masked text + the customer's menu choice + channel + (menu choice × channel).
   Why the last one: the menu is right 95% of the time in chat but only 76% on the phone (IVR),
   so the model must learn *when* to trust it.
2. Features: word pieces (1–2 words) and character pieces (2–5 letters, good for typos and
   Hinglish spellings) → logistic regression.
3. Calibration: isotonic, 3-fold, on training days only. "0.6 confident" then means about 60% right.
4. Threshold: on validation days we tried 0.5 … 0.95 and took the best accuracy within a 15%
   LLM budget → **0.6**. Below it, tickets go to Gemini in batches of 25 (masked, cached).
5. The LLM answer is checked (known category, every id present). Missing answers are asked
   once more, then the local answer stays.

## Worked example (test days 43–56, 18,032 tickets)
| Method | Accuracy | Phone (IVR) tickets |
|---|---|---|
| Customer's menu choice (status quo) | 90.9% | 75.8% |
| Local model | 97.97% | 95.8% |
| Cascade (local + LLM below 0.6) | **98.08%** | 95.7% |
| LLM alone (400 random tickets) | 90.0% | — |

- Only **1.54%** of tickets go to the LLM → about **617 requests per million tickets**.
- The LLM fixed 57 local mistakes and broke 37 correct answers: **net +20**.
- What matters for operations: tickets sent to the wrong team per 100 fall from **5.71 to 1.20**
  (phone: **14.83 to 2.54**). The simulator (M7) turns that into fewer transfers.
- Honest lesson: the LLM alone is *worse* than the local model here, because it cannot learn how
  reliable the menu choice is per channel. It is useful as a second opinion on hard tickets.

## Clusters
TF-IDF + KMeans inside each category; k chosen by silhouette (here 6 everywhere). Gemini names
each group from 10 masked messages, e.g. payment failure → "UPI Payment Deduction Failure",
"Duplicate Order Charges", "Ghost Debit Payment Failures". Names containing digits are refused.

## Real data (UCI)
Breach rate rises with reassignments: 0 → 21.6%, 1 → 42.9%, 2 → 60.1%, 4+ → 81.0%. Ping-pong
between teams is costly in real operations too.

## Weaknesses
- Most message wording is synthetic (Bitext + templates + ~600 LLM-written patterns), so
  accuracy on real messages would be lower.
- Some cluster names repeat ("Incomplete Order Delivery" three times in missing items): KMeans
  split one topic by wording.
- Hinglish accuracy (97.3%) is a little below English.

## How to read the code
`classify.py`: `train_local()` → `predict_local()` → `classify_with_llm()` → `cascade()`.
The experiment is `eval/run_classification.py`. Ingest: `ingest()` at the bottom of `ingest.py`.
