"""Performing one provider-limit release: the hold, the record, and the claim.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127) gives the release four ordered steps "without a human": record
the hold the failure observed, journal one `provider-limit-release` record,
"release the item's dispatch claim and return it to `ready`, NOT to `blocked`
and with no `blocked_reason`", and "leave the item to the ordinary admission
valve".

IT IS THE PEER OF `dispose_stall_cancel`, and deliberately shaped like it: a
post-run disposition keyed off the terminal outcome, reached from
`post_run_dispositions`, fail-soft on every ledger write, and journaling its
own refusals rather than returning them. Read that module's docstring for why
a disposition that crashed would be worse than one that wrote a partial
record: the terminal is already final, so the item it was about to release is
stranded either way.

WHAT THIS MUST NOT DO IS AS LOAD-BEARING AS WHAT IT DOES. The clause says a
release "MUST NOT consume any budget of the three rework caps" and "MUST NOT
be surfaced as a needs-human decision", and none of that is enforced here --
it is enforced by the outcome's own STATUS, which matches none of the three
predicates that would do those things (`escalate_needs_human_block` on
`blocked`, `is_non_convergence_outcome` on `failed`, the acceptance valve on
`green`). So this module adds no guard against them and must not grow one: a
guard here would suggest the status alone is insufficient, and the next editor
would weaken the status.

THE ADMISSION POLICY IS LEFT ALONE, which is step four. The needs-human park
beside this one writes `admission_policy="manual"` precisely so no further
dispatch happens without a human; copying that write here would return the
item to `ready` and simultaneously make it undispatchable, a state that reads
healthy on the status alone. The release therefore goes through
`update_work_item_status` -- which touches status and assignee and nothing
else -- rather than through `update_work_item_blocked_state`.

REPLAY IS KEYED ON THE RELEASE, NOT ON THE ITEM. The clause makes each release
"idempotent and replayable by reconciliation, keyed by resolved factory, run,
and failing node attempt", so the journal is asked about THIS release's own
`release_key` rather than about the item's most recent anything. That is what
lets one item be released twice for two different runs -- which the cost
clause's "an item released twice for provider-limit failures" requires -- while
a replay of ONE release still completes exactly once.

THE TWO HOLDS ARE KEPT APART AND THEY ARE NOT INTERCHANGEABLE. `already-
released` says the release landed and nothing is owed. `newer-dispatch-claim`
says a release IS owed and cannot be taken now without damaging a live
dispatch: performing it would hand a running run's claim back to the queue,
and the row it wrote would be byte-identical to a correct first release, so
nothing downstream could tell the two apart. Both are journaled rather than
silent, because a replay that did nothing and said nothing is
indistinguishable from one that never ran.

THE HOLD IS INGESTED THROUGH THE SHARED LEDGER, which is what makes the
expiry un-refreshable by a replay: `ingest_hold_observation` dedupes on every
observation id the journal has EVER carried, and the id digests the release
key, so a replay mints the identical id and is declined. Nothing here compares
timestamps, and nothing here may start to.

A REFUSED HOLD STILL RELEASES THE ITEM. The release is what unblocks the
queue, and the hold is an audit copy of evidence the factory's own records
remain the authority for -- so holding the ledger transition hostage to it
would strand the item over a record nobody reads first. The refusal is
journaled rather than swallowed, because a hold that was never minted is
exactly what explains the next dispatch spending the same exhausted allowance.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import (
    ingest_hold_observation,
    read_acp_hold_ledger,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome import (
    PROVIDER_LIMIT_RELEASE_STATUS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records import (
    PROVIDER_LIMIT_RELEASE_STAGE,
    provider_limit_hold_record,
    provider_limit_release_record,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PROVIDER_LIMIT_RELEASE_HELD_STAGE",
    "PROVIDER_LIMIT_RELEASE_REFUSED_HOLD_STAGE",
    "dispose_provider_limit_release",
]

# The journal stage a replay appends when it declines to perform the release.
# Its own stage rather than a field on the release row, for the reason the
# stall release's own held stage gives: a reader asking "was this item
# released" must not match the row that says it deliberately was not.
PROVIDER_LIMIT_RELEASE_HELD_STAGE = "provider-limit-release-held"

# The journal stage a hold the writer REFUSED appends. Distinct from the
# observation stage so a hold ledger read can never mistake a refusal for a
# record, and distinct from the held stage above because this one concerns the
# audit copy while that one concerns the release itself.
PROVIDER_LIMIT_RELEASE_REFUSED_HOLD_STAGE = "acp-availability-observed-refused"

# The two reasons a release is held, each naming the reading that stopped it.
_HELD_ALREADY_RELEASED = "already-released"
_HELD_NEWER_DISPATCH_CLAIM = "newer-dispatch-claim"

# The journal stage a dispatch writes to announce itself. Spelled here rather
# than imported, because the writer keeps it private; this reading only needs
# to RECOGNISE the row, and the name is part of the ratified record set.
_DISPATCH_ID_STAGE = "dispatch-id"

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def dispose_provider_limit_release(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    now_iso: str,
) -> None:
    """Perform, or replay, the release this terminal owes.

    A no-op for every outcome that is not a provider-limit release, which is
    every green run, every ordinary failure and every human-gate park. BOTH
    the status and the carried release are required rather than either alone:
    the status is what the terminal mapper sets, the release is what carries
    the evidence, and an outcome with one and not the other is a build
    mismatch rather than a release to perform.
    """
    release = outcome.provider_limit_release
    if outcome.status != PROVIDER_LIMIT_RELEASE_STATUS or release is None:
        return
    held = _release_hold_reason(journal=journal, release=release, item_id=item.id)
    if held is not None:
        journal.append(
            record={
                "stage": PROVIDER_LIMIT_RELEASE_HELD_STAGE,
                "work_item_id": item.id,
                "release_key": release.release_key,
                "reason": held,
            }
        )
        return
    _record_hold(release=release, item_id=item.id, journal=journal, now_iso=now_iso)
    journal.append(record=provider_limit_release_record(release=release, work_item_id=item.id))
    _release_claim(repo=repo, item=item, journal=journal, release=release)


def _record_hold(
    *, release: ProviderLimitRelease, item_id: str, journal: JournalFile, now_iso: str
) -> None:
    """Append the hold this release observed, or journal why it could not be.

    `None` from the record builder is the LEGACY posture -- no entitlement was
    measured, so there is nothing a typed hold could be scoped by -- and it is
    silent because that is not a failure. A refusal STRING is a hold that could
    not be built from readable evidence, which is journaled.

    THE INGEST IS GUARDED BECAUSE THE SHARED LEDGER READ IS NOT, and that is a
    MEASURED gap rather than a defensive habit. `read_acp_hold_ledger` guards
    only `is_file()`, so a journal that exists and cannot be READ raises
    `OSError` straight out of it -- which escaped this disposition, stranded
    the item it was about to release, and contradicted this module's own
    fail-soft claim. The hold is an AUDIT copy of evidence the factory's own
    records remain the authority for, so degrading to "no hold recorded" is the
    right direction; stranding the item over that copy is not. The failure is
    journaled under the same refused-hold stage a builder refusal takes,
    because both answer the one question an operator asks afterwards: why did
    the next dispatch spend the same exhausted allowance.
    """
    record = provider_limit_hold_record(release=release, work_item_id=item_id, occurred_at=now_iso)
    if record is None:
        return
    ingested = (
        record
        if isinstance(record, str)
        else attempt(
            action=lambda: ingest_hold_observation(
                record=record,
                ledger=read_acp_hold_ledger(journal_path=journal.path, now_iso=now_iso),
                journal=journal,
            ),
            exceptions=(OSError,),
        )
    )
    reason = _unrecorded_hold_reason(ingested=ingested)
    if reason is None:
        return
    journal.append(
        record={
            "stage": PROVIDER_LIMIT_RELEASE_REFUSED_HOLD_STAGE,
            "work_item_id": item_id,
            "release_key": release.release_key,
            "reason": reason,
        }
    )


def _unrecorded_hold_reason(*, ingested: str | bool | AttemptFailure) -> str | None:
    """Why no hold was appended, or `None` when one was.

    Three inputs collapse to two answers: a builder REFUSAL and a failed
    LEDGER READ are both reasons, while a boolean is the ingest's own
    first-write-wins verdict -- and BOTH of its values mean the hold stands,
    `True` because this pass appended it and `False` because an earlier pass
    already had. A replay must not report an already-recorded hold as a
    failure to record one.
    """
    if isinstance(ingested, str):
        return ingested
    if isinstance(ingested, AttemptFailure):
        return f"the hold ledger could not be read: {type(ingested.error).__name__}"
    return None


def _release_claim(
    *, repo: Path, item: WorkItem, journal: JournalFile, release: ProviderLimitRelease
) -> None:
    """Return the item to `ready` with its dispatch claim dropped.

    Through the SAME seam the stall release and the pre-run release use --
    `status="ready"` with `clear_assignee=True` -- so three released items
    leave the ledger in one shape rather than three that merely look alike. A
    `ready` item carries no dispatcher blocked-reason label, so no reason has
    to be cleared: the item was `active`, which is a status the escalation seam
    never writes a reason onto.
    """
    released = attempt(
        action=lambda: update_work_item_status(
            path=store_config(repo=repo),
            item_id=item.id,
            status="ready",
            clear_assignee=True,
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(released, AttemptFailure):
        journal.append(
            record={
                "stage": f"{PROVIDER_LIMIT_RELEASE_STAGE}-error",
                "work_item_id": item.id,
                "release_key": release.release_key,
                "reason": type(released.error).__name__,
            }
        )


def _release_hold_reason(
    *, journal: JournalFile, release: ProviderLimitRelease, item_id: str
) -> str | None:
    """Why this release must not be performed now, if it must not.

    Keyed on the RELEASE rather than on the item, which is the clause's own
    key: the question is settled by what the journal recorded for THIS
    `factory:run:node attempt` triple, so one item released for two different
    runs is two independent releases while a replay of one of them is declined.

    A journal carrying no record of this release holds nothing, which keeps the
    fail-soft direction: without a prior record there is no "after" to read,
    and the dispatch most likely to have left the item stranded is exactly the
    one whose record went missing.
    """
    records = _journal_records(journal=journal)
    released_at = [
        index
        for index, record in enumerate(records)
        if _names_release(record=record, item_id=item_id, release=release)
    ]
    if not released_at:
        return None
    following = records[released_at[-1] + 1 :]
    if any(
        record.get("stage") == _DISPATCH_ID_STAGE and record.get("work_item_id") == item_id
        for record in following
    ):
        return _HELD_NEWER_DISPATCH_CLAIM
    return _HELD_ALREADY_RELEASED


def _names_release(
    *, record: Mapping[str, object], item_id: str, release: ProviderLimitRelease
) -> bool:
    """Whether this record is THIS release's own row, for THIS item."""
    return (
        record.get("stage") == PROVIDER_LIMIT_RELEASE_STAGE
        and record.get("work_item_id") == item_id
        and record.get("release_key") == release.release_key
    )


def _journal_records(*, journal: JournalFile) -> tuple[Mapping[str, object], ...]:
    """Every mapping record the journal holds, in append order.

    Append order is what the reading above depends on: it asks what the journal
    recorded AFTER a particular release. Every read failure yields the EMPTY
    tuple rather than raising, and a line that is not a mapping is dropped, for
    the same fail-soft reason the stall disposition gives -- a disposition that
    crashed on one truncated line would strand the item it was about to
    release.
    """
    read = attempt(action=lambda: journal.path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return ()
    parsed = attempt(
        action=lambda: [json.loads(line) for line in read.splitlines() if line],
        exceptions=(ValueError,),
    )
    if isinstance(parsed, AttemptFailure):
        return ()
    return tuple(
        cast("Mapping[str, object]", record) for record in parsed if isinstance(record, dict)
    )
