from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pijiang.cli.main import main
from pijiang.factory.config import build_default_config, load_config, save_config


def write_fake_cli(path: Path) -> None:
    path.write_text(
        """from __future__ import annotations
import json
import re
import sys
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
                "- 证据：https://example.com/pijiang/search-evidence\\n"
                "- 证据：https://github.com/example/pijiang-search-case\\n"
                "- 证据：https://example.com/pijiang/search-benchmark\\n\\n"
            )
        return (
            f"# 问题定义\\n{lane} 输出\\n\\n"
            f"{evidence}"
            "# 目标与非目标\\n验证 cpj 主链路\\n\\n"
            "# 用户/场景\\n仓库自测\\n\\n"
            "# 系统架构\\n10 席议会\\n\\n"
            "# 模块拆分\\n配置、运行、进度、可视化\\n\\n"
            "# 关键流程\\nbrief -> variants -> fusion\\n\\n"
            "# 技术选型\\nPython\\n\\n"
            "# 风险与取舍\\n测试桩只模拟协议\\n\\n"
            "# 里程碑\\n先跑通 cpj\\n\\n"
            "# 待确认问题\\n无\\n"
        )
    if stage == "idea-map":
        return "# 共识点\\n协议兼容\\n\\n# 独特亮点\\n真实多模型议会\\n\\n# 冲突点\\n无\\n\\n# 质疑焦点\\n测试桩是否覆盖 fusion\\n\\n# 可组合点\\ncpj + 10 席拓扑\\n"
    if stage.startswith("debate-round-"):
        return f"# {stage}\\n- 议题：cpj 主链路\\n- 结论：保持结构化输出\\n"
    if stage == "final-decisions-json":
        return json.dumps(
            {
                "decisions": [
                    {
                        "topic": "cpj 主链路",
                        "decision": "保留 10 席议会拓扑与首次确认流程。",
                        "sources": [lane],
                        "reason": "这样才能体现多模型思路整合，而不是单模型角色扮演。",
                        "skeptic_challenge": "会不会导致等待更久？",
                        "skeptic_rebuttal": "通过阶段反馈和进度可视化降低等待焦虑。",
                        "rejected_options": [
                            {
                                "lane": lane,
                                "option": "退回单模型多角色扮演",
                                "reason": "不符合皮匠的真实多模型议会定位。",
                            }
                        ],
                        "open_questions": [],
                    }
                ],
                "fallback_options": [{"topic": "议会规模", "option": "reduced_council_mode"}],
                "next_validation_steps": ["运行 pytest -q"],
            },
            ensure_ascii=False,
        )
    if stage == "final-draft-json":
        return json.dumps(
            {
                "title": "cpj 测试终版草案",
                "sections": [
                    {
                        "title": "方案",
                        "content": "验证 cpj 初始化、运行、Obsidian 模板与 10 席议会输出。",
                        "sources": [lane],
                        "rationale": "保证首发命令面与运行器可用。",
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
lane = extract_marker(prompt, "SF-LANE-ID", "unknown-seat")
body = build_body(stage, lane)
output_path = get_option("--output-last-message")
if output_path:
    Path(output_path).write_text(body, encoding="utf-8")
print(body)
""",
        encoding="utf-8",
    )


def build_command_bridge_config(tmp_path: Path, fake_cli: Path) -> Path:
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
        if profile.id.startswith("planning-"):
            profile.capabilities.supports_planning = True
    config_path = tmp_path / "config.json"
    save_config(config, config_path)
    return config_path


