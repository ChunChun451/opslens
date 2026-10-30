from __future__ import annotations

import csv
import io
import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response

from server.v2 import (ADMIN, ANY_ROLE, TODAY, VIEWS, WORKING, can_see, find_tickets, floor_action, floor_rows, jsonable,
                       rows, scope)

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results.json"
V2_RESULTS = ROOT / "docs" / "v2" / "results"
router = APIRouter(prefix="/api/v2")
MESSAGE_KINDS = ("public", "internal")
MAX_MESSAGE = 4000
SEARCH_LIMIT = 12
TODAY_KEYS = ("language", "team", "channel", "category")
STATUS_WORD = {"idle": "free", "busy": "working", "cross": "helping another team", "wrong": "working", "break": "on break",
               "off": "off shift"}


def ticket_or_404(user: dict, ticket_id: str) -> dict | None:
    found = rows("select * from tickets where id = %s", (ticket_id,))
    return found[0] if found and can_see(user, found[0]) else None


def note(ticket_id: str, user: dict | None, kind: str, body: str, name: str | None = None, role: str | None = None) -> dict:
    return rows("insert into ticket_messages (ticket_id, author_id, author_name, author_role, kind, body) "
                "values (%s, %s, %s, %s, %s, %s) returning id, author_name, author_role, kind, body, at",
                (ticket_id, user["id"] if user else None, name or user["name"], role or user["role"], kind, body))[0]


@router.post("/tickets/{ticket_id}/messages")
def post_message(ticket_id: str, request: dict, user: dict = Depends(ANY_ROLE)) -> JSONResponse:
    t = ticket_or_404(user, ticket_id)
    if t is None:
        return JSONResponse({"error": "no such ticket"}, status_code=404)
    kind = request.get("kind", "public")
    body = str(request.get("body", "")).strip()[:MAX_MESSAGE]
    if kind not in MESSAGE_KINDS or not body:
        return JSONResponse({"error": "write a reply or a note first"}, status_code=400)
    solve = bool(request.get("solve"))
    if solve and (user["role"] != "agent" or t["assignee"] != user["agent_code"]):
        return JSONResponse({"error": "only the agent working on this ticket can mark it solved"}, status_code=403)
    effect = None
    if solve:
        mine = next((r for r in floor_rows() if r["id"] == user["agent_code"]), None)
        if not mine or not mine.get("current") or mine["current"]["ticket_id"] != ticket_id:
            return JSONResponse({"error": "This ticket is not the one you are working on right now."}, status_code=409)
        code, effect = floor_action("done", user["agent_code"])
        if code != 200:
            return JSONResponse(effect, status_code=code)
    saved = note(ticket_id, user, kind, body)
    return JSONResponse(jsonable({"message": saved, "solved": solve, "effect": effect}))


def fit(ticket: dict, person: dict) -> dict:
    skill = ticket["category"] in (person.get("skills") or [])
    language = ticket["language"] == "other" or ticket["language"] in (person.get("languages") or [])
    return {"skill": skill, "language": language, "good": skill and language}


@router.get("/tickets/{ticket_id}/assignees")
def assignees(ticket_id: str, user: dict = Depends(ADMIN)) -> JSONResponse:
    t = ticket_or_404(user, ticket_id)
    if t is None:
        return JSONResponse({"error": "no such ticket"}, status_code=404)
    profiles = {p["agent_code"]: p for p in rows("select agent_code, name, team, skills, languages from agent_profiles")}
    out = []
    for r in floor_rows():
        p = profiles.get(r["id"])
        if not p or r["status"] == "off":
            continue
        out.append({"agent": r["id"], "name": p["name"], "team": p["team"], "status": r["status"],
                    "status_word": STATUS_WORD.get(r["status"], r["status"]), **fit(t, p)})
    out.sort(key=lambda a: (not a["good"], a["status"] != "idle", a["team"] != t["team"], a["agent"]))
    return JSONResponse({"ticket_id": ticket_id, "agents": out})


@router.post("/tickets/{ticket_id}/assign")
def assign(ticket_id: str, request: dict, user: dict = Depends(ADMIN)) -> JSONResponse:
    t = ticket_or_404(user, ticket_id)
    if t is None:
        return JSONResponse({"error": "no such ticket"}, status_code=404)
    if t["status"] == "solved":
        return JSONResponse({"error": "this ticket is already solved"}, status_code=409)
    agent = str(request.get("agent", "")).upper()
    status = next((r["status"] for r in floor_rows() if r["id"] == agent), None)
    if status is None or status == "off":
        return JSONResponse({"error": f"{agent or 'that agent'} is not on shift right now"}, status_code=409)
    code, body = floor_action("take", agent, ticket_id=ticket_id, reason=f"assigned by {user['name']}")
    if code != 200:
        return JSONResponse(body, status_code=code)
    note(ticket_id, user, "internal", f"Assigned to {agent} by {user['name']}. OpsLens re-planned the floor around it.")
    return JSONResponse(jsonable({"ok": True, "effect": body.get("effect")}))


