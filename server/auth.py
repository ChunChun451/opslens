from __future__ import annotations

import hashlib
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse

from opslens import store

COOKIE = "opslens_session"
PICK_COOKIE = "opslens_pick"
PICK_MINUTES = 10
AGENT_LOGIN = "agent"
USERNAMES = {"admin": "admin@opslens.demo"}
SESSION_HOURS = 12
MAX_FAILS = 5
FAIL_WINDOW_S = 60.0
router = APIRouter(prefix="/api/v2")
hasher = PasswordHasher()
NO_USER_HASH = hasher.hash(secrets.token_urlsafe(16))
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()
_picks: dict[str, float] = {}
_picks_lock = threading.Lock()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def too_many_fails(email: str) -> bool:
    now = time.monotonic()
    with _fails_lock:
        recent = [t for t in _fails.get(email, []) if now - t < FAIL_WINDOW_S]
        _fails[email] = recent
        return len(recent) >= MAX_FAILS


def note_fail(email: str) -> None:
    with _fails_lock:
        _fails.setdefault(email, []).append(time.monotonic())


def public(user: dict) -> dict:
    return {k: user[k] for k in ("id", "email", "name", "role", "team", "agent_code")}


def current_user(opslens_session: str | None = Cookie(default=None)) -> dict:
    if not opslens_session:
        raise HTTPException(status_code=401, detail="log in first")
    with store.connection() as conn:
        user = conn.execute(
            "select u.* from sessions s join users u on u.id = s.user_id where s.token_hash = %s and s.expires_at > now()",
            (token_hash(opslens_session),)).fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="your session has ended, log in again")
    return public(user)


def require(*roles: str):
    def check(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="your role cannot open this")
        return user
    return check


def start_session(user: dict) -> JSONResponse:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    with store.connection() as conn:
        conn.execute("insert into sessions (token_hash, user_id, expires_at) values (%s, %s, %s)",
                     (token_hash(token), user["id"], expires))
        conn.execute("delete from sessions where expires_at < now()")
    out = JSONResponse({"user": public(user), "home": "/admin/" if user["role"] == "admin" else "/agent/"})
    out.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="lax", path="/")
    out.delete_cookie(PICK_COOKIE, path="/")
    return out


def checked(user: dict | None, password: str) -> bool:
    try:
        hasher.verify(user["password_hash"] if user else NO_USER_HASH, password)
        return user is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


@router.post("/login")
def login(request: dict) -> JSONResponse:
    name = str(request.get("username") or request.get("email") or "").strip().lower()
    password = str(request.get("password", ""))
    if not name or not password:
        return JSONResponse({"error": "username and password are needed"}, status_code=400)
    if too_many_fails(name):
        return JSONResponse({"error": "too many tries, wait a minute"}, status_code=429)
    with store.connection() as conn:
        if name == AGENT_LOGIN:
            user = conn.execute("select * from users where role = 'agent' order by id limit 1").fetchone()
        else:
            email = USERNAMES.get(name, name)
            user = conn.execute("select * from users where email = %s", (email,)).fetchone()
    if not checked(user, password):
        note_fail(name)
        return JSONResponse({"error": "wrong username or password"}, status_code=401)
    if name != AGENT_LOGIN:
        return start_session(user)
    token = secrets.token_urlsafe(32)
    with _picks_lock:
        now = time.monotonic()
        for key in [k for k, until in _picks.items() if until < now]:
            _picks.pop(key)
        _picks[token_hash(token)] = now + PICK_MINUTES * 60
    out = JSONResponse({"pick": True})
    out.set_cookie(PICK_COOKIE, token, max_age=PICK_MINUTES * 60, httponly=True, samesite="lax", path="/")
    return out


def pick_allowed(opslens_pick: str | None) -> bool:
    with _picks_lock:
        return bool(opslens_pick) and _picks.get(token_hash(opslens_pick), 0) > time.monotonic()


@router.get("/login/agents")
def on_shift(opslens_pick: str | None = Cookie(default=None)) -> JSONResponse:
    from server.v2 import WORKING, floor_rows, jsonable

    if not pick_allowed(opslens_pick):
        return JSONResponse({"error": "sign in as agent first"}, status_code=401)
    live = {r["id"]: r for r in floor_rows()}
    with store.connection() as conn:
        people = conn.execute("select p.agent_code, p.name, p.team, p.languages, p.shift_start_hour, p.shift_hours, t.name as team_name, "
                              "(select count(*) from tickets k where k.assignee = p.agent_code and k.status = 'solved' "
                              "and k.created_at >= current_date) as solved_today "
                              "from agent_profiles p join teams t on t.code = p.team order by p.agent_code").fetchall()
    order = {"busy": 0, "cross": 0, "wrong": 0, "idle": 1, "break": 2}
    out = []
    for p in people:
        r = live.get(p["agent_code"])
        status = r["status"] if r else "unknown"
        if live and status == "off":
            continue
        out.append({**p, "status": status, "working": status in WORKING,
                    "current": r.get("current") if r else None, "next": r.get("next") if r else None})
    out.sort(key=lambda a: (order.get(a["status"], 3), a["agent_code"]))
    return JSONResponse(jsonable({"agents": out, "live": bool(live)}))


@router.post("/login/pick")
def pick(request: dict, opslens_pick: str | None = Cookie(default=None)) -> JSONResponse:
    if not pick_allowed(opslens_pick):
        return JSONResponse({"error": "sign in as agent first"}, status_code=401)
    code = str(request.get("agent", "")).strip().lower()
    with store.connection() as conn:
        user = conn.execute("select * from users where role = 'agent' and lower(agent_code) = %s", (code,)).fetchone()
    if user is None:
        return JSONResponse({"error": "pick an agent from the list"}, status_code=400)
    with _picks_lock:
        _picks.pop(token_hash(opslens_pick), None)
    return start_session(user)


@router.post("/logout")
def logout(opslens_session: str | None = Cookie(default=None)) -> JSONResponse:
    if opslens_session:
        with store.connection() as conn:
            conn.execute("delete from sessions where token_hash = %s", (token_hash(opslens_session),))
    out = JSONResponse({"ok": True})
    out.delete_cookie(COOKIE, path="/")
    return out


@router.get("/me")
def me(user: dict = Depends(current_user)) -> JSONResponse:
    return JSONResponse({"user": user})
