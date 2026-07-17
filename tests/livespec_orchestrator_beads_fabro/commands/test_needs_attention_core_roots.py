"""Tests for CORE plugin-root resolution behind needs-attention."""

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._needs_attention_core_roots import (
    CoreRootBases,
    claude_installed_core_roots,
    codex_installed_core_roots,
    read_spec_clis_next_argv,
    resolve_core_plugin_root,
    resolve_spec_next_command,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_core_roots import (
    __all__ as core_roots_all,
)


def _plant_next(root: Path) -> Path:
    """Materialize `<root>/scripts/bin/next.py` so `root` resolves as a CORE root."""
    (root / "scripts" / "bin").mkdir(parents=True)
    _ = (root / "scripts" / "bin" / "next.py").write_text("# core next\n", encoding="utf-8")
    return root


def _empty_bases(tmp_path: Path) -> CoreRootBases:
    """Bases that resolve nothing (both cache tiers point at non-existent tmp paths)."""
    return CoreRootBases(
        claude_registry=tmp_path / "no-claude" / "installed_plugins.json",
        codex_cache=tmp_path / "no-codex-cache",
    )


def test_public_surface_names_are_non_private() -> None:
    assert core_roots_all == [
        "CoreRootBases",
        "argv_uses_plugin_root_placeholder",
        "as_str_argv",
        "claude_installed_core_roots",
        "codex_installed_core_roots",
        "core_root_candidates",
        "default_core_root_bases",
        "read_spec_clis_next_argv",
        "resolve_core_plugin_root",
        "resolve_spec_next_command",
        "version_key",
    ]
    assert all(not name.startswith("_") for name in core_roots_all)


def test_resolve_core_root_prefers_fleet_sibling(tmp_path) -> None:
    workspace = tmp_path / "ws"
    sibling = _plant_next(workspace / "livespec" / ".claude-plugin")
    project = workspace / "governed"
    project.mkdir(parents=True)

    assert resolve_core_plugin_root(project_root=project, bases=_empty_bases(tmp_path)) == sibling


def test_resolve_core_root_uses_claude_installed_cache(tmp_path) -> None:
    core = _plant_next(tmp_path / "claude-cache" / "livespec")
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text(
        json.dumps({"plugins": {"livespec@livespec": [{"installPath": str(core)}]}}),
        encoding="utf-8",
    )
    bases = CoreRootBases(claude_registry=registry, codex_cache=tmp_path / "no-codex")
    project = tmp_path / "governed"
    project.mkdir()

    assert resolve_core_plugin_root(project_root=project, bases=bases) == core


def test_resolve_core_root_uses_codex_installed_cache(tmp_path) -> None:
    # Codex-only user WITHOUT a fleet sibling and WITHOUT a Claude registry: the
    # Codex-cache tier must resolve `<cache>/livespec/livespec/<version>` — the
    # regression the pre-Codex-tier resolver silently dropped.
    codex_cache = tmp_path / "codex-cache"
    core = _plant_next(codex_cache / "livespec" / "livespec" / "0.7.1")
    bases = CoreRootBases(claude_registry=tmp_path / "missing.json", codex_cache=codex_cache)
    project = tmp_path / "governed"
    project.mkdir()

    assert resolve_core_plugin_root(project_root=project, bases=bases) == core


def test_resolve_core_root_codex_cache_picks_highest_version(tmp_path) -> None:
    codex_cache = tmp_path / "codex-cache"
    _ = _plant_next(codex_cache / "livespec" / "livespec" / "0.7.1")
    highest = _plant_next(codex_cache / "livespec" / "livespec" / "0.10.0")
    (codex_cache / "livespec" / "livespec" / "main").mkdir()  # non-numeric sorts lowest
    bases = CoreRootBases(claude_registry=tmp_path / "missing.json", codex_cache=codex_cache)
    project = tmp_path / "governed"
    project.mkdir()

    assert resolve_core_plugin_root(project_root=project, bases=bases) == highest


def test_resolve_core_root_none_when_all_tiers_miss(tmp_path) -> None:
    project = tmp_path / "governed"
    project.mkdir()

    assert resolve_core_plugin_root(project_root=project, bases=_empty_bases(tmp_path)) is None


def test_claude_installed_core_roots_missing_registry(tmp_path) -> None:
    assert list(claude_installed_core_roots(registry=tmp_path / "nope.json")) == []


def test_claude_installed_core_roots_unreadable_registry_yields_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text("{}", encoding="utf-8")

    def _raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
        _ = (self, args, kwargs)
        raise OSError("nope")

    monkeypatch.setattr(Path, "read_text", _raise_oserror)

    assert list(claude_installed_core_roots(registry=registry)) == []


@pytest.mark.parametrize(
    "registry_text",
    [
        "{ not json",
        json.dumps([1, 2]),
        json.dumps({}),
        json.dumps({"plugins": "x"}),
        json.dumps({"plugins": {"livespec@livespec": "x"}}),
        json.dumps({"plugins": {"livespec@livespec": ["str", {"installPath": ""}, {"x": 1}]}}),
    ],
)
def test_claude_installed_core_roots_malformed_yields_nothing(tmp_path, registry_text: str) -> None:
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text(registry_text, encoding="utf-8")
    assert list(claude_installed_core_roots(registry=registry)) == []


def test_claude_installed_core_roots_yields_install_paths(tmp_path) -> None:
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text(
        json.dumps(
            {"plugins": {"livespec@livespec": [{"installPath": "/a"}, {"installPath": "/b"}]}}
        ),
        encoding="utf-8",
    )
    assert list(claude_installed_core_roots(registry=registry)) == [Path("/a"), Path("/b")]


def test_codex_installed_core_roots_missing_plugin_dir(tmp_path) -> None:
    assert list(codex_installed_core_roots(cache=tmp_path / "empty-cache")) == []


def test_codex_installed_core_roots_yields_version_dirs_highest_first(tmp_path) -> None:
    base = tmp_path / "cache" / "livespec" / "livespec"
    (base / "0.7.1").mkdir(parents=True)
    (base / "0.10.0").mkdir()

    roots = list(codex_installed_core_roots(cache=tmp_path / "cache"))

    assert roots == [base / "0.10.0", base / "0.7.1"]


def test_read_spec_clis_next_argv_missing_file(tmp_path) -> None:
    assert read_spec_clis_next_argv(project_root=tmp_path) is None


def test_read_spec_clis_next_argv_unreadable_file_returns_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")

    def _raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
        _ = (self, args, kwargs)
        raise OSError("nope")

    monkeypatch.setattr(Path, "read_text", _raise_oserror)

    assert read_spec_clis_next_argv(project_root=tmp_path) is None


@pytest.mark.parametrize(
    "body",
    [
        "{ not valid jsonc",
        '"a string"',
        "{}",
        '{"spec_clis": "x"}',
        '{"spec_clis": {"next": "x"}}',
        '{"spec_clis": {"next": []}}',
        '{"spec_clis": {"next": [1, 2]}}',
    ],
)
def test_read_spec_clis_next_argv_off_happy_path_returns_none(tmp_path, body: str) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(body, encoding="utf-8")
    assert read_spec_clis_next_argv(project_root=tmp_path) is None


def test_read_spec_clis_next_argv_returns_configured_argv(tmp_path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"spec_clis": {"next": ["python3", "/abs/next.py"]}}', encoding="utf-8"
    )
    assert read_spec_clis_next_argv(project_root=tmp_path) == ["python3", "/abs/next.py"]


