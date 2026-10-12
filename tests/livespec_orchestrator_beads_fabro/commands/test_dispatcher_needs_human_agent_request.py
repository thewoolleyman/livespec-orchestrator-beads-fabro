"""An agent-requested needs-human ending keeps its guidance and tells the truth.

Two things a human coming to decide needs from this ending, and the ledger
decision guidance is only one of them. The other is WHAT A REWORK CAN START
FROM, because that is the fact the `resolve-blocked:<item>:ready` answer turns
on: re-dispatch seeded from the preserved tree, or re-dispatch from scratch.

The `needs_human` terminal node pushes its tree BEST-EFFORT and says which
happened — `LIVESPEC_NEEDS_HUMAN_PRESERVED: <ref>` when the push landed,
`LIVESPEC_NEEDS_HUMAN_PUSH_FAILED` when it did not, and
`LIVESPEC_NEEDS_HUMAN_NO_RUN_ID` when no run id reached it so there was no ref
to push at all. Measured on run `01M4C9GDZ7RYB477YXSMNMJWKH`, whose
preservation push FAILED after 256 seconds
(`plan/pr-stage-backgrounded-push-fault/research/001-failure-analysis-and-mechanism-candidates-2026-10-08.md`
section 2.2), and on `bd-ib-cvge`, where it failed a different way.

THE DETAIL NAMED A REF THAT DID NOT EXIST. It derived the ref from the run id
alone and asserted preservation unconditionally, so the two measured failures
read exactly like a successful push — and the one surface an operator reads
first pointed them at a ref `git fetch` cannot find. `_fabro_needs_human_question`
has carried `tree_preserved` separately from `preserved_ref` for precisely this
reason; the terminal's own detail did not.

WHY THE SUCCESSFUL CASE IS ASSERTED BESIDE THE FAILED ONE. Alone, the failed
case is satisfied by a build that stopped naming the ref at all, which would
lose the pointer this ending is supposed to retain. And alone, the successful
case is satisfied by the unconditional claim this module exists to retire. An
ABSENT sentinel is deliberately the successful arm: a record that reports
neither outcome is the ordinary one, and treating silence as failure would
retract a ref that is really there.

A transport fault is NOT one of these endings. An agent that ended through the
needs-human protocol asked a question, so this arm must keep saying a decision
awaits — which is why the stage attribution and the transport-fault
classification are asserted ABSENT here.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)

_ITEM = "bd-ib-555xcd"
_RUN = "01M4C9GDZ7RYB477YXSMNMJWKH"
_REF = f"refs/heads/needs-human/{_RUN}"
_POINTER = "preserve-by-reference pointer on the item for the dump digest"
_GUIDANCE = f"`resolve-blocked:{_ITEM}:ready`"
_PROMPT_LINE = (
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run terminated, "
    "work preserved by reference, decision routed to the ledger (blocked / needs-human)"
)
_PUSH_FAILED_LINE = (
    f"{NEEDS_HUMAN_MARKER}_PUSH_FAILED: tree not pushed; rely on the "
    "preserve-by-reference dump pointer"
)
_NO_RUN_ID_LINE = (
    f"{NEEDS_HUMAN_MARKER}_NO_RUN_ID: no run id arrived on the stdin of this script "
    "node, so no run-scoped ref exists to push and nothing was pushed; rely on the "
    "preserve-by-reference dump pointer"
)


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp.example:32276",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _detail(*, tmp_path: Path, stderr: str) -> str:
    """The terminal's detail for an AGENT-reported ending.

    `inspect=None` is the agent-reported shape: that ending rides a conditional
    edge off a node that SUCCEEDED, so the loop recorded no failure signature
    and there is no engine failure block to read.
    """
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=None,
        exit_code=1,
        stderr=stderr,
    )
    assert outcome is not None
    assert (outcome.status, outcome.stage) == ("blocked", "fabro-run")
    return outcome.detail


def test_a_preserved_tree_is_named_and_the_decision_guidance_is_retained(
    tmp_path: Path,
) -> None:
    """The control: an ending whose push landed still names its ref."""
    detail = _detail(
        tmp_path=tmp_path,
        stderr=f"{NEEDS_HUMAN_MARKER}_PRESERVED: {_REF}\n{_PROMPT_LINE}\n",
    )

    assert f"the tree was preserved on {_REF}" in detail
    assert _POINTER in detail
    assert _GUIDANCE in detail
    assert "leave the item blocked" in detail
    # An agent asked something, so this ending must NOT read as an engine fault.
    assert "failed at stage" not in detail
    assert "transport fault" not in detail
    assert "no agent asked anything" not in detail


def test_a_record_reporting_neither_outcome_claims_neither_outcome(
    tmp_path: Path,
) -> None:
    """Silence names no ref and alleges no failure — it is UNKNOWN, both ways.

    This case asserted the opposite until the three-way invariant landed: it
    read a missing failure marker as positive evidence of a successful push,
    and so pointed every legacy and truncated record at a ref `git fetch`
    cannot find. The mirror claim is refused in the same breath, because
    inventing a failed push sends a rework to the dump pointer while the ref is
    really there.
    """
    detail = _detail(tmp_path=tmp_path, stderr=f"{_PROMPT_LINE}\n")

    assert "whether the tree reached a run-scoped ref is UNKNOWN" in detail
    assert f"the tree was preserved on {_REF}" not in detail
    assert _REF not in detail
    assert "the tree was not pushed" not in detail
    # The route out and the pointer are RETAINED; only the claim is withdrawn.
    assert _POINTER in detail
    assert _GUIDANCE in detail


def test_a_failed_preservation_push_does_not_claim_a_ref_that_does_not_exist(
    tmp_path: Path,
) -> None:
    """The measured failure: the push did not land, so no ref can be offered."""
    detail = _detail(tmp_path=tmp_path, stderr=f"{_PUSH_FAILED_LINE}\n{_PROMPT_LINE}\n")

    assert f"the tree was preserved on {_REF}" not in detail
    assert _REF not in detail
    assert "NOT preserved" in detail
    # The pointer and the guidance are RETAINED: a rework still has a route and
    # the decision still lives in the ledger.
    assert _POINTER in detail
    assert _GUIDANCE in detail


def test_a_terminal_that_received_no_run_id_offers_no_ref_either(
    tmp_path: Path,
) -> None:
    """No run id reached the node, so there was never a ref to push."""
    detail = _detail(tmp_path=tmp_path, stderr=f"{_NO_RUN_ID_LINE}\n{_PROMPT_LINE}\n")

    assert _REF not in detail
    assert "NOT preserved" in detail
    assert _POINTER in detail
    assert _GUIDANCE in detail
