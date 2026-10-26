from __future__ import annotations

import re

from opslens.llm.base import LLMUnavailable
from opslens.llm.client import LLMClient

KEY = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
NUMBER_WORDS = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"thousand|million|half|double|twice|triple|percent)\b", re.IGNORECASE)
SYSTEM = (
    "You write the morning decision brief for the head of a food-delivery support floor: what the proof says, "
    "what to watch in the next two days, the biggest recurring problem, and the one fix to do first. "
    "Use ONLY the facts given. Never write a number yourself, in digits or in words: refer to every "
    "number as {{key}} exactly as listed, and use each key only with the meaning described next to it. "
    "3 to 4 sentences, plain words, no bullet points, written for a busy floor manager; never repeat a phrase. Each value already carries its unit; do not add "
    "units or words like 'respectively', and name the method or group next to every value. "
    'Reply with JSON only: {"brief": "..."}'
)


def facts_from_results(r: dict) -> dict[str, tuple[str, str, str]]:
    pol = r["sim"]["policies"]

    def kpi(policy: str, name: str) -> float:
        return pol[policy]["kpis"][name]["mean"]

    p = "sim.policies.{}.kpis.{}.mean"
    lead = "baseline_d" if "baseline_d" in pol else "baseline_b"
    facts = {
        "opslens_breach": (f"{kpi('opslens', 'turnaround.breach_pct'):.1f}%",
                           "share of customers who missed their deadline with OpsLens on the held-out days",
                           p.format("opslens", "turnaround.breach_pct")),
        "industry_breach": (f"{kpi(lead, 'turnaround.breach_pct'):.1f}%",
                            "the same share with the industry-standard way of routing, same customers and agents",
                            p.format(lead, "turnaround.breach_pct")),
    }
    for i, c in enumerate(r["sim"].get("comparisons", [])):
        if c["policy"] == "opslens" and c["baseline"] == lead and c["kpi"] == "turnaround.breach_pct":
            facts["difference"] = (f"{c['mean_diff']:+.2f} points, 95% interval {c['ci_low']:+.2f} to {c['ci_high']:+.2f}",
                                   "the difference between the two, with its interval", f"sim.comparisons[{i}].mean_diff")
    t = r.get("tracking")
    if t:
        s = t["summary"]
        facts["days_won"] = (f"{s['opslens_better_than_industry_days']} of {s['days']} days",
                             "on how many of the held-out days OpsLens missed fewer deadlines",
                             "tracking.summary.opslens_better_than_industry_days")
    all_blocks = (r.get("forecast") or {}).get("bottlenecks", [])
    horizon = (r.get("forecast") or {}).get("horizon") or []
    if all_blocks and horizon:
        first, last = min(h["time"] for h in horizon), max(h["time"] for h in horizon)
        ahead = [k for k, b in enumerate(all_blocks)
                 if int(b["start"][11:13]) >= 7 and b["end"] >= first and b["start"] <= last]
        if ahead:
            k = max(ahead, key=lambda i: all_blocks[i]["agent_hours_short"])
            facts["bottleneck"] = (all_blocks[k]["text"], "the biggest staffing shortage forecast for the next two days (team, time, size)",
                                   f"forecast.bottlenecks[{k}].text")
    cards = r["patterns"]["cards"]
    if cards:
        top = cards[0]
        issue = re.sub(r"\s+", " ", re.sub(r"[\d.]+\s*×?", "", top["title"])).strip()
        facts["top_issue"] = (issue, "the biggest recurring problem found in the history", "patterns.cards[0].title")
        facts["top_issue_value"] = (f"{top['value']:.1f} {top['metric']}", "that problem's rate (the value carries its unit)",
                                    "patterns.cards[0].value")
        facts["top_issue_normal"] = (f"{top['comparison_value']:.1f} {top['metric']}",
                                     "the same rate for comparable tickets", "patterns.cards[0].comparison_value")
    items = (r.get("plan") or {}).get("items") or []
    clear = [(j, it) for j, it in enumerate(items) if it["kind"] == "playbook" and it["effect"]["breaches"]["ci_high"] < 0]
    if clear:
        j, best = min(clear, key=lambda ji: ji[1]["effect"]["breaches"]["diff"])
        title = best["title"].rstrip(".")
        facts["best_fix"] = (title[0].lower() + title[1:], "the fix at the source with the largest measured effect", f"plan.items[{j}].title")
        facts["best_fix_effect"] = (f"{-best['effect']['breaches']['diff']:.1f} fewer missed deadlines over the held-out days",
                                    "what that fix alone changes, replayed on days OpsLens never saw",
                                    f"plan.items[{j}].effect.breaches.diff")
    return facts


def menu_text(facts: dict[str, tuple[str, str, str]]) -> str:
    return "\n".join(f"- {{{{{key}}}}}: {desc}" for key, (_, desc, _) in facts.items())


def check_and_fill(text: str, facts: dict[str, tuple[str, str, str]]) -> str | None:
    keys = KEY.findall(text)
    if any(k not in facts for k in keys):
        return None
    rest = KEY.sub("", text)
    if re.search(r"\d", rest) or NUMBER_WORDS.search(rest):
        return None
    return KEY.sub(lambda m: facts[m.group(1)][0], text)


def template_brief(facts: dict[str, tuple[str, str, str]]) -> str:
    v = {k: val for k, (val, _, _) in facts.items()}
    text = f"On the held-out days OpsLens missed {v['opslens_breach']} of deadlines against {v['industry_breach']} for the industry standard"
    text += f" ({v['difference']})" if "difference" in v else ""
    text += f", and it was lower on {v['days_won']}." if "days_won" in v else "."
    if "bottleneck" in v:
        text += f" Watch next: {v['bottleneck']}."
    if "top_issue" in v:
        text += f" Biggest recurring problem: {v['top_issue']}, {v['top_issue_value']} against {v['top_issue_normal']} for comparable tickets."
    if "best_fix" in v:
        text += f" Do first: {v['best_fix']}, which alone means {v['best_fix_effect']}."
    return text


def write_brief(results: dict, client: LLMClient | None) -> dict:
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
