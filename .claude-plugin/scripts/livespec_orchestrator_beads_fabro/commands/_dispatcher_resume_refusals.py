"""Every mismatch a resume refuses on, named in the clause's own order.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" lists eight refusals and then adds the rule that makes the
list more than a list: "When more than one refusal applies, the refusal MUST name
EVERY applicable mismatch, in the order listed, each with its remedy; a refusal
that names only the first does not satisfy this clause."

SO THIS IS NOT A LADDER OF EARLY RETURNS, and the difference is operational
rather than stylistic. An item `active` under a live claim is refused on the
status bullet AND the live-run bullet together; an operator told only "not ready"
runs `resolve-blocked` and drives the resume straight into the live run it was
never told about. Every arm therefore APPENDS, and the function returns the whole
tuple.

THE MODULE IS PURE, AND THE OBSERVATION IS WHAT MAKES IT SO. Three external
systems answer these questions — the ledger, the forge and the factory — and each
can fail to answer at all. Gathering them is the command's job; grading them is
this module's, which is what lets every arm be exercised without a forge, and
what keeps the "unobservable" case from being whatever a failed subprocess
happens to return.

AN UNOBSERVABLE MEASUREMENT IS A REFUSAL, NEVER A SKIP: "it MUST NOT proceed on
an unobservable answer". A forge that cannot report the head and a forge
reporting a head that matches support opposite decisions, and once the comparison
has been skipped nothing downstream can tell them apart — the fail-open direction
resumes on a tree no record describes. Each unobservable sits WHERE the
measurement it replaces would have sat, so the order an operator reads is the
order the questions were asked.

THE TWO PULL-REQUEST-STATE REMEDIES DIFFER AND MUST NOT BE MERGED. A closed pull
request's remedy is a plain dispatch; a MERGED one's is `reconcile-merged --item`,
which "requires a real merge and stays the only valve for one". Naming a plain
dispatch for a merged pull request sends an operator to cut an empty branch
against work that has already landed, and to spend an `acceptance_rework_cap`
attempt failing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

__all__: list[str] = [
    "PR_STATE_CLOSED",
    "PR_STATE_MERGED",
    "PR_STATE_OPEN",
    "LiveRun",
    "ResumeObservation",
    "resume_refusals",
]

# The forge's own `state` words for a pull request, as `gh pr view --json state`
# renders them. Spelled here so the comparison is against a named constant
# rather than against a literal a caller might case differently.
PR_STATE_OPEN = "OPEN"
PR_STATE_CLOSED = "CLOSED"
PR_STATE_MERGED = "MERGED"

_READY_STATUS = "ready"
_ACTIVE_STATUS = "active"


@dataclass(frozen=True, kw_only=True)
class LiveRun:
    """One non-terminal run of this item, as its factory reports it.

    The STATUS rides with the id because the clause requires the refusal to name
    "the run id and its status", and the two answers an operator needs are
    different: the id says which run to look at, the status says whether to wait
    for it or reconcile it.
    """

    run_id: str
    status: str


@dataclass(frozen=True, kw_only=True)
class ResumeObservation:
    """Every measurement the refusal ladder grades, gathered before it runs.

    FOUR FIELDS ENCODE "COULD NOT BE ASKED" DISTINCTLY FROM AN ANSWER, because
    for each of them the two support opposite decisions. `pull_request_state` and
    `pull_request_head` are `None` when the forge did not answer — never when it
    answered that there is nothing there, which `pull_request=None` says. And
    `liveness_observed` is false when the factory did not answer, which is
    deliberately not the same value as the empty `live_runs` tuple an answering
    factory with nothing alive produces.

    `forge_observed` is the fourth, and it is the one whose absence cost the most.
    A forge outage leaves no pull request NUMBER either, so without it the
    nothing-to-resume-from arm fired and advised a plain dispatch — which reclaims
    the publish branch, preserving the dead run's head to a ref and deleting the
    branch, so a transient `gh` failure destroyed the publication the resume
    exists to finish and left a journal record reading like a healthy recovery.
    It defaults to TRUE so every caller that measured the forge successfully, and
    every caller written before the field existed, is unchanged.

    `changed_assertions` is the Definition-of-Done difference as a LIST of the
    assertions the anchoring record does not carry, rather than a boolean, so the
    refusal can name the difference the clause requires it to name.
    """

    work_item_id: str
    status: str
    blocked_reason: str | None = None
    anchor_head: str | None = None
    forge_observed: bool = True
    pull_request: int | None = None
    pull_request_state: str | None = None
    pull_request_head: str | None = None
    live_runs: tuple[LiveRun, ...] = ()
    liveness_observed: bool = False
    lock_age_seconds: float | None = None
    changed_assertions: tuple[str, ...] = ()
    earlier_resumes: tuple[str, ...] = field(default=())


def resume_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """Every applicable refusal, in the clause's listed order; empty to proceed.

    Each arm appends rather than returns, per the conjunction rule above. The
    anchor arms run BEFORE the head comparison because a resume with no anchor
    has no head to compare, and reporting a mismatch against an absent head
    would name a sha nobody published as the one the record carries.
    """
    return (
        *_status_refusals(observation=observation),
        *_anchor_refusals(observation=observation),
        *_head_refusals(observation=observation),
        *_definition_of_done_refusals(observation=observation),
        *_liveness_refusals(observation=observation),
        *_lock_refusals(observation=observation),
        *_pull_request_state_refusals(observation=observation),
        *_resume_chain_refusals(observation=observation),
    )


def _status_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The not-`ready` refusal, with the remedy its status actually calls for.

    The two remedies answer two different situations and the status alone
    discriminates them. An item resting at `blocked` carries a human decision in
    the ledger, which `resolve-blocked` is the valve for; an `active` item carries
    a CLAIM whose run has ended, which is what `reconcile-runs` releases. Naming
    either remedy for the other sends the operator to a valve that will refuse.
    """
    if observation.status == _READY_STATUS:
        return ()
    if observation.status == _ACTIVE_STATUS:
        stranded = (
            f"the item is {observation.status}, not ready; a resume never steps around"
            " the ledger's own disposition — release the stranded claim with"
            " `dispatcher.py reconcile-runs` first"
        )
        return (stranded,)
    reason = "" if observation.blocked_reason is None else f" / {observation.blocked_reason}"
    parked = (
        f"the item is {observation.status}{reason}, not ready; a resume never steps"
        " around the ledger's human decision — release it with"
        f" `resolve-blocked:{observation.work_item_id}:ready` first"
    )
    return (parked,)


