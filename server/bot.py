from __future__ import annotations

import pickle
import re
import threading
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
QA_FILES = [ROOT / "server" / "answers.md"]
TICKETS = ROOT / "data" / "generated" / "world_tickets.csv"
TRIAGE_FILE = ROOT / "data" / "generated" / "models" / "bot_triage.pkl"
TRAIN_LAST_DAY = 35

QA_MIN_SCORE = 0.22
RERANK_K = 8

CATEGORY_LABEL = {
    "late_delivery": "Late delivery", "refund": "Refund", "payment_failure": "Payment failure",
    "missing_item": "Missing item", "wrong_item": "Wrong item", "account": "Account",
    "app_bug": "App bug", "restaurant_partner": "Restaurant / food quality",
}
TEAM_OF = {"late_delivery": "A", "refund": "B", "payment_failure": "B", "missing_item": "C",
           "wrong_item": "C", "account": "D", "app_bug": "D", "restaurant_partner": "D"}
TEAM_NAME = {"A": "Live orders", "B": "Payments & refunds", "C": "Order accuracy",
             "D": "Account, app bugs & restaurant partners"}
LANGUAGE_LABEL = {"en": "English", "hi": "Hindi / Hinglish", "other": "a regional language"}

HINGLISH = {"kyun": "why", "kyu": "why", "kaise": "how", "kya": "what", "kitna": "how much", "kitne": "how many",
            "galat": "wrong", "sahi": "right", "sach": "true", "nakli": "fake synthetic", "asli": "real",
            "bharosa": "trust", "bhrosa": "trust", "jaldi": "fast", "der": "late", "kaam": "work",
            "tum": "you", "aap": "you", "apna": "your", "data": "data"}

CUSTOMER = re.compile(
    r"\b(my|mera|meri|mere|mujhe|maine|humne|hamara|i ordered|i paid|i got|i received|order|khana|paisa|paise|"
    r"refund|deducted|debited|kat gaya|kata|nahi aaya|nahi mila|delivery boy|rider|restaurant|biryani|dosa|pizza|"
    r"burger|food|cold|stale|missing|wrong item|late|cancel|cancelled|app crash|crashing|otp|login)\b", re.I)
ABOUT_US = re.compile(
    r"\b(opslens|your (model|system|simulator|data|team|results?)|you (use|tested|trained|built)|how do(es)? (it|you)|"
    r"why (do|does|did|should|is|are) (you|it|opslens)|leak|baseline|judge|jury|auc|ci\b|confidence interval|"
    r"simulator|pre-?regist|ledger|sealed|held-?out|test days?|overfit|tuned?|llm|gemini|groq|privacy|pii)\b", re.I)
ENGINE = re.compile(
    r"(\bt\d{6}\b|\bwhat (if|happens if|happens when)\b.*\b(agents?|team [a-d]|volume|staff|people|monday|tuesday|"
    r"wednesday|thursday|friday|saturday|sunday|weekend)\b|\bplant (a|an)\b|\bhide a\b|\bfix first\b|\bagents? (on|at|for)\b|"
    r"\bteam [a-d]\b.*\b(lose|loses|gain|add|minus|plus)\b|\bvolume\b.*%|%.*\bvolume\b)", re.I)

EXPAND = {
    "explain": "explain reasons why shap", "explanation": "explain reasons why shap", "interpret": "explain reasons shap",
    "scale": "scale speed million large tickets", "millions": "scale million speed", "fast": "speed seconds",
    "rupees": "money cost rupee impact", "money": "money cost rupee impact", "roi": "money cost impact",
    "business": "impact cost", "tune": "tuned tuning test days validation", "tuned": "tuned tuning test days validation",
    "trust": "trust believe", "simulator": "simulator simulation", "simulation": "simulator simulation",
    "leakage": "leakage leak future", "leak": "leakage leak future", "fake": "synthetic generated fake",
    "synthetic": "synthetic generated fake", "llm": "llm gemini groq ai", "down": "outage fails unavailable free tier",
    "privacy": "privacy pii mask", "zendesk": "helpdesk industry standard", "freshdesk": "helpdesk industry standard",
    "competitor": "helpdesk industry standard", "accuracy": "accuracy classifier", "overfit": "overfit tuned test",
}


