"""Tier 1 Enemy Unit Tests for live Fabro run semantics.

This suite launches real workflows and can spend real runtime. It is
deliberately excluded from `just fabro-enemy-tier0` and `just check`; invoke it
explicitly:

    just fabro-enemy-tier1
"""

from __future__ import annotations

from pathlib import Path

from _tier0_support import (
    TIMEOUT_SECONDS,
    _assert_success,
    _FabroTier0Config,
    _inspect_record,
)
from _tier1_support import (
    _await_run_absent_from_ps,
    _event_name,
    _event_records,
    _failure_block,
    _has_event_timestamp,
    _terminal_outcome,
    _write_goal,
    _write_workflow,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = []

_RUN_TIMEOUT_SECONDS = 300.0
_PASSING_WORKFLOW = """
digraph FabroEnemyPassing {
    start [shape=Mdiamond, label="Start"]
    done [shape=parallelogram, label="Done", script="echo fabro-enemy-tier1-pass"]
    exit [shape=Msquare, label="Exit"]
    start -> done
    done -> exit
}
"""
# A script node's non-zero exit does NOT by itself fail the run: fabro routes
# the node's outcome along its outgoing edges, so `fail -> exit` alone would
# carry a failed node straight to the success terminal and the run reports
# SUCCEEDED (measured on 0.254.0 / 8de6611 AND on 0.378.0-nightly.0 / 64b9d88).
# The earlier fixture made `fail` a dead end with no outgoing edge; the
# Petri-era engine refuses such a graph at run creation
# (`attractor.exit_unreachable`, measured 2026-10-08), so the fixture now fails
# the run through `goal_gate=true`, which both engines honour: a goal-gated node
# that exits non-zero fails the run deterministically even though an edge to
# `exit` exists.
_FAILING_WORKFLOW = """
digraph FabroEnemyFailing {
    start [shape=Mdiamond, label="Start"]
    fail [shape=parallelogram, label="Fail", goal_gate=true, script="echo fabro-enemy-tier1-fail >&2; exit 1"]
    exit [shape=Msquare, label="Exit"]
    start -> fail
    fail -> exit
}
"""
_SLEEPING_WORKFLOW = """
digraph FabroEnemySleeping {
    start [shape=Mdiamond, label="Start"]
    sleep [shape=parallelogram, label="Sleep", timeout="600s", script="sleep 600"]
    exit [shape=Msquare, label="Exit"]
    start -> sleep
    sleep -> exit
}
"""


def test_preflight_accepts_the_tier1_minimal_run_configuration(
    *,
    tmp_path: Path,
    port: FabroPort,
) -> None:
    workflow = _write_workflow(tmp_path=tmp_path, name="passing", body=_PASSING_WORKFLOW)
    goal = _write_goal(tmp_path=tmp_path, title="preflight")

    # Preflight validates repository access, which on a first run for a branch
    # clones the repo into the sandbox and can exceed the 30s `TIMEOUT_SECONDS`
    # used for the cheap read-only verbs; give it the full run budget.
    result = port.preflight(
        workflow_toml=workflow,
        goal_file=goal,
        inputs=(),
        timeout_seconds=_RUN_TIMEOUT_SECONDS,
    )

    _assert_success(command=result.command)
    assert result.payload is not None


def test_completed_run_maps_to_green_terminal_path_and_emits_liveness_events(
    *,
    tmp_path: Path,
    config: _FabroTier0Config,
    port: FabroPort,
) -> None:
    workflow = _write_workflow(tmp_path=tmp_path, name="passing", body=_PASSING_WORKFLOW)
    goal = _write_goal(tmp_path=tmp_path, title="completed")

    run = port.run(
        workflow_toml=workflow,
        goal_file=goal,
        inputs=(),
        timeout_seconds=_RUN_TIMEOUT_SECONDS,
    )

    _assert_success(command=run.command)
    assert run.run_id is not None
    inspect = port.inspect(run_id=run.run_id, timeout_seconds=TIMEOUT_SECONDS)
    _assert_success(command=inspect.command)
    assert (
        _terminal_outcome(
            config=config,
            inspect=inspect,
            run_id=run.run_id,
            exit_code=run.command.exit_code,
            stderr=run.command.stderr,
        )
        is None
    )
    events = port.events(run_id=run.run_id, timeout_seconds=TIMEOUT_SECONDS)
    _assert_success(command=events.command)
    event_records = _event_records(stdout=events.command.stdout, payload=events.payload)
    assert any(_has_event_timestamp(event=event) for event in event_records)
    assert any(_event_name(event=event) is not None for event in event_records)


def test_failed_run_maps_to_failed_terminal_path_and_structured_failure_block(
    *,
    tmp_path: Path,
    config: _FabroTier0Config,
    port: FabroPort,
) -> None:
    workflow = _write_workflow(tmp_path=tmp_path, name="failing", body=_FAILING_WORKFLOW)
    goal = _write_goal(tmp_path=tmp_path, title="failed")

    run = port.run(
        workflow_toml=workflow,
        goal_file=goal,
        inputs=(),
        timeout_seconds=_RUN_TIMEOUT_SECONDS,
    )

    assert run.command.exit_code != 0
    assert run.run_id is not None
    inspect = port.inspect(run_id=run.run_id, timeout_seconds=TIMEOUT_SECONDS)
    _assert_success(command=inspect.command)
    outcome = _terminal_outcome(
        config=config,
        inspect=inspect,
        run_id=run.run_id,
        exit_code=run.command.exit_code,
        stderr=run.command.stderr,
    )
    assert outcome is not None
    assert outcome.status == "failed"
    record = _inspect_record(value=inspect.payload)
    failure = _failure_block(value=record)
    assert failure is not None
    # The structured failure block nests the classifier fields under `detail`
    # (measured 0.254.0: `{"reason": ..., "detail": {"category": ...,
    # "message": ...}}`); the production reader in `_fabro_port_records.py`
    # reads them from there, so assert them where they actually live.
    detail = failure.get("detail")
    assert isinstance(detail, dict)
    assert any(key in detail for key in ("category", "signature", "causes"))


def test_force_remove_in_flight_run_removes_it_from_ps(
    *,
    tmp_path: Path,
    port: FabroPort,
) -> None:
    workflow = _write_workflow(tmp_path=tmp_path, name="sleeping", body=_SLEEPING_WORKFLOW)
    goal = _write_goal(tmp_path=tmp_path, title="force-remove")

    # The sleeping workflow never completes within the budget, so `port.run`
    # returns when the CLI is killed at the timeout, carrying the run id parsed
    # from the launch output while the server keeps the run in flight. Keep the
    # window short -- long enough to capture the id, not the full run budget
    # (which would just block until the timeout since the run never ends).
    run = port.run(
        workflow_toml=workflow,
        goal_file=goal,
        inputs=(),
        timeout_seconds=TIMEOUT_SECONDS,
    )
    assert run.run_id is not None
    rm = port.rm(run_id=run.run_id, timeout_seconds=TIMEOUT_SECONDS)
    _assert_success(command=rm.command)

    # `fabro rm -f` removes the run from `ps -a` outright rather than leaving it
    # listed with a terminated status, so the force-removed run must disappear.
    assert _await_run_absent_from_ps(port=port, run_id=run.run_id)
