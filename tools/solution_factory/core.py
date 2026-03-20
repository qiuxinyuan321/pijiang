from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import os.path
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pijiang.factory.registry import LEGACY_PROFILE_ALIASES, LEGACY_STANDARD10_PROFILE, SEAT_REGISTRY_VERSION, STANDARD11_PROFILE
from pijiang.factory.runtime_support import trim_to_canonical_markdown, variant_quality_issue
from pijiang.factory.types import WatcherPolicy
from pijiang.factory.watcher import WatcherMonitor, WatcherRecorder, recover_abandoned_runs, watcher_enabled
from tools.workspace_paths import REPO_ROOT, get_workspace_drive_root, get_workspace_name, get_workspace_root


DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


CANONICAL_SECTIONS = [
    "问题定义",
    "目标与非目标",
    "用户/场景",
    "系统架构",
    "模块拆分",
    "关键流程",
    "技术选型",
    "风险与取舍",
    "里程碑",
    "待确认问题",
]

SECTION_ALIASES = {
    "问题定义": ["问题定义", "问题", "problem", "problem statement", "context"],
    "目标与非目标": ["目标与非目标", "目标", "非目标", "goals and non-goals", "goals", "non-goals"],
    "用户/场景": ["用户/场景", "用户", "场景", "users and scenarios", "users", "scenarios"],
    "系统架构": ["系统架构", "架构", "architecture", "system architecture"],
    "模块拆分": ["模块拆分", "模块", "module breakdown", "modules"],
    "关键流程": ["关键流程", "流程", "key flows", "flows"],
    "技术选型": ["技术选型", "技术", "tech stack", "technology choices", "technology"],
    "风险与取舍": ["风险与取舍", "风险", "trade-offs", "risks", "risks and trade-offs"],
    "里程碑": ["里程碑", "milestones", "milestone"],
    "待确认问题": ["待确认问题", "开放问题", "open questions", "questions to confirm"],
}

SECTION_ALIAS_MAP = {
    re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", alias.lower()): canonical
    for canonical, aliases in SECTION_ALIASES.items()
    for alias in aliases
}


FINAL_DECISIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "decision": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "skeptic_challenge": {"type": "string"},
                    "skeptic_rebuttal": {"type": "string"},
                    "rejected_options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lane": {"type": "string"},
                                "option": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                            "required": ["lane", "option", "reason"],
                            "additionalProperties": False,
                        },
                    },
                    "open_questions": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "topic",
                    "decision",
                    "sources",
                    "reason",
                    "skeptic_challenge",
                    "skeptic_rebuttal",
                    "rejected_options",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        },
        "fallback_options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "option": {"type": "string"},
                },
                "required": ["topic", "option"],
                "additionalProperties": False,
            },
        },
        "next_validation_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decisions", "fallback_options", "next_validation_steps"],
    "additionalProperties": False,
}


FINAL_DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["title", "content", "sources", "rationale", "status"],
                "additionalProperties": False,
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "validation_plan": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "sections", "open_questions", "validation_plan"],
    "additionalProperties": False,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_heading(heading: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", heading.lower())


def stage_marker_block(stage: str, lane_id: str) -> str:
    return f"SF-STAGE: {stage}\nSF-LANE-ID: {lane_id}\n"


@dataclass(frozen=True)
class LaneSpec:
    id: str
    source_cli: str
    family: str
    model: str
    thinking_angle: str
    obsidian_filename: str
    special_instructions: str = ""


@dataclass
class PreparedCommand:
    command: list[str]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    stdin_text: str | None = None


@dataclass
class SolutionFactoryConfig:
    workspace_root: Path
    cache_root: Path
    obsidian_root: Path
    project_path: str
    command_overrides: dict[str, list[str] | str] = field(default_factory=dict)
    timeout_sec: int = 900
    max_workers: int = 6
    fusion_lane_id: str = "codex-gpt"
    append_factory_dir: bool = True
    codex_reasoning_effort: str | None = "xhigh"
    codex_reasoning_summary: str | None = "auto"
    claude_effort: str | None = "max"
    opencode_variant: str | None = "max"
    retry_attempts: int = 2
    watcher_policy: WatcherPolicy = field(default_factory=WatcherPolicy)


@dataclass
class LaneResult:
    lane: LaneSpec
    status: str
    started_at: str
    finished_at: str
    lane_run_dir: Path
    raw_stdout_path: Path
    raw_stderr_path: Path
    raw_output_path: Path | None
    normalized_markdown_path: Path
    variant_result_path: Path
    error_summary: str = ""
    sections: dict[str, str] = field(default_factory=dict)


DEFAULT_LANES = [
    LaneSpec("codex-gpt", "codex", "codex", DEFAULT_CODEX_MODEL, "从工程编排、可执行性和流程收敛角度提出方案。", "10-codex-gpt.md"),
    LaneSpec("claude-gpt", "claude", "claude", DEFAULT_CLAUDE_MODEL, "从结构表达、风险边界和标准化输出角度提出方案。", "11-claude-gpt.md"),
    LaneSpec(
        "codex-github-cases",
        "codex",
        "codex",
        DEFAULT_CODEX_MODEL,
        "从 GitHub 上相关项目案例、仓库结构和可复用模式角度提出方案。",
        "12-codex-github-cases.md",
        "你必须先主动检索 GitHub 上与 interactive book、reading tutor、narrative engine、world model、learning app、branching story、knowledge graph 等相关的项目案例，再基于案例输出方案。至少吸收 5 个相关项目/仓库的可借鉴点、不可借鉴点与适用原因，并把这些观察明确写进各章节，而不是泛泛空谈。",
    ),
    LaneSpec(
        "codex-web-research",
        "codex",
        "codex",
        DEFAULT_CODEX_MODEL,
        "从网上已有产品经验、交互经验、技术方案和反模式角度提出方案。",
        "13-codex-web-research.md",
        "你必须先主动检索网上与 AI learning app、interactive reading、book companion、knowledge simulator、educational UX、agentic content system 等相关的资料、文章、产品经验或技术总结，再输出方案。至少吸收 5 组经验来源，并总结哪些经验适合本项目、哪些不适合、为什么。",
    ),
    LaneSpec(
        "codex-chaos",
        "codex",
        "codex",
        DEFAULT_CODEX_MODEL,
        "从反共识、破局路线和打破局部最优的角度提出方案。",
        "14-codex-chaos.md",
        "这一路是混沌路。除用户真实目标外，默认所有现有边界都可以被推翻。你需要先提出至少 3 个反常规破局方向，再收敛成一个最值得试的路线。不要被当前项目文件、常规 MVP 模板、已有技术栈和产品习惯绑住；优先给出能打破局部最优的建议。",
    ),
    LaneSpec(
        "codex-skeptic",
        "codex",
        "codex",
        DEFAULT_CODEX_MODEL,
        "从敌对审查、破坏性验证和系统性质疑角度提出方案。",
        "15-codex-skeptic.md",
        "你是质疑者/red team，不负责给漂亮方案，而负责拆系统。你必须在每个章节里主动寻找：错误前提、局部最优、隐藏复杂度、被忽略的失败模式、无法验证的口号、会导致后续返工的设计。你的目标是想办法破坏这个系统、质疑每个关键决定、指出议会可能集体自嗨的地方，并提出最难回答的反对意见。",
    ),
    LaneSpec(
        "opencode-kimi",
        "opencode",
        "opencode",
        "bailian/kimi-k2.5",
        "从创意发散、跨方案组合和新颖性角度提出方案。",
        "20-opencode-kimi.md",
        "你必须直接从 `# 问题定义` 开始输出，不允许输出 `Heading 1` 之类占位标题，不允许输出 Markdown 教学示例或 ```markdown 代码块。整体请保持克制精炼，但 10 个一级标题必须全部出现且每节都要有实质内容。",
    ),
    LaneSpec("opencode-glm5", "opencode", "opencode", "bailian/glm-5", "从契约设计、状态管理和日志可追溯角度提出方案。", "21-opencode-glm5.md"),
    LaneSpec("opencode-minimax", "opencode", "opencode", "bailian/MiniMax-M2.5", "从可读性、产品表达和人读文档链路角度提出方案。", "22-opencode-minimax.md"),
    LaneSpec("opencode-qwen", "opencode", "opencode", "bailian/qwen3.5-plus", "从多轮辩论、冲突收敛和终版成文角度提出方案。", "23-opencode-qwen.md"),
]


SINGLE_LANE_IDS = [DEFAULT_LANES[0].id]
REDUCED6_LANE_IDS = [lane.id for lane in DEFAULT_LANES[:6]]
LEGACY_STANDARD10_LANE_IDS = [lane.id for lane in DEFAULT_LANES if lane.id != "opencode-qwen"]
STANDARD11_LANE_IDS = [lane.id for lane in DEFAULT_LANES]

LANE_PRESETS: dict[str, list[str]] = {
    "single": SINGLE_LANE_IDS,
    "reduced6": REDUCED6_LANE_IDS,
    LEGACY_STANDARD10_PROFILE: LEGACY_STANDARD10_LANE_IDS,
    STANDARD11_PROFILE: STANDARD11_LANE_IDS,
    "default": STANDARD11_LANE_IDS,
    "default6": REDUCED6_LANE_IDS,
    "default9": [lane.id for lane in DEFAULT_LANES[:9]],
}

LANE_PRESET_ALIASES: dict[str, str] = {"default": STANDARD11_PROFILE, "default6": "reduced6", **LEGACY_PROFILE_ALIASES}


def normalize_lane_profile(name: str) -> str:
    candidate = name.strip().lower()
    if candidate in LANE_PRESET_ALIASES:
        return LANE_PRESET_ALIASES[candidate]
    if candidate in LANE_PRESETS:
        return candidate
    raise ValueError(
        "supported lane sets are single, reduced6, standard11, standard10, standard10-legacy, default, default6, default9, default10"
    )


def lane_seat_type(lane_id: str) -> str:
    if lane_id == "codex-gpt":
        return "controller"
    if lane_id == "claude-gpt":
        return "planning"
    if lane_id in {"codex-github-cases", "codex-web-research"}:
        return "search"
    if lane_id == "codex-chaos":
        return "chaos"
    if lane_id == "codex-skeptic":
        return "skeptic"
    if lane_id.startswith("opencode-"):
        return "marshal"
    return "marshal"


def lane_manifest_payload(lane: LaneSpec) -> dict[str, Any]:
    return {
        "id": lane.id,
        "seat_id": lane.id,
        "seat_type": lane_seat_type(lane.id),
        "source_cli": lane.source_cli,
        "family": lane.family,
        "model": lane.model,
        "obsidian_filename": lane.obsidian_filename,
    }


def default_cache_root(repo_root: Path = REPO_ROOT) -> Path:
    override = first_env("PIJIANG_FACTORY_CACHE_ROOT", "PIJIANG_CACHE_ROOT", "CODEX_CACHE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    workspace_name = get_workspace_name(repo_root)
    if os.name == "nt":
        return get_workspace_drive_root(repo_root) / f"{workspace_name} huancun" / "solution-factory"
    return get_workspace_root(repo_root) / ".cache" / "solution-factory"


def default_obsidian_root() -> Path:
    override = first_env("PIJIANG_OBSIDIAN_ROOT", "OBSIDIAN_VAULT_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return (REPO_ROOT / "output").resolve()


def default_config(project_path: str, repo_root: Path = REPO_ROOT) -> SolutionFactoryConfig:
    return SolutionFactoryConfig(
        workspace_root=get_workspace_root(repo_root),
        cache_root=default_cache_root(repo_root),
        obsidian_root=default_obsidian_root(),
        project_path=project_path,
    )


def split_project_path(project_path: str) -> list[str]:
    return [segment for segment in re.split(r"[\\/]+", project_path.strip()) if segment]


def get_user_environment_variable(name: str) -> str:
    current = os.environ.get(name, "").strip()
    if current:
        return current
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _value_type = winreg.QueryValueEx(key, name)
            return str(value).strip()
    except OSError:
        return ""


_SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _semver_key(value: str) -> tuple[int, int, int]:
    matched = _SEMVER_RE.search(value)
    if not matched:
        return (0, 0, 0)
    return tuple(int(part) for part in matched.groups())


def _find_bun_cached_opencode() -> Path | None:
    if os.name != "nt":
        return None
    bun_root = Path.home() / ".bun" / "install" / "cache"
    if not bun_root.exists():
        return None
    candidates: list[Path] = []
    for directory in bun_root.glob("opencode-windows-x64@*"):
        executable = directory / "bin" / "opencode.exe"
        if executable.exists():
            candidates.append(executable)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            _semver_key(item.parent.parent.name),
            item.stat().st_mtime,
        ),
        reverse=True,
    )
    return candidates[0]


def resolve_command_prefix(
    family: str,
    *,
    workspace_root: Path,
    command_overrides: dict[str, list[str] | str] | None = None,
) -> list[str]:
    overrides = command_overrides or {}
    if family in overrides:
        value = overrides[family]
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]

    if family == "codex":
        resolved = shutil.which("codex")
        return [resolved] if resolved else ["codex"]
    if family == "claude":
        resolved = shutil.which("claude")
        return [resolved] if resolved else ["claude"]
    if family == "opencode":
        resolved = shutil.which("opencode")
        if resolved:
            return [resolved]
        env_override = first_env("PIJIANG_OPENCODE_PATH", "OPENCODE_PATH")
        if env_override:
            override_path = Path(env_override).expanduser()
            if override_path.exists():
                return [str(override_path)]
        local_binary = workspace_root / "opencode-src" / "packages" / "opencode" / "node_modules" / "opencode-windows-x64" / "bin" / "opencode.exe"
        if local_binary.exists():
            return [str(local_binary)]
        bun_cached = _find_bun_cached_opencode()
        if bun_cached is not None:
            return [str(bun_cached)]
        local_bin = workspace_root / "opencode-src" / "packages" / "opencode" / "bin" / "opencode"
        bun_path = shutil.which("bun")
        if bun_path and local_bin.exists():
            return [bun_path, str(local_bin)]
        node_path = shutil.which("node")
        if node_path and local_bin.exists():
            return [node_path, str(local_bin)]
        raise FileNotFoundError("unable to resolve an opencode executable")
    raise ValueError(f"unsupported command family: {family}")


