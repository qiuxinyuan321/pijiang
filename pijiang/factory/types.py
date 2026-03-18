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
