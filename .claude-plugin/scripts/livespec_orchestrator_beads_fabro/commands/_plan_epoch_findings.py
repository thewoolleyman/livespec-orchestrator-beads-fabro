"""What a reader of a plan-authority chain REPORTS, and the remedy it names.

PURE. Every finding here withholds something: a dispatch, a transition, or a
walk. That is why each one carries a `remedy` rather than only a `detail` —
`contracts.md` section "Required result, budget and progress epoch" requires a
partial write to be DIAGNOSABLE and to stop authorizing a fresh dispatch until
it is reconciled, and a diagnosis nobody can act on satisfies neither half.

A FINDING IS NEVER A REFUSAL OF A COMPETING WRITER. Losing a race is an
ordinary, expected outcome with its own value (`StaleEpochRefusal`), and
reporting it here would put a routine loss into the same channel as a damaged
chain — which is the one distinction an operator reading either needs.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CHAIN_FORK",
    "CHAIN_UNREADABLE",
    "MISSING_TRACKING",
    "PARTIAL_WRITE",
    "RECEIPT_WITHOUT_EVENT",
    "ChainFinding",
    "chain_fork_finding",
    "chain_unreadable_finding",
    "missing_tracking_finding",
    "partial_write_finding",
    "receipt_without_event_finding",
]

MISSING_TRACKING = "plan-epoch-chain: missing"
CHAIN_FORK = "plan-epoch-chain: fork"
CHAIN_UNREADABLE = "plan-epoch-chain: unreadable"
PARTIAL_WRITE = "plan-epoch-chain: partial-write"
RECEIPT_WITHOUT_EVENT = "plan-epoch-chain: receipt-without-event"

# The sanctioned operation that creates a live epic's genesis token. Named in
# the missing-tracking finding because that is the ONE write permitted to
# create one: a writer that minted its own genesis on demand would give two
# concurrent writers two chains, and a chain is only an exclusion while every
# writer closes the same token (relay research note 007).
_MIGRATION_REMEDY = (
    "run the sanctioned plan-record migration for this epic, which creates its genesis token"
)


@dataclass(frozen=True, kw_only=True)
class ChainFinding:
    """One reportable condition of a plan epic's authority chain."""

    code: str
    detail: str
    remedy: str


def missing_tracking_finding(*, epic_id: str) -> ChainFinding:
    """Report a live epic with no chain, naming the migration that creates one.

    This is NOT an error state. A plan epic that predates the chain keeps its
    legacy pointer readable; the finding is what makes the gap visible rather
    than letting a reader mistake an unmigrated epic for one at epoch 0.
    """
    return ChainFinding(
        code=MISSING_TRACKING,
        detail=f"{epic_id} names no epoch-token chain, so its legacy pointer is the only authority",
        remedy=_MIGRATION_REMEDY,
    )


def chain_fork_finding(
    *, epic_id: str, token_id: str, claimed_prior: str, walked_from: str
) -> ChainFinding:
    """Report a closed token whose payload claims a predecessor it was not reached from.

    A fork is NEVER followed silently. Two closed tokens claiming one
    predecessor mean two transitions were admitted from one epoch, which is the
    exact condition the chain exists to make impossible — so a reader that
    picked one branch would be reporting a repaired chain it had invented.
    """
    return ChainFinding(
        code=CHAIN_FORK,
        detail=(
            f"{epic_id}: token {token_id} claims prior token {claimed_prior} "
            f"but was reached from {walked_from}"
        ),
        remedy="resolve the forked chain before any further transition or dispatch",
    )


def chain_unreadable_finding(*, epic_id: str, token_id: str, detail: str) -> ChainFinding:
    """Report a chain whose walk could not be completed, naming where it stopped.

    An unreadable chain is reported rather than treated as an absent one: the
    two support opposite conclusions, and a reader that silently fell back to
    "no chain" would hand a live epic's authority to its legacy pointer.
    """
    return ChainFinding(
        code=CHAIN_UNREADABLE,
        detail=f"{epic_id}: the chain walk stopped at token {token_id}: {detail}",
        remedy="read the named token directly and reconcile the chain before dispatching",
    )


def partial_write_finding(*, epic_id: str, detail: str) -> ChainFinding:
    """Report a projection that disagrees with the committed chain.

    This is the diagnosable partial write: the transition is durable in the
    closed token, and the cache or the progress comment the readers project
    from has not caught up. Dispatch is withheld until it is reconciled.
    """
    return ChainFinding(
        code=PARTIAL_WRITE,
        detail=f"{epic_id}: {detail}",
        remedy="reconcile the epic's projections from the chain before authorizing a dispatch",
    )


def receipt_without_event_finding(*, epic_id: str, operation_id: str) -> ChainFinding:
    """Report an operation the ring says committed whose event cannot be read.

    Returning a fresh transition here would duplicate a handoff the ring
    already accounts for, and synthesizing the original event would answer the
    retry with one nobody recorded. Both are worse than saying so.
    """
    return ChainFinding(
        code=RECEIPT_WITHOUT_EVENT,
        detail=(
            f"{epic_id}: operation {operation_id} holds a committed receipt "
            "but no progress event carries its recorded transition"
        ),
        remedy="recover the operation's progress event before retrying it",
    )
