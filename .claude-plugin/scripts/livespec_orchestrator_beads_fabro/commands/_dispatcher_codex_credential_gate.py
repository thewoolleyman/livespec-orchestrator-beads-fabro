"""The dispatch-path Codex credential freshness gate over a whole selection.

The IMPURE, selection-level entry point of the freshness-gate clause in
`SPECIFICATION/contracts.md` section "Worker credential projection" -- "the
Dispatcher MUST NOT dispatch a worker unless every projected credential covered
by the freshness gate has a usable lifetime that exceeds the worker's maximum run
budget" -- and the ONE surface both dispatch paths, the single dispatch and the
drain, call before any item is claimed.

WHY THIS IS NOT IN `_dispatcher_credentials`. The decision used to run inside
`materialize_overlay`, which `dispatch_one` reaches only AFTER
`admit_and_select` has moved the item `ready -> active` and set its assignee. The
contract says the Dispatcher must not DISPATCH on such a credential, and refusing
there satisfied that wording while leaving an `active` row nobody is working and
no run to reap. The POSITION is what this module adds: the pre-dispatch wall runs
after selection and before admission, which is the same place the
acceptance-criteria, proof-assets and proof-credential gates already sit.

WHY THE RENEWAL LIVES ON THIS SIDE OF THE CLAIM AND NOWHERE ELSE. A bounded
in-place renewal is the one thing that can turn an insufficient credential into a
sufficient one, so the question "can this credential be brought above the floor?"
has to be settled while the item is still unclaimed -- the answer decides whether
there is anything to claim. `project_host_codex_auth`, which the overlay calls
once the item IS claimed, therefore grades without renewing: a second renewal
request would spend provider work on a question whose answer can no longer be
reported before a claim.

WHAT THIS MODULE DOES NOT DO. It never renders a refusal of its own. The
freshness decision and its diagnostics belong to `_dispatcher_codex_auth`, which
is where the post-renewal observations are kept apart -- whether the expiry
advanced, held, or went unobserved, and whether a renewal response came back at
all; a gate that re-worded them would be a second account of the same
measurement, and the two would drift. It projects nothing either: the snapshot `project_codex_auth`
returns on success is DISCARDED here, because the overlay re-reads the credential
as it then stands and a snapshot carried across the claim would be the stale one.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    CodexProjectionRefusal,
    project_codex_auth,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)

__all__: list[str] = [
    "CODEX_CREDENTIAL_GATE_STAGE",
    "CODEX_CREDENTIAL_REQUIREMENT_STAGE",
    "codex_credential_refusal_for_items",
    "wall_clock_epoch",
]

# The journal stage a pre-claim refusal is recorded under. A refusal here leaves
# no `active` row and no run, so the journal is the only place the pass survives
# in at all -- which is why the record names the items it declined to claim.
CODEX_CREDENTIAL_GATE_STAGE = "codex-credential-gate-refused"

# The journal stage for a selection whose credential REQUIREMENT could not be
# resolved at all. Kept apart from the refusal above because the two are
# different findings: one says a credential is too short for a known allowance,
# the other says no allowance could be established, and an operator's remedy for
# the second is a configuration change rather than a renewal.
CODEX_CREDENTIAL_REQUIREMENT_STAGE = "codex-credential-requirement-unresolved"


def wall_clock_epoch() -> int:
    """The Dispatcher's own clock, as whole seconds since the epoch."""
    return int(time.time())


def codex_credential_refusal_for_items(
    *,
    work_item_ids: Sequence[str],
    requirement: CredentialLifetimeRequirement | str,
    clock: Callable[[], int] | None = None,
    journal: object = None,
) -> str | None:
    """The pre-claim gate over a whole selection: None to proceed, or the refusal.

    The host credential is a HOST-level fact, so the refusal is computed once and
    returned once: enumerating it per candidate would read as N distinct faults
    when there is one, and a wave refused here is refused whole.

    `requirement` is the caller's RESOLVED credential-lifetime requirement for the
    workflow this selection would run, or the string explaining why none could be
    established. An unresolved requirement refuses the selection rather than
    falling back to a fixed figure: a credential graded against an allowance
    nobody could derive is graded against nothing. It is resolved by the caller
    because the caller holds the dispatch's workflow selection and the items whose
    effective policy the figure depends on.

    `clock` is resolved at CALL time rather than bound as a default, because the
    bounded renewal underneath can take up to two minutes and the re-grade after
    it must read the clock AGAIN -- so the callable, not an instant, is what
    crosses this boundary, and a test standing a clock in stands in the one both
    readings come from.

    `journal` is optional and is reached through its own `append`, so the gate is
    callable from a hermetic test and from a caller holding none, without a
    second serializer. Only the refusal is recorded: an admitted pass is followed
    by the overlay's own projection record, and a line asserting that a
    credential was admitted would duplicate it.
    """
    # NOTHING TO CLAIM MEANS NOTHING TO GRADE, and the early return is the whole
    # point rather than an optimization. This gate answers one question -- can
    # the credential that this SELECTION will project be brought above the floor?
    # -- and with no selection nothing will project a credential, so the question
    # has no subject. Asking it anyway reads the host credential and spends a
    # bounded PROVIDER REQUEST on a pass that was never going to dispatch, then
    # reports the shortfall as a dispatch refusal: an idle drain exited 3 instead
    # of 0 and was charged a renewal for it (measured 2026-10-05). An idle pass
    # must not be observable at the provider at all.
    #
    # The drain reaches the wall with an empty selection on every pass that finds
    # no ready work, which is the COMMON case, so this is ordinary behaviour
    # rather than an edge. The guard lives here rather than in the drain because
    # the emptiness is this gate's own precondition: every caller handing an
    # empty selection is protected, and the wall's other refusals keep their own
    # empty-selection behaviour, including the proof-credential gate's grading of
    # a repository declaration that is broken whether or not work is queued.
    if not work_item_ids:
        return None
    if isinstance(requirement, str):
        _journal(
            journal=journal,
            stage=CODEX_CREDENTIAL_REQUIREMENT_STAGE,
            work_item_ids=work_item_ids,
            refusal=requirement,
        )
        return requirement
    projected = project_codex_auth(
        clock=clock if clock is not None else wall_clock_epoch,
        run_budget_seconds=requirement.allowance_seconds,
    )
    if not isinstance(projected, CodexProjectionRefusal):
        return None
    _journal(
        journal=journal,
        stage=CODEX_CREDENTIAL_GATE_STAGE,
        work_item_ids=work_item_ids,
        refusal=f"{projected.message} Requirement: {requirement.detail}.",
    )
    return f"{projected.message} Requirement: {requirement.detail}."


def _journal(
    *,
    journal: object,
    stage: str,
    work_item_ids: Sequence[str],
    refusal: str,
) -> None:
    """Record one refusal, reached through `append` so a caller may hold none.

    Only refusals are recorded. An admitted pass is followed by the overlay's own
    projection record, and a line asserting that a credential was admitted would
    duplicate it.
    """
    append = getattr(journal, "append", None)
    if append is None:
        return
    append(
        record={
            "stage": stage,
            "unclaimed_work_item_ids": list(work_item_ids),
            "refusal": refusal,
        }
    )