def build_codex_reasoning_args(*, effort: str | None, summary: str | None) -> list[str]:
    args: list[str] = []
    if effort:
        args.extend(["-c", f'model_reasoning_effort="{effort}"'])
    if summary:
        args.extend(["-c", f'model_reasoning_summary="{summary}"'])
    return args


def build_opencode_runtime_env(runtime_root: Path | None) -> dict[str, str]:
    if runtime_root is None:
        return {}

    home_dir = ensure_directory(runtime_root / "home")
    data_dir = ensure_directory(runtime_root / "share")
    cache_dir = ensure_directory(runtime_root / "cache")
    state_dir = ensure_directory(runtime_root / "state")
    return {
        "OPENCODE_TEST_HOME": str(home_dir),
        "XDG_DATA_HOME": str(data_dir),
        "XDG_CACHE_HOME": str(cache_dir),
        "XDG_STATE_HOME": str(state_dir),
    }


def build_lane_command(
    lane: LaneSpec,
    *,
    workspace_root: Path,
    output_last_message_path: Path,
    command_overrides: dict[str, list[str] | str] | None = None,
    prompt_text: str | None = "__PROMPT_PLACEHOLDER__",
    codex_reasoning_effort: str | None = "xhigh",
    codex_reasoning_summary: str | None = "auto",
    claude_effort: str | None = "max",
    opencode_variant: str | None = "max",
    opencode_runtime_root: Path | None = None,
) -> PreparedCommand:
    prefix = resolve_command_prefix(lane.family, workspace_root=workspace_root, command_overrides=command_overrides)
    if lane.family == "codex":
        command = prefix + [
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-C",
            str(workspace_root),
            "-m",
            lane.model,
            "-s",
            "read-only",
        ]
        command.extend(
            build_codex_reasoning_args(
                effort=codex_reasoning_effort,
                summary=codex_reasoning_summary,
            )
        )
        command.extend(
            [
            "--output-last-message",
            str(output_last_message_path),
            "--json",
            "-",
            ]
        )
        return PreparedCommand(command=command, cwd=workspace_root, stdin_text=prompt_text)

    if lane.family == "claude":
        command = prefix + [
            "-p",
            "--output-format",
            "text",
            "--permission-mode",
            "default",
            "--tools",
            "",
            "--model",
            lane.model,
        ]
        if claude_effort:
            command.extend(["--effort", claude_effort])
        return PreparedCommand(command=command, cwd=workspace_root, stdin_text=prompt_text or "")

    if lane.family == "opencode":
        env: dict[str, str] = build_opencode_runtime_env(opencode_runtime_root)
        if lane.model.startswith("bailian/"):
            api_key = get_user_environment_variable("BAILIAN_CODING_PLAN_API_KEY")
            if api_key:
                env["BAILIAN_CODING_PLAN_API_KEY"] = api_key
        command = prefix + [
            "run",
            "--format",
            "json",
            "--dir",
            str(workspace_root),
            "--model",
            lane.model,
        ]
        if opencode_variant:
            command.extend(["--variant", opencode_variant])
        if prompt_text:
            command.append(prompt_text)
        return PreparedCommand(command=command, cwd=workspace_root, env=env, stdin_text=None)

    raise ValueError(f"unsupported lane family: {lane.family}")


