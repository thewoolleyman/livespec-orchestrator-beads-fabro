"""Which adopter repositories have RESOLVED the current release.

Every governed repository pins this plugin at the MOVING `release` branch, so
there is no per-repo pin commit to look for — and therefore no per-repo event
confirming that an adopter has actually taken a release. An adopter can sit on
a stale build indefinitely and nothing reports it. "Pinned in all fleet repos"
is unverifiable in principle until a fact answers the adoption question
directly, which is what this lane composes.

TWO DIFFERENT QUESTIONS, AND CONFLATING THEM IS HOW THIS LANE GETS BUILT WRONG.
The newest build MATERIALISED IN THE SHARED CACHE is not the build any given
project RESOLVES; the two have been measured a full release apart, and both
readings were correct. This lane answers the second question only — what a
repository would actually load — because that is what decides whether a fix is
in force there. So the release tip is NEVER derived as the maximum version
found across installed builds: it is read from the marketplace clone, which is
itself checked out at the `release` ref.

A BUILD IS IDENTIFIED BY PARSING ITS `plugin.json`, NEVER BY ITS CACHE
DIRECTORY NAME. Cache directories are keyed by commit AND by version, both
shapes coexist, and the manifest's location moved to the build root; a
name-based match silently misses builds. Both locations are read here, and the
identity is taken from the parsed manifest.

THE PLUGIN BEING ADOPTED IS THIS ONE, WHEREVER THE LANE HAPPENS TO RUN. The
install-registry lookup key is therefore a constant here and is NEVER read from
`<project_root>/.claude-plugin/plugin.json`: that manifest names the GOVERNED
PROJECT — `livespec-overseer`, `homelab`, `livespec-runtime` — so deriving the
key from it asks the registry for a key that does not exist, and the lane goes
silent in every repository except one that falsely names this plugin as its own.
For a fact that reports an ABSENCE, finding no adopters is indistinguishable
from finding every adopter current, which is the exact all-clear this lane
exists to withhold.

Path discovery is a language-level `Path` read of an explicitly named
directory throughout. No shell listing is ever parsed into words — a listing
that renders long-format on one host yields confident rows for directories
that do not exist.

FAIL-CLOSED ON ABSENCE, in the one direction that matters. An adopter whose
build cannot be identified is reported BEHIND, never current: absence of
evidence that a fix arrived is not evidence that it did. Where the release tip
itself cannot be established while adopters exist, the lane says so rather
than reporting an all-clear, because absence reads as resolution downstream.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_core_roots import version_key
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "AdopterResolution",
    "ReleaseAdoptionBases",
    "adopter_resolutions",
    "default_release_adoption_bases",
    "read_build_version",
    "release_adoption_items",
    "release_tip_version",
]

# The two places a build's manifest has lived. The build root is checked FIRST
# because that is where it moved to; the bundle directory remains readable so a
# marketplace clone (a whole repository, not a flattened build) resolves too.
_MANIFEST_LOCATIONS: tuple[tuple[str, ...], ...] = (
    ("plugin.json",),
    (".claude-plugin", "plugin.json"),
)
# The plugin whose adoption this lane reports — an identity, not an observation.
# It is deliberately NOT read from the governed project's manifest; see the
# module docstring for what that mis-aimed read costs.
_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
# The moving channel every adopter pins. A marketplace clone checked out at any
# other ref is not the release tip and MUST NOT be read as one.
_RELEASE_REF = "release"
_UNKNOWN_VERSION = "unknown"
_FACT_TYPE = "release-adoption"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReleaseAdoptionBases:
    """Injectable registry files backing the adoption reading.

    Defaulted to production (`default_release_adoption_bases`, under the real
    HOME) and overridden in tests with tmp files, so every tier is covered
    hermetically without HOME monkeypatching.
    """

    install_record: Path
    marketplace_record: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class AdopterResolution:
    """One adopter repository and the plugin build it currently resolves."""

    adopter: str
    project_path: str
    install_path: str
    version: str
    behind: bool


def read_build_version(*, install_path: Path) -> str | None:
    """The version a materialized build declares, parsed from its `plugin.json`.

    Returns None when neither manifest location parses — the caller reports
    that adopter as behind rather than inventing an identity from the cache
    directory name.
    """
    for parts in _MANIFEST_LOCATIONS:
        version = _parsed_object(path=install_path.joinpath(*parts)).get("version")
        if isinstance(version, str) and version != "":
            return version
    return None


def release_tip_version(*, marketplace_record: Path, plugin_name: str) -> str | None:
    """The version at the `release` tip, read from the marketplace clone.

    The clone named by the marketplace registry is checked out at the ref the
    registry records, so it IS the release tip when that ref is `release`. Any
    other ref, or a clone whose manifest does not parse, yields None.
    """
    registry = _parsed_object(path=marketplace_record)
    entry = _object_at(mapping=registry, key=plugin_name)
    source = _object_at(mapping=entry, key="source")
    if source.get("ref") != _RELEASE_REF:
        return None
    location = entry.get("installLocation")
    if not isinstance(location, str) or location == "":
        return None
    return read_build_version(install_path=Path(location))


def adopter_resolutions(
    *,
    bases: ReleaseAdoptionBases,
    plugin_name: str,
    tip_version: str | None,
) -> tuple[AdopterResolution, ...]:
    """One resolution per install record this host holds for `plugin_name`.

    Records are read for EVERY marketplace the plugin is installed from, keyed
    on the plugin component of the registry key rather than on a hardcoded
    `<plugin>@<marketplace>` pair.
    """
    registry = _parsed_object(path=bases.install_record)
    plugins = _object_at(mapping=registry, key="plugins")
    resolutions: list[AdopterResolution] = []
    for key, entries in plugins.items():
        if key.split("@", maxsplit=1)[0] != plugin_name or not isinstance(entries, list):
            continue
        for entry in cast("list[Any]", entries):
            resolution = _resolution(entry=entry, tip_version=tip_version)
            if resolution is not None:
                resolutions.append(resolution)
    return tuple(sorted(resolutions, key=lambda item: (item.adopter, item.project_path)))


def release_adoption_items(
    *,
    project_root: Path,
    repo: str,
    bases: ReleaseAdoptionBases,
) -> list[AttentionItem]:
    """Compose the adoption fact, emitting nothing when every adopter is current.

    An attention list is not a dashboard: a host whose adopters have all taken
    the release needs no item. The moment ONE adopter is behind, EVERY adopter
    composes its own item — the ones that are behind at high urgency, and the
    ones that are current at low urgency, named as current. That positive half
    is what makes a broken reading visible: a lane that can only ever report
    "behind" is indistinguishable from a lane that has stopped reading.

    `project_root` names the repository this snapshot is FOR: it addresses the
    handoff commands, and is never the source of the plugin identity looked up.
    """
    tip_version = release_tip_version(
        marketplace_record=bases.marketplace_record, plugin_name=_PLUGIN_NAME
    )
    resolutions = adopter_resolutions(
        bases=bases, plugin_name=_PLUGIN_NAME, tip_version=tip_version
    )
    if not resolutions:
        return []
    if tip_version is None:
        return [_unresolved_tip_item(project_root=project_root, repo=repo, count=len(resolutions))]
    if not any(resolution.behind for resolution in resolutions):
        return []
    return [
        _resolution_item(
            project_root=project_root,
            repo=repo,
            resolution=resolution,
            tip_version=tip_version,
        )
        for resolution in resolutions
    ]


def default_release_adoption_bases() -> ReleaseAdoptionBases:  # pragma: no cover
    """The production registries under the real HOME (integration-covered)."""
    plugins = Path.home() / ".claude" / "plugins"
    return ReleaseAdoptionBases(
        install_record=plugins / "installed_plugins.json",
        marketplace_record=plugins / "known_marketplaces.json",
    )


def _resolution(*, entry: object, tip_version: str | None) -> AdopterResolution | None:
    record = cast("dict[str, Any]", entry) if isinstance(entry, dict) else {}
    project_path = record.get("projectPath")
    install_path = record.get("installPath")
    if not isinstance(project_path, str) or project_path == "":
        return None
    resolved = (
        read_build_version(install_path=Path(install_path))
        if isinstance(install_path, str) and install_path != ""
        else None
    )
    return AdopterResolution(
        adopter=Path(project_path).name,
        project_path=project_path,
        install_path=install_path if isinstance(install_path, str) else "",
        version=resolved if resolved is not None else _UNKNOWN_VERSION,
        behind=_is_behind(resolved=resolved, tip_version=tip_version),
    )


def _is_behind(*, resolved: str | None, tip_version: str | None) -> bool:
    """Fail-closed: an unidentifiable build is behind, never current."""
    if resolved is None:
        return True
    if tip_version is None:
        return False
    return version_key(name=resolved) < version_key(name=tip_version)


def _resolution_item(
    *,
    project_root: Path,
    repo: str,
    resolution: AdopterResolution,
    tip_version: str,
) -> AttentionItem:
    verdict = "BEHIND" if resolution.behind else "current"
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:{_FACT_TYPE}:{resolution.adopter}",
        kind="hygiene",
        urgency="high" if resolution.behind else "low",
        summary=(
            f"Adopter {resolution.adopter} resolves plugin build {resolution.version} "
            f"against release tip {tip_version}: {verdict}. Resolved from the install "
            f"record for project {resolution.project_path}, identified by parsing the "
            "build's own plugin.json."
        ),
        source_ref=SourceRef(repo=repo, path=resolution.project_path),
        handoff=Handoff(
            kind="shell",
            command=_resolution_command(project_root=project_root, resolution=resolution),
        ),
    )


def _unresolved_tip_item(*, project_root: Path, repo: str, count: int) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:{_FACT_TYPE}:unresolved-release-tip",
        kind="hygiene",
        urgency="high",
        summary=(
            f"Release adoption is unreadable for {count} adopter records: the release "
            "tip could not be established from the marketplace registry, so no adopter "
            "can be judged current. This is an unreadable instrument, never an all-clear."
        ),
        source_ref=SourceRef(repo=repo),
        handoff=Handoff(
            kind="shell",
            command=_unresolved_tip_command(project_root=project_root),
        ),
    )


def _resolution_command(*, project_root: Path, resolution: AdopterResolution) -> str:
    prompt = (
        f"inspect-release-adoption {resolution.adopter} in repository {project_root}. "
        f"That project resolves plugin build {resolution.version} from install path "
        f"{resolution.install_path}. Read the build's own plugin.json as the identity; "
        "never infer it from the cache directory name. Refresh the adopter's install "
        "when it is behind the release tip."
    )
    return f"cd {shlex.quote(str(project_root))} && codex exec {shlex.quote(prompt)} < /dev/null"


def _unresolved_tip_command(*, project_root: Path) -> str:
    prompt = (
        f"inspect-release-tip-resolution in repository {project_root}. The marketplace "
        "registry did not yield a clone checked out at the release ref, so adoption "
        "cannot be judged. Repair the reading; do not resolve it by treating the "
        "newest cached build as the release tip."
    )
    return f"cd {shlex.quote(str(project_root))} && codex exec {shlex.quote(prompt)} < /dev/null"


def _parsed_object(*, path: Path) -> dict[str, Any]:
    """The JSON object at `path`, or an empty mapping for any read/parse failure.

    `ValueError` is caught alongside `OSError` because a registry holding bytes
    that are not UTF-8 raises `UnicodeDecodeError` from the decode rather than
    from the read, and an undecodable registry must read as "no records" — the
    caller is fail-closed on absence — not as an unhandled crash of the whole
    attention snapshot.
    """
    if not path.is_file():
        return {}
    text = attempt(
        action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError, ValueError)
    )
    if isinstance(text, AttemptFailure):
        return {}
    parsed = parse_json(text=text)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return {}
    return cast("dict[str, Any]", parsed)


def _object_at(*, mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}
