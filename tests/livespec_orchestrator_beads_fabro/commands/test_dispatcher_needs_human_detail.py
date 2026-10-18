"""Tests for the needs-human terminal's operator-facing detail."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    NEEDS_HUMAN_CAUSE_ABSENT,
    needs_human_terminal_detail,
    needs_human_terminal_reason,
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
_REF = f"refs/heads/needs-human/{_RUN}"


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
        "terminal reason: not recorded; "
        "whether the tree reached a run-scoped ref is UNKNOWN — the run's record "
        "carries neither the terminal's LIVESPEC_NEEDS_HUMAN_PRESERVED sentinel nor a "
        "failure one, so no ref can be named; rework from the preserve-by-reference "
        "dump pointer instead — see the preserve-by-reference pointer on the item for "
        "the dump digest; no run is waiting, and this record does not establish "
        "whether a stage failed or an agent asked — triage the run to find out before "
        f"answering, then release the item with `resolve-blocked:{_ITEM}:ready` to "
        "re-dispatch, or leave the item blocked"
    )
    # The arm that establishes nothing must not borrow the fault arm's denial,
    # nor the request arm's promise that an answer is owed.
    assert "no agent asked anything" not in detail
    assert "the decision lives in the ledger: answer with" not in detail


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
    """The signature and the failure block are independent reads of one record.

    The stage attribution survives an unreadable block, and that block's own
    silence is now STATED rather than omitted (`bd-ib-3nu5vv`): an attributed
    ending has already claimed a fault, so a reader has to be able to tell a
    cause nobody could read from an ending that had none.
    """
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("pr",), signatures=(_PR_SIGNATURE,)),
        failure=None,
    )

    assert "failed at stage pr after a non-retryable fault" in detail
    assert NEEDS_HUMAN_CAUSE_ABSENT in detail


def test_a_failure_block_with_no_cause_states_that_the_cause_is_absent() -> None:
    """A block that WAS read and carries no cause: the gap is the engine's.

    Distinct from the case above, which could read no block at all, and both
    owe the reader the same statement — neither may print an empty or
    placeholder cause in its place.
    """
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="",
        causal=_causal(stages=("pr",), signatures=(_PR_SIGNATURE,)),
        failure=_failure(cause=None),
    )

    assert "failed at stage pr after a non-retryable fault" in detail
    assert NEEDS_HUMAN_CAUSE_ABSENT in detail


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


def test_a_preservation_sentinel_naming_no_ref_reads_as_unknown() -> None:
    """A sentinel is only evidence when it IDENTIFIES the ref it claims.

    Reporting the empty string as the preserved ref would claim preservation on
    a ref nobody can fetch — the exact class of claim the three-way invariant
    exists to refuse, reached through the positive arm rather than through
    silence. A later line that DOES name a ref is still read, so this is a case
    about skipping an empty sentinel and not about abandoning the scan.
    """
    blank = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text="LIVESPEC_NEEDS_HUMAN_PRESERVED: \n",
        causal=_unestablished(),
        failure=None,
    )

    assert "whether the tree reached a run-scoped ref is UNKNOWN" in blank
    assert "the tree was preserved on" not in blank

    named = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=_RUN,
        text=f"LIVESPEC_NEEDS_HUMAN_PRESERVED: \nLIVESPEC_NEEDS_HUMAN_PRESERVED: {_REF}\n",
        causal=_unestablished(),
        failure=None,
    )

    assert f"the tree was preserved on {_REF}" in named


def test_an_unparsed_run_id_renders_the_unknown_run_label_and_offers_no_ref() -> None:
    """A run-scoped ref cannot be named without one, so none is claimed.

    The run LABEL still degrades to `unknown-run`, because the detail has to
    name its subject. What changed is the preservation verdict: an unparsed
    launch id is a gap in THIS reader's evidence and says nothing about what
    the terminal pushed, so it reports unknown rather than alleging a failed
    push the record never mentions.
    """
    detail = needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=None,
        text="",
        causal=_unestablished(),
        failure=None,
    )

    assert "run unknown-run terminated at the needs_human node" in detail
    assert "refs/heads/needs-human/" not in detail
    assert "whether the tree reached a run-scoped ref is UNKNOWN" in detail
    assert "the tree was not pushed" not in detail


def test_the_shared_reason_parse_answers_none_for_every_absence() -> None:
    """The parse both surfaces read, on the three ways a reason can fail to arrive.

    PUBLIC and shared because the DURABLE ledger record reads the same line from
    the same text (work-item bd-ib-qhv7qs), and it reaches that record as an
    already-parsed field: the writer runs long after the run's output is gone.
    So the three absences are asserted here, at the one implementation, rather
    than twice at two renderings that could come to disagree.

    Each absence is a DIFFERENT shape of the same answer, and the middle one is
    the one a naive partition crashes on rather than returns: a sentinel sitting
    at the very end of the captured output leaves NO line after it at all, which
    is exactly what a truncated stream produces.
    """
    assert needs_human_terminal_reason(text="") is None
    assert needs_human_terminal_reason(text="ordinary output with no sentinel\n") is None
    assert needs_human_terminal_reason(text="LIVESPEC_NEEDS_HUMAN: ") is None
    assert needs_human_terminal_reason(text="LIVESPEC_NEEDS_HUMAN:    \nmore output\n") is None


def test_the_shared_reason_parse_strips_the_routing_suffix_and_stops_at_the_line() -> None:
    """The recorded reason, without the suffix every ending carries and without the rest.

    The suffix is the terminal's own routing sentence, which is identical on
    every ending and therefore carries nothing an operator reads; the line bound
    is what keeps a later log line out of a reason the record cannot be edited
    to remove.
    """
    text = (
        "LIVESPEC_NEEDS_HUMAN: open Red commit a1b2c3d at the branch head; run "
        "terminated, work preserved by reference, decision routed to the ledger "
        "(blocked / needs-human)\nsome later line\n"
    )

    assert needs_human_terminal_reason(text=text) == "open Red commit a1b2c3d at the branch head"
