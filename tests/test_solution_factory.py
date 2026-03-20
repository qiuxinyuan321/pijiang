from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tools.solution_factory.core as solution_factory_core
from tools.solution_factory import DEFAULT_LANES, SolutionFactory, SolutionFactoryConfig


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
        return (
            f"# 问题定义\\n{lane} 输出\\n\\n"
            "# 目标与非目标\\n验证议会主链路\\n\\n"
            "# 用户/场景\\n仓库自测\\n\\n"
            "# 系统架构\\n多模型议会\\n\\n"
            "# 模块拆分\\n变体、融合、落盘\\n\\n"
            "# 关键流程\\nbrief -> variants -> fusion\\n\\n"
            "# 技术选型\\nPython\\n\\n"
            "# 风险与取舍\\n假 CLI 只模拟协议\\n\\n"
            "# 里程碑\\n先跑通测试\\n\\n"
            "# 待确认问题\\n无\\n"
        )
    if stage == "idea-map":
        return "# 共识点\\n协议兼容\\n\\n# 独特亮点\\n真实多模型议会\\n\\n# 冲突点\\n无\\n\\n# 质疑焦点\\n测试桩是否覆盖 fusion\\n\\n# 可组合点\\nlane 预设 + 落盘\\n"
    if stage.startswith("debate-round-"):
        return f"# {stage}\\n- 议题：测试协议\\n- 结论：保持结构化输出\\n"
    if stage == "final-decisions-json":
        return json.dumps(
            {
                "decisions": [
                    {
                        "topic": "测试桩协议",
                        "decision": "假 CLI 必须同时覆盖 variant、fusion text、fusion json 三类输出。",
                        "sources": [lane],
                        "reason": "这样才能验证真实议会主链路，而不是只测一半协议。",
                        "skeptic_challenge": "会不会把测试写得过于耦合实现细节？",
                        "skeptic_rebuttal": "这里只耦合公共协议，不耦合具体模型内容，属于必要约束。",
                        "rejected_options": [
                            {
                                "lane": lane,
                                "option": "只模拟 variant 阶段",
                                "reason": "无法覆盖 fusion 阶段的 output-last-message 与 JSON 输出。",
                            }
                        ],
                        "open_questions": [],
                    }
                ],
                "fallback_options": [{"topic": "lane 预设", "option": "default10 全量运行"}],
                "next_validation_steps": ["运行 pytest -q"],
            },
            ensure_ascii=False,
        )
    if stage == "final-draft-json":
        return json.dumps(
            {
                "title": "皮匠测试终版草案",
                "sections": [
                    {
                        "title": "方案",
                        "content": "修复 lane 预设、包装脚本和测试桩。",
                        "sources": [lane],
                        "rationale": "保证仓库独立可验证。",
                        "status": "accepted",
                    }
                ],
                "open_questions": [],
                "validation_plan": ["pytest -q"],
            },
            ensure_ascii=False,
        )
    return f"# {stage}\\n来自 {lane} 的结构化结果\\n"


prompt = read_prompt()
stage = extract_marker(prompt, "SF-STAGE", "variant")
lane = extract_marker(prompt, "SF-LANE-ID", "codex-gpt")
slow_lanes = {item.strip() for item in os.environ.get("PIJIANG_FAKE_SLOW_LANES", "").split(",") if item.strip()}
slow_sec = float(os.environ.get("PIJIANG_FAKE_SLOW_SEC", "0").strip() or "0")
if slow_lanes and lane in slow_lanes:
    time.sleep(slow_sec)
body = build_body(stage, lane)
output_path = get_option("--output-last-message")
if output_path:
    Path(output_path).write_text(body, encoding="utf-8")
if "run" in sys.argv[1:]:
    print(json.dumps({"type": "text", "part": {"text": body}}, ensure_ascii=False))
else:
    print(body)
