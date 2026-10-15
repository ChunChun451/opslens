"""Upload CSV: run OpsLens's analysis on any company's ticket export (or the UCI example).

What it does: maps the uploaded columns to OpsLens's names, computes the timing columns and
breach flag, then returns headline KPIs, the worst teams and categories, and evidence cards
from the same pattern scans the engine uses (patterns.find_patterns_basic).

Mapping (from the Upload tab): ticket_id, created_at, resolved_at, priority are required;
category, team, sla_met, reassignments, text are optional. Priorities that are not P1/P2/P3
(e.g. "1 - Critical", "4 - Low") are ranked: the most urgent → P1, the least → P3, others → P2.
If an "SLA met" column exists it decides the breach; otherwise our SLA table (config/sla.yaml).

Example: the UCI ServiceNow log (24,918 incidents) → breach 36.6%, worst groups by breach %,
and cards such as "Category 26 × Group 70 resolution time 3.1× longer".
"""

from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd

from opslens.adapters.uci_incidents import load_uci
from opslens.config import load_config
from opslens.kpis import kpi_table
from opslens.patterns import find_patterns_basic

REQUIRED = ["ticket_id", "created_at", "resolved_at", "priority"]
RENAME = {"category": "final_category", "team": "resolved_by_team", "reassignments": "transfers",
          "sla_met": "made_sla", "text": "text"}
_UCI_CACHE: dict = {}


def to_priority(values: pd.Series) -> pd.Series:
    """Map any priority labels to P1/P2/P3 (most urgent first)."""
    labels = values.astype(str).str.strip()
    if set(labels.unique()) <= {"P1", "P2", "P3"}:
        return labels
    levels = sorted(labels.unique(), key=lambda v: (pd.to_numeric(v[:1], errors="coerce"), v))
    mapping = {v: "P2" for v in levels}
    mapping[levels[0]] = "P1"
    if len(levels) > 1:
        mapping[levels[-1]] = "P3"
    return labels.map(mapping)


def truthy(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y", "met"})


def parse_dates(values: pd.Series) -> pd.Series:
    """ISO dates (2026-09-01 10:00) first; if most fail, day-first (29/2/2016 01:16, as in UCI)."""
    iso = pd.to_datetime(values, errors="coerce", format="ISO8601")
    if iso.notna().mean() >= 0.9:
        return iso
    return pd.to_datetime(values, errors="coerce", dayfirst=True, format="mixed")


def prepare(raw: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    missing = [k for k in REQUIRED if not mapping.get(k)]
    if missing:
        raise ValueError(f"please map: {', '.join(missing)}")
    absent = [c for c in mapping.values() if c and c not in raw.columns]
    if absent:
        raise ValueError(f"columns not in the file: {', '.join(absent)}")
    df = pd.DataFrame({key: raw[col] for key, col in mapping.items() if col})
    df = df.rename(columns=RENAME).drop_duplicates(subset="ticket_id", keep="last")
    for col in ("created_at", "resolved_at"):
        df[col] = parse_dates(df[col])
    df = df.dropna(subset=["created_at"])
    df["priority"] = to_priority(df["priority"])
    df["resolution_min"] = (df["resolved_at"] - df["created_at"]).dt.total_seconds() / 60.0
    if "made_sla" in df:
        df["breached"] = ~truthy(df["made_sla"])
    else:
        sla = df["priority"].map(load_config("sla")["sla_minutes"]).astype(float)
        df["breached"] = df["resolution_min"].isna() | (df["resolution_min"] > sla)
    if "transfers" in df:
        df["transfers"] = pd.to_numeric(df["transfers"], errors="coerce").fillna(0)
    return df


def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("created_at").reset_index(drop=True)
    start = out["created_at"].min().normalize()
    out["day"] = (out["created_at"].dt.normalize() - start).dt.days + 1
    out["hour"] = out["created_at"].dt.hour
    out["weekday"] = out["created_at"].dt.weekday
    out["minute_of_run"] = (out["created_at"] - start).dt.total_seconds() / 60.0
    return out


def summarise(df: pd.DataFrame, source: str, started: float) -> dict:
    df = add_calendar(df)
    resolved = df["resolution_min"].dropna()
    tables = {}
    for key, col in (("by_team", "resolved_by_team"), ("by_category", "final_category")):
        if col in df and df[col].nunique() > 1:
            t = kpi_table(df.assign(reopens=0) if "reopens" not in df else df, [col], min_tickets=30)
            t = t.sort_values("breach_pct", ascending=False).head(8).reset_index()
            tables[key] = [{"name": str(r[col]), "tickets": int(r["tickets"]), "breach_pct": round(float(r["breach_pct"]), 1),
                            "mean_resolution_min": round(float(r["mean_resolution_min"]), 0)} for _, r in t.iterrows()]
    patterns = find_patterns_basic(df)
    return {
        "source": source, "rows": int(len(df)),
        "date_range": [str(df["created_at"].min())[:10], str(df["created_at"].max())[:10]],
        "breach_pct": round(100.0 * float(df["breached"].mean()), 1),
        "mean_resolution_min": round(float(resolved.mean()), 0) if len(resolved) else None,
        "p90_resolution_min": round(float(np.percentile(resolved, 90)), 0) if len(resolved) else None,
        **tables, "cards": patterns["cards"], "metric": patterns["metric"],
        "seconds": round(time.perf_counter() - started, 1),
    }


def json_safe(value):
    """NaN / infinity → None, recursively (JSON cannot carry NaN)."""
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def analyse_csv(content: bytes, mapping: dict[str, str]) -> dict:
    started = time.perf_counter()
    raw = pd.read_csv(io.BytesIO(content), na_values=["?"], low_memory=False)
    return json_safe(summarise(prepare(raw, mapping), "uploaded file", started))


def analyse_uci() -> dict:
    """The ready example: the real ServiceNow incident log, through the UCI adapter."""
    if not _UCI_CACHE:
        started = time.perf_counter()
        incidents, _ = load_uci()
        _UCI_CACHE["answer"] = json_safe(summarise(incidents, "UCI ServiceNow incident log (CC BY 4.0)", started))
    return _UCI_CACHE["answer"]
