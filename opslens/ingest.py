from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from opslens.config import load_config

CANONICAL_COLUMNS = [
    "ticket_id", "created_at", "channel", "selected_category", "priority", "language",
    "customer_tier", "order_value_inr", "restaurant_cluster_id", "text",
    "first_pickup_at", "resolved_at", "handled_min", "transfers", "reopens", "final_category",
    "resolved_by", "resolved_by_team",
]
REQUIRED = ["ticket_id", "created_at", "priority"]


class TicketRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticket_id: str
    created_at: datetime
    priority: str
    channel: str | None = None
    selected_category: str | None = None
    language: str | None = None
    customer_tier: str | None = None
    order_value_inr: float | None = None
    restaurant_cluster_id: int | None = None
    text: str | None = None
    first_pickup_at: datetime | None = None
    resolved_at: datetime | None = None
    handled_min: float | None = None
    transfers: int | None = None
    reopens: int | None = None
    final_category: str | None = None
    resolved_by: str | None = None
    resolved_by_team: str | None = None

    @field_validator("priority")
    @classmethod
    def known_priority(cls, value: str) -> str:
        if value not in {"P1", "P2", "P3"}:
            raise ValueError(f"priority must be P1/P2/P3, got {value!r}")
        return value


def apply_mapping(raw: pd.DataFrame, mapping: dict[str, str] | None) -> pd.DataFrame:
    if not mapping:
        return raw.copy()
    missing = [src for src in mapping.values() if src not in raw.columns]
    if missing:
        raise ValueError(f"columns not found in file: {missing}")
    return raw.rename(columns={src: canon for canon, src in mapping.items()})


def validate_rows(df: pd.DataFrame, max_errors: int = 5) -> list[str]:
    errors: list[str] = []
    for row in df.replace({np.nan: None}).to_dict("records"):
        try:
            TicketRecord.model_validate(row)
        except ValidationError as exc:
            first = exc.errors()[0]
            errors.append(f"ticket {row.get('ticket_id')}: {first['loc'][0]} — {first['msg']}")
            if len(errors) >= max_errors:
                break
    return errors


def clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.drop_duplicates(subset="ticket_id", keep="last").copy()
    for col in ("created_at", "first_pickup_at", "resolved_at"):
        if col in out:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    for col in ("channel", "selected_category", "language", "customer_tier", "final_category"):
        if col in out:
            out[col] = out[col].astype("string").str.strip().str.lower()
    for col in ("transfers", "reopens"):
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    return out.sort_values("created_at", kind="stable").reset_index(drop=True)


def add_timing(df: pd.DataFrame, sla_minutes: dict[str, float]) -> pd.DataFrame:
    out = df.copy()
    out["sla_min"] = out["priority"].map(sla_minutes).astype(float)
    if "first_pickup_at" in out:
        out["wait_min"] = (out["first_pickup_at"] - out["created_at"]).dt.total_seconds() / 60.0
    if "resolved_at" in out:
        out["resolution_min"] = (out["resolved_at"] - out["created_at"]).dt.total_seconds() / 60.0
        out["breached"] = out["resolution_min"].isna() | (out["resolution_min"] > out["sla_min"])
    return out


def add_calendar(df: pd.DataFrame, start_date: str, splits: dict[str, int]) -> pd.DataFrame:
    out = df.copy()
    start = pd.Timestamp(start_date)
    out["day"] = (out["created_at"].dt.normalize() - start).dt.days + 1
    out["hour"] = out["created_at"].dt.hour
    out["weekday"] = out["created_at"].dt.weekday
    out["minute_of_run"] = (out["created_at"] - start).dt.total_seconds() / 60.0
    out["split"] = np.select(
        [out["day"] <= splits["train_last_day"], out["day"] <= splits["validation_last_day"]],
        ["train", "validation"],
        default="test",
    )
    return out


def ingest(
    path: Path,
    mapping: dict[str, str] | None = None,
    sla_minutes: dict[str, float] | None = None,
    start_date: str | None = None,
) -> pd.DataFrame:
    raw = pd.read_csv(path)
    df = apply_mapping(raw, mapping)
    absent = [c for c in REQUIRED if c not in df.columns]
    if absent:
        raise ValueError(f"required columns missing: {absent}")
    errors = validate_rows(df)
    if errors:
        raise ValueError("invalid rows:\n  " + "\n  ".join(errors))
    df = clean(df[[c for c in CANONICAL_COLUMNS if c in df.columns]])
    sla = sla_minutes or load_config("sla")["sla_minutes"]
    df = add_timing(df, sla)
    calendar = load_config("calendar")
    return add_calendar(df, start_date or calendar["start_date"], calendar["splits"])


def load_history() -> pd.DataFrame:
    from opslens.config import PROJECT_ROOT

    return ingest(PROJECT_ROOT / "data" / "generated" / "history.csv")
