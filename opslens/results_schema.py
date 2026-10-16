"""The contract for eval/results.json — the single source of every number OpsLens shows.

Why this file exists:
- CLAUDE.md rule: "never show a number we did not compute". The dashboard, NUMBERS.md and the
  LLM brief read ONLY eval/results.json, and this module defines its exact shape.
- The UI is built in parallel against `eval/fixture_results.json` (same shape, invented
  numbers). Fixture files carry `meta.fixture = true`; the UI shows a red FIXTURE banner and
  `make demo` refuses to start on them.
- `extra="forbid"` everywhere: a typo in a field name fails loudly instead of silently
  showing nothing.
- Sections are optional because milestones fill them one by one (M3 classification, M4
  patterns, M5 risk, M6 forecast, M7-M8 simulation and evaluation).

Example (shortened):
    {"meta": {"fixture": false, "generated_at": "2026-10-22T18:00:00", ...},
     "sim": {"policies": {"opslens": {"kpis": {"turnaround.breach_pct": {"mean": 7.9, "std": 0.4}}}}}}
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- Meta ------------------------------------------------------------------------------------

class Meta(Strict):
    fixture: bool
    generated_at: str
    git_commit: str = ""
    data_seed: int
    n_tickets: int
    start_date: str
    days: int
    train_days: list[int]  # [first, last]
    validation_days: list[int]
    test_days: list[int]
    run_seconds: float = 0.0


# ---- Simulation comparison -------------------------------------------------------------------

class MeanStd(Strict):
    mean: float
    std: float


class PolicyResult(Strict):
    key: str  # "baseline_a", "baseline_b", "opslens", or an ablation key
    label: str  # "Baseline A (FIFO)"
    kpis: dict[str, MeanStd]  # e.g. "turnaround.breach_pct"
    per_seed: list[dict[str, float]]


class Comparison(Strict):
    policy: str
    baseline: str
    kpi: str
    mean_diff: float
    ci_low: float
    ci_high: float
    n: int


class ReplaySeries(Strict):
    waiting: list[int]
    breached_cum: list[int]


class Replay(Strict):
    title: str  # "Saturday 17 Oct, 18:00-23:59"
    day: int
    start_minute: float
    step_min: float
    times: list[str]  # "18:00", "18:15", ...
    series: dict[str, ReplaySeries]  # policy key -> series
    # Floor map (eval/run_opslens.py::floor_frames): agents, 5-min times, a status letter per
    # agent per frame, and each team's queue [can still make SLA, already late]. Optional so
    # older results still validate.
    floor: dict[str, dict[str, Any]] | None = None


class SimSection(Strict):
    seeds: list[int]
    test_days: list[int]
    policies: dict[str, PolicyResult]
    comparisons: list[Comparison]
    replay: Replay | None = None


# ---- Patterns (M4) ---------------------------------------------------------------------------

class ExampleTicket(Strict):
    ticket_id: str
    created_at: str
    text: str  # PII-masked
    wait_min: float | None = None
    breached: bool | None = None


class EvidenceCard(Strict):
    id: str
    title: str  # "Hindi refunds wait 5x longer"
    cause_type: Literal["capacity", "skill_gap", "volume_spike", "partner_issue", "process", "other"]
    metric: str  # "mean wait (min)"
    value: float
    comparison_value: float
    comparison_text: str  # "Hindi refunds wait 302 min vs 47 min for English refunds"
    segment: dict[str, str | int | float | list[str] | list[int]]
    affected_tickets: int
    affected_share_pct: float
    strength: float  # robust z or ratio, used for ranking
    not_explained_by: str = ""  # e.g. "not a known sale day"
    examples: list[ExampleTicket] = []
    recommendation: str = ""


class RecallResult(Strict):
    planted: int
    found: int
    false_alarms: int
    details: list[dict[str, str | bool]]


class PatternsSection(Strict):
    cards: list[EvidenceCard]
    recall: RecallResult | None = None
    blind_recall: dict[str, float] | None = None  # {"sets": 20, "found_pct": 90.0, "false_alarms_mean": 0.4}
    live_detection_latency_min: float | None = None
    delay_decomposition: dict[str, dict[str, float]] = {}  # team -> {waiting, handling, transfer, reopen}


# ---- Classification (M3) ---------------------------------------------------------------------

class Cluster(Strict):
    category: str
    name: str
    root_cause: str
    size: int
    examples: list[str]


class ClassificationSection(Strict):
    accuracy_local: float
    accuracy_cascade: float
    accuracy_llm_sample: float | None = None
    pct_sent_to_llm: float
    cost_per_million_tickets_usd: float | None = None
    transfers_avoided_per_100: float | None = None
    confusion: dict[str, dict[str, int]] = {}
    clusters: list[Cluster] = []


# ---- Forecast (M6) ---------------------------------------------------------------------------

class ForecastPoint(Strict):
    time: str  # ISO hour
    team: str
    demand_hours: float  # forecast agent-hours of work arriving
    lo80: float
    hi80: float
    capacity_hours: float
    actual_hours: float | None = None


class Bottleneck(Strict):
    team: str
    start: str
    end: str
    text: str
    peak_rho: float | None = None
    peak_gap_agents: float | None = None  # agents short at the worst hour
    agent_hours_short: float | None = None


class ForecastSection(Strict):
    wape_model: float
    wape_naive: float
    coverage_80: float
    coverage_90: float
    horizon: list[ForecastPoint]
    bottlenecks: list[Bottleneck]


# ---- Risk (M5) -------------------------------------------------------------------------------

class Reason(Strict):
    feature: str
    contribution: float  # in probability points, e.g. +0.21
    text: str  # "Hindi refund (+0.21)"


class AtRiskTicket(Strict):
    ticket_id: str
    created_at: str
    category: str
    priority: str
    language: str
    text: str  # masked
    probability: float
    minutes_to_sla: float
    reasons: list[Reason]
    action: str = ""  # "assign a Hindi refund agent now"
    probability_after_action: float | None = None


class CalibrationBin(Strict):
    predicted: float
    observed: float
    n: int


class RiskSection(Strict):
    auc: float
    pr_auc: float
    top10_precision: float
    brier: float
    base_rate: float
    calibration: list[CalibrationBin]
    at_risk: list[AtRiskTicket]
    realdata_auc: float | None = None
    realdata_n: int | None = None


# ---- Recommendations (M6-M7) -----------------------------------------------------------------

class AssignmentRec(Strict):
    ticket_id: str
    agent_id: str
    agent_name: str
    reason: str
    value: float


class StaffingMove(Strict):
    text: str  # "Move 3 missing/wrong-item trained agents from Team D to Team C, Sat 19:00-23:00"
    team_from: str
    team_to: str
    agents: list[str]
    when: str
    expected_effect: dict[str, float]  # kpi -> change


class RecommendationsSection(Strict):
    assignments: list[AssignmentRec]
    staffing_moves: list[StaffingMove]


# ---- Evaluation extras (M8) ------------------------------------------------------------------

class AblationRow(Strict):
    key: str
    label: str
    breach_pct: MeanStd
    p90_resolution_min: MeanStd
    delta_breach_vs_full: float


class SpeedSection(Strict):
    pipeline_seconds: float
    optimizer_ms_median: float
    optimizer_ms_max: float
    scale_test: dict[str, float] = {}  # {"tickets": 5000, "agents": 500, "seconds": 0.8}


class Brief(Strict):
    text: str
    source: Literal["llm", "template"]
    numbers_used: list[str]


class PlaybooksSection(Strict):
    """Fix-at-source playbooks (opslens/playbooks.py), each measured on the test days
    (eval/run_playbooks.py). Effects are paired differences vs the same policy without it."""

    test_days: list[int]
    seeds: list[int]
    playbooks: list[dict[str, Any]]
    all: dict[str, Any]
    opslens_all_vs_baseline_b: dict[str, Any]
    base: dict[str, Any]


class BaselineCSection(Strict):
    """Baseline C, the "SLA due" sort a helpdesk already has, vs A, B and OpsLens, plus how late
    the late customers are (eval/run_baseline_c.py; Claude 2 review). Validation first, then test."""

    validation: dict[str, Any]
    test: dict[str, Any]


class Results(Strict):
    meta: Meta
    sim: SimSection | None = None
    patterns: PatternsSection | None = None
    classification: ClassificationSection | None = None
    forecast: ForecastSection | None = None
    risk: RiskSection | None = None
    recommendations: RecommendationsSection | None = None
    ablations: list[AblationRow] = []
    sensitivity: list[dict[str, float | str]] = []
    stress: list[dict[str, float | str]] = []
    speed: SpeedSection | None = None
    brief: Brief | None = None
    playbooks: PlaybooksSection | None = None
    baseline_c: BaselineCSection | None = None
    # Supporting numbers behind the headline ones (tuning history, blind-test breakdown,
    # classification and forecast details, real-data findings). Free-form so each milestone
    # can add evidence without a schema change; the UI shows it under "How we tested".
    details: dict[str, Any] = {}
