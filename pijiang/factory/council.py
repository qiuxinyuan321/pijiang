from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .analysis import audit_council_run
from .runtime_support import (
    FINAL_DECISIONS_SCHEMA,
    FINAL_DRAFT_SCHEMA,
    LaneResult,
    LaneSpec,
    build_debate_round_prompt,
    build_final_decisions_prompt,
    build_final_draft_prompt,
    build_idea_map_prompt,
    build_variant_prompt,
    ensure_directory,
    normalize_variant_markdown,
    parse_variant_sections,
    render_brief_markdown,
    render_decisions_markdown,
    render_final_draft_markdown,
    render_index_markdown,
    render_stage_markdown,
    split_project_path,
    trim_to_canonical_markdown,
    utc_now_iso,
    variant_quality_issue,
    write_json,
    write_text,
)

from .config import PijiangConfig, active_seats, council_mode, find_provider, unique_active_profile_count
from .providers import ProviderExecutionError, adapter_for_profile, execute_profile_request
from .types import CouncilSeat, ExecutionRequest, RunProgressSnapshot
from .watcher import WatcherMonitor, WatcherRecorder, recover_abandoned_runs, watcher_enabled


ProgressCallback = Callable[[RunProgressSnapshot, dict[str, Any]], None]
HEARTBEAT_INTERVAL_SEC = 15
PARALLEL_POLICIES = {"strict_all", "ghost_isolation"}
STANDARD_QUORUM_PROFILE = "standard10-quorum6"


SEAT_LIBRARY: dict[str, dict[str, str]] = {
    "controller": {
        "filename": "10-controller.md",
        "thinking_angle": "从总体调度、强模型主控与最终收敛策略角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担主控分析职责。你的任务是给出可执行的总体路线，而不是做戏剧化角色表演。",
    },
    "planning": {
        "filename": "11-planning.md",
        "thinking_angle": "从 planning provider、结构化规划和强决策路径角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担规划分析职责。优先补强结构化规划、约束与关键路径。",
    },
    "search-1": {
        "filename": "12-search-1.md",
        "thinking_angle": "从外部产品、网页、资料与公开经验角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担外部搜索分析职责。重点补外部资料与产品经验。",
    },
    "search-2": {
        "filename": "13-search-2.md",
        "thinking_angle": "从 GitHub、案例仓库、实现经验与可复用模式角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担外部搜索分析职责。重点补 GitHub 与实现案例。",
    },
    "marshal-1": {
        "filename": "14-marshal-1.md",
        "thinking_angle": "从工程可执行性、落地路径与实现边界角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担裨将分析职责。重点给出可执行落地路径。",
    },
    "marshal-2": {
        "filename": "15-marshal-2.md",
        "thinking_angle": "从结构整理、约束归纳与方案压缩角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担裨将分析职责。重点做结构化归纳与约束压缩。",
    },
    "marshal-3": {
        "filename": "16-marshal-3.md",
        "thinking_angle": "从用户体验、可部署性与新手路径角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担裨将分析职责。重点补低门槛部署与新手体验。",
    },
    "chaos": {
        "filename": "17-chaos.md",
        "thinking_angle": "从反常规破局、打破局部最优与混沌创新角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担混沌分析职责。重点提出反共识与破局路线。",
    },
    "skeptic": {
        "filename": "18-skeptic.md",
        "thinking_angle": "从敌对审查、红队拆解、失败模式与强质疑角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担质疑分析职责。重点拆系统、找风险、提最难回答的反对意见。",
    },
    "fusion": {
        "filename": "19-fusion.md",
        "thinking_angle": "从最终合并、决策账本整理与终版收敛角度提出方案。",
        "special": "你不是在扮演人格，而是在真实多模型议会中承担融合分析职责。重点把多模型分歧整合成可执行终版。",
    },
}


def _seat_sort_key(seat: CouncilSeat) -> int:
    order = [
        "controller",
        "planning",
        "search-1",
        "search-2",
        "marshal-1",
        "marshal-2",
        "marshal-3",
        "chaos",
        "skeptic",
        "fusion",
    ]
    try:
        return order.index(seat.seat_id)
    except ValueError:
        return len(order)


def _estimate_wait_label(seats: list[CouncilSeat], provider_count: int) -> str:
    score = len(seats) + provider_count
    if any(seat.seat_type == "planning" for seat in seats):
        score += 2
    if sum(1 for seat in seats if seat.seat_type == "search") >= 2:
        score += 2
    if score >= 16:
        return "很慢"
    if score >= 12:
        return "较慢"
    if score >= 8:
        return "标准"
    return "快速"


def _heartbeat_message(prefix: str, started_at: float) -> str:
    elapsed = max(1, int(time.monotonic() - started_at))
    return f"{prefix}，已耗时 {elapsed}s。"


def _retry_backoff_seconds(values: list[int], attempt: int) -> int:
    if not values:
        return 0
    index = max(0, min(attempt - 1, len(values) - 1))
    return max(0, int(values[index]))


def _normalize_parallel_policy(value: str | None) -> str:
    candidate = (value or "ghost_isolation").strip().lower()
    if candidate not in PARALLEL_POLICIES:
        return "ghost_isolation"
    return candidate


def _effective_parallel_policy(config: PijiangConfig, seats: list[CouncilSeat]) -> str:
    candidate = _normalize_parallel_policy(config.execution_policy.parallel_policy)
    if candidate == "ghost_isolation" and len(seats) >= 10 and council_mode(config) == "standard":
        return "ghost_isolation"
    return "strict_all"