@router.post("/agents/{agent_code}/status")
def set_status(agent_code: str, request: dict, user: dict = Depends(ADMIN)) -> JSONResponse:
    kind = request.get("kind")
    if kind not in ("break", "back"):
        return JSONResponse({"error": "kind is break or back"}, status_code=400)
    code, body = floor_action(kind, agent_code.upper())
    return JSONResponse(body, status_code=code)


@router.get("/tickets/{ticket_id}/similar")
def similar(ticket_id: str, user: dict = Depends(ANY_ROLE)) -> JSONResponse:
    from opslens import agents

    t = ticket_or_404(user, ticket_id)
    if t is None:
        return JSONResponse({"error": "no such ticket"}, status_code=404)
    try:
        found = agents.similar_tickets(ticket_id, 3)
        how = "by meaning, on the local model"
    except Exception:
        found = rows("select id as ticket_id, category, left(body, 160) as message, not coalesce(breached, false) as kept_promise "
                     "from tickets where status = 'solved' and category = %s and id <> %s order by solved_at desc limit 3",
                     (t["category"], ticket_id))
        how = "same category (the local model is not running)"
    return JSONResponse(jsonable({"similar": found, "how": how}))


@router.get("/search")
def search(q: str = "", user: dict = Depends(ANY_ROLE)) -> JSONResponse:
    q = q.strip()[:80]
    if len(q) < 2:
        return JSONResponse({"results": []})
    allowed, params = scope(user)
    found = rows("select id, priority, status, category, assignee, left(body, 90) as subject, created_at from tickets "
                 f"where {allowed} and (id ilike %s or body ilike %s or assignee ilike %s) "
                 "order by (id ilike %s) desc, created_at desc limit %s",
                 (*params, f"%{q}%", f"%{q}%", q, f"{q}%", SEARCH_LIMIT))
    return JSONResponse(jsonable({"results": found}))


@router.get("/export.csv")
def export(view: str = "open", team: str = "", user: dict = Depends(ANY_ROLE)) -> Response:
    if view not in VIEWS:
        return JSONResponse({"error": "unknown view"}, status_code=400)
    found = find_tickets(user, view, team, limit=500)
    buf = io.StringIO()
    cols = ["id", "priority", "status", "category", "language", "channel", "team", "assignee", "created_at", "sla_due_at",
            "solved_at", "breached", "risk", "subject"]
    w = csv.writer(buf)
    w.writerow(cols)
    for r in found:
        w.writerow([r.get(c) for c in cols])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="opslens-{view}.csv"'})


@router.get("/me/stats")
def my_stats(user: dict = Depends(ANY_ROLE)) -> JSONResponse:
    if user["role"] != "agent":
        return JSONResponse({"error": "agents only"}, status_code=400)
    return JSONResponse(jsonable(rows(
        "select count(*) filter (where status = 'solved') as solved, "
        "count(*) filter (where status = 'solved' and not coalesce(breached, false)) as on_time, "
        "round(avg(extract(epoch from solved_at - assigned_at) / 60) filter (where status = 'solved')::numeric, 1) as avg_handle_min "
        f"from tickets where {TODAY} and assignee = %s", (user["agent_code"],))[0]))


@lru_cache(maxsize=1)
def results() -> dict:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def team_in(title: str) -> str | None:
    m = re.search(r"Team (\w)\)", title)
    return m.group(1) if m else None


def effect_of(item: dict) -> dict:
    e = item["effect"]
    return {"missed": round(e["breaches"]["diff"], 1), "missed_low": round(e["breaches"]["ci_low"], 1),
            "missed_high": round(e["breaches"]["ci_high"], 1), "rate": round(e["breach_pct"]["diff"], 2),
            "certain": e["breaches"]["ci_high"] < 0, "worse": e["breaches"]["ci_low"] > 0}


def fix_row(item: dict) -> dict:
    return {"id": item["id"], "kind": item["kind"], "title": item["title"], "owner": item.get("owner"),
            "when": item.get("when"), "action": item.get("action"), "assumptions": item.get("assumptions", []),
            "team": team_in(item["title"]), "effect": effect_of(item)}