def test_cpj_init_writes_default_config_and_vault(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    vault_path = tmp_path / "vault"
    exit_code = main(
        [
            "init",
            "--config",
            str(config_path),
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--vault-path",
            str(vault_path),
            "--yes",
        ]
    )
    assert exit_code == 0
    assert config_path.exists()
    assert (tmp_path / "demo-config.json").exists()
    assert (vault_path / "00-Start-Here.md").exists()
    assert (vault_path / "10-Dashboards" / "10席议会拓扑.md").exists()
    config = load_config(config_path)
    controller = config.provider_profiles[0]
    assert controller.relay_url == ""
    assert controller.scheme == "https"
    assert controller.host == ""
    assert controller.port is None
    assert controller.path_prefix == ""


def test_cpj_doctor_reports_blockers_for_placeholder_config(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    save_config(build_default_config(workspace_root=tmp_path / "workspace", vault_path=tmp_path / "vault"), config_path)
    exit_code = main(["doctor", "--config", str(config_path)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "readiness: blocker" in captured.out
    assert "profile `controller-primary` 仍是占位模板" in captured.out


def test_cpj_demo_generates_demo_run_without_real_api(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(build_default_config(workspace_root=tmp_path / "workspace", vault_path=tmp_path / "vault"), config_path)
    exit_code = main(["demo", "--config", str(config_path), "--topic", "demo议题"])
    assert exit_code == 0
    demo_run_root = tmp_path / "vault" / "皮匠" / "demo议题" / "方案工厂"
    output_dirs = list(demo_run_root.iterdir())
    assert len(output_dirs) == 1
    output_dir = output_dirs[0]
    assert (output_dir / "01-run-overview.md").exists()
    assert (output_dir / "30-idea-map.md").exists()
    assert (output_dir / "50-fusion-decisions.md").exists()
    assert (output_dir / "90-final-solution-draft.md").exists()


def test_cpj_demo_rejects_missing_explicit_config(tmp_path: Path, capsys) -> None:
    missing_config = tmp_path / "missing.json"
    exit_code = main(["demo", "--config", str(missing_config)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "配置文件不存在" in captured.err


def test_cpj_run_executes_full_council_with_command_bridge_profiles(tmp_path: Path) -> None:
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("# Brief\n\n测试 cpj 10 席议会。", encoding="utf-8")
    fake_cli = tmp_path / "fake_cli.py"
    write_fake_cli(fake_cli)
    config_path = build_command_bridge_config(tmp_path, fake_cli)

    exit_code = main(
        [
            "run",
            "--config",
            str(config_path),
            "--brief",
            str(brief_path),
            "--topic",
            "测试议题",
            "--yes",
            "--timeout-sec",
            "60",
            "--max-workers",
            "4",
        ]
    )
    assert exit_code == 0

    config = load_config(config_path)
    assert config.onboarding.first_run_acknowledged is True

    run_root = Path(config.cache_root) / "runs"
    runs = list(run_root.iterdir())
    assert len(runs) == 1
    run_dir = runs[0]
    assert (run_dir / "status.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "summary.json").exists()

    output_root = Path(config.visualization.vault_path) / config.project_prefix / "测试议题" / "方案工厂"
    output_dirs = list(output_root.iterdir())
    assert len(output_dirs) == 1
    output_dir = output_dirs[0]
    assert (output_dir / "01-run-overview.md").exists()
    assert (output_dir / "10-controller.md").exists()
    assert (output_dir / "11-planning.md").exists()
    assert (output_dir / "30-idea-map.md").exists()
    assert (output_dir / "50-fusion-decisions.md").exists()
    assert (output_dir / "90-final-solution-draft.md").exists()
    assert (output_dir / "70-run-truth-audit.json").exists()
    assert (output_dir / "80-regression-cases-index.md").exists()


def test_cpj_run_refuses_placeholder_config_without_allow_degraded(tmp_path: Path, capsys) -> None:
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("# Brief\n\n测试真实运行门禁。", encoding="utf-8")
    config_path = tmp_path / "config.json"
    save_config(build_default_config(workspace_root=tmp_path / "workspace", vault_path=tmp_path / "vault"), config_path)
    exit_code = main(["run", "--config", str(config_path), "--brief", str(brief_path), "--topic", "测试议题", "--yes"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "provider preflight blocker" in captured.err
