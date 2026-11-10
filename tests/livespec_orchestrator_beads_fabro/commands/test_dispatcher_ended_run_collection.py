"""Tests for collection of ended sandboxes after their item closes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_ended_run_collection import (
    collect_closed_ended_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preservation_ref_deletion import (
    JOURNAL_STAGE_DELETION_FAILED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary


@dataclass(kw_only=True)
class _Runner:
    calls: list[list[str]] = field(default_factory=list)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr=self.stderr)


@dataclass(kw_only=True)
class _Forge:
    """The forge's reference interface: lists refs by prefix, records deletions."""

    refs: tuple[str, ...] = ()
    refuse_delete: frozenset[str] = frozenset()
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if "DELETE" in argv:
            ref = "refs/" + argv[-1].removeprefix("/repos/{owner}/{repo}/git/refs/")
            if ref in self.refuse_delete:
                return CommandResult(exit_code=1, stdout="", stderr="HTTP 422")
            return CommandResult(exit_code=0, stdout="", stderr="")
        prefix = "refs/" + argv[3].removeprefix("/repos/{owner}/{repo}/git/matching-refs/")
        listed = [ref for ref in self.refs if ref.startswith(prefix)]
        return CommandResult(exit_code=0, stdout="\n".join(listed) + "\n", stderr="")

    @property
    def deleted(self) -> list[str]:
        return [
            "refs/" + call[-1].split("/git/refs/", 1)[1] for call in self.calls if "DELETE" in call
        ]


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_collects_only_ended_runs_of_closed_items_and_journals_the_provider_result(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01CLOSED", status_kind="succeeded"),
                _run(run_id="01BLOCKED", status_kind="succeeded"),
                _run(run_id="01CLEARANCE", status_kind="succeeded"),
                _run(run_id="01LIVE", status_kind="running"),
            ),
            statuses={"bd-ib-closed": "done", "bd-ib-blocked": "blocked"},
            stamps=(("01CLOSED", "bd-ib-closed"), ("01BLOCKED", "bd-ib-blocked")),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert runner.calls == [["fabro", "rm", "01CLOSED", "--server", "https://factory.test"]]
    assert journal.records == [
        {
            "stage": "ended-run-collected",
            "run_id": "01CLOSED",
            "factory_name": "factory",
            "factory_server_url": "https://factory.test",
            "work_item_id": "bd-ib-closed",
            "work_item_status": "done",
            "rm_exit_code": 0,
            "rm_stdout": "",
            "rm_stderr": "",
        }
    ]


def test_dry_run_leaves_an_ended_closed_run_and_its_journal_unchanged(tmp_path: Path) -> None:
    runner = _Runner()
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="failed"),),
            statuses={"bd-ib-closed": "closed"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=True,
    )

    assert (runner.calls, journal.records) == ([], [])


def test_failed_provider_delete_is_journaled_for_the_next_collection_pass(tmp_path: Path) -> None:
    runner = _Runner(exit_code=1)
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="dead"),),
            statuses={"bd-ib-closed": "done"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert journal.records[0]["rm_exit_code"] == 1


def test_journal_carries_the_bounded_rm_response_for_diagnosis_and_retry(tmp_path: Path) -> None:
    runner = _Runner(
        exit_code=1,
        stdout="Preserved: sandbox_preserved\n" + "x" * 5000,
        stderr="lease lease-1: prune failed",
    )
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="failed"),),
            statuses={"bd-ib-closed": "done"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    record = journal.records[0]
    stdout = record["rm_stdout"]
    assert isinstance(stdout, str)
    assert stdout.startswith("Preserved: sandbox_preserved")
    assert 0 < len(stdout) < 5000
    assert record["rm_stderr"] == "lease lease-1: prune failed"


def test_targeted_pass_collects_only_its_own_items_closed_runs(tmp_path: Path) -> None:
    runner = _Runner()
    forge = _Forge()
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01MINE", status_kind="succeeded"),
                _run(run_id="01OTHER", status_kind="succeeded"),
            ),
            statuses={"bd-ib-mine": "done", "bd-ib-other": "done"},
            stamps=(("01MINE", "bd-ib-mine"), ("01OTHER", "bd-ib-other")),
            only_work_item_id="bd-ib-mine",
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert runner.calls == [["fabro", "rm", "01MINE", "--server", "https://factory.test"]]
    assert [record["run_id"] for record in journal.records] == ["01MINE"]


