"""The token-guarded equivalents of the store's claim writers.

`_dispatcher_claim_writes` decides WHETHER a Dispatcher claim write is guarded.
This module is what a guarded write sends. The claim-token protocol allows the
winner one ledger write, and `change_claim` is that write, so a guarded
transition cannot pass through `update_work_item_status` or
`update_work_item_blocked_state`: it has to carry what they carry.

So the status mapping, the `rework:pending` and `blocked-reason:` label
removals and the ready-dwell instant of `update_work_item_status` are rebuilt
here. The blocked rest is one write, not the store's two, and its additions
and removals are kept DISJOINT: a label named in both is removed by the very
write that was meant to add it.

Every function answers `None` when its write landed and the protocol's own
outcome name when it did not (`claim-changed`, `claim-unobservable`,
`claim-lease-expired`, `claim-transition-pending`, `claim-token-missing`). A
refused writer has written nothing to the item. Ledger faults still raise.

THE TOKEN ALONE DOES NOT RE-CHECK THE CALLER'S DECISION, SO EVERY WRITE STATES
IT. `change_claim` reads the item's current token when it is called, later than
the caller's own read of the item. Winning that token excludes a writer racing
on it and nothing more: two writers that decided on one read and write one
AFTER the other would both win, the second taking the successor the first
named. So each guarded write here carries `still_as_decided`, a predicate over
the item record `change_claim` reads with the token. It states what the
caller's decision rested on, and a write whose predicate no longer holds writes
nothing and reports `claim-changed`.

The predicate builders live here, beside the writes, so a call site states its
decision in one line:

- `status_is` — the item still rests at the status the caller decided on;
- `held` — that status and that assignee;
- `claimed_by_run` — that status and assignee, and a claim stamp naming the
  run the decision was about;
- `terminal_claim` — the form a Dispatcher terminal disposition of one item
  and one run uses;
- `learning_run` and `same_claim_row` — the two run-stamp writers.

A PENDING OR ABSENT CLAIM STAMP IS NOT EVIDENCE OF ANOTHER RUN. A recovery
requires the stamp to NAME its run, as its own re-read always has. A terminal
disposition does not (`unstamped_ok`): the run stamp is fail-open, so a claim
whose stamp never landed is still the dispatch's own, and requiring the stamp
would turn one ledger fault at stamp time into a claim no disposition can ever
write. What it refuses on is a stamp naming a DIFFERENT run, or a status or
assignee that moved. The residual is a newer dispatch's own pending stamp,
which a terminal disposition cannot tell from its own because its outcome
carries no dispatch id.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord, make_beads_client
from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    LABEL_BLOCKED_REASON_PREFIX,
    blocked_reason_label_removals,
    blocked_reason_labels,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimRow,
    change_claim,
    claim_row_from_record,
    claim_stamp_from_record,
)
from livespec_orchestrator_beads_fabro._store_ready_dwell import (
    ready_transition_metadata,
    utc_now_iso,
)
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    rework_pending_label_removals,
)
from livespec_orchestrator_beads_fabro._store_statuses import beads_status_for
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "TRANSITION_OBSERVATIONS",
    "Decided",
    "claimed_by_run",
    "guarded_blocked_write",
    "guarded_hold",
    "guarded_metadata_write",
    "guarded_status_write",
    "guarded_write",
    "held",
    "learning_run",
    "same_claim_row",
    "status_is",
    "terminal_claim",
]

# What a claim writer's decision rested on, asked of the item record its
# token-guarded write is based on.
Decided = Callable[[BeadsRecord], bool]

# This process's first sightings of an unapplied transition, keyed as
# `change_claim` keys them. The takeover wait is measured from a writer's own
# first observation to a later fresh read, so the sighting has to outlive one
# call: a Dispatcher loop that meets the same stranded transition on a later
# pass takes it over, and a one-shot invocation reports it pending.
TRANSITION_OBSERVATIONS: dict[tuple[str, str, str], float] = {}

_APPLIED = "applied"
_CLAIM_CHANGED = "claim-changed"
_ACTIVE_STATUS = "active"
_READY_STATUS = "ready"
_BLOCKED_STATUS = "blocked"
_LABEL_ADMISSION = "admission:"
_ADMISSION_POLICIES = ("auto", "manual")


def status_is(*, status: str) -> Decided:
    """The item still rests at `status`, in the spelling the ledger stores it."""
    stored = beads_status_for(status=status)
    return lambda record: record.get("status") == stored


def held(*, status: str, assignee: str | None) -> Decided:
    """The item still rests at `status` and is still assigned to `assignee`."""
    resting = status_is(status=status)
    holder = assignee or None
    return lambda record: resting(record) and (record.get("assignee") or None) == holder


def claimed_by_run(
    *,
    assignee: str | None,
    run_id: str | None,
    status: str = _ACTIVE_STATUS,
    unstamped_ok: bool = False,
) -> Decided:
    """The item is still held as decided, and its claim stamp names `run_id`.

    A `run_id` of `None` is a decision about no particular run, which asks
    nothing of the stamp. `unstamped_ok` accepts a claim whose stamp is absent
    or still pending; a stamp naming a different run is refused either way.
    """
    holding = held(status=status, assignee=assignee)
    return lambda record: holding(record) and _names_run(
        record=record, run_id=run_id, unstamped_ok=unstamped_ok
    )


def terminal_claim(*, item: WorkItem, run_id: str | None) -> Decided:
    """The claim a terminal disposition of `item` under `run_id` decided on.

    The item's status and assignee as the disposition was handed them, and a
    claim stamp that does not name another run.
    """
    return claimed_by_run(
        assignee=item.assignee, run_id=run_id, status=item.status, unstamped_ok=True
    )


def learning_run(*, dispatch_id: str | None, run_id: str) -> Decided:
    """The claim a dispatch that just learned `run_id` stamps that run onto.

    Still `active`, and stamped by nothing that contradicts this dispatch: no
    stamp at all, this run already, this dispatch's own stamp, or a pending
    stamp when either dispatch id is unknown.
    """
    active = status_is(status=_ACTIVE_STATUS)
    return lambda record: active(record) and _is_dispatch(
        record=record, dispatch_id=dispatch_id, run_id=run_id
    )


def same_claim_row(*, row: ClaimRow) -> Decided:
    """The item is `active` and its claim row is still the one the caller read."""
    return lambda record: (
        row.status == _ACTIVE_STATUS and claim_row_from_record(record=record) == row
    )


def _names_run(*, record: BeadsRecord, run_id: str | None, unstamped_ok: bool) -> bool:
    if run_id is None:
        return True
    stamp = claim_stamp_from_record(record=record)
    if stamp is None or stamp.pending:
        return unstamped_ok
    return stamp.run_id == run_id


def _is_dispatch(*, record: BeadsRecord, dispatch_id: str | None, run_id: str) -> bool:
    stamp = claim_stamp_from_record(record=record)
    if stamp is None or stamp.run_id == run_id:
        return True
    if dispatch_id is None or stamp.dispatch_id is None:
        return stamp.pending
    return stamp.dispatch_id == dispatch_id


def guarded_status_write(  # noqa: PLR0913 — kw-only; mirrors the store's status writer.
    *,
    path: StoreConfig,
    item_id: str,
    status: str,
    intent: str,
    writer: str,
    assignee: str | None = None,
    clear_assignee: bool = False,
    metadata: dict[str, Any] | None = None,
    still_as_decided: Decided | None = None,
) -> str | None:
    """The token-guarded equivalent of `update_work_item_status`, in one write.

    `metadata` is an overlay of top-level keys that must land with the
    transition and nowhere else, which is how admission's pending claim stamp
    reaches the row only when the admission wins.
    """
    overlay = dict(metadata) if metadata is not None else {}
    if status == _READY_STATUS:
        overlay = ready_transition_metadata(existing_metadata=overlay, now_iso=utc_now_iso())
    removals = rework_pending_label_removals(status=status) + blocked_reason_label_removals(
        status=status
    )
    return guarded_write(
        path=path,
        item_id=item_id,
        writer=writer,
        intent=intent,
        status=beads_status_for(status=status),
        assignee=assignee,
        clear_assignee=clear_assignee,
        remove_labels=removals or None,
        metadata=overlay or None,
        still_as_decided=still_as_decided,
    )


def guarded_blocked_write(  # noqa: PLR0913 — kw-only; mirrors the store's blocked-state writer.
    *,
    path: StoreConfig,
    item_id: str,
    blocked_reason: str,
    intent: str,
    writer: str,
    admission_policy: str | None = None,
    metadata: dict[str, Any] | None = None,
    still_as_decided: Decided | None = None,
) -> str | None:
    """The token-guarded equivalent of the `blocked` rest, in ONE write.

    `metadata` is an overlay of top-level keys that must land with the rest and
    nowhere else, as it is for `guarded_status_write`.
    """
    add_labels = [f"{LABEL_BLOCKED_REASON_PREFIX}{blocked_reason}"]
    removable = blocked_reason_labels() + rework_pending_label_removals(status=_BLOCKED_STATUS)
    if admission_policy is not None:
        add_labels.append(f"{_LABEL_ADMISSION}{admission_policy}")
        removable.extend(f"{_LABEL_ADMISSION}{value}" for value in _ADMISSION_POLICIES)
    return guarded_write(
        path=path,
        item_id=item_id,
        writer=writer,
        intent=intent,
        status=_BLOCKED_STATUS,
        add_labels=add_labels,
        remove_labels=[label for label in removable if label not in add_labels],
        metadata=metadata,
        still_as_decided=still_as_decided,
    )


def guarded_hold(
    *,
    path: StoreConfig,
    item_id: str,
    intent: str,
    writer: str,
    still_as_decided: Decided | None = None,
) -> str | None:
    """Win the item's token and name its successor, changing nothing else.

    `bd close` is its own verb, so a close cannot name a successor in the write
    that closes. The winner names its successor in this write and closes
    immediately after it.

    THE CLOSE IS NOT FENCED BY THE TOKEN, SO THE HOLD RE-READS BEFORE IT
    ANSWERS. The successor this write names is open, and a status write that
    wins it between this write and the caller's close is the next legitimate
    write under the protocol; an unconditional `bd close` would land over it.
    So the item is read again immediately before the hold answers, and a hold
    whose successor is no longer the item's current token answers
    `claim-changed`: the later winner's write stands and the caller closes
    nothing. What remains is the same residual the protocol accepts for every
    guarded write, a write applied between a re-read and the write it guards.
    """
    client = make_beads_client(config=path)
    result = change_claim(
        client=client,
        work_item_id=item_id,
        writer=writer,
        intent=intent,
        claim_tokens=True,
        transition_observations=TRANSITION_OBSERVATIONS,
        still_as_decided=still_as_decided,
    )
    if result.outcome != _APPLIED:
        return result.outcome
    metadata = client.show_issue(issue_id=item_id).get("metadata")
    named = cast("dict[str, object]", metadata) if isinstance(metadata, dict) else {}
    current = named.get(CLAIM_TOKEN_METADATA_KEY)
    return None if current == result.successor_token_id else _CLAIM_CHANGED


def guarded_metadata_write(
    *,
    path: StoreConfig,
    item_id: str,
    intent: str,
    writer: str,
    metadata: dict[str, Any],
    still_as_decided: Decided | None = None,
) -> str | None:
    """Win the item's token, then land `metadata` and the successor in ONE write.

    The token-guarded form of a run stamp. A run stamp is a claim-changing
    write, and the store's stamp writers read the whole metadata object, add
    their keys and send the whole object back, the token key included. Sent
    after another writer won the token, that puts a CLOSED token id back on the
    item. Here the overlay is merged over the item as it was read with its
    current token, and nothing is written unless that token is won.
    """
    return guarded_write(
        path=path,
        item_id=item_id,
        writer=writer,
        intent=intent,
        metadata=metadata,
        still_as_decided=still_as_decided,
    )


def guarded_write(
    *,
    path: StoreConfig,
    item_id: str,
    writer: str,
    intent: str,
    still_as_decided: Decided | None = None,
    **update: Any,
) -> str | None:
    """One `change_claim`; `None` when applied, else its outcome name.

    The primitive every function above is built on, public for a claim writer
    whose write is none of those shapes. `update` is `change_claim`'s own field
    set (`status`, `assignee`, `clear_assignee`, `add_labels`, `remove_labels`,
    `metadata`), sent exactly as given: no status mapping, label removal or
    ready-dwell instant is added here, so a caller that needs what a store
    writer adds must send it. `still_as_decided` is `change_claim`'s parameter
    of that name, passed through.
    """
    result = change_claim(
        client=make_beads_client(config=path),
        work_item_id=item_id,
        writer=writer,
        intent=intent,
        claim_tokens=True,
        transition_observations=TRANSITION_OBSERVATIONS,
        still_as_decided=still_as_decided,
        **update,
    )
    return None if result.outcome == _APPLIED else result.outcome
