"""The needs-human detail claims only what the run's own record establishes.

Two claims in that detail are acted on directly, and each had a path to being
asserted on no evidence at all.

PRESERVATION. A rework either starts from a run-scoped ref or it does not, and
the operator chooses before finding out. The render used to treat SILENCE as
the preserved arm: absent an explicit failure sentinel it asserted
`refs/heads/needs-human/<run>`, so every record that said nothing about
preservation — a legacy ending, an empty output capture, a reader that never saw
the terminal's stderr — pointed at a ref `git fetch` cannot find. A missing
failure marker is not positive evidence of a successful push.

The terminal node emits a POSITIVE sentinel, `LIVESPEC_NEEDS_HUMAN_PRESERVED:
<ref>`, and it names the ref it actually pushed. So the invariant is three-way
and each arm needs its own evidence: a positive sentinel means preserved, an
explicit negative sentinel means failed, and the absence of both means UNKNOWN.
Unknown is not a failure claim either — inventing a failed push sends the
operator to the dump pointer when the ref is really there, which is the same lie
pointing the other way.

A PARSE GAP IS NOT A PUSH FAILURE, which is the edge that makes the rule worth
stating separately. Failing to parse a run id from the launch output says
nothing about what the terminal did; it can even co-exist with a positive
sentinel that names the ref outright. So an unparsed run id degrades to unknown,
and a positive sentinel still wins over it.

DECISION GUIDANCE. "The decision lives in the ledger: answer with
`resolve-blocked:...`" was rendered unconditionally, so a transport fault told
its triager that a human question awaited an answer. No agent asked, there is
nothing to answer, and the remedy is triage-then-re-dispatch rather than a
decision. The valve is still named in every arm, because it is the only route
out of `blocked`; what changes is whether the detail claims a question is
pending.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    needs_human_terminal_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
    UNESTABLISHED,
    CausalStageFailure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

_ITEM = "bd-ib-anfa5t"
_RUN = "01M44F9E56XCEWZNMVJX4M14Z6"
_REF = f"refs/heads/needs-human/{_RUN}"
_PR_SIGNATURE = "pr|deterministic|acp turn failed"
_CAUSE = "ACP tool call toolu_01 (git push -u origin HEAD) continued in background as task b9"

_PRESERVED_LINE = f"{NEEDS_HUMAN_MARKER}_PRESERVED: {_REF}"
_PUSH_FAILED_LINE = f"{NEEDS_HUMAN_MARKER}_PUSH_FAILED: tree not pushed; rely on the dump pointer"
_NO_RUN_ID_LINE = f"{NEEDS_HUMAN_MARKER}_NO_RUN_ID: no run id arrived on the stdin of this node"
# A legacy ending: the bare marker and its reason, and NOT one word about
# whether anything was pushed. This is the shape the silence rule mis-read.
_LEGACY_LINE = (
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run terminated, "
    "work preserved by reference, decision routed to the ledger (blocked / needs-human)"
)

# Deliberately shares NO substring with the positive claim
# `the tree was preserved on <ref>`: the cases below assert that the positive
# phrase is ABSENT from the unknown arm, so an unknown wording that merely
# embedded it would satisfy both assertions while still reading, to a human
# skimming the line, as a preservation claim.
_UNKNOWN_PRESERVATION = "whether the tree reached a run-scoped ref is UNKNOWN"


def _verdict(*, kind: str) -> CausalStageFailure:
    stages = ("pr",) if kind == STAGE_FAILURE else ()
    signatures = (_PR_SIGNATURE,) if kind == STAGE_FAILURE else ()
    return CausalStageFailure(kind=kind, stages=stages, signatures=signatures, history=())


def _detail(
    *,
    text: str,
    kind: str = UNESTABLISHED,
    run_id: str | None = _RUN,
    cause: str | None = None,
) -> str:
    failure = (
        None
        if cause is None
        else FabroFailureDetail(cause=cause, category="deterministic", signature=_PR_SIGNATURE)
    )
    return needs_human_terminal_detail(
        work_item_id=_ITEM,
        run_id=run_id,
        text=text,
        causal=_verdict(kind=kind),
        failure=failure,
    )


def test_a_positive_sentinel_names_the_ref_the_terminal_actually_pushed() -> None:
    """The ref comes FROM the sentinel, not from the run id it happens to match."""
    detail = _detail(text=f"{_PRESERVED_LINE}\n{_LEGACY_LINE}\n")

    assert f"the tree was preserved on {_REF}" in detail
    assert _UNKNOWN_PRESERVATION not in detail


def test_a_positive_sentinel_naming_another_ref_is_quoted_rather_than_rewritten() -> None:
    """The node owns the ref it pushed; a derived one would contradict the record."""
    other = "refs/heads/needs-human/01ADIFFERENTRUNID"
    detail = _detail(text=f"{NEEDS_HUMAN_MARKER}_PRESERVED: {other}\n")

    assert f"the tree was preserved on {other}" in detail
    assert _REF not in detail


def test_silence_about_preservation_is_unknown_and_claims_no_ref() -> None:
    """A record that never mentions a push has not reported a successful one."""
    detail = _detail(text="")

    assert _UNKNOWN_PRESERVATION in detail
    assert "the tree was preserved on" not in detail
    assert "refs/heads/needs-human/" not in detail
    # Unknown is not the failure claim either — that would be the mirror lie.
    assert "the tree was not pushed" not in detail


def test_a_legacy_marker_without_a_preservation_sentinel_is_unknown() -> None:
    """The exact shape the old nonempty-text fallback claimed success from."""
    detail = _detail(text=f"{_LEGACY_LINE}\n")

    assert _UNKNOWN_PRESERVATION in detail
    assert "the tree was preserved on" not in detail


def test_an_explicit_push_failure_is_still_reported_as_a_failure() -> None:
    """The negative sentinel is positive evidence and keeps its own arm."""
    detail = _detail(text=f"{_PUSH_FAILED_LINE}\n{_LEGACY_LINE}\n")

    assert "the tree was not pushed" in detail
    assert "NOT preserved" in detail
    assert _UNKNOWN_PRESERVATION not in detail
    assert "preserve-by-reference dump pointer" in detail


def test_an_explicit_absent_run_id_sentinel_is_still_reported_as_a_failure() -> None:
    """The node said no run id reached it, so it pushed nothing; that is evidence."""
    detail = _detail(text=f"{_NO_RUN_ID_LINE}\n{_LEGACY_LINE}\n")

    assert "the tree was not pushed" in detail
    assert _UNKNOWN_PRESERVATION not in detail


def test_an_unparsed_run_id_alone_is_unknown_rather_than_a_push_failure() -> None:
    """Failing to parse a launch id says nothing about what the terminal pushed."""
    detail = _detail(text="", run_id=None)

    assert _UNKNOWN_PRESERVATION in detail
    assert "the tree was not pushed" not in detail
    assert "no run id was parsed from the launch output" not in detail
    # The run is still labelled, because the detail has to name its subject.
    assert "run unknown-run terminated" in detail


def test_a_positive_sentinel_outranks_an_unparsed_run_id() -> None:
    """The sentinel names the ref outright, so no parse gap can hide it."""
    detail = _detail(text=f"{_PRESERVED_LINE}\n", run_id=None)

    assert f"the tree was preserved on {_REF}" in detail
    assert _UNKNOWN_PRESERVATION not in detail


def test_a_genuine_request_keeps_its_decision_guidance_verbatim() -> None:
    """Assertion 3: the arm that was never mis-rendered does not change."""
    detail = _detail(text=f"{_PRESERVED_LINE}\n{_LEGACY_LINE}\n", kind=AGENT_REQUEST)

    assert (
        "no run is waiting — the decision lives in the ledger: answer with "
        f"`resolve-blocked:{_ITEM}:ready`"
    ) in detail
    assert f"the tree was preserved on {_REF}" in detail


def test_a_transport_fault_is_not_offered_as_a_question_to_answer() -> None:
    """A fault arm must not imply a human question is awaiting an answer."""
    detail = _detail(
        text=f"{_PRESERVED_LINE}\n{_LEGACY_LINE}\n",
        kind=STAGE_FAILURE,
        cause=_CAUSE,
    )

    assert "the decision lives in the ledger: answer with" not in detail
    assert "no question to answer" in detail
    # The valve is STILL named: it is the only route out of blocked.
    assert f"resolve-blocked:{_ITEM}:ready" in detail
    # And the guidance names triage and re-dispatch rather than a decision.
    assert "triage" in detail


def test_an_unestablished_ending_offers_the_valve_without_claiming_a_question() -> None:
    """Nothing is established, so neither a pending question nor a fault is claimed."""
    detail = _detail(text=f"{_LEGACY_LINE}\n", kind=UNESTABLISHED)

    assert f"resolve-blocked:{_ITEM}:ready" in detail
    assert "the decision lives in the ledger: answer with" not in detail
    assert "no agent asked anything" not in detail
