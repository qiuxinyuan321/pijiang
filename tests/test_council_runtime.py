from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pijiang.factory.analysis as factory_analysis
from pijiang.factory.analysis import build_benchmark_report, load_truth_audit
from pijiang.factory.config import build_default_config, find_provider, save_config
from pijiang.factory.council import CouncilEngine
from pijiang.factory.watcher import recover_abandoned_runs


def write_fake_cli(path: Path) -> None:
    path.write_text(
        """from __future__ import annotations
import json
import os
import re
import sys
import time
from pathlib import Path

def read_prompt() -> str:
    prompt = sys.stdin.read()
    if prompt.strip():
        return prompt
    for arg in reversed(sys.argv[1:]):
        if not arg.startswith("-"):
            return arg
    return ""

def get_option(flag: str) -> str:
    for index, arg in enumerate(sys.argv[1:], start=1):
        if arg == flag and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
    return ""

def extract_marker(prompt: str, marker: str, fallback: str) -> str:
    match = re.search(rf"{re.escape(marker)}:\\s*([^\\n]+)", prompt)
    if match:
        return match.group(1).strip()
    return fallback

def build_body(stage: str, lane: str) -> str:
    if stage == "variant":
        if os.environ.get("PIJIANG_FAKE_BAD_LANE", "").strip() == lane:
            return "bad output without canonical headings"
        evidence = ""
        if lane in {"search-1", "search-2"}:
            evidence = (
                "- 证据：https://example.com/pijiang/runtime-search\\n"
                "- 证据：https://github.com/example/pijiang-runtime\\n"
                "- 证据：https://example.com/pijiang/runtime-benchmark\\n\\n"
            )
        return (
            f"# 问题定义\\n{lane} 输出\\n\\n"
            f"{evidence}"
            "# 目标与非目标\\n验证 runtime 回流链路\\n\\n"
            "# 用户/场景\\n仓库自测\\n\\n"
            "# 系统架构\\n11 席议会\\n\\n"
            "# 模块拆分\\nprogress、audit、benchmark\\n\\n"
            "# 关键流程\\nbrief -> variants -> fusion\\n\\n"
            "# 技术选型\\nPython\\n\\n"
            "# 风险与取舍\\n测试桩只模拟协议\\n\\n"
            "# 里程碑\\n先跑通 runtime\\n\\n"
            "# 待确认问题\\n无\\n"
        )
    if stage == "idea-map":
        return "# 共识点\\n需要 run 后 truth audit。\\n\\n# 独特亮点\\n真实多模型议会。\\n\\n# 冲突点\\n无。\\n\\n# 质疑焦点\\n心跳与质量门是否生效。\\n\\n# 可组合点\\nprogress + audit + benchmark。\\n"
    if stage.startswith("debate-round-"):
        return f"# {stage}\\n- 议题：runtime backflow\\n- 结论：保持结构化输出。\\n"
    if stage == "final-decisions-json":
        return json.dumps(
            {
                "decisions": [
                    {
                        "topic": "runtime backflow",
                        "decision": "回流 progress、truth audit、quality gate。",
                        "sources": [lane],
                        "reason": "这些能力已被真实 run 证实有效。",
                        "skeptic_challenge": "是否会把未验证能力一起回流？",
                        "skeptic_rebuttal": "只回流已验证通过的能力，budget/circuit breaker 继续保留为预留项。",
                        "rejected_options": [
                            {
                                "lane": lane,
                                "option": "一次性回流全部治理能力",
                                "reason": "会超出当前已验证范围。",
                            }
                        ],
                        "open_questions": [],
                    }
                ],
                "fallback_options": [{"topic": "benchmark", "option": "single / reduced6 / standard11"}],
                "next_validation_steps": ["运行 pytest -q"],
            },
            ensure_ascii=False,
        )
    if stage == "final-draft-json":
        return json.dumps(
            {
                "title": "runtime backflow 草案",
                "sections": [
                    {
                        "title": "方案",
                        "content": "回流 progress snapshot、truth audit、regression cases 与 benchmark 汇总。",
                        "sources": [lane],
                        "rationale": "这些能力都能直接提升议会运行可解释性。",
                        "status": "accepted",
                    }
                ],
                "open_questions": [],
                "validation_plan": ["运行 pytest -q"],
            },
            ensure_ascii=False,
        )
    return f"# {stage}\\n来自 {lane} 的结构化结果\\n"

prompt = read_prompt()
stage = extract_marker(prompt, "SF-STAGE", "variant")
lane = extract_marker(prompt, "SF-LANE-ID", "unknown-seat")
slow_lane = os.environ.get("PIJIANG_FAKE_SLOW_LANE", "").strip()
slow_lanes = {item.strip() for item in os.environ.get("PIJIANG_FAKE_SLOW_LANES", "").split(",") if item.strip()}
if slow_lane:
    slow_lanes.add(slow_lane)
slow_sec = float(os.environ.get("PIJIANG_FAKE_SLOW_SEC", "2").strip() or "2")
if slow_lanes and lane in slow_lanes:
    time.sleep(slow_sec)
body = build_body(stage, lane)
output_path = get_option("--output-last-message")
if output_path:
    Path(output_path).write_text(body, encoding="utf-8")
print(body)
""",
        encoding="utf-8",
    )


