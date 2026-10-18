"""Which of a resume's refusals FORBID a fallback, as against merely permitting one.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" draws the line and then routes
on it: a refusal is "*fallback-permitting* when its named remedy is a plain
dispatch", and "Every other refusal is *non-fallback*: the earlier run is live,
the item's dispatch-scoped ownership lock is held by a live process, or the pull
request is merged (its remedy stays `reconcile-merged --item`)". A non-fallback
refusal routes `held`, and it "takes precedence over every fallback-permitting
one, so a merged pull request is never treated as a missing anchor".

WHY THE CLASS IS A PROPERTY OF THE REMEDY RATHER THAN OF THE REFUSAL'S SEVERITY.
Every fallback-permitting refusal ends in "dispatch it plainly instead", and a
plain dispatch is exactly what the fallback routes — `seeded` or `fresh` — do. So
for those the Dispatcher can carry out the refusal's own advice unattended, and
the clause requires it to. The other three name remedies nothing here can
perform: waiting for a live run to end, waiting for or clearing a lock another
process holds, and `reconcile-merged --item`. Performing a fallback over any of
them does not merely ignore the advice; it does the one thing the remedy exists
to prevent — a second run against a branch the first is still pushing to, or an
empty branch cut against work that has already landed.

PURE, AND THE TEXT IS BORROWED RATHER THAN WRITTEN — the same discipline, for the
same reason, as `_dispatcher_recovery_measurements` beside it. The clause requires
a held item's record to carry "every applicable non-fallback refusal with its
EXISTING remedy in the order the resume's refusals are listed". Each arm is
therefore rendered by the arm of `_dispatcher_resume_refusals` that owns it and
carried here verbatim: two renderings of one refusal are free to drift, and the
journal would then say something the refusal an operator reads does not.

WHY THE CONDITIONS SELECT RATHER THAN RE-DERIVE. `lock_refusals` renders exactly
one refusal and only for a live lock, so it is asked unconditionally and whatever
it says is the answer. The arms that serve BOTH classes need a condition, because
one function renders the fallback-permitting case too — and in each of those the
condition names the state the clause calls non-fallback, never the absence of the
other one.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    PR_STATE_MERGED,
    ResumeObservation,
    liveness_refusals,
    lock_refusals,
    pull_request_state_refusals,
)

__all__: list[str] = [
    "non_fallback_refusals",
]


def non_fallback_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """Every applicable non-fallback refusal, in the resume's own listed order.

    EMPTY means every refusal this observation carries is fallback-permitting,
    which is the precondition for grading a `seeded` or `fresh` route at all —
    and deliberately not the same as "there are no refusals", which is the
    precondition for a `resume`.
    """
    return (
        *_live_run_refusals(observation=observation),
        *lock_refusals(observation=observation),
        *_merged_refusals(observation=observation),
    )


def _live_run_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The still-live earlier run, and never the factory that could not be asked.

    `liveness_refusals` renders BOTH, and the two are the same measurement read
    two ways: an unanswered factory routes `held` on the MEASUREMENT, while an
    answering factory naming a live run routes `held` on this REFUSAL. The
    unobservable arm is already graded one step earlier, by
    `unobservable_measurements`, so asking for it again here would put one hold
    in both of the record's lists and tell an operator to wait for a read that
    answered.

    This arm is the most expensive of the three to omit: a released item whose
    earlier run is ALIVE and one whose earlier run has ENDED present identically
    at every other surface — both `ready`, both with a standing publish branch,
    both with verifiable preserved work — so a fallback taken here starts a
    second run against a branch the first is still pushing to.
    """
    if not observation.liveness_observed or not observation.live_runs:
        return ()
    return liveness_refusals(observation=observation)


def _merged_refusals(*, observation: ResumeObservation) -> tuple[str, ...]:
    """The merged-pull-request refusal, and never the closed one beside it.

    `pull_request_state_refusals` renders BOTH states, and they fall on opposite
    sides of the line: a pull request closed without merging names a plain
    dispatch, which is what a fallback route performs, while a MERGED one names
    `reconcile-merged --item`, which nothing in routing can perform. So the
    state is tested here and the TEXT is still taken from that arm — selecting
    rather than re-deriving, which is what keeps the journal row and the refusal
    an operator reads one account of one measurement.
    """
    if observation.pull_request_state != PR_STATE_MERGED:
        return ()
    return pull_request_state_refusals(observation=observation)
