from server import bot


def test_every_prepared_answer_is_parsed_once():
    entries = bot.qa_index().entries
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate question ids"
    assert sum(i.startswith("Q") for i in ids) >= 80
    assert sum(i.startswith("B") for i in ids) >= 10
    assert all(e["question"] and e["answer"] for e in entries)
    attack = next(e for e in entries if e["id"] == "Q2")
    assert attack["attack"] and not attack["question"].lower().startswith("(attack)")


def test_customer_complaints_are_told_apart_from_judge_questions():
    for complaint in ("dosa ke jagah biryani de diya", "my food is 40 minutes late",
                      "paisa kat gaya but order nahi aaya", "the app keeps crashing when I pay",
                      "Customer: where is my refund"):
        assert bot.looks_like_customer(complaint), complaint
    for question in ("what about late deliveries?", "Isn't this data leakage?", "How does OpsLens handle refunds?",
                     "What if Team C loses 2 agents on Saturday?", "Why should we trust a simulator?"):
        assert not bot.looks_like_customer(question), question


def test_engine_questions_go_to_the_engine_and_others_do_not():
    for q in ("What if Team C loses 2 agents on Saturday?", "Why is T060582 at risk?", "Plant a refund spike",
              "What should we fix first?", "what happens if volume goes up 20%"):
        assert bot.ENGINE.search(q), q
    for q in ("What happens if the LLM is down during the demo?", "What if your data is wrong?"):
        assert not bot.ENGINE.search(q), q


def test_judge_questions_get_the_prepared_answer_offline():
    never = lambda q: (_ for _ in ()).throw(AssertionError("the engine was asked: " + q))
    cases = {"Is your baseline a strawman?": "Q9", "Does it only work on your generated data?": "Q37",
             "Can it scale to millions of tickets a day?": "B3"}
    for question, expected in cases.items():
        out = bot.respond(question, never, {}, client=None)
        assert out["kind"] == "qa" and out["id"] == expected, (question, out.get("id"))
        assert out["matched_by"].startswith("word matching")


def test_an_off_topic_question_is_not_answered_from_the_prepared_answers():
    asked = []

    def engine(q):
        asked.append(q)
        return {"route": {"tool": "none"}}

    out = bot.respond("what is the capital of peru", engine, {}, client=None)
    assert out["kind"] == "unknown" and asked == ["what is the capital of peru"]
    assert len(out["suggestions"]) == 3
