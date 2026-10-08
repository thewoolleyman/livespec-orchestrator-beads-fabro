"""A forge that cannot be asked is its own refusal, not a branch with no pull request.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" ends its refusal list with the rule that this file exists for:
"When the forge cannot report the pull request's head or state, or a factory
cannot report the earlier run's liveness, the resume MUST refuse with the same
exit code naming the measurement it could not take; it MUST NOT proceed on an
unobservable answer." Scenario 143's last arm asserts it.

WHY THE LADDER NEEDED A NEW ARM RATHER THAN REUSING THE ONE BESIDE IT. The
factory half of that sentence was already covered — `liveness_observed` false
renders its own refusal. The FORGE half was not, and it failed in the worst
available direction: a forge outage leaves no pull request number, so the
nothing-to-resume-from arm fired and told the operator the branch "carries no
open pull request, so there is nothing to resume from; dispatch it plainly
instead". That advice is a plain dispatch, which RECLAIMS the publish branch —
preserving the dead run's head to a ref and deleting the branch — so a transient
`gh` failure would have destroyed the very publication the resume exists to
finish, and the journal would read like a healthy recovery.

WHY THE ARM SITS WHERE IT DOES. The module's own docstring sets the rule: "Each
unobservable sits WHERE the measurement it replaces would have sat, so the order
an operator reads is the order the questions were asked." The forge's "does this
branch carry a pull request" read is the second question, after the ledger's
status, so the refusal replaces the anchor arms rather than preceding the status
one — which is what the conjunction test below pins.

WHY THE OTHER THREE FORGE ARMS MUST STAY SILENT. An unobservable forge read
yields no number, no head and no state, so a ladder that also reported a moved
head or a closed pull request would be naming comparisons against values nobody
read. One unmeasurable read is one refusal.
"""

from __future__ import annotations

import dataclasses

from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    ResumeObservation,
    resume_refusals,
)

_ITEM = "bd-ib-fngpwg"
_HEAD = "f" * 40
_FORGE_OBSERVED = "forge_observed"


def _declared() -> dict[str, dataclasses.Field[object]]:
    return {one.name: one for one in dataclasses.fields(ResumeObservation)}


def _observation(**overrides: object) -> ResumeObservation:
    """A ready item whose every other measurement succeeded."""
    fields: dict[str, object] = {
        "work_item_id": _ITEM,
        "status": "ready",
        "liveness_observed": True,
    }
    fields.update({name: value for name, value in overrides.items() if name in _declared()})
    return ResumeObservation(**fields)  # pyright: ignore[reportArgumentType]


def test_the_observation_carries_whether_the_forge_answered_at_all() -> None:
    """Without the field the ladder cannot tell an outage from an empty branch."""
    assert _FORGE_OBSERVED in _declared()


def test_an_observed_forge_is_the_default_so_every_existing_caller_is_unchanged() -> None:
    """A flipped default would refuse every resume on a measurement that succeeded."""
    assert _declared()[_FORGE_OBSERVED].default is True


def test_an_unobservable_forge_read_refuses_naming_the_measurement() -> None:
    """The clause's own words: name the measurement it could not take."""
    refusals = resume_refusals(observation=_observation(forge_observed=False))
    assert len(refusals) == 1
    assert "could not report" in refusals[0]
    assert "unobservable answer" in refusals[0]


def test_the_unobservable_forge_refusal_does_not_advise_a_plain_dispatch() -> None:
    """A plain dispatch reclaims the branch; that is the destruction this arm prevents."""
    refusals = resume_refusals(observation=_observation(forge_observed=False))
    assert "dispatch it plainly" not in refusals[0]
    assert "nothing to resume from" not in refusals[0]


def test_an_observed_forge_with_no_pull_request_still_advises_a_plain_dispatch() -> None:
    """The control: the genuine empty answer keeps the remedy it always had."""
    refusals = resume_refusals(observation=_observation(pull_request=None))
    assert len(refusals) == 1
    assert "no open pull request" in refusals[0]
    assert "dispatch it plainly" in refusals[0]


def test_an_unobservable_forge_names_no_head_or_state_comparison() -> None:
    """Comparisons against values nobody read are not findings."""
    refusals = resume_refusals(observation=_observation(forge_observed=False))
    joined = " ".join(refusals)
    assert "is now at" not in joined
    assert "without merging" not in joined
    assert "already merged" not in joined


def test_the_status_refusal_still_precedes_the_unobservable_forge_one() -> None:
    """The order an operator reads is the order the questions were asked."""
    refusals = resume_refusals(
        observation=_observation(
            status="blocked", blocked_reason="needs-human", forge_observed=False
        )
    )
    assert len(refusals) == 2
    assert "not ready" in refusals[0]
    assert "could not report" in refusals[1]


def test_an_unobservable_forge_and_an_unobservable_factory_are_both_named() -> None:
    """Two unmeasurable reads are two refusals; naming one hides the other."""
    refusals = resume_refusals(
        observation=_observation(forge_observed=False, liveness_observed=False)
    )
    assert len(refusals) == 2
    assert "could not report" in refusals[0]
    assert "liveness" in refusals[1]


def test_a_healthy_observation_still_proceeds() -> None:
    """The whole-ladder control: nothing added here refuses a resume that should run."""
    assert (
        resume_refusals(
            observation=_observation(
                anchor_head=_HEAD,
                pull_request=2639,
                pull_request_state="OPEN",
                pull_request_head=_HEAD,
            )
        )
        == ()
    )
