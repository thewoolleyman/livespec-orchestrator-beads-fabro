"""The one path every sanctioned plan pointer write takes through the epoch chain.

`append_handoff`, `append_supervisor_handoff` and `set_next_action` all funnel
here, so per-epic serialization, stale-epoch detection and same-operation retry
recovery are properties of ONE sequence rather than three similar ones. The
decision itself is `_plan_progress_decision`'s, and the exclusion is the Beads
server's conditional close inside `_plan_epoch_chain` — nothing here acquires a
lock, opens a socket or touches a host directory, because writers may run on
hosts that share nothing but that server (`.ai/ledger-writers-are-multi-host.md`,
maintainer ruling 2026-10-12).

THE ORDER OF THE SEQUENCE IS THE CLAUSE'S AND IS LOAD-BEARING AT EVERY STEP.
A committed operation identity is recognised FIRST, then the prior obligation is
read and the decision taken, and both happen before any mutation — "After
expiry, same-obligation continuation MUST be refused BEFORE appending a handoff
or updating the pointer". The chain transition then commits, and only a
transition that actually committed appends the comment and writes the pointer —
which is what makes both of those PROJECTIONS of the chain rather than
independent records that could disagree with it.

WHY A RECOVERED RETRY WRITES NOTHING. "retried calls with the same operation
identity MUST recover the original event rather than duplicate handoffs or
extend a deadline." The chain recognises the retry and hands back the ORIGINAL
payload; appending the comment again would duplicate the handoff the clause
forbids, and re-writing the pointer would re-render a projection that is already
correct. So a recovered commit returns the original epoch and consumed count
with `idempotent=True` and performs no write at all.

AND WHY THE RECOGNITION RUNS AHEAD OF THE DECISION RATHER THAN INSIDE THE
COMMIT. `commit_transition` carries its own retry guard, which is the chain's
last word and stays exactly where it is — but a write refused before it is
reached never gets the recovery the clause owes. The decision's expiry ladder
reads the OBSERVED head, so the retry of the handoff that consumed the final
`max_handoffs` unit is read as an expired continuation and refused, although the
write it is retrying succeeded: the caller is told to register a causal recovery
for an obligation it had just met. The identity question is therefore asked
first, where it cannot be pre-empted by any refusal the ladder grows later, and
a recognised retry short-circuits the whole sequence. `recover_committed_
operation` performs no write, so asking early costs one comment read and can
change nothing; a twin that commits in the window between that scan and the
chain's own is still answered as a recovery, by the chain's guard.

WHY AN EPIC WITH NO CHAIN IS WRITTEN ON THE LEGACY PATH RATHER THAN REFUSED.
Research note 007 and this item's brief are explicit: these writers MUST NEVER
create a chain genesis token, because a genesis created by a writer racing
another writer forks the authority permanently. And the clause requires legacy
pointers to "acquire the new shape on their next sanctioned write", so refusing
would make that impossible. The write therefore lands the five-field pointer
with no durable authority, and every READER keeps reporting
`plan-progress-tracking: missing` until the sanctioned migration
(`migrate-plan-records`) creates the chain. That is the honest state: the
pointer has the right shape and no authority behind it yet.

WHY EVERY OTHER CHAIN FINDING REFUSES. A fork, an unreadable chain or an
unreconciled partial write are states in which the prior obligation CANNOT BE
READ, and "A partial write MUST be diagnosable and must not authorize a fresh
dispatch until reconciled." Proceeding would preserve a budget nobody measured,
which is a gauge passing because it was blinded.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    COMMITTED,
    ChainHead,
    CommittedTransition,
    StaleEpochRefusal,
    TransitionRequest,
    commit_transition,
    read_chain_head,
    recover_committed_operation,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    MISSING_TRACKING,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NextAction,
    next_action_metadata,
    plan_record_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action_admission import (
    admit_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action_validation import (
    NextActionRefusal,
)
from livespec_orchestrator_beads_fabro.commands._plan_obligation import (
    obligation_of,
    projected_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_progress_decision import (
    TrackedDecision,
    TrackedRefusal,
    decide_tracked_write,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery import CausalRecovery
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_HANDOFF_PREFIX,
    plan_comment_body,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
        ResultObservation,
    )
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "TrackedWrite",
    "TrackedWriteRequest",
    "commit_tracked_write",
    "derived_operation_id",
]


@dataclass(frozen=True, kw_only=True)
class TrackedWriteRequest:
    """One sanctioned pointer write, with everything the chain needs to serialize it.

    `body` is the handoff entry's prose and is present exactly when `is_handoff`
    is true. `operation_id` is the identity a retry is recognised by; a caller
    that supplies none gets `derived_operation_id`'s deterministic value.
    `recovery` is the typed causal attempt an EXPIRED obligation needs before it
    will accept any continuation at all.
    """

    config: StoreConfig
    epic_id: str
    action: NextAction
    author: str
    now: str
    is_handoff: bool = False
    body: str | None = None
    operation_id: str | None = None
    recovery: CausalRecovery | None = None


@dataclass(frozen=True, kw_only=True)
class TrackedWrite:
    """What one admitted write committed, as the chain recorded it."""

    action: NextAction
    epoch: int
    consumed_handoffs: int
    idempotent: bool
    tracked: bool


def derived_operation_id(*, request: TrackedWriteRequest) -> str:
    """A deterministic operation identity for a caller that named none.

    Two calls agreeing on the epic, author, instant, WHOLE pointer and handoff
    body are the SAME logical operation — a retry — and must recover one event rather than
    consume two handoff units. Anything that differs in any of those is a
    different operation.

    THE PROPOSED OBLIGATION IS PART OF THE IDENTITY, including the budget the
    continuation path goes on to discard. On the FRESH-obligation arm the
    proposed budget is the very thing that becomes durable, so excluding it
    would let the second of two distinct establishing writes be recovered as a
    retry of the first, silently adopting a budget its caller never asked for.

    A digest is used rather than the fields themselves because the identity
    rides in a close reason and a progress event, and an unbounded
    concatenation of caller prose does not belong in either. The parts are
    joined on a unit separator so no two different field splits can render one
    string, and `sort_keys` makes the reference rendering independent of dict
    insertion order so two equal references cannot digest differently.
    """
    material = "\x1f".join(
        (
            request.epic_id,
            request.author,
            request.now,
            request.action.kind,
            request.action.ref,
            request.action.text,
            request.body or "",
            str(request.is_handoff),
            dumps(request.action.required_result, sort_keys=True, default=str),
            dumps(request.action.budget, sort_keys=True, default=str),
        )
    )
    return f"plan-write-{sha256(material.encode('utf-8')).hexdigest()[:16]}"


def commit_tracked_write(*, request: TrackedWriteRequest) -> TrackedWrite | NextActionRefusal:
    """Admit, serialize and persist one sanctioned plan pointer write."""
    refusal = admit_next_action(
        action=request.action,
        epic_id=request.epic_id,
        config=request.config,
    )
    if refusal is not None:
        return refusal
    head = read_chain_head(config=request.config, epic_id=request.epic_id)
    if isinstance(head, ChainFinding):
        if head.code == MISSING_TRACKING:
            if request.recovery is not None:
                return NextActionRefusal(
                    detail=(
                        "causal recovery is invalid: this epic carries no authority chain,"
                        " so it holds no obligation that could have expired"
                    )
                )
            return _legacy_write(request=request)
        return NextActionRefusal(detail=f"{head.code}: {head.detail} — {head.remedy}")
    return _tracked_write(request=request, head=head)


def _tracked_write(
    *,
    request: TrackedWriteRequest,
    head: ChainHead,
) -> TrackedWrite | NextActionRefusal:
    """Recover a retry, else decide against the observed head and commit.

    The recovery runs BEFORE the decision, for the reason this module's
    docstring records: the decision's expiry ladder would otherwise refuse the
    retry of the very handoff that exhausted the budget.
    """
    operation_id = request.operation_id or derived_operation_id(request=request)
    recovered = recover_committed_operation(
        config=request.config,
        epic_id=request.epic_id,
        operation_id=operation_id,
        observed_head=head,
    )
    if isinstance(recovered, ChainFinding):
        return NextActionRefusal(detail=f"{recovered.code}: {recovered.detail}")
    if recovered is not None:
        return _recovered_write(request=request, committed=recovered)
    decision = decide_tracked_write(
        epic_id=request.epic_id,
        head=head,
        candidate=request.action,
        now=request.now,
        is_handoff=request.is_handoff,
        observation=_prior_observation(request=request, head=head),
        recovery=request.recovery,
    )
    if isinstance(decision, TrackedRefusal):
        return NextActionRefusal(detail=decision.detail)
    committed = commit_transition(
        config=request.config,
        epic_id=request.epic_id,
        request=TransitionRequest(
            operation_id=operation_id,
            observed_head=head,
            authority=decision.authority,
            event_kind=decision.event_kind,
            author=request.author,
            now=request.now,
        ),
    )
    if isinstance(committed, StaleEpochRefusal):
        return NextActionRefusal(
            detail=(
                f"a concurrent writer committed from epoch {committed.observed_epoch};"
                f" re-read the plan and retry: {committed.detail}"
            )
        )
    if isinstance(committed, ChainFinding):
        return NextActionRefusal(detail=f"{committed.code}: {committed.detail}")
    return _persist(request=request, decision=decision, committed=committed)


def _persist(
    *,
    request: TrackedWriteRequest,
    decision: TrackedDecision,
    committed: CommittedTransition,
) -> TrackedWrite:
    """Project an admitted transition onto the comment and the pointer.

    A RECOVERED transition projects nothing: its original call already wrote
    both, so appending again would duplicate the handoff the retry clause
    forbids. The arm survives the pre-decision scan above because the chain's
    own guard sees a window that scan cannot — a twin of this call committing
    between the two readings.
    """
    if committed.source != COMMITTED:
        return _recovered_write(request=request, committed=committed)
    authority = committed.payload.authority
    action = projected_action(
        action=decision.action,
        authority=authority,
        epoch=committed.payload.new_epoch,
    )
    _project_write(request=request, action=action)
    return TrackedWrite(
        action=action,
        epoch=committed.payload.new_epoch,
        consumed_handoffs=authority.consumed_handoffs,
        idempotent=False,
        tracked=obligation_of(authority=authority) is not None,
    )


def _recovered_write(
    *,
    request: TrackedWriteRequest,
    committed: CommittedTransition,
) -> TrackedWrite:
    """Hand back the transition this operation already committed, writing nothing.

    The pointer is projected from the REQUEST's action rather than from any
    decision, because no decision was taken: the projection overlays the
    committed authority onto whatever tracking the action carries, so the two
    agree wherever a decision exists and the recovery needs none.
    """
    authority = committed.payload.authority
    return TrackedWrite(
        action=projected_action(
            action=request.action,
            authority=authority,
            epoch=committed.payload.new_epoch,
        ),
        epoch=committed.payload.new_epoch,
        consumed_handoffs=authority.consumed_handoffs,
        idempotent=True,
        tracked=obligation_of(authority=authority) is not None,
    )


def _project_write(*, request: TrackedWriteRequest, action: NextAction) -> None:
    """Append the handoff entry, if any, and store the pointer one write lands.

    Shared by the chain-committed arm and the legacy arm because both land the
    SAME two records against the same epic; a second copy is how the two paths
    come to write pointers that differ in a field nobody compared.
    """
    client = make_beads_client(config=request.config)
    if request.is_handoff:
        client.add_comment(
            issue_id=request.epic_id,
            body=plan_comment_body(
                prefix=PLAN_HANDOFF_PREFIX,
                author=request.author,
                now=request.now,
                body=request.body or "",
            ),
        )
    record = client.show_issue(issue_id=request.epic_id)
    client.update_issue(
        issue_id=request.epic_id,
        metadata=next_action_metadata(
            existing_metadata=plan_record_metadata(record=record),
            action=action,
            session=request.author,
            now=request.now,
        ),
    )


def _legacy_write(*, request: TrackedWriteRequest) -> TrackedWrite:
    """Persist the pointer on an epic whose authority chain does not exist yet.

    NO GENESIS IS CREATED HERE, deliberately — see this module's docstring. The
    pointer acquires its five-field shape, and every reader keeps reporting
    missing tracking until the sanctioned migration establishes the chain.
    """
    _project_write(request=request, action=request.action)
    return TrackedWrite(
        action=request.action,
        epoch=0,
        consumed_handoffs=0,
        idempotent=False,
        tracked=False,
    )


def _prior_observation(
    *,
    request: TrackedWriteRequest,
    head: ChainHead,
) -> ResultObservation | None:
    """Read the PRIOR obligation's target, which is what continuity turns on.

    The clause says "All sanctioned pointer writers MUST read the prior
    obligation and its target before accepting continuation", and the target read
    is the PRIOR one rather than the candidate's: reading the candidate's target
    would let a writer rename the obligation to something already satisfied and
    have the rename grade itself.
    """
    obligation = obligation_of(authority=head.authority)
    if obligation is None:
        return None
    project_root = request.config.repo_root
    return read_result(
        project_root=Path.cwd() if project_root is None else project_root,
        reference=obligation.required_result,
        runner=ShellCommandRunner(),
        now=request.now,
    )