def test_resolve_spec_next_command_none_when_core_unresolvable(tmp_path) -> None:
    project = tmp_path / "governed"
    project.mkdir()
    assert resolve_spec_next_command(project_root=project, bases=_empty_bases(tmp_path)) is None


def test_resolve_spec_next_command_uses_absolute_config_without_core(tmp_path) -> None:
    project = tmp_path / "governed"
    project.mkdir()
    _ = (project / ".livespec.jsonc").write_text(
        '{"spec_clis": {"next": ["python3", "/portable/core/next.py"]}}',
        encoding="utf-8",
    )

    command = resolve_spec_next_command(project_root=project, bases=_empty_bases(tmp_path))

    assert command == ["python3", "/portable/core/next.py"]


def test_resolve_spec_next_command_substitutes_default_template(tmp_path) -> None:
    workspace = tmp_path / "ws"
    sibling = _plant_next(workspace / "livespec" / ".claude-plugin")
    project = workspace / "governed"
    project.mkdir(parents=True)

    command = resolve_spec_next_command(project_root=project, bases=_empty_bases(tmp_path))

    assert command == ["python3", f"{sibling}/scripts/bin/next.py"]


def test_resolve_spec_next_command_uses_configured_argv(tmp_path) -> None:
    workspace = tmp_path / "ws"
    sibling = _plant_next(workspace / "livespec" / ".claude-plugin")
    project = workspace / "governed"
    project.mkdir(parents=True)
    _ = (project / ".livespec.jsonc").write_text(
        '{"spec_clis": {"next": ["python3", "${CLAUDE_PLUGIN_ROOT}/scripts/bin/next.py", "--x"]}}',
        encoding="utf-8",
    )

    command = resolve_spec_next_command(project_root=project, bases=_empty_bases(tmp_path))

    assert command == ["python3", f"{sibling}/scripts/bin/next.py", "--x"]
