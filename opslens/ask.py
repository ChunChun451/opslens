"""Ask OpsLens: a manager types a question in plain words; the engine answers it.

What it does: the LLM reads the question and picks ONE engine tool plus its arguments (JSON).
Our code checks that choice, runs the real tool (simulator, plant test, risk reasons, playbooks)
and writes the answer from the tool's output. So the LLM is the *ears*, the engine is the
*brain*, and every number on screen still comes from code (CLAUDE.md rule "the LLM never writes
a digit").

Why this design:
- A free-form chatbot would sound clever and invent numbers. Here the LLM's only job is
  understanding, which is what it is good at (Hinglish, vague wording, "Saturday night").
- Grounding check: every number in the tool arguments must appear in the question. The LLM may
  copy "2 agents" or "20%", never make up a day, a percentage or a headcount. Days are passed
  as weekday names and mapped to a test day by code.
- If the LLM is unavailable (Wi-Fi off) or its choice fails the checks, simple keyword rules
  try the same job, and the answer says which one understood the question.

Example: "What if Team C loses 2 agents on Saturday and volume goes up 20%?"
→ LLM: {"tool": "whatif", "args": {"weekday": "saturday", "agents_delta": {"C": -2},
        "volume_change_pct": 20}}
→ check: numbers 2 and 20 are in the question ✓ → day 48 (Sat 17 Oct), volume ×1.2, Team C −2
→ simulator runs the day for each policy → "OpsLens: 4.1% breaches vs 9.8% priority-first..."
  (numbers from the simulator at request time).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from opslens.llm.base import LLMUnavailable

TOOLS = ("whatif", "plant", "explain_ticket", "fix_first", "top_problems", "headline", "forecast", "at_risk")
TEAMS = {"A": "Live orders (late delivery)", "B": "Payments & refunds", "C": "Order accuracy (missing / wrong item)",
         "D": "Account, app bugs & restaurant partners"}
CATEGORIES = ("late_delivery", "refund", "payment_failure", "missing_item", "wrong_item", "account", "app_bug",
              "restaurant_partner")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Which team handles which category (as in opslens/classify.py), so "refund" questions find Team B.
TEAM_OF_CATEGORY = {"late_delivery": "A", "refund": "B", "payment_failure": "B", "missing_item": "C",
                    "wrong_item": "C", "account": "D", "app_bug": "D", "restaurant_partner": "D"}
# Plain and Hinglish words for a category, for the keyword rules (the LLM understands far more).
CATEGORY_WORDS = {"refund": ("refund", "paisa", "paise", "money back"), "payment_failure": ("payment", "upi", "debit"),
                  "late_delivery": ("late delivery", "delivery late", "khana late", "order late", "rider"),
                  "missing_item": ("missing", "nahi aaya"), "wrong_item": ("wrong item", "galat"),
                  "app_bug": ("app bug", "app crash", "app"), "account": ("account", "login"),
                  "restaurant_partner": ("restaurant", "partner")}
FUTURE_WORDS = ("forecast", "next 48", "next two days", "tomorrow", "tonight", "kal", "aaj raat", "raat", "busy",
                "rush", "bheed", "peak", "surge", "bottleneck", "short of", "understaffed", "how many agents",
                "capacity", "load")
RISK_WORDS = ("at risk", "risk", "miss", "late honge", "late hoga", "will be late", "breach next", "danger",
              "khatre", "kaun", "who will", "which tickets", "which customers")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
# Numbers written as words count as typed: "Two agents" grounds a 2 (found 22 Oct: the LLM answered
# {"D": -2} correctly, the check rejected it, and the keyword rules then simulated the day WITHOUT
# the change). English and common Hinglish words. "do" (Hindi 2) is also an English word, so it
# counts only right before a people word ("do log", "do agents").
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "hundred": 100, "ek": 1, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "bees": 20, "pachaas": 50,
}
HINDI_DO = re.compile(r"\bdo\s+(?:log|logon|agents?|bande|banda|aur|people)\b")


def typed_numbers(question: str) -> set[float]:
    """Every number the user wrote, as digits or as a word."""
    q = question.lower()
    typed = {float(m) for m in NUMBER.findall(q)}
    typed |= {float(NUMBER_WORDS[w]) for w in re.findall(r"[a-z]+", q) if w in NUMBER_WORDS}
    if HINDI_DO.search(q):
        typed.add(2.0)
    return typed


SYSTEM = (
    "You route a support-operations manager's question to ONE tool of a decision engine. "
    "Reply with JSON only: {\"tool\": ..., \"args\": {...}}. Tools:\n"
    "- whatif: simulate one day with changes. args: weekday (monday..sunday, optional), "
    "volume_change_pct (number, + or -, optional), agents_delta (object team letter -> + or - agents, optional). "
    "Teams: " + "; ".join(f"{k} = {v}" for k, v in TEAMS.items()) + ".\n"
    "- plant: hide a problem in fresh data and test whether the engine finds it. args: category (one of "
    + ", ".join(CATEGORIES) + "), effect (volume = a spike, wait = a skill gap / slow language, "
    "transfers = mislabelled tickets), language (hi or other, only for effect wait).\n"
    "- explain_ticket: why a ticket is at risk. args: ticket_id (like T060582).\n"
    "- fix_first: which upstream fix to do first. args: {}.\n"
    "- top_problems: the recurring problems found. args: {}.\n"
    "- headline: how much better the engine is than the usual ways of working. args: {}.\n"
    "- forecast: how busy the next 48 hours will be and which team will be short of people. args: team "
    "(A, B, C or D, optional), category (optional, as above).\n"
    "- at_risk: which waiting customers are most likely to miss their deadline now, and why. args: category "
    "(optional), language (hi, en or other, optional).\n"
    "Copy numbers only from the question; never add a number the user did not write. "
    "If nothing fits, use {\"tool\": \"none\", \"args\": {}}."
)


# ---- Understanding the question ----------------------------------------------------------------

def numbers_in(value: Any) -> list[float]:
    """Every number inside the tool arguments (recursively)."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [abs(float(value))]
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers_in(v)]
    if isinstance(value, str):
        return [] if re.fullmatch(r"T\d+", value) else [float(m) for m in NUMBER.findall(value)]
    return []


