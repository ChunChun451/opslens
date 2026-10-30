from __future__ import annotations

import inspect
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
import numpy as np

from opslens import bus, store
from opslens.config import load_config
from opslens.world import ALL_CATEGORIES

log = logging.getLogger("opslens.agents")
MAX_STEPS = 6
RESULT_CHARS = 1800
EMBED_MODEL = "nomic-embed-text"
SIMILAR_POOL = 3000
INTAKE_WINDOW_MIN = 30
ANALYST_EVERY_S = 900.0
IDLE_WAIT_S = 30.0
MAX_PROPOSALS = 3
WORKING = ("busy", "cross", "wrong")

Floor = Callable[[], list[dict]]


@dataclass
class Tool:
    name: str
    about: str
    args: dict[str, str]
    fn: Callable[..., Any]


def ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


def ollama_up() -> bool:
    try:
        return httpx.get(f"{ollama_url()}/api/tags", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def embed(texts: list[str]) -> list[list[float]]:
    r = httpx.post(f"{ollama_url()}/api/embed", json={"model": EMBED_MODEL, "input": texts}, timeout=60)
    r.raise_for_status()
    return r.json()["embeddings"]


def q(sql: str, params: tuple = ()) -> list[dict]:
    with store.connection() as conn:
        return conn.execute(sql, params).fetchall()


def cosine_top(query: list[float], rows: list[dict], k: int) -> list[tuple[float, dict]]:
    if not rows:
        return []
    m = np.asarray([r["embedding"] for r in rows], dtype=np.float32)
    v = np.asarray(query, dtype=np.float32)
    sims = m @ v / (np.linalg.norm(m, axis=1) * np.linalg.norm(v) + 1e-9)
    order = np.argsort(-sims)[:k]
    return [(round(float(sims[i]), 3), rows[i]) for i in order]


def create_run(agent: str, trigger: str, ticket_id: str | None = None, requested_by: int | None = None) -> int:
    with store.connection() as conn:
        return conn.execute("insert into agent_runs (agent, trigger, ticket_id, requested_by) values (%s, %s, %s, %s) "
                            "returning id", (agent, trigger, ticket_id, requested_by)).fetchone()["id"]


class Run:
    def __init__(self, run_id: int, agent: str):
        self.id, self.agent, self.n = run_id, agent, 0

    def step(self, kind: str, tool: str | None = None, payload: Any = None) -> None:
        self.n += 1
        with store.connection() as conn:
            conn.execute("insert into agent_steps (run_id, n, kind, tool, payload) values (%s, %s, %s, %s, %s)",
                         (self.id, self.n, kind, tool, json.dumps(payload, default=str)))
        bus.publish("agents", {"run": self.id, "n": self.n, "kind": kind})

    def finish(self, status: str, summary: str, output: Any = None) -> None:
        with store.connection() as conn:
            conn.execute("update agent_runs set status = %s, summary = %s, output = %s, finished_at = now() where id = %s",
                         (status, summary[:500], json.dumps(output, default=str), self.id))
        bus.publish("agents", {"run": self.id, "status": status})


SYSTEM = """You are {role}
You work in steps. Every reply is one JSON object and nothing else.
To use a tool, reply {{"tool": "<name>", "args": {{...}}}}.
When you know enough, reply {{"answer": {shape}}}.
Tools you may use:
{catalog}
Rules: use at most {steps} tools. Only state numbers, ticket IDs and agent codes that a tool returned. Do not repeat a tool call you already made."""


def catalog(tools: list[Tool]) -> str:
    lines = []
    for t in tools:
        args = "; ".join(f"{k}: {v}" for k, v in t.args.items())
        lines.append(f"- {t.name}: {t.about}" + (f" Args: {args}" if args else " No args."))
    return "\n".join(lines)


def think(client, run: Run, role: str, shape: str, goal: str, tools: list[Tool], max_steps: int = MAX_STEPS) -> dict:
    by_name = {t.name: t for t in tools}
    system = SYSTEM.format(role=role, shape=shape, catalog=catalog(tools), steps=max_steps)
    notes: list[str] = []
    done_calls: set[str] = set()
    for turn in range(max_steps + 1):
        last = turn == max_steps
        user = goal
        if notes:
            user += "\n\nWhat you found so far:\n" + "\n".join(notes)
        if last:
            user += "\n\nYou have no tool calls left. Reply with the answer now."
        reply = client.ask_json(f"agent_{run.agent}", system, user).data
        reply = reply if isinstance(reply, dict) else {}
        if "answer" in reply or "tool" not in reply or last:
            answer = reply.get("answer", reply)
            answer = answer if isinstance(answer, dict) else {"text": str(answer)}
            run.step("answer", payload=answer)
            return answer
        name = str(reply.get("tool"))
        tool = by_name.get(name)
        if tool is None:
            run.step("error", tool=name, payload={"error": "no such tool"})
            notes.append(f"{name}: there is no such tool. Use one of: {', '.join(by_name)}.")
            continue
        raw = reply.get("args") if isinstance(reply.get("args"), dict) else {}
        args = {k: v for k, v in raw.items() if k in tool.args}
        needed = [n for n, prm in inspect.signature(tool.fn).parameters.items()
                  if prm.default is inspect.Parameter.empty and n not in args]
        if needed:
            run.step("error", tool=name, payload={"missing": needed})
            notes.append(f"{name} was called without {', '.join(needed)}. Call it again with "
                         + ", ".join(f'"{n}": {tool.args.get(n, "a value")}' for n in needed) + ".")
            continue
        key = f"{name}{json.dumps(args, sort_keys=True)}"
        if key in done_calls:
            notes.append(f"{name}{json.dumps(args)}: you already have this result. Answer or use another tool.")
            continue
        done_calls.add(key)
        run.step("tool_call", tool=name, payload=args)
        try:
            result = tool.fn(**args)
        except Exception as exc:
            result = {"error": f"{exc.__class__.__name__}: {exc}"}
        run.step("tool_result", tool=name, payload=result)
        notes.append(f"{name}({json.dumps(args)}) returned: {json.dumps(result, default=str)[:RESULT_CHARS]}")
    return {}


def read_ticket(ticket_id: str) -> dict:
    found = q("select id, priority, channel, language, category, ai_category, ai_summary, customer_tier, order_value_inr, "
              "restaurant, body, status, assignee, team, sla_due_at, breached, risk, risk_reasons from tickets where id = %s",
              (str(ticket_id),))
    return found[0] if found else {"error": f"no ticket {ticket_id}"}


def seed_kb() -> int:
    articles = load_config("kb")["articles"]
    vectors = embed([f"search_document: {a['title']}. {a['body']}" for a in articles])
    with store.connection() as conn:
        for a, v in zip(articles, vectors):
            conn.execute("insert into kb_articles (title, category, body, embedding) values (%s, %s, %s, %s) "
                         "on conflict (title) do update set body = excluded.body, category = excluded.category, "
                         "embedding = excluded.embedding", (a["title"], a["category"], a["body"].strip(), v))
    return len(articles)


def search_policies(query: str) -> list[dict]:
    rows = q("select title, category, body, embedding from kb_articles where embedding is not null")
    if not rows:
        seed_kb()
        rows = q("select title, category, body, embedding from kb_articles where embedding is not null")
    hits = cosine_top(embed([f"search_query: {query}"])[0], rows, 2)
    return [{"title": r["title"], "policy": r["body"], "match": s} for s, r in hits]


def ticket_vector(ticket_id: str) -> list[float] | None:
    found = q("select embedding from ticket_embeddings where ticket_id = %s", (ticket_id,))
    if found:
        return found[0]["embedding"]
    t = read_ticket(ticket_id)
    if "error" in t:
        return None
    v = embed([f"search_document: {t['body']}"])[0]
    with store.connection() as conn:
        conn.execute("insert into ticket_embeddings (ticket_id, embedding) values (%s, %s) on conflict (ticket_id) do "
                     "update set embedding = excluded.embedding", (ticket_id, v))
    return v


def similar_tickets(ticket_id: str, k: int = 3) -> list[dict]:
    v = ticket_vector(str(ticket_id))
    if v is None:
        return [{"error": f"no ticket {ticket_id}"}]
    pool = q("select e.ticket_id, e.embedding, t.category, t.body, t.breached, t.assignee from ticket_embeddings e "
             "join tickets t on t.id = e.ticket_id where t.status = 'solved' and e.ticket_id <> %s "
             "order by t.created_at desc limit %s", (str(ticket_id), SIMILAR_POOL))
    return [{"ticket_id": r["ticket_id"], "category": r["category"], "message": r["body"][:160],
             "kept_promise": not r["breached"], "match": s} for s, r in cosine_top(v, pool, max(1, min(int(k), 5)))]


def floor_tools(team: str | None, floor: Floor) -> list[Tool]:
    only = "and team = %s" if team else ""
    params = (team,) if team else ()

    def floor_summary() -> dict:
        today = q("select count(*) as arrived, count(*) filter (where status = 'open') as waiting, "
                  "count(*) filter (where status = 'in_progress') as being_worked, count(*) filter (where breached) as missed "
                  f"from tickets where created_at::date = current_date {only}", params)[0]
        teams = q("select team, count(*) filter (where status = 'open') as waiting, count(*) filter (where breached) as missed, "
                  "count(*) filter (where status <> 'solved' and risk >= 0.5) as likely_to_miss from tickets "
                  f"where created_at::date = current_date {only} group by team order by team", params)
        return {"today": today, "teams": teams}

    def at_risk(limit: int = 6) -> list[dict]:
        rows = q("select id as ticket_id, priority, category, language, team, status, assignee, risk, risk_reasons, "
                 "round(extract(epoch from sla_due_at - now()) / 60) as minutes_left from tickets "
                 f"where created_at::date = current_date and status <> 'solved' {only} "
                 "order by risk desc nulls last, sla_due_at limit %s", (*params, max(1, min(int(limit), 10))))
        return rows

    def free_agents() -> list[dict]:
        profiles = {p["agent_code"]: p for p in q("select agent_code, name, team, skills, languages from agent_profiles")}
        out = []
        for r in floor():
            p = profiles.get(r["id"])
            if p and r["status"] == "idle" and (not team or p["team"] == team):
                out.append({"agent": r["id"], "team": p["team"], "skills": p["skills"], "languages": p["languages"]})
        return out

    def people_now() -> dict:
        profiles = {p["agent_code"]: p["team"] for p in q("select agent_code, team from agent_profiles")}
        counts: dict[str, dict[str, int]] = {}
        for r in floor():
            t = profiles.get(r["id"])
            if team and t != team:
                continue
            word = "working" if r["status"] in WORKING else "free" if r["status"] == "idle" else r["status"]
            counts.setdefault(t, {}).setdefault(word, 0)
            counts[t][word] += 1
        return counts

    def category_mix(hours: int = 2) -> list[dict]:
        h = max(1, min(int(hours), 12))
        return q("select category, team, count(*) filter (where created_at >= now() - make_interval(hours => %s)) as recent, "
                 "round(count(*) filter (where created_at < now() - make_interval(hours => %s))::numeric / "
                 "greatest(1, extract(epoch from (now() - make_interval(hours => %s)) - date_trunc('day', now())) / 3600)::numeric * %s, 1) "
                 "as usual_for_that_long from tickets where created_at::date = current_date "
                 f"{only} group by category, team order by recent desc", (h, h, h, h, *params))

    def tickets_per_hour() -> list[dict]:
        return q("select hour, sum(created) as arrived, sum(breached) as missed from team_hourly "
                 f"where hour::date = current_date {only} group by hour order by hour", params)

    return [
        Tool("floor_summary", "today's ticket counts: arrived, waiting, being worked, missed, per team.", {}, floor_summary),
        Tool("at_risk", "open tickets most likely to miss their promise, with minutes left and reasons.",
             {"limit": "how many, 1-10"}, at_risk),
        Tool("free_agents", "agents on shift with no ticket right now, with their skills and languages.", {}, free_agents),
        Tool("people_now", "how many agents are working, free, on break or off, per team.", {}, people_now),
        Tool("category_mix", "tickets per category in the last few hours against the usual rate today.",
             {"hours": "1-12"}, category_mix),
        Tool("tickets_per_hour", "tickets that arrived and missed their promise each hour today.", {}, tickets_per_hour),
    ]


INTAKE_SYSTEM = (
    "You read one customer message sent to a food delivery app's support desk and fill in four fields.\n"
    "category: one of " + ", ".join(ALL_CATEGORIES) + ".\n"
    "language: en if the message is in English, hi if it is Hindi or Hinglish (Hindi in Latin letters), other otherwise.\n"
    "urgency: high if money is lost, food is unsafe or the order is stuck now; low for questions; normal otherwise.\n"
    "summary: what the customer needs, at most 12 words, no names, phone numbers or addresses.\n"
    "Always reply with all four fields. Example reply for 'mera order 1 ghante se nahi aaya': "
    '{"category": "late_delivery", "language": "hi", "urgency": "high", "summary": "Order is an hour late and has not arrived"}'
)


def run_intake(client, run: Run, ticket_id: str) -> dict:
    t = read_ticket(ticket_id)
    run.step("tool_call", tool="read_ticket", payload={"ticket_id": ticket_id})
    run.step("tool_result", tool="read_ticket", payload={k: t.get(k) for k in ("id", "priority", "channel", "category", "error")})
    if "error" in t:
        run.finish("failed", t["error"])
        return t
    try:
        ticket_vector(ticket_id)
        run.step("tool_result", tool="embed", payload={"model": EMBED_MODEL, "stored": True})
    except httpx.HTTPError as exc:
        run.step("error", tool="embed", payload={"error": str(exc)})
    data = client.ask_json("intake", INTAKE_SYSTEM, t["body"]).data
    data = data if isinstance(data, dict) else {}
    category = data.get("category") if data.get("category") in ALL_CATEGORIES else None
    urgency = data.get("urgency") if data.get("urgency") in ("high", "normal", "low") else None
    summary = str(data.get("summary") or "")[:160] or None
    with store.connection() as conn:
        conn.execute("update tickets set ai_category = %s, ai_summary = %s, ai_urgency = %s where id = %s",
                     (category, summary, urgency, ticket_id))
    agrees = category == t["category"]
    out = {"category": category, "urgency": urgency, "summary": summary, "router_category": t["category"], "agrees": agrees}
    run.step("answer", payload=out)
    word = "agrees with" if agrees else "differs from"
    run.finish("done", f"Reads {ticket_id} as {category or 'unclear'}, which {word} the router ({t['category']}).", out)
    return out


COPILOT_ROLE = ("the reply copilot for a support agent at a food delivery app in India. You draft the agent's reply; "
                "the agent reads and edits it before anything is sent.")
COPILOT_SHAPE = ('{"reply": "the message to the customer, 2-4 sentences, in English, or in Hinglish written in Latin '
                 'letters if the customer wrote Hindi or Hinglish; never in Devanagari", '
                 '"policy": "title of the policy you followed", "check": "one thing the agent must check before sending"}')


def policy_note(ticket: dict) -> str | None:
    value = ticket.get("order_value_inr")
    for a in load_config("kb")["articles"]:
        if a["category"] == ticket.get("category") and a.get("limit_inr") and value is not None:
            above = float(value) > float(a["limit_inr"])
            return (f"This order is Rs {float(value):.0f}, {'above' if above else 'within'} the Rs {a['limit_inr']} limit "
                    f"in the {a['title']} policy, so {a['above_limit' if above else 'up_to_limit']}.")
    return None


def ticket_for_reply(ticket_id: str) -> dict:
    t = read_ticket(ticket_id)
    note = policy_note(t)
    return {**t, "policy_for_this_order": note} if note else t


def run_copilot(client, run: Run, ticket_id: str) -> dict:
    run.step("tool_call", tool="read_ticket", payload={"ticket_id": ticket_id})
    t = ticket_for_reply(ticket_id)
    run.step("tool_result", tool="read_ticket", payload=t)
    if "error" in t:
        run.finish("failed", t["error"])
        return t
    query = f"{t['category']}: {t['body']}"
    run.step("tool_call", tool="search_policies", payload={"query": query})
    found = search_policies(query)
    run.step("tool_result", tool="search_policies", payload=found)
    facts = {k: t.get(k) for k in ("id", "priority", "channel", "category", "customer_tier", "order_value_inr", "restaurant", "body")}
    goal = (f"Ticket: {json.dumps(facts, default=str)}\n"
            + (f"For this order: {t['policy_for_this_order']}\n" if t.get("policy_for_this_order") else "")
            + "Policies that match:\n" + "\n".join(f"- {p['title']}: {p['policy']}" for p in found)
            + "\n\nDraft the reply to this customer. Follow the first policy unless the second clearly fits better. "
            "Write to the customer as 'you'. Say only what the policy allows; copy amounts and times from the policy. "
            "Do not tell the customer what the agent or another team should do. Never ask for a password or OTP.")
    tools = [Tool("similar_tickets", "solved tickets most like this one, if you want examples.",
                  {"ticket_id": "the ticket ID", "k": "1-5"}, similar_tickets)]
    answer = think(client, run, COPILOT_ROLE, COPILOT_SHAPE, goal, tools, max_steps=2)
    reply = str(answer.get("reply") or "").strip()
    if not reply:
        run.finish("failed", "The model did not produce a draft.", answer)
        return answer
    out = {"reply": reply, "policy": answer.get("policy"), "check": answer.get("check")}
    out.update(review(client, run, ticket_id, out))
    word = "fixed after checking" if out["fixed"] else "checked against"
    run.finish("done", f"Drafted a reply for {ticket_id}, {word} the {out['policy'] or 'matching'} policy.", out)
    return out


REVIEW_SYSTEM = (
    "You check a support agent's draft reply against the company policy before it is sent. "
    "Split the draft into its claims and promises. For each one, copy the policy sentence that supports it, "
    "or null if no policy sentence supports it. Greetings, apologies, thanks and questions to the customer need no policy. Then write the reply again keeping only supported claims, "
    "2-4 sentences, nothing repeated. Reply with one JSON object: "
    '{"claims": [{"claim": "...", "policy_sentence": "... or null"}], "reply": "the checked reply"}'
)


def review(client, run: Run, ticket_id: str, draft: dict) -> dict:
    t = read_ticket(ticket_id)
    named = q("select title, body from kb_articles where lower(title) = lower(%s)", (str(draft.get("policy") or ""),))
    policy = named[0] if named else next(iter(q("select title, body from kb_articles where category = %s", (t.get("category"),))), None)
    if policy is None:
        return {"fixed": False, "problems": []}
    facts = {k: t.get(k) for k in ("category", "priority", "order_value_inr", "customer_tier", "body")}
    if policy_note(t):
        facts["policy_for_this_order"] = policy_note(t)
    run.step("tool_call", tool="review_against_policy", payload={"policy": policy["title"]})
    data = client.ask_json("copilot_review", REVIEW_SYSTEM, f"Policy ({policy['title']}): {policy['body']}\n\n"
                           f"Ticket: {json.dumps(facts, default=str)}\n\nDraft: {draft['reply']}").data
    data = data if isinstance(data, dict) else {}
    claims = [c for c in data.get("claims") or [] if isinstance(c, dict) and c.get("claim")]
    polite = ("sorry", "apolog", "thank", "understand", "inconvenience")
    problems = [str(c["claim"]) for c in claims if (not c.get("policy_sentence") or str(c["policy_sentence"]).lower() == "null")
                and not any(w in str(c["claim"]).lower() for w in polite)]
    fixed = str(data.get("reply") or "").strip()
    run.step("tool_result", tool="review_against_policy", payload={"claims": claims, "unsupported": problems})
    if problems and fixed:
        return {"fixed": True, "problems": problems, "reply": fixed, "first_draft": draft["reply"], "policy": policy["title"]}
    return {"fixed": False, "problems": [], "policy": policy["title"]}


ANALYST_ROLE = "OpsLens, the operations analyst for a food delivery support floor. You advise team leads."
ANALYST_SHAPE = '{"picked": [{"id": "an action id from the list", "why": "one sentence with the numbers behind it"}]}'
ASK_ROLE = "OpsLens, the operations analyst for a food delivery support floor. You answer a team lead's question with live numbers."
ASK_SHAPE = '{"text": "2-4 sentences that answer the question, with the numbers you found"}'


BRIEFING = ("floor_summary", "at_risk", "people_now", "free_agents")
LANG = {"en": "English", "hi": "Hindi", "other": "another language"}


def ticket_line(t: dict) -> str:
    left = t["minutes_left"]
    when = (f"OVERDUE: its promise passed {int(-left)} minutes ago" if left is not None and left < 0
            else f"{int(left or 0)} minutes before its promise")
    chance = f", {round(100 * t['risk'])}% chance of missing" if t["risk"] is not None and (left or 0) >= 0 else ""
    state = "waiting for an agent" if t["status"] == "open" else f"with {t['assignee']}"
    return (f"Ticket {t['ticket_id']} ({t['priority']} {t['category']}, {LANG.get(t['language'], t['language'])}, "
            f"team {t['team']}) is {state}; {when}{chance}.")


def describe(facts: dict) -> list[str]:
    s = facts["floor_summary"]["today"]
    lines = [f"Today {s['arrived']} tickets arrived; {s['waiting']} are waiting for an agent, {s['being_worked']} are "
             f"being worked and {s['missed']} have missed their promise."]
    for t in facts["floor_summary"]["teams"]:
        lines.append(f"Team {t['team']}: {t['waiting']} waiting, {t['likely_to_miss']} likely to miss, {t['missed']} missed today.")
    for team, c in sorted(facts["people_now"].items(), key=lambda kv: str(kv[0])):
        lines.append(f"Team {team} people: " + ", ".join(f"{n} {word}" for word, n in sorted(c.items())) + ".")
    lines += [ticket_line(t) for t in facts["at_risk"]]
    free = facts["free_agents"]
    lines.append("Free right now: " + ("; ".join(
        f"{a['agent']} (team {a['team']}, handles {', '.join(a['skills'])}, speaks {', '.join(LANG.get(x, x) for x in a['languages'])})"
        for a in free) if free else "nobody") + ".")
    return lines


def gather(run: Run, tools: list[Tool]) -> dict:
    by_name = {t.name: t for t in tools}
    facts = {}
    for name in BRIEFING:
        run.step("tool_call", tool=name, payload={})
        facts[name] = by_name[name].fn()
        run.step("tool_result", tool=name, payload=facts[name])
    return facts


def brief(facts: dict) -> str:
    return "The live floor, checked just now:\n- " + "\n- ".join(describe(facts))


def check_reassign(ticket_id: str, agent: str, floor: Floor) -> str | None:
    t = q("select status, team, category, language from tickets where id = %s", (str(ticket_id),))
    if not t:
        return f"there is no ticket {ticket_id}"
    if t[0]["status"] != "open":
        return f"{ticket_id} is not waiting for an agent"
    p = q("select team, skills, languages from agent_profiles where agent_code = %s", (str(agent),))
    if not p:
        return f"there is no agent {agent}"
    if t[0]["category"] not in p[0]["skills"]:
        return f"{agent} does not handle {t[0]['category']}"
    if t[0]["language"] != "other" and t[0]["language"] not in p[0]["languages"]:
        return f"{agent} does not speak {t[0]['language']}"
    status = next((r["status"] for r in floor() if r["id"] == agent), "off")
    if status != "idle":
        return f"{agent} is not free right now ({status})"
    return None


def candidates(facts: dict, floor: Floor) -> list[dict]:
    out: list[dict] = []
    used: set[str] = set()
    waiting = [t for t in facts["at_risk"] if t["status"] == "open"]
    for t in sorted(waiting, key=lambda t: t["minutes_left"] if t["minutes_left"] is not None else 1e9):
        late = t["minutes_left"] is not None and t["minutes_left"] < 0
        who = next((a["agent"] for a in facts["free_agents"]
                    if a["agent"] not in used and check_reassign(t["ticket_id"], a["agent"], floor) is None), None)
        if who:
            used.add(who)
            out.append({"kind": "reassign", "team": t["team"], "ticket_id": t["ticket_id"], "agent_code": who,
                        "title": f"Give {t['ticket_id']} to {who}", "fact": ticket_line(t) + f" {who} is free and can take it."})
        elif late or (t["risk"] or 0) >= 0.5:
            out.append({"kind": "note", "team": t["team"], "ticket_id": t["ticket_id"], "agent_code": None,
                        "title": f"Find someone for {t['ticket_id']}: nobody free handles {t['category']} in "
                                 f"{LANG.get(t['language'], t['language'])}",
                        "fact": ticket_line(t)})
    for t in facts["floor_summary"]["teams"]:
        if t["likely_to_miss"] >= 2:
            out.append({"kind": "note", "team": t["team"], "ticket_id": None, "agent_code": None,
                        "title": f"Team {t['team']} has {t['likely_to_miss']} tickets likely to miss; ask who can finish early",
                        "fact": f"Team {t['team']}: {t['likely_to_miss']} likely to miss, {t['waiting']} waiting."})
    for i, c in enumerate(out, 1):
        c["id"] = f"{'R' if c['kind'] == 'reassign' else 'N'}{i}"
    return out


def headline(facts: dict) -> str:
    s = facts["floor_summary"]["today"]
    overdue = sum(1 for t in facts["at_risk"] if t["status"] == "open" and (t["minutes_left"] or 0) < 0)
    likely = sum(t["likely_to_miss"] for t in facts["floor_summary"]["teams"])
    free = len(facts["free_agents"])
    return (f"{s['missed']} of {s['arrived']} tickets have missed their promise today. {s['waiting']} waiting now"
            f"{f', {overdue} of them overdue' if overdue else ''}; {likely} likely to miss; "
            f"{free} agent{'' if free == 1 else 's'} free.")


def expire_stale() -> None:
    with store.connection() as conn:
        conn.execute("update proposals set status = 'expired', decided_at = now() where status = 'waiting' and "
                     "(created_at < now() - interval '2 hours' or (ticket_id is not null and not exists "
                     "(select 1 from tickets t where t.id = proposals.ticket_id and t.status = 'open')))")


def run_analyst(client, run: Run, team: str | None, floor: Floor) -> dict:
    expire_stale()
    tools = floor_tools(team, floor)
    facts = gather(run, tools)
    options = candidates(facts, floor)
    summary = headline(facts)
    if not options:
        out = {"summary": summary + " Nothing needs a lead's action right now.", "proposals": []}
        run.step("answer", payload=out)
        run.finish("done", out["summary"], out)
        return out
    listed = "\n".join(f"{c['id']}: {c['title']}. Facts: {c['fact']}" for c in options)
    goal = (brief(facts) + f"\n\nActions OpsLens has already checked are possible:\n{listed}\n\n"
            f"Pick up to {MAX_PROPOSALS} of these actions that matter most for keeping promises in the next 30 minutes, "
            "most urgent first. Use only the ids above.")
    answer = think(client, run, ANALYST_ROLE, ANALYST_SHAPE, goal, [t for t in tools if t.name not in BRIEFING], max_steps=2)
    by_id = {c["id"]: c for c in options}
    picked = []
    for p in answer.get("picked") or []:
        c = by_id.get(str(p.get("id") if isinstance(p, dict) else p).strip())
        if c and c not in picked:
            c["why"] = str(p.get("why") if isinstance(p, dict) else "")[:300] or c["fact"]
            picked.append(c)
    picked = picked[:MAX_PROPOSALS] or options[:1]
    for c in picked:
        c.setdefault("why", c["fact"])
    with store.connection() as conn:
        for c in picked:
            conn.execute("insert into proposals (run_id, kind, team, ticket_id, agent_code, title, why, evidence) "
                         "select %s, %s, %s, %s, %s, %s, %s, %s where not exists "
                         "(select 1 from proposals where status = 'waiting' and title = %s)",
                         (run.id, c["kind"], c["team"], c["ticket_id"], c["agent_code"], c["title"], c["why"],
                          json.dumps({"fact": c["fact"]}), c["title"]))
    out = {"summary": summary, "proposals": picked, "considered": len(options)}
    run.finish("needs_approval", summary, out)
    return out


def describe_more(facts: dict) -> list[str]:
    lines = []
    teams = facts["floor_summary"]["teams"]
    if teams and max(t["missed"] for t in teams) > 0:
        worst = max(teams, key=lambda t: t["missed"])
        lines.append(f"Most missed promises today: team {worst['team']} with {worst['missed']}.")
    overdue = [t["ticket_id"] for t in facts["at_risk"] if (t["minutes_left"] or 0) < 0 and t["status"] == "open"]
    lines.append(f"Overdue and still waiting: {len(overdue)}" + (f" ({', '.join(overdue)})." if overdue else "."))
    hours = facts.get("tickets_per_hour") or []
    if hours:
        busiest = max(hours, key=lambda h: int(h["arrived"]))
        lines.append(f"Busiest hour so far: {str(busiest['hour'])[11:16]} with {busiest['arrived']} tickets.")
        lines.append("Tickets per hour today: " + "; ".join(
            f"{str(h['hour'])[11:16]} {h['arrived']} arrived, {h['missed']} missed" for h in hours) + ".")
    mix = [m for m in facts.get("category_mix") or [] if m["recent"]]
    if mix:
        lines.append("Tickets in the last 2 hours by category: " + "; ".join(
            f"{m['category']} (team {m['team']}) {m['recent']}" for m in mix[:8]) + ".")
    return lines


def numbers(text: str) -> list[str]:
    return [n.rstrip(".") for n in re.findall(r"\d+(?:\.\d+)?", text)]


def run_ask(client, run: Run, question: str, team: str | None, floor: Floor) -> dict:
    tools = floor_tools(team, floor)
    by_name = {t.name: t for t in tools}
    facts = gather(run, tools)
    for name, args in (("tickets_per_hour", {}), ("category_mix", {"hours": 2})):
        run.step("tool_call", tool=name, payload=args)
        facts[name] = by_name[name].fn(**args)
        run.step("tool_result", tool=name, payload=facts[name])
    data = "The live floor, checked just now:\n- " + "\n- ".join(describe(facts) + describe_more(facts))
    goal = f"{data}\n\nQuestion from a team lead: {question}\nAnswer only from the facts above."
    allowed = set(numbers(data)) | set(numbers(question))
    text, unverified = "", []
    for attempt in range(2):
        answer = think(client, run, ASK_ROLE, ASK_SHAPE, goal, [], max_steps=0)
        text = str(answer.get("text") or "").strip()
        unverified = [n for n in numbers(text) if n not in allowed]
        if text and not unverified:
            break
        run.step("error", tool="check_numbers", payload={"not_in_the_data": unverified})
        goal += (f"\n\nYour last answer used numbers that are not in the facts: {', '.join(unverified)}. "
                 "Answer again using only numbers that appear in the facts.") if unverified else ""
    if not text:
        run.finish("failed", "The model did not answer.", answer)
        return answer
    out = {"text": text, "unverified": unverified}
    run.finish("done", text, out)
    return out


def handle(client, job: dict, floor: Floor) -> dict:
    run = Run(int(job["run_id"]), job["agent"])
    try:
        if job["agent"] == "intake":
            return run_intake(client, run, job["ticket_id"])
        if job["agent"] == "copilot":
            return run_copilot(client, run, job["ticket_id"])
        if job["agent"] == "analyst":
            return run_analyst(client, run, job.get("team"), floor)
        if job["agent"] == "ask":
            return run_ask(client, run, job["question"], job.get("team"), floor)
        raise ValueError(f"unknown agent {job['agent']}")
    except Exception as exc:
        log.exception("agent run %s failed", run.id)
        run.step("error", payload={"error": f"{exc.__class__.__name__}: {exc}"})
        run.finish("failed", f"{exc.__class__.__name__}: {exc}")
        return {"error": str(exc)}


def submit(agent: str, trigger: str, requested_by: int | None = None, **job) -> int:
    run_id = create_run(agent, trigger, job.get("ticket_id"), requested_by)
    bus.enqueue("agents", {"agent": agent, "run_id": run_id, **job})
    return run_id


def next_intake() -> str | None:
    found = q("select t.id from tickets t where t.ai_summary is null and t.status <> 'solved' "
              "and t.created_at > now() - make_interval(mins => %s) and not exists "
              "(select 1 from agent_runs r where r.ticket_id = t.id and r.agent = 'intake') "
              "order by t.created_at desc limit 1", (INTAKE_WINDOW_MIN,))
    return found[0]["id"] if found else None


def work_forever(floor: Floor, client=None, stop: Callable[[], bool] = lambda: False) -> None:
    from opslens.llm.client import build_client

    cfg = load_config("providers")
    client = client or build_client([cfg["main"]])
    last_analyst = time.monotonic()
    while not stop():
        if not ollama_up():
            time.sleep(IDLE_WAIT_S)
            continue
        got = bus.dequeue("agents", timeout_s=5)
        if got:
            job_id, job = got
            handle(client, job, floor)
            bus.finish(job_id, True)
            continue
        if time.monotonic() - last_analyst > ANALYST_EVERY_S:
            last_analyst = time.monotonic()
            submit("analyst", "every 15 minutes")
            continue
        ticket_id = next_intake()
        if ticket_id:
            run_id = create_run("intake", "new ticket", ticket_id)
            handle(client, {"agent": "intake", "run_id": run_id, "ticket_id": ticket_id}, floor)