def parse_qa(text: str) -> list[dict]:
    entries: list[dict] = []
    section = ""
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        head = re.match(r"^\*\*([QB]\d+[a-z]?)\.\s*(.+?)\*\*\s*$", line.strip())
        if head:
            if current:
                entries.append(current)
            question = head.group(2).strip()
            attack = question.lower().startswith("(attack)")
            question = re.sub(r"^\(attack\)\s*", "", question, flags=re.I)
            current = {"id": head.group(1), "section": section, "question": question, "attack": attack, "answer": []}
            continue
        if current is None:
            continue
        if line.startswith("---") or line.startswith("## "):
            entries.append(current)
            current = None
            continue
        current["answer"].append(line)
    if current:
        entries.append(current)
    for e in entries:
        e["answer"] = "\n".join(e["answer"]).strip()
    return [e for e in entries if e["answer"]]


def normalise(text: str) -> str:
    words = re.findall(r"[\w%.-]+", text.lower())
    return " ".join(HINGLISH.get(w, w) for w in words)


class QAIndex:
    def __init__(self, entries: list[dict]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.entries = entries
        questions = [normalise(e["question"]) for e in entries]
        answers = [normalise(e["answer"]) for e in entries]
        self.q_words = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True).fit(questions + answers)
        self.q_chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit(questions)
        self.q_word_m = self.q_words.transform(questions)
        self.q_char_m = self.q_chars.transform(questions)
        self.a_word_m = self.q_words.transform(answers)

    def search(self, question: str, k: int = 4) -> list[tuple[float, dict]]:
        q = normalise(question)
        q = q + " " + " ".join(EXPAND[w] for w in q.split() if w in EXPAND)
        score = (0.45 * (self.q_word_m @ self.q_words.transform([q]).T).toarray().ravel()
                 + 0.35 * (self.q_char_m @ self.q_chars.transform([q]).T).toarray().ravel()
                 + 0.20 * (self.a_word_m @ self.q_words.transform([q]).T).toarray().ravel())
        best = score.argsort()[::-1][:k]
        return [(float(score[i]), self.entries[i]) for i in best]


_QA: dict = {}


def qa_index() -> QAIndex:
    files = [f for f in QA_FILES if f.exists()]
    mtime = tuple(f.stat().st_mtime for f in files)
    if _QA.get("mtime") != mtime:
        entries = [e for f in files for e in parse_qa(f.read_text(encoding="utf-8"))]
        _QA.update({"mtime": mtime, "index": QAIndex(entries)})
    return _QA["index"]


_TRIAGE: dict = {}
_TRIAGE_LOCK = threading.Lock()


def _train_triage() -> dict:
    import pandas as pd
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    from opslens.privacy import mask_pii

    df = pd.read_csv(TICKETS, usecols=["day", "category", "language", "text"])
    train = df[df["day"] <= TRAIN_LAST_DAY]
    text = train["text"].fillna("").map(lambda t: mask_pii(str(t)).text.lower())

    def model() -> Pipeline:
        return Pipeline([
            ("features", FeatureUnion([
                ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, token_pattern=r"(?u)\b\w+\b")),
                ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True,
                                          max_features=150_000)),
            ])),
            ("clf", LogisticRegression(C=4.0, max_iter=3000)),
        ])

    return {"category": model().fit(text, train["category"]), "language": model().fit(text, train["language"])}


def triage_models(wait: bool = True) -> dict | None:
    if _TRIAGE:
        return _TRIAGE
    if TRIAGE_FILE.exists():
        _TRIAGE.update(pickle.loads(TRIAGE_FILE.read_bytes()))
        return _TRIAGE
    if not wait and _TRIAGE_LOCK.locked():
        return None
    with _TRIAGE_LOCK:
        if not _TRIAGE:
            models = _train_triage()
            TRIAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            TRIAGE_FILE.write_bytes(pickle.dumps(models))
            _TRIAGE.update(models)
    return _TRIAGE


def warm_up() -> None:
    threading.Thread(target=triage_models, daemon=True).start()


