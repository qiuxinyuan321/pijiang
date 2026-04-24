"""Read-only inspectors for past council runs.

Used by `cpj runs` (history) and `cpj show <run-id>` to surface what the engine
wrote to disk (`cache_root/runs/<run_id>/` + the Obsidian/output mirror) without
re-running anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunSummary:
    """Aggregated view of a past run drawn from multiple JSON artifacts."""

    run_id: str
    status: str = "unknown"
    stage: str = ""
    topic: str = ""
    brief_path: str = ""
    council_mode: str = ""
    started_at: str = ""
    finished_at: str = ""
    seat_count: int = 0
    completed_seat_count: int = 0
    failed_seat_count: int = 0
    audit_status: str = ""
    reason_codes: list[str] = field(default_factory=list)
    fake_success_flag_count: int = 0
    regression_case_count: int = 0
    output_dir: str = ""
    run_dir: str = ""
    watcher_alert_count: int = 0
    watcher_action_count: int = 0


@dataclass
class RunArtifact:
    """A single artifact on disk — typically a Markdown or JSON file."""

    label: str
    relative_path: str
    absolute_path: str
    exists: bool
    size_bytes: int = 0


def runs_root(cache_root: Path) -> Path:
    """Return the directory the engine writes run state to."""
    return Path(cache_root).expanduser().resolve() / "runs"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_truth_audit(output_dir: Path) -> dict[str, Any]:
    if not output_dir:
        return {}
    return _read_json(output_dir / "70-run-truth-audit.json")


def load_run_summary(run_dir: Path) -> RunSummary | None:
    """Build a RunSummary from the files under `run_dir` or return None if the
    directory doesn't look like a pijiang run (no manifest)."""
    run_dir = run_dir.expanduser().resolve()
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return None
    manifest = _read_json(manifest_path)
    status_payload = _read_json(run_dir / "status.json")
    output_dir_str = str(manifest.get("obsidian_output_dir") or "").strip()
    output_dir = Path(output_dir_str) if output_dir_str else Path()
    audit = _read_truth_audit(output_dir)

    return RunSummary(
        run_id=str(manifest.get("run_id") or run_dir.name),
        status=str(status_payload.get("status") or manifest.get("status") or "unknown"),
        stage=str(status_payload.get("stage") or ""),
        topic=str(manifest.get("project_path") or ""),
        brief_path=str(manifest.get("brief_path") or ""),
        council_mode=str(manifest.get("council_mode") or ""),
        started_at=str(manifest.get("started_at") or ""),
        finished_at=str(status_payload.get("finished_at") or ""),
        seat_count=int(manifest.get("seat_count") or 0),
        completed_seat_count=int(status_payload.get("completed_seat_count") or 0),
        failed_seat_count=int(status_payload.get("failed_seat_count") or 0),
        audit_status=str(audit.get("audit_status") or ""),
        reason_codes=list(audit.get("reason_codes") or []),
        fake_success_flag_count=len(list(audit.get("fake_success_flags") or [])),
        regression_case_count=len(list(audit.get("regression_case_paths") or [])),
        output_dir=output_dir_str,
        run_dir=str(run_dir),
        watcher_alert_count=int(status_payload.get("watcher_alert_count") or 0),
        watcher_action_count=int(status_payload.get("watcher_action_count") or 0),
    )


def list_run_summaries(cache_root: Path, *, limit: int | None = 10) -> list[RunSummary]:
    """Return the most recent runs under the cache tree, newest first.

    Looks at both `cache_root/runs/` (real runs) and `cache_root/demo/runs/`
    (demo runs) so users see everything in one list. De-duplicates by run_id
    if the same id appears in both (real run wins)."""
    roots_to_scan: list[Path] = []
    base = Path(cache_root).expanduser().resolve()
    for candidate in (base / "runs", base / "demo" / "runs"):
        if candidate.exists():
            roots_to_scan.append(candidate)
    summaries: dict[str, RunSummary] = {}
    for root in roots_to_scan:
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            summary = load_run_summary(entry)
            if summary is None:
                continue
            # If we already saw this run_id from the primary root, keep it.
            summaries.setdefault(summary.run_id, summary)
    ordered = sorted(
        summaries.values(),
        key=lambda item: (item.started_at, item.run_id),
        reverse=True,
    )
    if limit is not None and limit > 0:
        ordered = ordered[:limit]
    return ordered


# Canonical artifact layout mirrored in `cpj show` output.
_STANDARD_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("Brief", "00-brief.md"),
    ("Run overview", "01-run-overview.md"),
    ("Topology report", "02-topology-report.md"),
    ("Seat registry", "03-seat-registry.json"),
    ("Provider preflight", "04-provider-preflight-snapshot.json"),
    ("觉者 watch", "06-juezhe-watch.md"),
    ("Controller", "10-controller.md"),
    ("Planning", "11-planning.md"),
    ("Search 1", "12-search-1.md"),
    ("Search 2", "13-search-2.md"),
    ("Marshal · Kimi", "14-opencode-kimi.md"),
    ("Marshal · GLM-5", "15-opencode-glm5.md"),
    ("Marshal · MiniMax", "16-opencode-minimax.md"),
    ("Marshal · Qwen", "17-opencode-qwen.md"),
    ("Chaos", "18-chaos.md"),
    ("Skeptic", "19-skeptic.md"),
    ("Fusion", "20-fusion.md"),
    ("Idea map", "30-idea-map.md"),
    ("Debate round 1", "40-debate-round-1.md"),
    ("Debate round 2", "41-debate-round-2.md"),
    ("Fusion decisions", "50-fusion-decisions.md"),
    ("Truth audit", "70-run-truth-audit.json"),
    ("Baseline admission", "75-baseline-admission.md"),
    ("Regression cases", "80-regression-cases-index.md"),
    ("Final draft", "90-final-solution-draft.md"),
    ("Index", "99-index.md"),
)


def list_run_artifacts(summary: RunSummary) -> list[RunArtifact]:
    """Collect the canonical artifacts for a run. Missing files are still
    returned (with `exists=False`) so the caller can show gaps."""
    artifacts: list[RunArtifact] = []
    output_dir = Path(summary.output_dir) if summary.output_dir else None
    for label, filename in _STANDARD_ARTIFACTS:
        if output_dir is None:
            artifacts.append(
                RunArtifact(
                    label=label,
                    relative_path=filename,
                    absolute_path="",
                    exists=False,
                )
            )
            continue
        full = output_dir / filename
        artifacts.append(
            RunArtifact(
                label=label,
                relative_path=filename,
                absolute_path=str(full),
                exists=full.exists(),
                size_bytes=full.stat().st_size if full.exists() else 0,
            )
        )
    return artifacts


def find_run_by_id(cache_root: Path, run_id: str) -> RunSummary | None:
    """Locate a run by exact id (or unique substring) across real and demo runs."""
    base = Path(cache_root).expanduser().resolve()
    roots_to_scan: list[Path] = []
    for candidate in (base / "runs", base / "demo" / "runs"):
        if candidate.exists():
            roots_to_scan.append(candidate)
    if not roots_to_scan:
        return None

    # Exact match wins, in priority order (real runs first).
    for root in roots_to_scan:
        exact = root / run_id
        if exact.is_dir():
            return load_run_summary(exact)

    # Substring match across all roots; only succeed if it resolves uniquely.
    matches: list[Path] = []
    for root in roots_to_scan:
        matches.extend(
            entry for entry in root.iterdir() if entry.is_dir() and run_id in entry.name
        )
    if len(matches) == 1:
        return load_run_summary(matches[0])
    return None