def _quorum_profile(parallel_policy: str) -> str:
    if parallel_policy == "ghost_isolation":
        return STANDARD_QUORUM_PROFILE
    return "strict-all"


def _seat_categories_met(success_seat_ids: set[str]) -> bool:
    return all(
        [
            "controller" in success_seat_ids,
            "planning" in success_seat_ids,
            bool({"search-1", "search-2"} & success_seat_ids),
            bool({"marshal-1", "marshal-2", "marshal-3"} & success_seat_ids),
            bool({"chaos", "skeptic"} & success_seat_ids),
        ]
    )


def _quorum_reached(success_seat_ids: set[str]) -> bool:
    return len(success_seat_ids) >= 6 and _seat_categories_met(success_seat_ids)


class _HeartbeatLoop:
    def __init__(
        self,
        *,
        tracker: "CouncilRunTracker",
        stage: str,
        seat_id: str = "",
        provider_profile: str = "",
        message_prefix: str,
        interval_sec: int | None = None,
    ) -> None:
        self.tracker = tracker
        self.stage = stage
        self.seat_id = seat_id
        self.provider_profile = provider_profile
        self.message_prefix = message_prefix
        self.interval_sec = interval_sec if interval_sec is not None else HEARTBEAT_INTERVAL_SEC
        self._stop = threading.Event()
        self._started = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_sec):
            message = _heartbeat_message(self.message_prefix, self._started)
            self.tracker.touch(message=message, seat_id=self.seat_id)
            self.tracker.emit(
                "heartbeat",
                stage=self.stage,
                seat_id=self.seat_id,
                provider_profile=self.provider_profile,
                message=message,
            )


def _run_overview_markdown(
    *,
    brief_path: Path,
    config: PijiangConfig,
    seats: list[CouncilSeat],
    mode: str,
    run_id: str,
    created_at: str,
) -> str:
    provider_count = len({seat.profile_id for seat in seats})
    seat_lines = "\n".join([f"- `{seat.seat_id}` / {seat.display_name} / profile=`{seat.profile_id}`" for seat in seats])
    return (
        "---\n"
        f"run_id: {run_id}\n"
        "stage: run-overview\n"
        f"created_at: {created_at}\n"
        f"mode: {mode}\n"
        f"seat_count: {len(seats)}\n"
        f"provider_count: {provider_count}\n"
        "---\n\n"
        "# 运行概览\n\n"
        "这不是单模型在扮演多个角色，而是多个真实模型位分别承担不同分析职责。\n\n"
        "## 本次结构\n\n"
        f"- 议题 brief: `{brief_path}`\n"
        f"- 项目前缀: `{config.project_prefix}`\n"
        f"- 议会模式: `{mode}`\n"
        f"- 启用席位数: `{len(seats)}`\n"
        f"- 启用 provider 数: `{provider_count}`\n"
        f"- 预估耗时: `{_estimate_wait_label(seats, provider_count)}`\n\n"
        "## 启用席位\n\n"
        f"{seat_lines}\n"
    )