def check_route(route: Any, question: str) -> dict | None:
    """The route if it is legal and grounded in the question, else None."""
    if not isinstance(route, dict) or route.get("tool") not in TOOLS:
        return None
    args = route.get("args") or {}
    if not isinstance(args, dict):
        return None
    typed = typed_numbers(question)
    if any(n not in typed for n in numbers_in(args)):
        return None  # the LLM added a number the user never wrote
    tool = route["tool"]
    if tool == "whatif":
        if args.get("weekday") and str(args["weekday"]).lower() not in WEEKDAYS:
            return None
        delta = args.get("agents_delta") or {}
        if not isinstance(delta, dict) or any(str(k).upper() not in TEAMS for k in delta):
            return None
    if tool == "plant" and (args.get("category") not in CATEGORIES or args.get("effect") not in ("volume", "wait", "transfers")):
        return None
    if tool == "explain_ticket" and not re.fullmatch(r"T\d{6}", str(args.get("ticket_id", ""))):
        return None
    if tool in ("forecast", "at_risk"):
        if args.get("category") and args["category"] not in CATEGORIES:
            return None
        if args.get("team") and str(args["team"]).upper() not in TEAMS:
            return None
        if args.get("language") and args["language"] not in ("hi", "en", "other"):
            return None
    return {"tool": tool, "args": args}


