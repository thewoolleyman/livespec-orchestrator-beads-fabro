"""The engine verdict recovered from the exported log of a lost-store run.

The incident shape is preserved rather than simplified: the run's conclusion is
the engine's zero-status worker exit before a terminal run event, and the run's
own exported log carries the engine's real terminal verdict — a deterministic
failure cycle on `janitor` — logged a second before the store loss.

Only the engine transport leaves the process, so the `fabro dump` seam is
controlled through a runner double that writes the measured export; the
recognition, the log reading, the journal row and the outcome rewrite are
production code.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroFailureDetail,
    FabroInspectResult,
)

_RUN_ID = "01M592T85GVV"
_WORKER_EXIT = "Worker exited before emitting a terminal run event: exit status: 0"
_SIGNATURE = "janitor|deterministic|script failed with exit code 1"
_ENGINE_FAILURE = (
    f"Workflow run failed deterministic failure cycle detected: signature {_SIGNATURE}"
)
_STORE_LOSS = (
    "Failed to write run event error=worker lost canonical run store during append run event"
)
_RUN_LOG = "\n".join(
    (
        "2026-10-19T06:27:30.001Z  INFO janitor completed command exit_code=1",
        f"2026-10-19T06:27:31.222Z ERROR {_ENGINE_FAILURE}",
        f"2026-10-19T06:27:32.701Z  WARN {_STORE_LOSS}",
    )
)
_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_worker_exit_log_cause.py"
)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ExportRunner:
    """Write one export for `fabro dump`, as the measured factory does."""

    log_text: str | None
    exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd
        _ = timeout_seconds
        _ = env
        _ = stdin
        self.calls.append(argv)
        log_text = self.log_text
        if self.exit_code == 0 and log_text is not None:
            _ = (Path(argv[argv.index("-o") + 1]) / "run.log").write_text(
                log_text, encoding="utf-8"
            )
        return CommandResult(exit_code=self.exit_code, stdout="", stderr="")


def _module() -> ModuleType:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_worker_exit_log_cause"
    )


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-pwb564",
        branch="feat/bd-ib-pwb564",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp-xubuntu.perch-rudd.ts.net:32276",
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _inspect() -> FabroInspectResult:
    return FabroInspectResult(
        command=CommandResult(exit_code=0, stdout="", stderr=""),
        payload=[{"run_id": _RUN_ID, "status": {"kind": "failed"}}],
        status_kind="failed",
        failure=FabroFailureDetail(
            cause=_WORKER_EXIT,
            category="deterministic",
            signature=None,
        ),
    )


def _terminal() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-pwb564",
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=f"{_WORKER_EXIT}; category=deterministic",
        fabro_run_id=_RUN_ID,
        fabro_failure_cause=_WORKER_EXIT,
        fabro_failure_category="deterministic",
        fabro_failure_signature=None,
    )


def test_recovered_engine_failure_is_surfaced_as_the_runs_cause(tmp_path: Path) -> None:
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(log_text=_RUN_LOG),
        journal=_RecordingJournal(),
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    assert surfaced is not None
    assert surfaced.fabro_failure_cause == _ENGINE_FAILURE
    assert _WORKER_EXIT not in surfaced.detail
    assert _ENGINE_FAILURE in surfaced.detail


def test_a_recovered_failure_cycle_classifies_the_ending_by_that_cycle(
    tmp_path: Path,
) -> None:
    journal = _RecordingJournal()
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(log_text=_RUN_LOG),
        journal=journal,
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    assert surfaced is not None
    # The cycle the engine named, not the run it reported as terminated: the
    # arriving ending carried no signature at all.
    assert _terminal().fabro_failure_signature is None
    assert surfaced.fabro_failure_signature == _SIGNATURE
    assert surfaced.fabro_failure_category == "deterministic"
    assert f"signature={_SIGNATURE}" in surfaced.detail
    rows = [
        record
        for record in journal.records
        if record.get("stage") == "fabro-worker-exit-engine-failure"
    ]
    assert rows[0].get("failure_cycle_signature") == _SIGNATURE


def test_an_engine_failure_that_is_not_a_failure_cycle_keeps_the_arriving_class(
    tmp_path: Path,
) -> None:
    journal = _RecordingJournal()
    other = "Workflow run failed to persist its terminal state"
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(log_text=f"2026-10-19T06:27:31.222Z ERROR {other}"),
        journal=journal,
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    assert surfaced is not None
    assert surfaced.fabro_failure_cause == other
    assert surfaced.fabro_failure_signature is None
    assert surfaced.fabro_failure_category == "deterministic"
    rows = [
        record
        for record in journal.records
        if record.get("stage") == "fabro-worker-exit-engine-failure"
    ]
    assert rows[0].get("failure_cycle_signature") is None


def test_a_failure_cycle_signature_of_the_wrong_shape_names_no_category(
    tmp_path: Path,
) -> None:
    truncated = "janitor"
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(
            log_text=(
                "2026-10-19T06:27:31.222Z ERROR Workflow run failed deterministic"
                f" failure cycle detected: signature {truncated}"
            )
        ),
        journal=_RecordingJournal(),
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    assert surfaced is not None
    assert surfaced.fabro_failure_signature == truncated
    assert surfaced.fabro_failure_category == "deterministic"


def test_a_failure_cycle_category_replaces_the_conclusions_own_category(
    tmp_path: Path,
) -> None:
    signature = "janitor|transient_infra|script failed with exit code 1"
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(
            log_text=(
                "2026-10-19T06:27:31.222Z ERROR Workflow run failed deterministic"
                f" failure cycle detected: signature {signature}"
            )
        ),
        journal=_RecordingJournal(),
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    assert surfaced is not None
    assert surfaced.fabro_failure_signature == signature
    assert surfaced.fabro_failure_category == "transient_infra"


def test_the_journal_records_the_conclusion_and_the_recovered_failure_separately(
    tmp_path: Path,
) -> None:
    journal = _RecordingJournal()
    _ = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(log_text=_RUN_LOG),
        journal=journal,
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    rows = [
        record
        for record in journal.records
        if record.get("stage") == "fabro-worker-exit-engine-failure"
    ]
    assert len(rows) == 1
    assert rows[0].get("work_item_id") == "bd-ib-pwb564"
    assert rows[0].get("run_id") == _RUN_ID
    # Separate fields, so the row says that the generic conclusion every other
    # surface keeps reporting and the recovered verdict describe ONE run.
    assert rows[0].get("conclusion_cause") == _WORKER_EXIT
    assert rows[0].get("engine_failure") == _ENGINE_FAILURE


def test_an_exported_log_with_no_engine_failure_line_keeps_the_worker_exit_cause(
    tmp_path: Path,
) -> None:
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(log_text=f"2026-10-19T06:27:32.701Z  WARN {_STORE_LOSS}"),
        journal=_RecordingJournal(),
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    assert surfaced == _terminal()


def test_an_export_that_wrote_no_log_keeps_the_worker_exit_cause(tmp_path: Path) -> None:
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(log_text=None),
        journal=_RecordingJournal(),
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    assert surfaced == _terminal()


def test_an_export_that_failed_keeps_the_worker_exit_cause(tmp_path: Path) -> None:
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=_ExportRunner(log_text=_RUN_LOG, exit_code=2),
        journal=_RecordingJournal(),
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=_terminal(),
    )
    assert surfaced == _terminal()


def test_a_conclusion_that_is_not_the_worker_exit_sentence_exports_nothing(
    tmp_path: Path,
) -> None:
    runner = _ExportRunner(log_text=_RUN_LOG)
    terminal = _terminal()
    ordinary = DispatchOutcome(
        work_item_id=terminal.work_item_id,
        status=terminal.status,
        stage=terminal.stage,
        pr_number=None,
        merge_sha=None,
        detail="ACP turn failed; category=deterministic",
        fabro_run_id=_RUN_ID,
        fabro_failure_cause="ACP turn failed",
        fabro_failure_category="deterministic",
        fabro_failure_signature="pr|deterministic|acp turn failed",
    )
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=runner,
        journal=_RecordingJournal(),
        run_id=_RUN_ID,
        inspect=_inspect(),
        terminal=ordinary,
    )
    assert surfaced == ordinary
    assert runner.calls == []


def test_a_live_or_unobserved_run_exports_nothing(tmp_path: Path) -> None:
    runner = _ExportRunner(log_text=_RUN_LOG)
    succeeded = FabroInspectResult(
        command=CommandResult(exit_code=0, stdout="", stderr=""),
        payload=None,
        status_kind="succeeded",
        failure=None,
    )
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=runner,
        journal=_RecordingJournal(),
        run_id=_RUN_ID,
        inspect=succeeded,
        terminal=_terminal(),
    )
    assert surfaced == _terminal()
    assert runner.calls == []


def test_a_green_run_with_no_terminal_outcome_exports_nothing(tmp_path: Path) -> None:
    runner = _ExportRunner(log_text=_RUN_LOG)
    surfaced = _module().worker_exit_engine_failure_outcome(
        plan=_plan(tmp_path=tmp_path),
        runner=runner,
        journal=_RecordingJournal(),
        run_id=None,
        inspect=_inspect(),
        terminal=None,
    )
    assert surfaced is None
    assert runner.calls == []
