from __future__ import annotations

import os
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
UNC_PATH_RE = re.compile(r"^(\\\\|//)")


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _looks_like_windows_absolute_path(value: str) -> bool:
    return bool(WINDOWS_DRIVE_PATH_RE.match(value) or UNC_PATH_RE.match(value))


def _override_path(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or _looks_like_windows_absolute_path(value):
        return candidate
    return candidate.resolve()


def get_workspace_root(repo_root: Path = REPO_ROOT) -> Path:
    return repo_root.resolve()


def get_workspace_name(repo_root: Path = REPO_ROOT) -> str:
    return get_workspace_root(repo_root).name


def get_workspace_drive_root(repo_root: Path = REPO_ROOT) -> Path:
    workspace_root = get_workspace_root(repo_root)
    return Path(workspace_root.anchor or f"{workspace_root.drive}\\")


def get_cold_storage_workspace_root(repo_root: Path = REPO_ROOT) -> Path:
    override = _first_env("PIJIANG_COLD_STORAGE_ROOT", "CODEX_COLD_STORAGE_ROOT")
    if override:
        return _override_path(override)
    workspace_name = get_workspace_name(repo_root)
    return get_workspace_drive_root(repo_root) / f"{workspace_name} huancun" / "workspace-cache" / workspace_name


def get_cache_root(repo_root: Path = REPO_ROOT) -> Path:
    override = _first_env("PIJIANG_CACHE_ROOT", "CODEX_CACHE_ROOT")
    if override:
        return _override_path(override)
    return get_cold_storage_workspace_root(repo_root) / "cache"


def get_models_root(repo_root: Path = REPO_ROOT) -> Path:
    override = _first_env("PIJIANG_MODELS_ROOT", "CODEX_MODELS_ROOT")
    if override:
        return _override_path(override)
    return get_cold_storage_workspace_root(repo_root) / "models"


def get_tmp_root(repo_root: Path = REPO_ROOT) -> Path:
    return get_workspace_root(repo_root) / "tmp"


def get_hidden_tmp_targets(repo_root: Path = REPO_ROOT) -> dict[str, Path]:
    legacy_root = get_tmp_root(repo_root) / "legacy-hidden"
    return {
        ".tmp": legacy_root / ".tmp",
        ".codex-tmp": legacy_root / ".codex-tmp",
    }


def get_default_cache_env(repo_root: Path = REPO_ROOT) -> dict[str, str]:
    cache_root = get_cache_root(repo_root)
    huggingface_root = cache_root / "huggingface"
    return {
        "HF_HOME": str(huggingface_root),
        "HUGGINGFACE_HUB_CACHE": str(huggingface_root / "hub"),
        "TRANSFORMERS_CACHE": str(huggingface_root / "transformers"),
        "PIP_CACHE_DIR": str(cache_root / "pip"),
        "MODELSCOPE_CACHE": str(cache_root / "modelscope"),
        "PADDLE_HOME": str(cache_root / "paddle"),
    }