class CouncilRunTracker:
    def __init__(
        self,
        *,
        run_dir: Path,
        manifest: dict[str, Any],
        seats: list[CouncilSeat],
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.status_path = run_dir / "status.json"
        self.events_path = run_dir / "events.jsonl"
        self.lock = threading.Lock()
        self.progress_callback = progress_callback
        self.state: dict[str, Any] = {
            "run_id": manifest["run_id"],
            "owner_pid": manifest.get("owner_pid", 0),
            "status": "running",
            "stage": "bootstrap",
            "started_at": manifest["started_at"],
            "finished_at": "",
            "council_mode": manifest["council_mode"],
            "seat_statuses": {seat.seat_id: "pending" for seat in seats},
            "completed_seat_count": 0,
            "failed_seat_count": 0,
            "running_seat_ids": [],
            "ghosted_seat_ids": [],
            "late_seat_ids": [],
            "current_seat_id": "",
            "current_message": "等待开始",
            "parallel_policy": manifest.get("parallel_policy", "strict_all"),
            "quorum_profile": manifest.get("quorum_profile", "strict-all"),
            "quorum_ready": False,
            "quorum_reached_at": "",
            "fusion_cutover_ms": 0,
            "updated_at": manifest["started_at"],
            "watcher_enabled": False,
            "watcher_state": "idle",
            "watcher_alert_count": 0,
            "watcher_action_count": 0,
            "watcher_last_message": "",
            "artifacts": {},
        }
        write_json(self.status_path, self.state)

    def _snapshot(self) -> RunProgressSnapshot:
        return RunProgressSnapshot(
            run_id=self.state["run_id"],
            status=self.state["status"],
            stage=self.state["stage"],
            seat_statuses=dict(self.state["seat_statuses"]),
            completed_seat_count=self.state["completed_seat_count"],
            failed_seat_count=self.state["failed_seat_count"],
            current_message=self.state["current_message"],
            running_seat_ids=list(self.state["running_seat_ids"]),
            current_seat_id=self.state["current_seat_id"],
            updated_at=self.state["updated_at"],
            quorum_ready=bool(self.state["quorum_ready"]),
            ghosted_seat_ids=list(self.state["ghosted_seat_ids"]),
            late_seat_ids=list(self.state["late_seat_ids"]),
            parallel_policy=str(self.state["parallel_policy"]),
            watcher_enabled=bool(self.state["watcher_enabled"]),
            watcher_state=str(self.state["watcher_state"]),
            watcher_alert_count=int(self.state["watcher_alert_count"]),
            watcher_action_count=int(self.state["watcher_action_count"]),
            watcher_last_message=str(self.state["watcher_last_message"]),
            artifacts=dict(self.state["artifacts"]),
        )

    def snapshot_payload(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.state)

    def _emit_progress(self, event: dict[str, Any]) -> None:
        if self.progress_callback is not None:
            self.progress_callback(self._snapshot(), event)

    def emit(self, kind: str, *, stage: str = "", seat_id: str = "", provider_profile: str = "", message: str = "") -> None:
        event = {
            "timestamp": utc_now_iso(),
            "kind": kind,
            "stage": stage or self.state["stage"],
            "seat_id": seat_id,
            "provider_profile": provider_profile,
            "message": message,
        }
        with self.lock:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._emit_progress(event)

    def set_stage(self, stage: str, message: str) -> None:
        with self.lock:
            self.state["stage"] = stage
            self.state["current_message"] = message
            self.state["current_seat_id"] = "fusion" if stage == "fusion" else ""
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)
        self.emit("stage-change", stage=stage, message=message)

    def set_seat_status(self, seat_id: str, status: str, message: str = "", provider_profile: str = "") -> None:
        with self.lock:
            self.state["seat_statuses"][seat_id] = status
            self.state["completed_seat_count"] = sum(
                1 for value in self.state["seat_statuses"].values() if value in {"success", "late_result"}
            )
            self.state["failed_seat_count"] = sum(
                1 for value in self.state["seat_statuses"].values() if value == "failed"
            )
            self.state["running_seat_ids"] = [
                current_seat_id
                for current_seat_id, current_status in self.state["seat_statuses"].items()
                if current_status == "running"
            ]
            if status == "ghost_blocked" and seat_id not in self.state["ghosted_seat_ids"]:
                self.state["ghosted_seat_ids"].append(seat_id)
            if status == "late_result" and seat_id not in self.state["late_seat_ids"]:
                self.state["late_seat_ids"].append(seat_id)
            if message:
                self.state["current_message"] = message
            self.state["current_seat_id"] = seat_id if status == "running" else (
                self.state["running_seat_ids"][0] if self.state["running_seat_ids"] else self.state["current_seat_id"]
            )
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)
        self.emit("seat-status", seat_id=seat_id, provider_profile=provider_profile, message=message or status)

    def set_quorum_reached(self, *, cutover_ms: int, message: str) -> None:
        with self.lock:
            self.state["quorum_ready"] = True
            self.state["quorum_reached_at"] = utc_now_iso()
            self.state["fusion_cutover_ms"] = cutover_ms
            self.state["current_message"] = message
            self.state["updated_at"] = self.state["quorum_reached_at"]
            write_json(self.status_path, self.state)
        self.emit("quorum-reached", stage=self.state["stage"], message=message)

    def add_artifact(self, key: str, value: str) -> None:
        with self.lock:
            self.state["artifacts"][key] = value
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)
        self.emit("artifact", message=f"{key} => {value}")

    def touch(self, *, message: str, seat_id: str = "") -> None:
        with self.lock:
            self.state["current_message"] = message
            if seat_id:
                self.state["current_seat_id"] = seat_id
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)

    def set_current_message(self, message: str, *, seat_id: str = "") -> None:
        self.touch(message=message, seat_id=seat_id)

    def update_watcher(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.state["watcher_enabled"] = bool(payload.get("watcher_enabled", self.state["watcher_enabled"]))
            self.state["watcher_state"] = str(payload.get("watcher_state", self.state["watcher_state"]))
            self.state["watcher_alert_count"] = int(payload.get("watcher_alert_count", self.state["watcher_alert_count"]))
            self.state["watcher_action_count"] = int(payload.get("watcher_action_count", self.state["watcher_action_count"]))
            self.state["watcher_last_message"] = str(payload.get("watcher_last_message", self.state["watcher_last_message"]))
            self.state["updated_at"] = utc_now_iso()
            write_json(self.status_path, self.state)

    def complete(self, status: str, message: str) -> None:
        with self.lock:
            self.state["status"] = status
            self.state["stage"] = "completed" if status in {"success", "degraded", "needs-review"} else "failed"
            self.state["finished_at"] = utc_now_iso()
            self.state["current_message"] = message
            self.state["current_seat_id"] = ""
            self.state["running_seat_ids"] = []
            self.state["updated_at"] = self.state["finished_at"]
            write_json(self.status_path, self.state)
        self.emit("run-complete", stage=self.state["stage"], message=message)


@dataclass
class CouncilEngine:
    config: PijiangConfig
    progress_callback: ProgressCallback | None = None

    def _active_seats(self) -> list[CouncilSeat]:
        seats = active_seats(self.config, runnable_only=True)
        return sorted(seats, key=_seat_sort_key)

    def _seat_lane(self, seat: CouncilSeat) -> LaneSpec:
        profile = find_provider(self.config, seat.profile_id)
        if profile is None:
            raise ProviderExecutionError(f"seat {seat.seat_id} references missing profile {seat.profile_id}")
        seat_template = SEAT_LIBRARY.get(seat.seat_id, SEAT_LIBRARY["fusion"])
        special = (
            f"{seat.description}\n"
            f"{seat_template['special']}\n"
            "请明确记住：你承担的是分析职责，不是在扮演角色。最终目标是多模型思路整合。"
        )
        return LaneSpec(
            id=seat.seat_id,
            source_cli=profile.adapter_type,
            family=profile.adapter_type,
            model=profile.model,
            thinking_angle=seat_template["thinking_angle"],
            obsidian_filename=seat_template["filename"],
            special_instructions=special,
        )

    def _prepare_run(self, brief_path: Path, seats: list[CouncilSeat], topic: str) -> tuple[str, Path, Path, dict[str, Any]]:
        created_at = utc_now_iso()
        run_id = f"cpj-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        cache_root = Path(self.config.cache_root).expanduser().resolve()
        run_dir = ensure_directory(cache_root / "runs" / run_id)
        base_root = Path(
            self.config.visualization.vault_path if self.config.visualization.obsidian_enabled else self.config.output_root
        ).expanduser().resolve()
        output_segments = split_project_path(f"{self.config.project_prefix}\\{topic}")
        output_segments.append("方案工厂")
        output_segments.append(run_id)
        output_dir = ensure_directory(base_root.joinpath(*output_segments))
        parallel_policy = _effective_parallel_policy(self.config, seats)
        quorum_profile = _quorum_profile(parallel_policy)
        manifest = {
            "run_id": run_id,
            "owner_pid": os.getpid() if hasattr(os, "getpid") else 0,
            "brief_path": str(brief_path),
            "project_path": topic,
            "started_at": created_at,
            "council_mode": council_mode(self.config),
            "parallel_policy": parallel_policy,
            "quorum_profile": quorum_profile,
            "seat_count": len(seats),
            "active_profile_count": unique_active_profile_count(self.config),
            "obsidian_output_dir": str(output_dir),
            "seats": [
                {
                    "seat_id": seat.seat_id,
                    "seat_type": seat.seat_type,
                    "display_name": seat.display_name,
                    "profile_id": seat.profile_id,
                    "obsidian_filename": self._seat_lane(seat).obsidian_filename,
                }
                for seat in seats
            ],
        }
        write_json(run_dir / "run_manifest.json", manifest)
        return run_id, run_dir, output_dir, manifest

    def _write_lane_result(
        self,
        *,
        lane: LaneSpec,
        seat: CouncilSeat,
        run_id: str,
        created_at: str,
        run_dir: Path,
        output_dir: Path,
        response_content: str,
        raw_stdout: str,
        raw_stderr: str,
        error_summary: str = "",
        status: str = "success",
    ) -> LaneResult:
        lane_run_dir = ensure_directory(run_dir / "seats" / seat.seat_id)
        raw_stdout_path = lane_run_dir / "stdout.log"
        raw_stderr_path = lane_run_dir / "stderr.log"
        raw_output_path = lane_run_dir / "raw-output.txt"
        write_text(raw_stdout_path, raw_stdout)
        write_text(raw_stderr_path, raw_stderr)
        write_text(raw_output_path, response_content)
        markdown = normalize_variant_markdown(response_content, lane=lane, run_id=run_id, created_at=created_at)
        normalized_markdown_path = output_dir / lane.obsidian_filename
        write_text(normalized_markdown_path, markdown)
        sections = parse_variant_sections(response_content)
        variant_result_path = lane_run_dir / "variant_result.json"
        write_json(
            variant_result_path,
            {
                "seat_id": seat.seat_id,
                "seat_type": seat.seat_type,
                "profile_id": seat.profile_id,
                "status": status,
                "error_summary": error_summary,
                "normalized_markdown_path": str(normalized_markdown_path),
            },
        )
        return LaneResult(
            lane=lane,
            status=status,
            started_at=created_at,
            finished_at=utc_now_iso(),
            lane_run_dir=lane_run_dir,
            raw_stdout_path=raw_stdout_path,
            raw_stderr_path=raw_stderr_path,
            raw_output_path=raw_output_path,
            normalized_markdown_path=normalized_markdown_path,
            variant_result_path=variant_result_path,
            error_summary=error_summary,
            sections=sections,
        )

    def _execution_policy(self) -> Any:
        return self.config.execution_policy

    def _execute_seat(
        self,
        *,
        seat: CouncilSeat,
        brief_text: str,
        run_id: str,
        run_dir: Path,
        output_dir: Path,
        tracker: CouncilRunTracker,
        timeout_sec: int,
        cancel_event: threading.Event | None = None,
    ) -> LaneResult:
        created_at = utc_now_iso()
        profile = find_provider(self.config, seat.profile_id)
        if profile is None:
            raise ProviderExecutionError(f"missing profile for seat {seat.seat_id}")
        lane = self._seat_lane(seat)
        seat_run_dir = ensure_directory(run_dir / "seats" / seat.seat_id)
        prompt = build_variant_prompt(brief_text, lane)
        write_text(seat_run_dir / "prompt.txt", prompt)
        policy = self._execution_policy()
        max_attempts = max(1, int(policy.max_attempts_per_seat))
        last_error = "unknown error"
        for attempt in range(1, max_attempts + 1):
            if cancel_event is not None and cancel_event.is_set():
                last_error = "seat quarantined before attempt"
                break
            tracker.set_seat_status(
                seat.seat_id,
                "running",
                message=f"正在生成 {seat.display_name} 产物（第 {attempt} 次尝试）",
                provider_profile=profile.id,
            )
            tracker.emit(
                "seat-attempt-start",
                stage="variants",
                seat_id=seat.seat_id,
                provider_profile=profile.id,
                message=f"{seat.display_name} attempt {attempt} started",
            )
            output_path = seat_run_dir / f"last-message.attempt-{attempt}.txt"
            heartbeat = _HeartbeatLoop(
                tracker=tracker,
                stage="variants",
                seat_id=seat.seat_id,
                provider_profile=profile.id,
                message_prefix=f"{seat.display_name} 正在运行第 {attempt} 次尝试",
            )
            heartbeat.start()
            try:
                response = execute_profile_request(
                    profile,
                    ExecutionRequest(
                        prompt=prompt,
                        output_mode="variant_markdown",
                        timeout_sec=timeout_sec,
                        output_path=output_path,
                    ),
                    cancel_event=cancel_event,
                    worker_dir=seat_run_dir / "worker",
                )
            except Exception as exc:
                heartbeat.stop()
                last_error = str(exc)
                if cancel_event is not None and cancel_event.is_set():
                    last_error = "seat quarantined after quorum cutover"
                    break
                write_text(seat_run_dir / f"stderr.attempt-{attempt}.log", str(exc))
                tracker.emit(
                    "seat-attempt-failure",
                    stage="variants",
                    seat_id=seat.seat_id,
                    provider_profile=profile.id,
                    message=last_error,
                )
                if attempt < max_attempts:
                    time.sleep(_retry_backoff_seconds(policy.retry_backoff_seconds, attempt))
                    continue
                break
            heartbeat.stop()
            raw_stdout = response.raw_stdout or ""
            raw_stderr = response.raw_stderr or ""
            write_text(seat_run_dir / f"stdout.attempt-{attempt}.log", raw_stdout)
            write_text(seat_run_dir / f"stderr.attempt-{attempt}.log", raw_stderr)
            response_content = trim_to_canonical_markdown((response.content or "").strip())
            quality_issue = variant_quality_issue(lane, response_content)
            if quality_issue:
                last_error = f"quality gate failed: {quality_issue}"
                tracker.emit(
                    "seat-attempt-failure",
                    stage="variants",
                    seat_id=seat.seat_id,
                    provider_profile=profile.id,
                    message=last_error,
                )
                if attempt < max_attempts:
                    time.sleep(_retry_backoff_seconds(policy.retry_backoff_seconds, attempt))
                    continue
                break
            result_status = "late_result" if cancel_event is not None and cancel_event.is_set() else "success"
            result = self._write_lane_result(
                lane=lane,
                seat=seat,
                run_id=run_id,
                created_at=created_at,
                run_dir=run_dir,
                output_dir=output_dir,
                response_content=response_content,
                raw_stdout=raw_stdout,
                raw_stderr=raw_stderr,
                status=result_status,
            )
            if result_status == "late_result":
                tracker.set_seat_status(
                    seat.seat_id,
                    "late_result",
                    message=f"{seat.display_name} 在 cutover 后迟到完成",
                    provider_profile=profile.id,
                )
                tracker.emit(
                    "late-lane-arrived",
                    stage="variants",
                    seat_id=seat.seat_id,
                    provider_profile=profile.id,
                    message=f"{seat.display_name} 迟到完成",
                )
            else:
                tracker.set_seat_status(
                    seat.seat_id,
                    "success",
                    message=f"{seat.display_name} 已完成",
                    provider_profile=profile.id,
                )
                tracker.emit(
                    "seat-success",
                    stage="variants",
                    seat_id=seat.seat_id,
                    provider_profile=profile.id,
                    message=f"{seat.display_name} 已完成",
                )
            tracker.add_artifact(seat.seat_id, str(result.normalized_markdown_path))
            return result

        final_status = "ghost_blocked" if cancel_event is not None and cancel_event.is_set() else "failed"
        result = self._write_lane_result(
            lane=lane,
            seat=seat,
            run_id=run_id,
            created_at=created_at,
            run_dir=run_dir,
            output_dir=output_dir,
            response_content=f"# 执行失败\n\n{last_error}",
            raw_stdout="",
            raw_stderr=last_error,
            error_summary=last_error,
            status=final_status,
        )
        if final_status == "ghost_blocked":
            tracker.set_seat_status(
                seat.seat_id,
                "ghost_blocked",
                message=f"{seat.display_name} 已被隔离，不再阻塞融合",
                provider_profile=profile.id,
            )
            tracker.emit(
                "lane-quarantined",
                stage="variants",
                seat_id=seat.seat_id,
                provider_profile=profile.id,
                message=last_error,
            )
        else:
            tracker.set_seat_status(
                seat.seat_id,
                "failed",
                message=f"{seat.display_name} 执行失败",
                provider_profile=profile.id,
            )
            tracker.emit(
                "seat-failure",
                stage="variants",
                seat_id=seat.seat_id,
                provider_profile=profile.id,
                message=last_error,
            )
        return result

    def _fusion_profiles(self) -> list[str]:
        topology = self.config.council_topology
        if topology is None or self.config.workflow is None:
            return []
        order = list(self.config.workflow.fusion_profile_order)
        fusion_seat = next((seat for seat in topology.seats if seat.seat_id == topology.fusion_seat), None)
        if fusion_seat and fusion_seat.profile_id not in order:
            order.insert(0, fusion_seat.profile_id)
        if self.config.workflow.controller_profile_id not in order:
            order.append(self.config.workflow.controller_profile_id)
        return order

    def _execute_fusion(
        self,
        *,
        stage: str,
        prompt: str,
        schema: dict[str, Any] | None,
        run_id: str,
        fusion_dir: Path,
        output_dir: Path,
        tracker: CouncilRunTracker,
        filename: str,
    ) -> tuple[str, str, str]:
        tracker.touch(message=f"正在执行融合步骤 `{stage}`。", seat_id="fusion")
        tracker.emit("fusion-step-start", stage="fusion", message=f"开始执行 {stage}")
        last_error = "no provider attempted"
        output_path = fusion_dir / f"{stage}.last-message.txt"
        for profile_id in self._fusion_profiles():
            profile = find_provider(self.config, profile_id)
            if profile is None or not profile.enabled:
                continue
            adapter = adapter_for_profile(profile)
            heartbeat = _HeartbeatLoop(
                tracker=tracker,
                stage="fusion",
                seat_id="fusion",
                provider_profile=profile.id,
                message_prefix=f"融合步骤 {stage} 正在调用 {profile.id}",
            )
            heartbeat.start()
            try:
                response = adapter.execute(
                    ExecutionRequest(
                        prompt=prompt,
                        output_mode="fusion_json" if schema is not None else "fusion_markdown",
                        schema=schema,
                        timeout_sec=900,
                        output_path=output_path,
                    )
                )
                heartbeat.stop()
                body = response.content.strip()
                if not body:
                    raise ProviderExecutionError(f"{profile.id} returned empty content")
                if schema is None:
                    write_text(
                        output_dir / filename,
                        render_stage_markdown(
                            body=body,
                            run_id=run_id,
                            stage=stage,
                            lane_id="fusion",
                            source_cli=profile.adapter_type,
                            model=profile.model,
                            created_at=utc_now_iso(),
                        ),
                    )
                tracker.emit(
                    "fusion-step-success",
                    stage="fusion",
                    provider_profile=profile.id,
                    message=f"{stage} 已完成",
                )
                tracker.touch(message=f"融合步骤 `{stage}` 已完成。", seat_id="fusion")
                return body, profile.id, profile.model
            except Exception as exc:
                heartbeat.stop()
                last_error = f"{profile.id}: {exc}"
                tracker.emit(
                    "fusion-step-failure",
                    stage="fusion",
                    provider_profile=profile_id,
                    message=str(exc),
                )
        raise ProviderExecutionError(f"fusion step {stage} failed: {last_error}")

    def run(
        self,
        *,
        brief_path: Path,
        topic: str,
        timeout_sec: int = 900,
        max_workers: int = 6,
        watcher_mode: str | None = None,
    ) -> dict[str, Any]:
        recover_abandoned_runs(Path(self.config.cache_root))
        seats = self._active_seats()
        brief_path = brief_path.expanduser().resolve()
        brief_text = brief_path.read_text(encoding="utf-8")
        if len({seat.profile_id for seat in seats}) < 1:
            raise RuntimeError("no enabled provider profiles configured")

        run_id, run_dir, output_dir, manifest = self._prepare_run(brief_path, seats, topic)
        tracker = CouncilRunTracker(run_dir=run_dir, manifest=manifest, seats=seats, progress_callback=self.progress_callback)
        watcher_active = watcher_enabled(watcher_mode or self.config.watcher_policy.cli_mode, task_kind="run")
        watcher_recorder: WatcherRecorder | None = None
        watcher_monitor: WatcherMonitor | None = None
        if watcher_active:
            watcher_policy = self.config.watcher_policy
            watcher_recorder = WatcherRecorder(
                run_dir=run_dir,
                output_dir=output_dir,
                policy=watcher_policy,
                status_updater=tracker.update_watcher,
            )
            watcher_recorder.set_state("watching", "觉者已启用，正在代表用户观察整条任务执行链。")
            watcher_monitor = WatcherMonitor(
                recorder=watcher_recorder,
                status_provider=tracker.snapshot_payload,
                events_path=tracker.events_path,
                target_dir_provider=lambda target_id: run_dir / "seats" / target_id,
                task_label="seat",
                heartbeat_sec=max(1, min(self.config.watcher_policy.seat_stall_threshold_sec, self.config.watcher_policy.stage_silent_threshold_sec, 5)),
            )
            watcher_monitor.start()
        parallel_policy = str(manifest.get("parallel_policy", "strict_all"))
        quorum_profile = str(manifest.get("quorum_profile", "strict-all"))
        tracker.set_stage("brief", "正在写入 brief 与运行概览")
        write_text(output_dir / "00-brief.md", render_brief_markdown(brief_text, run_id=run_id, created_at=manifest["started_at"]))
        write_text(
            output_dir / "01-run-overview.md",
            _run_overview_markdown(
                brief_path=brief_path,
                config=self.config,
                seats=seats,
                mode=manifest["council_mode"],
                run_id=run_id,
                created_at=manifest["started_at"],
            ),
        )
        tracker.add_artifact("brief_markdown", str(output_dir / "00-brief.md"))
        tracker.add_artifact("run_overview", str(output_dir / "01-run-overview.md"))

        tracker.set_stage("variants", f"正在并行生成 {len(seats)} 路议会材料")
        lane_results: list[LaneResult] = []
        success_seat_ids: set[str] = set()
        included_seat_ids: set[str] = set()
        ghosted_seat_ids: list[str] = []
        late_seat_ids: list[str] = []
        quorum_reached = False
        fusion_cutover_ms = 0
        variants_started = time.monotonic()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(seats))))
        future_map: dict[concurrent.futures.Future[LaneResult], CouncilSeat] = {}
        cancel_events: dict[str, threading.Event] = {}
        try:
            pending: set[concurrent.futures.Future[LaneResult]] = set()
            for seat in seats:
                cancel_event = threading.Event()
                cancel_events[seat.seat_id] = cancel_event
                future = executor.submit(
                    self._execute_seat,
                    seat=seat,
                    brief_text=brief_text,
                    run_id=run_id,
                    run_dir=run_dir,
                    output_dir=output_dir,
                    tracker=tracker,
                    timeout_sec=timeout_sec,
                    cancel_event=cancel_event,
                )
                future_map[future] = seat
                pending.add(future)

            while pending:
                done, pending = concurrent.futures.wait(
                    pending,
                    timeout=0.25,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    continue
                for future in done:
                    result = future.result()
                    lane_results.append(result)
                    if result.status == "success":
                        success_seat_ids.add(result.lane.id)
                    elif result.status == "ghost_blocked" and result.lane.id not in ghosted_seat_ids:
                        ghosted_seat_ids.append(result.lane.id)
                    elif result.status == "late_result" and result.lane.id not in late_seat_ids:
                        late_seat_ids.append(result.lane.id)

                if parallel_policy == "ghost_isolation" and not quorum_reached:
                    if _quorum_reached(success_seat_ids):
                        quorum_reached = True
                        included_seat_ids = set(success_seat_ids)
                        fusion_cutover_ms = int((time.monotonic() - variants_started) * 1000)
                        tracker.set_quorum_reached(
                            cutover_ms=fusion_cutover_ms,
                            message=f"已达到 {quorum_profile}，开始隔离幽灵 seat 并进入融合准备。",
                        )
                        for future in list(pending):
                            seat = future_map[future]
                            cancel_events[seat.seat_id].set()
                            tracker.emit(
                                "lane-quarantine-requested",
                                stage="variants",
                                seat_id=seat.seat_id,
                                provider_profile=seat.profile_id,
                                message="quorum_cutover",
                            )
        finally:
            executor.shutdown(wait=True, cancel_futures=False)
        lane_results.sort(key=lambda item: item.lane.obsidian_filename)

        fusion_context = {
            "variant_count": sum(
                1
                for item in lane_results
                if item.status == "success" and (not included_seat_ids or item.lane.id in included_seat_ids)
            ),
            "failed_lanes": [item.lane.id for item in lane_results if item.status == "failed"],
            "ghosted_lanes": sorted(set(ghosted_seat_ids)),
            "late_lanes": sorted(set(late_seat_ids)),
            "variants": [
                {
                    "lane_id": item.lane.id,
                    "source_cli": item.lane.source_cli,
                    "model": item.lane.model,
                    "markdown_path": str(item.normalized_markdown_path),
                    "sections": item.sections,
                }
                for item in lane_results
                if item.status == "success" and (not included_seat_ids or item.lane.id in included_seat_ids)
            ],
        }
        fusion_dir = ensure_directory(run_dir / "fusion")
        write_json(fusion_dir / "fusion_context.json", fusion_context)
        tracker.add_artifact("fusion_context", str(fusion_dir / "fusion_context.json"))
        pipeline_status = "success"
        pipeline_error = ""
        if parallel_policy == "ghost_isolation" and not quorum_reached:
            pipeline_status = "fail"
            pipeline_error = "critical quorum missing after variants"
            write_text(fusion_dir / "critical-quorum.error.txt", pipeline_error + "\n")
            write_text(output_dir / "98-error.md", f"# Fusion Error\n\n阶段：`critical-quorum`\n\n```\n{pipeline_error}\n```\n")
            tracker.emit("quorum-failed", stage="variants", message=pipeline_error)
            tracker.set_current_message("关键 quorum 未满足，已拒绝进入融合。", seat_id="")
            if watcher_recorder is not None:
                watcher_recorder.alert(
                    trigger_code="critical_quorum_missing",
                    stage="variants",
                    target_id="fusion",
                    severity="error",
                    observation="主议会在变体阶段结束后仍未达到法定人数，无法进入合法融合。",
                    recommendation="觉者建议优先检查关键席位是否失败、被隔离或 provider 不可用。",
                    suggested_next_step="查看 ghosted/failed seat 与 preflight 结果，再决定是否重试。",
                )
                watcher_recorder.action(
                    trigger_code="critical_quorum_missing",
                    stage="variants",
                    target_id="fusion",
                    executed_action="finalize_failed_run",
                    result="success",
                    observation=pipeline_error,
                    recommendation="已保留失败收尾，不再继续盲目融合。",
                )
        else:
            tracker.set_stage("fusion", "变体完成，正在开始 idea map 与多轮融合")
            idea_map_text, _, _ = self._execute_fusion(
                stage="idea-map",
                prompt=build_idea_map_prompt(fusion_context),
                schema=None,
                run_id=run_id,
                fusion_dir=fusion_dir,
                output_dir=output_dir,
                tracker=tracker,
                filename="30-idea-map.md",
            )
            debate_round_1_text, _, _ = self._execute_fusion(
                stage="debate-round-1",
                prompt=build_debate_round_prompt(
                    round_index=1,
                    fusion_context=fusion_context,
                    idea_map_text=idea_map_text,
                ),
                schema=None,
                run_id=run_id,
                fusion_dir=fusion_dir,
                output_dir=output_dir,
                tracker=tracker,
                filename="40-debate-round-1.md",
            )
            debate_round_2_text, _, _ = self._execute_fusion(
                stage="debate-round-2",
                prompt=build_debate_round_prompt(
                    round_index=2,
                    fusion_context=fusion_context,
                    idea_map_text=idea_map_text,
                    previous_round_text=debate_round_1_text,
                ),
                schema=None,
                run_id=run_id,
                fusion_dir=fusion_dir,
                output_dir=output_dir,
                tracker=tracker,
                filename="41-debate-round-2.md",
            )
            final_decisions_raw, decisions_profile_id, decisions_model = self._execute_fusion(
                stage="final-decisions",
                prompt=build_final_decisions_prompt(
                    fusion_context,
                    idea_map_text=idea_map_text,
                    debate_round_1_text=debate_round_1_text,
                    debate_round_2_text=debate_round_2_text,
                ),
                schema=FINAL_DECISIONS_SCHEMA,
                run_id=run_id,
                fusion_dir=fusion_dir,
                output_dir=output_dir,
                tracker=tracker,
                filename="50-fusion-decisions.md",
            )
            final_decisions = json.loads(final_decisions_raw)
            write_json(fusion_dir / "final_decisions.json", final_decisions)
            decisions_profile = find_provider(self.config, decisions_profile_id)
            write_text(
                output_dir / "50-fusion-decisions.md",
                render_decisions_markdown(
                    final_decisions,
                    run_id=run_id,
                    created_at=utc_now_iso(),
                    source_cli=decisions_profile.adapter_type if decisions_profile else decisions_profile_id,
                    model=decisions_model,
                ),
            )

            final_draft_raw, draft_profile_id, draft_model = self._execute_fusion(
                stage="final-draft",
                prompt=build_final_draft_prompt(fusion_context, decisions_payload=final_decisions),
                schema=FINAL_DRAFT_SCHEMA,
                run_id=run_id,
                fusion_dir=fusion_dir,
                output_dir=output_dir,
                tracker=tracker,
                filename="90-final-solution-draft.md",
            )
            final_draft = json.loads(final_draft_raw)
            draft_profile = find_provider(self.config, draft_profile_id)
            write_text(
                output_dir / "90-final-solution-draft.md",
                render_final_draft_markdown(
                    final_draft,
                    run_id=run_id,
                    created_at=utc_now_iso(),
                    source_cli=draft_profile.adapter_type if draft_profile else draft_profile_id,
                    model=draft_model,
                ),
            )
        write_text(output_dir / "99-index.md", render_index_markdown(run_id=run_id, created_at=utc_now_iso(), lane_results=lane_results))
        tracker.add_artifact("final_index", str(output_dir / "99-index.md"))
        summary = {
            "run_id": run_id,
            "status": pipeline_status,
            "run_dir": str(run_dir),
            "obsidian_output_dir": str(output_dir),
            "failed_lane_count": sum(1 for result in lane_results if result.status == "failed"),
            "council_mode": manifest["council_mode"],
            "seat_count": len(seats),
            "topic": topic,
            "parallel_policy": parallel_policy,
            "quorum_profile": quorum_profile,
            "quorum_reached": quorum_reached,
            "ghosted_lane_count": len(sorted(set(ghosted_seat_ids))),
            "ghosted_lane_ids": sorted(set(ghosted_seat_ids)),
            "late_result_count": len(sorted(set(late_seat_ids))),
            "late_lane_ids": sorted(set(late_seat_ids)),
            "fusion_cutover_ms": fusion_cutover_ms,
            "watcher_enabled": watcher_active,
            "watcher_status": tracker.state.get("watcher_state", "idle"),
            "watcher_alert_count": int(tracker.state.get("watcher_alert_count", 0)),
            "watcher_action_count": int(tracker.state.get("watcher_action_count", 0)),
        }
        if pipeline_error:
            summary["error"] = pipeline_error
        tracker.complete(
            pipeline_status,
            "议会运行完成，正在执行 truth audit" if pipeline_status == "success" else "议会运行失败，正在执行 truth audit",
        )
        audit = audit_council_run(summary)
        summary["truth_audit_path"] = str(output_dir / "70-run-truth-audit.json")
        summary["fake_success_flag_count"] = len(audit.fake_success_flags)
        summary["regression_case_count"] = len(audit.regression_case_paths)
        summary["audit_status"] = audit.audit_status
        summary["reason_codes"] = audit.reason_codes
        if pipeline_status == "success" and audit.audit_status != "success":
            summary["status"] = audit.audit_status
        tracker.add_artifact("truth_audit", summary["truth_audit_path"])
        tracker.add_artifact("regression_cases_index", str(output_dir / "80-regression-cases-index.md"))
        if watcher_recorder is not None:
            if watcher_monitor is not None:
                watcher_monitor.stop()
            watcher_path = watcher_recorder.finalize(
                expected_artifacts={
                    "brief": output_dir / "00-brief.md",
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
        if summary["status"] != pipeline_status:
            tracker.complete(summary["status"], f"议会运行完成，状态为 {summary['status']}")
        write_json(run_dir / "summary.json", summary)
        return summary
