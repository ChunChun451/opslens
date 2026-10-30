from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.agents import embed
from opslens.classify import CATEGORIES, CATEGORY_HELP, cascade, predict_local, train_local, LLMLabel
from opslens.config import load_config
from opslens.ingest import load_history
from opslens.llm.client import build_client
from opslens.privacy import mask_pii

RECORDED = ROOT / "eval" / "parts" / "classification.json"
LOCAL_RUN = ROOT / "docs" / "v2" / "results" / "local_llm_classification.json"
OUT = ROOT / "docs" / "v2" / "results" / "rag_classification.json"
POOL_PER_CATEGORY = 600
K = 5
LLM_SAMPLE = 400
BATCH = 64

SYSTEM = (
    "You classify customer-support tickets of an Indian food-delivery app.\n"
    "Categories:\n" + "\n".join(f"- {c}: {h}" for c, h in CATEGORY_HELP.items())
    + "\nTickets may be English or Hinglish (Hindi in Latin letters), have typos, or mention several issues: choose the MAIN "
    "issue the customer needs solved. The customer's menu choice is only a hint; for phone (IVR) tickets it is often wrong.\n"
    "You are shown the past tickets most similar to the new one, each with its correct category. They are strong evidence, "
    "but read the new ticket yourself: the most similar ticket is not always the same kind.\n"
    'Reply with JSON only: {"category": <one category>}'
)


def line(text: str, pick: str, channel: str) -> str:
    return f"\"{mask_pii(str(text)).text}\" (menu choice: {pick}; channel: {channel})"


def vectors(texts: list[str], kind: str) -> np.ndarray:
    out = []
    for i in range(0, len(texts), BATCH):
        out += embed([f"{kind}: {mask_pii(str(t)).text}" for t in texts[i:i + BATCH]])
    m = np.asarray(out, dtype=np.float32)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


def neighbours(query: np.ndarray, pool: np.ndarray, k: int = K) -> tuple[np.ndarray, np.ndarray]:
    sims = query @ pool.T
    top = np.argsort(-sims, axis=1)[:, :k]
    return top, np.take_along_axis(sims, top, axis=1)


def vote(cats: list[str], sims: np.ndarray) -> str:
    score: dict[str, float] = defaultdict(float)
    for c, s in zip(cats, sims):
        score[c] += float(s)
    return max(score, key=score.get)


def ask_with_examples(client, row, examples: list[tuple[str, str, str, str]]) -> str | None:
    shown = "\n".join(f"{i}. {line(t, p, ch)} -> {cat}" for i, (t, p, ch, cat) in enumerate(examples, 1))
    prompt = f"Similar past tickets:\n{shown}\n\nNew ticket: {line(row.text, row.selected_category, row.channel)}"
    try:
        data = client.ask_json("rag_classify", SYSTEM, prompt).data
    except Exception:
        return None
    category = str(data.get("category", "") if isinstance(data, dict) else "").strip().lower()
    return category if category in CATEGORIES else None


def accuracy(pred, truth) -> float:
    pred, truth = np.asarray(pred), np.asarray(truth)
    return float((pred == truth).mean()) if len(truth) else float("nan")


def main() -> int:
    started = time.perf_counter()
    recorded = json.loads(RECORDED.read_text(encoding="utf-8"))
    threshold = recorded["details"]["threshold"]
    local_run = json.loads(LOCAL_RUN.read_text(encoding="utf-8")) if LOCAL_RUN.exists() else {}
    h = load_history()
    train, test = (h[h["split"] == s].reset_index(drop=True) for s in ("train", "test"))
    model = train_local(train)
    local_test = predict_local(model, test)
    truth = test["final_category"].astype(str).to_numpy()

    pool = train.groupby("final_category").sample(n=POOL_PER_CATEGORY, random_state=0).reset_index(drop=True)
    pool_m = vectors(pool["text"].tolist(), "search_document")
    pool_rows = list(pool[["text", "selected_category", "channel", "final_category"]].itertuples(index=False, name=None))

    sample = test.sample(n=LLM_SAMPLE, random_state=0).reset_index(drop=True)
    unsure_mask = (local_test["conf_local"] < threshold).to_numpy()
    unsure = test[unsure_mask].reset_index(drop=True)
    client = build_client([load_config("providers")["main"]])
    cfg = client.providers[0].config

    def run(df) -> tuple[list, list]:
        top, sims = neighbours(vectors(df["text"].tolist(), "search_query"), pool_m)
        knn, llm = [], []
        for row, idx, sim in zip(df.itertuples(), top, sims):
            examples = [pool_rows[j] for j in idx]
            knn.append(vote([e[3] for e in examples], sim))
            llm.append(ask_with_examples(client, row, examples))
        return knn, llm

    s_knn, s_llm = run(sample)
    u_knn, u_llm = run(unsure)
    s_truth = sample["final_category"].astype(str).to_numpy()
    answered = [i for i, p in enumerate(s_llm) if p]

    def cascaded(preds: list) -> dict:
        labels = {tid: LLMLabel(p, "") for tid, p in zip(unsure["ticket_id"], preds) if p}
        final = cascade(local_test, labels, threshold)
        used = (final["source"] == "llm").to_numpy()
        local_ok = final["pred_local"].to_numpy() == truth
        final_ok = final["pred_final"].to_numpy() == truth
        return {"accuracy": accuracy(final["pred_final"], truth), "fixed": int((~local_ok & final_ok & used).sum()),
                "broke": int((local_ok & ~final_ok & used).sum()), "answered": int(used.sum())}

    out = {
        "model": cfg.model, "embedding_model": "nomic-embed-text", "examples_per_ticket": K,
        "example_pool": {"tickets": len(pool), "per_category": POOL_PER_CATEGORY, "from": "training days only"},
        "threshold": threshold, "test_tickets": int(len(test)),
        "sample": {"tickets": LLM_SAMPLE, "llm_alone_recorded": local_run.get("sample", {}).get("accuracy"),
                   "cloud_llm_recorded": recorded.get("accuracy_llm_sample"),
                   "nearest_tickets_vote": accuracy(s_knn, s_truth),
                   "llm_with_examples": accuracy([s_llm[i] for i in answered], s_truth[answered]),
                   "llm_with_examples_answered": len(answered)},
        "routing": {"hard_tickets": int(len(unsure)), "classifier_alone": accuracy(local_test["pred_local"], truth),
                    "llm_alone_recorded": local_run.get("cascade", {}).get("accuracy_with_local_llm"),
                    "llm_alone_fixed_recorded": local_run.get("cascade", {}).get("llm_fixed"),
                    "llm_alone_broke_recorded": local_run.get("cascade", {}).get("llm_broke"),
                    "nearest_tickets_vote": cascaded(u_knn), "llm_with_examples": cascaded(u_llm)},
        "seconds": round(time.perf_counter() - started, 1),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
