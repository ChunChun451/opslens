"""The OpsLens web server: serves the dashboard and the results, and runs live simulations.

Run:  mingw32-make serve     → http://localhost:8000/

Why this design:
- The dashboard (web/) only reads numbers from `GET /api/results`, which returns
  eval/results.json — the one file every number comes from. If it does not exist yet, the
  fixture file is returned instead, and the UI shows its red FIXTURE banner.
- Everything runs locally: no network calls at serve time (LLM answers are already cached),
  so the demo works with Wi-Fi off.
- Live endpoints (What-if M10, Plant-a-problem M11, Upload M10) are added as their milestones land.

Example: curl http://localhost:8000/api/health  →  {"ok": true, "results": "eval/results.json", "fixture": false}
"""

from __future__ import annotations

import json
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
    return RedirectResponse("/web/")


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


@app.post("/api/plant")
def plant(request: dict) -> JSONResponse:
    """Hide the judge's problem in fresh data and see whether OpsLens finds it (server/plant_demo.py)."""
    from server.plant_demo import run_plant

    try:
        return JSONResponse(run_plant(request))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


app.mount("/web", StaticFiles(directory=ROOT / "web", html=True), name="web")
app.mount("/eval", StaticFiles(directory=ROOT / "eval"), name="eval")
