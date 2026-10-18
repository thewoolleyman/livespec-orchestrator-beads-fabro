"""Scenario 173 — the progress watchdog observes its bound run by id.

Binds `SPECIFICATION/scenarios.md` "Scenario 173 — The progress watchdog
observes its bound run by id and never lists the factory's run history",
and the `contracts.md` paragraph it exercises (the Dispatcher progress
watchdog's "Observing the run").

The journey is driven through the PRODUCTION launcher — a real
`WatchedFabroLauncher`, a real `FabroPort`, the real per-poll observation
seam, the real dispatch-run stamp and the real threading — against a
scripted `CommandRunner` and an in-memory tenant. Only the fabro subprocess
is stood in, and it is stood in at the ARGV, which is the whole point: the
rule under test is about which call each poll ISSUES, and nothing about a
returned run can distinguish a per-run read from a listing that happened to
contain the same row.

Each case reads the verb sequence AND the journal, because neither alone is
the claim. The verbs say what the poll spent; the journal says what the
watchdog concluded from it, and the clause's two hardest requirements —
that a vanished run is NAMED as one, and that an unreadable read is NOT —
live entirely in that conclusion.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import WatchedFabroLauncher
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem

from tests.conftest import end_run_and_await_launcher_return

_WORK_ITEM_ID = "bd-ib-6pdigz"
_RUN_ID = "01M4BOUNDRUN"
# The factory's listing, carrying the one row this dispatch owns. Reachable
# only on the FIRST poll once the rule holds.
_PS_LISTING = json.dumps(
    [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "running"},
            "goal": f"Work-item: {_WORK_ITEM_ID}\nRepo: /tmp/repo",
        },
        {
            "run_id": "01SOMEONEELSE",
            "status": {"kind": "running"},
            "goal": "Work-item: bd-ib-other\nRepo: /tmp/other",
        },
    ]
)
_EVENTS = json.dumps([{"timestamp": "2026-10-13T09:00:00Z"}])
# The factory's own refusal for a run it does not hold, as `fabro` printed it
# against hp-xubuntu:32276 on 2026-10-12 for run 01M4R5S6GST6XNQA10SGJ9TA2H.
# The leading glyph is the cross fabro prefixes its error lines with, spelled
# by code point so the linter's ambiguous-character rule has nothing to flag.
_NOT_FOUND = f"\u00d7 No run found matching '{_RUN_ID}' (tried run ID prefix and workflow name)"
_UNREACHABLE = "error: request failed with status 502 Bad Gateway"


def _inspect_record(*, status_kind: str) -> str:
    return json.dumps([{"run_id": _RUN_ID, "status": {"kind": status_kind}}])


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _FactoryRunner:
    """The fabro CLI, scripted at the argv against one factory.

    `fabro run` BLOCKS until `run_done` so the foreground watch loop really
    polls, exactly as a long run makes it. `inspect_readings` is the per-poll
    sequence of `(exit_code, stdout, stderr)` the per-run read answers with,
    clamped to the last entry so a case states only the readings it cares
    about. Every argv is kept whole rather than reduced to a verb, because a
    read addressed to the wrong run answers perfectly well.

    `run_returned` is this fake's OWN account of returning, and no case waits
    on it: it fires before `port.run` has returned and so before the launcher
    has published anything, which is one step too early to read as the run
    being over (bd-ib-spc6xr). `end_run_and_await_launcher_return` waits on
    the launcher's own thread instead.
    """

    inspect_readings: list[tuple[int, str, str]]
    argvs: list[list[str]] = field(default_factory=list)
    run_done: threading.Event = field(default_factory=threading.Event)
    run_returned: threading.Event = field(default_factory=threading.Event)
    _inspects: int = 0

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
        # Dispatched rather than laddered, and with no fallthrough arm: a verb
        # this fake does not script is a KeyError naming it, which is louder
        # than a scripted "unexpected argv" result the launcher would read as
        # an ordinary probe failure. `rm` is deliberately absent — no case here
        # cancels, and `rm` in `verbs` is how each one says so.
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        return {
            "run": self._run,
            "ps": self._ps,
            "inspect": self._inspect,
            "events": self._events,
        }[argv[1]]()

    def _run(self) -> CommandResult:
        _ = self.run_done.wait(timeout=10.0)
        self.run_returned.set()
        return CommandResult(exit_code=0, stdout=f"    Run: {_RUN_ID}\n", stderr="")

    def _ps(self) -> CommandResult:
        return CommandResult(exit_code=0, stdout=_PS_LISTING, stderr="")

    def _events(self) -> CommandResult:
        return CommandResult(exit_code=0, stdout=_EVENTS, stderr="")

    def _inspect(self) -> CommandResult:
        index = min(self._inspects, len(self.inspect_readings) - 1)
        self._inspects += 1
        exit_code, stdout, stderr = self.inspect_readings[index]
        return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr)


@pytest.fixture(autouse=True)
def _hermetic_tenant() -> None:
    reset_fake_singleton()


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib", "tenant": "t", "fake": True}
                }
            }
        ),
        encoding="utf-8",
    )
    append_work_item(
        path=store_config(repo=repo),
        item=WorkItem(
            id=_WORK_ITEM_ID,
            type="bug",
            status="active",
            title="Run watchdog polls the whole Fabro run history every 30 s",
            description="A dispatched slice, claimed and in flight.",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee="fabro",
            depends_on=(),
            captured_at="2026-10-12T07:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
    )
    return repo


def _launch(
    *,
    tmp_path: Path,
    inspect_readings: list[tuple[int, str, str]],
    polls_before_the_run_ends: int,
) -> tuple[_FactoryRunner, _Journal]:
    """Drive the production launcher for a bounded number of polls."""
    runner = _FactoryRunner(inspect_readings=inspect_readings)
    journal = _Journal()
    slept = {"polls": 0}

    def _sleep(_seconds: float) -> None:
        # The watch loop sleeps BEFORE each poll, so the run is released on
        # the sleep AFTER the last poll this case wants — and the release
        # WAITS for the launcher itself to observe that return, so the loop
        # cannot take one more sample while the launcher is still publishing
        # its result. Every case below still asserts a FLOOR and the shape of
        # the tail rather than an exact poll count, because the floor is what
        # each clause is about; it is no longer a concession to that race.
        slept["polls"] += 1
        if slept["polls"] > polls_before_the_run_ends:
            end_run_and_await_launcher_return(run_done=runner.run_done, work_item_id=_WORK_ITEM_ID)

    repo = _repo(tmp_path=tmp_path)
    _ = WatchedFabroLauncher(sleep=_sleep, clock=lambda: 0.0).launch(
        plan=build_plan(
            repo=repo,
            work_item_id=_WORK_ITEM_ID,
            workflow_toml=repo / "workflow.toml",
            goal_file=repo / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=repo / "janitor",
            fabro_factory_name="hp",
            fabro_factory_server="https://hp-xubuntu.perch-rudd.ts.net:32276",
        ),
        runner=runner,
        journal=journal,
    )
    return runner, journal


def _poll_records(*, journal: _Journal) -> list[dict[str, object]]:
    return [
        record
        for record in journal.records
        if record.get("stage") in {"watchdog-discovery-poll", "watchdog-bound-poll"}
    ]


def test_scenario173_a_bound_run_is_polled_by_id_and_the_history_is_never_listed_again(
    tmp_path: Path,
) -> None:
    """One listing to discover the run; every poll after it reads that run by id.

    Both halves of the clause are asserted on ONE dispatch, because they are
    one rule: the listing is permitted before the bind and forbidden after
    it, and a fixture that showed only the second half could not tell a
    correct build from one that never discovered its run at all.

    The listing carries a SECOND factory row that belongs to another item.
    That is what makes the discovery leg a real attribution rather than a
    single-row lookup, and it is also the cost this change removes — on hp
    that list was 1,605 rows and 9-17 s per call, against 1.1-1.5 s for the
    per-run read.
    """
    runner, journal = _launch(
        tmp_path=tmp_path,
        inspect_readings=[(0, _inspect_record(status_kind="running"), "")],
        polls_before_the_run_ends=3,
    )

    first_inspect = runner.verbs.index("inspect")
    assert runner.verbs.count("ps") == 1
    assert runner.verbs.index("ps") < first_inspect
    assert "ps" not in runner.verbs[first_inspect:]
    first_read = next(argv for argv in runner.argvs if argv[1] == "inspect")
    assert first_read[:3] == ["fabro", "inspect", _RUN_ID]
    stages = [record["stage"] for record in _poll_records(journal=journal)]
    assert len(stages) >= 3
    assert stages[0] == "watchdog-discovery-poll"
    assert set(stages[1:]) == {"watchdog-bound-poll"}
    assert {record["run_id"] for record in _poll_records(journal=journal)} == {_RUN_ID}
    assert "rm" not in runner.verbs


def test_scenario173_a_terminal_bound_run_is_still_detected(tmp_path: Path) -> None:
    """The run reaches a terminal state and the per-run read reports it as one."""
    runner, journal = _launch(
        tmp_path=tmp_path,
        inspect_readings=[
            (0, _inspect_record(status_kind="running"), ""),
            (0, _inspect_record(status_kind="succeeded"), ""),
        ],
        polls_before_the_run_ends=4,
    )

    bound = [r for r in _poll_records(journal=journal) if r["stage"] == "watchdog-bound-poll"]
    reasons = [record["reason"] for record in bound]
    assert len(reasons) >= 2
    assert reasons[0] == "matched"
    assert set(reasons[1:]) == {"status-kind-not-running"}
    assert [record["status_kind"] for record in bound][-1] == "succeeded"
    assert [record["matched"] for record in bound][-1] is False
    assert "rm" not in runner.verbs


def test_scenario173_a_run_the_factory_no_longer_holds_is_still_detected(
    tmp_path: Path,
) -> None:
    """The factory answers "no such run", and the poll names the disappearance.

    Asserted against the OTHER two non-matching reasons as well, because the
    clause's whole content here is that the three stay apart: a vanished run,
    a run the factory still holds but is no longer running, and a read that
    observed nothing all produce `matched: False` and would satisfy a
    boolean-only assertion identically.
    """
    _, journal = _launch(
        tmp_path=tmp_path,
        inspect_readings=[(1, "", _NOT_FOUND)],
        polls_before_the_run_ends=3,
    )

    bound = [r for r in _poll_records(journal=journal) if r["stage"] == "watchdog-bound-poll"]
    assert bound
    assert {record["reason"] for record in bound} == {"run-not-held"}
    assert {record["matched"] for record in bound} == {False}


def test_scenario173_a_failed_per_run_read_is_not_a_disappearance(tmp_path: Path) -> None:
    """An unreachable factory has not lost the run, and the record must not say it has.

    The positive assertion and the two negative ones carry different weight.
    `run-read-unobservable` is what the clause asks for; `!= run-not-held` is
    what it FORBIDS, and that is the expensive direction — a confident claim
    that the factory dropped the run, earned from a read that saw nothing.
    """
    _, journal = _launch(
        tmp_path=tmp_path,
        inspect_readings=[(1, "", _UNREACHABLE)],
        polls_before_the_run_ends=3,
    )

    bound = [r for r in _poll_records(journal=journal) if r["stage"] == "watchdog-bound-poll"]
    assert bound
    assert {record["reason"] for record in bound} == {"run-read-unobservable"}
    assert "run-not-held" not in {record["reason"] for record in bound}
    assert {record["matched"] for record in bound} == {False}
