from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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


def _config_path(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return default_config_path()


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_error(message: str) -> int:
    print(f"错误: {message}", file=sys.stderr)
    return 2


def _intro_text(config: PijiangConfig) -> str:
    topology = config.council_topology
    seat_count = topology.seat_count if topology else 0
    provider_count = unique_active_profile_count(config)
    return (
        "皮匠不是单模型回答，也不是一个模型在扮演多个角色。\n"
        "它会引入多个真实模型位，分别承担主控、规划、外部搜索、裨将、混沌、质疑、融合等分析职责，"
        "最后做 发散 -> 对抗 -> 整合 -> 收敛 的多模型思路整合。\n\n"
        f"当前配置启用了 {seat_count} 席拓扑、{provider_count} 个已启用 profile。\n"
        "因为这里引入了大量模型与多轮融合，单次决策会明显慢于普通问答。\n"
        "你将会在执行期间持续看到阶段、席位和产物进度，而不是黑盒等待。"
    )


def _short_reminder(config: PijiangConfig) -> str:
    provider_count = unique_active_profile_count(config)
    return (
        f"本次将启用多模型议会，当前已启用 {provider_count} 个 profile。"
        "这不是单模型扮演多个角色，而是多个真实模型位的分析整合。"
        "标准 11 席议会通常会比普通问答慢很多。"
    )


def _progress_printer(snapshot, event: dict[str, object]) -> None:
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
    print(" ".join(parts))


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
            print("将生成一套官方默认配置：11 席公开议会、cpj 命令面、以及 Obsidian 模板。")
            choice = input("输入 YES 继续，其他任意输入取消: ").strip()
            if choice != "YES":
                print("已取消。")
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
        created = install_obsidian_template(Path(config.visualization.vault_path))
        _print_json(
            {
                "status": "initialized",
                "config_path": str(saved),
                "demo_config_path": str(demo_path),
                "vault_path": config.visualization.vault_path,
                "created_template_files": [str(path) for path in created],
                "next_steps": [
                    "打开 Vault 查看 00-Start-Here.md",
                    "运行 cpj doctor",
                    "运行 cpj demo",
                    "如需三方中转站，可编辑 provider 的 relay_url 或 host/port/path_prefix",
                ],
            }
        )
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


def _render_doctor_human(payload: dict[str, object]) -> str:
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
            print(_render_doctor_human(payload))
        return 0 if payload["readiness_status"] == "ready" else 2
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
            print(_render_doctor_human(_doctor_payload(config)))
            return _print_error("当前配置存在 provider preflight blocker，已拒绝真实运行。先修复后再执行，或先运行 cpj demo。")
        if readiness.warnings and not args.allow_degraded:
            print(_render_doctor_human(_doctor_payload(config)))
            return _print_error("当前配置存在 provider preflight warning。若你确认要带降级继续运行，请显式加上 --allow-degraded。")

        first_run = not config.onboarding.first_run_acknowledged
        if first_run or not config.onboarding.skip_repeated_intro:
            print(_intro_text(config))
        else:
            print(_short_reminder(config))
        print("")
        if not args.yes:
            choice = input("首次或当前运行需要确认。输入 YES 继续执行，其他任意输入取消: ").strip()
            if choice != "YES":
                print("已取消。")
                return 1

        engine = CouncilEngine(config, progress_callback=_progress_printer)
        config.execution_policy.parallel_policy = args.parallel_policy
        summary = engine.run(
            brief_path=brief_path,
            topic=args.topic.strip(),
            timeout_sec=args.timeout_sec,
            max_workers=args.max_workers,
            watcher_mode=args.watcher,
        )
        config.onboarding.first_run_acknowledged = True
        save_config(config, config_path)
        _print_json(summary)
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

        print("正在运行 demo 模式：不会调用真实外部 API，而是生成一套完整示例链路。")
        demo_config.execution_policy.parallel_policy = args.parallel_policy
        engine = CouncilEngine(demo_config, progress_callback=_progress_printer)
        summary = engine.run(
            brief_path=brief_path,
            topic=args.topic.strip(),
            timeout_sec=args.timeout_sec,
            max_workers=args.max_workers,
            watcher_mode=args.watcher,
        )
        _print_json({"demo_config_path": str(demo_path), **summary})
        return 0
    except Exception as exc:
        return _print_error(str(exc))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cpj", description="臭皮匠（cpj）：多模型议会能力层。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="初始化 11 席公开议会配置与官方 Obsidian 模板。")
    init_parser.add_argument("--config", help="配置文件路径。默认写到用户目录。")
    init_parser.add_argument("--workspace-root", help="工作区根目录。默认当前目录。")
    init_parser.add_argument("--output-root", help="输出根目录。默认 <workspace>/output。")
    init_parser.add_argument("--cache-root", help="缓存根目录。默认 <workspace>/.cache/solution-factory。")
    init_parser.add_argument("--vault-path", help="Obsidian Vault 路径。默认 <workspace>/obsidian-vault。")
    init_parser.add_argument("--host-mode", default="standalone", choices=["standalone", "generic-shell", "codex-openclaw-like"])
    init_parser.add_argument("--yes", action="store_true", help="跳过初始化确认。")
    init_parser.set_defaults(func=command_init)

    doctor_parser = subparsers.add_parser("doctor", help="检查当前配置、议会拓扑与可视化状态。")
    doctor_parser.add_argument("--config", help="配置文件路径。")
    doctor_parser.add_argument("--json", action="store_true", help="输出机器可读的 readiness JSON。")
    doctor_parser.set_defaults(func=command_doctor)

    demo_parser = subparsers.add_parser("demo", help="运行零 API 的示例议会，先验证安装与可视化。")
    demo_parser.add_argument("--config", help="主配置文件路径。若存在，将复用其中的可视化设置。")
    demo_parser.add_argument("--brief", help="可选 demo brief 路径。默认自动生成内置示例。")
    demo_parser.add_argument("--topic", default="皮匠-demo", help="demo 议题名称。")
    demo_parser.add_argument("--timeout-sec", type=int, default=120, help="单席超时时间。")
    demo_parser.add_argument("--max-workers", type=int, default=6, help="最大并行席位数。")
    demo_parser.add_argument("--parallel-policy", choices=["strict_all", "ghost_isolation"], default="ghost_isolation", help="并行执行策略。")
    demo_parser.add_argument("--watcher", choices=["auto", "on", "off"], default="off", help="觉者守护层策略。")
    demo_parser.set_defaults(func=command_demo)

    integrate_parser = subparsers.add_parser("integrate", help="生成宿主集成文件，不替换原入口。")
    integrate_parser.add_argument("host", help="宿主名称，例如 codex、openclaw、claude-code、cursor。")
    integrate_parser.add_argument("--config", help="配置文件路径。")
    integrate_parser.add_argument("--output-dir", help="集成产物输出目录。")
    integrate_parser.set_defaults(func=command_integrate)

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
    run_parser.set_defaults(func=command_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
