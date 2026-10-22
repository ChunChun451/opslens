"""W6 (a): the classification cascade on BANKING77, real customer queries we did not write.

Run:  python eval/run_nlp_bench.py [--no-llm]
Needs: python scripts/download_banking77.py. Design (pre-registered): docs/explain/nlp_bench.md.

For each setting (Full, 10-shot):
1. Split: validation = stratified 20% of train (Full) or 5 more per intent (10-shot), seed 77.
2. Local model = the product's text features (word + char TF-IDF → logistic regression, isotonic)
   trained without the validation part; the LLM labels every validation query the local model is
   unsure about (conf < the highest candidate); the threshold is picked on validation with the
   product's rule (opslens.classify.choose_threshold, ≤ 30% escalated).
3. Refit the local model on the whole training part; score local and cascade ONCE on the test set.
Plus LLM-only on 400 random test queries (seed 77). Every LLM call goes through LLMClient (PII
masking, cache, rate limits), so a re-run costs nothing and gives the same answers.
Writes eval/parts/nlp_bench.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.classify import BATCH_SIZE, LLMLabel, cascade, choose_threshold  # noqa: E402
from opslens.llm.base import LLMUnavailable  # noqa: E402
from opslens.llm.client import build_client  # noqa: E402
from opslens.privacy import mask_pii  # noqa: E402

DATA = ROOT / "data" / "public" / "banking77"
SEED = 77
CANDIDATES = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
MAX_ESCALATED_PCT = 30.0
LLM_ONLY_SAMPLE = 400
BOOT = 2000
PROVIDER = "gemini"
RETRY_WAITS_S = [20, 40, 60, 120, 240, 300]
# Gemini 3.1 Flash-Lite paid "Standard" list price, ai.google.dev/gemini-api/docs/pricing, read 22 Oct 2026.
# The free tier (what we use) costs nothing; the paid price is what a company would pay at scale.
USD_PER_M_INPUT, USD_PER_M_OUTPUT = 0.25, 1.50
PUBLISHED = {  # Casanueva et al. 2020, Table 3, BANKING77 accuracy (%)
    "source": "Casanueva et al. (2020), Efficient Intent Detection with Dual Sentence Encoders, Table 3",
    "full": {"BERT-fixed": 87.19, "BERT-tuned": 93.66, "USE": 92.81, "ConveRT": 93.01, "USE+ConveRT": 93.36},
    "10-shot": {"BERT-fixed": 67.55, "BERT-tuned": 83.42, "USE": 84.23, "ConveRT": 83.32, "USE+ConveRT": 85.19},
}


# ---- Local model (the product's text features) -------------------------------------------------

def local_model() -> CalibratedClassifierCV:
    features = FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, token_pattern=r"(?u)\b\w+\b")),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True,
                                  max_features=150_000)),
    ])
    pipe = Pipeline([("features", features), ("clf", LogisticRegression(C=4.0, max_iter=3000))])
    return CalibratedClassifierCV(pipe, method="isotonic", cv=3)


def clean_text(texts: pd.Series) -> list[str]:
    return [mask_pii(str(t)).text.lower() for t in texts]


def fit_predict(train: pd.DataFrame, score: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Local predictions for `score` and the local latency in ms per query."""
    model = local_model().fit(clean_text(train["text"]), train["category"])
    started = time.perf_counter()
    proba = model.predict_proba(clean_text(score["text"]))
    ms = 1000.0 * (time.perf_counter() - started) / len(score)
    best = proba.argmax(axis=1)
    return pd.DataFrame({"ticket_id": score["ticket_id"].to_numpy(), "pred_local": model.classes_[best],
                         "conf_local": proba[np.arange(len(score)), best]}), ms


# ---- LLM tier ----------------------------------------------------------------------------------

def system_prompt(intents: list[str]) -> str:
    return ("You classify customer messages sent to an online bank's support chat into exactly one of these "
            "77 intents:\n" + ", ".join(intents) + "\nChoose the intent that best matches what the customer "
            "needs. Personal data may be masked as [PHONE], [EMAIL] etc.\n"
            'Reply with JSON only: {"results": [{"id": <message number>, "intent": <one intent from the list>}]} '
            "with exactly one entry per message.")


class LLMStats:
    def __init__(self) -> None:
        self.requests = 0
        self.uncached_latency_s: list[float] = []
        self.input_chars = 0
        self.output_chars = 0
        self.failed_batches = 0
        self.models: set[str] = set()


