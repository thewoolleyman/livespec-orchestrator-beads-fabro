"""Tests for the watchdog's per-run observation of an already-bound run."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_watchdog_observation
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
# The factory's own answer for a run it does not hold, copied from the message
# `fabro dump` printed for run 01M4R5S6GST6XNQA10SGJ9TA2H against
# hp-xubuntu:32276 on 2026-10-12 (recorded on this work-item's own ledger).
_NOT_FOUND_STDERR = "\u00d7 No run found matching '01BOUND' (tried run ID prefix and workflow name)"
# Spelled as LITERALS and bound to the exported names by the cases below,
# because each one's Red predates its constant and a top-level import of a
# name that does not exist yet would make the Red a collection error.
_RUN_NOT_HELD = "run-not-held"
_UNOBSERVABLE = "run-read-unobservable"


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
    stderr_by_verb: dict[str, str]
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
            stderr=self.stderr_by_verb.get(argv[1], ""),
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
    stderr_by_verb: dict[str, str] | None = None,
    exit_code_by_verb: dict[str, int] | None = None,
) -> _Runner:
    return _Runner(
        argvs=[],
        stdout_by_verb=stdout_by_verb if stdout_by_verb is not None else {},
        stderr_by_verb=stderr_by_verb if stderr_by_verb is not None else {},
        exit_code_by_verb=exit_code_by_verb if exit_code_by_verb is not None else {},
    )


def _inspect(
    *,
    exit_code: int = 0,
    status_kind: str | None = "running",
    stderr: str = "",
) -> FabroInspectResult:
    return FabroInspectResult(
        command=CommandResult(exit_code=exit_code, stdout="", stderr=stderr),
        payload=None,
        status_kind=status_kind,
        failure=None,
    )


def test_an_unbound_poll_lists_the_factory_because_nothing_else_can_find_the_run() -> None:
    runner = _runner(stdout_by_verb={"ps": _PS_ROW})
    journal = _Journal(records=[])

    observed = observed_run(
        work_item_id="bd-ib-mine",
        port=_port(runner=runner),
        journal=journal,
        attribution=GOAL_TEXT_ONLY,
        bound_run_id=None,
    )

    run = observed.run
    assert runner.verbs == ["ps"]
    # The listing route reads no per-run record, so it carries none.
    assert observed.record is None
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

    observed = observed_run(
        work_item_id="bd-ib-mine",
        port=_port(runner=runner),
        journal=journal,
        attribution=GOAL_TEXT_ONLY,
        bound_run_id="01BOUND",
    )

    run = observed.run
    assert runner.verbs == ["inspect"]
    assert "ps" not in runner.verbs
    # The per-run read carries its own record, which is what lets a caller read
    # a FIELD of the run without spending a second round trip on it.
    assert observed.record is not None
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
        output=_INSPECT_RECORD,
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
        output=_INSPECT_RECORD,
    )

    assert outcome.reason == DISCOVERY_REASON_MATCHED
    assert outcome.run is not None


def test_classify_bound_poll_reports_a_terminal_run_and_still_names_its_subject() -> None:
    outcome = classify_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect_exit_code=0,
        status_kind="succeeded",
        output=_INSPECT_RECORD,
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


def test_the_run_not_held_reason_is_the_exported_constant() -> None:
    """Bind the literal above to the name the module exports.

    The literal exists because this module's Red predates the constant; this
    case is what stops the two drifting once it does not.
    """
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_observation"
    )

    assert getattr(module, "BOUND_POLL_REASON_RUN_NOT_HELD", None) == _RUN_NOT_HELD
    assert _dispatcher_watchdog_observation is module


def test_a_bound_poll_reports_a_run_the_factory_no_longer_holds() -> None:
    """A factory answering "no such run" is a DISAPPEARANCE, and is named one.

    Distinct from `status-kind-not-running`, which says the factory still
    holds the run and is simply not running it: the two are different facts
    about the factory with different remedies, so collapsing them would make
    a vanished run read as a finished one.
    """
    outcome = classify_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect_exit_code=1,
        status_kind=None,
        output=_NOT_FOUND_STDERR,
    )

    assert outcome.reason == _RUN_NOT_HELD
    assert outcome.run is None
    assert outcome.run_id == "01BOUND"


def test_a_readable_status_wins_over_a_not_found_phrase_inside_the_payload() -> None:
    """A run whose own payload quotes the not-found message is still held.

    `fabro inspect` echoes the run's whole `run_spec`, rendered goal included,
    so the marker can appear in a perfectly healthy reading — this very
    work-item's goal quotes it. The status the read DID yield is therefore
    consulted first, and the marker is only ever read where no status could
    be. Without this case a scan of the whole output passes every other
    assertion here while reporting a live run as vanished.
    """
    outcome = classify_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect_exit_code=0,
        status_kind="running",
        output='[{"run_spec": {"goal": "stderr: No run found matching ..."}}]',
    )

    assert outcome.reason == DISCOVERY_REASON_MATCHED
    assert outcome.run is not None


def test_journaled_bound_poll_records_a_run_the_factory_no_longer_holds() -> None:
    journal = _Journal(records=[])

    run = journaled_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect=_inspect(exit_code=1, status_kind=None, stderr=_NOT_FOUND_STDERR),
        journal=journal,
    )

    assert run is None
    assert journal.records == [
        {
            "work_item_id": "bd-ib-mine",
            "stage": BOUND_POLL_JOURNAL_STAGE,
            "matched": False,
            "reason": _RUN_NOT_HELD,
            "run_id": "01BOUND",
            "inspect_exit_code": 1,
            "status_kind": None,
        }
    ]


def test_a_bound_poll_whose_factory_holds_no_such_run_reports_it_through_the_port() -> None:
    """End to end through the real port: the engine's own refusal is read back."""
    runner = _runner(
        stderr_by_verb={"inspect": _NOT_FOUND_STDERR},
        exit_code_by_verb={"inspect": 1},
    )
    journal = _Journal(records=[])

    observed = observed_run(
        work_item_id="bd-ib-mine",
        port=_port(runner=runner),
        journal=journal,
        attribution=GOAL_TEXT_ONLY,
        bound_run_id="01BOUND",
    )

    assert observed.run is None
    assert runner.verbs == ["inspect"]
    assert [record["reason"] for record in journal.records] == [_RUN_NOT_HELD]


