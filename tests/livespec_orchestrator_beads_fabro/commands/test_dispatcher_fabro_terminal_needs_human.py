"""The needs-human marker reaches the ledger on BOTH engines, from two channels.

Plan `fabro-currency` P4 (`bd-ib-227cbw`). The workflow's `needs_human` terminal
prints `LIVESPEC_NEEDS_HUMAN` from a goal-gated script node and exits non-green,
and the Dispatcher turns that sentinel into the `blocked` outcome that rests the
work-item at `blocked / needs-human`. WHERE the sentinel can be read differs by
engine, and that is the whole point of these two tests:

- On the pinned 0.254 engine the node's own stderr is the channel. The engine's
  structured failure says only `goal gate unsatisfied for node fail and no retry
  target` (research note 007, probe p6, run 01M4DCXHTECH), so the marker is
  nowhere in the inspect payload and the raw `fabro run` stderr carries it.
- On the Petri-era candidate (v0.378.0-nightly.0, `64b9d88`) the script's stderr
  is lifted INTO `conclusion.failure.detail.message` (research note 007, probes
  p2 and p6, runs 01M4DCR2T008 and 01M4DCSSJM6C), and the `fabro run` stderr the
  Dispatcher sees need not carry it at all.

The Petri fixture below transcribes the key set measured on that binary — status
`{kind, reason}`, a conclusion keyed `diff, final_git_commit_sha, stages, status,
timestamp, timing, total_retries`, and `conclusion.failure` keyed `{reason,
detail: {message, category}}` with NO `causes` and NO `signature` (research note
006 and the P3 rider on the work-item). What the notes do not record is the exact
concatenation the engine builds the message from, only that it carries the marker
line, so the assertion is on the ROUTING, never on the sentence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroTarget,
)

_MARKER_LINE = "LIVESPEC_NEEDS_HUMAN: the acceptance criteria name a scenario heading"
_PETRI_RUN_ID = "01M4DCSSJM6C"
_LEGACY_RUN_ID = "01M4DCXHTECH"

# The candidate's terminal conclusion for a goal-gated script node that failed:
# the script's own stderr arrives in `conclusion.failure.detail.message`.
_PETRI_NEEDS_HUMAN_PAYLOAD: list[dict[str, Any]] = [
    {
        "run_id": _PETRI_RUN_ID,
        "parent_id": None,
        "status": {"kind": "failed", "reason": "workflow_error"},
        "stages": ["001-start@1", "002-needs_human@1"],
        "conclusion": {
            "diff": None,
            "final_git_commit_sha": "9bcd4faa2e3c4d5f6071829304a5b6c7d8e9f012",
            "stages": ["001-start@1", "002-needs_human@1"],
            "status": "failed",
            "timestamp": "2026-10-08T12:41:09.813442271Z",
            "timing": {"wall_time_ms": 41231},
            "total_retries": 0,
            "failure": {
                "reason": "workflow_error",
                "detail": {
                    "message": f"script exited with status 1\n{_MARKER_LINE}",
                    "category": "deterministic",
                },
            },
        },
    }
]

# The pinned engine's terminal conclusion for the SAME graph: the engine names
# the unsatisfied goal gate and never carries the node's own output.
_LEGACY_NEEDS_HUMAN_PAYLOAD: list[dict[str, Any]] = [
    {
        "run_id": _LEGACY_RUN_ID,
        "parent_id": None,
        "status": {"kind": "failed", "reason": "workflow_error"},
        "conclusion": {
            "timestamp": "2026-10-08T12:39:58.112094552Z",
            "status": "failed",
            "failure": {
                "reason": "workflow_error",
                "detail": {
                    "message": "goal gate unsatisfied for node fail and no retry target",
                    "category": "deterministic",
                },
            },
        },
    }
]


@dataclass(kw_only=True)
class _Runner:
    stdout: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _inspect(*, tmp_path: Path, payload: list[dict[str, Any]]) -> FabroInspectResult:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=_Runner(stdout=json.dumps(payload)),
        cwd=tmp_path,
    ).inspect(run_id="01RUN", timeout_seconds=1)


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-227cbw",
        branch="feat/bd-ib-227cbw",
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


def test_petri_needs_human_marker_in_the_conclusion_message_blocks_the_item(
    tmp_path: Path,
) -> None:
    """The candidate's only channel is the structured message; stderr is empty."""
    inspect = _inspect(tmp_path=tmp_path, payload=_PETRI_NEEDS_HUMAN_PAYLOAD)

    assert inspect.failure is not None
    assert inspect.failure.cause is not None
    assert _MARKER_LINE in inspect.failure.cause

    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_PETRI_RUN_ID,
        inspect=inspect,
        exit_code=1,
        stderr="",
    )

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.stage == "fabro-run"
    assert outcome.fabro_run_id == _PETRI_RUN_ID
    assert f"refs/heads/needs-human/{_PETRI_RUN_ID}" not in outcome.detail
    assert "dump pointer is the only preservation" in outcome.detail


def test_legacy_needs_human_marker_on_run_stderr_still_blocks_the_item(
    tmp_path: Path,
) -> None:
    """The 0.254 route is unchanged: the payload has no marker, the stderr does."""
    inspect = _inspect(tmp_path=tmp_path, payload=_LEGACY_NEEDS_HUMAN_PAYLOAD)

    assert inspect.failure is not None
    assert inspect.failure.cause is not None
    assert _MARKER_LINE not in inspect.failure.cause

    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_LEGACY_RUN_ID,
        inspect=inspect,
        exit_code=1,
        stderr=f"{_MARKER_LINE}\nnode fail exited 1",
    )

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.fabro_run_id == _LEGACY_RUN_ID
    assert f"refs/heads/needs-human/{_LEGACY_RUN_ID}" not in outcome.detail
    assert "dump pointer is the only preservation" in outcome.detail
