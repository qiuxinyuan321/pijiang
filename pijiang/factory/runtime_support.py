from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

SEARCH_SEAT_IDS = {"search-1", "search-2"}
OUTPUT_POLLUTION_MARKERS = (
    '{"type":"step_start"',
    '{"type":"tool_use"',
    "functions.bash",
    "现在我来生成",
    "下面我来",
    "我先核对",
    "我先检查",
    "我需要查看",
    "API Error:",
)

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


def split_project_path(project_path: str) -> list[str]:
    return [segment for segment in re.split(r"[\\/]+", project_path.strip()) if segment]


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


def has_canonical_heading(raw_text: str) -> bool:
    heading_pattern = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*$")
    for line in raw_text.splitlines():
        matched = heading_pattern.match(line)
        if not matched:
            continue
        canonical = SECTION_ALIAS_MAP.get(normalize_heading(matched.group(1)), "")
        if canonical:
            return True
    return False


def trim_to_canonical_markdown(raw_text: str) -> str:
    heading_pattern = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*$")
    lines = raw_text.splitlines()
    for index, line in enumerate(lines):
        matched = heading_pattern.match(line)
        if not matched:
            continue
        canonical = SECTION_ALIAS_MAP.get(normalize_heading(matched.group(1)), "")
        if canonical:
            return "\n".join(lines[index:]).strip()
    return raw_text.strip()


def extract_evidence_refs(text: str) -> list[str]:
    refs: list[str] = []
    refs.extend(re.findall(r"https?://[^\s)>\]]+", text))
    lowered = text.lower()
    for anchor in ("github", "readme", "roadmap", "ci", "contributing", "issue", "release", "cpj "):
        if anchor in lowered:
            refs.append(anchor.strip())
    deduped: list[str] = []
    for item in refs:
        if item not in deduped:
            deduped.append(item)
    return deduped


def variant_quality_issue(lane: LaneSpec, raw_text: str) -> str:
    trimmed = raw_text.strip()
    if not trimmed:
        return "output is empty"
    if not has_canonical_heading(trimmed):
        return "output does not contain canonical markdown headings"
    sections = parse_variant_sections(trimmed)
    filled_sections = sum(1 for value in sections.values() if value.strip())
    if filled_sections < len(CANONICAL_SECTIONS):
        return f"output only filled {filled_sections}/{len(CANONICAL_SECTIONS)} canonical sections"
    for marker in OUTPUT_POLLUTION_MARKERS:
        if marker in trimmed:
            return f"output contains polluted marker `{marker}`"
    if lane.id in SEARCH_SEAT_IDS:
        evidence_count = len(extract_evidence_refs(trimmed))
        if evidence_count < 3:
            return f"search seat only produced {evidence_count} evidence refs"
    return ""


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
            "sf_lane": "fusion",
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
                lines.append(f"  - {candidate.get('lane', 'unknown')} / {candidate.get('option', '')} / {candidate.get('reason', '')}")
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
            "sf_lane": "fusion",
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
    search_hardening_block = ""
    if lane.id in SEARCH_SEAT_IDS:
        search_hardening_block = (
            "搜索位硬约束：\n"
            "1. 你不是普通分析位，你必须先完成真实外部检索，再给结论。\n"
            "2. 至少保留 5 条外部证据，优先使用完整 URL 或 GitHub 仓库链接。\n"
            "3. 对每条关键外部观察，说明：借鉴点 / 不借鉴点 / 适用原因。\n"
            "4. 如果检索失败或证据不足，必须明确写出缺口，不允许假装已经完成搜索。\n\n"
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
        f"{search_hardening_block}"
        f"{special_block}"
        f"Brief:\n{brief_text.strip()}\n"
    )


def build_idea_map_prompt(fusion_context: dict[str, Any]) -> str:
    return (
        f"{stage_marker_block('idea-map', 'fusion')}\n"
        "请根据 fusion_context 输出 Markdown，并且必须包含以下一级标题：\n"
        "# 共识点\n# 独特亮点\n# 冲突点\n# 质疑焦点\n# 可组合点\n\n"
        "要求：明确抽取质疑席位的核心质疑，并把它单列到“质疑焦点”。\n\n"
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
        f"{stage_marker_block(f'debate-round-{round_index}', 'fusion')}\n"
        f"请输出第 {round_index} 轮辩论纪要的 Markdown。\n"
        "把这轮视为多模型议会对质疑席位的对抗讨论。\n"
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
        f"{stage_marker_block('final-decisions-json', 'fusion')}\n"
        "请输出 JSON，形成终版的决策账本。不要输出 Markdown，不要输出代码块。\n"
        "每条决策都必须包含 topic、decision、sources、reason、skeptic_challenge、skeptic_rebuttal、rejected_options、open_questions。\n"
        f"Idea map:\n{idea_map_text.strip()}\n\n"
        f"Round 1:\n{debate_round_1_text.strip()}\n\n"
        f"Round 2:\n{debate_round_2_text.strip()}\n\n"
        f"fusion_context:\n{json.dumps(fusion_context, ensure_ascii=False, indent=2)}\n"
    )


def build_final_draft_prompt(fusion_context: dict[str, Any], *, decisions_payload: dict[str, Any]) -> str:
    return (
        f"{stage_marker_block('final-draft-json', 'fusion')}\n"
        "请输出 JSON，形成终版方案草案。不要输出 Markdown，不要输出代码块。\n"
        "每个 section 都必须包含 title、content、sources、rationale、status。\n"
        f"decisions_payload:\n{json.dumps(decisions_payload, ensure_ascii=False, indent=2)}\n\n"
        f"fusion_context:\n{json.dumps(fusion_context, ensure_ascii=False, indent=2)}\n"
    )
