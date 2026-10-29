from __future__ import annotations

import hashlib
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from opslens import store

COOKIE = "opslens_session"
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


@router.post("/login")
def login(request: dict, response: Response) -> JSONResponse:
    email = str(request.get("email", "")).strip().lower()
    password = str(request.get("password", ""))
    if not email or not password:
        return JSONResponse({"error": "email and password are needed"}, status_code=400)
    if too_many_fails(email):
        return JSONResponse({"error": "too many tries, wait a minute"}, status_code=429)
    with store.connection() as conn:
        user = conn.execute("select * from users where email = %s", (email,)).fetchone()
        try:
            hasher.verify(user["password_hash"] if user else NO_USER_HASH, password)
            if user is None:
                raise VerifyMismatchError
        except (VerifyMismatchError, InvalidHashError):
            note_fail(email)
            return JSONResponse({"error": "wrong email or password"}, status_code=401)
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
        conn.execute("insert into sessions (token_hash, user_id, expires_at) values (%s, %s, %s)",
                     (token_hash(token), user["id"], expires))
        conn.execute("delete from sessions where expires_at < now()")
    out = JSONResponse({"user": public(user), "home": "/admin/" if user["role"] in ("admin", "lead") else "/agent/"})
    out.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="lax", path="/")
    return out


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
