from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.agents import embed
from opslens.classify import model_frame, train_local
from opslens.ingest import load_history
from opslens.privacy import mask_pii

OUT = ROOT / "docs" / "v2" / "results" / "rag_blend.json"
POOL_PER_CATEGORY = 2000
BATCH = 64
THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]
WEIGHTS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
KS = [5, 10, 20]


def vectors(texts: list[str], kind: str) -> np.ndarray:
    out = []
    for i in range(0, len(texts), BATCH):
        out += embed([f"{kind}: {mask_pii(str(t)).text}" for t in texts[i:i + BATCH]])
    m = np.asarray(out, dtype=np.float32)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


def neighbour_votes(query: np.ndarray, pool: np.ndarray, pool_labels: np.ndarray, classes: list[str], k: int) -> np.ndarray:
    sims = query @ pool.T
    top = np.argsort(-sims, axis=1)[:, :k]
    weight = np.clip(np.take_along_axis(sims, top, axis=1), 0, None)
    votes = np.zeros((len(query), len(classes)), dtype=np.float32)
    index = {c: i for i, c in enumerate(classes)}
    for row, (idx, w) in enumerate(zip(top, weight)):
        for j, s in zip(idx, w):
            votes[row, index[pool_labels[j]]] += s
    return votes / (votes.sum(axis=1, keepdims=True) + 1e-9)


def blended(proba: np.ndarray, votes: dict[int, np.ndarray], unsure: np.ndarray, k: int, w: float) -> np.ndarray:
    out = proba.copy()
    out[unsure] = (1 - w) * proba[unsure] + w * votes[k]
    return out


def main() -> int:
    started = time.perf_counter()
    h = load_history()
    train, val, test = (h[h["split"] == s].reset_index(drop=True) for s in ("train", "validation", "test"))
    model = train_local(train)
    classes = list(model.classes_)
    pool = train.groupby("final_category").sample(n=POOL_PER_CATEGORY, random_state=0).reset_index(drop=True)
    pool_m = vectors(pool["text"].tolist(), "search_document")
    pool_labels = pool["final_category"].astype(str).to_numpy()

    def prepare(df):
        proba = model.predict_proba(model_frame(df))
        truth = df["final_category"].astype(str).to_numpy()
        hard = proba.max(axis=1) < max(THRESHOLDS)
        q = vectors(df.loc[hard, "text"].tolist(), "search_query")
        votes = {k: neighbour_votes(q, pool_m, pool_labels, classes, k) for k in KS}
        return proba, truth, hard, votes

    def score(proba, truth, hard, votes, t, k, w):
        conf = proba.max(axis=1)
        unsure_all = conf < t
        sub = unsure_all[hard]
        p = proba.copy()
        idx = np.nonzero(hard)[0][sub]
        p[idx] = (1 - w) * proba[idx] + w * votes[k][sub]
        pred = np.asarray(classes)[p.argmax(axis=1)]
        base = np.asarray(classes)[proba.argmax(axis=1)]
        return {"accuracy": float((pred == truth).mean()), "changed": int(unsure_all.sum()),
                "fixed": int(((base != truth) & (pred == truth)).sum()), "broke": int(((base == truth) & (pred != truth)).sum())}

    v = prepare(val)
    grid = []
    for t in THRESHOLDS:
        for k in KS:
            for w in WEIGHTS:
                grid.append({"threshold": t, "k": k, "weight": w, **score(*v, t, k, w)})
    best = max(grid, key=lambda g: (g["accuracy"], -g["weight"], -g["threshold"]))
    base_val = float((np.asarray(classes)[v[0].argmax(axis=1)] == v[1]).mean())

    te = prepare(test)
    base_test = float((np.asarray(classes)[te[0].argmax(axis=1)] == te[1]).mean())
    chosen = score(*te, best["threshold"], best["k"], best["weight"])
    vote_only = score(*te, best["threshold"], best["k"], 1.0)
    out = {
        "how": "classifier probabilities blended with a similarity-weighted vote of the nearest past tickets, only where the classifier is unsure",
        "embedding_model": "nomic-embed-text", "pool": {"tickets": len(pool), "per_category": POOL_PER_CATEGORY, "from": "training days only"},
        "chosen_on_validation": {k: best[k] for k in ("threshold", "k", "weight")},
        "validation": {"tickets": int(len(val)), "classifier_alone": base_val, "with_retrieval": best["accuracy"],
                       "fixed": best["fixed"], "broke": best["broke"]},
        "test": {"tickets": int(len(test)), "classifier_alone": base_test, "with_retrieval": chosen["accuracy"],
                 "changed_tickets": chosen["changed"], "fixed": chosen["fixed"], "broke": chosen["broke"],
                 "net_tickets": chosen["fixed"] - chosen["broke"], "vote_only_same_settings": vote_only["accuracy"]},
        "grid_size": len(grid), "seconds": round(time.perf_counter() - started, 1),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
