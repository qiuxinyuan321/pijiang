"""Tests for v0.4 improvements: JSON extraction, HTTP retry, run inspect, and
provider presets."""

from __future__ import annotations

import json
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from pijiang.cli.main import _auto_fix_configured_providers, main
from pijiang.factory.analysis import audit_council_run
from pijiang.factory.config import build_default_config, load_config, save_config
from pijiang.factory.presets import PROVIDER_PRESETS, get_preset, list_presets
from pijiang.factory.providers import (
    RETRIABLE_HTTP_STATUSES,
    OpenAICompatibleAdapter,
    ProviderExecutionError,
    _extract_json_block,
    _parse_retry_after,
)
from pijiang.factory.run_inspect import (
    find_run_by_id,
    list_run_artifacts,
    list_run_summaries,
    load_run_summary,
)
from pijiang.factory.types import ExecutionRequest, ProviderProfile, WatcherPolicy
from pijiang.factory.watcher import WatcherRecorder

# ---------------------------------------------------------------------------
# E1: _extract_json_block robustness
# ---------------------------------------------------------------------------


def test_extract_json_block_parses_plain_json() -> None:
    assert _extract_json_block('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}


def test_extract_json_block_strips_fenced_code() -> None:
    payload = '```json\n{"a": 1}\n```'
    assert _extract_json_block(payload) == {"a": 1}


def test_extract_json_block_prefers_last_fenced_block() -> None:
    payload = '```json\n{"stale": true}\n```\n\n```json\n{"final": 2}\n```'
    assert _extract_json_block(payload) == {"final": 2}


def test_extract_json_block_handles_prose_before_json() -> None:
    payload = "好的，下面是结果：\n\n```json\n{\"result\": \"ok\"}\n```\n\n希望有用。"
    assert _extract_json_block(payload) == {"result": "ok"}


def test_extract_json_block_handles_trailing_prose_after_object() -> None:
    payload = 'Here you go:\n{"final": 7}\nLet me know if you need more.'
    assert _extract_json_block(payload) == {"final": 7}


def test_extract_json_block_scans_for_balanced_braces() -> None:
    payload = 'prefix {\"temperature\": 0.5} placeholder\nResult:\n{\"answer\": 42}\ntail'
    # widest slice starts at first `{`, ends at last `}` — the scanner
    # should fall back to the first balanced object.
    result = _extract_json_block(payload)
    assert isinstance(result, dict)
    # Either candidate is acceptable as long as we got a valid parse.
    assert result in ({"temperature": 0.5}, {"answer": 42})


def test_extract_json_block_raises_on_empty_input() -> None:
    with pytest.raises(json.JSONDecodeError):
        _extract_json_block("")


# ---------------------------------------------------------------------------
# E2: HTTP retry helper
# ---------------------------------------------------------------------------


def test_parse_retry_after_accepts_plain_seconds() -> None:
    assert _parse_retry_after("5") == 5.0


def test_parse_retry_after_rejects_nonsense() -> None:
    assert _parse_retry_after("later") is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("-1") is None


def test_parse_retry_after_caps_at_30_seconds() -> None:
    assert _parse_retry_after("999") == 30.0


def test_retriable_statuses_include_429_and_5xx() -> None:
    assert 429 in RETRIABLE_HTTP_STATUSES
    assert 502 in RETRIABLE_HTTP_STATUSES
    assert 503 in RETRIABLE_HTTP_STATUSES
    assert 504 in RETRIABLE_HTTP_STATUSES
    assert 408 in RETRIABLE_HTTP_STATUSES
    # Client errors that shouldn't auto-retry:
    assert 400 not in RETRIABLE_HTTP_STATUSES
    assert 401 not in RETRIABLE_HTTP_STATUSES


@contextmanager
def flaky_server(*, fail_count: int, fail_status: int = 503):
    """An HTTP server that returns `fail_status` for the first `fail_count`
    requests, then 200 with a valid OpenAI-shaped payload."""
    state = {"count": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            state["count"] += 1
            if state["count"] <= fail_count:
                self.send_response(fail_status)
                self.send_header("Retry-After", "0")
                self.end_headers()
                return
            body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], state
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_http_retry_recovers_after_503(monkeypatch: pytest.MonkeyPatch) -> None:
    # Don't actually sleep between retries; the test should finish fast.
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    with flaky_server(fail_count=1) as (port, state):
        profile = ProviderProfile(
            id="flaky",
            adapter_type="openai_compatible",
            model="mock",
            roles=["controller"],
            base_url=f"http://127.0.0.1:{port}",
            api_key_env="",
            config_status="configured",
        )
        adapter = OpenAICompatibleAdapter(profile=profile)
        response = adapter.execute(ExecutionRequest(prompt="hi", output_mode="text", timeout_sec=5))
    assert response.content == "ok"
    # One failure + one success.
    assert state["count"] == 2


def test_http_retry_gives_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    from pijiang.factory.providers import ProviderExecutionError

    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    with flaky_server(fail_count=10) as (port, state):
        profile = ProviderProfile(
            id="always-503",
            adapter_type="openai_compatible",
            model="mock",
            roles=["controller"],
            base_url=f"http://127.0.0.1:{port}",
            api_key_env="",
            config_status="configured",
        )
        adapter = OpenAICompatibleAdapter(profile=profile)
        with pytest.raises(ProviderExecutionError):
            adapter.execute(ExecutionRequest(prompt="hi", output_mode="text", timeout_sec=5))
    # Initial attempt + 2 retries = 3 total requests with the default config.
    assert state["count"] == 3


def test_http_retry_does_not_retry_client_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    class Handler(BaseHTTPRequestHandler):
        hits = 0

        def do_POST(self) -> None:
            Handler.hits += 1
            self.send_response(400)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = ProviderProfile(
            id="bad-request",
            adapter_type="openai_compatible",
            model="mock",
            roles=["controller"],
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
            api_key_env="",
            config_status="configured",
        )
        adapter = OpenAICompatibleAdapter(profile=profile)
        with pytest.raises(ProviderExecutionError):
            adapter.execute(ExecutionRequest(prompt="hi", output_mode="text", timeout_sec=5))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    # Single request — no retry for 400.
    assert Handler.hits == 1


def test_http_retry_recovers_after_partial_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    class Handler(BaseHTTPRequestHandler):
        hits = 0

        def do_POST(self) -> None:
            Handler.hits += 1
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            if Handler.hits == 1:
                body = b'{"choices":'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body) + 128))
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
                self.connection.close()
                return
            body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = ProviderProfile(
            id="partial-read",
            adapter_type="openai_compatible",
            model="mock",
            roles=["controller"],
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
            api_key_env="",
            config_status="configured",
        )
        adapter = OpenAICompatibleAdapter(profile=profile)
        response = adapter.execute(ExecutionRequest(prompt="hi", output_mode="text", timeout_sec=5))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    assert response.content == "ok"
    assert Handler.hits == 2


