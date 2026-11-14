"""The engine folds a run that ends at the `already_satisfied` dead end as FAILED.

Production Fabro (v0.393, bbe693847) runs petri c6bfd5e38, whose attractor
frontend sets `Completion::TerminalNode(exit)`; the engine folds a run to
Success only when `exit` holds a success-like record. `already_satisfied` has
no edge to `exit` (only `verify_pr` may lead there), so a proved ending
arrives at the Dispatcher with a non-None terminal. The ending is then read
off ONE record: the run's FINAL step-ending record, which must be
`already_satisfied` itself with a success status, and only that node's own
merged output.

The envelope below is the measured Petri-era shape of a succeeded command
step, taken from run 01M7AFVCPSK2GT0W2SWXP3258Z (`implement_commit_settle@1`):
the node on `item.subject.node.name`, the ending `step.finished` at
`item.record.body.event`, the verdict `outcome.status == "success"`, and the
script's output, stderr merged in, at `outcome.output.stdout`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_already_satisfied import (
    already_satisfied_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
)

_BASE = "d" * 40
_LINE = (
    f"LIVESPEC_ALREADY_SATISFIED: base={_BASE} red declared the work already satisfied "
    "on the unchanged dispatch base"
)
_LONG_BASE_LINE = f"LIVESPEC_ALREADY_SATISFIED: base={'d' * 41} red declared the work\n"
_NON_HEX_BASE_LINE = f"LIVESPEC_ALREADY_SATISFIED: base={'g' * 40} red declared the work\n"
_TENANT_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
"""


def _step_finished(*, node: str, status: object, stdout: str) -> dict[str, object]:
    return {
        "run_id": "01RUN",
        "kind": "petri",
        "item": {
            "subject": {"node": {"name": node, "kind": "attractor/command"}},
            "record": {
                "body": {
                    "event": "step.finished",
                    "outcome": {
                        "status": status,
                        "output": {"exit_status": 0, "stdout": stdout, "outcome": "succeeded"},
                    },
                }
            },
        },
    }


def _failed_terminal() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-1",
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="the run never reached exit",
    )


def _plan(*, repo: Path) -> DispatchPlan:
    _ = (repo / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text='{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}',
        default_branch="master",
    )


def _read(*, repo: Path, events: object, text: str = "") -> DispatchOutcome | None:
    return already_satisfied_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo),
        run_id="01RUN",
        terminal=_failed_terminal(),
        text=text,
        events_payload=events,
    )


def test_a_failed_folded_run_whose_final_step_is_a_proved_already_satisfied_is_the_ending(
    tmp_path: Path,
) -> None:
    events = [
        _step_finished(node="red", status="success", stdout="red turn ended\n"),
        _step_finished(node="already_satisfied", status="success", stdout=_LINE + "\n"),
    ]

    outcome = _read(repo=tmp_path, events=events)

    assert outcome is not None
    assert outcome.status == "green"
    assert outcome.stage == "already-satisfied"
    assert outcome.already_satisfied_base == _BASE
    assert outcome.pr_number is None


def test_a_later_non_ending_event_naming_another_node_does_not_move_the_final_step(
    tmp_path: Path,
) -> None:
    """Only a step-ENDING record can be the final step: a later `step.started` (or any other
    event) naming another node leaves the proved `already_satisfied` ending in place."""
    later_start: dict[str, object] = {
        "run_id": "01RUN",
        "kind": "petri",
        "item": {
            "subject": {"node": {"name": "needs_human", "kind": "attractor/command"}},
            "record": {"body": {"event": "step.started"}},
        },
    }
    events = [
        _step_finished(node="already_satisfied", status="success", stdout=_LINE + "\n"),
        later_start,
    ]

    outcome = _read(repo=tmp_path, events=events)

    assert outcome is not None
    assert outcome.already_satisfied_base == _BASE


def test_a_failed_folded_run_whose_final_step_is_another_node_stays_a_failure_however_it_quotes(
    tmp_path: Path,
) -> None:
    """Anti-spoof: the sentinel in the run's text, in an earlier step, or in the final step of
    any other node never makes a failed run the ending."""
    events = [
        _step_finished(node="already_satisfied", status="success", stdout=_LINE + "\n"),
        _step_finished(node="needs_human", status="success", stdout=_LINE + "\n"),
    ]

    assert _read(repo=tmp_path, events=events, text=_LINE) is None


def test_a_final_already_satisfied_step_that_did_not_succeed_stays_a_failure(
    tmp_path: Path,
) -> None:
    events = [
        _step_finished(
            node="already_satisfied",
            status={"failure": {"message": "unprovable"}},
            stdout=_LINE + "\n",
        ),
    ]

    assert _read(repo=tmp_path, events=events, text=_LINE) is None


@pytest.mark.parametrize(
    "events",
    [
        None,
        "not a list",
        [],
        ["not a mapping", {"item": "not a mapping"}],
        [{"item": {"record": {"body": {"event": "step.started"}}}}],
        [{"item": {"subject": {"node": {}}, "record": {"body": {"event": "step.finished"}}}}],
        [_step_finished(node="already_satisfied", status="success", stdout="")],
        [_step_finished(node="already_satisfied", status="success", stdout=_LONG_BASE_LINE)],
        [_step_finished(node="already_satisfied", status="success", stdout=_NON_HEX_BASE_LINE)],
        [
            {
                "item": {
                    "subject": {"node": {"name": "already_satisfied"}},
                    "record": {
                        "body": {
                            "event": "step.finished",
                            "outcome": {"status": "success", "output": {"stdout": 7}},
                        }
                    },
                }
            }
        ],
    ],
)
def test_a_failed_folded_run_with_no_readable_final_ending_stays_a_failure(
    tmp_path: Path, events: object
) -> None:
    """No observation is no ending: an unreadable or absent stream fails closed."""
    assert _read(repo=tmp_path, events=events, text=_LINE) is None


def test_a_succeeded_run_is_still_read_from_its_text_alone(tmp_path: Path) -> None:
    """The green-run path is unchanged: the engine's own success is the authority there."""
    outcome = already_satisfied_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        run_id="01RUN",
        terminal=None,
        text=_LINE,
        events_payload=None,
    )

    assert outcome is not None
    assert outcome.already_satisfied_base == _BASE
