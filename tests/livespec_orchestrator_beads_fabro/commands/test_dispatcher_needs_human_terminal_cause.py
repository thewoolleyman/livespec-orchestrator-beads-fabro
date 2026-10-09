"""The `needs_human` terminal names the stage and the cause that routed it there.

`plan/pr-stage-backgrounded-push-fault/research/001-failure-analysis-and-mechanism-candidates-2026-10-08.md`
section 3.5 measured the gap this module binds: since contract v093 the
`needs_human` node is a TERMINAL script that exits 1, so every needs-human
ending arrives through `_needs_human_terminal_outcome` — which named neither
the stage that failed nor why, and passed none of the structured failure
fields the sibling `failed` outcome a few lines below does pass. The one line
a triager needs (`pr|deterministic|acp turn failed` plus the innermost cause)
existed only in the run export.

THE PAYLOAD IS THE MEASURED SHAPE, SANITIZED. Run
`01M44F9E56XCEWZNMVJX4M14Z6` (work-item `bd-ib-qm4luz`, factory `hp`,
2026-10-04) recorded the cause under the newest checkpoint's
`node_outcomes.pr.failure.causes` with the loop signature beside it, and the
cause chain is outermost-first — `causes[0]` is the fixed wrapper
`ACP protocol error` in 17 of 17 measured blocks — so the INNERMOST element is
the one that carries the fault. Only the tool-call identifier is replaced.

THE SECOND CASE IS THE ONE THAT CANNOT BE SATISFIED BY ACCIDENT. A run that
dies at the `needs_human` terminal records a signature for THAT node too
(`stage needs_human failed with no outgoing fail edge` is how the measured run
ends), and the signatures arrive as an unordered map. A reader that took
whichever signature it met first would name the terminal — the node that could
not possibly be the cause, since it only runs because something else already
failed — and the `pr` attribution the triager needs would be hidden behind a
perfectly plausible answer.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)

_RUN = "01M44F9E56XCEWZNMVJX4M14Z6"
_ITEM = "bd-ib-qm4luz"
_PR_SIGNATURE = "pr|deterministic|acp turn failed"
_TERMINAL_SIGNATURE = "needs_human|deterministic|script failed"
_WRAPPER_CAUSE = "ACP protocol error"
_BACKGROUNDED_CAUSE = (
    "ACP tool call toolu_01SANITIZEDTOOLCALL "
    "(git push -u origin HEAD:refs/heads/feat/bd-ib-qm4luz 2>&1 | tail -100) "
    "continued in background as task b9hp9md1u; Fabro terminated the turn before "
    "the agent could start conflicting work"
)
_STDERR = (
    f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/{_RUN}\n"
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run "
    "terminated, work preserved by reference, decision routed to the ledger "
    "(blocked / needs-human)\n"
)


def _payload(*, signatures: dict[str, int]) -> list[object]:
    """`fabro inspect --json` for a run the engine routed to the terminal."""
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed"},
            "checkpoints": [
                {
                    "checkpoint": {
                        "next_node_id": "needs_human",
                        "loop_failure_signatures": signatures,
                        "node_outcomes": {
                            "pr": {
                                "failure": {
                                    "category": "deterministic",
                                    "signature": _PR_SIGNATURE,
                                    "causes": [_WRAPPER_CAUSE, _BACKGROUNDED_CAUSE],
                                }
                            }
                        },
                    }
                }
            ],
        }
    ]


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


def _outcome(*, tmp_path: Path, signatures: dict[str, int]) -> DispatchOutcome:
    """The terminal outcome, with the payload read by the production parsers."""
    payload = _payload(signatures=signatures)
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
        ),
        exit_code=1,
        stderr=_STDERR,
    )
    assert outcome is not None
    return outcome


def test_the_terminal_names_the_originating_stage_and_its_innermost_cause(
    tmp_path: Path,
) -> None:
    """Stage, innermost cause, and the taxonomy the sibling outcome already carried."""
    outcome = _outcome(tmp_path=tmp_path, signatures={_PR_SIGNATURE: 2})

    assert (outcome.status, outcome.stage, outcome.fabro_run_id) == ("blocked", "fabro-run", _RUN)
    assert "stage pr" in outcome.detail
    assert _BACKGROUNDED_CAUSE in outcome.detail
    # The innermost element of the chain, never the fixed `ACP protocol error`
    # wrapper that reads as a transport label and names no fault.
    assert outcome.fabro_failure_cause == _BACKGROUNDED_CAUSE
    assert outcome.fabro_failure_category == "deterministic"
    assert outcome.fabro_failure_signature == _PR_SIGNATURE
    # The ledger decision guidance stays beside the new attribution, and no
    # `fabro attach` is offered for a run that no longer exists.
    assert f"resolve-blocked:{_ITEM}:ready" in outcome.detail
    assert "fabro attach" not in outcome.detail


def test_a_later_terminal_node_signature_does_not_hide_the_earlier_causal_stage(
    tmp_path: Path,
) -> None:
    """The terminal's own signature is not a candidate cause of its own firing."""
    outcome = _outcome(
        tmp_path=tmp_path,
        signatures={_TERMINAL_SIGNATURE: 1, _PR_SIGNATURE: 2},
    )

    assert "stage pr" in outcome.detail
    assert "stage needs_human" not in outcome.detail
    assert _TERMINAL_SIGNATURE not in outcome.detail
    assert _PR_SIGNATURE in outcome.detail
