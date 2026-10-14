"""Terminal preservation comes from stage events, not the client's stderr."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
    inspect_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

_RUN = "01M4WSZ0B50B9QKMEEMNEYPQJC"
_REF = "refs/heads/needs-human/e3466246c2a84f0093457fc16d9ff426"
_SERVER = "https://hp.example:32276"
_TERMINAL_FAILURE = "stage needs_human failed with no outgoing fail edge"


@dataclass(kw_only=True)
class EventRunner:
    """Only the event read carries the terminal's emitted preservation line."""

    calls: list[list[str]] = field(default_factory=list)
    events_exit: int = 0
    events: object = field(
        default_factory=lambda: [
            {
                "event": "stage.failed",
                "node_id": "needs_human",
                "properties": {
                    "failure": {
                        "message": (
                            "Script failed with exit code: 1\n\n## output\n"
                            f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_REF}\n"
                            "LIVESPEC_NEEDS_HUMAN: loop cannot auto-resolve this work-item"
                        )
                    }
                },
            }
        ]
    )

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if argv[1] == "events":
            return CommandResult(
                exit_code=self.events_exit, stdout=json.dumps(self.events), stderr=""
            )
        assert argv[1] == "inspect"
        return CommandResult(
            exit_code=0,
            stderr="",
            stdout=json.dumps(
                [
                    {
                        "status": {"kind": "failed"},
                        "conclusion": {"failure": {"causes": [_TERMINAL_FAILURE]}},
                        "checkpoint": {
                            "current_node": "needs_human",
                            "next_node_id": None,
                            "completed_nodes": ["implement", "needs_human"],
                            "node_outcomes": {
                                "implement": {"status": "failed"},
                                "needs_human": {"status": "failed"},
                            },
                        },
                    }
                ]
            ),
        )


@dataclass(kw_only=True)
class Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def terminal_outcome(*, tmp_path: Path, runner: EventRunner) -> DispatchOutcome:
    plan = DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-jtl5ir",
        branch="feat/bd-ib-jtl5ir",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=_SERVER,
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )
    inspect = inspect_run(plan=plan, runner=runner, journal=Journal(), run_id=_RUN)
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=_RUN,
        inspect=inspect,
        exit_code=1,
        stderr="LIVESPEC_NEEDS_HUMAN: loop cannot auto-resolve this work-item",
    )
    assert outcome is not None
    return outcome


def test_preserved_ref_is_read_from_the_terminal_stage_event(*, tmp_path: Path) -> None:
    runner = EventRunner()
    outcome = terminal_outcome(tmp_path=tmp_path, runner=runner)

    assert _REF in outcome.detail
    assert outcome.status == "blocked"
    assert ["fabro", "events", _RUN, "--json", "--server", _SERVER] in runner.calls