def _anchor_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The nothing-to-resume-from refusals: no open pull request, or no head.

    Two refusals rather than one because the remedy is the same but the FACT is
    not: an item with no pull request never published, while an item whose pull
    request carries no head-naming record published before the head declaration
    was ratified. An operator reading the second knows a resume can never work
    for that pull request, however many times it is retried.

    The UNOBSERVABLE forge read is a THIRD, and it precedes both: it is the same
    question — does this branch carry a pull request — gone unanswered, so it sits
    where that measurement would have sat. Its remedy is deliberately NOT a plain
    dispatch, which is the difference that matters: a plain dispatch reclaims the
    branch, so advising one on an unmeasured read destroys the publication this
    whole surface exists to finish.
    """
    if not observation.forge_observed:
        unobservable = (
            "the forge could not report whether this item's publish branch carries"
            " a pull request, so the publication a resume would finish could not be"
            " measured at all; a resume does not proceed on an unobservable answer."
            " Retry once the forge answers"
        )
        return (unobservable,)
    if observation.pull_request is None:
        unpublished = (
            "the item's publish branch carries no open pull request, so there is"
            " nothing to resume from; dispatch it plainly instead"
        )
        return (unpublished,)
    if observation.anchor_head is None:
        headless = (
            f"no Proof of Done record on pull request #{observation.pull_request}"
            " names a publish-branch head, so no record can anchor a resume;"
            " dispatch it plainly instead"
        )
        return (headless,)
    return ()


def _head_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The moved-head refusal, and the forge-unobservable refusal in its place.

    A `pr` node that rebased and pushed before terminating leaves exactly the
    moved-head state, and the refusal is deliberate: proof verified on one tree
    is not proof of another. The remedy is a plain dispatch, which reclaims the
    branch.
    """
    if observation.anchor_head is None or observation.pull_request is None:
        return ()
    if observation.pull_request_head is None:
        unobservable = (
            f"the forge could not report the head of pull request #{observation.pull_request},"
            " so whether it still carries the head the record names could not be"
            " measured; a resume does not proceed on an unobservable answer"
        )
        return (unobservable,)
    if observation.pull_request_head != observation.anchor_head:
        moved = (
            f"pull request #{observation.pull_request} is now at"
            f" {observation.pull_request_head} while its latest record names"
            f" {observation.anchor_head}; proof verified on one tree is not proof of"
            " another, so dispatch it plainly instead, which reclaims the branch"
        )
        return (moved,)
    return ()


