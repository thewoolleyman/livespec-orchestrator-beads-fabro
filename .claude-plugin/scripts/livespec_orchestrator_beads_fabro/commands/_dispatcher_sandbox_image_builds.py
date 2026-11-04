"""WHICH plugin builds are executing on this host, for the sandbox-image enumeration.

The executing-build set is HOST-WIDE, and it is not the registered-install set:
a Claude Code session binds its plugin root once at session start and a
Dispatcher loop runs the build it started with, so the build a dispatch reads
its bundled run config out of may be one the registry replaced weeks ago. Three
routes therefore reach a build, and the set is their UNION: the build each
enumerated repository's install record names, every plugin-cache build holding
an `.in_use` lease whose recorded process is alive, and the payload of every
running Dispatcher process.

A BUILD REACHED BY MORE THAN ONE ROUTE IS ENUMERATED ONCE, and a build reached
ONLY through a lease whose process has exited is not enumerated at all — while
the same build reached by any other route still is. That asymmetry is the whole
content of the lease rule: a lease is evidence about a SESSION, so a dead
session's lease is evidence of nothing, and treating it as a route would make
every build any session ever bound look like one a dispatch could still read.

LIVENESS IS THE EXISTENCE OF THE RECORDED PID'S `/proc` ENTRY, and deliberately
not a comparison against the start time the lease also records. The lease file's
own encoding is Claude Code's, not a contract this read may assume, so parsing
it would make a format change here read as a host with no live sessions. The
cost of the weaker reading is bounded and lands in the harmless direction: a
RECYCLED pid can only make a dead session's build look live, which enumerates
one extra tag for a warm timer to hold, where the opposite error would leave
a tag a live dispatch needs unheld.

BOTH HOST TREES ARE READ ONLY, and never written: `rglob`, `iterdir` and
`read_bytes` are the whole surface. The clause forbids this command from
creating, modifying or deleting any file INCLUDING a lease file, which holds
structurally here rather than carefully — there is no write call in the module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images import BuildRoot
from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
    read_build_version,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "BuildDiscoveryRoots",
    "default_build_discovery_roots",
    "executing_builds",
]

# The lease directory each plugin-cache build carries, holding one file per
# session that has bound that build, named by the holding process id.
_LEASE_DIRECTORY = ".in_use"

# The ONE entry point every Dispatcher invocation runs through, as the trailing
# path segments its own argv carries. Keyed on the argv rather than on an
# environment variable because the launcher exports its payload root only when
# it has copied a release aside: a Dispatcher started from an installed build or
# a source checkout exports nothing, so an environ scan would report a host with
# no running Dispatcher at all while several were executing.
_DISPATCHER_ENTRY_SUBPATH = ("scripts", "bin", "dispatcher.py")


@dataclass(frozen=True, kw_only=True)
class BuildDiscoveryRoots:
    """The two host trees build discovery reads, injected so both can be exercised."""

    plugin_cache: Path
    proc: Path


def executing_builds(
    *, install_paths: tuple[Path, ...], roots: BuildDiscoveryRoots
) -> tuple[BuildRoot, ...]:
    """Every build executing on this host, each enumerated exactly once.

    The routes are consulted in the order the clause states them, and the
    deduplication keeps the FIRST reach of each build, so a build that is both
    registered and leased reports under one entry rather than two.
    """
    return _deduplicated(
        reached=(
            *install_paths,
            *_leased_builds(plugin_cache=roots.plugin_cache, proc=roots.proc),
            *_dispatcher_payloads(proc=roots.proc),
        )
    )


def default_build_discovery_roots() -> BuildDiscoveryRoots:  # pragma: no cover
    """The production trees under the real HOME and the real kernel (integration-covered)."""
    return BuildDiscoveryRoots(
        plugin_cache=Path.home() / ".claude" / "plugins" / "cache",
        proc=Path("/proc"),
    )


def _leased_builds(*, plugin_cache: Path, proc: Path) -> tuple[Path, ...]:
    if not plugin_cache.is_dir():
        return ()
    return tuple(
        lease_directory.parent
        for lease_directory in sorted(plugin_cache.rglob(_LEASE_DIRECTORY))
        if lease_directory.is_dir() and _holds_a_live_lease(lease=lease_directory, proc=proc)
    )


def _holds_a_live_lease(*, lease: Path, proc: Path) -> bool:
    return any(
        held.name.isdecimal() and (proc / held.name).exists() for held in sorted(lease.iterdir())
    )


def _dispatcher_payloads(*, proc: Path) -> tuple[Path, ...]:
    if not proc.is_dir():
        return ()
    payloads: list[Path] = []
    for entry in sorted(proc.iterdir()):
        payload = (
            _payload_of(argv=_argv_of(cmdline=entry / "cmdline"))
            if entry.name.isdecimal()
            else None
        )
        if payload is not None:
            payloads.append(payload)
    return tuple(payloads)


def _argv_of(*, cmdline: Path) -> tuple[str, ...]:
    """One process's argv, or an empty one for a pid that has since gone.

    A read failure is an EMPTY argv rather than a refusal, because a `/proc`
    scan races the processes it is scanning: an entry listed a moment ago may
    have exited before its `cmdline` is opened, and that is an ordinary reading
    of a host rather than a fault in it.
    """
    raw = attempt(action=lambda: cmdline.read_bytes(), exceptions=(OSError,))
    if isinstance(raw, AttemptFailure):
        return ()
    return tuple(token for token in raw.decode("utf-8", errors="replace").split("\0") if token)


def _payload_of(*, argv: tuple[str, ...]) -> Path | None:
    """The payload root a running Dispatcher executes from, read off its own argv."""
    depth = len(_DISPATCHER_ENTRY_SUBPATH)
    for token in argv:
        candidate = Path(token)
        if candidate.parts[-depth:] == _DISPATCHER_ENTRY_SUBPATH:
            return candidate.parents[depth - 1]
    return None


def _deduplicated(*, reached: tuple[Path, ...]) -> tuple[BuildRoot, ...]:
    seen: set[Path] = set()
    builds: list[BuildRoot] = []
    for root in reached:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            builds.append(BuildRoot(identity=_identity(root=resolved), root=resolved))
    return tuple(builds)


def _identity(*, root: Path) -> str:
    """The build's identity: its declared manifest version, else its directory name.

    A build whose manifest does not parse falls back to the directory name
    rather than to a null, because every entry this identity labels has to be
    attributable to SOME build — two bundled entries carrying no identity are
    indistinguishable at the surface a warm timer reads, which is precisely the
    question this enumeration exists to answer.
    """
    version = read_build_version(install_path=root)
    return root.name if version is None else version
