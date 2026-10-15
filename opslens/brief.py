"""The daily ops brief: the LLM writes the words, our code writes every number.

What it does: offers the LLM a menu of facts, each with a key ("opslens_breach" → 4.2%),
and asks for a short brief that refers to numbers ONLY as {{key}}. Our code then checks the
reply and fills in the values from results.json.

The check (CLAUDE.md rule "the LLM never writes a digit"):
- any digit outside a {{key}} → rejected,
- any {{key}} that is not on the menu → rejected,
- rejected or no LLM available → a plain template brief built from the same facts.
So a made-up number cannot reach the screen, by construction (the idea of "proof-carrying
numbers": every number carries a pointer to where it was computed).

Example: LLM reply "Breaches fell to {{opslens_breach}} against {{priority_breach}} for
priority routing." → "Breaches fell to 4.2% against 6.8% for priority routing."
"""

from __future__ import annotations

import re

from opslens.llm.base import LLMUnavailable
from opslens.llm.client import LLMClient

KEY = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
SYSTEM = (
    "You write a short daily brief for the head of a food-delivery support floor. "
    "Use ONLY the facts given. Never write a digit: refer to every number as {{key}} exactly as "
    "listed. 3 to 4 sentences, plain words, no bullet points. "
    'Reply with JSON only: {"brief": "..."}'
)


def facts_from_results(r: dict) -> dict[str, tuple[str, str, str]]:
    """key → (formatted value, plain description, results.json path)."""
    pol = r["sim"]["policies"]

    def kpi(policy: str, name: str) -> float:
        return pol[policy]["kpis"][name]["mean"]

    p = "sim.policies.{}.kpis.{}.mean"
    cards = r["patterns"]["cards"]
    top = cards[0] if cards else None
    facts = {
        "opslens_breach": (f"{kpi('opslens', 'turnaround.breach_pct'):.1f}%", "SLA breaches with OpsLens on the test days",
                           p.format("opslens", "turnaround.breach_pct")),
        "priority_breach": (f"{kpi('baseline_b', 'turnaround.breach_pct'):.1f}%", "SLA breaches with priority-first routing",
                            p.format("baseline_b", "turnaround.breach_pct")),
        "fifo_breach": (f"{kpi('baseline_a', 'turnaround.breach_pct'):.1f}%", "SLA breaches with first-in-first-out routing",
                        p.format("baseline_a", "turnaround.breach_pct")),
        "opslens_p90": (f"{kpi('opslens', 'turnaround.p90_resolution_min'):.0f} min", "time within which 90% of tickets are resolved, OpsLens",
                        p.format("opslens", "turnaround.p90_resolution_min")),
        "priority_p90": (f"{kpi('baseline_b', 'turnaround.p90_resolution_min'):.0f} min", "the same for priority-first routing",
                         p.format("baseline_b", "turnaround.p90_resolution_min")),
    }
    if top:
        facts["top_issue_affected"] = (f"{top['affected_tickets']:,}", f"tickets affected by the top issue: {top['title']}",
                                       "patterns.cards[0].affected_tickets")
    return facts


def menu_text(facts: dict[str, tuple[str, str, str]]) -> str:
    """The facts as the LLM sees them: key and meaning, never the value itself."""
    return "\n".join(f"- {{{{{key}}}}}: {desc}" for key, (_, desc, _) in facts.items())


def check_and_fill(text: str, facts: dict[str, tuple[str, str, str]]) -> str | None:
    """Return the filled brief, or None if the reply breaks the rules."""
    keys = KEY.findall(text)
    if any(k not in facts for k in keys):
        return None
    if re.search(r"\d", KEY.sub("", text)):
        return None  # a digit outside {{...}}: the LLM wrote a number itself
    return KEY.sub(lambda m: facts[m.group(1)][0], text)


def template_brief(facts: dict[str, tuple[str, str, str]]) -> str:
    v = {k: val for k, (val, _, _) in facts.items()}
    text = (f"On the held-out test days OpsLens kept SLA breaches to {v['opslens_breach']}, against "
            f"{v['priority_breach']} for priority-first and {v['fifo_breach']} for first-in-first-out routing. "
            f"90% of tickets were resolved within {v['opslens_p90']} (priority-first: {v['priority_p90']}).")
    if "top_issue_affected" in facts:
        text += f" The top issue to fix affects {v['top_issue_affected']} tickets."
    return text


def write_brief(results: dict, client: LLMClient | None) -> dict:
    """Brief for the dashboard: {"text", "source", "numbers_used"} (numbers_used = result paths)."""
    facts = facts_from_results(results)
    if client is not None:
        try:
            reply = client.ask_json("brief", SYSTEM, "Facts:\n" + menu_text(facts))
            text = reply.data.get("brief", "") if isinstance(reply.data, dict) else ""
            filled = check_and_fill(str(text), facts)
            if filled:
                used = [facts[k][2] for k in dict.fromkeys(KEY.findall(str(text)))]
                return {"text": filled, "source": "llm", "numbers_used": used}
        except LLMUnavailable:
            pass
    return {"text": template_brief(facts), "source": "template", "numbers_used": [path for _, _, path in facts.values()]}
