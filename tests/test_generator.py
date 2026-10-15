"""Generator, text bank and project-wide guards."""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.text_bank import TextBank, add_typos, fill_slots, food_flavour
from opslens.world import build_world, load_agents, ticket_numbers

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "data" / "generated"


# ---- Guards that protect the evaluation ------------------------------------------------------

def test_engine_never_reads_planted_json() -> None:
    """CLAUDE.md hard rule: only eval/ may read data/planted.json."""
    offenders = [
        str(p.relative_to(ROOT)) for p in (ROOT / "opslens").rglob("*.py")
        if re.search(r"planted\.json|PLANTED_PATH", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_engine_never_reads_generator_config() -> None:
    """generator.yaml describes the planted problems, so the engine must not read it
    (world.py builds the simulator — the test bench — and is the one exception)."""
    offenders = [
        str(p.relative_to(ROOT)) for p in (ROOT / "opslens").rglob("*.py")
        if 'load_config("generator")' in p.read_text(encoding="utf-8") and p.name != "world.py"
    ]
    assert offenders == []


def test_engine_never_reads_world_truth() -> None:
    """The engine reads the helpdesk export (history.csv), never the simulator's truth file,
    except world.py, which builds the simulator."""
    offenders = [
        str(p.relative_to(ROOT)) for p in (ROOT / "opslens").rglob("*.py")
        if "world_tickets" in p.read_text(encoding="utf-8") and p.name != "world.py"
    ]
    assert offenders == []


# ---- Roster ----------------------------------------------------------------------------------

def test_roster_plants_the_hindi_skill_gap() -> None:
    agents = load_agents()
    assert len(agents) == 40
    hindi_refund = [a.agent_id for a in agents if "hi" in a.languages and "refund" in a.skills]
    assert sorted(hindi_refund) == ["B01", "B02", "B05"]


def test_roster_has_cross_trained_team_d_agents() -> None:
    agents = {a.agent_id: a for a in load_agents()}
    for agent_id in ("D06", "D07", "D09"):
        assert {"missing_item", "wrong_item"} <= agents[agent_id].skills


# ---- Text bank -------------------------------------------------------------------------------

def test_food_flavour_swaps_ecommerce_words() -> None:
    assert food_flavour("where is my shipment? the product is late") == "where is my order? the food is late"


def test_fill_slots_never_leaves_placeholders() -> None:
    rng = np.random.default_rng(0)
    text = fill_slots(rng, "refund {{Refund Amount}} {{Weird}} for order {order_ref} from {restaurant}", "Dosa Corner", "4815162342", 1.0)
    assert "{" not in text and "}" not in text
    assert "order order" not in text and "Dosa Corner" in text


def test_typos_keep_word_count() -> None:
    rng = np.random.default_rng(1)
    text = "my biryani from the restaurant never arrived today"
    assert len(add_typos(rng, text, rate=1.0).split()) == len(text.split())


def test_make_text_hinglish_for_hindi() -> None:
    bank = TextBank(bitext_pool={}, vague_prob=0.0)
    rng = np.random.default_rng(3)
    texts = [bank.make_text(rng, "refund", "hi", "Dosa Corner", "4815162342") for _ in range(20)]
    hinglish_words = {"kab", "paisa", "wapas", "karo", "batao", "nahi", "chahiye", "mera", "kiya", "hafta"}
    assert all(any(w in t.lower() for w in hinglish_words) for t in texts)


# ---- World / CRN -----------------------------------------------------------------------------

def test_luck_is_tied_to_ticket_number_not_row() -> None:
    """Adding a ticket must not change the draws of existing tickets (common random numbers)."""
    base = pd.DataFrame({
        "ticket_id": ["T000001", "T000002"], "created_min": [0.0, 5.0], "category": ["refund", "refund"],
        "selected_category": ["refund", "refund"], "channel": ["chat", "chat"], "priority": ["P2", "P2"],
        "language": ["en", "en"], "customer_tier": ["normal", "normal"], "order_value_inr": [300, 300],
    })
    extra = pd.concat([base, base.iloc[[0]].assign(ticket_id="T000777", created_min=1.0)], ignore_index=True)
    w1, w2 = build_world(base, seed=7), build_world(extra, seed=7)
    h1 = dict(zip(w1.ticket_ids, w1.base_handle_min[:, 0]))
    h2 = dict(zip(w2.ticket_ids, w2.base_handle_min[:, 0]))
    assert h1["T000001"] == h2["T000001"] and h1["T000002"] == h2["T000002"]
    assert list(ticket_numbers(pd.Series(["T000777"]))) == [777]


# ---- Generated data (skipped until `make gen` has run) ---------------------------------------

@pytest.mark.skipif(not (GENERATED / "history.csv").exists(), reason="run `make gen` first")
def test_generated_data_shape_and_signals() -> None:
    hist = pd.read_csv(GENERATED / "history.csv")
    assert 60_000 < len(hist) < 80_000
    assert hist["resolution_min"].isna().sum() == 0
    # Planted signals are visible in the raw export.
    b = hist[hist["final_category"].isin(["refund", "payment_failure"])]
    waits = b.groupby("language")["wait_min"].mean()
    assert waits["hi"] > 3 * waits["en"]
    calls = hist.groupby("channel")["transfers"].mean()
    assert calls["call"] > 3 * calls["chat"]
    # No raw placeholder or template slot leaked into the text.
    assert not hist["text"].str.contains(r"\{|\}", regex=True).any()
    assert not hist["text"].str.contains("order my order").any()


def test_vague_tickets_have_no_category_words() -> None:
    bank = TextBank(bitext_pool={}, vague_prob=1.0, typo_prob=0.0, phone_prob=0.0, email_prob=0.0)
    rng = np.random.default_rng(5)
    texts = [bank.make_text(rng, "refund", "en", "Dosa Corner", "4815162342") for _ in range(30)]
    assert not any("refund" in t or "money" in t for t in texts)
