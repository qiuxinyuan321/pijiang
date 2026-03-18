from __future__ import annotations

import json
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pijiang.cli.main import main
from pijiang.factory.config import build_default_config, load_config, save_config
from pijiang.factory.endpoints import build_chat_endpoint, resolve_provider_base_url
from pijiang.factory.providers import OllamaAdapter, OpenAICompatibleAdapter
from pijiang.factory.readiness import build_readiness_report
from pijiang.factory.types import ExecutionRequest, ProviderProfile


@contextmanager
def recording_server(response_shape: str):
    records: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            records["path"] = self.path
            records["body"] = self.rfile.read(length).decode("utf-8")
            if response_shape == "ollama":
                payload = {"message": {"content": "ok"}}
            else:
                payload = {"choices": [{"message": {"content": "ok"}}]}
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], records
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _configured_http_profile(**overrides: object) -> ProviderProfile:
    profile = ProviderProfile(
        id="test-http",
        adapter_type="openai_compatible",
        model="test-model",
        roles=["controller"],
        base_url="https://legacy.example.com/v1",
        api_key_env="",
        config_status="configured",
    )
    for key, value in overrides.items():
        setattr(profile, key, value)
    return profile


def test_load_config_supports_legacy_provider_payload_without_new_endpoint_fields(tmp_path: Path) -> None:
    config = build_default_config(workspace_root=tmp_path / "workspace", vault_path=tmp_path / "vault")
    config.provider_profiles[0].config_status = "configured"
    config.provider_profiles[0].api_key_env = ""
    config_path = save_config(config, tmp_path / "config.json")

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    first_profile = payload["provider_profiles"][0]
    for key in ["relay_url", "scheme", "host", "port", "path_prefix"]:
        first_profile.pop(key, None)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    loaded = load_config(config_path)
    profile = loaded.provider_profiles[0]
    assert profile.relay_url == ""
    assert profile.scheme == "https"
    assert profile.host == ""
    assert profile.port is None
    assert profile.path_prefix == ""
    report = build_readiness_report(loaded)
    assert report.endpoint_diagnostics[0].endpoint_source == "base_url"


def test_save_config_round_trips_structured_endpoint_fields(tmp_path: Path) -> None:
    config = build_default_config(workspace_root=tmp_path / "workspace", vault_path=tmp_path / "vault")
    profile = config.provider_profiles[0]
    profile.host = "127.0.0.1"
    profile.port = 11434
    profile.scheme = "http"
    profile.path_prefix = "relay/openai/"
    profile.relay_url = ""
    config_path = save_config(config, tmp_path / "config.json")

    loaded = load_config(config_path)
    loaded_profile = loaded.provider_profiles[0]
    assert loaded_profile.host == "127.0.0.1"
    assert loaded_profile.port == 11434
    assert loaded_profile.scheme == "http"
    assert loaded_profile.path_prefix == "relay/openai/"


def test_resolve_provider_base_url_prioritizes_relay_then_structured_then_legacy() -> None:
    profile = _configured_http_profile(
        relay_url="https://relay.example.com/proxy/",
        host="127.0.0.1",
        port=8000,
        scheme="http",
        path_prefix="v1/",
    )
    relay_diagnostic = resolve_provider_base_url(profile)
    assert relay_diagnostic.endpoint_source == "relay_url"
    assert relay_diagnostic.effective_base_url == "https://relay.example.com/proxy"

    profile.relay_url = ""
    structured_diagnostic = resolve_provider_base_url(profile)
    assert structured_diagnostic.endpoint_source == "structured"
    assert structured_diagnostic.effective_base_url == "http://127.0.0.1:8000/v1"
    assert structured_diagnostic.normalized is True

    profile.host = ""
    profile.port = None
    profile.path_prefix = ""
    legacy_diagnostic = resolve_provider_base_url(profile)
    assert legacy_diagnostic.endpoint_source == "base_url"
    assert legacy_diagnostic.effective_base_url == "https://legacy.example.com/v1"


