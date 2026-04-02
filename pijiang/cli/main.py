from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.live import Live

from pijiang import __version__
from pijiang.factory.admission import DEMO_RUN_GRADE, DEMO_RUN_ROLE
from pijiang.factory.config import (
    PijiangConfig,
    active_seats,
    build_default_config,
    build_demo_config,
    council_mode,
    default_config_path,
    demo_config_path,
    find_provider,
    load_config,
    save_config,
    unique_active_profile_count,
)
from pijiang.factory.council import CouncilEngine
from pijiang.factory.registry import STANDARD11_PROFILE, STANDARD11_QUORUM_PROFILE
from pijiang.factory.readiness import build_readiness_report
from pijiang.obsidian import install_obsidian_template


console = Console()
err_console = Console(stderr=True)


def _config_path(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return default_config_path()


def _print_json(payload: dict[str, object]) -> None:
    console.print_json(json.dumps(payload, ensure_ascii=False))


def _print_error(message: str) -> int:
    err_console.print(f"[bold red]错误:[/bold red] {message}")
    return 2


# ---------------------------------------------------------------------------
# Rich progress callback for council runs
# ---------------------------------------------------------------------------

class _RichProgressTracker:
    """Wraps a Rich Live display to show seat-level parallel progress."""

    def __init__(self, seat_ids: list[str]) -> None:
        self._seat_ids = seat_ids
        self._statuses: dict[str, str] = {sid: "pending" for sid in seat_ids}
        self._messages: dict[str, str] = {sid: "" for sid in seat_ids}
        self._start = time.monotonic()
        self._live: Live | None = None

    def start(self) -> None:
        self._live = Live(self._build_table(), console=console, refresh_per_second=2)
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()

    def callback(self, snapshot, event: dict[str, object]) -> None:
        seat_id = str(event.get("seat_id", "")).strip()
        message = str(event.get("message", "")).strip()
        kind = str(event.get("kind", "")).strip()

        if seat_id and seat_id in self._statuses:
            if kind == "seat_done":
                self._statuses[seat_id] = "done"
            elif kind == "seat_failed":
                self._statuses[seat_id] = "failed"
            elif kind == "seat_start" or kind == "progress":
                self._statuses[seat_id] = "running"
            self._messages[seat_id] = message or kind

        # Update stage-level info
        stage = str(event.get("stage", "")).strip()
        if stage and not seat_id:
            for sid in self._seat_ids:
                if self._statuses[sid] == "pending":
                    self._messages[sid] = f"[{stage}] {message or kind}"
                    break

        if self._live:
            self._live.update(self._build_table())

    def _build_table(self) -> Table:
        elapsed = int(time.monotonic() - self._start)
        table = Table(
            title=f"[bold]议会执行中[/bold]  ⏱ {elapsed}s",
            show_header=True,
            header_style="bold cyan",
            border_style="dim",
            expand=True,
        )
        table.add_column("席位", style="bold", width=20)
        table.add_column("状态", width=8, justify="center")
        table.add_column("信息", ratio=1)

        status_icons = {
            "pending": "[dim]⏳[/dim]",
            "running": "[yellow]⚡[/yellow]",
            "done": "[green]✅[/green]",
            "failed": "[red]❌[/red]",
        }

        for sid in self._seat_ids:
            status = self._statuses.get(sid, "pending")
            icon = status_icons.get(status, "⏳")
            msg = self._messages.get(sid, "")
            table.add_row(sid, icon, msg)

        done = sum(1 for s in self._statuses.values() if s == "done")
        failed = sum(1 for s in self._statuses.values() if s == "failed")
        table.add_section()
        table.add_row(
            "[bold]合计[/bold]",
            "",
            f"完成 [green]{done}[/green] / 失败 [red]{failed}[/red] / 总计 {len(self._seat_ids)}",
        )
        return table


def _simple_progress_printer(snapshot, event: dict[str, object]) -> None:
    """Fallback progress printer when Rich Live is not appropriate."""
    message = str(event.get("message", "")).strip()
    stage = str(event.get("stage", "")).strip()
    seat_id = str(event.get("seat_id", "")).strip()
    prefix = f"[{snapshot.stage}]"
    if stage and stage != snapshot.stage:
        prefix = f"[{stage}]"
    parts = [prefix]
    if seat_id:
        parts.append(seat_id)
    if message:
        parts.append(message)
    else:
        parts.append(str(event.get("kind", "progress")))
    parts.append(f"完成 {snapshot.completed_seat_count} / 失败 {snapshot.failed_seat_count}")
    console.print(" ".join(parts))


# ---------------------------------------------------------------------------
# Rich rendering helpers
# ---------------------------------------------------------------------------

def _status_style(status: str) -> str:
    mapping = {
        "ready": "[bold green]✅ ready[/bold green]",
        "warning": "[bold yellow]⚠️  warning[/bold yellow]",
        "blocker": "[bold red]❌ blocker[/bold red]",
    }
    return mapping.get(status, status)


def _render_doctor_rich(payload: dict[str, object]) -> None:
    """Render doctor output using Rich tables and panels."""
    # Header
    console.print()
    console.print(Panel(
        f"[bold]皮匠部署体检[/bold]  v{__version__}",
        style="cyan",
    ))

    # Overview table
    overview = Table(show_header=False, border_style="dim", expand=True, padding=(0, 2))
    overview.add_column("项目", style="bold")
    overview.add_column("值")

    overview.add_row("Readiness", _status_style(str(payload["readiness_status"])))
    overview.add_row("Parallel Policy", str(payload["parallel_policy"]))
    overview.add_row("Quorum Profile", str(payload["quorum_profile"]))
    overview.add_row("当前模式", str(payload["council_mode"]))
    overview.add_row("标准拓扑席位", str(payload["standard_topology_seat_count"]))
    overview.add_row("已启用席位", str(payload["enabled_seat_count"]))
    overview.add_row("可运行席位", str(payload["runnable_seat_count"]))
    overview.add_row("已启用 Profiles", str(payload["active_profile_count"]))
    overview.add_row("可运行 Profiles", str(payload["runnable_profile_count"]))
    overview.add_row("Obsidian", "启用" if payload["obsidian_enabled"] else "[dim]未启用[/dim]")
    overview.add_row("Vault", str(payload["vault_path"]))
    console.print(overview)

    # Blockers
    blockers = payload.get("blockers", [])
    if blockers:
        console.print()
        console.print("[bold red]Blockers:[/bold red]")
        for item in blockers:
            console.print(f"  [red]❌[/red] [{item['code']}] {item['message']}")
            if item.get("fix_hint"):
                console.print(f"     [dim]修复建议: {item['fix_hint']}[/dim]")

    # Warnings
    warnings = payload.get("warnings", [])
    if warnings:
        console.print()
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for item in warnings:
            console.print(f"  [yellow]⚠️[/yellow]  [{item['code']}] {item['message']}")
            if item.get("fix_hint"):
                console.print(f"     [dim]修复建议: {item['fix_hint']}[/dim]")

    # Ready items
    ready_items = payload.get("ready_items", [])
    if ready_items:
        console.print()
        console.print("[bold green]Ready:[/bold green]")
        for item in ready_items:
            console.print(f"  [green]✅[/green] {item}")

    # Endpoint diagnostics
    endpoint_diagnostics = payload.get("endpoint_diagnostics", [])
    if endpoint_diagnostics:
        console.print()
        ep_table = Table(title="HTTP Endpoint 诊断", border_style="dim", expand=True)
        ep_table.add_column("Profile", style="bold")
        ep_table.add_column("Adapter")
        ep_table.add_column("Source")
        ep_table.add_column("URL")
        ep_table.add_column("状态", justify="center")
        for item in endpoint_diagnostics:
            status = "[green]✅[/green]" if item["valid"] else "[red]❌[/red]"
            ep_table.add_row(
                item["profile_id"],
                item["adapter_type"],
                item["endpoint_source"],
                item["effective_base_url"] or "[dim]<未解析>[/dim]",
                status,
            )
        console.print(ep_table)

    # Next steps
    console.print()
    console.print(Panel(
        "推荐下一步:\n"
        "  1. [bold]cpj demo[/bold]  — 先看完整示例链路\n"
        "  2. 修复 doctor 中的 blocker\n"
        "  3. [bold]cpj run[/bold]   — 修好后真实运行",
        title="下一步",
        border_style="green",
    ))


def _render_doctor_plain(payload: dict[str, object]) -> str:
    """Plain text doctor output for --json fallback and tests."""
    lines = [
        "皮匠部署体检",
        "",
        f"- readiness: {payload['readiness_status']}",
        f"- provider preflight: {payload['provider_preflight_status']}",
        f"- parallel policy: {payload['parallel_policy']}",
        f"- quorum profile: {payload['quorum_profile']}",
        f"- 标准拓扑席位: {payload['standard_topology_seat_count']}",
        f"- 已启用席位: {payload['enabled_seat_count']}",
        f"- 可真实运行席位: {payload['runnable_seat_count']}",
        f"- 已启用 profiles: {payload['active_profile_count']}",
        f"- 可真实运行 profiles: {payload['runnable_profile_count']}",
        f"- 当前模式: {payload['council_mode']}",
        f"- Obsidian: {'启用' if payload['obsidian_enabled'] else '未启用'}",
        f"- Vault: {payload['vault_path']}",
        "",
    ]
    blockers = payload.get("blockers", [])
    warnings = payload.get("warnings", [])
    ready_items = payload.get("ready_items", [])
    if blockers:
        lines.append("Blockers:")
        for item in blockers:
            lines.append(f"- [{item['code']}] {item['message']}")
            if item.get("fix_hint"):
                lines.append(f"  修复建议: {item['fix_hint']}")
        lines.append("")
    if warnings:
        lines.append("Warnings:")
        for item in warnings:
            lines.append(f"- [{item['code']}] {item['message']}")
            if item.get("fix_hint"):
                lines.append(f"  修复建议: {item['fix_hint']}")
        lines.append("")
    if ready_items:
        lines.append("Ready:")
        for item in ready_items:
            lines.append(f"- {item}")
        lines.append("")
    endpoint_diagnostics = payload.get("endpoint_diagnostics", [])
    if endpoint_diagnostics:
        lines.append("HTTP Endpoint 诊断:")
        for item in endpoint_diagnostics:
            lines.append(
                f"- `{item['profile_id']}` / {item['adapter_type']} / source={item['endpoint_source']} / "
                f"normalized={'是' if item['normalized'] else '否'} / effective_base_url={item['effective_base_url'] or '<未解析>'}"
            )
            issues = item.get("issues", [])
            if issues:
                lines.append(f"  问题: {', '.join(issues)}")
        lines.append("")
    lines.append("推荐下一步:")
    lines.append("- 先运行 cpj demo 看完整示例链路")
    lines.append("- 再逐项修复 doctor 中的 blocker")
    lines.append("- 修好后再运行 cpj run")
    return "\n".join(lines)


def _render_run_summary(summary: dict[str, object]) -> None:
    """Render a beautiful post-run summary panel."""
    status = summary.get("status", "unknown")
    status_style = "green" if status == "completed" else "red"

    lines = []
    lines.append(f"[bold]状态:[/bold] [{status_style}]{status}[/{status_style}]")
    if summary.get("run_id"):
        lines.append(f"[bold]Run ID:[/bold] {summary['run_id']}")
    if summary.get("topic"):
        lines.append(f"[bold]议题:[/bold] {summary['topic']}")
    if summary.get("elapsed_sec"):
        lines.append(f"[bold]耗时:[/bold] {summary['elapsed_sec']}s")
    if summary.get("completed_seats") is not None:
        lines.append(
            f"[bold]席位:[/bold] 完成 [green]{summary.get('completed_seats', 0)}[/green]"
            f" / 失败 [red]{summary.get('failed_seats', 0)}[/red]"
            f" / 总计 {summary.get('total_seats', 0)}"
        )
    if summary.get("output_dir"):
        lines.append(f"[bold]产物目录:[/bold] {summary['output_dir']}")
    if summary.get("truth_audit_path"):
        lines.append(f"[bold]Truth Audit:[/bold] {summary['truth_audit_path']}")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="议会运行摘要",
        border_style=status_style,
    ))


