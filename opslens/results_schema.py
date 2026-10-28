from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(Strict):
    fixture: bool
    generated_at: str
    git_commit: str = ""
    data_seed: int
    n_tickets: int
    start_date: str
    days: int
    train_days: list[int]
    validation_days: list[int]
    test_days: list[int]
    run_seconds: float = 0.0
    promises_min: dict[str, int] | None = None


class MeanStd(Strict):
    mean: float
    std: float


class PolicyResult(Strict):
    key: str
    label: str
    kpis: dict[str, MeanStd]
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
    title: str
    day: int
    start_minute: float
    step_min: float
    times: list[str]
    series: dict[str, ReplaySeries]
    floor: dict[str, dict[str, Any]] | None = None


class SimSection(Strict):
    seeds: list[int]
    test_days: list[int]
    policies: dict[str, PolicyResult]
    comparisons: list[Comparison]
    replay: Replay | None = None


class ExampleTicket(Strict):
    ticket_id: str
    created_at: str
    text: str
    wait_min: float | None = None
    breached: bool | None = None


class EvidenceCard(Strict):
    id: str
    title: str
    cause_type: Literal["capacity", "skill_gap", "volume_spike", "partner_issue", "process", "other"]
    metric: str
    value: float
    comparison_value: float
    comparison_text: str
    segment: dict[str, str | int | float | list[str] | list[int]]
    affected_tickets: int
    affected_share_pct: float
    strength: float
    not_explained_by: str = ""
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
    blind_recall: dict[str, float] | None = None
    live_detection_latency_min: float | None = None
    delay_decomposition: dict[str, dict[str, float]] = {}


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


class ForecastPoint(Strict):
    time: str
    team: str
    demand_hours: float
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
    peak_gap_agents: float | None = None
    agent_hours_short: float | None = None


class ForecastSection(Strict):
    wape_model: float
    wape_naive: float
    coverage_80: float
    coverage_90: float
    horizon: list[ForecastPoint]
    bottlenecks: list[Bottleneck]


class Reason(Strict):
    feature: str
    contribution: float
    text: str


class AtRiskTicket(Strict):
    ticket_id: str
    created_at: str
    category: str
    priority: str
    language: str
    text: str
    probability: float
    minutes_to_sla: float
    reasons: list[Reason]
    action: str = ""
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


class AssignmentRec(Strict):
    ticket_id: str
    agent_id: str
    agent_name: str
    reason: str
    value: float


class StaffingMove(Strict):
    text: str
    team_from: str
    team_to: str
    agents: list[str]
    when: str
    expected_effect: dict[str, float]


class RecommendationsSection(Strict):
    assignments: list[AssignmentRec]
    staffing_moves: list[StaffingMove]


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
    scale_test: dict[str, float] = {}


class Brief(Strict):
    text: str
    source: Literal["llm", "template"]
    numbers_used: list[str]


class PlaybooksSection(Strict):
    test_days: list[int]
    seeds: list[int]
    playbooks: list[dict[str, Any]]
    all: dict[str, Any]
    opslens_all_vs_baseline_b: dict[str, Any]
    base: dict[str, Any]


class BaselineCSection(Strict):
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
    sealed_world: dict[str, Any] | None = None
    best_baselines: dict[str, Any] | None = None
    sealed_world_rerun: dict[str, Any] | None = None
    floor: dict[str, Any] | None = None
    sealed_world_new: dict[str, Any] | None = None
    realdesk: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    concurrency: dict[str, Any] | None = None
    tracking: dict[str, Any] | None = None
    worlds: dict[str, Any] | None = None
    v6: dict[str, Any] | None = None
    anyfile: dict[str, Any] | None = None
    prediction_baselines: dict[str, Any] | None = None
    faithfulness: dict[str, Any] | None = None
    staffing_opt: dict[str, Any] | None = None
    nlp_bench: dict[str, Any] | None = None
    food_1530: dict[str, Any] | None = None
    earlier_floor: dict[str, Any] | None = None
    details: dict[str, Any] = {}
