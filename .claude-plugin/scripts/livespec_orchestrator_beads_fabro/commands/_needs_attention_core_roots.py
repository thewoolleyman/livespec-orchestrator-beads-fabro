"""CORE plugin-root resolution for the needs-attention spec-next seam."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
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

_LIVESPEC_CONFIG = ".livespec.jsonc"
_PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
# The default argv when the governed project declares no `spec_clis.next`:
# CORE ships the spec-`next` CLI at `<core-plugin-root>/scripts/bin/next.py`.
# `${CLAUDE_PLUGIN_ROOT}` is substituted with the resolved CORE plugin root.
_DEFAULT_SPEC_NEXT_ARGV: tuple[str, ...] = (
    "python3",
    f"{_PLUGIN_ROOT_PLACEHOLDER}/scripts/bin/next.py",
)
# CORE's spec-`next` CLI, relative to whichever plugin root resolves it. The
# resolver accepts a candidate root only when this file exists beneath it.
_CORE_SPEC_NEXT_REL: tuple[str, ...] = ("scripts", "bin", "next.py")
_CLAUDE_CORE_PLUGIN_KEY = "livespec@livespec"


@dataclass(frozen=True, slots=True, kw_only=True)
class CoreRootBases:
    """Injectable filesystem bases for CORE plugin-root resolution.

    Defaulted to production (`default_core_root_bases`, under the real HOME) and
    overridden in unit tests with tmp dirs so EVERY resolution tier — including
    the Codex-cache tier — is covered hermetically: no real `~/.claude` /
    `~/.codex`, no HOME monkeypatching.
    """

    claude_registry: Path
    codex_cache: Path


def read_spec_clis_next_argv(*, project_root: Path) -> list[str] | None:
    """The governed project's `spec_clis.next` argv, or None when absent/malformed.

    Reads `<project_root>/.livespec.jsonc` (JSONC); returns the top-level
    `spec_clis.next` value only when it is a non-empty list of strings, else
    None so the caller falls back to the default argv.
    """
    config_path = project_root / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return None
    config_text = attempt(
        action=lambda: config_path.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(config_text, AttemptFailure):
        return None
    parsed = _jsonc.parse(text=config_text)
    if isinstance(parsed, _jsonc.JsoncFailure):
        return None
    if not isinstance(parsed, dict):
        return None
    spec_clis = cast("dict[str, Any]", parsed).get("spec_clis")
    if not isinstance(spec_clis, dict):
        return None
    return as_str_argv(value=cast("dict[str, Any]", spec_clis).get("next"))


def as_str_argv(*, value: object) -> list[str] | None:
    """Return `value` as a non-empty list of strings, or None for any other shape."""
    if not isinstance(value, list):
        return None
    items = cast("list[Any]", value)
    if not items or not all(isinstance(element, str) for element in items):
        return None
    return [str(element) for element in items]


def claude_installed_core_roots(*, registry: Path) -> Iterator[Path]:
    """Yield CORE roots from a Claude `installed_plugins.json` registry file."""
    if not registry.is_file():
        return
    registry_text = attempt(
        action=lambda: registry.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(registry_text, AttemptFailure):
        return
    parsed = parse_json(text=registry_text)
    if isinstance(parsed, JsonParseFailure):
        return
    if not isinstance(parsed, dict):
        return
    plugins = cast("dict[str, Any]", parsed).get("plugins")
    if not isinstance(plugins, dict):
        return
    entries = cast("dict[str, Any]", plugins).get(_CLAUDE_CORE_PLUGIN_KEY)
    if not isinstance(entries, list):
        return
    for entry in cast("list[Any]", entries):
        if isinstance(entry, dict):
            install_path = cast("dict[str, Any]", entry).get("installPath")
            if isinstance(install_path, str) and install_path != "":
                yield Path(install_path)


def version_key(*, name: str) -> tuple[int, ...]:
    """Sort key for a version-dir name; a non-numeric chunk sorts lowest."""
    return tuple(int(chunk) if chunk.isdigit() else -1 for chunk in name.split("."))


def codex_installed_core_roots(*, cache: Path) -> Iterator[Path]:
    """Yield Codex-cached CORE roots, highest version first.

    A Codex-installed core lives at `<cache>/livespec/livespec/<version>/`
    (`<version>/scripts/bin/next.py`). Version dirs are yielded highest-first so
    the resolver picks the newest installed core (the stable cache path, not the
    marketplace tmp `source.path`).
    """
    plugin_dir = cache / "livespec" / "livespec"
    if not plugin_dir.is_dir():
        return
    version_dirs = sorted(
        (child for child in plugin_dir.iterdir() if child.is_dir()),
        key=lambda child: version_key(name=child.name),
        reverse=True,
    )
    yield from version_dirs


def core_root_candidates(*, project_root: Path, bases: CoreRootBases) -> Iterator[Path]:
    """Yield CORE plugin-root candidates, most-specific first.

    (a) fleet-sibling checkout `<parent-of-project_root>/livespec/.claude-plugin`;
    (b) Claude installed-plugin cache (`livespec@livespec` installPath);
    (c) Codex installed-plugin cache (`<codex-cache>/livespec/livespec/<version>`,
        highest version first). No `LIVESPEC_CORE_PLUGIN_ROOT` env lever (the
        ci-gate-discipline forbids it).
    """
    yield project_root.parent / "livespec" / ".claude-plugin"
    yield from claude_installed_core_roots(registry=bases.claude_registry)
    yield from codex_installed_core_roots(cache=bases.codex_cache)


def resolve_core_plugin_root(*, project_root: Path, bases: CoreRootBases) -> Path | None:
    """The first candidate root that actually carries the spec-`next` CLI, or None."""
    for candidate in core_root_candidates(project_root=project_root, bases=bases):
        if candidate.joinpath(*_CORE_SPEC_NEXT_REL).is_file():
            return candidate
    return None


def resolve_spec_next_command(*, project_root: Path, bases: CoreRootBases) -> list[str] | None:
    """The runnable spec-`next` argv (token-substituted), or None if unresolvable."""
    configured = read_spec_clis_next_argv(project_root=project_root)
    if configured is not None and not argv_uses_plugin_root_placeholder(argv=configured):
        return configured
    core_root = resolve_core_plugin_root(project_root=project_root, bases=bases)
    if core_root is None:
        return None
    template = configured if configured is not None else list(_DEFAULT_SPEC_NEXT_ARGV)
    return [element.replace(_PLUGIN_ROOT_PLACEHOLDER, str(core_root)) for element in template]


def argv_uses_plugin_root_placeholder(*, argv: list[str]) -> bool:
    """Whether argv still needs CORE plugin-root discovery for token substitution."""
    return any(_PLUGIN_ROOT_PLACEHOLDER in element for element in argv)


def default_core_root_bases() -> CoreRootBases:  # pragma: no cover
    """The production resolution bases under the real HOME (integration-covered)."""
    home = Path.home()
    return CoreRootBases(
        claude_registry=home / ".claude" / "plugins" / "installed_plugins.json",
        codex_cache=home / ".codex" / "plugins" / "cache",
    )
