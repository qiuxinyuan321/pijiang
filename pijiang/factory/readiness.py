from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import PijiangConfig, active_seats, build_default_council_topology, find_provider, unique_active_profile_count
from .endpoints import is_http_provider, resolve_provider_base_url
from .types import EndpointDiagnostic, ProviderProfile, ReadinessIssue, ReadinessReport


def _append_issue(
    issues: list[ReadinessIssue],
    *,
    level: str,
    code: str,
    message: str,
    fix_hint: str = "",
) -> None:
    issues.append(ReadinessIssue(level=level, code=code, message=message, fix_hint=fix_hint))


def _command_exists(profile: ProviderProfile) -> bool:
    if not profile.command:
        return False
    candidate = str(profile.command[0]).strip()
    if not candidate:
        return False
    path = Path(candidate)
    if path.exists():
        return True
    return shutil.which(candidate) is not None


def _path_writable(path_str: str) -> bool:
    if not path_str:
        return False
    path = Path(path_str).expanduser()
    base = path if path.exists() else path.parent
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    probe = base / ".pijiang-write-test.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def build_readiness_report(config: PijiangConfig) -> ReadinessReport:
    blockers: list[ReadinessIssue] = []
    warnings: list[ReadinessIssue] = []
    ready_items: list[str] = []
    endpoint_diagnostics: list[EndpointDiagnostic] = []

    topology = config.council_topology or build_default_council_topology()
    enabled_seats = active_seats(config)
    runnable_seats = active_seats(config, runnable_only=True)
    enabled_profile_count = unique_active_profile_count(config)
    runnable_profile_count = unique_active_profile_count(config, runnable_only=True)

    if not _path_writable(config.visualization.vault_path):
        _append_issue(
            blockers,
            level="blocker",
            code="vault_not_writable",
            message="Obsidian Vault 路径不存在或不可写。",
            fix_hint="修改 vault_path 到一个可写目录，或先运行 cpj init 重新生成默认路径。",
        )
    else:
        ready_items.append("vault_path 可写")

    if not _path_writable(config.cache_root):
        _append_issue(
            blockers,
            level="blocker",
            code="cache_not_writable",
            message="缓存目录不存在或不可写。",
            fix_hint="修改 cache_root 到一个可写目录。",
        )
    else:
        ready_items.append("cache_root 可写")

    if config.controller_policy is None or not config.controller_policy.controller_profile_id:
        _append_issue(
            blockers,
            level="blocker",
            code="missing_controller",
            message="缺少 controller_profile_id。",
            fix_hint="在配置里指定一个主控 profile。",
        )
    else:
        controller = find_provider(config, config.controller_policy.controller_profile_id)
        if controller is None:
            _append_issue(
                blockers,
                level="blocker",
                code="controller_profile_missing",
                message="controller_profile_id 指向的 profile 不存在。",
                fix_hint="修正 controller_profile_id 或补齐对应 profile。",
            )
        elif controller.quality_tier not in {"strong", "elite"}:
            _append_issue(
                warnings,
                level="warning",
                code="weak_controller",
                message="当前 controller 不是 strong/elite，可能影响议会收敛质量。",
                fix_hint="建议切到顶级强模型或高质量 coding plan 作为主控。",
            )
        else:
            ready_items.append("controller 已配置为强模型")

    for profile in config.provider_profiles:
        if not profile.enabled:
            continue
        endpoint_diagnostic: EndpointDiagnostic | None = None
        if is_http_provider(profile):
            endpoint_diagnostic = resolve_provider_base_url(profile)
            endpoint_diagnostics.append(endpoint_diagnostic)
        if profile.config_status == "disabled":
            _append_issue(
                warnings,
                level="warning",
                code=f"profile_disabled:{profile.id}",
                message=f"profile `{profile.id}` 已禁用，不会参与议会。",
                fix_hint="如需该席位参与，请启用该 profile。",
            )
            continue
        if profile.config_status != "configured":
            _append_issue(
                blockers,
                level="blocker",
                code=f"profile_needs_setup:{profile.id}",
                message=f"profile `{profile.id}` 仍是占位模板，尚未完成配置。",
                fix_hint="补齐该 profile 的 key / relay_url / host / port / path_prefix / base_url / command 等信息，并将 config_status 设为 configured。",
            )
            continue
        if endpoint_diagnostic is not None:
            for issue in endpoint_diagnostic.issues:
                if issue == "invalid_scheme":
                    _append_issue(
                        blockers,
                        level="blocker",
                        code=f"profile_invalid_scheme:{profile.id}",
                        message=f"profile `{profile.id}` 的 scheme 只能是 http 或 https。",
                        fix_hint="将 scheme 改成 http 或 https。",
                    )
                elif issue == "invalid_port":
                    _append_issue(
                        blockers,
                        level="blocker",
                        code=f"profile_invalid_port:{profile.id}",
                        message=f"profile `{profile.id}` 的 port 非法，必须在 1 到 65535 之间。",
                        fix_hint="修正 port，或留空以使用默认端口。",
                    )
                elif issue == "missing_endpoint":
                    _append_issue(
                        blockers,
                        level="blocker",
                        code=f"profile_missing_endpoint:{profile.id}",
                        message=f"profile `{profile.id}` 未配置 relay_url、host 或 base_url。",
                        fix_hint="优先填写 relay_url，或填写 host/port/path_prefix，或回退到 legacy base_url。",
                    )
                elif issue == "invalid_root_url":
                    _append_issue(
                        blockers,
                        level="blocker",
                        code=f"profile_invalid_endpoint:{profile.id}",
                        message=f"profile `{profile.id}` 的 endpoint 解析后不是有效 URL。",
                        fix_hint="检查 relay_url、host、path_prefix 或 base_url 是否是合法的 http(s) 地址。",
                    )
        if profile.adapter_type in {"openai_compatible", "planning_api"}:
            if profile.api_key_env and not os.environ.get(profile.api_key_env, "").strip():
                _append_issue(
                    blockers,
                    level="blocker",
                    code=f"profile_missing_api_key:{profile.id}",
                    message=f"profile `{profile.id}` 需要环境变量 `{profile.api_key_env}`，当前未设置。",
                    fix_hint="先设置环境变量，再运行 cpj doctor。",
                )
        elif profile.adapter_type == "command_bridge":
            if not _command_exists(profile):
                _append_issue(
                    blockers,
                    level="blocker",
                    code=f"profile_missing_command:{profile.id}",
                    message=f"profile `{profile.id}` 的 command bridge 不可执行。",
                    fix_hint="补齐 command，或确认命令在 PATH 中可用。",
                )
        if "search" in profile.roles and not profile.capabilities.supports_external_search:
            _append_issue(
                blockers,
                level="blocker",
                code=f"profile_search_capability_missing:{profile.id}",
                message=f"profile `{profile.id}` 被分配到搜索位，但没有 external-search capability。",
                fix_hint="启用外部搜索能力，或换成真正能做外部检索的 profile。",
            )

    if enabled_profile_count < 6:
        _append_issue(
            blockers,
            level="blocker",
            code="too_few_enabled_profiles",
            message="已启用 profile 少于 6 个，无法形成最小多模型议会。",
            fix_hint="至少启用 6 个 profile。",
        )
    if runnable_profile_count < 6:
        _append_issue(
            blockers,
            level="blocker",
            code="too_few_runnable_profiles",
            message="可真实运行的 profile 少于 6 个。",
            fix_hint="先完成必要 profile 的真实配置，或使用 cpj demo 查看系统效果。",
        )
    if len(runnable_seats) < 10:
        _append_issue(
            warnings,
            level="warning",
            code="reduced_council_mode",
            message="当前实际可运行席位少于 10 席，将进入 reduced_council_mode。",
            fix_hint="补齐缺失席位的可运行 provider。",
        )

    status = "ready"
    if blockers:
        status = "blocker"
    elif warnings:
        status = "warning"

    return ReadinessReport(
        status=status,
        standard_topology_seat_count=len(topology.seats),
        enabled_seat_count=len(enabled_seats),
        runnable_seat_count=len(runnable_seats),
        enabled_profile_count=enabled_profile_count,
        runnable_profile_count=runnable_profile_count,
        blockers=blockers,
        warnings=warnings,
        ready_items=ready_items,
        endpoint_diagnostics=endpoint_diagnostics,
    )
