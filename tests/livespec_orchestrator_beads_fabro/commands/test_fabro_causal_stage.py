"""Tests for the causal-stage reading of a terminated run's loop signatures."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import causal_stage_failure

_PR = "pr|deterministic|acp turn failed"
_REVIEW = "review|deterministic|acp turn failed"
_PR_SECOND = "pr|transient_infra|acp turn failed"
_TERMINAL = "needs_human|deterministic|script failed"


def test_no_signature_at_all_is_the_agent_reported_ending() -> None:
    assert causal_stage_failure(signatures=()) is None


def test_the_terminals_own_signature_alone_attributes_nothing() -> None:
    """The dead-end node ran; that says nothing about why it was reached."""
    assert causal_stage_failure(signatures=(_TERMINAL,)) is None


def test_one_causal_signature_names_its_stage() -> None:
    failure = causal_stage_failure(signatures=(_PR,))

    assert failure is not None
    assert failure.stages == ("pr",)
    assert failure.signatures == (_PR,)


def test_the_terminals_signature_does_not_displace_the_causal_one() -> None:
    """Both arrive from one unordered map; only one of them can be a cause."""
    failure = causal_stage_failure(signatures=(_TERMINAL, _PR))

    assert failure is not None
    assert failure.stages == ("pr",)
    assert failure.signatures == (_PR,)


def test_several_stages_are_all_carried_in_the_order_they_arrive() -> None:
    failure = causal_stage_failure(signatures=(_PR, _REVIEW))

    assert failure is not None
    assert failure.stages == ("pr", "review")
    assert failure.signatures == (_PR, _REVIEW)


def test_two_signatures_for_one_stage_name_that_stage_once() -> None:
    """A node can fail twice under different categories; it is still one stage."""
    failure = causal_stage_failure(signatures=(_PR, _PR_SECOND))

    assert failure is not None
    assert failure.stages == ("pr",)
    assert failure.signatures == (_PR, _PR_SECOND)


def test_a_signature_with_no_separator_is_read_as_a_bare_stage_name() -> None:
    """The engine owns this format; a field-less value degrades, never raises."""
    failure = causal_stage_failure(signatures=(" pr ",))

    assert failure is not None
    assert failure.stages == ("pr",)
