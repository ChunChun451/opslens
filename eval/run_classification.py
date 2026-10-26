from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.classify import (
    BATCH_SIZE, CATEGORIES, cascade, choose_threshold, classify_with_llm, misrouted_per_100, predict_local,
    train_local,
)
from opslens.clusters import assign, fit_category, name_clusters
from opslens.ingest import load_history
from opslens.llm.client import build_client

PARTS = ROOT / "eval" / "parts"
PRED_PATH = ROOT / "data" / "generated" / "predictions.csv"
THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95]
MAX_ESCALATED_PCT = 15.0
LLM_SAMPLE = 400


def accuracy(pred: pd.Series, truth: pd.Series) -> float:
    return float((pred.to_numpy() == truth.to_numpy()).mean())


def main() -> int:
    use_llm = "--no-llm" not in sys.argv
    started = time.perf_counter()
    h = load_history()
    train, val, test = (h[h["split"] == s].reset_index(drop=True) for s in ("train", "validation", "test"))

    t0 = time.perf_counter()
    model = train_local(train)
    print(f"local model trained on {len(train):,} tickets in {time.perf_counter() - t0:.0f}s")
    local_val, local_test = predict_local(model, val), predict_local(model, test)
    local_all = predict_local(model, h)

    client = build_client() if use_llm else None
    llm_val: dict = {}
    llm_test: dict = {}
    threshold = 0.0
    if client is not None:
        unsure_val = val[local_val["conf_local"] < max(THRESHOLDS)]
        print(f"validation: {len(unsure_val):,} tickets below {max(THRESHOLDS)} -> LLM "
              f"({int(np.ceil(len(unsure_val) / BATCH_SIZE))} requests)")
        llm_val = classify_with_llm(client, unsure_val, task="classify")
        threshold, table = choose_threshold(local_val, val["final_category"], llm_val, THRESHOLDS, MAX_ESCALATED_PCT)
        print("threshold search on validation days:\n" + table.round(4).to_string(index=False))
        unsure_test = test[local_test["conf_local"] < threshold]
        print(f"test: {len(unsure_test):,} tickets below {threshold} -> LLM")
        llm_test = classify_with_llm(client, unsure_test, task="classify")

    final_test = cascade(local_test, llm_test, threshold)
    truth = test["final_category"].astype(str)
    calls = (test["channel"] == "call").to_numpy()
    hinglish = (test["language"] == "hi").to_numpy()
    escalated = final_test["conf_local"] < threshold
    llm_used = final_test["source"] == "llm"
    fixed = int(((final_test["pred_local"] != truth) & (final_test["pred_final"] == truth) & llm_used).sum())
    broke = int(((final_test["pred_local"] == truth) & (final_test["pred_final"] != truth) & llm_used).sum())

    results = {
        "menu_choice_accuracy": accuracy(test["selected_category"].astype(str), truth),
        "accuracy_local": accuracy(final_test["pred_local"], truth),
        "accuracy_cascade": accuracy(final_test["pred_final"], truth),
        "accuracy_local_calls": accuracy(final_test["pred_local"][calls], truth[calls]),
        "accuracy_cascade_calls": accuracy(final_test["pred_final"][calls], truth[calls]),
        "menu_choice_accuracy_calls": accuracy(test["selected_category"].astype(str)[calls], truth[calls]),
        "accuracy_cascade_hinglish": accuracy(final_test["pred_final"][hinglish], truth[hinglish]),
        "threshold": threshold,
        "pct_sent_to_llm": 100.0 * float(escalated.mean()),
        "llm_fixed": fixed,
        "llm_broke": broke,
        "misrouted_per_100_menu": misrouted_per_100(test["selected_category"].astype(str), truth),
        "misrouted_per_100_opslens": misrouted_per_100(final_test["pred_final"], truth),
        "misrouted_per_100_menu_calls": misrouted_per_100(test["selected_category"].astype(str)[calls], truth[calls]),
        "misrouted_per_100_opslens_calls": misrouted_per_100(final_test["pred_final"][calls], truth[calls]),
        "llm_requests_per_million_tickets": float(escalated.mean()) * 1_000_000 / BATCH_SIZE,
        "test_tickets": int(len(test)),
    }
    if client is not None:
        sample = test.sample(n=LLM_SAMPLE, random_state=0)
        llm_sample = classify_with_llm(client, sample, task="classify_sample")
        got = sample[sample["ticket_id"].isin(llm_sample)]
        results["accuracy_llm_sample"] = accuracy(
            got["ticket_id"].map(lambda t: llm_sample[t].category), got["final_category"].astype(str))
        results["llm_sample_answered"] = int(len(got))

    for key, value in results.items():
        print(f"{key:36s} {value:.4f}" if isinstance(value, float) else f"{key:36s} {value}")

    final_val = cascade(local_val, llm_val, threshold)
    preds = local_all.set_index("ticket_id")
    preds["pred_final"] = preds["pred_local"]
    preds["source"] = "local"
    preds["root_cause"] = ""
    for part in (final_val, final_test):
        p = part.set_index("ticket_id")
        preds.loc[p.index, ["pred_final", "source", "root_cause"]] = p[["pred_final", "source", "root_cause"]]

    known = h[h["split"] != "test"]
    category_for = preds["pred_final"].reindex(h["ticket_id"]).to_numpy()
    category_for = np.where(h["split"] != "test", h["final_category"], category_for)
    preds["cluster"] = -1
    preds["cluster_name"] = ""
    clusters_out = []
    for category in CATEGORIES:
        fitted = fit_category(category, known.loc[known["final_category"] == category, "text"])
        name_clusters(client, fitted)
        rows = h[category_for == category]
        labels = assign(fitted, rows["text"])
        preds.loc[rows["ticket_id"], "cluster"] = labels
        preds.loc[rows["ticket_id"], "cluster_name"] = [fitted.names[c] for c in labels]
        for c in sorted(fitted.names):
            clusters_out.append({"category": category, "name": fitted.names[c], "root_cause": fitted.root_causes[c],
                                 "size": fitted.sizes[c], "examples": fitted.examples[c][:3]})
        print(f"{category:20s} k={len(fitted.names)}: " + " | ".join(fitted.names[c] for c in sorted(fitted.names)))
    preds.reset_index().to_csv(PRED_PATH, index=False)

    confusion = pd.crosstab(truth, final_test["pred_final"].to_numpy())
    PARTS.mkdir(parents=True, exist_ok=True)
    part = {
        "accuracy_local": results["accuracy_local"],
        "accuracy_cascade": results["accuracy_cascade"],
        "accuracy_llm_sample": results.get("accuracy_llm_sample"),
        "pct_sent_to_llm": results["pct_sent_to_llm"],
        "transfers_avoided_per_100": results["misrouted_per_100_menu"] - results["misrouted_per_100_opslens"],
        "confusion": {str(r): {str(c): int(v) for c, v in row.items()} for r, row in confusion.iterrows()},
        "clusters": clusters_out,
        "details": results,
    }
    (PARTS / "classification.json").write_text(json.dumps(part, indent=1), encoding="utf-8")
    print(f"wrote {PRED_PATH.relative_to(ROOT)} and eval/parts/classification.json "
          f"({time.perf_counter() - started:.0f}s total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
