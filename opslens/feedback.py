from __future__ import annotations

from opslens.config import load_config
from opslens.privacy import mask_pii

MAX_BODY = 1000
UNHAPPY = 2
HAPPY = 4
FRESH_DAYS = 2
LATEST = 200
CUSTOMER_AUTHOR = "Customer (entered by hand)"
CATEGORIES = ("late_delivery", "missing_item", "wrong_item", "refund", "payment_failure", "app_bug", "account", "restaurant_partner")

ITEM = ("select f.id, f.source, f.agent_code, p.name as agent_name, f.team, t.name as team_name, f.category, f.rating, f.body, "
        "f.author_name, f.created_at, f.seen_at from feedback f join agent_profiles p on p.agent_code = f.agent_code "
        "left join teams t on t.code = f.team")


def words(key: str | None) -> str:
    return (key or "").replace("_", " ")


def seed_feedback(conn) -> int:
    book = load_config("feedback")
    admin = conn.execute("select id, name from users where role = 'admin' order by id limit 1").fetchone()
    entries = [("customer", e) for e in book.get("customer", [])] + [("admin", e) for e in book.get("admin", [])]
    for source, e in entries:
        conn.execute(
            "insert into feedback (source, agent_code, team, category, rating, body, author_id, author_name, seed_key, created_at, seen_at) "
            "select %s, p.agent_code, p.team, %s, %s, %s, %s, %s, %s, w.made, case when %s >= %s then w.made + interval '1 hour' end "
            "from agent_profiles p, (select least(current_date - %s * interval '1 day' + %s * interval '1 hour', now() - interval '5 minutes') as made) w "
            "where p.agent_code = %s on conflict (seed_key) do nothing",
            (source, e.get("category"), e.get("rating"), " ".join(str(e["text"]).split()),
             admin["id"] if source == "admin" and admin else None,
             (admin["name"] if admin else "Ops admin") if source == "admin" else CUSTOMER_AUTHOR,
             f"seed:{e['key']}", int(e["days_ago"]), FRESH_DAYS, int(e["days_ago"]), int(e.get("hour", 12)), e["agent"]))
    return len(entries)


def clean_body(text: str, source: str) -> str:
    body = " ".join(str(text or "").split())[:MAX_BODY]
    return mask_pii(body).text if source == "customer" else body


def add(conn, request: dict, author: dict) -> tuple[dict | None, str]:
    source = request.get("source", "customer")
    if source not in ("customer", "admin"):
        return None, "feedback comes from a customer or from the admin"
    agent = conn.execute("select agent_code, team from agent_profiles where agent_code = %s",
                         (str(request.get("agent", "")).upper(),)).fetchone()
    if agent is None:
        return None, "choose the agent this feedback is about"
    rating = request.get("rating")
    try:
        rating = int(rating) if rating not in (None, "") else None
    except (TypeError, ValueError):
        return None, "the rating goes from 1 to 5"
    if rating is not None and not 1 <= rating <= 5:
        return None, "the rating goes from 1 to 5"
    if source == "customer" and rating is None:
        return None, "a customer's feedback needs a rating from 1 to 5"
    category = request.get("category") or None
    if category is not None and category not in CATEGORIES:
        return None, "unknown kind of complaint"
    body = clean_body(request.get("body"), source)
    if not body:
        return None, "write what was said first"
    row = conn.execute(
        "insert into feedback (source, agent_code, team, category, rating, body, author_id, author_name) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s) returning id",
        (source, agent["agent_code"], agent["team"], category, rating, body, author["id"],
         author["name"] if source == "admin" else CUSTOMER_AUTHOR)).fetchone()
    return conn.execute(ITEM + " where f.id = %s", (row["id"],)).fetchone(), ""