def rules_route(question: str) -> dict | None:
    """Keyword rules: the offline fallback. Handles the common phrasings, nothing clever."""
    q = question.lower()
    ticket = re.search(r"\bt\d{6}\b", q)
    if ticket:
        return {"tool": "explain_ticket", "args": {"ticket_id": ticket.group(0).upper()}}
    if any(w in q for w in ("plant", "hide", "inject")):
        category = next((c for c in CATEGORIES if c.replace("_", " ") in q or c in q), "refund")
        effect = "wait" if any(w in q for w in ("hindi", "language", "slow", "wait")) else \
                 "transfers" if any(w in q for w in ("transfer", "mislabel", "wrong team")) else "volume"
        return {"tool": "plant", "args": {"category": category, "effect": effect}}
    if any(w in q for w in ("what if", "what happens", "agents", "volume", "staff")):
        args: dict[str, Any] = {}
        day = next((d for d in WEEKDAYS if d in q), None)
        if day:
            args["weekday"] = day
        pct = re.search(r"(\d+)\s*%", q)
        if pct:
            down = any(w in q for w in ("down", "drop", "fall", "less", "fewer"))
            args["volume_change_pct"] = -int(pct.group(1)) if down else int(pct.group(1))
        delta = {}
        for verb, count, team in re.findall(r"(add|plus|gain|loses?|remove|minus|without)\s+(\d+)\D{0,20}?team\s+([a-d])\b", q):
            delta[team.upper()] = int(count) if verb in ("add", "plus", "gain") else -int(count)
        for team, verb, count in re.findall(r"team\s+([a-d])\b\D{0,20}?(adds?|gains?|loses?|minus|plus)\s+(\d+)", q):
            delta[team.upper()] = int(count) if verb.startswith(("add", "gain", "plus")) else -int(count)
        if delta:
            args["agents_delta"] = delta
        return {"tool": "whatif", "args": args}
    category = next((c for c, words in CATEGORY_WORDS.items() if any(w in q for w in words)), None)
    if any(w in q for w in FUTURE_WORDS):  # about what is coming: the forecast answers it
        return {"tool": "forecast", "args": {"category": category} if category else {}}
    if any(w in q for w in RISK_WORDS):  # about who is in danger now
        args = {"category": category} if category else {}
        if "hindi" in q:
            args["language"] = "hi"
        return {"tool": "at_risk", "args": args}
    if any(w in q for w in ("fix first", "fix", "upstream", "root cause", "playbook")):
        return {"tool": "fix_first", "args": {}}
    if any(w in q for w in ("problem", "pattern", "issue", "recurring", "why are")):
        return {"tool": "top_problems", "args": {}}
    if any(w in q for w in ("better", "baseline", "compare", "improve", "impact", "breach")):
        return {"tool": "headline", "args": {}}
    return None


def understand(question: str, client) -> dict:
    """{"tool", "args", "understood_by"}: LLM first, keyword rules if it is unavailable or fails."""
    if client is not None:
        try:
            reply = client.ask_json("ask_route", SYSTEM, question)
            route = check_route(reply.data, question)
            if route:
                return {**route, "understood_by": f"LLM ({reply.model}{', cached' if reply.from_cache else ''})"}
        except LLMUnavailable:
            pass
    route = rules_route(question)
    if route and check_route(route, question):
        return {**route, "understood_by": "keyword rules (LLM unavailable or unsure)"}
    return {"tool": "none", "args": {}, "understood_by": "nobody"}


# ---- Turning a route into an engine request ----------------------------------------------------

def whatif_request(args: dict, test_days: tuple[int, int], first_weekday: int) -> dict:
    """Map weekday names and percentages to the What-if request (opslens/whatif.py).

    Example: weekday "saturday", test days 43-56, day 1 a Monday → day 48 (the first test Saturday).
    """
    day = test_days[0]
    if args.get("weekday"):
        wanted = WEEKDAYS.index(str(args["weekday"]).lower())
        day = next(d for d in range(test_days[0], test_days[0] + 7) if (first_weekday + d - 1) % 7 == wanted)
    pct = float(args.get("volume_change_pct") or 0.0)
    delta = {str(k).upper(): int(v) for k, v in (args.get("agents_delta") or {}).items()}
    return {"day": day, "policy": "opslens", "volume_factor": round(1.0 + pct / 100.0, 3), "agents_delta": delta}