def today_like(segment: dict) -> dict | None:
    keys = [k for k in segment if k in TODAY_KEYS]
    if not keys or any(k not in TODAY_KEYS for k in segment):
        return None
    where = " and ".join(f"{k} = %s" for k in keys)
    found = rows(f"select count(*) as tickets, count(*) filter (where breached) as missed, "
                 "round(avg(extract(epoch from coalesce(assigned_at, now()) - created_at) / 60)::numeric, 1) as avg_wait_min "
                 f"from tickets where {TODAY} and {where}", tuple(segment[k] for k in keys))[0]
    return found


def test_days(span: list[int]) -> list[dict]:
    from datetime import date, timedelta

    from opslens.config import load_config

    start = date.fromisoformat(str(load_config("calendar")["start_date"]))
    return [{"day": d, "weekday": (start + timedelta(days=d - 1)).strftime("%A"),
             "date": (start + timedelta(days=d - 1)).strftime("%d %b")} for d in range(span[0], span[1] + 1)]


@router.get("/problems")
def problems(user: dict = Depends(ADMIN)) -> JSONResponse:
    r = results()
    plan = r["plan"]
    fixes = [fix_row(i) for i in plan["items"]]
    chosen = {c["item_id"] for c in rows("select item_id from plan_choices")}
    cards = []
    for c in r["patterns"]["cards"]:
        mine = [f for f, i in zip(fixes, plan["items"]) if i.get("card_id") == c["id"]]
        if not mine and c["cause_type"] == "capacity" and c["segment"].get("team"):
            mine = [f for f in fixes if f["kind"] == "staffing" and f["team"] == c["segment"]["team"]]
        cards.append({**{k: c.get(k) for k in ("id", "title", "cause_type", "metric", "value", "comparison_value",
                                               "comparison_text", "segment", "affected_tickets", "affected_share_pct",
                                               "strength", "not_explained_by", "examples", "recommendation")},
                      "fixes": [f["id"] for f in mine], "today": today_like(c["segment"])})
    a = plan["all_items"]["effect"]
    return JSONResponse(jsonable({
        "cards": cards, "fixes": fixes, "chosen": sorted(chosen),
        "all": {"missed": round(a["breaches"]["diff"], 1), "low": round(a["breaches"]["ci_low"], 1),
                "high": round(a["breaches"]["ci_high"], 1), "without_pct": round(a["breach_pct"]["without"], 2),
                "with_pct": round(a["breach_pct"]["with"], 2)},
        "how": f"Each fix was replayed on held-out days {plan['test_days'][0]}-{plan['test_days'][1]} with seeds "
               f"{', '.join(map(str, plan['seeds']))}: the same tickets and luck with and without it. "
               "Negative means fewer missed promises; the range is the 95% interval.",
        "recall": {"planted": r["patterns"]["recall"]["planted"], "found": r["patterns"]["recall"]["found"],
                   "blind_found": r["patterns"]["blind_recall"]["found"], "blind_planted": r["patterns"]["blind_recall"]["planted"]},
        "test_days": plan["test_days"],
        "days": test_days(plan["test_days"]),
    }))


@router.post("/plan/simulate")
def simulate(request: dict, user: dict = Depends(ADMIN)) -> JSONResponse:
    from server.app import plan_impact

    chosen = [c["item_id"] for c in rows("select item_id from plan_choices order by chosen_at")]
    if not chosen:
        return JSONResponse({"error": "Add at least one fix to the plan first."}, status_code=400)
    day = int(request.get("day", results()["plan"]["test_days"][0]))
    out = plan_impact({"day": day, "items": chosen})
    body = json.loads(out.body)
    if out.status_code == 200:
        rows("insert into plan_runs (day, items, result, run_by) values (%s, %s, %s, %s) returning id",
             (day, chosen, json.dumps(body), user["id"]))
    return JSONResponse(body, status_code=out.status_code)


@router.post("/plan/{item_id}")
def choose(item_id: str, request: dict, user: dict = Depends(ADMIN)) -> JSONResponse:
    if item_id not in {i["id"] for i in results()["plan"]["items"]}:
        return JSONResponse({"error": "no such fix"}, status_code=404)
    if request.get("chosen", True):
        rows("insert into plan_choices (item_id, chosen_by) values (%s, %s) on conflict (item_id) do nothing returning item_id",
             (item_id, user["id"]))
    else:
        rows("delete from plan_choices where item_id = %s returning item_id", (item_id,))
    return JSONResponse({"chosen": sorted(c["item_id"] for c in rows("select item_id from plan_choices"))})


