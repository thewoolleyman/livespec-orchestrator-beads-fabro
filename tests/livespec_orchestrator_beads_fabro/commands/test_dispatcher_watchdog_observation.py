"""Tests for the watchdog's per-run observation of an already-bound run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_discovery import (
    DISCOVERY_JOURNAL_STAGE,
    DISCOVERY_REASON_MATCHED,
    DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_observation import (
    BOUND_POLL_JOURNAL_STAGE,
    classify_bound_poll,
    journaled_bound_poll,
    observed_run,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import GOAL_TEXT_ONLY

_PS_ROW = (
    '[{"run_id": "01BOUND", "status": {"kind": "running"}, '
    '"goal": "Work-item: bd-ib-mine\\nRepo: /tmp/repo"}]'
)
_INSPECT_RECORD = '[{"run_id": "01BOUND", "status": {"kind": "running"}}]'


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]]

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Runner:
    """A runner that answers per verb and remembers which verbs were asked.

    The verb list is the load-bearing observation in this module: the rule
    under test is about which call the poll ISSUES, and a runner that simply
    answered whatever it was asked could not tell a per-run read apart from a
    listing that happened to contain the same run.
    """

    argvs: list[list[str]]
    stdout_by_verb: dict[str, str]
    exit_code_by_verb: dict[str, int]

    @property
    def verbs(self) -> list[str]:
        return [argv[1] for argv in self.argvs]

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
        self.argvs.append(argv)
        return CommandResult(
            exit_code=self.exit_code_by_verb.get(argv[1], 0),
            stdout=self.stdout_by_verb.get(argv[1], ""),
            stderr="",
        )


def _port(*, runner: _Runner) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url=None, dev_token=None, environment=None),
        runner=runner,
        cwd=Path("/tmp"),
    )


def _runner(
    *,
    stdout_by_verb: dict[str, str] | None = None,
    exit_code_by_verb: dict[str, int] | None = None,
) -> _Runner:
    return _Runner(
        argvs=[],
        stdout_by_verb=stdout_by_verb if stdout_by_verb is not None else {},
        exit_code_by_verb=exit_code_by_verb if exit_code_by_verb is not None else {},
    )


def _inspect(
    *,
    exit_code: int = 0,
    status_kind: str | None = "running",
) -> FabroInspectResult:
    return FabroInspectResult(
        command=CommandResult(exit_code=exit_code, stdout="", stderr=""),
        payload=None,
        status_kind=status_kind,
        failure=None,
    )


def test_an_unbound_poll_lists_the_factory_because_nothing_else_can_find_the_run() -> None:
    runner = _runner(stdout_by_verb={"ps": _PS_ROW})
    journal = _Journal(records=[])

    run = observed_run(
        work_item_id="bd-ib-mine",
        port=_port(runner=runner),
        journal=journal,
        attribution=GOAL_TEXT_ONLY,
        bound_run_id=None,
    )

    assert runner.verbs == ["ps"]
    assert run is not None
    assert run.run_id == "01BOUND"
    assert [record["stage"] for record in journal.records] == [DISCOVERY_JOURNAL_STAGE]


def test_a_bound_poll_reads_its_run_and_issues_no_listing() -> None:
    """The cost of a poll must not grow with the factory's run history.

    Asserted on the VERB LIST rather than on the returned run, because a build
    that listed AND inspected would return exactly the same run — the whole
    defect is the call that was made, not the answer that came back.
    """
    runner = _runner(stdout_by_verb={"inspect": _INSPECT_RECORD})
    journal = _Journal(records=[])

    run = observed_run(
        work_item_id="bd-ib-mine",
        port=_port(runner=runner),
        journal=journal,
        attribution=GOAL_TEXT_ONLY,
        bound_run_id="01BOUND",
    )

    assert runner.verbs == ["inspect"]
    assert "ps" not in runner.verbs
    assert run is not None
    assert run.run_id == "01BOUND"
    assert [record["stage"] for record in journal.records] == [BOUND_POLL_JOURNAL_STAGE]


def test_a_bound_poll_names_the_bound_run_in_the_command_it_issues() -> None:
    """The read is addressed to the BOUND run, not to whatever the port defaults to.

    Read off the argv rather than off the answer: a port asked about the wrong
    run returns a perfectly well-formed record for that other run, and every
    assertion about the verdict passes on it.
    """
    runner = _runner(stdout_by_verb={"inspect": _INSPECT_RECORD})

    _ = observed_run(
        work_item_id="bd-ib-mine",
        port=_port(runner=runner),
        journal=_Journal(records=[]),
        attribution=GOAL_TEXT_ONLY,
        bound_run_id="01BOUND",
    )

    assert runner.argvs == [["fabro", "inspect", "01BOUND", "--json"]]


def test_classify_bound_poll_matches_a_running_run() -> None:
    outcome = classify_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect_exit_code=0,
        status_kind="running",
    )

    assert outcome.reason == DISCOVERY_REASON_MATCHED
    assert outcome.run is not None
    assert outcome.run.run_id == "01BOUND"
    assert outcome.run.status_kind == "running"
    assert outcome.run.work_item_id == "bd-ib-mine"
    assert outcome.run.goal is None


def test_classify_bound_poll_matches_a_runnable_run_so_the_reaper_still_sees_it() -> None:
    outcome = classify_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect_exit_code=0,
        status_kind="runnable",
    )

    assert outcome.reason == DISCOVERY_REASON_MATCHED
    assert outcome.run is not None


def test_classify_bound_poll_reports_a_terminal_run_and_still_names_its_subject() -> None:
    outcome = classify_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect_exit_code=0,
        status_kind="succeeded",
    )

    assert outcome.reason == DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING
    assert outcome.run is None
    assert outcome.run_id == "01BOUND"
    assert outcome.status_kind == "succeeded"


def test_journaled_bound_poll_records_the_poll_and_returns_the_run() -> None:
    journal = _Journal(records=[])

    run = journaled_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect=_inspect(status_kind="running"),
        journal=journal,
    )

    assert run is not None
    assert journal.records == [
        {
            "work_item_id": "bd-ib-mine",
            "stage": BOUND_POLL_JOURNAL_STAGE,
            "matched": True,
            "reason": DISCOVERY_REASON_MATCHED,
            "run_id": "01BOUND",
            "inspect_exit_code": 0,
            "status_kind": "running",
        }
    ]


def test_journaled_bound_poll_records_a_poll_that_saw_no_actionable_run() -> None:
    journal = _Journal(records=[])

    run = journaled_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect=_inspect(status_kind="failed"),
        journal=journal,
    )

    assert run is None
    assert journal.records == [
        {
            "work_item_id": "bd-ib-mine",
            "stage": BOUND_POLL_JOURNAL_STAGE,
            "matched": False,
            "reason": DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING,
            "run_id": "01BOUND",
            "inspect_exit_code": 0,
            "status_kind": "failed",
        }
    ]
