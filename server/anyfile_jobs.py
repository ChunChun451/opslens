"""The server side of "OpsLens on your file": keep an uploaded file, run the report in the
background, and let the screen follow each step.

Why a background job: a big file takes a while (the 24,918-incident UCI file takes about 2 s on
this laptop, a 100k-row file longer), and a judge should see what OpsLens is doing ("Learning on
the first 70%...") instead of a frozen page. One worker at a time is enough for a demo.

Flow: POST a file -> a token, the column list, OpsLens's guesses and what will happen (peek);
POST the token with a changed mapping -> what will happen now (check, nothing learned yet);
POST the token with the mapping -> a job id; GET the job id every half second ->
{status, step, steps, file, result | error}. The same file with the same mapping returns the
finished report at once (kept in memory, so a page reload can fetch it again).

Example: upload uci_one_row.csv -> token "a1b2..." and 18 columns; run with the suggested mapping
-> job "a1b2...:9f3c"; a few polls later status "done" and the report, with "file": "uci_one_row.csv".
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from opslens import anyfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "cache" / "uci_one_row.csv"
MAX_BYTES = 60 * 1024 * 1024  # a 60 MB CSV is far more than a demo needs

_files: dict[str, dict] = {}  # token -> {"raw": the table, "name": the file's name}
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_worker = ThreadPoolExecutor(max_workers=1)


def json_safe(value):
    """NaN, infinity and NumPy numbers -> plain JSON values, recursively."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def read_csv(content: bytes) -> pd.DataFrame:
    """Read a CSV whatever its separator (comma, semicolon, tab); "?" and "NaN " count as empty."""
    if len(content) > MAX_BYTES:
        raise ValueError("the file is larger than 60 MB; please upload a sample (a few months of tickets)")
    head = content[:20000].decode("utf-8", errors="ignore")
    try:  # find the separator on the first lines, then read with pandas' fast parser
        sep = csv.Sniffer().sniff(head, delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    try:
        raw = pd.read_csv(io.BytesIO(content), sep=sep, na_values=["?", "NaN", "NaN ", "nan"], low_memory=False)
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same message to the person
        raise ValueError("This does not read as a CSV table: save it as CSV (comma separated) and try again.") from exc
    if raw.shape[1] < 2:
        raise ValueError("This file has fewer than 2 columns: a work-item export has at least a start and an end. "
                         "Try another file.")
    return raw


def keep_file(content: bytes, name: str) -> dict:
    """Store the table under a token and return what the upload card needs (anyfile.peek)."""
    raw = read_csv(content)
    token = hashlib.sha1(content).hexdigest()[:12]
    with _lock:
        _files[token] = {"raw": raw, "name": name}
    return json_safe({"token": token, "name": name, **anyfile.peek(raw)})


def kept(token: str) -> dict:
    with _lock:
        if token not in _files:
            raise ValueError("This upload has expired (the server restarted): please choose the file again.")
        return _files[token]


def keep_example() -> dict:
    """The ready example: the real UCI ServiceNow log, one row per incident (written once)."""
    if not EXAMPLE.exists():
        from opslens.adapters.uci_incidents import load_uci
        incidents, _ = load_uci()
        cols = ["ticket_id", "created_at", "channel", "priority_raw", "impact", "urgency", "final_category", "subcategory",
                "location", "first_team", "resolved_by_team", "transfers", "reopens", "knowledge", "priority_confirmed",
                "resolved_at", "made_sla", "n_events"]
        incidents[cols].rename(columns={"priority_raw": "priority", "final_category": "category"}).to_csv(EXAMPLE, index=False)
    return keep_file(EXAMPLE.read_bytes(), "uci_one_row.csv")


def check(token: str, mapping: dict, target_min: float | None) -> dict:
    """What will happen with a changed mapping, before anything is learned (anyfile.check_mapping)."""
    return json_safe(anyfile.check_mapping(kept(token)["raw"], mapping, target_min))


def start_job(token: str, mapping: dict, target_min: float | None, target_assumed: bool = False) -> dict:
    """Start (or reuse) the report for one file and one mapping; returns the job id."""
    file = kept(token)
    key = hashlib.sha1(json.dumps([mapping, target_min, target_assumed], sort_keys=True).encode()).hexdigest()[:8]
    job_id = f"{token}:{key}"
    with _lock:
        job = _jobs.get(job_id)
        if job and job["status"] != "error":
            return {"job": job_id}
        _jobs[job_id] = {"status": "queued", "step": "Waiting to start", "steps": [], "started": time.time(), "file": file["name"]}
    _worker.submit(run_job, job_id, file, mapping, target_min, target_assumed)
    return {"job": job_id}


def run_job(job_id: str, file: dict, mapping: dict, target_min: float | None, target_assumed: bool) -> None:
    def progress(step: str) -> None:
        with _lock:
            job = _jobs[job_id]
            job["status"] = "running"
            job["step"] = step
            job["steps"].append(step)

    try:
        report = anyfile.analyse(file["raw"], mapping, target_min, progress, target_assumed)
        # The same shape as results.anyfile (eval/run_anyfile.py): which file, how many rows, the mapping.
        result = {"file": file["name"], "rows": int(len(file["raw"])), "mapping": mapping, **report}
        with _lock:
            _jobs[job_id].update(status="done", result=json_safe(result))
    except ValueError as exc:  # our own refusals: one sentence and one fix, shown as they are
        with _lock:
            _jobs[job_id].update(status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - anything else: a plain sentence for the person, the detail for us
        with _lock:
            _jobs[job_id].update(status="error", detail=f"{exc.__class__.__name__}: {exc}",
                                 error="OpsLens could not analyse this file. Check the columns under Adjust, or try another file.")


def job_state(job_id: str) -> dict:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise ValueError("This report is gone (the server restarted): upload the file again.")
        return {k: v for k, v in job.items() if k != "started"} | {"elapsed": round(time.time() - job["started"], 1)}