@router.get("/plan/runs")
def plan_runs(user: dict = Depends(ADMIN)) -> JSONResponse:
    return JSONResponse(jsonable({"runs": rows(
        "select id, day, items, at, result->'without'->'breaches' as without, result->'with'->'breaches' as with_plan, "
        "result->>'weekday' as weekday from plan_runs order by id desc limit 10")}))


@router.get("/analysis")
def analysis(user: dict = Depends(ADMIN)) -> JSONResponse:
    r = results()
    t = r["food_1530"]["test"]
    names = {"baseline_d": "Skills routing (industry standard)", "least_slack_rescue": "Least slack first + rescue",
             "S2": "OpsLens"}
    metrics = {"turnaround.breach_pct": "Promises missed", "segment.p1_breach_pct": "Live orders (P1) missed",
               "segment.hindi_breach_pct": "Hindi tickets missed", "quality.p99_wait_min": "Longest waits (p99, min)",
               "quality.reopen_rate_pct": "Reopened"}
    policies = [{"key": k, "name": n, **{m: round(t["means"][k][m], 2) for m in metrics}} for k, n in names.items()]
    pairs = {}
    for label, key in (("vs skills routing", "S2 - baseline_d"), ("vs least slack + rescue", "S2 - least_slack_rescue")):
        p = t["paired"][key]
        pairs[label] = {m: {"diff": round(v["mean_diff"], 2), "low": round(v["ci_low"], 2), "high": round(v["ci_high"], 2)}
                        for m, v in p.items()}
    extra = {}
    for name in ("load_test", "local_llm_classification"):
        path = V2_RESULTS / f"{name}.json"
        if path.exists():
            extra[name] = json.loads(path.read_text(encoding="utf-8"))
    load = extra.get("load_test", {})
    llm = extra.get("local_llm_classification", {})
    return JSONResponse(jsonable({
        "headline": {"days": t["days"], "seeds": t["seeds"], "metrics": metrics, "policies": policies, "pairs": pairs,
                     "decision": t["decision"]},
        "models": {"risk_auc": round(r["risk"]["auc"], 3), "risk_real_auc": round(r["risk"]["realdata_auc"], 3),
                   "forecast_wape": round(r["forecast"]["wape_model"], 3), "forecast_naive_wape": round(r["forecast"]["wape_naive"], 3),
                   "forecast_cover_80": round(100 * r["forecast"]["coverage_80"], 1),
                   "classify_local": round(100 * r["classification"]["accuracy_local"], 2),
                   "classify_local_llm": round(100 * llm["sample"]["accuracy"], 2) if llm else None,
                   "classify_cloud_llm": round(100 * llm["sample"]["recorded_cloud_accuracy"], 2) if llm else None},
        "patterns": {"planted": r["patterns"]["recall"]["planted"], "found": r["patterns"]["recall"]["found"],
                     "blind_found": r["patterns"]["blind_recall"]["found"], "blind_planted": r["patterns"]["blind_recall"]["planted"]},
        "scale": {"tickets": load.get("loaded", {}).get("tickets"), "size": load.get("database_size"),
                  "queue_ms": load.get("queries", {}).get("open queue for one team (agent's team view)", {}).get("p50_ms"),
                  "rps": load.get("http", {}).get("requests_per_second"), "p95_ms": load.get("http", {}).get("p95_ms"),
                  "errors": load.get("http", {}).get("errors")},
    }))


@router.get("/team/{agent_code}")
def person(agent_code: str, user: dict = Depends(ADMIN)) -> JSONResponse:
    code = agent_code.upper()
    profile = rows("select agent_code, name, team, skills, languages, shift_start_hour, shift_hours from agent_profiles "
                   "where agent_code = %s", (code,))
    if not profile:
        return JSONResponse({"error": "no such agent"}, status_code=404)
    live = next((r for r in floor_rows() if r["id"] == code), None)
    today = rows("select count(*) filter (where status = 'solved') as solved, "
                 "count(*) filter (where status = 'solved' and not coalesce(breached, false)) as on_time, "
                 "count(*) filter (where status <> 'solved') as open from tickets "
                 f"where {TODAY} and assignee = %s", (code,))[0]
    recent = rows("select id, priority, category, status, sla_due_at, solved_at, breached, left(body, 90) as subject "
                  f"from tickets where {TODAY} and assignee = %s order by created_at desc limit 12", (code,))
    return JSONResponse(jsonable({"profile": profile[0], "live": live, "today": today, "recent": recent,
                                  "status_word": STATUS_WORD.get(live["status"], "") if live else "off shift",
                                  "working": bool(live and live["status"] in WORKING)}))
