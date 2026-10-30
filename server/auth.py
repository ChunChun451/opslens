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
USERNAMES = {"admin": "admin@opslens.demo"}
SESSION_HOURS = 12
MAX_FAILS = 5
FAIL_WINDOW_S = 60.0
router = APIRouter(prefix="/api/v2")
hasher = PasswordHasher()
NO_USER_HASH = hasher.hash(secrets.token_urlsafe(16))
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()


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
    out = JSONResponse({"user": public(user), "home": "/app/" if user["role"] == "admin" else "/app/#agent"})
    out.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="lax", path="/")
    return out


def checked(user: dict | None, password: str) -> bool:
    try:
        hasher.verify(user["password_hash"] if user else NO_USER_HASH, password)
        return user is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def plain(name: str) -> str:
    return " ".join(name.replace(".", " ").lower().split())


def find_agent(conn, name: str, team: str) -> dict | None:
    wanted = plain(name)
    if not wanted or not team:
        return None
    people = conn.execute("select u.*, p.name as profile_name from users u join agent_profiles p on p.agent_code = u.agent_code "
                          "where u.role = 'agent' and p.team = %s", (team.upper(),)).fetchall()
    exact = [u for u in people if plain(u["profile_name"]) == wanted or u["agent_code"].lower() == wanted]
    if exact:
        return exact[0]
    first = [u for u in people if plain(u["profile_name"]).split()[0] == wanted]
    return first[0] if len(first) == 1 else None


@router.get("/login/teams")
def teams() -> JSONResponse:
    with store.connection() as conn:
        return JSONResponse({"teams": conn.execute("select code, name from teams order by code").fetchall()})


@router.post("/login")
def login(request: dict) -> JSONResponse:
    password = str(request.get("password", ""))
    team = str(request.get("team", "")).strip().upper()
    as_agent = request.get("role") == "agent" or bool(team)
    name = str(request.get("name") or request.get("username") or request.get("email") or "").strip()
    key = f"agent:{team}:{plain(name)}" if as_agent else name.lower()
    if not name or not password or (as_agent and not team):
        return JSONResponse({"error": "your name, team and password are needed" if as_agent else "username and password are needed"},
                            status_code=400)
    if too_many_fails(key):
        return JSONResponse({"error": "too many tries, wait a minute"}, status_code=429)
    with store.connection() as conn:
        if as_agent:
            user = find_agent(conn, name, team)
        else:
            email = USERNAMES.get(name.lower(), name.lower())
            user = conn.execute("select * from users where email = %s", (email,)).fetchone()
    if not checked(user, password):
        note_fail(key)
        return JSONResponse({"error": "wrong name, team or password" if as_agent else "wrong username or password"}, status_code=401)
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