def build_codex_fusion_command(
    *,
    workspace_root: Path,
    model: str,
    output_last_message_path: Path,
    command_overrides: dict[str, list[str] | str] | None = None,
    prompt_text: str,
    output_schema_path: Path | None = None,
    codex_reasoning_effort: str | None = "xhigh",
    codex_reasoning_summary: str | None = "auto",
) -> PreparedCommand:
    prefix = resolve_command_prefix("codex", workspace_root=workspace_root, command_overrides=command_overrides)
    command = prefix + [
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "-C",
        str(workspace_root),
        "-m",
        model,
        "-s",
        "read-only",
    ]
    command.extend(
        build_codex_reasoning_args(
            effort=codex_reasoning_effort,
            summary=codex_reasoning_summary,
        )
    )
    command.extend(
        [
            "--output-last-message",
            str(output_last_message_path),
        ]
    )
    if output_schema_path is not None:
        command.extend(["--output-schema", str(output_schema_path)])
    command.extend(["--json", "-"])
    return PreparedCommand(command=command, cwd=workspace_root, stdin_text=prompt_text)


def build_claude_fusion_command(
    *,
    workspace_root: Path,
    model: str,
    prompt_text: str,
    json_schema: dict[str, Any] | None = None,
    command_overrides: dict[str, list[str] | str] | None = None,
    claude_effort: str | None = "max",
) -> PreparedCommand:
    prefix = resolve_command_prefix("claude", workspace_root=workspace_root, command_overrides=command_overrides)
    command = prefix + [
        "-p",
        "--output-format",
        "text",
        "--permission-mode",
        "default",
        "--tools",
        "",
        "--model",
        model,
    ]
    if claude_effort:
        command.extend(["--effort", claude_effort])
    if json_schema is not None:
        command.extend(["--json-schema", json.dumps(json_schema, ensure_ascii=False)])
    return PreparedCommand(command=command, cwd=workspace_root, stdin_text=prompt_text)


def parse_opencode_event_stream(stdout_text: str) -> str:
    text_parts: list[str] = []
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = payload.get("part", {})
        if payload.get("type") == "text" and isinstance(part, dict):
            text = str(part.get("text", "")).strip()
            if text:
                text_parts.append(text)
    return "\n\n".join(text_parts).strip()


def build_retry_variant_prompt(
    *,
    base_prompt: str,
    lane: LaneSpec,
    error_summary: str,
) -> str:
    return (
        f"{base_prompt.rstrip()}\n\n"
        "上一次输出未通过质量门，请你只做纠错，不要换题，也不要输出解释。\n"
        f"失败原因：{error_summary.strip()}\n"
        "纠错要求：\n"
        "1. 直接输出最终 Markdown 正文，不要输出代码块。\n"
        "2. 必须严格使用 10 个指定一级标题。\n"
        "3. 不允许输出占位标题、教程示例或过程旁白。\n"
        "4. 若某节不确定，也必须给出你的当前判断，不能留空。\n"
        f"请立即重写 `{lane.id}` 的最终可用输出。\n"
    )


def parse_variant_sections(raw_text: str) -> dict[str, str]:
    sections = {name: "" for name in CANONICAL_SECTIONS}
    collected: dict[str, list[str]] = {name: [] for name in CANONICAL_SECTIONS}
    current_section = ""
    preamble: list[str] = []
    heading_pattern = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*$")

    for line in raw_text.splitlines():
        matched = heading_pattern.match(line)
        if matched:
            canonical = SECTION_ALIAS_MAP.get(normalize_heading(matched.group(1)), "")
            if canonical:
                current_section = canonical
                continue
            if current_section:
                collected[current_section].append(line.rstrip())
                continue
        if current_section:
            collected[current_section].append(line.rstrip())
        else:
            preamble.append(line.rstrip())

    if preamble and not collected["问题定义"]:
        collected["问题定义"] = preamble

    for name in CANONICAL_SECTIONS:
        sections[name] = "\n".join(item for item in collected[name]).strip()
    return sections


