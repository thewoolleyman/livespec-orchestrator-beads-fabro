"""The pre-dispatch retry-discipline guard: refuse a re-dispatch that names no change.

The READER half of the retry record, and the FIRST refusal of the pre-dispatch
wall. Its position there is load-bearing in both directions. It must run before
any refusal that could WRITE a signature of its own, or an armed item would be
re-signed by a later gate and the refusal would then quote the gate that fired
today instead of the failure the operator has to account for; and it must run
before anything that SPENDS — a repository prerelease, a bounded provider
renewal, a paginated forge round trip — because an item whose last dispatch
failed has nothing to spend them on.

ITS REFUSAL LANDS BEFORE THE CLAIM AND BEFORE ANY FABRO RUN EXISTS, which is the
whole wall's guarantee rather than this refusal's alone: a refused item is never
transitioned `ready -> active`, so there is no `active` row to reclaim and no run
to reap.

THE ADMIT PATH IS A WRITE, AND THAT MAKES THIS GUARD UNLIKE THE WALL'S OTHER
REFUSALS. Every one of those either refuses or does nothing; this one, handed a
reason for an armed item, ADMITS the dispatch and records the reason — on the
item's ledger, so the next guard can say whether it changed anything, and in the
dispatch journal, so the attempt that spent the override is attributable. The
write happens only for an ARMED item: a reason given for an item with no
recorded failure overrides nothing, and recording it would put a named change on
a timeline that never refused.

THE TIMELINE READ FAILS CLOSED, with ONE discrimination that is a reading rather
than an exemption. An item ABSENT from the tenant has no comments — that is a
readable fact about an empty timeline, not a failed measurement — while a
connection, tenant or configuration error is a failure to MEASURE and refuses.
Folding the two together in either direction is wrong: treating a blind read as
empty admits exactly the re-dispatch this guard exists to refuse, and treating
an absent item as blind refuses a dispatch on the strength of a question that
has a perfectly good answer.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_retry_outcome import (
    append_retry_record,
    executing_build,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_retry_records import (
    NAMED_CHANGE_KIND,
    ExecutingBuild,
    GuardState,
    RetryRecord,
    guard_state,
    one_line,
    retry_records,
    stage_source_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_retry_refusal import (
    armed_refusal,
    blank_reason_refusal,
    module_identity_clause,
    unreadable_timeline_refusal,
)
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
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RETRY_NAMED_CHANGE_STAGE",
    "RETRY_REFUSED_STAGE",
    "RETRY_UNREADABLE_STAGE",
    "retry_discipline_refusal",
]

RETRY_REFUSED_STAGE = "dispatcher-retry-discipline-refused"
RETRY_NAMED_CHANGE_STAGE = "dispatcher-retry-discipline-named-change"
RETRY_UNREADABLE_STAGE = "dispatcher-retry-discipline-unreadable"

# An item that is not in the tenant carries no comments, which is an ANSWER
# about an empty timeline rather than a failed reading.
_ITEM_ABSENT_ERRORS = (WorkItemNotFoundError, BeadsMappingError)
# Every way the reading itself can fail. Each of these leaves the question
# unanswered, so each refuses.
_TIMELINE_BLIND_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


def retry_discipline_refusal(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalWriter,
    build: ExecutingBuild | None = None,
    now: str | None = None,
) -> str | None:
    """The guard over one selection: an operator-facing refusal, or `None`.

    An EMPTY selection is answered without any read, which is the common case:
    the drain reaches the wall on every pass that finds no ready work, and a
    timeline read there spends one ledger round trip per item of a selection
    that was never going to dispatch.
    """
    because = getattr(args, "because", None)
    if because is not None and because.strip() == "":
        return blank_reason_refusal()
    resolved_build = executing_build() if build is None else build
    for item in items:
        timeline = _timeline(repo=repo, work_item_id=item.id)
        if isinstance(timeline, str):
            journal.append(
                record={
                    "stage": RETRY_UNREADABLE_STAGE,
                    "work_item_id": item.id,
                    "reason": timeline,
                    "blocking": True,
                }
            )
            return unreadable_timeline_refusal(work_item_id=item.id, detail=timeline)
        state = guard_state(records=retry_records(comments=timeline))
        signature = state.signature
        if signature is None:
            continue
        if because is None:
            return _refuse(
                work_item_id=item.id,
                state=state,
                signature=signature,
                journal=journal,
                build=resolved_build,
            )
        _record_named_change(
            repo=repo,
            work_item_id=item.id,
            signature=signature,
            reason=because,
            journal=journal,
            build=resolved_build,
            now=now,
        )
    return None


def _refuse(
    *,
    work_item_id: str,
    state: GuardState,
    signature: RetryRecord,
    journal: JournalWriter,
    build: ExecutingBuild,
) -> str:
    """Journal the refusal, then return the text the operator reads.

    The journal row carries the RENDERED module clause rather than re-deriving
    it, so the durable record and the printed refusal say the same thing about
    the same two files.
    """
    module = stage_source_module(stage=signature.stage)
    clause = module_identity_clause(
        module=module,
        recorded=_module_bytes(root=signature.build.plugin_root, module=module),
        executing=_module_bytes(root=build.plugin_root, module=module),
    )
    journal.append(
        record={
            "stage": RETRY_REFUSED_STAGE,
            "work_item_id": work_item_id,
            "refusing_stage": signature.stage,
            "error_class": signature.error_class,
            "signature_build_version": signature.build.version,
            "signature_plugin_root": signature.build.plugin_root,
            "executing_build_version": build.version,
            "module_comparison": clause,
            "ineffective_reason": state.ineffective_reason,
            "blocking": True,
        }
    )
    return armed_refusal(
        work_item_id=work_item_id,
        signature=signature,
        module_clause=clause,
        ineffective_reason=state.ineffective_reason,
    )


def _record_named_change(  # noqa: PLR0913 — kw-only write; each input names one independent field of the record.
    *,
    repo: Path,
    work_item_id: str,
    signature: RetryRecord,
    reason: str,
    journal: JournalWriter,
    build: ExecutingBuild,
    now: str | None,
) -> None:
    """Record the reason this attempt was admitted with, on BOTH surfaces.

    The record names the signature it OVERRODE, stage and class, which is what
    lets the NEXT guard decide whether the reason changed anything: that decision
    compares the signature recorded for the next attempt against the one this
    attempt was answering, and no later reader can recover the second from the
    first.
    """
    append_retry_record(
        repo=repo,
        work_item_id=work_item_id,
        record=RetryRecord(
            kind=NAMED_CHANGE_KIND,
            stage=signature.stage,
            error_class=signature.error_class,
            build=build,
            recorded_at=utc_now_iso() if now is None else now,
            reason=one_line(text=reason),
            overrode_stage=signature.stage,
            overrode_error_class=signature.error_class,
        ),
        journal=journal,
        journal_stage=RETRY_NAMED_CHANGE_STAGE,
    )


def _module_bytes(*, root: str, module: str) -> bytes | None:
    """One build's copy of a module, or `None` when it cannot be read.

    `None` for an unnamed module and an unnamed root as well as for a read that
    failed, because all three leave the comparison untakeable and the clause
    reports that as one answer.
    """
    if root == "" or module == "":
        return None
    read = attempt(
        action=lambda: (Path(root) / module).read_bytes(),
        exceptions=(OSError,),
    )
    if isinstance(read, AttemptFailure):
        return None
    return read


def _timeline(*, repo: Path, work_item_id: str) -> tuple[Mapping[str, object], ...] | str:
    """One item's comment timeline, or the name of the error that hid it."""
    read = attempt(
        action=lambda: make_beads_client(config=store_config(repo=repo)).list_comments(
            issue_id=work_item_id
        ),
        exceptions=(*_ITEM_ABSENT_ERRORS, *_TIMELINE_BLIND_ERRORS),
    )
    if isinstance(read, AttemptFailure):
        if isinstance(read.error, _ITEM_ABSENT_ERRORS):
            return ()
        return type(read.error).__name__
    return tuple(read)