# ---------------------------------------------------------------------------
# Intro text
# ---------------------------------------------------------------------------

def _intro_text(config: PijiangConfig) -> None:
    topology = config.council_topology
    seat_count = topology.seat_count if topology else 0
    provider_count = unique_active_profile_count(config)
    console.print(Panel(
        f"皮匠不是单模型回答，也不是一个模型在扮演多个角色。\n"
        f"它会引入多个真实模型位，分别承担主控、规划、外部搜索、裨将、混沌、质疑、融合等分析职责，"
        f"最后做 [bold]发散 → 对抗 → 整合 → 收敛[/bold] 的多模型思路整合。\n\n"
        f"当前配置启用了 [cyan]{seat_count}[/cyan] 席拓扑、[cyan]{provider_count}[/cyan] 个已启用 profile。\n"
        f"因为这里引入了大量模型与多轮融合，单次决策会明显慢于普通问答。\n"
        f"你将会在执行期间持续看到阶段、席位和产物进度，而不是黑盒等待。",
        title="皮匠多模型议会",
        border_style="cyan",
    ))


def _short_reminder(config: PijiangConfig) -> None:
    provider_count = unique_active_profile_count(config)
    console.print(
        f"[dim]本次将启用多模型议会，当前已启用 {provider_count} 个 profile。"
        f"标准 11 席议会通常会比普通问答慢很多。[/dim]"
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def command_init(args: argparse.Namespace) -> int:
    try:
        config_path = _config_path(args.config)
        workspace_root = Path(args.workspace_root).expanduser().resolve() if args.workspace_root else Path.cwd().resolve()
        output_root = Path(args.output_root).expanduser().resolve() if args.output_root else None
        cache_root = Path(args.cache_root).expanduser().resolve() if args.cache_root else None
        vault_path = Path(args.vault_path).expanduser().resolve() if args.vault_path else None
        config = build_default_config(
            workspace_root=workspace_root,
            output_root=output_root,
            cache_root=cache_root,
            vault_path=vault_path,
            host_mode=args.host_mode,
        )
        if not args.yes:
            console.print("[bold]将生成一套官方默认配置：[/bold]11 席公开议会、cpj 命令面、以及 Obsidian 模板。")
            if not Confirm.ask("继续？", default=True, console=console):
                console.print("[dim]已取消。[/dim]")
                return 1
        saved = save_config(config, config_path)

        demo_config = build_demo_config(
            workspace_root=workspace_root,
            output_root=output_root,
            cache_root=cache_root,
            vault_path=Path(config.visualization.vault_path),
            host_mode=args.host_mode,
        )
        demo_path = save_config(demo_config, demo_config_path(config_path))

        created: list[Path] = []
        if not args.minimal:
            created = install_obsidian_template(Path(config.visualization.vault_path))

        if args.json:
            _print_json(
                {
                    "status": "initialized",
                    "config_path": str(saved),
                    "demo_config_path": str(demo_path),
                    "vault_path": config.visualization.vault_path,
                    "created_template_files": [str(path) for path in created],
                }
            )
        else:
            console.print()
            console.print(Panel(
                f"[bold green]初始化完成[/bold green]\n\n"
                f"  配置文件    {saved}\n"
                f"  Demo 配置   {demo_path}\n"
                f"  Vault 路径  {config.visualization.vault_path}\n"
                f"  模板文件    {len(created)} 个",
                title="皮匠 init",
                border_style="green",
            ))
            console.print()
            console.print("[bold]下一步:[/bold]")
            console.print("  1. 打开 Vault 查看 [cyan]00-Start-Here.md[/cyan]")
            console.print("  2. 运行 [bold]cpj doctor[/bold]")
            console.print("  3. 运行 [bold]cpj demo[/bold]")
            console.print("  4. 编辑 provider 的 relay_url 接入真实模型")
        return 0
    except Exception as exc:
        return _print_error(str(exc))


def _doctor_payload(config: PijiangConfig) -> dict[str, object]:
    topology = config.council_topology
    seats = active_seats(config)
    runnable_seats = active_seats(config, runnable_only=True)
    active_profiles = {seat.profile_id for seat in seats if find_provider(config, seat.profile_id)}
    readiness = build_readiness_report(config)
    return {
        "config_version": config.version,
        "host_mode": config.host_mode,
        "standard_topology_seat_count": len(topology.seats) if topology else 0,
        "enabled_seat_count": len(seats),
        "runnable_seat_count": len(runnable_seats),
        "council_mode": council_mode(config),
        "readiness_status": readiness.status,
        "provider_preflight_status": readiness.status,
        "parallel_policy": config.execution_policy.parallel_policy,
        "quorum_profile": STANDARD11_QUORUM_PROFILE if council_mode(config) == STANDARD11_PROFILE and config.execution_policy.parallel_policy == "ghost_isolation" else "strict-all",
        "active_profile_count": unique_active_profile_count(config),
        "runnable_profile_count": unique_active_profile_count(config, runnable_only=True),
        "active_profile_ids": sorted(active_profiles),
        "obsidian_enabled": config.visualization.obsidian_enabled,
        "vault_path": config.visualization.vault_path,
        "visualization_degraded": config.visualization.visualization_degraded or (not config.visualization.obsidian_enabled),
        "controller_profile_id": config.controller_policy.controller_profile_id if config.controller_policy else "",
        "blockers": [
            {"code": item.code, "message": item.message, "fix_hint": item.fix_hint}
            for item in readiness.blockers
        ],
        "warnings": [
            {"code": item.code, "message": item.message, "fix_hint": item.fix_hint}
            for item in readiness.warnings
        ],
        "ready_items": readiness.ready_items,
        "endpoint_diagnostics": [
            {
                "profile_id": item.profile_id,
                "adapter_type": item.adapter_type,
                "endpoint_source": item.endpoint_source,
                "effective_base_url": item.effective_base_url,
                "normalized": item.normalized,
                "valid": item.valid,
                "issues": item.issues,
            }
            for item in readiness.endpoint_diagnostics
        ],
    }


def command_doctor(args: argparse.Namespace) -> int:
    try:
        config_path = _config_path(args.config)
        if not config_path.exists():
            return _print_error(f"配置文件不存在: {config_path}")
        config = load_config(config_path)
        payload = _doctor_payload(config)
        if args.json:
            _print_json(payload)
        else:
            _render_doctor_rich(payload)
        return 0 if payload["readiness_status"] == "ready" else 2
    except Exception as exc:
        return _print_error(str(exc))


def command_status(args: argparse.Namespace) -> int:
    """Show current configuration overview — like `git status` for pijiang."""
    try:
        config_path = _config_path(args.config)
        if not config_path.exists():
            console.print(Panel(
                f"[dim]未找到配置文件: {config_path}[/dim]\n\n"
                f"运行 [bold]cpj init[/bold] 初始化。",
                title="皮匠 status",
                border_style="yellow",
            ))
            return 1
        config = load_config(config_path)
        readiness = build_readiness_report(config)
        seats = active_seats(config)

        table = Table(title=f"[bold]皮匠 v{__version__}[/bold]", border_style="cyan", expand=True)
        table.add_column("项目", style="bold")
        table.add_column("值")

        table.add_row("配置文件", str(config_path))
        table.add_row("Host Mode", config.host_mode)
        table.add_row("Readiness", _status_style(readiness.status))
        table.add_row("席位", f"{len(seats)} 席启用")
        table.add_row("Profiles", f"{unique_active_profile_count(config)} 个启用")
        table.add_row("Parallel Policy", config.execution_policy.parallel_policy)
        table.add_row("Obsidian", "启用" if config.visualization.obsidian_enabled else "[dim]未启用[/dim]")
        table.add_row("Vault", config.visualization.vault_path or "[dim]未设置[/dim]")

        console.print()
        console.print(table)

        if readiness.blockers:
            console.print(f"\n[red]有 {len(readiness.blockers)} 个 blocker[/red]，运行 [bold]cpj doctor[/bold] 查看详情。")
        elif readiness.warnings:
            console.print(f"\n[yellow]有 {len(readiness.warnings)} 个 warning[/yellow]，运行 [bold]cpj doctor[/bold] 查看详情。")
        else:
            console.print("\n[green]所有检查通过[/green]，可以运行 [bold]cpj demo[/bold] 或 [bold]cpj run[/bold]。")

        return 0
    except Exception as exc:
        return _print_error(str(exc))


def command_integrate(args: argparse.Namespace) -> int:
    try:
        config_path = _config_path(args.config)
        output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else config_path.parent / "integrations" / args.host
        output_dir.mkdir(parents=True, exist_ok=True)
        readme = output_dir / "README.md"
        invocation = output_dir / "cpj-run.txt"
        readme.write_text(
            (
                f"# {args.host} 集成说明\n\n"
                "皮匠是一个高级能力层，不替换原入口，只增加一个可调用的多模型议会能力。\n\n"
                "首次运行会先展示工作原理和耗时提醒，并要求确认后才真正发起调用。\n"
            ),
            encoding="utf-8",
        )
        invocation.write_text(
            f"cpj run --config \"{config_path}\" --brief \"<brief.md>\" --topic \"<会议主题>\"\n",
            encoding="utf-8",
        )
        _print_json(
            {
                "status": "integrated",
                "host": args.host,
                "output_dir": str(output_dir),
                "generated_files": [str(readme), str(invocation)],
            }
        )
        return 0
    except Exception as exc:
        return _print_error(str(exc))


def command_run(args: argparse.Namespace) -> int:
    try:
        config_path = _config_path(args.config)
        if not config_path.exists():
            return _print_error(f"配置文件不存在: {config_path}")
        config = load_config(config_path)
        brief_path = Path(args.brief).expanduser().resolve()
        if not brief_path.exists():
            return _print_error(f"brief 文件不存在: {brief_path}")
        if not config.visualization.obsidian_enabled:
            config.visualization.visualization_degraded = True
        readiness = build_readiness_report(config)
        if readiness.blockers:
            _render_doctor_rich(_doctor_payload(config))
            return _print_error("当前配置存在 provider preflight blocker，已拒绝真实运行。先修复后再执行，或先运行 cpj demo。")
        if readiness.warnings and not args.allow_degraded:
            _render_doctor_rich(_doctor_payload(config))
            return _print_error("当前配置存在 provider preflight warning。若你确认要带降级继续运行，请显式加上 --allow-degraded。")

        first_run = not config.onboarding.first_run_acknowledged
        if first_run or not config.onboarding.skip_repeated_intro:
            _intro_text(config)
        else:
            _short_reminder(config)
        console.print()

        if not args.yes:
            if not Confirm.ask("确认执行？", default=True, console=console):
                console.print("[dim]已取消。[/dim]")
                return 1

        # Build progress tracker
        seats = active_seats(config)
        seat_ids = [s.seat_id for s in seats]
        use_rich = not args.no_color
        tracker = _RichProgressTracker(seat_ids) if use_rich else None
        callback = tracker.callback if tracker else _simple_progress_printer

        config.execution_policy.parallel_policy = args.parallel_policy
        engine = CouncilEngine(config, progress_callback=callback)

        if tracker:
            tracker.start()
        try:
            summary = engine.run(
                brief_path=brief_path,
                topic=args.topic.strip(),
                timeout_sec=args.timeout_sec,
                max_workers=args.max_workers,
                watcher_mode=args.watcher,
                allow_degraded=bool(args.allow_degraded),
            )
        finally:
            if tracker:
                tracker.stop()

        config.onboarding.first_run_acknowledged = True
        save_config(config, config_path)

        if args.json:
            _print_json(summary)
        else:
            _render_run_summary(summary)
        return 0
    except Exception as exc:
        return _print_error(str(exc))


def command_demo(args: argparse.Namespace) -> int:
    try:
        config_path = _config_path(args.config)
        if args.config and not config_path.exists():
            return _print_error(f"配置文件不存在: {config_path}")
        base_config: PijiangConfig | None = load_config(config_path) if config_path.exists() else None
        demo_path = demo_config_path(config_path)
        if demo_path.exists():
            demo_config = load_config(demo_path)
        else:
            demo_config = build_demo_config(
                workspace_root=Path(base_config.workspace_root) if base_config else Path.cwd(),
                output_root=Path(base_config.output_root) if base_config else None,
                cache_root=Path(base_config.cache_root) if base_config else None,
                vault_path=Path(base_config.visualization.vault_path) if base_config else None,
                host_mode=base_config.host_mode if base_config else "standalone",
            )
            save_config(demo_config, demo_path)

        if base_config is not None:
            demo_config.visualization = base_config.visualization
            demo_config.project_prefix = base_config.project_prefix
            demo_config.workspace_root = base_config.workspace_root
            demo_config.output_root = base_config.output_root
            demo_config.cache_root = str((Path(base_config.cache_root) / "demo").resolve())
        save_config(demo_config, demo_path)

        brief_path = Path(args.brief).expanduser().resolve() if args.brief else None
        if brief_path is None:
            brief_path = Path(demo_config.workspace_root).expanduser().resolve() / "cpj-demo-brief.md"
            brief_path.parent.mkdir(parents=True, exist_ok=True)
            brief_path.write_text(
                "# Demo Brief\n\n"
                "请展示皮匠 11 席公开议会在没有真实 API 的情况下，如何仍然把完整产物链展示给新用户。\n",
                encoding="utf-8",
            )
        elif not brief_path.exists():
            return _print_error(f"demo brief 文件不存在: {brief_path}")

        console.print(Panel(
            "[bold]Demo 模式[/bold]：不会调用真实外部 API，生成完整示例链路。",
            border_style="cyan",
        ))

        # Build progress tracker
        seats = active_seats(demo_config)
        seat_ids = [s.seat_id for s in seats]
        use_rich = not args.no_color
        tracker = _RichProgressTracker(seat_ids) if use_rich else None
        callback = tracker.callback if tracker else _simple_progress_printer

        demo_config.execution_policy.parallel_policy = args.parallel_policy
        engine = CouncilEngine(demo_config, progress_callback=callback)

        if tracker:
            tracker.start()
        try:
            summary = engine.run(
                brief_path=brief_path,
                topic=args.topic.strip(),
                timeout_sec=args.timeout_sec,
                max_workers=args.max_workers,
                watcher_mode=args.watcher,
                allow_degraded=False,
                run_role=DEMO_RUN_ROLE,
                run_grade=DEMO_RUN_GRADE,
            )
        finally:
            if tracker:
                tracker.stop()

        if args.json:
            _print_json({"demo_config_path": str(demo_path), **summary})
        else:
            _render_run_summary(summary)
        return 0
    except Exception as exc:
        return _print_error(str(exc))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_HELP_EPILOG = """
[黄金路径]
  cpj init --yes    初始化配置
  cpj doctor        体检 readiness
  cpj demo          零 API 演示
  cpj run           真实议会运行

先看到价值，再接真实 provider；先过 doctor，再进 real run。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpj",
        description="臭皮匠（cpj）：多模型议会能力层。",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"cpj (皮匠) {__version__}")
    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出（CI 场景）。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="初始化 11 席公开议会配置与官方 Obsidian 模板。")
    init_parser.add_argument("--config", help="配置文件路径。默认写到用户目录。")
    init_parser.add_argument("--workspace-root", help="工作区根目录。默认当前目录。")
    init_parser.add_argument("--output-root", help="输出根目录。默认 <workspace>/output。")
    init_parser.add_argument("--cache-root", help="缓存根目录。默认 <workspace>/.cache/solution-factory。")
    init_parser.add_argument("--vault-path", help="Obsidian Vault 路径。默认 <workspace>/obsidian-vault。")
    init_parser.add_argument("--host-mode", default="standalone", choices=["standalone", "generic-shell", "codex-openclaw-like"])
    init_parser.add_argument("--yes", action="store_true", help="跳过初始化确认。")
    init_parser.add_argument("--minimal", action="store_true", help="只生成配置，不生成 Obsidian 模板。")
    init_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    init_parser.set_defaults(func=command_init)

    # doctor
    doctor_parser = subparsers.add_parser("doctor", help="检查当前配置、议会拓扑与可视化状态。")
    doctor_parser.add_argument("--config", help="配置文件路径。")
    doctor_parser.add_argument("--json", action="store_true", help="输出机器可读的 readiness JSON。")
    doctor_parser.set_defaults(func=command_doctor)

    # status
    status_parser = subparsers.add_parser("status", help="查看当前配置概览。")
    status_parser.add_argument("--config", help="配置文件路径。")
    status_parser.set_defaults(func=command_status)

    # demo
    demo_parser = subparsers.add_parser("demo", help="运行零 API 的示例议会，先验证安装与可视化。")
    demo_parser.add_argument("--config", help="主配置文件路径。若存在，将复用其中的可视化设置。")
    demo_parser.add_argument("--brief", help="可选 demo brief 路径。默认自动生成内置示例。")
    demo_parser.add_argument("--topic", default="皮匠-demo", help="demo 议题名称。")
    demo_parser.add_argument("--timeout-sec", type=int, default=120, help="单席超时时间。")
    demo_parser.add_argument("--max-workers", type=int, default=6, help="最大并行席位数。")
    demo_parser.add_argument("--parallel-policy", choices=["strict_all", "ghost_isolation"], default="ghost_isolation", help="并行执行策略。")
    demo_parser.add_argument("--watcher", choices=["auto", "on", "off"], default="off", help="觉者守护层策略。")
    demo_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    demo_parser.set_defaults(func=command_demo)

    # integrate
    integrate_parser = subparsers.add_parser("integrate", help="生成宿主集成文件，不替换原入口。")
    integrate_parser.add_argument("host", help="宿主名称，例如 codex、openclaw、claude-code、cursor。")
    integrate_parser.add_argument("--config", help="配置文件路径。")
    integrate_parser.add_argument("--output-dir", help="集成产物输出目录。")
    integrate_parser.set_defaults(func=command_integrate)

    # run
    run_parser = subparsers.add_parser("run", help="运行一次多模型议会。")
    run_parser.add_argument("--config", help="配置文件路径。")
    run_parser.add_argument("--brief", required=True, help="Brief Markdown 路径。")
    run_parser.add_argument("--topic", required=True, help="议题名称。")
    run_parser.add_argument("--timeout-sec", type=int, default=900, help="单席超时时间。")
    run_parser.add_argument("--max-workers", type=int, default=6, help="最大并行席位数。")
    run_parser.add_argument("--parallel-policy", choices=["strict_all", "ghost_isolation"], default="ghost_isolation", help="并行执行策略。")
    run_parser.add_argument("--watcher", choices=["auto", "on", "off"], default="auto", help="觉者守护层策略。")
    run_parser.add_argument("--yes", action="store_true", help="跳过运行前确认。")
    run_parser.add_argument("--allow-degraded", action="store_true", help="显式允许带 warning 的降级运行。")
    run_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    run_parser.set_defaults(func=command_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Apply --no-color globally
    if getattr(args, "no_color", False):
        global console, err_console
        console = Console(no_color=True, highlight=False)
        err_console = Console(stderr=True, no_color=True, highlight=False)
    # Inject no_color into args for downstream use
    if not hasattr(args, "no_color"):
        args.no_color = False
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