def test_resolve_provider_base_url_flags_invalid_scheme_and_port() -> None:
    profile = _configured_http_profile(base_url="", host="127.0.0.1", scheme="ftp", port=70000)
    diagnostic = resolve_provider_base_url(profile)
    assert diagnostic.valid is False
    assert "invalid_scheme" in diagnostic.issues
    assert "invalid_port" in diagnostic.issues


def test_openai_adapter_uses_relay_url_for_chat_completions() -> None:
    with recording_server("openai") as (port, records):
        profile = _configured_http_profile(
            relay_url=f"http://127.0.0.1:{port}/relay-root/",
            host="ignored.example.com",
            port=9000,
            scheme="http",
            path_prefix="v1",
        )
        response = OpenAICompatibleAdapter(profile).execute(
            ExecutionRequest(prompt="hello", output_mode="text", timeout_sec=5)
        )
    assert records["path"] == "/relay-root/chat/completions"
    assert response.content == "ok"


def test_ollama_adapter_uses_structured_endpoint_for_api_chat() -> None:
    with recording_server("ollama") as (port, records):
        profile = ProviderProfile(
            id="test-ollama",
            adapter_type="ollama",
            model="llama-test",
            roles=["marshal"],
            base_url="",
            scheme="http",
            host="127.0.0.1",
            port=port,
            path_prefix="ollama-root/",
            api_key_env="",
            config_status="configured",
        )
        response = OllamaAdapter(profile).execute(
            ExecutionRequest(prompt="hello", output_mode="text", timeout_sec=5)
        )
    assert records["path"] == "/ollama-root/api/chat"
    assert response.content == "ok"
    assert build_chat_endpoint(profile) == f"http://127.0.0.1:{port}/ollama-root/api/chat"


def test_doctor_json_includes_endpoint_diagnostics(tmp_path: Path, capsys) -> None:
    config = build_default_config(workspace_root=tmp_path / "workspace", vault_path=tmp_path / "vault")
    for profile in config.provider_profiles:
        if profile.adapter_type == "command_bridge":
            profile.enabled = False
            continue
        profile.config_status = "configured"
        profile.api_key_env = ""
    config.provider_profiles[0].relay_url = ""
    config.provider_profiles[0].host = "relay.local"
    config.provider_profiles[0].scheme = "https"
    config.provider_profiles[0].path_prefix = "proxy/v1/"
    config_path = save_config(config, tmp_path / "config.json")

    exit_code = main(["doctor", "--config", str(config_path), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    controller_diagnostic = next(
        item for item in payload["endpoint_diagnostics"] if item["profile_id"] == "controller-primary"
    )

    assert exit_code == 2
    assert controller_diagnostic["endpoint_source"] == "structured"
    assert controller_diagnostic["effective_base_url"] == "https://relay.local/proxy/v1"
    assert controller_diagnostic["normalized"] is True


def test_run_refuses_invalid_structured_endpoint_before_provider_execution(tmp_path: Path, capsys) -> None:
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("# Brief\n\n测试 invalid endpoint gate。", encoding="utf-8")
    config = build_default_config(workspace_root=tmp_path / "workspace", vault_path=tmp_path / "vault")
    for profile in config.provider_profiles:
        if profile.adapter_type == "command_bridge":
            profile.enabled = False
            continue
        profile.config_status = "configured"
        profile.api_key_env = ""
    config.provider_profiles[0].base_url = ""
    config.provider_profiles[0].relay_url = ""
    config.provider_profiles[0].host = "127.0.0.1"
    config.provider_profiles[0].scheme = "http"
    config.provider_profiles[0].port = 70000
    config_path = save_config(config, tmp_path / "config.json")

    exit_code = main(
        [
            "run",
            "--config",
            str(config_path),
            "--brief",
            str(brief_path),
            "--topic",
            "invalid-endpoint",
            "--yes",
            "--allow-degraded",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "当前配置存在 blocker" in captured.err