def triage(message: str, results: dict) -> dict:
    from opslens.privacy import mask_pii

    models = triage_models()
    text = mask_pii(message).text.lower()
    proba = models["category"].predict_proba([text])[0]
    classes = list(models["category"].classes_)
    best = int(proba.argmax())
    category = classes[best]
    language = str(models["language"].predict([text])[0])
    team = TEAM_OF.get(category, "D")
    out = {
        "kind": "triage",
        "category": category, "category_label": CATEGORY_LABEL.get(category, category),
        "confidence": round(float(proba[best]), 3),
        "language": language, "language_label": LANGUAGE_LABEL.get(language, language),
        "team": team, "team_name": TEAM_NAME[team],
        "steps": [
            f"Read from the text, not the menu the customer clicked: {CATEGORY_LABEL.get(category, category).lower()}.",
            f"Routed to Team {team} ({TEAM_NAME[team]}), to an agent who handles {CATEGORY_LABEL.get(category, category).lower()}"
            + (" and speaks Hindi." if language == "hi" else "."),
            "Its risk of missing the promise is re-scored every few minutes; if it climbs, OpsLens moves it up "
            "or rescues it with a cross-skilled agent before the deadline.",
        ],
        "masked": mask_pii(message).text != message,
    }
    cards = (results.get("patterns") or {}).get("cards") or []
    for c in cards:
        if (c.get("segment") or {}).get("category") == category:
            out["evidence"] = {"id": c["id"], "title": c["title"], "recommendation": c.get("recommendation", "")}
            break
    return out


FIRST_PERSON = re.compile(
    r"\b(my|mera|meri|mere|mujhe|maine|humne|hamara|hamare|i|i'm|i've|me|we|our|de diya|diya gaya|nahi aaya|nahi mila|"
    r"kat gaya|kab aayega|abhi tak|bhej diya|galat)\b", re.I)


def looks_like_customer(q: str) -> bool:
    if re.match(r"^\s*(customer|complaint|ticket)\s*[:\-]", q, re.I):
        return True
    return bool(CUSTOMER.search(q) and FIRST_PERSON.search(q)) and not ABOUT_US.search(q) and not ENGINE.search(q)


RERANK_SYSTEM = (
    "You match a hackathon judge's question to the closest prepared question about OpsLens, a decision engine for "
    "customer-support operations. You get the judge's question and numbered candidates. Pick the candidate whose "
    "answer would answer the judge, even if worded differently. If none fits (the question is off-topic or about "
    'something else), pick 0. Reply with JSON only: {"pick": <candidate number or 0>}'
)


def rerank(question: str, hits: list[tuple[float, dict]], client) -> tuple[dict | None, str]:
    from opslens.llm.base import LLMUnavailable

    if client is not None:
        listing = "\n".join(f"{i + 1}. {e['question']} (answer starts: {e['answer'][:90]}...)"
                            for i, (_, e) in enumerate(hits))
        try:
            reply = client.ask_json("bot_match", RERANK_SYSTEM, f"Judge's question: {question}\nCandidates:\n{listing}")
            pick = int((reply.data or {}).get("pick", -1))
            if 0 <= pick <= len(hits):
                return (hits[pick - 1][1] if pick else None), f"LLM ({reply.model})"
        except (LLMUnavailable, ValueError, TypeError, AttributeError):
            pass
    top_score, top = hits[0]
    return (top if top_score >= QA_MIN_SCORE else None), "word matching (LLM unavailable)"


def respond(question: str, ask: Callable[[str], dict], results: dict, client=None) -> dict:
    q = question.strip()
    if looks_like_customer(q):
        message = re.sub(r"^\s*(customer|complaint|ticket)\s*[:\-]\s*", "", q, flags=re.I)
        return triage(message, results)
    if ENGINE.search(q):
        return {"kind": "engine", **ask(q)}
    hits = qa_index().search(q, RERANK_K)
    chosen, matched_by = rerank(q, hits, client)
    if chosen:
        related = [{"id": e["id"], "question": e["question"]} for s, e in hits if e is not chosen and s >= QA_MIN_SCORE * 0.7][:3]
        return {"kind": "qa", "id": chosen["id"], "section": chosen["section"], "question": chosen["question"],
                "answer": chosen["answer"], "attack": chosen["attack"], "matched_by": matched_by, "related": related}
    engine = ask(q)
    if engine.get("route", {}).get("tool") not in (None, "none"):
        return {"kind": "engine", **engine}
    return {"kind": "unknown", "suggestions": [{"id": e["id"], "question": e["question"]} for _, e in hits[:3]]}
