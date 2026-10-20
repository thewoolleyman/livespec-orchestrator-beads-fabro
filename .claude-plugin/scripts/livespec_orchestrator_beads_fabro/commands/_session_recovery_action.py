"""Choosing the ONE typed action current authority sanctions, after re-reading it.

PURE. `contracts.md` section "Launch obligations and consumed recovery" puts the
re-read before the choice: "The consumer MUST re-read current authority, safety
state, result epoch, ledger/forge and the recorded remote factory before
selecting a typed sanctioned action. A stale pointer to a completed diagnostic
MUST be reconciled; a failed local gate MUST NOT be treated as proof that its
remote run or merged PR failed. An expired obligation MUST trigger authorized
diagnosis rather than fabricate a human block."

WHY THE LOCAL GATE OUTCOME IS CARRIED AND NEVER CONSULTED. It is the one reading
an operator naturally decides on, and it is the one that was measured WRONG:
on 2026-10-09 an overseer gate returned FAILED at 05:19:06Z for a pull request
that had merged at 05:18:03Z, and the correct action was a per-item
`reconcile-merged` rather than a redispatch. So the gate outcome reaches only the
DIAGNOSTICS — it is reported, so a reader can see what the consumer saw — and no
rung of the ladder reads it. "No blind redispatch follows solely from the local
gate failure" therefore holds structurally: the same evidence with the gate green
selects the same action.

WHY THE FORGE RUNG COMES BEFORE THE LEDGER RUNG. A merged pull request is the
strongest evidence available about what already happened, and the ledger lags it
— the measured case is exactly an item left `active` whose work had merged. Read
the other way round, a ready-looking item would be re-dispatched over work that
is already in master.

WHY A STALE COMPLETED DIAGNOSTIC IS REFRESHED RATHER THAN REPEATED. The pointer a
consumer wakes up holding may name an operation the ledger shows already
finished — the 2026-10-07 incident's epic pointed at a diagnostic completed six
minutes before the gate even failed. Repeating it costs a dispatch and cannot
change anything, so the ladder re-derives the action from CURRENT evidence; only
where current evidence authorizes nothing does the completed pointer become the
reported reason, and even then the answer is "nothing is authorized", never an
invented human blocker.

WHY AN UNOBSERVABLE READING STOPS EVERYTHING. The three readings the clause names
are each required to be observable before any action is chosen, so one that could
not be taken yields no action at all rather than a choice made on the other two.
The natural coding — treat an unreadable forge as "no merge" — is the fail-open
direction, and it re-dispatches merged work.

WHY THE DERIVED OPERATION IS ITSELF GRAMMAR-CHECKED. The same lesson
`_plan_recovery` records: a ladder that trusted its own derivation would
authorize whatever text its inputs happened to carry. `sanctioned_operation`
grades the result, so an item id that is really a sentence authorizes NOTHING
rather than authorizing itself.

WHY THE GRAMMAR EXTENDS THE RELAY'S RATHER THAN RESTATING IT. The executable
operations are the relay contract's, reached through its own
`is_executable_operation`, and this module adds exactly one consumer-side form —
the per-item `reconcile-merged` the clause calls "the sanctioned per-item
reconciliation". A second copy of the relay's grammar is how the two come to
disagree about what is executable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._plan_recovery import (
    DIAGNOSIS_OPERATION_PREFIX,
    is_executable_operation,
)

__all__: list[str] = [
    "ACTION_NONE_AUTHORIZED",
    "ACTION_SELECTED",
    "ACTION_STALE_EPOCH",
    "ACTION_UNAUTHORIZED",
    "ACTION_UNOBSERVABLE",
    "DIAGNOSTIC_FORGE_UNOBSERVABLE",
    "DIAGNOSTIC_LEDGER_UNOBSERVABLE",
    "DIAGNOSTIC_LOCAL_GATE_FAILED",
    "DIAGNOSTIC_REMOTE_FACTORY_UNOBSERVABLE",
    "GATE_FAILED",
    "LEDGER_STATUS_READY",
    "REASON_AUTHORIZED_DIAGNOSIS",
    "REASON_LEDGER_READY",
    "REASON_MERGED_PULL_REQUEST",
    "REASON_STALE_DIAGNOSTIC_COMPLETED",
    "RECONCILE_MERGED_PREFIX",
    "AuthoritativeEvidence",
    "Reading",
    "SanctionedAction",
    "sanctioned_operation",
    "select_sanctioned_action",
]

ACTION_SELECTED = "selected"
ACTION_STALE_EPOCH = "stale-epoch"
ACTION_UNOBSERVABLE = "unobservable"
ACTION_NONE_AUTHORIZED = "none-authorized"
ACTION_UNAUTHORIZED = "unauthorized"

REASON_MERGED_PULL_REQUEST = "merged-pull-request"
REASON_LEDGER_READY = "ledger-ready"
REASON_AUTHORIZED_DIAGNOSIS = "authorized-diagnosis"
REASON_STALE_DIAGNOSTIC_COMPLETED = "stale-diagnostic-completed"

DIAGNOSTIC_LEDGER_UNOBSERVABLE = "ledger-unobservable"
DIAGNOSTIC_FORGE_UNOBSERVABLE = "forge-unobservable"
DIAGNOSTIC_REMOTE_FACTORY_UNOBSERVABLE = "remote-factory-unobservable"
DIAGNOSTIC_LOCAL_GATE_FAILED = "local-gate-failed"

GATE_FAILED = "failed"
LEDGER_STATUS_READY = "ready"

# The ONE consumer-side operation this module adds to the relay's executable
# grammar: the per-item post-merge reconciliation. The id shape is the relay's
# own work-item shape rather than a looser one, so a sentence cannot pass as an
# item id.
RECONCILE_MERGED_PREFIX = "reconcile-merged:"
_RECONCILE_MERGED = re.compile(rf"{RECONCILE_MERGED_PREFIX}[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?:\.\d+)?")


@dataclass(frozen=True, kw_only=True)
class Reading:
    """One authoritative reading, or the fact that it could not be taken.

    An EMPTY value is a real reading — the forge was asked and reported no
    merge — and is kept apart from `None`, which is a reading that failed.
    Collapsing them turns an unreachable forge into "nothing has merged", which
    is the fail-open answer this whole ladder exists to refuse.
    """

    value: str | None

    @property
    def observable(self) -> bool:
        return self.value is not None


@dataclass(frozen=True, kw_only=True)
class AuthoritativeEvidence:
    """Everything a consumer re-read before choosing what to do next.

    `local_gate_outcome` is here because the consumer DID observe it and a
    reader needs to see that it did; no rung of the ladder consults it. See the
    module docstring for the measurement behind that.
    """

    item_id: str
    epic_id: str
    recorded_next_operation: str
    recorded_operation_completed: bool
    ledger_status: Reading
    merged_pull_request: Reading
    remote_run_outcome: Reading
    local_gate_outcome: str
    recorded_epoch: int
    current_epoch: int


@dataclass(frozen=True, kw_only=True)
class SanctionedAction:
    """The typed action this evidence authorizes, or why it authorizes none."""

    state: str
    operation: str | None
    reason: str | None
    diagnostics: tuple[str, ...]

    @property
    def authorized(self) -> bool:
        return self.state == ACTION_SELECTED


def sanctioned_operation(*, operation: str) -> bool:
    """Whether one operation is in the closed set a consumer may execute."""
    if _RECONCILE_MERGED.fullmatch(operation) is not None:
        return True
    return is_executable_operation(operation=operation)


def select_sanctioned_action(*, evidence: AuthoritativeEvidence) -> SanctionedAction:
    """Choose the one action current authoritative evidence sanctions."""
    reported = _reported(evidence=evidence)
    if evidence.recorded_epoch != evidence.current_epoch:
        return SanctionedAction(
            state=ACTION_STALE_EPOCH, operation=None, reason=None, diagnostics=reported
        )
    unobservable = _unobservable(evidence=evidence)
    if unobservable:
        return SanctionedAction(
            state=ACTION_UNOBSERVABLE,
            operation=None,
            reason=None,
            diagnostics=reported + unobservable,
        )
    return _graded(evidence=evidence, reported=reported)


def _reported(*, evidence: AuthoritativeEvidence) -> tuple[str, ...]:
    """What the consumer saw and is reporting, never what it decided on."""
    if evidence.local_gate_outcome == GATE_FAILED:
        return (DIAGNOSTIC_LOCAL_GATE_FAILED,)
    return ()


def _unobservable(*, evidence: AuthoritativeEvidence) -> tuple[str, ...]:
    """Every authority the clause names that could not be read, in its order."""
    named = (
        (evidence.ledger_status, DIAGNOSTIC_LEDGER_UNOBSERVABLE),
        (evidence.merged_pull_request, DIAGNOSTIC_FORGE_UNOBSERVABLE),
        (evidence.remote_run_outcome, DIAGNOSTIC_REMOTE_FACTORY_UNOBSERVABLE),
    )
    return tuple(diagnostic for reading, diagnostic in named if not reading.observable)


def _graded(*, evidence: AuthoritativeEvidence, reported: tuple[str, ...]) -> SanctionedAction:
    """Derive the action from observable evidence, then grade what was derived."""
    derived = _derived(evidence=evidence)
    if derived is None:
        return SanctionedAction(
            state=ACTION_NONE_AUTHORIZED,
            operation=None,
            reason=REASON_STALE_DIAGNOSTIC_COMPLETED,
            diagnostics=reported,
        )
    operation, reason = derived
    if not sanctioned_operation(operation=operation):
        return SanctionedAction(
            state=ACTION_UNAUTHORIZED, operation=None, reason=reason, diagnostics=reported
        )
    return SanctionedAction(
        state=ACTION_SELECTED, operation=operation, reason=reason, diagnostics=reported
    )


def _derived(*, evidence: AuthoritativeEvidence) -> tuple[str, str] | None:
    """The operation current evidence points at, or `None` when it points at none.

    The rungs are ordered strongest-evidence-first — see the module docstring on
    why the forge precedes the ledger — and the completed-pointer rung sits last
    so a refreshed action always wins over repeating a finished one.
    """
    if evidence.merged_pull_request.value != "":
        return (
            f"{RECONCILE_MERGED_PREFIX}{evidence.item_id}",
            REASON_MERGED_PULL_REQUEST,
        )
    if evidence.ledger_status.value == LEDGER_STATUS_READY:
        return (f"impl:{evidence.item_id}", REASON_LEDGER_READY)
    diagnosis = f"{DIAGNOSIS_OPERATION_PREFIX}{evidence.epic_id}"
    if evidence.recorded_operation_completed and evidence.recorded_next_operation == diagnosis:
        return None
    return (diagnosis, REASON_AUTHORIZED_DIAGNOSIS)