""",
        encoding="utf-8",
    )


def test_solution_factory_can_run_with_fake_clis(tmp_path: Path) -> None:
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("# Brief\\n\\n测试皮匠议会。", encoding="utf-8")

    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)

    config = SolutionFactoryConfig(
        workspace_root=tmp_path / "workspace",
        cache_root=tmp_path / "cache",
        obsidian_root=tmp_path / "obsidian",
        project_path=r"议会\\测试议题",
        command_overrides={
            "codex": [sys.executable, str(fake_cli)],
            "claude": [sys.executable, str(fake_cli)],
            "opencode": [sys.executable, str(fake_cli)],
        },
        timeout_sec=60,
        max_workers=4,
    )
    config.workspace_root.mkdir(parents=True, exist_ok=True)

    summary = SolutionFactory(config).run(brief_path=brief_path, lanes="reduced6")

    output_dir = Path(summary["obsidian_output_dir"])
    assert summary["failed_lane_count"] == 0
    assert summary["requested_lane_profile"] == "reduced6"
    assert summary["effective_lane_profile"] == "reduced6"
    assert summary["truth_audit_path"].endswith("70-run-truth-audit.json")
    assert summary["watcher_enabled"] is True
    assert summary["watcher_advice_path"].endswith("06-juezhe-watch.md")
    assert (output_dir / "00-brief.md").exists()
    assert (output_dir / "05-preflight.md").exists()
    assert (output_dir / "06-juezhe-watch.md").exists()
    assert (output_dir / "30-idea-map.md").exists()
    assert (output_dir / "40-debate-round-1.md").exists()
    assert (output_dir / "41-debate-round-2.md").exists()
    assert (output_dir / "50-fusion-decisions.md").exists()
    assert (output_dir / "90-final-solution-draft.md").exists()
    assert (output_dir / "70-run-truth-audit.json").exists()
    assert (output_dir / "99-index.md").exists()


def test_lane_presets_match_expected_sizes(tmp_path: Path) -> None:
    config = SolutionFactoryConfig(
        workspace_root=tmp_path / "workspace",
        cache_root=tmp_path / "cache",
        obsidian_root=tmp_path / "obsidian",
        project_path=r"议会\\测试议题",
    )
    factory = SolutionFactory(config)

    assert factory._select_lanes("single")[0] == "single"
    assert len(factory._select_lanes("single")[1]) == 1
    assert factory._select_lanes("default6")[0] == "reduced6"
    assert len(factory._select_lanes("default6")[1]) == 6
    assert len(factory._select_lanes("default9")[1]) == 9
    assert factory._select_lanes("default10")[0] == "standard10"
    assert len(factory._select_lanes("default10")[1]) == len(DEFAULT_LANES)


def test_resolve_command_prefix_uses_real_binary_path(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        if name == "codex":
            return r"C:\Tools\codex.CMD"
        if name == "claude":
            return r"C:\Tools\claude.EXE"
        return None

    monkeypatch.setattr(solution_factory_core.shutil, "which", fake_which)

    assert solution_factory_core.resolve_command_prefix("codex", workspace_root=tmp_path) == [r"C:\Tools\codex.CMD"]
    assert solution_factory_core.resolve_command_prefix("claude", workspace_root=tmp_path) == [r"C:\Tools\claude.EXE"]


def test_preflight_degrades_standard10_to_reduced6_when_opencode_missing(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        if name == "codex":
            return r"C:\Tools\codex.CMD"
        if name == "claude":
            return r"C:\Tools\claude.EXE"
        return None

    monkeypatch.setattr(solution_factory_core.shutil, "which", fake_which)

    config = SolutionFactoryConfig(
        workspace_root=tmp_path / "workspace",
        cache_root=tmp_path / "cache",
        obsidian_root=tmp_path / "obsidian",
        project_path=r"议会\\测试议题",
    )
    factory = SolutionFactory(config)
    requested_profile, requested_lanes = factory._select_lanes("standard10")
    effective_profile, effective_lanes, preflight = factory._preflight_lanes(
        requested_profile=requested_profile,
        requested_lanes=requested_lanes,
    )

    assert effective_profile == "reduced6"
    assert [lane.id for lane in effective_lanes] == [lane.id for lane in DEFAULT_LANES[:6]]
    assert "opencode-kimi" in preflight["unavailable_lane_ids"]
    assert any(issue["code"] == "profile_degraded" for issue in preflight["issues"])


def test_solution_factory_watcher_emits_alert_for_slow_lane(tmp_path: Path) -> None:
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("# Brief\n\n测试觉者 watcher。", encoding="utf-8")
    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)

    config = SolutionFactoryConfig(
        workspace_root=tmp_path / "workspace",
        cache_root=tmp_path / "cache",
        obsidian_root=tmp_path / "obsidian",
        project_path=r"议会\\觉者测试",
        command_overrides={
            "codex": [sys.executable, str(fake_cli)],
            "claude": [sys.executable, str(fake_cli)],
        },
        timeout_sec=60,
        max_workers=2,
    )
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.watcher_policy.seat_stall_threshold_sec = 1
    config.watcher_policy.stage_silent_threshold_sec = 1
    original_env = {key: os.environ.get(key) for key in {"PIJIANG_FAKE_SLOW_LANES", "PIJIANG_FAKE_SLOW_SEC"}}
    os.environ["PIJIANG_FAKE_SLOW_LANES"] = "codex-gpt"
    os.environ["PIJIANG_FAKE_SLOW_SEC"] = "2"
    try:
        summary = SolutionFactory(config).run(brief_path=brief_path, lanes="reduced6", watcher_mode="on")
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert summary["watcher_enabled"] is True
    assert summary["watcher_alert_count"] >= 1
    output_dir = Path(summary["obsidian_output_dir"])
    assert output_dir.joinpath("06-juezhe-watch.md").exists()
