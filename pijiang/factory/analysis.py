from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

from .runtime_support import CANONICAL_SECTIONS, utc_now_iso, write_json, write_text
from .registry import LEGACY_STANDARD10_PROFILE, OPENCODE_MARSHAL_SEAT_IDS, STANDARD11_PROFILE
from .types import BenchmarkMeasurement, BenchmarkReport, EvidenceRef, QualityAssessment, RegressionCase, RunTruthAudit, SearchArtifact, SeatResult


SEARCH_SEAT_IDS = {"search-1", "search-2", "codex-github-cases", "codex-web-research"}
POLLUTION_MARKERS = (
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
REPO_ANCHORS = ("cpj", "readme", "roadmap", "phase a", "phase b", "phase c", "doctor", "demo", "run")
DEFAULT_OUTPUT_FILENAMES = {
    "controller": "10-controller.md",
    "planning": "11-planning.md",
    "search-1": "12-search-1.md",
    "search-2": "13-search-2.md",
    "opencode-kimi": "14-opencode-kimi.md",
    "opencode-glm5": "15-opencode-glm5.md",
    "opencode-minimax": "16-opencode-minimax.md",
    "opencode-qwen": "17-opencode-qwen.md",
    "chaos": "18-chaos.md",
    "skeptic": "19-skeptic.md",
    "fusion": "20-fusion.md",
}

MISSING_SECTION_PLACEHOLDER = "> 缺口：模型未显式给出本节内容。"


def _seat_type_from_id(item_id: str) -> str:
    if item_id in {"search-1", "search-2", "codex-github-cases", "codex-web-research"}:
        return "search"
    if item_id in OPENCODE_MARSHAL_SEAT_IDS:
        return "marshal"
    if item_id in {"chaos", "codex-chaos"}:
        return "chaos"
    if item_id in {"skeptic", "codex-skeptic"}:
        return "skeptic"
    if item_id in {"controller", "codex-gpt"}:
        return "controller"
    if item_id in {"planning", "claude-gpt"}:
        return "planning"
    if item_id == "fusion":
        return "fusion"
    return "marshal"


def _manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("seats"):
        return list(manifest["seats"])
    if manifest.get("lanes"):
        payloads: list[dict[str, Any]] = []
        for lane in manifest["lanes"]:
            lane_id = str(lane.get("seat_id") or lane.get("id") or "").strip()
            payloads.append(
                {
                    **lane,
                    "seat_id": lane_id,
                    "seat_type": str(lane.get("seat_type") or _seat_type_from_id(lane_id)),
                }
            )
        return payloads
    return []


def _variant_dir_for_item(run_dir: Path, item_id: str) -> Path:
    for root_name in ("seats", "lanes"):
        candidate = run_dir / root_name / item_id
        if candidate.exists():
            return candidate
    return run_dir / "seats" / item_id


def _status_items(status_payload: dict[str, Any]) -> dict[str, str]:
    if status_payload.get("seat_statuses"):
        return {str(key): str(value) for key, value in status_payload["seat_statuses"].items()}
    if status_payload.get("lane_statuses"):
        return {str(key): str(value) for key, value in status_payload["lane_statuses"].items()}
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _is_missing_section_placeholder(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return stripped.startswith(MISSING_SECTION_PLACEHOLDER)


def _list_lines(text: str) -> list[str]:
    return [line.strip("- ").strip() for line in text.splitlines() if line.strip()]


def _first_sentence(text: str, limit: int = 160) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _normalize_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens = {token for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", left.lower()) if token}
    right_tokens = {token for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", right.lower()) if token}
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _extract_evidence_refs(text: str) -> list[str]:
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


def _count_anchor_hits(text: str) -> int:
    lowered = text.lower()
    return sum(1 for anchor in REPO_ANCHORS if anchor in lowered)


def _section_map_from_markdown(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {section: [] for section in CANONICAL_SECTIONS}
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            heading = line[2:].strip()
            if heading in sections:
                current = heading
                continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _mode_from_manifest(manifest: dict[str, Any]) -> str:
    effective_profile = str(manifest.get("effective_lane_profile", "")).strip().lower()
    if effective_profile in {"single", "reduced6", STANDARD11_PROFILE, LEGACY_STANDARD10_PROFILE, "standard10"}:
        return effective_profile
    seat_count = int(manifest.get("seat_count") or len(_manifest_items(manifest)))
    council_mode = str(manifest.get("council_mode", "")).strip()
    if seat_count == 1:
        return "single"
    if council_mode == STANDARD11_PROFILE or seat_count >= 11:
        return STANDARD11_PROFILE
    if seat_count >= 6:
        return "reduced6"
    return f"custom-{seat_count}"


def _output_filename_for_seat(seat_payload: dict[str, Any]) -> str:
    explicit = str(seat_payload.get("obsidian_filename", "")).strip()
    if explicit:
        return explicit
    return DEFAULT_OUTPUT_FILENAMES.get(str(seat_payload.get("seat_id", "")).strip(), "")


def _build_quality_assessment(seat_id: str, markdown_text: str) -> QualityAssessment:
    sections = _section_map_from_markdown(markdown_text)
    filled_sections = sum(1 for value in sections.values() if not _is_missing_section_placeholder(value))
    section_completeness = filled_sections / max(1, len(CANONICAL_SECTIONS))
    anchor_hits = _count_anchor_hits(markdown_text)
    evidence_count = len(_extract_evidence_refs(markdown_text))
    quality_flags: list[str] = []
    reason_codes: list[str] = []
    schema_valid = filled_sections == len(CANONICAL_SECTIONS)
    if not schema_valid:
        quality_flags.append("missing_sections")
        reason_codes.append("missing_sections")
    if evidence_count == 0 and seat_id in SEARCH_SEAT_IDS:
        quality_flags.append("search_without_evidence")
        reason_codes.append("search_without_real_evidence")
    if anchor_hits < 2:
        quality_flags.append("low_grounding")
    for marker in POLLUTION_MARKERS:
        if marker in markdown_text:
            quality_flags.append("polluted_output")
            reason_codes.append("polluted_output")
            break
    quality_score = round(
        section_completeness * 10
        + min(anchor_hits, 5) * 2
        + min(evidence_count, 5)
        + (0 if "polluted_output" in quality_flags else 5)
    )
    quality_score = max(0, min(25, quality_score))
    return QualityAssessment(
        seat_id=seat_id,
        schema_valid=schema_valid,
        anchor_hits=anchor_hits,
        evidence_count=evidence_count,
        section_completeness=round(section_completeness, 3),
        quality_score=quality_score,
        quality_flags=quality_flags,
        reason_codes=sorted(set(reason_codes)),
    )


def _build_seat_result(seat_id: str, seat_type: str, markdown_text: str) -> SeatResult:
    sections = _section_map_from_markdown(markdown_text)
    claims: list[dict[str, Any]] = []
    for section_name, body in sections.items():
        if _is_missing_section_placeholder(body):
            continue
        claims.append(
            {
                "statement": _first_sentence(body),
                "basis": section_name,
                "evidence_ref_ids": [hashlib.sha1(item.encode("utf-8")).hexdigest()[:8] for item in _extract_evidence_refs(body)],
            }
        )
    evidence_refs = [
        EvidenceRef(
            ref_id=hashlib.sha1(item.encode("utf-8")).hexdigest()[:8],
            source=item,
            snippet=item,
        )
        for item in _extract_evidence_refs(markdown_text)
    ]
    quality = _build_quality_assessment(seat_id, markdown_text)
    return SeatResult(
        seat_id=seat_id,
        seat_type=seat_type,
        summary=_first_sentence(sections.get("问题定义", "") or markdown_text),
        sections=sections,
        claims=claims,
        recommendations=_list_lines(sections.get("关键流程", "") + "\n" + sections.get("里程碑", ""))[:8],
        risks=_list_lines(sections.get("风险与取舍", ""))[:8],
        open_questions=_list_lines(sections.get("待确认问题", ""))[:8],
        evidence_refs=evidence_refs,
        confidence="low" if quality.quality_score < 10 else "medium" if quality.quality_score < 18 else "high",
        quality_flags=quality.quality_flags,
    )


def _build_search_artifact(seat_id: str, markdown_text: str) -> SearchArtifact:
    refs = _extract_evidence_refs(markdown_text)
    evidence_refs = [
        EvidenceRef(
            ref_id=hashlib.sha1(item.encode("utf-8")).hexdigest()[:8],
            source=item,
            snippet=item,
        )
        for item in refs
    ]
    return SearchArtifact(
        lane_id=seat_id,
        query_intent=_first_sentence(markdown_text),
        source_type="github" if "github" in markdown_text.lower() else "web",
        results=[
            {
                "title": item,
                "url": item if item.startswith("http") else "",
                "source_label": seat_id,
                "snippet": item,
                "relevance_reason": "run-derived evidence",
            }
            for item in refs[:8]
        ],
        evidence_refs=evidence_refs,
        key_findings=_list_lines(markdown_text)[:8],
        gaps=[] if refs else ["missing_evidence_refs"],
        confidence="medium" if refs else "low",
        degraded=not bool(refs),
    )


def _build_regression_case(
    *,
    failure_type: str,
    run_id: str,
    source_system: str,
    brief_text: str,
    offending_outputs: list[str],
    expected_behavior: str,
    repair_hypothesis: str,
    verification_command: str,
) -> RegressionCase:
    slug = hashlib.sha1(f"{run_id}:{failure_type}:{'|'.join(offending_outputs)}".encode("utf-8")).hexdigest()[:10]
    return RegressionCase(
        case_id=f"{failure_type}-{slug}",
        source_run_id=run_id,
        source_system=source_system,
        failure_type=failure_type,
        input_brief=brief_text,
        offending_outputs=offending_outputs,
        expected_behavior=expected_behavior,
        repair_hypothesis=repair_hypothesis,
        verification_command=verification_command,
    )


def _write_regression_cases(*, run_dir: Path, output_dir: Path, cases: list[RegressionCase]) -> list[str]:
    case_root = (run_dir / "analysis" / "regression-cases")
    case_root.mkdir(parents=True, exist_ok=True)
    output_case_root = output_dir / "regression-cases"
    output_case_root.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    index_lines = ["# Regression Cases", ""]
    for case in cases:
        case_path = case_root / case.failure_type / f"{case.case_id}.json"
        output_case_path = output_case_root / case.failure_type / f"{case.case_id}.json"
        case_path.parent.mkdir(parents=True, exist_ok=True)
        output_case_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(case_path, asdict(case))
        write_json(output_case_path, asdict(case))
        paths.append(str(output_case_path))
        index_lines.append(f"- `{case.case_id}` / `{case.failure_type}` / `{case.source_run_id}`")
    write_text(output_dir / "80-regression-cases-index.md", "\n".join(index_lines).rstrip() + "\n")
    return paths


def _load_events(run_dir: Path) -> list[dict[str, Any]]:
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def load_truth_audit(path: Path) -> RunTruthAudit:
    payload = _read_json(path.expanduser().resolve())
    payload.setdefault("audit_status", "success")
    payload.setdefault("reason_codes", [])
    return RunTruthAudit(**payload)


def _compute_audit_status(reason_codes: set[str], fake_success_flags: list[str], degraded_chain_ids: list[str]) -> str:
    fail_reasons = {
        "missing_final_draft",
        "fusion_parse_failure",
        "topology_mismatch",
        "stale_running_status",
        "critical_quorum_missing",
    }
    degraded_reasons = {
        "search_without_real_evidence",
        "polluted_output",
        "schema_failure",
        "timeout_partial_only",
        "hidden_fallback",
        "head_of_line_blocking",
        "provider_unavailable",
        "provider_invocation_failure",
        "profile_degraded",
    }
    review_reasons = {"missing_sections"}

    if reason_codes & fail_reasons:
        return "fail"
    if reason_codes & degraded_reasons:
        return "degraded"
    if reason_codes & review_reasons:
        return "needs-review"
    if fake_success_flags or degraded_chain_ids:
        return "degraded"
    return "success"


def audit_council_run(
    summary: dict[str, Any],
    *,
    source_system: str = "pijiang",
    verification_command: str = "",
) -> RunTruthAudit:
    run_dir = Path(summary["run_dir"]).expanduser().resolve()
    output_dir = Path(summary["obsidian_output_dir"]).expanduser().resolve()
    manifest = _read_json(run_dir / "run_manifest.json")
    brief_text = _read_text(Path(manifest["brief_path"]).expanduser().resolve())
    manifest_items = _manifest_items(manifest)
    expected_seat_count = len(manifest_items)
    successful_texts: list[str] = []
    cases: list[RegressionCase] = []
    degraded_chain_ids: list[str] = []
    fake_success_flags: list[str] = []
    repair_candidates: list[str] = []
    reason_codes: set[str] = set()
    analysis_root = run_dir / "analysis"
    analysis_root.mkdir(parents=True, exist_ok=True)
    status_payload = _load_status(run_dir)
    events = _load_events(run_dir)
    event_kinds = {event.get("kind", "") for event in events}
    fusion_fallback_logged = "fusion-step-fallback" in event_kinds

    search_expected = 0
    search_with_evidence = 0
    seat_valid_count = 0

    for seat_payload in manifest_items:
        seat_id = seat_payload["seat_id"]
        seat_type = seat_payload.get("seat_type", "")
        seat_dir = _variant_dir_for_item(run_dir, seat_id)
        variant_result_path = seat_dir / "variant_result.json"
        variant_payload = _read_json(variant_result_path) if variant_result_path.exists() else {"status": "missing"}
        markdown_name = _output_filename_for_seat(seat_payload)
        markdown_path = output_dir / markdown_name if markdown_name else output_dir / f"{seat_id}.md"
        markdown_text = _read_text(markdown_path)
        quality = _build_quality_assessment(seat_id, markdown_text)
        seat_result = _build_seat_result(seat_id, seat_type, markdown_text)
        write_json(analysis_root / f"{seat_id}.quality-assessment.json", asdict(quality))
        write_json(analysis_root / f"{seat_id}.seat-result.json", asdict(seat_result))

        if seat_id in SEARCH_SEAT_IDS or seat_type == "search":
            search_expected += 1
            search_artifact = _build_search_artifact(seat_id, markdown_text)
            write_json(analysis_root / f"{seat_id}.search-artifact.json", asdict(search_artifact))
            if search_artifact.evidence_refs:
                search_with_evidence += 1
            else:
                degraded_chain_ids.append(seat_id)
                repair_candidates.append(f"{seat_id}: 为搜索位补真实证据与链接，不要只保留名义搜索。")

        variant_status = str(variant_payload.get("status", "missing"))
        if variant_status == "success":
            successful_texts.append(markdown_text)
            if quality.schema_valid:
                seat_valid_count += 1
            if "polluted_output" in quality.quality_flags:
                fake_success_flags.append(f"polluted_output:{seat_id}")
                reason_codes.add("polluted_output")
                cases.append(
                    _build_regression_case(
                        failure_type="tool_log_pollution",
                        run_id=summary["run_id"],
                        source_system=source_system,
                        brief_text=brief_text,
                        offending_outputs=[str(markdown_path)],
                        expected_behavior="seat 成功产物应只包含最终方案正文，不应混入事件流或工具日志。",
                        repair_hypothesis="收紧解析器与输出净化逻辑，禁止工具日志进入最终正文。",
                        verification_command=verification_command,
                    )
                )
            if "missing_sections" in quality.quality_flags:
                degraded_chain_ids.append(seat_id)
                reason_codes.add("missing_sections")
                repair_candidates.append(f"{seat_id}: 强化结构化输出，保证 10 个 canonical sections 完整。")
        elif variant_status == "late_result":
            reason_codes.add("late_result_ignored")
            repair_candidates.append(f"{seat_id}: 迟到结果已被忽略，评估是否需要更细的 cutover 窗口。")
        elif variant_status == "ghost_blocked":
            reason_codes.add("ghost_blocked")
            repair_candidates.append(f"{seat_id}: 本轮被隔离为幽灵链路，检查 provider 慢链路与 cutover 条件。")
        else:
            degraded_chain_ids.append(seat_id)
            repair_candidates.append(f"{seat_id}: 修复失败 seat 的稳定性，并保留完整留痕。")
            error_summary = str(variant_payload.get("error_summary", "")).lower()
            if "unable to resolve" in error_summary or "executable" in error_summary:
                seat_failure_type = "provider_unavailable"
            elif "winerror 5" in error_summary or "permission" in error_summary:
                seat_failure_type = "provider_invocation_failure"
            else:
                seat_failure_type = "schema_failure" if markdown_text else "timeout_partial_only"
            reason_codes.add(seat_failure_type)
            cases.append(
                _build_regression_case(
                    failure_type=seat_failure_type,
                    run_id=summary["run_id"],
                    source_system=source_system,
                    brief_text=brief_text,
                    offending_outputs=[str(seat_dir)],
                    expected_behavior="失败 seat 必须有可回放工件，并在修复后转成稳定成功产物。",
                    repair_hypothesis="对失败 seat 增加更强的 prompt grounding、解析约束或 provider 降级策略。",
                    verification_command=verification_command,
                )
            )

    seat_integrity_score = round(100 * seat_valid_count / max(1, expected_seat_count))
    evidence_integrity_score = round(100 * search_with_evidence / max(1, search_expected))

    if len(successful_texts) >= 2:
        similarities = [
            _jaccard_similarity(_normalize_for_hash(left), _normalize_for_hash(right))
            for left, right in combinations(successful_texts, 2)
        ]
        discussion_diversity_score = round(100 * (1 - (sum(similarities) / len(similarities))))
    else:
        discussion_diversity_score = 100

    fusion_files = [
        output_dir / "30-idea-map.md",
        output_dir / "40-debate-round-1.md",
        output_dir / "41-debate-round-2.md",
        output_dir / "50-fusion-decisions.md",
        output_dir / "90-final-solution-draft.md",
    ]
    fusion_integrity_score = round(100 * sum(1 for path in fusion_files if path.exists() and _read_text(path).strip()) / len(fusion_files))

    artifact_files = [
        run_dir / "run_manifest.json",
        run_dir / "status.json",
        run_dir / "events.jsonl",
        run_dir / "fusion" / "fusion_context.json",
    ]
    artifact_integrity_score = round(100 * sum(1 for path in artifact_files if path.exists() and path.stat().st_size > 0) / len(artifact_files))

    final_draft_text = _read_text(output_dir / "90-final-solution-draft.md")
    if not final_draft_text.strip():
        fake_success_flags.append("missing_final_draft")
        reason_codes.add("missing_final_draft")
    if discussion_diversity_score < 20:
        fake_success_flags.append("high_homogeneity")
        cases.append(
            _build_regression_case(
                failure_type="generic_output",
                run_id=summary["run_id"],
                source_system=source_system,
                brief_text=brief_text,
                offending_outputs=[str(output_dir)],
                expected_behavior="多路议会应体现明显差异和分工，而不是高度同质化复读。",
                repair_hypothesis="强化 seat 差异化职责、grounding 和质量门，防止泛化模板复写。",
                verification_command=verification_command,
            )
        )
    if evidence_integrity_score < 50 and search_expected > 0:
        fake_success_flags.append("search_without_real_evidence")
        reason_codes.add("search_without_real_evidence")
        cases.append(
            _build_regression_case(
                failure_type="search_failure",
                run_id=summary["run_id"],
                source_system=source_system,
                brief_text=brief_text,
                offending_outputs=[str(output_dir)],
                expected_behavior="搜索席位应提供可引用证据，而不是只写通用分析。",
                repair_hypothesis="把 search seat 从意见席位升级成 SearchArtifact 证据生产层。",
                verification_command=verification_command,
            )
        )
    if fusion_integrity_score < 100:
        degraded_chain_ids.append("fusion")
        repair_candidates.append("fusion: 补齐 idea-map、debate、final-decisions、final-draft 全链路产物。")
    if status_payload.get("status") == "running":
        reason_codes.add("stale_running_status")
        cases.append(
            _build_regression_case(
                failure_type="stale_running_status",
                run_id=summary["run_id"],
                source_system=source_system,
                brief_text=brief_text,
                offending_outputs=[str(run_dir / "status.json")],
                expected_behavior="run 结束后 status.json 不得继续停留在 running。",
                repair_hypothesis="任何 fusion 或 audit 异常都必须显式收尾并写入 failed/degraded 状态。",
                verification_command=verification_command,
            )
        )
    status_items = _status_items(status_payload)
    non_terminal_seats = [
        seat_id
        for seat_id, seat_status in status_items.items()
        if seat_status not in {"success", "failed", "ghost_blocked", "late_result"}
    ]
    terminal_seat_count = sum(
        1
        for seat_status in status_items.values()
        if seat_status in {"success", "failed", "ghost_blocked", "late_result"}
    )
    if non_terminal_seats or terminal_seat_count != expected_seat_count:
        reason_codes.add("topology_mismatch")
    if manifest.get("requested_lane_profile") and manifest.get("effective_lane_profile"):
        if manifest["requested_lane_profile"] != manifest["effective_lane_profile"]:
            reason_codes.add("profile_degraded")
    if summary.get("parallel_policy") == "ghost_isolation":
        if summary.get("quorum_reached"):
            reason_codes.add("quorum_fusion")
        else:
            reason_codes.add("critical_quorum_missing")
        if summary.get("ghosted_lane_count", 0):
            reason_codes.add("ghost_blocked")
        if summary.get("late_result_count", 0):
            reason_codes.add("late_result_ignored")
    elif summary.get("parallel_policy") == "strict_all" and summary.get("failed_lane_count", 0):
        reason_codes.add("head_of_line_blocking")
    reason_codes.update(summary.get("reason_codes", []))
    if list((run_dir / "fusion").glob("*.claude.stdout.log")) and not fusion_fallback_logged:
        reason_codes.add("hidden_fallback")
    fusion_dir = run_dir / "fusion"
    fusion_stage_logs = list(fusion_dir.glob("final-decisions*.log")) + list(fusion_dir.glob("final-draft*.log"))
    missing_fusion_outputs = not (output_dir / "50-fusion-decisions.md").exists() or not final_draft_text.strip()
    if (
        summary.get("error")
        and ("json" in str(summary.get("error", "")).lower() or "fusion" in str(summary.get("error", "")).lower())
    ) or (fusion_stage_logs and missing_fusion_outputs):
        reason_codes.add("fusion_parse_failure")

    regression_case_paths = _write_regression_cases(run_dir=run_dir, output_dir=output_dir, cases=cases)
    audit_status = _compute_audit_status(reason_codes, fake_success_flags, degraded_chain_ids)
    audit = RunTruthAudit(
        run_id=summary["run_id"],
        mode=_mode_from_manifest(manifest),
        audit_status=audit_status,
        seat_integrity_score=seat_integrity_score,
        discussion_diversity_score=discussion_diversity_score,
        evidence_integrity_score=evidence_integrity_score,
        fusion_integrity_score=fusion_integrity_score,
        artifact_integrity_score=artifact_integrity_score,
        fake_success_flags=sorted(set(fake_success_flags)),
        degraded_chain_ids=sorted(set(degraded_chain_ids)),
        reason_codes=sorted(reason_codes),
        regression_case_paths=regression_case_paths,
        repair_candidates=sorted(set(repair_candidates)),
    )
    write_json(run_dir / "analysis" / "run-truth-audit.json", asdict(audit))
    write_json(output_dir / "70-run-truth-audit.json", asdict(audit))
    return audit


def _load_status(run_dir: Path) -> dict[str, Any]:
    return _read_json(run_dir / "status.json")


def _latency_ms(status_payload: dict[str, Any]) -> int:
    started = status_payload.get("started_at", "")
    finished = status_payload.get("finished_at", "")
    if not started or not finished:
        return 0
    started_at = datetime.fromisoformat(started.replace("Z", "+00:00"))
    finished_at = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    return int((finished_at - started_at).total_seconds() * 1000)


def _provider_call_count(run_dir: Path) -> int:
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        return 0
    count = 0
    for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("kind") in {"seat-attempt-start", "lane-attempt-start", "fusion-step-start"}:
            count += 1
    return count


def _estimate_cost(provider_calls: int, mode: str) -> float:
    weight = {"single": 1.0, "reduced6": 1.4, STANDARD11_PROFILE: 1.9, LEGACY_STANDARD10_PROFILE: 1.8, "standard10": 1.8}.get(mode, 1.0)
    return round(provider_calls * weight, 2)


def _issue_readiness_score(output_dir: Path) -> float:
    final_draft = _read_text(output_dir / "90-final-solution-draft.md")
    score = 0.0
    for marker in ("为什么现在做", "验收标准", "Issue", "优先级", "Phase"):
        if marker in final_draft:
            score += 1.0
    return score


def build_benchmark_measurement(summary: dict[str, Any], *, audit: RunTruthAudit | None = None) -> BenchmarkMeasurement:
    run_dir = Path(summary["run_dir"]).expanduser().resolve()
    output_dir = Path(summary["obsidian_output_dir"]).expanduser().resolve()
    manifest = _read_json(run_dir / "run_manifest.json")
    loaded_audit = audit or (
        load_truth_audit(Path(summary["truth_audit_path"])) if summary.get("truth_audit_path") else audit_council_run(summary)
    )
    status = _load_status(run_dir)
    expected = max(1, len(manifest.get("seats", [])))
    provider_calls = _provider_call_count(run_dir)
    return BenchmarkMeasurement(
        mode=_mode_from_manifest(manifest),
        run_id=summary["run_id"],
        latency_ms=_latency_ms(status),
        provider_calls=provider_calls,
        estimated_cost=_estimate_cost(provider_calls, _mode_from_manifest(manifest)),
        audit_pass_success_rate=1.0 if loaded_audit.audit_status == "success" else 0.0,
        cost_per_audited_success=_estimate_cost(provider_calls, _mode_from_manifest(manifest)) if loaded_audit.audit_status == "success" else 0.0,
        schema_pass_rate=round(loaded_audit.seat_integrity_score / 100, 3),
        evidence_coverage=round(loaded_audit.evidence_integrity_score / 100, 3),
        quality_score=round(
            (loaded_audit.seat_integrity_score + loaded_audit.discussion_diversity_score + loaded_audit.fusion_integrity_score)
            / 3
            / 100,
            3,
        ),
        issue_readiness_score=_issue_readiness_score(output_dir),
        failed_rate=round(summary.get("failed_lane_count", 0) / expected, 3),
        fake_success_rate=round(len(loaded_audit.fake_success_flags) / max(1, expected), 3),
        time_to_fusion_cutover_ms=int(summary.get("fusion_cutover_ms", 0) or 0),
        ghosted_lane_count=int(summary.get("ghosted_lane_count", 0) or 0),
        late_result_count=int(summary.get("late_result_count", 0) or 0),
        cutover_latency_saved_ms=max(0, _latency_ms(status) - int(summary.get("fusion_cutover_ms", 0) or 0)),
        degraded_flags=loaded_audit.fake_success_flags + loaded_audit.degraded_chain_ids,
        truth_audit_path=str(output_dir / "70-run-truth-audit.json"),
        watcher_enabled=bool(summary.get("watcher_enabled", False)),
        watcher_alert_count=int(summary.get("watcher_alert_count", 0) or 0),
        watcher_action_count=int(summary.get("watcher_action_count", 0) or 0),
    )


def build_benchmark_report(*, scenario_id: str, summaries_by_mode: dict[str, dict[str, Any]]) -> BenchmarkReport:
    report = BenchmarkReport(scenario_id=scenario_id, generated_at=utc_now_iso())
    order = ["single", "reduced6", STANDARD11_PROFILE]
    for mode in order:
        summary = summaries_by_mode.get(mode)
        if summary is None:
            continue
        measurement = build_benchmark_measurement(summary)
        report.measurements.append(measurement)
    return report


def render_benchmark_report_markdown(report: BenchmarkReport) -> str:
    lines = [
        "---",
        f"generated_at: {report.generated_at}",
        f"scenario_id: {report.scenario_id}",
        "---",
        "",
        "# Benchmark Report",
        "",
        "| 模式 | run_id | latency_ms | cutover_ms | ghosted | late | saved_ms | provider_calls | estimated_cost | audit_pass_success_rate | cost_per_audited_success | schema_pass_rate | evidence_coverage | quality_score | issue_ready | failed_rate | fake_success_rate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report.measurements:
        lines.append(
            f"| {item.mode} | `{item.run_id}` | {item.latency_ms} | {item.time_to_fusion_cutover_ms} | {item.ghosted_lane_count} | {item.late_result_count} | {item.cutover_latency_saved_ms} | {item.provider_calls} | {item.estimated_cost} | "
            f"{item.audit_pass_success_rate:.2f} | {item.cost_per_audited_success:.2f} | "
            f"{item.schema_pass_rate:.2f} | {item.evidence_coverage:.2f} | {item.quality_score:.2f} | {item.issue_readiness_score:.2f} | "
            f"{item.failed_rate:.2f} | {item.fake_success_rate:.2f} |"
        )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
