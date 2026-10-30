from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.classify import cascade, classify_with_llm, predict_local, train_local
from opslens.config import load_config
from opslens.ingest import load_history
from opslens.llm.client import build_client

RECORDED = ROOT / "eval" / "parts" / "classification.json"
OUT = ROOT / "docs" / "v2" / "results" / "local_llm_classification.json"
LLM_SAMPLE = 400


def accuracy(pred, truth) -> float:
    return float((pred.to_numpy() == truth.to_numpy()).mean())


def main() -> int:
    provider = sys.argv[1] if len(sys.argv) > 1 else load_config("providers")["main"]
    recorded = json.loads(RECORDED.read_text(encoding="utf-8"))
    threshold = recorded["details"]["threshold"]
    h = load_history()
    train, test = (h[h["split"] == s].reset_index(drop=True) for s in ("train", "test"))
    model = train_local(train)
    local_test = predict_local(model, test)
    truth = test["final_category"].astype(str)
    client = build_client([provider])
    cfg = client.providers[0].config

    sample = test.sample(n=LLM_SAMPLE, random_state=0)
    started = time.perf_counter()
    labels = classify_with_llm(client, sample, task="local_eval_sample")
    sample_s = time.perf_counter() - started
    got = sample[sample["ticket_id"].isin(labels)]
    sample_acc = accuracy(got["ticket_id"].map(lambda t: labels[t].category), got["final_category"].astype(str))

    unsure = test[local_test["conf_local"] < threshold]
    started = time.perf_counter()
    llm_test = classify_with_llm(client, unsure, task="local_eval_cascade")
    cascade_s = time.perf_counter() - started
    final = cascade(local_test, llm_test, threshold)
    used = final["source"] == "llm"
    hinglish = (test["language"] == "hi").to_numpy()
    out = {
        "provider": cfg.name, "model": cfg.model, "threshold": threshold, "test_tickets": int(len(test)),
        "sample": {"tickets": LLM_SAMPLE, "answered": int(len(got)), "accuracy": sample_acc,
                   "recorded_cloud_accuracy": recorded["accuracy_llm_sample"], "seconds": round(sample_s, 1)},
        "cascade": {"sent_to_llm": int(len(unsure)), "answered": int(len(llm_test)),
                    "accuracy_local_only": accuracy(final["pred_local"], truth),
                    "accuracy_with_local_llm": accuracy(final["pred_final"], truth),
                    "recorded_cloud_accuracy": recorded["accuracy_cascade"],
                    "accuracy_with_local_llm_hinglish": accuracy(final["pred_final"][hinglish], truth[hinglish]),
                    "llm_fixed": int(((final["pred_local"] != truth) & (final["pred_final"] == truth) & used).sum()),
                    "llm_broke": int(((final["pred_local"] == truth) & (final["pred_final"] != truth) & used).sum()),
                    "seconds": round(cascade_s, 1)},
        "seconds_per_ticket": round((sample_s + cascade_s) / max(1, len(got) + len(llm_test)), 3),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
