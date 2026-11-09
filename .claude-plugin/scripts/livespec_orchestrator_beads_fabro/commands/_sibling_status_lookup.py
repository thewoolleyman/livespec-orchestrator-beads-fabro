"""Orchestrator-side `sibling_status_lookup` for the readiness gate (qiqz6b).

The vendored `livespec_runtime` lifecycle layer (`lane_of` / `is_item_ready`)
resolves a `sibling_work_item` dependency through an OPTIONAL
`sibling_status_lookup(repo, work_item_id) -> RefStatus` callback. The runtime
deliberately ships NO such callback — a `runtime -> beads` read would be a
back-edge — so a cross-repo sibling dependency fails closed
(`UNKNOWN` -> BLOCK) until the orchestrator injects a real one. This module is
that injection: `make_sibling_status_lookup` builds a callable that resolves a
sibling `repo` slug to its host clone, reads that sibling tenant's LIVE
work-items via `load_items`, and maps the target item's status to a
`RefStatus`. The resolver accepts both the fetched fleet manifest and the
project's configured `.livespec.jsonc` `cross_repo_targets`, so a dispatch from
one fleet member can rely on explicitly configured siblings even when the core
fleet manifest lags behind. Only `done`/`closed` resolves `CLOSED` (and stops
blocking); every other live status resolves `OPEN`.

Fail-closed is the load-bearing invariant. Anything the lookup cannot resolve
definitively — a `repo` that is not a known fleet member, an unfetchable or
malformed fleet manifest, a clone directory that is missing or not a directory,
a `load_items` that raises against the sibling tenant, or a work-item id absent
from the sibling's ledger — returns `RefStatus.UNKNOWN`, which `_entry_blocks`
treats as BLOCKING for a `sibling_work_item` entry. Failing OPEN would re-open
the exact hole qiqz6b clause 1 closed (a still-open cross-repo blocker slipping
through as ready), so every unresolved path here MUST yield `UNKNOWN`, never
`CLOSED`.

The cross-tenant read lives entirely on the ORCHESTRATOR side — the
"orchestrator holds the beads client" half the runtime docstrings point at;
nothing here adds a `runtime -> beads` edge. Sibling clones are PARENT-DIR PEERS
of the orchestrator's own checkout (`project_root.parent / <repo>`), matching how
the dispatcher provisions sandbox sibling clones; no `/data/projects` is
hardcoded. The fleet-manifest fetch and every sibling `load_items` are LAZY
(deferred to the first actual resolution) and MEMOIZED per sibling repo, so a
command that resolves no sibling dependency pays nothing, and a ranking pass
over many items reads each sibling tenant at most once.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from livespec_runtime.cross_repo.types import CrossRepoManifest, CrossRepoTarget, RefStatus
from livespec_runtime.work_items.lifecycle import is_item_ready

from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import parse_fleet_members
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import groom_door_claimed
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones import (
    fetch_fleet_manifest_text,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "SiblingStatusLookup",
    "is_dispatch_candidate",
    "make_sibling_status_lookup",
    "sibling_dependency_diagnostics",
]


# The EXPECTED-error surface a single sibling-tenant read (`store_config` +
# `read_work_items`) can raise. Catching exactly this set — never a blanket
# `except` — keeps an unreachable / unconfigured / malformed sibling tenant
# fail-closed (`UNKNOWN`) instead of letting a substrate error crash the whole
# readiness enumeration.
_SIBLING_READ_ERRORS: tuple[type[Exception], ...] = (
    ConnectionPrefixMissingError,
    BeadsCredentialMissingError,
    BeadsConnectionError,
    BeadsTenantMissingError,
    BeadsCommandError,
    BeadsMappingError,
)

# The livespec `done` lane and the beads-native `closed` status both mean
# "resolved". `load_items` already maps beads `closed` -> `done` on read, so
# `closed` is belt-and-suspenders for any pre-normalization raw path.
_CLOSED_STATUSES: frozenset[str] = frozenset({"done", "closed"})

# Single-slot memo key for the once-computed fleet member -> clone-path map.
_MEMBERS_KEY = "members"


class SiblingStatusLookup(Protocol):
    def __call__(self, repo: str, work_item_id: str) -> RefStatus: ...

    def diagnostic(self, *, repo: str, work_item_id: str) -> str | None: ...


def make_sibling_status_lookup(*, project_root: Path) -> SiblingStatusLookup:
    """Build the orchestrator-side `sibling_status_lookup` for the readiness gate.

    `project_root` is the governed project's own checkout (each command resolves
    it from its `--repo` / `--project-root` argument or cwd). Fleet sibling
    clones are its PARENT-DIR PEERS (`project_root.parent / <repo>`). The
    returned callable is fail-closed and memoized (see the module docstring);
    pass the SAME instance to every `is_item_ready` / `lane_of` call in one
    command so each sibling tenant is read at most once per pass.
    """
    return _SiblingStatusLookup(
        project_root=project_root,
        clone_root=project_root.parent,
        manifest=load_manifest(project_root=project_root),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _SiblingStatusLookup:
    """Callable resolving `(repo, work_item_id)` to a fail-closed `RefStatus`.

    A callable class (not a closure) because the runtime invokes the callback
    POSITIONALLY — `sibling_status_lookup(repo, work_item_id)` — and only a
    `__call__` dunder may take positional parameters under the keyword-only-args
    rule. The two dict fields are lazily-populated memo caches: `_members_cache`
    holds the one computed member -> clone map, `_index_cache` holds each sibling
    repo's read-once work-item index (or `None` when that sibling was
    unresolvable).
    """

    project_root: Path
    clone_root: Path
    manifest: CrossRepoManifest
    _members_cache: dict[str, dict[str, Path]] = field(default_factory=dict)
    _index_cache: dict[str, dict[str, WorkItem] | None] = field(default_factory=dict)
    _diagnostic_cache: dict[tuple[str, str], str] = field(default_factory=dict)

    def __call__(self, repo: str, work_item_id: str) -> RefStatus:
        clone = self._member_clones().get(repo)
        if clone is None:
            self._record_diagnostic(
                repo=repo,
                work_item_id=work_item_id,
                message=f"no clone configured for {repo}:{work_item_id}",
            )
            return RefStatus.UNKNOWN
        index = self._sibling_index(repo=repo, clone=clone)
        if index is None:
            self._record_diagnostic(
                repo=repo,
                work_item_id=work_item_id,
                message=f"sibling tenant read failed for {repo}:{work_item_id}",
            )
            return RefStatus.UNKNOWN
        item = index.get(work_item_id)
        if item is None:
            self._record_diagnostic(
                repo=repo,
                work_item_id=work_item_id,
                message=f"{work_item_id} not found in {repo}",
            )
            return RefStatus.UNKNOWN
        self._clear_diagnostic(repo=repo, work_item_id=work_item_id)
        return RefStatus.CLOSED if item.status in _CLOSED_STATUSES else RefStatus.OPEN

    def diagnostic(self, *, repo: str, work_item_id: str) -> str | None:
        key = (repo, work_item_id)
        if key not in self._diagnostic_cache:
            _ = self(repo, work_item_id)
        return self._diagnostic_cache.get(key)

    def _record_diagnostic(self, *, repo: str, work_item_id: str, message: str) -> None:
        self._diagnostic_cache[(repo, work_item_id)] = message

    def _clear_diagnostic(self, *, repo: str, work_item_id: str) -> None:
        _ = self._diagnostic_cache.pop((repo, work_item_id), None)

    def _member_clones(self) -> dict[str, Path]:
        if _MEMBERS_KEY not in self._members_cache:
            self._members_cache[_MEMBERS_KEY] = self._compute_member_clones()
        return self._members_cache[_MEMBERS_KEY]

    def _compute_member_clones(self) -> dict[str, Path]:
        clones = self._fleet_member_clones()
        clones.update(
            {
                repo: _configured_clone(
                    project_root=self.project_root,
                    clone_root=self.clone_root,
                    repo=repo,
                    target=target,
                )
                for repo, target in self.manifest.targets.items()
            }
        )
        return clones

    def _fleet_member_clones(self) -> dict[str, Path]:
        manifest_text = fetch_fleet_manifest_text()
        if manifest_text is None:
            return {}
        members = parse_fleet_members(manifest_text=manifest_text)
        if members is None:
            return {}
        return {name: self.clone_root / name for name in members.repos}

    def _sibling_index(self, *, repo: str, clone: Path) -> dict[str, WorkItem] | None:
        if repo not in self._index_cache:
            self._index_cache[repo] = _load_sibling_index(clone=clone)
        return self._index_cache[repo]


def _load_sibling_index(*, clone: Path) -> dict[str, WorkItem] | None:
    if not clone.is_dir():
        return None
    loaded = attempt(action=lambda: load_items(repo=clone), exceptions=_SIBLING_READ_ERRORS)
    if isinstance(loaded, AttemptFailure):
        return None
    return {item.id: item for item in loaded}


def _configured_clone(
    *,
    project_root: Path,
    clone_root: Path,
    repo: str,
    target: CrossRepoTarget,
) -> Path:
    if target.local_clone is None:
        return clone_root / repo
    if target.local_clone.is_absolute():
        return target.local_clone
    return project_root / target.local_clone


def sibling_dependency_diagnostics(
    *,
    item: WorkItem,
    sibling_status_lookup: SiblingStatusLookup,
) -> tuple[str, ...]:
    diagnostics: list[str] = []
    for raw in item.depends_on:
        if not isinstance(raw, dict) or raw.get("kind") != "sibling_work_item":
            continue
        repo = raw.get("repo")
        work_item_id = raw.get("work_item_id")
        if not isinstance(repo, str) or not isinstance(work_item_id, str):
            continue
        if sibling_status_lookup(repo, work_item_id) != RefStatus.UNKNOWN:
            continue
        diagnostic = sibling_status_lookup.diagnostic(repo=repo, work_item_id=work_item_id)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return tuple(diagnostics)


def is_dispatch_candidate(
    *,
    item: WorkItem,
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None = None,
    repo: Path | None = None,
) -> bool:
    """Whether this row is one the Dispatcher may launch on this pass.

    Three members, and the third is the narrow one: a `ready` row, a
    `pending-approval` row whose dependencies are clear, and an `active` row
    the GROOM DOOR itself claimed and pinned. The door opens `backlog ->
    active` under a claim and a groom-variant pin and then returns, so without
    the third arm the row it prepared is one no launch path can pick up — it
    is not `ready`, so this predicate refused it, and the `--item` preflight
    that consumes this predicate read the door's own claim as somebody else's
    in-flight dispatch. `groom_door_claimed` owns that recognition, and it is
    scoped to the door's own claim: an ordinary `active` row is unaffected, so
    this is NOT a widening to `active` work in general. The status test that
    scopes it stays INSIDE that predicate rather than being restated as a guard
    here, so ONE module answers "is this the door's claim?" end to end.

    `repo` is the target repository the claim and pin are read against; it
    defaults, like `sibling_status_lookup`, to the working directory.
    """
    effective_repo = repo if repo is not None else Path.cwd()
    effective_sibling_status_lookup = (
        sibling_status_lookup
        if sibling_status_lookup is not None
        else make_sibling_status_lookup(project_root=effective_repo)
    )
    if is_item_ready(
        item=item,
        index=index,
        manifest=manifest,
        sibling_status_lookup=effective_sibling_status_lookup,
    ):
        return True
    if groom_door_claimed(repo=effective_repo, item=item):
        return True
    if item.status != "pending-approval":
        return False
    ready_projection = replace(item, status="ready")
    return is_item_ready(
        item=ready_projection,
        index=index,
        manifest=manifest,
        sibling_status_lookup=effective_sibling_status_lookup,
    )
