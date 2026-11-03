"""A helper absence after a resume is read from the run's own log by `run_dispatch`.

The engine records the sandbox re-acquisition in the run's `run.log`, which
neither the client stderr nor the failure detail carries.  Only the engine and
its export leave the process; the evidence read and the terminal classification
are production code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    DispatchOutcome,
    FabroRunResult,
    JournalWriter,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
)

_RUN_ID = "01REACQUIREDRUN"
_REPO_ROOT = Path(__file__).parents[2]
_WORKFLOW = _REPO_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml"
_CONFIG = '{"livespec-orchestrator-beads-fabro":{"compat":{"pinned":"master"}}}'
_RESUME_LOG = "INFO fencing a recorded sandbox\nINFO scope environment acquired\n"


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Launcher:
    stderr: str

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(exit_code=1, stdout=f"Run: {_RUN_ID}\n", stderr=self.stderr),
            run_id=_RUN_ID,
        )


@dataclass(kw_only=True)
class _Runner:
    run_log: str
    dumps: int = 0

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
        if argv[:2] == ["synthetic-fabro", "inspect"]:
            record = {
                "run_id": _RUN_ID,
                "status": {"kind": "failed", "reason": "workflow_error"},
                "conclusion": {
                    "status": "failed",
                    "failure": {
                        "reason": "workflow_error",
                        "detail": {"category": "deterministic", "message": "script failed"},
                    },
                },
            }
            return CommandResult(exit_code=0, stdout=json.dumps([record]), stderr="")
        if argv[:2] == ["synthetic-fabro", "dump"]:
            self.dumps += 1
            _ = (Path(argv[argv.index("-o") + 1]) / "run.log").write_text(
                self.run_log, encoding="utf-8"
            )
        return CommandResult(exit_code=0, stdout="", stderr="")


def _dispatch(*, root: Path, stderr: str, run_log: str) -> tuple[DispatchOutcome, _Runner]:
    repo = root / "repo"
    repo.mkdir(parents=True)
    plan = build_plan(
        repo=repo,
        work_item_id="reacquired-run",
        workflow_toml=_WORKFLOW,
        goal_file=root / "goal.md",
        fabro_bin="synthetic-fabro",
        janitor=("mise", "exec", "--", "just", "check"),
        janitor_checkout=root / "janitor",
        config_text=_CONFIG,
        default_branch="master",
    )
    runner = _Runner(run_log=run_log)
    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=_Journal(),
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0),
        fabro_launcher=_Launcher(stderr=stderr),
    )
    return outcome, runner


def test_a_helper_absence_with_resume_evidence_in_the_run_log_is_a_transient_host_fault(
    tmp_path: Path,
) -> None:
    outcome, runner = _dispatch(
        root=tmp_path, stderr="LIVESPEC_PROOF_GRADE_PROGRAM_ABSENT", run_log=_RESUME_LOG
    )

    assert runner.dumps == 1
    assert outcome.status == "host-fault-release"
    assert outcome.fabro_failure_category == "transient_infra"


def test_a_helper_absence_on_a_run_that_was_never_resumed_is_not_released(
    tmp_path: Path,
) -> None:
    outcome, runner = _dispatch(
        root=tmp_path,
        stderr="LIVESPEC_PROOF_GRADE_PROGRAM_ABSENT",
        run_log="INFO scope environment acquired\n",
    )

    assert runner.dumps == 1
    assert outcome.status != "host-fault-release"


def test_a_run_that_signalled_no_missing_helper_exports_no_log(tmp_path: Path) -> None:
    outcome, runner = _dispatch(root=tmp_path, stderr="", run_log=_RESUME_LOG)

    assert runner.dumps == 0
    assert outcome.status != "host-fault-release"