def stats(rows: list[dict]) -> dict:
    rated = [r["rating"] for r in rows if r["rating"] is not None]
    return {"count": len(rated), "average": round(sum(rated) / len(rated), 1) if rated else None,
            "unhappy": sum(1 for x in rated if x <= UNHAPPY), "happy": sum(1 for x in rated if x >= HAPPY)}


def grouped(rows: list[dict], key: str, extra) -> list[dict]:
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    out = [{key: k, **extra(v), **stats(v)} for k, v in groups.items()]
    return sorted(out, key=lambda g: (g["average"] if g["average"] is not None else 9, -g["count"]))


def worst(rows: list[dict]) -> dict | None:
    low = sorted(rows, key=lambda r: (r["rating"], -r["created_at"].timestamp()))
    return {"rating": low[0]["rating"], "body": low[0]["body"], "agent_name": low[0]["agent_name"]} if low else None


def summary(conn) -> dict:
    items = conn.execute(ITEM + " order by f.created_at desc").fetchall()
    customer = [r for r in items if r["source"] == "customer"]
    return {
        "customer": {**stats(customer), "by_rating": {str(s): sum(1 for r in customer if r["rating"] == s) for s in range(1, 6)}},
        "admin_notes": sum(1 for r in items if r["source"] == "admin"),
        "teams": grouped(customer, "team", lambda v: {"team_name": v[0]["team_name"]}),
        "agents": grouped(customer, "agent_code", lambda v: {"agent_name": v[0]["agent_name"], "team": v[0]["team"]}),
        "themes": grouped(customer, "category", lambda v: {"label": words(v[0]["category"]).capitalize(), "worst": worst(v)}),
        "items": items[:LATEST],
        "agents_all": conn.execute("select agent_code, name, team from agent_profiles order by team, agent_code").fetchall(),
        "categories": list(CATEGORIES),
    }


def mine(conn, agent_code: str) -> dict:
    items = conn.execute(ITEM + " where f.agent_code = %s order by f.created_at desc", (agent_code,)).fetchall()
    return {"customer": stats([r for r in items if r["source"] == "customer"]),
            "unseen": sum(1 for r in items if r["seen_at"] is None), "items": items[:LATEST]}


def mark_seen(conn, agent_code: str) -> int:
    return conn.execute("update feedback set seen_at = now() where agent_code = %s and seen_at is null", (agent_code,)).rowcount


def chunks(conn) -> list[dict]:
    rows = conn.execute(ITEM + " where f.source = 'customer' order by f.id").fetchall()
    if not rows:
        return []
    out = [{"source": "feedback", "ref": f"feedback:{r['id']}",
            "title": f"Customer feedback on {r['agent_name']}, {words(r['category']) or 'a ticket'}",
            "body": (f"A customer rated {r['agent_name']} (Team {r['team']}, {r['team_name']}) {r['rating']} out of 5 for a "
                     f"{words(r['category']) or 'support'} ticket and wrote: \"{r['body']}\". Entered by hand."),
            "link": "#feedback", "card": None} for r in rows]
    s = stats(rows)
    themes = grouped(rows, "category", lambda v: {"label": words(v[0]["category"])})
    teams = grouped(rows, "team", lambda v: {"team_name": v[0]["team_name"]})
    body = (f"Customer feedback, entered by hand because the floor's customers are simulated: {s['count']} reviews, an average of "
            f"{s['average']} out of 5; {s['unhappy']} unhappy (rated 1 or 2) and {s['happy']} happy (rated 4 or 5). By kind of complaint, "
            "worst first: " + "; ".join(f"{t['label']} {t['average']} out of 5 from {t['count']} reviews, {t['unhappy']} unhappy" for t in themes)
            + ". By team, worst first: " + "; ".join(f"Team {t['team']} ({t['team_name']}) {t['average']} out of 5 from {t['count']} reviews"
                                                  for t in teams) + ".")
    out.append({"source": "feedback", "ref": "feedback:summary", "title": "What customers say: feedback summary", "body": body,
                "link": "#feedback", "card": None})
    return out