def llm_label(client, intents: list[str], df: pd.DataFrame, stats: LLMStats) -> dict[str, LLMLabel]:
    """{ticket_id: LLMLabel} for the rows of df; one retry for missing ids, as in the product."""
    system = system_prompt(intents)
    known = set(intents)
    labels: dict[str, LLMLabel] = {}
    rows = list(df[["ticket_id", "text"]].itertuples(index=False))
    for start in range(0, len(rows), BATCH_SIZE):
        pending = {k + 1: r for k, r in enumerate(rows[start:start + BATCH_SIZE])}
        for _ in range(2):
            if not pending:
                break
            user = "Messages:\n" + "\n".join(f"{i}. {r.text}" for i, r in pending.items())
            result = None
            for wait in RETRY_WAITS_S:  # "high demand" 503s pass; a batch that never gets an answer stays local
                try:
                    result = client.ask_json("bench_banking77", system, user)
                    break
                except LLMUnavailable as exc:
                    print(f"  LLM unavailable at batch {start} (retry in {wait}s): {str(exc)[:120]}", flush=True)
                    time.sleep(wait)
            if result is None:
                stats.failed_batches += 1
                break
            stats.requests += 1
            stats.input_chars += len(system) + len(user)
            stats.output_chars += len(result.raw_text)
            stats.models.add(result.model)
            if not result.from_cache:
                stats.uncached_latency_s.append(result.latency_s)
            items = result.data.get("results", []) if isinstance(result.data, dict) else []
            for item in items if isinstance(items, list) else []:
                try:
                    i = int(item.get("id"))
                except (TypeError, ValueError, AttributeError):
                    continue
                intent = str(item.get("intent", "")).strip().lower()
                if i in pending and intent in known:
                    labels[pending.pop(i).ticket_id] = LLMLabel(intent, "")
    return labels


# ---- Statistics --------------------------------------------------------------------------------

def ci(correct: np.ndarray, rng: np.random.Generator) -> dict:
    idx = rng.integers(0, len(correct), size=(BOOT, len(correct)))
    means = correct[idx].mean(axis=1) * 100
    return {"pct": round(100 * float(correct.mean()), 2), "ci95": [round(float(np.percentile(means, 2.5)), 2),
                                                                   round(float(np.percentile(means, 97.5)), 2)]}


def paired(a: np.ndarray, b: np.ndarray, rng: np.random.Generator) -> dict:
    """a − b in accuracy points, paired bootstrap over the same queries."""
    diff = a.astype(float) - b.astype(float)
    idx = rng.integers(0, len(diff), size=(BOOT, len(diff)))
    means = diff[idx].mean(axis=1) * 100
    lo, hi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    return {"diff_pts": round(100 * float(diff.mean()), 2), "ci95": [round(lo, 2), round(hi, 2)],
            "excludes_zero": bool(lo > 0 or hi < 0)}


# ---- One setting -------------------------------------------------------------------------------