def _definition_of_done_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The changed-Definition-of-Done refusal, naming each unproved assertion.

    The clause's reason is what fixes the wording: the inherited records must
    "prove exactly the assertions the resumed dispatch is graded on". So the
    refusal names the assertions the anchoring record does NOT carry, which is
    the actionable half — an operator can read which assertion arrived after the
    earlier run and decide whether a plain dispatch is what they want.
    """
    if not observation.changed_assertions:
        return ()
    named = "; ".join(observation.changed_assertions)
    changed = (
        "the item's Definition of Done has changed since the earlier run: its"
        f" latest record does not carry {named}. The inherited records would not"
        " prove what this dispatch is graded on, so dispatch it plainly instead"
    )
    return (changed,)


def _liveness_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The live-earlier-run refusal, and the factory-unobservable one in its place.

    This runs AFTER the dispatch preamble's orphan reconciliation, so a run named
    here is one reconciliation could not or did not terminate — which is why the
    remedy is to wait or to reconcile rather than to retry.
    """
    if not observation.liveness_observed:
        unobservable = (
            "the factory could not report the earlier run's liveness, so whether it"
            " has ended could not be measured; a resume does not proceed on an"
            " unobservable answer"
        )
        return (unobservable,)
    if not observation.live_runs:
        return ()
    named = ", ".join(f"{one.run_id} ({one.status})" for one in observation.live_runs)
    live = (
        f"the earlier run is still live on its factory: {named}. Wait for it to end,"
        " or reconcile it with `dispatcher.py reconcile-runs`"
    )
    return (live,)


def _lock_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The live-ownership-lock refusal, naming the age, as `reconcile-merged` does."""
    if observation.lock_age_seconds is None:
        return ()
    held = (
        "this item's dispatch-scoped ownership lock is held by a live process,"
        f" {observation.lock_age_seconds:.0f}s old; wait for that dispatch to"
        " release it rather than running two against one branch"
    )
    return (held,)


def _pull_request_state_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The closed and merged refusals, each with the remedy its state calls for."""
    if observation.pull_request is None or observation.pull_request_state is None:
        return ()
    if observation.pull_request_state == PR_STATE_MERGED:
        merged = (
            f"pull request #{observation.pull_request} is already merged, so there is"
            " no unmerged publication left to finish; close the item out with"
            f" `dispatcher.py reconcile-merged --item {observation.work_item_id}`,"
            " which is the only valve for a real merge"
        )
        return (merged,)
    if observation.pull_request_state != PR_STATE_OPEN:
        closed = (
            f"pull request #{observation.pull_request} is"
            f" {observation.pull_request_state.casefold()} without merging, so no open"
            " publication remains for a resumed run to finish; dispatch it plainly"
            " instead"
        )
        return (closed,)
    return ()


def _resume_chain_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The third-resume refusal, naming both earlier resumes.

    The proof-loop caps of the dispatch section are PER RUN, so a chain of
    resumes would re-arm them indefinitely; the chain is bounded on the host
    instead. Naming both earlier resumes is what lets an operator see that the
    bound has been reached rather than reading the refusal as a transient.
    """
    if len(observation.earlier_resumes) < _RESUME_CHAIN_CAP:
        return ()
    named = ", ".join(observation.earlier_resumes)
    capped = (
        f"pull request #{observation.pull_request} has already anchored"
        f" {len(observation.earlier_resumes)} resumes ({named}); the chain is bounded"
        " on the host because the proof-loop caps are per run, so dispatch it"
        " plainly instead"
    )
    return (capped,)


# Two resumes of one pull request are admitted; the THIRD is refused. The caps
# this bound replaces are per run, so without it a chain of resumes re-arms them
# without limit.
_RESUME_CHAIN_CAP = 2


def live_runs_from_pairs(*, pairs: Sequence[tuple[str, str]]) -> tuple[LiveRun, ...]:
    """Build the live-run tuple from the (id, status) pairs a factory answered with.

    A builder rather than a comprehension at the call site because the ORDER of
    the pair is the thing a caller gets wrong, and a swapped pair produces a
    refusal that reads as a status named where an id belongs — plausible,
    actionable-looking, and pointing at nothing.
    """
    return tuple(LiveRun(run_id=run_id, status=status) for run_id, status in pairs)
