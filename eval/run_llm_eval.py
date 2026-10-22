"""W6 (b) and (c): does the LLM add value where we use it? Design: docs/explain/nlp_bench.md.

Run:  python eval/run_llm_eval.py [--only attribution|routing]
Needs eval/llm_eval/cards.json (python eval/llm_eval/make_cards.py) for (b).

(b) Root-cause attribution: the LLM reads each evidence card that matches a planted problem — with
    the card's cause type, title and recommendation removed — and names the cause type plus a
    one-line root cause (no digits). Scored against the planted truth, paired with our rules.
(c) Ask OpsLens routing: 60 labelled questions (eval/llm_eval/route_questions.json), LLM router
    (groq_route, the product's) vs keyword rules, both through the product's grounding check.
Writes eval/parts/llm_eval.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.recall import finds  # noqa: E402
from opslens.ask import SYSTEM as ROUTE_SYSTEM, check_route, rules_route  # noqa: E402
from opslens.config import load_config  # noqa: E402
from opslens.llm.base import LLMUnavailable  # noqa: E402
from opslens.llm.client import build_client  # noqa: E402

HERE = ROOT / "eval" / "llm_eval"
OUT = ROOT / "eval" / "parts" / "llm_eval.json"
BOOT = 2000
SEED = 77
RETRY_WAITS_S = [20, 40, 60, 120, 240]

CAUSE_TYPES = {
    "capacity": "the team has too little agent time for the work arriving in a time window "
                "(overloaded, or almost nobody capable on shift then)",
    "skill_gap": "a language or skill combination that very few agents have, so those tickets wait for the few",
    "volume_spike": "an unusual surge of one kind of ticket on a particular day",
    "partner_issue": "a restaurant (or partner cluster) causing more tickets of one kind than others",
    "process": "a routing or process fault, e.g. tickets sent to the wrong team and transferred",
    "other": "none of the above fits the evidence",
}
ATTR_SYSTEM = (
    "You are a support-operations analyst at an Indian food-delivery company. You get one evidence card "
    "about a group of tickets that is clearly worse than comparable tickets. Decide the most likely cause "
    "type:\n" + "\n".join(f"- {k}: {v}" for k, v in CAUSE_TYPES.items())
    + "\nTeams: A = live orders (late delivery); B = payments and refunds; C = order accuracy (missing / wrong "
    "item); D = account, app bugs and restaurant partners.\n"
    'Reply with JSON only: {"cause_type": <one cause type>, "root_cause": <one sentence, at most 20 words, '
    "NO digits>}"
)
EVIDENCE_KEYS = ("metric", "value", "comparison_value", "comparison_text", "segment", "affected_tickets",
                 "affected_share_pct", "not_explained_by", "examples")


# ---- Shared ------------------------------------------------------------------------------------

def ask(client, task: str, system: str, user: str):
    for wait in RETRY_WAITS_S:
        try:
            return client.ask_json(task, system, user)
        except LLMUnavailable as exc:
            print(f"  LLM unavailable (retry in {wait}s): {str(exc)[:120]}", flush=True)
            time.sleep(wait)
    return None


def rate(ok: np.ndarray, rng: np.random.Generator) -> dict:
    idx = rng.integers(0, len(ok), size=(BOOT, len(ok)))
    means = ok[idx].mean(axis=1) * 100
    return {"n": int(len(ok)), "correct": int(ok.sum()), "pct": round(100 * float(ok.mean()), 1),
            "ci95": [round(float(np.percentile(means, 2.5)), 1), round(float(np.percentile(means, 97.5)), 1)]}


def paired(a: np.ndarray, b: np.ndarray, rng: np.random.Generator) -> dict:
    diff = a.astype(float) - b.astype(float)
    idx = rng.integers(0, len(diff), size=(BOOT, len(diff)))
    means = diff[idx].mean(axis=1) * 100
    lo, hi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    return {"diff_pts": round(100 * float(diff.mean()), 1), "ci95": [round(lo, 1), round(hi, 1)],
            "above_zero": bool(lo > 0)}


# ---- (b) Attribution ---------------------------------------------------------------------------

def matched_pairs(cards_file: dict, team_skills: dict) -> list[dict]:
    """Every (planted problem, first matching card) pair, main world then blind sets."""
    pairs = []
    worlds = [("main", cards_file["main"]["cards"], cards_file["main"]["plants"])]
    worlds += [(f"blind{s['set']}", s["cards"], s["plants"]) for s in cards_file["blind"]]
    for world, cards, plants in worlds:
        for plant in plants:
            hits = [c for c in cards if finds(c, plant, team_skills)]
            if hits:
                pairs.append({"world": world, "plant": plant["id"], "plant_name": plant["name"],
                              "truth": plant["cause_type"], "card": hits[0]})
    return pairs


def run_attribution(client, rng: np.random.Generator) -> dict:
    cards_file = json.loads((HERE / "cards.json").read_text(encoding="utf-8"))
    team_skills = {t: v["skills"] for t, v in load_config("roster")["teams"].items()}
    pairs = matched_pairs(cards_file, team_skills)
    rows = []
    for p in pairs:
        evidence = {k: p["card"][k] for k in EVIDENCE_KEYS if k in p["card"]}
        reply = ask(client, "llm_attribution", ATTR_SYSTEM, json.dumps(evidence, ensure_ascii=False, default=str))
        data = reply.data if reply is not None and isinstance(reply.data, dict) else {}
        llm_type = str(data.get("cause_type", "")).strip().lower()
        line = str(data.get("root_cause", "")).strip()
        rows.append({"world": p["world"], "plant": p["plant_name"], "truth": p["truth"],
                     "rules": p["card"]["cause_type"], "llm": llm_type if llm_type in CAUSE_TYPES else "",
                     "root_cause": re.sub(r"\d", "", line)[:160], "had_digits": bool(re.search(r"\d", line)),
                     "answered": reply is not None, "model": reply.model if reply is not None else None})
        print(f"  {p['world']:8s} {p['plant_name'][:40]:40s} truth {p['truth']:13s} rules {rows[-1]['rules']:13s} "
              f"llm {rows[-1]['llm']:13s} {rows[-1]['root_cause'][:70]}", flush=True)
    truth = np.array([r["truth"] for r in rows])
    rules_ok = np.array([r["rules"] for r in rows]) == truth
    llm_ok = np.array([r["llm"] for r in rows]) == truth
    diff = paired(llm_ok, rules_ok, rng)
    return {"cards": len(rows), "rules": rate(rules_ok, rng), "llm": rate(llm_ok, rng), "llm_minus_rules": diff,
            "rule_llm_beats_rules": diff["above_zero"],
            "replies_with_digits": int(sum(r["had_digits"] for r in rows)),
            "unanswered": int(sum(not r["answered"] for r in rows)),
            "models": sorted({r["model"] for r in rows if r["model"]}), "rows": rows}


# ---- (c) Routing -------------------------------------------------------------------------------

def same_args(tool: str, want: dict, got: dict) -> bool:
    got = got or {}
    for key, value in want.items():
        have = got.get(key)
        if key == "agents_delta":
            try:
                have = {str(k).upper(): int(v) for k, v in (have or {}).items()}
            except (TypeError, ValueError):
                return False
            if have != value:
                return False
        elif key == "volume_change_pct":
            try:
                if have is None or float(have) != float(value):
                    return False
            except (TypeError, ValueError):
                return False
        elif str(have or "").strip().lower() != str(value).lower():
            return False
    return True


def score_route(q: dict, route: dict | None) -> tuple[str, bool, bool]:
    tool = route["tool"] if route else "none"
    tool_ok = tool == q["tool"]
    return tool, tool_ok, tool_ok and (tool == "none" or same_args(tool, q["args"], route["args"]))


def run_routing(client, rng: np.random.Generator) -> dict:
    questions = json.loads((HERE / "route_questions.json").read_text(encoding="utf-8"))["questions"]
    rows, latencies, models = [], [], set()
    for q in questions:
        rule_route = rules_route(q["q"])
        rule_route = check_route(rule_route, q["q"]) if rule_route else None
        reply = ask(client, "ask_route", ROUTE_SYSTEM, q["q"])
        llm_route = check_route(reply.data, q["q"]) if reply is not None else None
        if reply is not None:
            models.add(reply.model)
            if not reply.from_cache:
                latencies.append(reply.latency_s)
        r_tool, r_tool_ok, r_full = score_route(q, rule_route)
        l_tool, l_tool_ok, l_full = score_route(q, llm_route)
        rows.append({"id": q["id"], "lang": q["lang"], "want": q["tool"], "rules": r_tool, "rules_full": r_full,
                     "llm": l_tool, "llm_full": l_full, "llm_args": llm_route["args"] if llm_route else None,
                     "llm_answered": reply is not None})
        print(f"  {q['id']:2d} {q['lang']} want {q['tool']:14s} rules {r_tool:14s}{'✓' if r_full else '✗'} "
              f"llm {l_tool:14s}{'✓' if l_full else '✗'}", flush=True)

    def block(mask: np.ndarray) -> dict:
        get = lambda k: np.array([r[k] for r in rows])[mask]  # noqa: E731
        want = get("want")
        return {"rules_tool": rate(get("rules") == want, rng), "rules_full": rate(get("rules_full"), rng),
                "llm_tool": rate(get("llm") == want, rng), "llm_full": rate(get("llm_full"), rng),
                "llm_minus_rules_full": paired(get("llm_full"), get("rules_full"), rng)}

    langs = np.array([r["lang"] for r in rows])
    out = {"questions": len(rows), "all": block(np.ones(len(rows), bool)), "english": block(langs == "en"),
           "hinglish": block(langs == "hi"), "models": sorted(models),
           "median_uncached_latency_s": round(float(np.median(latencies)), 2) if latencies else None,
           "rows": rows}
    out["rule_llm_beats_rules"] = out["all"]["llm_minus_rules_full"]["above_zero"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["attribution", "routing"])
    args = parser.parse_args()
    rng = np.random.default_rng(SEED)
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if args.only in (None, "routing"):
        print("(c) routing", flush=True)
        out["routing"] = run_routing(build_client(["groq_route"]), rng)
    if args.only in (None, "attribution"):
        print("(b) attribution", flush=True)
        attribution = run_attribution(build_client(["gemini"]), rng)
        if attribution["unanswered"]:
            # A card the LLM never answered would count as wrong and bias the test against it.
            # Answers are cached, so a re-run only asks for the missing ones.
            print(f"{attribution['unanswered']} cards unanswered (provider down?): NOT written; run again later")
            return 1
        out["attribution"] = attribution
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for key in ("routing", "attribution"):
        if key in out:
            print(key, json.dumps({k: v for k, v in out[key].items() if k != "rows"}, ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