def build_command_bridge_config(tmp_path: Path, fake_cli: Path):
    config = build_default_config(
        workspace_root=tmp_path / "workspace",
        output_root=tmp_path / "output",
        cache_root=tmp_path / "cache",
        vault_path=tmp_path / "vault",
    )
    for profile in config.provider_profiles:
        profile.adapter_type = "command_bridge"
        profile.command = [sys.executable, str(fake_cli)]
        profile.base_url = ""
        profile.api_key_env = ""
        profile.config_status = "configured"
        if profile.id.startswith("search-"):
            profile.capabilities.supports_external_search = True
    return config


def limit_topology(config, seat_ids: list[str]) -> None:
    config.council_topology.seats = [seat for seat in config.council_topology.seats if seat.seat_id in seat_ids]
    config.council_topology.seat_count = len(config.council_topology.seats)
    config.council_topology.planning_seats = [seat for seat in config.council_topology.planning_seats if seat in seat_ids]
    config.council_topology.search_seats = [seat for seat in config.council_topology.search_seats if seat in seat_ids]
    config.council_topology.marshal_seats = [seat for seat in config.council_topology.marshal_seats if seat in seat_ids]
    if config.council_topology.chaos_seat not in seat_ids:
        config.council_topology.chaos_seat = ""
    if config.council_topology.skeptic_seat not in seat_ids:
        config.council_topology.skeptic_seat = ""
    if config.council_topology.fusion_seat not in seat_ids:
        config.council_topology.fusion_seat = ""
    if config.council_topology.controller_seat not in seat_ids:
        config.council_topology.controller_seat = seat_ids[0]


def run_engine(tmp_path: Path, fake_cli: Path, *, topic: str, seat_ids: list[str], env: dict[str, str] | None = None, progress_callback=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = build_command_bridge_config(tmp_path, fake_cli)
    limit_topology(config, seat_ids)
    brief_path = tmp_path / f"{topic}.md"
    brief_path.write_text("# Brief\n\n测试 runtime 回流。", encoding="utf-8")
    original = {key: os.environ.get(key) for key in (env or {})}
    try:
        for key, value in (env or {}).items():
            os.environ[key] = value
        return CouncilEngine(config, progress_callback=progress_callback).run(
            brief_path=brief_path,
            topic=topic,
            timeout_sec=60,
            max_workers=4,
        )
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_progress_snapshot_contains_runtime_fields(tmp_path: Path, monkeypatch) -> None:
    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)
    snapshots: list[tuple[object, dict[str, str]]] = []
    monkeypatch.setattr("pijiang.factory.council.HEARTBEAT_INTERVAL_SEC", 1)

    def progress(snapshot, event):
        snapshots.append((snapshot, event))

    summary = run_engine(
        tmp_path,
        fake_cli,
        topic="heartbeat",
        seat_ids=["controller"],
        env={"PIJIANG_FAKE_SLOW_LANE": "controller"},
        progress_callback=progress,
    )

    assert summary["status"] == "success"
    heartbeat_snapshots = [snapshot for snapshot, event in snapshots if event["kind"] == "heartbeat"]
    assert heartbeat_snapshots
    assert any(snapshot.current_seat_id for snapshot in heartbeat_snapshots)
    assert any(snapshot.running_seat_ids for snapshot in heartbeat_snapshots)
    assert all(snapshot.updated_at for snapshot in heartbeat_snapshots)


