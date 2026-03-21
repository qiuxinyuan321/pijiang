from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .runtime_support import utc_now_iso, write_json, write_text
from .types import WatcherAction, WatcherAdvice, WatcherAlert, WatcherLedgerEntry, WatcherPolicy


WATCHER_HEARTBEAT_SEC = 5
TERMINAL_RUN_STATUSES = {"success", "degraded", "needs-review", "fail", "failed"}


def watcher_enabled(cli_mode: str | None, *, task_kind: str) -> bool:
    normalized = (cli_mode or "auto").strip().lower()
    if normalized == "on":
        return True
    if normalized == "off":
        return False
    return task_kind == "run"


def _latest_mtime(path: Path | None) -> float:
    if path is None or not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_mtime
    try:
        latest = path.stat().st_mtime
    except OSError:
        return 0.0
    try:
        children = list(path.rglob("*"))
    except OSError:
        return latest
    for child in children:
        try:
            child_mtime = child.stat().st_mtime
        except OSError:
            continue
        if child_mtime > latest:
            latest = child_mtime
    return latest


def _parse_timestamp(value: str) -> float:
    if not value:
        return 0.0
    try:
        return time.mktime(time.strptime(value.replace("Z", ""), "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return 0.0


def _safe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _parse_iso_timestamp(value: str) -> float:
    if not value:
        return 0.0
    try:
        return __import__("datetime").datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _effective_activity_time(*timestamps: float) -> float:
    values = [value for value in timestamps if value > 0]
    return max(values) if values else 0.0


def _judgment_for_severity(severity: str) -> str:
    normalized = severity.strip().lower()
    if normalized == "error":
        return "blocking"
    if normalized == "warning":
        return "suspect"
    return "informational"


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class WatcherRecorder:
    def __init__(
        self,
        *,
        run_dir: Path,
        output_dir: Path,
        policy: WatcherPolicy,
        status_updater: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.output_dir = output_dir
        self.policy = policy
        self.status_updater = status_updater
        self.lock = threading.Lock()
        self.watcher_dir = run_dir / "watcher"
        self.events_path = self.watcher_dir / "watcher-events.jsonl"
        self.alerts_path = self.watcher_dir / "watcher-alerts.json"
        self.actions_path = self.watcher_dir / "watcher-actions.json"
        self.ledger_path = self.watcher_dir / "watcher-ledger.json"
        self.markdown_path = output_dir / "06-juezhe-watch.md"
        self.alerts: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.advices: list[dict[str, Any]] = []
        self.ledger_entries: list[dict[str, Any]] = []
        self.state = {
            "watcher_enabled": bool(policy.enabled),
            "watcher_state": "idle",
            "watcher_alert_count": 0,
            "watcher_action_count": 0,
            "watcher_last_message": "",
        }
        self._sync_files()

    def _emit_event(self, kind: str, **payload: Any) -> None:
        self.watcher_dir.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"timestamp": utc_now_iso(), "kind": kind, **payload}, ensure_ascii=False) + "\n")

    def _sync_files(self) -> None:
        self.watcher_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            self.alerts_path,
            {
                "watcher_enabled": self.state["watcher_enabled"],
                "watcher_state": self.state["watcher_state"],
                "alerts": self.alerts,
                "advices": self.advices,
            },
        )
        write_json(
            self.actions_path,
            {
                "watcher_enabled": self.state["watcher_enabled"],
                "watcher_state": self.state["watcher_state"],
                "actions": self.actions,
            },
        )
        write_json(
            self.ledger_path,
            {
                "watcher_enabled": self.state["watcher_enabled"],
                "watcher_state": self.state["watcher_state"],
                "entries": self.ledger_entries,
            },
        )
        if self.status_updater is not None:
            self.status_updater(dict(self.state))

    def set_state(self, state: str, message: str) -> None:
        with self.lock:
            self.state["watcher_state"] = state
            self.state["watcher_last_message"] = message
            self._emit_event("watcher-heartbeat", state=state, message=message)
            self._sync_files()

    def heartbeat(self, message: str) -> None:
        with self.lock:
            self.state["watcher_state"] = "watching"
            self.state["watcher_last_message"] = message
            self._emit_event("watcher-heartbeat", state="watching", message=message)
            self._sync_files()

    def alert(
        self,
        *,
        trigger_code: str,
        stage: str,
        target_id: str,
        severity: str,
        observation: str,
        recommendation: str,
        suggested_next_step: str = "",
        source_signals: list[str] | None = None,
        evidence: list[str] | None = None,
    ) -> None:
        with self.lock:
            digest = hashlib.sha1(f"{trigger_code}:{stage}:{target_id}:{observation}".encode("utf-8")).hexdigest()[:10]
            judgment = _judgment_for_severity(severity)
            alert = WatcherAlert(
                alert_id=f"watcher-alert-{digest}",
                timestamp=utc_now_iso(),
                trigger_code=trigger_code,
                target_id=target_id,
                stage=stage,
                severity=severity,
                observation=observation,
                recommendation=recommendation,
            )
            advice = WatcherAdvice(
                advice_id=f"watcher-advice-{digest}",
                timestamp=alert.timestamp,
                trigger_code=trigger_code,
                target_id=target_id,
                stage=stage,
                severity=severity,
                observation=observation,
                recommendation=recommendation,
                suggested_next_step=suggested_next_step,
            )
            ledger_entry = WatcherLedgerEntry(
                entry_id=f"watcher-ledger-{digest}",
                timestamp=alert.timestamp,
                trigger_code=trigger_code,
                target_id=target_id,
                stage=stage,
                severity=severity,
                judgment=judgment,
                source_signals=list(source_signals or []),
                evidence=list(evidence or []),
            )
            self.alerts.append(asdict(alert))
            self.advices.append(asdict(advice))
            self.ledger_entries.append(asdict(ledger_entry))
            self.state["watcher_state"] = "alerting"
            self.state["watcher_alert_count"] = len(self.alerts)
            self.state["watcher_last_message"] = recommendation
            self._emit_event("watcher-alert", trigger_code=trigger_code, stage=stage, target_id=target_id, severity=severity, message=observation)
            self._emit_event("watcher-advice", trigger_code=trigger_code, stage=stage, target_id=target_id, severity=severity, message=recommendation)
            self._sync_files()

    def action(
        self,
        *,
        trigger_code: str,
        stage: str,
        target_id: str,
        executed_action: str,
        result: str,
        observation: str = "",
        recommendation: str = "",
    ) -> None:
        with self.lock:
            digest = hashlib.sha1(f"{trigger_code}:{stage}:{target_id}:{executed_action}:{result}".encode("utf-8")).hexdigest()[:10]
            action = WatcherAction(
                action_id=f"watcher-action-{digest}",
                timestamp=utc_now_iso(),
                trigger_code=trigger_code,
                target_id=target_id,
                stage=stage,
                executed_action=executed_action,
                result=result,
                observation=observation,
                recommendation=recommendation,
            )
            self.actions.append(asdict(action))
            for entry in reversed(self.ledger_entries):
                if entry.get("trigger_code") == trigger_code and entry.get("stage") == stage and entry.get("target_id") == target_id:
                    entry["final_action"] = f"{executed_action}:{result}"
                    if recommendation and not entry.get("no_action_reason"):
                        entry["no_action_reason"] = recommendation
                    break
            self.state["watcher_state"] = "repairing" if result == "running" else "watching"
            self.state["watcher_action_count"] = len(self.actions)
            self.state["watcher_last_message"] = recommendation or executed_action
            event_kind = "watcher-repair-success" if result == "success" else "watcher-repair-failed" if result == "failed" else "watcher-action"
            self._emit_event(event_kind, trigger_code=trigger_code, stage=stage, target_id=target_id, executed_action=executed_action, result=result, message=recommendation or observation)
            self._sync_files()

    def finalize(self, *, expected_artifacts: dict[str, Path] | None = None) -> str:
        with self.lock:
            missing: list[str] = []
            if expected_artifacts:
                for label, path in expected_artifacts.items():
                    if not path.exists() or not path.read_text(encoding="utf-8", errors="ignore").strip():
                        missing.append(label)
                if missing:
                    self._emit_event("watcher-escalation", trigger_code="missing_expected_artifact", stage="finalize", target_id="", message=",".join(missing))
                    digest = hashlib.sha1(f"missing_expected_artifact:finalize:{','.join(missing)}".encode("utf-8")).hexdigest()[:10]
                    timestamp = utc_now_iso()
                    self.alerts.append(
                        asdict(
                            WatcherAlert(
                                alert_id=f"watcher-alert-{digest}",
                                timestamp=timestamp,
                                trigger_code="missing_expected_artifact",
                                target_id="",
                                stage="finalize",
                                severity="warning",
                                observation=f"缺少核心工件：{', '.join(missing)}",
                                recommendation="请优先补齐缺失工件，再把本轮 guardian 判断用于后续发布或基线说明。",
                            )
                        )
                    )
                    self.advices.append(
                        asdict(
                            WatcherAdvice(
                                advice_id=f"watcher-advice-{digest}",
                                timestamp=timestamp,
                                trigger_code="missing_expected_artifact",
                                target_id="",
                                stage="finalize",
                                severity="warning",
                                observation=f"缺少核心工件：{', '.join(missing)}",
                                recommendation="请优先补齐缺失工件，再把本轮 guardian 判断用于后续发布或基线说明。",
                                suggested_next_step="检查 output 目录与 run_dir artifacts。",
                            )
                        )
                    )
                    self.ledger_entries.append(
                        asdict(
                            WatcherLedgerEntry(
                                entry_id=f"watcher-ledger-{digest}",
                                timestamp=timestamp,
                                trigger_code="missing_expected_artifact",
                                target_id="",
                                stage="finalize",
                                severity="warning",
                                judgment="suspect",
                                source_signals=["artifact_presence"],
                                evidence=[f"missing:{item}" for item in missing],
                                final_action="no_action",
                                no_action_reason="missing_expected_artifact",
                            )
                        )
                    )
                    self.state["watcher_alert_count"] = len(self.alerts)
            for entry in self.ledger_entries:
                if entry.get("final_action") == "pending":
                    entry["final_action"] = "no_action"
                    if not entry.get("no_action_reason"):
                        entry["no_action_reason"] = "guardian_precision_not_validated_yet"
            lines = [
                "# 觉者守护记录",
                "",
                f"- 已启用：{'是' if self.state['watcher_enabled'] else '否'}",
                f"- 当前状态：`{self.state['watcher_state']}`",
                f"- 告警次数：`{self.state['watcher_alert_count']}`",
                f"- 自动动作次数：`{self.state['watcher_action_count']}`",
                f"- 最后消息：{self.state['watcher_last_message'] or '无'}",
                "",
            ]
            if self.alerts:
                lines.append("## 触发过的异常")
                for item in self.alerts:
                    lines.append(f"- `{item['trigger_code']}` / stage=`{item['stage']}` / target=`{item['target_id'] or '-'}`")
                    lines.append(f"  观察：{item['observation']}")
                    lines.append(f"  建议：{item['recommendation']}")
                lines.append("")
            if self.ledger_entries:
                lines.append("## Guardian Ledger")
                for item in self.ledger_entries:
                    lines.append(
                        f"- `{item['trigger_code']}` / judgment=`{item['judgment']}` / severity=`{item['severity']}` / action=`{item['final_action']}` / target=`{item['target_id'] or '-'}`"
                    )
                    if item.get("source_signals"):
                        lines.append(f"  signals：{', '.join(item['source_signals'])}")
                    if item.get("evidence"):
                        lines.append(f"  evidence：{'; '.join(item['evidence'])}")
                    if item.get("no_action_reason"):
                        lines.append(f"  no_action_reason：{item['no_action_reason']}")
                lines.append("")
            if self.actions:
                lines.append("## 执行过的自动修复")
                for item in self.actions:
                    lines.append(f"- `{item['executed_action']}` / result=`{item['result']}` / trigger=`{item['trigger_code']}` / target=`{item['target_id'] or '-'}`")
                lines.append("")
            if missing:
                lines.append("## 仍需关注")
                for item in missing:
                    lines.append(f"- 缺少核心工件：`{item}`")
                lines.append("")
            write_text(self.markdown_path, "\n".join(lines).rstrip() + "\n")
            self.state["watcher_state"] = "completed"
            self.state["watcher_last_message"] = f"觉者已完成收尾，保留 {len(self.alerts)} 条告警与 {len(self.actions)} 次动作。"
            self._sync_files()
            return str(self.markdown_path)


