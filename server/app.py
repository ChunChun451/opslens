"""The OpsLens web server: serves the dashboard and the results, and runs live simulations.

Run:  mingw32-make serve     → http://localhost:8000/

Why this design:
- The dashboard (web/) only reads numbers from `GET /api/results`, which returns
  eval/results.json — the one file every number comes from. If it does not exist yet, the
  fixture file is returned instead, and the UI shows its red FIXTURE banner.
- Everything runs locally: no network calls at serve time (LLM answers are already cached),
  so the demo works with Wi-Fi off.
- Live endpoints (What-if M10, Plant-a-problem M11, Upload M10) are added as their milestones land.
- "Live now" (GET /api/live, 24 Oct): today's weekday simulated once on this laptop (both the industry
  standard and OpsLens), then shown minute by minute at the viewer's real clock (opslens/live.py).
- "Your plan" (POST /api/plan/impact, 19 Oct): the accepted recommendations are replayed on one
  test day with and without them. Each run takes ~20 s, so the runs go to a few worker processes
  in parallel and every finished run is kept in memory (the same run is never simulated twice).

Example: curl http://localhost:8000/api/health  →  {"ok": true, "results": "eval/results.json", "fixture": false}
"""

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
    # /app/ serves the same files as /web/. It is the address people open now: a browser that
    # cached /web/ files before the no-cache header existed kept running them (24 Oct); under a
    # new address it has nothing cached, so it always loads the current dashboard.
    return RedirectResponse("/app/")


@app.get("/api/health")
def health() -> dict:
    path = results_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"ok": True, "results": str(path.relative_to(ROOT)).replace("\\", "/"), "fixture": data["meta"]["fixture"]}


@app.get("/api/results")
def results() -> JSONResponse:
    # Read on every request: re-running `make eval` updates the dashboard without a restart.
    data = json.loads(results_path().read_text(encoding="utf-8"))
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


_CACHE: dict = {}  # tickets, predictions, risk model and weights, loaded once on first use