def test_the_unobservable_reason_is_the_exported_constant() -> None:
    """Bind the literal above to the name the module exports."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_observation"
    )

    assert getattr(module, "BOUND_POLL_REASON_UNOBSERVABLE", None) == _UNOBSERVABLE


def test_a_failed_per_run_read_is_unobservable_and_never_a_disappearance() -> None:
    """A read that FAILED observed nothing, so it says nothing about the run.

    The two outcomes it must not be mistaken for are both asserted, because
    each is a confident claim this reading cannot support: `run-not-held`
    says the factory stopped holding the run, and `status-kind-not-running`
    says it answered with a status. Neither happened — the read did.
    """
    outcome = classify_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect_exit_code=1,
        status_kind=None,
        output="error: connection refused",
    )

    assert outcome.reason == _UNOBSERVABLE
    assert outcome.reason != _RUN_NOT_HELD
    assert outcome.reason != DISCOVERY_REASON_STATUS_KIND_NOT_RUNNING
    assert outcome.run is None
    assert outcome.run_id == "01BOUND"


def test_an_answer_the_watchdog_cannot_interpret_is_unobservable() -> None:
    """A read that SUCCEEDED but yielded no readable status is still no reading.

    This is the half a nonzero-exit test cannot reach: the command was fine
    and the payload was not, which is what a shape change in the engine looks
    like. Treating it as a status would let an unparseable answer decide a
    cancel.
    """
    outcome = classify_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect_exit_code=0,
        status_kind=None,
        output='{"unexpected": "shape"}',
    )

    assert outcome.reason == _UNOBSERVABLE
    assert outcome.run is None


def test_journaled_bound_poll_records_an_unobservable_read() -> None:
    journal = _Journal(records=[])

    run = journaled_bound_poll(
        work_item_id="bd-ib-mine",
        run_id="01BOUND",
        inspect=_inspect(exit_code=1, status_kind=None, stderr="error: connection refused"),
        journal=journal,
    )

    assert run is None
    assert journal.records == [
        {
            "work_item_id": "bd-ib-mine",
            "stage": BOUND_POLL_JOURNAL_STAGE,
            "matched": False,
            "reason": _UNOBSERVABLE,
            "run_id": "01BOUND",
            "inspect_exit_code": 1,
            "status_kind": None,
        }
    ]


def test_an_unreachable_factory_reports_unobservable_through_the_port() -> None:
    """End to end: a factory that cannot be reached has not lost the run."""
    runner = _runner(
        stderr_by_verb={"inspect": "error: connection refused"},
        exit_code_by_verb={"inspect": 1},
    )
    journal = _Journal(records=[])

    observed = observed_run(
        work_item_id="bd-ib-mine",
        port=_port(runner=runner),
        journal=journal,
        attribution=GOAL_TEXT_ONLY,
        bound_run_id="01BOUND",
    )

    assert observed.run is None
    assert [record["reason"] for record in journal.records] == [_UNOBSERVABLE]