class WatcherMonitor:
    def __init__(
        self,
        *,
        recorder: WatcherRecorder,
        status_provider: Callable[[], dict[str, Any]],
        events_path: Path,
        target_dir_provider: Callable[[str], Path | None],
        task_label: str,
        heartbeat_sec: int = WATCHER_HEARTBEAT_SEC,
    ) -> None:
        self.recorder = recorder
        self.status_provider = status_provider
        self.events_path = events_path
        self.target_dir_provider = target_dir_provider
        self.task_label = task_label
        self.heartbeat_sec = heartbeat_sec
        self._stop = threading.Event()
        self._alerts_seen: set[tuple[str, str]] = set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        manifest = _safe_read_json(self.recorder.run_dir / "run_manifest.json")
        items = manifest.get("seats") or manifest.get("lanes") or []
        self._target_meta = {
            str(item.get("seat_id") or item.get("id") or "").strip(): dict(item)
            for item in items
            if str(item.get("seat_id") or item.get("id") or "").strip()
        }

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self.heartbeat_sec):
            snapshot = self.status_provider()
            status = str(snapshot.get("status", "")).strip()
            stage = str(snapshot.get("stage", "")).strip()
            now = time.time()
            event_mtime = _latest_mtime(self.events_path)
            status_updated_at = _parse_iso_timestamp(str(snapshot.get("updated_at", "")))
            if status in TERMINAL_RUN_STATUSES:
                return
            self.recorder.heartbeat(f"觉者正在观察 `{stage or 'unknown'}` 阶段。")
            stage_activity_time = _effective_activity_time(event_mtime, status_updated_at)
            if stage_activity_time and now - stage_activity_time >= self.recorder.policy.stage_silent_threshold_sec:
                key = ("stage_silent", stage)
                if key not in self._alerts_seen:
                    self._alerts_seen.add(key)
                    self.recorder.alert(
                        trigger_code="stage_silent",
                        stage=stage,
                        target_id="",
                        severity="warning",
                        observation=f"阶段 `{stage}` 已超过 {self.recorder.policy.stage_silent_threshold_sec}s 无新事件。",
                        recommendation="请检查当前阶段是否卡顿、provider 是否悬挂，必要时执行有限重试或清理悬挂子进程。",
                        suggested_next_step="优先检查 events.jsonl、status.json 和当前运行 seat 的输出目录。",
                        source_signals=["events_mtime", "status_updated_at"],
                        evidence=[
                            f"events_age_sec={int(now - event_mtime) if event_mtime else -1}",
                            f"status_age_sec={int(now - status_updated_at) if status_updated_at else -1}",
                        ],
                    )
            running_ids = list(snapshot.get("running_seat_ids") or [])
            if not running_ids:
                seat_statuses = snapshot.get("seat_statuses") or snapshot.get("lane_statuses") or {}
                running_ids = [item_id for item_id, item_status in seat_statuses.items() if item_status == "running"]
            for target_id in running_ids:
                target_dir = self.target_dir_provider(target_id)
                target_activity = _latest_mtime(target_dir)
                activity_time = _effective_activity_time(target_activity, event_mtime, status_updated_at)
                if activity_time and now - activity_time >= self.recorder.policy.seat_stall_threshold_sec:
                    key = ("seat_stalled", target_id)
                    if key in self._alerts_seen:
                        continue
                    self._alerts_seen.add(key)
                    meta = self._target_meta.get(target_id, {})
                    self.recorder.alert(
                        trigger_code="seat_stalled",
                        stage=stage,
                        target_id=target_id,
                        severity="warning",
                        observation=f"{self.task_label} `{target_id}` 已超过 {self.recorder.policy.seat_stall_threshold_sec}s 无新输出增长。",
                        recommendation="觉者建议优先检查该目标是否真实卡顿，再决定是否进行一次有限自动修复。",
                        suggested_next_step=f"查看 `{target_id}` 的 stdout/stderr/last-message 是否仍在增长。",
                        source_signals=["target_dir_mtime", "events_mtime", "status_updated_at"],
                        evidence=[
                            f"seat_type={meta.get('seat_type', '')}",
                            f"family={meta.get('family', '')}",
                            f"target_age_sec={int(now - target_activity) if target_activity else -1}",
                            f"events_age_sec={int(now - event_mtime) if event_mtime else -1}",
                            f"status_age_sec={int(now - status_updated_at) if status_updated_at else -1}",
                        ],
                    )