def engine_inputs() -> dict:
    if not _CACHE:
        import pandas as pd

        from opslens import risk
        from opslens.config import load_config
        from opslens.world import load_agents

        generated = ROOT / "data" / "generated"
        preds = pd.read_csv(generated / "predictions.csv", usecols=["ticket_id", "pred_final"])
        splits = load_config("calendar")["splits"]
        _CACHE.update({
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
    """Re-run one test day with the judge's changes (see opslens/whatif.py)."""
    from opslens.whatif import run_whatif

    inputs = engine_inputs()
    try:
        answer = run_whatif(request, inputs["tickets"], inputs["agents"], inputs["preds"], inputs["model"],
                            inputs["weights"], inputs["test_days"])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(answer)


PLAN_SEEDS = [1, 2, 3]  # live plan runs: 3 seeds, without and with the plan = 6 runs side by side
_PLAN_POOL: ProcessPoolExecutor | None = None
_PLAN_RUNS: dict = {}  # (day, seed, accepted items) -> finished run
_PLAN_LOCK = threading.Lock()  # one plan request at a time: they share the pool and the memory


def plan_job(job: dict) -> dict:
    """One plan simulation (opslens/plan.py). Runs in a worker process, which loads the engine
    inputs once and keeps them for later requests."""
    from opslens.plan import run_plan_day

    return run_plan_day(engine_inputs(), job)


def run_plan_jobs(jobs: list[dict]) -> list[dict]:
    """Results for the jobs, from memory if this exact run was done before, else simulated in
    parallel. The "without" runs of a day are shared by every plan asked for that day."""
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
                _PLAN_POOL.shutdown(cancel_futures=True)  # e.g. a worker died: start fresh next time
                _PLAN_POOL = None
                raise
            _PLAN_RUNS.update(zip(todo, runs))
        return [_PLAN_RUNS[key] for key in keys]


@app.post("/api/plan/impact")
def plan_impact(request: dict) -> JSONResponse:
    """What the accepted recommendations would change on one test day (opslens/plan.py).
    Request: {"day": 48, "items": ["staff_43_C02", "pb_F2"]}. Unknown ids → 400."""
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
    """Run the analysis on an uploaded export, or on the UCI example (server/upload.py)."""
    from server.upload import analyse_csv, analyse_uci

    try:
        if file is None or example == "uci_incidents":
            return JSONResponse(analyse_uci())
        return JSONResponse(analyse_csv(await file.read(), json.loads(mapping)))
    except (ValueError, KeyError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/anyfile/peek")
async def anyfile_peek(file: UploadFile | None = File(None), example: str | None = Form(None)) -> JSONResponse:
    """OpsLens on your file, step 1: keep the CSV, return its columns and a suggested mapping."""
    from server.anyfile_jobs import keep_example, keep_file

    try:
        if example == "uci_incidents" or file is None:
            return JSONResponse(keep_example())
        return JSONResponse(keep_file(await file.read(), file.filename or "uploaded file"))
    except FileNotFoundError:
        return JSONResponse({"error": "the UCI example is not on this laptop yet; run `mingw32-make data` once"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/anyfile/run")
def anyfile_run(request: dict) -> JSONResponse:
    """Step 2: start the report for {token, mapping, target_min}; returns {job}."""
    from server.anyfile_jobs import start_job

    try:
        target = request.get("target_min")
        return JSONResponse(start_job(str(request["token"]), dict(request.get("mapping") or {}),
                                      float(target) if target not in (None, "") else None))
    except (ValueError, KeyError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/anyfile/job/{job_id}")
def anyfile_job(job_id: str) -> JSONResponse:
    """Step 3: poll the job: {status, step, steps, elapsed, result | error}."""
    from server.anyfile_jobs import job_state

    try:
        return JSONResponse(job_state(job_id))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


@app.post("/api/plant")
def plant(request: dict) -> JSONResponse:
    """Hide the judge's problem in fresh data and see whether OpsLens finds it (server/plant_demo.py)."""
    from server.plant_demo import run_plant

    try:
        return JSONResponse(run_plant(request))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def _route_client():
    """The LLM used only to understand questions (routing), or None when offline."""
    from opslens.llm.base import LLMUnavailable
    from opslens.llm.client import build_client

    try:
        return build_client(["groq_route", "gemini"])
    except LLMUnavailable:
        return None  # offline: keyword rules and word matching still answer


def _run_ask(question: str, client) -> dict:
    """Ask OpsLens on one question (opslens/ask.py): understand → one engine tool → the answer."""
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
    """Ask OpsLens: a plain-words question → one engine tool → an answer (opslens/ask.py)."""
    question = str(request.get("question", "")).strip()[:300]
    if not question:
        return JSONResponse({"error": "empty question"}, status_code=400)
    try:
        return JSONResponse(_run_ask(question, _route_client()))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


# ---- The OpsLens assistant (server/bot.py, 24 Oct): the bot in the side menu --------------------------

@app.get("/api/bot/warm")
def bot_warm() -> dict:
    """Load (or, the very first time, train in the background) the bot's text classifier."""
    from server.bot import warm_up

    warm_up()
    return {"ok": True}


@app.post("/api/bot")
def bot(request: dict) -> JSONResponse:
    """One question for the assistant: a customer complaint, an engine question or a judge question."""
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


# ---- Live now (opslens/live.py, 24 Oct): today's day, simulated here, shown at the real clock ----------

_LIVE: dict = {}  # (day, seed) -> LiveDay, simulated once and kept
_LIVE_BUILDING: dict = {}  # (day, seed) -> the thread simulating it
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

    day, seed, agents_delta, volume = key
    try:
        with _LIVE_BUILD_ONE_AT_A_TIME:  # it briefly wraps one engine function: one build at a time
            _LIVE[key] = simulate_live_day(engine_inputs(), day, seed, dict(agents_delta), volume)
    finally:
        _LIVE_BUILDING.pop(key, None)


def _parse_agents(text: str) -> tuple:
    """"C:-2,B:1" -> (("B", 1), ("C", -2)); teams A-D, each change -5..+5, zeros dropped."""
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
    """The floor at the viewer's real clock: `weekday` (0 = Monday) and `minute` of the day come
    from the browser. The first request for a weekday starts the simulation (about 20-40 s) and
    answers {"ready": false}; the page asks again until it is ready."""
    from opslens.live import state_at

    # `agents` ("C:-2,B:1") and `volume` (1.3 = 30% more customers) change the day, as in What-if.
    try:
        delta = _parse_agents(agents)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if not (0 <= weekday <= 6 and 0 <= minute < 1440 and 1 <= seed <= 99 and 0.5 <= volume <= 2.0):
        return JSONResponse({"error": "weekday 0-6, minute 0-1439, seed 1-99, volume 0.5-2.0"}, status_code=400)
    day, seed = _live_key(weekday, seed)
    key = (day, seed, delta, round(volume, 2))
    with _LIVE_LOCK:
        if key not in _LIVE and key not in _LIVE_BUILDING:
            thread = threading.Thread(target=_build_live, args=(key,), daemon=True)
            _LIVE_BUILDING[key] = thread
            thread.start()
    scenario = {"agents_delta": dict(delta), "volume": round(volume, 2)}
    if key not in _LIVE:
        return JSONResponse({"ready": False, "day": day, "seed": seed, "scenario": scenario})
    return JSONResponse({"ready": True, "scenario": scenario, **state_at(_LIVE[key], minute)},
                        headers={"Cache-Control": "no-store"})


@app.on_event("startup")
def warm_live_now() -> None:
    """Start simulating today's weekday the moment the server starts (24 Oct review): the first
    visitor then sees Live now ready instead of ~25 s of "Starting...". Same key as the endpoint's
    first request (seed 1, no change), so nothing is simulated twice. Skipped quietly if the data
    is missing (a fresh clone): the endpoint still builds on the first request."""
    import datetime

    try:
        day, seed = _live_key(datetime.datetime.now().weekday(), 1)
    except Exception:  # noqa: BLE001 — no generated data yet: nothing to warm
        return
    key = (day, seed, (), 1.0)
    with _LIVE_LOCK:
        if key not in _LIVE and key not in _LIVE_BUILDING:
            thread = threading.Thread(target=_build_live, args=(key,), daemon=True)
            _LIVE_BUILDING[key] = thread
            thread.start()


@app.middleware("http")
async def always_fresh_web_files(request, call_next):
    """The browser must ask for the newest dashboard files on every load (it may reuse its copy
    only when the file did not change). Without this, Chrome kept showing an old app.js."""
    response = await call_next(request)
    if request.url.path.startswith(("/web", "/app")):
        response.headers["Cache-Control"] = "no-cache"
    if request.url.path in ("/web", "/web/", "/web/index.html", "/app", "/app/", "/app/index.html"):
        # Opening the dashboard also tells the browser to drop every copy it kept from older
        # versions (files cached before this header existed were reused without asking).
        response.headers["Clear-Site-Data"] = '"cache"'
    return response


app.mount("/app", StaticFiles(directory=ROOT / "web", html=True), name="app")
app.mount("/web", StaticFiles(directory=ROOT / "web", html=True), name="web")
app.mount("/eval", StaticFiles(directory=ROOT / "eval"), name="eval")
