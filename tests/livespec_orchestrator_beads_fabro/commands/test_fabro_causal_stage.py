"""The verdict between the three endings a needs-human terminal can describe.

Rewritten from the loop-signature reading this module shipped with, because
that reading reached `AGENT_REQUEST` by SILENCE and the silence is ambiguous on
real records. The cases below therefore pin the one thing the old API could not
express: that an unreadable outcome map is `UNESTABLISHED` and not a question.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
    UNESTABLISHED,
    causal_stage_failure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import TerminalEvidence

_PR = "pr|deterministic|acp turn failed"
_REVIEW = "review|deterministic|acp turn failed"
_PR_SECOND = "pr|transient_infra|acp turn failed"


def _evidence(
    *,
    failed: tuple[str, ...] = (),
    signatures: tuple[str, ...] = (),
    history: tuple[str, ...] = (),
    observed: bool = True,
) -> TerminalEvidence:
    return TerminalEvidence(
        current_predecessor=failed[-1] if failed else None,
        failed_stages=failed,
        stage_signatures=signatures,
        history_signatures=history,
        outcomes_observed=observed,
    )


def test_a_read_outcome_map_with_no_failure_is_the_agent_reported_ending() -> None:
    """Positive evidence that nothing failed is what licenses "an agent asked"."""
    verdict = causal_stage_failure(evidence=_evidence())

    assert verdict.kind == AGENT_REQUEST
    assert verdict.is_stage_failure is False
    assert verdict.stages == ()


def test_absent_evidence_is_unestablished_and_never_a_question() -> None:
    """No terminal checkpoint read at all attributes nothing and denies nothing."""
    verdict = causal_stage_failure(evidence=None)

    assert verdict.kind == UNESTABLISHED
    assert verdict.is_stage_failure is False
    assert (verdict.stages, verdict.signatures, verdict.history) == ((), (), ())


def test_an_unread_outcome_map_is_unestablished_even_carrying_a_signature() -> None:
    """The signature cannot be graded, so it is history and the verdict is open.

    This is the arm the old silence-based reading could not reach: it would have
    attributed the signature as this ending's cause.
    """
    verdict = causal_stage_failure(evidence=_evidence(history=(_PR,), observed=False))

    assert verdict.kind == UNESTABLISHED
    assert verdict.stages == ()
    assert verdict.history == (_PR,)


def test_one_failed_stage_names_itself_and_its_signature() -> None:
    verdict = causal_stage_failure(evidence=_evidence(failed=("pr",), signatures=(_PR,)))

    assert verdict.kind == STAGE_FAILURE
    assert verdict.is_stage_failure is True
    assert verdict.stages == ("pr",)
    assert verdict.signatures == (_PR,)


def test_several_failed_stages_are_all_carried_in_evidence_order() -> None:
    """Naming one of several would hide the rest behind a complete-looking answer."""
    verdict = causal_stage_failure(
        evidence=_evidence(failed=("review", "pr"), signatures=(_REVIEW, _PR))
    )

    assert verdict.stages == ("review", "pr")
    assert verdict.signatures == (_REVIEW, _PR)


def test_two_signatures_for_one_stage_keep_both_under_that_one_stage() -> None:
    """A node can fail twice under different categories; it is still one stage."""
    verdict = causal_stage_failure(evidence=_evidence(failed=("pr",), signatures=(_PR, _PR_SECOND)))

    assert verdict.stages == ("pr",)
    assert verdict.signatures == (_PR, _PR_SECOND)


def test_a_stage_failure_still_reports_its_outlived_history() -> None:
    """An earlier recovered failure is the run's account, not this ending's cause."""
    verdict = causal_stage_failure(
        evidence=_evidence(failed=("pr",), signatures=(_PR,), history=(_REVIEW,))
    )

    assert verdict.kind == STAGE_FAILURE
    assert verdict.stages == ("pr",)
    assert verdict.history == (_REVIEW,)


def test_an_agent_request_after_a_recovered_failure_keeps_the_signature_as_history() -> None:
    """The negative control: a stale signature must not turn a question into a fault."""
    verdict = causal_stage_failure(evidence=_evidence(history=(_REVIEW,)))

    assert verdict.kind == AGENT_REQUEST
    assert verdict.stages == ()
    assert verdict.history == (_REVIEW,)
