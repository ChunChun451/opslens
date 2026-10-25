"""The server side of "OpsLens on your file": keep an uploaded file, run the report in the
background, and let the screen follow each step.

Why a background job: a big file takes a while (the 24,918-incident UCI file takes about 2 s on
this laptop, a 100k-row file longer), and a judge should see what OpsLens is doing ("Learning on
the first 70%...") instead of a frozen page. One worker at a time is enough for a demo.

Flow: POST a file -> a token and the column list (peek); POST the token with the mapping -> a job
id; GET the job id every half second -> {status, step, steps, result | error}. The same file with
the same mapping returns the finished report at once (kept in memory).

Example: upload uci_one_row.csv -> token "a1b2..." and 18 columns; run with the suggested mapping
-> job "a1b2...:9f3c"; a few polls later status "done" and the report.
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

_files: dict[str, pd.DataFrame] = {}
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
        raise ValueError(f"this does not read as a CSV table ({exc.__class__.__name__})") from exc
    if raw.shape[1] < 2:
        raise ValueError("the file has fewer than 2 columns; a work-item export has at least a start and an end")
    return raw


def keep_file(content: bytes, name: str) -> dict:
    """Store the table under a token and return what the mapping form needs."""
    raw = read_csv(content)
    token = hashlib.sha1(content).hexdigest()[:12]
    with _lock:
        _files[token] = raw
    return json_safe({"token": token, "name": name, **anyfile.peek(raw)})


def keep_example() -> dict:
    """The ready example: the real UCI ServiceNow log, one row per incident (written once)."""
    if not EXAMPLE.exists():
        from opslens.adapters.uci_incidents import load_uci
        incidents, _ = load_uci()
        cols = ["ticket_id", "created_at", "channel", "priority_raw", "impact", "urgency", "final_category", "subcategory",
                "location", "first_team", "resolved_by_team", "transfers", "reopens", "knowledge", "priority_confirmed",
                "resolved_at", "made_sla", "n_events"]
        incidents[cols].rename(columns={"priority_raw": "priority", "final_category": "category"}).to_csv(EXAMPLE, index=False)
    return keep_file(EXAMPLE.read_bytes(), "UCI ServiceNow incident log, one row per incident (CC BY 4.0)")


def start_job(token: str, mapping: dict, target_min: float | None) -> dict:
    """Start (or reuse) the report for one file and one mapping; returns the job id."""
    with _lock:
        if token not in _files:
            raise ValueError("this upload has expired; please choose the file again")
        raw = _files[token]
    key = hashlib.sha1(json.dumps([mapping, target_min], sort_keys=True).encode()).hexdigest()[:8]
    job_id = f"{token}:{key}"
    with _lock:
        job = _jobs.get(job_id)
        if job and job["status"] != "error":
            return {"job": job_id}
        _jobs[job_id] = {"status": "queued", "step": "Waiting to start", "steps": [], "started": time.time()}
    _worker.submit(run_job, job_id, raw, mapping, target_min)
    return {"job": job_id}


def run_job(job_id: str, raw: pd.DataFrame, mapping: dict, target_min: float | None) -> None:
    def progress(step: str) -> None:
        with _lock:
            job = _jobs[job_id]
            job["status"] = "running"
            job["step"] = step
            job["steps"].append(step)

    try:
        report = anyfile.analyse(raw, mapping, target_min, progress)
        with _lock:
            _jobs[job_id].update(status="done", result=json_safe(report))
    except Exception as exc:  # noqa: BLE001 - the person sees the reason, the server keeps running
        with _lock:
            _jobs[job_id].update(status="error", error=str(exc))


def job_state(job_id: str) -> dict:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise ValueError("unknown job")
        return {k: v for k, v in job.items() if k != "started"} | {"elapsed": round(time.time() - job["started"], 1)}