def test_council_run_writes_truth_audit_and_regression_case(tmp_path: Path) -> None:
    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)
    summary = run_engine(
        tmp_path,
        fake_cli,
        topic="audit",
        seat_ids=["controller", "planning", "search-1", "search-2", "skeptic", "fusion"],
        env={"PIJIANG_FAKE_BAD_LANE": "planning"},
    )

    assert summary["status"] == "degraded"
    assert summary["audit_status"] == "degraded"
    assert summary["failed_lane_count"] == 1
    assert summary["run_role"] == "requalification"
    assert summary["run_grade"] == "formal"
    assert summary["baseline_admitted"] is False
    assert summary["truth_audit_path"]
    assert summary["baseline_admission_path"].endswith("75-baseline-admission.md")
    assert summary["regression_case_count"] >= 1
    assert "schema_failure" in summary["reason_codes"]

    audit = load_truth_audit(Path(summary["truth_audit_path"]))
    assert audit.run_id == summary["run_id"]
    assert audit.audit_status == "degraded"
    assert "planning" in audit.degraded_chain_ids
    assert Path(summary["obsidian_output_dir"]).joinpath("02-topology-report.md").exists()
    assert Path(summary["obsidian_output_dir"]).joinpath("03-seat-registry.json").exists()
    assert Path(summary["obsidian_output_dir"]).joinpath("04-provider-preflight-snapshot.json").exists()
    assert Path(summary["obsidian_output_dir"]).joinpath("75-baseline-admission.md").exists()
    assert Path(summary["obsidian_output_dir"]).joinpath("80-regression-cases-index.md").exists()


def test_build_benchmark_report_from_completed_runs(tmp_path: Path) -> None:
    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)

    single = run_engine(tmp_path / "single", fake_cli, topic="single", seat_ids=["controller"])
    reduced = run_engine(
        tmp_path / "reduced",
        fake_cli,
        topic="reduced",
        seat_ids=["controller", "planning", "search-1", "search-2", "skeptic", "fusion"],
    )
    standard = run_engine(
        tmp_path / "standard",
        fake_cli,
        topic="standard",
        seat_ids=["controller", "planning", "search-1", "search-2", "opencode-kimi", "opencode-glm5", "opencode-minimax", "opencode-qwen", "chaos", "skeptic", "fusion"],
    )

    report = build_benchmark_report(
        scenario_id="runtime-backflow",
        summaries_by_mode={"single": single, "reduced6": reduced, "standard11": standard},
    )

    assert [item.mode for item in report.measurements] == ["single", "reduced6", "standard11"]
    assert all(item.truth_audit_path for item in report.measurements)
    assert all(hasattr(item, "audit_pass_success_rate") for item in report.measurements)


def test_ghost_isolation_cuts_over_before_slow_seats(tmp_path: Path) -> None:
    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)

    config = build_command_bridge_config(tmp_path / "ghost", fake_cli)
    config.execution_policy.parallel_policy = "ghost_isolation"
    brief_path = (tmp_path / "ghost" / "ghost.md")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# Brief\n\n验证 ghost isolation。", encoding="utf-8")

    original = {key: os.environ.get(key) for key in {"PIJIANG_FAKE_SLOW_LANES": "", "PIJIANG_FAKE_SLOW_SEC": ""}}
    os.environ["PIJIANG_FAKE_SLOW_LANES"] = "search-2,opencode-qwen"
    os.environ["PIJIANG_FAKE_SLOW_SEC"] = "8"
    try:
        started = time.monotonic()
        summary = CouncilEngine(config).run(
            brief_path=brief_path,
            topic="ghost-isolation",
            timeout_sec=30,
            max_workers=6,
        )
        elapsed = time.monotonic() - started
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert summary["parallel_policy"] == "ghost_isolation"
    assert summary["quorum_reached"] is True
    assert summary["quorum_profile"] == "standard11-quorum6"
    assert summary["ghosted_lane_count"] >= 1
    assert {"search-2", "opencode-qwen"}.issubset(set(summary["ghosted_lane_ids"]))
    assert summary["fusion_cutover_ms"] > 0
    assert elapsed < 8


