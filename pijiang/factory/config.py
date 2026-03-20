from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .types import (
    ControllerPolicy,
    CouncilSeat,
    CouncilTopology,
    ExecutionPolicy,
    ProviderCapabilities,
    ProviderProfile,
    VisualizationProfile,
    WatcherPolicy,
    WorkflowProfile,
)


DEFAULT_COUNCIL_VERSION = "v6"


@dataclass
class OnboardingState:
    first_run_acknowledged: bool = False
    skip_repeated_intro: bool = False
    intro_version: str = "v1"


@dataclass
class PijiangConfig:
    version: str = DEFAULT_COUNCIL_VERSION
    workspace_root: str = ""
    output_root: str = ""
    cache_root: str = ""
    project_prefix: str = "皮匠"
    host_mode: str = "standalone"
    provider_profiles: list[ProviderProfile] = field(default_factory=list)
    council_topology: CouncilTopology | None = None
    controller_policy: ControllerPolicy | None = None
    workflow: WorkflowProfile | None = None
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    visualization: VisualizationProfile = field(default_factory=VisualizationProfile)
    onboarding: OnboardingState = field(default_factory=OnboardingState)
    watcher_policy: WatcherPolicy = field(default_factory=WatcherPolicy)


def default_home() -> Path:
    override = os.environ.get("PIJIANG_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".pijiang"


def default_config_path() -> Path:
    return default_home() / "config.json"


def demo_config_path(base_config_path: Path | None = None) -> Path:
    config_path = (base_config_path or default_config_path()).expanduser().resolve()
    return config_path.with_name("demo-config.json")


def _capabilities(
    *,
    transport: str,
    supports_json_schema: bool = False,
    supports_planning: bool = False,
    supports_external_search: bool = False,
) -> ProviderCapabilities:
    return ProviderCapabilities(
        supports_text=True,
        supports_structured_json=True,
        supports_json_schema=supports_json_schema,
        supports_planning=supports_planning,
        supports_external_search=supports_external_search,
        supports_toolless_readonly=True,
        transport=transport,
    )


def build_default_provider_profiles() -> list[ProviderProfile]:
    return [
        ProviderProfile(
            id="controller-primary",
            adapter_type="openai_compatible",
            model="gpt-5.4",
            roles=["controller"],
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            priority=10,
            config_status="needs_setup",
            quality_tier="elite",
            capabilities=_capabilities(transport="openai-compatible", supports_json_schema=True),
            notes="建议使用顶级强模型作为主控。主控不等于角色扮演，而是负责总体调度与最终收敛。",
        ),
        ProviderProfile(
            id="planning-alibaba",
            adapter_type="planning_api",
            model="alibaba-coding-plan",
            roles=["planning"],
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key_env="ALIBABA_CODING_PLAN_API_KEY",
            priority=20,
            config_status="needs_setup",
            quality_tier="elite",
            capabilities=_capabilities(transport="planning-api", supports_json_schema=True, supports_planning=True),
            notes="官方一等公民 Planning Provider。",
        ),
        ProviderProfile(
            id="planning-volcengine",
            adapter_type="planning_api",
            model="volcengine-coding-plan",
            roles=["planning"],
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key_env="VOLCENGINE_CODING_PLAN_API_KEY",
            priority=30,
            config_status="needs_setup",
            quality_tier="elite",
            capabilities=_capabilities(transport="planning-api", supports_json_schema=True, supports_planning=True),
            notes="官方一等公民 Planning Provider 备用位。",
        ),
        ProviderProfile(
            id="search-web",
            adapter_type="command_bridge",
            model="web-capable-search-model",
            roles=["search"],
            priority=40,
            config_status="needs_setup",
            quality_tier="strong",
            capabilities=_capabilities(transport="command-bridge", supports_external_search=True),
            notes="负责产品/网页/资料检索。这里的“外部搜索者”是分析职责，不是人格扮演。",
        ),
        ProviderProfile(
            id="search-github",
            adapter_type="command_bridge",
            model="github-capable-search-model",
            roles=["search"],
            priority=50,
            config_status="needs_setup",
            quality_tier="strong",
            capabilities=_capabilities(transport="command-bridge", supports_external_search=True),
            notes="负责 GitHub/案例/实现检索。",
        ),
        ProviderProfile(
            id="marshal-engineering",
            adapter_type="openai_compatible",
            model="claude-sonnet-4.6",
            roles=["marshal"],
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            priority=60,
            config_status="needs_setup",
            quality_tier="strong",
            capabilities=_capabilities(transport="openai-compatible", supports_json_schema=True),
            notes="裨将位 1：工程可执行性与落地路径。",
        ),
        ProviderProfile(
            id="marshal-structure",
            adapter_type="openai_compatible",
            model="gemini-3.1-pro",
            roles=["marshal"],
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            priority=70,
            config_status="needs_setup",
            quality_tier="strong",
            capabilities=_capabilities(transport="openai-compatible", supports_json_schema=True),
            notes="裨将位 2：结构整理、约束归纳与方案压缩。",
        ),
        ProviderProfile(
            id="marshal-ux",
            adapter_type="openai_compatible",
            model="gpt-5.4",
            roles=["marshal"],
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            priority=80,
            config_status="needs_setup",
            quality_tier="strong",
            capabilities=_capabilities(transport="openai-compatible", supports_json_schema=True),
            notes="裨将位 3：用户体验、可部署性与新手路径。",
        ),
        ProviderProfile(
            id="chaos-breaker",
            adapter_type="openai_compatible",
            model="gemini-3.1-pro",
            roles=["chaos"],
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            priority=90,
            config_status="needs_setup",
            quality_tier="strong",
            capabilities=_capabilities(transport="openai-compatible", supports_json_schema=True),
            notes="混沌者：负责反常规破局与打破局部最优。",
        ),
        ProviderProfile(
            id="skeptic-redteam",
            adapter_type="openai_compatible",
            model="claude-sonnet-4.6",
            roles=["skeptic"],
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            priority=100,
            config_status="needs_setup",
            quality_tier="strong",
            capabilities=_capabilities(transport="openai-compatible", supports_json_schema=True),
            notes="质疑者：负责红队拆解、失败模式与反驳。",
        ),
        ProviderProfile(
            id="fusion-editor",
            adapter_type="openai_compatible",
            model="gpt-5.4",
            roles=["fusion"],
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            priority=110,
            config_status="needs_setup",
            quality_tier="elite",
            capabilities=_capabilities(transport="openai-compatible", supports_json_schema=True),
            notes="融合者：负责最终合并、决策账本与终版输出。",
        ),
    ]


def build_demo_provider_profiles() -> list[ProviderProfile]:
    profiles = build_default_provider_profiles()
    demo_models = {
        "controller-primary": "demo-controller",
        "planning-alibaba": "demo-planning",
        "planning-volcengine": "demo-planning-backup",
        "search-web": "demo-search-web",
        "search-github": "demo-search-github",
        "marshal-engineering": "demo-marshal-engineering",
        "marshal-structure": "demo-marshal-structure",
        "marshal-ux": "demo-marshal-ux",
        "chaos-breaker": "demo-chaos",
        "skeptic-redteam": "demo-skeptic",
        "fusion-editor": "demo-fusion",
    }
    for profile in profiles:
        profile.adapter_type = "demo"
        profile.model = demo_models.get(profile.id, profile.model)
        profile.base_url = ""
        profile.api_key_env = ""
        profile.command = []
        profile.config_status = "configured"
    return profiles


def build_default_council_topology() -> CouncilTopology:
    seats = [
        CouncilSeat("controller", "controller", "controller-primary", "主控", "负责总体调度与最终收敛策略。"),
        CouncilSeat("planning", "planning", "planning-alibaba", "规划者", "优先由 coding plan provider 承担。"),
        CouncilSeat("search-1", "search", "search-web", "外部搜索者 1", "偏产品/网页/资料检索。"),
        CouncilSeat("search-2", "search", "search-github", "外部搜索者 2", "偏 GitHub/案例/实现检索。"),
        CouncilSeat("marshal-1", "marshal", "marshal-engineering", "裨将 1", "偏工程可执行性与落地路径。"),
        CouncilSeat("marshal-2", "marshal", "marshal-structure", "裨将 2", "偏结构整理、约束归纳与方案压缩。"),
        CouncilSeat("marshal-3", "marshal", "marshal-ux", "裨将 3", "偏用户体验、可部署性与新手路径。"),
        CouncilSeat("chaos", "chaos", "chaos-breaker", "混沌者", "负责反常规破局与打破局部最优。"),
        CouncilSeat("skeptic", "skeptic", "skeptic-redteam", "质疑者", "负责红队拆解、失败模式与反驳。"),
        CouncilSeat("fusion", "fusion", "fusion-editor", "融合者", "负责最终合并、决策账本与终版输出。"),
    ]
    return CouncilTopology(
        mode="standard",
        seat_count=len(seats),
        controller_seat="controller",
        planning_seats=["planning"],
        search_seats=["search-1", "search-2"],
        marshal_seats=["marshal-1", "marshal-2", "marshal-3"],
        chaos_seat="chaos",
        skeptic_seat="skeptic",
        fusion_seat="fusion",
        seats=seats,
    )


def build_default_config(
    *,
    workspace_root: Path | None = None,
    output_root: Path | None = None,
    cache_root: Path | None = None,
    vault_path: Path | None = None,
    host_mode: str = "standalone",
) -> PijiangConfig:
    workspace = (workspace_root or Path.cwd()).resolve()
    output = (output_root or (workspace / "output")).resolve()
    cache = (cache_root or (workspace / ".cache" / "solution-factory")).resolve()
    visualization = VisualizationProfile(
        obsidian_enabled=True,
        vault_path=str((vault_path or (workspace / "obsidian-vault")).resolve()),
        template_id="official-default",
        write_mode="mirror",
        visualization_degraded=False,
    )
    topology = build_default_council_topology()
    workflow = WorkflowProfile(
        controller_profile_id="controller-primary",
        planning_profile_ids=["planning-alibaba", "planning-volcengine"],
        lane_profile_pool=[seat.profile_id for seat in topology.seats],
        fusion_profile_order=["fusion-editor", "controller-primary"],
        fallback_policy="controller-then-best-available",
    )
    controller_policy = ControllerPolicy(
        controller_profile_id="controller-primary",
        recommended_models=["Opus 4.6", "GPT-5.4", "Gemini 3.1 Pro", "高质量 Coding Plan"],
        warn_if_not_strong=True,
    )
    return PijiangConfig(
        version=DEFAULT_COUNCIL_VERSION,
        workspace_root=str(workspace),
        output_root=str(output),
        cache_root=str(cache),
        project_prefix="皮匠",
        host_mode=host_mode,
        provider_profiles=build_default_provider_profiles(),
        council_topology=topology,
        controller_policy=controller_policy,
        workflow=workflow,
        execution_policy=ExecutionPolicy(),
        visualization=visualization,
        onboarding=OnboardingState(),
    )


def build_demo_config(
    *,
    workspace_root: Path | None = None,
    output_root: Path | None = None,
    cache_root: Path | None = None,
    vault_path: Path | None = None,
    host_mode: str = "standalone",
) -> PijiangConfig:
    config = build_default_config(
        workspace_root=workspace_root,
        output_root=output_root,
        cache_root=cache_root,
        vault_path=vault_path,
        host_mode=host_mode,
    )
    config.provider_profiles = build_demo_provider_profiles()
    config.visualization.visualization_degraded = False
    return config


def _provider_capabilities_from_dict(payload: dict[str, Any]) -> ProviderCapabilities:
    return ProviderCapabilities(**payload)


def _provider_profile_from_dict(payload: dict[str, Any]) -> ProviderProfile:
    capabilities = _provider_capabilities_from_dict(payload.get("capabilities", {}))
    data = dict(payload)
    data["capabilities"] = capabilities
    return ProviderProfile(**data)


def _seat_from_dict(payload: dict[str, Any]) -> CouncilSeat:
    return CouncilSeat(**payload)


def _topology_from_dict(payload: dict[str, Any]) -> CouncilTopology:
    data = dict(payload)
    data["seats"] = [_seat_from_dict(item) for item in payload.get("seats", [])]
    return CouncilTopology(**data)


def _controller_policy_from_dict(payload: dict[str, Any] | None) -> ControllerPolicy | None:
    if payload is None:
        return None
    return ControllerPolicy(**payload)


def _workflow_from_dict(payload: dict[str, Any] | None) -> WorkflowProfile | None:
    if payload is None:
        return None
    return WorkflowProfile(**payload)


def _visualization_from_dict(payload: dict[str, Any] | None) -> VisualizationProfile:
    return VisualizationProfile(**(payload or {}))


def _execution_policy_from_dict(payload: dict[str, Any] | None) -> ExecutionPolicy:
    return ExecutionPolicy(**(payload or {}))


def _watcher_policy_from_dict(payload: dict[str, Any] | None) -> WatcherPolicy:
    return WatcherPolicy(**(payload or {}))


def _onboarding_from_dict(payload: dict[str, Any] | None) -> OnboardingState:
    return OnboardingState(**(payload or {}))


def load_config(path: Path | None = None) -> PijiangConfig:
    config_path = (path or default_config_path()).expanduser().resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return PijiangConfig(
        version=payload.get("version", DEFAULT_COUNCIL_VERSION),
        workspace_root=payload.get("workspace_root", ""),
        output_root=payload.get("output_root", ""),
        cache_root=payload.get("cache_root", ""),
        project_prefix=payload.get("project_prefix", "皮匠"),
        host_mode=payload.get("host_mode", "standalone"),
        provider_profiles=[_provider_profile_from_dict(item) for item in payload.get("provider_profiles", [])],
        council_topology=_topology_from_dict(payload["council_topology"]) if payload.get("council_topology") else None,
        controller_policy=_controller_policy_from_dict(payload.get("controller_policy")),
        workflow=_workflow_from_dict(payload.get("workflow")),
        execution_policy=_execution_policy_from_dict(payload.get("execution_policy")),
        visualization=_visualization_from_dict(payload.get("visualization")),
        onboarding=_onboarding_from_dict(payload.get("onboarding")),
        watcher_policy=_watcher_policy_from_dict(payload.get("watcher_policy")),
    )


def save_config(config: PijiangConfig, path: Path | None = None) -> Path:
    config_path = (path or default_config_path()).expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(config)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config_path


def find_provider(config: PijiangConfig, profile_id: str) -> ProviderProfile | None:
    for profile in config.provider_profiles:
        if profile.id == profile_id:
            return profile
    return None


def active_seats(config: PijiangConfig, *, runnable_only: bool = False) -> list[CouncilSeat]:
    topology = config.council_topology or build_default_council_topology()
    result: list[CouncilSeat] = []
    for seat in topology.seats:
        profile = find_provider(config, seat.profile_id)
        if profile and profile.enabled:
            if runnable_only and profile.config_status != "configured":
                continue
            result.append(seat)
    return result


def unique_active_profile_count(config: PijiangConfig, *, runnable_only: bool = False) -> int:
    return len({seat.profile_id for seat in active_seats(config, runnable_only=runnable_only)})


def council_mode(config: PijiangConfig) -> str:
    seat_count = len(active_seats(config, runnable_only=True))
    profile_count = unique_active_profile_count(config, runnable_only=True)
    if seat_count >= 10 and profile_count >= 6:
        return "standard"
    if seat_count >= 6:
        return "reduced_council_mode"
    return "minimal_mode"