def frontmatter_block(payload: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in payload.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
            continue
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def normalize_variant_markdown(raw_text: str, *, lane: LaneSpec, run_id: str, created_at: str) -> str:
    sections = parse_variant_sections(raw_text)
    frontmatter = frontmatter_block(
        {
            "sf_run_id": run_id,
            "sf_stage": "variant",
            "sf_lane": lane.id,
            "sf_source_cli": lane.source_cli,
            "sf_model": lane.model,
            "sf_created_at": created_at,
        }
    )
    rendered = [frontmatter, ""]
    for name in CANONICAL_SECTIONS:
        body = sections.get(name, "").strip() or "> 缺口：模型未显式给出本节内容。"
        rendered.append(f"# {name}")
        rendered.append(body)
        rendered.append("")
    return "\n".join(rendered).rstrip() + "\n"


def render_failed_variant_markdown(
    *,
    lane: LaneSpec,
    run_id: str,
    created_at: str,
    error_summary: str,
) -> str:
    frontmatter = frontmatter_block(
        {
            "sf_run_id": run_id,
            "sf_stage": "variant",
            "sf_lane": lane.id,
            "sf_source_cli": lane.source_cli,
            "sf_model": lane.model,
            "sf_created_at": created_at,
        }
    )
    return (
        f"{frontmatter}\n\n"
        "# 执行失败\n"
        f"> lane `{lane.id}` 执行失败，未生成标准方案正文。\n\n"
        "## 错误摘要\n"
        f"{error_summary.strip() or '未知错误'}\n"
    )


def render_brief_markdown(brief_text: str, *, run_id: str, created_at: str) -> str:
    frontmatter = frontmatter_block(
        {
            "sf_run_id": run_id,
            "sf_stage": "brief",
            "sf_lane": "brief",
            "sf_source_cli": "local",
            "sf_model": "n/a",
            "sf_created_at": created_at,
        }
    )
    return f"{frontmatter}\n\n{brief_text.strip()}\n"


def render_preflight_markdown(
    payload: dict[str, Any],
    *,
    run_id: str,
    created_at: str,
) -> str:
    frontmatter = frontmatter_block(
        {
            "sf_run_id": run_id,
            "sf_stage": "preflight",
            "sf_lane": "preflight",
            "sf_source_cli": "local",
            "sf_model": "n/a",
            "sf_created_at": created_at,
        }
    )
    lines = [
        frontmatter,
        "",
        "# 运行前检查",
        "",
        f"- 请求 profile：`{payload.get('requested_lane_profile', '')}`",
        f"- 实际 profile：`{payload.get('effective_lane_profile', '')}`",
        "",
    ]
    issues = payload.get("issues", [])
    if issues:
        lines.append("## 发现的问题")
        for issue in issues:
            lines.append(f"- `{issue.get('code', 'unknown')}`：{issue.get('message', '').strip()}")
        lines.append("")
    unavailable_lane_ids = payload.get("unavailable_lane_ids", [])
    if unavailable_lane_ids:
        lines.append("## 当前不可用 lane")
        for lane_id in unavailable_lane_ids:
            lines.append(f"- `{lane_id}`")
        lines.append("")
    availability = payload.get("family_availability", {})
    if availability:
        lines.append("## Family 可用性")
        for family, item in availability.items():
            lines.append(f"- `{family}`：`{item.get('status', 'unknown')}` / `{item.get('detail', '')}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_stage_markdown(
    *,
    body: str,
    run_id: str,
    stage: str,
    lane_id: str,
    source_cli: str,
    model: str,
    created_at: str,
) -> str:
    frontmatter = frontmatter_block(
        {
            "sf_run_id": run_id,
            "sf_stage": stage,
            "sf_lane": lane_id,
            "sf_source_cli": source_cli,
            "sf_model": model,
            "sf_created_at": created_at,
        }
    )
    return f"{frontmatter}\n\n{body.strip()}\n"


def render_decisions_markdown(
    payload: dict[str, Any],
    *,
    run_id: str,
    created_at: str,
    source_cli: str,
    model: str,
) -> str:
    frontmatter = frontmatter_block(
        {
            "sf_run_id": run_id,
            "sf_stage": "fusion-decisions",
            "sf_lane": "codex-gpt",
            "sf_source_cli": source_cli,
            "sf_model": model,
            "sf_created_at": created_at,
        }
    )
    lines = [frontmatter, "", "# 决策账本", ""]
    for item in payload.get("decisions", []):
        lines.append(f"## {item['topic']}")
        lines.append(f"- 终版采用：{item['decision']}")
        lines.append(f"- 来源版本：{', '.join(item.get('sources', []))}")
        lines.append(f"- 融合原因：{item['reason']}")
        lines.append(f"- 质疑者挑战：{item.get('skeptic_challenge', '').strip()}")
        lines.append(f"- 议会回应：{item.get('skeptic_rebuttal', '').strip()}")
        rejected = item.get("rejected_options", [])
        if rejected:
            lines.append("- 暂不采用：")
            for candidate in rejected:
                lines.append(
                    f"  - {candidate.get('lane', 'unknown')} / {candidate.get('option', '')} / {candidate.get('reason', '')}"
                )
        open_questions = item.get("open_questions", [])
        if open_questions:
            lines.append("- 待验证：")
            for question in open_questions:
                lines.append(f"  - {question}")
        lines.append("")

    fallback_options = payload.get("fallback_options", [])
    if fallback_options:
        lines.append("## 备选保留")
        for item in fallback_options:
            lines.append(f"- {item.get('topic', '')}：{item.get('option', '')}")
        lines.append("")

    validation_steps = payload.get("next_validation_steps", [])
    if validation_steps:
        lines.append("## 下一步验证")
        for step in validation_steps:
            lines.append(f"- {step}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_final_draft_markdown(
    payload: dict[str, Any],
    *,
    run_id: str,
    created_at: str,
    source_cli: str,
    model: str,
) -> str:
    frontmatter = frontmatter_block(
        {
            "sf_run_id": run_id,
            "sf_stage": "final-draft",
            "sf_lane": "codex-gpt",
            "sf_source_cli": source_cli,
            "sf_model": model,
            "sf_created_at": created_at,
        }
    )
    lines = [frontmatter, "", f"# {payload.get('title', '终版方案草案')}", ""]
    for section in payload.get("sections", []):
        lines.append(f"## {section.get('title', '未命名章节')}")
        lines.append(section.get("content", "").strip())
        lines.append("")
        lines.append(f"- 来源版本：{', '.join(section.get('sources', []))}")
        lines.append(f"- 融合依据：{section.get('rationale', '').strip()}")
        lines.append(f"- 状态：{section.get('status', '').strip()}")
        lines.append("")

    open_questions = payload.get("open_questions", [])
    if open_questions:
        lines.append("## 待确认问题")
        for question in open_questions:
            lines.append(f"- {question}")
        lines.append("")

    validation_plan = payload.get("validation_plan", [])
    if validation_plan:
        lines.append("## 验证计划")
        for step in validation_plan:
            lines.append(f"- {step}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_index_markdown(*, run_id: str, created_at: str, lane_results: list[LaneResult], watcher_filename: str | None = None) -> str:
    frontmatter = frontmatter_block(
        {
            "sf_run_id": run_id,
            "sf_stage": "index",
            "sf_lane": "index",
            "sf_source_cli": "local",
            "sf_model": "n/a",
            "sf_created_at": created_at,
        }
    )
    lines = [frontmatter, "", "# 方案工厂索引", "", "## 变体方案", ""]
    for result in lane_results:
        label = result.lane.obsidian_filename
        lines.append(f"- [{label}]({label}) - {result.status}")
    lines.extend(
        [
            "",
            "## 融合链路",
            "- [30-idea-map.md](30-idea-map.md)",
            "- [40-debate-round-1.md](40-debate-round-1.md)",
            "- [41-debate-round-2.md](41-debate-round-2.md)",
            "- [50-fusion-decisions.md](50-fusion-decisions.md)",
            "- [90-final-solution-draft.md](90-final-solution-draft.md)",
        ]
    )
    if watcher_filename:
        lines.extend(["", "## 守护层", f"- [{watcher_filename}]({watcher_filename})"])
    return "\n".join(lines).rstrip() + "\n"


def build_variant_prompt(brief_text: str, lane: LaneSpec) -> str:
    section_template = "\n".join(f"# {name}" for name in CANONICAL_SECTIONS)
    special_block = f"额外要求：\n{lane.special_instructions.strip()}\n\n" if lane.special_instructions.strip() else ""
    opencode_hardening_block = ""
    if lane.family == "opencode":
        opencode_hardening_block = (
            "opencode 系产线硬约束：\n"
            "1. 禁止输出 `Heading 1`、`Heading 2` 之类占位标题。\n"
            "2. 禁止输出 Markdown 教学示例、模板示例或 ```markdown 代码块。\n"
            "3. 必须直接从 `# 问题定义` 开始，严格给出 10 个一级中文标题。\n"
            "4. 任何一节都不能留空；即使不确定，也要写出当前判断与风险。\n\n"
        )
    return (
        f"{stage_marker_block('variant', lane.id)}\n"
        f"你是多模型方案工厂中的 `{lane.id}` 产线。\n"
        f"思考角度：{lane.thinking_angle}\n"
        "请只输出 Markdown，并严格使用下面这些一级标题，顺序不要改变：\n"
        f"{section_template}\n\n"
        "要求：\n"
        "1. 聚焦项目方案脑暴，不进入写代码阶段。\n"
        "2. 观点要便于后续多轮融合。\n"
        "3. 每个章节都给出实质内容。\n\n"
        f"{opencode_hardening_block}"
        f"{special_block}"
        f"Brief:\n{brief_text.strip()}\n"
    )


def build_idea_map_prompt(fusion_context: dict[str, Any]) -> str:
    return (
        f"{stage_marker_block('idea-map', 'codex-gpt')}\n"
        "请根据 fusion_context 输出 Markdown，并且必须包含以下一级标题：\n"
        "# 共识点\n# 独特亮点\n# 冲突点\n# 质疑焦点\n# 可组合点\n\n"
        "要求：明确抽取 `codex-skeptic` 的核心质疑，并把它单列到“质疑焦点”，不要把它稀释进普通冲突点。\n\n"
        f"fusion_context:\n{json.dumps(fusion_context, ensure_ascii=False, indent=2)}\n"
    )


def build_debate_round_prompt(
    *,
    round_index: int,
    fusion_context: dict[str, Any],
    idea_map_text: str,
    previous_round_text: str | None = None,
) -> str:
    previous = previous_round_text.strip() if previous_round_text else ""
    previous_block = f"\n上一轮辩论：\n{previous}\n" if previous else ""
    return (
        f"{stage_marker_block(f'debate-round-{round_index}', 'codex-gpt')}\n"
        f"请输出第 {round_index} 轮辩论纪要的 Markdown。\n"
        "把这轮视为“9 人议会回应 1 路质疑者”的对抗讨论。\n"
        "每轮都明确：谁提出观点、质疑者如何攻击、谁反驳、反驳依据、被采纳的修正、仍未解决的质疑。\n"
        f"Idea map:\n{idea_map_text.strip()}\n"
        f"{previous_block}"
        f"fusion_context:\n{json.dumps(fusion_context, ensure_ascii=False, indent=2)}\n"
    )


def build_final_decisions_prompt(
    fusion_context: dict[str, Any],
    *,
    idea_map_text: str,
    debate_round_1_text: str,
    debate_round_2_text: str,
) -> str:
    return (
        f"{stage_marker_block('final-decisions-json', 'codex-gpt')}\n"
        "请输出 JSON，形成终版的决策账本。不要输出 Markdown，不要输出代码块。\n"
        "每条决策都必须包含 topic、decision、sources、reason、skeptic_challenge、skeptic_rebuttal、rejected_options、open_questions。\n"
        "其中 skeptic_challenge 必须提炼 `codex-skeptic` 或辩论中的主要红队质疑；skeptic_rebuttal 必须写明议会为什么仍坚持该决定，或者如何局部让步后再采用。\n"
        f"Idea map:\n{idea_map_text.strip()}\n\n"
        f"Round 1:\n{debate_round_1_text.strip()}\n\n"
        f"Round 2:\n{debate_round_2_text.strip()}\n\n"
        f"fusion_context:\n{json.dumps(fusion_context, ensure_ascii=False, indent=2)}\n"
    )


def build_final_draft_prompt(fusion_context: dict[str, Any], *, decisions_payload: dict[str, Any]) -> str:
    return (
        f"{stage_marker_block('final-draft-json', 'codex-gpt')}\n"
        "请输出 JSON，形成终版方案草案。不要输出 Markdown，不要输出代码块。\n"
        "每个 section 都必须包含 title、content、sources、rationale、status。\n"
        f"decisions_payload:\n{json.dumps(decisions_payload, ensure_ascii=False, indent=2)}\n\n"
        f"fusion_context:\n{json.dumps(fusion_context, ensure_ascii=False, indent=2)}\n"
    )


class RunTracker:
    def __init__(self, run_dir: Path, manifest: dict[str, Any]):
        self.run_dir = run_dir
        self.status_path = run_dir / "status.json"
        self.events_path = run_dir / "events.jsonl"
        self.lock = threading.Lock()
        self.state = {
            "run_id": manifest["run_id"],
            "owner_pid": manifest.get("owner_pid", 0),
            "status": "running",
            "stage": "bootstrap",
            "started_at": manifest["started_at"],
            "finished_at": "",
            "updated_at": manifest["started_at"],
            "requested_lane_profile": manifest["requested_lane_profile"],
            "effective_lane_profile": manifest["effective_lane_profile"],
            "lane_statuses": {lane["id"]: "pending" for lane in manifest["lanes"]},
            "seat_statuses": {seat["seat_id"]: "pending" for seat in manifest.get("seats", [])},
            "running_seat_ids": [],
            "current_seat_id": "",
            "current_message": "等待开始",
            "failed_lane_count": 0,
            "watcher_enabled": False,
            "watcher_state": "idle",
            "watcher_alert_count": 0,
            "watcher_action_count": 0,
            "watcher_last_message": "",
            "artifacts": {},
        }
        write_json(self.status_path, self.state)

    def snapshot_payload(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.state)

    def emit(self, kind: str, **payload: Any) -> None:
        with self.lock:
            append_jsonl(self.events_path, {"timestamp": utc_now_iso(), "kind": kind, **payload})

    def set_stage(self, stage: str) -> None:
        with self.lock:
            self.state["stage"] = stage
            self.state["current_seat_id"] = ""
            self.state["current_message"] = f"进入阶段 `{stage}`"
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)

    def set_lane_status(self, lane_id: str, status: str) -> None:
        with self.lock:
            self.state["lane_statuses"][lane_id] = status
            if lane_id in self.state["seat_statuses"]:
                self.state["seat_statuses"][lane_id] = status
            self.state["failed_lane_count"] = sum(
                1 for value in self.state["lane_statuses"].values() if value == "failed"
            )
            self.state["running_seat_ids"] = [
                current_lane_id for current_lane_id, current_status in self.state["lane_statuses"].items() if current_status == "running"
            ]
            self.state["current_seat_id"] = lane_id if status == "running" else (self.state["running_seat_ids"][0] if self.state["running_seat_ids"] else "")
            self.state["current_message"] = f"{lane_id} => {status}"
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)

    def set_seat_status(self, seat_id: str, status: str) -> None:
        with self.lock:
            self.state["seat_statuses"][seat_id] = status
            if seat_id == "fusion":
                current_running = [item for item in self.state["running_seat_ids"] if item != "fusion"]
                if status == "running":
                    current_running.append("fusion")
                self.state["running_seat_ids"] = current_running
                self.state["current_seat_id"] = "fusion" if status == "running" else (current_running[0] if current_running else "")
                self.state["current_message"] = f"{seat_id} => {status}"
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)

    def add_artifact(self, key: str, value: str) -> None:
        with self.lock:
            self.state["artifacts"][key] = value
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)

    def touch(self, *, message: str, seat_id: str = "") -> None:
        with self.lock:
            self.state["current_message"] = message
            if seat_id:
                self.state["current_seat_id"] = seat_id
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)

    def update_watcher(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.state["watcher_enabled"] = bool(payload.get("watcher_enabled", self.state["watcher_enabled"]))
            self.state["watcher_state"] = str(payload.get("watcher_state", self.state["watcher_state"]))
            self.state["watcher_alert_count"] = int(payload.get("watcher_alert_count", self.state["watcher_alert_count"]))
            self.state["watcher_action_count"] = int(payload.get("watcher_action_count", self.state["watcher_action_count"]))
            self.state["watcher_last_message"] = str(payload.get("watcher_last_message", self.state["watcher_last_message"]))
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)

    def complete(self, status: str) -> None:
        with self.lock:
            self.state["status"] = status
            self.state["stage"] = "completed" if status in {"success", "degraded", "needs-review"} else "failed"
            self.state["finished_at"] = utc_now_iso()
            self.state["running_seat_ids"] = []
            self.state["current_seat_id"] = ""
            self.state["current_message"] = f"run => {status}"
            self.state["updated_at"] = self.state["finished_at"]
            write_json(self.status_path, self.state)


