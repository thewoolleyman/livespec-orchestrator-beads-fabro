"""A run that ends on the recapture cap rests at needs-human, not at needs-regroom.

Work-item `bd-ib-iy4cd4`. `non_converged` used to print the janitor cap line for
every cap, so a proof record that kept failing review was bounced to `backlog`
for re-grooming. The Dispatcher now recognises the recapture-cap line, rests the
item at `blocked` / `needs-human`, and the durable cause comment names the marker
and the recurring proof-record findings.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NON_CONVERGED_MARKER,
    DispatchPlan,
    is_non_convergence_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recapture_exhausted import (
    RECAPTURE_EXHAUSTED_MARKER,
    recapture_exhausted_outcome,
    recapture_exhausted_reason,
)

_RUN_ID = "01M5YH9P9REX"
_FINDING = "- [BLOCKING] (proof-record) step 2 runs a helper no step creates"
_ROUTE_LINE = (
    f"{RECAPTURE_EXHAUSTED_MARKER}: review has ended with a recapture verdict 3 times in this "
    "run, so the captured record is not converging on the proof-record findings the reviewer "
    "raised; routing to non_converged without entering proof_capture again"
)
_TERMINAL_LINE = (
    f"{RECAPTURE_EXHAUSTED_MARKER}: recapture cap hit, review ended with a recapture verdict "
    "three times without converging on the proof-record findings; recurring proof-record "
    f"findings: {_FINDING} ; routing back to the Dispatcher for needs-human proof-record repair"
)
_JANITOR_LINE = (
    f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit without converging; routing back to the "
    "Dispatcher for needs-regroom"
)


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-iy4cd4",
        branch="feat/bd-ib-iy4cd4",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=None,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _terminal(*, tmp_path: Path, stderr: str) -> DispatchOutcome:
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN_ID,
        inspect=None,
        exit_code=1,
        stderr=stderr,
    )
    assert outcome is not None
    return outcome


def test_the_terminal_cause_line_is_read_as_the_reason(tmp_path: Path) -> None:
    """The LAST marker line is the terminal's, and it carries the findings."""
    reason = recapture_exhausted_reason(text=f"{_ROUTE_LINE}\n{_TERMINAL_LINE}\n")

    assert reason is not None
    assert reason.startswith(RECAPTURE_EXHAUSTED_MARKER)
    assert _FINDING in reason
    assert recapture_exhausted_reason(text=_JANITOR_LINE) is None
    assert (
        recapture_exhausted_outcome(
            outcome_type=DispatchOutcome,
            plan=_plan(tmp_path=tmp_path),
            run_id=_RUN_ID,
            text=_JANITOR_LINE,
        )
        is None
    )


def test_a_recapture_cap_ending_rests_at_needs_human_and_is_not_a_bounce(
    tmp_path: Path,
) -> None:
    """Assertion 2: blocked, not the non-convergence bounce to backlog."""
    outcome = _terminal(tmp_path=tmp_path, stderr=f"{_ROUTE_LINE}\n{_TERMINAL_LINE}\n")

    assert outcome.status == "blocked"
    assert outcome.stage == "fabro-run"
    assert outcome.fabro_run_id == _RUN_ID
    assert outcome.needs_human_kind is not None
    assert not is_non_convergence_outcome(outcome=outcome)
    assert RECAPTURE_EXHAUSTED_MARKER in outcome.detail
    assert "needs-regroom" not in outcome.detail


def test_the_ledger_comment_names_the_marker_and_the_recurring_findings(
    tmp_path: Path,
) -> None:
    """Assertion 2: the durable cause record carries both."""
    outcome = _terminal(tmp_path=tmp_path, stderr=f"{_ROUTE_LINE}\n{_TERMINAL_LINE}\n")

    body = needs_human_cause_body(outcome=outcome)

    assert RECAPTURE_EXHAUSTED_MARKER in body
    assert _FINDING in body
    assert "janitor fix-loop cap" not in body


def test_a_janitor_cap_ending_is_still_a_non_convergence_bounce(tmp_path: Path) -> None:
    """Assertion 3: the janitor cap routes exactly as before."""
    outcome = _terminal(tmp_path=tmp_path, stderr=_JANITOR_LINE)

    assert outcome.status == "failed"
    assert is_non_convergence_outcome(outcome=outcome)