def _inventory(
    *,
    runs: tuple[FabroRunSummary, ...],
    statuses: dict[str, str],
    stamps: tuple[tuple[str, str], ...],
    only_work_item_id: str | None = None,
) -> FactoryRunInventory:
    return FactoryRunInventory(
        runs=runs,
        item_statuses=statuses,
        journaled=journaled_runs(
            text="\n".join(
                f'{{"stage":"dispatch-run-stamp","run_id":"{run_id}","work_item_id":"{item_id}"}}'
                for run_id, item_id in stamps
            )
        ),
        id_prefix="bd-ib",
        factory_name="factory",
        factory_server_url="https://factory.test",
        only_work_item_id=only_work_item_id,
    )


def _port(*, tmp_path: Path, runner: _Runner) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.test"),
        runner=runner,
        cwd=tmp_path,
    )


def _run(*, run_id: str, status_kind: str) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind=status_kind,
        goal=None,
        total_usd_micros=None,
    )


def test_collecting_a_closed_items_run_deletes_its_refs_and_not_an_open_items(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    forge = _Forge(
        refs=(
            "refs/livespec/wip/bd-ib-closed/01CLOSED/1",
            "refs/livespec/wip/bd-ib-closed/01OLDER/1",
            "refs/livespec/preserved-publish/bd-ib-closed/abc123",
            "refs/heads/needs-human/01CLOSED",
            "refs/livespec/wip/bd-ib-blocked/01BLOCKED/1",
            "refs/livespec/preserved-publish/bd-ib-blocked/def456",
            "refs/heads/needs-human/01BLOCKED",
        )
    )

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01CLOSED", status_kind="failed"),
                _run(run_id="01BLOCKED", status_kind="failed"),
            ),
            statuses={"bd-ib-closed": "done", "bd-ib-blocked": "blocked"},
            stamps=(("01CLOSED", "bd-ib-closed"), ("01BLOCKED", "bd-ib-blocked")),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=_Journal(),
        dry_run=False,
    )

    assert forge.deleted == [
        "refs/livespec/wip/bd-ib-closed/01CLOSED/1",
        "refs/livespec/preserved-publish/bd-ib-closed/abc123",
        "refs/heads/needs-human/01CLOSED",
    ]
    assert runner.calls == [["fabro", "rm", "01CLOSED", "--server", "https://factory.test"]]


def test_dry_run_deletes_no_preservation_ref(tmp_path: Path) -> None:
    forge = _Forge(refs=("refs/heads/needs-human/01CLOSED",))

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="failed"),),
            statuses={"bd-ib-closed": "closed"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=_Runner()),
        runner=forge,
        repo=tmp_path,
        journal=_Journal(),
        dry_run=True,
    )

    assert forge.calls == []


def test_a_refused_ref_deletion_is_journaled_and_leaves_the_run_for_the_next_pass(
    tmp_path: Path,
) -> None:
    refused = "refs/heads/needs-human/01CLOSED"
    runner = _Runner()
    forge = _Forge(refs=(refused,), refuse_delete=frozenset({refused}))
    journal = _Journal()

    collect_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01CLOSED", status_kind="failed"),),
            statuses={"bd-ib-closed": "done"},
            stamps=(("01CLOSED", "bd-ib-closed"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        repo=tmp_path,
        journal=journal,
        dry_run=False,
    )

    assert runner.calls == []
    assert [(record["stage"], record["ref"]) for record in journal.records] == [
        (JOURNAL_STAGE_DELETION_FAILED, refused)
    ]