def run_setting(name: str, train_all: pd.DataFrame, test: pd.DataFrame, intents: list[str], client,
                stats: LLMStats, rng_ci: np.random.Generator) -> dict:
    if name == "full":
        val_idx = (train_all.groupby("category", group_keys=False)
                   .apply(lambda g: g.sample(frac=0.2, random_state=SEED)).index)
        train = train_all.drop(index=val_idx)
        val = train_all.loc[val_idx]
    else:  # 10-shot: 10 per intent to learn, 5 more per intent to choose the threshold
        shuffled = train_all.sample(frac=1.0, random_state=SEED)
        ranks = shuffled.groupby("category").cumcount()
        train = shuffled[ranks < 10]
        val = shuffled[(ranks >= 10) & (ranks < 15)]
    print(f"[{name}] learn {len(train)}, validation {len(val)}, test {len(test)}", flush=True)

    # Threshold on validation.
    local_val, _ = fit_predict(train, val)
    # Only thresholds within the escalation budget can be chosen, so the LLM labels just the
    # queries below the highest such threshold (saves free quota; the choice is the same).
    conf_val = local_val["conf_local"].to_numpy()
    allowed = [t for t in CANDIDATES if 100.0 * (conf_val < t).mean() <= MAX_ESCALATED_PCT] or [min(CANDIDATES)]
    unsure_val = val[conf_val < max(allowed)]
    llm_val = llm_label(client, intents, unsure_val, stats) if client else {}
    threshold, table = choose_threshold(local_val, val["category"].reset_index(drop=True), llm_val,
                                        CANDIDATES, MAX_ESCALATED_PCT)
    if client is None:
        threshold = float("nan")
    print(f"[{name}] threshold {threshold} (validation)\n{table.to_string(index=False)}", flush=True)

    # Final: refit on all learning data (train + validation for Full; the 10 for 10-shot), test once.
    learn = train_all if name == "full" else train
    local_test, ms = fit_predict(learn, test)
    truth = test["category"].to_numpy()
    local_ok = local_test["pred_local"].to_numpy() == truth
    out = {"learn_queries": len(learn), "validation_queries": len(val), "test_queries": len(test),
           "local": {**ci(local_ok, rng_ci), "ms_per_query": round(ms, 3)},
           "threshold_table": table.round(4).to_dict(orient="records")}
    if client is None:
        return out
    unsure_test = test[local_test["conf_local"].to_numpy() < threshold]
    llm_test = llm_label(client, intents, unsure_test, stats)
    final = cascade(local_test, llm_test, threshold)
    cas_ok = final["pred_final"].to_numpy() == truth
    esc = local_test["conf_local"].to_numpy() < threshold
    llm_answered = final["source"].to_numpy() == "llm"
    out.update({
        "threshold": threshold,
        "escalated_pct": round(100 * float(esc.mean()), 2),
        "llm_answered_pct": round(100 * float(llm_answered.mean()), 2),
        "cascade": ci(cas_ok, rng_ci),
        "cascade_minus_local": paired(cas_ok, local_ok, rng_ci),
        "on_escalated": {  # the queries the local model was unsure about
            "n": int(esc.sum()),
            "local_pct": round(100 * float(local_ok[esc].mean()), 2) if esc.any() else None,
            "cascade_pct": round(100 * float(cas_ok[esc].mean()), 2) if esc.any() else None,
        },
    })
    out["rule_llm_adds_value"] = out["cascade_minus_local"]["excludes_zero"] and out["cascade_minus_local"]["diff_pts"] > 0
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    train_all = pd.read_csv(DATA / "train.csv")
    test = pd.read_csv(DATA / "test.csv")
    train_all["ticket_id"] = [f"tr{i}" for i in range(len(train_all))]
    test["ticket_id"] = [f"te{i}" for i in range(len(test))]
    intents = sorted(train_all["category"].unique())
    client = None if args.no_llm else build_client([PROVIDER])
    stats = LLMStats()
    rng_ci = np.random.default_rng(SEED)

    settings = {name: run_setting(name, train_all, test, intents, client, stats, rng_ci)
                for name in ("full", "10-shot")}

    llm_only = None
    if client is not None:
        sample = test.sample(n=LLM_ONLY_SAMPLE, random_state=SEED)
        labels = llm_label(client, intents, sample, stats)
        answered = sample["ticket_id"].map(lambda t: labels[t].category if t in labels else None)
        ok = answered.to_numpy() == sample["category"].to_numpy()
        llm_only = {"sample": LLM_ONLY_SAMPLE, "answered": int(answered.notna().sum()), **ci(ok, rng_ci),
                    "note": "zero-shot: intent names only, no training examples; unanswered counts as wrong"}

    llm = None
    if client is not None:
        tickets_seen = sum(s.get("on_escalated", {}).get("n", 0) for s in settings.values())
        per_request_in = stats.input_chars / 4 / max(stats.requests, 1)
        per_request_out = stats.output_chars / 4 / max(stats.requests, 1)
        cost = {}
        for name, s in settings.items():
            requests_per_m = s["escalated_pct"] / 100 * 1_000_000 / BATCH_SIZE
            usd = requests_per_m * (per_request_in * USD_PER_M_INPUT + per_request_out * USD_PER_M_OUTPUT) / 1e6
            cost[name] = {"llm_requests_per_m_tickets": round(requests_per_m),
                          "est_tokens_per_m_tickets": round(requests_per_m * (per_request_in + per_request_out)),
                          "usd_per_m_tickets_paid_tier": round(usd, 2)}
        llm = {"provider": PROVIDER, "models": sorted(stats.models), "requests": stats.requests,
               "failed_batches": stats.failed_batches, "test_queries_escalated": tickets_seen,
               "est_input_tokens_per_request": round(per_request_in), "est_output_tokens_per_request": round(per_request_out),
               "median_uncached_s_per_batch": round(float(np.median(stats.uncached_latency_s)), 2)
               if stats.uncached_latency_s else None,
               "price": {"usd_per_m_input": USD_PER_M_INPUT, "usd_per_m_output": USD_PER_M_OUTPUT,
                         "source": "ai.google.dev/gemini-api/docs/pricing, Gemini 3.1 Flash-Lite Standard, read 22 Oct 2026; "
                                   "we run on the free tier"},
               "cost": cost}

    out = {"dataset": {"name": "BANKING77", "licence": "CC BY 4.0", "train": len(train_all), "test": len(test),
                       "intents": len(intents), "source": "github.com/PolyAI-LDN/task-specific-datasets"},
           "settings": settings, "llm_only": llm_only, "llm": llm, "published": PUBLISHED,
           "no_llm": bool(args.no_llm), "seconds": round(time.perf_counter() - started, 1)}
    path = ROOT / "eval" / "parts" / "nlp_bench.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "published"}, indent=1)[:4000])
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