def test_http_invalid_json_is_observable_provider_error() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = b"not-json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = ProviderProfile(
            id="invalid-json",
            adapter_type="openai_compatible",
            model="mock",
            roles=["controller"],
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
            api_key_env="",
            config_status="configured",
        )
        adapter = OpenAICompatibleAdapter(profile=profile)
        with pytest.raises(ProviderExecutionError, match="invalid JSON"):
            adapter.execute(ExecutionRequest(prompt="hi", output_mode="text", timeout_sec=5))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


# ---------------------------------------------------------------------------
# E3: `cpj run` only writes back on first success
# (covered indirectly by existing cpj run tests; sanity-check flag semantics)
# ---------------------------------------------------------------------------


def test_run_first_acknowledge_flag_semantics(tmp_path: Path) -> None:
    """The existing run test already flips the flag; this verifies the flag
    itself defaults to False before any run, so the guard kicks in exactly
    once."""
    config = build_default_config(
        workspace_root=tmp_path / "workspace",
        vault_path=tmp_path / "vault",
    )
    assert config.onboarding.first_run_acknowledged is False
    config.onboarding.first_run_acknowledged = True
    config_path = save_config(config, tmp_path / "config.json")
    loaded = load_config(config_path)
    assert loaded.onboarding.first_run_acknowledged is True


# ---------------------------------------------------------------------------
# C1 / C2: cpj runs, cpj show
# ---------------------------------------------------------------------------


def test_list_run_summaries_returns_empty_when_no_cache(tmp_path: Path) -> None:
    assert list_run_summaries(tmp_path / "missing") == []


