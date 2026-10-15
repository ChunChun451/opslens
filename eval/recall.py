"""Score the pattern finder against the planted problems. Only eval/ may read planted.json.

A finding FINDS a planted problem when, for every key in the planted segment, the finding
covers that key with an overlapping value. Labels are expanded first, so that
"team B" also means categories {refund, payment_failure}, and "weekend dinner" means
weekdays {5, 6} and hours {19..22}.
A finding DIAGNOSES it when it finds it AND names the same cause type.

Example: planted P1 = {language: hi, category: [refund, payment_failure]}, cause skill_gap.
Finding {language: hi, team: B}, cause skill_gap → team B expands to {refund, payment_failure}
→ language overlaps, category overlaps → found and diagnosed.
"""

from __future__ import annotations

from opslens.patterns import HOUR_BANDS


def expand(segment: dict, team_skills: dict[str, list[str]]) -> dict[str, set]:
    """Turn a finding's labels into sets of comparable values."""
    out: dict[str, set] = {}
    owner = {c: t for t, cats in team_skills.items() for c in cats}
    for key, value in segment.items():
        values = set(value) if isinstance(value, (list, tuple, set)) else {value}
        if key == "when":
            for v in values:
                day_type, band = str(v).split(" ", 1)
                out.setdefault("weekday", set()).update({5, 6} if day_type == "weekend" else {0, 1, 2, 3, 4})
                low, high = next((lo, hi) for lo, hi, name in HOUR_BANDS if name == band)
                out.setdefault("hour", set()).update(range(low, high + 1))
        else:
            out.setdefault(key, set()).update(values)
    if "team" in out:
        for team in list(out["team"]):
            out.setdefault("category", set()).update(team_skills.get(str(team), []))
    if "category" in out:
        out.setdefault("team", set()).update(owner[c] for c in out["category"] if c in owner)
    return out


def finds(card: dict, planted: dict, team_skills: dict[str, list[str]]) -> bool:
    have = expand(card["segment"], team_skills)
    for key, value in planted["segment"].items():
        want = set(value) if isinstance(value, (list, tuple, set)) else {value}
        if key not in have or not (have[key] & want):
            return False
    return True


def score(cards: list[dict], planted: list[dict], team_skills: dict[str, list[str]]) -> dict:
    """Recall (found / diagnosed) per planted problem and the cards that match nothing."""
    details = []
    matched_cards: set[str] = set()
    for p in planted:
        hits = [c for c in cards if finds(c, p, team_skills)]
        diagnosed = [c for c in hits if c["cause_type"] == p["cause_type"]]
        matched_cards.update(c["id"] for c in hits)
        details.append({"id": p["id"], "name": p["name"], "found": bool(hits), "diagnosed": bool(diagnosed),
                        "card": hits[0]["id"] if hits else ""})
    unmatched = [c for c in cards if c["id"] not in matched_cards]
    return {
        "planted": len(planted),
        "found": sum(d["found"] for d in details),
        "diagnosed": sum(d["diagnosed"] for d in details),
        "details": details,
        "unmatched": unmatched,
    }