def test_strict_all_keeps_waiting_for_slow_seats(tmp_path: Path) -> None:
    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)

    config = build_command_bridge_config(tmp_path / "strict", fake_cli)
    config.execution_policy.parallel_policy = "strict_all"
    brief_path = (tmp_path / "strict" / "strict.md")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# Brief\n\n验证 strict_all。", encoding="utf-8")

    original = {key: os.environ.get(key) for key in {"PIJIANG_FAKE_SLOW_LANES": "", "PIJIANG_FAKE_SLOW_SEC": ""}}
    os.environ["PIJIANG_FAKE_SLOW_LANES"] = "search-2,opencode-qwen"
    os.environ["PIJIANG_FAKE_SLOW_SEC"] = "3"
    try:
        started = time.monotonic()
        summary = CouncilEngine(config).run(
            brief_path=brief_path,
            topic="strict-all",
            timeout_sec=30,
            max_workers=6,
        )
        elapsed = time.monotonic() - started
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert summary["parallel_policy"] == "strict_all"
    assert summary["quorum_reached"] is False
    assert summary["ghosted_lane_ids"] == []
    assert elapsed >= 3


def test_watcher_writes_guard_artifacts_for_slow_run(tmp_path: Path) -> None:
    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)

    config = build_command_bridge_config(tmp_path / "watcher", fake_cli)
    config.execution_policy.parallel_policy = "strict_all"
    config.watcher_policy.seat_stall_threshold_sec = 1
    config.watcher_policy.stage_silent_threshold_sec = 1
    brief_path = (tmp_path / "watcher" / "watcher.md")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# Brief\n\n验证觉者守护层。", encoding="utf-8")

    original = {key: os.environ.get(key) for key in {"PIJIANG_FAKE_SLOW_LANES": "", "PIJIANG_FAKE_SLOW_SEC": ""}}
    os.environ["PIJIANG_FAKE_SLOW_LANES"] = "search-2"
    os.environ["PIJIANG_FAKE_SLOW_SEC"] = "2"
    try:
        summary = CouncilEngine(config).run(
            brief_path=brief_path,
            topic="watcher-run",
            timeout_sec=30,
            max_workers=6,
            watcher_mode="on",
        )
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert summary["watcher_enabled"] is True
    assert summary["watcher_alert_count"] >= 1
    assert Path(summary["watcher_advice_path"]).exists()
    assert Path(summary["obsidian_output_dir"]).joinpath("06-juezhe-watch.md").exists()


def test_recover_abandoned_runs_marks_interrupted_run(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    run_dir = cache_root / "runs" / "cpj-abandoned"
    output_dir = tmp_path / "output"
    run_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "cpj-abandoned",
                "owner_pid": 999999,
                "obsidian_output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps(
            {
                "run_id": "cpj-abandoned",
                "owner_pid": 999999,
                "status": "running",
                "stage": "variants",
                "started_at": "2026-03-20T00:00:00Z",
                "finished_at": "",
                "updated_at": "2026-03-20T00:00:00Z",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    recovered = recover_abandoned_runs(cache_root)

    assert recovered
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["watcher_state"] == "recovered"
    assert output_dir.joinpath("06-juezhe-watch.md").exists()


def test_quality_assessment_does_not_treat_normal_gap_discussion_as_missing() -> None:
    markdown = (
        "# 问题定义\n这里讨论当前系统的关键缺口，但这不是占位文案。\n\n"
        "# 目标与非目标\n目标明确。\n\n"
        "# 用户/场景\n场景明确。\n\n"
        "# 系统架构\n架构明确。\n\n"
        "# 模块拆分\n模块明确。\n\n"
        "# 关键流程\n流程明确。\n\n"
        "# 技术选型\n技术明确。\n\n"
        "# 风险与取舍\n风险明确。\n\n"
        "# 里程碑\n里程碑明确。\n\n"
        "# 待确认问题\n无。\n"
    )
    assessment = factory_analysis._build_quality_assessment("controller", markdown)
    assert assessment.schema_valid is True
    assert "missing_sections" not in assessment.reason_codes
