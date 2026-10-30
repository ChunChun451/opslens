from __future__ import annotations

import json

import numpy as np

from opslens import rag
from opslens.llm.client import LLMClient
from opslens.llm.mock import MockProvider

ROWS = [
    {"source": "policy", "ref": "policy:refund", "title": "Refunds policy", "link": None, "card": None,
     "body": "Refunds to cards and UPI take 5 to 7 working days; wallet refunds are instant.", "embedding": [1.0, 0.0, 0.0]},
    {"source": "problem", "ref": "problem:F1", "title": "Hindi x Team B wait 13.0x longer", "link": "#problems", "card": "card-F1",
     "body": "Hindi refund tickets wait 368 min vs 28 min. Measured fix: 131 fewer missed promises.", "embedding": [0.0, 1.0, 0.0]},
    {"source": "ticket", "ref": "ticket:T1", "title": "Refund ticket T1", "link": None, "card": None,
     "body": "Customer wrote: refund nahi aaya. The promise was kept.", "embedding": [0.9, 0.1, 0.0]},
    {"source": "ticket", "ref": "ticket:T2", "title": "Refund ticket T2", "link": None, "card": None,
     "body": "Customer wrote: where is my refund. The promise was missed.", "embedding": [0.95, 0.0, 0.05]},
]


def finder(vector, mode="both"):
    idx = rag.make_index(ROWS)
    return lambda q: rag.search_in(idx, q, 5, mode, lambda texts: [vector])


def scripted(*replies) -> LLMClient:
    return LLMClient([MockProvider(replies=[json.dumps(r) for r in replies])])


def test_every_source_becomes_pieces_with_unique_refs_and_plain_numbers():
    chunks = rag.all_chunks()
    refs = [c["ref"] for c in chunks]
    assert len(refs) == len(set(refs))
    assert {c["source"] for c in chunks} == {"policy", "problem", "fix", "results", "readme", "docs", "faq", "ticket"}
    f1 = next(c for c in chunks if c["ref"] == "fix:pb_F1")
    assert "fewer missed promises" in f1["body"] and "−" not in f1["body"]


def test_search_blends_meaning_and_words_and_keeps_tickets_to_one():
    hits = finder([1.0, 0.0, 0.0])("how long do UPI refunds take")
    assert hits[0]["ref"] == "policy:refund" and hits[0]["how"] == "meaning and words"
    assert sum(1 for h in hits if h["source"] == "ticket") == 1
    words_only = rag.search_in(rag.make_index([{**r, "embedding": None} for r in ROWS]), "Hindi wait", 5, "both", None)
    assert words_only[0]["ref"] == "problem:F1" and words_only[0]["how"] == "words only"


def test_an_answer_cites_its_sources_and_passes_the_number_check():
    client = scripted({"answer": "Card and UPI refunds take 5 to 7 working days [1].", "used": [1]})
    out = rag.answer("how long do UPI refunds take", client=client, find=finder([1.0, 0.0, 0.0]))
    assert out["kind"] == "rag" and out["checked"] and out["unverified"] == []
    assert [s["ref"] for s in out["sources"] if s["used"]] == ["policy:refund"]


def test_a_number_not_in_the_sources_is_sent_back_once():
    client = scripted({"answer": "They take 12 days [1].", "used": [1]}, {"answer": "They take 5 to 7 working days.", "used": [1]})
    out = rag.answer("how long do UPI refunds take", client=client, find=finder([1.0, 0.0, 0.0]))
    assert out["answer"].endswith("[1]") and out["checked"]
    assert "not in the sources: 12" in client.providers[0].sent[1][1]["content"]


def test_off_topic_or_uncovered_questions_fall_back_instead_of_guessing():
    off = scripted({"answer": "Paris.", "used": []})
    assert rag.answer("capital of France", client=off, find=finder([0.0, 0.0, 1.0])) is None
    assert off.providers[0].sent == []
    uncovered = scripted({"answer": "OpsLens's data does not cover that.", "used": []})
    assert rag.answer("how long do UPI refunds take", client=uncovered, find=finder([1.0, 0.0, 0.0])) is None


def test_the_chatbot_uses_rag_first_and_the_prepared_answers_when_rag_has_none():
    from server import bot

    never = lambda q: (_ for _ in ()).throw(AssertionError("engine should not run"))
    written = {"kind": "rag", "answer": "x [1]", "sources": []}
    assert bot.respond("is this data leakage?", never, {}, client=None, rag=lambda q: dict(written))["kind"] == "rag"
    assert bot.respond("is this data leakage?", never, {}, client=None, rag=lambda q: None)["kind"] in ("qa", "unknown")


def test_numbers_ignore_citations_and_thousands_commas():
    assert rag.numbers("It affects 4,345 tickets [2] and 13.0x [3].") == ["4345", "13.0"]
    assert np.isclose(rag.VECTOR_WEIGHT + (1 - rag.VECTOR_WEIGHT), 1.0)