def answer(question: str, client, tools: dict[str, Callable[..., dict]], results: dict,
           test_days: tuple[int, int], first_weekday: int) -> dict:
    """The whole loop: understand → run one tool → write the answer from its output."""
    route = understand(question, client)
    trace = [f"Understood by {route['understood_by']}: tool {route['tool']}, arguments {route['args']}"]
    tool, args = route["tool"], route["args"]
    if tool == "whatif":
        request = whatif_request(args, test_days, first_weekday)
        trace.append(f"Engine request: {request}")
        out = tools["whatif"](request)
        return {"route": route, "trace": trace + ["Ran the simulator for every policy on that day."],
                **whatif_text(out)}
    if tool == "plant":
        out = tools["plant"](args)
        return {"route": route, "trace": trace + ["Generated fresh data with the problem hidden, ran the pattern finder."],
                **plant_text(out)}
    if tool == "explain_ticket":
        return {"route": route, "trace": trace + ["Looked up the risk model's reasons in results.json."],
                **ticket_text(results, args["ticket_id"])}
    if tool == "fix_first":
        return {"route": route, "trace": trace + ["Ranked the playbooks by breaches avoided under OpsLens."], **fix_first_text(results)}
    if tool == "top_problems":
        return {"route": route, "trace": trace + ["Read the evidence cards in results.json."], **problems_text(results)}
    if tool == "headline":
        return {"route": route, "trace": trace + ["Read the held-out comparison in results.json."], **headline_text(results)}
    if tool == "forecast":
        return {"route": route, "trace": trace + ["Read the 48-hour forecast (80% band) and the bottlenecks in results.json."],
                **forecast_text(results, args)}
    if tool == "at_risk":
        return {"route": route, "trace": trace + ["Read the risk model's at-risk list in results.json."],
                **at_risk_text(results, args)}
    return {"route": route, "trace": trace, "title": "I did not understand that",
            "lines": ["Try: “What if Team C loses 2 agents on Saturday?”, “How busy is tomorrow night?”, "
                      "“Which customers will miss their deadline?”, “Why is T060582 at risk?”, "
                      "“Plant a refund spike”, “What should we fix first?”"], "facts": []}


# ---- Answers (all numbers come from tool output) -----------------------------------------------

POLICY_NAMES = {"baseline_a": "First come, first served", "baseline_b": "Urgent first (priority)",
                "baseline_d": "Industry standard (skills routing)", "opslens": "OpsLens"}


def whatif_text(out: dict) -> dict:
    req, pol = out["request"], out["all_policies"]
    change = []
    if req["volume_factor"] != 1.0:
        change.append(f"volume ×{req['volume_factor']:g}")
    change += [f"Team {t} {d:+d} agents" for t, d in req["agents_delta"].items() if d]
    o = pol["opslens"]
    other = "baseline_d" if "baseline_d" in pol else "baseline_b"  # compare with the strongest baseline
    b, b_name = pol[other], POLICY_NAMES[other]
    lines = [f"Day {req['day']} with {', '.join(change) or 'no change'}: {o['tickets']:.0f} tickets.",
             f"OpsLens: {o['turnaround.breach_pct']:.1f}% SLA breaches, P90 resolution {o['turnaround.p90_resolution_min']:.0f} min.",
             f"{b_name} on the same day: {b['turnaround.breach_pct']:.1f}% breaches "
             f"({b['turnaround.breach_pct'] - o['turnaround.breach_pct']:+.1f} points vs OpsLens)."]
    if "quality.late_minutes_per_100" in o:
        # Under heavy load OpsLens saves the tickets that can still make it, so P90 can rise while
        # breaches fall; minutes past SLA (all customers) is the fair way to show that trade-off.
        lines.append(f"Minutes past SLA per 100 tickets: OpsLens {o['quality.late_minutes_per_100']:,.0f}, "
                     f"{b_name.lower()} {b['quality.late_minutes_per_100']:,.0f}.")
        late_worse = o["quality.late_minutes_per_100"] > b["quality.late_minutes_per_100"]
        if late_worse and o["turnaround.breach_pct"] < b["turnaround.breach_pct"]:
            lines.append("Trade-off: in this overload OpsLens saves the tickets that can still make it first, "
                         "so customers already late wait longer; a guard brings them back after 8 hours.")
    facts = [{"label": POLICY_NAMES[k], "breach_pct": v["turnaround.breach_pct"], "p90_min": v["turnaround.p90_resolution_min"],
              "max_backlog": v["turnaround.max_backlog"], "late_per_100": v.get("quality.late_minutes_per_100")}
             for k, v in pol.items()]
    return {"title": "What-if, simulated just now", "lines": lines, "facts": facts}


