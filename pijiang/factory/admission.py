from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import OPENCODE_MARSHAL_SEAT_IDS, STANDARD11_PROFILE


DEFAULT_RUN_ROLE = "requalification"
DEFAULT_RUN_GRADE = "formal"
DEMO_RUN_ROLE = "demo"
DEMO_RUN_GRADE = "demo"

AUTHORITY_COMPANION_DOCS = [
    "docs/contracts/20-decision-matrix.json",
    "docs/contracts/60-execution-contract.md",
    "docs/contracts/65-namespace-boundary.md",
    "docs/contracts/70-baseline-admission-charter.md",
]
BLOCKING_BASELINE_REASON_CODES = {
    "critical_quorum_missing",
    "fusion_parse_failure",
    "stale_running_status",
    "topology_mismatch",
}


def authority_guardian_layer() -> dict[str, Any]:
    return {
        "seat_id": "watcher",
        "display_name": "觉者",
        "included_in_roster": False,
        "counts_toward_quorum": False,
        "counts_toward_benchmark": False,
        "content_mutation_allowed": False,
    }


def authority_namespace_boundary() -> dict[str, Any]:
    return {
        "seat_namespace": {"fusion": "seat"},
        "phase_namespace": {"final-synthesis": "phase"},
        "guardian_namespace": {"watcher": "guardian"},
    }


def authority_manifest_fields(*, run_role: str, run_grade: str, allow_degraded: bool) -> dict[str, Any]:
    return {
        "run_role": run_role,
        "run_grade": run_grade,
        "allow_degraded": bool(allow_degraded),
        "guardian_layer": authority_guardian_layer(),
        "namespace_boundary": authority_namespace_boundary(),
        "admission_path": list(AUTHORITY_COMPANION_DOCS),
    }


def manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items = manifest.get("seats") or manifest.get("lanes") or []
    return [dict(item) for item in items]


def manifest_seat_ids(manifest: dict[str, Any]) -> list[str]:
    seat_ids: list[str] = []
    for item in manifest_items(manifest):
        seat_id = str(item.get("seat_id") or item.get("id") or "").strip()
        if seat_id:
            seat_ids.append(seat_id)
    return seat_ids


