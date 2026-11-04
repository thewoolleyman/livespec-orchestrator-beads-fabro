"""Writing the dispatch CLAIM stamp at the two moments a dispatch learns something.

`_store_dispatch_claim` owns the stamp VALUE and its one writer. This owns the
two PRODUCTION moments that write it, and they are not interchangeable:
admission knows the dispatch, the host and the factory but no run, and the
launch watch learns the run id some seconds later. Both write the whole key,
because `bd update --metadata` replaces a nested object wholesale — so a write
of "just the run id" would destroy the host the recovery fence reads.

THE PENDING WRITE PRECEDES THE `ready -> active` TRANSITION, and that order is
the whole point of having a pending stamp at all. An item released by a human
valve and admitted again still carries the PREVIOUS dispatch's run id, which
the factory now reports absent; a reconciler reading that row releases a LIVE
dispatch's claim. Stamping before the transition leaves no instant in which the
row is `active` under this dispatch while still naming the previous run — the
reading is `attribution-pending` from the first moment the claim exists.

THE RUN WRITE PRESERVES THE DISPATCH ID RATHER THAN RE-DERIVING IT. The launch
watch does not carry the dispatch id, and the four facts are only meaningful as
a set: a run id beside no dispatch is a stamp that reads as authoritative while
answering less than the one it replaced. So the existing stamp is read and its
dispatch id carried forward. An unreadable prior stamp leaves the field `None`
rather than failing the write, because the host and the run are what the
grading needs and the dispatch id is an audit convenience.

EVERY WRITE IS FAIL-OPEN AND NONE OF THEM IS FAIL-SILENT. A beads hiccup must
not refuse an admission or kill a run that is already doing the work — the run
is the expensive thing — but a fail-open write that says nothing is how a blind
spot hides. So each attempt journals a record carrying `claim_stamped` and, on
a failure, the CAUSE: "this dispatch has no claim stamp" becomes a queryable
state rather than an absence, and the two causes have different remedies. An
unresolvable `.livespec.jsonc` is a governed-repository misconfiguration a
human fixes; a beads fault may already have cleared.

THE CONSEQUENCE OF AN UNWRITTEN STAMP IS A HELD CLAIM, NEVER A RELEASED ONE,
which is what makes fail-open safe here rather than merely convenient. An
unstamped row grades `claim-unattributable` and a pending one grades
`attribution-pending`; both are holds. The dangerous direction — a row whose
stamp names a run this dispatch has moved off — is exactly what the pending
write removes, so a failure to write it leaves the previous reading standing
rather than inventing a worse one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    claim_row_for,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatching_host import (
    dispatching_host,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    unrecorded_dispatch_factory_target,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "PENDING_CLAIM_STAMP_STAGE",
    "RUN_CLAIM_STAMP_STAGE",
    "stamp_pending_claim",
    "stamp_run_claim",
]

# One stage per MOMENT rather than one shared stage with a mode field: the two
# answer different questions of the journal — "was this admission's claim
# attributable at all" and "did the claim learn its run" — and a reader
# filtering on one must not have to exclude the other.
PENDING_CLAIM_STAMP_STAGE = "dispatch-claim-stamp-pending"
RUN_CLAIM_STAMP_STAGE = "dispatch-claim-stamp-run"

# The EXPECTED faults either write degrades through: an id the tenant does not
# hold, a connection it cannot resolve, a mapping it cannot apply, and the two
# CONFIGURATION faults `store_config` raises before any row is touched. A bug
# still raises, exactly as it does on the run-stamp path.
_STAMP_FAULTS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


def stamp_pending_claim(
    *,
    repo: Path,
    work_item_id: str,
    dispatch_id: str,
    journal: JournalWriter,
    resume: bool = False,
    explicit_factory: str | None = None,
) -> None:
    """Replace this item's claim stamp with one naming THIS dispatch and no run.

    The factory is resolved under the WHOLE dispatch precedence, so the name
    this stamp carries is the name the dispatch is routed to. The ORDER of its
    layers is the resolution's own and is not restated here — a second order
    would stamp the row with a factory the run never runs on, which the
    reconcile pass then holds the claim against while reporting the stamp
    faithfully.

    `resume` is this item's assigned ROUTE, which the clause makes an input of
    the stamp rather than of the dispatch alone: "The admission claim stamp MUST
    apply the same order, using the route recovery routing assigned before the
    admission valve, so a fresh dispatch is stamped with the factory it will
    reach and a resume with the factory selected by that same order." It is what
    decides whether the item's recorded factory is a layer at all, and it
    defaults to the FRESH answer, which is what every dispatch is unless routing
    says otherwise.

    `explicit_factory` is the TOP layer, the `--factory` flag's name, and it
    arrives as an argument because admission holds no `argparse.Namespace` to
    read it out of. It is the one layer the environment variable cannot stand
    in for: an operator who types the flag has routed THIS dispatch and nothing
    in the item's own history says so. `None` means this invocation named no
    factory, which is the ordinary case and is not a default standing in for an
    unread flag — every dispatch path reads the flag and passes what it found.

    What the field must not be is ABSENT: a stamp naming no factory grades
    `claim-unattributable`, whose remedy is "this factory is no longer
    declared" rather than the move valve this state actually needs.
    """
    detail = _attempted(
        action=lambda: _write_pending_stamp(
            repo=repo,
            work_item_id=work_item_id,
            dispatch_id=dispatch_id,
            resume=resume,
            explicit_factory=explicit_factory,
        )
    )
    journal.append(
        record={
            "work_item_id": work_item_id,
            "stage": PENDING_CLAIM_STAMP_STAGE,
            "dispatch_id": dispatch_id,
            "claim_stamped": detail is None,
            "claim_stamp_failure_detail": detail,
        }
    )


def stamp_run_claim(
    *,
    repo: Path,
    work_item_id: str,
    run_id: str,
    factory_name: str,
    factory_server: str | None,
    journal: JournalWriter,
) -> None:
    """Fill this item's claim stamp in with the run the dispatch just learned.

    The factory is taken from the LAUNCH rather than re-resolved, because this
    is the factory the run was actually submitted to and a second resolution
    could answer differently from the one that placed the work.
    """
    detail = _attempted(
        action=lambda: _write_run_stamp(
            repo=repo,
            work_item_id=work_item_id,
            run_id=run_id,
            factory_name=factory_name,
            factory_server=factory_server,
        )
    )
    journal.append(
        record={
            "work_item_id": work_item_id,
            "stage": RUN_CLAIM_STAMP_STAGE,
            "run_id": run_id,
            "claim_stamped": detail is None,
            "claim_stamp_failure_detail": detail,
        }
    )


def _write_pending_stamp(
    *,
    repo: Path,
    work_item_id: str,
    dispatch_id: str,
    resume: bool,
    explicit_factory: str | None,
) -> None:
    """The admission-moment write. Reads no prior stamp: it replaces one wholesale."""
    target = unrecorded_dispatch_factory_target(
        repo=repo, work_item_id=work_item_id, resume=resume, explicit=explicit_factory
    )
    record_claim_stamp(
        path=store_config(repo=repo),
        work_item_id=work_item_id,
        stamp=ClaimStamp(
            dispatch_id=dispatch_id,
            dispatching_host=dispatching_host(),
            run_id=None,
            factory_name=target.name,
            factory_server=target.server,
        ),
    )


def _write_run_stamp(
    *,
    repo: Path,
    work_item_id: str,
    run_id: str,
    factory_name: str,
    factory_server: str | None,
) -> None:
    """The run-learned write, carrying the admission stamp's dispatch id forward."""
    config = store_config(repo=repo)
    existing = claim_row_for(path=config, work_item_id=work_item_id).stamp
    record_claim_stamp(
        path=config,
        work_item_id=work_item_id,
        stamp=ClaimStamp(
            dispatch_id=None if existing is None else existing.dispatch_id,
            dispatching_host=dispatching_host(),
            run_id=run_id,
            factory_name=factory_name,
            factory_server=factory_server,
        ),
    )


def _attempted(*, action: Callable[[], None]) -> str | None:
    """WHY no claim stamp was written, or None when the write landed."""
    written = attempt(action=action, exceptions=_STAMP_FAULTS)
    if isinstance(written, AttemptFailure):
        return f"claim stamp write raised {type(written.error).__name__}: {written.error}"
    return None
