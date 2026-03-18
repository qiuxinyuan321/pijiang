from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit

from .types import EndpointDiagnostic, ProviderProfile


HTTP_ADAPTER_TYPES = {"openai_compatible", "planning_api", "ollama"}
VALID_SCHEMES = {"http", "https"}


def is_http_provider(profile: ProviderProfile) -> bool:
    return profile.adapter_type in HTTP_ADAPTER_TYPES


def _normalize_text(value: str) -> str:
    return value.strip()


def _normalize_path_prefix(path_prefix: str) -> tuple[str, bool]:
    cleaned = _normalize_text(path_prefix)
    if not cleaned:
        return "", False
    normalized = "/" + cleaned.strip("/")
    return normalized, normalized != cleaned


def _coerce_port(port_value: object) -> tuple[int | None, bool]:
    if port_value in {None, ""}:
        return None, False
    if isinstance(port_value, int):
        return port_value, True
    text = str(port_value).strip()
    if not text:
        return None, False
    try:
        return int(text), True
    except ValueError:
        return None, False


def resolve_provider_base_url(profile: ProviderProfile) -> EndpointDiagnostic:
    source = "unresolved"
    raw_root = ""
    issues: list[str] = []
    normalized = False

    relay_url = _normalize_text(profile.relay_url)
    host = _normalize_text(profile.host)
    legacy_base_url = _normalize_text(profile.base_url)
    scheme = (_normalize_text(profile.scheme) or "https").lower()
    path_prefix, path_was_normalized = _normalize_path_prefix(profile.path_prefix)
    normalized = normalized or path_was_normalized

    if relay_url:
        source = "relay_url"
        raw_root = relay_url
    elif host:
        source = "structured"
        if scheme not in VALID_SCHEMES:
            issues.append("invalid_scheme")
        port, port_is_valid = _coerce_port(profile.port)
        if profile.port not in {None, ""} and not port_is_valid:
            issues.append("invalid_port")
        elif port is not None and not (1 <= port <= 65535):
            issues.append("invalid_port")
        netloc = host
        if port is not None and 1 <= port <= 65535:
            netloc = f"{host}:{port}"
        raw_root = f"{scheme}://{netloc}{path_prefix}"
    elif legacy_base_url:
        source = "base_url"
        raw_root = legacy_base_url
    else:
        issues.append("missing_endpoint")

    effective_base_url = raw_root.rstrip("/")
    normalized = normalized or (effective_base_url != raw_root)

    if effective_base_url:
        parsed = urlsplit(effective_base_url)
        if parsed.scheme.lower() not in VALID_SCHEMES:
            if "invalid_scheme" not in issues:
                issues.append("invalid_root_url")
        elif not parsed.netloc:
            issues.append("invalid_root_url")

    valid = not issues and bool(effective_base_url)
    return EndpointDiagnostic(
        profile_id=profile.id,
        adapter_type=profile.adapter_type,
        endpoint_source=source,
        effective_base_url=effective_base_url,
        normalized=normalized,
        valid=valid,
        issues=issues,
    )


def build_chat_endpoint(profile: ProviderProfile) -> str:
    diagnostic = resolve_provider_base_url(profile)
    if not diagnostic.valid:
        issues = ", ".join(diagnostic.issues) or "unresolved_endpoint"
        raise ValueError(f"profile {profile.id} has invalid endpoint configuration: {issues}")

    base = diagnostic.effective_base_url
    if profile.adapter_type in {"openai_compatible", "planning_api"}:
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    if profile.adapter_type == "ollama":
        return base if base.endswith("/api/chat") else f"{base}/api/chat"
    return base


def normalized_http_profile(profile: ProviderProfile) -> ProviderProfile:
    diagnostic = resolve_provider_base_url(profile)
    if not diagnostic.valid:
        return profile

    normalized_profile = replace(profile, base_url=diagnostic.effective_base_url)
    if diagnostic.endpoint_source == "structured":
        normalized_profile.scheme = (_normalize_text(profile.scheme) or "https").lower()
        normalized_profile.path_prefix = _normalize_path_prefix(profile.path_prefix)[0]
        port, _ = _coerce_port(profile.port)
        normalized_profile.port = port
    return normalized_profile
