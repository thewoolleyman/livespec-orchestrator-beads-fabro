"""Tests for the needs-human terminal's operator-facing detail."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    needs_human_terminal_detail,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    STAGE_FAILURE,
    UNESTABLISHED,
    CausalStageFailure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

_ITEM = "bd-ib-qm4luz"
_RUN = "01M44F9E56XCEWZNMVJX4M14Z6"
_PR_SIGNATURE = "pr|deterministic|acp turn failed"
_REVIEW_SIGNATURE = "review|deterministic|acp turn failed"
_CAUSE = "ACP tool call toolu_01 (git push) continued in background as task b9hp9md1u"


def _causal(
    *,
    stages: tuple[str, ...],
    signatures: tuple[str, ...],
    history: tuple[str, ...] = (),
) -> CausalStageFailure:
    return CausalStageFailure(
        kind=STAGE_FAILURE,
        stages=stages,
        signatures=signatures,
        history=history,
    )


def _unestablished(*, history: tuple[str, ...] = ()) -> CausalStageFailure:
    """The arm a record that grounds no attribution lands in."""
    return CausalStageFailure(kind=UNESTABLISHED, stages=(), signatures=(), history=history)


def _failure(*, cause: str | None) -> FabroFailureDetail:
    return FabroFailureDetail(
        cause=cause,
        category="deterministic",
        signature=_PR_SIGNATURE,
    )


def test_an_unattributed_ending_renders_the_whole_account_and_claims_no_cause() -> None:
    """Asserted whole, because the clause ORDER is part of what an operator reads.

    The `terminal reason` clause carries the node's own emitted line, which for
    some failures — a `publish_draft` permission refusal, say — is the only
    account of the fault that exists anywhere in the record.
    """
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_unestablished(),
        failure=None,
    )

    assert detail == (
        f"run {_RUN} terminated at the needs_human node (needs-human); "
        "terminal reason: not recorded; the tree was "
        f"preserved on refs/heads/needs-human/{_RUN} (see the preserve-by-reference "
        "pointer on the item for the dump digest); no run is waiting — the decision "
        f"lives in the ledger: answer with `resolve-blocked:{_ITEM}:ready` "
        "(re-dispatch, seeding rework from the preserved ref or from scratch) or "
        "leave the item blocked"
    )
    # The arm that establishes nothing must not borrow the fault arm's denial.
    assert "no agent asked anything" not in detail


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


def test_a_failed_stage_with_no_recorded_signature_names_the_stage_alone() -> None:
    """The provider-ceiling shape: an explicit failed node and no loop signature.

    The stage attribution must survive the absence, because requiring a
    signature is exactly what made that run read as a question nobody asked.
    An empty signature list is omitted rather than rendered as a dangling label.
    """
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("implement",), signatures=()),
        failure=_failure(cause=_CAUSE),
    )

    assert "failed at stage implement after a non-retryable fault" in detail
    assert f"innermost cause: {_CAUSE}" in detail
    assert "recorded loop failure signature" not in detail


def test_an_outlived_signature_is_labelled_history_and_not_this_endings_cause() -> None:
    """The engine never clears a loop signature a later successful visit outlived.

    So the signature is real and belongs in the account, and attributing it
    would name a stage that is not why this run ended. Both halves are asserted
    together: it IS reported, and it is reported AS history.
    """
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("pr",), signatures=(_PR_SIGNATURE,), history=(_REVIEW_SIGNATURE,)),
        failure=_failure(cause=_CAUSE),
    )

    assert f"recorded loop failure signature: {_PR_SIGNATURE}" in detail
    assert f"NOT as this ending's cause: {_REVIEW_SIGNATURE}" in detail
    # The history must not reach the causal attribution.
    assert "failed at stage pr after" in detail
    assert "failed at stages pr, review" not in detail


def test_an_unattributed_ending_still_reports_the_history_it_carries() -> None:
    """The negative control for the whole attribution, read at the render.

    A run that failed a gate, recovered, and then genuinely asked a question
    lands here: nothing is attributed, no fault is announced, and the stale
    signature is still on the record as history.
    """
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_unestablished(history=(_REVIEW_SIGNATURE,)),
        failure=_failure(cause=_CAUSE),
    )

    assert f"NOT as this ending's cause: {_REVIEW_SIGNATURE}" in detail
    assert "failed at stage" not in detail
    assert "no agent asked anything" not in detail
    # An unattributed ending names no cause, even when the record carries one:
    # the cause belongs to a failure block this ending was not traced to.
    assert "innermost cause" not in detail


def test_an_unparsed_run_id_renders_the_unknown_run_label_and_offers_no_ref() -> None:
    """A run-scoped ref cannot be named without a run id, so none is claimed."""
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=None,
        text="",
        causal=_unestablished(),
        failure=None,
    )

    assert "run unknown-run terminated at the needs_human node" in detail
    assert "refs/heads/needs-human/" not in detail
    assert "no run id was parsed from the launch output" in detail