def plant_text(out: dict) -> dict:
    p = out["planted"]
    if out["found"]:
        card = out["card"] or {}
        lines = [f"I hid this in {p['fresh_days']} fresh days: {p['description']}.",
                 f"Found it{' and named the right cause (' + p['cause_type'] + ')' if out['diagnosed'] else ''}: "
                 f"“{card.get('title', '')}”.", f"Took {out['seconds']:.0f} s."]
    else:
        lines = [f"I hid this in {p['fresh_days']} fresh days: {p['description']}.",
                 "OpsLens did NOT find it this time. Small groups with modest effects can be missed "
                 "(the blind test shows which ones)."]
    return {"title": "Plant-a-problem, run just now", "lines": lines, "facts": []}


def ticket_text(results: dict, ticket_id: str) -> dict:
    rows = (results.get("risk") or {}).get("at_risk") or []
    row = next((r for r in rows if r["ticket_id"] == ticket_id), None)
    if row is None:
        known = ", ".join(r["ticket_id"] for r in rows[:5])
        return {"title": f"{ticket_id} is not in today's at-risk list", "lines": [f"Tickets I can explain: {known}."], "facts": []}
    lines = [f"“{row['text']}” — {row['priority']} {row['category'].replace('_', ' ')}.",
             f"Breach risk {row['probability']:.2f}, {row['minutes_to_sla']:.0f} min to SLA."]
    lines += [f"• {r['text']}" for r in row["reasons"]]
    lines.append(f"Do this: {row['action']} → risk {row['probability_after_action']:.2f}.")
    return {"title": f"Why {ticket_id} is at risk", "lines": lines, "facts": []}


def fix_first_text(results: dict) -> dict:
    books = (results.get("playbooks") or {}).get("playbooks") or []
    def avoided(pb: dict) -> float:
        return -pb["effect"]["opslens"]["vs_without"]["breaches"]["mean_diff"]
    ranked = sorted(books, key=avoided, reverse=True)[:3]
    lines = []
    for pb in ranked:
        ci = pb["effect"]["opslens"]["vs_without"]["breaches"]
        sure = "clear effect" if ci["ci_high"] < 0 else "within noise"
        lines.append(f"{pb['title']} ({pb['owner']}): {avoided(pb):.0f} breaches avoided in two weeks, {sure}.")
    return {"title": "What to fix first", "lines": lines or ["No playbooks in the results yet."], "facts": []}


def problems_text(results: dict) -> dict:
    cards = (results.get("patterns") or {}).get("cards") or []
    lines = [f"{c['title']} — {c['cause_type']}, {c['affected_tickets']:,} tickets." for c in cards[:3]]
    return {"title": "Recurring problems, strongest evidence first", "lines": lines, "facts": []}


def headline_text(results: dict) -> dict:
    """The held-out result against the industry standard first (the lead comparison), then the 30 worlds."""
    pol = results["sim"]["policies"]
    b = {k: pol[k]["kpis"]["turnaround.breach_pct"]["mean"] for k in pol}
    days = results["meta"]["test_days"][1] - results["meta"]["test_days"][0] + 1
    lead = "baseline_d" if "baseline_d" in b else "baseline_b"
    lines = [f"On {days} held-out days, the same customers and the same agents: OpsLens {b['opslens']:.1f}% "
             f"missed their deadline, {POLICY_NAMES[lead].lower()} {b[lead]:.1f}%."]
    comp = next((c for c in results["sim"].get("comparisons", []) if c["policy"] == "opslens"
                 and c["baseline"] == lead and c["kpi"] == "turnaround.breach_pct"), None)
    if comp:
        lines.append(f"Difference {comp['mean_diff']:+.2f} points, 95% interval {comp['ci_low']:+.2f} to {comp['ci_high']:+.2f}.")
    others = [f"{POLICY_NAMES[k].lower()} {b[k]:.1f}%" for k in ("baseline_b", "baseline_a") if k in b and k != lead]
    if others:
        lines.append("The simpler ways of working: " + ", ".join(others) + ".")
    w = results.get("worlds")
    if w and w.get("breakdown"):
        bd = w["breakdown"]
        lines.append(f"On {bd['of']} random floors we did not design, OpsLens beat the industry standard on "
                     f"{bd['beats_industry_standard']}.")
    return {"title": "How much better than today", "lines": lines, "facts": []}


