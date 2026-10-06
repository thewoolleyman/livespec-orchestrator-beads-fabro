"""Build IDENTITY and remote-ref PROBES for the dispatcher currency gate.

Cut out of `_dispatcher_staleness_gate` along its own cohesion seam. The gate
is a DECISION layer: it assembles `DispatcherStalenessDecision` values out of
warnings and refusals. Underneath it sat this layer, which answers plain
factual questions instead — is this plugin root a git checkout, is its name a
release-cache build id, what sha does a remote ref point at, does a build id
match a sha — and traffics only in strings, booleans and argv tuples, naming
none of the decision types. That one-way dependency is what makes the cut
clean: this module imports nothing from the gate.

The split was forced by size. Threading the executing-payload root through the
gate so the minimum-release floor could judge the bytes actually running took
that file past its 250 LLOC hard ceiling, and the remedy for a file over the
ceiling is to decompose it by cohesion, never to shave lines.

Every name here is PUBLIC because it is consumed across a module boundary: a
`_`-prefixed name imported elsewhere is rejected by pyright strict
(`reportPrivateUsage`) and by the private-calls check alike. The gate
re-exports `latest_release_ref_argv` and `master_ref_argv` in its own `__all__`
— they are part of its published surface and callers import them from there.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    RELEASE_REPOSITORY_MASTER_REF,
    RELEASE_REPOSITORY_RELEASE_REF,
    RELEASE_REPOSITORY_URL,
)

__all__: list[str] = [
    "build_matches_ref",
    "executing_cache_build_id",
    "git_checkout_head",
    "latest_release_ref_argv",
    "master_ref_argv",
    "remote_ref_sha",
]

_PROBE_TIMEOUT_SECONDS = 60.0
_BUILD_ID_MINIMUM_LENGTH = 7
_BUILD_ID_MAXIMUM_LENGTH = 40
_HEX_DIGITS = frozenset("0123456789abcdef")


def latest_release_ref_argv() -> tuple[str, ...]:
    """Probe the newest installable release artifact.

    The repository and its ref come from the fleet-defaults module. They name
    THIS PLUGIN's own publishing identity rather than anything about the governed
    repository being dispatched -- but one of them is a bare default-branch name
    used as a ref, and the ratified fleet-toolchain-literal ban admits such a
    literal in exactly one module.
    """
    return ("git", "ls-remote", RELEASE_REPOSITORY_URL, RELEASE_REPOSITORY_RELEASE_REF)


def master_ref_argv() -> tuple[str, ...]:
    """Probe this plugin's own raw master, for the non-blocking unreleased-code warning."""
    return ("git", "ls-remote", RELEASE_REPOSITORY_URL, RELEASE_REPOSITORY_MASTER_REF)


def remote_ref_sha(*, runner: CommandRunner, argv: tuple[str, ...]) -> str | None:
    result = runner.run(
        argv=list(argv),
        cwd=Path.cwd(),
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    first = result.stdout.strip().split(maxsplit=1)
    return first[0] if first else None


def executing_cache_build_id(*, plugin_root: Path) -> str | None:
    """The flattened-cache build id, or None when the name is not a sha prefix."""
    name = plugin_root.name.strip()
    if not (_BUILD_ID_MINIMUM_LENGTH <= len(name) <= _BUILD_ID_MAXIMUM_LENGTH):
        return None
    return name if all(char in _HEX_DIGITS for char in name) else None


def build_matches_ref(*, build_id: str, ref_sha: str) -> bool:
    return ref_sha.startswith(build_id) or build_id.startswith(ref_sha)


def git_checkout_head(*, plugin_root: Path, runner: CommandRunner) -> str | None:
    result = runner.run(
        argv=["git", "-C", str(plugin_root), "rev-parse", "HEAD"],
        cwd=Path.cwd(),
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    sha = result.stdout.strip()
    return sha if sha else None
