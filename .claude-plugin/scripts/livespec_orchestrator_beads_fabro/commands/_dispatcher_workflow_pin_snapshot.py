"""One snapshot-wide read of every item's recorded `dispatch_workflow` pin.

WHY THE PIN IS READ FROM A SNAPSHOT. The pre-dispatch acceptance-criteria wall
asks, for every candidate it grades, which workflow variant the dispatch would
run, and the recorded `dispatch_workflow` metadata is the second step of that
precedence. Read per item that costs one guarded `bd show`, and the
needs-attention gathers that consume the shared eligibility decision graded
hundreds of items per snapshot (335 measured on the orchestrator tenant,
about 650 s) for a value the tenant's own `bd list` records already carry.
Inside `workflow_pin_snapshot_scope` the pin is taken from ONE list read per
repository instead, through the same `dispatch_workflow_from_record` reading a
per-item read uses, so the two cannot disagree about what a record pins.

A CONTEXT rather than a parameter on every wall signature, for the reason
`needs_human_snapshot_scope` gives: the decision's callers keep the keyword
shape their seams and tests bind, and a lone caller outside any scope still
takes the per-item read, which is correct and merely slow.

EVERY FAULT DEGRADES TO THE PER-ITEM READ. A list that cannot be read answers
`None`, which sends the caller back to `bd show`, whose own failure the wall
already resolves toward the ARMED `implement` side. The snapshot therefore can
never turn an environment fault into an exemption.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_dispatch_workflow import dispatch_workflows_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

__all__: list[str] = [
    "PREVIEW_UNRESOLVABLE_FAULTS",
    "snapshot_pins",
    "workflow_pin_snapshot_scope",
]

# Every EXPECTED way a workflow-variant read can fail to reach an answer,
# enumerated rather than caught broadly: each of these is an environment or
# configuration fault, and none of them is evidence about the variant. A bug
# still raises.
PREVIEW_UNRESOLVABLE_FAULTS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
    OSError,
)

_PinMap = Mapping[str, str | None]

# Per-repository cache for the active scope: a repository that could not be
# read is cached as None so a fault costs one failed read, not one per item.
_SCOPE: ContextVar[dict[Path, _PinMap | None] | None] = ContextVar(
    "workflow_pin_snapshot", default=None
)


@contextmanager
def workflow_pin_snapshot_scope() -> Iterator[None]:
    """Serve every workflow-pin read inside the block from one list per repository.

    Re-entrant: a nested scope joins the enclosing one, so a gather that opens
    its own scope inside the composer's shares the composer's reads.
    """
    if _SCOPE.get() is not None:
        yield
        return
    token = _SCOPE.set({})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def snapshot_pins(*, repo: Path) -> _PinMap | None:
    """The repository's id -> recorded workflow map, or None when there is none.

    None means "no snapshot to consult": no enclosing scope, or the repository's
    list could not be read. An item absent from a returned map was not in the
    snapshot, which is distinct from an item present with no pin.
    """
    cache = _SCOPE.get()
    if cache is None:
        return None
    key = repo.resolve()
    if key not in cache:
        read = attempt(
            action=lambda: dispatch_workflows_for(path=store_config(repo=repo)),
            exceptions=PREVIEW_UNRESOLVABLE_FAULTS,
        )
        cache[key] = None if isinstance(read, AttemptFailure) else read
    return cache[key]
