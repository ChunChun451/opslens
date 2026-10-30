from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from opslens import feedback, store
from server.v2 import ADMIN, AGENT_ONLY, jsonable

log = logging.getLogger("opslens.feedback")
router = APIRouter(prefix="/api/v2")


def refresh_rag() -> None:
    def run():
        try:
            from opslens.rag import refresh_feedback

            refresh_feedback()
        except Exception as error:
            log.warning("feedback not added to the RAG library: %s", error)

    threading.Thread(target=run, daemon=True).start()


@router.get("/feedback")
def all_feedback(user: dict = Depends(ADMIN)) -> JSONResponse:
    with store.connection() as conn:
        return JSONResponse(jsonable(feedback.summary(conn)))


@router.post("/feedback")
def add_feedback(request: dict, user: dict = Depends(ADMIN)) -> JSONResponse:
    with store.connection() as conn:
        item, error = feedback.add(conn, request, user)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    if item["source"] == "customer":
        refresh_rag()
    return JSONResponse(jsonable({"item": item}))


@router.get("/feedback/agent/{agent_code}")
def agent_feedback(agent_code: str, user: dict = Depends(ADMIN)) -> JSONResponse:
    with store.connection() as conn:
        return JSONResponse(jsonable(feedback.mine(conn, agent_code.upper())))


@router.get("/me/feedback")
def my_feedback(user: dict = Depends(AGENT_ONLY)) -> JSONResponse:
    with store.connection() as conn:
        return JSONResponse(jsonable(feedback.mine(conn, user["agent_code"])))


@router.post("/me/feedback/seen")
def seen(user: dict = Depends(AGENT_ONLY)) -> JSONResponse:
    with store.connection() as conn:
        return JSONResponse({"marked": feedback.mark_seen(conn, user["agent_code"])})
