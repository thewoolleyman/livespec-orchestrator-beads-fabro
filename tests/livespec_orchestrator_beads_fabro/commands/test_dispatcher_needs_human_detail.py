"""Tests for the needs-human terminal's operator-facing detail."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    needs_human_terminal_detail,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import CausalStageFailure
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

_ITEM = "bd-ib-qm4luz"
_RUN = "01M44F9E56XCEWZNMVJX4M14Z6"
_PR_SIGNATURE = "pr|deterministic|acp turn failed"
_REVIEW_SIGNATURE = "review|deterministic|acp turn failed"
_CAUSE = "ACP tool call toolu_01 (git push) continued in background as task b9hp9md1u"


def _causal(*, stages: tuple[str, ...], signatures: tuple[str, ...]) -> CausalStageFailure:
    return CausalStageFailure(stages=stages, signatures=signatures)


def _failure(*, cause: str | None) -> FabroFailureDetail:
    return FabroFailureDetail(
        cause=cause,
        category="deterministic",
        signature=_PR_SIGNATURE,
    )


def test_an_agent_reported_ending_keeps_the_wording_it_always_had() -> None:
    """Byte-identical: that arm was never mis-rendered, so it does not change."""
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=None,
        failure=None,
    )

    assert detail == (
        f"run {_RUN} terminated at the needs_human node (needs-human); the tree was "
        f"preserved on refs/heads/needs-human/{_RUN} (see the preserve-by-reference "
        "pointer on the item for the dump digest); no run is waiting — the decision "
        f"lives in the ledger: answer with `resolve-blocked:{_ITEM}:ready` "
        "(re-dispatch, seeding rework from the preserved ref or from scratch) or "
        "leave the item blocked"
    )


def test_an_engine_routed_ending_names_the_stage_cause_and_signature() -> None:
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("pr",), signatures=(_PR_SIGNATURE,)),
        failure=_failure(cause=_CAUSE),
    )

    assert "failed at stage pr after a non-retryable fault" in detail
    assert "no agent asked anything, so there is no question to answer" in detail
    assert f"innermost cause: {_CAUSE}" in detail
    assert f"recorded loop failure signature: {_PR_SIGNATURE}" in detail
    assert f"resolve-blocked:{_ITEM}:ready" in detail


def test_a_cause_that_is_not_a_transport_fault_is_quoted_and_not_labelled() -> None:
    """The control for the classification: not every engine fault is transport."""
    plain = "janitor script exited 1: coverage below 100%"
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("janitor",), signatures=("janitor|deterministic|script failed",)),
        failure=_failure(cause=plain),
    )

    assert f"innermost cause: {plain}" in detail
    assert "transport fault" not in detail


def test_several_causal_stages_are_pluralised_rather_than_reduced_to_one() -> None:
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("pr", "review"), signatures=(_PR_SIGNATURE, _REVIEW_SIGNATURE)),
        failure=_failure(cause=_CAUSE),
    )

    assert "failed at stages pr, review after" in detail
    assert f"recorded loop failure signature: {_PR_SIGNATURE}, {_REVIEW_SIGNATURE}" in detail


def test_an_unreadable_failure_block_still_attributes_the_stage() -> None:
    """The signature and the failure block are independent reads of one record."""
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("pr",), signatures=(_PR_SIGNATURE,)),
        failure=None,
    )

    assert "failed at stage pr after a non-retryable fault" in detail
    assert "innermost cause" not in detail


def test_a_failure_block_with_no_cause_names_no_cause() -> None:
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("pr",), signatures=(_PR_SIGNATURE,)),
        failure=_failure(cause=None),
    )

    assert "failed at stage pr after a non-retryable fault" in detail
    assert "innermost cause" not in detail


def test_an_unparsed_run_id_renders_the_unknown_run_label_and_offers_no_ref() -> None:
    """A run-scoped ref cannot be named without a run id, so none is claimed."""
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=None,
        text="",
        causal=None,
        failure=None,
    )

    assert "run unknown-run terminated at the needs_human node" in detail
    assert "refs/heads/needs-human/" not in detail
    assert "no run id was parsed from the launch output" in detail
