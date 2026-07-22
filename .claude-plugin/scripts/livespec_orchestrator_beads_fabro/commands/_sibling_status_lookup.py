"""Orchestrator-side `sibling_status_lookup` for the readiness gate (qiqz6b).

The vendored `livespec_runtime` lifecycle layer (`lane_of` / `is_item_ready`)
resolves a `sibling_work_item` dependency through an OPTIONAL
`sibling_status_lookup(repo, work_item_id) -> RefStatus` callback. The runtime
deliberately ships NO such callback — a `runtime -> beads` read would be a
back-edge — so a cross-repo sibling dependency fails closed
(`UNKNOWN` -> BLOCK) until the orchestrator injects a real one. This module is
that injection: `make_sibling_status_lookup` builds a callable that resolves a
fleet sibling's `repo` slug to its host clone, reads that sibling tenant's LIVE
work-items via `load_items`, and maps the target item's status to a
`RefStatus`. Only `done`/`closed` resolves `CLOSED` (and stops blocking); every
other live status resolves `OPEN`.

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
from dataclasses import dataclass, field
from pathlib import Path

from livespec_runtime.cross_repo.types import RefStatus

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import parse_fleet_members
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

__all__: list[str] = ["make_sibling_status_lookup"]


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


def make_sibling_status_lookup(*, project_root: Path) -> Callable[[str, str], RefStatus]:
    """Build the orchestrator-side `sibling_status_lookup` for the readiness gate.

    `project_root` is the governed project's own checkout (each command resolves
    it from its `--repo` / `--project-root` argument or cwd). Fleet sibling
    clones are its PARENT-DIR PEERS (`project_root.parent / <repo>`). The
    returned callable is fail-closed and memoized (see the module docstring);
    pass the SAME instance to every `is_item_ready` / `lane_of` call in one
    command so each sibling tenant is read at most once per pass.
    """
    return _SiblingStatusLookup(clone_root=project_root.parent)


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

    clone_root: Path
    _members_cache: dict[str, dict[str, Path]] = field(default_factory=dict)
    _index_cache: dict[str, dict[str, WorkItem] | None] = field(default_factory=dict)

    def __call__(self, repo: str, work_item_id: str) -> RefStatus:
        clone = self._member_clones().get(repo)
        if clone is None:
            return RefStatus.UNKNOWN
        index = self._sibling_index(repo=repo, clone=clone)
        if index is None:
            return RefStatus.UNKNOWN
        item = index.get(work_item_id)
        if item is None:
            return RefStatus.UNKNOWN
        return RefStatus.CLOSED if item.status in _CLOSED_STATUSES else RefStatus.OPEN

    def _member_clones(self) -> dict[str, Path]:
        if _MEMBERS_KEY not in self._members_cache:
            self._members_cache[_MEMBERS_KEY] = self._compute_member_clones()
        return self._members_cache[_MEMBERS_KEY]

    def _compute_member_clones(self) -> dict[str, Path]:
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
