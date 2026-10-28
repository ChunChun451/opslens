from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results.json"
FIXTURE = ROOT / "eval" / "fixture_results.json"

app = FastAPI(title="OpsLens", docs_url="/api/docs")


def results_path() -> Path:
    return RESULTS if RESULTS.exists() else FIXTURE


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/app/")


@app.get("/api/health")
def health() -> dict:
    path = results_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"ok": True, "results": str(path.relative_to(ROOT)).replace("\\", "/"), "fixture": data["meta"]["fixture"]}


@app.get("/api/results")
def results() -> JSONResponse:
    data = json.loads(results_path().read_text(encoding="utf-8"))
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


_CACHE: dict = {}


def engine_inputs() -> dict:
    if not _CACHE:
        import pandas as pd

        from opslens import risk
        from opslens.config import load_config
        from opslens.world import load_agents

        from opslens.policies import handle_lognormal

        generated = ROOT / "data" / "generated"
        preds = pd.read_csv(generated / "predictions.csv", usecols=["ticket_id", "pred_final"])
        calendar = load_config("calendar")
        splits = calendar["splits"]
        history = pd.read_csv(generated / "history.csv", usecols=["created_at", "final_category", "channel",
                                                                 "handled_min", "reopens", "resolution_min"])
        _CACHE.update({
            "handle_dist": handle_lognormal(history, calendar["start_date"], last_day=splits["train_last_day"]),
            "tickets": pd.read_csv(generated / "world_tickets.csv"),
            "preds": dict(zip(preds["ticket_id"], preds["pred_final"])),
            "agents": load_agents(),
            "model": risk.load(generated / "models"),
            "weights": load_config("optimizer"),
            "test_days": (splits["validation_last_day"] + 1, splits["test_last_day"]),
        })
    return _CACHE


@app.post("/api/whatif")
def whatif(request: dict) -> JSONResponse:
    from opslens.whatif import run_whatif

    inputs = engine_inputs()
    try:
        answer = run_whatif(request, inputs["tickets"], inputs["agents"], inputs["preds"], inputs["model"],
                            inputs["weights"], inputs["test_days"])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(answer)


PLAN_SEEDS = [1, 2, 3]
_PLAN_POOL: ProcessPoolExecutor | None = None
_PLAN_RUNS: dict = {}
_PLAN_LOCK = threading.Lock()


def plan_job(job: dict) -> dict:
    from opslens.plan import run_plan_day

    return run_plan_day(engine_inputs(), job)


def run_plan_jobs(jobs: list[dict]) -> list[dict]:
    global _PLAN_POOL
    keys = [(j["day"], j["seed"], json.dumps(j["items"], sort_keys=True)) for j in jobs]
    with _PLAN_LOCK:
        todo = {key: job for key, job in zip(keys, jobs) if key not in _PLAN_RUNS}
        if todo:
            if _PLAN_POOL is None:
                _PLAN_POOL = ProcessPoolExecutor(max_workers=2 * len(PLAN_SEEDS))
            try:
                runs = list(_PLAN_POOL.map(plan_job, list(todo.values())))
            except Exception:
                _PLAN_POOL.shutdown(cancel_futures=True)
                _PLAN_POOL = None
                raise
            _PLAN_RUNS.update(zip(todo, runs))
        return [_PLAN_RUNS[key] for key in keys]


@app.post("/api/plan/impact")
def plan_impact(request: dict) -> JSONResponse:
    import pandas as pd

    from opslens.config import load_config
    from opslens.plan import check_ids, impact_answer, plan_jobs
    from opslens.whatif import check_day

    plan = json.loads(results_path().read_text(encoding="utf-8")).get("plan")
    if not plan:
        return JSONResponse({"error": "results.json has no plan items yet: run make eval"}, status_code=503)
    calendar = load_config("calendar")
    test_days = (calendar["splits"]["validation_last_day"] + 1, calendar["splits"]["test_last_day"])
    first_weekday = pd.Timestamp(calendar["start_date"]).weekday()
    try:
        day = int(request.get("day", test_days[0]))
        check_day(day, test_days)
        items = check_ids(request.get("items", []), plan["items"])
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    started = time.perf_counter()
    without, with_plan = plan_jobs(items, day, PLAN_SEEDS, plan["alerts_used"], first_weekday)
    runs = run_plan_jobs(without + with_plan)
    answer = impact_answer(items, day, PLAN_SEEDS, first_weekday, runs[:len(without)], runs[len(without):],
                           time.perf_counter() - started)
    return JSONResponse(answer)