def _write_fake_run(cache_root: Path, run_id: str, *, topic: str, started_at: str) -> Path:
    run_dir = cache_root / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "project_path": topic,
                "started_at": started_at,
                "council_mode": "standard11",
                "seat_count": 11,
                "obsidian_output_dir": str(cache_root / "output" / run_id),
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps(
            {
                "status": "success",
                "stage": "completed",
                "finished_at": started_at,
                "completed_seat_count": 11,
                "failed_seat_count": 0,
            }
        ),
        encoding="utf-8",
    )
    output_dir = cache_root / "output" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "70-run-truth-audit.json").write_text(
        json.dumps(
            {
                "audit_status": "success",
                "reason_codes": ["quorum_fusion"],
                "fake_success_flags": [],
                "regression_case_paths": [],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "90-final-solution-draft.md").write_text("# Final", encoding="utf-8")
    return run_dir


def test_list_run_summaries_reads_manifest_and_audit(tmp_path: Path) -> None:
    _write_fake_run(tmp_path, "cpj-20260101-000000", topic="t1", started_at="2026-01-01T00:00:00Z")
    _write_fake_run(tmp_path, "cpj-20260102-000000", topic="t2", started_at="2026-01-02T00:00:00Z")
    summaries = list_run_summaries(tmp_path)
    assert [item.run_id for item in summaries] == [
        "cpj-20260102-000000",
        "cpj-20260101-000000",
    ]
    assert summaries[0].audit_status == "success"
    assert summaries[0].seat_count == 11
    assert summaries[0].topic == "t2"


def test_list_run_summaries_scans_demo_subdir(tmp_path: Path) -> None:
    _write_fake_run(tmp_path / "demo", "cpj-demo-0", topic="demo-topic", started_at="2026-01-03T00:00:00Z")
    summaries = list_run_summaries(tmp_path)
    assert len(summaries) == 1
    assert summaries[0].run_id == "cpj-demo-0"


def test_list_run_summaries_respects_limit(tmp_path: Path) -> None:
    for idx in range(5):
        _write_fake_run(
            tmp_path,
            f"cpj-2026010{idx}-000000",
            topic=f"t{idx}",
            started_at=f"2026-01-0{idx}T00:00:00Z",
        )
    summaries = list_run_summaries(tmp_path, limit=2)
    assert len(summaries) == 2


def test_find_run_by_id_supports_unique_prefix(tmp_path: Path) -> None:
    _write_fake_run(tmp_path, "cpj-20260101-000000", topic="t1", started_at="2026-01-01T00:00:00Z")
    found = find_run_by_id(tmp_path, "20260101")
    assert found is not None
    assert found.run_id == "cpj-20260101-000000"


def test_find_run_by_id_ambiguous_prefix_returns_none(tmp_path: Path) -> None:
    _write_fake_run(tmp_path, "cpj-20260101-000000", topic="t1", started_at="2026-01-01T00:00:00Z")
    _write_fake_run(tmp_path, "cpj-20260101-111111", topic="t2", started_at="2026-01-01T11:11:11Z")
    assert find_run_by_id(tmp_path, "20260101") is None


def test_list_run_artifacts_marks_missing_files(tmp_path: Path) -> None:
    run_dir = _write_fake_run(
        tmp_path,
        "cpj-20260101-000000",
        topic="t",
        started_at="2026-01-01T00:00:00Z",
    )
    summary = load_run_summary(run_dir)
    assert summary is not None
    artifacts = list_run_artifacts(summary)
    by_file = {item.relative_path: item for item in artifacts}
    assert by_file["90-final-solution-draft.md"].exists is True
    assert by_file["70-run-truth-audit.json"].exists is True
    # We didn't write a brief in the fake run — should be flagged as missing.
    assert by_file["00-brief.md"].exists is False


# ---------------------------------------------------------------------------
# C3: doctor --fix
# ---------------------------------------------------------------------------


def test_auto_fix_promotes_providers_when_env_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = build_default_config(
        workspace_root=tmp_path / "workspace",
        vault_path=tmp_path / "vault",
    )
    openai = next(p for p in config.provider_profiles if p.api_key_env == "OPENAI_API_KEY")
    assert openai.config_status == "needs_setup"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    changes = _auto_fix_configured_providers(config)
    changed_ids = {item[0] for item in changes}
    assert openai.id in changed_ids
    assert openai.config_status == "configured"


def test_auto_fix_leaves_opencode_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencode adapters depend on a command on disk, not env vars; --fix
    should not touch them even if related env happens to be set."""
    config = build_default_config(
        workspace_root=tmp_path / "workspace",
        vault_path=tmp_path / "vault",
    )
    opencode = next(p for p in config.provider_profiles if p.adapter_type == "opencode")
    # Manufacture an env var and see if --fix wrongly uses it.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _auto_fix_configured_providers(config)
    assert opencode.config_status == "needs_setup"


def test_doctor_fix_via_cli_saves_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Build a config and point HOME at tmp_path so default paths are writable.
    monkeypatch.setenv("PIJIANG_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = build_default_config(
        workspace_root=tmp_path / "workspace",
        vault_path=tmp_path / "vault",
    )
    config_path = save_config(config, tmp_path / "config.json")

    code = main(["doctor", "--fix", "--config", str(config_path), "--json"])
    # Doctor exits non-zero while other blockers remain; --fix just promoted
    # the env-backed providers, other HTTP providers still need keys.
    assert code in {0, 2}

    reloaded = load_config(config_path)
    openai = next(p for p in reloaded.provider_profiles if p.api_key_env == "OPENAI_API_KEY")
    assert openai.config_status == "configured"

    captured = capsys.readouterr()
    assert "auto_fixes_applied" in captured.out


# ---------------------------------------------------------------------------
# C4: provider presets + config add-provider
# ---------------------------------------------------------------------------


def test_preset_catalogue_has_expected_entries() -> None:
    ids = {preset.preset_id for preset in list_presets()}
    assert {
        "openai",
        "openai-compatible",
        "alibaba-coding-plan",
        "volcengine-coding-plan",
        "ollama-local",
        "openrouter",
        "fushengyunsuan",
        "siliconflow",
        "deepseek",
    }.issubset(ids)


def test_build_profile_sets_needs_setup_and_capabilities() -> None:
    preset = get_preset("openai")
    assert preset is not None
    profile = preset.build_profile()
    assert profile.config_status == "needs_setup"
    assert profile.adapter_type == "openai_compatible"
    assert profile.capabilities.supports_structured_json is True
    assert profile.api_key_env == "OPENAI_API_KEY"


def test_config_add_provider_appends_profile(tmp_path: Path) -> None:
    config = build_default_config(
        workspace_root=tmp_path / "workspace",
        vault_path=tmp_path / "vault",
    )
    config_path = save_config(config, tmp_path / "config.json")
    before_ids = {p.id for p in config.provider_profiles}

    code = main([
        "config",
        "add-provider",
        "openai-compatible",
        "--config",
        str(config_path),
        "--id",
        "custom-relay",
        "--relay-url",
        "https://my-relay.example.com/v1",
        "--model",
        "custom-model",
        "--json",
    ])
    assert code == 0

    reloaded = load_config(config_path)
    new_ids = {p.id for p in reloaded.provider_profiles}
    assert "custom-relay" in new_ids and "custom-relay" not in before_ids
    added = next(p for p in reloaded.provider_profiles if p.id == "custom-relay")
    assert added.relay_url == "https://my-relay.example.com/v1"
    assert added.model == "custom-model"


def test_config_add_provider_rejects_duplicate_without_force(tmp_path: Path) -> None:
    config = build_default_config(
        workspace_root=tmp_path / "workspace",
        vault_path=tmp_path / "vault",
    )
    config_path = save_config(config, tmp_path / "config.json")
    # Add once.
    assert (
        main([
            "config",
            "add-provider",
            "ollama-local",
            "--config",
            str(config_path),
            "--id",
            "dup",
            "--json",
        ])
        == 0
    )
    # Second time without --force should fail.
    code = main([
        "config",
        "add-provider",
        "ollama-local",
        "--config",
        str(config_path),
        "--id",
        "dup",
        "--json",
    ])
    assert code != 0


def test_get_preset_returns_none_for_unknown() -> None:
    assert get_preset("definitely-not-a-real-preset") is None
    # Sanity: the static catalogue is what list_presets reads.
    assert set(PROVIDER_PRESETS.keys()) == {p.preset_id for p in list_presets()}


def test_load_config_normalizes_legacy_provider_payload(tmp_path: Path) -> None:
    config_path = tmp_path / "legacy.json"
    config_path.write_text(
        json.dumps(
            {
                "version": "v6",
                "workspace_root": str(tmp_path / "workspace"),
                "providers": [
                    {
                        "id": "legacy-relay",
                        "model": "legacy-model",
                        "roles": ["controller"],
                        "relay_url": "https://relay.example.com/v1",
                        "api_key_env": "LEGACY_KEY",
                        "capabilities": {"transport": "openai-compatible", "ignored_future_field": True},
                        "unknown_profile_field": "ignored",
                    }
                ],
                "obsidian": {"enabled": True, "path": str(tmp_path / "vault")},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loaded = load_config(config_path)
    provider = loaded.provider_profiles[0]
    assert provider.adapter_type == "openai_compatible"
    assert provider.base_url == "https://relay.example.com/v1"
    assert loaded.visualization.vault_path == str(tmp_path / "vault")
    saved_path = save_config(loaded, config_path)
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert "providers" not in saved
    assert "obsidian" not in saved
    assert "provider_profiles" in saved


def test_watcher_deduplicates_repeated_alerts_and_missing_labels(tmp_path: Path) -> None:
    recorder = WatcherRecorder(
        run_dir=tmp_path / "run",
        output_dir=tmp_path / "out",
        policy=WatcherPolicy(enabled=True),
    )
    for _ in range(3):
        recorder.alert(
            trigger_code="seat_stalled",
            stage="variant",
            target_id="controller",
            severity="warning",
            observation="controller has not updated",
            recommendation="wait and inspect",
            source_signals=["status_stale"],
            evidence=["status:running"],
        )
    missing_path = tmp_path / "out" / "Missing.MD"
    recorder.finalize(expected_artifacts={"Final_Decisions": missing_path, "final_decisions": missing_path})
    ledger = json.loads((tmp_path / "run" / "watcher" / "watcher-ledger.json").read_text(encoding="utf-8"))
    seat_entries = [item for item in ledger["entries"] if item["trigger_code"] == "seat_stalled"]
    missing_entries = [item for item in ledger["entries"] if item["trigger_code"] == "missing_expected_artifact"]
    assert len(seat_entries) == 1
    assert seat_entries[0]["merged_count"] == 3
    assert len(missing_entries) == 1
    assert missing_entries[0]["evidence"] == ["missing:final_decisions"]


def test_truth_audit_does_not_count_fusion_as_regular_seat(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    output_dir = tmp_path / "output"
    brief_path = tmp_path / "brief.md"
    seat_dir = run_dir / "seats" / "controller"
    fusion_dir = run_dir / "fusion"
    seat_dir.mkdir(parents=True)
    fusion_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    brief_path.write_text("# Brief\n\n测试 fusion audit。", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "audit-fusion",
                "brief_path": str(brief_path),
                "requested_lane_profile": "single",
                "effective_lane_profile": "single",
                "seats": [
                    {"seat_id": "controller", "seat_type": "controller", "obsidian_filename": "10-controller.md"},
                    {"seat_id": "fusion", "seat_type": "fusion", "obsidian_filename": "20-fusion.md"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps({"status": "success", "seat_statuses": {"controller": "success", "fusion": "success"}}),
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    (fusion_dir / "fusion_context.json").write_text("{}", encoding="utf-8")
    (seat_dir / "variant_result.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    controller_md = "\n\n".join(
        f"# {heading}\n内容 {heading} https://example.com/{index}"
        for index, heading in enumerate(
            [
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
        )
    )
    (output_dir / "10-controller.md").write_text(controller_md, encoding="utf-8")
    for filename in ["30-idea-map.md", "40-debate-round-1.md", "41-debate-round-2.md"]:
        (output_dir / filename).write_text("# ok\n内容", encoding="utf-8")
    (output_dir / "50-fusion-decisions.md").write_text("# 决策账本\n内容", encoding="utf-8")
    (output_dir / "90-final-solution-draft.md").write_text("# 终版\n内容", encoding="utf-8")
    audit = audit_council_run(
        {
            "run_id": "audit-fusion",
            "run_dir": str(run_dir),
            "obsidian_output_dir": str(output_dir),
            "status": "success",
        }
    )
    assert audit.seat_integrity_score == 100
    assert "topology_mismatch" not in audit.reason_codes
    assert "timeout_partial_only" not in audit.reason_codes
