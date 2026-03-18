from __future__ import annotations

from pathlib import Path

from tools.workspace_paths import get_cache_root, get_cold_storage_workspace_root, get_models_root


def test_workspace_paths_support_pijiang_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("PIJIANG_COLD_STORAGE_ROOT", r"F:\cache-root")
    repo_root = Path(r"F:\github\皮匠")

    assert get_cold_storage_workspace_root(repo_root) == Path(r"F:\cache-root")

    monkeypatch.setenv("PIJIANG_CACHE_ROOT", r"F:\cache-root\cache")
    assert get_cache_root(repo_root) == Path(r"F:\cache-root\cache")

    monkeypatch.setenv("PIJIANG_MODELS_ROOT", r"F:\cache-root\models")
    assert get_models_root(repo_root) == Path(r"F:\cache-root\models")