def build_seat_registry(manifest: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(manifest_items(manifest), start=1):
        seat_id = str(item.get("seat_id") or item.get("id") or "").strip()
        entries.append(
            {
                "position": index,
                "seat_id": seat_id,
                "seat_type": str(item.get("seat_type", "")).strip(),
                "profile_id": str(item.get("profile_id", "")).strip(),
                "source_cli": str(item.get("source_cli", "")).strip(),
                "family": str(item.get("family", "")).strip(),
                "model": str(item.get("model", "")).strip(),
                "obsidian_filename": str(item.get("obsidian_filename", "")).strip(),
            }
        )
    return {
        "run_id": str(manifest.get("run_id", "")).strip(),
        "seat_registry_version": str(manifest.get("seat_registry_version", "")).strip(),
        "requested_profile": str(manifest.get("requested_lane_profile") or manifest.get("council_mode") or "").strip(),
        "effective_profile": str(manifest.get("effective_lane_profile") or manifest.get("council_mode") or "").strip(),
        "run_role": str(manifest.get("run_role", "")).strip(),
        "run_grade": str(manifest.get("run_grade", "")).strip(),
        "seat_count": len(entries),
        "fusion_seat_present": "fusion" in {entry["seat_id"] for entry in entries},
        "explicit_opencode_seats": list(OPENCODE_MARSHAL_SEAT_IDS),
        "entries": entries,
    }


def build_provider_preflight_snapshot(
    payload: dict[str, Any],
    *,
    source_system: str,
    requested_profile: str,
    effective_profile: str,
) -> dict[str, Any]:
    return {
        "source_system": source_system,
        "requested_profile": requested_profile,
        "effective_profile": effective_profile,
        "status": str(payload.get("status", "unknown")).strip(),
        "issues": list(payload.get("issues", [])),
        "ready_items": list(payload.get("ready_items", [])),
        "family_availability": payload.get("family_availability", {}),
        "endpoint_diagnostics": list(payload.get("endpoint_diagnostics", [])),
    }


def build_topology_report(manifest: dict[str, Any]) -> dict[str, Any]:
    seat_ids = manifest_seat_ids(manifest)
    guardian_layer = dict(manifest.get("guardian_layer") or authority_guardian_layer())
    namespace_boundary = dict(manifest.get("namespace_boundary") or authority_namespace_boundary())
    return {
        "run_id": str(manifest.get("run_id", "")).strip(),
        "requested_profile": str(manifest.get("requested_lane_profile") or manifest.get("council_mode") or "").strip(),
        "effective_profile": str(manifest.get("effective_lane_profile") or manifest.get("council_mode") or "").strip(),
        "run_role": str(manifest.get("run_role", "")).strip(),
        "run_grade": str(manifest.get("run_grade", "")).strip(),
        "seat_count": len(seat_ids),
        "resolved_seats": seat_ids,
        "explicit_opencode_seats": [seat_id for seat_id in OPENCODE_MARSHAL_SEAT_IDS if seat_id in seat_ids],
        "fusion_seat_present": "fusion" in seat_ids,
        "guardian_layer": guardian_layer,
        "namespace_boundary": namespace_boundary,
    }


def render_topology_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 拓扑与命名边界",
        "",
        f"- requested profile: `{report.get('requested_profile', '')}`",
        f"- effective profile: `{report.get('effective_profile', '')}`",
        f"- run_role: `{report.get('run_role', '')}`",
        f"- run_grade: `{report.get('run_grade', '')}`",
        f"- seat_count: `{report.get('seat_count', 0)}`",
        f"- fusion seat present: `{str(bool(report.get('fusion_seat_present', False))).lower()}`",
        "",
        "## 显式席位",
    ]
    for seat_id in report.get("resolved_seats", []):
        lines.append(f"- `{seat_id}`")
    lines.extend(
        [
            "",
            "## 四裨将",
        ]
    )
    for seat_id in OPENCODE_MARSHAL_SEAT_IDS:
        status = "present" if seat_id in report.get("explicit_opencode_seats", []) else "missing"
        lines.append(f"- `{seat_id}` / `{status}`")
    guardian = report.get("guardian_layer", {})
    lines.extend(
        [
            "",
            "## 守护层边界",
            f"- guardian seat: `{guardian.get('seat_id', 'watcher')}`",
            f"- included in roster: `{str(bool(guardian.get('included_in_roster', False))).lower()}`",
            f"- counts toward quorum: `{str(bool(guardian.get('counts_toward_quorum', False))).lower()}`",
            f"- counts toward benchmark: `{str(bool(guardian.get('counts_toward_benchmark', False))).lower()}`",
            "",
            "## 命名边界",
            "- `fusion` 只表示 seat。",
            "- `final-synthesis` 只表示 phase。",
            "- `watcher / 觉者` 只表示 guardian。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _check(code: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"code": code, "passed": bool(passed), "detail": detail}


def _required_artifact_status(artifact_paths: dict[str, str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for artifact_id, path_text in artifact_paths.items():
        path = Path(path_text)
        items.append({"artifact": artifact_id, "path": path_text, "present": path.exists() and path.stat().st_size > 0})
    return items


def build_baseline_admission_report(
    *,
    manifest: dict[str, Any],
    summary: dict[str, Any],
    audit_status: str,
    reason_codes: list[str],
    artifact_paths: dict[str, str],
    status_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seat_ids = manifest_seat_ids(manifest)
    requested_profile = str(manifest.get("requested_lane_profile") or manifest.get("council_mode") or "").strip()
    effective_profile = str(manifest.get("effective_lane_profile") or manifest.get("council_mode") or "").strip()
    run_role = str(manifest.get("run_role", "")).strip()
    run_grade = str(manifest.get("run_grade", "")).strip()
    allow_degraded = bool(manifest.get("allow_degraded", False))
    degraded_state = bool(manifest.get("degraded_state", False))
    resolved_seats = set(str(item).strip() for item in manifest.get("resolved_seats", []))
    guardian_layer = dict(manifest.get("guardian_layer") or authority_guardian_layer())
    guardian_id = str(guardian_layer.get("seat_id", "watcher")).strip()
    status_seats = set(str(key).strip() for key in (status_payload or {}).get("seat_statuses", {}).keys())
    reason_code_set = {str(item).strip() for item in reason_codes}
    artifact_status = _required_artifact_status(artifact_paths)

    explicit_opencode_ok = all(seat_id in seat_ids for seat_id in OPENCODE_MARSHAL_SEAT_IDS)
    guardian_isolated = guardian_id not in seat_ids and guardian_id not in resolved_seats and guardian_id not in status_seats
    fusion_traceable = "fusion" in seat_ids and next(
        (item["present"] for item in artifact_status if item["artifact"] == "final_decisions"),
        False,
    )
    final_synthesis_traceable = next(
        (item["present"] for item in artifact_status if item["artifact"] == "final_draft"),
        False,
    )
    required_artifacts_ready = all(item["present"] for item in artifact_status)
    topology_consistent = "topology_mismatch" not in reason_code_set
    no_undeclared_degraded = not degraded_state or allow_degraded
    no_explicit_degraded = not degraded_state
    predeclared_candidate = (
        requested_profile == STANDARD11_PROFILE
        and effective_profile == STANDARD11_PROFILE
        and run_grade == DEFAULT_RUN_GRADE
        and run_role in {DEFAULT_RUN_ROLE, "baseline-candidate"}
    )

    checks = [
        _check("run_role_declared", bool(run_role), f"run_role={run_role or '<missing>'}"),
        _check("run_grade_declared", bool(run_grade), f"run_grade={run_grade or '<missing>'}"),
        _check("formal_grade", run_grade == DEFAULT_RUN_GRADE, f"run_grade={run_grade}"),
        _check("canonical_standard11_target", requested_profile == STANDARD11_PROFILE, f"requested_profile={requested_profile}"),
        _check("effective_standard11_target", effective_profile == STANDARD11_PROFILE, f"effective_profile={effective_profile}"),
        _check("explicit_opencode_seats_present", explicit_opencode_ok, f"resolved_opencode={sorted(set(seat_ids) & set(OPENCODE_MARSHAL_SEAT_IDS))}"),
        _check("guardian_isolated", guardian_isolated, f"guardian_id={guardian_id} not in roster/status"),
        _check("fusion_path_traceable", fusion_traceable, "final-decisions artifact present and fusion seat resolved"),
        _check("final_synthesis_traceable", final_synthesis_traceable, "final-draft artifact present"),
        _check("required_artifacts_ready", required_artifacts_ready, "seat registry / provider preflight / run manifest / events / topology / final outputs"),
        _check("no_undeclared_degraded", no_undeclared_degraded, f"degraded_state={degraded_state}, allow_degraded={allow_degraded}"),
        _check("no_explicit_degraded_for_authority", no_explicit_degraded, f"degraded_state={degraded_state}"),
        _check("audit_status_success", audit_status == "success", f"audit_status={audit_status}"),
        _check("topology_consistent", topology_consistent, f"reason_codes={sorted(reason_code_set)}"),
        _check(
            "reason_code_gate_clean",
            not bool(reason_code_set & BLOCKING_BASELINE_REASON_CODES),
            f"blocking_reason_codes={sorted(reason_code_set & BLOCKING_BASELINE_REASON_CODES)}",
        ),
    ]

    candidate_ready = all(
        item["passed"]
        for item in checks
        if item["code"]
        in {
            "run_role_declared",
            "run_grade_declared",
            "formal_grade",
            "canonical_standard11_target",
            "effective_standard11_target",
            "explicit_opencode_seats_present",
            "guardian_isolated",
            "fusion_path_traceable",
            "final_synthesis_traceable",
            "required_artifacts_ready",
            "no_undeclared_degraded",
            "no_explicit_degraded_for_authority",
        }
    )
    admitted = predeclared_candidate and candidate_ready and all(
        item["passed"]
        for item in checks
        if item["code"] in {"audit_status_success", "topology_consistent", "reason_code_gate_clean"}
    )

    if admitted:
        promotion_status = "admitted"
    elif predeclared_candidate and candidate_ready:
        promotion_status = "candidate-denied"
    elif predeclared_candidate:
        promotion_status = "requalification-only"
    else:
        promotion_status = "not-eligible"

    blocking_reasons = [item["code"] for item in checks if not item["passed"]]
    return {
        "run_id": str(summary.get("run_id", manifest.get("run_id", ""))).strip(),
        "canonical_target": STANDARD11_PROFILE,
        "run_role": run_role,
        "run_grade": run_grade,
        "allow_degraded": allow_degraded,
        "requested_profile": requested_profile,
        "effective_profile": effective_profile,
        "degraded_state": degraded_state,
        "predeclared_candidate": predeclared_candidate,
        "candidate_ready": candidate_ready,
        "admitted": admitted,
        "promotion_status": promotion_status,
        "audit_status": audit_status,
        "reason_codes": sorted(reason_code_set),
        "blocking_reasons": blocking_reasons,
        "required_artifacts": artifact_status,
        "checks": checks,
        "admission_path": list(AUTHORITY_COMPANION_DOCS),
    }


def render_baseline_admission_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Baseline Admission Gate",
        "",
        f"- canonical_target: `{report.get('canonical_target', '')}`",
        f"- run_role: `{report.get('run_role', '')}`",
        f"- run_grade: `{report.get('run_grade', '')}`",
        f"- requested_profile: `{report.get('requested_profile', '')}`",
        f"- effective_profile: `{report.get('effective_profile', '')}`",
        f"- allow_degraded: `{str(bool(report.get('allow_degraded', False))).lower()}`",
        f"- promotion_status: `{report.get('promotion_status', '')}`",
        f"- admitted: `{str(bool(report.get('admitted', False))).lower()}`",
        "",
        "## Gate Checks",
    ]
    for item in report.get("checks", []):
        marker = "pass" if item.get("passed") else "fail"
        lines.append(f"- `{item.get('code', '')}` / `{marker}` / {item.get('detail', '')}")
    lines.extend(["", "## Required Artifacts"])
    for item in report.get("required_artifacts", []):
        marker = "present" if item.get("present") else "missing"
        lines.append(f"- `{item.get('artifact', '')}` / `{marker}` / `{item.get('path', '')}`")
    lines.extend(["", "## Admission Path"])
    for path in report.get("admission_path", []):
        lines.append(f"- `{path}`")
    return "\n".join(lines).rstrip() + "\n"