def recover_abandoned_runs(cache_root: Path) -> list[str]:
    recovered: list[str] = []
    runs_root = cache_root.expanduser().resolve() / "runs"
    if not runs_root.exists():
        return recovered
    for run_dir in sorted((path for path in runs_root.iterdir() if path.is_dir()), key=lambda item: item.stat().st_mtime, reverse=True)[:12]:
        status_path = run_dir / "status.json"
        manifest_path = run_dir / "run_manifest.json"
        status_payload = _safe_read_json(status_path)
        manifest = _safe_read_json(manifest_path)
        if status_payload.get("status") != "running":
            continue
        owner_pid = int(status_payload.get("owner_pid") or manifest.get("owner_pid") or 0)
        if owner_pid and _process_alive(owner_pid):
            continue
        output_dir = Path(str(manifest.get("obsidian_output_dir") or run_dir)).expanduser().resolve()
        watcher_dir = run_dir / "watcher"
        watcher_dir.mkdir(parents=True, exist_ok=True)
        finished_at = utc_now_iso()
        status_payload["status"] = "failed"
        status_payload["stage"] = "failed"
        status_payload["finished_at"] = finished_at
        status_payload["updated_at"] = finished_at
        status_payload["current_message"] = "觉者检测到上次运行已中断，已执行收尾修复。"
        status_payload["watcher_enabled"] = True
        status_payload["watcher_state"] = "recovered"
        status_payload["watcher_alert_count"] = int(status_payload.get("watcher_alert_count", 0)) + 1
        status_payload["watcher_action_count"] = int(status_payload.get("watcher_action_count", 0)) + 1
        status_payload["watcher_last_message"] = "觉者已代为收尾上次中断运行。"
        write_json(status_path, status_payload)
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"timestamp": finished_at, "kind": "watcher-alert", "stage": "recovery", "seat_id": "", "provider_profile": "", "message": "run_interrupted"}, ensure_ascii=False) + "\n")
            handle.write(json.dumps({"timestamp": finished_at, "kind": "watcher-action", "stage": "recovery", "seat_id": "", "provider_profile": "", "message": "finalize_failed_run"}, ensure_ascii=False) + "\n")
        write_json(
            watcher_dir / "watcher-alerts.json",
            {
                "watcher_enabled": True,
                "watcher_state": "recovered",
                "alerts": [
                    {
                        "trigger_code": "run_interrupted",
                        "stage": "recovery",
                        "target_id": "",
                        "severity": "warning",
                        "observation": "觉者检测到上次运行进程已消失，但状态仍停在 running。",
                        "recommendation": "已自动补写失败收尾，请重新发起一次真实运行。",
                        "user_proxy": True,
                    }
                ],
                "advices": [],
            },
        )
        write_json(
            watcher_dir / "watcher-actions.json",
            {
                "watcher_enabled": True,
                "watcher_state": "recovered",
                "actions": [
                    {
                        "trigger_code": "run_interrupted",
                        "stage": "recovery",
                        "target_id": "",
                        "executed_action": "finalize_failed_run",
                        "result": "success",
                        "user_proxy": True,
                    }
                ],
            },
        )
        write_text(
            output_dir / "06-juezhe-watch.md",
            "# 觉者守护记录\n\n- 已启用：是\n- 当前状态：`recovered`\n- 告警次数：`1`\n- 自动动作次数：`1`\n- 最后消息：觉者检测到上次运行被外部中断，已代为收尾。\n\n## 触发过的异常\n- `run_interrupted` / stage=`recovery`\n  观察：上次运行进程已消失，但状态仍停在 running。\n  建议：请重新发起一次真实运行。\n\n## 执行过的自动修复\n- `finalize_failed_run` / result=`success` / trigger=`run_interrupted` / target=`-`\n",
        )
        if not (output_dir / "98-error.md").exists():
            write_text(output_dir / "98-error.md", "# 运行失败\n\n```\n觉者检测到上次运行已被外部中断，已自动补写失败收尾。\n```\n")
        recovered.append(str(run_dir))
    return recovered