@app.post("/api/upload")
async def upload(mapping: str = Form("{}"), file: UploadFile | None = File(None),
                 example: str | None = Form(None)) -> JSONResponse:
    from server.upload import analyse_csv, analyse_uci

    try:
        if file is None or example == "uci_incidents":
            return JSONResponse(analyse_uci())
        return JSONResponse(analyse_csv(await file.read(), json.loads(mapping)))
    except (ValueError, KeyError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/anyfile/peek")
async def anyfile_peek(file: UploadFile | None = File(None), example: str | None = Form(None)) -> JSONResponse:
    from server.anyfile_jobs import keep_example, keep_file

    try:
        if example == "uci_incidents" or file is None:
            return JSONResponse(keep_example())
        return JSONResponse(keep_file(await file.read(), file.filename or "uploaded file"))
    except FileNotFoundError:
        return JSONResponse({"error": "the UCI example is not on this laptop yet; run `mingw32-make data` once"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/anyfile/check")
def anyfile_check(request: dict) -> JSONResponse:
    from server.anyfile_jobs import check

    try:
        target = request.get("target_min")
        return JSONResponse(check(str(request["token"]), dict(request.get("mapping") or {}),
                                  float(target) if target not in (None, "") else None))
    except (ValueError, KeyError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/anyfile/run")
def anyfile_run(request: dict) -> JSONResponse:
    from server.anyfile_jobs import start_job

    try:
        target = request.get("target_min")
        return JSONResponse(start_job(str(request["token"]), dict(request.get("mapping") or {}),
                                      float(target) if target not in (None, "") else None,
                                      bool(request.get("target_assumed", False))))
    except (ValueError, KeyError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/anyfile/job/{job_id}")
def anyfile_job(job_id: str) -> JSONResponse:
    from server.anyfile_jobs import job_state

    try:
        return JSONResponse(job_state(job_id))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


@app.post("/api/anyfile/effect")
def anyfile_effect(request: dict) -> JSONResponse:
    from server.anyfile_jobs import effect

    try:
        return JSONResponse(effect(str(request["job"]), list(request.get("groups") or []), bool(request.get("warn", False)),
                                   float(request.get("save", 0.5))))
    except (ValueError, KeyError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/plant")
def plant(request: dict) -> JSONResponse:
    from server.plant_demo import run_plant

    try:
        return JSONResponse(run_plant(request))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def _route_client():
    from opslens.llm.base import LLMUnavailable
    from opslens.llm.client import build_client

    try:
        return build_client(["groq_route", "gemini"])
    except LLMUnavailable:
        return None


def _run_ask(question: str, client) -> dict:
    import pandas as pd

    from opslens.ask import answer
    from opslens.config import load_config
    from opslens.whatif import run_whatif
    from server.plant_demo import run_plant

    inputs = engine_inputs()
    tools = {
        "whatif": lambda req: run_whatif(req, inputs["tickets"], inputs["agents"], inputs["preds"], inputs["model"],
                                         inputs["weights"], inputs["test_days"]),
        "plant": run_plant,
    }
    results = json.loads(results_path().read_text(encoding="utf-8"))
    first_weekday = pd.Timestamp(load_config("calendar")["start_date"]).weekday()
    return answer(question, client, tools, results, inputs["test_days"], first_weekday)


@app.post("/api/ask")
def ask(request: dict) -> JSONResponse:
    question = str(request.get("question", "")).strip()[:300]
    if not question:
        return JSONResponse({"error": "empty question"}, status_code=400)
    try:
        return JSONResponse(_run_ask(question, _route_client()))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/bot/warm")
def bot_warm() -> dict:
    from server.bot import warm_up

    warm_up()
    return {"ok": True}


@app.post("/api/bot")
def bot(request: dict) -> JSONResponse:
    from server.bot import respond

    question = str(request.get("question", "")).strip()[:400]
    if not question:
        return JSONResponse({"error": "empty question"}, status_code=400)
    client = _route_client()
    results = json.loads(results_path().read_text(encoding="utf-8"))
    try:
        return JSONResponse(respond(question, lambda q: _run_ask(q, client), results, client))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


_LIVE: dict = {}
_LIVE_BUILDING: dict = {}
_LIVE_LOCK = threading.Lock()


def _live_key(weekday: int, seed: int) -> tuple[int, int]:
    import pandas as pd

    from opslens.config import load_config
    from opslens.live import matching_test_day

    first_weekday = pd.Timestamp(load_config("calendar")["start_date"]).weekday()
    return matching_test_day(weekday, first_weekday, engine_inputs()["test_days"]), seed


_LIVE_BUILD_ONE_AT_A_TIME = threading.Lock()


def _build_live(key: tuple) -> None:
    from opslens.live import simulate_live_day

    day, seed, agents_delta, volume, log = key
    try:
        with _LIVE_BUILD_ONE_AT_A_TIME:
            _LIVE[key] = simulate_live_day(engine_inputs(), day, seed, dict(agents_delta), volume,
                                           actions=tuple(dict(a) for a in log))
    finally:
        _LIVE_BUILDING.pop(key, None)


_ACTIONS: dict = {}
ACTION_KINDS = ("take", "decline", "done", "extra_time", "break", "back")
ACTION_AHEAD_MIN = 60.0
ACTION_DAYS_KEPT = 6
_WAITING = {"actions": 0}


def _log_key(log: list[dict]) -> tuple:
    return tuple(tuple(sorted(a.items())) for a in log)


def _count_waiting(step: int) -> None:
    with _LIVE_LOCK:
        _WAITING["actions"] += step


def _action_waiting() -> bool:
    return _WAITING["actions"] > 0


def _finish_live(key: tuple) -> None:
    from opslens.live import finish_day

    try:
        while True:
            while _action_waiting():
                time.sleep(0.05)
            with _LIVE_BUILD_ONE_AT_A_TIME:
                partial = _LIVE.get(key)
                if partial is None or partial.complete:
                    return
                _LIVE[key] = finish_day(partial, _action_waiting)
                if _LIVE[key].complete:
                    _refresh_effects(key[0], key[1])
    finally:
        _LIVE_BUILDING.pop(key, None)


def _refresh_effects(day: int, seed: int) -> None:
    from opslens.live import relink

    with _LIVE_LOCK:
        mine = {k[4]: v for k, v in _LIVE.items() if len(k) == 5 and k[:4] == (day, seed, (), 1.0)}
    for log in sorted(mine, key=len):
        parent = mine.get(log[:-1]) if log else None
        if parent is not None:
            relink(mine[log], parent)


def _wait_complete(key: tuple, seconds: float = 60.0):
    thread = _LIVE_BUILDING.get(key)
    if thread is not None:
        thread.join(seconds)
    return _LIVE.get(key)


def _new_action(request: dict, current, minute: float, log: list[dict] | None = None) -> dict:
    from opslens.live import state_at

    kind, agent = request.get("kind"), str(request.get("agent") or "")
    if kind not in ACTION_KINDS:
        raise ValueError(f"kind is one of {', '.join(ACTION_KINDS)}")
    row = next((r for r in state_at(current, minute)["floor"] if r["id"] == agent), None)
    if row is None:
        raise ValueError("unknown agent")
    action = {"kind": kind, "agent": agent, "minute": round(minute, 2)}
    if kind in ("done", "extra_time"):
        if row["current"] is None:
            raise ValueError("Nothing in progress for this agent right now.")
        action["ticket_id"] = row["current"]["ticket_id"]
        action["started"] = row["current"]["assigned_at"]
        jobs = [j for j in current.work.get(agent, []) if j["ticket_id"] == action["ticket_id"]
                and j["minute"] <= current.start + minute]
        job = jobs[-1] if jobs else None
        action["cross"] = bool(job and "cross-skill" in job["reason"])
        if job and job["resolved"] is not None:
            action["planned_end"] = round(job["resolved"] - current.start, 2)
        if kind == "extra_time":
            extra = float(request.get("value") or 0)
            if not 1 <= extra <= 60:
                raise ValueError("extra time is 1-60 minutes")
            action["value"] = extra
        elif request.get("value") is not None:
            action["value"] = max(minute, min(1440.0, float(request["value"])))
    elif kind in ("decline", "take"):
        ticket = str(request.get("ticket_id") or "")
        if ticket not in current.context["index"]:
            raise ValueError("unknown ticket")
        action["ticket_id"] = ticket
        action["reason"] = str(request.get("reason") or "")[:60]
    elif kind == "break" and (row["status"] in ("off", "break") or _on_break(log or [], agent)):
        raise ValueError("This agent is not on shift or is already on a break.")
    elif kind == "back" and not _on_break(log or [], agent):
        raise ValueError("This agent is not on a break.")
    return action


def _on_break(log: list[dict], agent: str) -> bool:
    moves = [a["kind"] for a in log if a["agent"] == agent and a["kind"] in ("break", "back")]
    return bool(moves) and moves[-1] == "break"


@app.post("/api/live/action")
def live_action(request: dict) -> JSONResponse:
    from opslens.live import outcome_at, simulated_until, with_actions

    try:
        weekday, seed, minute = int(request.get("weekday", -1)), int(request.get("seed", 1)), float(request.get("minute", -1))
        if not (0 <= weekday <= 6 and 0 <= minute < 1440 and 1 <= seed <= 99):
            raise ValueError("weekday 0-6, minute 0-1439, seed 1-99")
        day, seed = _live_key(weekday, seed)
        log = list(_ACTIONS.get((day, seed), []))
        key = (day, seed, (), 1.0, _log_key(log))
        current = _LIVE.get(key)
        if current is None or simulated_until(current) < current.start + minute:
            current = _wait_complete(key)
        if current is None:
            return JSONResponse({"error": "Today is still being simulated. Try again in a few seconds."}, status_code=409)
        action = _new_action(request, current, minute, log)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    started = time.perf_counter()
    _count_waiting(1)
    try:
        with _LIVE_BUILD_ONE_AT_A_TIME:
            partial = with_actions(_LIVE.get(key) or current, log + [action], ahead_min=ACTION_AHEAD_MIN)
    finally:
        _count_waiting(-1)
    seconds = round(time.perf_counter() - started, 2)
    new_key = (day, seed, (), 1.0, _log_key(log + [action]))
    with _LIVE_LOCK:
        _ACTIONS[(day, seed)] = log + [action]
        _LIVE[new_key] = partial
        _forget_old_actions(day, seed)
        if not partial.complete:
            thread = threading.Thread(target=_finish_live, args=(new_key,), daemon=True)
            _LIVE_BUILDING[new_key] = thread
            thread.start()
    effect = partial.effects[-1]
    return JSONResponse({"ok": True, "seconds": seconds, "actions": len(log) + 1,
                         "effect": {**effect, "outcome": outcome_at(effect.get("went_to"), minute)}})


def _forget_old_actions(day: int, seed: int) -> None:
    mine = [k for k in _LIVE if len(k) == 5 and k[0] == day and k[1] == seed and k[4]]
    for k in mine[:-ACTION_DAYS_KEPT]:
        if k not in _LIVE_BUILDING:
            _LIVE.pop(k, None)


@app.get("/api/live/actions")
def live_actions(weekday: int, seed: int = 1) -> JSONResponse:
    if not (0 <= weekday <= 6 and 1 <= seed <= 99):
        return JSONResponse({"error": "weekday 0-6, seed 1-99"}, status_code=400)
    day, seed = _live_key(weekday, seed)
    return JSONResponse({"day": day, "seed": seed, "actions": _ACTIONS.get((day, seed), [])})


@app.post("/api/live/reset")
def live_reset(request: dict) -> JSONResponse:
    try:
        weekday, seed = int(request.get("weekday", -1)), int(request.get("seed", 1))
    except (TypeError, ValueError):
        weekday, seed = -1, 1
    if not (0 <= weekday <= 6 and 1 <= seed <= 99):
        return JSONResponse({"error": "weekday 0-6, seed 1-99"}, status_code=400)
    day, seed = _live_key(weekday, seed)
    with _LIVE_LOCK:
        cleared = len(_ACTIONS.pop((day, seed), []))
    return JSONResponse({"ok": True, "cleared": cleared})


def _parse_agents(text: str) -> tuple:
    out = {}
    for part in filter(None, text.split(",")):
        team, _, k = part.partition(":")
        team = team.strip().upper()
        if len(team) != 1 or team not in "ABCD":
            raise ValueError("teams are A, B, C, D")
        if int(k):
            out[team] = max(-5, min(5, int(k)))
    return tuple(sorted(out.items()))


@app.get("/api/live")
def live(weekday: int, minute: float, seed: int = 1, agents: str = "", volume: float = 1.0) -> JSONResponse:
    from opslens.live import state_at

    try:
        delta = _parse_agents(agents)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if not (0 <= weekday <= 6 and 0 <= minute < 1440 and 1 <= seed <= 99 and 0.5 <= volume <= 2.0):
        return JSONResponse({"error": "weekday 0-6, minute 0-1439, seed 1-99, volume 0.5-2.0"}, status_code=400)
    day, seed = _live_key(weekday, seed)
    log = _ACTIONS.get((day, seed), [])
    key = (day, seed, delta, round(volume, 2), _log_key(log))
    with _LIVE_LOCK:
        if key not in _LIVE and key not in _LIVE_BUILDING:
            thread = threading.Thread(target=_build_live, args=(key,), daemon=True)
            _LIVE_BUILDING[key] = thread
            thread.start()
    scenario = {"agents_delta": dict(delta), "volume": round(volume, 2), "actions": len(log)}
    if key not in _LIVE:
        return JSONResponse({"ready": False, "day": day, "seed": seed, "scenario": scenario})
    live_day = _LIVE[key]
    return JSONResponse({"ready": True, "scenario": scenario, "complete": live_day.complete, **state_at(live_day, minute)},
                        headers={"Cache-Control": "no-store"})


@app.on_event("startup")
def warm_live_now() -> None:
    import datetime

    try:
        day, seed = _live_key(datetime.datetime.now().weekday(), 1)
    except Exception:
        return
    key = (day, seed, (), 1.0, ())
    with _LIVE_LOCK:
        if key not in _LIVE and key not in _LIVE_BUILDING:
            thread = threading.Thread(target=_build_live, args=(key,), daemon=True)
            _LIVE_BUILDING[key] = thread
            thread.start()


@app.middleware("http")
async def always_fresh_web_files(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/web", "/app")):
        response.headers["Cache-Control"] = "no-cache"
    if request.url.path in ("/web", "/web/", "/web/index.html", "/app", "/app/", "/app/index.html"):
        response.headers["Clear-Site-Data"] = '"cache"'
    return response


app.mount("/app", StaticFiles(directory=ROOT / "web", html=True), name="app")
app.mount("/web", StaticFiles(directory=ROOT / "web", html=True), name="web")
app.mount("/eval", StaticFiles(directory=ROOT / "eval"), name="eval")
