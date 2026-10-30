from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from opslens import store
from opslens.config import PROJECT_ROOT, load_config
from opslens.privacy import mask_pii

RESULTS = PROJECT_ROOT / "eval" / "results.json"
NUMBERS = PROJECT_ROOT / "eval" / "NUMBERS.md"
DOCS = PROJECT_ROOT / "docs" / "v2" / "README.md"
README = PROJECT_ROOT / "README.md"
ANSWERS = PROJECT_ROOT / "server" / "answers.md"
EVAL_SET = "rag_eval"
EVAL_OUT = PROJECT_ROOT / "docs" / "v2" / "results" / "rag_retrieval.json"
TICKETS_PER_CATEGORY = 40
MAX_CHARS = 1400
EMBED_BATCH = 64
TOP_K = 5
MAX_TICKETS_SHOWN = 1
TICKET_WEIGHT = 0.9
VECTOR_WEIGHT = 0.65
MIN_MEANING = 0.58
MIN_WORDS = 0.15
NOT_COVERED = re.compile(r"(does not|doesn't|do not|don't) (cover|answer|say|mention)|not covered|no information|cannot answer|can't answer", re.I)
SOURCE_CHARS = 900
LABELS = {"policy": "Policy", "problem": "Recurring problem", "fix": "Measured fix", "results": "Results", "readme": "Overview",
          "docs": "How it works", "faq": "Prepared answer", "ticket": "Past ticket"}
CITE = re.compile(r"\[(\d+)\]")

_index: dict = {}
_lock = threading.Lock()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "part"


def change(x: float) -> str:
    return f"{abs(x):,.0f} {'fewer' if x < 0 else 'more'}"


def likely(low: float, high: float) -> str:
    if high < 0:
        return f"likely between {abs(high):,.0f} and {abs(low):,.0f} fewer"
    if low > 0:
        return f"likely between {low:,.0f} and {high:,.0f} more"
    return f"could be anywhere from {abs(low):,.0f} fewer to {high:,.0f} more, so no clear effect"


def sections(text: str, prefix: str, link: str | None) -> list[dict]:
    out, title, buf = [], "", []

    def flush():
        body = "\n".join(buf).strip()
        if title and body:
            parts = [body[i:i + MAX_CHARS] for i in range(0, len(body), MAX_CHARS)]
            for k, part in enumerate(parts):
                ref = f"{prefix}:{slug(title)}" + (f"-{k + 1}" if len(parts) > 1 else "")
                out.append({"source": prefix, "ref": ref, "title": title, "body": part, "link": link, "card": None})

    for line in text.splitlines():
        m = re.match(r"^#{2,3}\s+(.+)$", line)
        if m:
            flush()
            title, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    flush()
    seen: dict[str, int] = {}
    for c in out:
        seen[c["ref"]] = seen.get(c["ref"], 0) + 1
        if seen[c["ref"]] > 1:
            c["ref"] = f"{c['ref']}-{seen[c['ref']]}"
    return out


def policy_chunks() -> list[dict]:
    return [{"source": "policy", "ref": f"policy:{a['category']}", "title": f"{a['title']} policy",
             "body": " ".join(a["body"].split()), "link": None, "card": None} for a in load_config("kb")["articles"]]


def fix_line(item: dict) -> str:
    e = item["effect"]["breaches"]
    return (f"{item['title']}: {change(e['diff'])} missed promises over the 14 held-out days "
            f"({likely(e['ci_low'], e['ci_high'])})")


def plain(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2f}".rstrip("0").rstrip(".")


def problem_chunks(results: dict) -> list[dict]:
    items = results.get("plan", {}).get("items", [])
    out = []
    for c in results["patterns"]["cards"]:
        fixes = [fix_line(i) for i in items if i.get("card_id") == c["id"]]
        body = (f"{c['title']}. For this group the {c['metric']} is {plain(c['value'])}; for normal tickets it is "
                f"{plain(c['comparison_value'])}. It affects {c['affected_tickets']:,} tickets "
                f"({c['affected_share_pct']}% of all). Not explained by chance: {c.get('not_explained_by') or 'n/a'}. "
                f"What to do: {c.get('recommendation') or 'n/a'}."
                + (" Measured fix: " + "; ".join(fixes) + "." if fixes else ""))
        out.append({"source": "problem", "ref": f"problem:{c['id']}", "title": c["title"], "body": body,
                    "link": "#problems", "card": f"card-{c['id']}"})
    return out