class SolutionFactory:
    def __init__(self, config: SolutionFactoryConfig):
        self.config = config
        self.workspace_root = config.workspace_root.resolve()
        self.cache_root = config.cache_root.resolve()
        self.obsidian_root = config.obsidian_root.resolve()
        self.current_run_id = ""
        self.current_output_dir = Path(".")

    def _select_lanes(self, lanes: str) -> tuple[str, list[LaneSpec]]:
        normalized_profile = normalize_lane_profile(lanes)
        allowed_lane_ids = set(LANE_PRESETS[normalized_profile])
        return normalized_profile, [lane for lane in DEFAULT_LANES if lane.id in allowed_lane_ids]

    def _preflight_lanes(
        self,
        *,
        requested_profile: str,
        requested_lanes: list[LaneSpec],
    ) -> tuple[str, list[LaneSpec], dict[str, Any]]:
        family_availability: dict[str, dict[str, str]] = {}
        unavailable_families: dict[str, str] = {}
        for family in sorted({lane.family for lane in requested_lanes}):
            try:
                prefix = resolve_command_prefix(family, workspace_root=self.workspace_root, command_overrides=self.config.command_overrides)
                family_availability[family] = {"status": "ready", "detail": " ".join(prefix)}
            except Exception as exc:
                unavailable_families[family] = str(exc)
                family_availability[family] = {"status": "missing", "detail": str(exc)}

        effective_profile = requested_profile
        effective_lanes = list(requested_lanes)
        unavailable_lane_ids = [lane.id for lane in requested_lanes if lane.family in unavailable_families]
        issues: list[dict[str, str]] = []

        if requested_profile in {STANDARD11_PROFILE, LEGACY_STANDARD10_PROFILE} and set(unavailable_families) == {"opencode"}:
            effective_profile = "reduced6"
            effective_lanes = [lane for lane in DEFAULT_LANES if lane.id in REDUCED6_LANE_IDS]
            requested_label = "standard11" if requested_profile == STANDARD11_PROFILE else "standard10-legacy"
            issues.append(
                {
                    "code": "profile_degraded",
                    "message": f"{requested_label} 请求中缺少 opencode 可执行链路，已自动降级为 reduced6 以保证真实会议先可运行。",
                }
            )

        for family, error_text in unavailable_families.items():
            issues.append(
                {
                    "code": "provider_unavailable",
                    "message": f"{family} family 当前不可用：{error_text}",
                }
            )

        return effective_profile, effective_lanes, {
            "requested_lane_profile": requested_profile,
            "effective_lane_profile": effective_profile,
            "unavailable_lane_ids": unavailable_lane_ids,
            "family_availability": family_availability,
            "issues": issues,
        }

    def _prepare_run(
        self,
        brief_path: Path,
        *,
        requested_profile_input: str,
        requested_profile: str,
        effective_profile: str,
        lane_specs: list[LaneSpec],
        preflight: dict[str, Any],
    ) -> tuple[str, Path, Path, dict[str, Any]]:
        run_id = f"sf-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        run_dir = ensure_directory(self.cache_root / "runs" / run_id)
        output_segments = split_project_path(self.config.project_path)
        if self.config.append_factory_dir and (not output_segments or output_segments[-1] != "方案工厂"):
            output_segments.append("方案工厂")
        output_segments.append(run_id)
        output_dir = ensure_directory(self.obsidian_root.joinpath(*output_segments))
        manifest = {
            "run_id": run_id,
            "owner_pid": os.getpid(),
            "brief_path": str(brief_path),
            "project_path": self.config.project_path,
            "append_factory_dir": self.config.append_factory_dir,
            "seat_registry_version": SEAT_REGISTRY_VERSION,
            "requested_lane_profile_input": requested_profile_input,
            "requested_lane_profile": requested_profile,
            "effective_lane_profile": effective_profile,
            "legacy_compat_applied": requested_profile_input != requested_profile,
            "degraded_state": effective_profile != requested_profile,
            "parallel_policy": "strict_all",
            "quorum_profile": "strict-all",
            "preflight": preflight,
            "lanes": [lane_manifest_payload(lane) for lane in lane_specs],
            "seat_count": len(lane_specs) + 1,
            "seats": [lane_manifest_payload(lane) for lane in lane_specs]
            + [
                {
                    "id": "fusion",
                    "seat_id": "fusion",
                    "seat_type": "fusion",
                    "source_cli": "codex",
                    "family": "fusion",
                    "model": DEFAULT_CODEX_MODEL,
                    "obsidian_filename": "20-fusion.md",
                }
            ],
            "resolved_seats": [lane.id for lane in lane_specs] + ["fusion"],
            "started_at": utc_now_iso(),
            "timeouts": {"lane_timeout_sec": self.config.timeout_sec},
            "retry_policy": {"attempts": self.config.retry_attempts},
            "model_tuning": {
                "codex_reasoning_effort": self.config.codex_reasoning_effort,
                "codex_reasoning_summary": self.config.codex_reasoning_summary,
                "claude_effort": self.config.claude_effort,
                "opencode_variant": self.config.opencode_variant,
            },
            "obsidian_output_dir": str(output_dir),
        }
        write_json(run_dir / "run_manifest.json", manifest)
        write_json(run_dir / "preflight.json", preflight)
        return run_id, run_dir, output_dir, manifest

    def _run_subprocess(self, prepared: PreparedCommand, *, timeout_sec: int) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env.update(prepared.env)
        return subprocess.run(
            prepared.command,
            input=prepared.stdin_text,
            text=True,
            capture_output=True,
            cwd=prepared.cwd,
            env=env,
            timeout=timeout_sec,
            check=False,
        )

    def _extract_variant_output(
        self,
        *,
        lane: LaneSpec,
        completed: subprocess.CompletedProcess[str],
        output_last_message_path: Path,
    ) -> str:
        if lane.family == "codex":
            if output_last_message_path.exists():
                return output_last_message_path.read_text(encoding="utf-8").strip()
            return completed.stdout.strip()
        if lane.family == "claude":
            return completed.stdout.strip()
        if lane.family == "opencode":
            parsed = parse_opencode_event_stream(completed.stdout)
            return parsed.strip()
        raise ValueError(f"unsupported lane family: {lane.family}")

    def _write_lane_result(
        self,
        *,
        lane: LaneSpec,
        run_id: str,
        created_at: str,
        lane_run_dir: Path,
        output_dir: Path,
        raw_stdout_path: Path,
        raw_stderr_path: Path,
        raw_output_path: Path | None,
        markdown: str,
        status: str,
        error_summary: str,
        sections: dict[str, str] | None = None,
    ) -> LaneResult:
        normalized_markdown_path = output_dir / lane.obsidian_filename
        write_text(normalized_markdown_path, markdown)
        variant_result_path = lane_run_dir / "variant_result.json"
        payload = {
            "lane_id": lane.id,
            "status": status,
            "started_at": created_at,
            "finished_at": utc_now_iso(),
            "raw_stdout_path": str(raw_stdout_path),
            "raw_stderr_path": str(raw_stderr_path),
            "raw_output_path": str(raw_output_path) if raw_output_path else "",
            "normalized_markdown_path": str(normalized_markdown_path),
            "error_summary": error_summary,
        }
        write_json(variant_result_path, payload)
        return LaneResult(
            lane=lane,
            status=status,
            started_at=created_at,
            finished_at=payload["finished_at"],
            lane_run_dir=lane_run_dir,
            raw_stdout_path=raw_stdout_path,
            raw_stderr_path=raw_stderr_path,
            raw_output_path=raw_output_path,
            normalized_markdown_path=normalized_markdown_path,
            variant_result_path=variant_result_path,
            error_summary=error_summary,
            sections=sections or {},
        )

    def _execute_lane(
        self,
        lane: LaneSpec,
        *,
        run_id: str,
        brief_text: str,
        run_dir: Path,
        output_dir: Path,
        tracker: RunTracker,
    ) -> LaneResult:
        created_at = utc_now_iso()
        lane_run_dir = ensure_directory(run_dir / "lanes" / lane.id)
        prompt = build_variant_prompt(brief_text, lane)
        write_text(lane_run_dir / "prompt.txt", prompt)
        output_last_message_path = lane_run_dir / "last-message.txt"
        raw_stdout_path = lane_run_dir / "stdout.log"
        raw_stderr_path = lane_run_dir / "stderr.log"
        tracker.emit("lane-start", lane_id=lane.id, model=lane.model)
        tracker.set_lane_status(lane.id, "running")

        last_error = "unknown error"
        for attempt in range(1, max(1, self.config.retry_attempts) + 1):
            tracker.emit("lane-attempt-start", lane_id=lane.id, attempt=attempt)
            try:
                if output_last_message_path.exists():
                    output_last_message_path.unlink()
                attempt_prompt = prompt if attempt == 1 else build_retry_variant_prompt(base_prompt=prompt, lane=lane, error_summary=last_error)
                write_text(lane_run_dir / f"prompt.attempt-{attempt}.txt", attempt_prompt)
                prepared = build_lane_command(
                    lane,
                    workspace_root=self.workspace_root,
                    output_last_message_path=output_last_message_path,
                    command_overrides=self.config.command_overrides,
                    prompt_text=attempt_prompt,
                    codex_reasoning_effort=self.config.codex_reasoning_effort,
                    codex_reasoning_summary=self.config.codex_reasoning_summary,
                    claude_effort=self.config.claude_effort,
                    opencode_variant=self.config.opencode_variant,
                    opencode_runtime_root=lane_run_dir / "opencode-runtime" if lane.family == "opencode" else None,
                )
                completed = self._run_subprocess(prepared, timeout_sec=self.config.timeout_sec)
                write_text(raw_stdout_path, completed.stdout or "")
                write_text(raw_stderr_path, completed.stderr or "")
                write_text(lane_run_dir / f"stdout.attempt-{attempt}.log", completed.stdout or "")
                write_text(lane_run_dir / f"stderr.attempt-{attempt}.log", completed.stderr or "")
                if completed.returncode != 0:
                    raise RuntimeError(
                        f"command exited with {completed.returncode}: {(completed.stderr or completed.stdout).strip()}"
                    )

                raw_output = self._extract_variant_output(
                    lane=lane,
                    completed=completed,
                    output_last_message_path=output_last_message_path,
                ).strip()
                if not raw_output:
                    raise RuntimeError("command completed without a usable final message")
                raw_output = trim_to_canonical_markdown(raw_output)
                quality_issue = variant_quality_issue(lane, raw_output)
                if quality_issue:
                    raise RuntimeError(f"quality gate failed: {quality_issue}")

                raw_output_path = lane_run_dir / "raw-output.txt"
                write_text(raw_output_path, raw_output)
                markdown = normalize_variant_markdown(raw_output, lane=lane, run_id=run_id, created_at=created_at)
                sections = parse_variant_sections(raw_output)
                result = self._write_lane_result(
                    lane=lane,
                    run_id=run_id,
                    created_at=created_at,
                    lane_run_dir=lane_run_dir,
                    output_dir=output_dir,
                    raw_stdout_path=raw_stdout_path,
                    raw_stderr_path=raw_stderr_path,
                    raw_output_path=raw_output_path,
                    markdown=markdown,
                    status="success",
                    error_summary="",
                    sections=sections,
                )
                tracker.emit(
                    "lane-success",
                    lane_id=lane.id,
                    markdown_path=str(result.normalized_markdown_path),
                    attempt=attempt,
                )
                tracker.set_lane_status(lane.id, "success")
                return result
            except Exception as exc:
                last_error = str(exc)
                tracker.emit("lane-attempt-failure", lane_id=lane.id, attempt=attempt, error=last_error)
                if attempt < max(1, self.config.retry_attempts):
                    time.sleep(min(10, attempt * 2))
                    continue

        markdown = render_failed_variant_markdown(
            lane=lane,
            run_id=run_id,
            created_at=created_at,
            error_summary=last_error,
        )
        result = self._write_lane_result(
            lane=lane,
            run_id=run_id,
            created_at=created_at,
            lane_run_dir=lane_run_dir,
            output_dir=output_dir,
            raw_stdout_path=raw_stdout_path,
            raw_stderr_path=raw_stderr_path,
            raw_output_path=None,
            markdown=markdown,
            status="failed",
            error_summary=last_error,
        )
        tracker.emit("lane-failure", lane_id=lane.id, error=last_error)
        tracker.set_lane_status(lane.id, "failed")
        return result

    def _build_fusion_context(self, lane_results: list[LaneResult]) -> dict[str, Any]:
        available = [result for result in lane_results if result.status == "success"]
        failed = [result.lane.id for result in lane_results if result.status == "failed"]
        return {
            "variant_count": len(available),
            "failed_lanes": failed,
            "variants": [
                {
                    "lane_id": result.lane.id,
                    "source_cli": result.lane.source_cli,
                    "model": result.lane.model,
                    "markdown_path": str(result.normalized_markdown_path),
                    "sections": result.sections,
                }
                for result in available
            ],
        }

    def _run_fusion_text_step(
        self,
        *,
        stage: str,
        prompt: str,
        fusion_dir: Path,
        tracker: RunTracker,
        filename: str,
    ) -> str:
        created_at = utc_now_iso()
        output_last_message_path = fusion_dir / f"{stage}.last-message.txt"
        tracker.emit("fusion-step-start", stage=stage)
        provider_used = "codex"
        model_used = DEFAULT_CODEX_MODEL
        try:
            prepared = build_codex_fusion_command(
                workspace_root=self.workspace_root,
                model=model_used,
                output_last_message_path=output_last_message_path,
                command_overrides=self.config.command_overrides,
                prompt_text=prompt,
                codex_reasoning_effort=self.config.codex_reasoning_effort,
                codex_reasoning_summary=self.config.codex_reasoning_summary,
            )
            completed = self._run_subprocess(prepared, timeout_sec=self.config.timeout_sec)
            write_text(fusion_dir / f"{stage}.stdout.log", completed.stdout or "")
            write_text(fusion_dir / f"{stage}.stderr.log", completed.stderr or "")
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout).strip() or "codex fusion failed")
            body = output_last_message_path.read_text(encoding="utf-8").strip()
            if not body:
                raise RuntimeError("codex fusion returned empty content")
        except Exception as exc:
            provider_used = "claude"
            model_used = DEFAULT_CLAUDE_MODEL
            fallback = build_claude_fusion_command(
                workspace_root=self.workspace_root,
                model=model_used,
                prompt_text=prompt,
                command_overrides=self.config.command_overrides,
                claude_effort=self.config.claude_effort,
            )
            completed = self._run_subprocess(fallback, timeout_sec=self.config.timeout_sec)
            write_text(fusion_dir / f"{stage}.claude.stdout.log", completed.stdout or "")
            write_text(fusion_dir / f"{stage}.claude.stderr.log", completed.stderr or "")
            if completed.returncode != 0:
                raise RuntimeError(
                    f"fusion step {stage} failed: codex={str(exc)} | claude={(completed.stderr or completed.stdout).strip()}"
                )
            body = (completed.stdout or "").strip()
            if not body:
                raise RuntimeError(f"fusion step {stage} failed: codex={str(exc)} | claude returned empty content")
        write_text(
            self.current_output_dir / filename,
            render_stage_markdown(
                body=body,
                run_id=self.current_run_id,
                stage=stage,
                lane_id="codex-gpt",
                source_cli=provider_used,
                model=model_used,
                created_at=created_at,
            ),
        )
        tracker.emit(
            "fusion-step-success",
            stage=stage,
            provider=provider_used,
            output=str(self.current_output_dir / filename),
        )
        return body

    def _run_fusion_json_step(
        self,
        *,
        stage: str,
        prompt: str,
        schema: dict[str, Any],
        fusion_dir: Path,
        tracker: RunTracker,
    ) -> tuple[dict[str, Any], str, str]:
        schema_path = fusion_dir / f"{stage}.schema.json"
        write_json(schema_path, schema)
        output_last_message_path = fusion_dir / f"{stage}.last-message.json"
        tracker.emit("fusion-step-start", stage=stage)
        provider_used = "codex"
        model_used = DEFAULT_CODEX_MODEL
        try:
            prepared = build_codex_fusion_command(
                workspace_root=self.workspace_root,
                model=model_used,
                output_last_message_path=output_last_message_path,
                output_schema_path=schema_path,
                command_overrides=self.config.command_overrides,
                prompt_text=prompt,
                codex_reasoning_effort=self.config.codex_reasoning_effort,
                codex_reasoning_summary=self.config.codex_reasoning_summary,
            )
            completed = self._run_subprocess(prepared, timeout_sec=self.config.timeout_sec)
            write_text(fusion_dir / f"{stage}.stdout.log", completed.stdout or "")
            write_text(fusion_dir / f"{stage}.stderr.log", completed.stderr or "")
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout).strip() or "codex fusion failed")
            raw_payload = output_last_message_path.read_text(encoding="utf-8").strip()
            if not raw_payload:
                raise RuntimeError("codex fusion returned empty JSON payload")
            payload = json.loads(raw_payload)
        except Exception as exc:
            provider_used = "claude"
            model_used = DEFAULT_CLAUDE_MODEL
            fallback = build_claude_fusion_command(
                workspace_root=self.workspace_root,
                model=model_used,
                prompt_text=prompt,
                json_schema=schema,
                command_overrides=self.config.command_overrides,
                claude_effort=self.config.claude_effort,
            )
            completed = self._run_subprocess(fallback, timeout_sec=self.config.timeout_sec)
            write_text(fusion_dir / f"{stage}.claude.stdout.log", completed.stdout or "")
            write_text(fusion_dir / f"{stage}.claude.stderr.log", completed.stderr or "")
            if completed.returncode != 0:
                raise RuntimeError(
                    f"fusion step {stage} failed: codex={str(exc)} | claude={(completed.stderr or completed.stdout).strip()}"
                )
            raw_payload = (completed.stdout or "").strip()
            if not raw_payload:
                raise RuntimeError(f"fusion step {stage} failed: codex={str(exc)} | claude returned empty JSON")
            payload = json.loads(raw_payload)
            write_text(output_last_message_path, json.dumps(payload, ensure_ascii=False, indent=2))
        tracker.emit("fusion-step-success", stage=stage, provider=provider_used, output=str(output_last_message_path))
        return payload, provider_used, model_used

    def run(self, *, brief_path: Path, lanes: str = STANDARD11_PROFILE, watcher_mode: str | None = None) -> dict[str, Any]:
        recover_abandoned_runs(self.cache_root)
        requested_profile_input = lanes.strip().lower()
        requested_profile, requested_lanes = self._select_lanes(lanes)
        brief_path = brief_path.expanduser().resolve()
        brief_text = brief_path.read_text(encoding="utf-8")
        effective_profile, lane_specs, preflight = self._preflight_lanes(
            requested_profile=requested_profile,
            requested_lanes=requested_lanes,
        )
        if not lane_specs:
            raise RuntimeError("preflight resolved zero runnable lanes")

        run_id, run_dir, output_dir, manifest = self._prepare_run(
            brief_path,
            requested_profile_input=requested_profile_input,
            requested_profile=requested_profile,
            effective_profile=effective_profile,
            lane_specs=lane_specs,
            preflight=preflight,
        )
        self.current_run_id = run_id
        self.current_output_dir = output_dir
        tracker = RunTracker(run_dir, manifest)
        tracker.add_artifact("preflight_json", str(run_dir / "preflight.json"))
        watcher_active = watcher_enabled(watcher_mode or self.config.watcher_policy.cli_mode, task_kind="run")
        watcher_recorder: WatcherRecorder | None = None
        watcher_monitor: WatcherMonitor | None = None
        if watcher_active:
            watcher_recorder = WatcherRecorder(
                run_dir=run_dir,
                output_dir=output_dir,
                policy=self.config.watcher_policy,
                status_updater=tracker.update_watcher,
            )
            watcher_recorder.set_state("watching", "觉者已启用，正在代表用户观察本地真实议会执行链。")
            watcher_monitor = WatcherMonitor(
                recorder=watcher_recorder,
                status_provider=tracker.snapshot_payload,
                events_path=tracker.events_path,
                target_dir_provider=lambda target_id: run_dir / "lanes" / target_id,
                task_label="lane",
                heartbeat_sec=max(1, min(self.config.watcher_policy.seat_stall_threshold_sec, self.config.watcher_policy.stage_silent_threshold_sec, 5)),
            )
            watcher_monitor.start()
            for issue in preflight.get("issues", []):
                issue_code = str(issue.get("code", "")).strip()
                if issue_code in {"provider_unavailable", "profile_degraded"}:
                    watcher_recorder.alert(
                        trigger_code=issue_code,
                        stage="preflight",
                        target_id="",
                        severity="warning",
                        observation=str(issue.get("message", "")).strip(),
                        recommendation="觉者建议先修复 provider 链路；若系统已定义安全降级路径，可保留降级留痕后继续运行。",
                        suggested_next_step="核对 preflight 输出与 provider 发现结果。",
                    )
                    if issue_code == "profile_degraded":
                        watcher_recorder.action(
                            trigger_code=issue_code,
                            stage="preflight",
                            target_id="",
                            executed_action="controlled_degrade",
                            result="success",
                            observation=str(issue.get("message", "")).strip(),
                            recommendation="已记录受控降级，当前 run 不再伪装为完整 standard11。",
                        )

        lane_results: list[LaneResult] = []
        summary: dict[str, Any] = {
            "run_id": run_id,
            "status": "failed",
            "run_dir": str(run_dir),
            "obsidian_output_dir": str(output_dir),
            "requested_lane_profile": requested_profile,
            "effective_lane_profile": effective_profile,
            "parallel_policy": "strict_all",
            "quorum_profile": "strict-all",
            "quorum_reached": False,
            "ghosted_lane_ids": [],
            "late_lane_ids": [],
            "failed_lane_count": 0,
            "reason_codes": [],
            "watcher_enabled": watcher_active,
            "watcher_status": "watching" if watcher_active else "off",
            "watcher_alert_count": 0,
            "watcher_action_count": 0,
        }

        try:
            tracker.set_stage("brief")
            write_text(output_dir / "00-brief.md", render_brief_markdown(brief_text, run_id=run_id, created_at=manifest["started_at"]))
            tracker.add_artifact("brief_markdown", str(output_dir / "00-brief.md"))
            write_text(output_dir / "05-preflight.md", render_preflight_markdown(preflight, run_id=run_id, created_at=utc_now_iso()))
            tracker.add_artifact("preflight_markdown", str(output_dir / "05-preflight.md"))
            tracker.set_stage("variants")

            max_workers = max(1, min(self.config.max_workers, len(lane_specs)))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        self._execute_lane,
                        lane,
                        run_id=run_id,
                        brief_text=brief_text,
                        run_dir=run_dir,
                        output_dir=output_dir,
                        tracker=tracker,
                    )
                    for lane in lane_specs
                ]
                for future in concurrent.futures.as_completed(futures):
                    lane_results.append(future.result())
            lane_results.sort(key=lambda item: item.lane.obsidian_filename)

            fusion_dir = ensure_directory(run_dir / "fusion")
            fusion_context = self._build_fusion_context(lane_results)
            write_json(fusion_dir / "fusion_context.json", fusion_context)
            tracker.add_artifact("fusion_context", str(fusion_dir / "fusion_context.json"))
            tracker.set_stage("fusion")
            tracker.set_seat_status("fusion", "running")

            idea_map_text = self._run_fusion_text_step(
                stage="idea-map",
                prompt=build_idea_map_prompt(fusion_context),
                fusion_dir=fusion_dir,
                tracker=tracker,
                filename="30-idea-map.md",
            )
            debate_round_1_text = self._run_fusion_text_step(
                stage="debate-round-1",
                prompt=build_debate_round_prompt(
                    round_index=1,
                    fusion_context=fusion_context,
                    idea_map_text=idea_map_text,
                ),
                fusion_dir=fusion_dir,
                tracker=tracker,
                filename="40-debate-round-1.md",
            )
            debate_round_2_text = self._run_fusion_text_step(
                stage="debate-round-2",
                prompt=build_debate_round_prompt(
                    round_index=2,
                    fusion_context=fusion_context,
                    idea_map_text=idea_map_text,
                    previous_round_text=debate_round_1_text,
                ),
                fusion_dir=fusion_dir,
                tracker=tracker,
                filename="41-debate-round-2.md",
            )

            final_decisions, decisions_source_cli, decisions_model = self._run_fusion_json_step(
                stage="final-decisions",
                prompt=build_final_decisions_prompt(
                    fusion_context,
                    idea_map_text=idea_map_text,
                    debate_round_1_text=debate_round_1_text,
                    debate_round_2_text=debate_round_2_text,
                ),
                schema=FINAL_DECISIONS_SCHEMA,
                fusion_dir=fusion_dir,
                tracker=tracker,
            )
            write_json(fusion_dir / "final_decisions.json", final_decisions)
            write_text(
                output_dir / "50-fusion-decisions.md",
                render_decisions_markdown(
                    final_decisions,
                    run_id=run_id,
                    created_at=utc_now_iso(),
                    source_cli=decisions_source_cli,
                    model=decisions_model,
                ),
            )

            final_draft, final_draft_source_cli, final_draft_model = self._run_fusion_json_step(
                stage="final-draft",
                prompt=build_final_draft_prompt(fusion_context, decisions_payload=final_decisions),
                schema=FINAL_DRAFT_SCHEMA,
                fusion_dir=fusion_dir,
                tracker=tracker,
            )
            write_text(
                output_dir / "90-final-solution-draft.md",
                render_final_draft_markdown(
                    final_draft,
                    run_id=run_id,
                    created_at=utc_now_iso(),
                    source_cli=final_draft_source_cli,
                    model=final_draft_model,
                ),
            )
            write_text(output_dir / "99-index.md", render_index_markdown(run_id=run_id, created_at=utc_now_iso(), lane_results=lane_results))

            tracker.set_seat_status("fusion", "success")
            tracker.complete("success")
            summary["status"] = "success"
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            write_text(run_dir / "98-error.txt", error_text + "\n")
            write_text(output_dir / "98-error.md", f"# 运行失败\n\n```\n{error_text}\n```\n")
            tracker.emit("run-error", stage=tracker.state.get("stage", ""), error=error_text)
            if str(tracker.state.get("stage", "")) == "fusion":
                tracker.set_seat_status("fusion", "failed")
            if watcher_recorder is not None:
                watcher_recorder.alert(
                    trigger_code="fusion_failed" if tracker.state.get("stage") == "fusion" else "seat_failed",
                    stage=str(tracker.state.get("stage", "")),
                    target_id=str(tracker.state.get("current_seat_id", "")),
                    severity="error",
                    observation=error_text,
                    recommendation="觉者建议优先保留失败工件与当前收尾状态，不再继续盲目推进后续阶段。",
                    suggested_next_step="检查 98-error、对应 lane/fusion 日志与 watcher 工件。",
                )
                watcher_recorder.action(
                    trigger_code="run_interrupted" if "interrupt" in error_text.lower() else "fusion_failed",
                    stage=str(tracker.state.get("stage", "")),
                    target_id=str(tracker.state.get("current_seat_id", "")),
                    executed_action="finalize_failed_run",
                    result="success",
                    observation=error_text,
                    recommendation="已补写失败收尾状态与错误工件。",
                )
            tracker.complete("failed")
            summary["error"] = error_text
        finally:
            summary["failed_lane_count"] = sum(1 for result in lane_results if result.status == "failed")
            write_json(run_dir / "summary.json", summary)

        from pijiang.factory.analysis import audit_council_run

        audit = audit_council_run(
            summary,
            source_system="local_council",
            verification_command="python -m tools.solution_factory run --brief <brief> --project-path <project> --lanes <profile>",
        )
        summary["truth_audit_path"] = str(output_dir / "70-run-truth-audit.json")
        summary["audit_status"] = audit.audit_status
        summary["reason_codes"] = audit.reason_codes
        summary["fake_success_flag_count"] = len(audit.fake_success_flags)
        summary["regression_case_count"] = len(audit.regression_case_paths)
        if summary["status"] == "success" and audit.audit_status != "success":
            summary["status"] = audit.audit_status
            tracker.complete(audit.audit_status)
        if watcher_recorder is not None:
            if watcher_monitor is not None:
                watcher_monitor.stop()
            watcher_path = watcher_recorder.finalize(
                expected_artifacts={
                    "brief": output_dir / "00-brief.md",
                    "preflight": output_dir / "05-preflight.md",
                    "idea_map": output_dir / "30-idea-map.md",
                    "debate_round_1": output_dir / "40-debate-round-1.md",
                    "debate_round_2": output_dir / "41-debate-round-2.md",
                    "final_decisions": output_dir / "50-fusion-decisions.md",
                    "truth_audit": output_dir / "70-run-truth-audit.json",
                    "final_draft": output_dir / "90-final-solution-draft.md",
                }
            )
            tracker.add_artifact("watcher_advice", watcher_path)
            summary["watcher_status"] = tracker.state.get("watcher_state", "completed")
            summary["watcher_alert_count"] = int(tracker.state.get("watcher_alert_count", 0))
            summary["watcher_action_count"] = int(tracker.state.get("watcher_action_count", 0))
            summary["watcher_advice_path"] = watcher_path
            write_text(output_dir / "99-index.md", render_index_markdown(run_id=run_id, created_at=utc_now_iso(), lane_results=lane_results, watcher_filename="06-juezhe-watch.md"))
        write_json(run_dir / "summary.json", summary)
        return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the multi-model solution factory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run the solution factory.")
    run.add_argument("--brief", required=True, help="Absolute path to the brief markdown file.")
    run.add_argument("--project-path", required=True, help="Obsidian project path relative to the vault root.")
    run.add_argument("--lanes", default="standard11", help="Lane set to run. Supported: single, reduced6, standard11, standard10, default, default6, default9, default10.")
    run.add_argument("--watcher", choices=["auto", "on", "off"], default="auto", help="觉者守护层策略。")
    run.set_defaults(func=command_run)
    return parser


def command_run(args: argparse.Namespace) -> int:
    config = default_config(args.project_path)
    config.watcher_policy.cli_mode = args.watcher
    summary = SolutionFactory(config).run(brief_path=Path(args.brief), lanes=args.lanes, watcher_mode=args.watcher)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
