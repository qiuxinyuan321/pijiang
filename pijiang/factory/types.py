from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


QUALITY_TIERS = {"weak", "standard", "strong", "elite"}
ADAPTER_TYPES = {"openai_compatible", "ollama", "planning_api", "command_bridge", "demo"}
SEAT_TYPES = {"controller", "planning", "search", "marshal", "chaos", "skeptic", "fusion"}
CONFIG_STATUSES = {"configured", "needs_setup", "disabled"}


@dataclass
class ProviderCapabilities:
    supports_text: bool = True
    supports_structured_json: bool = True
    supports_json_schema: bool = False
    supports_planning: bool = False
    supports_external_search: bool = False
    supports_toolless_readonly: bool = True
    transport: str = "openai-compatible"


@dataclass
class ProviderProfile:
    id: str
    adapter_type: str
    model: str
    roles: list[str] = field(default_factory=list)
    base_url: str = ""
    relay_url: str = ""
    scheme: str = "https"
    host: str = ""
    port: int | None = None
    path_prefix: str = ""
    api_key_env: str = ""
    command: list[str] = field(default_factory=list)
    priority: int = 100
    enabled: bool = True
    config_status: str = "needs_setup"
    quality_tier: str = "standard"
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    notes: str = ""


@dataclass
class CouncilSeat:
    seat_id: str
    seat_type: str
    profile_id: str
    display_name: str
    description: str
    required: bool = True
    status: str = "pending"


@dataclass
class CouncilTopology:
    mode: str
    seat_count: int
    controller_seat: str
    planning_seats: list[str]
    search_seats: list[str]
    marshal_seats: list[str]
    chaos_seat: str
    skeptic_seat: str
    fusion_seat: str
    seats: list[CouncilSeat] = field(default_factory=list)


@dataclass
class ControllerPolicy:
    controller_profile_id: str
    recommended_models: list[str] = field(default_factory=list)
    warn_if_not_strong: bool = True


@dataclass
class WorkflowProfile:
    controller_profile_id: str
    planning_profile_ids: list[str] = field(default_factory=list)
    lane_profile_pool: list[str] = field(default_factory=list)
    fusion_profile_order: list[str] = field(default_factory=list)
    fallback_policy: str = "controller-then-best-available"


@dataclass
class VisualizationProfile:
    obsidian_enabled: bool = True
    vault_path: str = ""
    template_id: str = "official-default"
    write_mode: str = "mirror"
    visualization_degraded: bool = False


@dataclass
class HostIntegrationSpec:
    host: str
    output_dir: str
    generated_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ExecutionRequest:
    prompt: str
    output_mode: str
    schema: dict[str, Any] | None = None
    timeout_sec: int = 900
    output_path: Path | None = None


@dataclass
class ExecutionResponse:
    content: str
    raw_stdout: str = ""
    raw_stderr: str = ""
    provider_id: str = ""
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunEvent:
    timestamp: str
    kind: str
    stage: str = ""
    seat_id: str = ""
    provider_profile: str = ""
    message: str = ""


@dataclass
class RunProgressSnapshot:
    run_id: str
    status: str
    stage: str
    seat_statuses: dict[str, str]
    completed_seat_count: int
    failed_seat_count: int
    current_message: str
    running_seat_ids: list[str] = field(default_factory=list)
    current_seat_id: str = ""
    updated_at: str = ""
    quorum_ready: bool = False
    ghosted_seat_ids: list[str] = field(default_factory=list)
    late_seat_ids: list[str] = field(default_factory=list)
    parallel_policy: str = "strict_all"
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass
class ReadinessIssue:
    level: str
    code: str
    message: str
    fix_hint: str = ""


@dataclass
class EndpointDiagnostic:
    profile_id: str
    adapter_type: str
    endpoint_source: str = "unresolved"
    effective_base_url: str = ""
    normalized: bool = False
    valid: bool = False
    issues: list[str] = field(default_factory=list)


@dataclass
class ReadinessReport:
    status: str
    standard_topology_seat_count: int
    enabled_seat_count: int
    runnable_seat_count: int
    enabled_profile_count: int
    runnable_profile_count: int
    blockers: list[ReadinessIssue] = field(default_factory=list)
    warnings: list[ReadinessIssue] = field(default_factory=list)
    ready_items: list[str] = field(default_factory=list)
    endpoint_diagnostics: list[EndpointDiagnostic] = field(default_factory=list)


@dataclass
class EvidenceRef:
    ref_id: str
    source: str
    locator: str = ""
    snippet: str = ""


@dataclass
class SearchArtifact:
    lane_id: str
    query_intent: str
    source_type: str
    results: list[dict[str, str]] = field(default_factory=list)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    confidence: str = "medium"
    degraded: bool = False


@dataclass
class SeatResult:
    seat_id: str
    seat_type: str
    summary: str
    sections: dict[str, str] = field(default_factory=dict)
    claims: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    confidence: str = "medium"
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class QualityAssessment:
    seat_id: str
    schema_valid: bool
    anchor_hits: int
    evidence_count: int
    section_completeness: float
    quality_score: int
    quality_flags: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class ExecutionPolicy:
    max_attempts_per_seat: int = 2
    retry_backoff_seconds: list[int] = field(default_factory=lambda: [2, 6])
    soft_budget: int = 6
    hard_budget: int = 10
    circuit_breaker_threshold: int = 2
    quality_retry_threshold: int = 12
    parallel_policy: str = "ghost_isolation"


@dataclass
class BenchmarkScenario:
    scenario_id: str
    title: str
    brief_path: str
    description: str = ""


@dataclass
class BenchmarkMeasurement:
    mode: str
    run_id: str
    latency_ms: int
    provider_calls: int
    estimated_cost: float
    audit_pass_success_rate: float
    cost_per_audited_success: float
    schema_pass_rate: float
    evidence_coverage: float
    quality_score: float
    issue_readiness_score: float
    failed_rate: float
    fake_success_rate: float
    time_to_fusion_cutover_ms: int = 0
    ghosted_lane_count: int = 0
    late_result_count: int = 0
    cutover_latency_saved_ms: int = 0
    degraded_flags: list[str] = field(default_factory=list)
    truth_audit_path: str = ""


@dataclass
class BenchmarkReport:
    scenario_id: str
    generated_at: str
    measurements: list[BenchmarkMeasurement] = field(default_factory=list)


@dataclass
class RunTruthAudit:
    run_id: str
    mode: str
    audit_status: str
    seat_integrity_score: int
    discussion_diversity_score: int
    evidence_integrity_score: int
    fusion_integrity_score: int
    artifact_integrity_score: int
    fake_success_flags: list[str] = field(default_factory=list)
    degraded_chain_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    regression_case_paths: list[str] = field(default_factory=list)
    repair_candidates: list[str] = field(default_factory=list)


@dataclass
class RegressionCase:
    case_id: str
    source_run_id: str
    source_system: str
    failure_type: str
    input_brief: str
    offending_outputs: list[str] = field(default_factory=list)
    expected_behavior: str = ""
    repair_hypothesis: str = ""
    verification_command: str = ""


@dataclass
class IterationDeltaReport:
    current_run_id: str
    baseline_run_id: str = ""
    generated_at: str = ""
    improvements: list[str] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    remaining_gaps: list[str] = field(default_factory=list)
    next_focus: list[str] = field(default_factory=list)