def fix_chunks(results: dict) -> list[dict]:
    plan = results.get("plan", {})
    out = []
    for i in plan.get("items", []):
        rate = i["effect"]["breach_pct"]
        body = (f"{fix_line(i)}. The missed-promise rate goes from {rate['without']:.2f}% to {rate['with']:.2f}%. Owner: {i.get('owner')}. "
                f"When: {i.get('when')}. {i.get('action') or ''} Assumes: {'; '.join(i.get('assumptions', []))}.")
        out.append({"source": "fix", "ref": f"fix:{i['id']}", "title": i["title"], "body": " ".join(body.split()),
                    "link": "#actions", "card": None})
    a = plan.get("all_items", {}).get("effect")
    if a:
        out.append({"source": "fix", "ref": "fix:all", "title": f"All {len(plan['items'])} fixes together",
                    "body": (f"All {len(plan['items'])} measured fixes together: {change(a['breaches']['diff'])} missed promises over "
                             f"the 14 held-out days ({likely(a['breaches']['ci_low'], a['breaches']['ci_high'])}); "
                             f"the missed rate goes from {a['breach_pct']['without']:.2f}% to {a['breach_pct']['with']:.2f}%."),
                    "link": "#actions", "card": None})
    return out


def faq_chunks() -> list[dict]:
    from server.bot import parse_qa

    return [{"source": "faq", "ref": f"faq:{e['id']}", "title": e["question"], "body": " ".join(e["answer"].split())[:MAX_CHARS],
             "link": None, "card": None} for e in parse_qa(ANSWERS.read_text(encoding="utf-8"))]


def ticket_chunks() -> list[dict]:
    from opslens.ingest import load_history

    h = load_history()
    h = h[h["split"] == "train"]
    picked = h.groupby("final_category").sample(n=TICKETS_PER_CATEGORY, random_state=0)
    out = []
    for r in picked.itertuples():
        kept = "missed" if bool(r.breached) else "kept"
        body = (f"Customer wrote: \"{mask_pii(str(r.text)).text}\". It was a {str(r.final_category).replace('_', ' ')} ticket "
                f"({r.priority}, {r.language}, by {r.channel}), handled by team {r.resolved_by_team}; it waited "
                f"{float(r.wait_min):.0f} min and the promise was {kept}.")
        out.append({"source": "ticket", "ref": f"ticket:{r.ticket_id}", "title": f"{str(r.final_category).replace('_', ' ').capitalize()} ticket {r.ticket_id}",
                    "body": body, "link": None, "card": None})
    return out


def all_chunks() -> list[dict]:
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    return (policy_chunks() + problem_chunks(results) + fix_chunks(results)
            + sections(NUMBERS.read_text(encoding="utf-8"), "results", "#proof/results")
            + sections(README.read_text(encoding="utf-8"), "readme", "#proof/results")
            + sections(DOCS.read_text(encoding="utf-8"), "docs", None) + faq_chunks() + ticket_chunks())


def text_of(c: dict) -> str:
    return f"{c['title']}. {c['body']}"


def build() -> dict:
    from opslens.agents import embed

    store.migrate()
    chunks = all_chunks()
    started = time.perf_counter()
    vectors: list = []
    try:
        for i in range(0, len(chunks), EMBED_BATCH):
            vectors += embed([f"search_document: {text_of(c)}" for c in chunks[i:i + EMBED_BATCH]])
    except Exception:
        vectors = [None] * len(chunks)
    with store.connection() as conn:
        with conn.transaction():
            conn.execute("delete from rag_chunks")
            with conn.cursor() as cur:
                cur.executemany("insert into rag_chunks (source, ref, title, body, link, card, embedding) values "
                                "(%s, %s, %s, %s, %s, %s, %s)",
                                [(c["source"], c["ref"], c["title"], c["body"], c["link"], c["card"], v) for c, v in zip(chunks, vectors)])
    _index.clear()
    counts: dict[str, int] = {}
    for c in chunks:
        counts[c["source"]] = counts.get(c["source"], 0) + 1
    return {"chunks": len(chunks), "by_source": counts, "embedded": all(v is not None for v in vectors),
            "seconds": round(time.perf_counter() - started, 1)}


def index() -> dict | None:
    with _lock:
        with store.connection() as conn:
            stamp = conn.execute("select count(*) as n, max(built_at) as at from rag_chunks").fetchone()
            if not stamp["n"]:
                return None
            key = (stamp["n"], str(stamp["at"]))
            if _index.get("key") == key:
                return _index
            rows = conn.execute("select source, ref, title, body, link, card, embedding from rag_chunks order by id").fetchall()
        _index.clear()
        _index.update({"key": key, **make_index(rows)})
        return _index