def forecast_text(results: dict, args: dict) -> dict:
    """The next 48 hours from the forecast: the busiest hours against capacity, and named bottlenecks."""
    f = results.get("forecast") or {}
    team = str(args.get("team") or TEAM_OF_CATEGORY.get(args.get("category") or "", "")).upper() or None
    hours = [h for h in f.get("horizon", []) if team is None or h["team"] == team]
    window = (min(h["time"] for h in hours), max(h["time"] for h in hours)) if hours else ("", "")
    # The bottleneck list covers the whole test fortnight; keep the ones inside these 48 hours.
    # Night hours (before 07:00) are covered by the cross-trained night pool (opslens/staffing.py), so a
    # night "shortage" is not a bottleneck by our own staffing rule.
    blocks = [b for b in f.get("bottlenecks", []) if (team is None or b["team"] == team)
              and b["end"] >= window[0] and b["start"] <= window[1] and int(b["start"][11:13]) >= 7]
    if not hours:
        return {"title": "No forecast in the results yet", "lines": [], "facts": []}
    who = f"Team {team} ({TEAMS[team]})" if team else "the whole floor"
    peak = max(hours, key=lambda h: h["hi80"] - h["capacity_hours"])
    gap = peak["hi80"] - peak["capacity_hours"]
    lines = [f"Next 48 hours for {who}: the tightest hour is {nice_time(peak['time'])} (Team {peak['team']}), "
             f"work up to {peak['hi80']:.1f} agent-hours (80% band) against {peak['capacity_hours']:.1f} on shift."]
    if blocks:
        lines += [f"Bottleneck: {b['text']} ({b['agent_hours_short']:.1f} agent-hours short)." for b in blocks[:3]]
    elif gap <= 0:
        lines.append("No hour is predicted above capacity even at the top of the 80% band.")
    if blocks:
        lines.append("Open Actions → staffing changes or Your plan to cover it with the same people.")
    return {"title": f"What the next 48 hours look like for {who}", "lines": lines, "facts": []}


def at_risk_text(results: dict, args: dict) -> dict:
    """The waiting customers most likely to miss their deadline, from the risk model's list."""
    rows = (results.get("risk") or {}).get("at_risk") or []
    if args.get("category"):
        rows = [r for r in rows if r["category"] == args["category"]]
    if args.get("language"):
        rows = [r for r in rows if r["language"] == args["language"]]
    if not rows:
        return {"title": "Nobody matching that is in the at-risk list", "lines": [], "facts": []}
    lines = [f"{len(rows)} waiting customer{'s' if len(rows) != 1 else ''} at high risk right now. The riskiest:"]
    for r in rows[:3]:
        risk = "≥99%" if r["probability"] >= 0.995 else f"{100 * r['probability']:.0f}%"
        lines.append(f"• {r['ticket_id']} ({r['priority']} {r['category'].replace('_', ' ')}, {r['language']}): "
                     f"{risk} chance to miss, {r['minutes_to_sla']:.0f} min left. Main reason: {r['reasons'][0]['text']}.")
    # Where an action changes the most (not always the riskiest: with 7 minutes left nothing helps).
    best = max(rows, key=lambda r: r["probability"] - r["probability_after_action"])
    drop = best["probability"] - best["probability_after_action"]
    if drop >= 0.05:
        lines.append(f"Where acting changes the most: {best['ticket_id']}. If {best['action'].replace('assign now to', 'it went now to')}, "
                     f"its risk would fall from {100 * best['probability']:.0f}% to {100 * best['probability_after_action']:.0f}%. "
                     f"When no such agent is on shift, OpsLens weighs a cross-skill rescue instead.")
    else:
        lines.append("For these, time has nearly run out: no single action brings the risk down much, "
                     "so OpsLens gives them its strongest rescue and protects the ones that can still be saved.")
    return {"title": "Who will miss their deadline next", "lines": lines, "facts": []}


def nice_time(stamp: str) -> str:
    """'2026-10-24T20:00' -> 'Sat 24 Oct 20:00'."""
    from datetime import datetime
    t = datetime.fromisoformat(stamp)
    return f"{t.strftime('%a')} {t.day} {t.strftime('%b')} {t.strftime('%H:%M')}"