def make_index(rows: list[dict]) -> dict:
    texts = [text_of(r) for r in rows]
    words = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"(?u)\b\w+\b").fit(texts)
    matrix = None
    if all(r.get("embedding") for r in rows):
        matrix = np.asarray([r["embedding"] for r in rows], dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    weights = np.asarray([TICKET_WEIGHT if r["source"] == "ticket" else 1.0 for r in rows], dtype=np.float32)
    return {"rows": rows, "words": words, "word_matrix": words.transform(texts), "matrix": matrix, "weights": weights}


def search(question: str, k: int = TOP_K, mode: str = "both") -> list[dict]:
    from opslens.agents import embed

    idx = index()
    if idx is None:
        build()
        idx = index()
    return search_in(idx, question, k, mode, embed)


def search_in(idx: dict, question: str, k: int, mode: str, embed) -> list[dict]:
    keyword = (idx["word_matrix"] @ idx["words"].transform([question]).T).toarray().ravel()
    vector = np.zeros(len(idx["rows"]), dtype=np.float32)
    used_vectors = False
    if idx["matrix"] is not None and mode != "words":
        try:
            q = np.asarray(embed([f"search_query: {question}"])[0], dtype=np.float32)
            vector = idx["matrix"] @ (q / (np.linalg.norm(q) + 1e-9))
            used_vectors = True
        except Exception:
            pass
    score = (vector if mode == "meaning" else VECTOR_WEIGHT * vector + (1 - VECTOR_WEIGHT) * keyword) if used_vectors else keyword
    score = score * idx["weights"]
    hits, tickets = [], 0
    for i in np.argsort(-score):
        r = idx["rows"][int(i)]
        if r["source"] == "ticket":
            if tickets >= MAX_TICKETS_SHOWN:
                continue
            tickets += 1
        hits.append({**{key: r[key] for key in ("source", "ref", "title", "body", "link", "card")},
                     "label": LABELS.get(r["source"], r["source"]), "score": round(float(score[i]), 3),
                     "meaning": round(float(vector[i]), 3), "words": round(float(keyword[i]), 3), "how": "meaning and words" if used_vectors else "words only"})
        if len(hits) >= k:
            break
    return hits


def on_topic(hits: list[dict]) -> bool:
    if hits[0]["how"] == "meaning and words":
        return max(h["meaning"] for h in hits) >= MIN_MEANING
    return max(h["words"] for h in hits) >= MIN_WORDS


SYSTEM = (
    "You are OpsLens AI, the assistant inside OpsLens, a support-operations decision engine for a food delivery app. "
    "In OpsLens a promise is the time by which a customer must be helped; 'missed' or 'breached' means that time passed, so lower is "
    "better. Held-out days are test days the system never saw while it was built. "
    "Answer the question using only the numbered sources and add nothing they do not say. After each sentence, cite the sources it comes "
    "from, like [1] or [2][3]. "
    "Copy every number exactly as the source writes it, and keep each number with the words the source puts next to it: if the source "
    "says '13.0 times longer' or '131 fewer', never move 'longer' or 'fewer' onto a different number. If two sources give different "
    "numbers for the same thing, use the Measured fix, Results or Recurring problem source, not the Prepared answer. If the sources do not "
    "answer the question, say plainly that OpsLens's data does not cover it. Reply with one JSON object: "
    '{"answer": "2 to 4 sentences with citations", "used": [the source numbers you used]}'
)


RELATION = r"longer|more|fewer|less|higher|lower|shorter|faster|slower|better|worse"
PAIR = re.compile(r"(\d+(?:\.\d+)?)\s*(?:times|%|percent|points?|minutes?|mins?|hours?|days?|tickets?|missed promises?)?\s*(" + RELATION + r")\b", re.I)


def relations(text: str) -> set[tuple[float, str]]:
    flat = CITE.sub(" ", text.replace(",", "")).replace("×", " times ")
    return {(float(n), r.lower()) for n, r in PAIR.findall(flat)}


def numbers(text: str) -> list[str]:
    return [n.rstrip(".") for n in re.findall(r"\d+(?:\.\d+)?", CITE.sub(" ", text).replace(",", ""))]


def answer(question: str, client=None, find=None) -> dict | None:
    from opslens.llm.client import build_client

    started = time.perf_counter()
    try:
        hits = (find or search)(question)
    except Exception:
        return None
    if not hits or not on_topic(hits):
        return None
    sources = "\n\n".join(f"[{n}] ({h['label']}: {h['title']}) {h['body'][:SOURCE_CHARS]}" for n, h in enumerate(hits, 1))
    allowed = set(numbers(sources.replace(",", ""))) | set(numbers(question))
    said = relations(sources)
    try:
        client = client or build_client([load_config("providers")["main"]])
    except Exception:
        return None
    prompt = f"Sources:\n{sources}\n\nQuestion: {question}"
    text, used, unverified, unsupported = "", [], [], []
    for attempt in range(2):
        try:
            reply = client.ask_json("rag_answer", SYSTEM, prompt).data
        except Exception:
            return None
        reply = reply if isinstance(reply, dict) else {}
        text = str(reply.get("answer") or "").strip()
        used = sorted({int(n) for n in reply.get("used") or [] if str(n).isdigit() and 1 <= int(n) <= len(hits)}
                      | {int(n) for n in CITE.findall(text) if 1 <= int(n) <= len(hits)})
        unverified = [n for n in numbers(text) if n not in allowed]
        unsupported = [f"{n:g} {r}" for n, r in sorted(relations(text) - said)]
        if text and not unverified and not unsupported:
            break
        if unverified:
            prompt += (f"\n\nYour last answer used numbers that are not in the sources: {', '.join(unverified)}. "
                       "Answer again and copy numbers only from the sources.")
        if unsupported:
            prompt += (f"\n\nYour last answer said {', '.join(repr(u) for u in unsupported)}, but the sources never put that "
                       "number and that word together. Answer again and use each number with the words the source gives it.")
    if not text or NOT_COVERED.search(text):
        return None
    if used and not CITE.search(text):
        text += " " + "".join(f"[{n}]" for n in used)
    for n, h in enumerate(hits, 1):
        h["n"] = n
        h["used"] = n in used
        h["body"] = h["body"][:SOURCE_CHARS]
    cfg = client.providers[0].config
    return {"kind": "rag", "question": question, "answer": text, "sources": hits, "checked": not unverified and not unsupported,
            "unverified": unverified, "unsupported": unsupported, "model": cfg.model, "seconds": round(time.perf_counter() - started, 1),
            "how": hits[0]["how"]}


def scores(ranks: list) -> dict:
    n = len(ranks)
    return {"hit_at_1": round(sum(1 for r in ranks if r == 1) / n, 3), "hit_at_3": round(sum(1 for r in ranks if r and r <= 3) / n, 3),
            "hit_at_5": round(sum(1 for r in ranks if r and r <= 5) / n, 3), "mrr": round(sum(1 / r for r in ranks if r) / n, 3)}


def evaluate() -> dict:
    cases = load_config(EVAL_SET)["questions"]
    modes: dict[str, list] = {"both": [], "meaning": [], "words": []}
    rows = []
    for case in cases:
        want = case["expect"] if isinstance(case["expect"], list) else [case["expect"]]
        for mode in modes:
            refs = [h["ref"] for h in search(case["question"], k=10, mode=mode)]
            rank = next((i + 1 for i, r in enumerate(refs) if any(r == w or r.startswith(w + "-") for w in want)), None)
            modes[mode].append(rank)
            if mode == "both":
                rows.append({"question": case["question"], "expect": want, "rank": rank, "top3": refs[:3]})
    out = {"questions": len(cases), **scores(modes["both"]), "modes": {m: scores(r) for m, r in modes.items()}, "cases": rows}
    EVAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    EVAL_OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def faithfulness(label: str) -> dict:
    cases = load_config("rag_faithful")["questions"]
    rows = []
    for case in cases:
        out = answer(case["question"])
        text = out["answer"] if out else ""
        missing = [m for m in case["must"] if not re.search(m, text)]
        broke = [n for n in case["never"] if re.search(n, text)]
        verdict = "declined" if not out else "right" if not missing and not broke else "wrong"
        rows.append({"question": case["question"], "verdict": verdict, "missing": missing, "forbidden_found": broke,
                     "flagged": bool(out and not out["checked"]), "answer": text})
    n = len(rows)
    count = lambda v: sum(1 for r in rows if r["verdict"] == v)
    result = {"label": label, "questions": n, "right": count("right"), "wrong": count("wrong"), "declined": count("declined"),
              "right_pct": round(count("right") / n, 3), "cases": rows}
    path = EVAL_OUT.with_name(f"rag_faithfulness_{label}.json")
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def status() -> dict:
    with store.connection() as conn:
        by = conn.execute("select source, count(*) as n, count(embedding) as embedded, max(built_at) as at "
                          "from rag_chunks group by source order by source").fetchall()
    return {"sources": [{**r, "at": str(r["at"]), "label": LABELS.get(r["source"], r["source"])} for r in by],
            "chunks": sum(r["n"] for r in by)}


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    if command == "build":
        print(json.dumps(build(), indent=1))
    elif command == "eval":
        out = evaluate()
        print(json.dumps({k: v for k, v in out.items() if k != "cases"}, indent=1))
        for c in out["cases"]:
            print(f"{c['rank'] or '-':>3}  {c['question'][:70]:70s}  {c['top3']}")
    elif command == "faith":
        out = faithfulness(sys.argv[2] if len(sys.argv) > 2 else "after")
        print(json.dumps({k: v for k, v in out.items() if k != "cases"}, indent=1))
        for c in out["cases"]:
            print(f"{c['verdict']:9s} {c['question'][:62]:62s} missing={c['missing']} forbidden={c['forbidden_found']}")
            if c["verdict"] != "right":
                print("          ", c["answer"][:220])
    elif command == "ask":
        print(json.dumps(answer(" ".join(sys.argv[2:])), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
